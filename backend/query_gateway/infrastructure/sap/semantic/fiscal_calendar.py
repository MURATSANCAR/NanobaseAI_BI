"""Fiscal period resolution — calendar quarter ≠ SAP fiscal period."""

from __future__ import annotations

from typing import Any

from query_gateway.domain.errors import GatewayError

SAP_FISCAL_AMBIGUOUS = "SAP_FISCAL_AMBIGUOUS"


def resolve_fiscal_period(
    *,
    year: int,
    period_hint: str,
    fiscal_year_variant: str,
    special_periods: list[int] | None = None,
) -> dict[str, Any]:
    hint = (period_hint or "").strip().lower()
    special_periods = special_periods or []

    # Explicit SAP period P01..P16 / 001..016
    if hint.startswith("p") and hint[1:].isdigit():
        period = int(hint[1:])
        return {
            "fiscalYear": year,
            "fiscalPeriod": f"{period:03d}",
            "fiscalYearVariant": fiscal_year_variant,
            "kind": "SAP_PERIOD",
        }
    if hint.isdigit() and 1 <= int(hint) <= 16:
        period = int(hint)
        return {
            "fiscalYear": year,
            "fiscalPeriod": f"{period:03d}",
            "fiscalYearVariant": fiscal_year_variant,
            "kind": "SAP_PERIOD",
        }

    # Calendar quarter language — ambiguous vs fiscal; require clarification unless K4 calendar
    quarter_map = {
        "q1": 1,
        "q2": 2,
        "q3": 3,
        "q4": 4,
        "birinci çeyrek": 1,
        "ikinci çeyrek": 2,
        "üçüncü çeyrek": 3,
        "ucuncu ceyrek": 3,
        "dördüncü çeyrek": 4,
        "third quarter": 3,
        "3rd quarter": 3,
    }
    if hint in quarter_map:
        if fiscal_year_variant.upper() not in ("K4", "CALENDAR", "V3"):
            raise GatewayError(
                SAP_FISCAL_AMBIGUOUS,
                "Calendar quarter vs SAP fiscal period is ambiguous for this fiscalYearVariant; clarify.",
                status=400,
            )
        q = quarter_map[hint]
        # Map quarter to mid period of calendar FY
        start = (q - 1) * 3 + 1
        return {
            "fiscalYear": year,
            "fiscalPeriodFrom": f"{start:03d}",
            "fiscalPeriodTo": f"{start + 2:03d}",
            "fiscalYearVariant": fiscal_year_variant,
            "kind": "CALENDAR_QUARTER",
        }

    if "özel" in hint or "special" in hint:
        if not special_periods:
            raise GatewayError(
                SAP_FISCAL_AMBIGUOUS,
                "Special period requested but none configured.",
                status=400,
            )
        return {
            "fiscalYear": year,
            "fiscalPeriods": [f"{p:03d}" for p in special_periods],
            "kind": "SPECIAL_PERIOD",
        }

    raise GatewayError(
        SAP_FISCAL_AMBIGUOUS,
        f"Cannot resolve fiscal period hint: {period_hint}",
        status=400,
    )
