"""Validate + refresh budget actuals via Query Gateway."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from nanobase_api import budgets as budgets_mod
from nanobase_api.infrastructure.budget_schema import ensure_budget_tables
from nanobase_api.infrastructure.query_gateway_client import QueryGatewayClient

_LITERAL_SQL = re.compile(
    r"^\s*select\s+(-?\d+(?:\.\d+)?)\s*(?:as\s+\w+)?\s*;?\s*$",
    re.IGNORECASE,
)


def _active_datasource_id() -> str:
    try:
        from bridge import app as bridge_mod
        from nanobase_api.infrastructure.active_source import prefer_datasource_id

        return prefer_datasource_id(memory_id=bridge_mod.ACTIVE_DB.get("id"))
    except Exception:
        return "bi_reporting"


async def fetch_actual_value(
    sql: str,
    *,
    datasource_id: str | None = None,
    tenant_id: str | None = None,
    qg: QueryGatewayClient | None = None,
) -> float:
    cleaned = (sql or "").strip().rstrip(";")
    if not cleaned:
        raise ValueError("bi_budget_sql_required")
    lit = _LITERAL_SQL.match(cleaned)
    if lit:
        return float(lit.group(1))

    client = qg or QueryGatewayClient()
    ds = datasource_id or _active_datasource_id()
    # Prefer validate then execute
    validated = await client.validate(sql=cleaned, datasource_id=ds, tenant_id=tenant_id)
    if not validated.get("ok") and validated.get("status") not in (None, "APPROVED"):
        raise ValueError(validated.get("code") or validated.get("message") or "bi_budget_sql_rejected")
    run_sql = validated.get("sql") or cleaned
    result = await client.execute(sql=run_sql, datasource_id=ds, tenant_id=tenant_id)
    if not result.get("ok"):
        raise ValueError(result.get("error") or "bi_budget_actual_empty")
    rows = result.get("rows") or []
    cols = result.get("columns") or []
    if not rows or not cols:
        raise ValueError("bi_budget_actual_empty")
    row0 = rows[0]
    if isinstance(row0, dict):
        col0 = cols[0] if isinstance(cols[0], str) else (cols[0].get("name") if cols else None)
        raw = row0.get(col0) if col0 else next(iter(row0.values()), None)
    else:
        raw = row0[0] if row0 else None
    return float(raw)


async def validate_budget_sql(
    sql: str,
    *,
    datasource_id: str | None = None,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    cleaned = (sql or "").strip().rstrip(";")
    if not cleaned:
        raise ValueError("bi_budget_sql_required")
    lit = _LITERAL_SQL.match(cleaned)
    if lit:
        return {
            "ok": True,
            "sample": float(lit.group(1)),
            "sql": cleaned,
            "source": "literal",
        }
    sample = await fetch_actual_value(cleaned, datasource_id=datasource_id, tenant_id=tenant_id)
    return {"ok": True, "sample": sample, "sql": cleaned, "source": "query_gateway"}


def _insert_actuals_history(
    engine: Engine,
    *,
    tenant_id: str,
    budget_id: str,
    actual: float,
    source: str = "refresh",
) -> None:
    ensure_budget_tables(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO bi_budget_actuals_history
                  (tenant_id, budget_id, actual, source, recorded_at, payload_json)
                VALUES (:tenant, :bid, :actual, :source, NOW(), :payload)
                """
            ),
            {
                "tenant": tenant_id,
                "bid": budget_id,
                "actual": actual,
                "source": (source or "refresh")[:64],
                "payload": "{}",
            },
        )


def list_actuals_history(
    engine: Engine,
    budget_id: str,
    *,
    tenant_id: str = "default",
    limit: int = 24,
) -> list[dict[str, Any]]:
    ensure_budget_tables(engine)
    lim = max(1, min(int(limit or 24), 200))
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT actual, source, recorded_at
                FROM bi_budget_actuals_history
                WHERE tenant_id = :tenant AND budget_id = :bid
                ORDER BY recorded_at DESC
                LIMIT :lim
                """
            ),
            {"tenant": tenant_id, "bid": budget_id, "lim": lim},
        ).mappings()
        return [
            {
                "actual": float(r["actual"]) if r["actual"] is not None else None,
                "source": r["source"] or "refresh",
                "recorded_at": r["recorded_at"].isoformat() if r["recorded_at"] else None,
            }
            for r in rows
        ]


async def refresh_one(
    engine: Engine,
    budget_id: str,
    *,
    tenant_id: str = "default",
    datasource_id: str | None = None,
) -> dict[str, Any]:
    budget = budgets_mod.get_budget(engine, budget_id, tenant_id=tenant_id)
    if not budget:
        raise ValueError("bi_budget_not_found")
    sql = str(budget.get("actuals_sql") or "").strip()
    now = datetime.now(timezone.utc)
    if not sql:
        return budgets_mod.patch_budget_fields(
            engine,
            budget_id,
            {"actual": None, "actual_error": None, "actuals_at": None},
            tenant_id=tenant_id,
            allow_locked=True,
        )
    try:
        actual = await fetch_actual_value(sql, datasource_id=datasource_id, tenant_id=tenant_id)
        row = budgets_mod.patch_budget_fields(
            engine,
            budget_id,
            {"actual": actual, "actual_error": None, "actuals_at": now},
            tenant_id=tenant_id,
            allow_locked=True,
        )
        if not row.get("actual_error"):
            _insert_actuals_history(
                engine,
                tenant_id=tenant_id,
                budget_id=budget_id,
                actual=float(actual),
                source="refresh",
            )
        return row
    except Exception as exc:
        return budgets_mod.patch_budget_fields(
            engine,
            budget_id,
            {"actual": None, "actual_error": str(exc)[:300], "actuals_at": now},
            tenant_id=tenant_id,
            allow_locked=True,
        )


async def refresh_all(
    engine: Engine,
    *,
    tenant_id: str = "default",
    fiscal_year: Optional[int] = None,
    datasource_id: str | None = None,
) -> dict[str, Any]:
    items = budgets_mod.list_budgets(
        engine, tenant_id=tenant_id, fiscal_year=fiscal_year, status="approved"
    )
    refreshed = 0
    errors = 0
    for item in items:
        if not str(item.get("actuals_sql") or "").strip():
            continue
        row = await refresh_one(
            engine, str(item["id"]), tenant_id=tenant_id, datasource_id=datasource_id
        )
        refreshed += 1
        if row.get("actual_error"):
            errors += 1
    return {"refreshed": refreshed, "errors": errors}
