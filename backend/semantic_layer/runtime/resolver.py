"""Runtime Resolver — question → SemanticQuery using CERTIFIED catalog entries only.

No vectors, no LLM: normalised n-gram lookup (exact / stem / synonym), deterministic temporal parsing,
explicit code hints, group-by / limit / order detection, and an explanation trail ("why this mapping").
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Callable, Optional

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
from semantic_layer.normalize import (
    METRIC_VOCAB_S,
    MODIFIERS_S,
    STOPWORDS_S,
    cardinal,
    derived_forms,
    fold,
    is_domain_candidate,
    is_light_verb,
    is_negative,
    is_inflection_of,
    is_participle,
    short_root,
    stem,
    tokenize,
    verb_root,
)
from semantic_layer.history.question_facts import GENERIC_S
from semantic_layer.runtime.temporal import describe
from semantic_layer.store.catalog_store import CatalogStore

# Words the LLM handles from schema context; never reported as "unresolved" (they are entities, not values).
_ENTITY_WORDS = frozenset(stem(w) for w in "fatura musteri cari tedarikci kitap urun malzeme stok siparis satir hareket belge kayit firma sirket sube depo".split())
_TIME_WORDS = frozenset(stem(w) for w in "gun gunde gunler gunluk ay ayda aylar aylik ayin ayindaki yil yilda yillik hafta haftada haftalik ceyrek ceyreklik donem donemde donemsel tarih bugun dun son gecen onceki sonraki ilk itibaren beri bu yana".split())
_ORDINAL_WORDS = frozenset(stem(w) for w in "birinci ikinci ucuncu dorduncu besinci altinci yedinci sekizinci dokuzuncu onuncu".split())
_GROUP_MARKERS = re.compile(r"\b(bazinda|bazli|gore|kiriliminda|kirilimi|dagilimi|dagilim|itibariyla)\b")
_NUMERIC_TYPES = ("int", "float", "double", "decimal", "numeric", "real", "money", "smallmoney", "bigint", "smallint", "tinyint")
_AVG_WORDS = frozenset(stem(w) for w in "ortalama ortalamasi".split())
# A comparison cue turns several value sets on one column into a pivot instead of a contradiction.
_COMPARE_CUE = re.compile(r"\b(karsilastir|karsilastirma|kiyasla|kiyaslama|vs|ayri ayri|yan yana|ikisini)\b")
# "kaç fatura", "fatura sayısı", "kaç tane" — the question asks how many rows, not how much value.
_COUNT_CUE = re.compile(r"\b(kac|kacar|tane|adedi|adet|sayisi|sayilari|sayilariyla|sayi)\b")
# A movement word turns one number into a series: the answer has to be broken down over time.
# Cue words are recognised through the morphology, not by allowing any letters to follow. A tail of
# "up to six more letters" after "trend" also spells trendyol, a marketplace: the question then picked
# up a monthly breakdown nobody asked for, and the brand disappeared from it without a word — read as
# grammar, so never reported as a term the catalog could not place. Inflection is what stem() is for.
_TREND_WORDS = frozenset(
    "artis artiyor artan azalis azaliyor dusus dusuyor duserken buyume buyuyor kuculuyor "
    "gerileme trend gidisat seyir".split()
)
_TREND_PHRASES = re.compile(r"\b(?:ay ay|gun gun|yil yil|hafta hafta|zaman icinde|zamanla)\b")


def _is_trend_cue(token: str) -> bool:
    f = fold(token)
    if f in _TREND_WORDS or short_root(f) in _TREND_WORDS:
        return True
    return any(is_inflection_of(f, w) for w in _TREND_WORDS)


def _asks_for_a_trend(question: str) -> bool:
    folded = fold(question)
    return bool(_TREND_PHRASES.search(folded)) or any(_is_trend_cue(t) for t in tokenize(question))
# Ranking cues that make a following number a top-N rather than a value.
_RANK_CUE = frozenset("en ilk top bastaki basta".split())
_WHICH = frozenset("hangi hangisi hangileri kim kimler kimin kimden".split())
# "payı yüzde kaç" asks for a share: a plain total is a different answer, not a rounder one.
_SHARE_CUE = re.compile(r"\b(pay|payi|payin|paylari|paylarini|yuzde|yuzdesi|yuzdelik)\b")


def _parse_condition(key: str) -> Optional[tuple[tuple[str, str], set[str]]]:
    """'INVOICE.TRCODE IN (7, 8, 9)' → (('INVOICE', 'TRCODE'), {'7', '8', '9'})."""
    m = re.match(r"^(\w+)\.(\w+)\s+IN\s+\((.*)\)$", key.strip())
    if not m:
        return None
    ent, col, vals = m.groups()
    return (ent, col.upper()), {v.strip().strip("'") for v in vals.split(",") if v.strip()}


#: "iyi mi", "nasıl gidiyor", "ne durumda" — asking after a state of affairs rather than a figure.
#: On its own this means nothing: "yurtdışı satışlarımız geçen yıla göre nasıl?" asks the same way and
#: names its measure. It only decides anything where no measure was placed at all.
_HOW_ARE_THINGS = ("iyi", "kotu", "nasil", "durum", "gidiyor", "gidiyoruz", "ne alemde")


def _asks_how_things_are(tokens) -> bool:
    return any(stem(t) in _HOW_ARE_THINGS or t in _HOW_ARE_THINGS for t in tokens)


def _rooted(key: str) -> str:
    """A term reduced to the roots of its words, so an inflected form finds the same entry."""
    return " ".join(short_root(t) for t in key.split())


class SemanticResolver:
    def __init__(self, store: CatalogStore, tenant_id: str, datasource_id: str, profiles: list[SchemaProfile], *, default_temporal: "Optional[TemporalSlot] | Callable[[], Optional[TemporalSlot]]" = None, conventions: Any = None):
        from semantic_layer.conventions import Conventions

        self.store = store
        self.tenant_id = tenant_id
        self.datasource_id = datasource_id
        self.profiles = profiles
        # An entity can span several physical tables — one fiscal period each. Keep them all, so a
        # question about a past year is judged against everything this deployment holds rather than
        # against whichever table happened to be profiled last.
        # The certified vocabulary keyed by the roots of its own terms, rebuilt when the catalog is.
        self._roots_for: Optional[int] = None
        self._roots: dict = {}
        self.tables_of: dict[str, list[SchemaProfile]] = {}
        for prof in profiles:
            self.tables_of.setdefault(prof.entity, []).append(prof)
        self.by_entity = {e: ps[0] for e, ps in self.tables_of.items()}
        self.column_names = {c.name.upper() for p in profiles for c in p.columns}
        # Either a fixed period or something that decides one per question. A service started in
        # December must not still be answering "last month" against last year in January, and a fixed
        # value frozen at startup does exactly that — silently, which is the worst way to be wrong.
        self.default_temporal = default_temporal
        self.conventions = conventions or Conventions.from_profiles(profiles)
        self._value_index: dict[str, list[tuple[str, str, str]]] = {}
        self._edges: dict[str, set[str]] = {}
        self._related_cache: dict[str, set[str]] = {}
        self._fk_edges: dict[str, set[str]] = {}      # yönlü: hangi varlıktan hangisine tek satır gidilir
        self._fk_cache: dict[str, set[str]] = {}
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

        # 0) report frame: "1. kolon kanal adı 2. kolon yıl" — the shape of the deliverable, not the
        #     subject. First, and before anything looks a token up: a list marker is a fact about how
        #     the sentence is written, and in this catalog "2" and "3" are also TRCODE values, so a
        #     later pass reads the item numbers as a returns filter and the question quietly narrows.
        consumed: set[int] = set()
        frame_idx, projection = self._report_frame(qf, consumed, index)
        if frame_idx:
            consumed.update(frame_idx)
            for k in sorted(frame_idx):
                if qf.tokens[k] not in sq.ignored and not qf.tokens[k].isdigit():
                    sq.ignored.append(qf.tokens[k])   # izde görünsün: yutuldu ama saklanmadı
            sq.projection = projection
            if projection:
                sq.explanation.append("istenen kolonlar (sorulan sıra): " + " | ".join(projection))

        # 1) greedy longest-match over clause-local n-grams
        hits: list[ResolvedSlot] = []
        for i, j, key in sorted(qf.terms, key=lambda t: (-(t[1] - t[0]), t[0])):
            if any(k in consumed for k in range(i, j)):
                continue
            # The key reaching this point has already been stemmed, and stemming an inflected word
            # does not land where stemming its root does — "kanal" stems to "kanal" and "kanala" to
            # "kana", so the two never meet. The root is taken from what the person actually wrote.
            senses = index.get(key) or self._by_root(index).get(_rooted(qf.surface.get(key, key)))
            if not senses:
                continue
            slot = self._slot_from_senses(key, qf.surface.get(key, key), senses, (i, j))
            if slot is None:
                continue
            hits.append(slot)
            consumed.update(range(i, j))

        # 2) explicit physical codes in the question: "(TRCODE 8)" / "TRCODE 7,8,9"
        for col, values in qf.explicit_codes:
            if col not in self.column_names:
                continue
            # "…net ciro 3. kolon…": the number is the third item of a list, and CIRO happens to be a
            # column somewhere in the schema. Read as a code it silently adds CIRO = 3 to the query —
            # a filter nobody asked for, on a question that otherwise looks answered.
            at = [k for k, tok in enumerate(qf.tokens) if tok in values]
            if at and all(k in frame_idx for k in at):
                continue
            entity = self._entity_for_column(col, hits)
            if entity:
                prof = self.by_entity[entity]
                m = Mapping(concept_id="", entity=entity, table_pattern=prof.table_pattern, column=col, operator="IN", values=list(values))
                hits.append(ResolvedSlot(term=f"{col} {','.join(values)}", semantic_type=SemanticType.DIMENSION_VALUE, status="EXPLICIT", mapping=m, confidence=1.0, explain={"why": "kullanıcı fiziksel kodu sorunun içinde verdi"}))
                for k, tok in enumerate(qf.tokens):
                    if tok.upper() == col or tok in values:
                        consumed.add(k)
            else:
                # The column exists but nothing in the question says which table it belongs to — it
                # occurs in several. Answering without the filter answers a wider question than the
                # one that was asked, so this is stated rather than passed over.
                where = sorted({p.entity for p in self.profiles if any(c.name.upper() == col for c in p.columns)})
                term = f"{col} {','.join(values)}"
                if term not in sq.unhandled:
                    sq.unhandled.append(term)
                    sq.explanation.append(
                        f"'{col}' kolonu bu veritabanında var ({', '.join(where[:5])}) ama sorunun konusuyla "
                        f"ilişkili değil; {col} = {', '.join(values)} filtresi UYGULANMADI"
                    )
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
            found_values = self._value_index.get(phrase) or self._value_index.get(" ".join(stem(t) for t in qf.tokens[i:j])) or []
            for entity, column, raw in found_values:
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

        # 4a) people ask with verbs ("ne kadar sattık?"), the catalog is keyed on nouns ("satış tutarı").
        #     When nothing else supplied a measure, a verb root that uniquely prefixes one certified term
        #     bridges the two — reported as INFERRED so the answer says how it got there.
        if not any(s_.semantic_type == SemanticType.METRIC for s_ in hits):
            inferred = self._from_verb(qf, index, consumed)
            if inferred is not None:
                hits.append(inferred)
                sq.slots = hits

        # 4b) composed metric: certified measure column + aggregation word, when no certified metric matched
        #     ("iade tutarı" = 'iade' filtresi + 'satış tutarı' ölçü kolonu → SUM(INVOICE.NETTOTAL))
        # The composition is anchored on a certified column, so any resolved slot is enough to say which
        # entity it belongs to — requiring a filter or a breakdown as well only refused good questions.
        if not any(s_.semantic_type == SemanticType.METRIC for s_ in hits) and hits:
            composed = self._compose_metric(qf, hits, primary, consumed)
            if composed is not None:
                hits.append(composed)
                sq.slots = hits

        # 4c) a word the index does not carry verbatim: try its derivational base ("kârlılığımız" → "kâr")
        #     and then a certified term that contains it and belongs to exactly one concept ("alım"
        #     occurs only inside "mal alım"). Both are INFERRED, never certified by this step.
        for k, tok in enumerate(qf.tokens):
            if k in consumed or not is_domain_candidate(tok) or is_participle(tok):
                continue
            slot = self._backoff(tok, k, index)
            if slot is not None:
                hits.append(slot)
                consumed.add(k)
        sq.slots = hits

        # 4d) "kaç fatura kestik?" — a count question over an entity someone has already named in the
        #     catalog. The key column comes from the profile, so no table or column is written here.
        if not any(s_.semantic_type == SemanticType.METRIC for s_ in hits) and _COUNT_CUE.search(fold(question)):
            counted = self._count_metric(qf, hits, consumed)
            if counted is not None:
                hits.append(counted)
                sq.slots = hits

        # 4e) "hangi müşteri …" — the interrogative names the breakdown. The label column is the
        #     certified COLUMN concept of that entity whose own term contains the word that was used.
        which = self._which_breakdown(qf, hits, consumed)
        if which is not None and which not in sq.group_by:
            hits.append(which)
            sq.group_by.append(which)
            sq.slots = hits

        # 4f) "en yüksek beş kanal" — a written-out number after a ranking cue is a top-N.
        if qf.limit is None:
            for k, tok in enumerate(qf.tokens):
                n = cardinal(tok)
                if n is None or n < 2 or n > 1000 or re.fullmatch(r"(19|20)\d\d", tok):
                    continue
                if {fold(x) for x in qf.tokens[max(0, k - 3) : k]} & _RANK_CUE:
                    qf.limit = n
                    consumed.add(k)
                    sq.explanation.append(f"'{tok}' sıralama sayısı olarak okundu → ilk {n}")
                    break

        # 4g) grain: can this measure be attributed to the breakdown that was asked for?
        self._match_measure_to_grain(sq, hits, index)

        # 5) temporal
        sq.temporal = list(qf.temporal)
        sq.grain = qf.grain
        if not sq.temporal and self.default_temporal is not None:
            fallback = self.default_temporal() if callable(self.default_temporal) else self.default_temporal
            if fallback is not None:
                sq.temporal = [fallback]
                sq.explanation.append(f"dönem belirtilmedi → varsayılan {fallback.primitive} uygulandı")
        for t in sq.temporal:
            sq.explanation.append(describe(t))
        if not sq.grain and _asks_for_a_trend(question):
            sq.grain = "MONTH"
            sq.explanation.append("soru bir gidişat soruyor → sonuç ay ay kırılacak")
        for k, tok in enumerate(qf.tokens):
            if k in consumed or not (_is_trend_cue(tok) or _COUNT_CUE.fullmatch(fold(tok))):
                continue
            if is_participle(tok) and self._modifies_a_noun(qf.tokens, k, consumed):
                continue            # "artan ürünler" narrows the subject; it is not just a trend cue
            consumed.add(k)         # a cue that shaped the query is accounted for, not missing

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
            if st in _TIME_WORDS or short_root(tok) in _TIME_WORDS:
                continue
            if is_light_verb(tok):
                # "iade edilen" — the compound's meaning is in the noun beside it, not in this word
                if tok not in sq.ignored:
                    sq.ignored.append(tok)
                continue
            if is_negative(tok):
                root = verb_root(tok)
                named = self._metric_keys_for_root(root, index) if root else []
                if named:
                    # "hiç satmayan ürünler": the measure is known, what is being asked for is records
                    # with none of it. That is an anti-join, a shape this compiler cannot write but the
                    # model can — and it is not the positive question, which is what must never happen.
                    sq.shape = "ABSENCE"
                    sq.explanation.append(
                        f"'{tok}' olumsuz: '{named[0][0]}' ölçüsünün hiç gerçekleşmediği kayıtlar isteniyor"
                    )
                    if tok not in sq.ignored:
                        sq.ignored.append(tok)
                    continue
            if is_participle(tok) or is_negative(tok):
                # A participle is grammar, but an attributive one narrows the subject ("bekleyen
                # siparişler"): dropping it would answer a wider question than the one that was asked.
                if is_light_verb(tok) or not self._modifies_a_noun(qf.tokens, k, consumed):
                    if tok not in sq.ignored:
                        sq.ignored.append(tok)
                elif tok not in sq.unhandled:
                    sq.unhandled.append(tok)
                    sq.explanation.append(f"'{tok}' konuyu daraltıyor ama katalogda karşılığı yok; yok sayılırsa daha geniş bir soru cevaplanmış olur")
                continue
            if not is_domain_candidate(tok):
                # an inflected verb, a pronoun or a question particle says nothing about the catalog
                if tok not in sq.ignored:
                    sq.ignored.append(tok)
                continue
            if st in GENERIC_S and k > 0 and (k - 1) in consumed:
                # "toplam satış rakamı": a generic head noun sitting on a term that did resolve is
                # part of that phrase, not a second concept the catalog is missing. Only next to a
                # resolved word — on its own, "kod" is still a word the catalog may well define.
                if tok not in sq.ignored:
                    sq.ignored.append(tok)
                continue
            if tok not in sq.unresolved:
                sq.unresolved.append(tok)

        # 7) conflicting filters: two different value sets ANDed on one column (no comparison cue)
        by_col: dict[tuple[str, str], set[frozenset[str]]] = {}
        for s_ in hits:
            if s_.semantic_type == SemanticType.DIMENSION_VALUE and s_.mapping and s_.mapping.column:
                by_col.setdefault((s_.mapping.entity, s_.mapping.column.upper()), set()).add(frozenset(s_.mapping.values))
        for s_ in hits:
            if s_.semantic_type != SemanticType.METRIC or not s_.mapping:
                continue
            for key in (s_.mapping.extra or {}).get("conditions") or []:
                scope = _parse_condition(key)
                if scope is None:
                    continue
                col_key, scope_values = scope
                for f in hits:
                    if f.semantic_type != SemanticType.DIMENSION_VALUE or not f.mapping or not f.mapping.column:
                        continue
                    if (f.mapping.entity, f.mapping.column.upper()) != col_key:
                        continue
                    if (f.mapping.operator or "IN").upper() == "IN" and not (set(f.mapping.values) & scope_values):
                        label = f"{col_key[0]}.{col_key[1]}"
                        if label not in sq.conflicts:
                            sq.conflicts.append(label)
                            sq.explanation.append(
                                f"'{f.term}' filtresi '{s_.term}' ölçüsünün kapsamıyla ({key}) kesişmiyor: "
                                "birlikte sorulursa sonuç her zaman boş çıkar"
                            )
        comparison = bool(_COMPARE_CUE.search(fold(question)))
        for (entity, column), sets in by_col.items():
            if len(sets) > 1 and not comparison:
                sq.conflicts.append(f"{entity}.{column}")
                sq.explanation.append(f"aynı kolonda ({entity}.{column}) birbiriyle çelişen değer kümeleri istendi: " + " / ".join(", ".join(sorted(x)) for x in sets))
            elif len(sets) > 1:
                sq.explanation.append(f"karşılaştırma istendi: {entity}.{column} üzerinde " + " / ".join(", ".join(sorted(x)) for x in sets) + " ayrı sütunlara açılacak")

        # 8) does this deployment even hold the period being asked about? The window is measured, so the
        #    answer is "there is no data for 2019 here", not an empty result set that looks like zero sales.
        entity = self._primary_entity(hits) or next((s_.mapping.entity for s_ in hits if s_.mapping), None)
        from semantic_layer.runtime import periods

        covered = periods.spans(self.tables_of.get(entity or "", []))
        window = (covered[0].isoformat(), covered[1].isoformat()) if covered else None
        if window and sq.temporal:
            first, last = covered
            for t in sq.temporal:
                if not (first and last and t.start and t.end):
                    continue
                if t.end <= first:
                    # entirely before the data begins: there is nothing to find, and an empty result
                    # would read as a real zero
                    sq.out_of_scope.append(t.text)
                    sq.explanation.append(
                        # what this deployment was given, not what the business has: the difference
                        # matters, because a period missing here may be sitting in a table nobody scoped
                        f"'{t.text}' bu kurulumun kapsamı dışında: {entity} için tanımlı veri "
                        f"{window[0]} – {window[1]} arasını içeriyor"
                    )
                elif t.start > last:
                    # after the last row loaded. That is a loading state, not a gap in coverage — the
                    # current month legitimately has no rows yet — so the question is still answered,
                    # with the cut-off said out loud.
                    sq.explanation.append(
                        f"'{t.text}' için veri henüz yüklenmemiş olabilir: {entity} son kaydı {window[1]}"
                    )

        # 9) a share question needs a denominator. When no certified ratio supplies one, answering with
        #    the plain total would quietly replace "what percent" with "how much".
        if _SHARE_CUE.search(fold(question)) and not any(
            s_.semantic_type == SemanticType.METRIC and s_.mapping and "/" in (s_.mapping.formula or "") for s_ in hits
        ):
            cue = next((t for t in qf.tokens if _SHARE_CUE.fullmatch(stem(t)) or _SHARE_CUE.fullmatch(fold(t))), "pay")
            sq.shape = "RATIO"
            sq.explanation.append(
                f"'{cue}' bir oran istiyor; katalogda paydayı veren sertifikalı bir ölçü yok, "
                "bu yüzden payda soruya göre seçilmeli — düz toplam farklı bir soruyu cevaplar"
            )

        # 10) a question that names nothing — no measure, no filter, no column, no period, not even a
        #     word the catalog is missing — has not said what it is about. The model must ask, not pick
        #     a table: "toplam sayıyı ver" answered with a row count is a guess wearing a number.
        # A period is not a subject: "son çeyrekte ne oldu?" says when, never what.
        if not hits and not sq.shape and (not sq.unresolved or _asks_how_things_are(qf.tokens)):
            said_when = {t for slot in sq.temporal for t in tokenize(slot.text)}
            named = [t for t in qf.tokens if is_domain_candidate(t) and t not in said_when
                     and stem(t) not in _TIME_WORDS and short_root(t) not in _TIME_WORDS]
            # "Bu yıl performansımız iyi mi?" names a word — but the word is the question, not a
            # measure, and nothing in the catalog answers it. Asked how things are going with no
            # measure placed, the honest reply is to ask which one; picking a table and returning a
            # number is a guess the person has no way to check.
            if not named or (not sq.slots and _asks_how_things_are(qf.tokens)):
                sq.shape = "UNDERSPECIFIED"
                sq.explanation.append("soru neyin ölçüleceğini söylemiyor; hangi ölçü ve hangi kırılım istendiği sorulmalı")

        sq.limit = qf.limit
        sq.order_desc = qf.order_desc
        for s in hits:
            sq.explanation.append(self._why(s))
        if sq.unresolved:
            sq.explanation.append("katalogda karşılığı olmayan terimler: " + ", ".join(sq.unresolved))
        if sq.unhandled:
            sq.explanation.append("karşılanamayan niteleyiciler: " + ", ".join(sq.unhandled))
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

    def _by_root(self, index: dict) -> dict:
        """The certified vocabulary, keyed by the roots of its own terms.

        Turkish inflects: a question asks about "kanala göre" or "2026 satışı" and the catalog holds
        "kanal" and "satış". The lookup is exact, so the same question answered one way was refused
        the other — the root was already being computed and simply never consulted here.

        Nothing is added to the vocabulary and no suffix is written down anywhere: the keys are the
        catalog's own terms, reduced by the same root function the rest of the resolver uses, so this
        works for whatever language a deployment's catalog is written in.

        A root two different terms share is left out rather than guessed at. "One of these two, and I
        picked" is the kind of silent decision this system exists to avoid; those terms keep their
        exact spelling and nothing else changes.
        """
        marker = id(index)
        if self._roots_for != marker:
            groups: dict[str, set[str]] = {}
            for key in index:
                groups.setdefault(_rooted(key), set()).add(key)
            self._roots_for = marker
            roots: dict = {}
            for root, keys in groups.items():
                # The canonical spelling wins where the catalog holds it: "kanal" and "kanallar" both
                # reduce to "kanal", and the entry to use is the one written that way. Where no key is
                # the root itself, a root two different terms share is left out rather than guessed at
                # — "one of these two, and I picked" is the silent decision this system exists to
                # avoid, and those terms keep their exact spelling.
                if root in keys:
                    roots[root] = index[root]
                elif len(keys) == 1:
                    roots[root] = index[next(iter(keys))]
            self._roots = roots
        return self._roots

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
                    if col.sensitive:
                        continue        # personal data never becomes a searchable value literal
                    observed = [str(v) for v, _ in col.meaningful_values()] if col.is_enum() else []
                    documented = [str(v) for v in (concept.explain.get("documented_values") or [])]
                    for raw in dict.fromkeys(observed + documented):
                        token = " ".join(tokenize(raw))   # same shape the question tokens have ("E-TICARET" → "e ticaret")
                        if len(token) < 3 or token.isdigit() or token in STOPWORDS_S or token.isnumeric():
                            continue
                        # people inflect the value they say ("Kitapçılar bu ay …"), so the stemmed shape
                        # is indexed beside the literal one and the lookup tries both.
                        for form in dict.fromkeys([token, " ".join(stem(t) for t in tokenize(raw))]):
                            entry = (m.entity, col.name, raw)
                            if entry not in values.setdefault(form, []):
                                values[form].append(entry)
        self._value_index = values
        self._measure_columns = measures
        self._cache_key = key

    def _from_verb(self, qf: Any, index: dict[str, list[tuple[Concept, list[Mapping]]]], consumed: set[int]) -> Optional[ResolvedSlot]:
        for k, tok in enumerate(qf.tokens):
            if k in consumed:
                continue
            root = verb_root(tok)
            if not root or is_negative(tok):
                continue        # "satmayan" is the opposite of "satış": bridging it would invert the answer
            matches = self._metric_keys_for_root(root, index)
            if not matches:
                continue
            # Turkish forms a noun from a verb with -ış/-im/-ma ("sat" → "satış"): that nominalisation is
            # the term the catalog is keyed on, so it wins over an unrelated word sharing the prefix.
            nominal = [m for m in matches if m[0].split()[0] in {root + suf for suf in ("", "is", "im", "um", "ma", "me", "gi", "ki")}]
            if nominal:
                matches = nominal
            if len(matches) > 1:
                # several keys may be names of the same measure ("satış" and "satış tutarı"); that is not
                # ambiguity. Different measures are.
                concepts = {c.id for _, senses in matches for c, _ in senses if c.semantic_type == SemanticType.METRIC}
                if len(concepts) > 1:
                    continue                 # genuinely different measures: say nothing rather than guess
                matches = [min(matches, key=lambda m: (len(m[0].split()), len(m[0])))]
            key, senses = matches[0]
            slot = self._slot_from_senses(key, tok, senses, (k, k + 1))
            if slot is None or slot.semantic_type != SemanticType.METRIC:
                continue
            slot.status = "INFERRED"
            slot.confidence = min(slot.confidence, 0.7)
            slot.explain["why"] = f"'{tok}' fiilinin kökü ({root}) yalnız '{key}' ölçüsüyle eşleşiyor"
            consumed.add(k)
            return slot
        return None

    @staticmethod
    def _modifies_a_noun(tokens: list[str], k: int, consumed: Optional[set[int]] = None) -> bool:
        """Is the participle at k attached to a following noun ("bekleyen siparişler") rather than
        standing as the sentence's predicate ("iadeler artıyor mu")?

        A word the resolver already placed counts as a noun: it is part of the subject being narrowed.
        """
        for i in range(k + 1, min(k + 4, len(tokens))):
            nxt = tokens[i]
            if consumed is not None and i in consumed:
                return True
            f = fold(nxt)
            if cardinal(nxt) is not None or f in STOPWORDS_S or f in MODIFIERS_S:
                continue
            return is_domain_candidate(nxt) and not is_participle(nxt)
        return False

    def _backoff(self, tok: str, k: int, index: dict[str, list[tuple[Concept, list[Mapping]]]]) -> Optional[ResolvedSlot]:
        """Second-chance lookup for a single word: derivational base first, then a unique certified
        term that contains it. Never certifies anything — the slot is marked INFERRED and damped."""
        st = stem(tok)
        if {fold(tok), st} & (STOPWORDS_S | MODIFIERS_S | METRIC_VOCAB_S):
            return None         # a generic word ("sayı", "toplam") must not select one specific concept
        for key in derived_forms(tok):
            senses = index.get(key)
            slot = self._slot_from_senses(key, tok, senses, (k, k + 1)) if senses else None
            if slot is not None:
                slot.status = "INFERRED"
                slot.confidence = min(slot.confidence, 0.7)
                slot.explain["why"] = f"'{tok}' türetilmiş biçim; kökü '{key}' katalogda sertifikalı"
                return slot
        bases = {st} | set(derived_forms(tok))
        matches = [(key, senses) for key, senses in index.items() if bases & set(key.split())]
        if not matches:
            return None
        concepts = {c.id for _, senses in matches for c, _ in senses}
        if len({key for key, _ in matches}) == 1:
            concepts = {next(iter(concepts))}      # one term, several senses — ranking picks the sense
        if len(concepts) > 1:
            # several certified terms contain the word but mean different things — one of them is a
            # measure only when the rest are not; otherwise stay silent rather than pick a sense.
            metrics = {c.id for _, senses in matches for c, _ in senses if c.semantic_type == SemanticType.METRIC}
            entities = {m.entity for _, senses in matches for _, maps in senses for m in maps}
            if len(metrics) != 1 or len(entities) != 1:
                return None
            matches = [(key, [(c, maps) for c, maps in senses if c.id in metrics]) for key, senses in matches
                       if any(c.id in metrics for c, _ in senses)]
        key, senses = min(matches, key=lambda m: (len(m[0].split()), len(m[0])))
        slot = self._slot_from_senses(key, tok, senses, (k, k + 1))
        if slot is None:
            return None
        slot.status = "INFERRED"
        slot.confidence = min(slot.confidence, 0.65)
        slot.explain["why"] = f"'{tok}' katalogda yalnız '{key}' teriminin içinde geçiyor"
        return slot

    def _entity_of_word(self, token: str, index: dict[str, list[tuple[Concept, list[Mapping]]]]) -> Optional[str]:
        """Which entity does this word name? Answered from certified terms only: "sipariş" points at the
        table the certified concept "sipariş sayısı" maps to. Nothing is derived from table names."""
        bases = {stem(token)} | set(derived_forms(token))
        owners = {m.entity for key, senses in index.items() if bases & set(key.split())
                  for _, maps in senses for m in maps}
        return next(iter(owners)) if len(owners) == 1 else None

    def _count_metric(self, qf: Any, hits: list[ResolvedSlot], consumed: set[int]) -> Optional[ResolvedSlot]:
        index = self.store.certified_index(self.tenant_id, self.datasource_id)
        entity = None
        for k, tok in enumerate(qf.tokens):
            if not is_domain_candidate(tok):
                continue
            entity = self._entity_of_word(tok, index)
            if entity:
                break
        entity = entity or self._primary_entity(hits)
        prof = self.by_entity.get(entity or "")
        if prof is None:
            return None
        key = next((c.name for c in prof.columns if c.is_primary_key), None)
        formula = f"COUNT(DISTINCT {entity}.{key})" if key else f"COUNT(*)"
        m = Mapping(concept_id="", entity=entity, table_pattern=prof.table_pattern, formula=formula)
        return ResolvedSlot(
            term="kayıt sayısı", semantic_type=SemanticType.METRIC, status="COMPOSED", mapping=m, confidence=0.75,
            explain={"why": f"soru adet soruyor → {entity} kayıtları {('anahtar ' + key) if key else 'satır'} üzerinden sayıldı"},
        )

    def _which_breakdown(self, qf: Any, hits: list[ResolvedSlot], consumed: set[int]) -> Optional[ResolvedSlot]:
        """"Hangi müşteri …" → group by the entity's label column, chosen from certified COLUMN concepts."""
        index = self.store.certified_index(self.tenant_id, self.datasource_id)
        for k, tok in enumerate(qf.tokens):
            if fold(tok) not in _WHICH:
                continue
            for nxt_i in range(k + 1, min(k + 4, len(qf.tokens))):
                nxt = qf.tokens[nxt_i]
                if not is_domain_candidate(nxt):
                    continue
                entity = self._entity_of_word(nxt, index)
                if not entity:
                    break
                bases = {stem(nxt)} | set(derived_forms(nxt))
                best = None
                for key, senses in index.items():
                    for c, maps in senses:
                        if c.semantic_type != SemanticType.COLUMN:
                            continue
                        for m in maps:
                            prof = self.by_entity.get(m.entity)
                            col = prof.column(m.column) if prof and m.column else None
                            if col is None or m.entity != entity or col.is_primary_key or col.sensitive:
                                continue
                            if not bases & set(key.split()):
                                continue
                            rank = (0 if not self.conventions.is_scope_column(m.entity, col.name) else 1, len(key))
                            if best is None or rank < best[0]:
                                best = (rank, c, m, key)
                if best is None:
                    break
                _, c, m, key = best
                consumed.add(nxt_i)
                return ResolvedSlot(term=nxt, semantic_type=SemanticType.COLUMN, status="INFERRED", concept_id=c.id,
                                    mapping=m, confidence=min(c.confidence, 0.7),
                                    explain={"why": f"'{tok} {nxt}' kırılım istiyor → sertifikalı '{key}' kolonu ({m.entity}.{m.column})", "role": "group_by"},
                                    span=(nxt_i, nxt_i + 1))
        return None

    @staticmethod
    def _metric_keys_for_root(root: str, index: dict[str, list[tuple[Concept, list[Mapping]]]]) -> list[tuple[str, list[tuple[Concept, list[Mapping]]]]]:
        """Certified measures whose term begins with this verb root — how a verb reaches a noun catalog."""
        return [
            (key, senses) for key, senses in index.items()
            if key.split()[0].startswith(root) and any(c.semantic_type == SemanticType.METRIC for c, _ in senses)
        ]

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
            # the column this measure is built from is no longer a column being asked for: it *is* the
            # measure, and leaving it in place would read as a projection nobody requested
            for src in [x for x in hits if x.semantic_type == SemanticType.COLUMN and x.mapping
                        and x.mapping.entity == entity and (x.mapping.column or "").upper() == column.upper()]:
                hits.remove(src)
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

    def _points_at(self, root: str, hops: int = 1) -> set[str]:
        """Bir `root` satırından TEK bir satırına gidilebilen varlıklar — yabancı anahtarın yönü.

        `_related_entities` yönsüzdür ("bu ikisi bir arada sorulabilir" der). Taneciklik sorusu ise
        yönlüdür: faturanın müşterisi tektir, ama bir faturanın ürünü tek değildir. Kırılım yalnız
        okun gösterdiği yönde güvenlidir; ters yönde ölçü satırlara bölünmek zorundadır ve bölme
        işini yapan tablo elde yoksa çıkan rakam ya tekrarlanır ya da uydurulur.

        Tek sıçrama, ve bu bilerek: 4121 profillik gerçek bir grafikte üç sıçramada her şey her şeye
        ulaşıyor ve "güvenli" cevabı anlamını yitiriyor — fatura, müşterisi üzerinden ürüne de
        "bağlı" çıkıyordu. Kırılımın ölçünün kendi satırının doğrudan niteliği olması aranır;
        emin olunamayan durumda daha ince tanımı aramak, yanlış tanecikte cevap vermekten iyidir.
        """
        cached = self._fk_cache.get(root)
        if cached is not None:
            return cached
        if not self._fk_edges:
            for p in self.profiles:
                for rel in p.relationships or []:
                    other = rel.get("ref_entity")
                    if other and other != p.entity:
                        self._fk_edges.setdefault(p.entity, set()).add(other)
        seen, frontier = set(), {root}
        for _ in range(hops):
            nxt: set[str] = set()
            for e in frontier:
                nxt |= self._fk_edges.get(e, set())
            frontier = nxt - seen - {root}
            seen |= frontier
        self._fk_cache[root] = seen
        return seen

    @staticmethod
    def _grain_of(slot: ResolvedSlot) -> str:
        """Ölçünün bir satırının neyi temsil ettiği. Katalog `extra.grain` ile açıkça yazabilir;
        yazmadıysa ölçünün durduğu tablo neyse taneciklik odur."""
        m = slot.mapping
        if m is None:
            return ""
        return str((m.extra or {}).get("grain") or m.entity or "")

    def _match_measure_to_grain(self, sq: SemanticQuery, hits: list[ResolvedSlot], index: dict) -> None:
        """İstenen kırılım ölçünün tanecikliğinden ince mi — ve inceyse, uyan başka bir anlam var mı?

        "Ürün bazında net ciro" sorusunda fatura seviyeli ciro ürüne bölünemez: bir faturada birkaç
        ürün vardır. Katalogda aynı terimin satır seviyeli anlamı varsa doğru olan odur ve buradan
        seçilir. Yoksa soru sessizce yanlış tanecikte cevaplanmaz; niteliğiyle birlikte söylenir.
        """
        for metric in [s for s in hits if s.semantic_type == SemanticType.METRIC and s.mapping]:
            grain = self._grain_of(metric)
            if not grain:
                continue
            for dim in list(sq.group_by):
                target = dim.mapping.entity if dim.mapping else ""
                if not target or target == grain or target in self._points_at(grain):
                    continue                      # aynı satır ya da okun gösterdiği yön: bölünme yok
                alt = self._sense_at_grain(metric, target, index)
                if alt is not None:
                    old_grain, metric.mapping = grain, alt
                    metric.explain["grain_switch"] = f"{old_grain} → {self._grain_of(metric)}"
                    sq.explanation.append(
                        f"'{metric.term}' {old_grain} seviyesinde tanımlı ama kırılım '{dim.term}' "
                        f"({target}) daha ince; aynı terimin {self._grain_of(metric)} seviyesindeki "
                        f"tanımı kullanıldı"
                    )
                    grain = self._grain_of(metric)
                    continue
                # Uyan bir anlam yok. Soruyu burada reddetmiyoruz: deterministik derleyici bu
                # durumu zaten tanıyor ve planı kuramadığını söylüyor. Buraya düşen tek şey, neden
                # öyle olduğunun ize yazılması — iki kapı aynı işi yaparsa hangisinin konuştuğu
                # belirsizleşir.
                note = (f"'{metric.term}' {grain} seviyesinde ölçülüyor; '{dim.term}' ({target}) kırılımı "
                        f"daha ince ve bu ölçüyü satırlara bölecek bir tanım katalogda yok — bölünürse "
                        f"çıkan rakam her satırda tekrar eder")
                if note not in sq.explanation:
                    sq.explanation.append(note)

    def _sense_at_grain(self, metric: ResolvedSlot, target: str, index: dict) -> Optional[Mapping]:
        """Aynı terimin, istenen kırılımı taşıyabilen başka bir anlamı."""
        key = metric.explain.get("normalized") or metric.term
        for sense in (index.get(key) or []):
            concept, mappings = sense if isinstance(sense, tuple) else (sense, [])
            for m in mappings or []:
                grain = str((m.extra or {}).get("grain") or m.entity or "")
                if not grain or grain == self._grain_of(metric):
                    continue
                if target == grain or target in self._points_at(grain):
                    return m
        return None

    def _related_entities(self, root: str, hops: int = 2) -> set[str]:
        """Entities a question about `root` can also be about: those joined to it, either direction.

        Built from the relationships the source itself declares, so it says nothing about any
        particular schema — only that a filter has to land somewhere the answer can reach.
        """
        cached = self._related_cache.get(root)
        if cached is not None:
            return cached
        if not self._edges:
            for p in self.profiles:
                for rel in p.relationships:
                    other = rel.get("ref_entity")
                    if not other:
                        continue
                    self._edges.setdefault(p.entity, set()).add(other)
                    self._edges.setdefault(other, set()).add(p.entity)
        seen, frontier = {root}, {root}
        for _ in range(hops):
            nxt: set[str] = set()
            for e in frontier:
                nxt |= self._edges.get(e, set())
            frontier = nxt - seen
            seen |= frontier
        self._related_cache[root] = seen
        return seen

    def _entity_for_column(self, col: str, hits: list[ResolvedSlot]) -> Optional[str]:
        owners = [p.entity for p in self.profiles if p.column(col)]
        if not owners:
            return None
        primary = self._primary_entity(hits)
        if primary:
            # A stated filter belongs to what the question is about, or to something joined to it. A
            # column that merely happens to exist in one unrelated table is not what was meant, and
            # binding it there attaches a condition to an answer nobody can see the workings of.
            near = self._related_entities(primary)
            owners = [e for e in owners if e in near]
            if not owners:
                return None
        if len(owners) == 1:
            return owners[0]
        return self.conventions.preferred_entity(owners, hint=primary)

    def _knows_word(self, word: str, index: dict) -> bool:
        """Katalog bu kelimeyi tanıyor mu — terim, kolon adı ya da varlık adı olarak."""
        st = stem(word)
        if st in index or word.upper() in self.column_names or st in _ENTITY_WORDS:
            return True
        return bool(self._by_root(index).get(_rooted(word)))

    def _report_frame(self, qf, consumed: set[int], index: dict) -> tuple[set[int], list[str]]:
        """"1. kolon kanal adı 2. kolon yıl 3. kolon toplam satış" — çıktının iskeleti.

        Rol kelimesi ("kolon") bir listeden değil durduğu yerden tanınır: sıra sayısının hemen
        ardında, en az iki kez aynı biçimde tekrarlanan ve katalogda karşılığı olmayan bir kelime,
        veriyi değil teslimatın şeklini anlatıyordur. Liste tutmanın sonu yok — yarın "sütun", öbür
        gün "hane" gelir; tekrar eden konum ise dilin kendisinde.

        Katalogda karşılığı olan kelime asla çerçeve sayılmaz: "1. bölge cirosu 2. bölge cirosu"
        diye soran biri bölgeden vazgeçmiş olmaz. Bu yüzden reddi kaldırmak yetmez, çerçevenin
        çerçeve olduğu kanıtlanmalı.

        Döndürdüğü: tüketilecek belirteç indeksleri ve istenen kolonlar (sorulan sırayla).
        """
        toks = qf.tokens

        def is_ordinal(t: str) -> bool:
            # 20'den büyük sayı madde numarası değildir: "2026" bir yıl, "150" bir eşik.
            return (t.isdigit() and 1 <= int(t) <= 20) or stem(t) in _ORDINAL_WORDS

        marks: list[tuple[int, int]] = []                 # (sıra belirteci, rol kelimesi)
        for k in range(len(toks) - 1):
            tok = toks[k]
            if k in consumed or not is_ordinal(tok):
                continue
            r = k + 1
            if r in consumed or self._knows_word(toks[r], index):
                continue
            marks.append((k, r))
        if len(marks) < 3:
            return set(), []
        roles = [stem(toks[r]) for _, r in marks]
        common = max(set(roles), key=roles.count)
        hits = [m for m, role in zip(marks, roles) if role == common]
        # Üç kez: iki kez tekrar bir çerçeve değil, bir karşılaştırma da olabilir ("1. bölge cirosu
        # 2. bölge cirosu"). Üçüncü tekrar dilin kendisinde nadirdir; sayarak konuşan bir rapor
        # siparişinde ise kuraldır.
        if len(hits) < 3:
            return set(), []
        # Her slotun içeriği: rol kelimesinden sonraki sözcükler, bir SONRAKİ sıra belirtecine kadar
        # — kullanıcı her maddede rol kelimesini tekrar etmeyebilir ("4. ürün kırılımı").
        first = hits[0][0]
        ordinals = [k for k in range(first, len(toks)) if is_ordinal(toks[k])]
        order: list[str] = []
        for pos, o in enumerate(ordinals):
            start = o + 1
            # Madde numarasından sonra rol kelimesi varsa atlanır; kullanıcı her maddede tekrar
            # etmeyebilir ("3. kolon toplam satış" ile "4. ürün kırılımı" aynı listenin maddeleri).
            if start < len(toks) and stem(toks[start]) == common:
                start += 1
            end = ordinals[pos + 1] if pos + 1 < len(ordinals) else len(toks)
            words = [toks[i] for i in range(start, end)]
            if words:
                order.append(" ".join(words))
        # Aynı içerik tekrar ediyorsa bu bir çıktı listesi değil, aynı şeyin farklı örnekleri:
        # sıra sayısı kolonu değil konuyu numaralandırıyordur. Böyle bir cümlede rol kelimesini
        # yutmak, sorulandan daha geniş bir soruyu cevaplamak olur.
        if len(set(order)) < len(order):
            return set(), []
        idx = {k for k, _ in hits} | {r for _, r in hits}
        return idx, order

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
