"""OData execute entry for /internal/v1."""

from __future__ import annotations

import json
import os
from typing import Any

from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.sap.contracts.datasource import ODataDatasourceConfig
from query_gateway.infrastructure.sap.contracts.query import ODataLogicalPlan
from query_gateway.infrastructure.sap.odata.client import execute_odata_plan
from query_gateway.infrastructure.sap.odata.policy_engine import legacy_to_logical_plan
from query_gateway.infrastructure.sap.security.authorization import (
    assert_no_cross_company,
    enforce_company_scope,
)
from query_gateway.infrastructure.sap.security.client_scope import assert_client_not_user_controlled
from query_gateway.infrastructure.sap.security.masking import mask_sensitive_rows
from query_gateway.infrastructure.sap.semantic.currency import validate_result_currency_pair


def _execution_mode_gate(execution_id: str | None = None) -> None:
    if os.environ.get("SAP_EXECUTION_ENABLED", "0") != "1":
        # Allow validate-only offline; execute requires flag — but gateway may still run in tests
        # when SAP_EXECUTION_ENABLED unset and NANOBASE_ENV=test
        if os.environ.get("NANOBASE_ENV") != "test" and os.environ.get("SAP_ALLOW_OFFLINE") != "1":
            raise GatewayError(
                "SAP_EXECUTION_DISABLED",
                "SAP_EXECUTION_ENABLED=0.",
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


def resolve_odata_plan(sql_or_plan: str | dict[str, Any], ds: dict[str, Any]) -> ODataLogicalPlan:
    if isinstance(sql_or_plan, dict):
        return ODataLogicalPlan.from_dict(sql_or_plan)
    text = (sql_or_plan or "").strip()
    if text.startswith("{"):
        return ODataLogicalPlan.from_dict(json.loads(text))
    service = ""
    services = ds.get("allowed_services") or []
    if services:
        service = list(services)[0] if not isinstance(services, str) else services
    return legacy_to_logical_plan(text, service=str(service or ""))


def execute_odata_ro(
    ds: dict[str, Any],
    sql_or_plan: str | dict[str, Any],
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
    execution_id: str | None = None,
    timeout_ms: int = 15_000,
    max_rows: int = 100,
    settings: Any = None,
) -> tuple[list[str], list[dict[str, Any]], bool, int]:
    _execution_mode_gate(execution_id)
    cfg = ODataDatasourceConfig.from_datasource(ds)
    plan = resolve_odata_plan(sql_or_plan, ds)
    assert_client_not_user_controlled(plan.to_dict().get("filters") or [])

    allowed_cc = ds.get("allowed_company_codes") or ds.get("allowedCompanyCodes")
    if allowed_cc:
        plan = enforce_company_scope(
            plan,
            allowed_company_codes=list(allowed_cc),
            company_code_field=str(ds.get("company_code_field") or "CompanyCode"),
        )

    result = execute_odata_plan(
        cfg,
        plan,
        timeout_s=max(1.0, timeout_ms / 1000.0),
        max_rows=max_rows,
        max_pages=1,
    )
    rows = mask_sensitive_rows(result["rows"])
    if allowed_cc:
        assert_no_cross_company(
            rows,
            allowed={str(c) for c in allowed_cc},
            field=str(ds.get("company_code_field") or "CompanyCode"),
        )
    amount_f = ds.get("amount_field")
    currency_f = ds.get("currency_field")
    if amount_f and currency_f:
        validate_result_currency_pair(rows, amount_field=amount_f, currency_field=currency_f)

    return result["columns"], rows, bool(result["truncated"]), int(result["executionTimeMs"])


def validate_odata_only(
    ds: dict[str, Any],
    sql_or_plan: str | dict[str, Any],
) -> dict[str, Any]:
    from query_gateway.infrastructure.sap.odata.query_builder import build_odata_request

    cfg = ODataDatasourceConfig.from_datasource(ds)
    plan = resolve_odata_plan(sql_or_plan, ds)
    assert_client_not_user_controlled(plan.to_dict().get("filters") or [])
    allowed_cc = ds.get("allowed_company_codes") or ds.get("allowedCompanyCodes")
    if allowed_cc:
        plan = enforce_company_scope(
            plan,
            allowed_company_codes=list(allowed_cc),
            company_code_field=str(ds.get("company_code_field") or "CompanyCode"),
        )
    built = build_odata_request(plan, cfg)
    return {
        "status": "APPROVED",
        "normalizedSql": json.dumps(plan.to_dict(), sort_keys=True),
        "plan": plan.to_dict(),
        "urlPath": built["path"],
        "warnings": built.get("warnings") or [],
        "dialect": "odata",
        "statementType": "ODATA_GET",
    }
