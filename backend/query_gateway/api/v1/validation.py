from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from query_gateway.api.dependencies import AuthValidate
from query_gateway.application.validate_query import validate_query
from query_gateway.contracts.validation import ValidateRequest
from query_gateway.domain.errors import GatewayError

router = APIRouter(prefix="/internal/v1", tags=["internal-queries"])


@router.post("/queries/validate")
async def validate_endpoint(
    body: ValidateRequest,
    auth: dict = AuthValidate,
) -> dict[str, Any]:
    try:
        limits = body.limits
        return validate_query(
            execution_id=body.executionId,
            datasource_id=body.datasourceId,
            sql=body.sql,
            tenant_id=body.tenantId,
            user_id=body.userId,
            max_rows=limits.maxRows if limits else None,
            trace_id=auth.get("trace_id"),
        )
    except GatewayError as e:
        e.execution_id = e.execution_id or body.executionId
        e.trace_id = e.trace_id or auth.get("trace_id")
        raise
