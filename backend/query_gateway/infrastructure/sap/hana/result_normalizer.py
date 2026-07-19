"""HANA → Nanobase type normalization."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

HANA_TYPE_MAP = {
    "TINYINT": "INTEGER",
    "SMALLINT": "INTEGER",
    "INTEGER": "INTEGER",
    "BIGINT": "INTEGER",
    "DECIMAL": "DECIMAL",
    "SMALLDECIMAL": "DECIMAL",
    "REAL": "FLOAT",
    "DOUBLE": "FLOAT",
    "VARCHAR": "STRING",
    "NVARCHAR": "STRING",
    "DATE": "DATE",
    "TIME": "TIME",
    "TIMESTAMP": "DATETIME",
    "SECONDDATE": "DATETIME",
    "CLOB": "LIMITED_STRING",
    "NCLOB": "LIMITED_STRING",
    "BLOB": "REJECTED",
    "VARBINARY": "RESTRICTED_BINARY",
}

CLOB_LIMIT = 4096


def normalize_hana_value(v: Any, *, type_name: str | None = None) -> Any:
    t = (type_name or "").upper()
    if t == "BLOB" or isinstance(v, (bytes, memoryview)) and t == "BLOB":
        raise ValueError("BLOB rejected")
    if isinstance(v, (bytes, memoryview)):
        if t in ("VARBINARY",):
            return {"restricted": True, "length": len(bytes(v))}
        data = bytes(v)
        return data[:CLOB_LIMIT].decode("utf-8", errors="replace")
    if isinstance(v, Decimal):
        return format(v, "f")
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def normalize_hana_rows(
    cols: list[str],
    rows: list[tuple[Any, ...]],
    *,
    col_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {}
        for i, col in enumerate(cols):
            typ = col_types[i] if col_types and i < len(col_types) else None
            item[col] = normalize_hana_value(row[i], type_name=typ)
        out.append(item)
    return out
