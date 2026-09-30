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
  tonsuz 10, olumsuz 0). Hiç görüşme yoksa 0 ve «temas yok»; görüşme varsa 0–33 soğuk, 34–66 ılık, 67–100 sıcak. CRM olayları
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

import sqlalchemy as sa

from semantic_bridge import relations_core as core
# Ortak çekirdek (M7 ve M28 paylaşır): doğrulama, ısı puanı, gizli not, CRM şema/LIKE kaçışı. Adlar M7'nin eski adlarıyla
# burada da durur; testler ve çağıranlar `author_relations.heat`, `.TZ`, `.RelationError` … diye kullanmaya devam eder.
from semantic_bridge.relations_core import (  # noqa: F401 — yeniden dışa verilen adlar
    CHANNELS, FREQUENCY_EACH, FREQUENCY_MAX, MONTHS, RECENCY_DAYS, RECENCY_MAX, TONE_MAX, TONE_POINTS, TONES, TZ,
    RelationError, heat, month_keys,
)

log = logging.getLogger("semantic.author_relations")
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
STATUSES = {"planlandi": "Planlandı", "yapildi": "Yapıldı", "iptal": "İptal"}

PAGE_SIZE = 50


# new_projeBase.statuscode (editorial_intake ile aynı ölçüm, 2026-09-24): Red ve iptal.
PROJECT_CLOSED = (100000012, 100000009, 100000021)
# new_sozlesmeBase.statuscode: yürürlükte sayılanlar (editorial.ACTIVE_STATUS).
CONTRACT_ACTIVE = (100000000, 100000006, 100000007)

_ready: set[int] = set()
_lock = threading.Lock()


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)
        _ready.add(id(engine))


def meta() -> dict[str, Any]:
    """Ekranın seçenek listeleri ve ısı puanının tanımı (ekranda açıklama olarak gösterilir)."""
    pairs = lambda d: [{"key": k, "label": v} for k, v in d.items()]  # noqa: E731
    return {"stages": pairs(STAGES), "poolStages": list(POOL_STAGES), "sources": pairs(SOURCES),
            "channels": pairs(CHANNELS), "tones": pairs(TONES), "statuses": pairs(STATUSES),
            "heat": core.heat_meta()}


# ------------------------------------------------------------------------------------------ yardımcılar

_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_GUID = core.GUID_RE
_EMAIL, _PHONE, _URL = core.EMAIL_RE, core.PHONE_RE, core.URL_RE
_now, _utc, _iso = core.now, core.utc, core.iso
_text, _long, _choice, _list = core.text_field, core.long_field, core.choice, core.str_list
_guid, _cid, _json, _norm = core.guid, core.cid, core.json_list, core.norm


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


def card_stmt(tenant: str, card_id: str):
    return sa.select(CARDS).where(CARDS.c.id == _cid(card_id, "Yazar kartı"), CARDS.c.tenant_id == tenant)


def card_by_crm_stmt(tenant: str, contact_id: str):
    return sa.select(CARDS).where(CARDS.c.tenant_id == tenant, CARDS.c.crm_contact_id == contact_id)


def card_meetings_stmt(card_id: str):
    return sa.select(MEETINGS).where(MEETINGS.c.card_id == card_id).order_by(MEETINGS.c.starts_at.desc())


def cards_stmt(tenant: str, archived: bool = False):
    stmt = sa.select(CARDS).where(CARDS.c.tenant_id == tenant)
    return stmt.where(CARDS.c.archived_at.isnot(None) if archived else CARDS.c.archived_at.is_(None))


def live_meetings_stmt(tenant: str):
    """İptal edilmemiş bütün randevu ve görüşmeler (ısı ve sayılar bunlardan)."""
    return sa.select(MEETINGS).where(MEETINGS.c.tenant_id == tenant, MEETINGS.c.status != "iptal")


def all_cards_stmt(tenant: str):
    return sa.select(CARDS).where(CARDS.c.tenant_id == tenant)


def agenda_horizon(now: datetime, days: int) -> datetime:
    return now + timedelta(days=max(1, int(days)))


def agenda_meetings_stmt(tenant: str, horizon: datetime):
    """Randevular ekranı: ufka kadar planlanan randevular + kapanmamış sıradaki adımı olan görüşmeler."""
    return sa.select(MEETINGS).where(
        MEETINGS.c.tenant_id == tenant, MEETINGS.c.status != "iptal",
        sa.or_(sa.and_(MEETINGS.c.status == "planlandi", MEETINGS.c.starts_at < horizon),
               sa.and_(MEETINGS.c.next_step.isnot(None), MEETINGS.c.next_done.is_(False)))
    ).order_by(MEETINGS.c.starts_at)


def _get_card(c: Any, tenant: str, card_id: str, *, lock: bool = False) -> Any:
    stmt = card_stmt(tenant, card_id)
    row = c.execute(stmt.with_for_update() if lock else stmt).first()
    if not row:
        raise RelationError("Yazar kartı bulunamadı.", 404)
    return row


def _card_by_crm(c: Any, tenant: str, contact_id: str) -> Any:
    return c.execute(card_by_crm_stmt(tenant, contact_id)).first()


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
    return core.can_read(bool(r.private), r.created_by, r.participants_json, user, admin)


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
        out["participants_json"] = json.dumps(core.participants(body.get("participants") or []), ensure_ascii=False)
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

# `heat`, `month_keys` çekirdekten (relations_core); M7 görüşme tablosunun varsayılanlarıyla çalışır.
_band = core.band


#: CRM izleri: yazar adına açılan eser kaydı ve başlayan sözleşme. Yalnız yakınlık puanına girer.
TRACE_LABELS = {"eser": "yeni eser kaydı", "sozlesme": "sözleşme başlangıcı"}


_crm_day = core.crm_day


def with_trace(h: dict[str, Any], day: Optional[date], kind: Optional[str], now: Optional[datetime] = None) -> dict[str, Any]:
    """Isıya CRM izini katar: yakınlık, son görüşme ile son iz hangisi yeniyse ondan hesaplanır; sıklık ve ton yalnız
    görüşmeden gelir. Böylece hiç görüşme yazılmamış yazar da CRM hareketine göre soğuk/ılık ayrılır; «sıcak» için
    gerçek görüşme gerekir (iz tek başına en çok yakınlık puanını, 50'yi verir)."""
    if day is None:
        return h
    now = now or _now()
    t_days = max(0, (now.astimezone(TZ).date() - day).days)
    out = dict(h, lastTrace=day.isoformat(), traceKind=kind, traceDays=t_days)
    if h.get("daysSince") is not None and h["daysSince"] <= t_days:
        return out
    recency = round(RECENCY_MAX * max(0.0, 1 - t_days / RECENCY_DAYS))
    score = recency + h["parts"]["frequency"] + h["parts"]["tone"]
    return dict(out, score=score, band=_band(score), recencyFrom=kind, parts=dict(h["parts"], recency=recency))


def attention(h: dict[str, Any], contract_ends: Optional[str], meetings: Iterable[Any], *, warn_days: int,
              now: Optional[datetime] = None) -> list[str]:
    """«İlgi bekleyen» nedenleri: sözleşmesi yakında biten ama 60 gündür görüşülmeyen yazar, notu girilmemiş geçmiş
    randevu, tarihi geçmiş sıradaki adım. Görüşme günleri yalnız portal kaydından (CRM izi temas sayılmaz)."""
    now = now or _now()
    today = now.astimezone(TZ).date()
    out: list[str] = []
    end = _crm_day(contract_ends) if contract_ends else None
    if end is not None:
        left = (end - today).days
        talked = h.get("daysSince")          # yalnız görüşmeden; CRM izi bunu değiştirmez
        if 0 <= left <= warn_days and (talked is None or talked > 60):
            out.append(f"Sözleşmesi {left} gün sonra bitiyor; " + ("hiç görüşme yazılmadı" if talked is None else f"{talked} gündür görüşme yok"))
    ms = list(meetings)
    late = sum(1 for m in ms if m.status == "planlandi" and _utc(m.starts_at) < now)
    if late:
        out.append("Geçmiş randevunun notu girilmedi" if late == 1 else f"{late} geçmiş randevunun notu girilmedi")
    steps = sum(1 for m in ms if m.status == "yapildi" and m.next_step and not m.next_done and m.next_due and m.next_due < today)
    if steps:
        out.append("Sıradaki adımın tarihi geçti" if steps == 1 else f"{steps} sıradaki adımın tarihi geçti")
    return out


# ------------------------------------------------------------------------------------------ CRM (salt okuma)

_prefix, _like = core.crm_prefix, core.like


def _since(value: str) -> str:
    v = (value or "").strip()
    try:
        return date.fromisoformat(v).isoformat()
    except ValueError:
        raise RelationError("Havuz başlangıç tarihi YYYY-AA-GG biçiminde olmalı.", 503) from None


def _is_author(p: str, col: str) -> str:
    # Alt sorgunun takma adları (ya_e, ya_t) dış sorguda kullanılmaz: dıştaki `t`/`e` ile çakışınca SQL Server
    # içteki tabloyu seçer ve `t.new_kisi` «Invalid column name» verir (2026-09-28, canlı CRM'de yakalandı).
    return (f"EXISTS (SELECT 1 FROM {p}new_eserkatilimBase ya_e JOIN {p}new_katilimcitipiBase ya_t"
            f" ON ya_t.new_katilimcitipiId = ya_e.new_katilimciTipi WHERE ya_e.statecode = 0 AND ya_t.new_name = N'Yazar'"
            f" AND ya_e.new_Katilimsaglayan = {col})")


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
        " MIN(CASE WHEN ISNULL(s.new_suresizsozlesme, 0) = 0 THEN s.new_SozlesmeBitisTarihi END) AS en_yakin_bitis"
        f" FROM {p}new_sozlesmetarafiBase t JOIN {p}new_sozlesmeBase s ON s.new_sozlesmeId = t.new_sozlesmeid"
        f" JOIN {p}ContactBase k ON k.ContactId = t.new_kisi"
        f" WHERE t.statecode = 0 AND s.statecode = 0 AND s.statuscode IN ({', '.join(map(str, CONTRACT_ACTIVE))})"
        # Süresiz sözleşme, bitiş tarihi geçmiş görünse de yürürlüktedir; en yakın bitişe girmez.
        " AND (ISNULL(s.new_suresizsozlesme, 0) = 1 OR s.new_SozlesmeBitisTarihi IS NULL"
        " OR s.new_SozlesmeBitisTarihi >= CAST(GETDATE() AS date))"
        f" AND {_is_author(p, 't.new_kisi')}"
        " GROUP BY k.ContactId, k.FullName"
    )


def crm_events_sql(schema: str, since: str) -> str:
    """Son 12 ayda yazarların CRM olayları, kişi × ay: yazar rolüyle yeni eser kaydı ve başlayan sözleşme. Ay İstanbul
    saatiyle (CRM UTC saklar; +3 saat), `son` o aydaki en yeni kaydın ham (UTC) zamanı — ısıdaki son iz buradan."""
    p = _prefix(schema)
    s = _since(since)
    return (
        "SELECT x.kisi, x.tur, YEAR(DATEADD(hour, 3, x.gun)) AS yil, MONTH(DATEADD(hour, 3, x.gun)) AS ay,"
        " COUNT(*) AS adet, MAX(x.gun) AS son FROM ("
        " SELECT e.new_Katilimsaglayan AS kisi, 'eser' AS tur, e.CreatedOn AS gun"
        f" FROM {p}new_eserkatilimBase e JOIN {p}new_katilimcitipiBase t ON t.new_katilimcitipiId = e.new_katilimciTipi"
        f" WHERE e.statecode = 0 AND t.new_name = N'Yazar' AND e.CreatedOn >= '{s}'"
        " UNION ALL"
        " SELECT r.new_kisi AS kisi, 'sozlesme' AS tur, s.new_SozlesmeBaslangicTarihi AS gun"
        f" FROM {p}new_sozlesmetarafiBase r JOIN {p}new_sozlesmeBase s ON s.new_sozlesmeId = r.new_sozlesmeid"
        f" WHERE r.statecode = 0 AND s.statecode = 0 AND s.new_SozlesmeBaslangicTarihi >= '{s}'"
        f" AND {_is_author(p, 'r.new_kisi')}"
        ") x WHERE x.kisi IS NOT NULL GROUP BY x.kisi, x.tur, YEAR(DATEADD(hour, 3, x.gun)), MONTH(DATEADD(hour, 3, x.gun))"
    )


def crm_trace_sql(schema: str, contact_id: str) -> str:
    """Tek yazarın son CRM izi (kart panelindeki ısı için): yazar rolüyle son eser kaydı ve bugüne kadar başlamış son sözleşme."""
    p = _prefix(schema)
    cid = _guid(contact_id)
    return (
        "SELECT (SELECT MAX(e.CreatedOn)"
        f" FROM {p}new_eserkatilimBase e JOIN {p}new_katilimcitipiBase t ON t.new_katilimcitipiId = e.new_katilimciTipi"
        f" WHERE e.statecode = 0 AND t.new_name = N'Yazar' AND e.new_Katilimsaglayan = '{cid}') AS eser,"
        " (SELECT MAX(s.new_SozlesmeBaslangicTarihi)"
        f" FROM {p}new_sozlesmetarafiBase r JOIN {p}new_sozlesmeBase s ON s.new_sozlesmeId = r.new_sozlesmeid"
        f" WHERE r.statecode = 0 AND s.statecode = 0 AND r.new_kisi = '{cid}'"
        " AND s.new_SozlesmeBaslangicTarihi < DATEADD(day, 1, GETDATE())) AS sozlesme"
    )


def latest_trace(pairs: Iterable[tuple[str, Any]], now: Optional[datetime] = None) -> tuple[Optional[date], Optional[str]]:
    """(tür, CRM tarihi) çiftlerinden bugüne kadarki en yeni iz: (İstanbul günü, tür)."""
    today = (now or _now()).astimezone(TZ).date()
    best: tuple[Optional[date], Optional[str]] = (None, None)
    for kind, raw in pairs:
        d = _crm_day(raw)
        if d is not None and d <= today and (best[0] is None or d > best[0]):
            best = (d, kind)
    return best


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
        cards = c.execute(cards_stmt(tenant, archived)).fetchall()
        rows = c.execute(live_meetings_stmt(tenant)).fetchall()
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
        ms = c.execute(card_meetings_stmt(row.id)).fetchall()
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
    horizon = agenda_horizon(now, days)
    with engine.connect() as c:
        cards = {r.id: r for r in c.execute(all_cards_stmt(tenant)).fetchall()}
        rows = c.execute(agenda_meetings_stmt(tenant, horizon)).fetchall()

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
    # «horizon»: randevu sorgusunun çalıştığı ufuk (sorgu bilgisi aynı ifadeyi bununla kurar).
    return {"upcoming": upcoming, "missingNotes": missing, "openSteps": steps, "days": days,
            "today": today.isoformat(), "scope": scope, "horizon": horizon.isoformat()}


def cards_of_stmt(tenant: str, contact_ids: list[str]):
    """CRM kişilerinin kartları (havuzdaki «kartı var» işareti)."""
    return sa.select(CARDS.c.id, CARDS.c.stage, CARDS.c.crm_contact_id).where(
        CARDS.c.tenant_id == tenant, CARDS.c.crm_contact_id.in_(contact_ids))


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
            for r in c.execute(cards_of_stmt(tenant, ids)).fetchall():
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
            now: Optional[datetime] = None, warn_days: int = 60,
            loyalty: Optional[Callable[[], dict[str, dict[str, Any]]]] = None,
            crm: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Satırlar: yürürlükte sözleşmesi olan yazarlar (CRM) ∪ kartı olan herkes (arşiv hariç). Hücre: o ayda
    yapılan görüşme sayısı; CRM olayları (yeni eser, yeni sözleşme) ayrı sayı ve ısının yakınlık payına son iz olarak
    girer (`with_trace`). «İlgi bekleyen» nedenleri satırda (`attention`). Tamamı hesaplanır, sayfa sayfa döner."""
    now = now or _now()
    keys = month_keys(now)
    since = keys[0] + "-01"
    cards, by_card = _cards_with_meetings(engine, tenant)
    rows: dict[str, dict[str, Any]] = {}
    # Görüşmesiz satırın ısısı herkes için aynı: bir kez hesaplanır, satıra kopyası konur (binlerce yazarda her satırda
    # yeniden ay anahtarı kurulmaz; değer `heat([], now)` ile aynı).
    empty = heat([], now)

    def blank(key: str, name: str) -> dict[str, Any]:
        return {"key": key, "name": name, "cardId": None, "crmContactId": None, "stage": None, "stageLabel": None,
                "owner": None, "ownerDisplay": None, "contracts": 0, "contractEnds": None,
                "heat": dict(empty, parts=dict(empty["parts"]), months=list(empty["months"])),
                "crm": [0] * len(keys), "crmBooks": 0, "crmContracts": 0}

    crm_ok, crm_error = True, None
    try:
        # Önceden hazırlanmış CRM parçası varsa kaynak beklenmez (author_snapshots); yoksa canlı okunur.
        authors = crm["authors"] if crm else fetch_all(contracted_authors_sql(schema))
        events = crm["events"] if crm else fetch_all(crm_events_sql(schema, since))
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
        r.setdefault("_traces", []).append((_s(e.get("tur")) or "eser", e.get("son")))
        if _s(e.get("tur")) == "sozlesme":
            r["crmContracts"] += n
        else:
            r["crmBooks"] += n

    loy: dict[str, dict[str, Any]] = {}
    if loyalty is not None and crm_ok:
        try:
            loy = loyalty()
        except Exception as e:  # noqa: BLE001 — sadakat ek bilgidir, harita onsuz da çizilir
            log.warning("author heatmap: sadakat okunamadı: %s", e)
    for r in rows.values():
        r["loyalty"] = loy.get(r["crmContactId"] or "") if r["crmContactId"] else None
        day, kind = latest_trace(r.pop("_traces", []), now)
        if r["crmContactId"]:
            r["heat"] = with_trace(r["heat"], day, kind, now)
        r["attention"] = attention(r["heat"], r["contractEnds"], by_card.get(r["cardId"] or "", []),
                                   warn_days=warn_days, now=now)

    items = list(rows.values())
    if scope == "ilgi":
        items = [r for r in items if r["attention"]]
    elif scope == "sozlesmeli":
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
    waiting = sum(1 for r in rows.values() if r["attention"] and (not nq or nq in _norm(r["name"])))
    if order == "sicak":
        items.sort(key=lambda r: (-r["heat"]["score"], r["name"].casefold()))
    elif order in ("sadik", "zayif"):
        # Sadakat: en bağlı önce ya da en zayıf bağ önce; puanı olmayan (CRM'de yazar değil) hep sonda.
        sign = -1 if order == "sadik" else 1
        items.sort(key=lambda r: (r["loyalty"] is None, sign * (r["loyalty"] or {}).get("score", 0), r["name"].casefold()))
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
            "bands": bands, "attention": waiting, "warnDays": warn_days, "crmOk": crm_ok, "crmError": crm_error,
            "scope": scope, "order": order}
