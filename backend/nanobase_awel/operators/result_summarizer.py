"""Deterministic result summary before LLM explain."""

from __future__ import annotations

from typing import Any


def summarize_result(
    columns: list[Any],
    rows: list[dict[str, Any]],
    *,
    truncated: bool = False,
    max_sample: int = 100,
) -> dict[str, Any]:
    col_names: list[str] = []
    for c in columns:
        if isinstance(c, dict):
            col_names.append(str(c.get("name") or c))
        else:
            col_names.append(str(c))

    numeric_stats: dict[str, dict[str, float]] = {}
    for col in col_names:
        vals: list[float] = []
        for row in rows:
            v = row.get(col)
            if isinstance(v, bool) or v is None:
                continue
            try:
                vals.append(float(v))
            except Exception:
                continue
        if vals:
            numeric_stats[col] = {
                "min": min(vals),
                "max": max(vals),
                "sum": sum(vals),
                "count": float(len(vals)),
            }

    sample = rows[:max_sample]
    return {
        "rowCount": len(rows),
        "truncated": truncated,
        "columns": col_names,
        "numericStatistics": numeric_stats,
        "sampleRows": sample,
    }
