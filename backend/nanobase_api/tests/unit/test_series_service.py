from __future__ import annotations

from datetime import date

import pytest

from nanobase_api.application.series import (
    SeriesError,
    compile_series_sql,
    history_window,
    rows_to_points,
)
from nanobase_api.semantic_catalog.application.seed_total_revenue_slice import (
    seed_total_revenue_slice,
)
from nanobase_api.semantic_catalog.infrastructure.catalog_store import reset_catalog_store


@pytest.fixture()
def store():
    s = reset_catalog_store()
    seed_total_revenue_slice(s, published=True)
    return s


def test_history_window_excludes_current_partial_month():
    w = history_window("month", 36, today=date(2026, 9, 6))
    assert w == {"from": "2023-09-01", "to": "2026-09-01"}
    assert history_window("quarter", 8, today=date(2026, 9, 6)) == {"from": "2024-07-01", "to": "2026-07-01"}


def test_compile_series_sql_month(store):
    out = compile_series_sql(
        tenant_id="default",
        datasource_id="bi_reporting",
        metric_code="total_revenue",
        grain="month",
        history_periods=36,
        dimension_filters={"branch_city": "İstanbul"},
        today=date(2026, 9, 6),
    )
    sql = out["sql"]
    assert "date_trunc('month'" in sql and "ORDER BY date_trunc('month'" in sql
    assert "'2023-09-01'" in sql and "'2026-09-01'" in sql
    assert "'İstanbul'" in sql
    assert out["frequency"] == "M"
    assert out["logicalPlan"]["timeGrain"] == "month"


def test_compile_series_unknown_metric(store):
    with pytest.raises(SeriesError):
        compile_series_sql(tenant_id="default", datasource_id="bi_reporting", metric_code="nope", today=date(2026, 9, 6))


def test_compile_series_bad_grain(store):
    with pytest.raises(SeriesError) as e:
        compile_series_sql(tenant_id="default", datasource_id="bi_reporting", metric_code="total_revenue", grain="hour")
    assert e.value.code == "INVALID_GRAIN"


def test_rows_to_points_dict_and_positional():
    dict_rows = [{"period": "2026-01-01T00:00:00", "total_revenue": "12.5"}, {"period": "2026-02-01", "total_revenue": 7}]
    assert rows_to_points(dict_rows, ["period", "total_revenue"], metric_code="total_revenue") == [
        {"period": "2026-01-01", "value": 12.5},
        {"period": "2026-02-01", "value": 7.0},
    ]
    pos_rows = [["2026-01-01", 3], ["2026-02-01", None]]
    assert rows_to_points(pos_rows, [{"name": "period"}, {"name": "total_revenue"}], metric_code="total_revenue") == [
        {"period": "2026-01-01", "value": 3.0},
        {"period": "2026-02-01", "value": None},
    ]
