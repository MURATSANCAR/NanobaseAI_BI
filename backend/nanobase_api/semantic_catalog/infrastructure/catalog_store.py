"""In-memory catalog store for tests and bootstrap without DB."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any

from nanobase_api.semantic_catalog.domain.business_term import BusinessTerm
from nanobase_api.semantic_catalog.domain.filter_rule import FilterRule
from nanobase_api.semantic_catalog.domain.join_rule import JoinRule
from nanobase_api.semantic_catalog.domain.metric import Metric
from nanobase_api.semantic_catalog.domain.promotion import PromotionRequest
from nanobase_api.semantic_catalog.domain.semantic_version import SemanticVersion
from nanobase_api.semantic_catalog.domain.status import AssetStatus
from nanobase_api.semantic_catalog.domain.verified_query import VerifiedQuery, VerifiedQueryCandidate


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@dataclass
class CatalogStore:
    """Thread-safe in-memory persistence (swap for SQL repos in production)."""

    business_terms: dict[str, BusinessTerm] = field(default_factory=dict)
    metrics: dict[str, Metric] = field(default_factory=dict)
    filters: dict[str, FilterRule] = field(default_factory=dict)
    joins: dict[str, JoinRule] = field(default_factory=dict)
    candidates: dict[str, VerifiedQueryCandidate] = field(default_factory=dict)
    verified_queries: dict[str, VerifiedQuery] = field(default_factory=dict)
    promotions: dict[str, PromotionRequest] = field(default_factory=dict)
    versions: dict[str, SemanticVersion] = field(default_factory=dict)
    active_version: dict[tuple[str, str], str] = field(default_factory=dict)  # (tenant, ds) -> version_id
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def save_term(self, term: BusinessTerm) -> BusinessTerm:
        with self._lock:
            self.business_terms[term.id] = term
            return term

    def save_metric(self, metric: Metric) -> Metric:
        with self._lock:
            self.metrics[metric.id] = metric
            return metric

    def save_filter(self, fr: FilterRule) -> FilterRule:
        with self._lock:
            self.filters[fr.id] = fr
            return fr

    def get_metric_by_code(self, tenant_id: str, datasource_id: str, code: str) -> Metric | None:
        with self._lock:
            for m in self.metrics.values():
                if m.tenant_id == tenant_id and m.datasource_id == datasource_id and m.code == code:
                    return m
            return None

    def list_published_metrics(self, tenant_id: str, datasource_id: str) -> list[Metric]:
        with self._lock:
            return [
                m
                for m in self.metrics.values()
                if m.tenant_id == tenant_id
                and m.datasource_id == datasource_id
                and m.status == AssetStatus.PUBLISHED
            ]

    def list_published_filters(self, tenant_id: str, datasource_id: str) -> list[FilterRule]:
        with self._lock:
            return [
                f
                for f in self.filters.values()
                if f.tenant_id == tenant_id
                and f.datasource_id == datasource_id
                and f.status == AssetStatus.PUBLISHED
            ]

    def list_published_terms(self, tenant_id: str, datasource_id: str) -> list[BusinessTerm]:
        with self._lock:
            return [
                t
                for t in self.business_terms.values()
                if t.tenant_id == tenant_id
                and t.datasource_id == datasource_id
                and t.status == AssetStatus.PUBLISHED
            ]

    def mark_stale_by_column(self, tenant_id: str, datasource_id: str, column_ref: str) -> list[str]:
        """Mark metrics referencing column as STALE. Returns affected codes."""
        affected: list[str] = []
        with self._lock:
            for m in self.metrics.values():
                if m.tenant_id != tenant_id or m.datasource_id != datasource_id:
                    continue
                if m.status != AssetStatus.PUBLISHED:
                    continue
                refs = {m.source.qualified}
                if m.time:
                    refs.add(m.time.time_field)
                if column_ref in refs or column_ref.endswith("." + m.source.column) or m.source.qualified == column_ref:
                    m.status = AssetStatus.STALE
                    affected.append(m.code)
            for vq in self.verified_queries.values():
                if vq.tenant_id != tenant_id or vq.datasource_id != datasource_id:
                    continue
                metric_code = (vq.logical_plan or {}).get("metric")
                if metric_code in affected and vq.status == AssetStatus.PUBLISHED:
                    vq.status = AssetStatus.STALE
        return affected

    def set_active_version(self, version: SemanticVersion) -> None:
        with self._lock:
            key = (version.tenant_id, version.datasource_id)
            # deactivate others
            for v in self.versions.values():
                if v.tenant_id == version.tenant_id and v.datasource_id == version.datasource_id:
                    v.is_active = False
            version.is_active = True
            version.status = AssetStatus.PUBLISHED
            self.versions[version.id] = version
            self.active_version[key] = version.id

    def get_active_version(self, tenant_id: str, datasource_id: str) -> SemanticVersion | None:
        with self._lock:
            vid = self.active_version.get((tenant_id, datasource_id))
            return self.versions.get(vid) if vid else None


_GLOBAL_STORE: CatalogStore | None = None


def get_catalog_store() -> CatalogStore:
    global _GLOBAL_STORE
    if _GLOBAL_STORE is None:
        _GLOBAL_STORE = CatalogStore()
    return _GLOBAL_STORE


def reset_catalog_store() -> CatalogStore:
    global _GLOBAL_STORE
    _GLOBAL_STORE = CatalogStore()
    return _GLOBAL_STORE
