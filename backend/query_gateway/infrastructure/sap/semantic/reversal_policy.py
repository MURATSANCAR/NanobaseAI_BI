"""Mandatory reversal / cancellation rules — not LLM suggestions."""

from __future__ import annotations

from typing import Any

from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.sap.contracts.query import ODataFilter, ODataLogicalPlan

SAP_MANDATORY_RULE_MISSING = "SAP_MANDATORY_RULE_MISSING"

KNOWN_RULES = {
    "exclude_reversed_documents": ODataFilter(
        field="IsReversed", operator="EQ", value=False
    ),
    "exclude_unposted_documents": ODataFilter(
        field="PostingStatus", operator="EQ", value="POSTED"
    ),
    "not_cleared": ODataFilter(field="ClearingStatus", operator="EQ", value="OPEN"),
    "posted_only": ODataFilter(field="PostingStatus", operator="EQ", value="POSTED"),
}


def apply_mandatory_rules(
    plan: ODataLogicalPlan,
    mandatory_rules: list[str],
    *,
    field_overrides: dict[str, str] | None = None,
) -> ODataLogicalPlan:
    if not mandatory_rules:
        raise GatewayError(
            SAP_MANDATORY_RULE_MISSING,
            "SAP metric requires mandatory rules.",
            status=400,
        )
    overrides = field_overrides or {}
    existing_fields = {f.field for f in plan.filters}
    for rule in mandatory_rules:
        template = KNOWN_RULES.get(rule)
        if template is None:
            raise GatewayError(
                SAP_MANDATORY_RULE_MISSING,
                f"Unknown mandatory SAP rule: {rule}",
                status=400,
            )
        field = overrides.get(rule, template.field)
        if field in existing_fields:
            continue
        plan.filters.append(
            ODataFilter(field=field, operator=template.operator, value=template.value)
        )
        existing_fields.add(field)
    return plan


def validate_metric_rules(metric: dict[str, Any]) -> None:
    rules = metric.get("mandatoryRules") or metric.get("mandatory_rules") or []
    if metric.get("domain", "").upper() in ("SAP_FI", "FI") and not rules:
        raise GatewayError(
            SAP_MANDATORY_RULE_MISSING,
            "FI metric missing mandatoryRules.",
            status=400,
        )
    for r in rules:
        if r not in KNOWN_RULES:
            raise GatewayError(
                SAP_MANDATORY_RULE_MISSING,
                f"Unknown mandatory SAP rule: {r}",
                status=400,
            )
