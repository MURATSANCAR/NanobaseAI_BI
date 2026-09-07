"""Discriminating probes — the step that turns a proposal into a measurement.

A candidate says "toptan means <code column> = 8". Documentation and query history can support that, but
neither proves the code behaves the way the term claims. A probe asks the database a question whose answer
distinguishes the hypothesis from its alternatives, and records the outcome as evidence:

    value exists and carries a material share of the data   → EXECUTION evidence (supports)
    value never occurs / occurs in a negligible slice       → counter-evidence (VALUE_MISMATCH)
    the metric compiles and returns a usable, non-empty row → EXECUTION evidence (supports)
    the metric errors or returns nothing at all             → counter-evidence (EXECUTION_FAILED)

Everything is bounded: one aggregate per (entity, column) shared by every candidate on that column, one
execution per certified metric, all guarded by the read-only guardrails and the connector's own limits.
Probes never write, never run without a connector, and never certify on their own — they add or remove
evidence, and the Evidence Engine still decides.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from semantic_layer.models import (
    Concept,
    ConceptStatus,
    CounterEvidence,
    Evidence,
    EvidenceType,
    Mapping,
    SchemaProfile,
    SemanticType,
)
from semantic_layer.naming import physical_name
from semantic_layer.runtime.compiler import Dialect
from semantic_layer.runtime.guardrails import validate_sql

log = logging.getLogger(__name__)

# A code that covers less of the table than this is not what a business term refers to.
MIN_SHARE = 0.0005


@dataclass
class ProbeReport:
    distributions: int = 0
    values_confirmed: int = 0
    values_rejected: int = 0
    metrics_executed: int = 0
    metrics_failed: int = 0
    reconciliations: list[dict[str, Any]] = field(default_factory=list)
    freshness: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "distributions": self.distributions,
            "values_confirmed": self.values_confirmed,
            "values_rejected": self.values_rejected,
            "metrics_executed": self.metrics_executed,
            "metrics_failed": self.metrics_failed,
            "reconciliations": self.reconciliations,
            "freshness": self.freshness,
            "errors": self.errors[:5],
        }


#: how many sentinel-bearing columns of one table are checked for freshness in a single scan
MAX_FRESHNESS_COLUMNS = 40


class ValueProbe:
    """Measured share of every code in a column, cached per column so N candidates cost one query."""

    def __init__(self, connector: Any, profiles: list[SchemaProfile], context: Optional[dict[str, str]] = None, *, dialect: str = ""):
        self.c = connector
        self.by_entity = {p.entity: p for p in profiles}
        self.context = context or {}
        self.d = Dialect(dialect or getattr(connector, "dialect", "") or "generic")
        self._cache: dict[tuple[str, str], dict[str, float]] = {}

    #: how many distinct values a single distribution query asks for
    LIMIT = 128

    def distribution(self, entity: str, column: str) -> tuple[dict[str, float], bool]:
        """(value → share of rows, complete). `complete` is False when the answer was truncated, in which
        case a value's absence proves nothing — only a complete inventory can contradict a mapping."""
        key = (entity, column.upper())
        if key in self._cache:
            return self._cache[key]
        prof = self.by_entity.get(entity)
        self._cache[key] = ({}, False)
        if prof is None or prof.column(column) is None:
            return self._cache[key]
        col = prof.column(column)
        if col.sensitive:                       # personal data is never aggregated for the catalog
            return self._cache[key]
        table = physical_name(prof.table_pattern, {**prof.context, **self.context})
        try:
            pairs = self.c.top_values(prof.schema_name, table, col.name, self.LIMIT)
        except Exception as e:  # noqa: BLE001
            log.debug("distribution probe failed %s.%s: %s", entity, column, e)
            return self._cache[key]
        total = sum(n for _, n in pairs) or 0
        if total <= 0:
            return self._cache[key]
        complete = len(pairs) < self.LIMIT and all(n > 0 for _, n in pairs)
        self._cache[key] = ({str(v): n / total for v, n in pairs}, complete)
        return self._cache[key]


def probe_catalog(
    store: Any,
    tenant_id: str,
    datasource_id: str,
    profiles: list[SchemaProfile],
    connector: Any,
    *,
    context: Optional[dict[str, str]] = None,
    dialect: str = "",
    max_metrics: int = 25,
    budget_seconds: Optional[float] = None,
) -> ProbeReport:
    """Confront every value candidate with the data, and every certified metric with an execution.

    Each distribution is a GROUP BY over a whole table, so the pass gets a wall clock: past it, the
    remaining candidates keep the status they had and the report says how many were left unprobed. A
    probe that never finishes would hold back a catalog that is otherwise ready to serve."""
    report = ProbeReport()
    if connector is None:
        return report
    started = time.time()
    budget = budget_seconds if budget_seconds is not None else float(os.environ.get("SEMANTIC_PROBE_BUDGET_SEC", "900"))
    skipped = 0
    probe = ValueProbe(connector, profiles, context, dialect=dialect)
    by_entity = {p.entity: p for p in profiles}

    # --- value candidates: does this code actually occur, and does it carry data?
    for concept in store.find_concepts(tenant_id, datasource_id, semantic_type=SemanticType.DIMENSION_VALUE, limit=100000):
        if concept.status == ConceptStatus.REJECTED:
            continue
        if budget and time.time() - started > budget:
            skipped += 1
            continue
        for mapping in store.list_mappings(concept.id):
            if not mapping.column or not mapping.values:
                continue
            dist, complete = probe.distribution(mapping.entity, mapping.column)
            if not dist:
                continue
            report.distributions += 1
            share = sum(dist.get(str(v), 0.0) for v in mapping.values)
            missing = [str(v) for v in mapping.values if str(v) not in dist]
            payload = {"share": round(share, 6), "missing": missing, "complete": complete, "column": f"{mapping.entity}.{mapping.column}"}
            if missing and not complete:
                continue      # the inventory was truncated: absence here is not evidence of absence
            if missing or share < MIN_SHARE:
                store.add_counter_evidence(CounterEvidence(concept.id, f"probe:{mapping.entity}.{mapping.column}", "VALUE_MISMATCH", payload=payload | {"support": 2}, severity="BLOCKING" if missing else "MEDIUM"))
                report.values_rejected += 1
            else:
                store.clear_counter_evidence(concept.id, "VALUE_MISMATCH")
                store.add_evidence(Evidence(concept.id, EvidenceType.EXECUTION, f"probe:{mapping.entity}.{mapping.column}", support_count=1, weight=min(1.0, share * 4), payload=payload))
                report.values_confirmed += 1

    # --- certified metrics: compile the canonical form and run it once
    from semantic_layer.runtime.compiler import DeterministicCompiler, default_filters_provider
    from semantic_layer.models import ResolvedSlot, SemanticQuery

    compiler = DeterministicCompiler(profiles, context or {}, dialect or getattr(connector, "dialect", "") or "generic", default_filters=default_filters_provider(store, tenant_id, datasource_id))
    # Certified measures, and the ones a run of the probe itself knocked out: a concept rejected because
    # the database timed out once must have a way back, or a bad minute becomes a permanent verdict —
    # it is never probed again, so the evidence that would clear it can never be gathered.
    metrics = list(store.find_concepts(tenant_id, datasource_id, semantic_type=SemanticType.METRIC, status=ConceptStatus.CERTIFIED, limit=100000))
    seen_ids = {c.id for c in metrics}
    for c in store.find_concepts(tenant_id, datasource_id, semantic_type=SemanticType.METRIC, limit=100000):
        if c.id in seen_ids:
            continue
        blockers = store.list_counter_evidence(c.id)
        # whatever status it is sitting in, if the only thing against it is a run that did not complete,
        # it has to be run again — otherwise the score stays damped by an event nobody can retry
        if blockers and all(str(b.conflict_type).startswith("EXECUTION_") for b in blockers):
            metrics.append(c)
    metrics = metrics[:max_metrics]
    for concept in metrics:
        if budget and time.time() - started > budget:
            skipped += 1
            continue
        mapping = next(iter(store.list_mappings(concept.id)), None)
        if mapping is None or not mapping.formula or mapping.entity not in by_entity:
            continue
        query = SemanticQuery(question=concept.term, tenant_id=tenant_id, datasource_id=datasource_id)
        query.slots = [ResolvedSlot(term=concept.term, semantic_type=SemanticType.METRIC, status="CERTIFIED", concept_id=concept.id, mapping=mapping, explain={"normalized": concept.normalized_term})]
        compiled = compiler.compile(query, store)
        if compiled is None or not compiled.sql:
            continue
        ok, why = validate_sql(compiled.sql)
        if not ok:
            report.errors.append(f"{concept.term}: guardrail {why}")
            continue
        try:
            _, rows, _ = connector.execute(_physicalize(compiled.sql, profiles, context or {}, dialect or getattr(connector, "dialect", "")), 5)
        except Exception as e:  # noqa: BLE001
            from semantic_layer.runtime.guardrails import is_connection_error

            timed_out = "timeout" in str(e).lower() or "HYT00" in str(e)
            if timed_out or is_connection_error(e):
                # The measure could not be checked, which is not the same as failing the check. A
                # timeout is a statement about how much data there is, and a dropped connection about
                # the network; holding either against the definition would decertify correct knowledge
                # because a table grew.
                report.errors.append(f"{concept.term}: doğrulanamadı ({str(e)[:80]})")
                log.warning("metric probe could not run for %s: %s", concept.term, str(e)[:200])
                continue
            store.add_counter_evidence(CounterEvidence(concept.id, "probe:execute", "EXECUTION_FAILED", payload={"error": str(e)[:300], "support": 2}, severity="MEDIUM"))
            report.metrics_failed += 1
            report.errors.append(f"{concept.term}: {str(e)[:120]}")
            continue
        value = next((v for r in rows for v in r.values() if isinstance(v, (int, float))), None)
        if not rows or value is None:
            store.add_counter_evidence(CounterEvidence(concept.id, "probe:execute", "EXECUTION_EMPTY", payload={"rows": len(rows), "support": 1}, severity="LOW"))
            report.metrics_failed += 1
            continue
        store.clear_counter_evidence(concept.id, "EXECUTION_FAILED")
        store.clear_counter_evidence(concept.id, "EXECUTION_EMPTY")
        store.add_evidence(Evidence(concept.id, EvidenceType.EXECUTION, "probe:execute", support_count=1, weight=1.0, payload={"value": float(value), "rows": len(rows)}))
        report.metrics_executed += 1
    if skipped:
        # never a silent cap: an unprobed concept keeps the status it had, and the report says so
        note = f"probe budget ({budget:.0f}s) spent — {skipped} concepts left unprobed"
        log.warning(note)
        report.errors.append(note)
    log.info("probe: %d distributions, %d metrics executed, %d failed, %.0fs", report.distributions, report.metrics_executed, report.metrics_failed, time.time() - started)
    return report


def probe_all(store: Any, tenant_id: str, datasource_id: str, profiles: list[SchemaProfile], connector: Any, conventions: Any = None, *, context: Optional[dict[str, str]] = None, dialect: str = "") -> ProbeReport:
    """Every data-confronting step in one pass: values, metric executions, reconciliation, freshness."""
    report = probe_catalog(store, tenant_id, datasource_id, profiles, connector, context=context, dialect=dialect)
    try:
        report.reconciliations = reconcile_measures(store, tenant_id, datasource_id, profiles, connector, context=context, dialect=dialect)
    except Exception as e:  # noqa: BLE001
        report.errors.append(f"reconcile: {str(e)[:150]}")
    try:
        if conventions is not None:
            report.freshness = freshness(profiles, connector, conventions, context=context, dialect=dialect)
    except Exception as e:  # noqa: BLE001
        report.errors.append(f"freshness: {str(e)[:150]}")
    return report


def reconcile_measures(store: Any, tenant_id: str, datasource_id: str, profiles: list[SchemaProfile], connector: Any, *, context: Optional[dict[str, str]] = None, dialect: str = "", tolerance: float = 0.01) -> list[dict[str, Any]]:
    """Compare the same quantity as two related tables report it.

    Which pairs to compare is derived, not configured: whenever a certified metric on a parent entity and a
    certified metric on a child entity (the one holding the reference) aggregate numeric columns, their totals
    should agree. When they do not, that difference is a fact analysts must know — it is recorded as a caveat
    on both concepts instead of being discovered later in a meeting."""
    out: list[dict[str, Any]] = []
    if connector is None:
        return out
    by_entity = {p.entity: p for p in profiles}
    d = Dialect(dialect or getattr(connector, "dialect", "") or "generic")
    metrics: dict[str, list[tuple[Concept, Mapping]]] = {}
    for concept in store.find_concepts(tenant_id, datasource_id, semantic_type=SemanticType.METRIC, status=ConceptStatus.CERTIFIED, limit=100000):
        for mapping in store.list_mappings(concept.id):
            if mapping.formula and mapping.entity in by_entity:
                metrics.setdefault(mapping.entity, []).append((concept, mapping))
    for child, pairs in metrics.items():
        child_prof = by_entity[child]
        for rel in child_prof.relationships:
            parent = rel.get("ref_entity")
            if parent not in metrics or parent == child:
                continue
            for c_concept, c_map in pairs[:2]:
                for p_concept, p_map in metrics[parent][:2]:
                    if c_concept.normalized_term != p_concept.normalized_term:
                        continue          # only the *same business term* on both sides is comparable
                    totals = {}
                    for entity, mapping in ((parent, p_map), (child, c_map)):
                        prof = by_entity[entity]
                        table = physical_name(prof.table_pattern, {**prof.context, **(context or {})})
                        formula = _formula_sql(mapping.formula, d)
                        where = _scope_sql(mapping, d)
                        sql = f"SELECT {formula} AS total FROM {d.table(prof.schema_name, table)} AS {entity}" + (f" WHERE {where}" if where else "")
                        ok, _ = validate_sql(sql)
                        if not ok:
                            break
                        try:
                            _, rows, _ = connector.execute(sql, 1)
                        except Exception as e:  # noqa: BLE001
                            log.debug("reconcile failed %s: %s", entity, e)
                            break
                        value = next((v for r in rows for v in r.values() if isinstance(v, (int, float))), None)
                        if value is None:
                            break
                        totals[entity] = float(value)
                    if len(totals) == 2 and max(abs(v) for v in totals.values()) > 0:
                        diff = abs(totals[parent] - totals[child]) / max(abs(totals[parent]), abs(totals[child]))
                        entry = {"term": c_concept.term, "parent": parent, "child": child, "parent_total": totals[parent], "child_total": totals[child], "difference": round(diff, 4)}
                        out.append(entry)
                        if diff > tolerance:
                            for concept in (c_concept, p_concept):
                                store.update_concept(concept.id, explain={"reconciliation": entry})
                                store.add_counter_evidence(CounterEvidence(concept.id, f"reconcile:{parent}~{child}", "MEASURE_DISAGREEMENT", payload=entry | {"support": 1}, severity="LOW"))
    return out


def freshness(profiles: list[SchemaProfile], connector: Any, conventions: Any, *, context: Optional[dict[str, str]] = None, dialect: str = "") -> list[dict[str, Any]]:
    """How far a measure is actually populated. For every numeric column with an 'absent' marker, the last
    date where the column is populated is compared with the table's last date: the gap is the window in
    which any figure built on that column is incomplete."""
    out: list[dict[str, Any]] = []
    if connector is None:
        return out
    d = Dialect(dialect or getattr(connector, "dialect", "") or "generic")
    started = time.time()
    budget = float(os.environ.get("SEMANTIC_FRESHNESS_BUDGET_SEC", "300"))
    for prof in profiles:
        time_col = conventions.time_column(prof.entity) if conventions else None
        if not time_col:
            continue
        if budget and time.time() - started > budget:
            log.warning("freshness budget (%.0fs) spent; stopped before %s", budget, prof.entity)
            break
        candidates = [c for c in prof.columns
                      if c.sentinel_values and not c.sensitive and not c.ref_entity and not c.is_primary_key][:MAX_FRESHNESS_COLUMNS]
        if not candidates:
            continue
        # One scan per table, not two per column: a wide table with a hundred sentinel columns used to
        # cost two hundred full scans, which is how a probe pass stops looking like it is progressing.
        table = d.table(prof.schema_name, physical_name(prof.table_pattern, {**prof.context, **(context or {})}))
        parts = [f"MAX({d.q(time_col)}) AS last_row"]
        for i, col in enumerate(candidates):
            parts.append(f"MAX(CASE WHEN {d.q(col.name)} <> {col.sentinel_values[0]} THEN {d.q(time_col)} END) AS c{i}")
        try:
            _, rows, _ = connector.execute(f"SELECT {', '.join(parts)} FROM {table}", 1)
        except Exception as e:  # noqa: BLE001
            log.debug("freshness probe failed on %s: %s", prof.entity, e)
            continue
        row = dict(rows[0]) if rows else {}
        lowered = {str(k).lower(): v for k, v in row.items()}
        l_val = lowered.get("last_row")
        for i, col in enumerate(candidates):
            f_val = lowered.get(f"c{i}")
            if f_val and l_val and str(f_val) != str(l_val):
                marker = col.sentinel_values[0]
                out.append({"entity": prof.entity, "column": col.name, "filled_until": str(f_val), "last_row": str(l_val)})
                # a measurement of the data, not a competing definition: it holds whoever described this
                col.add_derived("freshness", f"{f_val} tarihine kadar dolu; sonrası {marker} (değer yok)")
    return out


def _formula_sql(formula: str, d: Dialect) -> str:
    import re

    return re.sub(r"\b([A-Z][A-Z0-9_]*)\.([A-Z][A-Z0-9_]*)\b", lambda m: f"{m.group(1)}.{d.q(m.group(2))}", formula or "")


def _scope_sql(mapping: Mapping, d: Dialect) -> str:
    import re

    parts = []
    for key in (mapping.extra or {}).get("conditions") or []:
        m = re.match(r"^(\w+)\.(\w+)\s+(IN|=|<>)\s+\((.*)\)$", key)
        if m:
            entity, column, op, values = m.groups()
            vals = ", ".join(v.strip() for v in values.split(",") if v.strip())
            parts.append(f"{entity}.{d.q(column)} {'IN' if op == '=' else op} ({vals})")
    return " AND ".join(parts)


def _physicalize(sql: str, profiles: list[SchemaProfile], context: dict[str, str], dialect: str) -> str:
    from semantic_layer.runtime.guardrails import physicalize_sql

    return physicalize_sql(sql, profiles, context, dialect or "generic")
