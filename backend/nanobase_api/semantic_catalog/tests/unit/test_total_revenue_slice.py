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


def test_group_by_breakdown_is_deterministic_and_tie_broken(store):
    """qa-016/017 shape: 'segmentlere göre ciro' — a dimensional breakdown
    with no ranking. Two independent compiles of the same request must be
    byte-identical, and Postgres gives no ordering guarantee among tied
    aggregate values without the tie-break column."""
    seed_total_revenue_slice(store, tenant_id="default", datasource_id="bi_reporting", published=True)
    r1 = compile_metric_sql(
        store,
        tenant_id="default",
        datasource_id="bi_reporting",
        metric_code="total_revenue",
        group_by=["segment"],
    )
    r2 = compile_metric_sql(
        store,
        tenant_id="default",
        datasource_id="bi_reporting",
        metric_code="total_revenue",
        group_by=["segment"],
    )
    assert r1["sql"] == r2["sql"]
    assert '"segment"' in r1["sql"]
    assert "GROUP BY" in r1["sql"]
    assert "ORDER BY" in r1["sql"]
    assert '"segment" ASC' in r1["sql"]  # tie-break
    assert "LIMIT" not in r1["sql"]


def test_ranked_top_n_breakdown(store):
    """qa-015 shape: 'ilk 3 müşteri' — GROUP BY + ORDER BY aggregate DESC + LIMIT."""
    seed_total_revenue_slice(store, tenant_id="default", datasource_id="bi_reporting", published=True)
    result = compile_metric_sql(
        store,
        tenant_id="default",
        datasource_id="bi_reporting",
        metric_code="total_revenue",
        group_by=["customer_name"],
        limit=3,
    )
    assert '"customer_name"' in result["sql"]
    assert "ORDER BY SUM" in result["sql"]
    assert "DESC" in result["sql"]
    assert "LIMIT 3" in result["sql"]
    assert result["logicalPlan"]["limit"] == 3


def test_total_quantity_sold_metric(store):
    """qa-020 shape: 'en çok adet satılan ürün' — a DIFFERENT metric
    (SUM(quantity), not SUM(line_total)) grouped by product, top-1."""
    ids = seed_total_revenue_slice(store, tenant_id="default", datasource_id="bi_reporting", published=True)
    assert "quantity_metric_id" in ids
    result = compile_metric_sql(
        store,
        tenant_id="default",
        datasource_id="bi_reporting",
        metric_code="total_quantity_sold",
        group_by=["product_name"],
        limit=1,
    )
    assert 'SUM(COALESCE(v."quantity", 0))' in result["sql"]
    assert '"product_name"' in result["sql"]
    assert "LIMIT 1" in result["sql"]
    # Must not be confused with the revenue metric's column.
    assert "line_total" not in result["sql"]


def test_group_by_rejects_non_identifier_column(store):
    """Defense in depth: even though the only real caller is the resolver's
    hardcoded dimension->column map, group_by must reject anything that
    isn't a plain identifier (the compiler's only other injection guard)."""
    seed_total_revenue_slice(store, tenant_id="default", datasource_id="bi_reporting", published=True)
    with pytest.raises(Exception):
        compile_metric_sql(
            store,
            tenant_id="default",
            datasource_id="bi_reporting",
            metric_code="total_revenue",
            group_by=["segment; DROP TABLE customers"],
        )
