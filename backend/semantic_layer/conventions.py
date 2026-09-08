"""Schema conventions discovered from the profile — the replacement for hardcoded column lists.

Every question the miner, the doc miner, the resolver and the compiler used to answer with a
customer-specific constant ("is this code column a metric scope?", "which column is the date?",
"where does this key point?") is answered here from profiled facts plus mined evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional
from pathlib import Path
import re

from semantic_layer.models import ColumnProfile, SchemaProfile

# A flag is a boolean-shaped column (0/1, Y/N, true/false): eligible as a default filter.
FLAG_VALUES = frozenset({"0", "1", "-1", "Y", "N", "T", "F", "E", "H", "TRUE", "FALSE", "YES", "NO", "", "NULL"})
FLAG_MAX_DISTINCT = 2
# Any other low-cardinality enum is a business *type* code: it scopes a metric, never a default.
SCOPE_MAX_DISTINCT = 64
_TIME_TYPES = ("date", "time", "timestamp", "datetime", "smalldatetime")
_NUMERIC_TYPES = ("int", "float", "double", "decimal", "numeric", "real", "money", "bigint", "smallint", "tinyint")


@dataclass
class Conventions:
    entities: list[str] = field(default_factory=list)
    columns: dict[str, set[str]] = field(default_factory=dict)
    enum_columns: dict[str, set[str]] = field(default_factory=dict)     # 3..64 distinct → metric scope
    flag_columns: dict[str, set[str]] = field(default_factory=dict)     # ≤ 2 distinct  → default filter
    time_columns: dict[str, list[str]] = field(default_factory=dict)
    numeric_columns: dict[str, set[str]] = field(default_factory=dict)
    sensitive_columns: dict[str, set[str]] = field(default_factory=dict)
    sentinels: dict[tuple[str, str], set[str]] = field(default_factory=dict)
    key_columns: dict[str, list[str]] = field(default_factory=dict)
    ref_columns: dict[str, dict[str, tuple[str, str]]] = field(default_factory=dict)
    row_counts: dict[str, int] = field(default_factory=dict)
    patterns: dict[str, str] = field(default_factory=dict)
    time_hint: dict[str, str] = field(default_factory=dict)             # evidence-preferred time column

    absence_rules: list[dict] = field(default_factory=list)
    filter_equivalences: list[dict] = field(default_factory=list)
    time_equivalences: list[dict] = field(default_factory=list)  # knowledge-pack declarations, never inferred from a join

    # ------------------------------------------------------------------ construction
    @classmethod
    def from_profiles(cls, profiles: Iterable[SchemaProfile]) -> "Conventions":
        c = cls()
        for p in profiles:
            c.entities.append(p.entity)
            c.patterns[p.entity] = p.table_pattern
            cols = {col.name.upper() for col in p.columns}
            c.columns[p.entity] = cols
            c.key_columns[p.entity] = list(p.primary_key)
            if p.row_count is not None:
                c.row_counts[p.entity] = int(p.row_count)
            enums, flags, times, numerics, sensitive = set(), set(), [], set(), set()
            for col in p.columns:
                name = col.name.upper()
                if col.sensitive:
                    sensitive.add(name)
                if col.sentinel_values:
                    c.sentinels[(p.entity, name)] = set(col.sentinel_values)
                if is_time(col):
                    times.append(name)
                if is_numeric(col) and not col.is_primary_key and not col.ref_entity:
                    numerics.add(name)
                distinct = col.distinct_count or (len(col.top_values) if col.top_values else None)
                if distinct is not None and col.top_values and not col.is_primary_key and not col.ref_entity and not col.sensitive:
                    values = {str(v).strip().upper() for v, _ in col.top_values}
                    if distinct <= FLAG_MAX_DISTINCT and values <= FLAG_VALUES:
                        flags.add(name)
                    elif distinct <= SCOPE_MAX_DISTINCT:
                        enums.add(name)
            c.enum_columns[p.entity] = enums
            c.sensitive_columns[p.entity] = sensitive
            c.flag_columns[p.entity] = flags
            c.time_columns[p.entity] = times
            c.numeric_columns[p.entity] = numerics
            c.ref_columns[p.entity] = {r["column"].upper(): (r["ref_entity"], r["ref_column"]) for r in p.relationships}
        return c

    # ------------------------------------------------------------------ queries
    def has(self, entity: str, column: str) -> bool:
        return column.upper() in self.columns.get(entity, set())

    def owners(self, column: str) -> list[str]:
        col = column.upper()
        return [e for e in self.entities if col in self.columns.get(e, set())]

    def is_sensitive(self, entity: Optional[str], column: str) -> bool:
        col = column.upper()
        entities = [entity] if entity else self.entities
        return any(col in self.sensitive_columns.get(e, set()) for e in entities if e)

    def sentinel_values(self, entity: str, column: str) -> set[str]:
        return self.sentinels.get((entity, column.upper()), set())

    def is_scope_column(self, entity: Optional[str], column: str) -> bool:
        """Business type code (enum with ≥3 values): belongs to a metric's scope, not to defaults."""
        col = column.upper()
        entities = [entity] if entity else self.entities
        return any(col in self.enum_columns.get(e, set()) for e in entities if e)

    def is_flag_column(self, entity: Optional[str], column: str) -> bool:
        col = column.upper()
        entities = [entity] if entity else self.entities
        return any(col in self.flag_columns.get(e, set()) for e in entities if e)

    def time_column(self, entity: str) -> Optional[str]:
        """Default business date; record-maintenance timestamps do not qualify."""
        times = [col for col in self.time_columns.get(entity, []) if not is_technical_time(col)]
        hint = self.time_hint.get(entity)
        if hint and hint.upper() in times:
            return hint.upper()
        return times[0] if times else None

    def load_equivalences(self, path: Path) -> None:
        """Load explicit business-date equivalences, bound to a profiled FK.

        A relationship alone does not equate dates (an order and its invoice may
        have different dates). Only this datasource's declared rules do so.
        """
        import yaml
        self.time_equivalences = []
        self.filter_equivalences = []
        if not path.exists():
            return
        declarations = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        self.absence_rules = []
        for rule in declarations.get("absence_queries", []):
            if all(self.join_path(j[0], j[2]) == tuple(j) for j in rule["joins"]) and all(
                    self.has(e, c) for e, cols in rule["columns"].items() for c in cols):
                self.absence_rules.append(rule)
        for rule in declarations.get("equivalent_dates", []):
            left, right = rule["left"], rule["right"]
            join = tuple(rule["join"])
            if len(join) != 4 or not rule.get("reason"):
                raise ValueError("time equivalence requires a join and a reason")
            if self.join_path(left["entity"], right["entity"]) != join:
                continue  # this deployment does not contain the declared relationship
            if not all(self.time_column(side["entity"]) == side["column"].upper() for side in (left, right)):
                continue
            self.time_equivalences.append(rule)
        for rule in declarations.get("equivalent_filters", []):
            left, right = rule["left"], rule["right"]
            if not rule.get("reason") or not rule.get("values"):
                raise ValueError("filter equivalence requires values and a reason")
            if self.join_path(left["entity"], right["entity"]) != tuple(rule["join"]):
                continue
            if all(self.has(side["entity"], side["column"]) for side in (left, right)):
                self.filter_equivalences.append(rule)

    def filter_bindings(self, mapping) -> list[dict]:
        out = []
        for rule in self.filter_equivalences:
            if (mapping.operator or "IN").upper() != rule["operator"].upper():
                continue
            if {str(v) for v in mapping.values} != {str(v) for v in rule["values"]}:
                continue
            for own, other in ((rule["left"], rule["right"]), (rule["right"], rule["left"])):
                if own["entity"] == mapping.entity and own["column"].upper() == mapping.column.upper():
                    out.append({"entity": other["entity"], "column": other["column"].upper(),
                                "operator": rule["operator"], "values": [str(v) for v in rule["values"]],
                                "join": list(rule["join"]), "source": "declared_business_filter", "reason": rule["reason"]})
        return out


    def temporal_binding(self, entity: str) -> Optional[dict]:
        column = self.time_column(entity)
        if not column:
            return None
        out = {"entity": entity, "column": column, "source": "resolved_metric", "alternatives": []}
        for rule in self.time_equivalences:
            for own, other in ((rule["left"], rule["right"]), (rule["right"], rule["left"])):
                if own["entity"] == entity and own["column"].upper() == column:
                    out["alternatives"].append({"entity": other["entity"], "column": other["column"].upper(),
                                                "join": list(rule["join"]), "source": "declared_business_date",
                                                "reason": rule["reason"]})
        return out

    def join_path(self, entity: str, other: str) -> Optional[tuple[str, str, str, str]]:
        for col, (ref_entity, ref_col) in self.ref_columns.get(entity, {}).items():
            if ref_entity == other:
                return (entity, col, other, ref_col)
        for col, (ref_entity, ref_col) in self.ref_columns.get(other, {}).items():
            if ref_entity == entity:
                return (other, col, entity, ref_col)
        return None

    def preferred_entity(self, candidates: list[str], *, hint: Optional[str] = None) -> Optional[str]:
        """Tie-break between entities owning the same column: an explicit hint first, then the
        entity with the fewest rows (a header table is smaller than its line table), then the
        entity referenced by the others, then declaration order."""
        cands = [e for e in candidates if e]
        if not cands:
            return None
        if hint in cands:
            return hint
        if len(cands) == 1:
            return cands[0]
        counted = [e for e in cands if e in self.row_counts]
        if len(counted) == len(cands):
            return min(cands, key=lambda e: self.row_counts[e])
        referenced = [e for e in cands if any(e == ref for other in cands if other != e for ref, _ in self.ref_columns.get(other, {}).values())]
        if len(referenced) == 1:
            return referenced[0]
        return cands[0]

    def learn_time_hint(self, bindings: Iterable[dict]) -> None:
        """Time column preference learned from validated SQL (which column the pairs actually filter)."""
        counts: dict[tuple[str, str], int] = {}
        for b in bindings:
            entity, column = b.get("entity"), b.get("column")
            if entity and column:
                counts[(entity, column.upper())] = counts.get((entity, column.upper()), 0) + 1
        for (entity, column), n in sorted(counts.items(), key=lambda kv: -kv[1]):
            self.time_hint.setdefault(entity, column)


def is_technical_time(column: str) -> bool:
    name = re.sub(r"[^A-Z0-9]", "", column.upper())
    return name.startswith("CAPIBLOCK") or name in {
        "CREATEDAT", "UPDATEDAT", "MODIFIEDAT", "DELETEDAT", "CREATEDDATE", "CREATIONDATE",
        "UPDATEDDATE", "MODIFIEDDATE", "LASTMODIFIED", "LASTUPDATED", "INSERTEDAT",
        "CREATETIME", "UPDATETIME", "MODIFYTIME",
    }


def is_time(col: ColumnProfile) -> bool:
    return any(t in (col.data_type or "").lower() for t in _TIME_TYPES)


def is_numeric(col: ColumnProfile) -> bool:
    return any(t in (col.data_type or "").lower() for t in _NUMERIC_TYPES)


def column_index(profiles: Iterable[SchemaProfile]) -> dict[str, set[str]]:
    return {p.entity: {c.name.upper() for c in p.columns} for p in profiles}
