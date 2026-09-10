"""History Miner — validated Q→SQL pairs → term↔predicate correlations, metric formulas,
default filters and relationships. Output is evidence, never certification."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from semantic_layer.history.question_facts import extract_question_facts
from semantic_layer.history.sql_facts import extract_sql_facts, is_value_predicate
from semantic_layer.models import (
    Candidate,
    Concept,
    ConceptStatus,
    Evidence,
    EvidenceType,
    Mapping,
    Predicate,
    SemanticType,
    ValidatedPair,
)
from semantic_layer.history.question_facts import GENERIC_S
from semantic_layer.normalize import METRIC_VOCAB_S, MODIFIERS_S, STOPWORDS_S, alias_tokens, stem

log = logging.getLogger(__name__)

# Terms that name entities/measures generically and must not become DIMENSION_VALUE mappings.
_GENERIC_TERMS = GENERIC_S | METRIC_VOCAB_S
_DATE_LIT = re.compile(r"'\d{4}-\d{2}-\d{2}")


@dataclass
class Correlation:
    term: str
    entity: str
    table_pattern: str
    column: str
    operator: str
    values: tuple[str, ...]
    support: int = 0                 # pairs where term ∧ predicate
    alias_support: int = 0
    explicit_support: int = 0
    term_total: int = 0
    pred_total: int = 0
    pair_ids: list[str] = field(default_factory=list)

    @property
    def precision(self) -> float:
        return self.support / self.term_total if self.term_total else 0.0

    @property
    def recall(self) -> float:
        return self.support / self.pred_total if self.pred_total else 0.0

    @property
    def strong(self) -> bool:
        return self.alias_support > 0 or self.explicit_support > 0

    def key(self) -> tuple:
        return (self.term, self.entity, self.column, self.operator, self.values)


@dataclass
class MetricCandidate:
    term: str
    entity: Optional[str]
    formula: str
    func: str
    support: int = 0
    aliases: set[str] = field(default_factory=set)
    pair_ids: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)


@dataclass
class MiningResult:
    correlations: list[Correlation] = field(default_factory=list)
    columns: list[Correlation] = field(default_factory=list)
    metrics: list[MetricCandidate] = field(default_factory=list)
    default_filters: list[tuple[Predicate, int]] = field(default_factory=list)
    relationships: dict[tuple[str, str, str, str], int] = field(default_factory=dict)
    temporal_bindings: list[dict[str, Any]] = field(default_factory=list)
    patterns: dict[str, str] = field(default_factory=dict)
    context: dict[str, str] = field(default_factory=dict)
    surface: dict[str, str] = field(default_factory=dict)
    surface_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    pairs_total: int = 0
    pairs_real: int = 0
    parse_errors: list[tuple[str, str]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "pairs_total": self.pairs_total,
            "pairs_real": self.pairs_real,
            "correlations": len(self.correlations),
            "strong_correlations": sum(1 for c in self.correlations if c.strong),
            "metrics": len(self.metrics),
            "columns": len(self.columns),
            "default_filters": [(p.key(), n) for p, n in self.default_filters],
            "relationships": len(self.relationships),
            "parse_errors": len(self.parse_errors),
        }


class HistoryMiner:
    def __init__(self, column_index: Optional[dict[str, set[str]]] = None, *, default_filter_ratio: float = 0.75, conventions: Any = None):
        self.conventions = conventions
        self.column_index = column_index or (dict(conventions.columns) if conventions is not None else None)
        self.default_filter_ratio = default_filter_ratio

    def _is_scope(self, entity: Optional[str], column: str) -> bool:
        """A metric's scope is a business type code — an enum with more than two values in the
        profile. Without a profile nothing is scope: unproven assumptions stay out of the catalog."""
        if self.conventions is None:
            return False
        return self.conventions.is_scope_column(entity, column)

    def _is_flag(self, entity: Optional[str], column: str) -> bool:
        if self.conventions is None:
            return True
        return self.conventions.is_flag_column(entity, column)

    # ------------------------------------------------------------------ mining
    def mine(self, pairs: Iterable[ValidatedPair]) -> MiningResult:
        res = MiningResult()
        pairs = list(pairs)
        res.pairs_total = len(pairs)
        real = [p for p in pairs if p.source != "seed"]
        res.pairs_real = len(real)

        co: dict[tuple, Correlation] = {}
        col_co: dict[tuple, Correlation] = {}
        term_total: dict[str, int] = defaultdict(int)
        term_entity_total: dict[tuple[str, str], int] = defaultdict(int)
        pred_total: dict[tuple, int] = defaultdict(int)
        pred_pairs: dict[tuple, int] = defaultdict(int)
        entity_pairs: dict[str, int] = defaultdict(int)
        metric_by_formula: dict[str, MetricCandidate] = {}
        column_names = {c.upper() for cols in (self.column_index or {}).values() for c in cols}

        for pair in pairs:
            sf = extract_sql_facts(pair.sql, self.column_index, self.conventions)
            if sf.parse_error:
                res.parse_errors.append((pair.id, sf.parse_error))
                continue
            res.patterns.update(sf.table_patterns)
            res.context.update(sf.context)
            for j in sf.joins:
                res.relationships[j] = res.relationships.get(j, 0) + 1
            if pair.source == "seed":
                continue  # synthetic English pairs only contribute join evidence

            for ent in sf.tables:
                entity_pairs[ent] += 1
            qf = extract_question_facts(pair.nl)
            all_terms = {t for _, _, t in qf.terms}
            terms = {t for t in all_terms if _usable_term(t) and t.upper() not in column_names}
            for t in all_terms:
                sf_ = qf.surface.get(t, t)
                res.surface_counts.setdefault(t, {})
                res.surface_counts[t][sf_] = res.surface_counts[t].get(sf_, 0) + 1
            # alias tokens bind only when the alias has a single CASE predicate on that column (ratios don't)
            alias_preds: dict[tuple, set] = defaultdict(set)
            for p in sf.predicates:
                if p.source == "case" and p.alias:
                    alias_preds[(p.alias, p.entity, p.column)].add((p.operator, p.values))
            for t in terms:
                res.surface.setdefault(t, qf.surface.get(t, t))
            for t in terms:
                term_total[t] += 1
                for ent in sf.tables:
                    term_entity_total[(t, ent)] += 1

            preds = {p for p in sf.predicates if is_value_predicate(p)}
            pred_keys = {(p.entity, p.column, p.operator, p.values) for p in preds}
            for pk in pred_keys:
                pred_pairs[pk] += 1

            # explicit "(TRCODE 8)" bindings — the question states the physical value itself
            for term, col, vals in qf.explicit_bindings:
                ent = self._entity_for_column(col, sf.tables)
                if ent:
                    c = _get(co, term, ent, res.patterns.get(ent, ent), col, "IN" if len(vals) > 1 else "=", vals)
                    c.explicit_support += 1
                    c.support += 1
                    c.pair_ids.append(pair.id)
                    term_total.setdefault(term, 0)

            for p in preds:
                pk = (p.entity, p.column, p.operator, p.values)
                pattern = res.patterns.get(p.entity, p.entity)
                unique_alias = bool(p.alias) and len(alias_preds.get((p.alias, p.entity, p.column), set())) == 1
                atoks = set(alias_tokens(p.alias)) if unique_alias else set()
                for t in terms:
                    c = _get(co, t, p.entity, pattern, p.column, p.operator, p.values)
                    if pair.id not in c.pair_ids:
                        c.support += 1
                        c.pair_ids.append(pair.id)
                    if atoks and all(w in atoks for w in t.split()):
                        c.alias_support += 1
                # alias tokens that are not in the question still bind (perakende_toplam ↔ TRCODE=7)
                for w in atoks:
                    if _usable_term(w) and w not in terms:
                        c = _get(co, w, p.entity, pattern, p.column, p.operator, p.values)
                        c.alias_support += 1
                        if pair.id not in c.pair_ids:
                            c.support += 1
                            c.pair_ids.append(pair.id)
                        term_total.setdefault(w, 0)

            # metrics: aggregate formulas ↔ alias / question terms
            for agg in sf.aggregates:
                if agg.func not in ("SUM", "COUNT", "COUNT_DISTINCT", "AVG", "RATIO", "EXPR", "MIN", "MAX"):
                    continue
                if _DATE_LIT.search(agg.formula):
                    continue  # question-specific date buckets are not metrics
                atoks = alias_tokens(agg.alias) if agg.alias else []
                term = _metric_term(atoks, all_terms)
                if not term or any(w.isdigit() for w in term.split()):
                    continue
                res.surface.setdefault(term, qf.surface.get(term, term.replace("_", " ")))
                # scope: WHERE value predicates on the metric's entity (SUM(NETTOTAL) means nothing without TRCODE IN (7,8,9))
                scope = sorted({p.key() for p in sf.predicates if p.source in ("where", "scope") and p.entity == (agg.entity or p.entity) and self._is_scope(p.entity, p.column) and p.operator in ("=", "IN", "<>", "NOT IN")})
                mkey = agg.formula + ("|" + ";".join(scope) if scope else "")
                mc = metric_by_formula.setdefault(mkey, MetricCandidate(term, agg.entity, agg.formula, agg.func))
                mc.support += 1
                if agg.alias:
                    mc.aliases.add(agg.alias)
                mc.pair_ids.append(pair.id)
                mc.conditions = scope

            # COLUMN concepts: projection aliases / group-by columns ↔ question terms
            known_entities = set(self.column_index or {}) or set(sf.tables)
            for alias, ent, col in sf.projections:
                if col in ("DATE_",) or not ent or ent not in known_entities:
                    continue
                if self.column_index and col not in {c.upper() for c in self.column_index.get(ent, set())}:
                    continue
                pattern = res.patterns.get(ent, ent)
                atoks = set(alias_tokens(alias)) if alias else set()
                bound = False
                for t in all_terms:
                    if not _usable_column_term(t):
                        continue
                    if atoks and all(w in atoks for w in t.split()):
                        c = _get(col_co, t, ent, pattern, col, "COLUMN", ())
                        c.alias_support += 1
                        if pair.id not in c.pair_ids:
                            c.support += 1
                            c.pair_ids.append(pair.id)
                        bound = True
                if not bound:
                    for w in atoks:
                        if _usable_column_term(w) and w.upper() != col:
                            c = _get(col_co, w, ent, pattern, col, "COLUMN", ())
                            c.alias_support += 1
                            if pair.id not in c.pair_ids:
                                c.support += 1
                                c.pair_ids.append(pair.id)
                            term_total.setdefault(w, 0)

            for tr in sf.time_ranges:
                for slot in qf.temporal:
                    res.temporal_bindings.append({"pair": pair.id, "text": slot.text, "primitive": slot.primitive, "entity": tr.entity, "column": tr.column, "start": tr.start, "end": tr.end})

        # default filters: flag-like predicates present in most real pairs that touch the entity
        # (business scope columns such as TRCODE/LINETYPE are metric scope, never defaults)
        for pk, n in pred_pairs.items():
            base = entity_pairs.get(pk[0], 0)
            if self._is_scope(pk[0], pk[1]) or pk[2] not in ("=", "IN"):
                continue
            if not self._is_flag(pk[0], pk[1]):
                continue
            if base and n / base >= self.default_filter_ratio and n >= 3:
                res.default_filters.append((Predicate(pk[0], pk[1], pk[2], pk[3], "where"), n))
        for c in col_co.values():
            c.term_total = term_total.get(c.term, 0) or c.support
            c.pred_total = c.support
            if c.strong:
                res.columns.append(c)
        default_keys = {(p.entity, p.column, p.operator, p.values) for p, _ in res.default_filters}

        for t, forms in res.surface_counts.items():
            res.surface[t] = sorted(forms.items(), key=lambda kv: (-kv[1], len(kv[0])))[0][0]
        for c in co.values():
            c.term_total = term_entity_total.get((c.term, c.entity), 0) or term_total.get(c.term, 0) or c.support
            c.pred_total = pred_pairs.get((c.entity, c.column, c.operator, c.values), c.support)
            if (c.entity, c.column, c.operator, c.values) in default_keys:
                continue
            if c.strong or (c.support >= 2 and c.precision >= 0.5):
                res.correlations.append(c)
        res.correlations.sort(key=lambda c: (-(c.explicit_support * 3 + c.alias_support * 2 + c.support), c.term))
        res.metrics = sorted(metric_by_formula.values(), key=lambda m: -m.support)
        return res

    def _entity_for_column(self, col: str, entities: list[str]) -> Optional[str]:
        col = col.upper()
        owners = [e for e in entities if col in {c.upper() for c in (self.column_index or {}).get(e, set())}]
        if len(owners) == 1:
            return owners[0]
        if owners and self.conventions is not None:
            return self.conventions.preferred_entity(owners)
        return owners[0] if owners else (entities[0] if entities else None)

    # ------------------------------------------------------------------ persistence
    def persist(self, res: MiningResult, store, tenant_id: str, datasource_id: str) -> dict[str, int]:
        """Write correlations/metrics/default filters as CANDIDATE concepts with evidence."""
        created = updated = 0
        for c in res.correlations:
            values = list(c.values)
            op = c.operator if len(values) > 1 or c.operator in ("<>", "NOT IN") else "="
            if op == "=" and len(values) > 1:
                op = "IN"
            mapping = Mapping(concept_id="", entity=c.entity, table_pattern=c.table_pattern, column=c.column, operator="IN" if op == "=" else op, values=values)
            concept, was_new = store.upsert_concept(tenant_id, datasource_id, res.surface.get(c.term, c.term), SemanticType.DIMENSION_VALUE, mapping=mapping, status=ConceptStatus.CANDIDATE)
            created += int(was_new)
            updated += int(not was_new)
            corr = 1.0 if c.strong else c.precision
            store.add_evidence(Evidence(concept.id, EvidenceType.VALIDATED_SQL, "history_miner", support_count=c.support, weight=1.0, payload={"precision": round(corr, 3), "raw_precision": round(c.precision, 3), "recall": round(c.recall, 3), "pairs": c.pair_ids[:50], "term_total": c.term_total}))
            if c.alias_support:
                store.add_evidence(Evidence(concept.id, EvidenceType.ALIAS_BINDING, "history_miner", support_count=c.alias_support, weight=1.0, payload={"pairs": c.pair_ids[:50]}))
            if c.explicit_support:
                store.add_evidence(Evidence(concept.id, EvidenceType.EXPLICIT_BINDING, "history_miner", support_count=c.explicit_support, weight=1.0, payload={"pairs": c.pair_ids[:50]}))
            store.add_candidate(Candidate(concept.id, "history_miner", payload={"support": c.support, "alias": c.alias_support, "explicit": c.explicit_support, "precision": round(c.precision, 3)}))
            if concept.status == ConceptStatus.DISCOVERED:
                store.update_concept(concept.id, status=ConceptStatus.CANDIDATE)
        for c in res.columns:
            mapping = Mapping(concept_id="", entity=c.entity, table_pattern=c.table_pattern, column=c.column, operator="COLUMN")
            concept, was_new = store.upsert_concept(tenant_id, datasource_id, res.surface.get(c.term, c.term), SemanticType.COLUMN, mapping=mapping, status=ConceptStatus.CANDIDATE)
            created += int(was_new)
            store.add_evidence(Evidence(concept.id, EvidenceType.VALIDATED_SQL, "history_miner", support_count=c.support, weight=1.0, payload={"precision": round(c.precision, 3), "pairs": c.pair_ids[:50]}))
            store.add_evidence(Evidence(concept.id, EvidenceType.ALIAS_BINDING, "history_miner", support_count=c.alias_support, weight=1.0, payload={"pairs": c.pair_ids[:50]}))
            store.add_candidate(Candidate(concept.id, "history_miner", payload={"support": c.support, "alias": c.alias_support}))
        for m in res.metrics:
            if not m.entity or m.entity == "UNKNOWN":
                continue
            mapping = Mapping(concept_id="", entity=m.entity or "UNKNOWN", table_pattern=res.patterns.get(m.entity or "", m.entity or "UNKNOWN"), formula=m.formula, extra={"func": m.func, "aliases": sorted(m.aliases), "conditions": m.conditions})
            concept, was_new = store.upsert_concept(tenant_id, datasource_id, res.surface.get(m.term, m.term), SemanticType.METRIC, mapping=mapping, status=ConceptStatus.CANDIDATE)
            created += int(was_new)
            store.add_evidence(Evidence(concept.id, EvidenceType.VALIDATED_SQL, "history_miner", support_count=m.support, weight=1.0, payload={"pairs": m.pair_ids[:50], "aliases": sorted(m.aliases)}))
            store.add_candidate(Candidate(concept.id, "history_miner", payload={"support": m.support, "formula": m.formula}))
        for p, n in res.default_filters:
            mapping = Mapping(concept_id="", entity=p.entity, table_pattern=res.patterns.get(p.entity, p.entity), column=p.column, operator=p.operator, values=list(p.values))
            term = f"{p.entity.lower()} default {p.column.lower()}"
            concept, was_new = store.upsert_concept(tenant_id, datasource_id, term, SemanticType.DEFAULT_FILTER, mapping=mapping, status=ConceptStatus.CANDIDATE, domain="defaults")
            created += int(was_new)
            store.add_evidence(Evidence(concept.id, EvidenceType.VALIDATED_SQL, "history_miner", support_count=n, weight=1.0, payload={"ratio": round(n / max(1, res.pairs_real), 3), "pairs": []}))
        for (ea, ca, eb, cb), n in res.relationships.items():
            mapping = Mapping(concept_id="", entity=ea, table_pattern=res.patterns.get(ea, ea), column=ca, operator="JOIN", values=[f"{eb}.{cb}"], extra={"ref_entity": eb, "ref_column": cb, "ref_pattern": res.patterns.get(eb, eb)})
            concept, was_new = store.upsert_concept(tenant_id, datasource_id, f"{ea}.{ca} -> {eb}.{cb}", SemanticType.RELATIONSHIP, mapping=mapping, status=ConceptStatus.CANDIDATE, domain="schema")
            created += int(was_new)
            store.add_evidence(Evidence(concept.id, EvidenceType.VALIDATED_SQL, "history_miner", support_count=n, weight=1.0))
        return {"created": created, "updated": updated}


# ---------------------------------------------------------------------- helpers

def _get(co: dict, term: str, entity: str, pattern: str, column: str, op: str, values: tuple[str, ...]) -> Correlation:
    key = (term, entity, column, op, values)
    if key not in co:
        co[key] = Correlation(term, entity, pattern, column, op, values)
    return co[key]


def _usable_term(t: str) -> bool:
    words = t.split()
    if not words or len(t) < 3:
        return False
    if all(w in _GENERIC_TERMS or w in MODIFIERS_S or w in STOPWORDS_S for w in words):
        return False
    if any(w.isdigit() for w in words):
        return False
    # multi-word terms must not start/end with a metric/modifier word ("toptan toplam" → no)
    if len(words) > 1 and (words[0] in MODIFIERS_S or words[-1] in MODIFIERS_S or words[-1] in METRIC_VOCAB_S or words[0] in METRIC_VOCAB_S):
        return False
    return True





def _metric_term(alias_toks: list[str], question_terms: set[str]) -> Optional[str]:
    """Metric term = the question n-gram that names the alias: exact match first, then the shortest
    n-gram containing every alias token, then (only for metric-worded aliases) the longest n-gram
    contained in the alias tokens; else the alias words themselves."""
    toks = [t for t in alias_toks if t not in STOPWORDS_S]
    if not toks:
        return None
    tset = set(toks)
    exact = [t for t in question_terms if set(t.split()) == tset]
    if exact:
        return min(exact, key=len)
    supers = [t for t in question_terms if tset <= set(t.split()) and len(t.split()) <= len(toks) + 1]
    if supers:
        return min(supers, key=lambda t: (len(t.split()), len(t)))
    subs = [t for t in question_terms if set(t.split()) <= tset and any(w in METRIC_VOCAB_S for w in t.split())]
    if subs:
        return max(subs, key=lambda t: (len(t.split()), len(t)))
    if any(w in METRIC_VOCAB_S or w in _GENERIC_TERMS for w in toks) or len(toks) >= 2:
        return " ".join(toks)
    return None


def _usable_column_term(t: str) -> bool:
    words = t.split()
    if not words or len(t) < 3:
        return False
    if any(w.isdigit() or w in STOPWORDS_S for w in words):
        return False
    if all(w in MODIFIERS_S for w in words):
        return False
    return True
