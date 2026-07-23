"""Read-only reporting DB executor for scenario validation farm."""

from __future__ import annotations

import os
import re
from typing import Any, Callable
from urllib.parse import quote_plus

from nanobase_api.scenario_engine.infrastructure.compiler import render_sql

_BIND_RE = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")


def reporting_dsn() -> str | None:
    return (
        os.environ.get("NANOBASE_REPORTING_DSN")
        or os.environ.get("REPORTING_DSN")
        or os.environ.get("BI_REPORTING_DSN")
    )


def datasource_ro_dsn(datasource_id: str) -> str | None:
    """Resolve a live Postgres DSN for schema snapshot / validation of a datasource."""
    sid = (datasource_id or "").strip()
    if not sid:
        return reporting_dsn()

    try:
        from pathlib import Path

        from nanobase_api.infrastructure.datasource_registry import (
            reporting_datasource_id,
            resolve_pg_connect_cfg,
        )

        cfg = resolve_pg_connect_cfg(sid)
        if cfg and cfg.get("host"):
            pw = cfg.get("password") or ""
            if not pw:
                pf = cfg.get("password_file")
                if pf:
                    p = Path(str(pf))
                    if not p.is_absolute():
                        secrets = Path(os.environ.get("SECRETS_ROOT", "/data/nanobaseai/bi/secrets"))
                        p = secrets / str(pf).lstrip("/")
                    if p.is_file():
                        pw = p.read_text(encoding="utf-8").strip()
            if not pw:
                ref = str(cfg.get("secret_ref") or "")
                if ref.startswith("file:"):
                    p = Path(ref[5:])
                    if p.is_file():
                        pw = p.read_text(encoding="utf-8").strip()
            user = cfg.get("user") or cfg.get("username") or ""
            host = cfg.get("host") or "127.0.0.1"
            port = int(cfg.get("port") or 5432)
            db = cfg.get("database") or cfg.get("dbname") or "postgres"
            sslmode = cfg.get("sslmode") or ("require" if cfg.get("ssl") else "prefer")
            if user and pw:
                return (
                    f"postgresql://{quote_plus(user)}:{quote_plus(pw)}"
                    f"@{host}:{port}/{db}?sslmode={sslmode}"
                )
        if sid == reporting_datasource_id():
            return reporting_dsn()
    except Exception:
        pass

    env_key = f"SCENARIO_DSN_{sid}".upper().replace("-", "_")
    return os.environ.get(env_key) or (
        reporting_dsn() if sid in ("bi_reporting", "reporting") else None
    )


def to_psycopg(sql_template: str, params: dict[str, object]) -> tuple[str, dict[str, object]]:
    return _BIND_RE.sub(lambda m: f"%({m.group(1)})s", sql_template), params


def make_reporting_execute_fn(
    *,
    dsn: str | None = None,
    datasource_id: str | None = None,
) -> Callable[[str, dict[str, object] | None], list[dict[str, Any]]] | None:
    """Return execute_fn(sql_template, params) -> rows, or None if no DSN."""
    dsn = dsn or (datasource_ro_dsn(datasource_id) if datasource_id else None) or reporting_dsn()
    if not dsn:
        return None
    pg = dsn.replace("postgresql+psycopg2://", "postgresql://")

    def _execute(sql: str, params: dict[str, object] | None = None) -> list[dict[str, Any]]:
        import psycopg2
        import psycopg2.extras

        conn = psycopg2.connect(pg)
        try:
            conn.set_session(readonly=True, autocommit=True)
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SET statement_timeout = '8000ms'")
                if params:
                    q, args = to_psycopg(sql, params)
                    cur.execute(q, args)
                else:
                    cur.execute(sql)
                if cur.description is None:
                    return []
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    return _execute


def offline_execute_fn(sql: str, params: dict[str, object] | None = None) -> list[dict[str, Any]]:
    """Structural offline executor — does not hit DB."""
    _ = (sql, params)
    return []
