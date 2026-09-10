"""Try to break a candidate before asking a person to judge it.

The engine is good at finding reasons to believe a term: a query used it, a document mentions it, the
data fits. Nothing in it looks for reasons to disbelieve, and that asymmetry is what filled the review
queue with claims that a minute's checking disposes of: a purchasing term pointed at an order table
whose own label for that code reads "order received" — the opposite side of the business.

This module asks the questions a person asks when they are trying to be wrong rather than right:

  * The source names this code something. Does that name have anything to do with the term?
  * The same term already means something on another table. Is there any reason the two tables should
    share a code system — a join, a shared document — or is this just two columns with one name?
  * Has anyone ever actually said this word, or did a model produce it?

A refutation is written as BLOCKING counter-evidence, so it lowers the score, keeps the candidate out
of certification, and stays visible: the claim is not deleted, it is contradicted, and the reason is
on the record for anyone who thinks the refutation itself is wrong.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from semantic_layer.models import Concept, ConceptStatus, CounterEvidence, Mapping, SchemaProfile, SemanticType
from semantic_layer.normalize import normalize_term

REFUTED = "REFUTED"


def _codes(meaning: Optional[str]) -> dict[str, str]:
    """The code→label table the source writes into its own column description."""
    if not meaning:
        return {}
    return {k.strip(): v.strip() for k, v in re.findall(r"(\w+)\s*=\s*([^,()]+)", meaning)}


def _words(text: str) -> set[str]:
    return {w for w in normalize_term(text or "").split() if len(w) > 2}


def _overlap(term: str, label: str) -> int:
    """How much of the term the source's label actually says.

    Turkish inflects by suffix, so equality is too strict — "alinan"/"alinmis", "satis"/"satislar".
    A shared four-character stem is the cheapest test that survives that and still refuses to call
    "mal" and "sipariş" the same word.
    """
    a, b = _words(term), _words(label)
    n = 0
    for x in a:
        if any(x == y or (len(x) >= 4 and len(y) >= 4 and (x.startswith(y[:4]) or y.startswith(x[:4]))) for y in b):
            n += 1
    return n


class Refuter:
    """Reads the catalog and the query log; writes counter-evidence. Runs no SQL of its own."""

    def __init__(self, store, tenant_id: str, datasource_id: str, profiles: Iterable[SchemaProfile],
                 annotations: Optional[dict] = None) -> None:
        self.store = store
        self.tenant_id = tenant_id
        self.datasource_id = datasource_id
        self.by_entity: dict[str, SchemaProfile] = {}
        for p in profiles:
            self.by_entity.setdefault(p.entity, p)
        self.annotations = annotations or {}
        self._linked: Optional[dict[str, set[str]]] = None
        self._asked: Optional[str] = None

    # ---------------------------------------------------------------- helpers
    def linked(self) -> dict[str, set[str]]:
        """Which entities are joined to which, from the catalog's own relationships.

        Two tables share a code system when they share a document: line rows belong to a header row,
        and measuring that join shows the type code agreeing on every one of a million rows. Two
        tables that are never joined have no such reason; a column name in common is a coincidence.
        """
        if self._linked is None:
            adj: dict[str, set[str]] = {}
            for p in self.by_entity.values():
                for r in p.relationships or []:
                    other = r.get("ref_entity")
                    if other:
                        adj.setdefault(p.entity, set()).add(other)
                        adj.setdefault(other, set()).add(p.entity)
            # Every join anyone has recorded counts, not only the certified ones. The question here
            # is whether there is *any* reason two tables should share a code system; an observed
            # join is such a reason even before somebody has ratified it. Reading only the certified
            # list made a line table and its own header look like strangers, and refuted a returns
            # term on the lines — a mapping the data confirms on a million rows.
            for c in self.store.find_concepts(self.tenant_id, self.datasource_id,
                                              semantic_type=SemanticType.RELATIONSHIP, limit=10000):
                if c.status == ConceptStatus.REJECTED:
                    continue
                for m in self.store.list_mappings(c.id):
                    for v in m.values or []:
                        other = str(v).split(".")[0]
                        if other and m.entity:
                            adj.setdefault(m.entity, set()).add(other)
                            adj.setdefault(other, set()).add(m.entity)
            self._linked = adj
        return self._linked

    def asked(self) -> str:
        """Everything anyone has ever typed, as one normalised haystack."""
        if self._asked is None:
            qs = self.store.recent_questions(self.tenant_id, self.datasource_id, limit=100000)
            self._asked = " || ".join(normalize_term(q) for q in qs)
        return self._asked

    def label_of(self, m: Mapping) -> str:
        prof = self.by_entity.get(m.entity)
        col = prof.column(m.column) if prof and m.column else None
        if col is None:
            return ""
        meaning = col.meaning(self.annotations.get((m.entity, (m.column or "").upper())))
        table = _codes(meaning)
        # Only the codes the source actually defines. Joining the misses gives a string of spaces,
        # which reads as "the source named this" and refutes a mapping the source is silent about —
        # STLINE.TRCODE, whose Logo description enumerates the wrong range entirely.
        return " ".join(x for x in (table.get(str(v), "") for v in (m.values or [])) if x.strip()).strip()

    # ---------------------------------------------------------------- the three questions
    def refute(self, c: Concept, mappings: list[Mapping], support: int,
               rivals: list[tuple[Concept, Mapping, int]]) -> Optional[tuple[str, dict[str, Any]]]:
        if not mappings:
            return None
        m = mappings[0]
        if c.semantic_type == SemanticType.DIMENSION_VALUE and m.values:
            mine = self.label_of(m)
            my_fit = _overlap(c.term, mine)
            near = self.linked().get(m.entity, set())
            for rc, rm, rsupport in rivals:
                if rm.entity == m.entity or sorted(rm.values or []) != sorted(m.values or []):
                    continue
                if rm.entity in near:
                    continue        # joined tables may legitimately share a code system
                fit = _overlap(rc.term, self.label_of(rm))
                if fit > my_fit or (fit == my_fit and rsupport > support):
                    return (REFUTED, {
                        "why": "unlinked_copy",
                        "message": (f"{m.entity} ile {rm.entity} arasında bağlantı yok; aynı kod listesinin "
                                    f"iki tabloda aynı şeyi anlatması için bir sebep yok"),
                        "rival_entity": rm.entity, "rival_fit": fit, "own_fit": my_fit, "support": 3})
            if mine.strip() and my_fit == 0 and any(_overlap(rc.term, self.label_of(rm)) > 0 for rc, rm, _ in rivals):
                return (REFUTED, {
                    "why": "source_label",
                    "message": (f"kaynağın bu koda verdiği ad «{mine.strip()}» — terimle ortak hiçbir "
                                f"kelimesi yok, ve aynı terimin adı tutan başka bir okuması var"),
                    "label": mine.strip(), "support": 3})
        # "Nobody ever asked this" refutes a word a *model* invented, and nothing else. A term that
        # came out of the vendor's documentation and fits the data is unproven, not false — the same
        # distinction the scorer makes, and getting it wrong here would throw away most of the
        # vocabulary this deployment does not have query history for yet.
        origin = {e["evidence_type"] for e in (self.store.concept_bundle(c.id) or {}).get("evidence", [])}
        if "LLM_CANDIDATE" in origin and not (origin & {"VALIDATED_SQL", "ALIAS_BINDING",
                                                        "EXPLICIT_BINDING", "HUMAN_ANNOTATION"}):
            key = normalize_term(c.term)
            if key and key not in self.asked():
                return (REFUTED, {
                    "why": "never_asked",
                    "message": "bu terimi model uydurdu; kimse böyle bir soru sormadı",
                    "support": 3})
        return None

    # ---------------------------------------------------------------- run
    def run(self, statuses: Iterable[str] = (ConceptStatus.CANDIDATE, ConceptStatus.DISCOVERED),
            apply: bool = True) -> list[dict[str, Any]]:
        rows = self.store.review_rows(self.tenant_id, self.datasource_id, list(statuses), limit=100000)
        by_term: dict[tuple[str, str], list[tuple[Concept, Mapping, int]]] = {}
        for x in rows:
            # A reading somebody already threw out is not a rival reading. Letting rejected rows into
            # this pool made two wrong claims refute each other and, worse, refute a right one:
            # "satış iade" on the invoice lines lost to a copy of itself sitting on a cheque table.
            if x["mapping"] is not None and x["concept"].status != ConceptStatus.REJECTED:
                by_term.setdefault((normalize_term(x["concept"].term), x["concept"].semantic_type), []) \
                       .append((x["concept"], x["mapping"], x["evidenceCount"]))
        # a term's rivals include the vocabulary already certified, not just other candidates
        for c in self.store.find_concepts(self.tenant_id, self.datasource_id,
                                          status=ConceptStatus.CERTIFIED, limit=100000):
            for m in self.store.list_mappings(c.id):
                by_term.setdefault((normalize_term(c.term), c.semantic_type), []).append((c, m, 99))

        out = []
        for x in rows:
            c, m = x["concept"], x["mapping"]
            if m is None:
                continue
            if c.explain.get("human_certified_by") or c.explain.get("human_rejected_by"):
                continue        # a person has ruled; refuting is not the engine's to do
            rivals = [r for r in by_term.get((normalize_term(c.term), c.semantic_type), []) if r[0].id != c.id]
            verdict = self.refute(c, [m], x["evidenceCount"], rivals)
            if verdict is None:
                continue
            kind, payload = verdict
            out.append({"concept": c.term, "id": c.id, "entity": m.entity, "column": m.column,
                        "values": m.values, **payload})
            if apply:
                self.store.add_counter_evidence(CounterEvidence(
                    c.id, f"refute:{payload['why']}", kind, payload=payload, severity="BLOCKING"))
        return out
