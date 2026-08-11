"""total_revenue metric slice: deterministic compile + compile_metric_sql wiring.

Guards the fix for the quality-corpus qa-014 case ("Toplam ciro nedir?"),
which the local LLM answered inconsistently (sometimes summing
sales_order_items correctly, sometimes reading analytics.invoices.gross_amount
— a different business figure). Publishing it removes the LLM from the loop
for this exact question pattern: same logical plan in, byte-identical SQL out.
"""

from __future__ import annotations

import pytest

from nanobase_api.semantic_catalog.application.seed_total_revenue_slice import (
    seed_total_revenue_slice,
)
from nanobase_api.semantic_catalog.application.services import compile_metric_sql
from nanobase_api.semantic_catalog.infrastructure.catalog_store import reset_catalog_store
from nanobase_api.semantic_catalog.infrastructure.metric_compiler import (
    CompileRequest,
    MetricCompiler,
)


@pytest.fixture()
def store():
    return reset_catalog_store()


def test_compiler_deterministic_total_revenue(store):
    ids = seed_total_revenue_slice(store, published=True)
    metric = store.metrics[ids["metric_id"]]
    filt = store.filters[ids["filter_id"]]
    c = MetricCompiler()

    r1 = c.compile(CompileRequest(metric=metric, filters=[filt]))
    r2 = c.compile(CompileRequest(metric=metric, filters=[filt]))
    assert r1.ast_fingerprint == r2.ast_fingerprint
    assert "SUM" in r1.sql
    assert "line_total" in r1.sql
    assert "v_sales_revenue_lines" in r1.sql
    assert "'completed'" in r1.sql
    assert "status" in r1.sql


def test_compile_metric_sql_via_catalog_wiring(store):
    """Exercises the exact call path chat_gateway takes (compile_metric_sql →
    get_metric_by_code + list_published_filters), not just the raw compiler."""
    seed_total_revenue_slice(store, tenant_id="default", datasource_id="bi_reporting", published=True)
    result = compile_metric_sql(
        store,
        tenant_id="default",
        datasource_id="bi_reporting",
        metric_code="total_revenue",
    )
    assert "SUM" in result["sql"]
    assert "'completed'" in result["sql"]
    assert result["logicalPlan"]["metric"] == "total_revenue"


def test_compile_metric_sql_requires_published_status(store):
    """Draft metrics must not be resolvable — governance would be pointless
    if an unreviewed definition could already answer live questions."""
    seed_total_revenue_slice(store, tenant_id="default", datasource_id="bi_reporting", published=False)
    with pytest.raises(Exception):
        compile_metric_sql(
            store,
            tenant_id="default",
            datasource_id="bi_reporting",
            metric_code="total_revenue",
        )


def test_metric_scoped_to_its_own_tenant_and_datasource(store):
    seed_total_revenue_slice(store, tenant_id="default", datasource_id="bi_reporting", published=True)
    with pytest.raises(Exception):
        compile_metric_sql(
            store,
            tenant_id="default",
            datasource_id="erp",
            metric_code="total_revenue",
        )
