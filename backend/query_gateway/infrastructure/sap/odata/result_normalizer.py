"""OData EDM → Nanobase type normalization."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

EDM_MAP = {
    "Edm.String": "STRING",
    "Edm.Boolean": "BOOLEAN",
    "Edm.Decimal": "DECIMAL",
    "Edm.Int16": "INTEGER",
    "Edm.Int32": "INTEGER",
    "Edm.Int64": "INTEGER",
    "Edm.Date": "DATE",
    "Edm.DateTimeOffset": "OFFSET_DATETIME",
    "Edm.TimeOfDay": "TIME",
    "Edm.Guid": "UUID",
    "Edm.Double": "FLOAT",
    "Edm.Single": "FLOAT",
}


def map_edm_type(edm: str | None) -> str:
    if not edm:
        return "STRING"
    if edm.startswith("Collection("):
        return "CONTROLLED_LIST"
    return EDM_MAP.get(edm, "STRING")


def normalize_odata_rows(
    rows: list[dict[str, Any]],
    *,
    decimal_fields: set[str] | None = None,
) -> list[dict[str, Any]]:
    decimal_fields = decimal_fields or set()
    out: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {}
        for k, v in row.items():
            if str(k).startswith("@") or str(k).startswith("__"):
                continue
            if k in decimal_fields or (isinstance(v, str) and _looks_decimal(v) and "Amount" in k):
                item[k] = _as_decimal_str(v)
            else:
                item[k] = v
        out.append(item)
    return out


def _looks_decimal(v: str) -> bool:
    try:
        Decimal(v)
        return "." in v or "E" in v.upper()
    except (InvalidOperation, ValueError):
        return False


def _as_decimal_str(v: Any) -> str:
    if isinstance(v, Decimal):
        return format(v, "f")
    try:
        return format(Decimal(str(v)), "f")
    except (InvalidOperation, ValueError):
        return str(v)
