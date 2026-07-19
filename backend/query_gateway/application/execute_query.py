"""Validate + execute via Postgres RO path."""

from __future__ import annotations

import time
from typing import Any

from query_gateway.application.validate_query import validate_query
from query_gateway.config.settings import Settings, get_settings
from query_gateway.domain.errors import DATASOURCE_NOT_FOUND, GatewayError
from query_gateway.infrastructure.audit.logger import get_audit_logger
from query_gateway.infrastructure.database.datasources import load_datasources
from query_gateway.infrastructure.database.postgres_executor import execute_postgres_ro
from query_gateway.infrastructure.result.guard import guard_result


def execute_query(
    *,
    execution_id: str,
    datasource_id: str,
    sql: str,
    tenant_id: str | None = None,
    user_id: str | None = None,
    max_rows: int | None = None,
    timeout_ms: int | None = None,
    settings: Settings | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    t0 = time.time()

    approved = validate_query(
        execution_id=execution_id,
        datasource_id=datasource_id,
        sql=sql,
        tenant_id=tenant_id,
        user_id=user_id,
        max_rows=max_rows,
        settings=settings,
        trace_id=trace_id,
    )
    validation_ms = int((time.time() - t0) * 1000)

    ds_map = load_datasources(settings)
    ds = ds_map.get(datasource_id)
    if not ds:
        raise GatewayError(DATASOURCE_NOT_FOUND, "Datasource bulunamadı.", status=404)

    driver = ds.get("driver") or "postgresql"
    if driver != "postgresql":
        raise GatewayError(
            DATASOURCE_NOT_FOUND,
            "Internal execute şu an yalnız PostgreSQL destekler.",
            status=400,
            execution_id=execution_id,
        )

    rows_limit = min(max_rows or settings.max_rows, settings.max_limit)
    timeout = min(timeout_ms or settings.statement_timeout_ms, 60_000)

    cols, rows, truncated, exec_ms = execute_postgres_ro(
        ds,
        approved["normalizedSql"],
        tenant_id=tenant_id,
        timeout_ms=timeout,
        max_rows=rows_limit,
        size_profile=str(ds.get("size_profile") or "medium"),
        run_explain=True,
        settings=settings,
    )

    guarded = guard_result(
        cols,
        rows,
        column_policies=ds.get("column_policies") or {},
        truncated=truncated,
        settings=settings,
    )

    gateway_ms = int((time.time() - t0) * 1000)
    get_audit_logger().record(
        {
            "executionId": execution_id,
            "event": "QUERY_EXECUTED",
            "status": "SUCCESS",
            "rowCount": guarded["rowCount"],
            "truncated": guarded["truncated"],
            "executionTimeMs": exec_ms,
            "gatewayTimeMs": gateway_ms,
            "traceId": trace_id,
            "datasourceId": datasource_id,
            "tenantId": tenant_id,
            "sqlFingerprint": approved.get("sqlFingerprint"),
        }
    )

    return {
        "executionId": execution_id,
        "status": "SUCCESS",
        "columns": guarded["columns"],
        "rows": guarded["rows"],
        "rowCount": guarded["rowCount"],
        "truncated": guarded["truncated"],
        "executionTimeMs": exec_ms,
        "validationTimeMs": validation_ms,
        "gatewayTimeMs": gateway_ms,
        "policyVersion": approved["policyVersion"],
        "traceId": trace_id,
        "sqlFingerprint": approved.get("sqlFingerprint"),
        "normalizedSql": approved.get("normalizedSql"),
    }
