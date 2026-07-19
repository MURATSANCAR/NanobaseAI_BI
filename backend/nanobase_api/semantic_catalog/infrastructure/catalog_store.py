"""Catalog store — in-memory with optional PostgreSQL write-through (sc_* tables)."""

from __future__ import annotations

import logging
import os
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

logger = logging.getLogger(__name__)


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@dataclass
class CatalogStore:
    """Thread-safe catalog. When sql_repo is set, mutations persist to sc_* tables."""

    business_terms: dict[str, BusinessTerm] = field(default_factory=dict)
    metrics: dict[str, Metric] = field(default_factory=dict)
    filters: dict[str, FilterRule] = field(default_factory=dict)
    joins: dict[str, JoinRule] = field(default_factory=dict)
    candidates: dict[str, VerifiedQueryCandidate] = field(default_factory=dict)
    verified_queries: dict[str, VerifiedQuery] = field(default_factory=dict)
    promotions: dict[str, PromotionRequest] = field(default_factory=dict)
    versions: dict[str, SemanticVersion] = field(default_factory=dict)
    active_version: dict[tuple[str, str], str] = field(default_factory=dict)
    sql_repo: Any | None = field(default=None, repr=False)
    backend: str = "memory"
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def _persist(self, kind: str, entity: Any) -> None:
        if self.sql_repo is None:
            return
        try:
            if kind == "metric":
                self.sql_repo.upsert_metric(entity)
            elif kind == "filter":
                self.sql_repo.upsert_filter(entity)
            elif kind == "term":
                self.sql_repo.upsert_term(entity)
            elif kind == "candidate":
                self.sql_repo.upsert_candidate(entity)
            elif kind == "verified":
                self.sql_repo.upsert_verified_query(entity)
            elif kind == "promotion":
                self.sql_repo.upsert_promotion(entity)
            elif kind == "version":
                self.sql_repo.upsert_version(entity)
        except Exception:
            logger.exception("semantic catalog SQL persist failed kind=%s", kind)
            raise

    def save_term(self, term: BusinessTerm) -> BusinessTerm:
        with self._lock:
            self.business_terms[term.id] = term
            self._persist("term", term)
            return term

    def save_metric(self, metric: Metric) -> Metric:
        with self._lock:
            self.metrics[metric.id] = metric
            self._persist("metric", metric)
            return metric

    def save_filter(self, fr: FilterRule) -> FilterRule:
        with self._lock:
            self.filters[fr.id] = fr
            self._persist("filter", fr)
            return fr

    def save_candidate(self, cand: VerifiedQueryCandidate) -> VerifiedQueryCandidate:
        with self._lock:
            self.candidates[cand.id] = cand
            self._persist("candidate", cand)
            return cand

    def save_verified_query(self, vq: VerifiedQuery) -> VerifiedQuery:
        with self._lock:
            self.verified_queries[vq.id] = vq
            self._persist("verified", vq)
            return vq

    def save_promotion(self, promo: PromotionRequest) -> PromotionRequest:
        with self._lock:
            self.promotions[promo.id] = promo
            self._persist("promotion", promo)
            return promo

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
                if (
                    column_ref in refs
                    or column_ref.endswith("." + m.source.column)
                    or m.source.qualified == column_ref
                ):
                    m.status = AssetStatus.STALE
                    self._persist("metric", m)
                    affected.append(m.code)
            for vq in self.verified_queries.values():
                if vq.tenant_id != tenant_id or vq.datasource_id != datasource_id:
                    continue
                metric_code = (vq.logical_plan or {}).get("metric")
                if metric_code in affected and vq.status == AssetStatus.PUBLISHED:
                    vq.status = AssetStatus.STALE
                    self._persist("verified", vq)
        return affected

    def set_active_version(self, version: SemanticVersion) -> None:
        with self._lock:
            for v in self.versions.values():
                if v.tenant_id == version.tenant_id and v.datasource_id == version.datasource_id:
                    if v.is_active and v.id != version.id:
                        v.is_active = False
                        self._persist("version", v)
            version.is_active = True
            version.status = AssetStatus.PUBLISHED
            self.versions[version.id] = version
            self.active_version[(version.tenant_id, version.datasource_id)] = version.id
            self._persist("version", version)

    def get_active_version(self, tenant_id: str, datasource_id: str) -> SemanticVersion | None:
        with self._lock:
            vid = self.active_version.get((tenant_id, datasource_id))
            return self.versions.get(vid) if vid else None

    def hydrate_from_sql(self) -> None:
        if self.sql_repo is None:
            return
        data = self.sql_repo.hydrate_store_dicts()
        with self._lock:
            self.metrics = data["metrics"]
            self.filters = data["filters"]
            self.business_terms = data["business_terms"]
            self.candidates = data["candidates"]
            self.verified_queries = data["verified_queries"]
            self.promotions = data["promotions"]
            self.versions = data["versions"]
            self.active_version = data["active_version"]
            self.backend = "sql"


_GLOBAL_STORE: CatalogStore | None = None


def _want_sql_backend() -> bool:
    mode = os.environ.get("SEMANTIC_CATALOG_BACKEND", "auto").lower()
    if mode == "memory":
        return False
    if mode == "sql":
        return True
    # auto: use SQL when tables exist
    return True


def get_catalog_store() -> CatalogStore:
    global _GLOBAL_STORE
    if _GLOBAL_STORE is not None:
        return _GLOBAL_STORE

    store = CatalogStore()
    if _want_sql_backend():
        try:
            from nanobase_api.db import get_sync_engine
            from nanobase_api.semantic_catalog.infrastructure.repositories.sql_catalog_repo import (
                SqlCatalogRepository,
            )

            repo = SqlCatalogRepository(get_sync_engine())
            if repo.tables_ready():
                store.sql_repo = repo
                store.hydrate_from_sql()
                logger.info("semantic catalog backend=sql (hydrated from sc_*)")
            else:
                logger.warning(
                    "semantic catalog sc_* tables missing — using memory until alembic 002-009 applied"
                )
        except Exception:
            logger.exception("semantic catalog SQL init failed — falling back to memory")
    _GLOBAL_STORE = store
    return _GLOBAL_STORE


def reset_catalog_store(*, backend: str = "memory") -> CatalogStore:
    """Reset global store (tests always use memory unless backend=sql explicitly)."""
    global _GLOBAL_STORE
    store = CatalogStore(backend=backend)
    if backend == "sql":
        from nanobase_api.db import get_sync_engine
        from nanobase_api.semantic_catalog.infrastructure.repositories.sql_catalog_repo import (
            SqlCatalogRepository,
        )

        repo = SqlCatalogRepository(get_sync_engine())
        store.sql_repo = repo
        if repo.tables_ready():
            store.hydrate_from_sql()
    _GLOBAL_STORE = store
    return _GLOBAL_STORE
