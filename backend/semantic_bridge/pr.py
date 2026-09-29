"""M20 Basın, medya ve halkla ilişkiler: kitap başına PR dosyası, medya kişileri, gönderim takibi, yansıma kaydı.

Kayıtlar köprünün kendi tablolarındadır (`semantic_pr_*`); CRM yalnız okunur (kitap kartı, medya kişisi, 2025-06'dan
beri kullanılmayan Haber modülü arşivi, tanıtım gönderimi siparişleri — `pr_sources.py`). Bu dosya saf iş kurallarıdır:
tablo, durum makinesi, kişi birleştirme, öneri puanı, rapor derleme. Uçlar `pr_api.py`.

**PR dosyası (kit):** `taslak` → (onaya gönder) `onayda` → (onay, `ozellik:pr.onay`) `onayli` | (gerekçeyle geri)
`geri` → (düzelt, yeniden gönder) `onayda`. Gönderen onaylayamaz (iki göz). Onaylı dosyanın metni değişirse dosya
`taslak`a döner ve henüz gönderilmemiş satırların onayı düşer. `kapali` = iş bitti; kapalı dosya değişmez.
Bir kitabın aynı anda tek açık (kapalı olmayan) dosyası olur.

**Gönderim satırı:** `hazir` (listede, henüz gitmedi) → `gonderildi` → `cevap` | `haber` | `olumsuz` | `cevapsiz`.
Satır ancak onaylıysa gönderilmiş sayılabilir: dosya onaylanırken listedeki satırlar birlikte onaylanır; sonradan
eklenen satır tek başına onaylanır (ekleyen onaylayamaz). E-posta yalnız tek alıcıya, onaylı satırdan, açıkça verilen
`ozellik:pr.gonder` ile gider — toplu gönderim ucu yoktur (kullanıcı kararı 2026-09-28: otomatik dış gönderim yok).

**Medya kişisi:** CRM kişisi (anahtar `crm:<guid>`) + portal kaydı (anahtar portal kimliği). CRM kişisine yazılan not,
etiket, «haberdar olmak istemiyor» işareti portalda bir örtü satırıdır (`crm_contact_id` dolu); CRM'e yazılmaz.
«Haberdar olmak istemiyorum» diyen kişi (`do_not_contact`) öneriye girmez ve ona e-posta gitmez (KVKK).

**Yansıma:** elle (bağlantı yapıştır), `web` (Basın ve web taramasının ilgili bulduğu kayıt; önce `aday`, insan
kabul eder) ve okunurken birleştirilen CRM Haber arşivi. Haber metni kopyalanmaz: başlık, en çok 400 karakter özet,
bağlantı. Erişim/tiraj rakamı yoktur (hiçbir kaynakta yok; uydurulmaz).
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

import sqlalchemy as sa

TZ = ZoneInfo("Europe/Istanbul")
_md = sa.MetaData()

CONTACTS = sa.Table(
    "semantic_pr_contacts", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("crm_contact_id", sa.String(40)),                        # doluysa CRM kişisinin portal örtüsü
    sa.Column("name", sa.String(200)),
    sa.Column("outlet", sa.String(200)),
    sa.Column("outlet_type", sa.String(16)),
    sa.Column("role", sa.String(120)),
    sa.Column("email", sa.String(200)),
    sa.Column("phone", sa.String(60)),
    sa.Column("topics_json", sa.Text),
    sa.Column("region", sa.String(8)),
    sa.Column("do_not_contact", sa.Boolean, nullable=False, default=False),
    sa.Column("dnc_reason", sa.String(300)),
    sa.Column("dnc_at", sa.DateTime(timezone=True)),
    sa.Column("note", sa.Text),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
    sa.UniqueConstraint("tenant_id", "crm_contact_id", name="uq_pr_contact_crm"),
)
KITS = sa.Table(
    "semantic_pr_kits", _md,
    sa.Column("id", sa.String(24), primary_key=True),                  # PR-<yıl>-<sıra>
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("crm_book_id", sa.String(40), nullable=False, index=True),
    sa.Column("stok_kodu", sa.String(60)),
    sa.Column("book_title", sa.String(400), nullable=False),
    sa.Column("author", sa.String(400)),
    sa.Column("publish_date", sa.String(10)),
    sa.Column("status", sa.String(12), nullable=False),                # taslak | onayda | onayli | geri | kapali
    sa.Column("release_national", sa.Text),
    sa.Column("release_local", sa.Text),
    sa.Column("pitch_template", sa.Text),
    sa.Column("sources_json", sa.Text),                                # alan → kaynak (crm:<alan> | m15:<id> | zeki | kullanici)
    sa.Column("draft_json", sa.Text),                                  # Zeki AI önerileri ve denetimde düşen cümleler
    sa.Column("assets_json", sa.Text),                                 # medya kiti: kapak, yazar notu, ek bağlantılar
    sa.Column("qa_json", sa.Text),                                     # röportaj soru seti (sonraki sürüm)
    sa.Column("owner", sa.String(120)),
    sa.Column("version", sa.Integer, nullable=False, default=1),
    sa.Column("submitted_by", sa.String(120)),
    sa.Column("submitted_at", sa.DateTime(timezone=True)),
    sa.Column("approved_by", sa.String(120)),
    sa.Column("approved_at", sa.DateTime(timezone=True)),
    sa.Column("reject_note", sa.Text),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)
SENDS = sa.Table(
    "semantic_pr_sends", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("kit_id", sa.String(24), nullable=False, index=True),
    sa.Column("contact_key", sa.String(48), nullable=False, index=True),
    sa.Column("contact_name", sa.String(200)),
    sa.Column("outlet", sa.String(200)),
    sa.Column("channel", sa.String(12), nullable=False),               # eposta | kargo | elden | telefon
    sa.Column("status", sa.String(12), nullable=False),
    sa.Column("pitch", sa.Text),
    sa.Column("pitch_source", sa.String(12)),                          # sablon | zeki | kullanici
    sa.Column("approved_by", sa.String(120)),
    sa.Column("approved_at", sa.DateTime(timezone=True)),
    sa.Column("sent_at", sa.DateTime(timezone=True)),
    sa.Column("follow_up_at", sa.String(10)),
    sa.Column("reminded_at", sa.DateTime(timezone=True)),
    sa.Column("crm_order_no", sa.String(60)),
    sa.Column("mail_status", sa.String(20)),
    sa.Column("mailed_at", sa.DateTime(timezone=True)),
    sa.Column("mailed_by", sa.String(120)),
    sa.Column("note", sa.Text),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
    sa.UniqueConstraint("kit_id", "contact_key", name="uq_pr_send_contact"),
)
COVERAGE = sa.Table(
    "semantic_pr_coverage", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("url", sa.String(1000)),
    sa.Column("title", sa.String(500), nullable=False),
    sa.Column("published_at", sa.String(10)),
    sa.Column("outlet", sa.String(200)),
    sa.Column("outlet_type", sa.String(16)),
    sa.Column("contact_key", sa.String(48)),
    sa.Column("crm_book_id", sa.String(40), index=True),
    sa.Column("stok_kodu", sa.String(60)),
    sa.Column("book_title", sa.String(400)),
    sa.Column("author_name", sa.String(200)),
    sa.Column("author_contact_id", sa.String(40)),
    sa.Column("kit_id", sa.String(24)),
    sa.Column("send_id", sa.String(32)),
    sa.Column("tone", sa.String(10)),                                  # olumlu | notr | olumsuz | ilgisiz
    sa.Column("tone_source", sa.String(8)),                            # zeki | elle | web
    sa.Column("tone_prob", sa.Float),
    sa.Column("source", sa.String(10), nullable=False),                # elle | web
    sa.Column("state", sa.String(12), nullable=False),                 # kayitli | aday | reddedildi
    sa.Column("web_item_id", sa.String(32)),
    sa.Column("summary", sa.String(400)),
    sa.Column("note", sa.Text),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
    sa.UniqueConstraint("tenant_id", "url", name="uq_pr_coverage_url"),
)
EVENTS = sa.Table(
    "semantic_pr_events", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("kind", sa.String(12), nullable=False),                  # kit | contact | send | coverage
    sa.Column("ref_id", sa.String(48), nullable=False, index=True),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("who", sa.String(120), nullable=False),
    sa.Column("what", sa.String(40), nullable=False),
    sa.Column("old_json", sa.Text),
    sa.Column("new_json", sa.Text),
)
JOBS = sa.Table(
    "semantic_pr_jobs", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("ref_id", sa.String(48), nullable=False, index=True),    # kit ya da yansıma kimliği
    sa.Column("kind", sa.String(12), nullable=False),                  # draft | pitch | tone
    sa.Column("status", sa.String(12), nullable=False),                # bekliyor | calisiyor | bitti | hata
    sa.Column("step", sa.String(200)),
    sa.Column("error", sa.Text),
    sa.Column("result_json", sa.Text),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("finished_at", sa.DateTime(timezone=True)),
)
META = sa.Table(
    "semantic_pr_meta", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("key", sa.String(80), primary_key=True),
    sa.Column("value_json", sa.Text, nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

OUTLET_TYPES = {"gazete": "Gazete", "dergi": "Dergi", "tv": "Televizyon", "radyo": "Radyo", "web": "İnternet sitesi",
                "podcast": "Podcast", "youtube": "Video kanalı", "ajans": "Haber ajansı", "diger": "Diğer"}
REGIONS = {"ulusal": "Ulusal", "yerel": "Yerel"}
KIT_STATUSES = {"taslak": "Taslak", "onayda": "Onay bekliyor", "onayli": "Onaylı", "geri": "Geri gönderildi", "kapali": "Kapandı"}
KIT_EDITABLE = ("taslak", "geri", "onayli")
CHANNELS = {"eposta": "E-posta", "kargo": "Kargo ile kitap", "elden": "Elden", "telefon": "Telefon"}
SEND_STATUSES = {"hazir": "Gönderilecek", "gonderildi": "Gönderildi", "cevap": "Cevap geldi", "haber": "Haber çıktı",
                 "olumsuz": "Olumsuz", "cevapsiz": "Cevapsız"}
SENT = ("gonderildi", "cevap", "haber", "olumsuz", "cevapsiz")
TONES = {"olumlu": "Olumlu", "notr": "Nötr", "olumsuz": "Olumsuz", "ilgisiz": "İlgisiz"}
COVERAGE_SOURCES = {"elle": "Elle girildi", "web": "Basın ve web taraması", "crm-arsiv": "CRM haber arşivi"}
COVERAGE_STATES = {"kayitli": "Kayıtlı", "aday": "Aday (onay bekliyor)", "reddedildi": "Reddedildi"}
FIELDS = {"national": ("release_national", "Basın bülteni (ulusal)"), "local": ("release_local", "Basın bülteni (yerel)"),
          "pitch": ("pitch_template", "Kişiye özel e-posta şablonu")}
SUMMARY_MAX = 400
PAGE = 50

_ready: set[int] = set()
_lock = threading.Lock()


class PrError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)
        _ready.add(id(engine))


# ------------------------------------------------------------------ yardımcılar


def now() -> datetime:
    return datetime.now(timezone.utc)


def today() -> date:
    return datetime.now(TZ).date()


def iso(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()


def local_day(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).astimezone(TZ).date().isoformat()


def loads(v: Optional[str], default: Any) -> Any:
    try:
        return json.loads(v) if v else default
    except ValueError:
        return default


def dump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def text(v: Any, limit: int) -> Optional[str]:
    s = str(v or "").strip()
    return s[:limit] or None


def one_line(v: Any, limit: int) -> Optional[str]:
    s = " ".join(str(v or "").split())
    return s[:limit] or None


def day(v: Any, label: str) -> Optional[str]:
    if v is None or v == "":
        return None
    try:
        return date.fromisoformat(str(v)[:10]).isoformat()
    except ValueError:
        raise PrError(f"{label} YYYY-AA-GG biçiminde olmalı.") from None


_FOLD = str.maketrans("İIıŞşĞğÜüÖöÇçÂâÎîÛû’‘`´", "iiissgguuooccaaiiuu''''")


def fold(s: Any) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", str(s or "").translate(_FOLD).lower()).split())


def short_summary(s: Any) -> Optional[str]:
    t = one_line(s, 2000)
    if not t:
        return None
    return t if len(t) <= SUMMARY_MAX else t[: SUMMARY_MAX - 1].rstrip() + "…"


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def email(v: Any) -> Optional[str]:
    s = one_line(v, 200)
    if not s:
        return None
    if not _EMAIL.match(s):
        raise PrError("E-posta adresi geçerli değil.")
    return s


def _uid() -> str:
    return uuid.uuid4().hex


def _event(c: Any, tenant: str, kind: str, ref: str, who: str, what: str, old: Any = None, new: Any = None) -> None:
    c.execute(EVENTS.insert().values(id=_uid(), tenant_id=tenant, kind=kind, ref_id=str(ref)[:48], at=now(),
                                     who=(who or "sistem")[:120], what=what[:40],
                                     old_json=None if old is None else dump(old)[:20000],
                                     new_json=None if new is None else dump(new)[:20000]))


def events_stmt(tenant: str, ref: str):
    return sa.select(EVENTS).where(EVENTS.c.tenant_id == tenant, EVENTS.c.ref_id == ref).order_by(EVENTS.c.at.desc())


def events(engine: sa.engine.Engine, tenant: str, ref: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(events_stmt(tenant, ref)).all()
    return [{"at": iso(r.at), "who": r.who, "what": r.what, "old": loads(r.old_json, None), "new": loads(r.new_json, None)}
            for r in rows]


def meta_get(engine: sa.engine.Engine, tenant: str, key: str) -> dict[str, Any]:
    with engine.connect() as c:
        row = c.execute(sa.select(META).where(META.c.tenant_id == tenant, META.c.key == key)).first()
    return {**loads(row.value_json, {}), "_at": iso(row.updated_at)} if row else {}


def meta_set(engine: sa.engine.Engine, tenant: str, key: str, value: dict[str, Any]) -> None:
    with engine.begin() as c:
        cond = (META.c.tenant_id == tenant, META.c.key == key)
        if c.execute(sa.select(META.c.key).where(*cond)).first():
            c.execute(META.update().where(*cond).values(value_json=dump(value), updated_at=now()))
        else:
            c.execute(META.insert().values(tenant_id=tenant, key=key, value_json=dump(value), updated_at=now()))


# ------------------------------------------------------------------ ayarlar


def settings(conf: Callable[[str], str]) -> dict[str, Any]:
    def num(key: str, default: float) -> float:
        try:
            v = float(str(conf(key) or "").replace(",", "."))
            return v if v >= 0 else default
        except ValueError:
            return default

    def lst(key: str) -> list[str]:
        return [x.strip() for x in str(conf(key) or "").split(",") if x.strip()]

    weekday = int(num("PR_REPORT_WEEKDAY", 1))
    return {
        "followUpDays": int(num("PR_FOLLOW_UP_DAYS", 5)) or 5,
        "recipients": lst("PR_ALERT_RECIPIENTS"),
        "reportRecipients": lst("PR_REPORT_RECIPIENTS") or lst("PR_ALERT_RECIPIENTS"),
        "reportWeekday": weekday if 1 <= weekday <= 7 else 1,          # 1 = pazartesi … 7 = pazar
        "crmRoles": lst("PR_CRM_MEDIA_ROLES"),                         # CRM «Kişi Rolü» adları (ölçülecek)
        "toneMinProb": num("PR_TONE_MIN_PROB", 0.6),
        "toneMinMargin": num("PR_TONE_MIN_MARGIN", 0.2),
        "claims": lst("MARKETING_BANNED_CLAIMS"),
        "webWatch": str(conf("WEB_WATCH_ENABLED") or "0").strip().lower() in ("1", "true", "evet", "on"),
    }


# ------------------------------------------------------------------ medya kişileri


def crm_key(guid: str) -> str:
    return f"crm:{str(guid).lower()}"


def split_key(key: str) -> tuple[Optional[str], Optional[str]]:
    """(crm guid, portal kimliği)."""
    k = str(key or "").strip()
    if k.startswith("crm:"):
        return k[4:].lower() or None, None
    return None, (k[:32] or None)


def _topics(v: Any) -> list[str]:
    if v is None:
        return []
    items = v if isinstance(v, list) else str(v).split(",")
    out: list[str] = []
    for x in items:
        t = one_line(x, 60)
        if t and t.lower() not in {o.lower() for o in out}:
            out.append(t)
    return out


def _clean_contact(body: dict[str, Any], *, partial: bool) -> dict[str, Any]:
    vals: dict[str, Any] = {}
    if "name" in body or not partial:
        n = one_line(body.get("name"), 200)
        if not n and not partial:
            raise PrError("Kişinin adı gerekli.")
        vals["name"] = n
    if "outlet" in body:
        vals["outlet"] = one_line(body.get("outlet"), 200)
    if "outletType" in body:
        t = str(body.get("outletType") or "") or None
        if t and t not in OUTLET_TYPES:
            raise PrError("Mecra türü tanınmıyor.")
        vals["outlet_type"] = t
    if "role" in body:
        vals["role"] = one_line(body.get("role"), 120)
    if "email" in body:
        vals["email"] = email(body.get("email"))
    if "phone" in body:
        vals["phone"] = one_line(body.get("phone"), 60)
    if "topics" in body:
        vals["topics_json"] = dump(_topics(body.get("topics")))
    if "region" in body:
        r = str(body.get("region") or "") or None
        if r and r not in REGIONS:
            raise PrError("Bölge ulusal ya da yerel olmalı.")
        vals["region"] = r
    if "note" in body:
        vals["note"] = text(body.get("note"), 4000)
    if "doNotContact" in body:
        vals["do_not_contact"] = bool(body.get("doNotContact"))
        vals["dnc_reason"] = one_line(body.get("dncReason"), 300) if vals["do_not_contact"] else None
        vals["dnc_at"] = now() if vals["do_not_contact"] else None
    return vals


def overlays_stmt(tenant: str):
    return sa.select(CONTACTS).where(CONTACTS.c.tenant_id == tenant)


def overlays(engine: sa.engine.Engine, tenant: str) -> list[Any]:
    with engine.connect() as c:
        return c.execute(overlays_stmt(tenant)).all()


def merge_contacts(crm_rows: Iterable[dict[str, Any]], rows: Iterable[Any]) -> list[dict[str, Any]]:
    """CRM medya kişileri + portal kayıtları tek listede. Portal örtüsündeki dolu alan CRM'dekini ezer; CRM'de
    «E-postaya izin verme» işaretliyse kişi iletişim dışıdır (örtü kaldıramaz)."""
    over = {r.crm_contact_id.lower(): r for r in rows if r.crm_contact_id}
    out: list[dict[str, Any]] = []
    for c in crm_rows:
        o = over.get(str(c["id"]).lower())
        out.append(_contact(c, o))
    for r in rows:
        if not r.crm_contact_id:
            out.append(_contact(None, r))
    return out


def _contact(c: Optional[dict[str, Any]], o: Any) -> dict[str, Any]:
    def pick(field: str, crm_val: Any) -> Any:
        v = getattr(o, field) if o is not None else None
        return v if v not in (None, "") else crm_val

    crm_dnc = bool(c and c.get("epostaYok"))
    dnc = crm_dnc or bool(o is not None and o.do_not_contact)
    return {
        "key": crm_key(c["id"]) if c else o.id,
        "source": "crm" if c else "portal",
        "crmContactId": str(c["id"]).lower() if c else None,
        "name": pick("name", c.get("ad") if c else None) or "—",
        "outlet": pick("outlet", (c.get("mecra") or c.get("kurum")) if c else None),
        "outletType": pick("outlet_type", None),
        "role": pick("role", c.get("unvan") if c else None),
        "email": pick("email", c.get("eposta") if c else None),
        "phone": pick("phone", c.get("telefon") if c else None),
        "topics": loads(o.topics_json, []) if o is not None else [],
        "region": o.region if o is not None else None,
        "doNotContact": dnc,
        "dncReason": ("CRM'de «E-postaya izin verme» işaretli." if crm_dnc else None) or (o.dnc_reason if o is not None else None),
        "note": o.note if o is not None else None,
        "crm": {"mecra": c.get("mecra"), "kurum": c.get("kurum"), "unvan": c.get("unvan"), "iys": c.get("iys"),
                "topluEpostaYok": c.get("topluYok"), "haberSayisi": c.get("haberSayisi", 0)} if c else None,
        "hasOverlay": o is not None and c is not None,
        "updatedAt": iso(o.updated_at) if o is not None else None,
    }


def find_contact(contacts: list[dict[str, Any]], key: str) -> dict[str, Any]:
    for c in contacts:
        if c["key"] == key:
            return c
    raise PrError("Medya kişisi bulunamadı.", 404)


def create_contact(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any]) -> str:
    vals = _clean_contact(body, partial=False)
    cid = _uid()
    with engine.begin() as c:
        c.execute(CONTACTS.insert().values(id=cid, tenant_id=tenant, crm_contact_id=None, created_by=user, created_at=now(),
                                           updated_by=user, updated_at=now(), **{"do_not_contact": False, **vals}))
        _event(c, tenant, "contact", cid, user, "olusturuldu", None, {k: v for k, v in vals.items() if k != "dnc_at"})
    return cid


def update_contact(engine: sa.engine.Engine, tenant: str, user: str, key: str, body: dict[str, Any],
                   crm_known: Callable[[str], bool]) -> str:
    """Portal kaydı güncellenir; CRM kişisi için örtü satırı açılır ya da güncellenir. Dönen: kişinin anahtarı."""
    vals = _clean_contact(body, partial=True)
    if not vals:
        raise PrError("Değiştirilecek alan yok.")
    guid, pid = split_key(key)
    if pid and "name" in vals and not vals["name"]:
        raise PrError("Kişinin adı boş olamaz.")
    with engine.begin() as c:
        if guid:
            if not crm_known(guid):
                raise PrError("Bu CRM kişisi medya kişileri arasında değil.", 404)
            row = c.execute(sa.select(CONTACTS).where(CONTACTS.c.tenant_id == tenant, CONTACTS.c.crm_contact_id == guid)).first()
            if row is None:
                oid = _uid()
                c.execute(CONTACTS.insert().values(id=oid, tenant_id=tenant, crm_contact_id=guid, created_by=user, created_at=now(),
                                                   updated_by=user, updated_at=now(), **{"do_not_contact": False, **vals}))
                _event(c, tenant, "contact", key, user, "ortu", None, {k: v for k, v in vals.items() if k != "dnc_at"})
                return key
        else:
            row = c.execute(sa.select(CONTACTS).where(CONTACTS.c.tenant_id == tenant, CONTACTS.c.id == pid)).first()
            if row is None:
                raise PrError("Medya kişisi bulunamadı.", 404)
        old = {k: getattr(row, k) for k in vals if k != "dnc_at"}
        c.execute(CONTACTS.update().where(CONTACTS.c.id == row.id).values(updated_by=user, updated_at=now(), **vals))
        _event(c, tenant, "contact", key, user, "duzenlendi", old, {k: v for k, v in vals.items() if k != "dnc_at"})
    return key


def delete_contact(engine: sa.engine.Engine, tenant: str, user: str, key: str) -> dict[str, Any]:
    """Yalnız portalda açılmış ve hiç gönderim/yansıma bağı olmayan kişi silinir; bağı olan kişi «haberdar olmak
    istemiyor» diye işaretlenir (geçmiş kaydı bozulmasın). CRM kişisi silinmez; örtüsü kaldırılabilir."""
    guid, pid = split_key(key)
    with engine.begin() as c:
        used = c.execute(sa.select(sa.func.count()).select_from(SENDS).where(SENDS.c.tenant_id == tenant, SENDS.c.contact_key == key)).scalar() \
            + c.execute(sa.select(sa.func.count()).select_from(COVERAGE).where(COVERAGE.c.tenant_id == tenant, COVERAGE.c.contact_key == key)).scalar()
        if guid:
            row = c.execute(sa.select(CONTACTS).where(CONTACTS.c.tenant_id == tenant, CONTACTS.c.crm_contact_id == guid)).first()
            if row is None:
                raise PrError("Bu CRM kişisinin portal notu yok; CRM kaydı buradan silinmez.", 409)
        else:
            row = c.execute(sa.select(CONTACTS).where(CONTACTS.c.tenant_id == tenant, CONTACTS.c.id == pid)).first()
            if row is None:
                raise PrError("Medya kişisi bulunamadı.", 404)
            if used:
                raise PrError("Kişinin gönderim ya da yansıma kaydı var; silmek yerine «haberdar olmak istemiyor» işaretleyin.", 409)
        c.execute(CONTACTS.delete().where(CONTACTS.c.id == row.id))
        _event(c, tenant, "contact", key, user, "silindi", {"name": row.name}, None)
    return {"key": key, "name": row.name}


# ------------------------------------------------------------------ PR dosyası


def next_kit_id(c: Any, tenant: str, year: int) -> str:
    prefix = f"PR-{year}-"
    ids = c.execute(sa.select(KITS.c.id).where(KITS.c.tenant_id == tenant, KITS.c.id.like(prefix + "%"))).scalars().all()
    n = max((int(i[len(prefix):]) for i in ids if i[len(prefix):].isdigit()), default=0) + 1
    return f"{prefix}{n:04d}"


def kit_stmt(tenant: str, kit_id: str):
    return sa.select(KITS).where(KITS.c.tenant_id == tenant, KITS.c.id == str(kit_id)[:24])


def kit_sends_stmt(kit_id: str):
    return sa.select(SENDS).where(SENDS.c.kit_id == kit_id).order_by(SENDS.c.created_at, SENDS.c.id)


def kit_coverage_stmt(tenant: str, kit_id: str, crm_book_id: Optional[str]):
    return sa.select(COVERAGE).where(COVERAGE.c.tenant_id == tenant, COVERAGE.c.state != "reddedildi",
                                     sa.or_(COVERAGE.c.kit_id == kit_id, COVERAGE.c.crm_book_id == crm_book_id)) \
        .order_by(sa.func.coalesce(COVERAGE.c.published_at, "").desc())


def kit_job_stmt(kit_id: str):
    return sa.select(JOBS).where(JOBS.c.ref_id == kit_id).order_by(JOBS.c.created_at.desc()).limit(1)


def _kit_row(c: Any, tenant: str, kit_id: str, *, lock: bool = False) -> Any:
    q = kit_stmt(tenant, kit_id)
    if lock and c.engine.dialect.name == "postgresql":
        q = q.with_for_update()
    r = c.execute(q).first()
    if not r:
        raise PrError("PR dosyası bulunamadı.", 404)
    return r


def kit_head(r: Any) -> dict[str, Any]:
    return {
        "id": r.id, "crmBookId": r.crm_book_id, "stokKodu": r.stok_kodu, "bookTitle": r.book_title, "author": r.author,
        "publishDate": r.publish_date, "status": r.status, "statusLabel": KIT_STATUSES.get(r.status, r.status),
        "owner": r.owner, "version": r.version, "submittedBy": r.submitted_by, "submittedAt": iso(r.submitted_at),
        "approvedBy": r.approved_by, "approvedAt": iso(r.approved_at), "rejectNote": r.reject_note,
        "createdBy": r.created_by, "createdAt": iso(r.created_at), "updatedBy": r.updated_by, "updatedAt": iso(r.updated_at),
    }


def send_dict(r: Any, today_: Optional[date] = None) -> dict[str, Any]:
    t = (today_ or today()).isoformat()
    return {
        "id": r.id, "kitId": r.kit_id, "contactKey": r.contact_key, "contactName": r.contact_name, "outlet": r.outlet,
        "channel": r.channel, "channelLabel": CHANNELS.get(r.channel, r.channel), "status": r.status,
        "statusLabel": SEND_STATUSES.get(r.status, r.status), "pitch": r.pitch, "pitchSource": r.pitch_source,
        "approved": bool(r.approved_by), "approvedBy": r.approved_by, "approvedAt": iso(r.approved_at),
        "sentAt": iso(r.sent_at), "followUpAt": r.follow_up_at,
        "overdue": r.status == "gonderildi" and bool(r.follow_up_at) and r.follow_up_at <= t,
        "remindedAt": iso(r.reminded_at), "crmOrderNo": r.crm_order_no, "mailStatus": r.mail_status,
        "mailedAt": iso(r.mailed_at), "mailedBy": r.mailed_by, "note": r.note, "createdBy": r.created_by,
        "createdAt": iso(r.created_at), "updatedAt": iso(r.updated_at),
    }


def coverage_dict(r: Any) -> dict[str, Any]:
    return {
        "id": r.id, "source": r.source, "sourceLabel": COVERAGE_SOURCES.get(r.source, r.source), "state": r.state,
        "stateLabel": COVERAGE_STATES.get(r.state, r.state), "url": r.url, "title": r.title, "publishedAt": r.published_at,
        "outlet": r.outlet, "outletType": r.outlet_type, "contactKey": r.contact_key, "crmBookId": r.crm_book_id,
        "stokKodu": r.stok_kodu, "bookTitle": r.book_title, "authorName": r.author_name, "kitId": r.kit_id, "sendId": r.send_id,
        "tone": r.tone, "toneLabel": TONES.get(r.tone or "", None), "toneSource": r.tone_source, "toneProb": r.tone_prob,
        "summary": r.summary, "note": r.note, "createdBy": r.created_by, "createdAt": iso(r.created_at),
        "readOnly": False,
    }


def kit_full(engine: sa.engine.Engine, tenant: str, kit_id: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = _kit_row(c, tenant, kit_id)
        sends = c.execute(kit_sends_stmt(r.id)).all()
        cov = c.execute(kit_coverage_stmt(tenant, r.id, r.crm_book_id)).all()
        job = c.execute(kit_job_stmt(r.id)).first()
    t = today()
    return {**kit_head(r),
            "releaseNational": r.release_national, "releaseLocal": r.release_local, "pitchTemplate": r.pitch_template,
            "sources": loads(r.sources_json, {}), "draft": loads(r.draft_json, {}), "assets": loads(r.assets_json, {}),
            "sends": [send_dict(s, t) for s in sends], "coverage": [coverage_dict(x) for x in cov],
            "job": job_dict(job) if job else None}


def list_kits_stmts(tenant: str, *, status: str = "", books: Iterable[str] | None = None,
                    include_closed: bool = True) -> Optional[tuple[Any, Any, Any]]:
    """(dosyalar, dosya başına gönderim / gönderilen sayısı, kitap başına kayıtlı yansıma); kitap süzgeci boşsa None."""
    cond = [KITS.c.tenant_id == tenant]
    if status:
        cond.append(KITS.c.status.in_([s for s in status.split(",") if s]))
    elif not include_closed:
        cond.append(KITS.c.status != "kapali")
    ids = [b.lower() for b in (books or []) if b]
    if books is not None:
        if not ids:
            return None
        cond.append(KITS.c.crm_book_id.in_(ids))
    return (sa.select(KITS).where(*cond).order_by(KITS.c.created_at.desc()),
            sa.select(SENDS.c.kit_id, sa.func.count().label("gonderim"),
                      sa.func.sum(sa.case((SENDS.c.status.in_(SENT), 1), else_=0)).label("gonderilen"))
            .where(SENDS.c.tenant_id == tenant).group_by(SENDS.c.kit_id),
            sa.select(COVERAGE.c.crm_book_id, sa.func.count().label("yansima")).where(
                COVERAGE.c.tenant_id == tenant, COVERAGE.c.state == "kayitli").group_by(COVERAGE.c.crm_book_id))


def list_kits(engine: sa.engine.Engine, tenant: str, *, status: str = "", books: Iterable[str] | None = None,
              include_closed: bool = True) -> list[dict[str, Any]]:
    q = list_kits_stmts(tenant, status=status, books=books, include_closed=include_closed)
    if q is None:
        return []
    with engine.connect() as c:
        rows = c.execute(q[0]).all()
        counts = {k: (int(n), int(s or 0)) for k, n, s in c.execute(q[1]).all()}
        cov = dict(c.execute(q[2]).all())
    out = []
    for r in rows:
        n, sent = counts.get(r.id, (0, 0))
        out.append({**kit_head(r), "sendCount": n, "sentCount": sent, "coverageCount": int(cov.get(r.crm_book_id, 0))})
    return out


def open_kit_for(engine: sa.engine.Engine, tenant: str, crm_book_id: str) -> Optional[dict[str, Any]]:
    with engine.connect() as c:
        r = c.execute(sa.select(KITS).where(KITS.c.tenant_id == tenant, KITS.c.crm_book_id == crm_book_id.lower(),
                                            KITS.c.status != "kapali").order_by(KITS.c.created_at.desc())).first()
    return kit_head(r) if r else None


def create_kit(engine: sa.engine.Engine, tenant: str, user: str, book: dict[str, Any],
               release: Optional[tuple[str, str]] = None) -> str:
    """`book`: CRM kitap kartı (kitapId, stokKodu, ad, yazar, yayinTarihi). `release`: (metin, kaynak) — M15'in onaylı
    basın bülteni ya da CRM kitap kartındaki «Basın Bülteni» alanı; yoksa boş başlar."""
    bid = str(book.get("kitapId") or "").lower()
    if not bid:
        raise PrError("Kitap kimliği gerekli.")
    with engine.begin() as c:
        open_ = c.execute(sa.select(KITS.c.id).where(KITS.c.tenant_id == tenant, KITS.c.crm_book_id == bid,
                                                     KITS.c.status != "kapali")).first()
        if open_:
            raise PrError(f"Bu kitabın açık PR dosyası var ({open_.id}); onu açın.", 409)
        kid = next_kit_id(c, tenant, today().year)
        srcs = {"national": release[1]} if release and release[0] else {}
        c.execute(KITS.insert().values(
            id=kid, tenant_id=tenant, crm_book_id=bid, stok_kodu=book.get("stokKodu"),
            book_title=one_line(book.get("ad"), 400) or book.get("stokKodu") or bid, author=one_line(book.get("yazar"), 400),
            publish_date=book.get("yayinTarihi"), status="taslak",
            release_national=release[0] if release and release[0] else None, release_local=None, pitch_template=None,
            sources_json=dump(srcs), draft_json=None, assets_json=None, owner=user, version=1,
            created_by=user, created_at=now(), updated_by=user, updated_at=now()))
        _event(c, tenant, "kit", kid, user, "olusturuldu", None, {"kitap": bid, "bulten": srcs.get("national")})
    return kid


def _drop_send_approvals(c: Any, kit_id: str) -> int:
    res = c.execute(SENDS.update().where(SENDS.c.kit_id == kit_id, SENDS.c.status == "hazir", SENDS.c.approved_by.is_not(None))
                    .values(approved_by=None, approved_at=None))
    return int(res.rowcount or 0)


def update_kit(engine: sa.engine.Engine, tenant: str, user: str, kit_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Metin alanları (ulusal/yerel bülten, e-posta şablonu), medya kiti notları, sahip. Onaylı dosyanın metni
    değişirse dosya taslağa döner, gönderilmemiş satırların onayı düşer."""
    vals: dict[str, Any] = {}
    sources_changed: dict[str, str] = {}
    for key, (col, _label) in FIELDS.items():
        name = {"national": "releaseNational", "local": "releaseLocal", "pitch": "pitchTemplate"}[key]
        if name in body:
            vals[col] = text(body.get(name), 60000)
            sources_changed[key] = str(body.get(f"{name}Source") or "kullanici")[:40] if vals[col] else ""
    if "assets" in body:
        a = body.get("assets")
        if a is not None and not isinstance(a, dict):
            raise PrError("Medya kiti bilgisi nesne olmalı.")
        vals["assets_json"] = dump(a) if a else None
    if "owner" in body:
        vals["owner"] = one_line(body.get("owner"), 120)
    if not vals:
        raise PrError("Değiştirilecek alan yok.")
    with engine.begin() as c:
        r = _kit_row(c, tenant, kit_id, lock=True)
        if r.status == "kapali":
            raise PrError("Kapalı PR dosyası değiştirilemez.", 409)
        text_change = any(col in vals and vals[col] != getattr(r, col) for col, _ in FIELDS.values())
        if text_change and r.status == "onayda":
            raise PrError("Onay bekleyen dosyanın metni değiştirilemez; önce onaydan geri çekin.", 409)
        srcs = loads(r.sources_json, {})
        for k, v in sources_changed.items():
            if v:
                srcs[k] = v
            else:
                srcs.pop(k, None)
        extra: dict[str, Any] = {"sources_json": dump(srcs)} if sources_changed else {}
        dropped = 0
        if text_change and r.status == "onayli":
            extra.update(status="taslak", approved_by=None, approved_at=None, version=r.version + 1)
            dropped = _drop_send_approvals(c, r.id)
        old = {k: (getattr(r, k) or "")[:200] if isinstance(getattr(r, k), str) else getattr(r, k) for k in vals}
        c.execute(KITS.update().where(KITS.c.id == r.id).values(updated_by=user, updated_at=now(), **vals, **extra))
        _event(c, tenant, "kit", r.id, user, "duzenlendi", old,
               {**{k: (v or "")[:200] if isinstance(v, str) else v for k, v in vals.items()},
                **({"durum": "taslak", "onayiDusenSatir": dropped} if "status" in extra else {})})
    return kit_full(engine, tenant, kit_id)


def put_draft(engine: sa.engine.Engine, tenant: str, user: str, kit_id: str, drafts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Zeki AI taslağı: alan boşsa (ya da son kaynağı Zeki AI ise ve dosya düzenlenebilirse) alana yazılır; kullanıcının
    yazdığı metin ezilmez, taslak «öneri» olarak yanında durur. Dönen: hangi alanın doldurulduğu."""
    filled: dict[str, str] = {}
    with engine.begin() as c:
        r = _kit_row(c, tenant, kit_id, lock=True)
        srcs = loads(r.sources_json, {})
        draft = loads(r.draft_json, {})
        vals: dict[str, Any] = {}
        for key, d in drafts.items():
            draft[key] = {**d, "zaman": iso(now()), "kim": user}
            if key not in FIELDS or not d.get("metin"):
                continue
            col = FIELDS[key][0]
            cur = getattr(r, col)
            if r.status in ("taslak", "geri") and (not cur or srcs.get(key) == "zeki"):
                vals[col] = d["metin"]
                srcs[key] = "zeki"
                filled[key] = "alana-yazildi"
            else:
                filled[key] = "oneri"
        c.execute(KITS.update().where(KITS.c.id == r.id).values(draft_json=dump(draft), sources_json=dump(srcs),
                                                                updated_at=now(), **vals))
        _event(c, tenant, "kit", r.id, user, "zeki-taslak", None, {k: {"sonuc": v, "dusen": (drafts.get(k) or {}).get("dusenSayisi")}
                                                                  for k, v in filled.items()})
    return filled


def submit_kit(engine: sa.engine.Engine, tenant: str, user: str, kit_id: str) -> dict[str, Any]:
    with engine.begin() as c:
        r = _kit_row(c, tenant, kit_id, lock=True)
        if r.status not in ("taslak", "geri"):
            raise PrError("Yalnız taslak ya da geri gönderilmiş dosya onaya gönderilir.", 409)
        if not (r.release_national or "").strip():
            raise PrError("Basın bülteni boş; önce bülteni yazın ya da Zeki AI taslağı alın.")
        c.execute(KITS.update().where(KITS.c.id == r.id).values(status="onayda", submitted_by=user, submitted_at=now(),
                                                                reject_note=None, updated_by=user, updated_at=now()))
        n = c.execute(sa.select(sa.func.count()).select_from(SENDS).where(SENDS.c.kit_id == r.id, SENDS.c.status == "hazir")).scalar()
        _event(c, tenant, "kit", r.id, user, "onaya-gonderildi", {"durum": r.status}, {"durum": "onayda", "gonderimListesi": int(n or 0)})
    return kit_full(engine, tenant, kit_id)


def withdraw_kit(engine: sa.engine.Engine, tenant: str, user: str, kit_id: str) -> dict[str, Any]:
    with engine.begin() as c:
        r = _kit_row(c, tenant, kit_id, lock=True)
        if r.status != "onayda":
            raise PrError("Dosya onayda değil.", 409)
        c.execute(KITS.update().where(KITS.c.id == r.id).values(status="taslak", updated_by=user, updated_at=now()))
        _event(c, tenant, "kit", r.id, user, "geri-cekildi", {"durum": "onayda"}, {"durum": "taslak"})
    return kit_full(engine, tenant, kit_id)


def decide_kit(engine: sa.engine.Engine, tenant: str, user: str, kit_id: str, approve: bool, note: Any = None) -> dict[str, Any]:
    """Onay bülteni ve o anki gönderim listesini birlikte onaylar. Gönderen onaylayamaz; geri gönderme gerekçe ister."""
    reason = text(note, 2000)
    with engine.begin() as c:
        r = _kit_row(c, tenant, kit_id, lock=True)
        if r.status != "onayda":
            raise PrError("Dosya onay beklemiyor.", 409)
        if (r.submitted_by or "").lower() == user.lower():
            raise PrError("Dosyayı onaya gönderen kişi onaylayamaz; başka bir yetkili karar vermeli.", 409)
        if approve:
            c.execute(KITS.update().where(KITS.c.id == r.id).values(status="onayli", approved_by=user, approved_at=now(),
                                                                    reject_note=None, updated_by=user, updated_at=now()))
            res = c.execute(SENDS.update().where(SENDS.c.kit_id == r.id, SENDS.c.status == "hazir", SENDS.c.approved_by.is_(None))
                            .values(approved_by=user, approved_at=now()))
            _event(c, tenant, "kit", r.id, user, "onaylandi", {"durum": "onayda"},
                   {"durum": "onayli", "onaylananSatir": int(res.rowcount or 0), "not": reason})
        else:
            if not reason:
                raise PrError("Geri gönderme gerekçesi gerekli.")
            c.execute(KITS.update().where(KITS.c.id == r.id).values(status="geri", reject_note=reason, updated_by=user, updated_at=now()))
            _event(c, tenant, "kit", r.id, user, "geri-gonderildi", {"durum": "onayda"}, {"durum": "geri", "gerekce": reason})
    return kit_full(engine, tenant, kit_id)


def close_kit(engine: sa.engine.Engine, tenant: str, user: str, kit_id: str, reopen: bool = False) -> dict[str, Any]:
    with engine.begin() as c:
        r = _kit_row(c, tenant, kit_id, lock=True)
        if reopen:
            if r.status != "kapali":
                raise PrError("Dosya kapalı değil.", 409)
            other = c.execute(sa.select(KITS.c.id).where(KITS.c.tenant_id == tenant, KITS.c.crm_book_id == r.crm_book_id,
                                                         KITS.c.status != "kapali", KITS.c.id != r.id)).first()
            if other:
                raise PrError(f"Bu kitabın açık başka bir dosyası var ({other.id}).", 409)
            new = "onayli" if r.approved_by else "taslak"
        else:
            if r.status == "kapali":
                raise PrError("Dosya zaten kapalı.", 409)
            if r.status == "onayda":
                raise PrError("Onay bekleyen dosya kapatılamaz; önce geri çekin.", 409)
            new = "kapali"
        c.execute(KITS.update().where(KITS.c.id == r.id).values(status=new, updated_by=user, updated_at=now()))
        _event(c, tenant, "kit", r.id, user, "yeniden-acildi" if reopen else "kapatildi", {"durum": r.status}, {"durum": new})
    return kit_full(engine, tenant, kit_id)


# ------------------------------------------------------------------ gönderim satırları


def fill_pitch(template: Optional[str], contact: dict[str, Any]) -> Optional[str]:
    """Şablondaki {ad} ve {mecra} yer tutucuları kişinin bilgisiyle doldurulur (kural; model değil)."""
    if not template:
        return None
    first = (contact.get("name") or "").split(" ")[0] if contact.get("name") not in (None, "—") else ""
    return (template.replace("{ad}", first or "").replace("{adsoyad}", contact.get("name") or "")
            .replace("{mecra}", contact.get("outlet") or ""))


def add_sends(engine: sa.engine.Engine, tenant: str, user: str, kit_id: str, contacts: list[dict[str, Any]],
              channel: str = "eposta") -> dict[str, Any]:
    """Kişiler listeye eklenir (her biri ayrı satır; aynı kişi iki kez eklenmez). «Haberdar olmak istemiyor»
    işaretli kişi eklenmez."""
    if channel not in CHANNELS:
        raise PrError("Kanal e-posta, kargo, elden ya da telefon olmalı.")
    if not contacts:
        raise PrError("Eklenecek kişi seçilmedi.")
    added, skipped = [], []
    with engine.begin() as c:
        r = _kit_row(c, tenant, kit_id, lock=True)
        if r.status in ("kapali", "onayda"):
            raise PrError("Kapalı ya da onay bekleyen dosyanın listesi değiştirilemez.", 409)
        have = set(c.execute(sa.select(SENDS.c.contact_key).where(SENDS.c.kit_id == r.id)).scalars().all())
        for p in contacts:
            if p["key"] in have:
                skipped.append({"key": p["key"], "name": p["name"], "neden": "listede var"})
                continue
            if p.get("doNotContact"):
                skipped.append({"key": p["key"], "name": p["name"], "neden": "haberdar olmak istemiyor"})
                continue
            sid = _uid()
            pitch = fill_pitch(r.pitch_template, p)
            c.execute(SENDS.insert().values(
                id=sid, tenant_id=tenant, kit_id=r.id, contact_key=p["key"], contact_name=one_line(p.get("name"), 200),
                outlet=one_line(p.get("outlet"), 200), channel=channel, status="hazir", pitch=pitch,
                pitch_source="sablon" if pitch else None, created_by=user, created_at=now(), updated_by=user, updated_at=now()))
            have.add(p["key"])
            added.append(sid)
        if added:
            _event(c, tenant, "kit", r.id, user, "liste-eklendi", None, {"eklenen": len(added), "atlanan": len(skipped),
                                                                         "onayGerekir": r.status == "onayli"})
    return {"added": added, "skipped": skipped}


def _send_row(c: Any, tenant: str, sid: str, *, lock: bool = False) -> Any:
    q = sa.select(SENDS).where(SENDS.c.tenant_id == tenant, SENDS.c.id == str(sid)[:32])
    if lock and c.engine.dialect.name == "postgresql":
        q = q.with_for_update()
    r = c.execute(q).first()
    if not r:
        raise PrError("Gönderim satırı bulunamadı.", 404)
    return r


def get_send(engine: sa.engine.Engine, tenant: str, sid: str) -> dict[str, Any]:
    with engine.connect() as c:
        return send_dict(_send_row(c, tenant, sid))


def update_send(engine: sa.engine.Engine, tenant: str, user: str, sid: str, body: dict[str, Any], follow_up_days: int) -> dict[str, Any]:
    """Durum (tek tık: cevap geldi / haber çıktı / olumsuz / cevapsız), kanal, not, CRM tanıtım siparişi numarası,
    kişiye özel metin. «Gönderildi» ve sonrası için satır onaylı olmalı. Metin değişirse satırın onayı düşer."""
    with engine.begin() as c:
        r = _send_row(c, tenant, sid, lock=True)
        k = _kit_row(c, tenant, r.kit_id)
        if k.status == "kapali":
            raise PrError("Kapalı dosyanın satırı değiştirilemez.", 409)
        vals: dict[str, Any] = {}
        if "status" in body:
            st = str(body.get("status") or "")
            if st not in SEND_STATUSES:
                raise PrError("Durum tanınmıyor.")
            if st != r.status:
                if st != "hazir" and not r.approved_by:
                    raise PrError("Satır onaylı değil: gönderim listesi pazarlama müdürünün onayından sonra işlenir.", 409)
                if st == "hazir" and r.status != "hazir":
                    raise PrError("Gönderilmiş satır «gönderilecek»e geri alınamaz.", 409)
                vals["status"] = st
                if st == "gonderildi" and r.sent_at is None:
                    sent = day(body.get("sentAt"), "Gönderim tarihi")
                    at = datetime.fromisoformat(sent).replace(tzinfo=TZ).astimezone(timezone.utc) if sent else now()
                    vals["sent_at"] = at
                    vals["follow_up_at"] = (at.astimezone(TZ).date() + timedelta(days=follow_up_days)).isoformat()
        if "channel" in body:
            ch = str(body.get("channel") or "")
            if ch not in CHANNELS:
                raise PrError("Kanal tanınmıyor.")
            if r.sent_at is not None and ch != r.channel:
                raise PrError("Gönderilmiş satırın kanalı değiştirilemez.", 409)
            vals["channel"] = ch
        if "note" in body:
            vals["note"] = text(body.get("note"), 4000)
        if "crmOrderNo" in body:
            vals["crm_order_no"] = one_line(body.get("crmOrderNo"), 60)
        if "followUpAt" in body:
            vals["follow_up_at"] = day(body.get("followUpAt"), "Takip tarihi")
        if "pitch" in body:
            p = text(body.get("pitch"), 20000)
            if r.sent_at is not None:
                raise PrError("Gönderilmiş satırın metni değiştirilemez.", 409)
            if p != r.pitch:
                vals.update(pitch=p, pitch_source=str(body.get("pitchSource") or "kullanici")[:12], approved_by=None, approved_at=None)
        if not vals:
            raise PrError("Değiştirilecek alan yok.")
        old = {x: getattr(r, x) for x in vals if x not in ("pitch", "sent_at")}
        c.execute(SENDS.update().where(SENDS.c.id == r.id).values(updated_by=user, updated_at=now(), **vals))
        _event(c, tenant, "send", r.id, user, "duzenlendi", old,
               {x: v for x, v in vals.items() if x not in ("pitch", "sent_at")} | ({"metin": "değişti"} if "pitch" in vals else {}))
        _event(c, tenant, "kit", r.kit_id, user, "satir", None, {"satir": r.id, "kisi": r.contact_name, **({"durum": vals["status"]} if "status" in vals else {})})
        return send_dict(c.execute(sa.select(SENDS).where(SENDS.c.id == r.id)).one())


def approve_send(engine: sa.engine.Engine, tenant: str, user: str, sid: str) -> dict[str, Any]:
    """Onaylı dosyaya sonradan eklenen satırın tek başına onayı. Satırı ekleyen ya da metnini yazan onaylayamaz."""
    with engine.begin() as c:
        r = _send_row(c, tenant, sid, lock=True)
        k = _kit_row(c, tenant, r.kit_id)
        if k.status != "onayli":
            raise PrError("Dosya onaylı değil; satırlar dosyayla birlikte onaylanır.", 409)
        if r.approved_by:
            raise PrError("Satır zaten onaylı.", 409)
        if user.lower() in {(r.created_by or "").lower(), (r.updated_by or "").lower()}:
            raise PrError("Satırı ekleyen ya da metnini değiştiren kişi onaylayamaz.", 409)
        c.execute(SENDS.update().where(SENDS.c.id == r.id).values(approved_by=user, approved_at=now()))
        _event(c, tenant, "send", r.id, user, "onaylandi", None, {"kisi": r.contact_name})
        _event(c, tenant, "kit", r.kit_id, user, "satir-onay", None, {"satir": r.id, "kisi": r.contact_name})
        return send_dict(c.execute(sa.select(SENDS).where(SENDS.c.id == r.id)).one())


def delete_send(engine: sa.engine.Engine, tenant: str, user: str, sid: str) -> dict[str, Any]:
    with engine.begin() as c:
        r = _send_row(c, tenant, sid, lock=True)
        k = _kit_row(c, tenant, r.kit_id)
        if k.status in ("kapali", "onayda"):
            raise PrError("Kapalı ya da onay bekleyen dosyanın listesi değiştirilemez.", 409)
        if r.sent_at is not None or r.status != "hazir":
            raise PrError("Gönderilmiş satır silinmez; durumunu işaretleyin.", 409)
        c.execute(SENDS.delete().where(SENDS.c.id == r.id))
        _event(c, tenant, "kit", r.kit_id, user, "liste-cikarildi", {"satir": r.id, "kisi": r.contact_name}, None)
    return {"id": r.id}


def mail_check(kit: dict[str, Any], send: dict[str, Any], contact: dict[str, Any]) -> Optional[str]:
    """E-posta gönderilebilir mi; gönderilemiyorsa nedeni (ekranda aynen görünür)."""
    if kit["status"] != "onayli":
        return "PR dosyası onaylı değil."
    if not send["approved"]:
        return "Bu satır onaylı değil."
    if send["channel"] != "eposta":
        return "Satırın kanalı e-posta değil."
    if send["mailStatus"] == "gonderildi":
        return "Bu kişiye bu dosya için e-posta zaten gönderildi."
    if contact.get("doNotContact"):
        return "Kişi haberdar olmak istemiyor; e-posta gönderilmez."
    if not contact.get("email"):
        return "Kişinin e-posta adresi yok."
    if not (send.get("pitch") or "").strip():
        return "Kişiye özel metin boş."
    return None


def record_mail(engine: sa.engine.Engine, tenant: str, user: str, sid: str, result: str, follow_up_days: int) -> dict[str, Any]:
    with engine.begin() as c:
        r = _send_row(c, tenant, sid, lock=True)
        vals: dict[str, Any] = {"mail_status": result, "mailed_at": now(), "mailed_by": user}
        if result == "gonderildi":
            vals.update(status="gonderildi" if r.status == "hazir" else r.status, sent_at=r.sent_at or now(),
                        follow_up_at=r.follow_up_at or (today() + timedelta(days=follow_up_days)).isoformat())
        c.execute(SENDS.update().where(SENDS.c.id == r.id).values(updated_by=user, updated_at=now(), **vals))
        _event(c, tenant, "send", r.id, user, "eposta", None, {"sonuc": result})
        _event(c, tenant, "kit", r.kit_id, user, "eposta", None, {"satir": r.id, "kisi": r.contact_name, "sonuc": result})
        return send_dict(c.execute(sa.select(SENDS).where(SENDS.c.id == r.id)).one())


def overdue_stmt(tenant: str, ref: Optional[date] = None):
    """Takip günü geçmiş, dönüşsüz gönderimler (kapalı dosya hariç)."""
    t = (ref or today()).isoformat()
    return sa.select(SENDS, KITS.c.book_title, KITS.c.owner).join(KITS, KITS.c.id == SENDS.c.kit_id) \
        .where(SENDS.c.tenant_id == tenant, SENDS.c.status == "gonderildi", SENDS.c.follow_up_at.is_not(None),
               SENDS.c.follow_up_at <= t, KITS.c.status != "kapali").order_by(SENDS.c.follow_up_at, SENDS.c.id)


def overdue_sends(engine: sa.engine.Engine, tenant: str, ref: Optional[date] = None) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(overdue_stmt(tenant, ref)).all()
    return [{**send_dict(r, ref), "bookTitle": r.book_title, "owner": r.owner} for r in rows]


def mark_reminded(engine: sa.engine.Engine, ids: list[str]) -> None:
    if not ids:
        return
    with engine.begin() as c:
        c.execute(SENDS.update().where(SENDS.c.id.in_(ids)).values(reminded_at=now()))


# ------------------------------------------------------------------ yansıma


def _clean_url(v: Any) -> Optional[str]:
    s = one_line(v, 1000)
    if not s:
        return None
    if not re.match(r"^https?://[^\s/]+", s, re.I):
        raise PrError("Bağlantı http:// ya da https:// ile başlamalı.")
    return s


def _link_send(c: Any, tenant: str, user: str, cov_id: str, contact_key: Optional[str], book_id: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Yansımanın kişisi ve kitabı bir gönderim satırıyla eşleşiyorsa satır «haber çıktı» olur."""
    if not contact_key or not book_id:
        return None, None
    row = c.execute(sa.select(SENDS.c.id, SENDS.c.kit_id, SENDS.c.status, SENDS.c.contact_name).join(KITS, KITS.c.id == SENDS.c.kit_id)
                    .where(SENDS.c.tenant_id == tenant, SENDS.c.contact_key == contact_key, KITS.c.crm_book_id == book_id)
                    .order_by(SENDS.c.created_at.desc())).first()
    if row is None:
        return None, None
    if row.status in ("gonderildi", "cevap", "cevapsiz"):
        c.execute(SENDS.update().where(SENDS.c.id == row.id).values(status="haber", updated_by=user, updated_at=now()))
        _event(c, tenant, "kit", row.kit_id, user, "satir", None, {"satir": row.id, "kisi": row.contact_name, "durum": "haber",
                                                                   "yansima": cov_id})
    return row.kit_id, row.id


def _clean_coverage(body: dict[str, Any], *, partial: bool) -> dict[str, Any]:
    vals: dict[str, Any] = {}
    if "url" in body:
        vals["url"] = _clean_url(body.get("url"))
    if "title" in body or not partial:
        t = one_line(body.get("title"), 500)
        if not t:
            raise PrError("Haber başlığı gerekli.")
        vals["title"] = t
    if "publishedAt" in body:
        vals["published_at"] = day(body.get("publishedAt"), "Yayın tarihi")
    if "outlet" in body:
        vals["outlet"] = one_line(body.get("outlet"), 200)
    if "outletType" in body:
        t = str(body.get("outletType") or "") or None
        if t and t not in OUTLET_TYPES:
            raise PrError("Mecra türü tanınmıyor.")
        vals["outlet_type"] = t
    if "contactKey" in body:
        vals["contact_key"] = one_line(body.get("contactKey"), 48)
    if "crmBookId" in body:
        vals["crm_book_id"] = (one_line(body.get("crmBookId"), 40) or "").lower() or None
    if "stokKodu" in body:
        vals["stok_kodu"] = one_line(body.get("stokKodu"), 60)
    if "bookTitle" in body:
        vals["book_title"] = one_line(body.get("bookTitle"), 400)
    if "authorName" in body:
        vals["author_name"] = one_line(body.get("authorName"), 200)
    if "summary" in body:
        vals["summary"] = short_summary(body.get("summary"))
    if "note" in body:
        vals["note"] = text(body.get("note"), 4000)
    if "tone" in body:
        t = str(body.get("tone") or "") or None
        if t and t not in TONES:
            raise PrError("Ton olumlu, nötr, olumsuz ya da ilgisiz olmalı.")
        vals.update(tone=t, tone_source="elle" if t else None, tone_prob=None)
    return vals


def add_coverage(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
    vals = _clean_coverage(body, partial=False)
    cid = _uid()
    with engine.begin() as c:
        if vals.get("url"):
            dup = c.execute(sa.select(COVERAGE.c.id, COVERAGE.c.state).where(COVERAGE.c.tenant_id == tenant, COVERAGE.c.url == vals["url"])).first()
            if dup:
                raise PrError("Bu bağlantı zaten kayıtlı" + (" (reddedilmiş aday)." if dup.state == "reddedildi" else "."), 409)
        kit_id, send_id = _link_send(c, tenant, user, cid, vals.get("contact_key"), vals.get("crm_book_id"))
        c.execute(COVERAGE.insert().values(id=cid, tenant_id=tenant, source="elle", state="kayitli", kit_id=kit_id, send_id=send_id,
                                           created_by=user, created_at=now(), updated_by=user, updated_at=now(), **vals))
        _event(c, tenant, "coverage", cid, user, "olusturuldu", None, {"baslik": vals["title"], "kitap": vals.get("crm_book_id"),
                                                                       "satir": send_id})
        return coverage_dict(c.execute(sa.select(COVERAGE).where(COVERAGE.c.id == cid)).one())


def _cov_row(c: Any, tenant: str, cid: str) -> Any:
    r = c.execute(sa.select(COVERAGE).where(COVERAGE.c.tenant_id == tenant, COVERAGE.c.id == str(cid)[:32])).first()
    if not r:
        raise PrError("Yansıma bulunamadı.", 404)
    return r


def update_coverage(engine: sa.engine.Engine, tenant: str, user: str, cid: str, body: dict[str, Any]) -> dict[str, Any]:
    """Alan düzeltme, ton düzeltme (insan kazanır), adayı kabul / red (`state`)."""
    vals = _clean_coverage(body, partial=True)
    if "state" in body:
        s = str(body.get("state") or "")
        if s not in COVERAGE_STATES:
            raise PrError("Durum kayıtlı, aday ya da reddedildi olmalı.")
        vals["state"] = s
    if not vals:
        raise PrError("Değiştirilecek alan yok.")
    with engine.begin() as c:
        r = _cov_row(c, tenant, cid)
        if vals.get("url") and vals["url"] != r.url:
            dup = c.execute(sa.select(COVERAGE.c.id).where(COVERAGE.c.tenant_id == tenant, COVERAGE.c.url == vals["url"],
                                                           COVERAGE.c.id != r.id)).first()
            if dup:
                raise PrError("Bu bağlantı başka bir kayıtta var.", 409)
        contact = vals.get("contact_key", r.contact_key)
        book = vals.get("crm_book_id", r.crm_book_id)
        state = vals.get("state", r.state)
        if state == "kayitli" and ("contact_key" in vals or "crm_book_id" in vals or "state" in vals) and not r.send_id:
            kit_id, send_id = _link_send(c, tenant, user, r.id, contact, book)
            if send_id:
                vals.update(kit_id=kit_id, send_id=send_id)
        old = {k: getattr(r, k) for k in vals if k in COVERAGE.c}
        c.execute(COVERAGE.update().where(COVERAGE.c.id == r.id).values(updated_by=user, updated_at=now(), **vals))
        _event(c, tenant, "coverage", r.id, user, "duzenlendi", old, vals)
        return coverage_dict(c.execute(sa.select(COVERAGE).where(COVERAGE.c.id == r.id)).one())


def delete_coverage(engine: sa.engine.Engine, tenant: str, user: str, cid: str) -> dict[str, Any]:
    with engine.begin() as c:
        r = _cov_row(c, tenant, cid)
        if r.source == "web":
            raise PrError("Taramadan gelen kayıt silinmez (tekrar aday olmasın); «reddet» ile kapatın.", 409)
        c.execute(COVERAGE.delete().where(COVERAGE.c.id == r.id))
        _event(c, tenant, "coverage", r.id, user, "silindi", {"baslik": r.title, "url": r.url}, None)
    return {"id": r.id, "title": r.title}


def set_tone(engine: sa.engine.Engine, cid: str, tone: Optional[str], prob: Optional[float]) -> bool:
    """Zeki AI sınıflaması: kullanıcı tonu elle girdiyse dokunulmaz. Emin olunamayınca ton boş, kaynak «zeki» kalır
    (bir daha denenmez; ekranda «Zeki AI emin değil, siz seçin» görünür)."""
    with engine.begin() as c:
        r = c.execute(sa.select(COVERAGE.c.tone_source).where(COVERAGE.c.id == cid)).first()
        if r is None or r.tone_source in ("elle", "web"):
            return False
        c.execute(COVERAGE.update().where(COVERAGE.c.id == cid).values(tone=tone, tone_source="zeki", tone_prob=prob))
    return True


def untoned(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    """Tonu hiç sınıflanmamış elle girilmiş yansımalar (gece toplu sınıflama)."""
    with engine.connect() as c:
        rows = c.execute(sa.select(COVERAGE).where(COVERAGE.c.tenant_id == tenant, COVERAGE.c.state == "kayitli",
                                                   COVERAGE.c.tone.is_(None), COVERAGE.c.tone_source.is_(None))).all()
    return [coverage_dict(r) for r in rows]


def import_web(engine: sa.engine.Engine, tenant: str, items: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Basın ve web taramasının ilgili bulduğu kayıtlar aday yansıma olur (bağlantı tekse). Reddedilmiş aday tekrar gelmez."""
    added = seen = 0
    with engine.begin() as c:
        for it in items:
            url = str(it.get("url") or "")[:1000]
            if not url:
                continue
            if c.execute(sa.select(COVERAGE.c.id).where(COVERAGE.c.tenant_id == tenant, COVERAGE.c.url == url)).first():
                seen += 1
                continue
            books = it.get("books") or []
            b = books[0] if books else {}
            cid = _uid()
            c.execute(COVERAGE.insert().values(
                id=cid, tenant_id=tenant, url=url, title=one_line(it.get("title"), 500) or url,
                published_at=it.get("publishedAt"), outlet=one_line(it.get("outlet"), 200), outlet_type="web",
                contact_key=None, crm_book_id=(b.get("id") or "").lower() or None, book_title=one_line(b.get("title"), 400),
                author_name=one_line(it.get("author"), 200), author_contact_id=(it.get("contactId") or "").lower() or None,
                tone=it.get("label") if it.get("label") in TONES else None, tone_source="web" if it.get("label") in TONES else None,
                source="web", state="aday", web_item_id=it.get("itemId"), summary=short_summary(it.get("summary")),
                created_by="sistem", created_at=now()))
            added += 1
    return {"eklenen": added, "zatenVar": seen}


def coverage_stmt(tenant: str, state: str = "kayitli"):
    cond = [COVERAGE.c.tenant_id == tenant]
    if state:
        cond.append(COVERAGE.c.state.in_([s for s in state.split(",") if s]))
    return sa.select(COVERAGE).where(*cond)


def list_coverage(engine: sa.engine.Engine, tenant: str, *, state: str = "kayitli") -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(coverage_stmt(tenant, state)).all()
    return [coverage_dict(r) for r in rows]


def archive_as_coverage(a: dict[str, Any]) -> dict[str, Any]:
    """CRM Haber arşivi satırı → yansıma listesi satırı (salt okunur)."""
    books = a.get("books") or []
    return {"id": f"crm:{a['id']}", "source": "crm-arsiv", "sourceLabel": COVERAGE_SOURCES["crm-arsiv"], "state": "kayitli",
            "stateLabel": COVERAGE_STATES["kayitli"], "url": a.get("link"), "title": a.get("baslik") or "—", "publishedAt": a.get("tarih"),
            "outlet": a.get("mecra"), "outletType": None, "contactKey": crm_key(a["muhabirId"]) if a.get("muhabirId") else None,
            "crmBookId": books[0]["kitapId"] if books else None, "stokKodu": books[0].get("stokKodu") if books else None,
            "bookTitle": ", ".join(b.get("ad") or "" for b in books) or a.get("kitapText"), "authorName": a.get("yazar"),
            "kitId": None, "sendId": None, "tone": None, "toneLabel": None, "toneSource": None, "toneProb": None, "summary": None,
            "note": a.get("muhabir") and f"Haberi yapan: {a['muhabir']}", "createdBy": None, "createdAt": None, "readOnly": True,
            "books": books}


def filter_coverage(rows: list[dict[str, Any]], *, frm: Optional[str] = None, to: Optional[str] = None, book: str = "",
                    source: str = "", tone: str = "", q: str = "", contact: str = "") -> list[dict[str, Any]]:
    fq = fold(q)
    out = []
    for r in rows:
        d = r.get("publishedAt") or (r.get("createdAt") or "")[:10] or None
        if frm and (not d or d < frm):
            continue
        if to and (not d or d > to):
            continue
        if book and book.lower() not in {(r.get("crmBookId") or "").lower(), *[(b.get("kitapId") or "").lower() for b in r.get("books") or []]}:
            continue
        if source and r["source"] != source:
            continue
        if tone and (r.get("tone") or "") != tone:
            continue
        if contact and r.get("contactKey") != contact:
            continue
        if fq and fq not in fold(" ".join(str(r.get(k) or "") for k in ("title", "outlet", "bookTitle", "authorName", "summary"))):
            continue
        out.append(r)
    out.sort(key=lambda r: (r.get("publishedAt") or (r.get("createdAt") or "")[:10] or "", r["id"]), reverse=True)
    return out


def page_of(rows: list[Any], page: int, size: int = PAGE) -> dict[str, Any]:
    p = max(0, int(page or 0))
    return {"items": rows[p * size:(p + 1) * size], "total": len(rows), "page": p, "pageSize": size}


# ------------------------------------------------------------------ öneri puanı


def _book_tokens(book: dict[str, Any]) -> set[str]:
    words: set[str] = set()
    for k in ("kitaplik", "hedefKitle", "turler"):
        for part in re.split(r"[,;/|]", str(book.get(k) or "")):
            f = fold(part)
            if f:
                words.add(f)
    return words


def suggest(contacts: list[dict[str, Any]], archive: list[dict[str, Any]], book: dict[str, Any],
            history: dict[str, dict[str, Any]], exclude: set[str], ref: Optional[date] = None) -> list[dict[str, Any]]:
    """Kitaba uygun medya kişileri, puana göre sıralı; hepsi döner (tavan yok). Puan kuraldır, her kalemi gerekçede:
    aynı yazarın kitabı hakkında haber +3, aynı kitaplık +2, aynı hedef kitle +1 (CRM arşivinde bu kişinin yaptığı
    haberler), kişinin konu etiketi kitabın türü/kitaplığı/hedef kitlesiyle eşleşiyor +2, portalda kayıtlı yansıması +1,
    önceki gönderime cevap/haber +1, olumsuz −1, son 365 günde temas +1. «Haberdar olmak istemiyor» olan listelenmez."""
    ref = ref or today()
    author = fold(book.get("yazar"))
    kitaplik = fold(book.get("kitaplik"))
    audience = fold(book.get("hedefKitle"))
    tokens = _book_tokens(book)
    by_journalist: dict[str, list[dict[str, Any]]] = {}
    for a in archive:
        for key in {a.get("muhabirId"), a.get("gorusulenId")} - {None}:
            by_journalist.setdefault(crm_key(key), []).append(a)
    out = []
    for p in contacts:
        if p.get("doNotContact"):
            continue
        reasons: list[str] = []
        score = 0
        news = by_journalist.get(p["key"], [])
        same_author = sum(1 for a in news if author and any(fold(b.get("yazar")) == author for b in a.get("books") or []))
        same_lib = sum(1 for a in news if kitaplik and any(fold(b.get("kitaplik")) == kitaplik for b in a.get("books") or []))
        same_aud = sum(1 for a in news if audience and any(fold(b.get("hedefKitle")) == audience for b in a.get("books") or []))
        if same_author:
            score += 3 * same_author
            reasons.append(f"yazarın kitapları hakkında {same_author} haber")
        if same_lib:
            score += 2 * same_lib
            reasons.append(f"aynı kitaplıktan {same_lib} haber ({book.get('kitaplik')})")
        if same_aud:
            score += same_aud
            reasons.append(f"aynı hedef kitleden {same_aud} haber")
        hits = [t for t in p.get("topics") or [] if fold(t) and any(fold(t) in tok or tok in fold(t) for tok in tokens)]
        if hits:
            score += 2 * len(hits)
            reasons.append("konu etiketi: " + ", ".join(hits))
        h = history.get(p["key"]) or {}
        if h.get("coverage"):
            score += int(h["coverage"])
            reasons.append(f"portalda {h['coverage']} yansıması var")
        if h.get("positive"):
            score += int(h["positive"])
            reasons.append(f"{h['positive']} gönderime dönüş yaptı")
        if h.get("negative"):
            score -= int(h["negative"])
            reasons.append(f"{h['negative']} gönderim olumsuz kapandı")
        last = max([x for x in [h.get("last")] + [a.get("tarih") for a in news] if x] or [""])
        if last and (ref - date.fromisoformat(last[:10])).days <= 365:
            score += 1
            reasons.append("son bir yılda temas")
        out.append({**p, "score": score, "reasons": reasons, "lastContact": last or None, "archiveCount": len(news),
                    "inList": p["key"] in exclude})
    out.sort(key=lambda x: (-x["score"], x["inList"], fold(x["name"])))
    return out


def history_stmts(tenant: str) -> tuple[Any, Any]:
    """Kişi başına geçmiş: (gönderim satırları, kişi başına kayıtlı yansıma sayısı)."""
    return (sa.select(SENDS.c.contact_key, SENDS.c.status, SENDS.c.sent_at).where(SENDS.c.tenant_id == tenant),
            sa.select(COVERAGE.c.contact_key, sa.func.count().label("yansima")).where(
                COVERAGE.c.tenant_id == tenant, COVERAGE.c.state == "kayitli", COVERAGE.c.contact_key.is_not(None))
            .group_by(COVERAGE.c.contact_key))


def history_by_contact(engine: sa.engine.Engine, tenant: str) -> dict[str, dict[str, Any]]:
    """Kişi başına portal geçmişi: gönderim sayısı, dönüş, olumsuz, son temas, yansıma sayısı."""
    out: dict[str, dict[str, Any]] = {}
    sq, cq = history_stmts(tenant)
    with engine.connect() as c:
        for r in c.execute(sq).all():
            h = out.setdefault(r.contact_key, {"sends": 0, "positive": 0, "negative": 0, "coverage": 0, "last": None})
            if r.status in SENT:
                h["sends"] += 1
            if r.status in ("cevap", "haber"):
                h["positive"] += 1
            if r.status == "olumsuz":
                h["negative"] += 1
            d = local_day(r.sent_at)
            if d and (h["last"] is None or d > h["last"]):
                h["last"] = d
        for key, n in c.execute(cq).all():
            out.setdefault(key, {"sends": 0, "positive": 0, "negative": 0, "coverage": 0, "last": None})["coverage"] = int(n)
    return out


def sends_of_contact_stmt(tenant: str, key: str):
    return sa.select(SENDS, KITS.c.book_title).join(KITS, KITS.c.id == SENDS.c.kit_id) \
        .where(SENDS.c.tenant_id == tenant, SENDS.c.contact_key == key).order_by(SENDS.c.created_at.desc())


def sends_of_contact(engine: sa.engine.Engine, tenant: str, key: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sends_of_contact_stmt(tenant, key)).all()
    return [{**send_dict(r), "bookTitle": r.book_title} for r in rows]


# ------------------------------------------------------------------ iş kuyruğu (Zeki AI)


def job_dict(j: Any) -> dict[str, Any]:
    return {"id": j.id, "refId": j.ref_id, "kind": j.kind, "status": j.status, "step": j.step, "error": j.error,
            "result": loads(j.result_json, None), "createdBy": j.created_by, "createdAt": iso(j.created_at),
            "finishedAt": iso(j.finished_at)}


def job_create(engine: sa.engine.Engine, tenant: str, user: str, ref: str, kind: str) -> dict[str, Any]:
    with engine.begin() as c:
        busy = c.execute(sa.select(JOBS.c.id).where(JOBS.c.ref_id == ref, JOBS.c.kind == kind,
                                                    JOBS.c.status.in_(("bekliyor", "calisiyor")))).first()
        if busy:
            raise PrError("Bu kayıt için Zeki AI zaten çalışıyor.", 409)
        jid = _uid()
        c.execute(JOBS.insert().values(id=jid, tenant_id=tenant, ref_id=ref, kind=kind, status="bekliyor", created_by=user, created_at=now()))
        return job_dict(c.execute(sa.select(JOBS).where(JOBS.c.id == jid)).one())


def job_update(engine: sa.engine.Engine, jid: str, **vals: Any) -> None:
    v = dict(vals)
    if "result" in v:
        v["result_json"] = dump(v.pop("result"))
    if v.get("status") in ("bitti", "hata"):
        v["finished_at"] = now()
    with engine.begin() as c:
        c.execute(JOBS.update().where(JOBS.c.id == jid).values(**v))


def job_get(engine: sa.engine.Engine, jid: str) -> dict[str, Any]:
    with engine.connect() as c:
        j = c.execute(sa.select(JOBS).where(JOBS.c.id == jid)).first()
    if not j:
        raise PrError("İş bulunamadı.", 404)
    return job_dict(j)


def fail_stale_jobs(engine: sa.engine.Engine) -> int:
    """Köprü yeniden başlarken yarıda kalan işler «hata» olur (kullanıcı yeniden başlatır)."""
    with engine.begin() as c:
        res = c.execute(JOBS.update().where(JOBS.c.status.in_(("bekliyor", "calisiyor")))
                        .values(status="hata", error="Köprü yeniden başladı; işi yeniden başlatın.", finished_at=now()))
    return int(res.rowcount or 0)


# ------------------------------------------------------------------ rapor


def report_stmts(tenant: str) -> tuple[Any, Any, Any]:
    """Rapor okumaları: gönderilmiş satırlar, kayıtlı yansımalar, aday yansıma sayısı (dönem süzgeci hesapta)."""
    return (sa.select(SENDS.c.id, SENDS.c.status, SENDS.c.channel, SENDS.c.sent_at, SENDS.c.kit_id)
            .where(SENDS.c.tenant_id == tenant, SENDS.c.sent_at.is_not(None)),
            sa.select(COVERAGE).where(COVERAGE.c.tenant_id == tenant, COVERAGE.c.state == "kayitli"),
            sa.select(sa.func.count()).select_from(COVERAGE).where(COVERAGE.c.tenant_id == tenant, COVERAGE.c.state == "aday"))


def report(engine: sa.engine.Engine, tenant: str, frm: str, to: str, archive: list[dict[str, Any]]) -> dict[str, Any]:
    """Dönem raporu. Sayılar doğrudan tablolardan: gönderim (gönderim gününe göre), yansıma (yayın gününe göre;
    yoksa kayıt günü), CRM arşivi (haber tarihine göre) ayrı. Erişim/tiraj yok."""
    sq, cq, pq = report_stmts(tenant)
    with engine.connect() as c:
        sends = c.execute(sq).all()
        cov = c.execute(cq).all()
        pending = c.execute(pq).scalar() or 0
    in_range = lambda d: bool(d) and frm <= d <= to  # noqa: E731
    s_rows = [s for s in sends if in_range(local_day(s.sent_at))]
    by_status: dict[str, int] = {}
    by_channel: dict[str, int] = {}
    for s in s_rows:
        by_status[s.status] = by_status.get(s.status, 0) + 1
        by_channel[s.channel] = by_channel.get(s.channel, 0) + 1
    answered = by_status.get("cevap", 0) + by_status.get("haber", 0)
    c_rows = [coverage_dict(r) for r in cov if in_range(r.published_at or local_day(r.created_at))]
    tone: dict[str, int] = {}
    outlet_type: dict[str, int] = {}
    source: dict[str, int] = {}
    outlets: dict[str, int] = {}
    books: dict[str, dict[str, Any]] = {}
    authors: dict[str, int] = {}
    for r in c_rows:
        tone[r["tone"] or "belirsiz"] = tone.get(r["tone"] or "belirsiz", 0) + 1
        outlet_type[r["outletType"] or "belirsiz"] = outlet_type.get(r["outletType"] or "belirsiz", 0) + 1
        source[r["source"]] = source.get(r["source"], 0) + 1
        if r["outlet"]:
            outlets[r["outlet"]] = outlets.get(r["outlet"], 0) + 1
        if r["crmBookId"] or r["bookTitle"]:
            k = r["crmBookId"] or r["bookTitle"]
            b = books.setdefault(k, {"crmBookId": r["crmBookId"], "title": r["bookTitle"], "count": 0})
            b["count"] += 1
        if r["authorName"]:
            authors[r["authorName"]] = authors.get(r["authorName"], 0) + 1
    a_rows = [a for a in archive if in_range(a.get("tarih"))]
    rank = lambda d: [{"name": k, "count": v} for k, v in sorted(d.items(), key=lambda x: (-x[1], x[0]))]  # noqa: E731
    return {
        "from": frm, "to": to,
        "sends": {"total": len(s_rows), "byStatus": by_status, "byChannel": by_channel, "answered": answered,
                  "answerRate": (answered / len(s_rows)) if s_rows else None},
        "coverage": {"total": len(c_rows), "byTone": tone, "byOutletType": outlet_type, "bySource": source,
                     "outlets": rank(outlets), "books": sorted(books.values(), key=lambda b: (-b["count"], b["title"] or "")),
                     "authors": rank(authors), "items": sorted(c_rows, key=lambda r: r["publishedAt"] or "", reverse=True)},
        "archive": {"total": len(a_rows)},
        "pendingCandidates": int(pending),
    }


def report_facts(rep: dict[str, Any]) -> list[str]:
    """Modelin yorumunda kullanabileceği sayılar (rakamı model üretmez; bu listede olmayan sayı cümleyi düşürür)."""
    f = [f"Dönem: {rep['from']} – {rep['to']}", f"Gönderim: {rep['sends']['total']}", f"Dönüş (cevap ya da haber): {rep['sends']['answered']}",
         f"Kayıtlı yansıma: {rep['coverage']['total']}", f"CRM arşivindeki haber: {rep['archive']['total']}"]
    for k, v in rep["coverage"]["byTone"].items():
        f.append(f"{TONES.get(k, 'Tonu belirsiz')} yansıma: {v}")
    for b in rep["coverage"]["books"]:
        f.append(f"{b['title'] or '—'}: {b['count']} yansıma")
    for o in rep["coverage"]["outlets"]:
        f.append(f"{o['name']}: {o['count']} yansıma")
    return f


def week_of(ref: date) -> tuple[str, str]:
    """Bir önceki tam hafta (pazartesi–pazar)."""
    start = ref - timedelta(days=ref.weekday() + 7)
    return start.isoformat(), (start + timedelta(days=6)).isoformat()


# ------------------------------------------------------------------ Zeki AI (taslak, kişiye özel metin, ton, rapor yorumu)
#
# Model yalnız LLM kapısından gelir (`rt.llm_for("pr", …)`); rakamı model üretmez. Her metin pazarlama çekirdeğinin
# denetiminden geçer (`marketing.guard`): kaynakta birebir geçmeyen alıntı, olgu listesinde olmayan sayı, kanıtsız
# üstünlük iddiası ve teknoloji adı içeren cümle düşer; düşen cümleler nedeniyle kayda geçer.

AY = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")

SYSTEM = ("Sen TİMAŞ Yayınları'nın basın ilişkileri ekibine taslak yazan Zeki AI'sın. Kurallar: Türkçe yaz. Yalnız sana "
          "verilen bilgileri kullan; kitap ya da yazar hakkında bilgi uydurma. Olgu listesinde olmayan hiçbir sayı yazma "
          "(satış, baskı, takipçi, yüzde, sıra, tarih dahil). Kitaptan alıntıyı yalnız verilen metinlerde birebir geçen "
          "cümlelerden, « » içinde yaz; emin değilsen alıntı yapma. «En çok satan», «bir numara», «rekor», «eşsiz» gibi "
          "kanıtsız üstünlük iddiası yazma. Hiçbir teknoloji, model ya da yazılım adı yazma. Açıklama ekleme; yalnız "
          "istenen metni ver.")

PROMPTS = {
    "national": "Ulusal basın için basın bülteni yaz: başlık, bir paragraflık spot, kitabı ve yazarı anlatan iki üç "
                "paragraf, sonunda künye (yalnız olgu listesindeki yayınevi, sayfa sayısı, fiyat ve yayın tarihi).",
    "local": "Yerel basın için kısa basın bülteni yaz: başlık ve en çok iki kısa paragraf; sade ve haber diliyle.",
    "pitch": "Gazeteciye gidecek kişiye özel e-posta şablonu yaz: en çok 120 kelime, samimi ama resmî. Kişinin adı "
             "yerine {ad}, çalıştığı mecra yerine {mecra} yaz (bu iki yer tutucuyu aynen kullan). Kitabın neden o "
             "mecranın okurunu ilgilendireceğini bir cümleyle söyle; kitap göndermeyi ya da yazarla söyleşiyi öner. "
             "Konu satırı yazma.",
    "openings": "Bülten için üç farklı açılış cümlesi yaz; her biri ayrı satırda, numara koymadan.",
}
PARTS = {"national": "Ulusal bülten", "local": "Yerel bülten", "pitch": "E-posta şablonu", "openings": "Açılış cümleleri"}
TONE_CHOICES = ("Olumlu", "Nötr", "Olumsuz", "İlgisiz (kitapla ya da yazarla ilgili değil)")
TONE_KEYS = dict(zip(TONE_CHOICES, ("olumlu", "notr", "olumsuz", "ilgisiz")))


def tr_day(d: Optional[str]) -> Optional[str]:
    if not d:
        return None
    x = date.fromisoformat(d[:10])
    return f"{x.day} {AY[x.month - 1]} {x.year}"


def book_sources(book: dict[str, Any], extra: Iterable[str] = ()) -> list[str]:
    out = [m["metin"] for m in book.get("metinler") or []]
    out += [x for x in (book.get("ad"), book.get("yazar"), book.get("yayinevi"), book.get("kitaplik"), book.get("hedefKitle"),
                        book.get("turler")) if x]
    out += [a["ad"] for a in book.get("yazarlar") or [] if a.get("ad")]
    return out + [x for x in extra if x]


def book_facts(book: dict[str, Any]) -> list[str]:
    f = []
    if book.get("yayinTarihi"):
        f.append(f"Yayın tarihi: {tr_day(book['yayinTarihi'])}")
    if book.get("fiyat"):
        f.append(f"Kapak fiyatı: {book['fiyat']:g} TL")
    if book.get("sayfa"):
        f.append(f"Sayfa sayısı: {int(book['sayfa'])}")
    yas = [x for x in (book.get("yas") or []) if x]
    if len(yas) == 2:
        f.append(f"Hedef yaş: {yas[0]}–{yas[1]}")
    if book.get("yayinevi"):
        f.append(f"Yayınevi: {book['yayinevi']}")
    return f


def book_brief(book: dict[str, Any], extra: Iterable[tuple[str, str]] = ()) -> str:
    parts = [f"Kitap: {book.get('ad')}", f"Yazar: {book.get('yazar') or '—'}", f"Yayınevi: {book.get('yayinevi') or '—'}",
             f"Kitaplık: {book.get('kitaplik') or '—'}", f"Hedef kitle: {book.get('hedefKitle') or '—'}",
             f"Türler: {book.get('turler') or '—'}"]
    for m in book.get("metinler") or []:
        parts.append(f"\n[{m['ad']}]\n{m['metin'][:4000]}")
    for label, body in extra:
        if body:
            parts.append(f"\n[{label}]\n{body[:4000]}")
    return "\n".join(parts)


def _chat(llm: Any, prompt: str, max_tokens: int = 1600) -> str:
    return str(llm.chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}], max_tokens=max_tokens) or "").strip()


def draft_part(llm: Any, book: dict[str, Any], part: str, claims: Iterable[str] = (),
               extra: Iterable[tuple[str, str]] = ()) -> dict[str, Any]:
    from semantic_bridge.marketing import guard as G

    extra = list(extra)
    facts = book_facts(book)
    prompt = (f"{PROMPTS[part]}\n\nOlgu listesi (yazabileceğin sayılar yalnız bunlar):\n" + ("\n".join(facts) or "—")
              + f"\n\nKitap bilgisi ve CRM'deki metinler:\n{book_brief(book, extra)}")
    raw = _chat(llm, prompt, 700 if part in ("pitch", "openings") else 1800)
    res = G.check(raw, book_sources(book, [b for _, b in extra]), facts, claims)
    return {"metin": res["metin"] or None, "dusen": res["dusen"], "sayac": res["sayac"], "dusenSayisi": res["dusenSayisi"]}


def personal_pitch(llm: Any, book: dict[str, Any], contact: dict[str, Any], template: Optional[str],
                   past_titles: list[str], claims: Iterable[str] = ()) -> dict[str, Any]:
    """Tek kişiye özel e-posta metni. Kişinin mecrası, konu etiketleri ve CRM arşivindeki geçmiş haber başlıkları
    (yalnız başlık) bağlamdır; gazeteci hakkında bilgi uydurulmaz."""
    from semantic_bridge.marketing import guard as G

    facts = book_facts(book)
    who = [f"Ad: {contact.get('name')}", f"Mecra: {contact.get('outlet') or '—'}",
           f"Mecra türü: {OUTLET_TYPES.get(contact.get('outletType') or '', '—')}",
           f"Konuları: {', '.join(contact.get('topics') or []) or '—'}"]
    prompt = ("Aşağıdaki gazeteciye bu kitap için kişiye özel kısa bir e-posta yaz (en çok 120 kelime, konu satırı yok, "
              "hitapla başla, imza yazma). Gazeteci hakkında verilmeyen bilgi yazma."
              + (f"\nEkibin şablonu (üslup için):\n{template[:2000]}" if template else "")
              + "\n\nGazeteci:\n" + "\n".join(who)
              + ("\nDaha önce Timaş kitapları hakkında yaptığı haberlerin başlıkları:\n- " + "\n- ".join(past_titles) if past_titles else "")
              + "\n\nOlgu listesi:\n" + ("\n".join(facts) or "—") + f"\n\nKitap:\n{book_brief(book)[:6000]}")
    raw = _chat(llm, prompt, 600)
    src = book_sources(book, [template or "", contact.get("name") or "", contact.get("outlet") or "", *past_titles])
    res = G.check(raw, src, facts, claims)
    return {"metin": res["metin"] or None, "dusen": res["dusen"], "dusenSayisi": res["dusenSayisi"]}


def classify_tone(llm: Any, title: str, summary: Optional[str], book_title: Optional[str], author: Optional[str],
                  min_prob: float, min_margin: float) -> tuple[Optional[str], Optional[float], dict[str, Any]]:
    """Kapalı küme karar (seçenek + olasılık): emin değilse ton boş kalır, insan karar verir."""
    if llm is None or not hasattr(llm, "choose"):
        return None, None, {"method": "yok"}
    q = ("Bir yayınevi için basında çıkan haberleri sınıflıyoruz. Haber aşağıdaki kitap ya da yazar hakkında mı; öyleyse "
         "kitaba/yazara karşı tonu ne?\n\n" + f"Kitap: {book_title or '—'}\nYazar: {author or '—'}\nHaber başlığı: {title}\n"
         + f"Özet: {summary or '—'}")
    ch = llm.choose(q, list(TONE_CHOICES))
    info = ch.as_dict() if hasattr(ch, "as_dict") else {}
    if not ch.confident(min_prob, min_margin):
        return None, ch.probability, info
    return TONE_KEYS.get(ch.choice or ""), ch.probability, info


def report_comment(llm: Any, rep: dict[str, Any], claims: Iterable[str] = ()) -> dict[str, Any]:
    from semantic_bridge.marketing import guard as G

    facts = report_facts(rep)
    titles = [r["title"] for r in rep["coverage"]["items"]]
    prompt = ("Aşağıdaki sayılar basın ilişkileri raporundan kodla hesaplandı. Pazarlama müdürüne dönemi üç cümleyle "
              "yorumla. Yeni sayı yazma, sayıları yeniden hesaplama; sayı söyleyeceksen listedekini aynen kullan.\n\nSayılar:\n"
              + "\n".join(facts) + ("\n\nYansıma başlıkları:\n- " + "\n- ".join(titles) if titles else ""))
    raw = _chat(llm, prompt, 400)
    res = G.check(raw, titles + [o["name"] for o in rep["coverage"]["outlets"]] + [b["title"] or "" for b in rep["coverage"]["books"]],
                  facts, claims)
    return {"metin": res["metin"] or None, "dusenSayisi": res["dusenSayisi"]}
