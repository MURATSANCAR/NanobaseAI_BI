"""Vertical slice seed: unpaid_invoice_amount + exclude_cancelled + business term."""

from __future__ import annotations

from nanobase_api.semantic_catalog.domain.business_term import BusinessTerm
from nanobase_api.semantic_catalog.domain.filter_rule import FilterExpression, FilterRule
from nanobase_api.semantic_catalog.domain.metric import (
    CurrencySemantics,
    Metric,
    SourceExpression,
    TimeSemantics,
)
from nanobase_api.semantic_catalog.domain.status import AssetStatus
import uuid

from nanobase_api.semantic_catalog.infrastructure.catalog_store import CatalogStore


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def seed_unpaid_invoice_slice(
    store: CatalogStore,
    *,
    tenant_id: str = "default",
    datasource_id: str = "default",
    published: bool = False,
) -> dict[str, str]:
    """Create the first production vertical slice assets."""
    status = AssetStatus.PUBLISHED if published else AssetStatus.DRAFT

    term = BusinessTerm(
        id=_id("bt"),
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        name="Ödenmemiş Fatura",
        description="Vadesi gelmiş veya gelmemiş ancak tamamen tahsil edilmemiş fatura.",
        synonyms=["açık fatura", "ödenmeyen fatura", "kalan fatura"],
        status=status,
    )
    store.save_term(term)

    filt = FilterRule(
        id=_id("fr"),
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        code="exclude_cancelled_invoices",
        description="İptal ve hükümsüz faturaları dışarıda bırakır.",
        expression=FilterExpression(
            field="reporting.invoice.status",
            operator="NOT_IN",
            values=["CANCELLED", "VOID"],
        ),
        mandatory=True,
        status=status,
    )
    store.save_filter(filt)

    metric = Metric(
        id=_id("met"),
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        code="unpaid_invoice_amount",
        name="Ödenmemiş Fatura Tutarı",
        description="Faturalardaki kalan tahsil edilmemiş tutarın toplamı.",
        aggregation="SUM",
        source=SourceExpression(table="reporting.invoice", column="remaining_amount"),
        default_filter_codes=["exclude_cancelled_invoices"],
        null_policy="ZERO",
        time=TimeSemantics(time_field="reporting.invoice.invoice_date"),
        currency=CurrencySemantics(
            amount_field="reporting.invoice.remaining_amount",
            currency_field="reporting.invoice.currency_code",
            conversion_policy="DOCUMENT_CURRENCY",
        ),
        is_financial=True,
        multi_currency_datasource=False,
        status=status,
    )
    store.save_metric(metric)

    return {"term_id": term.id, "filter_id": filt.id, "metric_id": metric.id}
