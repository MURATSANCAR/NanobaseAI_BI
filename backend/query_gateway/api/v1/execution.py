from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any

from fastapi import APIRouter

from query_gateway.api.dependencies import AuthExecute
from query_gateway.application.execute_query import execute_query
from query_gateway.contracts.validation import ExecuteRequest
from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.audit.logger import get_audit_logger

router = APIRouter(prefix="/internal/v1", tags=["internal-queries"])

# Bounded per-process registry of recent executions (oldest evicted past the cap).
_EXECUTIONS_MAX = 500
_executions: OrderedDict[str, dict[str, Any]] = OrderedDict()
_executions_lock = threading.Lock()


def _remember_execution(execution_id: str, entry: dict[str, Any]) -> None:
    with _executions_lock:
        _executions[execution_id] = entry
        _executions.move_to_end(execution_id)
        while len(_executions) > _EXECUTIONS_MAX:
            _executions.popitem(last=False)


# Plain def: blocking DB drivers (psycopg2/oracledb/hdbcli) must run in the
# FastAPI threadpool, not on the event loop.
@router.post("/queries/execute")
def execute_endpoint(
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
        _remember_execution(
            body.executionId,
            {
                "executionId": body.executionId,
                "status": result.get("status"),
                "rowCount": result.get("rowCount"),
                "sqlFingerprint": result.get("sqlFingerprint"),
                "traceId": auth.get("trace_id"),
            },
        )
        return result
    except GatewayError as e:
        e.execution_id = e.execution_id or body.executionId
        e.trace_id = e.trace_id or auth.get("trace_id")
        raise


@router.get("/queries/{execution_id}")
def get_execution(
    execution_id: str,
    auth: dict = AuthExecute,
) -> dict[str, Any]:
    found = _executions.get(execution_id)
    if found:
        return found
    # fallback: scan recent audit memory
    for ev in reversed(get_audit_logger().recent_events()):
        if ev.get("executionId") == execution_id:
            return {
                "executionId": execution_id,
                "status": ev.get("status") or ev.get("result"),
                "event": ev.get("event"),
                "traceId": ev.get("traceId") or auth.get("trace_id"),
            }
    return {"executionId": execution_id, "status": "UNKNOWN"}
