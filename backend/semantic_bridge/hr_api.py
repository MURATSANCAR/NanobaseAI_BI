"""İK-0 uçları: /api/v1/hr/* (çalışan, birim, aydınlatma, rıza, saklama, imha, erişim kaydı).

Sayfa kapısı `access.RULES`: `/api/v1/hr/` İK sayfalarından birini ister (hepsi `explicit`, Herkes rolüne girmez);
`/api/v1/hr/me` oturumla açık; `/api/v1/hr/purge/run-due` yalnız zamanlayıcı. İşlem ve kişisel veri anahtarları
(`ozellik:ik.*`, hepsi açıkça verilir) burada `Who.can` ile denetlenir; duyarlı anahtarlar yöneticiye ancak rolüyle
gelir (`hr_core.who_from`, `HR_ADMIN_SEES_PERSONAL`).

`register` bir `HrContext` döner (`app.state.hr`): M55 işe alım ve M56–M58 aynı kimlik, yetki, değişiklik kaydı ve
model sarmalayıcısını buradan kullanır.

Zamanlayıcı: `timas-hr-purge.timer` her gece 03:40 → `POST /api/v1/hr/purge/run-due` (sistem jetonuyla).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request

from semantic_bridge import hr_core as H
from semantic_bridge import hr_kaynak as HK
from semantic_bridge import hr_sources as S
from semantic_bridge import provenance as PV

log = logging.getLogger("semantic_bridge.hr.api")
P = "/api/v1/hr"

F_EMPLOYEES = "ozellik:ik.calisan-yonet"
F_KVKK = "ozellik:ik.kvkk-yonet"
F_ACCESS_LOG = "ozellik:ik.erisim-kaydi"
F_EXPORT = "ozellik:ik.disa-aktar"
PAGE_RECORDS = "sayfa:ik-kayitlar"

# Çalışan kaydının tamamını (giriş/çıkış tarihi, ayrılanlar, hesap ve kaynak kimlikleri) yalnız kayıtları yöneten
# İK görür. Başka İK sayfasıyla gelen (eğitim, işe alım, belgeler) yalnız kişi seçicinin rehber alanlarını alır.
DIRECTORY_FIELDS = ("id", "displayName", "unitId", "unitName", "title", "status", "statusLabel")


def sees_full_record(who: H.Who) -> bool:
    return who.can(F_EMPLOYEES, PAGE_RECORDS)


def directory_view(e: dict[str, Any]) -> dict[str, Any]:
    return {k: e.get(k) for k in DIRECTORY_FIELDS}

# Sorgu bilgisi formülleri (hr_kaynak): kural metni, kişi adı ya da sayı içermez.
F_CALISAN = ("Çalışan listesi = portal çalışan kaydı (CRM ∩ Active Directory eşitlemesiyle ya da İK'nın elle girdiği), "
             "seçili durum, birim ve arama süzgeciyle; sayı = listedeki kayıt.")
F_ESITLEME = ("Eşitleme önizlemesi: CRM'de devre dışı olmayan kullanıcılar (etkin), bunlardan erişim türü okuma-yazma ya da "
              "yönetici ve alan adı olanlar (etkileşimli); Active Directory eşitlemesinde etkin hesabı olanlar eşleşen. Yeni / "
              "değişen = portal çalışan kaydıyla karşılaştırma; ayrılan = kayıtta etkin ama eşleşmede olmayan. Hiçbir şey yazılmaz.")
F_ESITLEME_BIRIM = ("Birim satırı: CRM iş birimi; etkin kullanıcı = o birimde devre dışı olmayan CRM kullanıcısı, çalışan = "
                    "eşleşen (Active Directory'de etkin) kişi sayısı; yönetici kolonu ayardan.")
F_ESITLEME_EKIP = "Ekip üye sayısı = CRM ekip üyeliği, devre dışı olmayan kullanıcılar."
F_BIRIM = "Birimler = portal birim kaydı (CRM iş biriminden eşitlenen ya da elle); sayılar birimin kayıtlı çalışanlarıdır."
F_AYDINLATMA = "Aydınlatma metinleri = portal kaydı; sürüm numarası her yayında bir artar."
F_SAKLAMA = ("Saklama: veri sınıfı başına saklama süresi (gün, ayar kaydı) ve bu süreyi dolduran kayıt sayısı (kaydın "
             "tarihi + süre < bugün).")
F_IMHA = "İmha önizlemesi: saklama süresi dolan kayıtların veri sınıfı başına sayısı; hiçbir şey silinmez."
F_IMHA_KAYIT = "İmha tutanakları = gece imha işinin veri sınıfı başına yazdığı silinen kayıt sayısı (portal kaydı)."
F_ERISIM = "Erişim kaydı = kişisel kayıt görüntüleme ve değişiklik satırları (portal kaydı)."


class HrContext:
    """İK uçlarının ortak kimlik/yetki/kayıt yardımcıları. M55–M58 aynı nesneyi kullanır."""

    def __init__(self, rt: Callable[[], Any], require_caller: Callable[[Request], None], conf: Callable[[str], str],
                 audit: Callable[..., None], is_admin: Callable[[str], bool]):
        self.rt = rt
        self.require_caller = require_caller
        self.conf = conf
        self._audit = audit
        self.is_admin = is_admin

    # -- kimlik ve yetki
    def system(self) -> tuple[Any, str]:
        r = self.rt()
        H.ensure(r.store.engine)
        return r.store.engine, r.settings.tenant_id

    def ctx(self, request: Request) -> tuple[Any, str, H.Who]:
        from semantic_bridge import access as access_mod
        from semantic_bridge import board as board_mod

        self.require_caller(request)
        try:
            user, display = board_mod.session_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        engine, tenant = self.system()
        acc = access_mod.effective(engine, tenant, user, self.is_admin)
        who = H.who_from(acc, display, access_mod.sensitive_keys(), self.settings()["adminSeesPersonal"])
        return engine, tenant, who

    def settings(self) -> dict[str, Any]:
        return H.settings(self.conf)

    @staticmethod
    def need(who: H.Who, *keys: str, what: str = "Bu işlem") -> None:
        if not who.can(*keys):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    @staticmethod
    def call(fn: Callable[..., Any], *a: Any, **kw: Any) -> Any:
        try:
            return fn(*a, **kw)
        except H.HrError as e:
            raise HTTPException(status_code=e.status, detail={"code": "HR", "message": str(e)}) from e
        except S.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "HR_SOURCE", "message": str(e)}) from e

    def audit(self, engine: Any, user: str, action: str, kind: str, oid: Optional[str], title: Optional[str],
              detail: Any = None) -> None:
        """Değişiklik kaydı. Başlık ve ayrıntıya aday adı/e-posta yazılmaz; kayıt kimliği yeter."""
        self._audit(engine, user, action, kind, oid, title, detail)

    def llm(self, label: str, priority: Optional[int] = None) -> Any:
        return H.hr_llm(self.rt(), label, priority)

    def kaynak(self, out: Any, got: list, prefix: str, mapping: dict[str, Any], rest: Optional[tuple[str, str]] = None,
               hidden: Any = (), ignore: Any = ()) -> Any:
        """Sorgu bilgisi (hr_kaynak): isteğin çalıştırdığı sorgular + alan → formül. Kurulamazsa rakam yine döner."""
        if not isinstance(out, dict):
            return out
        return PV.bagla(out, lambda: HK.build(got, prefix, mapping, out=out, rest=rest, hidden=hidden, ignore=ignore,
                                              **HK.db_names(self.rt)))


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None]) -> HrContext:
    from semantic_bridge import admin as admin_mod

    hr = HrContext(rt, require_caller, admin_mod.conf, admin_mod.audit, admin_mod.is_admin)
    ctx, need, call = hr.ctx, hr.need, hr.call

    def crm_file() -> str:
        return os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")

    def preview(engine: Any, tenant: str) -> dict[str, Any]:
        return S.read_preview(crm_file(), admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo",
                              (admin_mod.conf("HR_CRM_UNIT_MANAGER_COLUMN") or "new_departmanyoneticisiid").strip(),
                              {k: admin_mod.conf(k) for k in admin_mod.store_keys("ad")},
                              H.list_employees(engine, tenant, status=""), H.list_units(engine, tenant))

    # ------------------------------------------------------------------ genel

    @app.get(P + "/me")
    def hr_me(request: Request) -> dict[str, Any]:
        """Kendi çalışan kaydım, rızalarım ve haklarım (oturum yeter)."""
        engine, tenant, who = ctx(request)
        return H.me(engine, tenant, who.user)

    @app.get(P + "/meta")
    def hr_meta(request: Request) -> dict[str, Any]:
        _, _, who = ctx(request)
        st = hr.settings()
        return {
            "me": {"username": who.user, "display": who.display, "isAdmin": who.admin,
                   "keys": sorted(k for k in who.keys if k.startswith(("ozellik:ik.", "sayfa:ik-")))},
            "settings": {"slaDays": st["slaDays"], "fileMaxMb": st["fileMaxMb"], "adminSeesPersonal": st["adminSeesPersonal"],
                         "alertRecipients": len(st["alertRecipients"])},
            "purposes": H.PURPOSES, "dataClasses": H.DATA_CLASSES, "channels": H.CHANNELS, "audiences": H.AUDIENCES,
            "employeeStatus": H.EMPLOYEE_STATUS,
            "modelVar": hr.llm("durum") is not None,
        }

    @app.get(P + "/jobs/{jid}")
    def hr_job(jid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who = ctx(request)
        return call(H.job, engine, tenant, jid, who.user)

    # ------------------------------------------------------------------ çalışanlar ve birimler

    @app.get(P + "/employees")
    def hr_employees(request: Request, status: str = "aktif", q: str = "", unit: str = "") -> dict[str, Any]:
        engine, tenant, who = ctx(request)
        full = sees_full_record(who)
        with HK.capture(engine) as got:
            # Kayıt yetkisi olmayan yalnız etkin çalışanların rehber alanlarını alır; arama da yalnız o alanlarda.
            items = H.list_employees(engine, tenant, status=status if full else "aktif", q=q if full else "", unit_id=unit)
        if not full:
            needle = (q or "").strip().casefold()
            items = [directory_view(e) for e in items
                     if not needle or needle in f"{e['displayName']} {e['title']} {e['unitName'] or ''}".casefold()]
        out = {"items": items, "total": len(items)}
        return hr.kaynak(out, got, "calisan", {"total": ("calisanSay", F_CALISAN), "items[]": ("calisan", F_CALISAN)})

    @app.post(P + "/employees", status_code=201)
    def hr_employee_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ctx(request)
        need(who, F_EMPLOYEES, what="Çalışan kaydını düzenleme")
        out, _ = call(H.save_employee, engine, tenant, who.user, body)
        hr.audit(engine, who.user, "create", "hr_employee", out["id"], out["displayName"])
        return out

    @app.get(P + "/employees/{eid}")
    def hr_employee(eid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who = ctx(request)
        out = call(H.get_employee, engine, tenant, eid)
        if not sees_full_record(who):
            if out.get("status") != "aktif":
                raise HTTPException(status_code=404, detail={"code": "HR", "message": "Çalışan kaydı bulunamadı."})
            out = directory_view(out)
        H.log_access(engine, tenant, who.user, "calisan", eid, "goruntule")
        return out

    @app.patch(P + "/employees/{eid}")
    def hr_employee_update(eid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ctx(request)
        need(who, F_EMPLOYEES, what="Çalışan kaydını düzenleme")
        out, diff = call(H.save_employee, engine, tenant, who.user, body, eid)
        if diff:
            hr.audit(engine, who.user, "update", "hr_employee", eid, out["displayName"], diff)
        return out

    @app.post(P + "/employees/sync-preview")
    def hr_sync_preview(request: Request) -> dict[str, Any]:
        """CRM ∩ AD'den öneri; hiçbir şey yazmaz."""
        engine, tenant, who = ctx(request)
        need(who, F_EMPLOYEES, what="Çalışan eşitlemesi")
        with HK.capture(engine) as got:
            out = call(preview, engine, tenant)
        return hr.kaynak(out, got, "esitleme", {"stats": ("esitleme", F_ESITLEME), "units": ("esitlemeBirim", F_ESITLEME_BIRIM),
                                                 "teams": ("esitlemeEkip", F_ESITLEME_EKIP, ["crm"])},
                         rest=("esitleme", F_ESITLEME))

    @app.post(P + "/employees/sync-apply")
    def hr_sync_apply(body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Öneriyi o anki CRM/AD ile yeniden kurar ve seçilen türleri yazar (units, new, changed, departed)."""
        engine, tenant, who = ctx(request)
        need(who, F_EMPLOYEES, what="Çalışan eşitlemesi")
        kinds = [k for k in (body.get("kinds") or []) if k in ("units", "new", "changed", "departed")]
        if not kinds:
            raise HTTPException(400, detail={"code": "HR", "message": "Uygulanacak öneri türünü seçin."})
        pv = call(preview, engine, tenant)
        done = call(H.apply_sync, engine, tenant, who.user, pv, kinds)
        hr.audit(engine, who.user, "run", "hr_employee", "sync", "Çalışan ve birim eşitlemesi (CRM ∩ AD)",
                 {"turler": kinds, **done, "crmEtkin": pv["stats"]["crmInteractive"], "adBakildi": pv["stats"]["adChecked"]})
        return {"applied": done, "stats": pv["stats"], "notes": pv["notes"]}

    @app.get(P + "/units")
    def hr_units(request: Request) -> dict[str, Any]:
        engine, tenant, _ = ctx(request)
        with HK.capture(engine) as got:
            out = {"items": H.list_units(engine, tenant)}
        return hr.kaynak(out, got, "birim", {"items[]": ("birim", F_BIRIM)})

    @app.post(P + "/units", status_code=201)
    def hr_unit_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ctx(request)
        need(who, F_EMPLOYEES, what="Birim kaydını düzenleme")
        out, _ = call(H.save_unit, engine, tenant, who.user, body)
        hr.audit(engine, who.user, "create", "hr_unit", out["id"], out["name"])
        return out

    @app.patch(P + "/units/{uid}")
    def hr_unit_update(uid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ctx(request)
        need(who, F_EMPLOYEES, what="Birim kaydını düzenleme")
        out, diff = call(H.save_unit, engine, tenant, who.user, body, uid)
        if diff:
            hr.audit(engine, who.user, "update", "hr_unit", uid, out["name"], diff)
        return out

    # ------------------------------------------------------------------ aydınlatma ve rıza

    @app.get(P + "/notices")
    def hr_notices(request: Request, audience: str = "") -> dict[str, Any]:
        engine, tenant, _ = ctx(request)
        with HK.capture(engine) as got:
            out = {"items": H.list_notices(engine, tenant, audience)}
        return hr.kaynak(out, got, "aydinlatma", {"items[]": ("aydinlatma", F_AYDINLATMA)})

    @app.post(P + "/notices", status_code=201)
    def hr_notice_publish(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ctx(request)
        need(who, F_KVKK, what="Aydınlatma metni yayımlama")
        out = call(H.publish_notice, engine, tenant, who.user, body)
        hr.audit(engine, who.user, "create", "hr_notice", out["id"], f"{out['title']} (sürüm {out['version']})",
                 {"kitle": out["audience"], "surum": out["version"]})
        return out

    def _consent_key(subject_type: str) -> tuple[str, ...]:
        # Aday rızası adayın kartından İK'nın kendisi tarafından da işlenir.
        return (F_KVKK, "ozellik:ik.aday-hepsi") if subject_type == "aday" else (F_KVKK,)

    @app.get(P + "/consents")
    def hr_consents(request: Request, subjectType: str = "", subjectId: str = "") -> dict[str, Any]:
        engine, tenant, who = ctx(request)
        need(who, *(_consent_key(subjectType) if subjectType else (F_KVKK,)), what="Rıza kayıtlarını görme")
        return {"items": H.list_consents(engine, tenant, subjectType, subjectId), "purposes": H.PURPOSES}

    @app.post(P + "/consents", status_code=201)
    def hr_consent_add(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ctx(request)
        need(who, *_consent_key(str(body.get("subjectType") or "")), what="Rıza kaydı")
        out = call(H.add_consent, engine, tenant, who.user, body,
                   lambda st, sid: H.subject_exists(engine, tenant, st, sid))
        hr.audit(engine, who.user, "create", "hr_consent", out["id"], out["purposeLabel"],
                 {"kisi": f"{out['subjectType']}:{out['subjectId']}", "aydinlatmaSurumu": out["noticeVersion"], "kanal": out["channel"]})
        return out

    @app.post(P + "/consents/{cid}/withdraw")
    def hr_consent_withdraw(cid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who = ctx(request)
        rows = [c for c in H.list_consents(engine, tenant) if c["id"] == cid]
        need(who, *_consent_key(rows[0]["subjectType"] if rows else ""), what="Rızayı geri çekme")
        out = call(H.withdraw_consent, engine, tenant, who.user, cid)
        hr.audit(engine, who.user, "update", "hr_consent", cid, f"{out['purposeLabel']} geri çekildi",
                 {"kisi": f"{out['subjectType']}:{out['subjectId']}"})
        return out

    # ------------------------------------------------------------------ saklama ve imha

    @app.get(P + "/retention")
    def hr_retention(request: Request) -> dict[str, Any]:
        engine, tenant, _ = ctx(request)
        with HK.capture(engine) as got:
            out = {"items": H.retention(engine, tenant)}
        return hr.kaynak(out, got, "saklama", {"items[]": ("saklama", F_SAKLAMA)})

    @app.put(P + "/retention")
    def hr_retention_put(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ctx(request)
        need(who, F_KVKK, what="Saklama süresi ayarı")
        items, diff = call(H.put_retention, engine, tenant, who.user, list(body.get("items") or []))
        if diff:
            hr.audit(engine, who.user, "update", "hr_retention", "retention", "İK saklama süreleri", diff)
        return {"items": items}

    @app.get(P + "/purge/preview")
    def hr_purge_preview(request: Request) -> dict[str, Any]:
        engine, tenant, who = ctx(request)
        need(who, F_KVKK, what="İmha önizlemesi")
        with HK.capture(engine) as got:
            out = {"items": H.purge_preview(engine, tenant)}
        return hr.kaynak(out, got, "imha", {"items[]": ("imha", F_IMHA)})

    @app.get(P + "/purge/runs")
    def hr_purge_runs(request: Request, before: int = 0, limit: int = 200) -> dict[str, Any]:
        engine, tenant, who = ctx(request)
        need(who, F_KVKK, F_ACCESS_LOG, what="İmha tutanakları")
        with HK.capture(engine) as got:
            out = H.purge_runs(engine, tenant, before=before or None, limit=limit)
        return hr.kaynak(out, got, "imhaKayit", {}, rest=("imhaKayit", F_IMHA_KAYIT))

    @app.post(P + "/purge/run-due")
    def hr_purge_run_due(request: Request) -> dict[str, Any]:
        """Zamanlayıcı: saklama süresi dolan İK kayıtlarını siler, sınıf başına tutanak yazar."""
        require_caller(request)
        engine, tenant = hr.system()
        out = H.run_due_purge(engine, tenant, "sistem")
        hr.audit(engine, "sistem", "run", "hr_purge", "run-due", "İK gece imha işi",
                 {x["key"]: x["purged"] for x in out["classes"]})
        return out

    @app.get(P + "/access-log")
    def hr_access_log(request: Request, subjectId: str = "", user: str = "", before: int = 0, limit: int = 200) -> dict[str, Any]:
        engine, tenant, who = ctx(request)
        need(who, F_ACCESS_LOG, what="İK erişim kaydı")
        with HK.capture(engine) as got:
            out = H.access_log(engine, tenant, subject_id=subjectId, username=user, before=before or None, limit=limit)
        return hr.kaynak(out, got, "erisim", {}, rest=("erisim", F_ERISIM))

    return hr
