"""Toplantı odası rezervasyonu: odalar, günün takvimi, rezerve et, iptal.

Rezervasyonlar ortak kaynaktır: oda, saat, rezerve edenin adı ve konu herkese görünür. Kimin yaptığı istekten
değil oturumdan gelir. Saat İstanbul saatiyle seçilir, UTC saklanır; tarayıcının saat dilimi hesaba girmez.

Aralık yarı açıktır: 14:00–15:00 ile 15:00–16:00 çakışmaz. Çakışma denetimi oda satırı kilitlenerek yapılır;
aynı saate aynı anda basan iki kişiden biri kazanır, diğeri kimin aldığını görür.
"""

from __future__ import annotations

import re
import threading
import uuid
from datetime import date as Date, datetime, time, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

import sqlalchemy as sa

TZ = ZoneInfo("Europe/Istanbul")

_md = sa.MetaData()

ROOMS = sa.Table(
    "semantic_rooms", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("name", sa.String(200), nullable=False),
    sa.Column("location", sa.String(200)),
    sa.Column("capacity", sa.Integer),
    sa.Column("active", sa.Boolean, nullable=False, default=True),
    sa.Column("created_by", sa.String(120)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

BOOKINGS = sa.Table(
    "semantic_room_bookings", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("room_id", sa.String(40), nullable=False),
    sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("username", sa.String(120), nullable=False),
    sa.Column("display_name", sa.String(200), nullable=False),
    sa.Column("title", sa.Text),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("cancelled_at", sa.DateTime(timezone=True)),
    sa.Column("cancelled_by", sa.String(120)),
    sa.Index("ix_semantic_room_bookings_room_start", "room_id", "starts_at"),
)

_ready: set[int] = set()
_lock = threading.Lock()
_HHMM = re.compile(r"^([01]\d|2[0-4]):([0-5]\d)$")


class RoomError(ValueError):
    """Kullanıcıya olduğu gibi gösterilecek düz Türkçe hata."""

    status = 422


class NotFound(RoomError):
    status = 404


class Forbidden(RoomError):
    status = 403


class Conflict(RoomError):
    status = 409

    def __init__(self, message: str, booking: dict[str, Any]):
        super().__init__(message)
        self.booking = booking


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


# ------------------------------------------------------------------ zaman


def _now() -> datetime:
    return datetime.now(timezone.utc)


def today(now: Optional[datetime] = None) -> str:
    """İstanbul'daki bugünün tarihi."""
    return (now or _now()).astimezone(TZ).date().isoformat()


def _utc(v: datetime) -> datetime:
    return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)


def _minutes(hhmm: str, label: str) -> int:
    m = _HHMM.match((hhmm or "").strip())
    if not m or (m.group(1) == "24" and m.group(2) != "00"):
        raise RoomError(f"{label} saati SS:DD biçiminde olmalı.")
    return int(m.group(1)) * 60 + int(m.group(2))


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _day(value: str) -> Date:
    try:
        return Date.fromisoformat((value or "").strip())
    except ValueError:
        raise RoomError("Gün YYYY-AA-GG biçiminde olmalı.") from None


def _at(day: Date, minutes: int) -> datetime:
    """İstanbul gününün dakikasını UTC ana çevirir. 24:00 ertesi günün başıdır."""
    local = datetime.combine(day, time(0), tzinfo=TZ) + timedelta(minutes=minutes)
    return local.astimezone(timezone.utc)


def grid(conf: Any = None) -> dict[str, Any]:
    """Takvim ızgarası: gün başı, gün sonu, adım. Yönetim ayarından okunur."""
    if conf is None:
        from semantic_bridge import admin as admin_mod
        conf = admin_mod.conf
    start = _minutes(conf("ROOM_DAY_START") or "08:00", "Gün başlangıç")
    end = _minutes(conf("ROOM_DAY_END") or "20:00", "Gün bitiş")
    try:
        slot = int(conf("ROOM_SLOT_MINUTES") or "30")
    except ValueError:
        slot = 30
    if slot <= 0 or 1440 % slot:
        slot = 30
    if end <= start:
        start, end = 8 * 60, 20 * 60
    return {"start": _hhmm(start), "end": _hhmm(end), "slotMinutes": slot, "startMin": start, "endMin": end}


# ------------------------------------------------------------------ biçim


def _room(row: Any) -> dict[str, Any]:
    return {"id": row.id, "name": row.name, "location": row.location or "", "capacity": row.capacity,
            "active": bool(row.active)}


def _booking(row: Any, user: Optional[str] = None, admin: bool = False, now: Optional[datetime] = None) -> dict[str, Any]:
    start, end = _utc(row.starts_at), _utc(row.ends_at)
    ls, le = start.astimezone(TZ), end.astimezone(TZ)
    mine = bool(user) and row.username.lower() == str(user).lower()
    ended = end <= (now or _now())
    end_label = "24:00" if le.date() > ls.date() and le.time() == time(0) else le.strftime("%H:%M")
    return {
        "id": row.id, "roomId": row.room_id, "start": start.isoformat(), "end": end.isoformat(),
        "date": ls.date().isoformat(), "startLocal": ls.strftime("%H:%M"), "endLocal": end_label,
        "username": row.username, "displayName": row.display_name, "title": row.title or "",
        "mine": mine, "canCancel": (mine or admin) and not ended and row.cancelled_at is None,
    }


# ------------------------------------------------------------------ odalar


def list_rooms(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(ROOMS).where(ROOMS.c.tenant_id == tenant, ROOMS.c.active.is_(True))
                         .order_by(ROOMS.c.name)).fetchall()
    return [_room(r) for r in rows]


def add_room(engine: sa.engine.Engine, tenant: str, actor: str, body: dict[str, Any]) -> dict[str, Any]:
    name = str(body.get("name") or "").strip()
    location = str(body.get("location") or "").strip()
    if not name:
        raise RoomError("Oda adı boş olamaz.")
    if len(name) > 200 or len(location) > 200:
        raise RoomError("Oda adı ve yeri en fazla 200 karakter olabilir.")
    capacity = body.get("capacity")
    if capacity in (None, ""):
        capacity = None
    else:
        try:
            capacity = int(capacity)
        except (TypeError, ValueError):
            raise RoomError("Kapasite bir tam sayı olmalı.") from None
        if capacity <= 0:
            raise RoomError("Kapasite sıfırdan büyük olmalı.")
    if any(r["name"].casefold() == name.casefold() for r in list_rooms(engine, tenant)):
        raise RoomError(f"«{name}» adında bir oda zaten var.")
    row = {"id": uuid.uuid4().hex, "tenant_id": tenant, "name": name, "location": location or None,
           "capacity": capacity, "active": True, "created_by": actor[:120], "created_at": _now()}
    with engine.begin() as c:
        c.execute(ROOMS.insert().values(**row))
    return {"id": row["id"], "name": name, "location": location, "capacity": capacity, "active": True}


def remove_room(engine: sa.engine.Engine, tenant: str, actor: str, room_id: str,
                now: Optional[datetime] = None) -> dict[str, Any]:
    """Odayı listeden kaldırır; bitmemiş rezervasyonları iptal eder. Geçmiş kayıt kalır."""
    now = now or _now()
    with engine.begin() as c:
        row = c.execute(sa.select(ROOMS).where(ROOMS.c.id == room_id, ROOMS.c.tenant_id == tenant,
                                               ROOMS.c.active.is_(True)).with_for_update()).first()
        if not row:
            raise NotFound("Oda bulunamadı.")
        c.execute(ROOMS.update().where(ROOMS.c.id == room_id).values(active=False))
        cancelled = c.execute(BOOKINGS.update().where(
            BOOKINGS.c.room_id == room_id, BOOKINGS.c.cancelled_at.is_(None), BOOKINGS.c.ends_at > now,
        ).values(cancelled_at=now, cancelled_by=actor[:120])).rowcount
    return {**_room(row), "active": False, "cancelledBookings": int(cancelled or 0)}


# ------------------------------------------------------------------ takvim


def day_view(engine: sa.engine.Engine, tenant: str, day: str, user: Optional[str], admin: bool = False,
             now: Optional[datetime] = None, conf: Any = None) -> dict[str, Any]:
    d = _day(day)
    lo, hi = _at(d, 0), _at(d, 24 * 60)
    now = now or _now()
    with engine.connect() as c:
        rows = c.execute(
            sa.select(BOOKINGS).join(ROOMS, ROOMS.c.id == BOOKINGS.c.room_id).where(
                BOOKINGS.c.tenant_id == tenant, ROOMS.c.active.is_(True), BOOKINGS.c.cancelled_at.is_(None),
                BOOKINGS.c.starts_at < hi, BOOKINGS.c.ends_at > lo,
            ).order_by(BOOKINGS.c.starts_at)).fetchall()
    return {"date": d.isoformat(), "today": now.astimezone(TZ).date().isoformat(), "grid": grid(conf),
            "rooms": list_rooms(engine, tenant), "bookings": [_booking(r, user, admin, now) for r in rows]}


def now_view(engine: sa.engine.Engine, tenant: str, user: Optional[str] = None,
             now: Optional[datetime] = None) -> dict[str, Any]:
    """Kampüs kartı: her odanın şu anki ve sıradaki rezervasyonu."""
    now = now or _now()
    rooms = list_rooms(engine, tenant)
    out = []
    with engine.connect() as c:
        for room in rooms:
            base = sa.select(BOOKINGS).where(BOOKINGS.c.room_id == room["id"], BOOKINGS.c.cancelled_at.is_(None))
            current = c.execute(base.where(BOOKINGS.c.starts_at <= now, BOOKINGS.c.ends_at > now)
                                .order_by(BOOKINGS.c.starts_at)).first()
            after = _utc(current.ends_at) if current else now
            nxt = c.execute(base.where(BOOKINGS.c.starts_at >= after).order_by(BOOKINGS.c.starts_at).limit(1)).first()
            out.append({**room, "current": _booking(current, user, False, now) if current else None,
                        "next": _booking(nxt, user, False, now) if nxt else None})
    return {"now": now.isoformat(), "today": now.astimezone(TZ).date().isoformat(), "rooms": out}


def book(engine: sa.engine.Engine, tenant: str, room_id: str, user: str, display: str, body: dict[str, Any],
         now: Optional[datetime] = None, conf: Any = None) -> dict[str, Any]:
    now = now or _now()
    g = grid(conf)
    d = _day(str(body.get("date") or ""))
    s = _minutes(str(body.get("start") or ""), "Başlangıç")
    e = _minutes(str(body.get("end") or ""), "Bitiş")
    if e <= s:
        raise RoomError("Bitiş saati başlangıçtan sonra olmalı.")
    if s < g["startMin"] or e > g["endMin"]:
        raise RoomError(f"Rezervasyon {g['start']}–{g['end']} arasında olmalı.")
    step = g["slotMinutes"]
    if (s - g["startMin"]) % step or (e - g["startMin"]) % step:
        raise RoomError(f"Saatler {step} dakikalık adımlarla seçilir.")
    starts, ends = _at(d, s), _at(d, e)
    if ends <= now or starts <= now - timedelta(minutes=step):
        raise RoomError("Geçmiş bir saate rezervasyon yapılamaz.")
    title = str(body.get("title") or "").strip()

    with engine.begin() as c:
        room = c.execute(sa.select(ROOMS).where(ROOMS.c.id == room_id, ROOMS.c.tenant_id == tenant,
                                                ROOMS.c.active.is_(True)).with_for_update()).first()
        if not room:
            raise NotFound("Oda bulunamadı.")
        clash = c.execute(sa.select(BOOKINGS).where(
            BOOKINGS.c.room_id == room_id, BOOKINGS.c.cancelled_at.is_(None),
            BOOKINGS.c.starts_at < ends, BOOKINGS.c.ends_at > starts,
        ).order_by(BOOKINGS.c.starts_at).limit(1)).first()
        if clash:
            b = _booking(clash, user, False, now)
            raise Conflict(f"{room.name} {b['startLocal']}–{b['endLocal']} arasında {b['displayName']} adına dolu.", b)
        row = {"id": uuid.uuid4().hex, "tenant_id": tenant, "room_id": room_id, "starts_at": starts, "ends_at": ends,
               "username": user[:120], "display_name": (display or user)[:200], "title": title or None,
               "created_at": now, "cancelled_at": None, "cancelled_by": None}
        c.execute(BOOKINGS.insert().values(**row))
    out = _booking(_RowView(row), user, False, now)
    return {**out, "roomName": room.name}


def cancel(engine: sa.engine.Engine, tenant: str, booking_id: str, user: str, admin: bool = False,
           now: Optional[datetime] = None) -> dict[str, Any]:
    now = now or _now()
    with engine.begin() as c:
        row = c.execute(sa.select(BOOKINGS).where(BOOKINGS.c.id == booking_id, BOOKINGS.c.tenant_id == tenant,
                                                  BOOKINGS.c.cancelled_at.is_(None)).with_for_update()).first()
        if not row:
            raise NotFound("Rezervasyon bulunamadı ya da zaten iptal edilmiş.")
        if row.username.lower() != user.lower() and not admin:
            raise Forbidden("Bu rezervasyonu yalnız yapan kişi iptal edebilir.")
        if _utc(row.ends_at) <= now:
            raise RoomError("Bitmiş bir rezervasyon iptal edilemez.")
        c.execute(BOOKINGS.update().where(BOOKINGS.c.id == booking_id).values(cancelled_at=now, cancelled_by=user[:120]))
    return _booking(row, user, admin, now)


class _RowView:
    """Az önce yazılan satırı okunmuş satır gibi biçime vermek için."""

    def __init__(self, d: dict[str, Any]):
        self.__dict__.update(d)
