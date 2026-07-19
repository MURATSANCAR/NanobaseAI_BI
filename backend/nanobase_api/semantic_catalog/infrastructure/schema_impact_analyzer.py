"""Schema impact analyzer — diff → dependency → STALE."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from nanobase_api.semantic_catalog.domain.dependency import DependencyEdge, DependencyGraph, DependencyKind
from nanobase_api.semantic_catalog.domain.status import AssetStatus
from nanobase_api.semantic_catalog.infrastructure.catalog_store import CatalogStore


class DiffKind(str, Enum):
    TABLE_ADDED = "TABLE_ADDED"
    TABLE_REMOVED = "TABLE_REMOVED"
    COLUMN_ADDED = "COLUMN_ADDED"
    COLUMN_REMOVED = "COLUMN_REMOVED"
    COLUMN_RENAMED = "COLUMN_RENAMED"
    TYPE_CHANGED = "TYPE_CHANGED"
    NULLABILITY_CHANGED = "NULLABILITY_CHANGED"
    FK_CHANGED = "FK_CHANGED"
    VIEW_CHANGED = "VIEW_CHANGED"
    COMMENT_CHANGED = "COMMENT_CHANGED"


class ImpactLevel(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


_IMPACT = {
    DiffKind.COMMENT_CHANGED: ImpactLevel.NONE,
    DiffKind.COLUMN_ADDED: ImpactLevel.LOW,
    DiffKind.TABLE_ADDED: ImpactLevel.LOW,
    DiffKind.NULLABILITY_CHANGED: ImpactLevel.MEDIUM,
    DiffKind.TYPE_CHANGED: ImpactLevel.HIGH,
    DiffKind.COLUMN_RENAMED: ImpactLevel.CRITICAL,
    DiffKind.COLUMN_REMOVED: ImpactLevel.CRITICAL,
    DiffKind.TABLE_REMOVED: ImpactLevel.CRITICAL,
    DiffKind.FK_CHANGED: ImpactLevel.HIGH,
    DiffKind.VIEW_CHANGED: ImpactLevel.HIGH,
}


@dataclass
class SchemaDiff:
    kind: DiffKind
    ref: str  # table or table.column
    detail: str = ""

    @property
    def impact(self) -> ImpactLevel:
        return _IMPACT.get(self.kind, ImpactLevel.MEDIUM)


@dataclass
class ImpactReport:
    diffs: list[SchemaDiff] = field(default_factory=list)
    stale_assets: list[str] = field(default_factory=list)
    locked: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "diffs": [{"kind": d.kind.value, "ref": d.ref, "impact": d.impact.value, "detail": d.detail} for d in self.diffs],
            "staleAssets": self.stale_assets,
            "locked": self.locked,
            "error": self.error,
        }


def diff_schemas(old: dict[str, Any], new: dict[str, Any]) -> list[SchemaDiff]:
    """old/new: { "schema.table": { "columns": { "col": {"type": "...", "nullable": bool, "comment": "..."} } } }"""
    diffs: list[SchemaDiff] = []
    old_tables = set(old.keys())
    new_tables = set(new.keys())
    for t in sorted(old_tables - new_tables):
        diffs.append(SchemaDiff(DiffKind.TABLE_REMOVED, t))
    for t in sorted(new_tables - old_tables):
        diffs.append(SchemaDiff(DiffKind.TABLE_ADDED, t))
    for t in sorted(old_tables & new_tables):
        oc = (old[t] or {}).get("columns") or {}
        nc = (new[t] or {}).get("columns") or {}
        for c in sorted(set(oc) - set(nc)):
            diffs.append(SchemaDiff(DiffKind.COLUMN_REMOVED, f"{t}.{c}"))
        for c in sorted(set(nc) - set(oc)):
            diffs.append(SchemaDiff(DiffKind.COLUMN_ADDED, f"{t}.{c}"))
        for c in sorted(set(oc) & set(nc)):
            if (oc[c] or {}).get("type") != (nc[c] or {}).get("type"):
                diffs.append(SchemaDiff(DiffKind.TYPE_CHANGED, f"{t}.{c}"))
            if (oc[c] or {}).get("nullable") != (nc[c] or {}).get("nullable"):
                diffs.append(SchemaDiff(DiffKind.NULLABILITY_CHANGED, f"{t}.{c}"))
            if (oc[c] or {}).get("comment") != (nc[c] or {}).get("comment"):
                diffs.append(SchemaDiff(DiffKind.COMMENT_CHANGED, f"{t}.{c}"))
    return diffs


def build_metric_dependency_graph(store: CatalogStore, tenant_id: str, datasource_id: str) -> DependencyGraph:
    g = DependencyGraph()
    for m in store.metrics.values():
        if m.tenant_id != tenant_id or m.datasource_id != datasource_id:
            continue
        g.add(DependencyEdge("METRIC", m.code, DependencyKind.TABLE, m.source.table))
        g.add(DependencyEdge("METRIC", m.code, DependencyKind.COLUMN, m.source.qualified))
        if m.time:
            g.add(DependencyEdge("METRIC", m.code, DependencyKind.COLUMN, m.time.time_field))
        for fc in m.default_filter_codes:
            g.add(DependencyEdge("METRIC", m.code, DependencyKind.FILTER, fc))
    return g


def apply_schema_impact(
    store: CatalogStore,
    *,
    tenant_id: str,
    datasource_id: str,
    old_schema: dict[str, Any],
    new_schema: dict[str, Any],
    publish_lock_held: bool = False,
) -> ImpactReport:
    if publish_lock_held:
        return ImpactReport(locked=True, error="SCHEMA_VERSION_CONFLICT")

    diffs = diff_schemas(old_schema, new_schema)
    report = ImpactReport(diffs=diffs)
    graph = build_metric_dependency_graph(store, tenant_id, datasource_id)

    for d in diffs:
        if d.impact in (ImpactLevel.NONE, ImpactLevel.LOW):
            continue
        # Find dependents
        if d.kind in (DiffKind.COLUMN_REMOVED, DiffKind.COLUMN_RENAMED, DiffKind.TYPE_CHANGED):
            for edge in graph.dependents_of(DependencyKind.COLUMN, d.ref):
                code = edge.from_code
                m = store.get_metric_by_code(tenant_id, datasource_id, code)
                if m and m.status == AssetStatus.PUBLISHED:
                    m.status = AssetStatus.STALE
                    store.save_metric(m)
                    report.stale_assets.append(f"METRIC:{code}")
            # also direct mark
            affected = store.mark_stale_by_column(tenant_id, datasource_id, d.ref)
            for code in affected:
                key = f"METRIC:{code}"
                if key not in report.stale_assets:
                    report.stale_assets.append(key)
        if d.kind == DiffKind.TABLE_REMOVED:
            for edge in graph.dependents_of(DependencyKind.TABLE, d.ref):
                m = store.get_metric_by_code(tenant_id, datasource_id, edge.from_code)
                if m and m.status == AssetStatus.PUBLISHED:
                    m.status = AssetStatus.STALE
                    store.save_metric(m)
                    report.stale_assets.append(f"METRIC:{edge.from_code}")
    return report
