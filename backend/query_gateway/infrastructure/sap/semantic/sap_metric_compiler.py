"""Compile SAP FI metric → OData logical plan."""

from __future__ import annotations

from typing import Any

from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.sap.semantic.cds_binding import build_plan_from_binding
from query_gateway.infrastructure.sap.semantic.reversal_policy import validate_metric_rules

SAP_METRIC_INVALID = "SAP_METRIC_INVALID"


def compile_sap_metric(
    metric: dict[str, Any],
    binding: dict[str, Any],
    *,
    company_code: str | None = None,
    top: int = 100,
) -> dict[str, Any]:
    validate_metric_rules(metric)
    ledger = metric.get("ledger") or binding.get("ledger")
    if (metric.get("domain") or "").upper() in ("SAP_FI", "FI") and not ledger:
        raise GatewayError(SAP_METRIC_INVALID, "FI metric requires ledger.", status=400)

    merged = dict(binding)
    merged.setdefault("domain", metric.get("domain"))
    merged.setdefault(
        "mandatoryRules",
        metric.get("mandatoryRules") or metric.get("mandatory_rules") or metric.get("filters"),
    )
    # Map logical filter names to rules when present
    filters = metric.get("filters") or []
    rules = list(merged.get("mandatoryRules") or [])
    for f in filters:
        if f in ("posted_only", "not_cleared", "exclude_reversed_documents", "exclude_unposted_documents"):
            if f not in rules:
                rules.append(f)
    # open receivable typical rules
    if metric.get("code") == "open_receivable_amount" or metric.get("metric") == "open_receivable_amount":
        for r in ("posted_only", "not_cleared", "exclude_reversed_documents"):
            if r not in rules:
                rules.append(r)
    merged["mandatoryRules"] = rules

    plan = build_plan_from_binding(merged, company_code=company_code, top=top)
    return {
        "plan": plan.to_dict(),
        "ledger": ledger,
        "currencyPolicy": metric.get("currencyPolicy") or binding.get("currencyPolicy"),
        "metric": metric.get("code") or metric.get("metric"),
    }
