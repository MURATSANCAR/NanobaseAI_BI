"""Vertical slice seed: total_revenue + completed_orders_only + business term.

Mirrors seed_unpaid_slice.py's pattern (the accepted way to bootstrap a
hand-verified metric straight to PUBLISHED, ahead of the multi-reviewer
promotion workflow used for later changes).

Why this exists: "ciro nedir" (bare aggregate, no dimension/ranking) was the
one Text2SQL case the local LLM answered inconsistently — sometimes summing
sales_order_items correctly, sometimes reading analytics.invoices.gross_amount
(a different business figure), and not always restricting to completed
orders. Publishing it as a semantic metric makes that ONE question pattern
100% deterministic — the LLM is never asked, so there is no variance to chase.
It does not cover dimensional breakdowns ("segmentlere göre ciro") or ranked
lists ("ilk 3 müşteri") — MetricCompiler only compiles a single scalar
aggregate; those stay on the LLM path (see planning_guidance.py's explicit
completed-orders-only instruction for that path).

Depends on the analytics.v_sales_revenue_lines / public.v_sales_revenue_lines
views (infra/sql/09-sales-revenue-lines-view.sql) that expose a precomputed
quantity*unit_price line_total alongside the owning order's status — Metric
source must be a plain column, not an arbitrary expression.
"""

from __future__ import annotations

import uuid

from nanobase_api.semantic_catalog.domain.business_term import BusinessTerm
from nanobase_api.semantic_catalog.domain.filter_rule import FilterExpression, FilterRule
from nanobase_api.semantic_catalog.domain.metric import Metric, SourceExpression, TimeSemantics
from nanobase_api.semantic_catalog.domain.status import AssetStatus
from nanobase_api.semantic_catalog.infrastructure.catalog_store import CatalogStore


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def seed_total_revenue_slice(
    store: CatalogStore,
    *,
    tenant_id: str = "default",
    datasource_id: str = "bi_reporting",
    published: bool = False,
) -> dict[str, str]:
    status = AssetStatus.PUBLISHED if published else AssetStatus.DRAFT

    term = BusinessTerm(
        id=_id("bt"),
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        name="Ciro",
        description="Tamamlanmış satış siparişlerinden elde edilen toplam satış geliri.",
        synonyms=["satış geliri", "satis geliri", "toplam satış", "toplam satis", "revenue"],
        status=status,
    )
    store.save_term(term)

    filt = FilterRule(
        id=_id("fr"),
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        code="completed_orders_only",
        description=(
            "Yalnızca tamamlanmış (completed) siparişleri içerir; beklemede, "
            "iptal edilmiş veya iade edilmiş siparişler ciroya dahil edilmez."
        ),
        expression=FilterExpression(
            field="public.v_sales_revenue_lines.status",
            operator="=",
            values=["completed"],
        ),
        mandatory=True,
        status=status,
    )
    store.save_filter(filt)

    metric = Metric(
        id=_id("met"),
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        code="total_revenue",
        name="Toplam Ciro",
        description="Tamamlanmış siparişlerin satış geliri (miktar × birim fiyat toplamı).",
        aggregation="SUM",
        source=SourceExpression(table="public.v_sales_revenue_lines", column="line_total"),
        default_filter_codes=["completed_orders_only"],
        null_policy="ZERO",
        time=TimeSemantics(time_field="public.v_sales_revenue_lines.order_date"),
        is_financial=False,
        status=status,
    )
    store.save_metric(metric)

    return {"term_id": term.id, "filter_id": filt.id, "metric_id": metric.id}
