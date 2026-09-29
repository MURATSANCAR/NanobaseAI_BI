"""H4 Kurumsal e-posta yönetimi (timas@timas.com.tr): depo, durum makinesi, SLA, kurallar, rapor, etiketleme.

**Akış.** Zamanlayıcı her 5 dakikada `run-due` çağırır: kutudan yeni iletiler okunur (`mailbox_sources`), gönderen CRM'de
tanınır, Zeki AI türü ve önceliği seçer (`mailbox_classify`, `QueuedLlm.choose`), yürürlükteki yönlendirme tablosundan
sorumlu önerilir. İnsan atar (K2); olasılığı yüksek ve yönetimin açtığı türlerde (`MAIL_AUTO_ASSIGN_CATEGORIES`, varsayılan
boş) atama kendiliğinden yapılır (K1). Kutudan gönderilen yanıt konu zincirinden okunur ve ileti «yanıtlandı» olur.
Saatlik `sla-due` iş saatleriyle SLA'yı sayar: hatırlatma (atanan), eskalasyon (birim yöneticisi), üst yönetici — iç
bildirim e-postası; dışarıya hiçbir şey gitmez.

**Durumlar.** yeni → atandi → yanitlandi → kapandi; her durumdan arsiv (spam/ilgisiz, geri alınır); kapandi/arsiv →
yeni ya da atandi (yeniden açma).

**Saklanmayan:** ileti gövdesi ve ekin kendisi (KVKK: gövde kutudan anlık okunur); gönderen adresi yalnız özet (SHA-256)
ve maskeli gösterimle tutulur. Saklanan: konu, 1–2 cümle Zeki özeti, tür, öncelik, durum, sorumlu, süreler, ek adları ve
boyutları, CRM kayıt kimlikleri.

**İş başvurusu (İK).** Türü `ik` rolündeki iletiler yalnız açıkça verilen `ozellik:eposta.ik` sahiplerine görünür;
yöneticiye istisna yoktur (portal yöneticisi de rolle almalıdır, kayıt altındadır). Aday kaydına dönüşüm M55'in
`POST /api/v1/hr/recruit/intake` ucuyla yapılır (uç yoksa ileti bekler).

**Dosya başvurusu.** Türü `basvuru` rolündeki iletiden yazar, eser adı, tür, sayfa çıkarılır (metinde birebir geçen);
«Yazar giriş sürecine aktar» M1'in `POST /api/v1/editorial/applications` ucuna kişinin kendi oturumuyla gider.

**Geçmiş iletiler.** `MAIL_START_DATE`'ten (yoksa ilk okumanın anından) önce gelenler «geçmiş» işaretlenir: listelere,
SLA'ya ve bildirimlere girmez; yalnız Etiketleme ekranında (doğruluk ölçümü) görünür.

**CRM'e, Logo'ya ve kutuya yazma yok.** Kutu yalnız okunur (gmail.readonly + gmail.labels).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

import sqlalchemy as sa

log = logging.getLogger("semantic.mailbox")
TZ = ZoneInfo("Europe/Istanbul")
_md = sa.MetaData()
_lock = threading.Lock()
_ready: set[int] = set()

MESSAGES = sa.Table(
    "semantic_mail_messages", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("provider", sa.String(12), nullable=False),              # gmail | graph | imap
    sa.Column("provider_id", sa.String(200), nullable=False),
    sa.Column("thread_id", sa.String(200)),
    sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("from_addr_hash", sa.String(64), nullable=False),         # sha256(küçük harf adres)
    sa.Column("from_display", sa.String(200)),                          # gönderen adı (başlıktaki)
    sa.Column("from_masked", sa.String(200)),                           # a***@ornek.com
    sa.Column("subject", sa.String(500)),
    sa.Column("summary", sa.Text),                                      # Zeki özeti (1–2 cümle, rakamsız)
    sa.Column("category", sa.String(40)),
    sa.Column("category_prob", sa.Float),
    sa.Column("category_margin", sa.Float),
    sa.Column("category_source", sa.String(10)),                        # model | kural | insan
    sa.Column("category_method", sa.String(12)),                        # logprobs | text | none | single
    sa.Column("model_category", sa.String(40)),                         # modelin ilk seçimi (doğruluk ölçümü; ezilmez)
    sa.Column("model_prob", sa.Float),
    sa.Column("unsure", sa.Boolean, nullable=False, default=False),
    sa.Column("priority", sa.String(10)),                               # yuksek | normal | dusuk
    sa.Column("priority_prob", sa.Float),
    sa.Column("status", sa.String(12), nullable=False),                 # yeni | atandi | yanitlandi | kapandi | arsiv
    sa.Column("assignee", sa.String(120)),
    sa.Column("unit", sa.String(120)),
    sa.Column("suggested_assignee", sa.String(120)),
    sa.Column("suggested_unit", sa.String(120)),
    sa.Column("due_at", sa.DateTime(timezone=True)),                    # ilk yanıt hedefi (hatırlatma eşiği)
    sa.Column("first_reply_at", sa.DateTime(timezone=True)),
    sa.Column("reply_checked_at", sa.DateTime(timezone=True)),
    sa.Column("closed_at", sa.DateTime(timezone=True)),
    sa.Column("crm_contact_id", sa.String(40)),
    sa.Column("crm_account_id", sa.String(40)),
    sa.Column("crm_lead_id", sa.String(40)),
    sa.Column("crm_project_id", sa.String(40)),
    sa.Column("crm_json", sa.Text),                                     # {kisi|firma|aday: {id, ad, proje}}
    sa.Column("is_hr", sa.Boolean, nullable=False, default=False),
    sa.Column("historical", sa.Boolean, nullable=False, default=False),
    sa.Column("labels_json", sa.Text),                                  # kutunun kendi etiketleri (SPAM, CATEGORY_…)
    sa.Column("attachments_json", sa.Text),                             # [{name, size, mime}] — yalnız ad ve boyut
    sa.Column("order_refs_json", sa.Text),                              # metindeki sipariş numaraları (desenle)
    sa.Column("classified_at", sa.DateTime(timezone=True)),
    sa.Column("remind_sent_at", sa.DateTime(timezone=True)),
    sa.Column("escalate_sent_at", sa.DateTime(timezone=True)),
    sa.Column("top_sent_at", sa.DateTime(timezone=True)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
    sa.UniqueConstraint("tenant_id", "provider", "provider_id", name="uq_semantic_mail_provider"),
    sa.Index("ix_semantic_mail_messages_list", "tenant_id", "historical", "status", "received_at"),
    sa.Index("ix_semantic_mail_messages_sender", "tenant_id", "from_addr_hash"),
)
EVENTS = sa.Table(
    "semantic_mail_events", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("message_id", sa.String(32), nullable=False, index=True),
    sa.Column("action", sa.String(24), nullable=False),
    sa.Column("by", sa.String(120), nullable=False),                    # kişi | zeki | kural | kutu | sistem
    sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("detail_json", sa.Text),
)
RULESETS = sa.Table(
    "semantic_mail_rulesets", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("version", sa.Integer, primary_key=True),
    sa.Column("status", sa.String(8), nullable=False),                  # taslak | onayli | arsiv
    sa.Column("note", sa.Text),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
    sa.Column("approved_by", sa.String(120)),
    sa.Column("approved_at", sa.DateTime(timezone=True)),
)
CATEGORIES = sa.Table(
    "semantic_mail_categories", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("version", sa.Integer, primary_key=True),
    sa.Column("key", sa.String(40), primary_key=True),
    sa.Column("label", sa.String(120), nullable=False),
    sa.Column("description", sa.String(400)),                           # modele giden açıklama
    sa.Column("enabled", sa.Boolean, nullable=False, default=True),
    sa.Column("auto_reply_enabled", sa.Boolean, nullable=False, default=False),   # bu sürümde etkisiz: gönderim yok
    sa.Column("hr_only", sa.Boolean, nullable=False, default=False),
    sa.Column("role", sa.String(10)),                                   # basvuru | ik | spam | None
    sa.Column("sort", sa.Integer, nullable=False, default=0),
)
ROUTES = sa.Table(
    "semantic_mail_routes", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("version", sa.Integer, primary_key=True),
    sa.Column("category_key", sa.String(40), primary_key=True),
    sa.Column("unit", sa.String(120)),
    sa.Column("primary_user", sa.String(120)),
    sa.Column("backup_user", sa.String(120)),
    sa.Column("manager_user", sa.String(120)),                          # birim yöneticisi (eskalasyon)
)
TEMPLATES = sa.Table(
    "semantic_mail_templates", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("category_key", sa.String(40), nullable=False),
    sa.Column("name", sa.String(200), nullable=False),
    sa.Column("body", sa.Text, nullable=False),
    sa.Index("ix_semantic_mail_templates_v", "tenant_id", "version"),
)
SLA = sa.Table(
    "semantic_mail_sla", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("version", sa.Integer, primary_key=True),
    sa.Column("category_key", sa.String(40), primary_key=True),
    sa.Column("remind_h", sa.Float, nullable=False),
    sa.Column("escalate_h", sa.Float, nullable=False),
    sa.Column("top_h", sa.Float, nullable=False),
)
APPLICATIONS = sa.Table(
    "semantic_mail_applications", _md,
    sa.Column("message_id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("author_name", sa.String(300)),
    sa.Column("work_title", sa.String(300)),
    sa.Column("genre", sa.String(120)),
    sa.Column("page_estimate", sa.Integer),
    sa.Column("attachments_json", sa.Text),
    sa.Column("status", sa.String(12), nullable=False),                 # yeni | aktarildi | reddedildi
    sa.Column("intake_ref", sa.String(80)),                             # M1 başvuru kimliği
    sa.Column("intake_no", sa.String(40)),
    sa.Column("crm_project_id", sa.String(40)),
    sa.Column("evidence_json", sa.Text),                                # çıkarmada düşen alanlar
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)
LABELS = sa.Table(
    "semantic_mail_labels", _md,
    sa.Column("message_id", sa.String(32), primary_key=True),
    sa.Column("by", sa.String(120), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("category_key", sa.String(40), nullable=False),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False),
)
META = sa.Table(
    "semantic_mail_meta", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("key", sa.String(60), primary_key=True),
    sa.Column("value_json", sa.Text, nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

STATUSES = {"yeni": "Yeni", "atandi": "Atandı", "yanitlandi": "Yanıtlandı", "kapandi": "Kapandı", "arsiv": "Arşiv"}
OPEN = ("yeni", "atandi")
DONE = ("kapandi", "arsiv")
#: Elle geçilebilecek durumlar: nereden → nereye.
TRANSITIONS = {
    "yeni": {"kapandi", "arsiv", "yanitlandi"},
    "atandi": {"kapandi", "arsiv", "yanitlandi", "yeni"},
    "yanitlandi": {"kapandi", "arsiv", "atandi"},
    "kapandi": {"atandi", "yeni"},
    "arsiv": {"yeni", "atandi"},
}
ROLES = {"basvuru": "Dosya başvurusu (yazar giriş sürecine aktarılır)", "ik": "İş başvurusu (yalnız İK görür)",
         "spam": "Tanıtım / spam (arşive)"}
VIEWS = {"mine": "Bana atanan", "unit": "Birimim", "unassigned": "Atanmamış", "unsure": "Emin olunmayan",
         "overdue": "Süresi aşan", "archive": "Arşiv"}
EVENT_LABELS = {"okundu": "Kutudan okundu", "siniflandi": "Zeki AI sınıfladı", "atandi": "Atandı",
                "tur-duzeltildi": "Tür düzeltildi", "durum": "Durum değişti", "yanitlandi": "Yanıtlandı",
                "hatirlatma": "Hatırlatma", "eskalasyon": "Eskalasyon", "kapandi": "Kapandı", "arsivlendi": "Arşivlendi",
                "aktarildi": "Aktarıldı", "taslak": "Yanıt taslağı hazırlandı", "basvuru": "Başvuru bilgisi düzeltildi"}

#: Kurulumda yürürlüğe giren ilk tür listesi (iş tanımındaki beş tür + analizde görülen kalemler). Kod bu listeyi yalnız
#: tablo boşken yazar; sonra her değişiklik Kurallar ekranından taslak → onay ile yapılır.
SEED_CATEGORIES = [
    ("dosya-basvurusu", "Dosya başvurusu", "Yazarın kitap/dosya önerisi, yayımlanma talebi, eser dosyası", "basvuru"),
    ("is-basvurusu", "İş başvurusu", "Özgeçmiş, iş/staj başvurusu, açık pozisyon sorusu", "ik"),
    ("sikayet", "Şikâyet", "Ürün, baskı hatası, kargo, hizmet şikâyeti", None),
    ("soru", "Soru / bilgi talebi", "Kitap, yazar, etkinlik, stok hakkında soru", None),
    ("siparis", "Sipariş ve kargo", "Sipariş durumu, iade, fatura, kargo takibi", None),
    ("bayi", "Bayi / kurum", "Kitapçı, bayi, kurum alımı, toplu sipariş", None),
    ("telif", "Telif ve izin", "Telif, çeviri hakkı, alıntı izni, yurt dışı yayınevi yazışması", None),
    ("bagis", "Bağış ve sponsorluk", "Kitap bağışı, kütüphane, sponsorluk, destek talebi", None),
    ("basin", "Basın ve medya", "Röportaj, basın bülteni, etkinlik daveti, medya talebi", None),
    ("tanitim", "Tanıtım / reklam / spam", "Reklam, bülten, satış teklifi, istenmeyen ileti", "spam"),
    ("diger", "Diğer", "Yukarıdakilerin hiçbirine girmeyen", None),
]

DEFAULTS = {
    "MAIL_START_DATE": "", "MAIL_HISTORY_FROM": "", "MAIL_READ_OVERLAP_MIN": "60",
    "MAIL_SUGGEST_MIN_PROB": "0.70", "MAIL_SUGGEST_MIN_MARGIN": "0.30",
    "MAIL_AUTO_MIN_PROB": "0.90", "MAIL_AUTO_MIN_MARGIN": "0.50",
    "MAIL_AUTO_ASSIGN_CATEGORIES": "", "MAIL_MODEL_BODY_CHARS": "6000", "MAIL_LLM_BUDGET_SEC": "200",
    "MAIL_REPLY_CHECK_MIN": "15", "MAIL_BUSINESS_HOURS": "1-5 09:00-18:00", "MAIL_HOLIDAYS": "",
    "MAIL_SLA_REMIND_H": "24", "MAIL_SLA_ESCALATE_H": "48", "MAIL_SLA_TOP_H": "72",
    "MAIL_INBOX_OWNERS": "", "MAIL_TOP_MANAGERS": "", "MAIL_SPAM_SENDERS": "",
    "MAIL_ORDER_PATTERN": r"(?:sipari[şs]|order)\s*(?:no|numaras[ıi]|#)?\s*[:#]?\s*([A-Z0-9][A-Z0-9\-]{4,19})",
    "MAIL_CONNECTION_ALERT_MIN": "30", "MAIL_CONNECTION_ALERT_TO": "", "MAIL_NOTIFY_EMAIL": "1",
}


class MailError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------------------------------------ kurulum, ayar


def ensure(engine: sa.engine.Engine) -> None:
    key = id(engine)
    with _lock:
        if key in _ready:
            return
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)
        _ready.add(key)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new() -> str:
    return uuid.uuid4().hex


def _aware(v: Optional[datetime]) -> Optional[datetime]:
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _iso(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return _aware(v).isoformat()
    return v.isoformat() if isinstance(v, date) else str(v)


def _j(v: Optional[str], default: Any = None) -> Any:
    if not v:
        return default
    try:
        return json.loads(v)
    except ValueError:
        return default


def _day(raw: str) -> Optional[date]:
    try:
        return date.fromisoformat(str(raw or "").strip()[:10]) if str(raw or "").strip() else None
    except ValueError:
        return None


def _users(raw: str) -> list[str]:
    return [u.strip().lower() for u in re.split(r"[,;\s]+", raw or "") if re.match(r"^[a-z0-9._$\-]+$", u.strip().lower())]


def settings_from(conf: Callable[[str, str], str]) -> dict[str, Any]:
    def g(key: str) -> str:
        v = conf(key, DEFAULTS[key])
        return DEFAULTS[key] if v is None else str(v)

    def gf(key: str, lo: float, hi: float) -> float:
        try:
            return max(lo, min(hi, float(g(key).replace(",", "."))))
        except ValueError:
            return float(DEFAULTS[key])

    return {
        "startDate": _day(g("MAIL_START_DATE")),
        "historyFrom": _day(g("MAIL_HISTORY_FROM")),
        "overlapMin": int(gf("MAIL_READ_OVERLAP_MIN", 0, 7 * 24 * 60)),
        "thresholds": {"suggestProb": gf("MAIL_SUGGEST_MIN_PROB", 0, 1), "suggestMargin": gf("MAIL_SUGGEST_MIN_MARGIN", 0, 1),
                       "autoProb": gf("MAIL_AUTO_MIN_PROB", 0, 1), "autoMargin": gf("MAIL_AUTO_MIN_MARGIN", 0, 1)},
        "autoAssign": {k.strip() for k in re.split(r"[,;\s]+", g("MAIL_AUTO_ASSIGN_CATEGORIES")) if k.strip()},
        "bodyChars": int(gf("MAIL_MODEL_BODY_CHARS", 500, 200_000)),
        "llmBudgetSec": int(gf("MAIL_LLM_BUDGET_SEC", 0, 3000)),
        "replyCheckMin": int(gf("MAIL_REPLY_CHECK_MIN", 0, 24 * 60)),
        "calendar": parse_calendar(g("MAIL_BUSINESS_HOURS"), g("MAIL_HOLIDAYS")),
        "businessHours": g("MAIL_BUSINESS_HOURS"),
        "defaultSla": (gf("MAIL_SLA_REMIND_H", 1, 2000), gf("MAIL_SLA_ESCALATE_H", 1, 2000), gf("MAIL_SLA_TOP_H", 1, 2000)),
        "inboxOwners": _users(g("MAIL_INBOX_OWNERS")),
        "topManagers": _users(g("MAIL_TOP_MANAGERS")),
        "spamSenders": {s.strip().lower().lstrip("@") for s in re.split(r"[,;\s]+", g("MAIL_SPAM_SENDERS")) if s.strip()},
        "orderPattern": g("MAIL_ORDER_PATTERN"),
        "connectionAlertMin": int(gf("MAIL_CONNECTION_ALERT_MIN", 5, 24 * 60)),
        "connectionAlertTo": [x.strip() for x in re.split(r"[,;\s]+", g("MAIL_CONNECTION_ALERT_TO")) if "@" in x],
        "notifyEmail": g("MAIL_NOTIFY_EMAIL").strip() != "0",
    }


def meta_get(engine: sa.engine.Engine, tenant: str, key: str, default: Any = None) -> Any:
    with engine.connect() as c:
        v = c.execute(sa.select(META.c.value_json).where(META.c.tenant_id == tenant, META.c.key == key)).scalar()
    return _j(v, default) if v else default


def meta_set(engine: sa.engine.Engine, tenant: str, key: str, value: Any) -> None:
    raw = json.dumps(value, ensure_ascii=False, default=str)
    with engine.begin() as c:
        n = c.execute(sa.update(META).where(META.c.tenant_id == tenant, META.c.key == key)
                      .values(value_json=raw, updated_at=_now())).rowcount
        if not n:
            c.execute(META.insert().values(tenant_id=tenant, key=key, value_json=raw, updated_at=_now()))


# ------------------------------------------------------------------------------------------------ iş saatleri


def parse_calendar(hours: str, holidays: str) -> dict[str, Any]:
    """«1-5 09:00-18:00» (ISO hafta günü 1 = pazartesi) ya da «1-5 09:00-18:00; 6 10:00-14:00». Tatiller YYYY-AA-GG."""
    days: dict[int, tuple[int, int]] = {}
    for part in re.split(r"[;\n]", hours or ""):
        m = re.match(r"^\s*(\d)(?:\s*-\s*(\d))?\s+(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*$", part)
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        start, end = int(m.group(3)) * 60 + int(m.group(4)), int(m.group(5)) * 60 + int(m.group(6))
        if not (1 <= a <= b <= 7) or end <= start:
            continue
        for d in range(a, b + 1):
            days[d] = (start, end)
    if not days:
        days = {d: (9 * 60, 18 * 60) for d in range(1, 6)}
    hol = {d for d in (_day(x) for x in re.split(r"[,;\s]+", holidays or "")) if d}
    return {"days": days, "holidays": hol}


def _windows(cal: dict[str, Any], day: date) -> Optional[tuple[datetime, datetime]]:
    if day in cal["holidays"] or day.isoweekday() not in cal["days"]:
        return None
    s, e = cal["days"][day.isoweekday()]
    base = datetime(day.year, day.month, day.day, tzinfo=TZ)
    return base + timedelta(minutes=s), base + timedelta(minutes=e)


def add_business_hours(start: datetime, hours: float, cal: dict[str, Any]) -> datetime:
    """`start`'tan itibaren `hours` iş saati sonrası (UTC)."""
    left = timedelta(hours=hours)
    cur = _aware(start).astimezone(TZ)
    day = cur.date()
    for _ in range(3700):                                   # ~10 yıl: çalışma günü hiç yoksa sonsuz döngü olmasın
        w = _windows(cal, day)
        if w:
            a, b = max(w[0], cur), w[1]
            if a < b:
                if b - a >= left:
                    return (a + left).astimezone(timezone.utc)
                left -= b - a
        day += timedelta(days=1)
        cur = datetime(day.year, day.month, day.day, tzinfo=TZ)
    raise MailError("İş saatleri takviminde çalışma günü yok.")


def business_hours_between(a: datetime, b: datetime, cal: dict[str, Any]) -> float:
    a, b = _aware(a).astimezone(TZ), _aware(b).astimezone(TZ)
    if b <= a:
        return 0.0
    total = timedelta(0)
    day = a.date()
    while day <= b.date():
        w = _windows(cal, day)
        if w:
            s, e = max(w[0], a), min(w[1], b)
            if e > s:
                total += e - s
        day += timedelta(days=1)
    return total.total_seconds() / 3600


# ------------------------------------------------------------------------------------------------ kurallar


def _seed(c: Any, tenant: str, st: dict[str, Any]) -> None:
    if c.execute(sa.select(sa.func.count()).select_from(RULESETS).where(RULESETS.c.tenant_id == tenant)).scalar():
        return
    now = _now()
    c.execute(RULESETS.insert().values(tenant_id=tenant, version=1, status="onayli", created_by="kurulum", created_at=now,
                                       approved_by="kurulum", approved_at=now,
                                       note="Kurulumdaki başlangıç listesi (iş tanımındaki türler). Yönlendirme boş: "
                                            "her ileti «Atanmamış»ta başlar."))
    r, e, t = st["defaultSla"]
    for i, (key, label, desc, role) in enumerate(SEED_CATEGORIES):
        c.execute(CATEGORIES.insert().values(tenant_id=tenant, version=1, key=key, label=label, description=desc, enabled=True,
                                             auto_reply_enabled=False, hr_only=role == "ik", role=role, sort=i))
        c.execute(SLA.insert().values(tenant_id=tenant, version=1, category_key=key, remind_h=r, escalate_h=e, top_h=t))


def _version(c: Any, tenant: str, status: str) -> Optional[int]:
    return c.execute(sa.select(sa.func.max(RULESETS.c.version))
                     .where(RULESETS.c.tenant_id == tenant, RULESETS.c.status == status)).scalar()


def _ruleset(c: Any, tenant: str, version: int) -> dict[str, Any]:
    head = c.execute(sa.select(RULESETS).where(RULESETS.c.tenant_id == tenant, RULESETS.c.version == version)).first()
    cats = [dict(r._mapping) for r in c.execute(sa.select(CATEGORIES).where(CATEGORIES.c.tenant_id == tenant,
                                                                           CATEGORIES.c.version == version)
                                                .order_by(CATEGORIES.c.sort, CATEGORIES.c.key))]
    routes = {r.category_key: dict(r._mapping) for r in c.execute(sa.select(ROUTES).where(ROUTES.c.tenant_id == tenant,
                                                                                         ROUTES.c.version == version))}
    sla = {r.category_key: dict(r._mapping) for r in c.execute(sa.select(SLA).where(SLA.c.tenant_id == tenant,
                                                                                   SLA.c.version == version))}
    tmpl = [dict(r._mapping) for r in c.execute(sa.select(TEMPLATES).where(TEMPLATES.c.tenant_id == tenant,
                                                                          TEMPLATES.c.version == version)
                                                .order_by(TEMPLATES.c.category_key, TEMPLATES.c.name))]
    return {
        "version": version, "status": head.status if head else None, "note": head.note if head else None,
        "createdBy": head.created_by if head else None, "createdAt": _iso(head.created_at) if head else None,
        "updatedBy": head.updated_by if head else None, "updatedAt": _iso(head.updated_at) if head else None,
        "approvedBy": head.approved_by if head else None, "approvedAt": _iso(head.approved_at) if head else None,
        "categories": [{"key": x["key"], "label": x["label"], "description": x["description"], "enabled": bool(x["enabled"]),
                        "role": x["role"], "hrOnly": bool(x["hr_only"]), "autoReply": bool(x["auto_reply_enabled"]),
                        "sort": x["sort"]} for x in cats],
        "routes": [{"category": k, "unit": v["unit"], "primary": v["primary_user"], "backup": v["backup_user"],
                    "manager": v["manager_user"]} for k, v in sorted(routes.items())],
        "sla": [{"category": k, "remindH": v["remind_h"], "escalateH": v["escalate_h"], "topH": v["top_h"]}
                for k, v in sorted(sla.items())],
        "templates": [{"id": x["id"], "category": x["category_key"], "name": x["name"], "body": x["body"]} for x in tmpl],
    }


def active_rules(engine: sa.engine.Engine, tenant: str, st: dict[str, Any]) -> dict[str, Any]:
    with engine.begin() as c:
        _seed(c, tenant, st)
        v = _version(c, tenant, "onayli")
        return _ruleset(c, tenant, v) if v else {"version": None, "categories": [], "routes": [], "sla": [], "templates": []}


def rules_view(engine: sa.engine.Engine, tenant: str, st: dict[str, Any]) -> dict[str, Any]:
    with engine.begin() as c:
        _seed(c, tenant, st)
        va, vd = _version(c, tenant, "onayli"), _version(c, tenant, "taslak")
        history = [{"version": r.version, "status": r.status, "approvedBy": r.approved_by, "approvedAt": _iso(r.approved_at),
                    "createdBy": r.created_by, "note": r.note}
                   for r in c.execute(sa.select(RULESETS).where(RULESETS.c.tenant_id == tenant)
                                      .order_by(RULESETS.c.version.desc()))]
        return {"active": _ruleset(c, tenant, va) if va else None, "draft": _ruleset(c, tenant, vd) if vd else None,
                "history": history, "roles": ROLES, "businessHours": st["businessHours"],
                "defaultSla": dict(zip(("remindH", "escalateH", "topH"), st["defaultSla"]))}


_KEY = re.compile(r"^[a-z0-9][a-z0-9\-]{1,39}$")
_USER = re.compile(r"^[a-z0-9._$\-]{1,120}$")


def _opt_user(v: Any, what: str) -> Optional[str]:
    s = str(v or "").strip().lower()
    if not s:
        return None
    if not _USER.match(s):
        raise MailError(f"{what} «{s}» geçerli bir hesap adı değil.")
    return s


def _validate_rules(body: dict[str, Any]) -> dict[str, Any]:
    cats_in = body.get("categories")
    if not isinstance(cats_in, list) or not cats_in:
        raise MailError("En az bir tür gerekli.")
    cats, seen, labels = [], set(), set()
    for i, x in enumerate(cats_in):
        key = str((x or {}).get("key") or "").strip().lower()
        label = re.sub(r"\s+", " ", str((x or {}).get("label") or "")).strip()
        if not _KEY.match(key):
            raise MailError(f"Tür anahtarı «{key}» geçersiz (küçük harf, rakam, tire; 2–40 karakter).")
        if key in seen:
            raise MailError(f"«{key}» türü iki kez yazılmış.")
        if not label or len(label) > 120:
            raise MailError(f"«{key}» türünün adı boş ya da çok uzun.")
        if label.casefold() in labels:
            raise MailError(f"«{label}» adı iki türde kullanılmış; model türleri adıyla ayırır.")
        role = (x or {}).get("role") or None
        if role is not None and role not in ROLES:
            raise MailError(f"«{label}» için rol geçersiz.")
        seen.add(key)
        labels.add(label.casefold())
        cats.append({"key": key, "label": label, "description": str((x or {}).get("description") or "").strip()[:400] or None,
                     "enabled": bool((x or {}).get("enabled", True)), "role": role, "hr_only": role == "ik", "sort": i})
    if not any(c["enabled"] for c in cats):
        raise MailError("En az bir tür açık olmalı.")
    routes = []
    for x in body.get("routes") or []:
        k = str((x or {}).get("category") or "").strip().lower()
        if k not in seen:
            raise MailError(f"Yönlendirme tablosunda bilinmeyen tür: «{k}».")
        routes.append({"category_key": k, "unit": (str(x.get("unit") or "").strip()[:120] or None),
                       "primary_user": _opt_user(x.get("primary"), "Sorumlu"), "backup_user": _opt_user(x.get("backup"), "Yedek"),
                       "manager_user": _opt_user(x.get("manager"), "Birim yöneticisi")})
    if len({r["category_key"] for r in routes}) != len(routes):
        raise MailError("Bir türün iki yönlendirme satırı olamaz.")
    sla = []
    for x in body.get("sla") or []:
        k = str((x or {}).get("category") or "").strip().lower()
        if k not in seen:
            raise MailError(f"SLA tablosunda bilinmeyen tür: «{k}».")
        try:
            r, e, t = (float(x.get(f)) for f in ("remindH", "escalateH", "topH"))
        except (TypeError, ValueError):
            raise MailError(f"«{k}» SLA saatleri sayı olmalı.") from None
        if not (0 < r <= e <= t <= 2000):
            raise MailError(f"«{k}» SLA: hatırlatma ≤ eskalasyon ≤ üst yönetici olmalı (saat, 0'dan büyük).")
        sla.append({"category_key": k, "remind_h": r, "escalate_h": e, "top_h": t})
    templates = []
    for x in body.get("templates") or []:
        k = str((x or {}).get("category") or "").strip().lower()
        name = str((x or {}).get("name") or "").strip()[:200]
        text = str((x or {}).get("body") or "").strip()
        if k not in seen:
            raise MailError(f"Şablonda bilinmeyen tür: «{k}».")
        if not name or not text:
            raise MailError("Şablonun adı ve metni boş olamaz.")
        templates.append({"category_key": k, "name": name, "body": text[:8000]})
    return {"categories": cats, "routes": routes, "sla": sla, "templates": templates,
            "note": str(body.get("note") or "").strip()[:2000] or None}


def save_draft(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any], st: dict[str, Any]) -> dict[str, Any]:
    """Taslak kural sürümünü yazar (varsa üzerine). Yürürlükteki sürüm değişmez; onay ayrı adımdır."""
    v = _validate_rules(body)
    with engine.begin() as c:
        _seed(c, tenant, st)
        draft = _version(c, tenant, "taslak")
        now = _now()
        if draft is None:
            draft = int(c.execute(sa.select(sa.func.max(RULESETS.c.version)).where(RULESETS.c.tenant_id == tenant)).scalar() or 0) + 1
            c.execute(RULESETS.insert().values(tenant_id=tenant, version=draft, status="taslak", note=v["note"],
                                               created_by=user, created_at=now, updated_by=user, updated_at=now))
        else:
            c.execute(sa.update(RULESETS).where(RULESETS.c.tenant_id == tenant, RULESETS.c.version == draft)
                      .values(note=v["note"], updated_by=user, updated_at=now))
        for t in (CATEGORIES, ROUTES, SLA, TEMPLATES):
            c.execute(sa.delete(t).where(t.c.tenant_id == tenant, t.c.version == draft))
        for x in v["categories"]:
            c.execute(CATEGORIES.insert().values(tenant_id=tenant, version=draft, auto_reply_enabled=False, **x))
        for x in v["routes"]:
            c.execute(ROUTES.insert().values(tenant_id=tenant, version=draft, **x))
        for x in v["sla"]:
            c.execute(SLA.insert().values(tenant_id=tenant, version=draft, **x))
        for x in v["templates"]:
            c.execute(TEMPLATES.insert().values(id=_new(), tenant_id=tenant, version=draft, **x))
        return _ruleset(c, tenant, draft)


def discard_draft(engine: sa.engine.Engine, tenant: str) -> int:
    with engine.begin() as c:
        draft = _version(c, tenant, "taslak")
        if draft is None:
            raise MailError("Silinecek taslak yok.", 404)
        for t in (CATEGORIES, ROUTES, SLA, TEMPLATES):
            c.execute(sa.delete(t).where(t.c.tenant_id == tenant, t.c.version == draft))
        c.execute(sa.delete(RULESETS).where(RULESETS.c.tenant_id == tenant, RULESETS.c.version == draft))
        return draft


def approve_draft(engine: sa.engine.Engine, tenant: str, user: str, version: int) -> dict[str, Any]:
    """Taslağı yürürlüğe alır; önceki yürürlükteki sürüm arşive geçer. Taslağı yazan onaylayamaz (iki göz)."""
    with engine.begin() as c:
        head = c.execute(sa.select(RULESETS).where(RULESETS.c.tenant_id == tenant, RULESETS.c.version == int(version))).first()
        if head is None or head.status != "taslak":
            raise MailError("Onaylanacak taslak bulunamadı (başka biri onaylamış ya da silmiş olabilir).", 409)
        if user in {head.created_by, head.updated_by}:
            raise MailError("Taslağı yazan ya da son düzenleyen onaylayamaz; başka bir yetkili onaylamalı.", 403)
        now = _now()
        c.execute(sa.update(RULESETS).where(RULESETS.c.tenant_id == tenant, RULESETS.c.status == "onayli").values(status="arsiv"))
        c.execute(sa.update(RULESETS).where(RULESETS.c.tenant_id == tenant, RULESETS.c.version == head.version)
                  .values(status="onayli", approved_by=user, approved_at=now))
        return _ruleset(c, tenant, head.version)


def _all_labels(c: Any, tenant: str) -> dict[str, str]:
    """Bütün sürümlerdeki tür adları (eski sürümde kalan türle sınıflanmış ileti de adıyla görünsün); yenisi kazanır."""
    out: dict[str, str] = {}
    for r in c.execute(sa.select(CATEGORIES.c.key, CATEGORIES.c.label).where(CATEGORIES.c.tenant_id == tenant)
                       .order_by(CATEGORIES.c.version)):
        out[r.key] = r.label
    return out


def _sla_for(rules: dict[str, Any], category: Optional[str], st: dict[str, Any]) -> tuple[float, float, float]:
    for s in rules.get("sla") or []:
        if s["category"] == category:
            return float(s["remindH"]), float(s["escalateH"]), float(s["topH"])
    return st["defaultSla"]


def _route_for(rules: dict[str, Any], category: Optional[str]) -> dict[str, Any]:
    return next((r for r in rules.get("routes") or [] if r["category"] == category), {})


def _cat(rules: dict[str, Any], key: Optional[str]) -> Optional[dict[str, Any]]:
    return next((c for c in rules.get("categories") or [] if c["key"] == key), None)


def user_units(rules: dict[str, Any], user: str) -> set[str]:
    """Kişinin birimleri: yürürlükteki yönlendirmede sorumlu, yedek ya da yönetici olduğu satırların birimi."""
    return {r["unit"] for r in rules.get("routes") or [] if r.get("unit") and user in (r.get("primary"), r.get("backup"), r.get("manager"))}


# ------------------------------------------------------------------------------------------------ kayıt


def addr_hash(addr: str) -> str:
    return hashlib.sha256((addr or "").strip().lower().encode()).hexdigest()


def mask_addr(addr: str) -> str:
    """«a***@alan.com» (ortak maske `zeki_text.mask_address`; modele giden gönderen de bu biçimdedir)."""
    from semantic_bridge import zeki_text as Z

    return Z.mask_address(addr)


def _event(c: Any, tenant: str, message_id: str, action: str, by: str, detail: Any = None) -> None:
    c.execute(EVENTS.insert().values(id=_new(), tenant_id=tenant, message_id=message_id, action=action, by=by, at=_now(),
                                     detail_json=json.dumps(detail, ensure_ascii=False, default=str) if detail is not None else None))


def start_at(engine: sa.engine.Engine, tenant: str, st: dict[str, Any]) -> datetime:
    """Canlı işlemenin başlangıcı: ayardaki tarih (İstanbul gece yarısı) ya da ilk okumanın anı (kalıcı)."""
    if st["startDate"]:
        d = st["startDate"]
        return datetime(d.year, d.month, d.day, tzinfo=TZ).astimezone(timezone.utc)
    got = meta_get(engine, tenant, "start_at")
    if got:
        return _aware(datetime.fromisoformat(got))
    now = _now()
    meta_set(engine, tenant, "start_at", now.isoformat())
    return now


def read_window(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], start: datetime) -> datetime:
    """Bu okumanın alt sınırı: son okunan iletinin zamanı − örtüşme; ilk okumada geçmiş başlangıcı ya da canlı başlangıç."""
    with engine.connect() as c:
        last = c.execute(sa.select(sa.func.max(MESSAGES.c.received_at)).where(MESSAGES.c.tenant_id == tenant)).scalar()
    if last is not None:
        return _aware(last) - timedelta(minutes=st["overlapMin"])
    if st["historyFrom"]:
        d = st["historyFrom"]
        return min(start, datetime(d.year, d.month, d.day, tzinfo=TZ).astimezone(timezone.utc))
    return start - timedelta(minutes=st["overlapMin"])


def known_ids(engine: sa.engine.Engine, tenant: str, provider: str, ids: Iterable[str]) -> set[str]:
    ids = list(ids)
    out: set[str] = set()
    with engine.connect() as c:
        for i in range(0, len(ids), 900):
            out |= {r[0] for r in c.execute(sa.select(MESSAGES.c.provider_id).where(
                MESSAGES.c.tenant_id == tenant, MESSAGES.c.provider == provider, MESSAGES.c.provider_id.in_(ids[i:i + 900])))}
    return out


def ingest(engine: sa.engine.Engine, tenant: str, provider: str, item: Any, crm: dict[str, Any], rules: dict[str, Any],
           st: dict[str, Any], start: datetime) -> Optional[str]:
    """Bir iletiyi kaydeder (gövde yazılmaz). Aynı sağlayıcı kimliği varsa None. Kutunun spam işareti ya da ayardaki
    gönderen listesi → spam rolündeki tür, kaynak «kural», arşiv (geri alınabilir)."""
    from semantic_bridge.mailbox_classify import order_refs

    historical = _aware(item.received_at) < start
    spam_cat = next((c for c in rules.get("categories") or [] if c["role"] == "spam" and c["enabled"]), None)
    domain = item.from_addr.rpartition("@")[2]
    rule_spam = spam_cat is not None and ("SPAM" in item.labels or item.from_addr in st["spamSenders"]
                                          or domain in st["spamSenders"])
    mid = _new()
    now = _now()
    vals: dict[str, Any] = dict(
        id=mid, tenant_id=tenant, provider=provider, provider_id=item.provider_id, thread_id=item.thread_id,
        received_at=_aware(item.received_at), from_addr_hash=addr_hash(item.from_addr),
        from_display=(item.from_name or None), from_masked=mask_addr(item.from_addr), subject=item.subject or None,
        unsure=False, status="yeni", historical=historical,
        labels_json=json.dumps(item.labels), attachments_json=json.dumps([a.public() for a in item.attachments], ensure_ascii=False),
        order_refs_json=json.dumps(order_refs(item.text, item.subject, st["orderPattern"]), ensure_ascii=False),
        crm_json=json.dumps(crm, ensure_ascii=False) if crm else None,
        crm_contact_id=(crm.get("kisi") or {}).get("id"), crm_account_id=(crm.get("firma") or {}).get("id"),
        crm_lead_id=(crm.get("aday") or {}).get("id"), created_at=now,
    )
    if not historical:
        vals["due_at"] = add_business_hours(item.received_at, _sla_for(rules, None, st)[0], st["calendar"])
    if rule_spam:
        vals.update(category=spam_cat["key"], category_source="kural", category_method="kural", classified_at=now,
                    status="arsiv" if not historical else "yeni", priority="dusuk")
    try:
        with engine.begin() as c:
            c.execute(MESSAGES.insert().values(**vals))
            _event(c, tenant, mid, "okundu", "kutu", {"gecmis": historical} if historical else None)
            if rule_spam:
                _event(c, tenant, mid, "arsivlendi", "kural", {"neden": "kutunun spam işareti" if "SPAM" in item.labels
                                                                else "ayardaki gönderen listesi"})
    except sa.exc.IntegrityError:
        return None
    return mid


def apply_classification(engine: sa.engine.Engine, tenant: str, mid: str, res: dict[str, Any], rules: dict[str, Any],
                         st: dict[str, Any], summary: Optional[str], application: Optional[dict[str, Any]],
                         attachments: list[dict[str, Any]]) -> dict[str, Any]:
    """Zeki AI sonucunu yazar: tür (olasılıkla), öncelik, özet, sorumlu önerisi; spam ve otomatik atama eşiklerini uygular."""
    cat = _cat(rules, res.get("category"))
    route = _route_for(rules, res.get("category"))
    with engine.begin() as c:
        row = c.execute(sa.select(MESSAGES).where(MESSAGES.c.id == mid)).first()
        if row is None or row.classified_at is not None:
            return {"skipped": True}
        vals: dict[str, Any] = dict(
            category=res.get("category"), category_prob=res.get("category_prob"), category_margin=res.get("category_margin"),
            category_source="model" if res.get("category") else None, category_method=res.get("category_method"),
            model_category=res.get("category"), model_prob=res.get("category_prob"), unsure=bool(res.get("unsure")),
            priority=res.get("priority") or "normal", priority_prob=res.get("priority_prob"),
            is_hr=bool(cat and cat["role"] == "ik"), classified_at=_now(), updated_at=_now(),
            suggested_unit=route.get("unit"), suggested_assignee=route.get("primary") or route.get("backup"),
        )
        if summary is not None:
            vals["summary"] = summary
        if not row.historical:
            vals["due_at"] = add_business_hours(row.received_at, _sla_for(rules, res.get("category"), st)[0], st["calendar"])
        auto = bool(res.get("auto")) and not row.historical
        action = None
        if cat and cat["role"] == "spam" and auto:
            vals["status"], action = "arsiv", "arsivlendi"
        elif (cat and auto and cat["key"] in st["autoAssign"] and vals["suggested_assignee"] and row.status == "yeni"):
            vals.update(status="atandi", assignee=vals["suggested_assignee"], unit=vals["suggested_unit"])
            action = "atandi"
        c.execute(sa.update(MESSAGES).where(MESSAGES.c.id == mid).values(**vals))
        _event(c, tenant, mid, "siniflandi", "zeki", {"tur": res.get("category"), "olasilik": res.get("category_prob"),
                                                      "marj": res.get("category_margin"), "yontem": res.get("category_method"),
                                                      "eminDegil": bool(res.get("unsure")), "oncelik": vals["priority"],
                                                      "kanit": res.get("evidence")})
        if action == "arsivlendi":
            _event(c, tenant, mid, "arsivlendi", "zeki", {"neden": "tanıtım/spam, olasılık otomatik eşiğin üstünde"})
        elif action == "atandi":
            _event(c, tenant, mid, "atandi", "zeki", {"kime": vals["assignee"], "birim": vals["unit"], "otomatik": True})
        if application is not None and cat and cat["role"] == "basvuru":
            exists = c.execute(sa.select(APPLICATIONS.c.message_id).where(APPLICATIONS.c.message_id == mid)).first()
            if not exists:
                c.execute(APPLICATIONS.insert().values(
                    message_id=mid, tenant_id=tenant, author_name=application.get("author_name"),
                    work_title=application.get("work_title"), genre=application.get("genre"),
                    page_estimate=application.get("page_estimate"),
                    attachments_json=json.dumps(attachments, ensure_ascii=False), status="yeni",
                    evidence_json=json.dumps({"dusen": application.get("dropped") or []}, ensure_ascii=False),
                    created_at=_now()))
    return {"action": action}


def mark_unclassifiable(engine: sa.engine.Engine, tenant: str, mid: str, reason: str) -> None:
    """Model tanımlı değilse ileti yine kayıtlıdır: «emin olunmayan» kuyruğuna düşer, insan sınıflar."""
    with engine.begin() as c:
        n = c.execute(sa.update(MESSAGES).where(MESSAGES.c.id == mid, MESSAGES.c.classified_at.is_(None))
                      .values(unsure=True, classified_at=_now(), category_method="none", priority="normal")).rowcount
        if n:
            _event(c, tenant, mid, "siniflandi", "zeki", {"eminDegil": True, "neden": reason})


def pending(engine: sa.engine.Engine, tenant: str, historical: bool) -> list[Any]:
    """Sınıflanmamış iletiler, eskiden yeniye. Hepsi döner; süre bütçesi çağıranda."""
    with engine.connect() as c:
        return list(c.execute(sa.select(MESSAGES.c.id, MESSAGES.c.provider_id, MESSAGES.c.crm_json)
                              .where(MESSAGES.c.tenant_id == tenant, MESSAGES.c.classified_at.is_(None),
                                     MESSAGES.c.historical.is_(historical))
                              .order_by(MESSAGES.c.received_at)))


def reply_candidates(engine: sa.engine.Engine, tenant: str, st: dict[str, Any]) -> list[Any]:
    cut = _now() - timedelta(minutes=st["replyCheckMin"])
    with engine.connect() as c:
        return list(c.execute(sa.select(MESSAGES.c.id, MESSAGES.c.thread_id, MESSAGES.c.provider_id, MESSAGES.c.received_at)
                              .where(MESSAGES.c.tenant_id == tenant, MESSAGES.c.historical.is_(False),
                                     MESSAGES.c.status.in_(OPEN), MESSAGES.c.first_reply_at.is_(None),
                                     sa.or_(MESSAGES.c.reply_checked_at.is_(None), MESSAGES.c.reply_checked_at < cut))
                              .order_by(MESSAGES.c.reply_checked_at.is_(None).desc(), MESSAGES.c.received_at)))


def record_reply(engine: sa.engine.Engine, tenant: str, mid: str, at: Optional[datetime]) -> bool:
    with engine.begin() as c:
        if at is None:
            c.execute(sa.update(MESSAGES).where(MESSAGES.c.id == mid).values(reply_checked_at=_now()))
            return False
        n = c.execute(sa.update(MESSAGES).where(MESSAGES.c.id == mid, MESSAGES.c.first_reply_at.is_(None))
                      .values(first_reply_at=at, reply_checked_at=_now(), status="yanitlandi", updated_at=_now())).rowcount
        if n:
            _event(c, tenant, mid, "yanitlandi", "kutu", {"zaman": at.isoformat(), "kaynak": "kutunun konu zinciri"})
        return bool(n)


# ------------------------------------------------------------------------------------------------ okuma (ekran)


def _row(c: Any, tenant: str, mid: str) -> Any:
    r = c.execute(sa.select(MESSAGES).where(MESSAGES.c.id == str(mid or ""), MESSAGES.c.tenant_id == tenant)).first()
    if r is None:
        raise MailError("İleti bulunamadı.", 404)
    return r


def _remaining(r: Any, st: dict[str, Any], now: datetime) -> Optional[float]:
    if r.due_at is None or r.first_reply_at is not None or r.status not in OPEN:
        return None
    due = _aware(r.due_at)
    return round(business_hours_between(now, due, st["calendar"]) if due > now
                 else -business_hours_between(due, now, st["calendar"]), 1)


def _out(r: Any, labels: dict[str, str], st: dict[str, Any], now: datetime) -> dict[str, Any]:
    crm = _j(r.crm_json, {}) or {}
    rem = _remaining(r, st, now)
    return {
        "id": r.id, "receivedAt": _iso(r.received_at), "fromName": r.from_display, "fromMasked": r.from_masked,
        "subject": r.subject, "summary": r.summary, "category": r.category,
        "categoryLabel": labels.get(r.category or "", r.category), "categoryProb": r.category_prob,
        "categoryMargin": r.category_margin, "categorySource": r.category_source, "categoryMethod": r.category_method,
        "unsure": bool(r.unsure), "classified": r.classified_at is not None, "priority": r.priority,
        "priorityProb": r.priority_prob, "status": r.status, "statusLabel": STATUSES.get(r.status, r.status),
        "assignee": r.assignee, "unit": r.unit, "suggestedAssignee": r.suggested_assignee, "suggestedUnit": r.suggested_unit,
        "dueAt": _iso(r.due_at), "remainingH": rem, "overdue": rem is not None and rem < 0,
        "firstReplyAt": _iso(r.first_reply_at), "closedAt": _iso(r.closed_at), "isHr": bool(r.is_hr),
        "historical": bool(r.historical), "crm": crm,
        "attachments": _j(r.attachments_json, []) or [], "orderRefs": _j(r.order_refs_json, []) or [],
        "boxLabels": _j(r.labels_json, []) or [],
    }


def _scope(rules: dict[str, Any], user: str, rights: dict[str, bool]) -> list[Any]:
    cond: list[Any] = []
    if not rights.get("hr"):
        cond.append(MESSAGES.c.is_hr.is_(False))
    if not rights.get("all"):
        units = user_units(rules, user)
        cond.append(sa.or_(MESSAGES.c.assignee == user, MESSAGES.c.unit.in_(units) if units else sa.false()))
    return cond


def _view_cond(view: str, user: str, units: set[str], now: datetime) -> list[Any]:
    open_ = MESSAGES.c.status.in_(OPEN)
    if view == "mine":
        return [MESSAGES.c.assignee == user, MESSAGES.c.status.notin_(DONE)]
    if view == "unit":
        return [MESSAGES.c.unit.in_(units) if units else sa.false(), MESSAGES.c.status.notin_(DONE)]
    if view == "unassigned":
        return [MESSAGES.c.status == "yeni", MESSAGES.c.assignee.is_(None), MESSAGES.c.unsure.is_(False)]
    if view == "unsure":
        return [MESSAGES.c.unsure.is_(True), MESSAGES.c.status.notin_(DONE)]
    if view == "overdue":
        return [open_, MESSAGES.c.first_reply_at.is_(None), MESSAGES.c.due_at < now]
    if view == "archive":
        return [MESSAGES.c.status.in_(DONE)]
    raise MailError("Görünüm geçerli değil.")


def listing(engine: sa.engine.Engine, tenant: str, user: str, rights: dict[str, bool], st: dict[str, Any], *,
            view: str = "mine", q: str = "", category: str = "", page: int = 0, page_size: int = 50) -> dict[str, Any]:
    rules = active_rules(engine, tenant, st)
    units = user_units(rules, user)
    now = _now()
    base = [MESSAGES.c.tenant_id == tenant, MESSAGES.c.historical.is_(False), *_scope(rules, user, rights)]
    page_size = max(10, min(int(page_size or 50), 200))
    with engine.connect() as c:
        labels = _all_labels(c, tenant)
        counts = {}
        for v in VIEWS:
            counts[v] = int(c.execute(sa.select(sa.func.count()).select_from(MESSAGES)
                                      .where(*base, *_view_cond(v, user, units, now))).scalar() or 0)
        cond = base + _view_cond(view, user, units, now)
        if category:
            cond.append(MESSAGES.c.category == category)
        if q.strip():
            like = f"%{q.strip()}%"
            cond.append(sa.or_(MESSAGES.c.subject.ilike(like), MESSAGES.c.from_display.ilike(like),
                               MESSAGES.c.summary.ilike(like), MESSAGES.c.from_masked.ilike(like)))
        total = int(c.execute(sa.select(sa.func.count()).select_from(MESSAGES).where(*cond)).scalar() or 0)
        order = ([MESSAGES.c.due_at.asc()] if view == "overdue" else
                 [sa.case((MESSAGES.c.priority == "yuksek", 0), else_=1), MESSAGES.c.received_at.desc()]
                 if view in ("mine", "unit", "unassigned") else [MESSAGES.c.received_at.desc()])
        rows = c.execute(sa.select(MESSAGES).where(*cond).order_by(*order).offset(max(0, int(page)) * page_size).limit(page_size))
        items = [_out(r, labels, st, now) for r in rows]
    return {"view": view, "items": items, "total": total, "page": page, "pageSize": page_size, "counts": counts,
            "units": sorted(units)}


def badge(engine: sa.engine.Engine, tenant: str, user: str, st: dict[str, Any], hr: bool) -> dict[str, int]:
    now = _now()
    with engine.connect() as c:
        base = [MESSAGES.c.tenant_id == tenant, MESSAGES.c.historical.is_(False), MESSAGES.c.assignee == user,
                MESSAGES.c.status.in_(OPEN)]
        if not hr:
            base.append(MESSAGES.c.is_hr.is_(False))
        mine = int(c.execute(sa.select(sa.func.count()).select_from(MESSAGES).where(*base)).scalar() or 0)
        overdue = int(c.execute(sa.select(sa.func.count()).select_from(MESSAGES)
                                .where(*base, MESSAGES.c.first_reply_at.is_(None), MESSAGES.c.due_at < now)).scalar() or 0)
    return {"mine": mine, "overdue": overdue}


def can_see(rules: dict[str, Any], r: Any, user: str, rights: dict[str, bool]) -> bool:
    if r.is_hr and not rights.get("hr"):
        return False
    if rights.get("all"):
        return True
    return r.assignee == user or (r.unit is not None and r.unit in user_units(rules, user))


def detail(engine: sa.engine.Engine, tenant: str, user: str, rights: dict[str, bool], st: dict[str, Any], mid: str) -> dict[str, Any]:
    rules = active_rules(engine, tenant, st)
    now = _now()
    with engine.connect() as c:
        r = _row(c, tenant, mid)
        if not can_see(rules, r, user, rights):
            raise MailError("Bu iletiyi görme yetkiniz yok." if not r.is_hr else "İş başvuruları yalnız İnsan Kaynakları'na açıktır.", 403)
        labels = _all_labels(c, tenant)
        out = _out(r, labels, st, now)
        out["events"] = [{"action": e.action, "label": EVENT_LABELS.get(e.action, e.action), "by": e.by, "at": _iso(e.at),
                          "detail": _j(e.detail_json)}
                         for e in c.execute(sa.select(EVENTS).where(EVENTS.c.message_id == r.id).order_by(EVENTS.c.at))]
        prev_cond = [MESSAGES.c.tenant_id == tenant, MESSAGES.c.from_addr_hash == r.from_addr_hash, MESSAGES.c.id != r.id,
                     *_scope(rules, user, rights)]
        out["previous"] = [{"id": p.id, "receivedAt": _iso(p.received_at), "subject": p.subject,
                            "category": labels.get(p.category or "", p.category), "status": STATUSES.get(p.status, p.status)}
                           for p in c.execute(sa.select(MESSAGES.c.id, MESSAGES.c.received_at, MESSAGES.c.subject,
                                                        MESSAGES.c.category, MESSAGES.c.status)
                                              .where(*prev_cond).order_by(MESSAGES.c.received_at.desc()))]
        a = c.execute(sa.select(APPLICATIONS).where(APPLICATIONS.c.message_id == r.id)).first()
        out["application"] = _app_out(a) if a else None
        out["provider"], out["providerId"], out["threadId"] = r.provider, r.provider_id, r.thread_id
    cat = _cat(rules, r.category)
    out["role"] = cat["role"] if cat else None
    out["templates"] = [t for t in rules.get("templates") or [] if t["category"] == r.category]
    return out


def _app_out(a: Any) -> dict[str, Any]:
    return {"messageId": a.message_id, "authorName": a.author_name, "workTitle": a.work_title, "genre": a.genre,
            "pageEstimate": a.page_estimate, "attachments": _j(a.attachments_json, []) or [], "status": a.status,
            "intakeRef": a.intake_ref, "intakeNo": a.intake_no, "crmProjectId": a.crm_project_id,
            "dropped": (_j(a.evidence_json, {}) or {}).get("dusen") or [], "createdAt": _iso(a.created_at),
            "updatedBy": a.updated_by, "updatedAt": _iso(a.updated_at)}


# ------------------------------------------------------------------------------------------------ yazma (ekran)


def _visible_row(c: Any, engine: Any, tenant: str, user: str, rights: dict[str, bool], rules: dict[str, Any], mid: str) -> Any:
    r = _row(c, tenant, mid)
    if not can_see(rules, r, user, rights):
        raise MailError("Bu iletiyi görme yetkiniz yok.", 403)
    if r.historical:
        raise MailError("Geçmiş ileti yalnız etiketleme içindir; işlem yapılmaz.", 409)
    return r


def assign(engine: sa.engine.Engine, tenant: str, user: str, rights: dict[str, bool], st: dict[str, Any], mid: str,
           body: dict[str, Any], hr_ok: Callable[[str], bool]) -> dict[str, Any]:
    """Atama ya da atamayı kaldırma (assignee boş). İş başvurusu yalnız İK yetkisi olan kişiye atanır."""
    rules = active_rules(engine, tenant, st)
    who = _opt_user(body.get("assignee"), "Atanan kişi")
    unit = str(body.get("unit") or "").strip()[:120] or None
    with engine.begin() as c:
        r = _visible_row(c, engine, tenant, user, rights, rules, mid)
        if r.status in DONE:
            raise MailError("Kapanmış ya da arşivdeki ileti atanmaz; önce yeniden açın.", 409)
        if who and r.is_hr and not hr_ok(who):
            raise MailError("İş başvurusu yalnız İnsan Kaynakları yetkisi olan kişiye atanır.", 409)
        if who and not unit:
            route = _route_for(rules, r.category)
            if who in {route.get("primary"), route.get("backup"), route.get("manager")}:
                unit = route.get("unit")
            elif who == r.assignee:
                unit = r.unit
            else:
                # Tür henüz belli değilse (sınıflanmamış ileti) kişinin tek birimi varsa o birim; birden çok birimi
                # varsa birim boş kalır, ileti yalnız atanan kişiye görünür.
                own = user_units(rules, who)
                if len(own) == 1:
                    unit = next(iter(own))
        status = r.status if r.status == "yanitlandi" else ("atandi" if who else "yeni")
        c.execute(sa.update(MESSAGES).where(MESSAGES.c.id == r.id)
                  .values(assignee=who, unit=unit if who else None, status=status, updated_at=_now()))
        _event(c, tenant, r.id, "atandi", user, {"onceki": r.assignee, "kime": who, "birim": unit,
                                                 "oneriyleAyni": bool(who and who == r.suggested_assignee)})
    return {"id": mid, "assignee": who, "unit": unit if who else None, "status": status, "previous": r.assignee}


def set_category(engine: sa.engine.Engine, tenant: str, user: str, rights: dict[str, bool], st: dict[str, Any], mid: str,
                 key: str) -> dict[str, Any]:
    """İnsan türü düzeltir. Düzeltme kayda geçer (doğruluk ölçümü); modelin ilk seçimi `model_category`'de kalır."""
    rules = active_rules(engine, tenant, st)
    cat = _cat(rules, str(key or "").strip())
    if not cat or not cat["enabled"]:
        raise MailError("Tür yürürlükteki listede yok.")
    route = _route_for(rules, cat["key"])
    with engine.begin() as c:
        r = _visible_row(c, engine, tenant, user, rights, rules, mid)
        # İK dışındaki kişi iletiyi «İş başvurusu» yapabilir; sonra kendisi göremez (bilerek: yanlış kutudaki özgeçmiş).
        vals: dict[str, Any] = dict(category=cat["key"], category_source="insan", unsure=False, is_hr=cat["role"] == "ik",
                                    suggested_unit=route.get("unit"), suggested_assignee=route.get("primary") or route.get("backup"),
                                    updated_at=_now(), due_at=add_business_hours(r.received_at, _sla_for(rules, cat["key"], st)[0],
                                                                                 st["calendar"]))
        if cat["role"] == "ik" and r.assignee:
            vals.update(assignee=None, unit=None, status="yeni" if r.status == "atandi" else r.status)
        c.execute(sa.update(MESSAGES).where(MESSAGES.c.id == r.id).values(**vals))
        _event(c, tenant, r.id, "tur-duzeltildi", user, {"onceki": r.category, "yeni": cat["key"], "model": r.model_category,
                                                         "modelOlasilik": r.model_prob, "eminDegildi": bool(r.unsure)})
        if cat["role"] == "basvuru" and not c.execute(sa.select(APPLICATIONS.c.message_id).where(APPLICATIONS.c.message_id == r.id)).first():
            c.execute(APPLICATIONS.insert().values(message_id=r.id, tenant_id=tenant, status="yeni",
                                                   attachments_json=r.attachments_json, created_at=_now()))
    return {"id": mid, "category": cat["key"], "categoryLabel": cat["label"], "isHr": cat["role"] == "ik",
            "suggestedAssignee": vals["suggested_assignee"], "suggestedUnit": vals["suggested_unit"]}


def set_status(engine: sa.engine.Engine, tenant: str, user: str, rights: dict[str, bool], st: dict[str, Any], mid: str,
               status: str, note: str = "") -> dict[str, Any]:
    rules = active_rules(engine, tenant, st)
    if status not in STATUSES:
        raise MailError("Durum geçerli değil.")
    with engine.begin() as c:
        r = _visible_row(c, engine, tenant, user, rights, rules, mid)
        if status == r.status:
            return {"id": mid, "status": status}
        if status not in TRANSITIONS.get(r.status, set()):
            raise MailError(f"«{STATUSES[r.status]}» durumundan «{STATUSES[status]}» durumuna geçilmez.", 409)
        if status == "atandi" and not r.assignee:
            raise MailError("Önce bir kişiye atayın.", 409)
        vals: dict[str, Any] = {"status": status, "updated_at": _now()}
        if status == "kapandi":
            vals["closed_at"] = _now()
        elif status in OPEN:
            vals["closed_at"] = None
        if status == "yanitlandi" and r.first_reply_at is None:
            vals["first_reply_at"] = _now()          # kutu dışından (kişinin kendi adresinden) yanıt: insan beyanı
        c.execute(sa.update(MESSAGES).where(MESSAGES.c.id == r.id).values(**vals))
        action = {"kapandi": "kapandi", "arsiv": "arsivlendi", "yanitlandi": "yanitlandi"}.get(status, "durum")
        _event(c, tenant, r.id, action, user, {"onceki": r.status, "yeni": status, "not": note[:500] or None,
                                               "beyan": status == "yanitlandi" or None})
    return {"id": mid, "status": status, "previous": r.status}


def update_application(engine: sa.engine.Engine, tenant: str, user: str, rights: dict[str, bool], st: dict[str, Any], mid: str,
                       body: dict[str, Any]) -> dict[str, Any]:
    rules = active_rules(engine, tenant, st)
    vals: dict[str, Any] = {}
    for k, col, n in (("authorName", "author_name", 300), ("workTitle", "work_title", 300), ("genre", "genre", 120)):
        if k in body:
            vals[col] = str(body.get(k) or "").strip()[:n] or None
    if "pageEstimate" in body:
        raw = str(body.get("pageEstimate") or "").strip()
        if raw and (not raw.isdigit() or not 1 <= int(raw) <= 20000):
            raise MailError("Sayfa tahmini 1–20000 arası bir sayı olmalı.")
        vals["page_estimate"] = int(raw) if raw else None
    if "status" in body:
        s = str(body.get("status") or "")
        if s not in ("yeni", "reddedildi"):
            raise MailError("Başvuru durumu yalnız «yeni» ya da «reddedildi» yapılabilir; aktarım ayrı adımdır.")
        vals["status"] = s
    with engine.begin() as c:
        r = _visible_row(c, engine, tenant, user, rights, rules, mid)
        a = c.execute(sa.select(APPLICATIONS).where(APPLICATIONS.c.message_id == r.id)).first()
        if a is None:
            raise MailError("Bu ileti dosya başvurusu olarak işaretli değil.", 404)
        if a.status == "aktarildi":
            raise MailError("Aktarılmış başvuru burada değişmez; yazar giriş sürecinde düzenleyin.", 409)
        c.execute(sa.update(APPLICATIONS).where(APPLICATIONS.c.message_id == r.id)
                  .values(updated_by=user, updated_at=_now(), **vals))
        _event(c, tenant, r.id, "basvuru", user, {"alanlar": sorted(vals)})
        return _app_out(c.execute(sa.select(APPLICATIONS).where(APPLICATIONS.c.message_id == r.id)).first())


def mark_transferred(engine: sa.engine.Engine, tenant: str, user: str, mid: str, target: str, ref: Optional[str],
                     no: Optional[str]) -> None:
    with engine.begin() as c:
        if target == "yazar-giris":
            c.execute(sa.update(APPLICATIONS).where(APPLICATIONS.c.message_id == mid)
                      .values(status="aktarildi", intake_ref=ref, intake_no=no, updated_by=user, updated_at=_now()))
        _event(c, tenant, mid, "aktarildi", user, {"hedef": target, "kayit": ref, "no": no})


def applications(engine: sa.engine.Engine, tenant: str, status: str = "yeni") -> dict[str, Any]:
    """Sözleşme ucu (yazar giriş süreci ekranı okur): e-postayla gelen dosya başvuruları. Geçmiş iletiler girmez."""
    cond = [APPLICATIONS.c.tenant_id == tenant, MESSAGES.c.historical.is_(False)]
    if status:
        if status not in ("yeni", "aktarildi", "reddedildi"):
            raise MailError("Durum geçerli değil.")
        cond.append(APPLICATIONS.c.status == status)
    j = APPLICATIONS.join(MESSAGES, MESSAGES.c.id == APPLICATIONS.c.message_id)
    with engine.connect() as c:
        rows = c.execute(sa.select(APPLICATIONS, MESSAGES.c.received_at, MESSAGES.c.from_display, MESSAGES.c.from_masked,
                                   MESSAGES.c.subject, MESSAGES.c.summary, MESSAGES.c.assignee)
                         .select_from(j).where(*cond).order_by(MESSAGES.c.received_at.desc()))
        items = [{**_app_out(r), "receivedAt": _iso(r.received_at), "fromName": r.from_display, "fromMasked": r.from_masked,
                  "subject": r.subject, "summary": r.summary, "assignee": r.assignee} for r in rows]
    return {"items": items, "total": len(items)}


# ------------------------------------------------------------------------------------------------ SLA


def sla_due(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], now: Optional[datetime] = None) -> list[dict[str, Any]]:
    """Seviyesi gelmiş bildirimler: [{id, level, recipients(users), subject, isHr, elapsedH, category}]. Her seviye bir
    kez; yazma `mark_sla` ile. Geçmiş iletiler, yanıtlanmış ve kapanmış iletiler girmez."""
    now = now or _now()
    rules = active_rules(engine, tenant, st)
    out: list[dict[str, Any]] = []
    with engine.connect() as c:
        labels = _all_labels(c, tenant)
        rows = c.execute(sa.select(MESSAGES).where(MESSAGES.c.tenant_id == tenant, MESSAGES.c.historical.is_(False),
                                                   MESSAGES.c.status.in_(OPEN), MESSAGES.c.first_reply_at.is_(None),
                                                   MESSAGES.c.top_sent_at.is_(None)))
        for r in rows:
            cat = _cat(rules, r.category)
            if cat and cat["role"] == "spam":
                continue
            remind_h, esc_h, top_h = _sla_for(rules, r.category, st)
            elapsed = business_hours_between(r.received_at, now, st["calendar"])
            route = _route_for(rules, r.category)
            level = None
            if elapsed >= top_h and r.top_sent_at is None:
                level, users = "ust", st["topManagers"]
            elif elapsed >= esc_h and r.escalate_sent_at is None:
                level, users = "eskalasyon", [u for u in [route.get("manager")] if u] or st["inboxOwners"]
            elif elapsed >= remind_h and r.remind_sent_at is None:
                level, users = "hatirlatma", [r.assignee] if r.assignee else (
                    [u for u in [route.get("primary") or route.get("backup")] if u] or st["inboxOwners"])
            if level:
                out.append({"id": r.id, "level": level, "users": list(dict.fromkeys(users)), "subject": r.subject,
                            "isHr": bool(r.is_hr), "elapsedH": round(elapsed, 1), "assignee": r.assignee,
                            "category": labels.get(r.category or "", r.category or "türü belirsiz")})
    return out


def mark_sla(engine: sa.engine.Engine, tenant: str, mid: str, level: str, detail: dict[str, Any]) -> None:
    col = {"hatirlatma": "remind_sent_at", "eskalasyon": "escalate_sent_at", "ust": "top_sent_at"}[level]
    now = _now()
    with engine.begin() as c:
        vals: dict[str, Any] = {col: now}
        # Üst seviyeye atlanırsa alttakiler de gönderilmiş sayılır (aynı bildirimi geriye dönük yollamayız).
        if level in ("eskalasyon", "ust"):
            vals.setdefault("remind_sent_at", now)
        if level == "ust":
            vals.setdefault("escalate_sent_at", now)
        c.execute(sa.update(MESSAGES).where(MESSAGES.c.id == mid)
                  .values(**{k: sa.func.coalesce(getattr(MESSAGES.c, k), v) for k, v in vals.items()}))
        _event(c, tenant, mid, "hatirlatma" if level == "hatirlatma" else "eskalasyon", "sistem", {"seviye": level, **detail})


# ------------------------------------------------------------------------------------------------ rapor


def report(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], start: date, end: date) -> dict[str, Any]:
    """[start, end] (İstanbul günleri) aralığında gelen iletiler: tür bazında hacim, ilk yanıt ve kapanış süresi (duvar
    saati ve iş saati), SLA uyumu, birim/kişi dağılımı, haftalık hacim, emin olunmayan payı, tür düzeltme oranı. Rakamlar
    yalnız kayıttan; model yorum yazmaz."""
    if end < start:
        raise MailError("Bitiş başlangıçtan önce olamaz.")
    a = datetime(start.year, start.month, start.day, tzinfo=TZ).astimezone(timezone.utc)
    b = datetime(end.year, end.month, end.day, tzinfo=TZ).astimezone(timezone.utc) + timedelta(days=1)
    rules = active_rules(engine, tenant, st)
    now = _now()
    with engine.connect() as c:
        labels = _all_labels(c, tenant)
        rows = list(c.execute(sa.select(MESSAGES).where(MESSAGES.c.tenant_id == tenant, MESSAGES.c.historical.is_(False),
                                                        MESSAGES.c.received_at >= a, MESSAGES.c.received_at < b)))
        corrected = {e[0] for e in c.execute(sa.select(EVENTS.c.message_id).where(
            EVENTS.c.tenant_id == tenant, EVENTS.c.action == "tur-duzeltildi", EVENTS.c.at >= a))}
    by_cat: dict[str, dict[str, Any]] = {}
    by_person: dict[tuple[str, str], dict[str, Any]] = {}
    weekly: dict[str, int] = {}
    for r in rows:
        key = r.category or "-"
        cat = _cat(rules, r.category)
        spam = bool(cat and cat["role"] == "spam")
        d = by_cat.setdefault(key, {"category": key, "label": labels.get(key, "Türü belirsiz" if key == "-" else key), "n": 0,
                                    "replied": 0, "closed": 0, "open": 0, "overdue": 0, "slaMet": 0, "slaDue": 0,
                                    "_wall": [], "_biz": [], "_close": [], "spam": spam})
        d["n"] += 1
        remind_h = _sla_for(rules, r.category, st)[0]
        if r.first_reply_at is not None:
            d["replied"] += 1
            wall = (_aware(r.first_reply_at) - _aware(r.received_at)).total_seconds() / 3600
            biz = business_hours_between(r.received_at, r.first_reply_at, st["calendar"])
            d["_wall"].append(wall)
            d["_biz"].append(biz)
            d["slaDue"] += 1
            d["slaMet"] += int(biz <= remind_h)
        elif r.status in OPEN and r.due_at is not None and _aware(r.due_at) < now:
            d["slaDue"] += 1
            d["overdue"] += 1
        if r.status in OPEN:
            d["open"] += 1
        if r.closed_at is not None:
            d["closed"] += 1
            d["_close"].append(business_hours_between(r.received_at, r.closed_at, st["calendar"]))
        if r.assignee or r.unit:
            p = by_person.setdefault((r.unit or "-", r.assignee or "-"), {"unit": r.unit, "assignee": r.assignee, "n": 0,
                                                                          "open": 0, "replied": 0, "overdue": 0})
            p["n"] += 1
            p["open"] += int(r.status in OPEN)
            p["replied"] += int(r.first_reply_at is not None)
            p["overdue"] += int(r.status in OPEN and r.first_reply_at is None and r.due_at is not None and _aware(r.due_at) < now)
        wk = _aware(r.received_at).astimezone(TZ).date()
        wk = (wk - timedelta(days=wk.weekday())).isoformat()
        weekly[wk] = weekly.get(wk, 0) + 1

    def avg(xs: list[float]) -> Optional[float]:
        return round(sum(xs) / len(xs), 1) if xs else None

    cats = []
    for d in sorted(by_cat.values(), key=lambda x: -x["n"]):
        cats.append({k: v for k, v in d.items() if not k.startswith("_")} |
                    {"avgFirstReplyH": avg(d["_wall"]), "avgFirstReplyBizH": avg(d["_biz"]), "avgCloseBizH": avg(d["_close"]),
                     "slaRate": round(d["slaMet"] / d["slaDue"], 4) if d["slaDue"] else None})
    classified = [r for r in rows if r.category_source in ("model", "insan") or r.unsure]
    total_due = sum(d["slaDue"] for d in by_cat.values())
    return {
        "start": start.isoformat(), "end": end.isoformat(), "total": len(rows),
        "replied": sum(1 for r in rows if r.first_reply_at is not None),
        "slaRate": round(sum(d["slaMet"] for d in by_cat.values()) / total_due, 4) if total_due else None,
        "unsureRate": round(sum(1 for r in rows if r.unsure) / len(rows), 4) if rows else None,
        "correctedRate": round(sum(1 for r in rows if r.id in corrected) / len(classified), 4) if classified else None,
        "categories": cats, "people": sorted(by_person.values(), key=lambda x: -x["n"]),
        "weekly": [{"week": k, "n": v} for k, v in sorted(weekly.items())],
        "businessHours": st["businessHours"],
    }


# ------------------------------------------------------------------------------------------------ etiketleme


def labeling(engine: sa.engine.Engine, tenant: str, user: str, rights: dict[str, bool], st: dict[str, Any], *,
             page: int = 0, page_size: int = 30, mine_only: bool = True) -> dict[str, Any]:
    """Etiketleme kuyruğu: kişinin henüz etiketlemediği iletiler (önce geçmiş). Modelin önerisi gösterilmez (kör
    etiketleme); doğruluk tablosu insan etiketi ile `model_category` karşılaştırmasıdır."""
    page_size = max(10, min(int(page_size or 30), 200))
    with engine.connect() as c:
        labels = _all_labels(c, tenant)
        done = sa.select(LABELS.c.message_id).where(LABELS.c.tenant_id == tenant, LABELS.c.by == user)
        cond = [MESSAGES.c.tenant_id == tenant, MESSAGES.c.id.notin_(done)]
        if not rights.get("hr"):
            cond.append(MESSAGES.c.is_hr.is_(False))
        total = int(c.execute(sa.select(sa.func.count()).select_from(MESSAGES).where(*cond)).scalar() or 0)
        rows = c.execute(sa.select(MESSAGES.c.id, MESSAGES.c.received_at, MESSAGES.c.subject, MESSAGES.c.from_display,
                                   MESSAGES.c.from_masked, MESSAGES.c.historical, MESSAGES.c.attachments_json)
                         .where(*cond).order_by(MESSAGES.c.historical.desc(), MESSAGES.c.received_at.desc())
                         .offset(max(0, int(page)) * page_size).limit(page_size))
        items = [{"id": r.id, "receivedAt": _iso(r.received_at), "subject": r.subject, "fromName": r.from_display,
                  "fromMasked": r.from_masked, "historical": bool(r.historical),
                  "attachments": [a.get("name") for a in _j(r.attachments_json, []) or []]} for r in rows]
        mine = int(c.execute(sa.select(sa.func.count()).select_from(LABELS)
                             .where(LABELS.c.tenant_id == tenant, LABELS.c.by == user)).scalar() or 0)
    return {"items": items, "total": total, "page": page, "pageSize": page_size, "labeledByMe": mine,
            "accuracy": accuracy(engine, tenant, labels)}


def accuracy(engine: sa.engine.Engine, tenant: str, labels: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """İnsan etiketi (aynı iletiye birden çok kişi etiketlediyse çoğunluk; eşitlikte en son) ile modelin ilk seçimi."""
    with engine.connect() as c:
        labels = labels or _all_labels(c, tenant)
        rows = list(c.execute(sa.select(LABELS.c.message_id, LABELS.c.category_key, LABELS.c.at, MESSAGES.c.model_category)
                              .select_from(LABELS.join(MESSAGES, MESSAGES.c.id == LABELS.c.message_id))
                              .where(LABELS.c.tenant_id == tenant).order_by(LABELS.c.at)))
    votes: dict[str, dict[str, int]] = {}
    model: dict[str, Optional[str]] = {}
    last: dict[str, str] = {}
    for r in rows:
        votes.setdefault(r.message_id, {})
        votes[r.message_id][r.category_key] = votes[r.message_id].get(r.category_key, 0) + 1
        model[r.message_id] = r.model_category
        last[r.message_id] = r.category_key
    n = agree = unscored = 0
    confusion: dict[tuple[str, str], int] = {}
    per: dict[str, dict[str, int]] = {}
    for mid, v in votes.items():
        top = max(v.values())
        human = last[mid] if list(v.values()).count(top) > 1 else max(v, key=v.get)
        m = model.get(mid)
        if m is None:
            unscored += 1
            continue
        n += 1
        agree += int(m == human)
        confusion[(human, m)] = confusion.get((human, m), 0) + 1
        p = per.setdefault(human, {"n": 0, "agree": 0})
        p["n"] += 1
        p["agree"] += int(m == human)
    return {"n": n, "agree": agree, "rate": round(agree / n, 4) if n else None, "unscored": unscored,
            "labeled": len(votes), "target": 0.90,
            "byCategory": [{"category": k, "label": labels.get(k, k), **v, "rate": round(v["agree"] / v["n"], 4)}
                           for k, v in sorted(per.items(), key=lambda x: -x[1]["n"])],
            "confusion": [{"human": h, "humanLabel": labels.get(h, h), "model": m, "modelLabel": labels.get(m, m), "n": k}
                          for (h, m), k in sorted(confusion.items(), key=lambda x: -x[1])]}


def add_label(engine: sa.engine.Engine, tenant: str, user: str, rights: dict[str, bool], st: dict[str, Any], mid: str,
              key: str) -> dict[str, Any]:
    rules = active_rules(engine, tenant, st)
    if not _cat(rules, key):
        raise MailError("Tür yürürlükteki listede yok.")
    with engine.begin() as c:
        r = _row(c, tenant, mid)
        if r.is_hr and not rights.get("hr"):
            raise MailError("İş başvuruları yalnız İnsan Kaynakları'na açıktır.", 403)
        n = c.execute(sa.update(LABELS).where(LABELS.c.message_id == r.id, LABELS.c.by == user)
                      .values(category_key=key, at=_now())).rowcount
        if not n:
            c.execute(LABELS.insert().values(message_id=r.id, by=user, tenant_id=tenant, category_key=key, at=_now()))
    return {"id": mid, "category": key}


# ------------------------------------------------------------------------------------------------ özet


def overview(engine: sa.engine.Engine, tenant: str, user: str, rights: dict[str, bool], st: dict[str, Any]) -> dict[str, Any]:
    rules = active_rules(engine, tenant, st)
    units = user_units(rules, user)
    now = _now()
    base = [MESSAGES.c.tenant_id == tenant, MESSAGES.c.historical.is_(False), *_scope(rules, user, rights)]
    with engine.connect() as c:
        counts = {v: int(c.execute(sa.select(sa.func.count()).select_from(MESSAGES)
                                   .where(*base, *_view_cond(v, user, units, now))).scalar() or 0) for v in VIEWS}
        today = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        counts["today"] = int(c.execute(sa.select(sa.func.count()).select_from(MESSAGES)
                                        .where(*base, MESSAGES.c.received_at >= today)).scalar() or 0)
        counts["pending"] = int(c.execute(sa.select(sa.func.count()).select_from(MESSAGES).where(
            MESSAGES.c.tenant_id == tenant, MESSAGES.c.classified_at.is_(None), MESSAGES.c.historical.is_(False))).scalar() or 0)
        counts["historical"] = int(c.execute(sa.select(sa.func.count()).select_from(MESSAGES).where(
            MESSAGES.c.tenant_id == tenant, MESSAGES.c.historical.is_(True))).scalar() or 0)
    return {"counts": counts, "units": sorted(units),
            "categories": [c for c in rules["categories"] if c["enabled"] and (rights.get("hr") or c["role"] != "ik")],
            "rulesVersion": rules.get("version")}
