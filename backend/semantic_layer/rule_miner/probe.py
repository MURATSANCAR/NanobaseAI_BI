"""Refute, then decide.

A candidate is a claim about the data: 'faturalar' means CLFLINE.MODULENR = 4. The claim is run
against the live database before anything is written — a value no row has, a formula the server
rejects, a column the copy lacks all fall here. What survives is written with the view as evidence;
the policy agreed on 2026-09-16 certifies what the business itself wrote (a consultant's view, a
user's saved view) and queues everything else for the approval screen.
"""
from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

from semantic_layer.models import ConceptStatus, Evidence, EvidenceType, Mapping, SemanticType
from semantic_layer.normalize import normalize_term
from semantic_layer.rule_miner.common import Candidate, Catalog, is_generic, spoken_variants, sql_values

log = logging.getLogger(__name__)

SELF_CERTIFYING_KINDS = {"label_map", "column_alias", "expression_alias", "saved_query", "user_query"}


@dataclass
class Grouped:
    """One claim, however many views make it."""
    cand: Candidate
    sources: list[str] = field(default_factory=list)
    kinds: set[str] = field(default_factory=set)


def group(cands: Iterable[Candidate]) -> list[Grouped]:
    by: dict[tuple[str, str, str], Grouped] = {}
    for c in cands:
        k = (normalize_term(c.term), c.semantic_type, c.key())
        g = by.get(k)
        if g is None:
            g = by[k] = Grouped(c)
        if c.source not in g.sources:
            g.sources.append(c.source)
        g.kinds.add(c.kind)
    return list(by.values())


def probe_sql(c: Candidate, catalog: Catalog, prof) -> Optional[str]:
    phys = catalog.physical_for(prof)

    def spell(text: str) -> str:
        # ENTITY.COLUMN references → the column as the source spells it
        return re.sub(re.escape(c.entity) + r"\.([A-Za-z_][A-Za-z0-9_]*)", lambda m: "[" + Catalog.spelled(prof, m.group(1)) + "]", text)

    if c.semantic_type == SemanticType.COLUMN:
        return f"SELECT TOP 1 [{Catalog.spelled(prof, c.column)}] FROM {phys}"
    if c.semantic_type == SemanticType.DIMENSION_VALUE:
        where = [f"[{Catalog.spelled(prof, c.column)}] {c.operator} ({sql_values(c.values)})"]
        for cond in c.conditions:
            where.append(spell(cond))
        return f"SELECT COUNT(*) AS n FROM {phys} WHERE " + " AND ".join(where)
    if c.semantic_type == SemanticType.METRIC and c.formula:
        return f"SELECT {spell(c.formula)} AS v FROM {phys}"
    return None


def refute(g: Grouped, catalog: Catalog, connector, *, timeout_note: dict[str, Any]) -> tuple[bool, str, int]:
    """(passes, reason, ms). Passing means the claim has rows / evaluates; nothing more."""
    prof = catalog.by_pattern.get(g.cand.table_pattern.upper())
    if prof is None:
        return False, "tablo katalogda yok", 0
    sql = probe_sql(g.cand, catalog, prof)
    if sql is None:
        return False, "sorgulanamaz aday", 0
    t = time.perf_counter()
    try:
        cols, rows, _ = connector.execute(sql, 5)
    except Exception as e:  # noqa: BLE001
        return False, f"sunucu reddetti: {str(e)[:160]}", int((time.perf_counter() - t) * 1000)
    ms = int((time.perf_counter() - t) * 1000)
    if g.cand.semantic_type == SemanticType.DIMENSION_VALUE:
        n = rows[0]["n"] if rows else 0
        if not n and g.kinds & {"saved_query", "user_query"}:
            # A saved view is a definition the business keeps whether or not anything is in that
            # state today ("YK onayında bekleyen sözleşmeler" is empty between approvals). The filter
            # ran, so its columns and values are real; the count is noted, not held against it.
            return True, "şu an 0 kayıt", ms
        return (n or 0) > 0, ("" if n else "bu değeri taşıyan satır yok"), ms
    if g.cand.semantic_type == SemanticType.METRIC:
        v = rows[0]["v"] if rows else None
        return v is not None, ("" if v is not None else "formül boş döndü"), ms
    return True, "", ms


def names_its_own_entity(g: Grouped, catalog: Catalog) -> bool:
    """'fiyat listesi' → new_fiyatlistesi (statecode 0): the view is named after the table it lists.
    That is the table's name, not a business state — certified as a filter it claims every question
    that says the table's name, in either database ("fiyat listesinde tanımlı fiyatın altında kesilen
    faturalar" is about the ERP's price list). Left to a person."""
    from semantic_layer.normalize import stem, tokenize
    prof = catalog.by_pattern.get(g.cand.table_pattern.upper())
    if prof is None or g.cand.kind not in ("saved_query", "user_query"):
        return False
    words = {stem(w) for w in tokenize(g.cand.term)}
    title = (prof.description or "").split(".")[0]
    base = re.sub(r"(?i)^(new_|lg_)|base$", "", prof.table_name or "")
    own = {stem(w) for w in tokenize(title)} | {stem(w) for w in tokenize(re.sub(r"(?<=[a-z])(?=[A-Z])", " ", base))}
    return bool(words) and words <= own


def decide(g: Grouped, passed: bool, *, conflict: bool, ambiguous: bool = False, entity_name: bool = False) -> str:
    """CERTIFIED for the business's own rule that survived refutation and contradicts no certified term;
    CANDIDATE (approval screen) otherwise. A generic word ("tutar"), a word the mined views themselves
    use for several different things ("fiş no" on five tables), or a column alias a single view coined
    is left to a person: certified, each would claim every question that says it."""
    if not passed or conflict or ambiguous or entity_name or is_generic(g.cand.term):
        return ConceptStatus.CANDIDATE
    if g.kinds <= {"column_alias"} and len(g.sources) < 2:
        return ConceptStatus.CANDIDATE
    if len(g.cand.term.split()) == 1 and len(g.sources) < 3:
        # One word, one or two views: "üretimler", "bekleyenler", "credit". Stemmed, such a word meets
        # every question that says it ("üretim emirleri") and drags in a filter nobody asked for. A
        # label several views agree on ("tamamlandı" ×12) is a word the business really uses that way.
        return ConceptStatus.CANDIDATE
    if g.kinds & SELF_CERTIFYING_KINDS:
        return ConceptStatus.CERTIFIED
    return ConceptStatus.CANDIDATE


def write(store, engine, settings, g: Grouped, status: str, reason: str, ms: int) -> dict[str, Any]:
    c = g.cand
    mapping = Mapping(concept_id="", entity=c.entity, table_pattern=c.table_pattern, column=c.column,
                      operator=c.operator, values=list(c.values), formula=c.formula,
                      extra={"conditions": list(c.conditions)} if c.conditions else {})
    concept, created = store.upsert_concept(settings.tenant_id, settings.datasource_id, c.term, c.semantic_type,
                                            mapping=mapping, status=ConceptStatus.CANDIDATE,
                                            synonyms=spoken_variants(c.term) or None)
    if not created and spoken_variants(c.term):
        for syn in spoken_variants(c.term):
            if syn not in (concept.synonyms or []):
                store.add_synonym(concept.id, syn)
    ev_type = EvidenceType.ALIAS_BINDING if c.kind in ("column_alias", "expression_alias") else EvidenceType.DOC
    store.add_evidence(Evidence(concept.id, ev_type, f"rule-miner:{c.kind}", support_count=len(g.sources),
                                payload={"sources": g.sources[:20], "kind": c.kind, "probe_ms": ms}))
    if status == ConceptStatus.CERTIFIED:
        store.add_evidence(Evidence(concept.id, EvidenceType.EXECUTION, "rule-miner:probe", payload={"ms": ms}))
        if concept.status != ConceptStatus.CERTIFIED:
            engine.human_certify(concept.id, "rule-miner", f"kaynağın kendi kuralı ({', '.join(g.sources[:3])}); canlı veride doğrulandı")
    return {"concept": concept.id, "created": created, "status": status}


def conflicts(store, settings, g: Grouped) -> bool:
    """The same word already certified to a different meaning: a person must choose."""
    from semantic_layer.models import ConceptStatus as CS
    for c in store.find_concepts(settings.tenant_id, settings.datasource_id, normalized_term=normalize_term(g.cand.term),
                                 status=CS.CERTIFIED):
        for m in store.list_mappings(c.id):
            if m.key() != Mapping(concept_id="", entity=g.cand.entity, table_pattern=g.cand.table_pattern, column=g.cand.column,
                                  operator=g.cand.operator, values=list(g.cand.values), formula=g.cand.formula).key():
                return True
    return False


def run(groups: list[Grouped], catalog: Catalog, connector_for: Callable[[Candidate], Any], store, engine, settings,
        *, apply: bool, report: list[dict[str, Any]]) -> dict[str, int]:
    tally: dict[str, int] = defaultdict(int)
    meanings: dict[str, set[str]] = defaultdict(set)
    for g in groups:
        meanings[normalize_term(g.cand.term)].add(g.cand.entity)
    for g in groups:
        conn = connector_for(g.cand)
        if conn is None:
            tally["no_connector"] += 1
            continue
        passed, why, ms = refute(g, catalog, conn, timeout_note={})
        conflict = conflicts(store, settings, g) if passed else False
        ambiguous = len(meanings[normalize_term(g.cand.term)]) > 1
        status = decide(g, passed, conflict=conflict, ambiguous=ambiguous, entity_name=names_its_own_entity(g, catalog)) if passed else "REFUTED"
        row = {"term": g.cand.term, "type": g.cand.semantic_type, "key": g.cand.key(), "kind": sorted(g.kinds),
               "sources": len(g.sources), "passed": passed, "why": why, "conflict": conflict, "ambiguous": ambiguous, "status": status, "ms": ms}
        report.append(row)
        tally[status] += 1
        if apply and passed:
            write(store, engine, settings, g, status, why, ms)
    return dict(tally)
