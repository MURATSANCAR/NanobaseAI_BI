"""Result guard: normalize, limit, mask, safe JSON."""

from __future__ import annotations

import math
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from query_gateway.config.settings import Settings, get_settings
from query_gateway.domain.errors import RESULT_LIMIT_EXCEEDED, RESULT_MASKING_FAILED, GatewayError
from query_gateway.infrastructure.result.masking import column_mask_kind, mask_value


def _normalize_cell(
    value: Any,
    settings: Settings,
    *,
    preserve_decimal_strings: bool = False,
) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, Decimal):
        if preserve_decimal_strings:
            return format(value, "f")
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (bytes, memoryview, bytearray)):
        # risk: drop/truncate
        raw = bytes(value)
        if len(raw) > settings.max_cell_bytes:
            return {"truncated": True, "type": "BYTEA"}
        return raw.decode("utf-8", errors="replace")[: settings.max_cell_bytes]
    if isinstance(value, (dict, list)):
        return value
    s = str(value)
    if len(s.encode("utf-8")) > settings.max_cell_bytes:
        return s.encode("utf-8")[: settings.max_cell_bytes].decode("utf-8", errors="ignore")
    return s


def guard_result(
    columns: list[str],
    rows: list[dict[str, Any]],
    *,
    column_policies: dict[str, str] | None = None,
    truncated: bool = False,
    settings: Settings | None = None,
    preserve_decimal_strings: bool = False,
) -> dict[str, Any]:
    settings = settings or get_settings()
    policies = {k.lower(): str(v).upper() for k, v in (column_policies or {}).items()}

    if len(columns) > settings.max_columns:
        raise GatewayError(
            RESULT_LIMIT_EXCEEDED,
            "Kolon sayısı limiti aşıldı.",
            status=400,
        )

    out_cols = []
    masked_count = 0
    for c in columns:
        kind = column_mask_kind(c, policies)
        out_cols.append(
            {
                "name": c,
                "type": "STRING",
                "masked": kind is not None,
            }
        )

    out_rows: list[dict[str, Any]] = []
    payload = 0
    try:
        for row in rows:
            item: dict[str, Any] = {}
            for c in columns:
                val = _normalize_cell(
                    row.get(c),
                    settings,
                    preserve_decimal_strings=preserve_decimal_strings,
                )
                kind = column_mask_kind(c, policies)
                if kind:
                    val = mask_value(val, kind)
                    masked_count += 1
                item[c] = val
            # rough size
            payload += len(str(item).encode("utf-8"))
            if payload > settings.max_payload_bytes:
                truncated = True
                break
            out_rows.append(item)
    except GatewayError:
        raise
    except Exception as e:
        raise GatewayError(
            RESULT_MASKING_FAILED,
            "Sonuç maskeleme başarısız.",
            status=500,
        ) from e

    return {
        "columns": out_cols,
        "rows": out_rows,
        "rowCount": len(out_rows),
        "truncated": truncated,
        "maskedCells": masked_count,
    }
