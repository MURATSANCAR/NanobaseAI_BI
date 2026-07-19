"""Oracle result type normalization (NUMBER/DATE/LOB safety)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

MAX_CLOB_CHARS = 4 * 1024  # 4 KB

REJECTED_TYPES = frozenset(
    {
        "BLOB",
        "BFILE",
        "LONG RAW",
        "XMLTYPE",
        "SDO_GEOMETRY",
        "REF CURSOR",
        "CURSOR",
    }
)


def oracle_type_name(type_obj: Any) -> str:
    name = getattr(type_obj, "name", None) or getattr(type_obj, "__name__", None) or str(type_obj)
    return str(name).upper()


def normalize_oracle_value(
    value: Any,
    *,
    type_name: str | None = None,
    precision: int | None = None,
    scale: int | None = None,
    max_clob: int = MAX_CLOB_CHARS,
) -> Any:
    """Normalize a single Oracle cell for JSON-safe frontend payload."""
    if value is None:
        return None

    tname = (type_name or "").upper()
    if tname in REJECTED_TYPES or type(value).__name__.upper() in REJECTED_TYPES:
        return {"rejected": True, "type": tname or type(value).__name__}

    # LOB / CLOB
    if hasattr(value, "read") and not isinstance(value, (str, bytes, memoryview)):
        try:
            chunk = value.read(max_clob + 1)
            if isinstance(chunk, bytes):
                text = chunk.decode("utf-8", errors="replace")
            else:
                text = str(chunk)
            truncated = len(text) > max_clob
            return {
                "value": text[:max_clob],
                "truncated": truncated,
                "type": "LIMITED_STRING",
            }
        except Exception:
            return {"rejected": True, "type": "LOB"}

    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"rejected": True, "type": "BLOB"}

    if isinstance(value, bool):
        return value

    if isinstance(value, int) and not isinstance(value, bool):
        return value

    if isinstance(value, float):
        # Prefer Decimal string for financial fidelity when coming from NUMBER
        return str(Decimal(str(value)))

    if isinstance(value, Decimal):
        if scale == 0 or (precision is not None and scale == 0):
            try:
                return int(value)
            except Exception:
                return str(value)
        # Keep as string to avoid JSON float precision loss
        return format(value, "f")

    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day).isoformat()

    if isinstance(value, str):
        if len(value) > max_clob:
            return {"value": value[:max_clob], "truncated": True, "type": "LIMITED_STRING"}
        return value

    # Fallback
    s = str(value)
    if len(s) > max_clob:
        return {"value": s[:max_clob], "truncated": True, "type": "LIMITED_STRING"}
    return s


def number_nanobase_type(precision: int | None, scale: int | None) -> str:
    if scale == 0 and precision is not None:
        return "INTEGER"
    return "DECIMAL"


def normalize_oracle_rows(
    columns: list[str],
    rows: list[tuple[Any, ...] | list[Any]],
    *,
    type_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {}
        for i, col in enumerate(columns):
            tname = type_names[i] if type_names and i < len(type_names) else None
            item[col] = normalize_oracle_value(row[i], type_name=tname)
        out.append(item)
    return out
