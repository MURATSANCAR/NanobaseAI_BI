"""HANA read-only execute path."""

from __future__ import annotations

import os
import time
from typing import Any

from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.sap.hana.error_mapper import map_hana_exception
from query_gateway.infrastructure.sap.hana.parser_policy import (
    assert_view_allowlisted,
    enforce_hana_sql_policy,
)
from query_gateway.infrastructure.sap.hana.plan_guard import evaluate_plan_text, explain_sql
from query_gateway.infrastructure.sap.hana.pool import acquire, release
from query_gateway.infrastructure.sap.hana.profile import build_hana_profile
from query_gateway.infrastructure.sap.hana.result_normalizer import normalize_hana_rows
from query_gateway.infrastructure.sap.hana.workload_guard import enforce_workload_policy

SAP_HANA_DISABLED = "SAP_HANA_DISABLED"


def execute_hana_ro(
    ds: dict[str, Any],
    sql: str,
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
    execution_id: str | None = None,
    timeout_ms: int = 15_000,
    max_rows: int = 100,
    size_profile: str = "MEDIUM",
    run_explain: bool = True,
    settings: Any = None,
) -> tuple[list[str], list[dict[str, Any]], bool, int]:
    if os.environ.get("SAP_HANA_EXECUTION_ENABLED", "0") != "1":
        raise GatewayError(
            SAP_HANA_DISABLED,
            "SAP HANA execution disabled (SAP_HANA_EXECUTION_ENABLED=0).",
            status=403,
            execution_id=execution_id,
        )

    mode = (os.environ.get("SAP_EXECUTION_MODE") or "QUERY_GATEWAY").upper()
    if mode == "PLAN_ONLY":
        raise GatewayError(
            "SAP_PLAN_ONLY",
            "SAP execution mode is PLAN_ONLY.",
            status=403,
            execution_id=execution_id,
        )
    if mode == "METADATA_ONLY":
        raise GatewayError(
            "SAP_METADATA_ONLY",
            "SAP execution mode is METADATA_ONLY.",
            status=403,
            execution_id=execution_id,
        )

    cfg = build_hana_profile(ds)
    enforce_hana_sql_policy(sql)
    assert_view_allowlisted(sql, cfg.allowed_views)
    wl = enforce_workload_policy(cfg)
    timeout_ms = min(timeout_ms, int(wl["statementTimeoutS"]) * 1000)

    t0 = time.time()
    conn = acquire(cfg, timeout_ms=timeout_ms)
    discard = False
    try:
        if run_explain:
            plan_text = explain_sql(conn, sql)
            evaluate_plan_text(plan_text, size_profile=cfg.size_profile or size_profile)

        cur = conn.cursor()
        try:
            cur.execute(sql)
            if cur.description is None:
                return [], [], False, int((time.time() - t0) * 1000)
            cols = [d[0] for d in cur.description]
            raw = cur.fetchmany(max_rows + 1)
            truncated = len(raw) > max_rows
            raw = raw[:max_rows]
            rows = normalize_hana_rows(cols, raw)
        finally:
            try:
                cur.close()
            except Exception:
                pass
        try:
            conn.rollback()
        except Exception:
            discard = True
        return cols, rows, truncated, int((time.time() - t0) * 1000)
    except GatewayError:
        discard = True
        raise
    except Exception as e:
        discard = True
        raise map_hana_exception(e) from e
    finally:
        release(cfg, conn, discard=discard)
