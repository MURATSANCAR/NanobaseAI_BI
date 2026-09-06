"""MetricCompiler.time_grain — monthly/other bucketed series for forecasting.

Forecasting V1 plan Faz 1.1: `date_trunc('<grain>', time_field) AS period`,
GROUP BY period (+ any breakdown column), ORDER BY period ASC (time order,
never rank order), combined with `period` (from/to) and `dimension_filters`.
"""

from __future__ import annotations

import pytest

from nanobase_api.semantic_catalog.application.seed_total_revenue_slice import (
    seed_total_revenue_slice,
)
from nanobase_api.semantic_catalog.application.services import compile_metric_sql
from nanobase_api.semantic_catalog.domain.errors import ValidationError
from nanobase_api.semantic_catalog.infrastructure.catalog_store import reset_catalog_store
from nanobase_api.semantic_catalog.infrastructure.metric_compiler import (
    CompileRequest,
    MetricCompiler,
)


@pytest.fixture()
def store():
    return reset_catalog_store()


def _seeded(store):
    ids = seed_total_revenue_slice(store, published=True)
    return store.metrics[ids["metric_id"]], store.filters[ids["filter_id"]]


def test_month_grain_postgres_shape(store):
    metric, filt = _seeded(store)
    r = MetricCompiler().compile(
        CompileRequest(
            metric=metric,
            filters=[filt],
            time_grain="month",
            period={"from": "2023-09-01", "to": "2026-09-01"},
            dimension_filters={"branch_city": "İstanbul"},
        )
    )
    sql = r.sql
    assert 'date_trunc(\'month\', v."order_date") AS "period"' in sql
    assert 'GROUP BY date_trunc(\'month\', v."order_date")' in sql
    assert 'ORDER BY date_trunc(\'month\', v."order_date") ASC' in sql
    assert "v.\"order_date\" >= '2023-09-01'" in sql
    assert "v.\"order_date\" < '2026-09-01'" in sql
    assert "v.\"branch_city\" = 'İstanbul'" in sql
    assert "v.\"status\" = 'completed'" in sql
    assert "LIMIT" not in sql
    assert r.logical_plan["timeGrain"] == "month"
    assert r.logical_plan["periodAlias"] == "period"


def test_grain_with_breakdown_orders_by_period_then_dimension(store):
    metric, filt = _seeded(store)
    r = MetricCompiler().compile(
        CompileRequest(metric=metric, filters=[filt], time_grain="month", group_by=["segment"])
    )
    assert 'GROUP BY date_trunc(\'month\', v."order_date"), v."segment"' in r.sql
    assert 'ORDER BY date_trunc(\'month\', v."order_date") ASC, v."segment" ASC' in r.sql
    # period column first, breakdown second, aggregate last
    select_block = r.sql.split("FROM")[0]
    assert select_block.index('"period"') < select_block.index('"segment"') < select_block.index('"total_revenue"')


def test_grain_is_deterministic(store):
    metric, filt = _seeded(store)
    c = MetricCompiler()
    a = c.compile(CompileRequest(metric=metric, filters=[filt], time_grain="month"))
    b = c.compile(CompileRequest(metric=metric, filters=[filt], time_grain="month"))
    assert a.sql == b.sql
    assert a.ast_fingerprint == b.ast_fingerprint


@pytest.mark.parametrize("grain", ["day", "week", "quarter", "year"])
def test_all_grains_accepted(store, grain):
    metric, filt = _seeded(store)
    r = MetricCompiler().compile(CompileRequest(metric=metric, filters=[filt], time_grain=grain))
    assert f"date_trunc('{grain}'" in r.sql


def test_invalid_grain_rejected(store):
    metric, filt = _seeded(store)
    with pytest.raises(ValidationError):
        MetricCompiler().compile(CompileRequest(metric=metric, filters=[filt], time_grain="fortnight"))


def test_grain_requires_time_field(store):
    metric, filt = _seeded(store)
    metric.time = None
    with pytest.raises(ValidationError):
        MetricCompiler().compile(CompileRequest(metric=metric, filters=[filt], time_grain="month"))


def test_oracle_grain_uses_trunc(store):
    metric, filt = _seeded(store)
    r = MetricCompiler().compile(
        CompileRequest(metric=metric, filters=[filt], time_grain="month", dialect="oracle")
    )
    assert "TRUNC(V.ORDER_DATE, 'MM') AS PERIOD" in r.sql
    assert "ORDER BY TRUNC(V.ORDER_DATE, 'MM') ASC" in r.sql


def test_compile_metric_sql_passes_time_grain(store):
    seed_total_revenue_slice(store, published=True)
    out = compile_metric_sql(
        store,
        tenant_id="default",
        datasource_id="bi_reporting",
        metric_code="total_revenue",
        time_grain="month",
        dimension_filters={"branch_city": "Ankara"},
    )
    assert "date_trunc('month'" in out["sql"]
    assert out["logicalPlan"]["timeGrain"] == "month"
    assert out["logicalPlan"]["dimensionFilters"] == {"branch_city": "Ankara"}
