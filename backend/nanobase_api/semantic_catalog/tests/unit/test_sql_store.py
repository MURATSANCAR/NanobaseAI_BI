"""Unit tests for SQL write-through catalog store."""

from __future__ import annotations

from nanobase_api.semantic_catalog.application.seed_unpaid_slice import seed_unpaid_invoice_slice
from nanobase_api.semantic_catalog.domain.status import AssetStatus
from nanobase_api.semantic_catalog.infrastructure.catalog_store import CatalogStore, reset_catalog_store


class FakeSqlRepo:
    def __init__(self) -> None:
        self.metrics: list = []
        self.filters: list = []
        self.terms: list = []
        self.versions: list = []

    def upsert_metric(self, m) -> None:
        self.metrics.append(m.code)

    def upsert_filter(self, f) -> None:
        self.filters.append(f.code)

    def upsert_term(self, t) -> None:
        self.terms.append(t.normalized_name)

    def upsert_version(self, v) -> None:
        self.versions.append(v.version)

    def tables_ready(self) -> bool:
        return True

    def hydrate_store_dicts(self) -> dict:
        return {
            "metrics": {},
            "filters": {},
            "business_terms": {},
            "candidates": {},
            "verified_queries": {},
            "promotions": {},
            "versions": {},
            "active_version": {},
        }


def test_sql_write_through_on_seed():
    store = reset_catalog_store()
    fake = FakeSqlRepo()
    store.sql_repo = fake
    store.backend = "sql"
    seed_unpaid_invoice_slice(store, published=True)
    assert "unpaid_invoice_amount" in fake.metrics
    assert "exclude_cancelled_invoices" in fake.filters
    assert "odenmemis_fatura" in fake.terms


def test_stale_persists_via_sql():
    store = CatalogStore()
    fake = FakeSqlRepo()
    store.sql_repo = fake
    ids = seed_unpaid_invoice_slice(store, published=True)
    fake.metrics.clear()
    store.mark_stale_by_column("default", "default", "reporting.invoice.remaining_amount")
    assert store.metrics[ids["metric_id"]].status == AssetStatus.STALE
    assert "unpaid_invoice_amount" in fake.metrics
