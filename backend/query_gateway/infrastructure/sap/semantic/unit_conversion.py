"""Quantity/unit binding validation."""

from __future__ import annotations

from typing import Any

from query_gateway.domain.errors import GatewayError

SAP_UNIT_VALIDATION_FAILED = "SAP_UNIT_VALIDATION_FAILED"


def validate_unit_binding(binding: dict[str, Any]) -> None:
    qty = binding.get("quantityField") or binding.get("quantity_field")
    unit = binding.get("unitField") or binding.get("unit_field")
    if qty and not unit:
        raise GatewayError(
            SAP_UNIT_VALIDATION_FAILED,
            "quantityField requires unitField.",
            status=400,
        )
