"""M60 İzin yönetimi uçları: /api/v1/hr/leave/* (çalışan ve yönetici), /api/v1/hr/leave/admin/* (İK yönetimi).

Sayfa kapısı `access.RULES`: çalışan uçları `ik-izin`, `ik-izin-ekip`, `ik-anasayfa`, `ik-rehber` sayfalarından birini ister
(Herkes'e açık; uç kişinin kendi / ekibinin verisini döner); `admin/` uçları `ik-yonetim`. İşlem yetkisi
`ozellik:ik.izin-yonet` (talepler, bakiye, açılış, bordro listesi) ve `ozellik:ik.izin-ayar` (türler, tatiller, takvim,
akış); hassas türün ayrıntısı `ozellik:ik.ozluk-hassas`. Zamanlayıcı `timas-hr-leave.timer` her gece 02:10 →
`POST /api/v1/hr/leave/run-due` (sistem jetonu): hakediş + onay hatırlatması.

Her olay `hr_mail` kuyruğuna şirket içi e-posta yazar (tür hassassa tür adı yazılmaz). Değişiklik kaydına ad/tarih değil
talep kimliği ve olay yazılır.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import hr_core as H
from semantic_bridge import hr_kaynak as HK
from semantic_bridge import hr_leave as LV
from semantic_bridge import hr_mail as HM
from semantic_bridge import hr_portal as PT
from semantic_bridge.hr_portal_api import XLSX, _download

P = "/api/v1/hr/leave"
A = P + "/admin"
HK.TABLES.update(LV.TABLE_LABELS)


def register(app, hr: Any) -> None:
    ctx, need, call = hr.ctx, hr.need, hr.call

    def ready(request: Request) -> tuple[Any, str, H.Who]:
        engine, tenant, who = ctx(request)
        LV.ensure(engine)
        return engine, tenant, who

    def admin(request: Request, *keys: str, what: str) -> tuple[Any, str, H.Who]:
        engine, tenant, who = ready(request)
        need(who, *keys, what=what)
        return engine, tenant, who

    def can_hr(who: H.Who) -> bool:
        return who.can(LV.F_LEAVE)

    def sens(who: H.Who) -> bool:
        return who.can(PT.F_SENS)

    def max_mb() -> int:
        return int(hr.settings()["fileMaxMb"])

    # ------------------------------------------------------------------ bildirim

    def notify(engine: Any, tenant: str, event: str, req: Any) -> None:
        cfg = HM.settings(hr.conf)
        tsd = {t["key"]: t for t in LV.types(engine, tenant)}
        t = tsd.get(req.type_key, {})
        people = {p.id: p for p in LV._people(engine, tenant)}
        person = people.get(req.person_id)
        name = person.ad_soyad if person else "Çalışan"
        subject, body = LV.mail_text(event if event != "yonetici_onayladi" else "ik", req, name, t.get("label", "İzin"), bool(t.get("sensitive")),
                                     req.reject_reason)

        def to_person(p: Optional[Any], *, required: bool, ev: str = event, subj: str = subject, text: str = body) -> None:
            if p is None:
                return
            HM.enqueue(engine, tenant, cfg, event=f"izin_{ev}"[:40], to=p.mail_adresi, username=p.username, subject=subj, body=text,
                       ref_type="izin_talebi", ref_id=req.id, required=required)

        def to_hr() -> None:
            for addr in hr.settings()["alertRecipients"]:
                HM.enqueue(engine, tenant, cfg, event="izin_ik", to=addr, subject=subject, body=body, ref_type="izin_talebi",
                           ref_id=req.id, required=True)

        manager = next((p for p in people.values() if req.manager_id_no and p.id_no == req.manager_id_no), None)
        if event == "yeni":
            if req.status == "yonetici":
                to_person(manager, required=True)
            else:
                s, b = LV.mail_text("ik", req, name, t.get("label", "İzin"), bool(t.get("sensitive")))
                subject, body = s, b
                to_hr()
        elif event == "yonetici_onayladi":
            to_hr()
        elif event in ("onaylandi", "reddedildi"):
            to_person(person, required=False)
            if event == "onaylandi" and req.deputy_person_id:
                s, b = LV.mail_text("vekil", req, name, t.get("label", "İzin"), bool(t.get("sensitive")))
                to_person(people.get(req.deputy_person_id), required=False, ev="vekil", subj=s, text=b)
        elif event == "iptal":
            to_person(manager, required=False)

    # ------------------------------------------------------------------ çalışan

    @app.get(P + "/me")
    def leave_me(request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        out = LV.my_view(engine, tenant, who.user)
        out["rights"] = {"admin": can_hr(who), "settings": who.can(LV.F_LEAVE_SET), "sensitive": sens(who)}
        return out

    @app.post(P + "/calc")
    def leave_calc(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        me = call(LV._me, engine, tenant, who.user)
        out = call(LV.calc, engine, tenant, me, body)
        out.pop("type", None)
        return out

    @app.post(P + "/requests", status_code=201)
    def leave_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        out = call(LV.create, engine, tenant, who.user, body)
        req = LV._load_req(engine, tenant, out["id"])
        hr.audit(engine, who.user, "create", "hr_leave_request", out["id"], "İzin talebi", {"gun": out["days"], "durum": out["status"]})
        notify(engine, tenant, "yeni", req)
        return {"id": out["id"], "status": out["status"], "days": out["days"]}

    @app.post(P + "/requests/{rid}/cancel")
    def leave_cancel(rid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        out = call(LV.cancel, engine, tenant, who.user, can_hr(who), rid)
        hr.audit(engine, who.user, "update", "hr_leave_request", rid, "İzin talebi", {"olay": out["event"]})
        if out["event"] == "iptal":
            notify(engine, tenant, "iptal", out["request"])
        return {"ok": True, "status": out["request"].status}

    @app.post(P + "/requests/{rid}/decide")
    def leave_decide(rid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        out = call(LV.decide, engine, tenant, who.user, can_hr(who), rid, body)
        hr.audit(engine, who.user, "update", "hr_leave_request", rid, "İzin kararı", {"olay": out["event"]})
        notify(engine, tenant, out["event"], out["request"])
        return {"ok": True, "status": out["request"].status}

    @app.post(P + "/requests/{rid}/files", status_code=201)
    async def leave_file_add(rid: str, request: Request, filename: str = "") -> dict[str, Any]:
        engine, tenant, who = await run_in_threadpool(ready, request)
        mb = max_mb()
        if int(request.headers.get("content-length") or 0) > mb * 1024 * 1024:
            raise HTTPException(413, detail={"code": "HR", "message": f"Dosya {mb} MB sınırını aşıyor."})
        data = await request.body()
        out = await run_in_threadpool(call, LV.add_file, engine, tenant, who.user, sens(who) and can_hr(who), rid, filename, data, mb)
        hr.audit(engine, who.user, "upload", "hr_leave_request", rid, "İzin belgesi", {"boyut": out["size"]})
        return out

    @app.get(P + "/requests/{rid}/files/{fid}")
    def leave_file(rid: str, fid: str, request: Request) -> Response:
        engine, tenant, who = ready(request)
        data, name, mime, pid = call(LV.file_blob, engine, tenant, who.user, sens(who) and can_hr(who), can_hr(who), rid, fid)
        H.log_access(engine, tenant, who.user, "personel", pid, "indir", "izin belgesi")
        return _download(data, name, mime)

    @app.get(P + "/team")
    def leave_team(request: Request, month: str = "") -> dict[str, Any]:
        engine, tenant, who = ready(request)
        return call(LV.team_view, engine, tenant, who.user, month, sens(who))

    @app.get(P + "/today")
    def leave_today(request: Request) -> dict[str, Any]:
        engine, tenant, _ = ready(request)
        return {"items": LV.on_leave_today(engine, tenant)}

    # ------------------------------------------------------------------ İK yönetimi

    @app.get(A + "/requests")
    def leave_admin_requests(request: Request, status: str = "acik", type: str = "", month: str = "", q: str = "") -> dict[str, Any]:
        engine, tenant, who = admin(request, LV.F_LEAVE, what="İzin talepleri")
        items = call(LV.admin_requests, engine, tenant, sens(who), status=status, type_key=type, month=month, q=q)
        return {"items": items, "total": len(items), "status": LV.STATUS}

    @app.get(A + "/balances")
    def leave_admin_balances(request: Request) -> dict[str, Any]:
        engine, tenant, _ = admin(request, LV.F_LEAVE, what="İzin bakiyeleri")
        with HK.capture(engine) as got:
            items = LV.balances(engine, tenant)
            st = LV.stats(engine, tenant)
        out = {"items": items, "total": len(items), "stats": st}
        return hr.kaynak(out, got, "izin", {
            "items[]": ("bakiye", "Bakiye = izin defterindeki hareketlerin toplamı (açılış + hakediş − kullanım + iade ± düzeltme); "
                                  "kullanılabilir = bakiye − onay bekleyen yıllık izin günleri."),
            "total": ("bakiye", "Aktif personel sayısı (özlük kaydı)."),
            "stats": ("izinOzet", "Bugün izinde = onaylı ve bugünü kapsayan talep; onay bekleyen = yönetici ya da İK onayındaki "
                                  "talepler; birikmiş = bakiyesi 30 gün ve üstü; yaklaşan hakediş = 30 gün içindeki yıldönümü."),
        })

    @app.get(A + "/ledger/{pid}")
    def leave_admin_ledger(pid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who = admin(request, LV.F_LEAVE, what="İzin defteri")
        p = call(LV._person, engine, tenant, pid)
        return {"person": {"id": p.id, "idNo": p.id_no, "adSoyad": p.ad_soyad}, "summary": LV.summary_for(engine, tenant, p),
                "items": LV.ledger(engine, tenant, pid)}

    @app.post(A + "/ledger", status_code=201)
    def leave_admin_adjust(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = admin(request, LV.F_LEAVE, what="Bakiye düzeltme")
        out = call(LV.adjust, engine, tenant, who.user, body)
        hr.audit(engine, who.user, "update", "hr_leave_ledger", str(body.get("personId") or ""), "İzin bakiyesi düzeltildi",
                 {"gun": body.get("days")})
        return out

    @app.post(A + "/opening")
    async def leave_admin_opening(request: Request, apply: int = 0, filename: str = "") -> dict[str, Any]:
        engine, tenant, who = await run_in_threadpool(admin, request, LV.F_LEAVE, what="Açılış bakiyesi")
        if not filename.lower().endswith(".xlsx"):
            raise HTTPException(422, detail={"code": "HR", "message": "Yalnız .xlsx dosyası alınır."})
        data = await request.body()
        out = await run_in_threadpool(call, LV.import_opening, engine, tenant, who.user, data, apply=bool(apply))
        if apply and out["applied"]:
            hr.audit(engine, who.user, "import", "hr_leave_ledger", None, "İzin açılış bakiyesi aktarıldı", {"kisi": out["applied"]})
        return out

    @app.get(A + "/opening-template")
    def leave_admin_opening_template(request: Request) -> Response:
        from openpyxl import Workbook

        admin(request, LV.F_LEAVE, what="Açılış şablonu")
        import io

        wb = Workbook()
        ws = wb.active
        ws.title = "acilis"
        ws.append(["id_no", "gun", "tarih", "aciklama"])
        buf = io.BytesIO()
        wb.save(buf)
        return _download(buf.getvalue(), "izin-acilis-sablon.xlsx", XLSX)

    @app.get(A + "/payroll")
    def leave_admin_payroll(request: Request, month: str = "") -> Response:
        engine, tenant, who = admin(request, LV.F_LEAVE, what="Bordro izin listesi")
        month = month or date.today().isoformat()[:7]
        data = call(LV.payroll_xlsx, engine, tenant, month, sens(who))
        H.log_access(engine, tenant, who.user, "personel", "hepsi", "disa_aktar", f"bordro izin listesi {month}")
        return _download(data, f"bordro-izin-{month}.xlsx", XLSX)

    @app.get(A + "/settings")
    def leave_admin_settings(request: Request) -> dict[str, Any]:
        engine, tenant, _ = admin(request, LV.F_LEAVE, LV.F_LEAVE_SET, what="İzin ayarları")
        year = date.today().year
        return {"settings": {k.split(".", 1)[1]: v for k, v in LV.settings(engine, tenant).items()}, "types": LV.types(engine, tenant),
                "holidays": LV.holidays(engine, tenant, year) + LV.holidays(engine, tenant, year + 1), "calendars": LV.calendars(engine, tenant),
                "countModes": LV.COUNT_MODES, "weekdays": LV.WEEKDAYS}

    @app.put(A + "/settings")
    def leave_admin_settings_put(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = admin(request, LV.F_LEAVE_SET, what="İzin ayarları")
        out, changed = call(LV.save_settings, engine, tenant, who.user, body)
        if changed:
            hr.audit(engine, who.user, "update", "hr_leave_settings", None, "İzin ayarları", {"alanlar": changed})
        return {k.split(".", 1)[1]: v for k, v in out.items()}

    @app.post(A + "/types", status_code=201)
    def leave_admin_type_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = admin(request, LV.F_LEAVE_SET, what="İzin türü ekleme")
        out = call(LV.save_type, engine, tenant, who.user, body)
        hr.audit(engine, who.user, "create", "hr_leave_type", out["key"], out["label"])
        return out

    @app.patch(A + "/types/{key}")
    def leave_admin_type_update(key: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = admin(request, LV.F_LEAVE_SET, what="İzin türü")
        out = call(LV.save_type, engine, tenant, who.user, body, key)
        hr.audit(engine, who.user, "update", "hr_leave_type", key, out["label"], {"alanlar": sorted(body)})
        return out

    @app.put(A + "/holidays")
    def leave_admin_holidays(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = admin(request, LV.F_LEAVE_SET, what="Resmî tatiller")
        n = call(LV.save_holidays, engine, tenant, who.user, body.get("days") or [])
        hr.audit(engine, who.user, "update", "hr_holidays", None, "Resmî tatil takvimi", {"gun": n})
        return {"ok": True, "days": n}

    @app.post(A + "/holidays/fixed")
    def leave_admin_holidays_fixed(request: Request, year: int = 0) -> dict[str, Any]:
        engine, tenant, who = admin(request, LV.F_LEAVE_SET, what="Resmî tatiller")
        n = call(LV.add_fixed_holidays, engine, tenant, who.user, year or date.today().year)
        if n:
            hr.audit(engine, who.user, "update", "hr_holidays", None, "Sabit resmî tatiller eklendi", {"yil": year, "gun": n})
        return {"ok": True, "added": n}

    @app.put(A + "/calendars")
    def leave_admin_calendars(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = admin(request, LV.F_LEAVE_SET, what="Çalışma takvimi")
        out = call(LV.save_calendars, engine, tenant, who.user, body.get("items") or [])
        hr.audit(engine, who.user, "update", "hr_work_calendar", None, "Çalışma takvimleri", {"takvim": len(out)})
        return {"items": out}

    # ------------------------------------------------------------------ gece işi

    @app.post(P + "/run-due")
    def leave_run_due(request: Request) -> dict[str, Any]:
        """Zamanlayıcı (her gece 02:10): yıllık izin hakedişi + 2 iş günü onaysız talepler için günlük tek hatırlatma."""
        hr.require_caller(request)
        engine, tenant = hr.system()
        LV.ensure(engine)
        today = date.today()
        out = LV.run_due(engine, tenant, today)
        cfg = HM.settings(hr.conf)
        people = {p.id: p for p in LV._people(engine, tenant)}
        by_manager: dict[str, list[Any]] = {}
        to_hr = []
        for r in out["remind"]:
            if r.status == "yonetici" and r.manager_id_no:
                by_manager.setdefault(r.manager_id_no, []).append(r)
            else:
                to_hr.append(r)
        sent = 0
        for mgr_no, reqs in by_manager.items():
            mgr = next((p for p in people.values() if p.id_no == mgr_no), None)
            if mgr is None:
                continue
            names = ", ".join(sorted({people[r.person_id].ad_soyad for r in reqs if r.person_id in people}))
            HM.enqueue(engine, tenant, cfg, event="izin_hatirlatma", to=mgr.mail_adresi, username=mgr.username, required=True,
                       subject=f"{len(reqs)} izin talebi onayınızı bekliyor",
                       body=f"Onayınızı bekleyen izin talepleri: {names}.\n\nKarar vermek için: {{link}}/ik/izin/ekip",
                       ref_type="izin_talebi", ref_id=reqs[0].id)
            sent += 1
        if to_hr:
            for addr in hr.settings()["alertRecipients"]:
                HM.enqueue(engine, tenant, cfg, event="izin_hatirlatma", to=addr, required=True,
                           subject=f"{len(to_hr)} izin talebi İK onayı bekliyor",
                           body="İK onayı bekleyen izin talepleri var.\n\nİK yönetimi › İzinler: {link}/ik/yonetim?sekme=izinler",
                           ref_type="izin_talebi", ref_id=to_hr[0].id)
            sent += 1
        LV.mark_reminded(engine, tenant, [r.id for r in out["remind"]], today)
        if out["accrued"]:
            hr.audit(engine, "ZEKİ AI", "update", "hr_leave_ledger", None, "Yıllık izin hakedişi", {"kisi": len(out["accrued"])})
        return {"accrued": len(out["accrued"]), "accrualFrom": out["accrualFrom"], "reminders": sent, "waiting": len(out["remind"])}
