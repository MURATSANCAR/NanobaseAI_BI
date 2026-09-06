"""Runtime Resolver — question → SemanticQuery using CERTIFIED catalog entries only.

No vectors, no LLM: normalised n-gram lookup (exact / stem / synonym), deterministic temporal parsing,
explicit code hints, group-by / limit / order detection, and an explanation trail ("why this mapping").
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Optional

from semantic_layer.history.question_facts import GENERIC_S, extract_question_facts
from semantic_layer.models import (
    Concept,
    Mapping,
    ResolvedSlot,
    SchemaProfile,
    SemanticQuery,
    SemanticType,
    TemporalSlot,
)
from semantic_layer.normalize import METRIC_VOCAB_S, MODIFIERS_S, STOPWORDS_S, fold, stem, tokenize
from semantic_layer.runtime.temporal import describe
from semantic_layer.store.catalog_store import CatalogStore

# Words the LLM handles from schema context; never reported as "unresolved" (they are entities, not values).
_ENTITY_WORDS = frozenset(stem(w) for w in "fatura musteri cari tedarikci kitap urun malzeme stok siparis satir hareket belge kayit firma sirket sube depo".split())
_TIME_WORDS = frozenset(stem(w) for w in "gun gunde gunler gunluk ay ayda aylar aylik ayin ayindaki yil yilda yillik hafta haftada haftalik ceyrek ceyreklik donem donemde donemsel tarih bugun dun son gecen onceki sonraki ilk itibaren beri bu yana".split())
_GROUP_MARKERS = re.compile(r"\b(bazinda|bazli|gore|kiriliminda|kirilimi|dagilimi|dagilim|itibariyla)\b")
_NUMERIC_TYPES = ("int", "float", "double", "decimal", "numeric", "real", "money", "smallmoney", "bigint", "smallint", "tinyint")
_AVG_WORDS = frozenset(stem(w) for w in "ortalama ortalamasi".split())
# A comparison cue turns several value sets on one column into a pivot instead of a contradiction.
_COMPARE_CUE = re.compile(r"\b(karsilastir|karsilastirma|kiyasla|kiyaslama|vs|ayri ayri|yan yana|ikisini)\b")


class SemanticResolver:
    def __init__(self, store: CatalogStore, tenant_id: str, datasource_id: str, profiles: list[SchemaProfile], *, default_temporal: Optional[TemporalSlot] = None):
        self.store = store
        self.tenant_id = tenant_id
        self.datasource_id = datasource_id
        self.profiles = profiles
        self.by_entity = {p.entity: p for p in profiles}
        self.column_names = {c.name.upper() for p in profiles for c in p.columns}
        self.default_temporal = default_temporal
        self._value_index: dict[str, list[tuple[str, str, str]]] = {}
        self._measure_columns: dict[tuple[str, str], tuple[str, str]] = {}

    # ------------------------------------------------------------------ public
    def resolve(self, question: str, today: Optional[date] = None) -> SemanticQuery:
        qf = extract_question_facts(question)
        index = self.store.certified_index(self.tenant_id, self.datasource_id)
        self._refresh_column_caches(index)
        latest = self.store.latest_version(self.tenant_id, self.datasource_id)
        sq = SemanticQuery(question=question, tenant_id=self.tenant_id, datasource_id=self.datasource_id, catalog_version=latest["version"] if latest else 0)
        if today is not None:
            from semantic_layer.runtime.temporal import parse_temporal

            qf.temporal, qf.grain = parse_temporal(question, today)

        # 1) greedy longest-match over clause-local n-grams
        consumed: set[int] = set()
        hits: list[ResolvedSlot] = []
        for i, j, key in sorted(qf.terms, key=lambda t: (-(t[1] - t[0]), t[0])):
            if any(k in consumed for k in range(i, j)):
                continue
            senses = index.get(key)
            if not senses:
                continue
            slot = self._slot_from_senses(key, qf.surface.get(key, key), senses, (i, j))
            if slot is None:
                continue
            hits.append(slot)
            consumed.update(range(i, j))

        # 2) explicit physical codes in the question: "(TRCODE 8)" / "TRCODE 7,8,9"
        for col, values in qf.explicit_codes:
            if col in self.column_names:
                entity = self._entity_for_column(col, hits)
                if entity:
                    prof = self.by_entity[entity]
                    m = Mapping(concept_id="", entity=entity, table_pattern=prof.table_pattern, column=col, operator="IN", values=list(values))
                    hits.append(ResolvedSlot(term=f"{col} {','.join(values)}", semantic_type=SemanticType.DIMENSION_VALUE, status="EXPLICIT", mapping=m, confidence=1.0, explain={"why": "kullanıcı fiziksel kodu sorunun içinde verdi"}))
                    for k, tok in enumerate(qf.tokens):
                        if tok.upper() == col or tok in values:
                            consumed.add(k)

        # 2b) profile-backed literal values: a token that *is* a value of a certified column
        #     ("KITAPCI" ∈ CLCARD.SPECODE2 profile) — the column meaning is certified, the value is observed.
        literal: dict[tuple[str, str], list[tuple[int, int, str]]] = {}
        for i, j, _ in sorted(qf.terms, key=lambda t: (-(t[1] - t[0]), t[0])):
            if any(k in consumed for k in range(i, j)):
                continue
            phrase = " ".join(qf.tokens[i:j])
            for entity, column, raw in self._value_index.get(phrase, []):
                literal.setdefault((entity, column), []).append((i, j, raw))
                consumed.update(range(i, j))
                break
        for (entity, column), found in literal.items():
            prof = self.by_entity[entity]
            values = sorted({raw for _, _, raw in found})
            span = (min(i for i, _, _ in found), max(j for _, j, _ in found))
            m = Mapping(concept_id="", entity=entity, table_pattern=prof.table_pattern, column=column, operator="IN", values=values)
            hits.append(ResolvedSlot(term=", ".join(values), semantic_type=SemanticType.DIMENSION_VALUE, status="PROFILE", mapping=m, confidence=0.9,
                                     explain={"why": f"değer profilde gözlendi: {entity}.{column}", "source": "profile"}, span=span))

        # 2c) noun-modifier metrics: "satış faturaları" names a document, not a measure — drop the
        #     metric reading when the next token is an entity word.
        for slot in list(hits):
            if slot.semantic_type != SemanticType.METRIC or slot.span[1] - slot.span[0] != 1:
                continue
            nxt = qf.tokens[slot.span[1]] if slot.span[1] < len(qf.tokens) else ""
            if stem(nxt) in _ENTITY_WORDS:
                hits.remove(slot)
                sq.explanation.append(f"'{slot.term} {nxt}' bir belge türü olarak okundu, ölçü değil")

        sq.slots = hits
        # 3) primary entity → choose among alternatives on other slots
        primary = self._primary_entity(hits)
        for s in hits:
            alts = s.explain.get("alternatives") or []
            if alts and primary and s.mapping and s.mapping.entity != primary:
                for alt in alts:
                    if alt["entity"] == primary:
                        s.mapping = Mapping(concept_id=alt["conceptId"], entity=alt["entity"], table_pattern=alt["tablePattern"], column=alt.get("column"), operator=alt.get("operator"), values=list(alt.get("values") or []), formula=alt.get("formula"), extra=alt.get("extra") or {})
                        s.concept_id = alt["conceptId"]
                        s.explain["chosen_by"] = f"primary entity {primary}"
                        break

        # 4) group-by: "<term> bazında / göre", or a named column that also carries value filters
        #    ("KITAPCI, E-TICARET ve DAGITICI kanalları için …" → filter on those channels, broken down by channel)
        folded_tokens = [stem(t) for t in qf.tokens]
        for k, tok in enumerate(qf.tokens):
            if _GROUP_MARKERS.fullmatch(stem(tok)) or _GROUP_MARKERS.fullmatch(tok):
                for slot in hits:
                    if slot.span and slot.span[1] == k and slot.semantic_type == SemanticType.COLUMN and slot not in sq.group_by:
                        sq.group_by.append(slot)
                        slot.explain["role"] = "group_by"
        filtered_columns = {(s_.mapping.entity, (s_.mapping.column or "").upper()) for s_ in hits if s_.semantic_type == SemanticType.DIMENSION_VALUE and s_.mapping}
        for slot in hits:
            if slot.semantic_type != SemanticType.COLUMN or slot in sq.group_by or not slot.mapping:
                continue
            if (slot.mapping.entity, (slot.mapping.column or "").upper()) in filtered_columns:
                sq.group_by.append(slot)
                slot.explain["role"] = "group_by"
                sq.explanation.append(f"'{slot.term}' hem filtre hem kırılım: sorulan değerler bu kolonda")

        # 4b) composed metric: certified measure column + aggregation word, when no certified metric matched
        #     ("iade tutarı" = 'iade' filtresi + 'satış tutarı' ölçü kolonu → SUM(INVOICE.NETTOTAL))
        if not any(s_.semantic_type == SemanticType.METRIC for s_ in hits) and (sq.filters or sq.group_by):
            composed = self._compose_metric(qf, hits, primary, consumed)
            if composed is not None:
                hits.append(composed)
                sq.slots = hits

        # 5) temporal
        sq.temporal = list(qf.temporal)
        sq.grain = qf.grain
        if not sq.temporal and self.default_temporal is not None:
            sq.temporal = [self.default_temporal]
            sq.explanation.append(f"dönem belirtilmedi → varsayılan {self.default_temporal.primitive} uygulandı")
        for t in sq.temporal:
            sq.explanation.append(describe(t))

        # 6) unresolved content words
        for k, tok in enumerate(qf.tokens):
            if k in consumed:
                continue
            st = folded_tokens[k]
            if st in STOPWORDS_S or st in MODIFIERS_S or st in METRIC_VOCAB_S or st in _ENTITY_WORDS or tok.isdigit():
                continue
            if st in _TIME_WORDS or any(tok in tokenize(t.text) for t in qf.temporal):
                continue
            if tok.upper() in self.column_names or _GROUP_MARKERS.fullmatch(st) or _GROUP_MARKERS.fullmatch(tok):
                continue
            if len(tok) < 3:
                continue
            if tok not in sq.unresolved:
                sq.unresolved.append(tok)

        # 7) conflicting filters: two different value sets ANDed on one column (no comparison cue)
        by_col: dict[tuple[str, str], set[frozenset[str]]] = {}
        for s_ in hits:
            if s_.semantic_type == SemanticType.DIMENSION_VALUE and s_.mapping and s_.mapping.column:
                by_col.setdefault((s_.mapping.entity, s_.mapping.column.upper()), set()).add(frozenset(s_.mapping.values))
        comparison = bool(_COMPARE_CUE.search(fold(question)))
        for (entity, column), sets in by_col.items():
            if len(sets) > 1 and not comparison:
                sq.conflicts.append(f"{entity}.{column}")
                sq.explanation.append(f"aynı kolonda ({entity}.{column}) birbiriyle çelişen değer kümeleri istendi: " + " / ".join(", ".join(sorted(x)) for x in sets))
            elif len(sets) > 1:
                sq.explanation.append(f"karşılaştırma istendi: {entity}.{column} üzerinde " + " / ".join(", ".join(sorted(x)) for x in sets) + " ayrı sütunlara açılacak")

        sq.limit = qf.limit
        sq.order_desc = qf.order_desc
        for s in hits:
            sq.explanation.append(self._why(s))
        if sq.unresolved:
            sq.explanation.append("katalogda karşılığı olmayan terimler: " + ", ".join(sq.unresolved))
        return sq

    def explain_term(self, term: str) -> dict[str, Any]:
        key = " ".join(stem(t) for t in tokenize(term))
        index = self.store.certified_index(self.tenant_id, self.datasource_id)
        senses = index.get(key) or []
        out = []
        for c, maps in senses:
            out.append({"concept": c.to_dict(), "mappings": [m.to_dict() for m in maps], "evidence": [{"type": e.evidence_type, "support": e.support_count, "source": e.source_id} for e in self.store.list_evidence(c.id)]})
        candidates = [c.to_dict() for c in self.store.find_concepts(self.tenant_id, self.datasource_id, normalized_term=key) if c.status != "CERTIFIED"]
        return {"term": term, "normalized": key, "certified": out, "otherSenses": candidates}

    # ------------------------------------------------------------------ helpers
    def _slot_from_senses(self, key: str, surface: str, senses: list[tuple[Concept, list[Mapping]]], span: tuple[int, int]) -> Optional[ResolvedSlot]:
        usable = [(c, maps) for c, maps in senses if maps]
        if not usable:
            return None
        # prefer METRIC > DIMENSION_VALUE > COLUMN > others; within type, highest confidence
        order = {SemanticType.METRIC: 0, SemanticType.DIMENSION_VALUE: 1, SemanticType.COLUMN: 2, SemanticType.ENTITY: 3, SemanticType.TEMPORAL: 4, SemanticType.DEFAULT_FILTER: 9, SemanticType.RELATIONSHIP: 9}
        usable.sort(key=lambda cm: (order.get(cm[0].semantic_type, 5), -cm[0].confidence))
        c, maps = usable[0]
        if c.semantic_type in (SemanticType.DEFAULT_FILTER, SemanticType.RELATIONSHIP):
            return None
        alternatives = []
        for c2, maps2 in usable[1:]:
            if c2.semantic_type == c.semantic_type:
                for m2 in maps2:
                    alternatives.append({"conceptId": c2.id, "entity": m2.entity, "tablePattern": m2.table_pattern, "column": m2.column, "operator": m2.operator, "values": m2.values, "formula": m2.formula, "extra": m2.extra, "confidence": c2.confidence})
        ev = self.store.list_evidence(c.id)
        support = c.explain.get("support") or {}
        return ResolvedSlot(
            term=surface,
            semantic_type=c.semantic_type,
            status="CERTIFIED",
            concept_id=c.id,
            mapping=maps[0],
            confidence=c.confidence,
            explain={"normalized": key, "sense": c.sense_id, "version": c.version, "support": support, "evidence_types": sorted({e.evidence_type for e in ev}), "alternatives": alternatives},
            span=span,
        )

    def _refresh_column_caches(self, index: dict[str, list[tuple[Concept, list[Mapping]]]]) -> None:
        """Value literals and measure columns come only from CERTIFIED COLUMN concepts: a value is
        offered to the resolver just when someone has already named the column it lives in."""
        version = self.store.latest_version(self.tenant_id, self.datasource_id)
        key = (version or {}).get("version", 0), len(index)
        if getattr(self, "_cache_key", None) == key:
            return
        values: dict[str, list[tuple[str, str, str]]] = {}
        measures: dict[tuple[str, str], tuple[str, str]] = {}
        seen: set[tuple[str, str]] = set()
        for senses in index.values():
            for concept, maps in senses:
                if concept.semantic_type != SemanticType.COLUMN:
                    continue
                for m in maps:
                    prof = self.by_entity.get(m.entity)
                    col = prof.column(m.column) if prof and m.column else None
                    if col is None or (m.entity, col.name, concept.normalized_term) in seen:
                        continue
                    seen.add((m.entity, col.name, concept.normalized_term))
                    if any(t in col.data_type.lower() for t in _NUMERIC_TYPES) and not col.is_primary_key and not col.ref_entity:
                        head = concept.normalized_term.split()[-1]
                        measures.setdefault((m.entity, head), (col.name, concept.term))
                    observed = [str(v) for v, _ in col.top_values] if col.is_enum() else []
                    documented = [str(v) for v in (concept.explain.get("documented_values") or [])]
                    for raw in dict.fromkeys(observed + documented):
                        token = fold(raw)
                        if len(token) >= 3 and not token.isdigit() and token not in STOPWORDS_S and not token.isnumeric():
                            values.setdefault(token, []).append((m.entity, col.name, raw))
        self._value_index = values
        self._measure_columns = measures
        self._cache_key = key

    def _compose_metric(self, qf: Any, hits: list[ResolvedSlot], primary: Optional[str], consumed: set[int]) -> Optional[ResolvedSlot]:
        entity = primary or next((s_.mapping.entity for s_ in hits if s_.mapping), None)
        prof = self.by_entity.get(entity or "")
        if prof is None:
            return None
        agg = "AVG" if any(stem(t) in _AVG_WORDS for t in qf.tokens) else "SUM"
        for k, tok in enumerate(qf.tokens):
            head = stem(tok)
            if head not in METRIC_VOCAB_S:
                continue
            found = self._measure_columns.get((entity, head))
            if not found:
                continue
            column, source_term = found
            m = Mapping(concept_id="", entity=entity, table_pattern=prof.table_pattern, formula=f"{agg}({entity}.{column})", extra={"composed_from": source_term})
            phrase = " ".join(qf.tokens[max(0, k - 1) : k + 1])
            return ResolvedSlot(
                term=phrase,
                semantic_type=SemanticType.METRIC,
                status="COMPOSED",
                mapping=m,
                confidence=0.8,
                explain={"why": f"'{tok}' ölçü kelimesi + sertifikalı '{source_term}' kolonu → {agg}({entity}.{column})", "composed_from": source_term},
                span=(k, k + 1),
            )
        return None

    def _entity_for_column(self, col: str, hits: list[ResolvedSlot]) -> Optional[str]:
        owners = [p.entity for p in self.profiles if p.column(col)]
        if len(owners) == 1:
            return owners[0]
        primary = self._primary_entity(hits)
        if primary in owners:
            return primary
        if "INVOICE" in owners:
            return "INVOICE"
        return owners[0] if owners else None

    @staticmethod
    def _primary_entity(hits: list[ResolvedSlot]) -> Optional[str]:
        for s in hits:
            if s.semantic_type == SemanticType.METRIC and s.mapping:
                return s.mapping.entity
        counts: dict[str, int] = {}
        for s in hits:
            if s.mapping and s.semantic_type == SemanticType.DIMENSION_VALUE:
                counts[s.mapping.entity] = counts.get(s.mapping.entity, 0) + 1
        return max(counts, key=counts.get) if counts else None

    @staticmethod
    def _why(s: ResolvedSlot) -> str:
        m = s.mapping
        if m is None:
            return f"'{s.term}' → çözümlenemedi"
        sup = s.explain.get("support") or {}
        target = m.formula if m.formula else (f"{m.entity}.{m.column} {m.operator} ({', '.join(m.values)})" if m.values else f"{m.entity}.{m.column}")
        why = f"'{s.term}' → {target} [{s.status}"
        if sup:
            why += f", {sup.get('validated_queries', 0)} doğrulanmış sorgu, doküman {sup.get('doc', 0)}, insan {sup.get('human', 0)}"
        return why + "]"


__all__ = ["SemanticResolver", "GENERIC_S", "fold"]
