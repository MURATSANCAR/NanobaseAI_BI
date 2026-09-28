"""H2 Okuyucu veri tabanı uçları: /api/v1/readers/*.

Sayfa kapısı `access.RULES` (`sayfa:okurlar`). İşlem yetkileri (`FEATURE_RULES`): birleştirme kararı ve kaynak
yenileme `ozellik:okur.birlestir`; segment taslağı/düzenleme/onaya gönderme/arşiv ve Zeki önerisi
`ozellik:okur.segment`; etkinlik dosyası `ozellik:okur.ice-aktar`; liste ve «CRM'e işlenecek» CSV'si
`ozellik:veri.disa-aktar`. Açıkça verilenler burada, ucun içinde denetlenir: kişisel veriyi açık görmek
(`ozellik:okur.kisisel-veri` — okur kartında ad/e-posta/telefon, ada göre arama, KVKK başvurusu), segment onayı
(`ozellik:okur.segment-onay`; yazan onaylayamaz), liste dışa aktarımı (`ozellik:okur.liste-aktar`).

Kişisel veri her görüntülendiğinde ve her dışa aktarımda `semantic_audit`'e yazılır.

Sözleşme uçları (M24 bülten, M37 topluluk, M35 kampanya): `GET /api/v1/readers/contract/segments` (onaylı segmentler)
ve `GET /api/v1/readers/contract/segments/{id}/summary` (yalnız sayılar).

Zamanlayıcı (`timas-readers.timer`, her gece 03:20) yalnız `POST /api/v1/readers/run-due`'yu çağırır: CRM okuması,
kesin birleştirme, izin kanıtları, belirsiz adaylar, onaylı segmentlerin günlük sayısı, süresi dolan yükleme
satırlarının silinmesi, kaynak hatası / kuyruk / dışa aktarım özeti e-postası (iç alıcılar).

Model çağrısı yalnız LLM kapısından: `rt.llm_for("readers", NORMAL)` (segment taslağı). Modele kişisel veri gitmez.
"""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import readers as R
from semantic_bridge import readers_imports as imp
from semantic_bridge import readers_segments as seg
from semantic_bridge import readers_sources as src

log = logging.getLogger("semantic.readers.api")
P = "/api/v1/readers"
F_PERSONAL = "ozellik:okur.kisisel-veri"
F_MERGE = "ozellik:okur.birlestir"
F_SEGMENT = "ozellik:okur.segment"
F_APPROVE = "ozellik:okur.segment-onay"
F_LIST = "ozellik:okur.liste-aktar"
F_IMPORT = "ozellik:okur.ice-aktar"
F_EXPORT = "ozellik:veri.disa-aktar"

_job: dict[str, Any] = {"running": False, "step": None, "startedAt": None, "finishedAt": None, "error": None, "result": None}
_job_lock = threading.Lock()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None], can: Callable[[str, str], bool]):
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod

    def crm_path() -> str:
        return os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")

    def schema() -> str:
        return admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo"

    def crm():
        return src.runner(crm_path())

    def llm():
        try:
            from semantic_layer.runtime.llm_queue import NORMAL
            return rt().llm_for("readers", NORMAL)
        except Exception:  # noqa: BLE001 — model tanımlı değil
            return None

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        require_caller(request)
        try:
            user, display = board_mod.session_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        r = rt()
        R.ensure(r.store.engine)
        admin_mod.ensure(r.store.engine)
        return r.store.engine, r.settings.tenant_id, user, display

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except R.ReadersError as e:
            raise HTTPException(status_code=e.status, detail={"code": "READERS", "message": str(e)}) from e
        except src.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "READERS_SOURCE", "message": str(e)}) from e

    def need(user: str, key: str, what: str) -> None:
        if not can(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def audit(engine, user, action, kind, oid, title, detail=None) -> None:
        admin_mod.audit(engine, user, action, kind, oid, title, detail)

    def personal_reader() -> Callable[[list[tuple[str, str]]], dict[tuple[str, str], dict[str, Any]]]:
        return lambda keys: src.read_personal(crm(), schema(), keys)

    def csv_response(name: str, data: bytes) -> Response:
        return Response(content=data, media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})

    # ------------------------------------------------------------------ okuma turu

    def run_sync(engine, tenant: str) -> dict[str, Any]:
        cfg = R.settings()
        R.salt()                                                    # tuz yoksa CRM hiç okunmaz
        bundle = src.read_all(crm(), schema(), cfg)
        return R.sync(engine, tenant, bundle, cfg)

    def start_refresh(engine, tenant: str) -> bool:
        with _job_lock:
            if _job["running"]:
                return False
            _job.update(running=True, step="CRM okunuyor", startedAt=_iso_now(), finishedAt=None, error=None, result=None)

        def work() -> None:
            try:
                res = run_sync(engine, tenant)
                with _job_lock:
                    _job.update(result={k: res[k] for k in ("readers", "links", "merged", "candidates") if k in res})
            except (R.ReadersError, src.SourceError) as e:
                R.record_sync_error(engine, tenant, "crm_contact", str(e))
                with _job_lock:
                    _job.update(error=str(e))
            except Exception as e:  # noqa: BLE001
                log.exception("okur okuma turu düştü")
                with _job_lock:
                    _job.update(error=f"Okuma tamamlanamadı: {str(e)[:200]}")
            finally:
                with _job_lock:
                    _job.update(running=False, step=None, finishedAt=_iso_now())

        threading.Thread(target=work, name="readers-sync", daemon=True).start()
        return True

    # ------------------------------------------------------------------ genel

    @app.get(P + "/meta")
    def readers_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        cfg = R.settings()
        with _job_lock:
            job = dict(_job)
        return {
            "me": {"username": user, "display": display, "canPersonal": can(user, F_PERSONAL), "canMerge": can(user, F_MERGE),
                   "canSegment": can(user, F_SEGMENT), "canApprove": can(user, F_APPROVE), "canList": can(user, F_LIST),
                   "canImport": can(user, F_IMPORT), "canExport": can(user, F_EXPORT)},
            "channels": R.CHANNEL_LABELS, "statuses": R.STATUS_LABELS, "sources": R.SOURCE_LABELS,
            "origins": R.ORIGIN_LABELS, "segmentStatuses": seg.STATUS_LABELS, "excludeLabels": seg.EXCLUDE_LABELS,
            "importRoles": imp.ROLES, "importRowStatuses": imp.ROW_STATUS, "opLabels": seg.OP_LABELS,
            "settings": {"requireKvkk": cfg["requireKvkk"], "minorAge": cfg["minorAge"], "minorExport": cfg["minorExport"],
                         "exportEnabled": cfg["exportEnabled"], "importRetentionDays": cfg["importRetentionDays"],
                         "okSources": cfg["okSources"], "fileMaxMb": cfg["fileMaxMb"], "staleHours": cfg["staleHours"]},
            "job": job, "modelVar": llm() is not None,
        }

    @app.get(P + "/overview")
    def readers_overview(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(R.overview, engine, tenant)

    @app.get(P + "/sources")
    def readers_sources(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {"sources": R.sources_state(engine, tenant), "run": R.last_run(engine, tenant)}

    @app.get(P + "/mine")
    def readers_mine(request: Request) -> dict[str, Any]:
        """Kampüs zili: onayınızı bekleyen segment ve kaynak sorunu (yalnız sayı)."""
        engine, tenant, user, _ = ctx(request)
        waiting = seg.pending_for(engine, tenant, user) if can(user, F_APPROVE) else 0
        problems = [s["label"] for s in R.sources_state(engine, tenant) if s["failing"] or s["stale"]]
        return {"segmentsAwaiting": waiting, "sourceProblems": problems}

    @app.get(P + "/status")
    def readers_status(request: Request) -> dict[str, Any]:
        ctx(request)
        with _job_lock:
            return dict(_job)

    @app.post(P + "/refresh", status_code=202)
    def readers_refresh(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        call(R.salt)
        started = start_refresh(engine, tenant)
        if started:
            audit(engine, user, "run", "readers_sync", tenant, "Okur kaynakları yeniden okundu")
        with _job_lock:
            return {**_job, "started": started}

    # ------------------------------------------------------------------ arama, kart, KVKK başvurusu

    @app.get(P + "/search")
    async def readers_search(request: Request, q: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        ids, how = await run_in_threadpool(call, R.search_ids, engine, tenant, q)
        if how == "ad":
            if not can(user, F_PERSONAL):
                return {"items": [], "how": how, "note": "Ada göre arama kişisel veri yetkisi ister; e-posta, cep telefonu "
                                                          "ya da okur numarasıyla arayabilirsiniz."}
            rows = await run_in_threadpool(call, lambda: crm()(src.name_search_sql(schema(), q)))
            keys = {(r["kaynak"], src._id(r["id"])) for r in rows}
            ids = await run_in_threadpool(R.readers_for_links, engine, tenant, keys)
            audit(engine, user, "view", "reader_search", None, "Okur ada göre arandı", {"sonuc": len(ids)})
        items = await run_in_threadpool(R.summaries, engine, tenant, ids)
        return {"items": items, "how": how, "total": len(items)}

    @app.get(P + "/item/{rid}")
    async def readers_item(rid: str, request: Request, kisisel: bool = False) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        out = await run_in_threadpool(call, R.card, engine, tenant, rid)
        if out.get("redirect"):
            return out
        out["personal"] = None
        if kisisel:
            need(user, F_PERSONAL, "Kişisel veriyi görme yetkisi")
            links = await run_in_threadpool(R.links_of, engine, tenant, [rid])
            live = await run_in_threadpool(call, src.read_personal, crm(), schema(), [(l.source, l.source_id) for l in links])
            out["personal"] = [{"source": R.SOURCE_LABELS.get(s, s), "sourceId": i, "name": v.get("ad"),
                                "email": R.norm_email(v.get("eposta")) or v.get("eposta"),
                                "email2": R.norm_email(v.get("eposta2")), "phone": v.get("cep"),
                                "active": int(v.get("durum") or 0) == 0} for (s, i), v in live.items()]
            audit(engine, user, "view", "reader_personal", rid, "Okurun kişisel verisi görüntülendi",
                  {"kayit": len(out["personal"])})
        return out

    @app.get(P + "/subject")
    async def readers_subject(request: Request, email: str = "", phone: str = "") -> dict[str, Any]:
        """KVKK ilgili kişi başvurusu: bu e-posta/telefona ait bütün okur kayıtları, izinler, listeler, yüklemeler."""
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        need(user, F_PERSONAL, "Kişisel veriyi görme yetkisi")
        hashes = []
        if email.strip():
            h = R.email_key(email)
            if not h:
                raise HTTPException(400, detail={"code": "READERS", "message": "E-posta geçersiz."})
            hashes.append(("e", h))
        if phone.strip():
            h = R.phone_key(phone)
            if not h:
                raise HTTPException(400, detail={"code": "READERS", "message": "Cep telefonu geçersiz (Türkiye cep numarası)."})
            hashes.append(("p", h))
        if not hashes:
            raise HTTPException(400, detail={"code": "READERS", "message": "E-posta ya da cep telefonu yazın."})

        def work() -> dict[str, Any]:
            ids: list[str] = []
            for kind, h in hashes:
                ids += R.by_hash(engine, tenant, kind, h)
            alive = sorted({R._alive_id(engine, tenant, i) or i for i in ids})
            cards = [R.card(engine, tenant, i) for i in alive]
            rows = []
            with engine.connect() as c:
                for x in c.execute(imp.IMPORT_ROWS.select().where(
                        imp.IMPORT_ROWS.c.email_hash.in_([h for k, h in hashes if k == "e"] or ["-"])
                        | imp.IMPORT_ROWS.c.phone_hash.in_([h for k, h in hashes if k == "p"] or ["-"]))):
                    rows.append({"import": x.import_id, "row": x.row_no, "status": x.status})
            return {"readers": cards, "uploads": rows}
        out = await run_in_threadpool(call, work)
        audit(engine, user, "view", "reader_subject", None, "KVKK başvurusu için okur arandı",
              {"okur": len(out["readers"]), "yukleme": len(out["uploads"])})
        return out

    # ------------------------------------------------------------------ belirsiz eşleşme kuyruğu

    @app.get(P + "/merge-candidates")
    def readers_candidates(request: Request, durum: str = "bekliyor", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        if durum not in ("bekliyor", "ayni", "farkli", "gecersiz"):
            raise HTTPException(400, detail={"code": "READERS", "message": "Durum geçersiz."})
        return call(R.candidates, engine, tenant, durum, max(0, page))

    @app.post(P + "/merge-candidates/{cid}/decision")
    def readers_candidate_decide(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(R.decide_candidate, engine, tenant, cid, str(body.get("karar") or ""), user, body.get("not"))
        audit(engine, user, "update", "reader_merge", cid,
              "Okur birleştirildi" if out["status"] == "ayni" else "Okurlar farklı kişi olarak işaretlendi", out)
        return out

    # ------------------------------------------------------------------ segmentler

    @app.get(P + "/fields")
    async def readers_fields(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        profs = await run_in_threadpool(R.profiles, engine, tenant)
        return {"fields": seg.field_catalog(profs), "ops": seg.OP_LABELS}

    @app.post(P + "/preview")
    async def readers_preview(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        return await run_in_threadpool(call, seg.preview, engine, tenant, body.get("definition") or {})

    @app.get(P + "/segments")
    def readers_segments(request: Request, durum: str = "", alan: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {"items": seg.list_segments(engine, tenant, durum, alan)}

    @app.post(P + "/segments", status_code=201)
    async def readers_segment_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        profs = await run_in_threadpool(R.profiles, engine, tenant)
        out = await run_in_threadpool(call, seg.create, engine, tenant, user, body, profs)
        audit(engine, user, "create", "reader_segment", out["id"], out["name"], {"definition": out["definition"]})
        return out

    @app.post(P + "/segments/draft-from-text")
    async def readers_segment_draft(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        m = llm()
        if m is None:
            raise HTTPException(503, detail={"code": "READERS", "message": "Zeki AI şu an kullanılamıyor; kuralı elle kurabilirsiniz."})

        def chat(messages: list[dict[str, str]]) -> str:
            return m.chat(messages, max_tokens=600, temperature=0.0, user_id=user)
        try:
            return await run_in_threadpool(call, seg.draft_from_text, engine, tenant, str(body.get("text") or ""), chat)
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001 — model cevap veremedi
            log.warning("segment taslağı üretilemedi: %s", e)
            raise HTTPException(503, detail={"code": "READERS", "message": "Zeki AI şu an cevap veremedi; biraz sonra deneyin."}) from e

    @app.get(P + "/segments/{sid}")
    async def readers_segment(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        out = await run_in_threadpool(call, seg.get_segment, engine, tenant, sid)
        out["counts"] = (await run_in_threadpool(call, seg.preview, engine, tenant, out["definition"]))
        out["history"] = await run_in_threadpool(seg.history, engine, tenant, sid)
        return out

    @app.patch(P + "/segments/{sid}")
    async def readers_segment_update(sid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        profs = await run_in_threadpool(R.profiles, engine, tenant)
        out, diff = await run_in_threadpool(call, seg.update, engine, tenant, sid, user, body, profs)
        if diff:
            audit(engine, user, "update", "reader_segment", sid, out["name"], diff)
        return out

    @app.post(P + "/segments/{sid}/submit")
    def readers_segment_submit(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(seg.submit, engine, tenant, sid, user)
        audit(engine, user, "submit", "reader_segment", sid, out["name"])
        return out

    @app.post(P + "/segments/{sid}/approve")
    def readers_segment_approve(sid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_APPROVE, "Segment onayı")
        out = call(seg.decide, engine, tenant, sid, user, True, body.get("note"))
        audit(engine, user, "approve", "reader_segment", sid, out["name"], {"version": out["version"]})
        return out

    @app.post(P + "/segments/{sid}/reject")
    def readers_segment_reject(sid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_APPROVE, "Segment onayı")
        out = call(seg.decide, engine, tenant, sid, user, False, body.get("note"))
        audit(engine, user, "reject", "reader_segment", sid, out["name"], {"note": body.get("note")})
        return out

    @app.post(P + "/segments/{sid}/archive")
    def readers_segment_archive(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(seg.archive, engine, tenant, sid, user)
        audit(engine, user, "delete", "reader_segment", sid, out["name"])
        return out

    @app.post(P + "/segments/{sid}/preview")
    async def readers_segment_preview(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        s = await run_in_threadpool(call, seg.get_segment, engine, tenant, sid)
        return await run_in_threadpool(call, seg.preview, engine, tenant, s["definition"])

    @app.post(P + "/segments/{sid}/export")
    async def readers_segment_export(sid: str, body: dict[str, Any], request: Request) -> Response:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        need(user, F_LIST, "Okur listesi dışa aktarma yetkisi")
        name, data, rec = await run_in_threadpool(call, seg.export, engine, tenant, sid, user, str(body.get("channel") or ""),
                                                  str(body.get("purpose") or ""), personal_reader())
        audit(engine, user, "export", "reader_export", rec["id"], f"{rec['segment']} — {rec['count']} kişi",
              {"kanal": rec["channel"], "amac": rec["purpose"], "disarida": rec["excluded"]})
        resp = csv_response(name, data)
        resp.headers["X-Readers-Count"] = str(rec["count"])
        resp.headers["X-Readers-Excluded"] = str(rec["excludedTotal"])
        return resp

    # ------------------------------------------------------------------ etkinlik dosyası

    @app.get(P + "/imports")
    def readers_imports(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {"items": imp.list_imports(engine, tenant)}

    @app.post(P + "/imports", status_code=201)
    async def readers_import_create(request: Request, filename: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        max_mb = R.settings()["fileMaxMb"]
        if int(request.headers.get("content-length") or 0) > max_mb * 1024 * 1024:
            raise HTTPException(413, detail={"code": "READERS", "message": f"Dosya {max_mb} MB sınırını aşıyor."})
        data = await request.body()
        out = await run_in_threadpool(call, imp.create, engine, tenant, user, filename, data)
        audit(engine, user, "create", "reader_import", out["id"], out["fileName"], {"satir": out["rows"]})
        return out

    @app.get(P + "/imports/{iid}")
    def readers_import(iid: str, request: Request, durum: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        personal = can(user, F_PERSONAL)
        out = call(imp.get, engine, tenant, iid, personal=personal, status=durum, page=max(0, page))
        if personal and out["items"]:
            audit(engine, user, "view", "reader_import", iid, "Yükleme satırları açık görüntülendi", {"satir": len(out["items"])})
        return out

    @app.post(P + "/imports/{iid}/confirm")
    async def readers_import_confirm(iid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        out = await run_in_threadpool(call, imp.confirm, engine, tenant, iid, user, body)
        audit(engine, user, "update", "reader_import", iid, out["eventName"],
              {"eslesen": out["matched"], "yeni": out["new"], "gecersiz": out["rejected"], "izinEksik": out["missingConsent"]})
        return out

    @app.get(P + "/imports/{iid}/crm.csv")
    def readers_import_crm(iid: str, request: Request) -> Response:
        engine, tenant, user, _ = ctx(request)
        head = call(imp.get, engine, tenant, iid, personal=False, page=0, size=1)
        if head["uploadedBy"].lower() != user.lower():
            need(user, F_PERSONAL, "Başkasının yüklemesindeki kişileri görme yetkisi")
        name, data, n = call(imp.new_people_csv, engine, tenant, iid)
        audit(engine, user, "export", "reader_import", iid, f"CRM'e işlenecek yeni kişiler — {n}", {"satir": n})
        return csv_response(name, data)

    @app.delete(P + "/imports/{iid}")
    def readers_import_delete(iid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        n = call(imp.purge, engine, tenant, iid)
        audit(engine, user, "delete", "reader_import", iid, "Yükleme satırları silindi")
        return {"purged": n}

    # ------------------------------------------------------------------ dışa aktarım günlüğü

    @app.get(P + "/exports")
    def readers_exports(request: Request, page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return seg.list_exports(engine, tenant, max(0, page))

    # ------------------------------------------------------------------ sözleşme uçları (M24, M37, M35)

    @app.get(P + "/contract/segments")
    def readers_contract_segments(request: Request, alan: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        items = seg.list_segments(engine, tenant, "onayli", alan)
        return {"items": [{k: s[k] for k in ("id", "name", "explanation", "version", "domain", "approvedAt", "lastSnapshot")}
                          for s in items]}

    @app.get(P + "/contract/segments/{sid}/summary")
    async def readers_contract_summary(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        return await run_in_threadpool(call, seg.summary, engine, tenant, sid)

    # ------------------------------------------------------------------ zamanlayıcı

    @app.post(P + "/run-due")
    def readers_run_due(request: Request) -> dict[str, Any]:
        require_caller(request)
        from semantic_bridge.budget_api import _send_mail

        r = rt()
        engine, tenant = r.store.engine, r.settings.tenant_id
        R.ensure(engine)
        cfg = R.settings()
        out: dict[str, Any] = {}
        try:
            res = run_sync(engine, tenant)
            out["okuma"] = {k: res.get(k) for k in ("readers", "links", "merged", "gone", "candidates", "minors", "errors")}
        except (R.ReadersError, src.SourceError) as e:
            R.record_sync_error(engine, tenant, "crm_contact", str(e))
            out["okuma"] = {"hata": str(e)}
        try:
            out["segmentSayimi"] = seg.snapshot_all(engine, tenant, cfg)
        except Exception as e:  # noqa: BLE001
            out["segmentSayimi"] = {"hata": str(e)[:200]}
        out["silinenYukleme"] = imp.purge(engine, tenant)

        link = (admin_mod.conf("ALERT_LINK") or "").split("/uyarilar")[0]
        link = f"{link}/okurlar" if link else ""
        lines: list[str] = []
        problems = [s for s in R.sources_state(engine, tenant, cfg) if s["failing"] or s["stale"]]
        for s in problems:
            lines.append(f"- {s['label']}: " + (f"okunamadı ({s['error']})" if s["failing"] else
                                                f"{cfg['staleHours']} saatten eski (son okuma {s['at'] or 'yok'})"))
        pending = R.candidates(engine, tenant, "bekliyor", 0, 1, cfg)["total"]
        if pending >= cfg["queueAlert"]:
            lines.append(f"- Birleştirme kuyruğunda {pending} çift karar bekliyor (eşik {cfg['queueAlert']}).")
        mail: dict[str, str] = {}
        rcpt = [x.strip() for x in (admin_mod.conf("READERS_ALERT_RECIPIENTS") or "").replace(";", ",").split(",") if "@" in x]
        if lines:
            mail["uyari"] = _send_mail("Okur veri tabanı: dikkat gereken durum",
                                       "\n".join(["Okur veri tabanında dikkat gereken durumlar:", *lines, "", link]), rcpt) \
                if rcpt else "alici_yok"
        ex = seg.exports_since(engine, tenant, datetime.now(timezone.utc) - timedelta(days=1))
        kvkk = [x.strip() for x in (admin_mod.conf("READERS_KVKK_RECIPIENTS") or "").replace(";", ",").split(",") if "@" in x]
        if ex:
            body = ["Son 24 saatte dışa aktarılan okur listeleri:"] + [
                f"- {x['at'][:16].replace('T', ' ')} {x['user']}: «{x['segment']}» ({x['channelLabel']}) {x['count']} kişi; "
                f"amaç: {x['purpose']}; dışarıda kalan {x['excludedTotal']}" for x in ex] + ["", link]
            mail["kvkk"] = _send_mail(f"Okur listesi dışa aktarımları: {len(ex)}", "\n".join(body), kvkk) if kvkk else "alici_yok"
        out.update(sorunluKaynak=len(problems), bekleyenAday=pending, disaAktarim=len(ex), eposta=mail)
        return out

    return {"run_sync": run_sync}
