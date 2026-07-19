"""Company code / authorization scope enforcement."""

from __future__ import annotations

from typing import Any

from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.sap.contracts.query import ODataFilter, ODataLogicalPlan

SAP_AUTHORIZATION_FAILURE = "SAP_AUTHORIZATION_FAILURE"


def enforce_company_scope(
    plan: ODataLogicalPlan,
    *,
    allowed_company_codes: list[str] | None,
    company_code_field: str = "CompanyCode",
) -> ODataLogicalPlan:
    if not allowed_company_codes:
        raise GatewayError(
            SAP_AUTHORIZATION_FAILURE,
            "allowedCompanyCodes required for SAP execute.",
            status=403,
        )
    allowed = {c.strip() for c in allowed_company_codes}
    requested = None
    for f in plan.filters:
        if f.field == company_code_field and f.normalized_op() == "EQ":
            requested = str(f.value)
    if requested is None:
        if len(allowed) == 1:
            only = next(iter(allowed))
            plan.filters.append(ODataFilter(field=company_code_field, operator="EQ", value=only))
            return plan
        raise GatewayError(
            SAP_AUTHORIZATION_FAILURE,
            "Company code filter required.",
            status=403,
        )
    if requested not in allowed:
        raise GatewayError(
            SAP_AUTHORIZATION_FAILURE,
            "Company code outside authorization scope.",
            status=403,
        )
    return plan


def assert_no_cross_company(rows: list[dict[str, Any]], *, allowed: set[str], field: str = "CompanyCode") -> None:
    for row in rows:
        cc = row.get(field)
        if cc is not None and str(cc) not in allowed:
            raise GatewayError(
                SAP_AUTHORIZATION_FAILURE,
                "Cross-company data detected in result.",
                status=403,
            )
