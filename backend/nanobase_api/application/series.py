"""Governed metric time series (plan Faz 1.3) — the `query_semantic()` of the
forecasting design, as an internal service used by the /series endpoint and
the chat forecast branch.

metric (published) → MetricCompiler(time_grain) → Query Gateway → rows
The LLM is nowhere in this path.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from forecasting.contracts.builder import next_period, period_start
from nanobase_api.semantic_catalog.application.services import compile_metric_sql
from nanobase_api.semantic_catalog.domain.errors import DomainError
from nanobase_api.semantic_catalog.infrastructure.catalog_store import get_catalog_store

_GRAIN_FREQ = {"day": "D", "week": "W", "month": "M", "quarter": "Q", "year": "Y"}


class SeriesError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def history_window(grain: str, history_periods: int, *, today: date | None = None) -> dict[str, str]:
    """[from, to) covering the last `history_periods` closed buckets — the current
    (partial) bucket is excluded so the last point is never a half month."""
    today = today or date.today()
    freq = _GRAIN_FREQ[grain]
    current = period_start(today, freq)
    start = next_period(current, freq, -history_periods)
    return {"from": start.isoformat(), "to": current.isoformat()}


def compile_series_sql(
    *,
    tenant_id: str,
    datasource_id: str,
    metric_code: str,
    grain: str = "month",
    history_periods: int = 36,
    dimension_filters: dict[str, Any] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    if grain not in _GRAIN_FREQ:
        raise SeriesError("INVALID_GRAIN", f"Geçersiz zaman aralığı: {grain}")
    try:
        compiled = compile_metric_sql(
            get_catalog_store(),
            tenant_id=tenant_id,
            datasource_id=datasource_id,
            metric_code=metric_code,
            period=history_window(grain, history_periods, today=today),
            dimension_filters=dimension_filters or {},
            time_grain=grain,
        )
    except DomainError as e:
        raise SeriesError(e.code or "METRIC_UNAVAILABLE", e.message) from e
    compiled["frequency"] = _GRAIN_FREQ[grain]
    return compiled


def rows_to_points(rows: list[Any], columns: list[Any], *, period_alias: str = "period", metric_code: str) -> list[dict[str, Any]]:
    """Gateway rows (dicts or positional lists) → [{"period": iso, "value": float}]."""
    col_names: list[str] = []
    for c in columns or []:
        name = str(c.get("name") if isinstance(c, dict) else c or "").strip()
        if name:
            col_names.append(name)
    out: list[dict[str, Any]] = []
    for row in rows or []:
        if isinstance(row, dict):
            period = row.get(period_alias)
            value = row.get(metric_code)
            if value is None:
                others = [k for k in row.keys() if k != period_alias]
                value = row.get(others[-1]) if others else None
        else:
            idx_p = col_names.index(period_alias) if period_alias in col_names else 0
            idx_v = col_names.index(metric_code) if metric_code in col_names else len(row) - 1
            period, value = row[idx_p], row[idx_v]
        p = str(period)[:10] if period is not None else None
        out.append({"period": p, "value": float(value) if value is not None else None})
    return out


async def load_metric_series(
    *,
    tenant_id: str,
    datasource_id: str,
    metric_code: str,
    grain: str = "month",
    history_periods: int = 36,
    dimension_filters: dict[str, Any] | None = None,
    execution_id: str | None = None,
) -> dict[str, Any]:
    """Compile + execute through the Query Gateway. Raises SeriesError on failure."""
    from nanobase_api.infrastructure.query_gateway_client import QueryGatewayClient

    compiled = compile_series_sql(
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        metric_code=metric_code,
        grain=grain,
        history_periods=history_periods,
        dimension_filters=dimension_filters,
    )
    qg = QueryGatewayClient()
    res = await qg.execute(sql=compiled["sql"], datasource_id=datasource_id, execution_id=execution_id, tenant_id=tenant_id)
    if not res.get("ok"):
        raise SeriesError(str(res.get("code") or "GATEWAY_FAILED"), str(res.get("message") or res.get("error") or "Gateway execute failed"))
    points = rows_to_points(res.get("rows") or [], res.get("columns") or [], metric_code=metric_code)
    return {
        "metricCode": metric_code,
        "grain": grain,
        "frequency": compiled["frequency"],
        "dimensionFilters": dict(dimension_filters or {}),
        "period": compiled["logicalPlan"].get("period"),
        "sql": compiled["sql"],
        "sqlSource": "semantic_metric_compiler",
        "astFingerprint": compiled.get("astFingerprint"),
        "logicalPlan": compiled.get("logicalPlan"),
        "rows": points,
        "rowCount": len(points),
        "truncated": bool(res.get("truncated")),
    }
