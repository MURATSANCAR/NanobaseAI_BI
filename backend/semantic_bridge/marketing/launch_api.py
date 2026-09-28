"""M16 Lansman uçları: /api/v1/marketing/launches*.

Sayfa kapısı `access.RULES` (`sayfa:pazarlama-lansman`); yazma `ozellik:pazarlama.lansman-yaz` (`FEATURE_RULES`),
dışa aktarım `ozellik:veri.disa-aktar`. Değerlendirme kararı (bütçe revizyonu) açıkça verilen
`ozellik:pazarlama.plan-onay` ile ucun içinde denetlenir. Ciro yalnız `ozellik:pazarlama.butce-gor` olana gider.

Zamanlayıcı (`timas-marketing-launch.timer`, saatte bir) yalnız `POST /api/v1/marketing/launches/run-due`'yu çağırır:
onaylı planların lansmanını açar (yayına `MARKETING_LAUNCH_OPEN_DAYS` gün kala), CRM sipariş sinyalini okur; günde bir
(`MARKETING_LAUNCH_DAILY_HOUR` sonrası ilk koşu) Logo satış/depo/veri sonu ve emsal, D+7/D+30 rapor taslağı, günlük
özet e-postası; stok–talep çatışması anında (kitap başına günde en çok bir kez).

Hiçbir dış kanala gönderim yok; e-posta yalnız iç alıcılara (Yönetim → Pazarlama planları) ve lansman sahibine gider.
"""
from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timedelta
from typing import Any, Callable

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import pazarlama_kaynak as PK
from semantic_bridge import provenance as PV
from semantic_bridge.marketing import core as C
from semantic_bridge.marketing import kaynak_lansman as K
from semantic_bridge.marketing import launch as L
from semantic_bridge.marketing import launch_report as RP
from semantic_bridge.marketing import launch_risk as LR
from semantic_bridge.marketing import launch_track as TR
from semantic_bridge.marketing.launch_sources import Sources
from semantic_bridge.marketing.sources import SourceError, crm_file
from semantic_layer.runtime.llm_queue import BATCH, NORMAL

log = logging.getLogger("semantic.marketing.launch.api")

R = "/api/v1/marketing/launches"
F_WRITE = "ozellik:pazarlama.lansman-yaz"
F_BUDGET = "ozellik:pazarlama.butce-gor"
F_DECIDE = "ozellik:pazarlama.plan-onay"
F_EXPORT = "ozellik:veri.disa-aktar"


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None], can: Callable[[str, str], bool],
             core: dict[str, Any]) -> dict[str, Any]:
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod
    from semantic_bridge import budget_sources as bsrc
    from semantic_bridge.budget_api import _send_mail

    crm = core["crm"]          # pazarlama çekirdeğinin CRM okuyucusu (kitap kartı, e-posta)
    pool = core["pool"]        # pazarlama iş havuzu (Zeki AI metinleri)
    src = Sources(lambda: admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo",
                  lambda: bsrc.runner(crm_file()), lambda: bsrc.runner(rt().settings.connection_file))
    run_lock = threading.Lock()

    def st() -> dict[str, Any]:
        return L.settings(admin_mod.conf)

    def db() -> tuple[Any, str]:
        r = rt()
        L.ensure(r.store.engine)
        admin_mod.ensure(r.store.engine)
        return r.store.engine, r.settings.tenant_id

    def ctx(request: Request) -> tuple[Any, str, str]:
        require_caller(request)
        try:
            user, _display = board_mod.session_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        engine, tenant = db()
        return engine, tenant, user

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except C.MarketingError as e:
            raise HTTPException(status_code=e.status, detail={"code": "MARKETING", "message": str(e)}) from e
        except SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "MARKETING_SOURCE", "message": str(e)}) from e

    def need(user: str, key: str, what: str) -> None:
        if not can(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def audit(engine, user: str, action: str, lid: str, title: str, detail: Any = None) -> None:
        admin_mod.audit(engine, user, action, "marketing_launch", lid, title, detail)

    def link(path: str = "") -> str:
        base = (admin_mod.conf("ALERT_LINK") or "").split("/uyarilar")[0]
        return f"{base}/pazarlama/lansman{('/' + path) if path else ''}" if base else ""

    def web_on() -> bool:
        return (admin_mod.conf("WEB_WATCH_ENABLED") or "0").strip().lower() in ("1", "true", "evet", "on")

    def detail_of(code: str):
        try:
            return crm.book(code)
        except SourceError as e:
            log.warning("launch: CRM kitap kartı okunamadı (%s): %s", code, e)
            return None

    def exit_of_for(engine, tenant):
        def exit_of(kitap_id: str):
            svc = getattr(app.state, "production", None)
            if svc is None:
                return None
            try:
                from semantic_bridge import production_store as pstore

                pstore.ensure(engine)
                return svc.print_exit(engine, tenant, kitap_id)
            except Exception as e:  # noqa: BLE001 — üretim modülü okunamazsa CRM tarihleri yeter
                log.warning("launch: üretim baskı çıkışı okunamadı (%s): %s", kitap_id, e)
                return None
        return exit_of

    def money(user: str, obj: dict[str, Any]) -> dict[str, Any]:
        if can(user, F_BUDGET):
            return obj
        return {**obj, "reviews": [{**r, "rakam": RP.redact(r["rakam"])} for r in obj.get("reviews") or []]}

    def events_of(engine, full: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        warn = []
        crm_rows: list[dict[str, Any]] = []
        if full.get("crmKitapId"):
            try:
                crm_rows, _sql = src.events(full["crmKitapId"])
            except SourceError as e:
                warn.append(f"CRM etkinlikleri okunamadı: {e}")
        else:
            warn.append("Planda CRM kitap kimliği yok; yalnız portalda girilen etkinlikler.")
        return L.merge_events(crm_rows, L.portal_events(engine, full["id"])), warn

    def media_of(engine, tenant, full: dict[str, Any]) -> dict[str, Any]:
        items = [{**m, "kaynakAdi": "Elle"} for m in L.portal_media(engine, full["id"])]
        web = web_on()
        if web and full.get("crmKitapId"):
            from semantic_bridge import web_watch

            lo = (date.fromisoformat(full["yayinGunu"]) - timedelta(days=int((full.get("ozet") or {}).get("onGun") or 14))).isoformat()
            try:
                for w in web_watch.book(engine, tenant, full["crmKitapId"])["items"]:
                    if (w.get("on") or "")[:10] >= lo:
                        items.append({"id": None, "kaynak": "web", "kaynakAdi": w.get("source"), "mecra": w.get("source"),
                                      "baslik": w.get("title"), "url": w.get("url"), "tarih": (w.get("on") or "")[:10] or None,
                                      "ton": w.get("label"), "tonAdi": L.TONES.get(w.get("label") or ""), "giren": None})
            except Exception as e:  # noqa: BLE001
                log.warning("launch: basın ve web kayıtları okunamadı: %s", e)
        items.sort(key=lambda x: x.get("tarih") or "", reverse=True)
        counts = {k: sum(1 for m in items if m.get("ton") == k) for k in L.TONES}
        return {"items": items, "ton": counts, "webAcik": web}

    # ------------------------------------------------------------------ genel (önce sabit yollar)

    @app.get(R + "/meta")
    def launch_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        s = st()
        return {
            "statuses": L.STATUSES, "dateSources": L.DATE_SOURCES, "decisions": L.DECISIONS, "tones": L.TONES,
            "channels": C.CHANNELS, "taskStatuses": C.TASK_STATUSES,
            "settings": {k: s[k] for k in ("openDays", "preDays", "alertRatio", "dailyHour")},
            "lastRun": C.meta_get(engine, tenant, "launch-run-due") or None, "webWatch": web_on(),
            "modelReady": getattr(rt(), "llm", None) is not None,
            "me": {"username": user, "canWrite": can(user, F_WRITE), "canSeeBudget": can(user, F_BUDGET),
                   "canDecide": can(user, F_DECIDE), "canExport": can(user, F_EXPORT)},
        }

    @app.get(R)
    def launch_list(request: Request, frm: str = "", to: str = "", durum: str = "", kim: str = "") -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        items = L.list_launches(engine, tenant, frm=frm or None, to=to or None, durum=durum, sahip=user if kim == "ben" else "")
        # Kural eşikli risk bayrağı + tek cümle (öneri 17): cümle gece yazılır, burada yalnız okunur.
        items = LR.attach(engine, tenant, items, st()["alertRatio"], LR.settings(admin_mod.conf))
        out = {"items": items, "total": len(items)}
        return PV.bagla(out, lambda: K.for_list(engine, tenant, out, frm=frm or None, to=to or None, durum=durum,
                                                sahip=user if kim == "ben" else ""))

    @app.get(R + "/today")
    def launch_today(request: Request, kim: str = "ben") -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        items = L.today_tasks(engine, tenant, user, mine=kim != "hepsi")
        return PV.bagla({"items": items, "total": len(items), "tarih": C.today().isoformat()}, lambda: K.for_today(engine, tenant))

    @app.get(R + "/candidates")
    def launch_candidates(request: Request) -> dict[str, Any]:
        """Lansmanı açılabilecek onaylı yeni kitap planları (lansmanı olmayan)."""
        engine, tenant, _ = ctx(request)
        items = L.plans_due(engine, tenant, C.today(), 3650, back_days=3650)
        return {"items": [{k: p.get(k) for k in ("id", "baslik", "stokKodu", "yayinTarihi", "sahip")} for p in items]}

    @app.post(R + "/run-due")
    def launch_run_due(request: Request, force: bool = False) -> dict[str, Any]:
        require_caller(request)
        engine, tenant = db()
        if not run_lock.acquire(blocking=False):
            return {"atlandi": "Önceki koşu sürüyor."}
        try:
            return run_due(engine, tenant, force)
        finally:
            run_lock.release()

    @app.post(R, status_code=201)
    async def launch_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = await run_in_threadpool(ctx, request)
        pid = str(body.get("plan_id") or body.get("planId") or "")
        if not pid:
            raise HTTPException(status_code=400, detail={"code": "MARKETING", "message": "Plan gerekli."})
        plan = call(C.plan_full, engine, tenant, pid)
        card = C.card_get(engine, tenant, plan["stokKodu"]) if plan.get("stokKodu") else None
        k = (card or {}).get("kitap") or {}
        lid = await run_in_threadpool(call, L.create, engine, tenant, user, pid, st(), book_name=k.get("ad"), kapak=k.get("kapak"))
        # İlk okuma (CRM + Logo + emsal) arka planda: açma hemen döner, İzleme sekmesi okuma bitince dolar.
        pool.submit(refresh_bg, engine, tenant, lid)
        full = L.get_full(engine, tenant, lid)
        audit(engine, user, "create", lid, full["baslik"], {"plan": pid, "yayin": full["yayinGunu"]})
        return money(user, full)

    # ------------------------------------------------------------------ lansman

    def refresh_one(engine, tenant, lid: str, logo: bool) -> dict[str, Any]:
        head = L.get(engine, tenant, lid)
        return TR.refresh(engine, tenant, [head], src, st(), logo=logo, detail_of=detail_of, exit_of=exit_of_for(engine, tenant))

    def refresh_bg(engine, tenant, lid: str) -> None:
        try:
            refresh_one(engine, tenant, lid, True)
        except Exception as e:  # noqa: BLE001 — okuma hatası lansman özetinde ve bir sonraki koşuda görünür
            log.warning("launch: ilk okuma yapılamadı (%s): %s", lid, e)

    def logo_db() -> str | None:
        return PK.logo_db(rt)

    @app.get(R + "/{lid}")
    def launch_get(lid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        full = call(L.get_full, engine, tenant, lid)
        return PV.bagla(money(user, full), lambda: K.for_launch(engine, tenant, full, logo_db()))

    @app.patch(R + "/{lid}")
    def launch_patch(lid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        out = call(L.update, engine, tenant, user, lid, body)
        audit(engine, user, "update", lid, out["baslik"], {k: body[k] for k in ("sahip", "yayinGunu", "yayinGunuKaynagi", "durum") if k in body})
        return money(user, out)

    @app.put(R + "/{lid}/tasks/{tid}")
    def launch_task(lid: str, tid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        t = call(L.set_task, engine, tenant, user, lid, tid, body)
        audit(engine, user, "update", lid, t["is"], {"madde": tid, **{k: body[k] for k in ("durum", "kanitUrl", "sorumlu") if k in body}})
        return {"task": t}

    @app.post(R + "/{lid}/tasks", status_code=201)
    def launch_task_add(lid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        t = call(L.add_task, engine, tenant, user, lid, body)
        audit(engine, user, "create", lid, t["is"], {"madde": t["id"], "tarih": t["tarih"]})
        return {"task": t}

    @app.post(R + "/{lid}/refresh")
    async def launch_refresh(lid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user = await run_in_threadpool(ctx, request)
        rep = await run_in_threadpool(call, refresh_one, engine, tenant, lid, True)
        audit(engine, user, "run", lid, "Lansman verisi yenilendi", {"gun": rep["gun"], "hata": len(rep["hatalar"])})
        return {"rapor": rep, "lansman": money(user, L.get_full(engine, tenant, lid))}

    @app.get(R + "/{lid}/tracking")
    def launch_tracking(lid: str, request: Request, gun: int = 7) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        if gun not in (7, 30):
            raise HTTPException(status_code=400, detail={"code": "MARKETING", "message": "gun 7 ya da 30 olmalı."})
        out = call(L.tracking, engine, tenant, lid, gun, can(user, F_BUDGET))
        out.pop("sql", None)   # çalışmış metinler sorgu bilgisinde (kalem kalem, kopyalanabilir)
        return PV.bagla(out, lambda: K.for_tracking(engine, tenant, L.get_full(engine, tenant, lid), logo_db()))

    # ---- etkinlik ve medya

    @app.get(R + "/{lid}/events")
    async def launch_events(lid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user = await run_in_threadpool(ctx, request)
        full = call(L.get_full, engine, tenant, lid)
        ev, warn = await run_in_threadpool(events_of, engine, full)
        if not can(user, F_BUDGET):
            ev = {"items": [{**x, "gelir": None, "gider": None} for x in ev["items"]],
                  "toplam": {**ev["toplam"], "gelir": None, "gider": None}}
        return PV.bagla({**ev, "uyarilar": warn}, lambda: K.for_events(engine, full, crm.schema()))

    @app.post(R + "/{lid}/events", status_code=201)
    def launch_event_add(lid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        e = call(L.save_event, engine, tenant, user, lid, body)
        audit(engine, user, "create", lid, e.get("ad") or "Etkinlik sonucu", {"etkinlik": e["id"], "kaynak": e["kaynak"]})
        return {"event": e}

    @app.put(R + "/{lid}/events/{eid}")
    def launch_event_put(lid: str, eid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        e = call(L.save_event, engine, tenant, user, lid, body, eid)
        audit(engine, user, "update", lid, e.get("ad") or "Etkinlik sonucu", {"etkinlik": e["id"]})
        return {"event": e}

    @app.delete(R + "/{lid}/events/{eid}")
    def launch_event_del(lid: str, eid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        out = call(L.delete_entry, engine, tenant, user, lid, "events", eid)
        audit(engine, user, "delete", lid, "Etkinlik kaydı", {"etkinlik": eid})
        return out

    @app.get(R + "/{lid}/media")
    def launch_media(lid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _ = ctx(request)
        full = call(L.get_full, engine, tenant, lid)
        return PV.bagla(media_of(engine, tenant, full), lambda: K.for_media(engine, full))

    @app.post(R + "/{lid}/media", status_code=201)
    def launch_media_add(lid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        m = call(L.save_media, engine, tenant, user, lid, body)
        audit(engine, user, "create", lid, m["baslik"], {"medya": m["id"]})
        return {"media": m}

    @app.delete(R + "/{lid}/media/{mid}")
    def launch_media_del(lid: str, mid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        out = call(L.delete_entry, engine, tenant, user, lid, "media", mid)
        audit(engine, user, "delete", lid, "Medya kaydı", {"medya": mid})
        return out

    @app.get(R + "/{lid}/crm-todo")
    async def launch_crm_todo(lid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user = await run_in_threadpool(ctx, request)
        full = call(L.get_full, engine, tenant, lid)
        ev, warn = await run_in_threadpool(events_of, engine, full)
        items = L.crm_todo(ev, L.portal_media(engine, lid), full)
        if not can(user, F_BUDGET):
            items = [{**i, "alanlar": {k: v for k, v in i["alanlar"].items() if "gelir" not in k.lower() and "gider" not in k.lower()}}
                     for i in items]
        return PV.bagla({"items": items, "uyarilar": warn}, lambda: K.for_crm_todo(engine, full, crm.schema()))

    # ---- değerlendirme

    def review_numbers(engine, tenant, lid: str, gun: int) -> dict[str, Any]:
        full = L.get_full(engine, tenant, lid)
        ev, _warn = events_of(engine, full)
        media = media_of(engine, tenant, full)["ton"]
        return RP.numbers(full, L.days_of(engine, lid), gun, ev, media)

    def draft_job(jid: str, tenant: str, user: str, lid: str, gun: int, priority: int) -> None:
        engine = rt().store.engine
        try:
            C.job_update(engine, jid, durum="calisiyor", adim="Zeki AI özeti yazılıyor")
            llm = rt().llm_for("marketing", priority)
            if llm is None:
                C.job_update(engine, jid, durum="bitti", adim=None,
                             sonuc={"uyari": "Zeki AI modeli bu kurulumda bağlı değil: rapor yalnız rakam tablosuyla hazır."})
                return
            full = L.get_full(engine, tenant, lid)
            rv = L.review_get(engine, lid, gun)
            if not rv:
                raise C.MarketingError("Rapor rakamları bulunamadı.")
            ozet, oneriler, dog = RP.draft_text(llm, full, rv["rakam"], st()["claims"])
            L.review_put_text(engine, lid, gun, ozet, oneriler, dog)
            C.job_update(engine, jid, durum="bitti", adim=None, sonuc={"gun": gun, "dusen": dog["dusenSayisi"]})
            admin_mod.audit(engine, user, "run", "marketing_launch", lid, f"D+{gun} lansman raporu", {"dusen": dog["dusenSayisi"]})
        except Exception as e:  # noqa: BLE001 — iş hatası ekranda görünür
            log.exception("launch review job failed")
            C.job_update(engine, jid, durum="hata", adim=None, hata=str(e)[:500] or e.__class__.__name__)

    def start_review(engine, tenant, user: str, lid: str, gun: int, priority: int) -> dict[str, Any]:
        rakam = review_numbers(engine, tenant, lid, gun)
        rv = L.review_put_numbers(engine, lid, gun, rakam, user)
        head = L.get(engine, tenant, lid)
        job = C.job_create(engine, tenant, user, head["planId"], f"lansman-rapor-{gun}", {"lansman": lid, "gun": gun})
        pool.submit(draft_job, job["id"], tenant, user, lid, gun, priority)
        return {"review": rv, "job": job}

    @app.get(R + "/{lid}/reviews")
    def launch_reviews(lid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        full = call(L.get_full, engine, tenant, lid)
        jobs = [j for j in C.jobs_of(engine, full["planId"]) if j["tur"].startswith("lansman-rapor")
                and (j.get("hedef") or {}).get("lansman") == lid]
        return PV.bagla({"items": money(user, full)["reviews"], "jobs": jobs},
                        lambda: K.for_reviews(engine, tenant, full, logo_db()))

    @app.post(R + "/{lid}/reviews/{gun}/draft", status_code=202)
    async def launch_review_draft(lid: str, gun: int, request: Request) -> dict[str, Any]:
        engine, tenant, user = await run_in_threadpool(ctx, request)
        if gun not in L.REVIEW_DAYS:
            raise HTTPException(status_code=400, detail={"code": "MARKETING", "message": "Değerlendirme günü 7 ya da 30 olmalı."})
        out = await run_in_threadpool(call, start_review, engine, tenant, user, lid, gun, NORMAL)
        audit(engine, user, "run", lid, f"D+{gun} lansman raporu", {"elle": True})
        if not can(user, F_BUDGET):
            out["review"] = {**out["review"], "rakam": RP.redact(out["review"]["rakam"])}
        return out

    @app.post(R + "/{lid}/reviews/{gun}/decide")
    def launch_review_decide(lid: str, gun: int, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        need(user, F_DECIDE, "Lansman değerlendirme kararı (pazarlama planı onayı)")
        rv = call(L.review_decide, engine, tenant, user, lid, gun, str(body.get("karar") or ""), body.get("gerekce"))
        audit(engine, user, "approve", lid, f"D+{gun} kararı", {"karar": rv["karar"], "gerekce": rv["gerekce"]})
        return {"review": rv if can(user, F_BUDGET) else {**rv, "rakam": RP.redact(rv["rakam"])}}

    @app.get(R + "/{lid}/export.pdf")
    async def launch_pdf(lid: str, request: Request) -> Response:
        engine, tenant, user = await run_in_threadpool(ctx, request)
        full = call(L.get_full, engine, tenant, lid)
        body = await run_in_threadpool(call, RP.report_pdf, full, full["reviews"], can(user, F_BUDGET), user)
        audit(engine, user, "run", lid, full["baslik"], {"disaAktar": "pdf"})
        return Response(body, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="lansman-raporu-{lid}.pdf"'})

    # ------------------------------------------------------------------ zamanlayıcı

    def owner_mail(user: str | None) -> list[str]:
        mail = crm.email_of(user) if user else None
        return [mail] if mail else []

    def run_due(engine, tenant: str, force: bool) -> dict[str, Any]:
        s = st()
        today = C.today()
        now_hour = datetime.now(C.TZ).hour
        out: dict[str, Any] = {"tarih": today.isoformat(), "acilan": [], "hatalar": []}
        # 1 — onaylı planların lansmanı kendiliğinden açılır (K1)
        for p in L.plans_due(engine, tenant, today, s["openDays"]):
            try:
                card = C.card_get(engine, tenant, p["stokKodu"]) or {}
                k = card.get("kitap") or {}
                lid = L.create(engine, tenant, "sistem", p["id"], s, book_name=k.get("ad"), kapak=k.get("kapak"))
                out["acilan"].append(lid)
                admin_mod.audit(engine, "sistem", "create", "marketing_launch", lid, p.get("baslik"), {"plan": p["id"], "kendiliginden": True})
            except C.MarketingError as e:
                out["hatalar"].append(f"{p['id']}: {e}")
        # 2 — okuma: sipariş her koşuda, Logo günde bir
        last = C.meta_get(engine, tenant, "launch-logo")
        logo = force or (now_hour >= s["dailyHour"] and last.get("tarih") != today.isoformat())
        active = L.list_launches(engine, tenant, durum=",".join(L.ACTIVE))
        rep = TR.refresh(engine, tenant, active, src, s, logo=logo, today=today, detail_of=detail_of,
                         exit_of=exit_of_for(engine, tenant))
        out["okuma"] = rep
        if logo:
            C.meta_set(engine, tenant, "launch-logo", {"tarih": today.isoformat(), "veriSonu": rep.get("veriSonuLogo"),
                                                       "hata": len(rep["hatalar"])})
        # 3 — D+7 / D+30 raporu (günlük okumadan sonra; rakam hemen, Zeki AI özeti arka planda)
        made: dict[str, list[int]] = {}
        if logo:
            for x in active:
                p = date.fromisoformat(x["yayinGunu"])
                for g in L.REVIEW_DAYS:
                    if today >= p + timedelta(days=g) and not L.review_get(engine, x["id"], g):
                        try:
                            start_review(engine, tenant, "sistem", x["id"], g, BATCH)
                            made.setdefault(x["id"], []).append(g)
                        except (C.MarketingError, SourceError) as e:
                            out["hatalar"].append(f"{x['id']} D+{g}: {e}")
        out["rapor"] = made
        # 4 — stok–talep çatışması: anında, kitap başına günde en çok bir kez
        heads = {h["id"]: h for h in L.list_launches(engine, tenant, durum=",".join(L.ACTIVE))}
        stock_sent = []
        for h in heads.values():
            sig = h.get("sinyal") or {}
            if not (sig.get("stokCatismasi") or sig.get("dagilimYok")):
                continue
            key = f"launch-stock:{h['id']}"
            if C.meta_get(engine, tenant, key).get("tarih") == today.isoformat() and not force:
                continue
            to = list(dict.fromkeys(s["stockRecipients"] + owner_mail(h.get("sahip"))))
            dep = sig.get("depo") or {}
            text = (f"Lansman stok–talep uyarısı: {h['baslik']} (stok kodu {h['stokKodu']}, yayın {RP.tr_day(h['yayinGunu'])}).\n"
                    + (f"Açık sipariş {RP.tr_num(sig.get('bekleyen'))} adet, depo stoku {RP.tr_num(dep.get('deger'))} adet "
                       f"({dep.get('kaynakAdi') or '—'}).\n" if sig.get("stokCatismasi") else "")
                    + ("Yayın günü geçti, dağılım siparişi görünmüyor.\n" if sig.get("dagilimYok") else "")
                    + (f"\nLansman: {link(h['id'])}" if link() else ""))
            status = _send_mail(f"ZEKİ lansman: stok uyarısı — {h['baslik']}", text, to) if to else "no_recipient"
            C.meta_set(engine, tenant, key, {"tarih": today.isoformat(), "sonuc": status})
            with engine.begin() as c:
                C.event(c, h["planId"], "sistem", "bildirim", None, {"konu": "lansman stok uyarısı", "alici": len(to), "sonuc": status})
            stock_sent.append({"lansman": h["id"], "sonuc": status})
        out["stokUyarisi"] = stock_sent
        # 5 — günlük tek özet (D−7 açık madde, bugün yayında, ilk hafta hedef altı, hazır rapor)
        if logo:
            items = []
            for h in heads.values():
                g = h.get("gun")
                sig = h.get("sinyal") or {}
                notes = []
                if g == -7:
                    full = L.get_full(engine, tenant, h["id"])
                    open_n = sum(1 for t in full["tasks"] if t["durum"] == "bekliyor")
                    notes.append(f"Yayına 7 gün: kontrol listesinde {open_n} açık madde.")
                if g == 0:
                    dist = sig.get("dagilim") or {}
                    dep = sig.get("depo") or {}
                    notes.append(f"Bugün yayında. Depo {RP.tr_num(dep.get('deger'))} ({dep.get('kaynakAdi') or '—'}), dağılım "
                                 f"{RP.tr_num(dist.get('adet'))} adet / {RP.tr_num(dist.get('bayi'))} bayi, açık sipariş "
                                 f"{RP.tr_num(sig.get('bekleyen'))}.")
                if g is not None and 1 <= g < 7 and sig.get("hedefAltinda"):
                    notes.append(("Faturalı satış" if sig.get("oranEsas") == "fatura" else "Sipariş")
                                 + f" hedef payının %{RP.tr_num((sig.get('oran') or 0) * 100)}'inde.")
                for rg in made.get(h["id"], []):
                    notes.append(f"D+{rg} değerlendirme raporu hazır; karar bekliyor.")
                if notes:
                    items.append({**h, "notlar": notes})
            dg = C.meta_get(engine, tenant, "launch-digest")
            if items and (dg.get("tarih") != today.isoformat() or force):
                text = RP.digest_text(items, link())
                status = _send_mail(f"ZEKİ lansman özeti ({today.strftime('%d.%m.%Y')})", text, s["recipients"]) \
                    if s["recipients"] else "no_recipient"
                owners: dict[str, list[dict[str, Any]]] = {}
                for it in items:
                    for m in owner_mail(it.get("sahip")):
                        if m not in s["recipients"]:
                            owners.setdefault(m, []).append(it)
                for m, its in owners.items():
                    _send_mail(f"ZEKİ lansman özeti ({today.strftime('%d.%m.%Y')})", RP.digest_text(its, link()) or "", [m])
                C.meta_set(engine, tenant, "launch-digest", {"tarih": today.isoformat(), "sonuc": status, "kalem": len(items),
                                                             "sahip": len(owners)})
                out["ozet"] = {"kalem": len(items), "sonuc": status, "sahip": len(owners)}
        # 6 — risk bayrağının Zeki AI cümlesi (günlük okumadan sonra; BATCH). Bayrak kuraldır, cümle yalnız açıklar.
        if logo:
            try:
                out["risk"] = LR.run(engine, tenant, list(heads.values()), s["alertRatio"], LR.settings(admin_mod.conf),
                                     rt().llm_for("marketing", BATCH), s["claims"])
            except Exception as e:  # noqa: BLE001 — cümle yazılamazsa ekranda kural cümlesi kalır
                out["hatalar"].append(f"risk cümlesi: {e}")
        C.meta_set(engine, tenant, "launch-run-due", {k: v for k, v in out.items() if k != "okuma"}
                   | {"okuma": {k: rep.get(k) for k in ("lansman", "gun", "logo", "veriSonuLogo")}, "hataSayisi": len(rep["hatalar"])})
        return out

    return {"sources": src, "run_due": run_due}
