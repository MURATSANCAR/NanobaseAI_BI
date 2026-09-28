"""M36 Dijital yayın ve e-kitap uçları: /api/v1/dijital/*.

Sayfa kapısı `access.RULES`: katalog, fırsat, hak riski, kitap ayrıntısı, CRM'e işlenecekler `sayfa:dijital-yayin`;
rapor yükleme ve satış panosu `sayfa:dijital-satis` (finans verisi, ayrı anahtar); göstergeler ve platform listesi iki
sayfada da açık. Platform durumu, platform tanımı ve «Yenile» `ozellik:dijital.durum-yaz`; rapor yükleme, kolon düzeltme,
satır eşleme ve onay `ozellik:dijital.rapor-yukle`; fırsat ve satış CSV'si `ozellik:veri.disa-aktar` (`FEATURE_RULES`).
Hak kararı (`ozellik:dijital.hak-karari`) ve dijital fiyat kararı (`ozellik:dijital.fiyat-onay`) açıkça verilen
yetkilerdir, burada denetlenir. Kitap ayrıntısındaki dijital satış yalnız `sayfa:dijital-satis`'i olana döner.

Zamanlayıcı (`timas-dijital.timer`, her gece 04:00) yalnız `POST /api/v1/dijital/run-due`'yu çağırır: CRM/Logo/stüdyo
okuması, hak notu ön okuması (Zeki AI, süre bütçesiyle), iç uyarı e-postaları. Dış gönderim yok: platformlara, T-soft'a,
CRM'e ve Logo'ya hiçbir şey yazılmaz. Model yalnız LLM kapısından: `llm(priority)` → `rt.llm_for("dijital", …)`.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date
from typing import Any, Optional

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import dijital as D
from semantic_bridge import dijital_sources as src

log = logging.getLogger("semantic.dijital.api")
P = "/api/v1/dijital"
F_WRITE = "ozellik:dijital.durum-yaz"
F_IMPORT = "ozellik:dijital.rapor-yukle"
F_RIGHTS = "ozellik:dijital.hak-karari"
F_PRICE = "ozellik:dijital.fiyat-onay"
F_EXPORT = "ozellik:veri.disa-aktar"
PAGE_SALES = "sayfa:dijital-satis"


def register(app: Any, deps: dict[str, Any]) -> D.Refresher:
    """app.py'de bağlanır. `deps`: auth(request) → (engine, tenant, user, display) · require_caller(request) · can(user, key) ·
    is_admin(user) · audit(engine, user, action, kind, id, title, detail) · conf(key, default) · engine() · tenant() ·
    logo_file() · crm_file() · llm(priority) → LLM kapısı istemcisi ya da None · studio_jobs() / studio_view(job) (isteğe
    bağlı, stüdyo) · send_mail(subject, text, to) → "sent" | …."""
    auth, require_caller, can, is_admin, audit, conf = (deps[k] for k in ("auth", "require_caller", "can", "is_admin", "audit", "conf"))
    settings = lambda: D.settings_from(conf)  # noqa: E731
    refresher = D.Refresher(deps["engine"], deps["tenant"], lambda: src.runner(deps["crm_file"]()),
                            lambda: src.runner(deps["logo_file"]()), deps.get("studio_jobs"), deps.get("studio_view"), settings)
    jobs_lock = threading.Lock()
    match_jobs: set[str] = set()

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        engine, tenant, user, display = auth(request)
        D.ensure(engine)
        return engine, tenant, user, display

    def has(user: str, key: str) -> bool:
        return is_admin(user) or can(user, key)

    def need(user: str, key: str, what: str) -> None:
        if not has(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except D.DigitalError as e:
            raise HTTPException(status_code=e.status, detail={"code": "FORBIDDEN" if e.status == 403 else "DIJITAL",
                                                              "message": str(e)}) from e
        except src.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "DIJITAL_SOURCE", "retryable": True, "message": str(e)}) from e

    def llm(priority_name: str) -> Any:
        from semantic_layer.runtime import llm_queue

        try:
            return deps["llm"](getattr(llm_queue, priority_name))
        except Exception as e:  # noqa: BLE001 — model tanımlı değil
            log.info("dijital: model yok: %s", e)
            return None

    def csv_response(text: str, name: str) -> Response:
        return Response(content=text.encode("utf-8"), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    # ------------------------------------------------------------------ genel

    @app.get(P + "/meta")
    def dijital_meta(request: Request) -> dict[str, Any]:
        _, _, user, display = ctx(request)
        st = settings()
        return {
            "haklar": D.RIGHTS, "bicimler": D.FORMATS, "platformDurumlari": D.LISTING_STATES, "platformTurleri": D.PLATFORM_KINDS,
            "dagitim": D.DISTRIBUTION, "studyo": D.STUDIO_STATES, "kararlar": D.DECISIONS_KINDS, "notAdlari": D.NOTE_CHOICES,
            "crmAlanlari": D.PENDING_FIELDS,
            "ayarlar": {k: st[k] for k in ("oppMinQty", "audioMinQty", "audioGenres", "matchMinProb", "importMaxMb")},
            "okuma": refresher.status(), "modelVar": llm("NORMAL") is not None,
            "me": {"username": user, "display": display, "admin": is_admin(user), "canWrite": has(user, F_WRITE),
                   "canImport": has(user, F_IMPORT), "canRights": has(user, F_RIGHTS), "canPrice": has(user, F_PRICE),
                   "canExport": has(user, F_EXPORT), "canSales": has(user, PAGE_SALES)},
        }

    @app.get(P + "/overview")
    def dijital_overview(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return D.overview(engine, tenant, settings())

    @app.post(P + "/refresh", status_code=202)
    def dijital_refresh(request: Request) -> dict[str, Any]:
        engine, _, user, _ = ctx(request)
        out = refresher.start()
        if out.get("started"):
            audit(engine, user, "run", "dijital_refresh", "katalog", "Dijital katalog okuması", None)
        return out

    # ------------------------------------------------------------------ katalog

    @app.get(P + "/titles")
    def dijital_titles(request: Request, hak: str = "", durum: str = "", q: str = "", tur: str = "kitap", platform: int = 0,
                       page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return D.list_titles(engine, tenant, settings(), hak=hak, durum=durum, q=q, tur=tur, platform=platform, page=page)

    @app.get(P + "/titles/{kitap_id}")
    def dijital_title(kitap_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return call(D.get_title, engine, tenant, kitap_id, with_sales=has(user, PAGE_SALES))

    @app.put(P + "/titles/{kitap_id}/listings/{platform_id}")
    def dijital_listing(kitap_id: str, platform_id: int, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(D.set_listing, engine, tenant, user, kitap_id, platform_id, body)
        audit(engine, user, "update", "dijital_listing", f"{out['kitapId']}:{platform_id}", out.get("ad"),
              {"durum": body.get("durum"), "tarih": body.get("tarih")})
        return out

    @app.put(P + "/titles/{kitap_id}/price")
    def dijital_price(kitap_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_PRICE, "Dijital fiyat kararı")
        out = call(D.set_price, engine, tenant, user, kitap_id, body)
        audit(engine, user, "update", "dijital_price", out["kitapId"], out.get("ad"),
              {"fiyat": out.get("dijitalFiyat"), "gerekce": (out.get("fiyatGerekce") or "")[:200]})
        return out

    @app.get(P + "/opportunities")
    def dijital_opportunities(request: Request, tur: str = "ekitap", q: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return D.opportunities(engine, tenant, tur="sesli" if tur == "sesli" else "ekitap", q=q, page=page)

    @app.get(P + "/opportunities/export.csv")
    def dijital_opportunities_csv(request: Request, tur: str = "ekitap", q: str = "") -> Response:
        engine, tenant, user, _ = ctx(request)
        need(user, F_EXPORT, "Dışa aktarma")
        kind = "sesli" if tur == "sesli" else "ekitap"
        data = D.opportunities(engine, tenant, tur=kind, q=q, all_rows=True)
        audit(engine, user, "export", "dijital_opportunities", kind, f"Dijital fırsat listesi ({D.FORMATS[kind]})", {"satir": data["total"]})
        return csv_response(D.opportunities_csv(data), f"dijital-firsat-{kind}.csv")

    @app.get(P + "/rights-risks")
    def dijital_rights_risks(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return D.rights_risks(engine, tenant)

    @app.post(P + "/rights-decisions", status_code=201)
    def dijital_rights_decision(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_RIGHTS, "Dijital hak kararı")
        out = call(D.decide_rights, engine, tenant, user, body)
        audit(engine, user, "create", "dijital_rights", f"{out['kitapId']}:{body.get('sozlesmeId')}:{body.get('bicim')}", out.get("ad"),
              {"karar": body.get("karar"), "gerekce": str(body.get("gerekce") or "")[:200]})
        return out

    @app.get(P + "/crm-pending")
    def dijital_crm_pending(request: Request, durum: str = "acik") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return D.crm_pending(engine, tenant, durum)

    # ------------------------------------------------------------------ platformlar

    @app.get(P + "/platforms")
    def dijital_platforms(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return D.list_platforms(engine, tenant)

    @app.post(P + "/platforms", status_code=201)
    def dijital_platform_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(D.create_platform, engine, tenant, user, body)
        audit(engine, user, "create", "dijital_platform", str(out["id"]), out["ad"], {"tur": out["tur"], "dagitim": out["dagitim"]})
        return out

    @app.patch(P + "/platforms/{pid}")
    def dijital_platform_update(pid: int, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(D.update_platform, engine, tenant, pid, body)
        audit(engine, user, "update", "dijital_platform", str(pid), out["ad"], {k: body[k] for k in body if k in ("ad", "tur", "dagitim", "paraBirimi", "raporGunu", "aktif")})
        return out

    # ------------------------------------------------------------------ rapor yükleme

    @app.get(P + "/imports")
    def dijital_imports(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return D.list_imports(engine, tenant)

    @app.post(P + "/imports", status_code=201)
    async def dijital_import_create(request: Request, platform: int = 0, donem: str = "", filename: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        limit = settings()["importMaxMb"]
        if int(request.headers.get("content-length") or 0) > limit * 1024 * 1024:
            raise HTTPException(413, detail={"code": "DIJITAL", "message": f"Dosya {limit} MB sınırını aşıyor."})
        data = await request.body()
        out = await run_in_threadpool(call, D.create_import, engine, tenant, user, platform, donem, filename, data)
        audit(engine, user, "create", "dijital_import", out["id"], f"{out['platform']} {out['donem']}",
              {"dosya": out["dosya"], "satir": out["satir"], "eslesen": out["eslesen"], "atilanKolon": len(out["atilanKolonlar"])})
        return out

    @app.get(P + "/imports/{iid}")
    def dijital_import(iid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(D.get_import, engine, tenant, iid)

    @app.patch(P + "/imports/{iid}")
    def dijital_import_remap(iid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(D.remap_import, engine, tenant, iid, body.get("kolonlar") or {})
        audit(engine, user, "update", "dijital_import", iid, f"{out['platform']} {out['donem']}", {"kolonlar": out["kolonlar"]})
        return out

    @app.post(P + "/imports/{iid}/match", status_code=202)
    def dijital_import_match(iid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        imp = call(D.get_import, engine, tenant, iid)
        if imp["durum"] == "iptal":
            raise HTTPException(409, detail={"code": "DIJITAL", "message": "İptal edilmiş rapor."})
        with jobs_lock:
            if iid in match_jobs:
                return {"started": False, "eslestirme": imp["eslestirme"]}
            match_jobs.add(iid)
        st = settings()
        model = llm("BATCH")

        def work() -> None:
            t0 = time.time()
            D.set_match_job(engine, iid, {"durum": "suruyor", "bitti": 0, "toplam": imp["eslesmeyen"], "basladi": t0})
            try:
                res = D.suggest_matches(engine, tenant, iid, model, st,
                                        progress=lambda d, n: D.set_match_job(engine, iid, {"durum": "suruyor", "bitti": d, "toplam": n, "basladi": t0}))
                D.set_match_job(engine, iid, {"durum": "bitti", **res, "sure": round(time.time() - t0, 1)})
            except Exception as e:  # noqa: BLE001
                log.warning("dijital: eşleme önerisi hata verdi: %s", e)
                D.set_match_job(engine, iid, {"durum": "hata", "mesaj": "Öneri üretilemedi; satırlar elle eşlenebilir."})
            finally:
                with jobs_lock:
                    match_jobs.discard(iid)

        threading.Thread(target=work, name=f"dijital-match-{iid}", daemon=True).start()
        audit(engine, user, "run", "dijital_import", iid, "Zeki AI eşleme önerisi", {"satir": imp["eslesmeyen"]})
        return {"started": True, "model": model is not None}

    @app.post(P + "/imports/{iid}/rows")
    def dijital_import_rows(iid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        rows = body.get("satirlar") or []
        if not isinstance(rows, list) or not rows:
            raise HTTPException(422, detail={"code": "DIJITAL", "message": "Eşlenecek satır verilmedi."})
        out = call(D.decide_rows, engine, tenant, iid, rows, settings())
        audit(engine, user, "update", "dijital_import", iid, f"{out['platform']} {out['donem']}",
              {"satir": len(rows), "eslesen": out["eslesen"], "eslesmeyen": out["eslesmeyen"]})
        return out

    @app.post(P + "/imports/{iid}/accept-strong")
    def dijital_import_accept(iid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(D.accept_strong, engine, tenant, iid, settings())
        audit(engine, user, "update", "dijital_import", iid, "Güçlü Zeki AI önerileri onaylandı",
              {"eslesen": out["eslesen"], "eslesmeyen": out["eslesmeyen"]})
        return out

    @app.post(P + "/imports/{iid}/commit")
    def dijital_import_commit(iid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(D.commit_import, engine, tenant, user, iid, body)
        audit(engine, user, "approve", "dijital_import", iid, f"{out['platform']} {out['donem']}",
              {"satir": out["satir"], "eslesen": out["eslesen"], "eslesmeyen": out["eslesmeyen"], "kurlar": out["kurlar"]})
        return out

    @app.delete(P + "/imports/{iid}")
    def dijital_import_delete(iid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(D.delete_import, engine, tenant, iid)
        audit(engine, user, "delete", "dijital_import", iid, "Satış raporu " + ("silindi" if out.get("silindi") else "iptal edildi"), None)
        return out

    # ------------------------------------------------------------------ satış

    @app.get(P + "/sales")
    def dijital_sales(request: Request, donem: str = "", platform: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return D.sales(engine, tenant, donem=donem, platform=platform)

    @app.get(P + "/sales/export.csv")
    def dijital_sales_csv(request: Request, donem: str = "", platform: int = 0) -> Response:
        engine, tenant, user, _ = ctx(request)
        need(user, F_EXPORT, "Dışa aktarma")
        data = D.sales(engine, tenant, donem=donem, platform=platform)
        audit(engine, user, "export", "dijital_sales", donem or "hepsi", "Dijital satış", {"platform": platform or None})
        return csv_response(D.sales_csv(data), f"dijital-satis{('-' + donem) if donem else ''}.csv")

    # ------------------------------------------------------------------ zamanlayıcı

    @app.post(P + "/run-due")
    def dijital_run_due(request: Request) -> dict[str, Any]:
        """Gece: okuma → hak notu ön okuması (süre bütçesiyle) → iç uyarı e-postaları (her uyarı bir kez)."""
        require_caller(request)
        engine, tenant = deps["engine"](), deps["tenant"]()
        D.ensure(engine)
        st = settings()
        out: dict[str, Any] = {}
        try:
            out["okuma"] = refresher.run()
        except (D.DigitalError, src.SourceError) as e:
            out["okuma"] = {"ok": False, "error": str(e)}
        try:
            out["hakNotu"] = D.read_notes(engine, tenant, llm("BATCH"), st["noteBudgetSec"])
        except Exception as e:  # noqa: BLE001
            out["hakNotu"] = {"error": str(e)[:200]}
        items = D.due_alerts(engine, tenant, st, date.today())
        link = (conf("ALERT_LINK", "") or "").split("/uyarilar")[0]
        link = f"{link}/dijital-yayin" if link else ""
        mails: dict[str, Any] = {}
        send = deps.get("send_mail")
        for who, rcpt, subject in (("telif", st["rightsRecipients"], "Dijital hak riski"),
                                   ("dijital", st["alertRecipients"], "Dijital sürüm güncellemesi"),
                                   ("finans", st["financeRecipients"], "Dijital satış raporu bekleniyor")):
            part = [i for i in items if i["kime"] == who]
            if not part:
                continue
            if not rcpt or send is None:
                mails[who] = "alici_yok"
                continue
            res = send(f"{subject}: {len(part)} kayıt", D.alert_text(part, link), rcpt)
            mails[who] = res
            if res == "sent":
                D.mark_sent(engine, tenant, [i["key"] for i in part])
        out["uyari"] = {"toplam": len(items), "eposta": mails}
        return out

    return refresher
