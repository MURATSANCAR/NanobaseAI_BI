"""HANA view binding helpers."""

from __future__ import annotations

from typing import Any

from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.sap.semantic.currency import validate_currency_binding

SAP_HANA_BINDING_INVALID = "SAP_HANA_BINDING_INVALID"


def validate_hana_binding(binding: dict[str, Any]) -> None:
    if (binding.get("sourceType") or "") != "SAP_HANA_VIEW":
        raise GatewayError(
            SAP_HANA_BINDING_INVALID,
            "sourceType must be SAP_HANA_VIEW.",
            status=400,
        )
    if not binding.get("schema") or not binding.get("view"):
        raise GatewayError(SAP_HANA_BINDING_INVALID, "schema and view required.", status=400)
    validate_currency_binding(binding)


def compile_hana_select(binding: dict[str, Any], *, company_code: str | None = None, limit: int = 100) -> str:
    validate_hana_binding(binding)
    schema = binding["schema"]
    view = binding["view"]
    amount = binding["amountField"]
    currency = binding["currencyField"]
    cc_field = binding.get("companyCodeField") or "COMPANY_CODE"
    cols = f"{cc_field}, {amount}, {currency}"
    sql = f"SELECT {cols} FROM {schema}.{view}"
    if company_code:
        sql += f" WHERE {cc_field} = '{company_code.replace(chr(39), chr(39)+chr(39))}'"
    sql += f" LIMIT {int(limit)}"
    return sql
