"""Currency/amount binding validation — zero tolerance for mismatch."""

from __future__ import annotations

from typing import Any

from query_gateway.domain.errors import GatewayError

SAP_CURRENCY_VALIDATION_FAILED = "SAP_CURRENCY_VALIDATION_FAILED"


def validate_currency_binding(binding: dict[str, Any]) -> None:
    amount = binding.get("amountField") or binding.get("amount_field")
    currency = binding.get("currencyField") or binding.get("currency_field")
    policy = binding.get("currencyPolicy") or binding.get("currency_policy")
    if not amount or not currency:
        raise GatewayError(
            SAP_CURRENCY_VALIDATION_FAILED,
            "amountField and currencyField are required together.",
            status=400,
        )
    if not policy:
        raise GatewayError(
            SAP_CURRENCY_VALIDATION_FAILED,
            "currencyPolicy is required.",
            status=400,
        )


def validate_result_currency_pair(
    rows: list[dict[str, Any]],
    *,
    amount_field: str,
    currency_field: str,
) -> None:
    for row in rows:
        has_amt = amount_field in row and row[amount_field] is not None
        has_cur = currency_field in row and row[currency_field] is not None
        if has_amt and not has_cur:
            raise GatewayError(
                SAP_CURRENCY_VALIDATION_FAILED,
                "Amount present without currency.",
                status=400,
            )
