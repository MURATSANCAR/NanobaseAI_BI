"""Evidence Engine — hard gate → weighted score → counter-evidence damping → status.

    E  = 0.30·validated_sql + 0.20·question_correlation + 0.15·profile_fit
       + 0.15·physical_context_fit + 0.10·semantic_similarity + 0.10·execution_consistency
    E' = E · (1 − min(1, 2·r_contra))

Gate (multi_source, default):
    validated_support ≥ min_support
    OR (validated_support ≥ 1 AND documented (DOC/HUMAN) AND profile_fit = 1)
    OR (a person wrote it in the portal AND the data agrees: HUMAN ≥ 1 AND profile_fit = 1)
    OR human_certified
    AND physical mapping exists AND table pattern is profiled AND no BLOCKING counter-evidence
Gate (strict): only validated_support ≥ min_support OR human_certified.

Sense handling: sibling senses (same term, same entity.column, different values) — the documented
sense wins over an undocumented one (the loser gets DOC_CONTRADICTION counter-evidence and is REJECTED);
two undocumented senses with material support each → SENSE_CONFLICT for both.
Drift: certified enum values that disappeared from the profile → DEPRECATED.
"""

from __future__ import annotations

import logging
import re
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
from semantic_layer.store.catalog_store import CatalogStore

log = logging.getLogger(__name__)

WEIGHTS = {
    "validated_sql": 0.30,
    "question_correlation": 0.20,
    "profile_fit": 0.15,
    "physical_context_fit": 0.15,
    "semantic_similarity": 0.10,
    "execution_consistency": 0.10,
}


@dataclass
class Evaluation:
    concept_id: str
    status: str
    score: float
    raw_score: float
    gate_passed: bool
    gate_reasons: list[str]
    breakdown: dict[str, float]
    validated_support: int
    doc_support: int
    human_support: int
    counter_ratio: float
    explain: dict[str, Any] = field(default_factory=dict)


class EvidenceEngine:
    def __init__(self, store: CatalogStore, *, min_support: int = 3, threshold: float = 0.6, gate_mode: str = "multi_source"):
        self.store = store
        self.min_support = min_support
        self.threshold = threshold
        self.gate_mode = gate_mode

    # ------------------------------------------------------------------ evidence aggregation
    @staticmethod
    def _support(evidence: list[Evidence]) -> tuple[int, int, int, float, int]:
        pairs: set[str] = set()
        counted = 0
        precision: list[float] = []
        doc = human = llm = 0
        for e in evidence:
            if e.evidence_type in (EvidenceType.VALIDATED_SQL, EvidenceType.ALIAS_BINDING, EvidenceType.EXPLICIT_BINDING):
                p = e.payload.get("pairs")
                if p:
                    pairs.update(str(x) for x in p)
                else:
                    counted = max(counted, e.support_count)
                if e.evidence_type == EvidenceType.VALIDATED_SQL and "precision" in e.payload:
                    precision.append(float(e.payload["precision"]))
            elif e.evidence_type == EvidenceType.DOC:
                doc += 1
            elif e.evidence_type == EvidenceType.HUMAN_ANNOTATION:
                human += 1
            elif e.evidence_type == EvidenceType.LLM_CANDIDATE:
                llm += 1
        validated = max(len(pairs), counted)
        corr = max(precision) if precision else (0.0 if validated == 0 else 0.5)
        return validated, doc, human, corr, llm

    def _profile_fit(self, mappings: list[Mapping], profiles: dict[str, SchemaProfile]) -> tuple[float, float, list[str]]:
        """(profile_fit, physical_fit, reasons)."""
        if not mappings:
            return 0.0, 0.0, ["no physical mapping"]
        fits, phys, reasons = [], [], []
        for m in mappings:
            prof = profiles.get(m.entity)
            if prof is None:
                phys.append(0.0)
                fits.append(0.0)
                reasons.append(f"table pattern {m.table_pattern} not profiled")
                continue
            if m.formula:
                cols = {c.name.upper() for c in prof.columns}
                refs = {tok.split(".")[1] for tok in _column_refs(m.formula) if tok.split(".")[0] == m.entity}
                missing = [r for r in refs if r not in cols]
                phys.append(0.0 if missing else 1.0)
                fits.append(0.0 if missing else 1.0)
                if missing:
                    reasons.append(f"formula columns missing: {missing}")
                continue
            col = prof.column(m.column or "")
            if col is None:
                phys.append(0.0)
                fits.append(0.0)
                reasons.append(f"column {m.entity}.{m.column} not in profile")
                continue
            phys.append(1.0)
            if m.operator in ("COLUMN", "JOIN"):
                fits.append(1.0)
            elif col.top_values:
                known = {v for v, _ in col.top_values}
                complete = (col.distinct_count or 0) <= len(col.top_values)
                present = sum(1 for v in m.values if v in known)
                fit = present / len(m.values) if m.values else 0.0
                if fit < 1.0 and not complete:
                    fit = 1.0 if present else 0.9  # incomplete top-N list: absence is not contradiction
                fits.append(fit)
                if fit < 1.0:
                    reasons.append(f"values {sorted(set(m.values) - known)} not in profile of {m.entity}.{m.column}")
            else:
                fits.append(0.5)
        return min(fits), min(phys), reasons

    # ------------------------------------------------------------------ evaluation
    def evaluate(self, concept: Concept, profiles: dict[str, SchemaProfile], *, scoped: bool = False) -> Evaluation:
        mappings = self.store.list_mappings(concept.id)
        evidence = self.store.list_evidence(concept.id)
        counters = self.store.list_counter_evidence(concept.id)
        validated, doc, human, corr, llm = self._support(evidence)
        profile_fit, physical_fit, reasons = self._profile_fit(mappings, profiles)
        documented = (doc + human) > 0
        human_certified = bool(concept.explain.get("human_certified_by"))

        blocking = [c for c in counters if c.severity == "BLOCKING"]
        contra_support = 0.0
        for c in counters:
            contra_support += {"LOW": 0.5, "MEDIUM": 1.0, "BLOCKING": 3.0}.get(c.severity, 1.0) * float(c.payload.get("support", 1))
        support_total = validated + doc + human
        r_contra = contra_support / (support_total + contra_support) if (support_total + contra_support) > 0 else 0.0

        gate_reasons: list[str] = []
        if concept.semantic_type == SemanticType.DEFAULT_FILTER:
            support_ok = validated >= 2
        elif concept.semantic_type == SemanticType.RELATIONSHIP:
            support_ok = validated >= 2 or _relationship_in_profile(mappings, profiles)
        elif self.gate_mode == "strict":
            support_ok = validated >= self.min_support
        else:
            support_ok = (
                validated >= self.min_support
                or (validated >= 1 and documented and profile_fit >= 0.9)
                or (concept.semantic_type == SemanticType.COLUMN and documented and physical_fit >= 0.99)
                # Someone deliberately wrote this down against this table and column, and the data
                # agrees with what they wrote. That is a definition, not a guess, and waiting for a
                # validated query on top of it means a deployment where nobody presses the approve
                # button can define columns but never what its codes or its measures mean — which is
                # the part of the business that actually needs saying. The data still has to confirm
                # it: an annotation the profile contradicts does not pass.
                or (human >= 1 and profile_fit >= 0.9 and physical_fit >= 0.99)
            )
        if human_certified:
            support_ok = True
        if not support_ok:
            gate_reasons.append(f"support {validated} < {self.min_support} (documented={documented}, profile_fit={profile_fit:.2f})")
        if physical_fit < 0.99:
            gate_reasons.append("physical mapping invalid: " + "; ".join(reasons))
        if blocking:
            gate_reasons.append("blocking counter-evidence: " + ", ".join(c.conflict_type for c in blocking))
        if concept.explain.get("schema_drift"):      # None once a later run saw the table again
            gate_reasons.append("unresolved schema drift")
        if scoped and any(m.entity not in profiles for m in mappings):
            # Not covered by this run's scope: keep whatever the catalog already decided.
            gate_reasons = [r for r in gate_reasons if "physical mapping invalid" not in r]
            gate_reasons.append("out of profiling scope — status preserved")
        gate_passed = not gate_reasons

        breakdown = {
            "validated_sql": min(1.0, validated / max(1, self.min_support * 2)),
            "question_correlation": corr,
            "profile_fit": profile_fit,
            "physical_context_fit": physical_fit,
            "semantic_similarity": 1.0 if documented else (0.3 if llm else 0.0),
            "execution_consistency": 1.0 if validated > 0 else 0.0,
        }
        # Three of these terms measure use, not truth: whether queries ran, whether they correlated,
        # whether one executed. For a definition a person wrote and the data confirms, they are not
        # zero — they are unmeasured, and scoring an unmeasured axis as a failure is how a correct
        # definition gets held below the bar for the sole reason that nobody has asked yet. When there
        # is no query history at all, the score is taken over the axes that do apply, capped short of
        # certainty because it is still unproven in use.
        usage = ("validated_sql", "question_correlation", "execution_consistency")
        if validated == 0 and human > 0:
            applies = {k: v for k, v in breakdown.items() if k not in usage}
            raw = min(0.85, sum(WEIGHTS[k] * v for k, v in applies.items()) / sum(WEIGHTS[k] for k in applies))
        else:
            raw = sum(WEIGHTS[k] * v for k, v in breakdown.items())
        score = raw * (1.0 - min(1.0, 2.0 * r_contra))

        if human_certified:
            status = ConceptStatus.CERTIFIED
        elif blocking:
            status = ConceptStatus.REJECTED
        elif gate_passed and score >= (0.4 if concept.semantic_type == SemanticType.COLUMN else self.threshold):
            status = ConceptStatus.CERTIFIED
        elif validated == 0 and not documented and not human and llm == 0:
            status = ConceptStatus.DISCOVERED
        else:
            status = ConceptStatus.CANDIDATE
        explain = {
            "gate": {"passed": gate_passed, "reasons": gate_reasons, "mode": self.gate_mode, "min_support": self.min_support},
            "score": round(score, 3),
            "raw_score": round(raw, 3),
            "breakdown": {k: round(v, 3) for k, v in breakdown.items()},
            "support": {"validated_queries": validated, "doc": doc, "human": human, "llm": llm},
            "counter_ratio": round(r_contra, 3),
            "counter_evidence": [c.conflict_type for c in counters],
        }
        return Evaluation(concept.id, status, score, raw, gate_passed, gate_reasons, breakdown, validated, doc, human, r_contra, explain)

    # ------------------------------------------------------------------ sense conflicts
    def resolve_senses(self, tenant_id: str, datasource_id: str, profiles: dict[str, SchemaProfile]) -> list[dict[str, Any]]:
        """Compare sibling senses; add counter-evidence / mark conflicts. Returns a report."""
        report: list[dict[str, Any]] = []
        concepts = self.store.find_concepts(tenant_id, datasource_id, semantic_type=SemanticType.DIMENSION_VALUE, limit=100000)
        groups: dict[tuple[str, str, str], list[tuple[Concept, Mapping, int, bool]]] = {}
        for c in concepts:
            if c.status == ConceptStatus.REJECTED:
                continue
            ev = self.store.list_evidence(c.id)
            validated, doc, human, _, _ = self._support(ev)
            for m in self.store.list_mappings(c.id):
                if m.column:
                    groups.setdefault((c.normalized_term, m.entity, m.column.upper()), []).append((c, m, validated, (doc + human) > 0))
        for (term, entity, column), senses in groups.items():
            if len(senses) < 2:
                continue
            documented = [s for s in senses if s[3]]
            undocumented = [s for s in senses if not s[3]]
            if documented and undocumented:
                for c, m, sup, _ in undocumented:
                    dv = sorted({v for d in documented for v in d[1].values})
                    self.store.add_counter_evidence(CounterEvidence(c.id, f"sense:{documented[0][0].id}", "DOC_CONTRADICTION", payload={"documented_values": dv, "support": max(1, sup)}, severity="BLOCKING"))
                    report.append({"term": term, "entity": entity, "column": column, "rejected_values": m.values, "documented_values": dv})
                for c, m, sup, _ in documented:
                    self.store.clear_counter_evidence(c.id, "SENSE_CONFLICT")
                continue
            # neither (or both) documented: dominance rule 3:1 else conflict
            senses_sorted = sorted(senses, key=lambda s: -s[2])
            top = senses_sorted[0]
            rest = senses_sorted[1:]
            rest_support = sum(s[2] for s in rest)
            if rest_support == 0:
                continue
            if top[2] >= 3 * rest_support:
                for c, m, sup, _ in rest:
                    self.store.add_counter_evidence(CounterEvidence(c.id, f"sense:{top[0].id}", "SENSE_MINORITY", payload={"dominant_values": top[1].values, "support": sup}, severity="MEDIUM"))
                self.store.add_counter_evidence(CounterEvidence(top[0].id, "sense:minor", "SENSE_MINORITY", payload={"other_values": [s[1].values for s in rest], "support": rest_support}, severity="LOW"))
            else:
                for c, m, sup, _ in senses:
                    others = [s[1].values for s in senses if s[0].id != c.id]
                    self.store.add_counter_evidence(CounterEvidence(c.id, "sense:conflict", "SENSE_CONFLICT", payload={"other_values": others, "support": sum(s[2] for s in senses if s[0].id != c.id)}, severity="MEDIUM"))
                    self.store.update_concept(c.id, status=ConceptStatus.SENSE_CONFLICT, explain={"sense_conflict": {"others": others}})
                report.append({"term": term, "entity": entity, "column": column, "conflict": [list(s[1].values) for s in senses]})
        return report

    # ------------------------------------------------------------------ drift
    def _drift_free(self, m: Mapping, profiles: dict[str, SchemaProfile]) -> bool:
        """Does this mapping still point at something that exists? Read-only: the same three questions
        detect_drift asks, asked in order to withdraw a stale answer rather than to record a new one."""
        prof = profiles.get(m.entity)
        if prof is None:
            return False
        if m.column and prof.column(m.column) is None:
            return False
        col = prof.column(m.column) if m.column else None
        if col and col.top_values and m.values and (col.distinct_count or 0) <= len(col.top_values):
            known = {v for v, _ in col.top_values}
            if [v for v in m.values if v not in known]:
                return False
        return True

    def detect_drift(self, tenant_id: str, datasource_id: str, profiles: dict[str, SchemaProfile], *, scoped: bool = False) -> list[dict[str, Any]]:
        """Drift is a table or value that *disappeared*. A table that was never in this run's scope is
        unknown, not gone: `scoped=True` says the profile covers only part of the schema, and concepts
        outside it keep their status instead of being decertified by a narrower scan."""
        out = []
        # Drift is a claim about a moment: "this table was here and now it is not". A run that sees the
        # table again refutes it, and a refuted claim has to be withdrawn — it is BLOCKING, so leaving
        # it attached decertifies a healthy concept on some later run, long after the scan that wrote
        # it. That is what took "ciro", "kanal" and the joins out of the vocabulary here: a narrow scan
        # once failed to see LG_{n0}_{n1}_INVOICE, and every run since carried its verdict forward.
        for c in self.store.find_concepts(tenant_id, datasource_id,
                                          status=[ConceptStatus.CERTIFIED, ConceptStatus.REJECTED,
                                                  ConceptStatus.CANDIDATE, ConceptStatus.DEPRECATED],
                                          limit=100000):
            maps = self.store.list_mappings(c.id)
            if maps and all(self._drift_free(m, profiles) for m in maps) and \
                    any(x.conflict_type == "DRIFT" for x in self.store.list_counter_evidence(c.id)):
                self.store.clear_counter_evidence(c.id, "DRIFT")
                # The note the detector left behind blocks the gate on its own — clearing only the
                # counter-evidence would leave the concept failing for a reason nothing supports.
                if c.explain.get("schema_drift"):
                    self.store.update_concept(c.id, explain={"schema_drift": None})
                out.append({"concept": c.term, "drift": "resolved"})
        for c in self.store.find_concepts(tenant_id, datasource_id, status=ConceptStatus.CERTIFIED, limit=100000):
            for m in self.store.list_mappings(c.id):
                prof = profiles.get(m.entity)
                if prof is None:
                    if scoped:
                        continue      # out of scope this run — say nothing rather than decertify
                    self.store.add_counter_evidence(CounterEvidence(c.id, "drift:table", "DRIFT", payload={"missing_table": m.table_pattern, "support": 3}, severity="BLOCKING"))
                    self.store.update_concept(c.id, status=ConceptStatus.DEPRECATED, explain={"schema_drift": f"table {m.table_pattern} missing"})
                    out.append({"concept": c.term, "drift": "table_missing", "table": m.table_pattern})
                    break
                if m.column and prof.column(m.column) is None:
                    self.store.add_counter_evidence(CounterEvidence(c.id, "drift:column", "DRIFT", payload={"missing_column": f"{m.entity}.{m.column}", "support": 3}, severity="BLOCKING"))
                    self.store.update_concept(c.id, status=ConceptStatus.DEPRECATED, explain={"schema_drift": f"column {m.entity}.{m.column} missing"})
                    out.append({"concept": c.term, "drift": "column_missing", "column": f"{m.entity}.{m.column}"})
                    break
                col = prof.column(m.column) if m.column else None
                if col and col.top_values and m.values and (col.distinct_count or 0) <= len(col.top_values):
                    known = {v for v, _ in col.top_values}
                    gone = [v for v in m.values if v not in known]
                    if gone:
                        self.store.add_counter_evidence(CounterEvidence(c.id, "drift:values", "DRIFT", payload={"values_gone": gone, "support": 3}, severity="BLOCKING"))
                        self.store.update_concept(c.id, status=ConceptStatus.DEPRECATED, explain={"schema_drift": f"values {gone} no longer observed in {m.entity}.{m.column}"})
                        out.append({"concept": c.term, "drift": "values_gone", "values": gone})
                        break
        return out

    # ------------------------------------------------------------------ synonyms (evidence-backed)
    def link_synonyms(self, tenant_id: str, datasource_id: str) -> list[dict[str, Any]]:
        """Two evidence-backed synonym rules for CERTIFIED metrics:
        (a) a validated sub-term ('satis' ⊂ 'satis tutar') whose own formula uses the same columns and scope;
        (b) terms declared together in documentation ("ciro / satış tutarı" = the same measure column)."""
        out: list[dict[str, Any]] = []
        certified = self.store.find_concepts(tenant_id, datasource_id, semantic_type=SemanticType.METRIC, status=ConceptStatus.CERTIFIED, limit=100000)
        others = [c for c in self.store.find_concepts(tenant_id, datasource_id, semantic_type=SemanticType.METRIC, limit=100000) if c.status not in (ConceptStatus.CERTIFIED, ConceptStatus.REJECTED)]
        columns = self.store.find_concepts(tenant_id, datasource_id, semantic_type=SemanticType.COLUMN, limit=100000)
        for y in certified:
            ymaps = self.store.list_mappings(y.id)
            if not ymaps or not ymaps[0].formula:
                continue
            ym = ymaps[0]
            ycols = set(_column_refs(ym.formula))
            yscope = set((ym.extra or {}).get("conditions") or [])
            ywords = set(y.normalized_term.split())
            syns = set(y.synonyms)
            for x in others:
                xm = next(iter(self.store.list_mappings(x.id)), None)
                if not xm or not xm.formula or xm.entity != ym.entity:
                    continue
                xwords = set(x.normalized_term.split())
                if xwords < ywords and set(_column_refs(xm.formula)) <= ycols and (set((xm.extra or {}).get("conditions") or []) == yscope or _scope_in_formula(ym.formula, xm.extra)):
                    validated, _, _, _, _ = self._support(self.store.list_evidence(x.id))
                    if validated >= 1 and x.normalized_term not in syns:
                        syns.add(x.normalized_term)
                        out.append({"metric": y.term, "synonym": x.term, "rule": "validated_subterm"})
            # (c) equivalent measure: same base formula on the same entity with compatible scope
            #     ("satılan adet" ≡ "adet" = SUM(STLINE.AMOUNT)); conflicting value sets never link.
            ybase, yconds = metric_signature(ym)
            for x in others:
                if x.normalized_term in syns or x.normalized_term == y.normalized_term:
                    continue
                xm = next(iter(self.store.list_mappings(x.id)), None)
                if not xm or not xm.formula or xm.entity != ym.entity:
                    continue
                xbase, xconds = metric_signature(xm)
                if xbase != ybase or not conditions_compatible(xconds, yconds):
                    continue
                validated, _, _, _, _ = self._support(self.store.list_evidence(x.id))
                if validated >= 1:
                    syns.add(x.normalized_term)
                    out.append({"metric": y.term, "synonym": x.term, "rule": "equivalent_formula"})
            for c in columns:
                declared = set(c.explain.get("declared_synonyms") or [])
                if not declared:
                    continue
                cm = next(iter(self.store.list_mappings(c.id)), None)
                if not cm or f"{cm.entity}.{cm.column}" not in ycols:
                    continue
                if y.normalized_term in declared or y.normalized_term == c.normalized_term:
                    for d in declared | {c.normalized_term}:
                        if d != y.normalized_term and d not in syns:
                            syns.add(d)
                            out.append({"metric": y.term, "synonym": d, "rule": "declared_alias"})
            if syns != set(y.synonyms):
                self.store.update_concept(y.id, synonyms=sorted(syns), explain={"synonym_rules": out[-5:]})
        return out

    # ------------------------------------------------------------------ full run
    def run(self, tenant_id: str, datasource_id: str, profiles: list[SchemaProfile], *, note: str = "", scoped: Optional[bool] = None) -> dict[str, Any]:
        pmap = {p.entity: p for p in profiles}
        if scoped is None:
            import os

            scoped = bool(os.environ.get("SEMANTIC_TABLE_LIKE") or os.environ.get("SEMANTIC_DEEP_TABLES"))
        sense_report = self.resolve_senses(tenant_id, datasource_id, pmap)
        drift = self.detect_drift(tenant_id, datasource_id, pmap, scoped=scoped)
        changed: dict[str, list[str]] = {s: [] for s in ConceptStatus.ALL}
        evaluations: list[Evaluation] = []
        for c in self.store.find_concepts(tenant_id, datasource_id, limit=100000):
            if c.status in (ConceptStatus.DEPRECATED,):
                continue
            if c.status == ConceptStatus.SENSE_CONFLICT and not self.store.list_counter_evidence(c.id):
                pass
            ev = self.evaluate(c, pmap, scoped=scoped)
            evaluations.append(ev)
            new_status = ev.status
            if scoped and "out of profiling scope" in " ".join(ev.gate_reasons):
                continue      # leave it exactly as it was
            if c.status == ConceptStatus.SENSE_CONFLICT and any(x.conflict_type == "SENSE_CONFLICT" for x in self.store.list_counter_evidence(c.id)):
                new_status = ConceptStatus.SENSE_CONFLICT
            if new_status != c.status:
                changed[new_status].append(c.term)
            self.store.update_concept(c.id, status=new_status, confidence=ev.score, explain=ev.explain)
        synonyms = self.link_synonyms(tenant_id, datasource_id)
        certified = self.store.find_concepts(tenant_id, datasource_id, status=ConceptStatus.CERTIFIED, limit=100000)
        snapshot = {
            "certified_count": len(certified),
            "certified": sorted(f"{c.semantic_type}:{c.normalized_term}#{c.sense_id}" for c in certified),
            "synonyms": {c.id: sorted(c.synonyms) for c in certified if c.synonyms},
            "mappings": {c.id: [m.key() for m in self.store.list_mappings(c.id)] for c in certified},
        }
        latest = self.store.latest_version(tenant_id, datasource_id)
        version = latest["version"] if latest else 0
        if latest is None or (latest.get("snapshot") or {}).get("certified") != snapshot["certified"] or (latest.get("snapshot") or {}).get("mappings") != snapshot["mappings"]:
            version = self.store.create_version(tenant_id, datasource_id, snapshot, note=note or "evidence engine run")
        return {
            "evaluated": len(evaluations),
            "certified": len(certified),
            "status_counts": self.store.status_counts(tenant_id, datasource_id),
            "changed": {k: v for k, v in changed.items() if v},
            "sense_report": sense_report,
            "drift": drift,
            "synonyms": synonyms,
            "catalog_version": version,
        }

    # ------------------------------------------------------------------ human governance
    def human_certify(self, concept_id: str, user: str, reason: str = "") -> Optional[Concept]:
        return self.store.update_concept(concept_id, status=ConceptStatus.CERTIFIED, confidence=1.0, explain={"human_certified_by": user, "human_reason": reason}, bump_version=True)

    def human_reject(self, concept_id: str, user: str, reason: str = "") -> Optional[Concept]:
        self.store.add_counter_evidence(CounterEvidence(concept_id, f"human:{user}", "HUMAN_REJECT", payload={"reason": reason, "support": 3}, severity="BLOCKING"))
        return self.store.update_concept(concept_id, status=ConceptStatus.REJECTED, explain={"human_rejected_by": user, "human_reason": reason}, bump_version=True)


def _column_refs(formula: str) -> list[str]:
    return re.findall(r"\b([A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*)\b", formula or "")


_COND_IN = re.compile(r"\b([A-Z][A-Z0-9_]*)\.([A-Z][A-Z0-9_]*)\s+IN\s*\(([^)]*)\)", re.I)
_COND_EQ = re.compile(r"\b([A-Z][A-Z0-9_]*)\.([A-Z][A-Z0-9_]*)\s*=\s*(-?\d+)", re.I)
_CASE_SUM = re.compile(r"^\s*(SUM|COUNT)\(\s*CASE\s+WHEN\s+(.+?)\s+THEN\s+(.+?)\s+ELSE\s+0\s+END\s*\)\s*$", re.I | re.S)


def _values_of(raw: str) -> frozenset[str]:
    return frozenset(v.strip().strip("'\"") for v in raw.split(",") if v.strip())


def conditions_map(conditions: list[str]) -> dict[str, frozenset[str]]:
    """['INVOICE.TRCODE IN (7,8,9)'] → {'INVOICE.TRCODE': {'7','8','9'}}."""
    out: dict[str, frozenset[str]] = {}
    for c in conditions or []:
        m = _COND_IN.search(c) or None
        if m:
            out[f"{m.group(1).upper()}.{m.group(2).upper()}"] = _values_of(m.group(3))
            continue
        m = _COND_EQ.search(c)
        if m:
            out[f"{m.group(1).upper()}.{m.group(2).upper()}"] = frozenset({m.group(3)})
    return out


def metric_signature(mapping: Mapping) -> tuple[str, dict[str, frozenset[str]]]:
    """Base aggregate + scope, folding a redundant conditional aggregate into the scope:
    SUM(CASE WHEN <code> IN (…) THEN <measure> ELSE 0 END) ≡ SUM(<measure>) scoped to that condition.
    An ELSE branch that is not 0 (a signed net measure) is a different measure and is never folded."""
    formula = (mapping.formula or "").strip()
    conds = conditions_map(list((mapping.extra or {}).get("conditions") or []))
    m = _CASE_SUM.match(formula)
    if m and "CASE" not in m.group(3).upper():
        conds.update(conditions_map([m.group(2)]))
        formula = f"{m.group(1).upper()}({m.group(3).strip()})"
    return " ".join(formula.split()), conds


def conditions_compatible(a: dict[str, frozenset[str]], b: dict[str, frozenset[str]]) -> bool:
    """Columns present in both must carry the same value set; a column present in only one is fine."""
    return all(a[col] == b[col] for col in set(a) & set(b))


def _scope_in_formula(formula: str, extra: dict | None) -> bool:
    """A sub-term metric whose WHERE scope (TRCODE IN (7,8,9)) equals the CASE scope embedded in the certified formula."""
    conds = (extra or {}).get("conditions") or []
    if not conds:
        return False
    for key in conds:
        m = re.match(r"^(\w+)\.(\w+)\s+(IN|=)\s+\((.*)\)$", key)
        if not m:
            return False
        col, vals = m.group(2), sorted(v.strip() for v in m.group(4).split(","))
        fm = re.search(rf"{col} IN \(([^)]*)\)", formula)
        if not fm or sorted(v.strip() for v in fm.group(1).split(",")) != vals:
            return False
    return True


def _relationship_in_profile(mappings: list[Mapping], profiles: dict[str, SchemaProfile]) -> bool:
    for m in mappings:
        prof = profiles.get(m.entity)
        if not prof:
            continue
        for r in prof.relationships:
            if r["column"].upper() == (m.column or "").upper() and r["ref_entity"] == m.extra.get("ref_entity"):
                return True
    return False
