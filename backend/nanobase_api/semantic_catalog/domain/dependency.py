"""Dependency graph + conflict detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from nanobase_api.semantic_catalog.domain.errors import ConflictError, ValidationError
from nanobase_api.semantic_catalog.domain.normalize import normalize_synonym


class DependencyKind(str, Enum):
    TABLE = "TABLE"
    COLUMN = "COLUMN"
    FILTER = "FILTER"
    DIMENSION = "DIMENSION"
    JOIN = "JOIN"
    CURRENCY_POLICY = "CURRENCY_POLICY"
    METRIC = "METRIC"
    BUSINESS_TERM = "BUSINESS_TERM"


@dataclass(frozen=True)
class DependencyEdge:
    from_type: str
    from_code: str
    to_kind: DependencyKind
    to_ref: str

    def key(self) -> tuple[str, str, str, str]:
        return (self.from_type, self.from_code, self.to_kind.value, self.to_ref)


@dataclass
class DependencyGraph:
    edges: list[DependencyEdge] = field(default_factory=list)

    def add(self, edge: DependencyEdge) -> None:
        if edge.key() not in {e.key() for e in self.edges}:
            self.edges.append(edge)

    def dependents_of(self, kind: DependencyKind, ref: str) -> list[DependencyEdge]:
        return [e for e in self.edges if e.to_kind == kind and e.to_ref == ref]

    def edges_from(self, from_type: str, from_code: str) -> list[DependencyEdge]:
        return [e for e in self.edges if e.from_type == from_type and e.from_code == from_code]

    def has_cycle(self) -> bool:
        """Cycle detection among METRIC→METRIC and JOIN path nodes."""
        adj: dict[str, set[str]] = {}
        for e in self.edges:
            if e.to_kind in (DependencyKind.METRIC, DependencyKind.JOIN, DependencyKind.DIMENSION):
                src = f"{e.from_type}:{e.from_code}"
                dst = f"{e.to_kind.value}:{e.to_ref}"
                adj.setdefault(src, set()).add(dst)
                adj.setdefault(dst, set())

        visiting: set[str] = set()
        visited: set[str] = set()

        def dfs(n: str) -> bool:
            if n in visiting:
                return True
            if n in visited:
                return False
            visiting.add(n)
            for m in adj.get(n, ()):
                if dfs(m):
                    return True
            visiting.remove(n)
            visited.add(n)
            return False

        return any(dfs(n) for n in list(adj.keys()))

    def assert_acyclic(self) -> None:
        if self.has_cycle():
            raise ValidationError("Circular dependency tespit edildi.")


@dataclass
class ConflictReport:
    conflicts: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.conflicts

    def raise_if_any(self) -> None:
        if self.conflicts:
            raise ConflictError("; ".join(self.conflicts))


def detect_synonym_conflicts(
    metric_synonyms: dict[str, Iterable[str]],
) -> ConflictReport:
    """Same synonym must not map to two different metrics."""
    report = ConflictReport()
    owner: dict[str, str] = {}
    for metric_code, syns in metric_synonyms.items():
        for s in syns:
            key = normalize_synonym(s)
            if not key:
                continue
            if key in owner and owner[key] != metric_code:
                report.conflicts.append(
                    f"Synonym '{s}' hem {owner[key]} hem {metric_code} metric'ine bağlı"
                )
            else:
                owner[key] = metric_code
    return report


def detect_join_conflicts(joins: list[dict[str, Any]]) -> ConflictReport:
    """Conflicting join rules for the same table pair."""
    report = ConflictReport()
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for j in joins:
        pair = (j["fromTable"], j["toTable"])
        if pair in seen:
            prev = seen[pair]
            if prev.get("conditions") != j.get("conditions") or prev.get("joinType") != j.get("joinType"):
                report.conflicts.append(
                    f"Çelişkili join rule: {pair[0]} → {pair[1]} ({prev.get('code')} vs {j.get('code')})"
                )
        else:
            seen[pair] = j
    return report


def detect_stale_schema_refs(
    *,
    referenced_columns: Iterable[str],
    existing_columns: set[str],
) -> ConflictReport:
    report = ConflictReport()
    for col in referenced_columns:
        if col not in existing_columns:
            report.conflicts.append(f"Stale schema reference: {col}")
    return report
