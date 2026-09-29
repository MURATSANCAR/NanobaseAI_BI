"""İK personel portalı uçları: /api/v1/hr/portal/* (çalışan) ve /api/v1/hr/portal/admin/* (İK yönetimi).

Sayfa kapısı `access.RULES`: çalışan uçları portal sayfalarından birini ister (İK ana sayfası, Profilim, Personel
rehberi, Duyurular, Evrak, SSS — «Herkes» rolüne açıktır); `admin/` uçları `sayfa:ik-yonetim` ister (açıkça verilir).
İşlem ve kişisel veri anahtarları `hr_portal.F_*` burada `Who.can` ile denetlenir; `ozluk-hassas` duyarlıdır,
yöneticiye ancak rolüyle gelir.

Değişiklik kaydına (`semantic_audit`) kişinin adı ya da alan değeri yazılmaz: personel no ve değişen alan anahtarları.
Kart açma, belge indirme ve Excel dışa aktarma `semantic_hr_access_log`'a düşer (konu türü «personel»).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Optional
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import hr_core as H
from semantic_bridge import hr_kaynak as HK
from semantic_bridge import hr_mail as HM
from semantic_bridge import hr_portal as PT

log = logging.getLogger("semantic_bridge.hr.portal")
P = "/api/v1/hr/portal"
A = P + "/admin"
SUBJECT = "personel"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

HK.TABLES.update(PT.TABLE_LABELS)
HK.TABLES.update(HM.TABLE_LABELS)

F_KADRO = "Aktif personel = durumu «Aktif» olan özlük kaydı; pasif = öbürleri (portal kaydı)."
F_GIRIS = ("İşe giren = son işe giriş tarihi bu ayın (yılın) ilk gününden bugüne olan kayıt; ayrılan = işten çıkış "
           "tarihi aynı aralıkta olan kayıt. Yıllık devir oranı = yıl içinde ayrılan ÷ (aktif + yıl içinde ayrılan).")
F_KIDEM = "Ortalama kıdem = aktif personelde son işe giriş (yoksa ilk işe giriş) tarihinden bugüne yıl; ortalama yaş doğum tarihinden."
F_DAGILIM = "Dağılım = aktif personelin alan değerine göre sayısı; alanı boş olan «Girilmemiş»."
F_YAKLASAN = "Yaklaşan tarih = aktif personelde çalışma izni bitişi ya da askerlik tecil bitişi bugünden ayar gün sayısı içinde (geçmiş olan dahil)."
F_EKSIK = ("Eksik zorunlu alan = zorunlu işaretli (belge dışı) alanlardan en az biri boş aktif kayıt; eksik belge = o belge "
           "türünde yüklenmiş dosyası olmayan aktif kayıt.")
F_TALEP = "Açık evrak talebi = durumu «Bekliyor» ya da «Hazırlanıyor» olan talep."


def _qname(name: str) -> str:
    return quote(name or "dosya", safe="")


def _download(data: bytes, name: str, mime: str, *, inline: bool = False) -> Response:
    disp = "inline" if inline else "attachment"
    return Response(content=data, media_type=mime, headers={
        "Content-Disposition": f"{disp}; filename*=UTF-8''{_qname(name)}", "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store"})


def register(app, hr: Any) -> None:
    ctx, need, call = hr.ctx, hr.need, hr.call

    def rights_of(who: H.Who) -> dict[str, bool]:
        return PT.rights(who)

    def ready(request: Request) -> tuple[Any, str, H.Who, dict[str, bool]]:
        engine, tenant, who = ctx(request)
        PT.ensure(engine)
        return engine, tenant, who, rights_of(who)

    def max_mb() -> int:
        return int(hr.settings()["fileMaxMb"])

    def mailcfg() -> dict[str, Any]:
        return HM.settings(hr.conf)

    def notify_hr(engine: Any, tenant: str, event: str, subject: str, body: str, ref_type: str, ref_id: str) -> None:
        """İK dağıtım adreslerine (HR_ALERT_RECIPIENTS) iş e-postası; kişi tercihi uygulanmaz."""
        cfg = mailcfg()
        for addr in hr.settings()["alertRecipients"]:
            HM.enqueue(engine, tenant, cfg, event=event, to=addr, subject=subject, body=body, ref_type=ref_type, ref_id=ref_id, required=True)

    async def body_bytes(request: Request) -> bytes:
        mb = max_mb()
        if int(request.headers.get("content-length") or 0) > mb * 1024 * 1024:
            raise HTTPException(413, detail={"code": "HR", "message": f"Dosya {mb} MB sınırını aşıyor."})
        return await request.body()

    # ------------------------------------------------------------------ çalışan: ana sayfa ve genel

    @app.get(P + "/meta")
    def portal_meta(request: Request) -> dict[str, Any]:
        engine, tenant, who, rg = ready(request)
        st = PT.settings(engine, tenant)
        return {"me": {"username": who.user, "display": who.display, "isAdmin": who.admin}, "rights": rg,
                "settings": st, "groups": PT.GROUPS, "fieldTypes": PT.FIELD_TYPES, "requestStatus": PT.REQUEST_STATUS,
                "delivery": PT.DELIVERY, "peopleStatus": list(PT.PEOPLE_STATUS), "fileMaxMb": max_mb(),
                "fileAccept": PT.FILE_ACCEPT, "imageAccept": ",".join(PT.IMAGE_EXT),
                "mail": {"mode": mailcfg()["mode"], "modes": HM.MODES, "domains": mailcfg()["domains"], "linkSet": bool(mailcfg()["link"]),
                         "hrRecipients": len(hr.settings()["alertRecipients"])}}

    @app.get(P + "/home")
    def portal_home(request: Request) -> dict[str, Any]:
        engine, tenant, who, rg = ready(request)
        me = PT.person_of(engine, tenant, who.user)
        d = H.load(me.data_json, {}) if me else {}
        today = date.today()
        mine = PT.list_requests(engine, tenant, user=who.user)
        out: dict[str, Any] = {
            "me": {"display": (me.ad_soyad if me else None) or who.display, "username": who.user,
                   "linked": me is not None, "unvan": d.get("unvan"), "departman": d.get("departman"),
                   "hasPhoto": bool(me and PT.photo(engine, tenant, me.id))},
            "rights": rg,
            # Kişinin açabildiği İK sayfaları: ana sayfa öbür İK ekranlarının kutucuğunu yalnız bunlar için gösterir.
            "pages": sorted(k for k in who.keys if k.startswith("sayfa:ik-")) if not who.admin else ["*"],
            "birthdays": PT.birthdays(engine, tenant, today)["upcoming"],
            "posts": [dict(p, body=p["body"][:280]) for p in PT.list_posts(engine, tenant, limit=3)],
            "menuToday": next(iter(PT.menu(engine, tenant, today, today)), None),
            "myOpenRequests": sum(1 for r in mine if r["status"] in ("bekliyor", "hazirlaniyor")),
        }
        from semantic_bridge import hr_leave as LV

        LV.ensure(engine)
        # Bugün izinde olanlar (tür yok) ve kişinin kullanılabilir yıllık izni; ekip onayı bekleyen sayısı.
        out["onLeave"] = LV.on_leave_today(engine, tenant, today)
        out["leave"] = {"available": LV.summary_for(engine, tenant, me, today)["available"] if me else None,
                        "teamWaiting": LV.team_waiting(engine, tenant, me.id_no) if me else 0}
        if rg["leave"]:
            out["leaveStats"] = LV.stats(engine, tenant, today)
        if rg["view"]:
            with HK.capture(engine) as got:
                s = PT.stats(engine, tenant, rg, today)
            out["stats"] = hr.kaynak(s, got, "ikpano", {
                "headcount": ("kadro", F_KADRO), "joined": ("giris", F_GIRIS), "left": ("giris", F_GIRIS),
                "avgTenureYears": ("kidem", F_KIDEM), "avgAgeYears": ("kidem", F_KIDEM), "by": ("dagilim", F_DAGILIM),
                "upcoming[]": ("yaklasan", F_YAKLASAN), "anniversaries[]": ("kidem", F_KIDEM),
                "completeness": ("eksik", F_EKSIK), "pendingRequests": ("talep", F_TALEP),
            }, rest=("kadro", F_KADRO), ignore=("expiryDays",))
        return out

    # ------------------------------------------------------------------ çalışan: Profilim

    @app.get(P + "/me")
    def portal_me(request: Request) -> dict[str, Any]:
        engine, tenant, who, _ = ready(request)
        return PT.my_profile(engine, tenant, who.user)

    @app.get(P + "/me/files/{fid}")
    def portal_me_file(fid: str, request: Request) -> Response:
        engine, tenant, who, _ = ready(request)
        me = PT.person_of(engine, tenant, who.user)
        if me is None:
            raise HTTPException(404, detail={"code": "HR", "message": "Özlük kaydınız bulunamadı."})
        allowed = {f["key"] for f in PT.fields(engine, tenant) if f["showProfile"] and f["type"] == "file"}
        data, name, mime, _ = call(PT.file_blob, engine, tenant, me.id, fid, allowed)
        return _download(data, name, mime)

    @app.get(P + "/me/photo")
    def portal_me_photo(request: Request) -> Response:
        engine, tenant, who, _ = ready(request)
        me = PT.person_of(engine, tenant, who.user)
        got = PT.photo(engine, tenant, me.id) if me else None
        if not got:
            raise HTTPException(404, detail={"code": "HR", "message": "Fotoğraf yok."})
        return _download(got[0], "fotograf", got[1], inline=True)

    # ------------------------------------------------------------------ çalışan: rehber, doğum günleri

    @app.get(P + "/directory")
    def portal_directory(request: Request) -> dict[str, Any]:
        from semantic_bridge import hr_leave as LV

        engine, tenant, _, _ = ready(request)
        out = PT.directory(engine, tenant)
        LV.ensure(engine)
        out["onLeave"] = {x["id"]: x["back"] for x in LV.on_leave_today(engine, tenant)}
        return out

    @app.get(P + "/photo/{pid}")
    def portal_photo(pid: str, request: Request) -> Response:
        engine, tenant, who, rg = ready(request)
        me = PT.person_of(engine, tenant, who.user)
        if not (PT.directory_photo_allowed(engine, tenant) or rg["view"] or (me is not None and me.id == pid)):
            raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Fotoğrafı görme yetkiniz yok."})
        got = PT.photo(engine, tenant, pid)
        if not got:
            raise HTTPException(404, detail={"code": "HR", "message": "Fotoğraf yok."})
        return _download(got[0], "fotograf", got[1], inline=True)

    @app.get(P + "/birthdays")
    def portal_birthdays(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ready(request)
        return PT.birthdays(engine, tenant)

    # ------------------------------------------------------------------ çalışan: duyurular, yemek, evrak, SSS

    @app.get(P + "/posts")
    def portal_posts(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ready(request)
        return {"items": PT.list_posts(engine, tenant)}

    @app.get(P + "/posts/{post_id}/image")
    def portal_post_image(post_id: str, request: Request) -> Response:
        engine, tenant, _, rg = ready(request)
        data, mime = call(PT.post_image, engine, tenant, post_id, all_=rg["portal"])
        return _download(data, "gorsel", mime, inline=True)

    @app.get(P + "/menu")
    def portal_menu(request: Request, start: str = "", end: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ready(request)
        today = date.today()
        a = call(H.parse_date, start, "Başlangıç") or (today - timedelta(days=today.weekday()))
        b = call(H.parse_date, end, "Bitiş") or (a + timedelta(days=13))
        if (b - a).days > 62:
            raise HTTPException(422, detail={"code": "HR", "message": "En çok iki aylık menü bir arada okunur."})
        return {"start": a.isoformat(), "end": b.isoformat(), "days": PT.menu(engine, tenant, a, b)}

    @app.get(P + "/docs")
    def portal_docs(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ready(request)
        return {"items": PT.list_docs(engine, tenant)}

    @app.get(P + "/docs/{did}/file")
    def portal_doc_file(did: str, request: Request) -> Response:
        engine, tenant, _, _ = ready(request)
        data, name, mime = call(PT.doc_blob, engine, tenant, did)
        return _download(data, name, mime)

    @app.get(P + "/requests/mine")
    def portal_my_requests(request: Request) -> dict[str, Any]:
        engine, tenant, who, _ = ready(request)
        me = PT.person_of(engine, tenant, who.user)
        return {"items": PT.list_requests(engine, tenant, user=who.user),
                "defaultMail": (me.mail_adresi if me else None)}

    @app.post(P + "/requests", status_code=201)
    def portal_request_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who, _ = ready(request)
        out = call(PT.create_request, engine, tenant, who.user, who.display, body)
        hr.audit(engine, who.user, "create", "hr_doc_request", out["id"], "Evrak talebi", {"tip": out["docType"]})
        notify_hr(engine, tenant, "evrak_yeni", f"Evrak talebi: {out['docType']}",
                  f"{out['display'] or out['username']} «{out['docType']}» istedi ({out['deliveryLabel']}).\n\n"
                  "Evrak talepleri: {link}/ik/yonetim?sekme=talepler", "evrak_talebi", out["id"])
        return out

    @app.get(P + "/requests/{rid}/files/{fid}")
    def portal_request_file(rid: str, fid: str, request: Request) -> Response:
        engine, tenant, who, _ = ready(request)
        data, name, mime = call(PT.request_file, engine, tenant, rid, fid, user=who.user)
        return _download(data, name, mime)

    @app.get(P + "/me/mail-pref")
    def portal_mail_pref(request: Request) -> dict[str, Any]:
        engine, tenant, who, _ = ready(request)
        return {"off": HM.pref_off(engine, tenant, who.user), "mode": mailcfg()["mode"]}

    @app.put(P + "/me/mail-pref")
    def portal_mail_pref_put(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who, _ = ready(request)
        out = HM.set_pref(engine, tenant, who.user, bool(body.get("off")))
        hr.audit(engine, who.user, "update", "hr_mail_pref", who.user, "E-posta bildirim tercihi", {"kapali": out["off"]})
        return out

    @app.delete(P + "/requests/{rid}")
    def portal_request_cancel(rid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who, _ = ready(request)
        call(PT.cancel_request, engine, tenant, who.user, rid)
        hr.audit(engine, who.user, "delete", "hr_doc_request", rid, "Evrak talebi geri alındı")
        return {"ok": True}

    @app.get(P + "/faq")
    def portal_faq(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ready(request)
        return {"items": PT.list_faq(engine, tenant)}

    # ------------------------------------------------------------------ İK yönetimi: personel

    def admin(request: Request, *keys: str, what: str) -> tuple[Any, str, H.Who, dict[str, bool]]:
        engine, tenant, who, rg = ready(request)
        need(who, *keys, what=what)
        return engine, tenant, who, rg

    @app.get(A + "/people")
    def admin_people(request: Request, q: str = "", durum: str = "Aktif", firma: str = "", departman: str = "",
                     ofis_lokasyon: str = "") -> dict[str, Any]:
        engine, tenant, _, rg = admin(request, PT.F_VIEW, PT.F_EDIT, what="Personel listesini görme")
        return PT.list_people(engine, tenant, rg, q=q, durum=durum,
                              filters={"firma": firma, "departman": departman, "ofis_lokasyon": ofis_lokasyon})

    @app.get(A + "/people/{pid}")
    def admin_person(pid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who, rg = admin(request, PT.F_VIEW, PT.F_EDIT, what="Personel kartını görme")
        out = call(PT.get_person, engine, tenant, rg, pid)
        H.log_access(engine, tenant, who.user, SUBJECT, pid, "goruntule", "özlük kartı" + (" (hassas dahil)" if rg["sensitive"] else ""))
        return out

    @app.post(A + "/people", status_code=201)
    def admin_person_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who, rg = admin(request, PT.F_EDIT, what="Personel kaydı ekleme")
        out, changed = call(PT.save_person, engine, tenant, who.user, rg, body)
        hr.audit(engine, who.user, "create", "hr_person", out["id"], f"Personel kaydı {out['idNo']}", {"alanlar": changed})
        return out

    @app.patch(A + "/people/{pid}")
    def admin_person_update(pid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who, rg = admin(request, PT.F_EDIT, what="Personel kaydını düzenleme")
        out, changed = call(PT.save_person, engine, tenant, who.user, rg, body, pid)
        if changed:
            hr.audit(engine, who.user, "update", "hr_person", pid, f"Personel kaydı {out['idNo']}", {"alanlar": changed})
        return out

    @app.delete(A + "/people/{pid}")
    def admin_person_delete(pid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who, _ = admin(request, PT.F_EDIT, what="Personel kaydını silme")
        need(who, PT.F_SENS, what="Belgeleriyle birlikte personel kaydını silme")
        out = call(PT.delete_person, engine, tenant, pid)
        H.log_access(engine, tenant, who.user, SUBJECT, pid, "sil", f"özlük kaydı ve {out['files']} belge")
        hr.audit(engine, who.user, "delete", "hr_person", pid, f"Personel kaydı {out['idNo']}", {"belge": out["files"]})
        return {"ok": True, **out}

    @app.post(A + "/people/{pid}/files/{field_key}", status_code=201)
    async def admin_person_file_add(pid: str, field_key: str, request: Request, filename: str = "") -> dict[str, Any]:
        engine, tenant, who, rg = await run_in_threadpool(admin, request, PT.F_EDIT, what="Belge yükleme")
        data = await body_bytes(request)
        out = await run_in_threadpool(call, PT.add_file, engine, tenant, who.user, rg, pid, field_key, filename, data, max_mb())
        hr.audit(engine, who.user, "upload", "hr_person", pid, "Personel belgesi yüklendi", {"belge": field_key, "boyut": out["size"]})
        return out

    @app.get(A + "/people/{pid}/files/{fid}")
    def admin_person_file(pid: str, fid: str, request: Request, inline: int = 0) -> Response:
        engine, tenant, who, rg = admin(request, PT.F_VIEW, PT.F_EDIT, what="Belgeyi görme")
        allowed = {f["key"] for f in PT.fields(engine, tenant) if f["type"] == "file" and f["showAdmin"]
                   and (rg["sensitive"] or not f["sensitive"])}
        data, name, mime, key = call(PT.file_blob, engine, tenant, pid, fid, allowed)
        H.log_access(engine, tenant, who.user, SUBJECT, pid, "indir", f"belge: {key}")
        return _download(data, name, mime, inline=bool(inline) and mime.startswith(("image/", "application/pdf")))

    @app.delete(A + "/people/{pid}/files/{fid}")
    def admin_person_file_delete(pid: str, fid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who, rg = admin(request, PT.F_EDIT, what="Belge silme")
        key = call(PT.delete_file, engine, tenant, rg, pid, fid)
        hr.audit(engine, who.user, "delete", "hr_person", pid, "Personel belgesi silindi", {"belge": key})
        return {"ok": True}

    @app.post(A + "/import")
    async def admin_import(request: Request, apply: int = 0, filename: str = "") -> dict[str, Any]:
        engine, tenant, who, rg = await run_in_threadpool(admin, request, PT.F_EDIT, what="Excel'den personel aktarma")
        data = await body_bytes(request)
        if not filename.lower().endswith(".xlsx"):
            raise HTTPException(422, detail={"code": "HR", "message": "Yalnız .xlsx dosyası alınır."})
        out = await run_in_threadpool(call, PT.import_xlsx, engine, tenant, who.user, rg, data, apply=bool(apply))
        if apply and out["applied"]:
            hr.audit(engine, who.user, "import", "hr_person", None, "Excel'den personel aktarıldı",
                     {"yeni": out["counts"]["new"], "guncellenen": out["counts"]["update"], "kolon": len(out["columns"])})
        return out

    @app.get(A + "/export")
    def admin_export(request: Request, durum: str = "hepsi") -> Response:
        engine, tenant, who, rg = admin(request, PT.F_EDIT, what="Personel listesini Excel'e aktarma")
        data = PT.export_xlsx(engine, tenant, rg, durum=durum)
        H.log_access(engine, tenant, who.user, SUBJECT, "hepsi", "disa_aktar",
                     "personel Excel" + (" (hassas dahil)" if rg["sensitive"] else ""))
        return _download(data, f"personel-{date.today().isoformat()}.xlsx", XLSX)

    @app.get(A + "/template")
    def admin_template(request: Request) -> Response:
        """Boş şablon: yalnız başlık satırı ve alan listesi, kişisel veri yok (genel dışa aktarma yetkisi istemez)."""
        engine, tenant, _, rg = admin(request, PT.F_EDIT, what="Personel şablonu")
        return _download(PT.export_xlsx(engine, tenant, rg, template=True), "personel-sablon.xlsx", XLSX)

    # ------------------------------------------------------------------ İK yönetimi: alanlar ve listeler

    @app.get(A + "/fields")
    def admin_fields(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = admin(request, PT.F_VIEW, PT.F_EDIT, PT.F_FIELDS, what="Alan listesini görme")
        return {"items": PT.fields(engine, tenant, include_inactive=True)}

    @app.post(A + "/fields", status_code=201)
    def admin_field_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who, rg = admin(request, PT.F_FIELDS, what="Alan ekleme")
        out, diff = call(PT.save_field, engine, tenant, who.user, rg, body)
        hr.audit(engine, who.user, "create", "hr_person_field", out["key"], out["label"], diff)
        return out

    @app.patch(A + "/fields/{key}")
    def admin_field_update(key: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who, rg = admin(request, PT.F_FIELDS, what="Alan ayarı")
        out, diff = call(PT.save_field, engine, tenant, who.user, rg, body, key)
        if diff:
            hr.audit(engine, who.user, "update", "hr_person_field", key, out["label"], diff)
        return out

    @app.delete(A + "/fields/{key}")
    def admin_field_delete(key: str, request: Request) -> dict[str, Any]:
        engine, tenant, who, rg = admin(request, PT.F_FIELDS, what="Alan silme")
        n = call(PT.delete_field, engine, tenant, rg, key)
        hr.audit(engine, who.user, "delete", "hr_person_field", key, "Personel alanı silindi", {"kayit": n})
        return {"ok": True, "cleared": n}

    @app.put(A + "/settings")
    def admin_settings(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who, _ = admin(request, PT.F_FIELDS, PT.F_PORTAL, what="İK portal listeleri")
        out, changed = call(PT.save_settings, engine, tenant, who.user, body)
        if changed:
            hr.audit(engine, who.user, "update", "hr_portal_settings", None, "İK portal listeleri", {"alanlar": changed})
        return out

    # ------------------------------------------------------------------ İK yönetimi: portal içeriği

    @app.get(A + "/posts")
    def admin_posts(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = admin(request, PT.F_PORTAL, what="Duyuru yönetimi")
        return {"items": PT.list_posts(engine, tenant, all_=True)}

    @app.post(A + "/posts", status_code=201)
    def admin_post_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who, _ = admin(request, PT.F_PORTAL, what="Duyuru yayımlama")
        out = call(PT.save_post, engine, tenant, who.user, body)
        hr.audit(engine, who.user, "create", "hr_post", out["id"], out["title"])
        return out

    @app.patch(A + "/posts/{post_id}")
    def admin_post_update(post_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who, _ = admin(request, PT.F_PORTAL, what="Duyuru düzenleme")
        out = call(PT.save_post, engine, tenant, who.user, body, post_id)
        hr.audit(engine, who.user, "update", "hr_post", post_id, out["title"], {"alanlar": sorted(body)})
        return out

    @app.delete(A + "/posts/{post_id}")
    def admin_post_delete(post_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, who, _ = admin(request, PT.F_PORTAL, what="Duyuru silme")
        title = call(PT.delete_post, engine, tenant, post_id)
        hr.audit(engine, who.user, "delete", "hr_post", post_id, title)
        return {"ok": True}

    @app.post(A + "/posts/{post_id}/image")
    async def admin_post_image(post_id: str, request: Request, filename: str = "") -> dict[str, Any]:
        engine, tenant, who, _ = await run_in_threadpool(admin, request, PT.F_PORTAL, what="Duyuru görseli")
        data = await body_bytes(request)
        out = await run_in_threadpool(call, PT.set_post_image, engine, tenant, who.user, post_id, filename, data, max_mb())
        hr.audit(engine, who.user, "upload", "hr_post", post_id, "Duyuru görseli")
        return out

    @app.delete(A + "/posts/{post_id}/image")
    def admin_post_image_delete(post_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, who, _ = admin(request, PT.F_PORTAL, what="Duyuru görseli")
        out = call(PT.set_post_image, engine, tenant, who.user, post_id, "", None, max_mb())
        hr.audit(engine, who.user, "delete", "hr_post", post_id, "Duyuru görseli kaldırıldı")
        return out

    @app.post(A + "/docs", status_code=201)
    async def admin_doc_add(request: Request, filename: str = "", title: str = "", category: str = "", code: str = "") -> dict[str, Any]:
        engine, tenant, who, _ = await run_in_threadpool(admin, request, PT.F_PORTAL, what="Evrak deposuna ekleme")
        data = await body_bytes(request)
        out = await run_in_threadpool(call, PT.add_doc, engine, tenant, who.user,
                                      {"title": title, "category": category, "code": code}, filename, data, max_mb())
        hr.audit(engine, who.user, "upload", "hr_doc", out["id"], out["title"], {"kategori": out["category"]})
        return out

    @app.delete(A + "/docs/{did}")
    def admin_doc_delete(did: str, request: Request) -> dict[str, Any]:
        engine, tenant, who, _ = admin(request, PT.F_PORTAL, what="Evrak silme")
        title = call(PT.delete_doc, engine, tenant, did)
        hr.audit(engine, who.user, "delete", "hr_doc", did, title)
        return {"ok": True}

    @app.get(A + "/requests")
    def admin_requests(request: Request, status: str = "acik") -> dict[str, Any]:
        engine, tenant, _, _ = admin(request, PT.F_PORTAL, what="Evrak talepleri")
        items = PT.list_requests(engine, tenant, status="" if status == "hepsi" else status)
        return {"items": items, "total": len(items)}

    @app.patch(A + "/requests/{rid}")
    def admin_request_handle(rid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who, _ = admin(request, PT.F_PORTAL, what="Evrak talebini işleme")
        out = call(PT.handle_request, engine, tenant, who.user, rid, body)
        hr.audit(engine, who.user, "update", "hr_doc_request", rid, "Evrak talebi", {"durum": out["status"]})
        person = PT.person_of(engine, tenant, out["username"])
        to = out["mail"] or (person.mail_adresi if person else None)
        note = f"\nİK notu: {out['answer']}" if out.get("answer") else ""
        HM.enqueue(engine, tenant, mailcfg(), event="evrak_durum", to=to, username=out["username"],
                   subject=f"Evrak talebiniz: {out['statusLabel']}",
                   body=f"«{out['docType']}» talebinizin durumu: {out['statusLabel']}.{note}\n\nEvrak talebim: {{link}}/ik/evrak?sekme=talep",
                   ref_type="evrak_talebi", ref_id=rid)
        return out

    @app.post(A + "/requests/{rid}/files", status_code=201)
    async def admin_request_file_add(rid: str, request: Request, filename: str = "") -> dict[str, Any]:
        engine, tenant, who, _ = await run_in_threadpool(admin, request, PT.F_PORTAL, what="Hazır evrak ekleme")
        data = await body_bytes(request)
        out = await run_in_threadpool(call, PT.add_request_file, engine, tenant, who.user, rid, filename, data, max_mb())
        hr.audit(engine, who.user, "upload", "hr_doc_request", rid, "Hazır evrak eklendi", {"boyut": out["size"]})
        return out

    @app.get(A + "/requests/{rid}/files/{fid}")
    def admin_request_file(rid: str, fid: str, request: Request) -> Response:
        engine, tenant, _, _ = admin(request, PT.F_PORTAL, what="Hazır evrak")
        data, name, mime = call(PT.request_file, engine, tenant, rid, fid)
        return _download(data, name, mime)

    @app.delete(A + "/requests/{rid}/files/{fid}")
    def admin_request_file_delete(rid: str, fid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who, _ = admin(request, PT.F_PORTAL, what="Hazır evrak silme")
        call(PT.delete_request_file, engine, tenant, rid, fid)
        hr.audit(engine, who.user, "delete", "hr_doc_request", rid, "Hazır evrak silindi")
        return {"ok": True}

    # ------------------------------------------------------------------ e-posta kuyruğu

    @app.get(A + "/mail")
    def admin_mail(request: Request, before: int = 0) -> dict[str, Any]:
        from semantic_bridge import hr_leave as LV

        engine, tenant, _, _ = admin(request, PT.F_PORTAL, LV.F_LEAVE, LV.F_LEAVE_SET, what="E-posta kuyruğu")
        return {**HM.list_outbox(engine, tenant, before=before), "settings": {k: v for k, v in mailcfg().items()}, "modes": HM.MODES,
                "states": HM.STATE}

    @app.post("/api/v1/hr/mail/run-due")
    def hr_mail_run_due(request: Request) -> dict[str, Any]:
        """Zamanlayıcı (5 dk): kuyruktaki bekleyen e-postaları gönderir (`HR_MAIL_MODE=gonder` iken satır oluşur)."""
        from semantic_bridge.budget_api import _send_mail

        hr.require_caller(request)
        engine, tenant = hr.system()
        return {"mode": mailcfg()["mode"], **HM.run_outbox(engine, tenant, _send_mail)}

    @app.put(A + "/menu")
    def admin_menu(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who, _ = admin(request, PT.F_PORTAL, what="Yemek listesi")
        n = call(PT.save_menu, engine, tenant, who.user, body)
        hr.audit(engine, who.user, "update", "hr_menu", None, "Yemek listesi", {"gun": n})
        return {"ok": True, "days": n}

    @app.post(A + "/faq", status_code=201)
    def admin_faq_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who, _ = admin(request, PT.F_PORTAL, what="Sık sorulan soru ekleme")
        out = call(PT.save_faq, engine, tenant, who.user, body)
        hr.audit(engine, who.user, "create", "hr_faq", out["id"], out["question"])
        return out

    @app.patch(A + "/faq/{fid}")
    def admin_faq_update(fid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who, _ = admin(request, PT.F_PORTAL, what="Sık sorulan soru düzenleme")
        out = call(PT.save_faq, engine, tenant, who.user, body, fid)
        hr.audit(engine, who.user, "update", "hr_faq", fid, out["question"])
        return out

    @app.delete(A + "/faq/{fid}")
    def admin_faq_delete(fid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who, _ = admin(request, PT.F_PORTAL, what="Sık sorulan soru silme")
        q = call(PT.delete_faq, engine, tenant, fid)
        hr.audit(engine, who.user, "delete", "hr_faq", fid, q)
        return {"ok": True}
