"""Pazarlama uçları: /api/v1/marketing/*.

Sayfa kapısı `access.RULES` (`sayfa:pazarlama-yeni-kitap`); taslak yazma `ozellik:pazarlama.plan-yaz` (`FEATURE_RULES`),
dışa aktarım `ozellik:veri.disa-aktar`. Açıkça verilen yetkiler ucun içinde denetlenir: plan onayı
`ozellik:pazarlama.plan-onay`, eşik üstü bütçe `ozellik:pazarlama.butce-ust-onay`, materyalin editoryal onayı
`ozellik:pazarlama.materyal-editoryal-onay`. Bütçe tutarları `ozellik:pazarlama.butce-gor` olmayan kişiye gitmez.

Zamanlayıcı (`timas-marketing.timer`) yalnız `POST /api/v1/marketing/run-due`'yu çağırır; M18'in günlük işi (15'inde
ay taslağı, föy denetimi, hatırlatmalar) oradan kancayla koşar.
Sözleşme ucu (M16, M18, M19, M20–M23 okur): `GET /api/v1/marketing/contract/plans`.
M18 aylık plan ve satış föyü uçları `monthly_api.py`'de (`/months/*`, `/foy*`, `/contract/month/*`).
"""
from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Any, Callable

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import pazarlama_kaynak as PK
from semantic_bridge import provenance as PV
from semantic_bridge.marketing import core as C
from semantic_bridge.marketing import export as X
from semantic_bridge.marketing import kaynak_plan as K
from semantic_bridge.marketing import plans as P
from semantic_bridge.marketing.sources import Crm, SourceError
from semantic_layer.runtime.llm_queue import NORMAL

log = logging.getLogger("semantic.marketing.api")

R = "/api/v1/marketing"
PAGE = "sayfa:pazarlama-yeni-kitap"
F_WRITE = "ozellik:pazarlama.plan-yaz"
F_BUDGET = "ozellik:pazarlama.butce-gor"
F_APPROVE = "ozellik:pazarlama.plan-onay"
F_UPPER = "ozellik:pazarlama.butce-ust-onay"
F_EDITORIAL = "ozellik:pazarlama.materyal-editoryal-onay"
F_EXPORT = "ozellik:veri.disa-aktar"
#: Zeki AI önerisinde varsayılan olarak yazılan materyaller (iş tanımı: föy, basın bülteni, sosyal, e-bülten konu
#: satırı, video senaryosu). Arka kapak CRM'de çoğunlukla dolu (9.373 kitap); istenirse tek tek üretilir.
SUGGEST_MATERIALS = ("foy", "basin-bulteni", "sosyal", "e-bulten-konu", "video-senaryo")


def _redact(plan: dict[str, Any]) -> dict[str, Any]:
    """Bütçe tutarı görme yetkisi olmayan kişi için tutarlar boş."""
    out = {**plan, "butceToplam": None, "butceCerceve": None, "butceCerceveKaynak": None,
           "hedef": {k: v for k, v in (plan.get("hedef") or {}).items() if k not in ("ciro", "aylik")} if plan.get("hedef") else None}
    if "lines" in plan:
        out["lines"] = [{**ln, "tutar": None} for ln in plan["lines"]]
    z = plan.get("zeki")
    if z:
        out["zeki"] = {k: v for k, v in z.items() if k not in ("cerceve", "paylar")}
    return out


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None], can: Callable[[str, str], bool]):
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod
    from semantic_bridge.budget_api import _send_mail

    crm = Crm(lambda: admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo")
    pool = ThreadPoolExecutor(max_workers=max(1, int(os.environ.get("MARKETING_JOB_WORKERS", "2"))), thread_name_prefix="marketing")
    started = {"stale": False}
    lock = threading.Lock()
    #: Modül kancaları (M18 aylık plan ve föy): günlük iş ve meta ekleri. M16/M17 de aynı yolla bağlanır.
    hooks: dict[str, list[Any]] = {"run_due": [], "meta": []}

    def st() -> dict[str, Any]:
        return P.settings(admin_mod.conf)

    def db() -> tuple[Any, str]:
        r = rt()
        C.ensure(r.store.engine)
        admin_mod.ensure(r.store.engine)
        with lock:
            if not started["stale"]:
                started["stale"] = True
                n = C.fail_stale_jobs(r.store.engine)
                if n:
                    log.info("marketing: yarıda kalan %d iş kapatıldı", n)
        return r.store.engine, r.settings.tenant_id

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        require_caller(request)
        try:
            user, display = board_mod.session_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        engine, tenant = db()
        return engine, tenant, user, display

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

    def view(user: str, plan: dict[str, Any]) -> dict[str, Any]:
        return plan if can(user, F_BUDGET) else _redact(plan)

    def logo_db() -> str | None:
        """Sorgu bilgisindeki «USE [..]» satırı için yalnız veritabanı adı."""
        return PK.logo_db(rt)

    def pview(engine, tenant: str, user: str, plan: dict[str, Any]) -> dict[str, Any]:
        """Plan cevabı + sorgu bilgisi (plan, satır, takvim, materyal okumaları ve hesaplar)."""
        return PV.bagla(view(user, plan), lambda: K.for_plan(engine, tenant, plan, logo_db()))

    def audit(engine, user: str, action: str, plan: dict[str, Any], detail: Any = None, kind: str = "marketing_plan") -> None:
        admin_mod.audit(engine, user, action, kind, plan.get("id"), plan.get("baslik"), detail)

    def m10():
        return P.m10_engine(app.state)

    def link(path: str = "") -> str:
        base = (admin_mod.conf("ALERT_LINK") or "").split("/uyarilar")[0]
        return f"{base}/pazarlama/{path}" if base else ""

    def notify(engine, tenant: str, plan: dict[str, Any], subject: str, text: str, to_owner: bool) -> None:
        """Bildirim arka planda; sonucu plan geçmişine yazılır. SMTP ya da alıcı yoksa «gönderilemedi» kaydı kalır."""
        def run() -> None:
            try:
                to = list(st()["recipients"])
                if to_owner and plan.get("sahip"):
                    mail = crm.email_of(plan["sahip"])
                    to = [mail] if mail else to
                status = _send_mail(subject, text, to) if to else "no_recipient"
                with engine.begin() as c:
                    C.event(c, plan["id"], "sistem", "bildirim", None, {"konu": subject, "alici": len(to), "sonuc": status})
            except Exception as e:  # noqa: BLE001
                log.warning("marketing: bildirim gönderilemedi: %s", e)
        pool.submit(run)

    # ------------------------------------------------------------------ genel

    @app.get(R + "/meta")
    def mkt_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        s = st()
        last = C.meta_get(engine, tenant, "run-due")
        extra: dict[str, Any] = {}
        for fn in hooks["meta"]:
            extra.update(fn(user))
        me_extra = extra.pop("meExtra", {})
        return {
            **extra,
            "channels": C.CHANNELS, "statuses": C.STATUSES, "kinds": C.KINDS, "materials": {k: v[0] for k, v in C.MATERIALS_KINDS.items()},
            "materialStatuses": C.MATERIAL_STATUSES, "taskStatuses": C.TASK_STATUSES, "dateSources": C.DATE_SOURCES,
            "settings": {"horizonDays": s["horizonDays"], "noPlanDays": s["noPlanDays"], "materialDays": s["materialDays"],
                         "remindDays": s["remindDays"], "requiredMaterials": s["requiredMaterials"],
                         "threshold": s["threshold"] if can(user, F_BUDGET) else None, "dateOrder": s["dateOrder"],
                         "thresholdSet": s["threshold"] is not None},
            "lastRun": last or None,
            "modelReady": getattr(rt(), "llm", None) is not None,
            "me": {"username": user, "display": display, "canWrite": can(user, F_WRITE), "canSeeBudget": can(user, F_BUDGET),
                   "canApprove": can(user, F_APPROVE), "canUpperApprove": can(user, F_UPPER),
                   "canEditorial": can(user, F_EDITORIAL), "canExport": can(user, F_EXPORT), **me_extra},
        }

    @app.get(R + "/new-books")
    async def mkt_new_books(request: Request, frm: str = "", to: str = "", durum: str = "", yayinevi: str = "",
                            sahip: str = "", q: str = "", page: int = 0, yenile: bool = False) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        s = st()
        start = date.fromisoformat(frm) if frm else C.today()
        end = date.fromisoformat(to) if to else C.today() + timedelta(days=s["horizonDays"])
        if end < start:
            raise HTTPException(status_code=400, detail={"code": "MARKETING", "message": "Bitiş başlangıçtan önce olamaz."})
        trace: dict[str, Any] = {}
        out = await run_in_threadpool(call, P.new_books, engine, tenant, user, crm, s, frm=start, to=end, durum=durum,
                                      yayinevi=yayinevi, sahip=sahip, q=q, page=page, fresh=yenile, can_approve=can(user, F_APPROVE),
                                      trace=trace)
        if not can(user, F_BUDGET):
            for r in out["items"]:
                if r.get("hedef"):
                    r["hedef"] = {**r["hedef"], "ciro": None}
                if r.get("plan"):
                    r["plan"] = {**r["plan"], "butce": None}
        return await run_in_threadpool(PV.bagla, out, lambda: K.for_new_books(engine, tenant, crm.schema(), s, out, trace, start, end))

    @app.get(R + "/books/{stok}/card")
    async def mkt_card(stok: str, request: Request, yenile: bool = False) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        out = await run_in_threadpool(call, P.card, engine, tenant, crm, m10(), stok, st(), fresh=yenile)
        if not can(user, F_BUDGET):
            out = {**out, "crmButce": None, "hedef": {k: v for k, v in (out.get("hedef") or {}).items() if k not in ("ciro", "aylik")}}
        return await run_in_threadpool(PV.bagla, out, lambda: K.for_card(engine, tenant, crm.schema(), app.state, out, logo_db()))

    @app.get(R + "/books/{stok}/emsal-adaylari")
    async def mkt_emsal_candidates(stok: str, request: Request, n: int = 10) -> dict[str, Any]:
        """Emsali girilmemiş kitaba anlamca yakın katalog kitapları (aday; seçim insanda). Satış sütunları SQL'den."""
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        if not 1 <= n <= 100:
            raise HTTPException(status_code=400, detail={"code": "MARKETING", "message": "Aday sayısı 1–100 olmalı."})
        eng = m10()
        card_ = await run_in_threadpool(call, P.card, engine, tenant, crm, eng, stok, st())
        out = await run_in_threadpool(call, P.emsal_candidates, engine, tenant, eng, card_, n)
        return PV.bagla(out, lambda: K.for_emsal_candidates(app.state, out))

    # ------------------------------------------------------------------ planlar

    @app.post(R + "/plans", status_code=201)
    async def mkt_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        kind = str(body.get("kind") or "yeni")
        if kind != "yeni":
            raise HTTPException(status_code=400, detail={"code": "MARKETING", "message": "Bu sürümde yalnız yeni kitap planı açılır."})
        pid = await run_in_threadpool(call, P.create_new_book_plan, engine, tenant, user, crm, m10(), st(), body)
        plan = C.plan_full(engine, tenant, pid)
        audit(engine, user, "create", plan, {"stok": plan["stokKodu"], "yayin": plan["yayinTarihi"], "kaynak": plan["yayinTarihiKaynagi"],
                                             "crmMateryal": len(plan["materials"])})
        return view(user, plan)

    @app.get(R + "/plans")
    def mkt_plans(request: Request, kind: str = "", durum: str = "", sahip: str = "", donem: str = "", stok: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        items = C.list_plans(engine, tenant, kind=kind, durum=durum, sahip=sahip, donem=donem,
                             stok=[x for x in stok.split(",") if x] if stok else None)
        return {"items": [view(user, p) for p in items], "total": len(items)}

    @app.get(R + "/plans/{plan_id}")
    def mkt_plan(plan_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        plan = call(C.plan_full, engine, tenant, plan_id)
        plan["ustOnayGerekli"] = C.needs_upper(plan["butceToplam"], st()["threshold"])
        plan["eksikMateryal"] = P._missing_materials(plan, st()["requiredMaterials"])
        return pview(engine, tenant, user, plan)

    @app.patch(R + "/plans/{plan_id}")
    def mkt_plan_update(plan_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        if "butceCerceve" in body and not can(user, F_BUDGET):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Bütçe görme yetkiniz yok."})
        out = call(C.update_plan, engine, tenant, user, plan_id, body)
        if "yayinTarihi" in body:
            call(C.reschedule, engine, tenant, user, plan_id)
            out = C.plan_full(engine, tenant, plan_id)
        audit(engine, user, "update", out, {k: body[k] for k in ("baslik", "yayinTarihi", "sahip", "butceCerceve") if k in body})
        return pview(engine, tenant, user, out)

    @app.delete(R + "/plans/{plan_id}")
    def mkt_plan_delete(plan_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(C.delete_plan, engine, tenant, plan_id)
        audit(engine, user, "delete", out)
        return {"ok": True}

    @app.put(R + "/plans/{plan_id}/lines")
    def mkt_lines(plan_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_BUDGET, "Bütçe görme")
        out = call(C.replace_lines, engine, tenant, user, plan_id, body.get("items"))
        audit(engine, user, "update", out, {"butce": out["butceToplam"], "satir": len(out["lines"])})
        return pview(engine, tenant, user, out)

    @app.put(R + "/plans/{plan_id}/tasks")
    def mkt_tasks(plan_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(C.replace_tasks, engine, tenant, user, plan_id, body.get("items"))
        audit(engine, user, "update", out, {"takvim": len(out["tasks"])})
        return pview(engine, tenant, user, out)

    @app.get(R + "/plans/{plan_id}/events")
    def mkt_events(plan_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        call(C.plan_full, engine, tenant, plan_id)
        items = C.events(engine, plan_id)
        if not can(user, F_BUDGET):
            for e in items:
                for side in ("eski", "yeni"):
                    if isinstance(e.get(side), dict):
                        e[side] = {k: v for k, v in e[side].items() if k not in ("toplam", "butce", "butce_cerceve", "butce_toplam")}
        return PV.bagla({"items": items}, lambda: K.for_events(engine, plan_id))

    # ------------------------------------------------------------------ Zeki AI

    def run_job(jid: str, tenant: str, user: str, plan_id: str, turler: list[str], sug: dict[str, Any] | None) -> None:
        engine = rt().store.engine
        try:
            s = st()
            C.job_update(engine, jid, durum="calisiyor", adim="Karne okunuyor")
            plan = C.plan_full(engine, tenant, plan_id)
            card_ = P.card(engine, tenant, crm, m10(), plan["stokKodu"], s) if plan.get("stokKodu") else {}
            llm = rt().llm_for("marketing", NORMAL)
            if llm is None:
                C.job_update(engine, jid, durum="bitti", adim=None,
                             sonuc={"uyari": "Zeki AI modeli bu kurulumda bağlı değil: kanal ve bütçe kural ve emsal oranlarıyla "
                                             "kuruldu; gerekçe ve metin taslağı yazılamadı."})
                return
            result: dict[str, Any] = {"materyal": []}
            if sug is not None:
                zeki = dict(plan.get("zeki") or {})
                C.job_update(engine, jid, adim="Emsal kontrolü")
                zeki["emsal"] = P.check_emsal(llm, card_, s)
                C.job_update(engine, jid, adim="Kanal gerekçesi")
                ex = P.explain_channels(llm, card_, plan, sug, s)
                C.job_update(engine, jid, adim="Hedef okur ve konumlama")
                pos = P.positioning(llm, card_, plan, s)
                zeki.update({"kanalGerekce": ex.get("metin"), "konumlama": pos.get("metin"), "cerceve": sug.get("cerceve"),
                             "paylar": sug.get("paylar"), "dusen": (ex.get("dusenSayisi") or 0) + (pos.get("dusenSayisi") or 0),
                             "zaman": C.iso(C.now()), "kim": user})
                C.set_fields(engine, plan_id, zeki_json=C.dump(zeki))
                with engine.begin() as c:
                    C.event(c, plan_id, user, "zeki-oneri", None, {"emsalKontrol": len(zeki["emsal"]), "dusen": zeki["dusen"]})
            for tur in turler:
                C.job_update(engine, jid, adim=f"{C.MATERIALS_KINDS[tur][0]} taslağı")
                plan = C.plan_full(engine, tenant, plan_id)
                metin, dog = P.draft_material(llm, card_, plan, tur, s)
                if metin:
                    m = C.add_material(engine, tenant, user, plan_id, tur, metin, "zeki", dog, replace_draft=True)
                    result["materyal"].append({"tur": tur, "id": m["id"], "dusen": dog["dusenSayisi"]})
                else:
                    result["materyal"].append({"tur": tur, "id": None, "dusen": dog["dusenSayisi"],
                                               "not": "Denetimden geçen cümle kalmadı; taslak yazılmadı."})
            C.job_update(engine, jid, durum="bitti", adim=None, sonuc=result)
            admin_mod.audit(engine, user, "run", "marketing_plan", plan_id, "Zeki AI önerisi", result)
        except Exception as e:  # noqa: BLE001 — iş hatası ekranda görünür, köprüyü düşürmez
            log.exception("marketing job failed")
            C.job_update(engine, jid, durum="hata", adim=None, hata=str(e)[:500] or e.__class__.__name__)

    @app.post(R + "/plans/{plan_id}/suggest", status_code=202)
    async def mkt_suggest(plan_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Kanal/bütçe önerisi hemen (kural + emsal oranı, elle düzeltilen satırlar korunur); gerekçe, emsal kontrolü ve
        materyal taslakları arka planda (iş kuyruğu, `GET …/jobs`)."""
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        s = st()
        plan = call(C.plan_full, engine, tenant, plan_id)
        if plan["kind"] != "yeni":
            raise HTTPException(status_code=409, detail={"code": "MARKETING", "message": "Bu öneri yeni kitap planı içindir; "
                                                         "backlist planının taslakları Backlist ekranından istenir."})
        card_ = await run_in_threadpool(call, P.card, engine, tenant, crm, m10(), plan["stokKodu"], s)
        sug = None
        if plan["durum"] in C.EDITABLE:
            sug = await run_in_threadpool(call, P.apply_budget_suggestion, engine, tenant, user, crm, plan, card_, s)
        done = {m["tur"] for m in plan["materials"] if m["durum"] == "onayli"}
        want = [t for t in (body.get("materyaller") or SUGGEST_MATERIALS) if t in C.MATERIALS_KINDS and t not in done]
        job = call(C.job_create, engine, tenant, user, plan_id, "suggest", {"materyaller": want, "butce": sug is not None})
        pool.submit(run_job, job["id"], tenant, user, plan_id, want, sug)
        plan = C.plan_full(engine, tenant, plan_id)
        audit(engine, user, "run", plan, {"oneri": True, "cerceve": (sug or {}).get("cerceve", {}).get("kaynak"), "materyal": want})
        return {"job": job, "plan": view(user, plan)}

    @app.get(R + "/plans/{plan_id}/jobs")
    def mkt_jobs(plan_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        call(C.plan_full, engine, tenant, plan_id)
        return {"items": C.jobs_of(engine, plan_id)}

    @app.post(R + "/plans/{plan_id}/materials", status_code=201)
    def mkt_material_new(plan_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        tur = str(body.get("tur") or "")
        if tur not in C.MATERIALS_KINDS:
            raise HTTPException(status_code=400, detail={"code": "MARKETING", "message": "Materyal türü tanınmıyor."})
        if body.get("metin"):
            m = call(C.add_material, engine, tenant, user, plan_id, tur, body["metin"], "kullanici")
            audit(engine, user, "create", {"id": m["id"], "baslik": m["turAdi"]}, {"plan": plan_id, "kaynak": "kullanici"}, "marketing_material")
            return {"material": m}
        if tur not in P.MATERIAL_PROMPTS or call(C.plan_full, engine, tenant, plan_id)["kind"] != "yeni":
            raise HTTPException(status_code=409, detail={"code": "MARKETING", "message": "Bu tür için Zeki AI taslağı bu ekrandan "
                                                         "yazılmaz; backlist planında Backlist ekranını kullanın ya da metni elle yazın."})
        job = call(C.job_create, engine, tenant, user, plan_id, "material", {"materyaller": [tur]})
        pool.submit(run_job, job["id"], tenant, user, plan_id, [tur], None)
        return {"job": job}

    @app.put(R + "/materials/{mid}")
    def mkt_material_update(mid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        m = call(C.update_material, engine, tenant, user, mid, body.get("metin"))
        audit(engine, user, "update", {"id": m["id"], "baslik": m["turAdi"]}, {"plan": m["planId"], "surum": m["surum"]}, "marketing_material")
        return {"material": m}

    @app.post(R + "/materials/{mid}/approve")
    def mkt_material_approve(mid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        seviye = str(body.get("seviye") or "")
        if seviye == "editoryal":
            need(user, F_EDITORIAL, "Materyal editoryal onayı")
        else:
            need(user, F_APPROVE, "Pazarlama onayı")
        m = call(C.approve_material, engine, tenant, user, mid, seviye)
        audit(engine, user, "approve", {"id": m["id"], "baslik": m["turAdi"]}, {"plan": m["planId"], "seviye": seviye, "surum": m["surum"]},
              "marketing_material")
        return {"material": m}

    # ------------------------------------------------------------------ onay akışı

    @app.post(R + "/plans/{plan_id}/submit")
    def mkt_submit(plan_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(C.submit, engine, tenant, user, plan_id)
        audit(engine, user, "update", out, {"durum": "onayda", "butce": out["butceToplam"]})
        upper = C.needs_upper(out["butceToplam"], st()["threshold"])
        notify(engine, tenant, out, f"Onay bekleyen pazarlama planı: {out['baslik']}",
               f"{user} planı onaya gönderdi.\nPlan: {out['id']} · {out['baslik']}\nYayın tarihi: {out.get('yayinTarihi') or '—'}\n"
               + ("Bütçe eşiğin üstünde: pazarlama onayına ek olarak üst onay gerekir.\n" if upper else "")
               + (f"\nPlan: {link('plan/' + out['id'])}" if link() else ""), False)
        return view(user, out)

    @app.post(R + "/plans/{plan_id}/withdraw")
    def mkt_withdraw(plan_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(C.withdraw, engine, tenant, user, plan_id)
        audit(engine, user, "update", out, {"durum": "taslak", "neden": "onaydan geri çekildi"})
        return view(user, out)

    def _decide(plan_id: str, body: dict[str, Any], request: Request, approve: bool, level: str) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_UPPER if level == "ust" else F_APPROVE, "Bütçe üst onayı" if level == "ust" else "Pazarlama planı onayı")
        out = call(C.decide, engine, tenant, user, plan_id, approve, body.get("note"), level=level, threshold=st()["threshold"])
        audit(engine, user, "approve" if approve else "reject", out, {"seviye": level, "not": body.get("note"), "durum": out["durum"],
                                                                    "arsivlenen": out.get("archived")})
        if not approve or out["durum"] == "onayli":
            what = "onaylandı" if approve else "geri gönderildi"
            notify(engine, tenant, out, f"Pazarlama planı {what}: {out['baslik']}",
                   f"Plan {what} ({user}).\n" + (f"Gerekçe: {body.get('note')}\n" if body.get("note") else "")
                   + (f"\nPlan: {link('plan/' + out['id'])}" if link() else ""), True)
        return view(user, out)

    @app.post(R + "/plans/{plan_id}/approve")
    def mkt_approve(plan_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        return _decide(plan_id, body, request, True, "pazarlama")

    @app.post(R + "/plans/{plan_id}/upper-approve")
    def mkt_upper(plan_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        return _decide(plan_id, body, request, True, "ust")

    @app.post(R + "/plans/{plan_id}/reject")
    def mkt_reject(plan_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        level = "ust" if (can(user, F_UPPER) and not can(user, F_APPROVE)) else "pazarlama"
        return _decide(plan_id, body, request, False, level)

    @app.post(R + "/plans/{plan_id}/revise", status_code=201)
    def mkt_revise(plan_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(C.revise, engine, tenant, user, plan_id, body.get("reason"))
        audit(engine, user, "create", out, {"revizyon": plan_id, "gerekce": body.get("reason")})
        return view(user, out)

    # ------------------------------------------------------------------ dışa aktarım ve CRM listesi

    def _card_for(engine, tenant, plan) -> dict[str, Any] | None:
        if not plan.get("stokKodu"):
            return None
        try:
            return P.card(engine, tenant, crm, m10(), plan["stokKodu"], st())
        except (C.MarketingError, SourceError) as e:
            log.warning("marketing: karne okunamadı (%s): %s", plan["id"], e)
            return C.card_get(engine, tenant, plan["stokKodu"])

    @app.get(R + "/plans/{plan_id}/export.csv")
    def mkt_csv(plan_id: str, request: Request) -> Response:
        engine, tenant, user, _ = ctx(request)
        plan = call(C.plan_full, engine, tenant, plan_id)
        text = X.plan_csv(plan, can(user, F_BUDGET))
        audit(engine, user, "run", plan, {"disaAktar": "csv"})
        return Response(text.encode("utf-8"), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="pazarlama-plani-{plan_id}.csv"'})

    @app.get(R + "/plans/{plan_id}/export.pdf")
    async def mkt_pdf(plan_id: str, request: Request) -> Response:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        plan = call(C.plan_full, engine, tenant, plan_id)
        card_ = await run_in_threadpool(_card_for, engine, tenant, plan)
        body = await run_in_threadpool(call, X.plan_pdf, plan, card_, can(user, F_BUDGET), user)
        audit(engine, user, "run", plan, {"disaAktar": "pdf"})
        return Response(body, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="pazarlama-plani-{plan_id}.pdf"'})

    @app.get(R + "/plans/{plan_id}/package.zip")
    def mkt_package(plan_id: str, request: Request) -> Response:
        engine, tenant, user, _ = ctx(request)
        plan = call(C.plan_full, engine, tenant, plan_id)
        body = X.package_zip(plan, can(user, F_BUDGET))
        audit(engine, user, "run", plan, {"disaAktar": "paket", "materyal": sum(1 for m in plan["materials"] if m["durum"] == "onayli")})
        return Response(body, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="yayina-hazir-paket-{plan_id}.zip"'})

    @app.get(R + "/plans/{plan_id}/crm-todo")
    async def mkt_todo(plan_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        plan = call(C.plan_full, engine, tenant, plan_id)
        card_ = await run_in_threadpool(_card_for, engine, tenant, plan)
        items = P.crm_todo(plan, card_)
        if not can(user, F_BUDGET):
            items = [{**i, "tutar": None} if i["tur"] != "proje-alani" else {**i, "deger": None, "crmDeger": None} for i in items]
        return PV.bagla({"items": items, "planOnayli": plan["durum"] == "onayli"}, lambda: K.for_todo(engine, tenant, plan, card_))

    @app.get(R + "/plans/{plan_id}/crm-todo.csv")
    async def mkt_todo_csv(plan_id: str, request: Request) -> Response:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        plan = call(C.plan_full, engine, tenant, plan_id)
        card_ = await run_in_threadpool(_card_for, engine, tenant, plan)
        text = X.todo_csv(P.crm_todo(plan, card_), can(user, F_BUDGET))
        audit(engine, user, "run", plan, {"disaAktar": "crm-listesi"})
        return Response(text.encode("utf-8"), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="crm-islenecek-{plan_id}.csv"'})

    # ------------------------------------------------------------------ sözleşme

    @app.get(R + "/contract/plans")
    def mkt_contract(request: Request, stok: str = "", kind: str = "", durum: str = "onayli", donem: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = C.contract(engine, tenant, stok=stok, kind=kind, durum=durum, donem=donem)
        if not can(user, F_BUDGET):
            out["items"] = [_redact(p) for p in out["items"]]
        return out

    # ------------------------------------------------------------------ zamanlayıcı

    @app.post(R + "/run-due")
    def mkt_run_due(request: Request, force: bool = False) -> dict[str, Any]:
        """Günlük: hatırlatma özeti (60/30/14 gün, 21 gün materyal, hedefi değişen, onay bekleyen) tek e-posta; onaylı
        olmayan planların karnesi tazelenir."""
        require_caller(request)
        engine, tenant = db()
        s = st()
        today = C.today()
        out: dict[str, Any] = {"tarih": today.isoformat()}
        try:
            until = today + timedelta(days=max(s["remindDays"] + [s["noPlanDays"], s["materialDays"]]))
            data = P.new_books(engine, tenant, "", crm, s, frm=today, to=until, fresh=True)
            rows: list[dict[str, Any]] = []
            page = 0
            while True:
                rows += data["items"]
                if len(rows) >= data["total"] or not data["items"]:
                    break
                page += 1
                data = P.new_books(engine, tenant, "", crm, s, frm=today, to=until, page=page)
            dg = P.digest(rows, s)
            out["ozet"] = {"yayinaKalan": {k: len(v) for k, v in dg["yayinaKalan"].items()}, "materyalEksik": len(dg["materyalEksik"]),
                           "hedefDegisti": len(dg["hedefDegisti"]), "onayBekleyen": len(dg["onayBekleyen"])}
            last = C.meta_get(engine, tenant, "digest")
            text = P.digest_text(dg, link("yeni-kitap"))
            if text is None:
                out["eposta"] = "yok"
            elif last.get("tarih") == today.isoformat() and last.get("sonuc") == "sent" and not force:
                out["eposta"] = "bugün gönderildi"
            else:
                status = _send_mail(f"ZEKİ pazarlama: yeni kitap planları ({today.strftime('%d.%m.%Y')})", text, s["recipients"]) \
                    if s["recipients"] else "no_recipient"
                C.meta_set(engine, tenant, "digest", {"tarih": today.isoformat(), "sonuc": status})
                out["eposta"] = status
        except (SourceError, C.MarketingError) as e:
            out["hata"] = str(e)
        refreshed, errors = 0, []
        eng = m10()
        for p in C.list_plans(engine, tenant, kind="yeni", durum="taslak,onayda,geri"):
            if not p.get("stokKodu"):
                continue
            try:
                P.build_card(engine, tenant, crm, eng, p["stokKodu"], s, fresh=True)
                refreshed += 1
            except (SourceError, C.MarketingError) as e:
                errors.append(f"{p['id']}: {e}")
        out["karne"] = {"tazelenen": refreshed, "hata": errors}
        # M18 (aylık plan taslağı, föy denetimi, hatırlatmalar) aynı zamanlayıcıyla koşar; biri düşerse diğeri sürer.
        for fn in hooks["run_due"]:
            try:
                out.update(fn(engine, tenant, force))
            except Exception as e:  # noqa: BLE001 — zamanlayıcı işi yarıda kalmasın, hata sonuçta görünsün
                log.exception("marketing run-due hook failed")
                out.setdefault("kancaHata", []).append(str(e)[:300])
        C.meta_set(engine, tenant, "run-due", out)
        return out

    # M18 Aylık pazarlama planı ve satış föyü: aynı yardımcılarla /months, /foy uçları.
    from types import SimpleNamespace

    from semantic_bridge.marketing import monthly_api

    monthly_api.register(app, rt, SimpleNamespace(
        ctx=ctx, call=call, need=need, db=db, crm=crm, pool=pool, audit=audit, link=link, can=can, conf=admin_mod.conf,
        notify=notify, send_mail=_send_mail, hooks=hooks, admin=admin_mod, require_caller=require_caller))

    return {"crm": crm, "pool": pool}
