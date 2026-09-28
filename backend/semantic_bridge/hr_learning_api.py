"""M57 Eğitim ve gelişim uçları: /api/v1/hr/learning/* ve /api/v1/hr/visit.

Sayfa kapısı `access.RULES`:
- `/api/v1/hr/learning/me` ve altı: oturum yeter (Eğitimlerim, ekibim, anket, rehber okuma). Her uç yalnız isteği
  yapanın kendi kaydını ya da (yönetici, `ik.egitim-onay`) kendi ekibini döner.
- `/api/v1/hr/visit`: oturum yeter; yalnız isteği yapanın hesabına yazar.
- `/api/v1/hr/learning/reminders/run-due`: yalnız zamanlayıcı.
- Geri kalanı `sayfa:ik-egitim` (açıkça verilir). Kişi listeleri `ik.egitim-yonet` (duyarlı: yönetici ancak rolüyle),
  kullanım haritası `ik.kullanim-haritasi`, rehber yazımı `ik.rehber-yaz`, bütçe `ik.egitim-butce`, dışa aktarma
  `ik.disa-aktar` ister; ucun içinde `HrContext.need` ile denetlenir.

Model çağrıları `HrContext.llm` (LLM kapısı, sıra kaydına yalnız etiket). Modele kişi adı, hesap adı gitmez. Ekranda
model adı yazmaz. Hiçbir uç çalışana ya da dışarıya e-posta göndermez; zamanlayıcının özeti yalnız İK alıcılarına gider
ve kişi adı içermez.

Zamanlayıcı: `timas-hr-learning.timer` her gün 07:30 → `POST /api/v1/hr/learning/reminders/run-due`.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import timedelta
from typing import Any, Optional

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import hr_core as H
from semantic_bridge import hr_kaynak as HK
from semantic_bridge import hr_learning as L
from semantic_bridge import hr_learning_sources as S
from semantic_bridge.hr_api import HrContext

log = logging.getLogger("semantic_bridge.hr.learning.api")
P = "/api/v1/hr/learning"


# Sorgu bilgisi formülleri (hr_kaynak): kural metni; kişi adı ya da sayı içermez.
F_AYAR = ("Ayar değerleri (uyarı günü, dosya boyu sınırı, anket soruları) İK ayarı ve eğitim modülünün tanımıdır; bir "
          "okumadan hesaplanmaz. Sorgu listesi bu ekranın okumalarıdır.")
F_BENIM = ("Eğitimlerim: zorunlu eğitim durumu = eğitimin geçerlilik süresi ile son tamamlanan katılım (ya da doğrulanmış "
           "sertifika) tarihinden hesaplanır (geçerli / dolacak: uyarı günü içinde / dolmuş / hiç almamış); geçmiş = "
           "tamamlanan katılımlar; bekleyen anket = yanıtlanmamış eğitim anketi daveti.")
F_KULLANIM_BEN = ("Kullanımım: menü öğesi başına ziyaret günü (gün × ekran sayacı, yalnız sizin hesabınız) ve Zeki AI'a "
                  "sorduğunuz soru sayısı (soru kaydı), seçili gün penceresinde.")
F_EKIP = "Ekibim: ekip üyesi başına zorunlu eğitim durumu (yukarıdaki kural) ve onay bekleyen katılım talebi sayısı."
F_PANO = ("Eğitim panosu: süresi dolmuş = geçerliliği geçmiş + zorunlu olup hiç almamış; dolacak = uyarı günü içinde "
          "dolacak; bu ay oturum = bu ay başlayan oturum (yoklaması kapatılmamış ayrıca); tamamlanma = tamamlanan ÷ katılım. "
          "Birim × eğitim tablosu aynı kuralla birim bazında.")
F_DOLACAK = "Süresi dolanlar: zorunlu eğitimlerde durumu geçerli olmayan kişi × eğitim satırları; toplam = satır sayısı."
F_KATALOG = "Eğitim kataloğu = portal kaydı; kişi başı maliyet ve geçerlilik günü İK'nın girdiği değerdir; sayılar kayıttan."
F_OTURUM = ("Oturum: katılımcı = onaylı katılım (kontenjan oturum kaydından); yoklama = katıldı / gelmedi işaretli; anket = "
            "yanıtlanan ÷ gönderilen davet; reddedilen talep = reddedilen katılım.")
F_ANKET_OZET = ("Eğitim anketi özeti: soru başına ortalama = 1–5 yanıtların ortalaması, n = yanıt; yorumlar kural maskesiyle; "
                "temaları Zeki AI özetler. Yanıt gizlilik eşiğinin altındaysa ortalama ve tema gösterilmez.")
F_SERTIFIKA = "Sertifikalar = portal kaydı (dosya ve doğrulama durumu); toplam = satır sayısı."
F_IHTIYAC = "Eğitim ihtiyaçları: eğitim başına ihtiyaç kaydı sayısı, önceliğe göre (yüksek / orta / düşük) ve toplam."
F_HARITA = ("Kullanım haritası: birim × ekran = pencerede o ekranı en az bir gün açan farklı kişi sayısı (çalışan kaydındaki "
            "birimiyle); gizlilik eşiğinden küçük birimler ve kayıtsız hesaplar tek satırda birleştirilir, hesap adı yoktur. "
            "Toplam = ekranı açan farklı kişi.")
F_REHBER = "Ekran rehberleri: ekran başına yayındaki rehber sayısı ve oy sayıları (portal kaydı)."
F_GIDER = ("Eğitim gideri: Logo muhasebe fiş satırlarında ayardaki eğitim gider hesapları (ve alt hesapları) için borç − "
           "alacak, iptal ve dönem sonu kapanış fişleri hariç; ay ve hesap kırılımı; toplam = Σ. Bütçe = İK'nın girdiği yıllık "
           "tutar; kullanım = gerçekleşen ÷ bütçe.")


def register(app, hr: HrContext) -> None:
    ctx, need, call = hr.ctx, hr.need, hr.call
    L.register_hooks()

    def ready(request: Request) -> tuple[Any, str, H.Who]:
        engine, tenant, who = ctx(request)
        L.ensure(engine)
        return engine, tenant, who

    def st() -> dict[str, Any]:
        try:
            return L.settings(hr.conf)
        except H.HrError:
            # Hesap ayarı bozuksa yalnız gider ekranı hata verir; diğer ekranlar çalışır.
            out = L.settings(lambda k: "" if k == "HR_TRAINING_ACCOUNTS" else hr.conf(k))
            out["accountsError"] = True
            return out

    def model(label: str) -> Any:
        m = hr.llm(label)
        if m is None:
            raise HTTPException(503, detail={"code": "HR_MODEL", "message": "Zeki AI bu kurulumda tanımlı değil."})
        return m

    def chatter(m: Any, max_tokens: int):
        return lambda messages: m.chat(messages, max_tokens=max_tokens, temperature=0.0)

    def my_employee(engine: Any, tenant: str, who: H.Who) -> dict[str, Any]:
        emp = H.employee_by_username(engine, tenant, who.user)
        if emp is None:
            raise HTTPException(404, detail={"code": "HR", "message": "Çalışan kaydınız yok; İnsan Kaynakları'na başvurun."})
        return emp

    def can_flags(who: H.Who) -> dict[str, bool]:
        return {"manage": who.can(L.F_MANAGE), "approve": who.can(L.F_APPROVE), "budget": who.can(L.F_BUDGET),
                "usage": who.can(L.F_USAGE), "guides": who.can(L.F_GUIDES), "export": who.can(L.F_EXPORT),
                "page": who.can("sayfa:ik-egitim")}

    # ------------------------------------------------------------------ ziyaret sayacı

    @app.post("/api/v1/hr/visit")
    def hr_visit(body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Menü öğesi değişince ön yüz çağırır: (gün, öğe, hesap) sayacı. Yalnız kendi hesabına."""
        from semantic_bridge import board as board_mod

        hr.require_caller(request)
        try:
            user, _ = board_mod.session_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        engine, tenant = hr.system()
        call(L.record_visit, engine, tenant, user, str(body.get("route") or ""))
        return {"ok": True}

    # ------------------------------------------------------------------ Eğitimlerim (oturum yeter)

    @app.get(P + "/me")
    def learning_me(request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        s = st()
        with HK.capture(engine) as got:
            out = L.me(engine, tenant, who.user, s["alertDays"])
            out.update(can=can_flags(who), alertDays=s["alertDays"], questions=L.QUESTIONS,
                       catalog=[{"id": k["id"], "title": k["title"], "kind": k["kind"], "validityDays": k["validityDays"]}
                                for k in L.list_courses(engine, tenant, active_only=True)],
                       fileMaxMb=hr.settings()["fileMaxMb"])
        return hr.kaynak(out, got, "egitimim", {"catalog": ("katalog", F_KATALOG, ["semantic_hr_courses"]),
                                                 "alertDays": ("ayar", F_AYAR), "fileMaxMb": "hesap:ayar",
                                                 "questions": "hesap:ayar"},
                         rest=("egitimim", F_BENIM))

    @app.get(P + "/me/usage")
    def learning_my_usage(request: Request, days: int = 30, user: str = "") -> dict[str, Any]:
        """Kişi bazında portal kullanımı YALNIZ kişinin kendisine. Başkası sorulursa 403 (İK dahil)."""
        engine, tenant, who = ready(request)
        if user and user.strip().lower() != who.user.lower():
            raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Kişi bazında kullanım yalnız kişinin kendisine gösterilir."})
        if not 1 <= days <= 366:
            raise HTTPException(400, detail={"code": "HR", "message": "Gün 1–366 arasında olmalı."})
        with HK.capture(engine) as got:
            out = S.my_usage(engine, tenant, who.user, days)
        return hr.kaynak(out, got, "kullanimim", {}, rest=("kullanimim", F_KULLANIM_BEN))

    @app.post(P + "/me/certificates", status_code=201)
    async def learning_my_cert_upload(request: Request, filename: str = "", courseId: str = "", title: str = "",
                                      issuedOn: str = "", expiresOn: str = "") -> dict[str, Any]:
        engine, tenant, who = await run_in_threadpool(ready, request)
        emp = await run_in_threadpool(my_employee, engine, tenant, who)
        max_mb = hr.settings()["fileMaxMb"]
        if int(request.headers.get("content-length") or 0) > max_mb * 1024 * 1024:
            raise HTTPException(413, detail={"code": "HR", "message": f"Dosya {max_mb} MB sınırını aşıyor."})
        data = await request.body()
        out = await run_in_threadpool(call, L.upload_certificate, engine, tenant, who.user, emp["id"],
                                      {"courseId": courseId, "title": title, "issuedOn": issuedOn, "expiresOn": expiresOn},
                                      filename, data, max_mb)
        hr.audit(engine, who.user, "create", "hr_certificate", out["id"], "Sertifika yüklendi (doğrulama bekliyor)",
                 {"boyut": out["fileSize"], "egitim": out["courseId"]})
        return out

    @app.get(P + "/me/certificates/{cid}/file")
    def learning_my_cert_file(cid: str, request: Request) -> Response:
        engine, tenant, who = ready(request)
        emp = my_employee(engine, tenant, who)
        data, name, mime, _ = call(L.certificate_file, engine, tenant, cid, emp["id"])
        return _file(data, name, mime)

    @app.delete(P + "/me/certificates/{cid}")
    def learning_my_cert_delete(cid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        emp = my_employee(engine, tenant, who)
        call(L.delete_certificate, engine, tenant, cid, emp["id"])
        hr.audit(engine, who.user, "delete", "hr_certificate", cid, "Doğrulanmamış belge geri alındı")
        return {"ok": True}

    @app.post(P + "/me/enroll/{sid}", status_code=201)
    def learning_my_enroll(sid: str, request: Request) -> dict[str, Any]:
        """Çalışanın katılım talebi: yöneticisinin onayını bekler (dış eğitimde ardından İK)."""
        engine, tenant, who = ready(request)
        emp = my_employee(engine, tenant, who)
        out = call(L.enroll, engine, tenant, who.user, sid, [emp["id"]], "bekliyor")
        if not out["added"]:
            raise HTTPException(409, detail={"code": "HR", "message": "Bu oturumda kaydınız zaten var."})
        hr.audit(engine, who.user, "create", "hr_enrollment", sid, "Katılım talebi")
        return out

    @app.delete(P + "/me/enrollments/{eid}")
    def learning_my_enroll_withdraw(eid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        emp = my_employee(engine, tenant, who)
        mine = [e for e in L.me(engine, tenant, who.user, None)["enrollments"] if e["id"] == eid]
        if not mine or mine[0]["approval"] not in ("bekliyor", "yonetici_onayladi"):
            raise HTTPException(409, detail={"code": "HR", "message": "Yalnız onay bekleyen kendi talebinizi geri alabilirsiniz."})
        call(L.remove_enrollment, engine, tenant, eid)
        hr.audit(engine, who.user, "delete", "hr_enrollment", eid, "Katılım talebi geri alındı", {"calisan": emp["id"]})
        return {"ok": True}

    @app.post(P + "/me/needs", status_code=201)
    def learning_my_need(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        emp = my_employee(engine, tenant, who)
        out = call(L.add_need, engine, tenant, who.user, body, source="calisan", employee_id=emp["id"])
        hr.audit(engine, who.user, "create", "hr_need", out["id"], "Eğitim ihtiyacı (çalışan)")
        return out

    @app.get(P + "/me/feedback/{token}")
    def learning_feedback_form(token: str, request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        emp = my_employee(engine, tenant, who)
        return call(L.feedback_form, engine, tenant, token, emp["id"])

    @app.post(P + "/me/feedback/{token}")
    def learning_feedback_submit(token: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Anonim yanıt. Değişiklik kaydına kişi yazılmaz (yanıtı kişiye bağlamasın)."""
        engine, tenant, who = ready(request)
        emp = my_employee(engine, tenant, who)
        return call(L.submit_feedback, engine, tenant, token, emp["id"], body)

    # ------------------------------------------------------------------ yöneticinin ekibi

    @app.get(P + "/me/team")
    def learning_team(request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, L.F_APPROVE, what="Ekibin eğitim durumu")
        with HK.capture(engine) as got:
            out = L.team(engine, tenant, who.user, st()["alertDays"])
        return hr.kaynak(out, got, "ekip", {}, rest=("ekip", F_EKIP))

    @app.post(P + "/me/team/enrollments/{eid}/decide")
    def learning_team_decide(eid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, L.F_APPROVE, L.F_MANAGE, what="Katılım onayı")
        out = call(L.decide_enrollment, engine, tenant, who, eid, str(body.get("action") or ""), str(body.get("note") or ""))
        hr.audit(engine, who.user, "update", "hr_enrollment", eid, f"Katılım kararı: {out['approvalLabel']}",
                 {"oturum": out["sessionId"]})
        return out

    @app.post(P + "/me/team/needs", status_code=201)
    def learning_team_need(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, L.F_APPROVE, what="Ekip için eğitim ihtiyacı")
        _, team_ids = L.managed_employee_ids(engine, tenant, who.user)
        eid = str(body.get("employeeId") or "")
        if eid not in team_ids:
            raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Yalnız kendi ekibiniz için ihtiyaç bildirebilirsiniz."})
        out = call(L.add_need, engine, tenant, who.user, body, source="yonetici", employee_id=eid)
        hr.audit(engine, who.user, "create", "hr_need", out["id"], "Eğitim ihtiyacı (yönetici)")
        return out

    # ------------------------------------------------------------------ rehber okuma (oturum yeter)

    @app.get(P + "/me/guides")
    def learning_guide_index(request: Request) -> dict[str, Any]:
        engine, tenant, _ = ready(request)
        with HK.capture(engine) as got:
            out = {"items": L.published_index(engine, tenant)}
        return hr.kaynak(out, got, "rehberim", {"items[]": ("rehber", F_REHBER)})

    @app.get(P + "/me/guides/{gid}")
    def learning_guide_read(gid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        return call(L.read_guide, engine, tenant, gid, who.user)

    @app.post(P + "/me/guides/{gid}/vote")
    def learning_guide_vote(gid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        return call(L.vote_guide, engine, tenant, who.user, gid, bool(body.get("useful")))

    # ------------------------------------------------------------------ İK: genel

    @app.get(P + "/info")
    def learning_info(request: Request) -> dict[str, Any]:
        engine, _, who = ready(request)
        s = st()
        return {"kinds": L.KINDS, "delivery": L.DELIVERY, "sessionStates": L.SESSION_STATES, "approval": L.APPROVAL,
                "attendance": L.ATTENDANCE, "needSources": L.NEED_SOURCES, "needStates": L.NEED_STATES,
                "priorities": L.PRIORITIES, "guideStates": L.GUIDE_STATES, "status": L.STATUS, "questions": L.QUESTIONS,
                "themes": L.THEMES, "alertDays": s["alertDays"], "minGroup": s["minGroup"],
                "accountsConfigured": bool(s["accounts"]), "accountsError": bool(s.get("accountsError")),
                "modelVar": hr.llm("durum") is not None, "can": can_flags(who),
                "me": {"username": who.user, "display": who.display}}

    @app.get(P + "/dashboard")
    def learning_dashboard(request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        people = who.can(L.F_MANAGE)
        with HK.capture(engine) as got:
            out = L.dashboard(engine, tenant, alert_days=st()["alertDays"], people=people)
        if people:
            H.log_access(engine, tenant, who.user, "calisan", "egitim-pano", "goruntule", "zorunlu eğitim durumu")
        return hr.kaynak(out, got, "egitimPano", {}, rest=("pano", F_PANO))

    @app.get(P + "/expiring")
    def learning_expiring(request: Request, days: Optional[int] = None) -> dict[str, Any]:
        """Dolacak/dolmuş zorunlu eğitimler, kişi kişi. Gün verilmezse İK ayarı; o da yoksa yalnız dolmuş olanlar."""
        engine, tenant, who = ready(request)
        need(who, L.F_MANAGE, what="Kişi bazında eğitim durumu")
        d = st()["alertDays"] if days is None else days
        if d is not None and not 0 <= d <= 3650:
            raise HTTPException(400, detail={"code": "HR", "message": "Gün 0–3650 arasında olmalı."})
        with HK.capture(engine) as got:
            items = [x for x in L.mandatory_status(engine, tenant, days=d or 0) if x["status"] != "gecerli"]
        H.log_access(engine, tenant, who.user, "calisan", "egitim-dolacak", "goruntule", "zorunlu eğitim listesi")
        out = {"days": d, "items": items, "total": len(items)}
        return hr.kaynak(out, got, "dolacak", {"items[]": ("dolacak", F_DOLACAK), "total": "hesap:dolacak", "days": "hesap:dolacak"})

    @app.get(P + "/export/expiring.csv")
    def learning_expiring_csv(request: Request, days: Optional[int] = None) -> Response:
        engine, tenant, who = ready(request)
        need(who, L.F_MANAGE, what="Kişi bazında eğitim durumu")
        need(who, L.F_EXPORT, what="İK verisini dışa aktarma")
        d = st()["alertDays"] if days is None else days
        items = [x for x in L.mandatory_status(engine, tenant, days=d or 0) if x["status"] != "gecerli"]
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["Çalışan", "Birim", "Eğitim", "Durum", "Son geçerlilik", "Kalan gün", "Planlı oturum"])
        for x in items:
            w.writerow([x["displayName"], x["unitName"] or "", x["courseTitle"], x["statusLabel"], x["expiresOn"] or "",
                        "" if x["daysLeft"] is None else x["daysLeft"], (x["plannedAt"] or "")[:16]])
        H.log_access(engine, tenant, who.user, "calisan", "egitim-dolacak", "disa_aktar", f"{len(items)} satır")
        hr.audit(engine, who.user, "run", "hr_certificate", "dolacak", "Zorunlu eğitim listesi dışa aktarıldı", {"satir": len(items)})
        return Response(content=("﻿" + buf.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": "attachment; filename=zorunlu-egitim.csv", "Cache-Control": "private, no-store"})

    # ------------------------------------------------------------------ katalog

    @app.get(P + "/courses")
    def learning_courses(request: Request, active: bool = False) -> dict[str, Any]:
        engine, tenant, _ = ready(request)
        with HK.capture(engine) as got:
            out = {"items": L.list_courses(engine, tenant, active_only=active)}
        return hr.kaynak(out, got, "katalog", {"items[]": ("katalog", F_KATALOG)})

    @app.post(P + "/courses", status_code=201)
    def learning_course_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, L.F_MANAGE, what="Eğitim kataloğunu düzenleme")
        out, _ = call(L.save_course, engine, tenant, who.user, body)
        hr.audit(engine, who.user, "create", "hr_course", out["id"], out["title"])
        return out

    @app.patch(P + "/courses/{cid}")
    def learning_course_update(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, L.F_MANAGE, what="Eğitim kataloğunu düzenleme")
        out, diff = call(L.save_course, engine, tenant, who.user, body, cid)
        if diff:
            hr.audit(engine, who.user, "update", "hr_course", cid, out["title"], diff)
        return out

    # ------------------------------------------------------------------ oturumlar

    @app.get(P + "/sessions")
    def learning_sessions(request: Request, state: str = "", course: str = "") -> dict[str, Any]:
        engine, tenant, _ = ready(request)
        with HK.capture(engine) as got:
            out = {"items": L.list_sessions(engine, tenant, state=state, course_id=course)}
        return hr.kaynak(out, got, "oturumlar", {"items[]": ("oturum", F_OTURUM)})

    @app.post(P + "/sessions", status_code=201)
    def learning_session_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, L.F_MANAGE, what="Oturum açma")
        out = call(L.create_session, engine, tenant, who.user, body)
        hr.audit(engine, who.user, "create", "hr_session", out["id"], out["courseTitle"],
                 {"baslangic": out["startsAt"], "katilimci": out["counts"].get("approved", 0)})
        return out

    @app.get(P + "/sessions/{sid}")
    def learning_session(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        people = who.can(L.F_MANAGE)
        with HK.capture(engine) as got:
            out = call(L.get_session, engine, tenant, sid, people=people)
        if people:
            H.log_access(engine, tenant, who.user, "calisan", f"oturum:{sid}"[:40], "goruntule", "katılımcı listesi")
        return hr.kaynak(out, got, "oturum", {}, rest=("oturum", F_OTURUM))

    @app.patch(P + "/sessions/{sid}")
    def learning_session_update(sid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, L.F_MANAGE, what="Oturumu düzenleme")
        out, diff = call(L.update_session, engine, tenant, who.user, sid, body)
        if diff:
            hr.audit(engine, who.user, "update", "hr_session", sid, out["courseTitle"], diff)
        return out

    @app.post(P + "/sessions/{sid}/enroll")
    def learning_session_enroll(sid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, L.F_MANAGE, what="Katılımcı ekleme")
        ids = [str(x) for x in (body.get("employeeIds") or []) if str(x).strip()]
        if not ids:
            raise HTTPException(400, detail={"code": "HR", "message": "Eklenecek çalışanı seçin."})
        out = call(L.enroll, engine, tenant, who.user, sid, ids, "onaylandi")
        hr.audit(engine, who.user, "update", "hr_session", sid, "Katılımcı eklendi", out)
        return out

    @app.delete(P + "/enrollments/{eid}")
    def learning_enrollment_delete(eid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, L.F_MANAGE, what="Katılımcı çıkarma")
        call(L.remove_enrollment, engine, tenant, eid)
        hr.audit(engine, who.user, "delete", "hr_enrollment", eid, "Katılımcı çıkarıldı")
        return {"ok": True}

    @app.post(P + "/enrollments/{eid}/decide")
    def learning_enrollment_decide(eid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, L.F_MANAGE, L.F_APPROVE, what="Katılım onayı")
        out = call(L.decide_enrollment, engine, tenant, who, eid, str(body.get("action") or ""), str(body.get("note") or ""))
        hr.audit(engine, who.user, "update", "hr_enrollment", eid, f"Katılım kararı: {out['approvalLabel']}", {"oturum": out["sessionId"]})
        return out

    @app.post(P + "/sessions/{sid}/attendance")
    def learning_attendance(sid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, L.F_MANAGE, what="Yoklama")
        out = call(L.set_attendance, engine, tenant, who.user, sid, list(body.get("items") or []))
        return out

    @app.post(P + "/sessions/{sid}/close")
    def learning_session_close(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, L.F_MANAGE, what="Oturumu kapatma")
        out = call(L.close_session, engine, tenant, who.user, sid)
        hr.audit(engine, who.user, "run", "hr_session", sid, "Oturum kapatıldı", out)
        return out

    @app.get(P + "/sessions/{sid}/feedback-summary")
    def learning_feedback_summary(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, L.F_MANAGE, what="Geri bildirim sonuçları")
        with HK.capture(engine) as got:
            out = call(L.feedback_summary, engine, tenant, sid, st()["minGroup"])
        hidden = ["averages", "themes"] if out.get("hidden") else []
        return hr.kaynak(out, got, "egitimAnket", {"responses": ("anketSay", F_ANKET_OZET), "invited": "hesap:anketSay",
                                                   "minGroup": "hesap:anketSay"},
                         rest=("anketOzet", F_ANKET_OZET), hidden=hidden)

    @app.post(P + "/sessions/{sid}/feedback-themes", status_code=202)
    def learning_feedback_themes(sid: str, request: Request) -> dict[str, Any]:
        """Yorumların Zeki AI tema özeti (arka planda). Eşiğin altındaki oturumda çalışmaz."""
        engine, tenant, who = ready(request)
        need(who, L.F_MANAGE, what="Geri bildirim özeti")
        summary = call(L.feedback_summary, engine, tenant, sid, st()["minGroup"])
        if summary["hidden"]:
            raise HTTPException(409, detail={"code": "HR", "message": "Yanıt sayısı gizlilik eşiğinin altında; özet çıkarılmaz."})
        if not summary["comments"]:
            raise HTTPException(409, detail={"code": "HR", "message": "Bu oturumda yazılı yorum yok."})
        m = model("egitim geri bildirim")

        def work(progress):
            progress(0, len(summary["comments"]))
            data = L.feedback_themes(summary["comments"], m.choose, chatter(m, 200))
            L.store_themes(engine, tenant, sid, data)
            progress(len(summary["comments"]), len(summary["comments"]))
            return {"themes": len(data["themes"])}

        return call(H.start_job, engine, tenant, who.user, "egitim-tema", sid, work)

    # ------------------------------------------------------------------ sertifikalar

    @app.get(P + "/certificates")
    def learning_certificates(request: Request, employeeId: str = "", unverified: bool = False) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, L.F_MANAGE, what="Sertifika kayıtları")
        with HK.capture(engine) as got:
            items = L.list_certificates(engine, tenant, employee_id=employeeId, unverified=unverified)
        H.log_access(engine, tenant, who.user, "calisan", employeeId or "egitim-sertifika", "goruntule", "sertifika kayıtları")
        out = {"items": items, "total": len(items)}
        return hr.kaynak(out, got, "sertifika", {"items[]": ("sertifika", F_SERTIFIKA), "total": "hesap:sertifika"})

    @app.post(P + "/certificates", status_code=201)
    def learning_certificate_record(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, L.F_MANAGE, what="Sertifika kaydı")
        out = call(L.record_certificate, engine, tenant, who.user, body)
        hr.audit(engine, who.user, "create", "hr_certificate", out["id"], "Sertifika kaydı (İK)",
                 {"calisan": out["employeeId"], "egitim": out["courseId"]})
        return out

    @app.post(P + "/certificates/{cid}/verify")
    def learning_certificate_verify(cid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, L.F_MANAGE, what="Sertifika doğrulama")
        out = call(L.verify_certificate, engine, tenant, who.user, cid)
        hr.audit(engine, who.user, "update", "hr_certificate", cid, "Sertifika doğrulandı")
        return out

    @app.post(P + "/certificates/{cid}/check")
    def learning_certificate_check(cid: str, request: Request) -> dict[str, Any]:
        """Doğrulamaya yardım: belge okunur (taranmışsa OCR), kayıttaki tarih ve ad belgede birebir aranır."""
        engine, tenant, who = ready(request)
        need(who, L.F_MANAGE, what="Sertifika belgesi")
        out = call(L.certificate_check, engine, tenant, cid)
        H.log_access(engine, tenant, who.user, "calisan", out["employeeId"], "goruntule", "sertifika belgesi okuma")
        return out

    @app.delete(P + "/certificates/{cid}")
    def learning_certificate_delete(cid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, L.F_MANAGE, what="Sertifika silme")
        out = call(L.delete_certificate, engine, tenant, cid)
        hr.audit(engine, who.user, "delete", "hr_certificate", cid, "Sertifika kaydı silindi", {"calisan": out["employeeId"]})
        return {"ok": True}

    @app.get(P + "/certificates/{cid}/file")
    def learning_certificate_file(cid: str, request: Request) -> Response:
        engine, tenant, who = ready(request)
        need(who, L.F_MANAGE, what="Sertifika belgesi")
        data, name, mime, eid = call(L.certificate_file, engine, tenant, cid)
        H.log_access(engine, tenant, who.user, "calisan", eid, "indir", "sertifika belgesi")
        return _file(data, name, mime)

    # ------------------------------------------------------------------ ihtiyaçlar

    @app.get(P + "/needs")
    def learning_needs(request: Request, state: str = "") -> dict[str, Any]:
        engine, tenant, who = ready(request)
        people = who.can(L.F_MANAGE)
        with HK.capture(engine) as got:
            out = L.list_needs(engine, tenant, state=state, people=people)
        return hr.kaynak(out, got, "ihtiyac", {}, rest=("ihtiyac", F_IHTIYAC))

    @app.post(P + "/needs", status_code=201)
    def learning_need_add(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, L.F_MANAGE, what="Eğitim ihtiyacı kaydı")
        source = str(body.get("source") or "ik")
        if source == "calisan":
            raise HTTPException(400, detail={"code": "HR", "message": "Çalışan talebi Eğitimlerim ekranından girilir."})
        out = call(L.add_need, engine, tenant, who.user, body, source=source, employee_id=str(body.get("employeeId") or "") or None)
        hr.audit(engine, who.user, "create", "hr_need", out["id"], f"Eğitim ihtiyacı ({out['sourceLabel']})")
        return out

    @app.post(P + "/needs/{nid}/decide")
    def learning_need_decide(nid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, L.F_MANAGE, what="Eğitim ihtiyacı kararı")
        out, diff = call(L.decide_need, engine, tenant, who.user, nid, body)
        hr.audit(engine, who.user, "update", "hr_need", nid, f"İhtiyaç: {out['stateLabel']}", diff)
        return out

    @app.post(P + "/needs/suggest", status_code=202)
    def learning_need_suggest(body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Açık ihtiyaçlar için Zeki AI önerisi (arka planda). `ids` verilmezse önerisi olmayan bütün açık ihtiyaçlar."""
        engine, tenant, who = ready(request)
        need(who, L.F_MANAGE, what="Zeki AI önerisi")
        courses = L.list_courses(engine, tenant, active_only=True)
        if not courses:
            raise HTTPException(409, detail={"code": "HR", "message": "Katalogda etkin eğitim yok; önce kataloğu doldurun."})
        want = {str(x) for x in (body.get("ids") or [])}
        open_items = L.list_needs(engine, tenant, state="acik")["items"]
        items = [n for n in open_items if n["id"] in want] if want else [n for n in open_items if n["suggestion"] is None]
        if not items:
            raise HTTPException(409, detail={"code": "HR", "message": "Önerilecek açık ihtiyaç yok."})
        m = model("egitim ihtiyaci")

        def work(progress):
            for i, n in enumerate(items):
                s = L.suggest_need(n, courses, m.choose, chatter(m, 120))
                L.apply_suggestion(engine, tenant, n["id"], s)
                progress(i + 1, len(items))
            return {"suggested": len(items)}

        hr.audit(engine, who.user, "run", "hr_need", "suggest", "Zeki AI ihtiyaç önerisi", {"ihtiyac": len(items)})
        return call(H.start_job, engine, tenant, who.user, "egitim-ihtiyac", "needs", work)

    # ------------------------------------------------------------------ kullanım haritası

    @app.get(P + "/usage-map")
    def learning_usage_map(request: Request, days: int = 30) -> dict[str, Any]:
        """Birim × modül: farklı kişi sayısı. Hesap adı yok; kişi bazında görünüm yalnız kişinin kendisinde (/me/usage)."""
        engine, tenant, who = ready(request)
        need(who, L.F_USAGE, what="Portal kullanım haritası")
        if not 1 <= days <= 366:
            raise HTTPException(400, detail={"code": "HR", "message": "Gün 1–366 arasında olmalı."})
        with HK.capture(engine) as got:
            out = S.usage_map(engine, tenant, days, st()["minGroup"])
        return hr.kaynak(out, got, "harita", {}, rest=("harita", F_HARITA))

    # ------------------------------------------------------------------ rehberler

    @app.get(P + "/guides")
    def learning_guides(request: Request) -> dict[str, Any]:
        engine, tenant, _ = ready(request)
        with HK.capture(engine) as got:
            out = {"items": L.list_guides(engine, tenant)}
        return hr.kaynak(out, got, "rehber", {"items[]": ("rehber", F_REHBER)})

    @app.post(P + "/guides", status_code=201)
    def learning_guide_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, L.F_GUIDES, what="Rehber yazma")
        out = call(L.save_guide, engine, tenant, who.user, body)
        hr.audit(engine, who.user, "create", "hr_guide", out["id"], out["title"], {"ekran": out["moduleRoute"]})
        return out

    @app.patch(P + "/guides/{gid}")
    def learning_guide_update(gid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, L.F_GUIDES, what="Rehber yazma")
        out = call(L.save_guide, engine, tenant, who.user, body, gid)
        hr.audit(engine, who.user, "update", "hr_guide", gid, out["title"])
        return out

    @app.post(P + "/guides/draft")
    async def learning_guide_draft(body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Zeki AI taslağı: ekranın menü tanımından (ad, kısa tanım, sözcükler) ve sorumlunun notlarından. Taslak kaydedilir,
        yayımlamayı insan yapar."""
        engine, tenant, who = await run_in_threadpool(ready, request)
        need(who, L.F_GUIDES, what="Rehber yazma")
        route = str(body.get("moduleRoute") or "").strip().lower()
        if not L._ROUTE.match(route):  # noqa: SLF001
            raise HTTPException(400, detail={"code": "HR", "message": "Rehberin ait olduğu ekranı seçin."})
        m = model("egitim rehber")
        text = (await run_in_threadpool(chatter(m, 900), L.guide_messages(body)) or "").strip()
        if not text:
            raise HTTPException(502, detail={"code": "HR_MODEL", "message": "Zeki AI taslak üretemedi; yeniden deneyin."})
        title = f"{str(body.get('label') or route).strip()[:150]} — nasıl kullanılır"
        gid = str(body.get("guideId") or "") or None
        if gid is None:
            existing = [g for g in L.list_guides(engine, tenant) if g["moduleRoute"] == route]
            gid = existing[0]["id"] if existing else None
        out = await run_in_threadpool(call, L.save_guide, engine, tenant, who.user,
                                      {"moduleRoute": route, "title": title, "body": text}, gid, model_drafted=True)
        hr.audit(engine, who.user, "create" if gid is None else "update", "hr_guide", out["id"], out["title"], {"zekiTaslak": True})
        return out

    @app.post(P + "/guides/{gid}/publish")
    def learning_guide_publish(gid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, L.F_GUIDES, what="Rehber yayımlama")
        out = call(L.publish_guide, engine, tenant, who.user, gid)
        hr.audit(engine, who.user, "publish", "hr_guide", gid, f"{out['title']} yayımlandı (sürüm {out['version']})")
        return out

    @app.post(P + "/guides/{gid}/unpublish")
    def learning_guide_unpublish(gid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, L.F_GUIDES, what="Rehberi yayından kaldırma")
        call(L.unpublish_guide, engine, tenant, gid)
        hr.audit(engine, who.user, "unpublish", "hr_guide", gid, "Rehber yayından kaldırıldı")
        return {"ok": True}

    # ------------------------------------------------------------------ gider ve bütçe

    @app.get(P + "/spend")
    async def learning_spend(request: Request, year: int = 0) -> dict[str, Any]:
        engine, tenant, who = await run_in_threadpool(ready, request)
        need(who, L.F_BUDGET, what="Eğitim bütçesi ve gideri")
        y = year or L.today().year
        s = st()
        if s.get("accountsError"):
            raise HTTPException(422, detail={"code": "HR", "message": "Eğitim gider hesapları ayarı geçersiz (Portal ayarları → İnsan kaynakları)."})
        conn = hr.rt().settings.connection_file

        def work() -> tuple[dict[str, Any], Any, list]:
            with HK.capture(engine) as got:      # iş parçacığında: Logo metni + bütçe okuması yakalanır
                sp = call(S.read_spend, conn, y, s["accounts"])
                bb = L.budget(engine, tenant, y)
            return sp, bb, got

        spend, b, got = await run_in_threadpool(work)
        ratio = round(spend["total"] / b["amount"], 4) if spend.get("total") is not None and b and b["amount"] else None
        out = {**spend, "budget": b, "ratio": ratio, "accountCodes": s["accounts"]}
        return await run_in_threadpool(hr.kaynak, out, got, "gider", {}, ("gider", F_GIDER))

    @app.get(P + "/spend/accounts")
    async def learning_spend_accounts(request: Request, year: int = 0) -> dict[str, Any]:
        """Adında eğitim/seminer/kurs geçen gider hesapları (ölçüm; İK ve Mali İşler seçer)."""
        engine, tenant, who = await run_in_threadpool(ready, request)
        need(who, L.F_BUDGET, what="Eğitim bütçesi ve gideri")
        conn = hr.rt().settings.connection_file
        items = await run_in_threadpool(call, S.read_candidates, conn, year or L.today().year)
        return {"items": items, "selected": st()["accounts"]}

    @app.put(P + "/budget/{year}")
    def learning_budget_put(year: int, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, L.F_BUDGET, what="Eğitim bütçesi")
        out, diff = call(L.put_budget, engine, tenant, who.user, year, body)
        hr.audit(engine, who.user, "update", "hr_training_budget", str(year), f"{year} eğitim bütçesi", diff)
        return out

    # ------------------------------------------------------------------ zamanlayıcı

    @app.post(P + "/reminders/run-due")
    def learning_reminders(request: Request) -> dict[str, Any]:
        """Her sabah: İK alıcılarına kişi adı içermeyen tek özet (dolmuş/dolacak zorunlu eğitim birim başına, yarınki
        oturumlar, kapanmamış oturum, onay ve doğrulama bekleyenler). Alıcı yoksa hiçbir şey gönderilmez."""
        from semantic_bridge.budget_api import _send_mail

        hr.require_caller(request)
        engine, tenant = hr.system()
        L.ensure(engine)
        s = st()
        d = L.dashboard(engine, tenant, alert_days=s["alertDays"], people=False)
        c = d["counters"]
        tomorrow = L.today() + timedelta(days=1)
        soon = [x for x in L.list_sessions(engine, tenant, state="planli", since=L.today())
                if x["startsAt"] and H.aware(x["startsAt"]).astimezone(L.TZ).date() == tomorrow]
        lines = []
        if c["overdue"] or c["never"]:
            lines.append(f"Süresi dolmuş zorunlu eğitim: {c['overdue']} · hiç almamış: {c['never']}")
        if c["expiring"]:
            lines.append(f"{s['alertDays']} gün içinde dolacak zorunlu eğitim: {c['expiring']}")
        for u in d["attentionByUnit"]:
            lines.append(f"  - {u['unitName']}: dolmuş {u['doldu']}, hiç almamış {u['hic_yok']}, dolacak {u['dolacak']}")
        if soon:
            lines.append(f"Yarın {len(soon)} eğitim oturumu var: " + ", ".join(x["courseTitle"] for x in soon))
        if c["awaitingClose"]:
            lines.append(f"Tarihi geçmiş, yoklaması kapatılmamış oturum: {c['awaitingClose']}")
        if c["pendingApprovals"]:
            lines.append(f"Onay bekleyen katılım talebi: {c['pendingApprovals']}")
        if c["unverifiedCertificates"]:
            lines.append(f"Doğrulama bekleyen sertifika: {c['unverifiedCertificates']}")
        mail = "bos"
        recipients = hr.settings()["alertRecipients"]
        if lines:
            if recipients:
                link = (hr.conf("ALERT_LINK") or "").split("/uyarilar")[0]
                text = "Eğitim ve gelişim — günlük özet\n\n" + "\n".join(lines) + (f"\n\nAyrıntı: {link}/ik/egitim" if link else "")
                mail = _send_mail("Eğitim: günlük özet", text, recipients)
            else:
                mail = "alici_yok"
        return {"lines": len(lines), "mail": mail, "recipients": len(recipients), "alertDays": s["alertDays"],
                "counters": c}


def _file(data: bytes, name: str, mime: str) -> Response:
    from urllib.parse import quote

    return Response(content=data, media_type=mime, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name, safe='')}", "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store"})
