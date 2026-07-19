"""CDS/OData metric binding helpers."""

from __future__ import annotations

from typing import Any

from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.sap.contracts.query import ODataFilter, ODataLogicalPlan
from query_gateway.infrastructure.sap.semantic.currency import validate_currency_binding
from query_gateway.infrastructure.sap.semantic.reversal_policy import apply_mandatory_rules

SAP_BINDING_INVALID = "SAP_BINDING_INVALID"


def build_plan_from_binding(
    binding: dict[str, Any],
    *,
    company_code: str | None = None,
    extra_select: list[str] | None = None,
    top: int = 100,
) -> ODataLogicalPlan:
    if (binding.get("sourceType") or binding.get("source_type")) not in (
        "SAP_ODATA",
        None,
        "",
    ) and binding.get("sourceType") != "SAP_ODATA":
        st = binding.get("sourceType") or binding.get("source_type")
        if st and st != "SAP_ODATA":
            raise GatewayError(SAP_BINDING_INVALID, f"Expected SAP_ODATA binding, got {st}", status=400)

    validate_currency_binding(binding)
    ledger = binding.get("ledger")
    if binding.get("domain", "").upper() in ("SAP_FI", "FI") and not ledger:
        # allow ledger on metric level
        pass

    select = list(
        dict.fromkeys(
            [
                *(extra_select or []),
                binding.get("amountField"),
                binding.get("currencyField"),
                binding.get("companyCodeField") or "CompanyCode",
            ]
        )
    )
    select = [s for s in select if s]

    plan = ODataLogicalPlan(
        source_type="SAP_ODATA",
        service=str(binding.get("service") or ""),
        entity_set=str(binding.get("entitySet") or binding.get("entity_set") or ""),
        select=select,
        filters=[],
        top=top,
    )
    cc_field = binding.get("companyCodeField") or "CompanyCode"
    if company_code:
        plan.filters.append(ODataFilter(field=cc_field, operator="EQ", value=company_code))

    rules = binding.get("mandatoryRules") or binding.get("mandatory_rules") or []
    field_overrides = {}
    if binding.get("clearingStatusField"):
        field_overrides["not_cleared"] = binding["clearingStatusField"]
    if binding.get("reversalField"):
        field_overrides["exclude_reversed_documents"] = binding["reversalField"]
    if binding.get("postingStatusField"):
        field_overrides["exclude_unposted_documents"] = binding["postingStatusField"]
        field_overrides["posted_only"] = binding["postingStatusField"]

    if rules:
        plan = apply_mandatory_rules(plan, rules, field_overrides=field_overrides)
    return plan
