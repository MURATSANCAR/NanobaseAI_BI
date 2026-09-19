"""Kişi tercihleri: bir kişinin kendi ekran alanları (ör. Genel bakış kanvasının kart düzeni).

Anahtar AD hesabıdır; değer JSON. Başka bilgisayardan ya da tarayıcıdan girildiğinde aynı düzen gelir.
Tarayıcı yalnız önbellek tutar, doğru olan buradaki kayıttır.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from typing import Any, Optional

import sqlalchemy as sa

_md = sa.MetaData()

PREFS = sa.Table(
    "semantic_user_prefs", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("datasource_id", sa.String(80), primary_key=True),
    sa.Column("username", sa.String(120), primary_key=True),
    sa.Column("key", sa.String(120), primary_key=True),
    sa.Column("value", sa.Text, nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

#: "layout:genel", "layout:uyarilar" gibi. Nokta, iki nokta, tire, alt çizgi serbest.
_KEY = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")
#: Bir tercihin boyut üst sınırı. Aşılırsa sessizce kesilmez, açık hata döner.
MAX_BYTES = 1_000_000

_ready: set[int] = set()
_lock = threading.Lock()


class PrefError(ValueError):
    """Kullanıcıya olduğu gibi gösterilecek düz Türkçe hata."""


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def _iso(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()


def _where(tenant: str, ds: str, user: str, key: str) -> list[Any]:
    if not _KEY.match(key or ""):
        raise PrefError("Tercih anahtarı geçersiz.")
    return [PREFS.c.tenant_id == tenant, PREFS.c.datasource_id == ds,
            sa.func.lower(PREFS.c.username) == user.lower(), PREFS.c.key == key]


def get(engine: sa.engine.Engine, tenant: str, ds: str, user: str, key: str) -> dict[str, Any]:
    with engine.connect() as c:
        row = c.execute(sa.select(PREFS.c.value, PREFS.c.updated_at).where(*_where(tenant, ds, user, key))).first()
    if not row:
        return {"value": None, "updatedAt": None}
    try:
        value = json.loads(row[0])
    except ValueError:
        value = None
    return {"value": value, "updatedAt": _iso(row[1])}


def put(engine: sa.engine.Engine, tenant: str, ds: str, user: str, key: str, value: Any) -> dict[str, Any]:
    where = _where(tenant, ds, user, key)
    raw = json.dumps(value, ensure_ascii=False)
    if len(raw.encode("utf-8")) > MAX_BYTES:
        raise PrefError(f"Tercih çok büyük ({len(raw) // 1024} kB); en fazla {MAX_BYTES // 1024} kB.")
    now = datetime.now(timezone.utc)
    with engine.begin() as c:
        c.execute(PREFS.delete().where(*where))
        c.execute(PREFS.insert().values(tenant_id=tenant, datasource_id=ds, username=user[:120], key=key,
                                        value=raw, updated_at=now))
    return {"value": value, "updatedAt": _iso(now)}


def delete(engine: sa.engine.Engine, tenant: str, ds: str, user: str, key: str) -> bool:
    with engine.begin() as c:
        return bool(c.execute(PREFS.delete().where(*_where(tenant, ds, user, key))).rowcount)
