"""Oracle Plan Guard via EXPLAIN PLAN + PLAN_TABLE / DBMS_XPLAN."""

from __future__ import annotations

import re
import uuid
from typing import Any

from query_gateway.config.settings import Settings, get_settings
from query_gateway.domain.errors import QUERY_COST_EXCEEDED, GatewayError
from query_gateway.infrastructure.oracle.error_mapper import (
    ORACLE_PLAN_VALIDATION_UNAVAILABLE,
    map_oracle_error,
)

REJECT_OPS = frozenset(
    {
        "MERGE JOIN CARTESIAN",
        "CARTESIAN",
        "REMOTE",
        "COLLECTION ITERATOR",
    }
)


def _parse_plan_rows(rows: list[tuple[Any, ...]]) -> dict[str, Any]:
    """Normalize DBMS_XPLAN / PLAN_TABLE rows into a summary."""
    ops: list[str] = []
    max_rows = 0.0
    max_cost = 0.0
    max_depth = 0
    filterless_full: list[str] = []
    text_blob = ""
    for row in rows:
        line = " ".join(str(c) for c in row if c is not None)
        text_blob += line.upper() + "\n"
        ops.append(line.upper())
        # PLAN_TABLE style: id, operation, options, object_name, cost, cardinality, ...
        if len(row) >= 6:
            try:
                depth = int(row[0]) if row[0] is not None else 0
                max_depth = max(max_depth, depth)
            except Exception:
                pass
            try:
                cost = float(row[4]) if row[4] is not None else 0.0
                max_cost = max(max_cost, cost)
            except Exception:
                pass
            try:
                card = float(row[5]) if row[5] is not None else 0.0
                max_rows = max(max_rows, card)
            except Exception:
                pass
            op = str(row[1] or "").upper()
            opt = str(row[2] or "").upper()
            obj = str(row[3] or "")
            if "TABLE ACCESS" in op and "FULL" in opt:
                filterless_full.append(obj)

    for bad in REJECT_OPS:
        if bad in text_blob:
            raise GatewayError(
                QUERY_COST_EXCEEDED,
                f"Oracle plan reddedildi: {bad}.",
                status=400,
            )
    if "PARALLEL" in text_blob and "PQ" in text_blob:
        # Parallel query forced — reject by default
        raise GatewayError(
            QUERY_COST_EXCEEDED,
            "Oracle parallel plan reddedildi.",
            status=400,
        )
    return {
        "operations": ops[:50],
        "max_cost": max_cost,
        "max_rows": max_rows,
        "max_depth": max_depth,
        "filterless_full": filterless_full,
        "text": text_blob[:4000],
    }


def analyze_oracle_plan(
    summary: dict[str, Any],
    *,
    size_profile: str,
    settings: Settings,
    max_joins: int = 8,
    max_depth: int = 20,
) -> dict[str, Any]:
    profile = (size_profile or "medium").lower()
    max_rows = {
        "small": settings.cost_max_rows_small,
        "medium": settings.cost_max_rows_medium,
        "large": settings.cost_max_rows_large,
        "very_large": settings.cost_max_rows_large * 2,
    }.get(profile, settings.cost_max_rows_medium)
    max_cost = {
        "small": settings.cost_max_total_small,
        "medium": settings.cost_max_total_medium,
        "large": settings.cost_max_total_large,
        "very_large": settings.cost_max_total_large * 2,
    }.get(profile, settings.cost_max_total_medium)

    if summary.get("max_depth", 0) > max_depth:
        raise GatewayError(QUERY_COST_EXCEEDED, "Oracle plan derinliği limiti aşıldı.", status=400)
    if summary.get("max_rows", 0) > max_rows:
        raise GatewayError(
            QUERY_COST_EXCEEDED,
            "Oracle plan tahmini satır sayısı eşiği aşıyor.",
            status=400,
        )
    # Cost is relative — still apply baseline; LARGE/VERY_LARGE more permissive
    if summary.get("max_cost", 0) > max_cost and profile in ("small", "medium"):
        raise GatewayError(
            QUERY_COST_EXCEEDED,
            "Oracle plan maliyeti eşiği aşıyor.",
            status=400,
        )
    # filterless full scan on LARGE profiles: reject
    if profile in ("large", "very_large") and summary.get("filterless_full"):
        raise GatewayError(
            QUERY_COST_EXCEEDED,
            "Büyük tabloda filtersiz TABLE ACCESS FULL reddedildi.",
            status=400,
        )
    return summary


def explain_and_validate(
    conn: Any,
    sql: str,
    *,
    size_profile: str = "medium",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Run EXPLAIN PLAN on the given connection (prefer PLAN_RO user)."""
    settings = settings or get_settings()
    statement_id = f"NB{uuid.uuid4().hex[:24]}"
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM PLAN_TABLE WHERE STATEMENT_ID = :sid",
                sid=statement_id,
            )
            cur.execute(f"EXPLAIN PLAN SET STATEMENT_ID = '{statement_id}' FOR {sql}")
            try:
                cur.execute(
                    """
                    SELECT ID, OPERATION, OPTIONS, OBJECT_NAME, COST, CARDINALITY
                    FROM PLAN_TABLE
                    WHERE STATEMENT_ID = :sid
                    ORDER BY ID
                    """,
                    sid=statement_id,
                )
                rows = cur.fetchall() or []
            except Exception:
                cur.execute(
                    "SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY(NULL, :sid, 'BASIC'))",
                    sid=statement_id,
                )
                rows = cur.fetchall() or []
            # cleanup plan rows
            try:
                cur.execute(
                    "DELETE FROM PLAN_TABLE WHERE STATEMENT_ID = :sid",
                    sid=statement_id,
                )
            except Exception:
                pass
            conn.rollback()
    except GatewayError:
        raise
    except Exception as e:
        raise GatewayError(
            ORACLE_PLAN_VALIDATION_UNAVAILABLE,
            "Oracle Plan Guard çalıştırılamadı.",
            status=503,
            retryable=True,
        ) from e

    summary = _parse_plan_rows(list(rows))
    return analyze_oracle_plan(summary, size_profile=size_profile, settings=settings)


def strip_statement_id(sql: str) -> str:
    return re.sub(r"STATEMENT_ID\s*=\s*'[^']*'", "", sql, flags=re.IGNORECASE)
