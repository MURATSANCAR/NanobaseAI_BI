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
    normalize_term,
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
from semantic_layer.naming import is_shadow_copy, source_rank
from dataclasses import replace
from datetime import timedelta

from semantic_layer.runtime.temporal import describe
from semantic_layer.store.catalog_store import CatalogStore

# Words the LLM handles from schema context; never reported as "unresolved" (they are entities, not values).
_ENTITY_WORDS = frozenset(stem(w) for w in "fatura musteri cari tedarikci kitap urun malzeme stok siparis satir hareket belge kayit firma sirket sube depo".split())
_TIME_WORDS = frozenset(stem(w) for w in "gun gunde gunler gunluk ay ayda aylar aylik ayin ayindaki yil yilda yillik hafta haftada haftalik ceyrek ceyreklik donem donemde donemsel tarih bugun dun son gecen onceki sonraki ilk itibaren beri bu yana".split())
# Bir aday, ikincisinden bu kadar önde olmalı ki "tek belirgin aday" sayılsın.
_DOMINANT = 1.5


def _next_span(start, end):
    """The period that follows [start, end) — by the calendar where the span is a calendar unit.

    Shifting by the number of days puts the month after a 31-day August at the 2nd of October.
    A month is compared with a month and a year with a year, so the unit is what moves.
    """
    if start.day == 1 and end.day == 1:
        months = (end.year - start.year) * 12 + (end.month - start.month)
        if months >= 1:
            y, m = end.year, end.month + months
            y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
            return date(y, m, 1)
    return end + (end - start)


def _one_measure_under_two_names(concepts) -> bool:
    """Are these the same measure named twice, according to the catalog itself?

    Only a declared synonym counts — a name one of them carries in its own `synonyms` list, written
    by whoever defined it. Nothing is inferred from the words looking alike: "satış adedi" and
    "satış tutarı" share every word and are different measures.
    """
    items = list(concepts)
    if len(items) < 2:
        return True
    names = {normalize_term(c.term) for c in items}
    declared = {normalize_term(s) for c in items for s in (getattr(c, "synonyms", None) or [])}
    # every name but one has to be claimed by another concept in the group
    return len(names - declared) <= 1


def _identifier_words(name: str) -> set[str]:
    """`RAF_BILGISI` → {raf, bilgisi}. Kolon adının kendi kelimeleri."""
    return {w for w in re.split(r"[^a-z0-9]+", fold(name or "")) if w}


# "geçen yıla göre", "2025'e kıyasla" — ikinci dönem söylenmez, "göre" onu ima eder.
_COMPARE_TO = re.compile(
    r"\b(?:(?:gecen|onceki|bu|[0-9]{4})\s+(?:yil|ay|hafta|ceyrek|donem|gun)\w*|"
    r"[0-9]{4}(?:[’']?[eya]+)?)\s+(?:gore|kiyasla|karsi|nazaran|oranla)\b"
)
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
    def _all_years(self, sq: SemanticQuery, today: date) -> "Optional[TemporalSlot]":
        """"Yıllara göre ciro" bir yılı değil, yılları sorar.

        Dönem söylenmeyen soruya bu yılı vermek "şimdi" demek için doğru; ama yıllık kırılım isteyen
        soruya tek yıl vermek tek satırlık bir "trend" döndürür ve soruyu cevaplamaz. Bu durumda dönem,
        ölçünün tablolarında gerçekten gözlenen ilk yıldan bugüne kadar olan aralıktır — uydurulmuş
        bir başlangıç değil, verinin kendi kapsamı.
        """
        from semantic_layer.runtime import periods

        entities = {s.mapping.entity for s in sq.metrics if s.mapping}
        if len(entities) != 1:
            return None
        covered = periods.spans(self.tables_of.get(next(iter(entities)), []))
        if not covered or not covered[0]:
            return None
        first = covered[0].year
        last = max(first, min(today.year, covered[1].year if covered[1] else today.year))
        return TemporalSlot(text=f"{first}–{last}", primitive="RANGE", start=date(first, 1, 1),
                            end=date(last + 1, 1, 1), grain="YEAR",
                            params={"from": str(first), "to": str(last), "allYears": True})

    def __init__(self, store: CatalogStore, tenant_id: str, datasource_id: str, profiles: list[SchemaProfile], *, default_temporal: "Optional[TemporalSlot] | Callable[[], Optional[TemporalSlot]]" = None, conventions: Any = None, verified_pairs=()):
        from semantic_layer.conventions import Conventions

        from semantic_layer.history.modifiers import ModifierHistory

        self.modifier_history = ModifierHistory(verified_pairs, datasource_id)
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
        # Kolon adları, açıklamaları ve içerdikleri değerler üzerinde sözlük araması. Dışarıdan
        # verilir; verilmezse çözümleme bugünkü gibi yalnız sertifikalı sözlükten yürür.
        self.columns: Any = None
        self._measure_columns: dict[tuple[str, str], tuple[str, str]] = {}

    @staticmethod
    def _measure_expressions(question, qf, sq):
        """Reserve subtraction operands before noun lookup can turn them into filters.

        An arithmetic request is not evidence that its operands share a unit or
        grain. Until a certified expression binds them, retain the request and
        ask; neither deterministic nor fallback SQL may silently omit it.
        """
        if "eksi" not in qf.tokens:
            return set()
        folded = fold(question)
        spans = [(m.start(), m.end(), m.group()) for m in re.finditer(r"\([^()]*\)", folded)
                 if "eksi" in tokenize(m.group())]
        # Without a parenthesized boundary the operands' extent is not known.
        # Reserve the whole request rather than invent a boundary around a noun.
        covered = {k for a,b,_ in spans for k in range(len(tokenize(folded[:a])), len(tokenize(folded[:b])))}
        if any(t == "eksi" and k not in covered for k,t in enumerate(qf.tokens)):
            spans = [(0, len(folded), folded)]
        reserved = set()
        for a,b,text in spans:
            start, end = len(tokenize(folded[:a])), len(tokenize(folded[:b]))
            if qf.tokens[start:end] != tokenize(text):
                start,end,text = 0,len(qf.tokens),folded
            reserved.update(range(start,end))
            expression = text.strip("() ")
            sq.measure_expressions.append({"text":expression,"operator":"SUBTRACT",
                                           "span":[start,end],"status":"NEEDS_DEFINITION"})
            sq.unhandled.append(expression)
            sq.clarification.append(
                f"‘{expression}’ hesabında hangi ölçüden hangisini çıkarmalıyım? "
                "Tutar mı, adet mi; hangi dönem ve işlem kapsamı kullanılmalı?"
            )
            sq.explanation.append(f"'{expression}' bir hesap ifadesi; bileşenleri satır filtresine dönüştürülmedi")
        return reserved

    # ------------------------------------------------------------------ public
    def resolve(self, question: str, today: Optional[date] = None) -> SemanticQuery:
        from semantic_layer.runtime.monthly_analysis import resolve_frame
        framed = resolve_frame(self, question, today)
        if framed is not None:
            return framed
        index = self.store.certified_index(self.tenant_id, self.datasource_id)
        # Certified phrases may exceed three words. Splitting one can change
        # the measure's scope, for example dropping returns from net sales.
        n_max = max([3] + [len(key.split()) for key in index])
        qf = extract_question_facts(question, n_max=n_max)
        # In a ranking request, an explicitly named certified measure (including
        # parenthesized units) must not be discarded as generic query grammar.
        rank_requested = qf.limit is not None or any(
            cardinal(token) is not None and 2 <= cardinal(token) <= 1000
            and {fold(word) for word in qf.tokens[max(0, k - 3):k]} & _RANK_CUE
            for k, token in enumerate(qf.tokens))
        if rank_requested:
            for k, token in enumerate(qf.tokens):
                key = normalize_term(token)
                senses = index.get(key, [])
                if any(c.semantic_type == SemanticType.METRIC for c, _ in senses):
                    if (k, k + 1, key) not in qf.terms:
                        qf.terms.append((k, k + 1, key))
                        qf.surface.setdefault(key, token)
        version, content_hash = self.store.publish_runtime_snapshot(self.tenant_id, self.datasource_id, index)
        self._refresh_column_caches(index)
        sq = SemanticQuery(question=question, tenant_id=self.tenant_id, datasource_id=self.datasource_id, catalog_version=version)
        sq.catalog_hash = content_hash
        if today is not None:
            from semantic_layer.runtime.temporal import parse_temporal

            qf.temporal, qf.grain = parse_temporal(question, today)

        # 0) report frame: "1. kolon kanal adı 2. kolon yıl" — the shape of the deliverable, not the
        #     subject. First, and before anything looks a token up: a list marker is a fact about how
        #     the sentence is written, and in this catalog "2" and "3" are also TRCODE values, so a
        #     later pass reads the item numbers as a returns filter and the question quietly narrows.
        consumed: set[int] = set()
        expression_idx = self._measure_expressions(question, qf, sq)
        consumed.update(expression_idx)
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
            # "net ciro 2025": CIRO may also be a physical column, but here it
            # belongs to a certified measure and the number is a parsed period.
            # Explicit =/: syntax still denotes an intentional physical filter.
            temporal_words = {token for period in qf.temporal for token in tokenize(period.text)}
            metric_positions = {k for slot in hits if slot.semantic_type == SemanticType.METRIC
                                for k in range(*slot.span)}
            if (values and all(value in temporal_words for value in values)
                    and any(token.upper() == col and k in metric_positions for k, token in enumerate(qf.tokens))
                    and not re.search(r"\b" + re.escape(col) + r"\s*[=:]", question, re.I)):
                continue
            if col not in self.column_names:
                continue
            # "…net ciro 3. kolon…": the number is the third item of a list, and CIRO happens to be a
            # column somewhere in the schema. Read as a code it silently adds CIRO = 3 to the query —
            # a filter nobody asked for, on a question that otherwise looks answered.
            at = [k for k, tok in enumerate(qf.tokens) if tok in values]
            if at and all(k in frame_idx or k in expression_idx for k in at):
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

        # An adjacent explicit measure gives a single-word, ambiguous label its
        # modifier reading when the catalog certifies that value on the measure's entity.
        for pos, slot in enumerate(list(hits)):
            if slot.semantic_type != SemanticType.METRIC or slot.span[1] - slot.span[0] != 1:
                continue
            following = [h for h in hits if h is not slot and h.semantic_type == SemanticType.METRIC
                         and h.mapping and h.span[0] == slot.span[1]]
            if len(following) != 1:
                continue
            measure = following[0]
            if not re.search(r"\b" + re.escape(fold(slot.term)) + r"\s+" + re.escape(fold(measure.term)) + r"\b", fold(question)):
                continue
            senses = index.get(slot.explain.get("normalized", "")) or []
            values = [(c, [m for m in maps if m.entity == measure.mapping.entity]) for c, maps in senses
                      if c.semantic_type == SemanticType.DIMENSION_VALUE]
            values = [(c,maps) for c,maps in values if maps]
            if len(values) == 1:
                replacement = self._slot_from_senses(slot.explain["normalized"], slot.term, values, slot.span)
                if replacement:
                    hits[pos] = replacement
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
        # A trailing marker scopes a coordinated list: "müşteri, ürün ve birim bazında".
        # Keep the raw separators so a sentence boundary cannot silently join two lists.
        surface = fold(question)
        surface_tokens = list(re.finditer(r"[a-z0-9%]+", surface))
        aligned = [m.group() for m in surface_tokens] == qf.tokens
        columns_by_end = {s.span[1]: s for s in hits
                          if s.span and s.semantic_type == SemanticType.COLUMN}
        for k, tok in enumerate(qf.tokens):
            if not (_GROUP_MARKERS.fullmatch(stem(tok)) or _GROUP_MARKERS.fullmatch(tok)):
                continue
            cursor = k
            while cursor in columns_by_end:
                slot = columns_by_end[cursor]
                if slot not in sq.group_by:
                    sq.group_by.append(slot)
                    slot.explain["role"] = "group_by"
                start = slot.span[0]
                previous_end = start - 1 if start and qf.tokens[start - 1] in ("ve", "ile") else start
                previous = columns_by_end.get(previous_end)
                if not previous or not aligned:
                    break
                separator = surface[surface_tokens[previous.span[1] - 1].end():surface_tokens[start].start()]
                if not re.fullmatch(r"\s*(?:,\s*)?(?:(?:ve|ile)\s+)?", separator):
                    break
                cursor = previous_end
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
            if k in consumed or not is_domain_candidate(tok) or self._modifier_candidate(qf.tokens, k, consumed):
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

        # A top-N of named entities is a grouped ranking, even without "bazında".
        if qf.limit is not None and any(h.semantic_type == SemanticType.METRIC for h in hits):
            for slot in hits:
                if slot.semantic_type == SemanticType.COLUMN and slot.mapping and slot not in sq.group_by:
                    sq.group_by.append(slot)
                    slot.explain["role"] = "rank_group_by"

        # 4g) grain: can this measure be attributed to the breakdown that was asked for?
        self._match_measure_to_grain(sq, hits, index)

        # 5) temporal
        sq.temporal = list(qf.temporal)
        sq.grain = qf.grain
        if not sq.temporal and sq.grain == "YEAR":
            span = self._all_years(sq, today or date.today())
            if span is not None:
                sq.temporal = [span]
                sq.explanation.append(
                    f"yıllık kırılım istendi, dönem söylenmedi → verinin tüm yılları ({span.params['from']}–{span.params['to']})")
        if not sq.temporal and self.default_temporal is not None:
            fallback = self.default_temporal() if callable(self.default_temporal) else self.default_temporal
            if fallback is not None:
                sq.temporal = [fallback]
                sq.explanation.append(f"dönem belirtilmedi → varsayılan {fallback.primitive} uygulandı")
        self._read_comparison(sq, qf, question, today or date.today())
        if sq.comparison:
            metric_entity = next((s.mapping.entity for s in sq.metrics if s.mapping), None)
            sq.comparison["entity"] = metric_entity
            sq.comparison["dateColumn"] = self.conventions.time_column(metric_entity) if metric_entity else None
        for t in sq.temporal:
            sq.explanation.append(describe(t))
        if not sq.grain and _asks_for_a_trend(question):
            sq.grain = "MONTH"
            sq.explanation.append("soru bir gidişat soruyor → sonuç ay ay kırılacak")
        for k, tok in enumerate(qf.tokens):
            if k in consumed or not (_is_trend_cue(tok) or _COUNT_CUE.fullmatch(fold(tok))):
                continue
            if self._modifier_candidate(qf.tokens, k, consumed) and self._modifies_a_noun(qf.tokens, k, consumed):
                continue            # "artan ürünler" narrows the subject; it is not just a trend cue
            consumed.add(k)         # a cue that shaped the query is accounted for, not missing

        self._account_modifiers(sq, qf, consumed, index)
        metric_entities = {s.mapping.entity for s in sq.metrics if s.mapping}
        for slot in sq.filters:
            if slot.mapping and slot.mapping.column:
                bindings = self.conventions.filter_bindings(slot.mapping)
                # A declared business equivalence can bind the same restriction
                # directly to the measure. A join or matching column name alone
                # cannot authorize this substitution.
                target = next(iter(metric_entities)) if len(metric_entities) == 1 else None
                choices = [b for b in bindings if b["entity"] == target
                           and b["source"] == "declared_business_filter"]
                if (slot.status in ("CERTIFIED", "INFERRED") and target in self.by_entity
                        and target != slot.mapping.entity and len(choices) == 1):
                    binding = choices[0]
                    original = slot.mapping
                    slot.mapping = replace(original, entity=target,
                        table_pattern=self.by_entity[target].table_pattern,
                        column=binding["column"], operator=binding["operator"], values=list(binding["values"]))
                    slot.status = "INFERRED"
                    slot.explain["binding_substitution"] = {
                        "from": {"entity":original.entity,"column":original.column,"values":list(original.values)},
                        "to":dict(binding), "source":"declared_business_filter"}
                    sq.explanation.append(f"'{slot.term}' filtresi katalogdaki eşdeğerlik tanımıyla ölçünün tablosuna bağlandı: {target}.{binding['column']}")
                    bindings = self.conventions.filter_bindings(slot.mapping)
                slot.explain["equivalent_bindings"] = bindings
        # A qualitative price judgment needs a business definition, not a
        # similarly named numeric column or a threshold invented by the model.
        for k, token in enumerate(qf.tokens):
            if stem(token) not in {stem("pahali"), stem("ucuz")}:
                continue
            proven = any(s.status == "CERTIFIED" and s.mapping and s.span[0] <= k < s.span[1]
                         for s in sq.slots)
            if not proven:
                sq.clarification.append(
                    f"‘{token}’ derken hangi fiyatı, para birimini ve hangi eşik veya karşılaştırma grubunu kastediyorsunuz?"
                )
                if token not in sq.unhandled:
                    sq.unhandled.append(token)

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
            if not is_domain_candidate(tok):
                # an inflected verb, a pronoun or a question particle says nothing about the catalog
                if tok not in sq.ignored:
                    sq.ignored.append(tok)
                continue
            generic_anchor = k - 1
            # A composed measure may leave its head ("tutari") unconsumed after
            # resolving "perakende satis". Follow only adjacent measure words
            # back to a resolved term, retaining standalone information fields.
            while generic_anchor >= 0 and generic_anchor not in consumed and folded_tokens[generic_anchor] in METRIC_VOCAB_S:
                generic_anchor -= 1
            if st in GENERIC_S and generic_anchor >= 0 and generic_anchor in consumed:
                # "toplam satış rakamı": a generic head noun sitting on a term that did resolve is
                # part of that phrase, not a second concept the catalog is missing. Only next to a
                # resolved word — on its own, "kod" is still a word the catalog may well define.
                if tok not in sq.ignored:
                    sq.ignored.append(tok)
                continue
            if tok not in sq.unresolved:
                sq.unresolved.append(tok)

        # 6b) a word the vocabulary has no entry for, looked for in the data itself. What the catalog
        #     does not define, the schema may still contain: the question is then about a column
        #     nobody wrote down, not about something this deployment has no answer for.
        self._from_data(sq, index, qf, consumed)

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
        # A grouping/filter entity is not the owner of the requested measure.
        # With no resolved measure, its creation date must not become an obligation.
        metric_entities = {s.mapping.entity for s in sq.metrics if s.mapping and s.status in ("CERTIFIED", "INFERRED")}
        entity = next(iter(metric_entities)) if len(metric_entities) == 1 else None
        from semantic_layer.runtime import periods

        if sq.temporal and entity:
            sq.temporal_binding = self.conventions.temporal_binding(entity)
        if sq.comparison and sq.temporal_binding:
            sq.comparison.update(entity=entity, dateColumn=sq.temporal_binding["column"])
        covered = periods.spans(self.tables_of.get(entity or "", []))
        window = (covered[0].isoformat(), covered[1].isoformat()) if covered else None
        if window and sq.temporal:
            first, last = covered
            for t in sq.temporal:
                if not (first and last and t.start and t.end):
                    continue
                status = "OUTSIDE_OBSERVED" if t.end <= first or t.start > last else (
                    "PARTIAL_OBSERVED" if t.start < first or t.end > last + timedelta(days=1) else "WITHIN_OBSERVED")
                sq.data_coverage.append({"entity": entity, "period": t.to_dict(), "status": status,
                                         "observedStart": window[0], "observedEnd": window[1],
                                         "completeness": "UNKNOWN", "source": "profile_observed_range"})
                if status == "OUTSIDE_OBSERVED":
                    sq.out_of_scope.append(t.text)
                    sq.explanation.append(
                        f"'{t.text}' gözlenen veri kapsamı dışında: {entity} kayıtları {window[0]}–{window[1]}. "
                        "Bu dönem için veri yok; satışın sıfır olduğu sonucuna varılamaz."
                    )
                elif status == "PARTIAL_OBSERVED":
                    sq.explanation.append(
                        f"'{t.text}' dönemi kısmen gözleniyor: {entity} kayıtları {window[0]}–{window[1]}. "
                        "Yükleme bütünlüğü doğrulanmadı; sonuç yalnız mevcut kayıtlara aittir."
                    )

        if sq.comparison:
            sq.comparison["alignment"] = "CALENDAR_PERIODS"
            sq.comparison["coverageComparable"] = False
            # Profile extrema cannot certify equally complete periods, even when
            # both requested windows lie inside them.
            sq.explanation.append(
                "Karşılaştırmada takvim dönemleri kullanıldı; dönemlerin eşit veri kapsamına sahip olduğu "
                "doğrulanmadı. Sonuç eş süreli performans değişimi olarak yorumlanmamalı."
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
        # Default row scopes belong to the semantic contract too. Otherwise the
        # model fallback can omit cancelled/non-item exclusions while deterministic
        # SQL applies them, returning different totals for the same measure.
        metric_entities = {slot.mapping.entity for slot in sq.metrics if slot.mapping}
        seen_defaults = set()
        for candidates in index.values():
            for concept, mappings in candidates:
                if concept.semantic_type != SemanticType.DEFAULT_FILTER:
                    continue
                for mapping in mappings:
                    key = (concept.id, mapping.entity, mapping.column)
                    if mapping.entity in metric_entities and key not in seen_defaults:
                        seen_defaults.add(key)
                        sq.slots.append(ResolvedSlot(term=concept.term, semantic_type=SemanticType.DEFAULT_FILTER,
                            status="CERTIFIED", mapping=mapping, confidence=1.0,
                            explain={"source": "catalog_default", "why": "ölçünün varsayılan satır kapsamı"}))
        return sq

    def _modifier_candidate(self, tokens, k, consumed):
        tok = tokens[k]
        if is_participle(tok) or is_negative(tok):
            return True
        # Ambiguous -an/-en is only a candidate in noun context, never a global
        # morphological fact ("en çok", brands and catalog terms keep their reading).
        return (len(tok) >= 4 and tok.endswith(("an", "en")) and stem(tok) == tok
                and self._modifies_a_noun(tokens, k, consumed))

    def _account_modifiers(self, sq, qf, consumed, index):
        for k, tok in enumerate(qf.tokens):
            if (any(tok in tokenize(t.text) for t in qf.temporal)
                    or (stem(tok) in STOPWORDS_S | MODIFIERS_S
                        and not self._modifies_a_noun(qf.tokens, k, consumed))):
                continue
            if not self._modifier_candidate(qf.tokens, k, consumed):
                continue
            covering = [s for s in sq.slots if s.span[0] <= k < s.span[1]]
            if k in consumed and not covering:
                continue  # a previously explained report/time/trend cue
            if covering and all(s.status == "CERTIFIED" and s.span == (k, k + 1) for s in covering) and not (is_participle(tok) or is_negative(tok)):
                # A certified noun ending in -en is not an unresolved modifier.
                continue
            left = [s for s in sq.slots if s.span[1] == k]
            right = [s for s in sq.slots if s.span[0] == k + 1]
            record = {"token": tok, "position": k, "decision": "UNKNOWN",
                      "evidence_source": "none", "structural_candidate": bool(left and right),
                      "light_verb_hint": is_light_verb(tok),
                      "recovered": not is_participle(tok) and not is_negative(tok)}
            # A full certified phrase already supplies its meaning. A join edge
            # or two neighbouring slots never supplies verb direction.
            if covering and all(s.mapping is not None for s in covering):
                # Something already placed this word — a certified phrase, or the verb-root bridge in
                # step 4a. Its meaning is accounted for; recording it a second time would put the same
                # measure in the query twice.
                record.update(decision="SEMANTIC", evidence_source="catalog",
                              concept_ids=[s.concept_id for s in covering],
                              resolved_as=",".join(sorted({f"{s.semantic_type}:{s.status}" for s in covering})))
            elif is_negative(tok) and (root := verb_root(tok)) and (named := self._metric_keys_for_root(root, index)):
                sq.shape = "ABSENCE"
                record.update(decision="ABSENCE", evidence_source="catalog", verb_root=root)
                sq.explanation.append(f"'{tok}' olumsuz: '{named[0][0]}' ölçüsünün hiç gerçekleşmediği kayıtlar isteniyor")
            elif not is_negative(tok) and (root := verb_root(tok)) and (selected := [
                    slot for slot in sq.slots if slot.semantic_type == SemanticType.METRIC
                    and slot.concept_id in {c.id for _, senses in self._metric_keys_for_root(root, index)
                                           for c, _ in senses}]):
                # The user supplied the measure explicitly. Its certified names
                # already account for this verb; never add a conflicting money measure.
                record.update(decision="SEMANTIC", evidence_source="explicit_catalog_metric",
                              concept_ids=[slot.concept_id for slot in selected], recovered=True)
            elif not is_negative(tok) and (metric := self._metric_from_verb(tok, k, index)) is not None:
                # The word is the verbal form of a measure this catalog defines: "en çok satan" ranks
                # by "satış". Not grammar to be discarded — a measure to be used, recorded with the
                # concept it came from. Bridging is refused where it would change meaning: a negative
                # never reaches here, and a root that reaches two different measures returns nothing.
                sq.slots.append(metric)
                record.update(decision="SEMANTIC", evidence_source="catalog",
                              concept_ids=[metric.concept_id],
                              resolved_as=f"{metric.semantic_type}:{metric.explain.get('evidence_key')}")
                sq.explanation.append(f"'{tok}' → '{metric.explain.get('evidence_key')}' ölçüsü (fiil kökünden, sertifikalı değil)")
            elif not is_negative(tok) and (proof := self.modifier_history.lookup(qf.tokens, k)):
                record.update(decision="GRAMMATICAL", evidence_source="history", pair_ids=proof)
            if record["decision"] == "UNKNOWN":
                if tok not in sq.unhandled:
                    sq.unhandled.append(tok)
                sq.clarification.append(f"‘{tok}’ ile hangi koşulu kastediyorsunuz? Bu ifadenin hangi kayıtları seçmesi gerektiğini belirtir misiniz?")
            consumed.add(k)
            sq.modifiers.append(record)
            sq.explanation.append(f"'{tok}' niteleyici: {record['decision']} (kanıt: {record['evidence_source']})")

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
            slot = self._metric_from_verb(tok, k, index)
            if slot is not None:
                consumed.add(k)
                return slot
        return None

    def _metric_from_verb(self, tok: str, k: int, index: dict[str, list[tuple[Concept, list[Mapping]]]]) -> Optional[ResolvedSlot]:
        """"satan" → the measure the catalog keys on the same root ("satış"), or nothing.

        The form of the word gets us here; the catalog decides. A root that reaches no certified
        measure, or reaches two different ones, returns nothing rather than a guess — and a negative
        never bridges, because "satmayan" is the opposite of "satış" and bridging it would invert the
        answer. What comes back is a measure slot, not a verdict that the word was noise: nothing is
        dropped, and which concept was used is written into the slot.
        """
        for _ in (0,):
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
                # ambiguity. Different measures are, and the catalog says which is which: a concept that
                # declares another's name among its synonyms is that measure under a second name. Read
                # as two, this refused "en çok satan" outright — the root reaches "satış" and "satış
                # tutarı", and treating a declared synonym pair as a disagreement says nothing at all.
                found = {c.id: c for _, senses in matches for c, _ in senses if c.semantic_type == SemanticType.METRIC}
                if len(found) > 1 and not _one_measure_under_two_names(found.values()):
                    continue                 # genuinely different measures: say nothing rather than guess
                matches = [min(matches, key=lambda m: (len(m[0].split()), len(m[0])))]
            key, senses = matches[0]
            slot = self._slot_from_senses(key, tok, senses, (k, k + 1))
            if slot is None or slot.semantic_type != SemanticType.METRIC:
                continue
            slot.status = "INFERRED"
            slot.confidence = min(slot.confidence, 0.7)
            slot.explain["why"] = f"'{tok}' fiilinin kökü ({root}) yalnız '{key}' ölçüsüyle eşleşiyor"
            slot.explain["source"] = "verb_root"
            slot.explain["evidence_key"] = key
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

    def _read_comparison(self, sq: SemanticQuery, qf: Any, question: str, today: date) -> None:
        """"geçen yıla göre" — bir karşılaştırma isteği, tek bir dönem değil.

        Bu ifade tek bir dönem olarak ayrıştırılıyordu ve seçilen dönem *referans* olandı: soru "bu
        yıl geçen yıla göre nasıl" iken cevap yalnız geçen yılın rakamıydı. Ne karşılaştırma vardı,
        ne de eksikliği söyleniyordu — cevap tek bir sayı olarak, başarılı görünerek dönüyordu.

        Buradaki iş yalnız ikinci dönemi eklemek değil: isteğin kendisi kaydediliyor, ki çalıştırma
        öncesinde "iki dönem gerçekten plana ve SQL'e taşındı mı" diye sorulabilsin.
        """
        if len(sq.temporal) == 2:
            current, reference = sorted(sq.temporal, key=lambda t: t.start or date.min, reverse=True)
            sq.comparison = {"kind": "PERIOD", "current": current.to_dict(),
                             "reference": reference.to_dict(), "satisfied": False}
            return
        if len(sq.temporal) != 1 or not _COMPARE_TO.search(fold(question)):
            return
        reference = sq.temporal[0]
        if not (reference.start and reference.end):
            return
        # Infer the current calendar unit from the request clock, not the default
        # window or the end of a named historical reference (2019 does not imply 2020).
        from semantic_layer.runtime.temporal import parse_temporal
        unit = {"YEAR": "bu yıl", "MONTH": "bu ay", "WEEK": "bu hafta", "DAY": "bugün", "QUARTER": "bu çeyrek"}.get(reference.grain)
        periods, _ = parse_temporal(unit, today) if unit else ([], None)
        current = periods[0] if len(periods) == 1 else None
        if current is None or not (current.start and current.end):
            # Neye göre karşılaştırılacağı belli değil. Tek dönemlik cevabı karşılaştırma diye
            # sunmaktansa istek kayda geçer ve denetim bunu yakalar.
            sq.comparison = {"kind": "PERIOD", "reference": reference.to_dict(), "current": None,
                             "satisfied": False, "why": "karşılaştırılacak güncel dönem belirlenemedi"}
            sq.explanation.append(f"'{reference.text}' bir karşılaştırma isteği ama güncel dönem belirlenemedi")
            return
        if (current.start, current.end) == (reference.start, reference.end):
            sq.comparison = {"kind": "PERIOD", "reference": reference.to_dict(), "current": None, "satisfied": False}
            sq.clarification.append(f"{reference.text} ile hangi dönemi karşılaştırmak istiyorsunuz?")
            return
        # The default period's own label is an internal word ("varsayılan") and it ends up as a column
        # name the reader sees. Name it by what it is.
        if current.start and (not current.text or "varsay" in fold(current.text)):
            # This label becomes a column name the reader sees, so it says what the period is rather
            # than repeating an internal word. The end is exclusive: 2026-01-01 … 2027-01-01 is the
            # year 2026, not a span of two.
            last = (current.end - timedelta(days=1)) if current.end else current.start
            if current.start == date(current.start.year, 1, 1) and last == date(current.start.year, 12, 31):
                label = "bu yıl"
            elif (current.start.day, current.start.year, current.start.month) == (1, last.year, last.month):
                label = "bu ay"
            else:
                label = "bu dönem"
            current = replace(current, text=label)
        sq.temporal = [current, reference]
        sq.comparison = {"kind": "PERIOD", "reference": reference.to_dict(), "current": current.to_dict(),
                         "satisfied": False}
        sq.explanation.append(
            f"'{reference.text}' karşılaştırma isteği: {current.start}–{current.end} ile "
            f"{reference.start}–{reference.end} yan yana istendi"
        )

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
        key = metric.explain.get("normalized") or normalize_term(metric.term)
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

    def _word_forms(self, word: str) -> list[str]:
        """Bir kelimenin, kolon adlarıyla buluşabileceği biçimleri.

        Kolon adları indekste çekimsiz duruyor ("BARKOD"), soru ise çekimli geliyor ("barkodu").
        Kökü almadan ikisi hiç karşılaşmıyor — arama boş dönüyor ve kelime "veride yok" sayılıyor.
        """
        forms = [word, fold(word), stem(word), short_root(word)] + derived_forms(word)
        return [f for f in dict.fromkeys(forms) if f and len(f) >= 3]

    def _from_data(self, sq: SemanticQuery, index: dict, qf: Any = None, consumed: Optional[set] = None) -> None:
        """Sözlükte olmayan kelimeyi şemanın kendisinde ara; yeterince baskınsa oku, değilse aday bırak.

        İki ayrı sessiz hata için: bir kelime ya reddediliyor ("tanımlı bir kavram değil") ya da
        gramer sayılıp atılıyor — ikisinde de veride duran karşılığına hiç bakılmıyor. Atılmış bir
        kelimenin şemada güçlü bir karşılığı varsa o kelime gramer değil, içerikti; kararı morfoloji
        değil kanıt versin.

        Bulunan hiçbir şey sertifikalı sayılmaz: slot INFERRED olarak işaretlenir, cevap "doğrulanmış"
        damgası almaz ve ne okunduğu ize yazılır.
        """
        if self.columns is None:
            return
        # A word the resolver could not place, or dropped as grammar. Never a word it *did* place by
        # other means: an entity word names a table, and reading "müşteri" as a column would answer
        # by a breakdown nobody asked for.
        skip = STOPWORDS_S | MODIFIERS_S | METRIC_VOCAB_S | _ENTITY_WORDS | _TIME_WORDS
        def _worth(w: str) -> bool:
            return len(w) >= 4 and not {stem(w), short_root(w), fold(w)} & skip
        looked = [w for w in sq.unresolved if _worth(w)] + [w for w in sq.ignored if _worth(w)]
        # A word that *is* a column name. Step 6 passes over it — it is plainly not a missing business
        # term — but nothing then reads it either, so the question is answered as though it had not
        # been said. Naming a column outright is the strongest evidence a question can carry.
        for k, tok in enumerate(getattr(qf, "tokens", []) or []):
            if (consumed and k in consumed) or tok.upper() not in self.column_names:
                continue
            if _worth(tok) and tok not in looked:
                looked.append(tok)
        if not looked:
            return
        primary = self._primary_entity(sq.slots)
        near = self._related_entities(primary) | {primary} if primary else set()
        for word in dict.fromkeys(looked):
            best: dict[tuple[str, str], dict] = {}
            for form in self._word_forms(word):
                # Wide on purpose: a column name like NETTOTAL is carried by dozens of tables, and a
                # short list is whichever copies scored highest — the base table the business runs on
                # need not be among them. The ranking below is what chooses; this only has to see it.
                for hit in (self.columns.search(form, limit=40) or []):
                    # Only a hit on the column's own name counts as a reading of this word. A word
                    # that merely occurs among a column's values says what to filter for, not what
                    # the column is, and taking it for a column is how "fark" becomes a transaction
                    # type nobody asked about.
                    if form not in _identifier_words(hit["column"]):
                        continue
                    key = (hit["entity"], hit["column"])
                    if hit["score"] > best.get(key, {}).get("score", 0):
                        best[key] = hit
            if not best:
                continue
            by_column: dict[str, list[dict]] = {}
            for hit in best.values():
                by_column.setdefault(hit["column"], []).append(hit)
            ranked = sorted(by_column.items(), key=lambda kv: -max(h["score"] for h in kv[1]))
            top_col, top_hits = ranked[0]
            top = max(h["score"] for h in top_hits)
            runner = max((h["score"] for _, hs in ranked[1:] for h in hs), default=0.0)
            sq.candidates.append({"term": word, "column": top_col,
                                  "entities": [h["entity"] for h in sorted(top_hits, key=lambda h: -h["score"])][:4],
                                  "score": round(top, 2), "runnerUp": round(runner, 2)})
            # One name, clearly ahead of any other. Several tables carrying that same name is not
            # ambiguity about *what* was meant — it is a choice of table, and the question's own
            # subject settles it. A name that only exists far from the subject would answer a
            # different question, so it is left as a candidate instead.
            if runner and top < runner * _DOMINANT:
                continue
            # Among the tables carrying that name, a base table before a view and a full one before an
            # empty one. Ranked by search score alone the answer lands in whichever hand-made copy
            # scored highest, and the question is answered from a report view instead of the table
            # the business runs on.
            def _own_rank(hit: dict) -> tuple:
                pr = self.by_entity.get(hit["entity"])
                rows = (pr.row_count or 0) if pr else 0
                is_view = pr.row_count is None if pr else True
                name = pr.table_name if pr else hit["entity"]
                # A dated copy of a table carries the same columns and scores like the original. Last,
                # always: answering from someone's 2017 backup is answering a different question.
                return (is_shadow_copy(name), source_rank(name, is_view=is_view), -rows, -hit["score"])
            owners = [h["entity"] for h in sorted(top_hits, key=_own_rank)]
            # Only on or beside what the question is already about. Without a subject there is
            # nothing to judge a table against, and the best-scoring copy of a column name is as
            # likely to be a report view or someone's dated backup as the table the business runs
            # on — this deployment offered a 2017 copy of the invoice table. A candidate that cannot
            # be placed is reported, not assumed.
            pick = next((e for e in owners if e in near), None)
            if pick is None:
                continue
            prof = self.by_entity.get(pick)
            if prof is None or prof.column(top_col) is None:
                continue
            m = Mapping(concept_id="", entity=pick, table_pattern=prof.table_pattern, column=top_col, operator="COLUMN")
            sq.slots.append(ResolvedSlot(term=word, semantic_type=SemanticType.COLUMN, status="INFERRED",
                                         mapping=m, confidence=0.5,
                                         explain={"why": f"katalogda yok; şemada {pick}.{top_col} ile eşleşti",
                                                  "source": "column_index", "normalized": stem(word)}))
            if word in sq.unresolved:
                sq.unresolved.remove(word)
            if word in sq.ignored:
                sq.ignored.remove(word)
            sq.explanation.append(f"'{word}' → {pick}.{top_col} olarak okundu (veride eşleşti, sertifikalı değil)")

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
