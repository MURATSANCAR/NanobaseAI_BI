from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from query_gateway.api.dependencies import AuthExecute
from query_gateway.application.execute_query import execute_query
from query_gateway.contracts.validation import ExecuteRequest
from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.audit.logger import get_audit_logger

router = APIRouter(prefix="/internal/v1", tags=["internal-queries"])

_executions: dict[str, dict[str, Any]] = {}


@router.post("/queries/execute")
async def execute_endpoint(
    body: ExecuteRequest,
    auth: dict = AuthExecute,
) -> dict[str, Any]:
    try:
        limits = body.limits
        result = execute_query(
            execution_id=body.executionId,
            datasource_id=body.datasourceId,
            sql=body.sql,
            tenant_id=body.tenantId,
            user_id=body.userId,
            max_rows=limits.maxRows if limits else None,
            timeout_ms=limits.timeoutMs if limits else None,
            trace_id=auth.get("trace_id"),
            parameters=body.parameters,
        )
        _executions[body.executionId] = {
            "executionId": body.executionId,
            "status": result.get("status"),
            "rowCount": result.get("rowCount"),
            "sqlFingerprint": result.get("sqlFingerprint"),
            "traceId": auth.get("trace_id"),
        }
        return result
    except GatewayError as e:
        e.execution_id = e.execution_id or body.executionId
        e.trace_id = e.trace_id or auth.get("trace_id")
        raise


@router.get("/queries/{execution_id}")
async def get_execution(
    execution_id: str,
    auth: dict = AuthExecute,
) -> dict[str, Any]:
    found = _executions.get(execution_id)
    if found:
        return found
    # fallback: scan recent audit memory
    for ev in reversed(get_audit_logger()._memory):
        if ev.get("executionId") == execution_id:
            return {
                "executionId": execution_id,
                "status": ev.get("status") or ev.get("result"),
                "event": ev.get("event"),
                "traceId": ev.get("traceId") or auth.get("trace_id"),
            }
    return {"executionId": execution_id, "status": "UNKNOWN"}
