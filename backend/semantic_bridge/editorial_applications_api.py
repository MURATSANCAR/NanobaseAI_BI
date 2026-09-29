"""M1 başvuru ve yayın kurulu uçları: `/api/v1/editorial/applications/*` ve `/api/v1/editorial/board-sessions/*`.

Yetki: sayfa kuralı `access.RULES` (Başvurular + Yayın kurulu); başvuruya yazan her istek `ozellik:basvuru.yaz`
ister (`access.FEATURE_RULES`). Açıkça verilen iki özellik uçların içinde denetlenir: `ozellik:basvuru.yonet`
(başkasına atama, başkasının başvurusunda karar/rapor, yeniden açma) ve `ozellik:yayin-kurulu.yonet` (oturum açma,
her oturumu yönetme). Oturumun başkanı kendi oturumunu yetkisiz yönetir; üye yalnız kendi oyunu verir.
Her yazma `semantic_audit`'e düşer.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from semantic_bridge import editorial_applications as mod
from semantic_bridge import editorial_applications_market as mkt
from semantic_bridge import sorgu_izi as IZ

# Kurul oturumu ekranının «i» hesabı (045c5aa8 bu adı ve IZ'yi kullanıyordu ama tanımlamamıştı: oturum detayı her
# açılışta 500 veriyordu).
T_OTURUM = ("Kurul oturumu: gündemdeki başvurular, üyelerin oyları ve puanları (misyon, yayıncılık, ticari; 0–100), "
            "başvuru başına ortalama puan ve öneri eşikleri portaldaki kurul, gündem ve oy kayıtlarından hesaplanır; "
            "karar başkanın kaydıdır.")

log = logging.getLogger("semantic.editorial_applications")

A = "/api/v1/editorial/applications"
S = "/api/v1/editorial/board-sessions"
MARKET_MAX_AGE_HOURS = 24
_categories: dict[str, Any] = {"at": 0.0, "items": None}
_cat_lock = threading.Lock()


def register(app, deps: dict[str, Any]) -> None:
    """deps: session(request)→(engine, tenant, user, display) · can(user, key) · audit · conf ·
    connection_files()→{"logo","crm"} · run(sql)→run_sql sonucu · person(schema, run, contact_id)."""
    session: Callable[[Request], tuple[Any, str, str, str]] = deps["session"]
    can: Callable[[str, str], bool] = deps["can"]
    audit = deps["audit"]
    conf = deps["conf"]
    connection_files = deps["connection_files"]
    run_catalog = deps["run"]
    person = deps["person"]
    runner = mkt.ReportRunner()
    state = {"reset": set()}

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        engine, tenant, user, display = session(request)
        first = id(engine) not in mod._ready
        mod.ensure(engine)
        if first and id(engine) not in state["reset"]:
            state["reset"].add(id(engine))
            n = mod.reset_stale_reports(engine)
            if n:
                log.warning("kurul raporu: %d yarıda kalan hazırlık hata olarak işaretlendi", n)
        return engine, tenant, user, display or user

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except mod.ApplicationError as e:
            raise HTTPException(status_code=e.status, detail={"code": "APPLICATION", "message": str(e)}) from e
        except mkt.MarketError as e:
            raise HTTPException(status_code=e.status, detail={"code": "APPLICATION_MARKET", "message": str(e)}) from e

    def thresholds() -> tuple[int, int]:
        def num(key: str, default: int) -> int:
            try:
                return max(0, min(100, int(conf(key) or default)))
            except ValueError:
                return default
        acc, rev = num("EDITORIAL_BOARD_ACCEPT_SCORE", mod.DEFAULT_ACCEPT), num("EDITORIAL_BOARD_REVISE_SCORE", mod.DEFAULT_REVISE)
        return (acc, min(rev, acc))

    def manager(user: str) -> bool:
        return can(user, "ozellik:basvuru.yonet")

    def board_manager(user: str) -> bool:
        return can(user, "ozellik:yayin-kurulu.yonet")

    def names(user: str) -> bool:
        return can(user, "ozellik:yayin-kurulu.gorusler")

    def schema() -> str:
        return conf("CRM_SCHEMA")

    def connector(name: str):
        from semantic_layer.profiler.connectors import connector_from_file
        path = connection_files().get(name)
        if not path:
            raise mkt.MarketError(("CRM" if name == "crm" else "Logo") + " bağlantısı bu kurulumda tanımlı değil.")
        conn = connector_from_file(path)
        conn.query_timeout = 900
        return conn

    def crm_rows(sql: str) -> list[dict[str, Any]]:
        conn = connector("crm")
        try:
            _, rows, _ = conn.execute(sql, 1_000_000)
            return rows
        except mkt.MarketError:
            raise
        except Exception as e:  # noqa: BLE001 — sürücü metni günlüğe, kişiye düz cümle
            log.warning("başvuru: CRM okunamadı: %s", str(e)[:300])
            raise mkt.MarketError("CRM'e şu an ulaşılamıyor; birazdan yeniden deneyin.") from e
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------------------------------ başvuru

    @app.get(f"{A}/meta")
    def applications_meta(request: Request) -> dict[str, Any]:
        _, _, user, display = ctx(request)
        acc, rev = thresholds()
        return dict(mod.meta(acc, rev), me={
            "username": user, "display": display, "canWrite": can(user, "ozellik:basvuru.yaz"),
            "canManage": manager(user), "canRunBoard": board_manager(user), "canSeeNames": names(user)})

    @app.get(f"{A}/categories")
    def applications_categories(request: Request) -> dict[str, Any]:
        ctx(request)
        with _cat_lock:
            if _categories["items"] is not None and time.monotonic() - _categories["at"] < 3600:
                return {"items": _categories["items"]}
        rows = call(crm_rows, mkt.categories_sql(schema()))
        items = [{"id": str(r.get("id")).lower(), "name": str(r.get("ad") or "").strip(), "books": int(r.get("kitap") or 0)}
                 for r in rows if r.get("id") and str(r.get("ad") or "").strip()]
        with _cat_lock:
            _categories.update(at=time.monotonic(), items=items)
        return {"items": items}

    @app.get(A)
    def applications_list(request: Request, view: str = "kuyruk", q: str = "", status: str = "", mine: bool = False) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return call(mod.listing, engine, tenant, user, view=view, q=q, status=status, mine=mine)

    @app.post(A, status_code=201)
    def applications_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        out = call(mod.create, engine, tenant, user, display, body)
        audit(engine, user, "create", "application", out["id"], f"{out['no']} {out['title']}", {"yazar": out["authorName"]})
        return out

    @app.get(A + "/{app_id}")
    def applications_detail(app_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return call(mod.detail, engine, tenant, user, app_id, can_see_names=names(user))

    @app.patch(A + "/{app_id}")
    def applications_update(app_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        out, diff = call(mod.update, engine, tenant, user, display, app_id, body)
        if diff:
            audit(engine, user, "update", "application", out["id"], f"{out['no']} {out['title']}", diff)
        return out

    @app.put(A + "/{app_id}/files", status_code=201)
    async def applications_file_add(app_id: str, request: Request, filename: str = "", kind: str = "dosya") -> dict[str, Any]:
        engine, tenant, user, display = await run_in_threadpool(ctx, request)
        length = int(request.headers.get("content-length") or 0)
        if length > mod.FILE_MAX:
            raise HTTPException(status_code=413, detail={"code": "APPLICATION", "message": "Dosya 10 MB sınırını aşıyor."})
        data = await request.body()
        out = await run_in_threadpool(call, mod.add_file, engine, tenant, user, display, app_id, filename, kind, data)
        audit(engine, user, "upload", "application_file", app_id, out["filename"], {"bytes": out["bytes"], "tur": out["kindLabel"]})
        return out

    @app.get(A + "/files/{file_id}")
    def applications_file(file_id: str, request: Request) -> FileResponse:
        engine, tenant, _, _ = ctx(request)
        f = call(mod.file_for, engine, tenant, file_id)
        return FileResponse(f["path"], media_type=f["mime"], filename=f["filename"],
                            headers={"Cache-Control": "private, no-store"})

    @app.delete(A + "/files/{file_id}")
    def applications_file_delete(file_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        out = call(mod.delete_file, engine, tenant, user, display, file_id)
        audit(engine, user, "delete", "application_file", out["appId"], out["filename"], None)
        return {"ok": True}

    @app.post(A + "/{app_id}/assign")
    def applications_assign(app_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        who = body.get("evaluator") or user
        who_name = body.get("evaluatorName") or (display if str(who).lower() == user else None)
        out = call(mod.assign, engine, tenant, user, display, app_id, who, who_name, manager=manager(user))
        audit(engine, user, "assign", "application", out["id"], f"{out['no']} {out['title']}", {"editor": out["evaluatorName"]})
        return out

    @app.put(A + "/{app_id}/evaluation")
    def applications_evaluation(app_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        out = call(mod.save_evaluation, engine, tenant, user, display, app_id, body, manager=manager(user))
        audit(engine, user, "submit" if body.get("submit") else "update", "application_evaluation", app_id, None,
              {"oneri": out["recommendation"], "tamam": out["submitted"]})
        return out

    @app.post(A + "/{app_id}/decision")
    def applications_decision(app_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        action = str(body.get("action") or "")
        out = call(mod.editor_decision, engine, tenant, user, display, app_id, action, body.get("note"), manager=manager(user))
        audit(engine, user, "decide", "application", out["id"], f"{out['no']} {out['title']}", {"karar": action})
        if action == "kurula":
            # İş tanımı: «Yayın Kurulu Raporu otomatik üretilir».
            _start_report(engine, tenant, user, app_id, force=False)
        elif action in ("red", "revizyon"):
            call(mod.create_letter, engine, tenant, user, display, app_id, action, if_missing=True)
        return out

    @app.post(A + "/{app_id}/reopen")
    def applications_reopen(app_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        out = call(mod.reopen, engine, tenant, user, display, app_id, body.get("note"), manager=manager(user))
        audit(engine, user, "reopen", "application", out["id"], f"{out['no']} {out['title']}", {"tur": out["round"]})
        return out

    @app.get(A + "/{app_id}/overlap")
    def applications_overlap(app_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        a = call(mod.snapshot, engine, tenant, app_id)["app"]
        sql = call(mkt.overlap_sql, schema(), a["title"], a["crmContactId"])
        items = mkt.overlap_rows(call(crm_rows, sql)) if sql else []
        return {"items": items, "words": mkt._words(a["title"])}

    @app.get(A + "/{app_id}/similar")
    def applications_similar(app_id: str, request: Request, n: int = 10) -> dict[str, Any]:
        """Katalogda anlamca benzer kitaplar (ortak yapı taşı 5): başvurunun adı, türü, kategorisi ve özeti ile kitap
        benzerliği dizini. Başlık-kelime örtüşmesinin yanına; benzerlik yalnız sıralama, rakam yok. Özet gömmeye
        maskelenerek gider (kişisel veri)."""
        from semantic_bridge import book_similarity as BS
        from semantic_bridge import zeki_text as Z

        if not 1 <= n <= 50:
            raise HTTPException(status_code=400, detail={"code": "APPLICATION", "message": "Kitap sayısı 1–50 olmalı."})
        engine, tenant, _, _ = ctx(request)
        a = call(mod.snapshot, engine, tenant, app_id)["app"]
        parts = [a.get("title") or "", f"Tür: {a['genre']}" if a.get("genre") else "",
                 f"Kitaplık: {a['categoryName']}" if a.get("categoryName") else "", Z.mask_personal(a.get("summary") or "")]
        text = ". ".join(p for p in parts if p.strip())
        try:
            out = BS.similar_books(engine, tenant, metin=text, n=n,
                                   suzgec={"baglam": {"kitaplik": a.get("categoryName"), "turler": a.get("genre")}})
        except BS.SimilarityError as e:
            raise HTTPException(status_code=e.status, detail={"code": "APPLICATION", "message": str(e)}) from e
        out["ozetVar"] = bool((a.get("summary") or "").strip())
        return out

    @app.post(A + "/{app_id}/crm-project")
    def applications_crm_project(app_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        pid = str(body.get("projectId") or "").strip().strip("{}")
        name = None
        if pid:
            rows = call(crm_rows, call(mkt.project_sql, schema(), pid))
            if not rows:
                raise HTTPException(status_code=404, detail={"code": "APPLICATION", "message": "Proje CRM'de bulunamadı."})
            name = str(rows[0].get("ad") or "").strip() or None
        out = call(mod.link_crm_project, engine, tenant, user, display, app_id, pid, name)
        audit(engine, user, "update", "application", out["id"], f"{out['no']} {out['title']}", {"crmProje": name})
        return out

    # ------------------------------------------------------------------------------- yayın kurulu raporu

    def _start_report(engine, tenant: str, user: str, app_id: str, *, force: bool) -> dict[str, Any]:
        rid = call(mod.start_report, engine, tenant, user, app_id)
        if rid is None:
            return {"status": "hazirlaniyor", "already": True}

        def job() -> None:
            problems: list[str] = []
            try:
                snap = mod.snapshot(engine, tenant, app_id)
                a = snap["app"]
                market = None
                if not a["categoryId"]:
                    problems.append("Kategori seçilmemiş; benzer kitap satışı, senaryolar ve baskı önerisi hesaplanmadı.")
                else:
                    market = None if force else mod.market_cached(engine, tenant, a["categoryId"], MARKET_MAX_AGE_HOURS)
                    if market is None:
                        crm, logo = connector("crm"), connector("logo")
                        try:
                            market = mkt.market(a["categoryId"], a["categoryName"], schema(), crm, logo,
                                                datetime.now(timezone.utc).date())
                        finally:
                            for c in (crm, logo):
                                try:
                                    c.close()
                                except Exception:  # noqa: BLE001
                                    pass
                        mod.market_store(engine, tenant, a["categoryId"], market)
                    if market.get("missingYears"):
                        problems.append("Logo'da " + ", ".join(map(str, market["missingYears"])) + " satış görünümü yok; bu yıllar okunmadı.")
                    if market["withSales"] == 0:
                        problems.append("Kategoride dönemde satışı görülen kitap yok; senaryo hesaplanamadı.")
                overlap = None
                try:
                    sql = mkt.overlap_sql(schema(), a["title"], a["crmContactId"])
                    overlap = mkt.overlap_rows(crm_rows(sql)) if sql else []
                except mkt.MarketError as e:
                    problems.append(f"Katalog örtüşmesi okunamadı: {e}")
                author_crm = None
                if a["crmContactId"]:
                    try:
                        author_crm = person(schema(), run_catalog, a["crmContactId"])
                    except Exception as e:  # noqa: BLE001
                        log.warning("kurul raporu: yazarın CRM geçmişi okunamadı: %s", str(e)[:300])
                        problems.append("Yazarın CRM geçmişi okunamadı.")
                content = mkt.build_report(snap, market, overlap, author_crm, problems, user)
                mod.finish_report(engine, rid, content, None)
            except mkt.MarketError as e:
                mod.finish_report(engine, rid, None, str(e))
            except Exception as e:  # noqa: BLE001 — ayrıntı günlükte
                log.exception("kurul raporu üretilemedi (%s)", app_id)
                text = str(e)
                msg = ("Logo ya da CRM'e şu an ulaşılamıyor; birazdan yeniden üretin."
                       if any(k in text for k in ("08S01", "08001", "HYT00", "HYT01", "timeout", "Login")) else
                       "Rapor üretilirken beklenmeyen bir hata oldu; yöneticiye bildirin.")
                mod.finish_report(engine, rid, None, msg)

        runner.start(job, app_id)
        return {"status": "hazirlaniyor", "id": rid}

    @app.post(A + "/{app_id}/report")
    def applications_report_start(app_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = _start_report(engine, tenant, user, app_id, force=bool(body.get("refresh")))
        audit(engine, user, "run", "application_report", app_id, None, {"yenile": bool(body.get("refresh"))})
        return out

    @app.get(A + "/{app_id}/report")
    def applications_report(app_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(mod.report, engine, tenant, app_id)

    # --------------------------------------------------------------------------------------------- yazışma

    @app.post(A + "/{app_id}/letters", status_code=201)
    def applications_letter_create(app_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        out = call(mod.create_letter, engine, tenant, user, display, app_id, body.get("kind") or None)
        audit(engine, user, "create", "application_letter", app_id, out["kindLabel"], None)
        return out

    @app.patch(A + "/letters/{letter_id}")
    def applications_letter_update(letter_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return call(mod.update_letter, engine, tenant, user, letter_id, body)

    @app.post(A + "/letters/{letter_id}/{action}")
    def applications_letter_action(letter_id: str, action: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        out = call(mod.letter_state, engine, tenant, user, display, letter_id, action, body)
        audit(engine, user, action, "application_letter", letter_id, out.get("kindLabel"), {"durum": out.get("state")})
        return out

    # -------------------------------------------------------------------------------------- kurul oturumu

    @app.get(S)
    def board_sessions(request: Request, state: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return call(mod.sessions, engine, tenant, user, state=state)

    @app.post(S, status_code=201)
    def board_session_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        if not board_manager(user):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Kurul oturumu açmak «yayın kurulu yönetimi» yetkisi ister."})
        out = call(mod.create_session, engine, tenant, user, display, body)
        audit(engine, user, "create", "board_session", out["id"], out["title"], {"uye": len(out["members"])})
        return out

    @app.get(S + "/{sid}")
    def board_session(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        acc, rev = thresholds()
        return IZ.izli(engine, lambda: call(mod.session_detail, engine, tenant, user, sid, manager=board_manager(user),
                                            can_see_names=names(user), accept=acc, revise=rev),
                       prefix="portal.kurul.oturum", title="Yayın kurulu oturumu", text=T_OTURUM)

    @app.patch(S + "/{sid}")
    def board_session_update(sid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        out, diff = call(mod.update_session, engine, tenant, user, display, sid, body, manager=board_manager(user))
        if diff:
            audit(engine, user, "update", "board_session", out["id"], out["title"], diff)
        return out

    @app.delete(S + "/{sid}")
    def board_session_delete(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(mod.delete_session, engine, tenant, user, sid, manager=board_manager(user))
        audit(engine, user, "delete", "board_session", out["id"], out["title"], None)
        return {"ok": True}

    @app.post(S + "/{sid}/agenda")
    def board_agenda_add(sid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        app_id = str(body.get("applicationId") or "")
        out = call(mod.add_to_agenda, engine, tenant, user, display, sid, app_id, manager=board_manager(user))
        audit(engine, user, "agenda_add", "board_session", sid, out["session"], {"basvuru": out["title"]})
        return out

    @app.delete(S + "/{sid}/agenda/{app_id}")
    def board_agenda_remove(sid: str, app_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        out = call(mod.remove_from_agenda, engine, tenant, user, display, sid, app_id, manager=board_manager(user))
        audit(engine, user, "agenda_remove", "board_session", sid, None, {"basvuru": out["title"]})
        return out

    @app.put(S + "/{sid}/votes/{app_id}")
    def board_vote(sid: str, app_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        out = call(mod.vote, engine, tenant, user, display, sid, app_id, body)
        # Oyun kendisi değil, verildiği kaydedilir (gizlilik: denetim kaydını gören herkes oyu görmesin).
        audit(engine, user, "vote", "board_session", sid, None, {"basvuru": app_id})
        return out

    @app.post(S + "/{sid}/decisions/{app_id}")
    def board_decide(sid: str, app_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        out = call(mod.decide, engine, tenant, user, display, sid, app_id, body, manager=board_manager(user))
        audit(engine, user, "decide", "board_session", sid, None, {"basvuru": app_id, "karar": out.get("decision")})
        if out.get("decision") in ("kabul", "red", "revizyon"):
            call(mod.create_letter, engine, tenant, user, display, app_id, out["decision"], if_missing=True)
        return out

    @app.post(S + "/{sid}/close")
    def board_close(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        out = call(mod.close_session, engine, tenant, user, display, sid, manager=board_manager(user))
        audit(engine, user, "close", "board_session", sid, None, {"ertelendi": out["postponed"]})
        return out


__all__ = ["register"]
