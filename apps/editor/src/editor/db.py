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

_pool: ConnectionPool | None = None
MIGRATIONS = Path(__file__).resolve().parent.parent.parent / "db" / "migrations"


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        import atexit
        _pool = ConnectionPool(
            settings().db_dsn,
            min_size=1,
            max_size=24,
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
    return applied


J = Jsonb
