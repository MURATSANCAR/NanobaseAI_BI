"""Result masking for sensitive SAP fields."""

from __future__ import annotations

from typing import Any

SENSITIVE_DEFAULT = frozenset(
    {
        "BankAccount",
        "IBAN",
        "TaxNumber",
        "TaxNumber1",
        "SocialSecurityNumber",
        "CreditCardNumber",
    }
)


def mask_sensitive_rows(
    rows: list[dict[str, Any]],
    *,
    sensitive_fields: set[str] | None = None,
) -> list[dict[str, Any]]:
    fields = sensitive_fields or set(SENSITIVE_DEFAULT)
    out = []
    for row in rows:
        item = dict(row)
        for f in fields:
            if f in item and item[f] is not None:
                item[f] = "***"
        out.append(item)
    return out
