"""Kampüs kutlamaları: "Kutla"ya basılınca kutlanan kişinin ekranında bildirim çıkar.

Kutlayan istekten değil oturumdan gelir. Kutlanan kişi kampüs kartındaki ad soyaddır; hesabı ona AD'deki ad
soyadı (ya da hesap adı) Türkçe küçük harfle eşleştirir. Aynı kişi aynı gün aynı kişiyi bir kez kutlar; ikinci
basış yeni satır yazmaz. Bildirim kişi görene kadar bekler, gördüğü an işaretlenir ve bir daha gösterilmez.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

import sqlalchemy as sa

TZ = ZoneInfo("Europe/Istanbul")

_md = sa.MetaData()

GREETINGS = sa.Table(
    "semantic_greetings", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("day", sa.String(10), nullable=False),
    sa.Column("from_user", sa.String(120), nullable=False),
    sa.Column("from_display", sa.String(200), nullable=False),
    sa.Column("to_name", sa.String(200), nullable=False),
    sa.Column("to_key", sa.String(200), nullable=False),
    sa.Column("occasion", sa.String(200)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("seen_at", sa.DateTime(timezone=True)),
    sa.Index("ix_semantic_greetings_to", "tenant_id", "to_key", "seen_at"),
    sa.UniqueConstraint("tenant_id", "day", "from_user", "to_key", name="uq_semantic_greetings_once"),
)

_ready: set[int] = set()
_lock = threading.Lock()


class GreetingError(ValueError):
    """Kullanıcıya olduğu gibi gösterilecek düz Türkçe hata."""

    status = 422


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _day(now: Optional[datetime]) -> str:
    return (now or _now()).astimezone(TZ).date().isoformat()


def key(name: str) -> str:
    """Ad eşleştirme anahtarı: Türkçe küçük harf, tek boşluk. "AHMET YILDIZ" = "Ahmet Yıldız"."""
    s = (name or "").replace("I", "ı").replace("İ", "i").lower()
    return " ".join(s.split())[:200]


def _keys(user: str, display: str) -> set[str]:
    return {k for k in (key(display), key(user)) if k}


def _row(r: Any) -> dict[str, Any]:
    at = r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=timezone.utc)
    return {"id": r.id, "from": r.from_display, "to": r.to_name, "occasion": r.occasion, "at": at.isoformat(),
            "seen": r.seen_at is not None}


def _since(days: int, now: Optional[datetime]) -> datetime:
    return (now or _now()) - timedelta(days=max(0, int(days)))


def received(engine: sa.engine.Engine, tenant: str, user: str, display: str, days: int = 30,
             now: Optional[datetime] = None) -> list[dict[str, Any]]:
    """Bu kişiye son `days` günde gelen bütün kutlamalar (görülmüş olanlar dahil); yeniden eskiye.
    Kampüs'teki zil bunu listeler; `inbox` yalnız görülmemişleri verir ve toast'tan sonra boşalır."""
    with engine.connect() as c:
        rows = c.execute(sa.select(GREETINGS).where(
            GREETINGS.c.tenant_id == tenant, GREETINGS.c.to_key.in_(_keys(user, display)),
            GREETINGS.c.created_at >= _since(days, now),
        ).order_by(GREETINGS.c.created_at.desc())).all()
    return [_row(r) for r in rows]


def wall(engine: sa.engine.Engine, tenant: str, days: int = 30, now: Optional[datetime] = None) -> list[dict[str, Any]]:
    """Alkış duvarı: kiracıdaki herkesin son `days` günde gönderdiği kutlamalar; yeniden eskiye."""
    with engine.connect() as c:
        rows = c.execute(sa.select(GREETINGS).where(
            GREETINGS.c.tenant_id == tenant, GREETINGS.c.created_at >= _since(days, now),
        ).order_by(GREETINGS.c.created_at.desc())).all()
    return [_row(r) for r in rows]


def send(engine: sa.engine.Engine, tenant: str, user: str, display: str, body: dict[str, Any],
         now: Optional[datetime] = None) -> dict[str, Any]:
    to_name = " ".join(str(body.get("to") or "").split())[:200]
    if not to_name:
        raise GreetingError("Kimin kutlandığı boş olamaz.")
    to_key = key(to_name)
    if to_key in _keys(user, display):
        raise GreetingError("Kendinizi kutlayamazsınız.")
    occasion = " ".join(str(body.get("occasion") or "").split())[:200] or None
    at = now or _now()
    scope = (GREETINGS.c.tenant_id == tenant, GREETINGS.c.day == _day(at),
             GREETINGS.c.from_user == user, GREETINGS.c.to_key == to_key)
    created = False
    with engine.begin() as c:
        if c.execute(sa.select(GREETINGS.c.id).where(*scope)).first() is None:
            try:
                with c.begin_nested():
                    c.execute(GREETINGS.insert().values(
                        id=uuid.uuid4().hex, tenant_id=tenant, day=_day(at), from_user=user,
                        from_display=display or user, to_name=to_name, to_key=to_key, occasion=occasion,
                        created_at=at,
                    ))
                created = True
            except sa.exc.IntegrityError:
                pass  # aynı anda iki basış: biri yazdı, diğeri onu okur
        row = c.execute(sa.select(GREETINGS).where(*scope)).one()
    return {**_row(row), "created": created}


def sent_today(engine: sa.engine.Engine, tenant: str, user: str, now: Optional[datetime] = None) -> list[str]:
    with engine.connect() as c:
        rows = c.execute(sa.select(GREETINGS.c.to_name).where(
            GREETINGS.c.tenant_id == tenant, GREETINGS.c.day == _day(now), GREETINGS.c.from_user == user)).all()
    return [r.to_name for r in rows]


def inbox(engine: sa.engine.Engine, tenant: str, user: str, display: str) -> list[dict[str, Any]]:
    """Bu kişiye gelen, henüz görülmemiş kutlamalar; eskiden yeniye."""
    with engine.connect() as c:
        rows = c.execute(sa.select(GREETINGS).where(
            GREETINGS.c.tenant_id == tenant, GREETINGS.c.to_key.in_(_keys(user, display)),
            GREETINGS.c.seen_at.is_(None),
        ).order_by(GREETINGS.c.created_at)).all()
    return [_row(r) for r in rows]


def mark_seen(engine: sa.engine.Engine, tenant: str, user: str, display: str, ids: Iterable[str],
              now: Optional[datetime] = None) -> int:
    """Yalnız kişinin kendisine gelenleri işaretler; başkasının bildirimi buradan kapanmaz."""
    ids = [str(i) for i in ids if i]
    if not ids:
        return 0
    with engine.begin() as c:
        res = c.execute(GREETINGS.update().where(
            GREETINGS.c.tenant_id == tenant, GREETINGS.c.id.in_(ids),
            GREETINGS.c.to_key.in_(_keys(user, display)), GREETINGS.c.seen_at.is_(None),
        ).values(seen_at=now or _now()))
    return res.rowcount or 0
