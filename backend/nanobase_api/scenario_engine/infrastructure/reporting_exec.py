"""Read-only reporting DB executor for scenario validation farm."""

from __future__ import annotations

import os
import re
from typing import Any, Callable

from nanobase_api.scenario_engine.infrastructure.compiler import render_sql

_BIND_RE = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")


def reporting_dsn() -> str | None:
    return (
        os.environ.get("NANOBASE_REPORTING_DSN")
        or os.environ.get("REPORTING_DSN")
        or os.environ.get("BI_REPORTING_DSN")
    )


def to_psycopg(sql_template: str, params: dict[str, object]) -> tuple[str, dict[str, object]]:
    return _BIND_RE.sub(lambda m: f"%({m.group(1)})s", sql_template), params


def make_reporting_execute_fn(
    *,
    dsn: str | None = None,
) -> Callable[[str, dict[str, object] | None], list[dict[str, Any]]] | None:
    """Return execute_fn(sql_template, params) -> rows, or None if no DSN."""
    dsn = dsn or reporting_dsn()
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
    _ = render_sql(sql, params or {})
    return []
