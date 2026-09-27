"""M7 Yazar ilişkileri: yazar kartı, randevu ve görüşme notu, potansiyel yazar havuzu, ilişki ısı haritası.

CRM'de yazarla temasın kaydı yok (randevu, görüşme, not tabloları köprü kataloğunda değil; 2026-09-20 analizi:
"Randevu, not, duygu analizi yok"). Bu yüzden ilişki kayıtları bizim tablolarımızdadır:

- **Yazar kartı** (`semantic_author_cards`): bir kişinin ilişki kaydı. CRM'de henüz olmayan aday için sıfırdan
  açılır (ad, alan, nereden bulundu, iletişim, sorumlu editör); CRM'deki bir kişiye (`crm_contact_id`) bağlanabilir.
  Bir CRM kişisine en çok bir kart düşer. CRM'deki bir yazara ilk randevu/not yazılınca kartı kendiliğinden açılır
  (aşama «Yayınevi yazarı»).
- **Aşama**: aday → ilk temas → görüşülüyor → teklif → anlaşıldı / vazgeçildi; CRM yazarının kartı «yazar».
  Potansiyel yazar havuzu = «yazar» dışındaki kartlar + CRM'de bir projenin olası yazarı olup henüz yazar rolüyle
  eser kaydı olmayan kişiler (`new_projeBase.new_OlasYazarYazar`, yalnız okunur).
- **Randevu / görüşme notu** (`semantic_author_meetings`): planlanan randevu yapılınca görüşme notuna döner (durum
  planlandı → yapıldı / iptal). Not, ton (olumlu / nötr / olumsuz), sıradaki adım ve tarihi, isteğe bağlı toplantı
  odası rezervasyonu (Kampüs odaları, aynı çakışma denetimi). «Yalnız ben ve katılımcılar» işaretli notun metni
  başkasına gitmez; varlığı (tarih, kanal) ısı haritasına yine sayılır.
- **Isı puanı** (0–100, yalnız insan temasından): son yapılan görüşmenin yakınlığı en çok 50 (180 günde sıfırlanır),
  son 12 aydaki görüşme sayısı en çok 30 (görüşme başı 10), son üç görüşmenin tonu en çok 20 (olumlu 20, nötr ya da
  tonsuz 10, olumsuz 0). Hiç görüşme yoksa 0. Bant: 0 temas yok, 1–33 soğuk, 34–66 ılık, 67–100 sıcak. CRM olayları
  (yeni eser kaydı, yeni sözleşme) puana girmez; haritada ayrı işaret olarak durur.

CRM yalnız okunur, köprünün `run_sql` yolundan (katalog kapısı). Kullanıcıdan gelen serbest metin `_like` ile
kaçışlanır, kimlikler GUID'e zorlanır.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

import sqlalchemy as sa

log = logging.getLogger("semantic.author_relations")
TZ = ZoneInfo("Europe/Istanbul")
_md = sa.MetaData()

CARDS = sa.Table(
    "semantic_author_cards", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("crm_contact_id", sa.String(40)),
    sa.Column("name", sa.String(300), nullable=False),
    sa.Column("stage", sa.String(20), nullable=False),
    sa.Column("genre", sa.String(200)),
    sa.Column("source", sa.String(20)),
    sa.Column("source_note", sa.String(300)),
    sa.Column("email", sa.String(200)),
    sa.Column("phone", sa.String(60)),
    sa.Column("city", sa.String(120)),
    sa.Column("links_json", sa.Text, nullable=False, default="[]"),
    sa.Column("bio", sa.Text),
    sa.Column("tags_json", sa.Text, nullable=False, default="[]"),
    sa.Column("owner", sa.String(120)),
    sa.Column("owner_display", sa.String(200)),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
    sa.Column("archived_at", sa.DateTime(timezone=True)),
    sa.Column("archived_by", sa.String(120)),
    sa.Index("ux_semantic_author_cards_crm", "tenant_id", "crm_contact_id", unique=True,
             postgresql_where=sa.text("crm_contact_id IS NOT NULL"),
             sqlite_where=sa.text("crm_contact_id IS NOT NULL")),
)
MEETINGS = sa.Table(
    "semantic_author_meetings", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("card_id", sa.String(32), nullable=False, index=True),
    sa.Column("status", sa.String(20), nullable=False),            # planlandi | yapildi | iptal
    sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("minutes", sa.Integer),
    sa.Column("channel", sa.String(20), nullable=False),
    sa.Column("location", sa.String(200)),
    sa.Column("topic", sa.String(300), nullable=False),
    sa.Column("notes", sa.Text),
    sa.Column("tone", sa.String(10)),                               # olumlu | notr | olumsuz
    sa.Column("next_step", sa.String(500)),
    sa.Column("next_due", sa.Date),
    sa.Column("next_done", sa.Boolean, nullable=False, default=False),
    sa.Column("private", sa.Boolean, nullable=False, default=False),
    sa.Column("participants_json", sa.Text, nullable=False, default="[]"),
    sa.Column("room_id", sa.String(40)),
    sa.Column("room_booking_id", sa.String(40)),
    sa.Column("room_name", sa.String(200)),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_display", sa.String(200)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
    sa.Index("ix_semantic_author_meetings_start", "tenant_id", "starts_at"),
)

STAGES = {
    "aday": "Aday",
    "temas": "İlk temas",
    "gorusme": "Görüşülüyor",
    "teklif": "Teklif verildi",
    "anlasma": "Anlaşıldı",
    "vazgecildi": "Vazgeçildi",
    "yazar": "Yayınevi yazarı",
}
#: Havuzdaki (yazar olmamış) aşamalar, sırasıyla.
POOL_STAGES = ("aday", "temas", "gorusme", "teklif", "anlasma", "vazgecildi")
SOURCES = {
    "oneri": "Tavsiye / öneri",
    "basvuru": "Dosya başvurusu",
    "etkinlik": "Fuar / etkinlik",
    "medya": "Basın / medya",
    "sosyal": "Sosyal medya",
    "akademi": "Akademi",
    "ajans": "Ajans",
    "diger": "Diğer",
}
CHANNELS = {
    "yuz_yuze": "Yüz yüze",
    "telefon": "Telefon",
    "video": "Görüntülü",
    "eposta": "E-posta",
    "etkinlik": "Etkinlik",
    "diger": "Diğer",
}
TONES = {"olumlu": "Olumlu", "notr": "Nötr", "olumsuz": "Olumsuz"}
STATUSES = {"planlandi": "Planlandı", "yapildi": "Yapıldı", "iptal": "İptal"}

#: Isı puanı parçaları (modül başındaki tanım).
RECENCY_MAX, RECENCY_DAYS = 50, 180
FREQUENCY_MAX, FREQUENCY_EACH = 30, 10
TONE_MAX = 20
TONE_POINTS = {"olumlu": 20, "notr": 10, "olumsuz": 0, None: 10}

PAGE_SIZE = 50
MONTHS = 12

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_GUID = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
_ID = re.compile(r"^[0-9a-f]{32}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE = re.compile(r"^[0-9+()\-\s./]{5,60}$")
_URL = re.compile(r"^https?://\S+$", re.I)
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

# new_projeBase.statuscode (editorial_intake ile aynı ölçüm, 2026-09-24): Red ve iptal.
PROJECT_CLOSED = (100000012, 100000009, 100000021)
# new_sozlesmeBase.statuscode: yürürlükte sayılanlar (editorial.ACTIVE_STATUS).
CONTRACT_ACTIVE = (100000000, 100000006, 100000007)

_ready: set[int] = set()
_lock = threading.Lock()


class RelationError(ValueError):
    """Kişiye gösterilecek düz Türkçe hata."""

    def __init__(self, message: str, status: int = 400, **extra: Any):
        super().__init__(message)
        self.status = status
        self.extra = extra


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def meta() -> dict[str, Any]:
    """Ekranın seçenek listeleri ve ısı puanının tanımı (ekranda açıklama olarak gösterilir)."""
    pairs = lambda d: [{"key": k, "label": v} for k, v in d.items()]  # noqa: E731
    return {"stages": pairs(STAGES), "poolStages": list(POOL_STAGES), "sources": pairs(SOURCES),
            "channels": pairs(CHANNELS), "tones": pairs(TONES), "statuses": pairs(STATUSES),
            "heat": {"recencyMax": RECENCY_MAX, "recencyDays": RECENCY_DAYS, "frequencyMax": FREQUENCY_MAX,
                     "frequencyEach": FREQUENCY_EACH, "toneMax": TONE_MAX, "months": MONTHS}}


# ------------------------------------------------------------------------------------------ yardımcılar

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(v: Optional[datetime]) -> Optional[datetime]:
    if v is None:
        return None
    return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)


def _iso(v: Optional[datetime]) -> Optional[str]:
    v = _utc(v)
    return v.isoformat() if v else None


def _text(body: dict[str, Any], key: str, limit: int, label: str, *, required: bool = False) -> Optional[str]:
    v = body.get(key)
    t = re.sub(r"\s+", " ", str(v)).strip() if v is not None else ""
    if required and not t:
        raise RelationError(f"{label} gerekli.")
    if len(t) > limit:
        raise RelationError(f"{label} en çok {limit} karakter olabilir.")
    return t or None


def _long(body: dict[str, Any], key: str, limit: int, label: str) -> Optional[str]:
    v = body.get(key)
    t = str(v).replace("\r\n", "\n").strip() if v is not None else ""
    if len(t) > limit:
        raise RelationError(f"{label} en çok {limit} karakter olabilir.")
    return t or None


def _choice(body: dict[str, Any], key: str, options: dict[str, str], label: str, default: Optional[str] = None) -> Optional[str]:
    v = body.get(key)
    if v in (None, ""):
        return default
    if v not in options:
        raise RelationError(f"{label} geçerli değil.")
    return str(v)


def _list(body: dict[str, Any], key: str, limit: int, label: str) -> list[str]:
    v = body.get(key) or []
    if isinstance(v, str):
        v = [x for x in re.split(r"[,\n]", v)]
    if not isinstance(v, list):
        raise RelationError(f"{label} liste olmalı.")
    out: list[str] = []
    for x in v:
        t = re.sub(r"\s+", " ", str(x or "")).strip()
        if not t:
            continue
        if len(t) > limit:
            raise RelationError(f"{label} içindeki her değer en çok {limit} karakter olabilir.")
        if t.lower() not in (o.lower() for o in out):
            out.append(t)
    return out


def _guid(v: Any, label: str = "CRM kişi kimliği") -> str:
    t = str(v or "").strip().strip("{}")
    if not _GUID.match(t):
        raise RelationError(f"{label} geçerli değil.")
    return t.lower()


def _cid(v: Any, label: str = "Kayıt") -> str:
    t = str(v or "").strip().lower()
    if not _ID.match(t):
        raise RelationError(f"{label} bulunamadı.", 404)
    return t


def _json(v: Optional[str]) -> list[Any]:
    try:
        out = json.loads(v or "[]")
        return out if isinstance(out, list) else []
    except ValueError:
        return []


def _norm(name: str) -> str:
    t = (name or "").casefold().replace("ı", "i").replace("İ".casefold(), "i")
    for a, b in (("ç", "c"), ("ğ", "g"), ("ö", "o"), ("ş", "s"), ("ü", "u"), ("â", "a"), ("î", "i"), ("û", "u")):
        t = t.replace(a, b)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _local_start(body: dict[str, Any]) -> datetime:
    day = str(body.get("date") or "").strip()
    hhmm = str(body.get("time") or "").strip()
    try:
        d = date.fromisoformat(day)
    except ValueError:
        raise RelationError("Tarih YYYY-AA-GG biçiminde olmalı.") from None
    m = _HHMM.match(hhmm)
    if not m:
        raise RelationError("Saat SS:DD biçiminde olmalı.")
    return datetime.combine(d, dtime(int(m.group(1)), int(m.group(2))), tzinfo=TZ).astimezone(timezone.utc)


def _local_parts(v: datetime) -> tuple[str, str]:
    loc = _utc(v).astimezone(TZ)
    return loc.date().isoformat(), loc.strftime("%H:%M")


# ------------------------------------------------------------------------------------------ kart

def _card_values(body: dict[str, Any], *, partial: bool) -> dict[str, Any]:
    out: dict[str, Any] = {}

    def has(k: str) -> bool:
        return not partial or k in body

    if has("name"):
        out["name"] = _text(body, "name", 300, "Ad soyad", required=True)
    if has("stage"):
        out["stage"] = _choice(body, "stage", STAGES, "Aşama", "aday")
    if has("genre"):
        out["genre"] = _text(body, "genre", 200, "Alan / tür")
    if has("source"):
        out["source"] = _choice(body, "source", SOURCES, "Nereden bulundu")
    if has("sourceNote"):
        out["source_note"] = _text(body, "sourceNote", 300, "Kaynak notu")
    if has("email"):
        e = _text(body, "email", 200, "E-posta")
        if e and not _EMAIL.match(e):
            raise RelationError("E-posta adresi geçerli değil.")
        out["email"] = e.lower() if e else None
    if has("phone"):
        p = _text(body, "phone", 60, "Telefon")
        if p and not _PHONE.match(p):
            raise RelationError("Telefon yalnız rakam, boşluk ve + ( ) - içerebilir.")
        out["phone"] = p
    if has("city"):
        out["city"] = _text(body, "city", 120, "Şehir")
    if has("links"):
        links = _list(body, "links", 500, "Bağlantılar")
        bad = [x for x in links if not _URL.match(x)]
        if bad:
            raise RelationError(f"Bağlantı http:// ya da https:// ile başlamalı: {bad[0]}")
        out["links_json"] = json.dumps(links, ensure_ascii=False)
    if has("bio"):
        out["bio"] = _long(body, "bio", 4000, "Kısa not")
    if has("tags"):
        out["tags_json"] = json.dumps(_list(body, "tags", 40, "Etiketler"), ensure_ascii=False)
    if has("owner"):
        out["owner"] = _text(body, "owner", 120, "Sorumlu")
        out["owner"] = out["owner"].lower() if out["owner"] else None
        out["owner_display"] = _text(body, "ownerDisplay", 200, "Sorumlu adı") if out["owner"] else None
    if has("crmContactId"):
        v = body.get("crmContactId")
        out["crm_contact_id"] = _guid(v) if v else None
    return out


def _card(r: Any) -> dict[str, Any]:
    return {
        "id": r.id, "crmContactId": r.crm_contact_id, "name": r.name, "stage": r.stage,
        "stageLabel": STAGES.get(r.stage, r.stage), "genre": r.genre, "source": r.source,
        "sourceLabel": SOURCES.get(r.source or "", None), "sourceNote": r.source_note, "email": r.email,
        "phone": r.phone, "city": r.city, "links": _json(r.links_json), "bio": r.bio, "tags": _json(r.tags_json),
        "owner": r.owner, "ownerDisplay": r.owner_display, "createdBy": r.created_by, "createdAt": _iso(r.created_at),
        "updatedBy": r.updated_by, "updatedAt": _iso(r.updated_at), "archived": r.archived_at is not None,
        "archivedAt": _iso(r.archived_at),
    }


def _get_card(c: Any, tenant: str, card_id: str, *, lock: bool = False) -> Any:
    stmt = sa.select(CARDS).where(CARDS.c.id == _cid(card_id, "Yazar kartı"), CARDS.c.tenant_id == tenant)
    row = c.execute(stmt.with_for_update() if lock else stmt).first()
    if not row:
        raise RelationError("Yazar kartı bulunamadı.", 404)
    return row


def _card_by_crm(c: Any, tenant: str, contact_id: str) -> Any:
    return c.execute(sa.select(CARDS).where(CARDS.c.tenant_id == tenant,
                                            CARDS.c.crm_contact_id == contact_id)).first()


def create_card(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
    vals = _card_values(body, partial=False)
    now = _now()
    with engine.begin() as c:
        if vals.get("crm_contact_id"):
            other = _card_by_crm(c, tenant, vals["crm_contact_id"])
            if other:
                raise RelationError(f"Bu CRM kişisinin kartı zaten var: {other.name}.", 409, cardId=other.id)
        row = {"id": uuid.uuid4().hex, "tenant_id": tenant, "created_by": user, "created_at": now,
               "updated_by": user, "updated_at": now, **vals}
        c.execute(CARDS.insert().values(**row))
        return _card(c.execute(sa.select(CARDS).where(CARDS.c.id == row["id"])).first())


def update_card(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, card_id: str,
                body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Kart ortak kayıttır: sayfayı gören herkes düzeltir (değişiklik kaydına düşer). Arşivleme ve arşivden
    çıkarma kartı açan, sorumlu ya da yönetici işidir. Dönen ikinci değer önce→sonra farkıdır."""
    vals = _card_values(body, partial=True)
    archive = body.get("archived")
    with engine.begin() as c:
        row = _get_card(c, tenant, card_id, lock=True)
        if archive is not None and bool(archive) != (row.archived_at is not None):
            if not (admin or user == row.created_by or user == (row.owner or "")):
                raise RelationError("Kartı yalnız açan kişi, sorumlusu ya da yönetici arşivler.", 403)
            vals["archived_at"] = _now() if archive else None
            vals["archived_by"] = user if archive else None
        if vals.get("crm_contact_id") and vals["crm_contact_id"] != row.crm_contact_id:
            other = _card_by_crm(c, tenant, vals["crm_contact_id"])
            if other and other.id != row.id:
                raise RelationError(f"Bu CRM kişisinin kartı zaten var: {other.name}.", 409, cardId=other.id)
        changed = {k: v for k, v in vals.items() if getattr(row, k) != v}
        if changed:
            c.execute(CARDS.update().where(CARDS.c.id == row.id).values(updated_by=user, updated_at=_now(), **changed))
        diff = {k: {"before": getattr(row, k), "after": v} for k, v in changed.items() if k not in ("archived_by",)}
        return _card(c.execute(sa.select(CARDS).where(CARDS.c.id == row.id)).first()), diff


def card_for_crm(engine: sa.engine.Engine, tenant: str, user: str, contact_id: str, name: str,
                 stage: str = "yazar") -> tuple[Any, bool]:
    """CRM kişisinin kartı; yoksa açılır (ilk randevu/not ya da «havuza al»). İkinci değer: şimdi mi açıldı."""
    cid = _guid(contact_id)
    now = _now()
    with engine.begin() as c:
        row = _card_by_crm(c, tenant, cid)
        if row:
            return row, False
        nm = re.sub(r"\s+", " ", name or "").strip()[:300]
        if not nm:
            raise RelationError("Kişinin adı gerekli.")
        rid = uuid.uuid4().hex
        try:
            c.execute(CARDS.insert().values(id=rid, tenant_id=tenant, crm_contact_id=cid, name=nm,
                                            stage=stage if stage in STAGES else "yazar", links_json="[]",
                                            tags_json="[]", created_by=user, created_at=now, updated_by=user,
                                            updated_at=now))
        except sa.exc.IntegrityError:
            created = False   # aynı anda başka istek açtı
        else:
            created = True
    with engine.connect() as c:
        return _card_by_crm(c, tenant, cid), created


# ------------------------------------------------------------------------------------------ görüşme

def _visible(r: Any, user: str, admin: bool) -> bool:
    if not r.private or admin or r.created_by == user:
        return True
    return user in (str(p.get("username") or "").lower() for p in _json(r.participants_json) if isinstance(p, dict))


def _meeting(r: Any, user: str, admin: bool, now: Optional[datetime] = None) -> dict[str, Any]:
    now = now or _now()
    open_text = _visible(r, user, admin)
    day, hhmm = _local_parts(r.starts_at)
    starts = _utc(r.starts_at)
    return {
        "id": r.id, "cardId": r.card_id, "status": r.status, "statusLabel": STATUSES.get(r.status, r.status),
        "startsAt": _iso(starts), "date": day, "time": hhmm, "minutes": r.minutes, "channel": r.channel,
        "channelLabel": CHANNELS.get(r.channel, r.channel), "location": r.location,
        "topic": r.topic if open_text else "Gizli görüşme",
        "notes": r.notes if open_text else None, "tone": r.tone if open_text else None,
        "toneLabel": TONES.get(r.tone or "", None) if open_text else None,
        "nextStep": r.next_step if open_text else None, "nextDue": r.next_due.isoformat() if r.next_due and open_text else None,
        "nextDone": bool(r.next_done), "private": bool(r.private), "hidden": not open_text,
        "participants": _json(r.participants_json) if open_text else [],
        "roomBookingId": r.room_booking_id, "roomName": r.room_name,
        "createdBy": r.created_by, "createdDisplay": r.created_display, "createdAt": _iso(r.created_at),
        "updatedAt": _iso(r.updated_at),
        "canEdit": admin or r.created_by == user,
        "overdue": r.status == "planlandi" and starts < now,
    }


def _meeting_values(body: dict[str, Any], *, partial: bool, current: Any = None) -> dict[str, Any]:
    out: dict[str, Any] = {}

    def has(k: str) -> bool:
        return not partial or k in body

    if has("date") or has("time"):
        src = dict(body)
        if current is not None:
            d, t = _local_parts(current.starts_at)
            src.setdefault("date", d)
            src.setdefault("time", t)
        out["starts_at"] = _local_start(src)
    if has("minutes"):
        v = body.get("minutes")
        if v in (None, ""):
            out["minutes"] = None
        else:
            try:
                m = int(v)
            except (TypeError, ValueError):
                raise RelationError("Süre dakika olarak yazılmalı.") from None
            if not 5 <= m <= 24 * 60:
                raise RelationError("Süre 5 dakika ile 24 saat arasında olmalı.")
            out["minutes"] = m
    if has("status"):
        out["status"] = _choice(body, "status", STATUSES, "Durum", "planlandi")
    if has("channel"):
        out["channel"] = _choice(body, "channel", CHANNELS, "Kanal", "yuz_yuze")
    if has("location"):
        out["location"] = _text(body, "location", 200, "Yer")
    if has("topic"):
        out["topic"] = _text(body, "topic", 300, "Konu", required=True)
    if has("notes"):
        out["notes"] = _long(body, "notes", 20000, "Görüşme notu")
    if has("tone"):
        out["tone"] = _choice(body, "tone", TONES, "Ton")
    if has("nextStep"):
        out["next_step"] = _text(body, "nextStep", 500, "Sıradaki adım")
    if has("nextDue"):
        v = str(body.get("nextDue") or "").strip()
        try:
            out["next_due"] = date.fromisoformat(v) if v else None
        except ValueError:
            raise RelationError("Sıradaki adım tarihi YYYY-AA-GG biçiminde olmalı.") from None
    if has("nextDone"):
        out["next_done"] = bool(body.get("nextDone"))
    if has("private"):
        out["private"] = bool(body.get("private"))
    if has("participants"):
        ps = body.get("participants") or []
        if not isinstance(ps, list):
            raise RelationError("Katılımcılar liste olmalı.")
        clean, seen = [], set()
        for p in ps:
            if not isinstance(p, dict):
                continue
            u = str(p.get("username") or "").strip().lower()[:120]
            d = re.sub(r"\s+", " ", str(p.get("display") or u)).strip()[:200]
            if u and u not in seen:
                seen.add(u)
                clean.append({"username": u, "display": d or u})
        out["participants_json"] = json.dumps(clean, ensure_ascii=False)
    return out


def _book_room(rooms_mod: Any, engine: sa.engine.Engine, tenant: str, user: str, display: str, room_id: str,
               starts: datetime, minutes: Optional[int], title: str) -> dict[str, Any]:
    if not minutes:
        raise RelationError("Oda ayırmak için süre gerekli.")
    day, start = _local_parts(starts)
    end_local = _utc(starts).astimezone(TZ) + timedelta(minutes=minutes)
    if end_local.date().isoformat() != day:
        raise RelationError("Oda rezervasyonu aynı gün içinde bitmeli.")
    try:
        return rooms_mod.book(engine, tenant, room_id, user, display,
                              {"date": day, "start": start, "end": end_local.strftime("%H:%M"), "title": title})
    except rooms_mod.RoomError as e:
        raise RelationError(f"Oda ayrılamadı: {e}", getattr(e, "status", 422)) from e


def _cancel_room(rooms_mod: Any, engine: sa.engine.Engine, tenant: str, booking_id: Optional[str], user: str) -> None:
    if not booking_id:
        return
    try:
        rooms_mod.cancel(engine, tenant, booking_id, user, admin=True)
    except rooms_mod.RoomError as e:   # bitmiş ya da zaten iptal edilmiş rezervasyon: görüşmeyi etkilemez
        log.info("author meeting room booking %s not cancelled: %s", booking_id, e)


def create_meeting(engine: sa.engine.Engine, tenant: str, user: str, display: str, admin: bool,
                   body: dict[str, Any], rooms_mod: Any = None) -> dict[str, Any]:
    if body.get("cardId"):
        with engine.connect() as c:
            card = _get_card(c, tenant, str(body["cardId"]))
    elif body.get("crmContactId"):
        card, _ = card_for_crm(engine, tenant, user, str(body["crmContactId"]), str(body.get("name") or ""))
    else:
        raise RelationError("Görüşmenin kime ait olduğu (yazar kartı ya da CRM kişisi) gerekli.")
    if card.archived_at is not None:
        raise RelationError("Arşivdeki karta görüşme yazılmaz; önce kartı arşivden çıkarın.")
    vals = _meeting_values(body, partial=False)
    now = _now()
    if vals["status"] == "planlandi" and vals["starts_at"] < now - timedelta(days=1):
        raise RelationError("Geçmiş tarihli görüşme «Yapıldı» olarak yazılır.")
    if vals["status"] == "yapildi" and vals["starts_at"] > now + timedelta(minutes=5):
        raise RelationError("İleri tarihli görüşme yapıldı olarak yazılamaz; randevu olarak planlayın.")
    mid = uuid.uuid4().hex
    booking = None
    room_id = str(body.get("roomId") or "").strip()
    if room_id:
        if rooms_mod is None or vals["status"] != "planlandi":
            raise RelationError("Oda yalnız planlanan randevuya ayrılır.")
        booking = _book_room(rooms_mod, engine, tenant, user, display, room_id, vals["starts_at"], vals.get("minutes"),
                             f"Yazar görüşmesi: {card.name}")
    try:
        with engine.begin() as c:
            c.execute(MEETINGS.insert().values(
                id=mid, tenant_id=tenant, card_id=card.id, created_by=user, created_display=(display or user)[:200],
                created_at=now, updated_by=user, updated_at=now,
                room_id=room_id if booking else None,
                room_booking_id=booking["id"] if booking else None, room_name=booking.get("roomName") if booking else None,
                **vals))
            row = c.execute(sa.select(MEETINGS).where(MEETINGS.c.id == mid)).first()
    except Exception:
        if booking:
            _cancel_room(rooms_mod, engine, tenant, booking["id"], user)
        raise
    return dict(_meeting(row, user, admin, now), cardName=card.name)


def update_meeting(engine: sa.engine.Engine, tenant: str, user: str, display: str, admin: bool, meeting_id: str,
                   body: dict[str, Any], rooms_mod: Any = None) -> tuple[dict[str, Any], dict[str, Any]]:
    mid = _cid(meeting_id, "Görüşme")
    with engine.connect() as c:
        row = c.execute(sa.select(MEETINGS).where(MEETINGS.c.id == mid, MEETINGS.c.tenant_id == tenant)).first()
    if not row:
        raise RelationError("Görüşme bulunamadı.", 404)
    only_step = set(body) <= {"nextDone"}
    if not (admin or row.created_by == user or (only_step and _visible(row, user, admin))):
        raise RelationError("Görüşmeyi yalnız yazan kişi ya da yönetici değiştirir.", 403)
    vals = _meeting_values(body, partial=True, current=row)
    status = vals.get("status", row.status)
    starts = vals.get("starts_at", _utc(row.starts_at))
    now = _now()
    if status == "yapildi" and starts > now + timedelta(minutes=5):
        raise RelationError("Henüz gelmemiş randevu yapıldı olarak işaretlenemez.")
    booking_id, room_name = row.room_booking_id, row.room_name
    moved = ("starts_at" in vals and vals["starts_at"] != _utc(row.starts_at)) or \
        ("minutes" in vals and vals["minutes"] != row.minutes)
    # Oda: gövdede roomId yoksa var olan oda korunur (tarih/süre değişirse aynı oda yeni saate yeniden ayrılır),
    # '' ise bırakılır, başka bir kimlikse o oda ayrılır.
    asked = body.get("roomId")
    target = (row.room_id if asked is None else str(asked).strip()) or None
    if booking_id and (status == "iptal" or moved or target != row.room_id):
        _cancel_room(rooms_mod, engine, tenant, booking_id, user)
        booking_id, room_name = None, None
    room_id = row.room_id if booking_id else None
    if target and status == "planlandi" and not booking_id:
        if rooms_mod is None:
            raise RelationError("Oda ayrılamadı: oda servisi yok.", 503)
        with engine.connect() as c:
            card_name = c.execute(sa.select(CARDS.c.name).where(CARDS.c.id == row.card_id)).scalar() or ""
        booked = _book_room(rooms_mod, engine, tenant, user, display, target, starts,
                            vals.get("minutes", row.minutes), f"Yazar görüşmesi: {card_name}")
        booking_id, room_name, room_id = booked["id"], booked.get("roomName"), target
    vals.update(room_id=room_id, room_booking_id=booking_id, room_name=room_name)
    changed = {k: v for k, v in vals.items()
               if (_utc(row.starts_at) if k == "starts_at" else getattr(row, k)) != v}
    with engine.begin() as c:
        if changed:
            c.execute(MEETINGS.update().where(MEETINGS.c.id == mid).values(updated_by=user, updated_at=now, **changed))
        out = c.execute(sa.select(MEETINGS).where(MEETINGS.c.id == mid)).first()
    diff = {k: {"before": str(getattr(row, k)) if getattr(row, k) is not None else None,
                "after": str(v) if v is not None else None}
            for k, v in changed.items() if k not in ("notes", "participants_json")}
    if "notes" in changed:
        diff["notes"] = {"before": "…", "after": "…"}   # not metni değişiklik kaydına kopyalanmaz
    return _meeting(out, user, admin, now), diff


def delete_meeting(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, meeting_id: str,
                   rooms_mod: Any = None) -> dict[str, Any]:
    mid = _cid(meeting_id, "Görüşme")
    with engine.begin() as c:
        row = c.execute(sa.select(MEETINGS).where(MEETINGS.c.id == mid, MEETINGS.c.tenant_id == tenant)
                        .with_for_update()).first()
        if not row:
            raise RelationError("Görüşme bulunamadı.", 404)
        if not (admin or row.created_by == user):
            raise RelationError("Görüşmeyi yalnız yazan kişi ya da yönetici siler.", 403)
        c.execute(MEETINGS.delete().where(MEETINGS.c.id == mid))
    if row.room_booking_id and rooms_mod is not None:
        _cancel_room(rooms_mod, engine, tenant, row.room_booking_id, user)
    return {"id": row.id, "cardId": row.card_id, "topic": row.topic, "date": _local_parts(row.starts_at)[0]}


# ------------------------------------------------------------------------------------------ ısı

def month_keys(now: Optional[datetime] = None, months: int = MONTHS) -> list[str]:
    """Son `months` ay (İstanbul), eskiden yeniye 'YYYY-AA'."""
    loc = (now or _now()).astimezone(TZ)
    y, m = loc.year, loc.month
    out = []
    for _ in range(months):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def heat(meetings: Iterable[Any], now: Optional[datetime] = None) -> dict[str, Any]:
    """Kartın görüşmelerinden ısı puanı ve ay ay temas sayısı. Yalnız yapılmış görüşme sayılır."""
    now = now or _now()
    keys = month_keys(now)
    by_month = {k: 0 for k in keys}
    done = sorted((m for m in meetings if m.status == "yapildi"), key=lambda m: _utc(m.starts_at), reverse=True)
    upcoming = sorted((m for m in meetings if m.status == "planlandi" and _utc(m.starts_at) >= now),
                      key=lambda m: _utc(m.starts_at))
    year_ago = now - timedelta(days=365)
    in_year = 0
    for m in done:
        s = _utc(m.starts_at)
        k = s.astimezone(TZ).strftime("%Y-%m")
        if k in by_month:
            by_month[k] += 1
        if s >= year_ago:
            in_year += 1
    if not done:
        score, recency, freq, tone = 0, 0, 0, 0
        days = None
    else:
        days = max(0, (now - _utc(done[0].starts_at)).days)
        recency = round(RECENCY_MAX * max(0.0, 1 - days / RECENCY_DAYS))
        freq = min(FREQUENCY_MAX, FREQUENCY_EACH * in_year)
        last3 = done[:3]
        tone = round(sum(TONE_POINTS.get(m.tone, 10) for m in last3) / len(last3))
        score = recency + freq + tone
    band = "yok" if score == 0 else "soguk" if score <= 33 else "ilik" if score <= 66 else "sicak"
    return {"score": score, "band": band, "parts": {"recency": recency, "frequency": freq, "tone": tone},
            "lastContact": _iso(done[0].starts_at) if done else None, "daysSince": days,
            "contactsYear": in_year, "months": [by_month[k] for k in keys],
            "next": _iso(upcoming[0].starts_at) if upcoming else None}


# ------------------------------------------------------------------------------------------ CRM (salt okuma)

def _prefix(schema: str) -> str:
    db, _, sch = (schema or "").strip().rpartition(".")
    for part in (db, sch):
        if part and not _NAME.match(part):
            raise RelationError(f"CRM şeması «{schema}» geçerli bir ad değil.", 503)
    if not sch:
        raise RelationError("CRM şeması girilmemiş; CRM okunamıyor.", 503)
    return (f"{db}." if db else "") + f"{sch}."


def _like(text: str) -> str:
    t = (text or "").strip()[:80].replace("'", "''")
    for ch in ("[", "%", "_"):
        t = t.replace(ch, f"[{ch}]")
    return t


def _since(value: str) -> str:
    v = (value or "").strip()
    try:
        return date.fromisoformat(v).isoformat()
    except ValueError:
        raise RelationError("Havuz başlangıç tarihi YYYY-AA-GG biçiminde olmalı.", 503) from None


def _is_author(p: str, col: str) -> str:
    return (f"EXISTS (SELECT 1 FROM {p}new_eserkatilimBase e JOIN {p}new_katilimcitipiBase t"
            f" ON t.new_katilimcitipiId = e.new_katilimciTipi WHERE e.statecode = 0 AND t.new_name = N'Yazar'"
            f" AND e.new_Katilimsaglayan = {col})")


def _pool_from(p: str, since: str, q: str, closed: bool) -> str:
    sql = (f" FROM {p}new_projeBase j JOIN {p}ContactBase k ON k.ContactId = j.new_OlasYazarYazar"
           f" WHERE j.statecode = 0 AND k.statecode = 0 AND j.CreatedOn >= '{_since(since)}'"
           f" AND NOT {_is_author(p, 'j.new_OlasYazarYazar')}")
    if not closed:
        sql += f" AND (j.statuscode IS NULL OR j.statuscode NOT IN ({', '.join(map(str, PROJECT_CLOSED))}))"
    if q.strip():
        sql += f" AND k.FullName LIKE N'%{_like(q)}%'"
    return sql


def pool_count_sql(schema: str, since: str, q: str = "", closed: bool = False) -> str:
    p = _prefix(schema)
    return f"SELECT COUNT(DISTINCT k.ContactId) AS n{_pool_from(p, since, q, closed)}"


def pool_list_sql(schema: str, since: str, page: int, q: str = "", closed: bool = False) -> str:
    p = _prefix(schema)
    return (
        "SELECT k.ContactId, k.FullName, COUNT(*) AS proje, MAX(j.CreatedOn) AS son"
        f"{_pool_from(p, since, q, closed)} GROUP BY k.ContactId, k.FullName"
        f" ORDER BY MAX(j.CreatedOn) DESC, k.ContactId OFFSET {max(0, int(page)) * PAGE_SIZE} ROWS"
        f" FETCH NEXT {PAGE_SIZE} ROWS ONLY"
    )


def pool_projects_sql(schema: str, since: str, ids: list[str]) -> str:
    p = _prefix(schema)
    inn = ", ".join(f"'{_guid(i)}'" for i in ids)
    return (
        "SELECT j.new_OlasYazarYazar AS kisi, j.new_projeId, j.new_name, j.statuscode, j.CreatedOn, u.FullName AS editor"
        f" FROM {p}new_projeBase j LEFT JOIN {p}SystemUserBase u ON u.SystemUserId = j.new_editoru"
        f" WHERE j.statecode = 0 AND j.CreatedOn >= '{_since(since)}' AND j.new_OlasYazarYazar IN ({inn})"
        " ORDER BY j.CreatedOn DESC"
    )


def contracted_authors_sql(schema: str) -> str:
    """Yürürlükte sözleşmesi olan yazarlar (yazar rolüyle eser kaydı olan ve sözleşme tarafı olan kişiler)."""
    p = _prefix(schema)
    return (
        "SELECT k.ContactId, k.FullName, COUNT(DISTINCT s.new_sozlesmeId) AS sozlesme,"
        " MIN(s.new_SozlesmeBitisTarihi) AS en_yakin_bitis"
        f" FROM {p}new_sozlesmetarafiBase t JOIN {p}new_sozlesmeBase s ON s.new_sozlesmeId = t.new_sozlesmeid"
        f" JOIN {p}ContactBase k ON k.ContactId = t.new_kisi"
        f" WHERE t.statecode = 0 AND s.statecode = 0 AND s.statuscode IN ({', '.join(map(str, CONTRACT_ACTIVE))})"
        " AND (s.new_SozlesmeBitisTarihi IS NULL OR s.new_SozlesmeBitisTarihi >= CAST(GETDATE() AS date))"
        f" AND {_is_author(p, 't.new_kisi')}"
        " GROUP BY k.ContactId, k.FullName"
    )


def crm_events_sql(schema: str, since: str) -> str:
    """Son 12 ayda yazarların CRM olayları, kişi × ay: yazar rolüyle yeni eser kaydı ve başlayan sözleşme."""
    p = _prefix(schema)
    s = _since(since)
    return (
        "SELECT x.kisi, x.tur, x.yil, x.ay, COUNT(*) AS adet FROM ("
        " SELECT e.new_Katilimsaglayan AS kisi, 'eser' AS tur, YEAR(e.CreatedOn) AS yil, MONTH(e.CreatedOn) AS ay"
        f" FROM {p}new_eserkatilimBase e JOIN {p}new_katilimcitipiBase t ON t.new_katilimcitipiId = e.new_katilimciTipi"
        f" WHERE e.statecode = 0 AND t.new_name = N'Yazar' AND e.CreatedOn >= '{s}'"
        " UNION ALL"
        " SELECT r.new_kisi AS kisi, 'sozlesme' AS tur, YEAR(s.new_SozlesmeBaslangicTarihi) AS yil,"
        " MONTH(s.new_SozlesmeBaslangicTarihi) AS ay"
        f" FROM {p}new_sozlesmetarafiBase r JOIN {p}new_sozlesmeBase s ON s.new_sozlesmeId = r.new_sozlesmeid"
        f" WHERE r.statecode = 0 AND s.statecode = 0 AND s.new_SozlesmeBaslangicTarihi >= '{s}'"
        f" AND {_is_author(p, 'r.new_kisi')}"
        ") x WHERE x.kisi IS NOT NULL GROUP BY x.kisi, x.tur, x.yil, x.ay"
    )


def similar_sql(schema: str, name: str) -> str:
    """Yeni kart açılırken aynı adlı CRM kişileri (çift kart ve çift kişi açılmasın)."""
    p = _prefix(schema)
    words = [w for w in re.split(r"\s+", (name or "").strip()) if len(w) >= 2][:4]
    if not words:
        raise RelationError("Ad gerekli.")
    cond = " AND ".join(f"k.FullName LIKE N'%{_like(w)}%'" for w in words)
    return (
        "SELECT k.ContactId, k.FullName, COUNT(*) OVER () AS toplam,"
        f" CASE WHEN {_is_author(p, 'k.ContactId')} THEN 1 ELSE 0 END AS yazar"
        f" FROM {p}ContactBase k WHERE k.statecode = 0 AND {cond}"
        " ORDER BY k.FullName, k.ContactId OFFSET 0 ROWS FETCH NEXT 20 ROWS ONLY"
    )


def _s(v: Any) -> Optional[str]:
    t = None if v is None else str(v).strip()
    return t or None


def _n(v: Any) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _lid(v: Any) -> str:
    return str(v or "").strip().strip("{}").lower()


def _timing(res: dict[str, Any]) -> dict[str, Any]:
    return {"ms": res.get("dbMs"), "cached": bool(res.get("cached")), "at": res.get("cachedAt") or res.get("computedAt")}


# ------------------------------------------------------------------------------------------ okumalar

def _cards_with_meetings(engine: sa.engine.Engine, tenant: str, *, archived: bool = False) -> tuple[list[Any], dict[str, list[Any]]]:
    with engine.connect() as c:
        stmt = sa.select(CARDS).where(CARDS.c.tenant_id == tenant)
        stmt = stmt.where(CARDS.c.archived_at.isnot(None) if archived else CARDS.c.archived_at.is_(None))
        cards = c.execute(stmt).fetchall()
        rows = c.execute(sa.select(MEETINGS).where(MEETINGS.c.tenant_id == tenant, MEETINGS.c.status != "iptal")).fetchall()
    by_card: dict[str, list[Any]] = {}
    for m in rows:
        by_card.setdefault(m.card_id, []).append(m)
    return cards, by_card


def _card_summary(r: Any, ms: list[Any], now: datetime) -> dict[str, Any]:
    h = heat(ms, now)
    return dict(_card(r), heat=h, meetings=len([m for m in ms if m.status == "yapildi"]),
                openSteps=sum(1 for m in ms if m.next_step and not m.next_done))


def list_cards(engine: sa.engine.Engine, tenant: str, user: str, *, stage: str = "", q: str = "", scope: str = "",
               archived: bool = False) -> dict[str, Any]:
    """Havuz panosu: yazar olmamış kartlar aşama aşama (ya da tek aşama). Sessiz tavan yok, hepsi döner."""
    now = _now()
    cards, by_card = _cards_with_meetings(engine, tenant, archived=archived)
    nq = _norm(q)
    items = []
    for r in cards:
        if r.stage == "yazar" and stage != "yazar":
            continue
        if stage and r.stage != stage:
            continue
        if nq and nq not in _norm(r.name):
            continue
        if scope == "benim" and user not in (r.owner or "", r.created_by):
            continue
        items.append(_card_summary(r, by_card.get(r.id, []), now))
    items.sort(key=lambda x: x["updatedAt"] or "", reverse=True)
    counts = {s: 0 for s in POOL_STAGES}
    for r in cards:
        if r.stage in counts:
            counts[r.stage] += 1
    return {"items": items, "total": len(items), "stages": counts}


def card_detail(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, card_id: str) -> dict[str, Any]:
    now = _now()
    with engine.connect() as c:
        row = _get_card(c, tenant, card_id)
        ms = c.execute(sa.select(MEETINGS).where(MEETINGS.c.card_id == row.id).order_by(MEETINGS.c.starts_at.desc())).fetchall()
    live = [m for m in ms if m.status != "iptal"]
    return dict(_card(row), heat=heat(live, now), timeline=[_meeting(m, user, admin, now) for m in ms])


def by_crm(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, contact_id: str) -> dict[str, Any]:
    cid = _guid(contact_id)
    with engine.connect() as c:
        row = _card_by_crm(c, tenant, cid)
    if not row:
        return {"card": None, "heat": heat([]), "timeline": []}
    d = card_detail(engine, tenant, user, admin, row.id)
    return {"card": {k: v for k, v in d.items() if k not in ("heat", "timeline")}, "heat": d["heat"], "timeline": d["timeline"]}


def agenda(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, *, scope: str = "benim",
           days: int = 30) -> dict[str, Any]:
    """Randevular ekranı: önümüzdeki randevular, notu girilmemiş geçmiş randevular, açık sıradaki adımlar.
    `benim`: yazdığım, katılımcısı olduğum ya da kartın sorumlusu olduğum."""
    now = _now()
    today = now.astimezone(TZ).date()
    horizon = now + timedelta(days=max(1, int(days)))
    with engine.connect() as c:
        cards = {r.id: r for r in c.execute(sa.select(CARDS).where(CARDS.c.tenant_id == tenant)).fetchall()}
        rows = c.execute(sa.select(MEETINGS).where(
            MEETINGS.c.tenant_id == tenant, MEETINGS.c.status != "iptal",
            sa.or_(sa.and_(MEETINGS.c.status == "planlandi", MEETINGS.c.starts_at < horizon),
                   sa.and_(MEETINGS.c.next_step.isnot(None), MEETINGS.c.next_done.is_(False)))
        ).order_by(MEETINGS.c.starts_at)).fetchall()

    def mine(m: Any) -> bool:
        card = cards.get(m.card_id)
        parts = {str(p.get("username") or "").lower() for p in _json(m.participants_json) if isinstance(p, dict)}
        return m.created_by == user or user in parts or (card is not None and card.owner == user)

    def item(m: Any) -> dict[str, Any]:
        card = cards.get(m.card_id)
        return dict(_meeting(m, user, admin, now), cardName=card.name if card else None,
                    cardStage=card.stage if card else None, crmContactId=card.crm_contact_id if card else None)

    upcoming, missing, steps = [], [], []
    for m in rows:
        if scope == "benim" and not mine(m):
            continue
        if not _visible(m, user, admin) and scope != "benim":
            # başkasının gizli notunun adımı listelenmez; randevunun varlığı listelenir
            if m.status != "planlandi":
                continue
        if m.status == "planlandi":
            (upcoming if _utc(m.starts_at) >= now else missing).append(item(m))
        if m.next_step and not m.next_done and m.status == "yapildi" and _visible(m, user, admin):
            it = item(m)
            it["stepLate"] = bool(m.next_due and m.next_due < today)
            steps.append(it)
    steps.sort(key=lambda x: (x["nextDue"] or "9999", x["startsAt"]))
    missing.sort(key=lambda x: x["startsAt"], reverse=True)
    return {"upcoming": upcoming, "missingNotes": missing, "openSteps": steps, "days": days,
            "today": today.isoformat(), "scope": scope}


def pool_crm(schema: str, run: Callable[[str], dict[str, Any]], engine: sa.engine.Engine, tenant: str, since: str,
             page_no: int, *, q: str = "", closed: bool = False) -> dict[str, Any]:
    """CRM'de olası yazar olup henüz yazar rolüyle eser kaydı olmayan kişiler, bir sayfa + toplam."""
    head = (run(pool_count_sql(schema, since, q, closed)).get("records") or [{}])[0]
    res = run(pool_list_sql(schema, since, page_no, q, closed))
    items = [{"crmContactId": _lid(r.get("ContactId")), "name": _s(r.get("FullName")), "projects": _n(r.get("proje")),
              "last": _s(r.get("son")), "latest": None, "cardId": None, "cardStage": None}
             for r in res.get("records") or []]
    ids = [i["crmContactId"] for i in items if i["crmContactId"]]
    if ids:
        by = {i["crmContactId"]: i for i in items}
        for r in run(pool_projects_sql(schema, since, ids)).get("records") or []:
            it = by.get(_lid(r.get("kisi")))
            if it is not None and it["latest"] is None:
                it["latest"] = {"id": _lid(r.get("new_projeId")), "name": _s(r.get("new_name")),
                                "status": _s(r.get("statuscode")), "on": _s(r.get("CreatedOn")),
                                "editor": _s(r.get("editor"))}
        with engine.connect() as c:
            for r in c.execute(sa.select(CARDS.c.id, CARDS.c.stage, CARDS.c.crm_contact_id).where(
                    CARDS.c.tenant_id == tenant, CARDS.c.crm_contact_id.in_(ids))).fetchall():
                it = by.get(r.crm_contact_id)
                if it is not None:
                    it["cardId"], it["cardStage"] = r.id, r.stage
    return {"items": items, "total": _n(head.get("n")), "page": max(0, int(page_no)), "pageSize": PAGE_SIZE,
            "since": _since(since), "db": _timing(res)}


def similar(schema: str, run: Optional[Callable[[str], dict[str, Any]]], engine: sa.engine.Engine, tenant: str,
            name: str) -> dict[str, Any]:
    """Aynı adlı kartlar (bizde) ve CRM kişileri. CRM okunamazsa kartlar yine döner."""
    nq = _norm(name)
    if len(nq) < 3:
        return {"cards": [], "crm": [], "crmTotal": 0}
    words = nq.split()
    with engine.connect() as c:
        rows = c.execute(sa.select(CARDS).where(CARDS.c.tenant_id == tenant)).fetchall()
    cards = [{"id": r.id, "name": r.name, "stage": r.stage, "stageLabel": STAGES.get(r.stage), "archived": r.archived_at is not None,
              "crmContactId": r.crm_contact_id}
             for r in rows if all(w in _norm(r.name) for w in words)]
    crm: list[dict[str, Any]] = []
    total = 0
    crm_error = None
    if run is not None:
        try:
            recs = run(similar_sql(schema, name)).get("records") or []
            crm = [{"crmContactId": _lid(r.get("ContactId")), "name": _s(r.get("FullName")), "author": bool(_n(r.get("yazar")))}
                   for r in recs]
            total = _n(recs[0].get("toplam")) if recs else 0
        except Exception as e:  # noqa: BLE001 — CRM kapalıyken kart yine açılabilsin
            crm_error = str(e)[:200]
    linked = {c["crmContactId"]: c["id"] for c in cards if c["crmContactId"]}
    with engine.connect() as c:
        ids = [x["crmContactId"] for x in crm]
        if ids:
            for r in c.execute(sa.select(CARDS.c.id, CARDS.c.crm_contact_id).where(
                    CARDS.c.tenant_id == tenant, CARDS.c.crm_contact_id.in_(ids))).fetchall():
                linked[r.crm_contact_id] = r.id
    for x in crm:
        x["cardId"] = linked.get(x["crmContactId"])
    return {"cards": cards, "crm": crm, "crmTotal": total, "crmError": crm_error}


def heatmap(schema: str, fetch_all: Callable[[str], list[dict[str, Any]]], engine: sa.engine.Engine, tenant: str,
            user: str, *, scope: str = "hepsi", q: str = "", order: str = "soguk", page_no: int = 0,
            now: Optional[datetime] = None) -> dict[str, Any]:
    """Satırlar: yürürlükte sözleşmesi olan yazarlar (CRM) ∪ kartı olan herkes (arşiv hariç). Hücre: o ayda
    yapılan görüşme sayısı; CRM olayları (yeni eser, yeni sözleşme) ayrı sayı. Tamamı hesaplanır, sayfa sayfa döner."""
    now = now or _now()
    keys = month_keys(now)
    since = keys[0] + "-01"
    cards, by_card = _cards_with_meetings(engine, tenant)
    rows: dict[str, dict[str, Any]] = {}

    def blank(key: str, name: str) -> dict[str, Any]:
        return {"key": key, "name": name, "cardId": None, "crmContactId": None, "stage": None, "stageLabel": None,
                "owner": None, "ownerDisplay": None, "contracts": 0, "contractEnds": None,
                "heat": heat([], now), "crm": [0] * len(keys), "crmBooks": 0, "crmContracts": 0}

    crm_ok, crm_error = True, None
    try:
        authors = fetch_all(contracted_authors_sql(schema))
        events = fetch_all(crm_events_sql(schema, since))
    except Exception as e:  # noqa: BLE001 — CRM okunamazsa yalnız kartlarla çizilir, ekran bunu söyler
        log.warning("author heatmap: CRM okunamadı: %s", e)
        authors, events, crm_ok, crm_error = [], [], False, str(e)[:300]
    for a in authors:
        cid = _lid(a.get("ContactId"))
        if not cid:
            continue
        r = rows.setdefault(cid, blank(cid, _s(a.get("FullName")) or "Adı kayıtlı değil"))
        r["crmContactId"] = cid
        r["contracts"] = _n(a.get("sozlesme"))
        r["contractEnds"] = _s(a.get("en_yakin_bitis"))
    for card in cards:
        key = card.crm_contact_id or card.id
        r = rows.setdefault(key, blank(key, card.name))
        r.update(cardId=card.id, crmContactId=card.crm_contact_id, stage=card.stage,
                 stageLabel=STAGES.get(card.stage), owner=card.owner, ownerDisplay=card.owner_display,
                 name=r["name"] if card.crm_contact_id and r["name"] else card.name)
        r["heat"] = heat(by_card.get(card.id, []), now)
        r["_created_by"] = card.created_by
        r["_mine"] = user in (card.owner or "", card.created_by) or any(
            m.created_by == user for m in by_card.get(card.id, []))
    idx = {k: i for i, k in enumerate(keys)}
    for e in events:
        r = rows.get(_lid(e.get("kisi")))
        if r is None:
            continue
        i = idx.get(f"{_n(e.get('yil')):04d}-{_n(e.get('ay')):02d}")
        if i is None:
            continue
        n = _n(e.get("adet"))
        r["crm"][i] += n
        if _s(e.get("tur")) == "sozlesme":
            r["crmContracts"] += n
        else:
            r["crmBooks"] += n

    items = list(rows.values())
    if scope == "sozlesmeli":
        items = [r for r in items if r["contracts"]]
    elif scope == "havuz":
        items = [r for r in items if r["stage"] in POOL_STAGES]
    elif scope == "benim":
        items = [r for r in items if r.get("_mine")]
    nq = _norm(q)
    if nq:
        items = [r for r in items if nq in _norm(r["name"])]
    bands = {"yok": 0, "soguk": 0, "ilik": 0, "sicak": 0}
    for r in items:
        bands[r["heat"]["band"]] += 1
    if order == "sicak":
        items.sort(key=lambda r: (-r["heat"]["score"], r["name"].casefold()))
    elif order == "ad":
        items.sort(key=lambda r: r["name"].casefold())
    else:
        # En soğuk önce; eşitlikte sözleşmesi daha önce biten (arama sırası) ve CRM'de hareketli olan öne.
        items.sort(key=lambda r: (r["heat"]["score"], r["contractEnds"] or "9999", -(r["crmBooks"] + r["crmContracts"]),
                                  r["name"].casefold()))
    total = len(items)
    page_no = max(0, int(page_no))
    chunk = items[page_no * PAGE_SIZE:(page_no + 1) * PAGE_SIZE]
    for r in chunk:
        r.pop("_created_by", None)
        r.pop("_mine", None)
    return {"months": keys, "items": chunk, "total": total, "page": page_no, "pageSize": PAGE_SIZE,
            "bands": bands, "crmOk": crm_ok, "crmError": crm_error, "scope": scope, "order": order}
