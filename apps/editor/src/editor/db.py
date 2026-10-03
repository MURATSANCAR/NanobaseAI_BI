"""Postgres access for the evidence ledger (schema `ed`)."""

from __future__ import annotations

import contextlib
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg import sql
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .config import settings

validation_token: ContextVar[str | None] = ContextVar("editor_validation_token", default=None)
#: Merkezi denetim kaydı: kişinin yazma isteğinde {"rid", "actor"} (audit.py ara katmanı koyar). İşlemin başında
#: `nanobase.audit` olarak verilir; `ed.nb_audit_row` tetikleyicisi oradan okur. Bağlam yoksa tetikleyici çalışmaz.
audit_context: ContextVar[str | None] = ContextVar("editor_audit_context", default=None)

_pool: ConnectionPool | None = None
MIGRATIONS = Path(__file__).resolve().parent.parent.parent / "db" / "migrations"


#: Süreç başına üst sınır. Postgres max_connections 100'ü Temporal ve on kadar editör süreci paylaşır;
#: 2026-10-02'de 100'ün 98'i doluydu (editor_app 67 boşta: rebuild ~24, gateway ~21, worker ~18) ve yeni süreç
#: bağlanamadı. Eski varsayılan 24 × süreç sayısı sınırı tek başına aşıyordu; psycopg_pool fazla bağlantıyı
#: `max_idle` sürede bir tane kapatır (varsayılan 10 dk), bu yüzden bir patlamadan sonra saatlerce boşta kalıyordu.
POOL_MAX = 8
POOL_MIN = 1
POOL_MAX_IDLE = 60.0


def pool_limits() -> dict:
    """Havuz ayarları, env ile: EDITOR_DB_POOL_MAX (vars. 8), EDITOR_DB_POOL_MIN (1), EDITOR_DB_POOL_MAX_IDLE
    (sn, 60: fazla bağlantı bu sürede bir kapanır), EDITOR_DB_POOL_TIMEOUT (sn, 600). Bekleme uzun: her sorgu
    bir iş parçacığından yapılır, boş bağlantıyı beklemek bir şeye mal olmaz; psycopg'nin 30 sn'si birkaç yoğun
    saniyeyi düşen etkinliğe çeviriyordu."""
    import os

    def num(key: str, default: float) -> float:
        raw = os.environ.get(key, "")
        return float(raw) if raw.strip() else default
    size = max(2, int(num("EDITOR_DB_POOL_MAX", POOL_MAX)))
    low = min(size, max(0, int(num("EDITOR_DB_POOL_MIN", POOL_MIN))))
    return {"min_size": low, "max_size": size, "max_idle": max(5.0, num("EDITOR_DB_POOL_MAX_IDLE", POOL_MAX_IDLE)),
            "timeout": max(1.0, num("EDITOR_DB_POOL_TIMEOUT", 600))}


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        import atexit
        lim = pool_limits()
        _pool = ConnectionPool(
            settings().db_dsn,
            min_size=lim["min_size"],
            max_size=lim["max_size"],
            max_idle=lim["max_idle"],
            timeout=lim["timeout"],
            kwargs={"row_factory": dict_row, "options": "-c search_path=ed,public"},
            open=True,
        )
        atexit.register(_pool.close)
    return _pool


@contextlib.contextmanager
def tx() -> Iterator[psycopg.Connection]:
    """One transaction; commits on success (deferred evidence check runs here)."""
    with pool().connection() as conn:
        with conn.transaction():
            token = validation_token.get()
            if token:
                conn.execute(sql.SQL("SET LOCAL editor.validation_token = {}").format(sql.Literal(token)))
            audit = audit_context.get()
            if audit:
                conn.execute("SELECT set_config('nanobase.audit', %s, true)", (audit,))
            yield conn


def one(sql: str, *args: Any) -> dict | None:
    with tx() as c:
        return c.execute(sql, args).fetchone()


def all_rows(sql: str, *args: Any) -> list[dict]:
    with tx() as c:
        return c.execute(sql, args).fetchall()


def migrate() -> list[str]:
    """Apply db/migrations/*.sql once each, in name order."""
    applied: list[str] = []
    with psycopg.connect(settings().db_dsn, autocommit=True) as conn:
        conn.execute("CREATE SCHEMA IF NOT EXISTS ed")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS ed.schema_migration "
            "(name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        done = {r[0] for r in conn.execute("SELECT name FROM ed.schema_migration")}
        for f in sorted(MIGRATIONS.glob("*.sql")):
            # «._022_….sql» is macOS metadata a Mac `tar` carries along, not SQL: reading it as a
            # migration crashed migrate() before anything was applied (2026-09-22).
            if f.name in done or f.name.startswith("._"):
                continue
            with conn.transaction():
                conn.execute(f.read_text())
                conn.execute("INSERT INTO ed.schema_migration(name) VALUES (%s) "
                             "ON CONFLICT DO NOTHING", (f.name,))
            applied.append(f.name)
        # Denetim tetikleyicisi sonradan açılan tablolara da (035_audit_outbox.sql).
        if conn.execute("SELECT to_regprocedure('ed.nb_audit_install()')").fetchone()[0]:
            conn.execute("SELECT ed.nb_audit_install()")
    return applied


J = Jsonb
