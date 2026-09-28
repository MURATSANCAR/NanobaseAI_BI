"""M57 Eğitim ve gelişim: katalog, oturum, katılım, sertifika, zorunlu eğitim son tarihi, ihtiyaç, anonim geri
bildirim, modül rehberleri; iş kuralları.

Analiz: docs/analiz/kullanici-ihtiyaclari/M57-egitim-gelisim.md §14. Ortak temel `hr_core` (İK-0). Portal kullanım
sayımı ve Logo eğitim gideri `hr_learning_sources`'ta.

Kurallar:
- **Zorunlu eğitim durumu hesaplanır, saklanmaz.** Bir çalışanın zorunlu eğitimdeki durumu, o eğitimdeki doğrulanmış
  (`verified_at` dolu) en son sertifikasının `expires_on` tarihinden gelir: yok → «hiç almadı», geçmiş → «süresi doldu»,
  `bugün + gün` öncesi → «dolacak». Zorunlu eğitim kartında birim listesi boşsa bütün etkin çalışanlara uygulanır.
  Geçerlilik süresi (yenileme periyodu) sistemde sabit değildir; İK/İSG sorumlusu eğitim kartına girer (tehlike sınıfı).
- **Oturum kapanınca** yoklamada «katıldı» olan her onaylı katılım tamamlanır; eğitimin geçerlilik süresine göre
  doğrulanmış sertifika yazılır ve katılımcı başına tek kullanımlık geri bildirim jetonu üretilir. Yoklaması eksik oturum
  kapanmaz.
- **Geri bildirim anonimdir.** `semantic_hr_learning_feedback` tablosunda kişi kolonu yoktur; jeton tablosu kimin
  jetonu kullandığını yalnız gün düzeyinde tutar, yanıt da yalnız gün düzeyinde tarih taşır (saat eşleşmesiyle kişi
  bulunamasın). Gizlilik eşiği (`HR_PRIVACY_MIN_GROUP`) girildiyse yanıt sayısı eşiğin altındaki oturumun sonucu
  gösterilmez.
- **Katılım onayı:** çalışanın kendi talebi yöneticisinin (`ik.egitim-onay`) onayını bekler; dış eğitimde ardından İK
  (`ik.egitim-yonet`) onayı gelir. İK'nın doğrudan eklediği katılım onaylı başlar.
- **Model:** Zeki AI ihtiyaç metnini katalogdaki eğitimlerden birine kapalı seçimle eşler (katalog dışı seçenek dahil),
  öncelik önerir ve gerekçe yazar; yorumları kapalı tema listesine ayırır; rehber taslağı yazar. Modele kişi adı, hesap
  adı ya da kimlik gitmez; ihtiyaç metni ve yorumlar önce kural maskesinden geçer (e-posta, telefon, T.C. no, IBAN).
  Rakamı model üretmez.
- **Saklama:** `egitim_kaydi` (ayrılan çalışanın eğitim, sertifika ve ihtiyaç kayıtları; süre ayrılış tarihinden) ve
  `egitim_kullanim` (portal sayfa ziyaret sayacı; süre ziyaret gününden). Süre girilmemiş sınıfta imha yapılmaz.
"""
from __future__ import annotations

import logging
import re
import secrets
import threading
import weakref
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

import sqlalchemy as sa

from semantic_bridge import hr_core as H
from semantic_bridge.hr_core import HrError, aware, clean, dump, iso, load, new_id, now

log = logging.getLogger("semantic_bridge.hr.learning")

_md = sa.MetaData()
TZ = ZoneInfo("Europe/Istanbul")


def _ts(name: str, **kw: Any) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), **kw)


COURSES = sa.Table(
    "semantic_hr_courses", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("title", sa.String(200), nullable=False),
    sa.Column("kind", sa.String(16), nullable=False),               # zorunlu | gelisim | zeki
    sa.Column("delivery", sa.String(16), nullable=False),           # ic | dis | cevrimici
    sa.Column("duration_hours", sa.Float),
    sa.Column("validity_days", sa.Integer),                         # boş = süresiz
    sa.Column("cost_per_person", sa.Float),
    sa.Column("provider", sa.String(200)),
    sa.Column("module_route", sa.String(80)),                       # ZEKİ eğitiminde ilgili menü öğesi (ör. «telif-sozlesme»)
    sa.Column("required_units_json", sa.Text),                      # zorunlu eğitimin birimleri; boş = bütün etkin çalışanlar
    sa.Column("description", sa.Text),
    sa.Column("active", sa.Boolean, nullable=False, default=True),
    sa.Column("created_by", sa.String(120)),
    _ts("created_at", nullable=False),
    sa.Column("updated_by", sa.String(120)),
    _ts("updated_at", nullable=False),
)

SESSIONS = sa.Table(
    "semantic_hr_sessions", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("course_id", sa.String(40), nullable=False, index=True),
    _ts("starts_at", nullable=False),
    _ts("ends_at"),
    sa.Column("location", sa.String(300)),
    sa.Column("room_booking_id", sa.String(80)),
    sa.Column("trainer", sa.String(200)),
    sa.Column("capacity", sa.Integer),                              # bilgi; kayıt kesmez
    sa.Column("state", sa.String(16), nullable=False),              # planli | yapildi | iptal
    sa.Column("feedback_summary_json", sa.Text),                    # Zeki AI tema özeti (kimlik yok)
    sa.Column("closed_by", sa.String(120)),
    _ts("closed_at"),
    sa.Column("created_by", sa.String(120)),
    _ts("created_at", nullable=False),
    _ts("updated_at", nullable=False),
)

ENROLLMENTS = sa.Table(
    "semantic_hr_enrollments", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("session_id", sa.String(40), nullable=False, index=True),
    sa.Column("employee_id", sa.String(40), nullable=False, index=True),
    sa.Column("approval", sa.String(20), nullable=False),           # bekliyor | yonetici_onayladi | onaylandi | reddedildi
    sa.Column("requested_by", sa.String(120)),
    _ts("requested_at"),
    sa.Column("approved_by", sa.String(120)),                       # yönetici onayı
    _ts("approved_at"),
    sa.Column("hr_approved_by", sa.String(120)),                    # dış eğitimde İK onayı
    _ts("hr_approved_at"),
    sa.Column("decision_note", sa.Text),
    sa.Column("attendance", sa.String(12)),                         # katildi | gelmedi | NULL
    sa.Column("attendance_by", sa.String(120)),
    _ts("completed_at"),
    sa.UniqueConstraint("session_id", "employee_id", name="uq_hr_enrollment"),
)

CERTIFICATES = sa.Table(
    "semantic_hr_certificates", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("employee_id", sa.String(40), nullable=False, index=True),
    sa.Column("course_id", sa.String(40), index=True),              # katalog dışı belgede boş (ör. dil sertifikası)
    sa.Column("title", sa.String(200)),
    sa.Column("source", sa.String(16), nullable=False),             # oturum | yukleme | ik
    sa.Column("session_id", sa.String(40)),
    sa.Column("issued_on", sa.Date, nullable=False),
    sa.Column("expires_on", sa.Date),                               # boş = süresiz
    sa.Column("file_blob", sa.LargeBinary),
    sa.Column("file_name", sa.String(255)),
    sa.Column("file_mime", sa.String(120)),
    sa.Column("file_size", sa.Integer),
    sa.Column("created_by", sa.String(120)),
    _ts("created_at", nullable=False),
    sa.Column("verified_by", sa.String(120)),
    _ts("verified_at"),
)

NEEDS = sa.Table(
    "semantic_hr_training_needs", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("employee_id", sa.String(40), index=True),            # birim düzeyindeki ihtiyaçta boş
    sa.Column("unit_id", sa.String(40)),
    sa.Column("source", sa.String(20), nullable=False),             # gelisim_plani | yonetici | calisan | yetkinlik | ik
    sa.Column("text", sa.Text, nullable=False),
    sa.Column("suggested_course_id", sa.String(40)),
    sa.Column("suggestion_reason", sa.Text),
    sa.Column("suggestion_json", sa.Text),                          # seçim olasılıkları (kimlik yok)
    sa.Column("priority", sa.String(12)),                           # yuksek | orta | dusuk
    sa.Column("state", sa.String(16), nullable=False),              # acik | onaylandi | reddedildi | karsilandi
    sa.Column("course_id", sa.String(40)),                          # İK'nın kararıyla bağlanan eğitim
    sa.Column("decided_by", sa.String(120)),
    _ts("decided_at"),
    sa.Column("decision_note", sa.Text),
    sa.Column("created_by", sa.String(120)),
    _ts("created_at", nullable=False),
)

#: Anonim yanıt: kişi kolonu YOK (şema testi bunu denetler). Tarih yalnız gün.
FEEDBACK = sa.Table(
    "semantic_hr_learning_feedback", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("session_id", sa.String(40), nullable=False, index=True),
    sa.Column("submitted_on", sa.Date, nullable=False),
    sa.Column("answers_json", sa.Text, nullable=False),
    sa.Column("comment", sa.Text),
)

#: Tek yanıt garantisi. Jeton gizlidir; kullanıldığı gün tutulur, saat tutulmaz.
FEEDBACK_TOKENS = sa.Table(
    "semantic_hr_feedback_tokens", _md,
    sa.Column("token", sa.String(64), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("session_id", sa.String(40), nullable=False, index=True),
    sa.Column("employee_id", sa.String(40), nullable=False, index=True),
    sa.Column("created_on", sa.Date, nullable=False),
    sa.Column("used_on", sa.Date),
)

GUIDES = sa.Table(
    "semantic_hr_guides", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("module_route", sa.String(80), nullable=False, index=True),   # menü öğesi kimliği
    sa.Column("title", sa.String(200), nullable=False),
    sa.Column("body_md", sa.Text, nullable=False),
    sa.Column("version", sa.Integer, nullable=False, default=0),            # yayımlanan sürüm; 0 = hiç yayımlanmadı
    sa.Column("state", sa.String(12), nullable=False),                      # taslak | yayinda
    sa.Column("published_body", sa.Text),                                   # okuyucunun gördüğü sürüm
    sa.Column("published_title", sa.String(200)),
    sa.Column("model_drafted", sa.Boolean, nullable=False, default=False),
    sa.Column("approved_by", sa.String(120)),
    _ts("approved_at"),
    sa.Column("updated_by", sa.String(120)),
    _ts("updated_at", nullable=False),
)

GUIDE_VOTES = sa.Table(
    "semantic_hr_guide_votes", _md,
    sa.Column("guide_id", sa.String(40), primary_key=True),
    sa.Column("username", sa.String(120), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("useful", sa.Boolean, nullable=False),
    _ts("at", nullable=False),
)

#: Günlük özet: (gün, menü öğesi, hesap) başına sayı. Ham tıklama tutulmaz.
PAGE_VISITS = sa.Table(
    "semantic_hr_page_visits", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("day", sa.Date, primary_key=True),
    sa.Column("route_prefix", sa.String(80), primary_key=True),
    sa.Column("username", sa.String(120), primary_key=True),
    sa.Column("count", sa.Integer, nullable=False, default=1),
)

BUDGETS = sa.Table(
    "semantic_hr_training_budget", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("year", sa.Integer, primary_key=True),
    sa.Column("amount", sa.Float, nullable=False),
    sa.Column("note", sa.Text),
    sa.Column("updated_by", sa.String(120)),
    _ts("updated_at", nullable=False),
)

_ready: "weakref.WeakSet[sa.engine.Engine]" = weakref.WeakSet()
_lock = threading.Lock()

F_MANAGE = "ozellik:ik.egitim-yonet"
F_APPROVE = "ozellik:ik.egitim-onay"
F_BUDGET = "ozellik:ik.egitim-butce"
F_USAGE = "ozellik:ik.kullanim-haritasi"
F_GUIDES = "ozellik:ik.rehber-yaz"
F_EXPORT = "ozellik:ik.disa-aktar"

KINDS = {"zorunlu": "Zorunlu", "gelisim": "Gelişim", "zeki": "ZEKİ kullanımı"}
DELIVERY = {"ic": "İç eğitim", "dis": "Dış eğitim", "cevrimici": "Çevrimiçi"}
SESSION_STATES = {"planli": "Planlı", "yapildi": "Yapıldı", "iptal": "İptal"}
APPROVAL = {"bekliyor": "Yönetici onayı bekliyor", "yonetici_onayladi": "İK onayı bekliyor", "onaylandi": "Onaylı",
            "reddedildi": "Reddedildi"}
ATTENDANCE = {"katildi": "Katıldı", "gelmedi": "Gelmedi"}
CERT_SOURCES = {"oturum": "Oturum", "yukleme": "Çalışan yükledi", "ik": "İK kaydı"}
NEED_SOURCES = {"gelisim_plani": "Gelişim planı", "yonetici": "Yönetici talebi", "calisan": "Çalışan talebi",
                "yetkinlik": "Yetkinlik boşluğu", "ik": "İK"}
NEED_STATES = {"acik": "Açık", "onaylandi": "Onaylandı", "reddedildi": "Reddedildi", "karsilandi": "Karşılandı"}
PRIORITIES = {"yuksek": "Yüksek", "orta": "Orta", "dusuk": "Düşük"}
GUIDE_STATES = {"taslak": "Taslak", "yayinda": "Yayında"}
STATUS = {"hic_yok": "Hiç almadı", "doldu": "Süresi doldu", "dolacak": "Süresi dolacak", "gecerli": "Geçerli"}

#: Geri bildirim formu: 1–5 ölçekli dört soru + açık uç. Sorular sabittir ki oturumlar karşılaştırılabilsin.
QUESTIONS = [
    {"key": "fayda", "label": "Eğitim işimde işime yarayacak"},
    {"key": "anlatim", "label": "Eğitmen konuyu anlaşılır anlattı"},
    {"key": "sure", "label": "Süre konuya uygundu"},
    {"key": "genel", "label": "Genel olarak memnun kaldım"},
]
#: Yorum temaları (kapalı liste; model yalnız bunlardan seçer).
THEMES = ["İçerik işime uzak / örnekler uygun değil", "Süre kısa ya da uzun", "Eğitmenin anlatımı",
          "Ortam, araç ya da teknik sorun", "Daha ileri düzey isteniyor", "Olumlu genel yorum", "Diğer"]

CERT_EXT = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}
_MAGIC = {"pdf": (b"%PDF",), "jpg": (b"\xff\xd8\xff",), "jpeg": (b"\xff\xd8\xff",), "png": (b"\x89PNG",)}
_ROUTE = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
#: Rehber metninde geçmemesi gereken altyapı adları (ekranda teknoloji adı yok).
_TECH = re.compile(r"\b(qwen\w*|vllm|llama\w*|gpt\w*|openai|chatgpt|claude|anthropic|gemini|mistral|deepseek|timesfm|"
                   r"temporal|typst|ghostscript|real-esrgan|ollama|qdrant|postgres\w*|fastapi|sqlalchemy|docker)\b", re.I)


def ensure(engine: sa.engine.Engine) -> None:
    H.ensure(engine)
    with _lock:
        if engine in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(engine)


def today() -> date:
    return datetime.now(TZ).date()


def _d(v: Any) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def _dt(v: Any, what: str) -> Optional[datetime]:
    if v in (None, ""):
        return None
    try:
        t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        raise HrError(f"{what} geçersiz (YYYY-AA-GG SS:DD).") from None
    return t if t.tzinfo else t.replace(tzinfo=TZ)


def _num(v: Any, what: str, *, integer: bool = False, positive: bool = False) -> Optional[float]:
    if v in (None, ""):
        return None
    try:
        n = int(v) if integer else float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        raise HrError(f"{what} sayı olmalı.") from None
    if positive and n <= 0:
        raise HrError(f"{what} sıfırdan büyük olmalı.")
    if n < 0:
        raise HrError(f"{what} eksi olamaz.")
    return n


def settings(conf: Callable[[str], str]) -> dict[str, Any]:
    """Ayarlar ekran > env. Varsayılan eşik yok: girilmediyse ekran «ayarlanmadı» der."""
    def num(key: str) -> Optional[int]:
        try:
            n = int((conf(key) or "").strip())
        except ValueError:
            return None
        return n if n > 0 else None

    return {"alertDays": num("HR_LEARNING_ALERT_DAYS"), "minGroup": num("HR_PRIVACY_MIN_GROUP"),
            "accounts": parse_accounts(conf("HR_TRAINING_ACCOUNTS") or "")}


_ACCOUNT = re.compile(r"^[0-9][0-9A-Za-z.\-]{0,39}$")


def parse_accounts(raw: str) -> list[str]:
    """Virgülle Logo hesap kodları (alt hesaplar dahil sayılır). Geçersiz kod atlanmaz, hata verir."""
    out: list[str] = []
    for part in re.split(r"[,;\s]+", raw or ""):
        p = part.strip()
        if not p:
            continue
        if not _ACCOUNT.match(p) or not p.startswith("7"):
            raise HrError(f"«{p}» geçerli bir gider hesabı kodu değil (7 ile başlamalı).")
        if p not in out:
            out.append(p)
    return out


def _units(c: Any, tenant: str) -> dict[str, str]:
    return dict(c.execute(sa.select(H.UNITS.c.id, H.UNITS.c.name).where(H.UNITS.c.tenant_id == tenant)).all())


def _employees(c: Any, tenant: str, active_only: bool = False) -> dict[str, Any]:
    q = sa.select(H.EMPLOYEES).where(H.EMPLOYEES.c.tenant_id == tenant)
    if active_only:
        q = q.where(H.EMPLOYEES.c.status == "aktif")
    return {r.id: r for r in c.execute(q).all()}


def _emp_brief(r: Any, units: dict[str, str]) -> dict[str, Any]:
    return {"id": r.id, "displayName": r.display_name, "unitId": r.unit_id, "unitName": units.get(r.unit_id or "") or None,
            "title": r.title or "", "status": r.status}


# ------------------------------------------------------------------ katalog


def _course_out(r: Any, units: Optional[dict[str, str]] = None) -> dict[str, Any]:
    req = load(r.required_units_json, []) or []
    return {"id": r.id, "title": r.title, "kind": r.kind, "kindLabel": KINDS.get(r.kind, r.kind), "delivery": r.delivery,
            "deliveryLabel": DELIVERY.get(r.delivery, r.delivery), "durationHours": r.duration_hours,
            "validityDays": r.validity_days, "costPerPerson": r.cost_per_person, "provider": r.provider or "",
            "moduleRoute": r.module_route or None, "requiredUnits": req,
            "requiredUnitNames": [(units or {}).get(u, u) for u in req], "description": r.description or "",
            "active": bool(r.active), "updatedBy": r.updated_by, "updatedAt": iso(r.updated_at)}


def list_courses(engine: sa.engine.Engine, tenant: str, *, active_only: bool = False) -> list[dict[str, Any]]:
    ensure(engine)
    q = sa.select(COURSES).where(COURSES.c.tenant_id == tenant)
    if active_only:
        q = q.where(COURSES.c.active.is_(True))
    with engine.connect() as c:
        rows = c.execute(q.order_by(COURSES.c.kind, COURSES.c.title)).all()
        units = _units(c, tenant)
    return [_course_out(r, units) for r in rows]


def get_course(engine: sa.engine.Engine, tenant: str, cid: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(COURSES).where(COURSES.c.id == cid, COURSES.c.tenant_id == tenant)).first()
        if r is None:
            raise HrError("Eğitim kartı bulunamadı.", 404)
        return _course_out(r, _units(c, tenant))


_COURSE_FIELDS = ("title", "kind", "delivery", "durationHours", "validityDays", "costPerPerson", "provider",
                  "moduleRoute", "requiredUnits", "description", "active")


def save_course(engine: sa.engine.Engine, tenant: str, actor: str, body: dict[str, Any],
                cid: Optional[str] = None) -> tuple[dict[str, Any], dict[str, Any]]:
    ensure(engine)
    with engine.begin() as c:
        before = None
        if cid:
            before = c.execute(sa.select(COURSES).where(COURSES.c.id == cid, COURSES.c.tenant_id == tenant)).first()
            if before is None:
                raise HrError("Eğitim kartı bulunamadı.", 404)
        vals: dict[str, Any] = {}
        for key in _COURSE_FIELDS:
            if key not in body and before is not None:
                continue
            v = body.get(key)
            if key == "title":
                v = clean(v, 200)
                if not v:
                    raise HrError("Eğitimin adı boş olamaz.")
                vals["title"] = v
            elif key == "kind":
                if v not in KINDS:
                    raise HrError("Eğitim türü «zorunlu», «gelisim» ya da «zeki» olmalı.")
                vals["kind"] = v
            elif key == "delivery":
                if v not in DELIVERY:
                    raise HrError("Eğitim biçimi «ic», «dis» ya da «cevrimici» olmalı.")
                vals["delivery"] = v
            elif key == "durationHours":
                vals["duration_hours"] = _num(v, "Süre (saat)")
            elif key == "validityDays":
                n = _num(v, "Geçerlilik süresi (gün)", integer=True, positive=True)
                vals["validity_days"] = int(n) if n is not None else None
            elif key == "costPerPerson":
                vals["cost_per_person"] = _num(v, "Kişi başı maliyet")
            elif key == "provider":
                vals["provider"] = clean(v, 200) or None
            elif key == "moduleRoute":
                r = clean(v, 80).lower() or None
                if r and not _ROUTE.match(r):
                    raise HrError("Modül bağlantısı bir menü öğesi kimliği olmalı (ör. «telif-sozlesme»).")
                vals["module_route"] = r
            elif key == "requiredUnits":
                ids = [str(x) for x in (v or []) if str(x).strip()]
                if ids:
                    known = set(_units(c, tenant))
                    bad = [x for x in ids if x not in known]
                    if bad:
                        raise HrError("Seçilen birimlerden biri kayıtta yok.")
                vals["required_units_json"] = dump(sorted(set(ids))) if ids else None
            elif key == "description":
                vals["description"] = str(v or "").strip()[:4000] or None
            elif key == "active":
                vals["active"] = True if v is None else bool(v)
        kind = vals.get("kind", before.kind if before is not None else None)
        if kind != "zorunlu" and vals.get("required_units_json"):
            raise HrError("Birim listesi yalnız zorunlu eğitimde girilir.")
        t = now()
        vals.update(updated_by=actor, updated_at=t)
        if before is None:
            cid = new_id("egt")
            c.execute(COURSES.insert().values(id=cid, tenant_id=tenant, created_by=actor, created_at=t, **vals))
            diff = {"yeni": vals["title"]}
        else:
            diff = {k: {"once": getattr(before, k), "sonra": v} for k, v in vals.items()
                    if k not in ("updated_by", "updated_at") and getattr(before, k) != v}
            c.execute(COURSES.update().where(COURSES.c.id == cid).values(**vals))
    return get_course(engine, tenant, cid), diff


# ------------------------------------------------------------------ oturumlar ve katılım


def _session_out(r: Any, course: Optional[Any], counts: Optional[dict[str, int]] = None) -> dict[str, Any]:
    return {"id": r.id, "courseId": r.course_id, "courseTitle": course.title if course is not None else "",
            "courseKind": course.kind if course is not None else None, "delivery": course.delivery if course is not None else None,
            "startsAt": iso(r.starts_at), "endsAt": iso(r.ends_at), "location": r.location or "", "roomBookingId": r.room_booking_id,
            "trainer": r.trainer or "", "capacity": r.capacity, "state": r.state, "stateLabel": SESSION_STATES.get(r.state, r.state),
            "closedAt": iso(r.closed_at), "closedBy": r.closed_by, "counts": counts or {}}


def _session_counts(c: Any, tenant: str, sids: list[str]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {s: {"approved": 0, "pending": 0, "attended": 0, "absent": 0, "completed": 0} for s in sids}
    if not sids:
        return out
    rows = c.execute(sa.select(ENROLLMENTS.c.session_id, ENROLLMENTS.c.approval, ENROLLMENTS.c.attendance,
                               ENROLLMENTS.c.completed_at).where(ENROLLMENTS.c.tenant_id == tenant,
                                                                 ENROLLMENTS.c.session_id.in_(sids))).all()
    for r in rows:
        o = out[r.session_id]
        if r.approval == "onaylandi":
            o["approved"] += 1
        elif r.approval in ("bekliyor", "yonetici_onayladi"):
            o["pending"] += 1
        if r.attendance == "katildi":
            o["attended"] += 1
        elif r.attendance == "gelmedi":
            o["absent"] += 1
        if r.completed_at is not None:
            o["completed"] += 1
    return out


def list_sessions(engine: sa.engine.Engine, tenant: str, *, state: str = "", course_id: str = "",
                  since: Optional[date] = None) -> list[dict[str, Any]]:
    ensure(engine)
    q = sa.select(SESSIONS).where(SESSIONS.c.tenant_id == tenant)
    if state in SESSION_STATES:
        q = q.where(SESSIONS.c.state == state)
    if course_id:
        q = q.where(SESSIONS.c.course_id == course_id)
    if since is not None:
        q = q.where(SESSIONS.c.starts_at >= datetime(since.year, since.month, since.day, tzinfo=TZ))
    with engine.connect() as c:
        rows = c.execute(q.order_by(SESSIONS.c.starts_at.desc())).all()
        courses = {r.id: r for r in c.execute(sa.select(COURSES).where(COURSES.c.tenant_id == tenant)).all()}
        counts = _session_counts(c, tenant, [r.id for r in rows])
    return [_session_out(r, courses.get(r.course_id), counts.get(r.id)) for r in rows]


def _enr_out(r: Any, emps: dict[str, Any], units: dict[str, str]) -> dict[str, Any]:
    e = emps.get(r.employee_id)
    return {"id": r.id, "sessionId": r.session_id, "employeeId": r.employee_id,
            "employee": _emp_brief(e, units) if e is not None else None, "approval": r.approval,
            "approvalLabel": APPROVAL.get(r.approval, r.approval), "requestedBy": r.requested_by,
            "requestedAt": iso(r.requested_at), "approvedBy": r.approved_by, "approvedAt": iso(r.approved_at),
            "hrApprovedBy": r.hr_approved_by, "hrApprovedAt": iso(r.hr_approved_at), "decisionNote": r.decision_note or "",
            "attendance": r.attendance, "attendanceLabel": ATTENDANCE.get(r.attendance or "", None),
            "completedAt": iso(r.completed_at)}


def get_session(engine: sa.engine.Engine, tenant: str, sid: str, *, people: bool) -> dict[str, Any]:
    """Oturum ve (yalnız `people` ise) katılımcılar. Kişi listesi `ik.egitim-yonet` ister."""
    ensure(engine)
    with engine.connect() as c:
        r = c.execute(sa.select(SESSIONS).where(SESSIONS.c.id == sid, SESSIONS.c.tenant_id == tenant)).first()
        if r is None:
            raise HrError("Oturum bulunamadı.", 404)
        course = c.execute(sa.select(COURSES).where(COURSES.c.id == r.course_id)).first()
        out = _session_out(r, course, _session_counts(c, tenant, [sid]).get(sid))
        out["course"] = _course_out(course, _units(c, tenant)) if course is not None else None
        if people:
            emps, units = _employees(c, tenant), _units(c, tenant)
            rows = c.execute(sa.select(ENROLLMENTS).where(ENROLLMENTS.c.session_id == sid, ENROLLMENTS.c.tenant_id == tenant)).all()
            items = [_enr_out(x, emps, units) for x in rows]
            items.sort(key=lambda x: ((x["employee"] or {}).get("displayName") or "").casefold())
            out["enrollments"] = items
        tokens = c.execute(sa.select(sa.func.count(), sa.func.count(FEEDBACK_TOKENS.c.used_on)).where(
            FEEDBACK_TOKENS.c.session_id == sid, FEEDBACK_TOKENS.c.tenant_id == tenant)).first()
        out["feedback"] = {"invited": int(tokens[0] or 0), "answered": int(tokens[1] or 0)}
    return out


def create_session(engine: sa.engine.Engine, tenant: str, actor: str, body: dict[str, Any]) -> dict[str, Any]:
    """Oturum açar; `employeeIds` verilirse onaylı katılımcı olarak ekler (dolacak zorunlu eğitimden «Oturum aç»)."""
    ensure(engine)
    cid = str(body.get("courseId") or "")
    starts = _dt(body.get("startsAt"), "Başlangıç")
    ends = _dt(body.get("endsAt"), "Bitiş")
    if starts is None:
        raise HrError("Oturumun başlangıç tarihini girin.")
    if ends is not None and ends <= starts:
        raise HrError("Bitiş başlangıçtan sonra olmalı.")
    cap = _num(body.get("capacity"), "Kontenjan", integer=True, positive=True)
    t = now()
    sid = new_id("otr")
    with engine.begin() as c:
        course = c.execute(sa.select(COURSES).where(COURSES.c.id == cid, COURSES.c.tenant_id == tenant)).first()
        if course is None:
            raise HrError("Eğitim kartı bulunamadı.", 404)
        if not course.active:
            raise HrError("Pasif eğitime oturum açılmaz; önce kartı etkinleştirin.")
        c.execute(SESSIONS.insert().values(id=sid, tenant_id=tenant, course_id=cid, starts_at=starts, ends_at=ends,
                                           location=clean(body.get("location"), 300) or None,
                                           room_booking_id=clean(body.get("roomBookingId"), 80) or None,
                                           trainer=clean(body.get("trainer"), 200) or None,
                                           capacity=int(cap) if cap is not None else None, state="planli",
                                           created_by=actor, created_at=t, updated_at=t))
    ids = [str(x) for x in (body.get("employeeIds") or []) if str(x).strip()]
    if ids:
        enroll(engine, tenant, actor, sid, ids, "onaylandi")
    return get_session(engine, tenant, sid, people=True)


def update_session(engine: sa.engine.Engine, tenant: str, actor: str, sid: str, body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    ensure(engine)
    with engine.begin() as c:
        r = c.execute(sa.select(SESSIONS).where(SESSIONS.c.id == sid, SESSIONS.c.tenant_id == tenant)).first()
        if r is None:
            raise HrError("Oturum bulunamadı.", 404)
        if r.state != "planli":
            raise HrError("Yapılmış ya da iptal edilmiş oturum değiştirilemez.", 409)
        vals: dict[str, Any] = {}
        if "startsAt" in body:
            vals["starts_at"] = _dt(body.get("startsAt"), "Başlangıç") or r.starts_at
        if "endsAt" in body:
            vals["ends_at"] = _dt(body.get("endsAt"), "Bitiş")
        s, e = aware(vals.get("starts_at", r.starts_at)), aware(vals.get("ends_at", r.ends_at))
        if e is not None and e <= s:
            raise HrError("Bitiş başlangıçtan sonra olmalı.")
        for api, col, n in (("location", "location", 300), ("trainer", "trainer", 200), ("roomBookingId", "room_booking_id", 80)):
            if api in body:
                vals[col] = clean(body.get(api), n) or None
        if "capacity" in body:
            cap = _num(body.get("capacity"), "Kontenjan", integer=True, positive=True)
            vals["capacity"] = int(cap) if cap is not None else None
        if body.get("state") == "iptal":
            vals["state"] = "iptal"
        elif "state" in body and body.get("state") not in (None, "planli"):
            raise HrError("Oturum «Yapıldı»ya yoklama alınıp kapatılarak geçer.")
        diff = {k: {"once": iso(getattr(r, k)) if k.endswith("_at") else getattr(r, k), "sonra": iso(v) if k.endswith("_at") else v}
                for k, v in vals.items() if getattr(r, k) != v}
        vals["updated_at"] = now()
        c.execute(SESSIONS.update().where(SESSIONS.c.id == sid).values(**vals))
    return get_session(engine, tenant, sid, people=True), diff


def enroll(engine: sa.engine.Engine, tenant: str, actor: str, sid: str, employee_ids: Iterable[str],
           approval: str) -> dict[str, int]:
    """Katılım ekler. Aynı kişi aynı oturuma iki kez eklenmez; ayrılmış çalışan eklenmez."""
    ensure(engine)
    if approval not in APPROVAL:
        raise HrError("Geçersiz onay durumu.")
    t = now()
    added = skipped = 0
    with engine.begin() as c:
        s = c.execute(sa.select(SESSIONS).where(SESSIONS.c.id == sid, SESSIONS.c.tenant_id == tenant)).first()
        if s is None:
            raise HrError("Oturum bulunamadı.", 404)
        if s.state != "planli":
            raise HrError("Yalnız planlı oturuma katılımcı eklenir.", 409)
        have = set(c.execute(sa.select(ENROLLMENTS.c.employee_id).where(ENROLLMENTS.c.session_id == sid)).scalars())
        emps = _employees(c, tenant)
        for eid in dict.fromkeys(employee_ids):
            e = emps.get(eid)
            if e is None:
                raise HrError("Seçilen çalışanlardan biri kayıtta yok.", 404)
            if e.status != "aktif" or eid in have:
                skipped += 1
                continue
            vals: dict[str, Any] = dict(id=new_id("ktl"), tenant_id=tenant, session_id=sid, employee_id=eid, approval=approval,
                                        requested_by=actor, requested_at=t)
            if approval == "onaylandi":
                vals.update(approved_by=actor, approved_at=t)
            c.execute(ENROLLMENTS.insert().values(**vals))
            have.add(eid)
            added += 1
    return {"added": added, "skipped": skipped}


def remove_enrollment(engine: sa.engine.Engine, tenant: str, enr_id: str) -> None:
    with engine.begin() as c:
        r = c.execute(sa.select(ENROLLMENTS, SESSIONS.c.state).join(SESSIONS, SESSIONS.c.id == ENROLLMENTS.c.session_id)
                      .where(ENROLLMENTS.c.id == enr_id, ENROLLMENTS.c.tenant_id == tenant)).first()
        if r is None:
            raise HrError("Katılım kaydı bulunamadı.", 404)
        if r.state != "planli":
            raise HrError("Yapılmış oturumdan katılımcı çıkarılmaz.", 409)
        c.execute(ENROLLMENTS.delete().where(ENROLLMENTS.c.id == enr_id))


def _load_enr(c: Any, tenant: str, enr_id: str) -> tuple[Any, Any, Any]:
    r = c.execute(sa.select(ENROLLMENTS).where(ENROLLMENTS.c.id == enr_id, ENROLLMENTS.c.tenant_id == tenant)).first()
    if r is None:
        raise HrError("Katılım kaydı bulunamadı.", 404)
    s = c.execute(sa.select(SESSIONS).where(SESSIONS.c.id == r.session_id)).first()
    course = c.execute(sa.select(COURSES).where(COURSES.c.id == s.course_id)).first() if s is not None else None
    return r, s, course


def managed_employee_ids(engine: sa.engine.Engine, tenant: str, user: str) -> tuple[Optional[str], set[str]]:
    """Kişinin yöneticisi olduğu etkin çalışanlar: doğrudan bağlılar (`manager_id`) ve yöneticisi olduğu birimlerin
    çalışanları. Dönen: (kendi çalışan kimliği, ekip)."""
    me = H.employee_by_username(engine, tenant, user)
    if me is None:
        return None, set()
    with engine.connect() as c:
        units = set(c.execute(sa.select(H.UNITS.c.id).where(H.UNITS.c.tenant_id == tenant,
                                                            H.UNITS.c.manager_employee_id == me["id"])).scalars())
        q = sa.select(H.EMPLOYEES.c.id).where(H.EMPLOYEES.c.tenant_id == tenant, H.EMPLOYEES.c.status == "aktif",
                                              H.EMPLOYEES.c.id != me["id"])
        cond = H.EMPLOYEES.c.manager_id == me["id"]
        if units:
            cond = sa.or_(cond, H.EMPLOYEES.c.unit_id.in_(units))
        team = set(c.execute(q.where(cond)).scalars())
    return me["id"], team


def decide_enrollment(engine: sa.engine.Engine, tenant: str, who: H.Who, enr_id: str, action: str,
                      note: str = "") -> dict[str, Any]:
    """Onay zinciri: bekliyor → (yönetici) → dış eğitimde yonetici_onayladi → (İK) → onaylandi. Ret her adımda.
    Yönetici yalnız kendi ekibinde karar verir; İK (`egitim-yonet`) her adımı verebilir."""
    ensure(engine)
    if action not in ("onayla", "reddet"):
        raise HrError("İşlem «onayla» ya da «reddet» olmalı.")
    _, team = managed_employee_ids(engine, tenant, who.user)
    hr_role = who.can(F_MANAGE)
    t = now()
    with engine.begin() as c:
        r, s, course = _load_enr(c, tenant, enr_id)
        if s is None or s.state != "planli":
            raise HrError("Oturum planlı değil; katılım kararı verilemez.", 409)
        is_manager = who.can(F_APPROVE) and r.employee_id in team
        if r.approval == "bekliyor":
            if not (is_manager or hr_role):
                raise HrError("Bu katılımı yalnız çalışanın yöneticisi ya da İK onaylar.", 403)
        elif r.approval == "yonetici_onayladi":
            if not hr_role:
                raise HrError("Dış eğitimde son onay İK'nındır.", 403)
        else:
            raise HrError("Bu katılım için karar zaten verilmiş.", 409)
        vals: dict[str, Any] = {"decision_note": clean(note, 500) or None}
        if action == "reddet":
            vals["approval"] = "reddedildi"
            if r.approval == "bekliyor":
                vals.update(approved_by=who.user, approved_at=t)
            else:
                vals.update(hr_approved_by=who.user, hr_approved_at=t)
        elif r.approval == "bekliyor":
            vals.update(approved_by=who.user, approved_at=t)
            external = course is not None and course.delivery == "dis"
            if external and not hr_role:
                vals["approval"] = "yonetici_onayladi"
            else:
                vals["approval"] = "onaylandi"
                if external:
                    vals.update(hr_approved_by=who.user, hr_approved_at=t)
        else:
            vals.update(approval="onaylandi", hr_approved_by=who.user, hr_approved_at=t)
        c.execute(ENROLLMENTS.update().where(ENROLLMENTS.c.id == enr_id).values(**vals))
        row = c.execute(sa.select(ENROLLMENTS).where(ENROLLMENTS.c.id == enr_id)).first()
        emps, units = _employees(c, tenant), _units(c, tenant)
    return _enr_out(row, emps, units)


def set_attendance(engine: sa.engine.Engine, tenant: str, actor: str, sid: str, items: list[dict[str, Any]]) -> dict[str, int]:
    """Yoklama: yalnız onaylı katılımda. `attendance` boş gönderilirse işaret kaldırılır."""
    ensure(engine)
    n = 0
    with engine.begin() as c:
        s = c.execute(sa.select(SESSIONS).where(SESSIONS.c.id == sid, SESSIONS.c.tenant_id == tenant)).first()
        if s is None:
            raise HrError("Oturum bulunamadı.", 404)
        if s.state != "planli":
            raise HrError("Kapanmış oturumun yoklaması değişmez.", 409)
        for it in items or []:
            att = it.get("attendance") or None
            if att is not None and att not in ATTENDANCE:
                raise HrError("Yoklama «katildi» ya da «gelmedi» olmalı.")
            r = c.execute(sa.select(ENROLLMENTS).where(ENROLLMENTS.c.id == str(it.get("enrollmentId") or ""),
                                                       ENROLLMENTS.c.session_id == sid)).first()
            if r is None:
                raise HrError("Katılım kaydı bu oturumda yok.", 404)
            if r.approval != "onaylandi":
                raise HrError("Onaylanmamış katılımın yoklaması alınmaz.", 409)
            c.execute(ENROLLMENTS.update().where(ENROLLMENTS.c.id == r.id).values(attendance=att, attendance_by=actor))
            n += 1
    return {"updated": n}


def close_session(engine: sa.engine.Engine, tenant: str, actor: str, sid: str) -> dict[str, Any]:
    """Oturumu kapatır: katılanlar tamamlanır, sertifika yazılır, anket jetonları üretilir. Yoklaması eksikse 409."""
    ensure(engine)
    t = now()
    day = today()
    with engine.begin() as c:
        s = c.execute(sa.select(SESSIONS).where(SESSIONS.c.id == sid, SESSIONS.c.tenant_id == tenant)).first()
        if s is None:
            raise HrError("Oturum bulunamadı.", 404)
        if s.state != "planli":
            raise HrError("Oturum zaten kapanmış ya da iptal edilmiş.", 409)
        course = c.execute(sa.select(COURSES).where(COURSES.c.id == s.course_id)).first()
        rows = c.execute(sa.select(ENROLLMENTS).where(ENROLLMENTS.c.session_id == sid,
                                                      ENROLLMENTS.c.approval == "onaylandi")).all()
        missing = sum(1 for r in rows if r.attendance is None)
        if missing:
            raise HrError(f"Yoklaması alınmamış {missing} katılımcı var; önce yoklamayı tamamlayın.", 409)
        issued = aware(s.starts_at).astimezone(TZ).date()
        expires = issued + timedelta(days=course.validity_days) if course is not None and course.validity_days else None
        done = 0
        for r in rows:
            if r.attendance != "katildi":
                continue
            c.execute(ENROLLMENTS.update().where(ENROLLMENTS.c.id == r.id).values(completed_at=t))
            c.execute(CERTIFICATES.insert().values(id=new_id("srt"), tenant_id=tenant, employee_id=r.employee_id,
                                                   course_id=s.course_id, title=course.title if course is not None else None,
                                                   source="oturum", session_id=sid, issued_on=issued, expires_on=expires,
                                                   created_by=actor, created_at=t, verified_by=actor, verified_at=t))
            c.execute(FEEDBACK_TOKENS.insert().values(token=secrets.token_hex(24), tenant_id=tenant, session_id=sid,
                                                      employee_id=r.employee_id, created_on=day))
            done += 1
        c.execute(SESSIONS.update().where(SESSIONS.c.id == sid).values(state="yapildi", closed_by=actor, closed_at=t, updated_at=t))
    return {"completed": done, "absent": sum(1 for r in rows if r.attendance == "gelmedi"), "feedbackInvited": done}


# ------------------------------------------------------------------ sertifikalar


def _cert_out(r: Any, courses: dict[str, Any], emps: Optional[dict[str, Any]] = None,
              units: Optional[dict[str, str]] = None) -> dict[str, Any]:
    course = courses.get(r.course_id or "")
    out = {"id": r.id, "employeeId": r.employee_id, "courseId": r.course_id,
           "title": (course.title if course is not None else None) or r.title or "",
           "courseKind": course.kind if course is not None else None, "source": r.source,
           "sourceLabel": CERT_SOURCES.get(r.source, r.source), "issuedOn": iso(r.issued_on), "expiresOn": iso(r.expires_on),
           "hasFile": bool(r.file_name), "fileName": r.file_name, "fileSize": r.file_size, "verified": r.verified_at is not None,
           "verifiedBy": r.verified_by, "verifiedAt": iso(r.verified_at), "createdAt": iso(r.created_at)}
    if emps is not None:
        e = emps.get(r.employee_id)
        out["employee"] = _emp_brief(e, units or {}) if e is not None else None
    return out


def _check_file(filename: str, data: bytes, max_mb: int) -> tuple[str, str]:
    name = clean(filename, 255) or "belge"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in CERT_EXT:
        raise HrError("Belge PDF, JPG ya da PNG olmalı.", 415)
    if not data:
        raise HrError("Dosya boş.")
    if len(data) > max_mb * 1024 * 1024:
        raise HrError(f"Dosya {max_mb} MB sınırını aşıyor.", 413)
    if not any(data.startswith(m) for m in _MAGIC[ext]):
        raise HrError("Dosyanın içeriği uzantısıyla uyuşmuyor.", 415)
    return name, CERT_EXT[ext]


def upload_certificate(engine: sa.engine.Engine, tenant: str, actor: str, employee_id: str, meta: dict[str, Any],
                       filename: str, data: bytes, max_mb: int) -> dict[str, Any]:
    """Çalışanın kendi belgesi: doğrulanmamış başlar, İK doğrular. Belge yalnız kişiye ve İK'ya açıktır."""
    ensure(engine)
    name, mime = _check_file(filename, data, max_mb)
    issued = H.parse_date(meta.get("issuedOn"), "Belge") or today()
    expires = H.parse_date(meta.get("expiresOn"), "Geçerlilik bitiş")
    if expires is not None and expires <= issued:
        raise HrError("Geçerlilik bitişi belge tarihinden sonra olmalı.")
    if issued > today():
        raise HrError("Belge tarihi gelecekte olamaz.")
    course_id = str(meta.get("courseId") or "") or None
    title = clean(meta.get("title"), 200) or None
    with engine.begin() as c:
        if course_id and c.execute(sa.select(COURSES.c.id).where(COURSES.c.id == course_id, COURSES.c.tenant_id == tenant)).first() is None:
            raise HrError("Eğitim kartı bulunamadı.", 404)
        if not course_id and not title:
            raise HrError("Belgenin hangi eğitime ait olduğunu seçin ya da adını yazın.")
        cid = new_id("srt")
        c.execute(CERTIFICATES.insert().values(id=cid, tenant_id=tenant, employee_id=employee_id, course_id=course_id, title=title,
                                               source="yukleme", issued_on=issued, expires_on=expires, file_blob=data,
                                               file_name=name, file_mime=mime, file_size=len(data), created_by=actor,
                                               created_at=now()))
        courses = {r.id: r for r in c.execute(sa.select(COURSES).where(COURSES.c.tenant_id == tenant)).all()}
        return _cert_out(c.execute(sa.select(CERTIFICATES).where(CERTIFICATES.c.id == cid)).first(), courses)


def record_certificate(engine: sa.engine.Engine, tenant: str, actor: str, body: dict[str, Any]) -> dict[str, Any]:
    """İK'nın elle kaydı (ör. İSG hizmet firmasının listesi); doğrulanmış başlar, dosyasız."""
    ensure(engine)
    eid = str(body.get("employeeId") or "")
    course_id = str(body.get("courseId") or "") or None
    title = clean(body.get("title"), 200) or None
    issued = H.parse_date(body.get("issuedOn"), "Belge")
    if issued is None:
        raise HrError("Belge tarihini girin.")
    if issued > today():
        raise HrError("Belge tarihi gelecekte olamaz.")
    t = now()
    with engine.begin() as c:
        emp = c.execute(sa.select(H.EMPLOYEES).where(H.EMPLOYEES.c.id == eid, H.EMPLOYEES.c.tenant_id == tenant)).first()
        if emp is None:
            raise HrError("Çalışan kaydı bulunamadı.", 404)
        course = None
        if course_id:
            course = c.execute(sa.select(COURSES).where(COURSES.c.id == course_id, COURSES.c.tenant_id == tenant)).first()
            if course is None:
                raise HrError("Eğitim kartı bulunamadı.", 404)
        elif not title:
            raise HrError("Belgenin hangi eğitime ait olduğunu seçin ya da adını yazın.")
        if "expiresOn" in body and body.get("expiresOn") not in (None, ""):
            expires = H.parse_date(body.get("expiresOn"), "Geçerlilik bitiş")
        else:
            expires = issued + timedelta(days=course.validity_days) if course is not None and course.validity_days else None
        if expires is not None and expires <= issued:
            raise HrError("Geçerlilik bitişi belge tarihinden sonra olmalı.")
        cid = new_id("srt")
        c.execute(CERTIFICATES.insert().values(id=cid, tenant_id=tenant, employee_id=eid, course_id=course_id, title=title,
                                               source="ik", issued_on=issued, expires_on=expires, created_by=actor, created_at=t,
                                               verified_by=actor, verified_at=t))
        courses = {r.id: r for r in c.execute(sa.select(COURSES).where(COURSES.c.tenant_id == tenant)).all()}
        return _cert_out(c.execute(sa.select(CERTIFICATES).where(CERTIFICATES.c.id == cid)).first(), courses)


def list_certificates(engine: sa.engine.Engine, tenant: str, *, employee_id: str = "", unverified: bool = False) -> list[dict[str, Any]]:
    ensure(engine)
    q = sa.select(CERTIFICATES.c.id, CERTIFICATES.c.employee_id, CERTIFICATES.c.course_id, CERTIFICATES.c.title,
                  CERTIFICATES.c.source, CERTIFICATES.c.issued_on, CERTIFICATES.c.expires_on, CERTIFICATES.c.file_name,
                  CERTIFICATES.c.file_size, CERTIFICATES.c.verified_by, CERTIFICATES.c.verified_at,
                  CERTIFICATES.c.created_at).where(CERTIFICATES.c.tenant_id == tenant)
    if employee_id:
        q = q.where(CERTIFICATES.c.employee_id == employee_id)
    if unverified:
        q = q.where(CERTIFICATES.c.verified_at.is_(None))
    with engine.connect() as c:
        rows = c.execute(q.order_by(CERTIFICATES.c.issued_on.desc())).all()
        courses = {r.id: r for r in c.execute(sa.select(COURSES).where(COURSES.c.tenant_id == tenant)).all()}
        emps, units = _employees(c, tenant), _units(c, tenant)
    return [_cert_out(r, courses, emps, units) for r in rows]


def verify_certificate(engine: sa.engine.Engine, tenant: str, actor: str, cert_id: str) -> dict[str, Any]:
    with engine.begin() as c:
        r = c.execute(sa.select(CERTIFICATES.c.id, CERTIFICATES.c.verified_at).where(
            CERTIFICATES.c.id == cert_id, CERTIFICATES.c.tenant_id == tenant)).first()
        if r is None:
            raise HrError("Belge bulunamadı.", 404)
        if r.verified_at is not None:
            raise HrError("Belge zaten doğrulanmış.", 409)
        c.execute(CERTIFICATES.update().where(CERTIFICATES.c.id == cert_id).values(verified_by=actor, verified_at=now()))
    return {"id": cert_id, "verified": True}


def delete_certificate(engine: sa.engine.Engine, tenant: str, cert_id: str, owner_employee_id: Optional[str] = None) -> dict[str, Any]:
    """İK her belgeyi, çalışan yalnız kendi doğrulanmamış yüklemesini siler. Dönen: silinen kaydın özeti."""
    with engine.begin() as c:
        r = c.execute(sa.select(CERTIFICATES.c.id, CERTIFICATES.c.employee_id, CERTIFICATES.c.verified_at,
                                CERTIFICATES.c.source).where(CERTIFICATES.c.id == cert_id, CERTIFICATES.c.tenant_id == tenant)).first()
        if r is None or (owner_employee_id is not None and r.employee_id != owner_employee_id):
            raise HrError("Belge bulunamadı.", 404)
        if owner_employee_id is not None and (r.verified_at is not None or r.source != "yukleme"):
            raise HrError("Doğrulanmış belgeyi yalnız İK kaldırabilir.", 403)
        c.execute(CERTIFICATES.delete().where(CERTIFICATES.c.id == cert_id))
    return {"id": cert_id, "employeeId": r.employee_id}


def certificate_file(engine: sa.engine.Engine, tenant: str, cert_id: str, owner_employee_id: Optional[str] = None) -> tuple[bytes, str, str, str]:
    """(veri, dosya adı, tür, çalışan kimliği). `owner_employee_id` verilirse yalnız o kişinin belgesi."""
    with engine.connect() as c:
        r = c.execute(sa.select(CERTIFICATES).where(CERTIFICATES.c.id == cert_id, CERTIFICATES.c.tenant_id == tenant)).first()
    if r is None or (owner_employee_id is not None and r.employee_id != owner_employee_id):
        raise HrError("Belge bulunamadı.", 404)
    if not r.file_blob:
        raise HrError("Bu kayıtta dosya yok.", 404)
    return bytes(r.file_blob), r.file_name or "belge", r.file_mime or "application/octet-stream", r.employee_id


# ------------------------------------------------------------------ zorunlu eğitim durumu


def mandatory_status(engine: sa.engine.Engine, tenant: str, *, days: int = 0, on: Optional[date] = None,
                     employee_ids: Optional[set[str]] = None) -> list[dict[str, Any]]:
    """Her etkin çalışan × kendisine uygulanan etkin zorunlu eğitim için durum. Yalnız doğrulanmış sertifika sayılır.
    `days` uyarı öne alma günü; 0 → yalnız süresi dolmuş/hiç almamış olanlar «geçerli» dışında kalır."""
    ensure(engine)
    d0 = on or today()
    limit = d0 + timedelta(days=max(0, int(days or 0)))
    with engine.connect() as c:
        courses = c.execute(sa.select(COURSES).where(COURSES.c.tenant_id == tenant, COURSES.c.kind == "zorunlu",
                                                     COURSES.c.active.is_(True))).all()
        if not courses:
            return []
        emps = _employees(c, tenant, active_only=True)
        units = _units(c, tenant)
        certs = c.execute(sa.select(CERTIFICATES.c.employee_id, CERTIFICATES.c.course_id, CERTIFICATES.c.issued_on,
                                    CERTIFICATES.c.expires_on).where(
            CERTIFICATES.c.tenant_id == tenant, CERTIFICATES.c.verified_at.isnot(None),
            CERTIFICATES.c.course_id.in_([k.id for k in courses]))).all()
        planned = c.execute(sa.select(ENROLLMENTS.c.employee_id, SESSIONS.c.course_id, SESSIONS.c.starts_at, SESSIONS.c.id)
                            .join(SESSIONS, SESSIONS.c.id == ENROLLMENTS.c.session_id)
                            .where(ENROLLMENTS.c.tenant_id == tenant, SESSIONS.c.state == "planli",
                                   ENROLLMENTS.c.approval.in_(("bekliyor", "yonetici_onayladi", "onaylandi")))).all()
    best: dict[tuple[str, str], tuple[date, Optional[date]]] = {}
    for r in certs:
        key = (r.employee_id, r.course_id)
        exp = _d(r.expires_on)
        cur = best.get(key)
        # Süresiz belge her süreli belgeden «geç» sayılır; aynı bitişte en yeni belge.
        rank = (date.max if exp is None else exp, _d(r.issued_on))
        if cur is None or rank > ((date.max if cur[1] is None else cur[1]), cur[0]):
            best[key] = (_d(r.issued_on), exp)
    plan: dict[tuple[str, str], dict[str, Any]] = {}
    for r in planned:
        key = (r.employee_id, r.course_id)
        if key not in plan or aware(r.starts_at) < aware(plan[key]["at"]):
            plan[key] = {"at": r.starts_at, "sessionId": r.id}
    out = []
    for k in courses:
        req = set(load(k.required_units_json, []) or [])
        for e in emps.values():
            if req and e.unit_id not in req:
                continue
            if employee_ids is not None and e.id not in employee_ids:
                continue
            got = best.get((e.id, k.id))
            if got is None:
                status, exp, issued = "hic_yok", None, None
            else:
                issued, exp = got
                status = "gecerli" if exp is None else ("doldu" if exp < d0 else ("dolacak" if exp < limit else "gecerli"))
            p = plan.get((e.id, k.id))
            out.append({"employeeId": e.id, "displayName": e.display_name, "unitId": e.unit_id,
                        "unitName": units.get(e.unit_id or "") or None, "courseId": k.id, "courseTitle": k.title,
                        "issuedOn": iso(issued), "expiresOn": iso(exp), "status": status, "statusLabel": STATUS[status],
                        "daysLeft": (exp - d0).days if exp is not None else None,
                        "plannedAt": iso(p["at"]) if p else None, "plannedSessionId": p["sessionId"] if p else None})
    order = {"doldu": 0, "hic_yok": 1, "dolacak": 2, "gecerli": 3}
    out.sort(key=lambda x: (order[x["status"]], x["expiresOn"] or "", x["courseTitle"].casefold(), x["displayName"].casefold()))
    return out


# ------------------------------------------------------------------ pano


def dashboard(engine: sa.engine.Engine, tenant: str, *, alert_days: Optional[int], people: bool) -> dict[str, Any]:
    """Sayaçlar ve birim × eğitim tamamlanma. Tamamlanma = iptal edilmemiş oturumlardaki onaylı katılımlardan
    tamamlanan payı (kabul betiği aynı tanımı bağımsız SQL ile sınar). `people` yoksa kişi listesi dönmez."""
    ensure(engine)
    d0 = today()
    status = mandatory_status(engine, tenant, days=alert_days or 0, on=d0)
    month_start = datetime(d0.year, d0.month, 1, tzinfo=TZ)
    month_end = datetime(d0.year + (d0.month == 12), d0.month % 12 + 1, 1, tzinfo=TZ)
    with engine.connect() as c:
        sessions = c.execute(sa.select(SESSIONS.c.id, SESSIONS.c.state, SESSIONS.c.starts_at, SESSIONS.c.course_id)
                             .where(SESSIONS.c.tenant_id == tenant)).all()
        live = {s.id: s for s in sessions if s.state != "iptal"}
        enr = c.execute(sa.select(ENROLLMENTS.c.session_id, ENROLLMENTS.c.employee_id, ENROLLMENTS.c.approval,
                                  ENROLLMENTS.c.completed_at).where(ENROLLMENTS.c.tenant_id == tenant)).all()
        emps = _employees(c, tenant)
        units = _units(c, tenant)
        courses = {r.id: r for r in c.execute(sa.select(COURSES).where(COURSES.c.tenant_id == tenant)).all()}
        tokens = c.execute(sa.select(sa.func.count()).where(FEEDBACK_TOKENS.c.tenant_id == tenant,
                                                            FEEDBACK_TOKENS.c.used_on.is_(None))).scalar() or 0
        unverified = c.execute(sa.select(sa.func.count()).where(CERTIFICATES.c.tenant_id == tenant,
                                                                CERTIFICATES.c.verified_at.is_(None))).scalar() or 0
        open_needs = c.execute(sa.select(sa.func.count()).where(NEEDS.c.tenant_id == tenant, NEEDS.c.state == "acik")).scalar() or 0
    cells: dict[tuple[str, str], list[int]] = {}
    total = completed = 0
    pending = 0
    for r in enr:
        if r.approval in ("bekliyor", "yonetici_onayladi") and r.session_id in live and live[r.session_id].state == "planli":
            pending += 1
        if r.approval != "onaylandi" or r.session_id not in live:
            continue
        e = emps.get(r.employee_id)
        unit = (e.unit_id if e is not None else None) or "-"
        key = (unit, live[r.session_id].course_id)
        cell = cells.setdefault(key, [0, 0])
        cell[0] += 1
        total += 1
        if r.completed_at is not None:
            cell[1] += 1
            completed += 1
    matrix = [{"unitId": None if u == "-" else u, "unitName": units.get(u) or ("Birimi girilmemiş" if u == "-" else u),
               "courseId": k, "courseTitle": courses[k].title if k in courses else "", "enrolled": v[0], "completed": v[1],
               "rate": round(v[1] / v[0], 4) if v[0] else None} for (u, k), v in cells.items()]
    matrix.sort(key=lambda x: (x["unitName"].casefold(), x["courseTitle"].casefold()))
    counters = {
        "overdue": sum(1 for s in status if s["status"] == "doldu"),
        "never": sum(1 for s in status if s["status"] == "hic_yok"),
        "expiring": sum(1 for s in status if s["status"] == "dolacak") if alert_days else None,
        "alertDays": alert_days,
        "sessionsThisMonth": sum(1 for s in sessions if s.state == "planli" and month_start <= aware(s.starts_at) < month_end),
        "awaitingClose": sum(1 for s in sessions if s.state == "planli" and aware(s.starts_at) < now()),
        "completionRate": round(completed / total, 4) if total else None,
        "enrolled": total, "completed": completed,
        "pendingFeedback": int(tokens), "pendingApprovals": pending, "unverifiedCertificates": int(unverified),
        "openNeeds": int(open_needs),
    }
    by_unit: dict[str, dict[str, Any]] = {}
    for s in status:
        if s["status"] == "gecerli":
            continue
        u = by_unit.setdefault(s["unitId"] or "-", {"unitId": s["unitId"], "unitName": s["unitName"] or "Birimi girilmemiş",
                                                     "doldu": 0, "hic_yok": 0, "dolacak": 0})
        u[s["status"]] += 1
    out = {"counters": counters, "matrix": matrix, "attentionByUnit": sorted(by_unit.values(), key=lambda x: x["unitName"].casefold())}
    if people:
        out["attention"] = [s for s in status if s["status"] != "gecerli"]
    return out


# ------------------------------------------------------------------ Eğitimlerim ve ekip


def me(engine: sa.engine.Engine, tenant: str, user: str, alert_days: Optional[int]) -> dict[str, Any]:
    """Kişinin kendi eğitimleri; çalışan kaydı yoksa boş (ekran bunu söyler)."""
    ensure(engine)
    emp = H.employee_by_username(engine, tenant, user)
    if emp is None:
        return {"employee": None, "enrollments": [], "certificates": [], "mandatory": [], "feedback": [], "openSessions": [],
                "needs": []}
    eid = emp["id"]
    with engine.connect() as c:
        courses = {r.id: r for r in c.execute(sa.select(COURSES).where(COURSES.c.tenant_id == tenant)).all()}
        rows = c.execute(sa.select(ENROLLMENTS, SESSIONS.c.starts_at, SESSIONS.c.ends_at, SESSIONS.c.location,
                                   SESSIONS.c.state.label("session_state"), SESSIONS.c.course_id, SESSIONS.c.trainer)
                         .join(SESSIONS, SESSIONS.c.id == ENROLLMENTS.c.session_id)
                         .where(ENROLLMENTS.c.tenant_id == tenant, ENROLLMENTS.c.employee_id == eid)
                         .order_by(SESSIONS.c.starts_at.desc())).all()
        tokens = c.execute(sa.select(FEEDBACK_TOKENS.c.token, FEEDBACK_TOKENS.c.session_id, SESSIONS.c.starts_at, SESSIONS.c.course_id)
                           .join(SESSIONS, SESSIONS.c.id == FEEDBACK_TOKENS.c.session_id)
                           .where(FEEDBACK_TOKENS.c.tenant_id == tenant, FEEDBACK_TOKENS.c.employee_id == eid,
                                  FEEDBACK_TOKENS.c.used_on.is_(None))).all()
        mine = {r.session_id for r in rows}
        upcoming = c.execute(sa.select(SESSIONS).where(SESSIONS.c.tenant_id == tenant, SESSIONS.c.state == "planli",
                                                       SESSIONS.c.starts_at >= now()).order_by(SESSIONS.c.starts_at)).all()
        needs = c.execute(sa.select(NEEDS).where(NEEDS.c.tenant_id == tenant, NEEDS.c.employee_id == eid)
                          .order_by(NEEDS.c.created_at.desc())).all()
    enrollments = [{"id": r.id, "sessionId": r.session_id, "courseId": r.course_id,
                    "courseTitle": courses[r.course_id].title if r.course_id in courses else "",
                    "startsAt": iso(r.starts_at), "endsAt": iso(r.ends_at), "location": r.location or "", "trainer": r.trainer or "",
                    "sessionState": r.session_state, "approval": r.approval, "approvalLabel": APPROVAL.get(r.approval, r.approval),
                    "attendance": r.attendance, "completedAt": iso(r.completed_at)} for r in rows]
    return {
        "employee": {"id": eid, "displayName": emp["displayName"], "unitName": emp["unitName"]},
        "enrollments": enrollments,
        "certificates": list_certificates(engine, tenant, employee_id=eid),
        "mandatory": mandatory_status(engine, tenant, days=alert_days or 0, employee_ids={eid}),
        "feedback": [{"token": t.token, "sessionId": t.session_id, "startsAt": iso(t.starts_at),
                      "courseTitle": courses[t.course_id].title if t.course_id in courses else ""} for t in tokens],
        "openSessions": [{"id": s.id, "courseId": s.course_id, "courseTitle": courses[s.course_id].title if s.course_id in courses else "",
                          "delivery": courses[s.course_id].delivery if s.course_id in courses else None,
                          "startsAt": iso(s.starts_at), "location": s.location or ""}
                         for s in upcoming if s.id not in mine and s.course_id in courses and courses[s.course_id].active],
        "needs": [_need_out(n, courses, None, None) for n in needs],
    }


def team(engine: sa.engine.Engine, tenant: str, user: str, alert_days: Optional[int]) -> dict[str, Any]:
    """Yöneticinin ekibi: zorunlu eğitim durumu ve onay bekleyen katılımlar. Portal kullanımı burada YOK."""
    my_id, ids = managed_employee_ids(engine, tenant, user)
    if my_id is None:
        return {"members": [], "pending": [], "mandatory": [], "managerKnown": False}
    with engine.connect() as c:
        emps, units = _employees(c, tenant), _units(c, tenant)
        rows = c.execute(sa.select(ENROLLMENTS).where(ENROLLMENTS.c.tenant_id == tenant,
                                                      ENROLLMENTS.c.employee_id.in_(sorted(ids) or ["-"]),
                                                      ENROLLMENTS.c.approval == "bekliyor")).all()
        sessions = {s.id: s for s in c.execute(sa.select(SESSIONS).where(SESSIONS.c.tenant_id == tenant)).all()}
        courses = {k.id: k for k in c.execute(sa.select(COURSES).where(COURSES.c.tenant_id == tenant)).all()}
        done = dict(c.execute(sa.select(ENROLLMENTS.c.employee_id, sa.func.count()).where(
            ENROLLMENTS.c.tenant_id == tenant, ENROLLMENTS.c.employee_id.in_(sorted(ids) or ["-"]),
            ENROLLMENTS.c.completed_at.isnot(None)).group_by(ENROLLMENTS.c.employee_id)).all())
    pending = []
    for r in rows:
        s = sessions.get(r.session_id)
        if s is None or s.state != "planli":
            continue
        k = courses.get(s.course_id)
        pending.append({**_enr_out(r, emps, units), "courseTitle": k.title if k is not None else "",
                        "delivery": k.delivery if k is not None else None, "startsAt": iso(s.starts_at)})
    status = mandatory_status(engine, tenant, days=alert_days or 0, employee_ids=ids)
    members = []
    for eid in ids:
        e = emps.get(eid)
        if e is None:
            continue
        mine = [s for s in status if s["employeeId"] == eid]
        members.append({**_emp_brief(e, units), "completed": int(done.get(eid, 0)),
                        "overdue": sum(1 for s in mine if s["status"] in ("doldu", "hic_yok")),
                        "expiring": sum(1 for s in mine if s["status"] == "dolacak")})
    members.sort(key=lambda x: x["displayName"].casefold())
    return {"members": members, "pending": pending, "mandatory": [s for s in status if s["status"] != "gecerli"],
            "managerKnown": True}


# ------------------------------------------------------------------ eğitim ihtiyaçları


def _need_out(r: Any, courses: dict[str, Any], emps: Optional[dict[str, Any]], units: Optional[dict[str, str]]) -> dict[str, Any]:
    sug = courses.get(r.suggested_course_id or "")
    chosen = courses.get(r.course_id or "")
    out = {"id": r.id, "source": r.source, "sourceLabel": NEED_SOURCES.get(r.source, r.source), "text": r.text,
           "suggestedCourseId": r.suggested_course_id, "suggestedCourseTitle": sug.title if sug is not None else None,
           "suggestionReason": r.suggestion_reason or "", "suggestion": load(r.suggestion_json),
           "priority": r.priority, "priorityLabel": PRIORITIES.get(r.priority or "", None), "state": r.state,
           "stateLabel": NEED_STATES.get(r.state, r.state), "courseId": r.course_id,
           "courseTitle": chosen.title if chosen is not None else None, "decidedBy": r.decided_by,
           "decidedAt": iso(r.decided_at), "decisionNote": r.decision_note or "", "createdAt": iso(r.created_at),
           "unitId": r.unit_id}
    if emps is not None:
        e = emps.get(r.employee_id or "")
        out["employee"] = _emp_brief(e, units or {}) if e is not None else None
        out["unitName"] = (units or {}).get(r.unit_id or "") or ((units or {}).get(e.unit_id or "") if e is not None else None)
    return out


def list_needs(engine: sa.engine.Engine, tenant: str, *, state: str = "", people: bool = True) -> dict[str, Any]:
    """İhtiyaçlar ve eğitim başına öncelik özeti (açık + onaylı ihtiyaç sayısı, önceliğe göre)."""
    ensure(engine)
    q = sa.select(NEEDS).where(NEEDS.c.tenant_id == tenant)
    if state in NEED_STATES:
        q = q.where(NEEDS.c.state == state)
    with engine.connect() as c:
        rows = c.execute(q.order_by(NEEDS.c.created_at.desc())).all()
        courses = {k.id: k for k in c.execute(sa.select(COURSES).where(COURSES.c.tenant_id == tenant)).all()}
        emps, units = _employees(c, tenant), _units(c, tenant)
    items = [_need_out(r, courses, emps if people else None, units if people else None) for r in rows]
    if not people:
        for it in items:
            it.pop("text", None)
    summary: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r.state not in ("acik", "onaylandi"):
            continue
        cid = r.course_id or r.suggested_course_id or "-"
        s = summary.setdefault(cid, {"courseId": None if cid == "-" else cid,
                                     "courseTitle": courses[cid].title if cid in courses else "Katalogda karşılığı yok",
                                     "total": 0, "yuksek": 0, "orta": 0, "dusuk": 0, "belirsiz": 0})
        s["total"] += 1
        s[r.priority if r.priority in PRIORITIES else "belirsiz"] += 1
    ranked = sorted(summary.values(), key=lambda x: (-x["yuksek"], -x["total"], x["courseTitle"].casefold()))
    return {"items": items, "summary": ranked}


def add_need(engine: sa.engine.Engine, tenant: str, actor: str, body: dict[str, Any], *, source: str,
             employee_id: Optional[str]) -> dict[str, Any]:
    ensure(engine)
    if source not in NEED_SOURCES:
        raise HrError("İhtiyacın kaynağı geçersiz.")
    text = str(body.get("text") or "").strip()[:2000]
    if len(text) < 5:
        raise HrError("İhtiyacı bir cümleyle yazın.")
    unit_id = str(body.get("unitId") or "") or None
    with engine.begin() as c:
        if employee_id and c.execute(sa.select(H.EMPLOYEES.c.id).where(H.EMPLOYEES.c.id == employee_id,
                                                                       H.EMPLOYEES.c.tenant_id == tenant)).first() is None:
            raise HrError("Çalışan kaydı bulunamadı.", 404)
        if unit_id and unit_id not in _units(c, tenant):
            raise HrError("Birim bulunamadı.", 404)
        if not employee_id and not unit_id:
            raise HrError("İhtiyacın kime ya da hangi birime ait olduğunu seçin.")
        nid = new_id("iht")
        c.execute(NEEDS.insert().values(id=nid, tenant_id=tenant, employee_id=employee_id, unit_id=unit_id, source=source,
                                        text=text, state="acik", created_by=actor, created_at=now()))
        courses = {k.id: k for k in c.execute(sa.select(COURSES).where(COURSES.c.tenant_id == tenant)).all()}
        return _need_out(c.execute(sa.select(NEEDS).where(NEEDS.c.id == nid)).first(), courses, None, None)


def decide_need(engine: sa.engine.Engine, tenant: str, actor: str, nid: str, body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    ensure(engine)
    state = str(body.get("state") or "")
    if state not in ("onaylandi", "reddedildi", "karsilandi", "acik"):
        raise HrError("Karar «onaylandi», «reddedildi», «karsilandi» ya da «acik» olmalı.")
    prio = body.get("priority")
    if prio not in (None, "") and prio not in PRIORITIES:
        raise HrError("Öncelik «yuksek», «orta» ya da «dusuk» olmalı.")
    with engine.begin() as c:
        r = c.execute(sa.select(NEEDS).where(NEEDS.c.id == nid, NEEDS.c.tenant_id == tenant)).first()
        if r is None:
            raise HrError("İhtiyaç kaydı bulunamadı.", 404)
        course_id = body.get("courseId", r.course_id if r.course_id else r.suggested_course_id) or None
        if course_id and c.execute(sa.select(COURSES.c.id).where(COURSES.c.id == course_id, COURSES.c.tenant_id == tenant)).first() is None:
            raise HrError("Eğitim kartı bulunamadı.", 404)
        vals = {"state": state, "course_id": course_id if state != "reddedildi" else r.course_id,
                "priority": prio or r.priority, "decided_by": actor, "decided_at": now(),
                "decision_note": clean(body.get("note"), 500) or None}
        diff = {k: {"once": getattr(r, k), "sonra": v} for k, v in vals.items() if k in ("state", "course_id", "priority") and getattr(r, k) != v}
        c.execute(NEEDS.update().where(NEEDS.c.id == nid).values(**vals))
        courses = {k.id: k for k in c.execute(sa.select(COURSES).where(COURSES.c.tenant_id == tenant)).all()}
        return _need_out(c.execute(sa.select(NEEDS).where(NEEDS.c.id == nid)).first(), courses, None, None), diff


NO_MATCH = "Katalogda uygun eğitim yok"
PRIORITY_CHOICES = ["Yüksek", "Orta", "Düşük"]
_PRIO_KEY = {"Yüksek": "yuksek", "Orta": "orta", "Düşük": "dusuk"}
NEED_SYSTEM = ("Sen bir yayınevinin eğitim ve gelişim uzmanısın. Sana bir çalışanın ya da birimin eğitim ihtiyacı "
               "(kişi adı yok) ve şirketin eğitim kataloğu verilir. Kişi hakkında yorum yapmazsın, yalnız ihtiyaç ile "
               "eğitim arasındaki bağı değerlendirirsin.")


def _mask(text: str) -> str:
    from semantic_bridge import hr_recruit_text as X

    return X.rule_mask(text)[0]


def need_prompt(text: str, source_label: str) -> str:
    return f"Eğitim ihtiyacı ({source_label}):\n{_mask(text)[:1500]}\n\nBu ihtiyacı en iyi karşılayan katalogdaki eğitim hangisi?"


def suggest_need(need: dict[str, Any], courses: list[dict[str, Any]], choose: Callable[..., Any],
                 chat: Callable[[list[dict[str, str]]], str]) -> dict[str, Any]:
    """Bir ihtiyaç için eğitim seçimi (kapalı küme, olasılıkla), öncelik önerisi ve tek cümlelik gerekçe.
    Girdi yalnız ihtiyaç metni (maskeli), kaynak türü ve katalog; kişi bilgisi yok."""
    titles: list[str] = []
    ids: list[str] = []
    for k in courses:
        label = f"{k['title']} ({k['kindLabel']}, {k['deliveryLabel']})"
        if label in titles:
            label = f"{label} #{len(titles) + 1}"
        titles.append(label)
        ids.append(k["id"])
    pick = choose(need_prompt(need["text"], need["sourceLabel"]), titles + [NO_MATCH], system=NEED_SYSTEM)
    course_id = ids[pick.index] if pick.choice is not None and pick.index is not None and pick.index < len(ids) else None
    prio = choose(f"Eğitim ihtiyacı ({need['sourceLabel']}):\n{_mask(need['text'])[:1500]}\n\n"
                  "Bu ihtiyacın işe etkisine göre önceliği nedir?", PRIORITY_CHOICES, system=NEED_SYSTEM)
    chosen = titles[pick.index] if course_id else NO_MATCH
    reason = (chat([{"role": "system", "content": NEED_SYSTEM + " Tek cümle, en çok 35 kelime yaz. Rakam uydurma."},
                    {"role": "user", "content": f"{need_prompt(need['text'], need['sourceLabel'])}\n\nSeçilen: {chosen}\n"
                                                f"Öncelik: {prio.choice or 'belirsiz'}\nBu eşleşmenin gerekçesini yaz."}]) or "").strip()
    return {"courseId": course_id, "priority": _PRIO_KEY.get(prio.choice or ""), "reason": " ".join(reason.split())[:400],
            "probs": {"egitim": pick.probability, "oncelik": prio.probability, "method": pick.method}}


def apply_suggestion(engine: sa.engine.Engine, tenant: str, nid: str, s: dict[str, Any]) -> None:
    with engine.begin() as c:
        c.execute(NEEDS.update().where(NEEDS.c.id == nid, NEEDS.c.tenant_id == tenant, NEEDS.c.state == "acik").values(
            suggested_course_id=s["courseId"], suggestion_reason=s["reason"] or None, suggestion_json=dump(s["probs"]),
            priority=s["priority"]))


# ------------------------------------------------------------------ geri bildirim (anonim)


def feedback_form(engine: sa.engine.Engine, tenant: str, token: str, employee_id: str) -> dict[str, Any]:
    ensure(engine)
    with engine.connect() as c:
        t = c.execute(sa.select(FEEDBACK_TOKENS).where(FEEDBACK_TOKENS.c.token == token, FEEDBACK_TOKENS.c.tenant_id == tenant)).first()
        if t is None or t.employee_id != employee_id:
            raise HrError("Anket bağlantısı geçersiz.", 404)
        s = c.execute(sa.select(SESSIONS).where(SESSIONS.c.id == t.session_id)).first()
        k = c.execute(sa.select(COURSES).where(COURSES.c.id == s.course_id)).first() if s is not None else None
    return {"used": t.used_on is not None, "courseTitle": k.title if k is not None else "", "startsAt": iso(s.starts_at) if s else None,
            "questions": QUESTIONS,
            "note": "Yanıtınız adınız olmadan kaydedilir; İK yalnız ortalamaları ve yorumların özetini görür."}


def submit_feedback(engine: sa.engine.Engine, tenant: str, token: str, employee_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Tek kullanımlık jetonla yanıt. Yanıt satırında kişi yok; jeton «kullanıldı» diye (gün düzeyinde) işaretlenir.
    İkinci gönderim 409."""
    ensure(engine)
    answers: dict[str, int] = {}
    for q in QUESTIONS:
        v = (body.get("answers") or {}).get(q["key"])
        if v in (None, ""):
            continue
        try:
            n = int(v)
        except (TypeError, ValueError):
            raise HrError("Puanlar 1 ile 5 arasında olmalı.") from None
        if not 1 <= n <= 5:
            raise HrError("Puanlar 1 ile 5 arasında olmalı.")
        answers[q["key"]] = n
    comment = str(body.get("comment") or "").strip()[:2000] or None
    if not answers and not comment:
        raise HrError("En az bir soruyu yanıtlayın.")
    day = today()
    with engine.begin() as c:
        t = c.execute(sa.select(FEEDBACK_TOKENS).where(FEEDBACK_TOKENS.c.token == token, FEEDBACK_TOKENS.c.tenant_id == tenant)).first()
        if t is None or t.employee_id != employee_id:
            raise HrError("Anket bağlantısı geçersiz.", 404)
        res = c.execute(FEEDBACK_TOKENS.update().where(FEEDBACK_TOKENS.c.token == token, FEEDBACK_TOKENS.c.used_on.is_(None))
                        .values(used_on=day))
        if res.rowcount != 1:
            raise HrError("Bu anket zaten yanıtlandı.", 409)
        c.execute(FEEDBACK.insert().values(id=new_id("gb"), tenant_id=tenant, session_id=t.session_id, submitted_on=day,
                                           answers_json=dump(answers), comment=comment))
    return {"ok": True}


def feedback_summary(engine: sa.engine.Engine, tenant: str, sid: str, min_group: Optional[int]) -> dict[str, Any]:
    """Ortalama puanlar (SQL'den) ve yorumlar (kural maskesiyle). Eşik girildiyse ve yanıt eşiğin altındaysa gizli."""
    ensure(engine)
    with engine.connect() as c:
        s = c.execute(sa.select(SESSIONS).where(SESSIONS.c.id == sid, SESSIONS.c.tenant_id == tenant)).first()
        if s is None:
            raise HrError("Oturum bulunamadı.", 404)
        rows = c.execute(sa.select(FEEDBACK.c.answers_json, FEEDBACK.c.comment).where(FEEDBACK.c.session_id == sid)).all()
        invited = c.execute(sa.select(sa.func.count()).where(FEEDBACK_TOKENS.c.session_id == sid)).scalar() or 0
    n = len(rows)
    hidden = bool(min_group) and n < int(min_group or 0)
    out: dict[str, Any] = {"responses": n, "invited": int(invited), "minGroup": min_group, "hidden": hidden,
                           "questions": QUESTIONS, "averages": {}, "comments": [], "themes": load(s.feedback_summary_json)}
    if hidden:
        out["themes"] = None
        return out
    sums: dict[str, list[int]] = {}
    comments = []
    for r in rows:
        for k, v in (load(r.answers_json, {}) or {}).items():
            sums.setdefault(k, []).append(int(v))
        if r.comment:
            comments.append(_mask(r.comment))
    out["averages"] = {k: {"avg": round(sum(v) / len(v), 2), "n": len(v)} for k, v in sums.items()}
    comments.sort()
    out["comments"] = comments
    return out


THEME_SYSTEM = ("Sen bir eğitim değerlendirme uzmanısın. Anonim katılımcı yorumlarını okursun. Kişiyi ele verecek "
                "ayrıntı (ad, birim, olay) yazmazsın.")


def feedback_themes(comments: list[str], choose: Callable[..., Any], chat: Callable[[list[dict[str, str]]], str]) -> dict[str, Any]:
    """Her yorum kapalı tema listesinden birine (olasılıkla); tema başına kısa özet. Yorumlar zaten maskeli gelir."""
    counts: dict[str, list[str]] = {}
    for text in comments:
        r = choose(f"Eğitim sonrası anonim yorum:\n{text[:1200]}\n\nBu yorumun ana teması hangisi?", THEMES, system=THEME_SYSTEM)
        counts.setdefault(r.choice or "Diğer", []).append(text)
    themes = []
    for theme, items in sorted(counts.items(), key=lambda x: -len(x[1])):
        joined = "\n".join(f"- {x[:400]}" for x in items)
        summary = (chat([{"role": "system", "content": THEME_SYSTEM + " En çok iki cümle, Türkçe yaz. Rakam yazma."},
                         {"role": "user", "content": f"Tema: {theme}\nYorumlar:\n{joined}\n\nOrtak noktayı özetle."}]) or "").strip()
        themes.append({"theme": theme, "count": len(items), "summary": " ".join(summary.split())[:500]})
    return {"themes": themes, "at": iso(now())}


def store_themes(engine: sa.engine.Engine, tenant: str, sid: str, data: dict[str, Any]) -> None:
    with engine.begin() as c:
        c.execute(SESSIONS.update().where(SESSIONS.c.id == sid, SESSIONS.c.tenant_id == tenant).values(feedback_summary_json=dump(data)))


# ------------------------------------------------------------------ modül rehberleri


def _guide_out(r: Any, votes: Optional[dict[str, dict[str, int]]] = None, *, reader: bool = False) -> dict[str, Any]:
    v = (votes or {}).get(r.id, {"useful": 0, "notUseful": 0})
    if reader:
        return {"id": r.id, "moduleRoute": r.module_route, "title": r.published_title or r.title,
                "body": r.published_body or "", "version": r.version, "approvedAt": iso(r.approved_at)}
    return {"id": r.id, "moduleRoute": r.module_route, "title": r.title, "body": r.body_md, "version": r.version,
            "state": r.state, "stateLabel": GUIDE_STATES.get(r.state, r.state), "published": bool(r.published_body),
            "dirty": bool(r.published_body) and (r.published_body != r.body_md or (r.published_title or "") != r.title),
            "modelDrafted": bool(r.model_drafted), "approvedBy": r.approved_by, "approvedAt": iso(r.approved_at),
            "updatedBy": r.updated_by, "updatedAt": iso(r.updated_at), "votes": v}


def _votes(c: Any, tenant: str) -> dict[str, dict[str, int]]:
    """Yalnız yayımlı sürüme verilen oylar sayılır (sürüm değişince yeniden oylanır)."""
    out: dict[str, dict[str, int]] = {}
    rows = c.execute(sa.select(GUIDE_VOTES.c.guide_id, GUIDE_VOTES.c.useful, sa.func.count())
                     .join(GUIDES, sa.and_(GUIDES.c.id == GUIDE_VOTES.c.guide_id, GUIDES.c.version == GUIDE_VOTES.c.version))
                     .where(GUIDE_VOTES.c.tenant_id == tenant).group_by(GUIDE_VOTES.c.guide_id, GUIDE_VOTES.c.useful)).all()
    for gid, useful, n in rows:
        d = out.setdefault(gid, {"useful": 0, "notUseful": 0})
        d["useful" if useful else "notUseful"] += int(n)
    return out


def list_guides(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    ensure(engine)
    with engine.connect() as c:
        rows = c.execute(sa.select(GUIDES).where(GUIDES.c.tenant_id == tenant).order_by(GUIDES.c.module_route)).all()
        votes = _votes(c, tenant)
    return [_guide_out(r, votes) for r in rows]


def published_index(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    """Yayımlı rehberlerin listesi (ekranın «Bu ekran nasıl kullanılır» bağlantısı)."""
    ensure(engine)
    with engine.connect() as c:
        rows = c.execute(sa.select(GUIDES.c.id, GUIDES.c.module_route, GUIDES.c.published_title, GUIDES.c.version)
                         .where(GUIDES.c.tenant_id == tenant, GUIDES.c.published_body.isnot(None))).all()
    return [{"id": r.id, "moduleRoute": r.module_route, "title": r.published_title, "version": r.version} for r in rows]


def read_guide(engine: sa.engine.Engine, tenant: str, gid: str, user: str) -> dict[str, Any]:
    ensure(engine)
    with engine.connect() as c:
        r = c.execute(sa.select(GUIDES).where(GUIDES.c.id == gid, GUIDES.c.tenant_id == tenant)).first()
        if r is None or not r.published_body:
            raise HrError("Rehber bulunamadı.", 404)
        mine = c.execute(sa.select(GUIDE_VOTES.c.useful, GUIDE_VOTES.c.version).where(
            GUIDE_VOTES.c.guide_id == gid, GUIDE_VOTES.c.username == user)).first()
    out = _guide_out(r, reader=True)
    out["myVote"] = None if mine is None or mine.version != r.version else bool(mine.useful)
    return out


def check_guide_text(title: str, body: str) -> None:
    hit = _TECH.search(f"{title}\n{body}")
    if hit:
        raise HrError(f"Rehber metninde altyapı adı geçiyor («{hit.group(0)}»); ekranda yalnız «Zeki AI» ya da işlev adı yazılır.")


def save_guide(engine: sa.engine.Engine, tenant: str, actor: str, body: dict[str, Any], gid: Optional[str] = None,
               *, model_drafted: bool = False) -> dict[str, Any]:
    ensure(engine)
    title = clean(body.get("title"), 200)
    text = str(body.get("body") or "").strip()[:20000]
    route = clean(body.get("moduleRoute"), 80).lower()
    t = now()
    with engine.begin() as c:
        if gid:
            r = c.execute(sa.select(GUIDES).where(GUIDES.c.id == gid, GUIDES.c.tenant_id == tenant)).first()
            if r is None:
                raise HrError("Rehber bulunamadı.", 404)
            vals = {"title": title or r.title, "body_md": text or r.body_md, "state": "taslak", "updated_by": actor, "updated_at": t}
            if model_drafted:
                vals["model_drafted"] = True
            c.execute(GUIDES.update().where(GUIDES.c.id == gid).values(**vals))
        else:
            if not _ROUTE.match(route or ""):
                raise HrError("Rehberin ait olduğu ekranı seçin.")
            if not title or not text:
                raise HrError("Başlık ve metin boş olamaz.")
            if c.execute(sa.select(GUIDES.c.id).where(GUIDES.c.tenant_id == tenant, GUIDES.c.module_route == route)).first():
                raise HrError("Bu ekranın rehberi zaten var; onu düzenleyin.", 409)
            gid = new_id("rhb")
            c.execute(GUIDES.insert().values(id=gid, tenant_id=tenant, module_route=route, title=title, body_md=text, version=0,
                                             state="taslak", model_drafted=model_drafted, updated_by=actor, updated_at=t))
        r = c.execute(sa.select(GUIDES).where(GUIDES.c.id == gid)).first()
        return _guide_out(r, _votes(c, tenant))


def publish_guide(engine: sa.engine.Engine, tenant: str, actor: str, gid: str) -> dict[str, Any]:
    ensure(engine)
    with engine.begin() as c:
        r = c.execute(sa.select(GUIDES).where(GUIDES.c.id == gid, GUIDES.c.tenant_id == tenant)).first()
        if r is None:
            raise HrError("Rehber bulunamadı.", 404)
        check_guide_text(r.title, r.body_md)
        if r.published_body == r.body_md and (r.published_title or "") == r.title:
            raise HrError("Yayımdaki sürümle aynı; değişiklik yok.", 409)
        c.execute(GUIDES.update().where(GUIDES.c.id == gid).values(
            published_body=r.body_md, published_title=r.title, version=int(r.version or 0) + 1, state="yayinda",
            approved_by=actor, approved_at=now()))
        return _guide_out(c.execute(sa.select(GUIDES).where(GUIDES.c.id == gid)).first(), _votes(c, tenant))


def unpublish_guide(engine: sa.engine.Engine, tenant: str, gid: str) -> None:
    with engine.begin() as c:
        n = c.execute(GUIDES.update().where(GUIDES.c.id == gid, GUIDES.c.tenant_id == tenant)
                      .values(published_body=None, published_title=None, state="taslak")).rowcount
    if not n:
        raise HrError("Rehber bulunamadı.", 404)


def vote_guide(engine: sa.engine.Engine, tenant: str, user: str, gid: str, useful: bool) -> dict[str, Any]:
    ensure(engine)
    with engine.begin() as c:
        r = c.execute(sa.select(GUIDES.c.version, GUIDES.c.published_body).where(GUIDES.c.id == gid, GUIDES.c.tenant_id == tenant)).first()
        if r is None or not r.published_body:
            raise HrError("Rehber bulunamadı.", 404)
        c.execute(GUIDE_VOTES.delete().where(GUIDE_VOTES.c.guide_id == gid, GUIDE_VOTES.c.username == user))
        c.execute(GUIDE_VOTES.insert().values(guide_id=gid, username=user, tenant_id=tenant, version=r.version,
                                              useful=bool(useful), at=now()))
    return {"ok": True, "useful": bool(useful)}


GUIDE_SYSTEM = ("Sen bir kurumsal portalın eğitim içeriği yazarısın. Verilen ekran tanımından çalışanlar için kısa, adım "
                "adım bir kullanım rehberi yazarsın. Türkçe, sade, «siz» diliyle. Başlıklar için «## », adımlar için "
                "numaralı liste kullan. En çok 250 kelime. Yazılımın altyapısından, model ya da ürün adından söz etme; "
                "yapay zekâ özelliği varsa yalnız «Zeki AI» de. Ekranda olmayan bir düğme ya da özellik uydurma; emin "
                "olmadığın adımı «ekranda … bölümüne bakın» diye genel yaz. Rakam uydurma.")


def guide_messages(module: dict[str, Any]) -> list[dict[str, str]]:
    kw = ", ".join(str(x) for x in (module.get("keywords") or [])[:20])
    notes = str(module.get("notes") or "").strip()[:2000]
    user = (f"Ekran: {clean(module.get('label'), 120)}\nÇalışma alanı: {clean(module.get('group'), 120)}\n"
            f"Kısa tanım: {clean(module.get('hint'), 400)}\nİlgili sözcükler: {kw}\n"
            + (f"Portal sorumlusunun notları:\n{notes}\n" if notes else "")
            + "\nBu ekranın yeni başlayanlar için rehberini yaz: ne işe yarar, en sık üç işlem nasıl yapılır, dikkat edilecekler.")
    return [{"role": "system", "content": GUIDE_SYSTEM}, {"role": "user", "content": user}]


# ------------------------------------------------------------------ kullanım sayacı


def record_visit(engine: sa.engine.Engine, tenant: str, user: str, route: str) -> None:
    """(gün, menü öğesi, hesap) satırını artırır. Hesap yalnız isteği yapanın kendisi."""
    ensure(engine)
    route = (route or "").strip().lower()
    if not _ROUTE.match(route):
        raise HrError("Geçersiz ekran kimliği.")
    u = (user or "").strip().lower()[:120]
    if not u:
        raise HrError("Oturum gerekli.", 401)
    d = today()
    key = (PAGE_VISITS.c.tenant_id == tenant) & (PAGE_VISITS.c.day == d) & (PAGE_VISITS.c.route_prefix == route) & (PAGE_VISITS.c.username == u)
    with engine.begin() as c:
        if c.execute(PAGE_VISITS.update().where(key).values(count=PAGE_VISITS.c.count + 1)).rowcount:
            return
    try:
        with engine.begin() as c:
            c.execute(PAGE_VISITS.insert().values(tenant_id=tenant, day=d, route_prefix=route, username=u, count=1))
    except sa.exc.IntegrityError:
        # Aynı anda iki sekme: öteki satırı açtı, bu istek sayacı artırır.
        with engine.begin() as c:
            c.execute(PAGE_VISITS.update().where(key).values(count=PAGE_VISITS.c.count + 1))


# ------------------------------------------------------------------ bütçe


def budget(engine: sa.engine.Engine, tenant: str, year: int) -> Optional[dict[str, Any]]:
    ensure(engine)
    with engine.connect() as c:
        r = c.execute(sa.select(BUDGETS).where(BUDGETS.c.tenant_id == tenant, BUDGETS.c.year == year)).first()
    return {"year": r.year, "amount": r.amount, "note": r.note or "", "updatedBy": r.updated_by, "updatedAt": iso(r.updated_at)} if r else None


def put_budget(engine: sa.engine.Engine, tenant: str, actor: str, year: int, body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    ensure(engine)
    if not 2000 <= int(year) <= 2100:
        raise HrError("Yıl geçersiz.")
    amount = _num(body.get("amount"), "Bütçe tutarı")
    if amount is None:
        raise HrError("Bütçe tutarını girin.")
    with engine.begin() as c:
        old = c.execute(sa.select(BUDGETS).where(BUDGETS.c.tenant_id == tenant, BUDGETS.c.year == year)).first()
        vals = dict(amount=float(amount), note=clean(body.get("note"), 500) or None, updated_by=actor, updated_at=now())
        if old is None:
            c.execute(BUDGETS.insert().values(tenant_id=tenant, year=year, **vals))
        else:
            c.execute(BUDGETS.update().where(BUDGETS.c.tenant_id == tenant, BUDGETS.c.year == year).values(**vals))
    return budget(engine, tenant, year), {"once": old.amount if old is not None else None, "sonra": float(amount)}


# ------------------------------------------------------------------ saklama ve imha (İK-0 bağları)


def due_departed(engine: sa.engine.Engine, tenant: str, t: datetime) -> list[str]:
    """Ayrılış tarihinden bu yana `egitim_kaydi` süresi dolmuş çalışanlar (eğitim kaydı olanlar)."""
    days = H.keep_days(engine, tenant, "egitim_kaydi")
    if not days:
        return []
    cutoff = t.astimezone(TZ).date() - timedelta(days=days)
    with engine.connect() as c:
        gone = set(c.execute(sa.select(H.EMPLOYEES.c.id).where(
            H.EMPLOYEES.c.tenant_id == tenant, H.EMPLOYEES.c.status == "ayrildi", H.EMPLOYEES.c.end_date.isnot(None),
            H.EMPLOYEES.c.end_date < cutoff)).scalars())
        if not gone:
            return []
        have: set[str] = set()
        for tbl in (ENROLLMENTS, CERTIFICATES, FEEDBACK_TOKENS, NEEDS):
            have |= set(c.execute(sa.select(tbl.c.employee_id).where(tbl.c.tenant_id == tenant,
                                                                     tbl.c.employee_id.in_(gone)).distinct()).scalars())
    return sorted(have)


def purge_departed(engine: sa.engine.Engine, tenant: str, ids: list[str], t: datetime) -> int:
    n = 0
    with engine.begin() as c:
        for tbl in (ENROLLMENTS, CERTIFICATES, FEEDBACK_TOKENS, NEEDS):
            c.execute(tbl.delete().where(tbl.c.tenant_id == tenant, tbl.c.employee_id.in_(ids)))
        n = len(ids)
    return n


def due_visits(engine: sa.engine.Engine, tenant: str, t: datetime) -> list[str]:
    """Silinecek ziyaret günleri (kimlik olarak gün; hesap adı tutanağa yazılmaz)."""
    days = H.keep_days(engine, tenant, "egitim_kullanim")
    if not days:
        return []
    cutoff = t.astimezone(TZ).date() - timedelta(days=days)
    ensure(engine)
    with engine.connect() as c:
        rows = c.execute(sa.select(PAGE_VISITS.c.day).where(PAGE_VISITS.c.tenant_id == tenant, PAGE_VISITS.c.day < cutoff).distinct()).scalars()
        return sorted(iso(_d(d)) for d in rows)


def purge_visits(engine: sa.engine.Engine, tenant: str, ids: list[str], t: datetime) -> int:
    days = [date.fromisoformat(x) for x in ids]
    with engine.begin() as c:
        return int(c.execute(PAGE_VISITS.delete().where(PAGE_VISITS.c.tenant_id == tenant, PAGE_VISITS.c.day.in_(days))).rowcount or 0)


def register_hooks() -> None:
    H.register_data_class("egitim_kaydi", "Ayrılan çalışanın eğitim kaydı",
                          "Katılım, sertifika (belgesiyle), ihtiyaç ve anket jetonu; süre ayrılış tarihinden sayılır")
    H.register_data_class("egitim_kullanim", "Portal kullanım sayacı",
                          "Eğitim ihtiyacı için günlük ekran ziyaret sayısı (gün, ekran, hesap); süre ziyaret gününden sayılır")
    H.register_purger(H.Purger("egitim_kaydi", "Ayrılan çalışanın eğitim kaydı", due_departed, purge_departed))
    H.register_purger(H.Purger("egitim_kullanim", "Portal kullanım sayacı (gün)", due_visits, purge_visits))
