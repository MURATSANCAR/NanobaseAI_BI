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
    number_role,
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
# Copula participles: grammar that attaches one phrase to another ("tüm satış yerlerimizle olan
# ciromuz"). They restrict nothing and must never reach the clarification step.
_COPULA = frozenset("olan oldugu olup olsun olacak olmus bulunan bulundugu duran durmakta gorunen gozuken".split())
# Verbs of a record's own existence or arrival, spoken before the noun they belong to. "Açılan
# sipariş" is every order, "kesilen fatura" every invoice, "iade alan müşteri" a customer whose
# returns the return filter already selects. None of them is a restriction the catalog must define.
#: Turkish forms most state verbs with an auxiliary ("iptal *edildi*", "sevk *edilen*"). The auxiliary
#: carries the tense and the polarity; the state itself is the noun beside it. As a search key it would
#: match every label the source ever wrote in the passive, so it is never one.
_AUXILIARY_ROOTS = ("edil", "edile", "edilm", "ediliyor", "olun", "olus", "yapil", "gerceklestiril")

_RECORD_VERBS = frozenset("""acilan acilmis kesilen kesilmis duzenlenen duzenlenmis olusturulan olusan olusmus
    yapilan yapilmis gerceklesen gerceklestirilen verilen gelen alan alinan giren girilen cikan islenen
    kaydedilen kayitli tutulan""".split())
# Converb (-Ip) forms of the same record verbs ("geçen yıl alıp satmış", "sipariş verip vazgeçmiş").
# A verb in converb form is as grammatical as in participle form ("alan"), but the short -Ip suffix
# cannot be told from an ordinary noun by morphology alone (the catalog carries "grup", "tip", "slip",
# "takip", "sahip"), so the converbs of the everyday record verbs are listed rather than derived. Kept
# out of the phrase-fragment backoff, they no longer bind "alıp" to the trade-goods value label
# "alıp sattık" (ITEMS.CARDTYPE=1) and turn a customer's purchase into a material-card-type filter.
_RECORD_CONVERBS = frozenset("""alip alinip verip gelip girip cikip satip gonderip acilip kesilip
    duzenlenip olusturulup olusup yapilip islenip kaydedilip tutulup gerceklesip""".split())
_DEGREE_ADVERBS = frozenset("tamamen tumuyle butunuyle hala halen henuz gercekten gercekte fiilen aslinda hakikaten".split())
# "maliyetin altında", "hedeften düşük", "limitin üzerinde", "eşiği aşan": a postposition or adjective
# that compares the measure beside it with something else (another column or a threshold). Every one is
# grammar to `is_domain_candidate`, so — placed directly after a resolved measure — it was dropped into
# `ignored` and the comparison it makes was never recorded. The gate then had no obligation to check and
# the deterministic answer served "the total cost per customer" for "sold below cost": a confident number
# for a wider question. Left to the model as an obligation instead (a `-- yorum:` and a real restriction),
# not resolved to any specific column here — the catalog names no value for the threshold.
# "geçen/aşağı/yukarı" alone are left out: "geçen ay/yıl" is a period, not a comparison, and would
# collide with the temporal reader; "aşan" is unambiguous.
_COMPARATORS = frozenset("altinda altindaki alti ustunde ustundeki ustu uzerinde uzerindeki uzeri "
                         "asagisinda dusuk asan asani".split())
_BREAKDOWN_CUES = frozenset("bazinda bazli basina gore kiriliminda kirilimli ozelinde".split())
_ENTITY_WORDS = frozenset(stem(w) for w in "fatura musteri cari tedarikci kitap urun malzeme stok siparis satir hareket belge kayit firma sirket sube depo kart karti".split())
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
# "kaç kalem / kaç satır": the unit asked for is the line itself, whatever document key the concept counts by.
_LINE_UNIT = re.compile(r"\b(kalem|kalemi|kalemleri|satir|satiri|satirlari)\b")
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
_RANK_CUE = frozenset("en ilk top bastaki basta cok fazla yuksek dusuk buyuk".split())
#: These rank only as a superlative. After an ablative they compare ("birden fazla", "yüzden yüksek").
_COMPARATIVE_CUE = frozenset("cok fazla yuksek dusuk buyuk".split())
_ABLATIVE = re.compile(r"(?:den|dan|ten|tan)$")


def _rank_cue_before(tokens: list[str], k: int, span: int) -> bool:
    """Is one of the `span` words before tokens[k] a ranking cue — and used as one?"""
    for j in range(max(0, k - span), k):
        word = fold(tokens[j])
        if word not in _RANK_CUE:
            continue
        if word in _COMPARATIVE_CUE and j > 0 and _ABLATIVE.search(fold(tokens[j - 1])):
            continue
        return True
    return False
_WHICH = frozenset("hangi hangisi hangileri kim kimler kimin kimden".split())
# "payı yüzde kaç" asks for a share: a plain total is a different answer, not a rounder one.
_SHARE_CUE = re.compile(r"\b(pay|payi|payin|paylari|paylarini|yuzde|yuzdesi|yuzdelik)\b")
#: "iade hariç", "iptaller dışında", "fuar haricinde": the label right before is what the answer leaves out.
_EXCLUDE_CUE = frozenset("haric harici haricinde disinda disindaki olmadan olmaksizin".split())
#: "indirim yüzdesi tanımlı", "vadesi girilmiş", "grup kodu dolu": the column right before carries a value.
_DEFINED_CUE = frozenset("tanimli tanimlanmis tanimlanan dolu girilmis girili belirlenmis atanmis".split())
#: "cirosu olan müşteri", "hedefi olan ürün", "borcu bulunan cari": a possessive-marked measure/column
#: named and then said to *exist*. Reads like the copula (_COPULA) but here it is an existence condition
#: on that column — the same "has a value" reading as _DEFINED_CUE, spoken with "olan/bulunan/olup".
_EXISTENCE_COPULA = frozenset("olan bulunan olup".split())
#: "X, Y'nin ne kadarı?", "X Y'nin yüzde kaçı?", "X'in Y'ye oranı": two measures, one divided by the other.
_RATIO_CUE = re.compile(r"\b(ne kadari|ne kadarini|kacta kaci|yuzde kaci|yuzde kacini|orani|oranini|oran)\b")


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


#: "Yıllık ciro" bu yılın yıllık tutarını da anlatabilir; yıllara YAYILMAYI yalnız açık kırılım ister.
_YEARLY_BREAKDOWN = re.compile(r"\b(yillara gore|yil yil|yil bazinda|yillar bazinda|yillara bol\w*|her yil)\b")


def _negated_record_verb(tok: str) -> bool:
    """"kesilmemiş", "açılmamış", "verilmemiş": the negation of a verb that only says a record came to
    exist ("kesilen fatura"). Negated, the record does not exist — an absence, like a light verb's."""
    root = verb_root(tok) or ""
    base = re.sub(r"(ma|me)$", "", root)
    return bool(base) and base in {verb_root(v) for v in _RECORD_VERBS}


def _negated_light_verb(tok: str) -> bool:
    """"edilmemiş", "verilmedi", "olmamış": a light verb carrying the negation. `is_light_verb` knows the
    affirmative roots; the negation infix hides them, so it is stripped first."""
    root = verb_root(tok) or ""
    base = re.sub(r"(ma|me)$", "", root)
    return bool(base) and (is_light_verb(base) or base in {"et", "ed", "edil", "ol", "olun", "yap", "yapil", "ver", "veril", "al", "alin", "kil", "kilin", "bulun", "gel", "gecir"})


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
        # A written-out number is a number: "beş" is the five of "en pahalı beş yazar", not a term the
        # catalog may know as a column ("5 yaş"). Bare cardinals are never looked up.
        qf.terms = [t for t in qf.terms if not (t[1] - t[0] == 1 and cardinal(qf.tokens[t[0]]) is not None)]
        # In a ranking request, an explicitly named certified measure (including
        # parenthesized units) must not be discarded as generic query grammar.
        rank_requested = qf.limit is not None or any(
            cardinal(token) is not None and 2 <= cardinal(token) <= 1000
            and number_role(qf.tokens, k) == "count" and _rank_cue_before(qf.tokens, k, 3)
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
        # The words the temporal parser read — "geçen çeyrekte", and the grain phrase "ay ay" — are
        # spent: looked up again, "ay" found a CRM project-month column and "çeyrek" a sales-quarter
        # field, and both were then reported as words the catalog cannot place.
        consumed.update(self._temporal_positions(qf))
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
            after = qf.tokens[slot.span[1] + 1] if slot.span[1] + 1 < len(qf.tokens) else ""
            if fold(after) in _BREAKDOWN_CUES:
                # "ciroyu kitap bazında", "tirajı kitap bazında": the entity word opens a breakdown
                # phrase of its own; it is not the head of a document name the measure modifies.
                continue
            if stem(nxt) in _ENTITY_WORDS:
                hits.remove(slot)
                sq.explanation.append(f"'{slot.term} {nxt}' bir belge türü olarak okundu, ölçü değil")

        # 2d) "bekleyen sipariş adedi": a bare count word right after a resolved term asks how many of
        #     *that* thing there are. The catalog also certifies "adet" as a measure of its own (sold
        #     quantity on the sales lines) — read that way the question moved to another table, and
        #     the gate then looked for the period on a table the answer never read.
        for slot in list(hits):
            if slot.semantic_type != SemanticType.METRIC or slot.span[1] - slot.span[0] != 1 or not slot.mapping:
                continue
            k = slot.span[0]
            if not _COUNT_CUE.fullmatch(fold(qf.tokens[k])):
                continue
            # After a named set of records ("bekleyen sipariş", "fatura") the word counts them. After a
            # measure ("satışta adet") or a breakdown column ("kitap adet") it is the quantity measure.
            # "stok adedi", "elde kalan stok miktarı": after a *state* measure the word is only its unit —
            # the balance is already a quantity. Kept, it added the sold-quantity measure beside the
            # stock and dragged the default year onto a balance that has no period.
            state_before = [h for h in hits if h is not slot and h.mapping and h.span and h.span[1] == k
                            and h.semantic_type == SemanticType.METRIC and (h.mapping.extra or {}).get("state_measure")]
            if state_before:
                hits.remove(slot)
                sq.explanation.append(f"'{qf.tokens[k]}' '{state_before[0].term}' ölçüsünün birimi olarak okundu")
                continue
            left = [h for h in hits if h is not slot and h.mapping and h.span and h.span[1] == k
                    and h.semantic_type in (SemanticType.DIMENSION_VALUE, SemanticType.ENTITY)]
            if left and all(h.mapping.entity != slot.mapping.entity for h in left):
                hits.remove(slot)
                consumed.discard(k)
                sq.explanation.append(f"'{qf.tokens[k]}' sayım sözcüğü olarak okundu: '{left[0].term}' kayıtları sayılır, "
                                      f"{slot.mapping.entity} ölçüsü değil")

        # 2f) "iade hariç toplam ciro": the label is named in order to be left out. Read as a filter it
        #     asked for the returns alone, and the gate refused every statement that did what was asked.
        for k, tok in enumerate(qf.tokens):
            if k in consumed or fold(tok) not in _EXCLUDE_CUE:
                continue
            label = next((h for h in hits if h.semantic_type == SemanticType.DIMENSION_VALUE and h.mapping and h.mapping.column
                          and h.span and h.span[1] == k and (h.mapping.operator or "IN").upper() in ("IN", "=")), None)
            if label is None:
                continue
            m0 = label.mapping
            label.mapping = Mapping(concept_id=m0.concept_id, entity=m0.entity, table_pattern=m0.table_pattern, column=m0.column,
                                    operator="NOT IN", values=list(m0.values), extra=dict(m0.extra or {}))
            label.status = "INFERRED"
            label.term = f"{label.term} {tok}"
            label.span = (label.span[0], k + 1)
            label.explain = {**(label.explain or {}), "source": "exclude_cue",
                             "why": f"'{label.term}': {m0.entity}.{m0.column} NOT IN ({', '.join(map(str, m0.values))}) — dışarıda bırakılır"}
            consumed.add(k)
            sq.explanation.append(label.explain["why"])

        # 2e) "kartında indirim yüzdesi tanımlı müşteriler": a column named and then said to be filled.
        #     The word is a condition on that column — non-zero for a number, non-empty for text — not
        #     a word the catalog lacks. Left unread, the question was refused for "tanımlı".
        for k, tok in enumerate(qf.tokens):
            if k in consumed or fold(tok) not in _DEFINED_CUE:
                continue
            col_slot = next((h for h in hits if h.semantic_type == SemanticType.COLUMN and h.mapping and h.mapping.column
                             and h.span and h.span[1] == k), None)
            if col_slot is None:
                continue
            prof = self.by_entity.get(col_slot.mapping.entity)
            column = prof.column(col_slot.mapping.column) if prof else None
            if column is None:
                continue
            numeric = any(t in (column.data_type or "").lower() for t in ("int", "float", "decimal", "numeric", "money", "real", "double", "bit"))
            m = Mapping(concept_id="", entity=col_slot.mapping.entity, table_pattern=col_slot.mapping.table_pattern,
                        column=column.name, operator="<>", values=["0" if numeric else ""])
            hits.append(ResolvedSlot(term=f"{col_slot.term} {tok}", semantic_type=SemanticType.DIMENSION_VALUE, status="INFERRED", mapping=m,
                                     confidence=0.8, span=(k, k + 1),
                                     explain={"source": "defined_cue", "why": f"'{tok}': {m.entity}.{m.column} dolu olan kayıtlar ({m.column} <> {m.values[0]!r})"}))
            consumed.add(k)
            sq.explanation.append(f"'{col_slot.term} {tok}' → {m.entity}.{m.column} <> {m.values[0]!r} (değeri girilmiş kayıtlar)")

        # 2e-bis) "cirosu olan müşteriler", "hedefi bulunan ürünler", "borcu olup kapanmamış cariler": a
        #     possessive-marked measure or column named and then said to *exist* ("olan/bulunan/olup") is a
        #     condition that its value is present — non-zero for a number, non-empty otherwise — on the rows
        #     kept. It looks like the grammatical copula (_COPULA, which the modifier pass consumes and
        #     discards) and so was dropped, leaving "X olan" unread and the answer computed over every row.
        #     Read here it becomes the same "has a value" filter a _DEFINED_CUE builds. Guarded tightly so
        #     the plain copula is untouched: the word right before must be a resolved measure/column that
        #     carries a third-person possessive suffix ("cirosu", "hedefi"; a bare noun keeps its copular
        #     reading, as in "… ile olan bakiye"), and "olan" must lead into a following noun.
        for k, tok in enumerate(qf.tokens):
            if k in consumed or fold(tok) not in _EXISTENCE_COPULA or k + 1 >= len(qf.tokens):
                continue
            src = next((h for h in hits if h.mapping and h.mapping.column and h.span and h.span[1] == k
                        and h.semantic_type in (SemanticType.COLUMN, SemanticType.METRIC)), None)
            if src is None:
                continue
            head = (src.term or "").split()[-1] if (src.term or "").split() else ""
            if not head or head[-1] not in "ıiuüIİUÜ":     # 3rd-person possessive vowel (-ı/-i/-u/-ü, incl. -sı/-si/…)
                continue
            prof = self.by_entity.get(src.mapping.entity)
            column = prof.column(src.mapping.column) if prof else None
            if column is None:
                continue
            numeric = any(t in (column.data_type or "").lower() for t in ("int", "float", "decimal", "numeric", "money", "real", "double", "bit"))
            m = Mapping(concept_id="", entity=src.mapping.entity, table_pattern=src.mapping.table_pattern,
                        column=column.name, operator="<>", values=["0" if numeric else ""])
            hits.append(ResolvedSlot(term=f"{src.term} {tok}", semantic_type=SemanticType.DIMENSION_VALUE, status="INFERRED", mapping=m,
                                     confidence=0.75, span=(k, k + 1),
                                     explain={"source": "existence_copula", "why": f"'{src.term} {tok}': {m.entity}.{m.column} değeri olan kayıtlar ({m.column} <> {m.values[0]!r})"}))
            consumed.add(k)
            sq.explanation.append(f"'{src.term} {tok}' → {m.entity}.{m.column} <> {m.values[0]!r} (değeri olan kayıtlar)")

        # 2g) one measure named twice ("elde kalan stok") is one measure: the second name is dropped, or
        #     the answer carries the same column twice.
        seen_metric: set[str] = set()
        for slot in list(hits):
            if slot.semantic_type == SemanticType.METRIC and slot.concept_id:
                if slot.concept_id in seen_metric:
                    hits.remove(slot)
                else:
                    seen_metric.add(slot.concept_id)

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
            if k in consumed or not is_domain_candidate(tok) or self._modifier_candidate(qf.tokens, k, consumed) or cardinal(tok) is not None:
                continue
            if fold(tok) in _RECORD_CONVERBS:
                # A record verb in converb form ("alıp") is grammar; the second-chance backoff would
                # otherwise bind it to the first word of a verb-phrase label ("alıp sattık"). Left for
                # step 6, where its record-verb reading drops it as a word that does not narrow rows.
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

        # 4f) "en yüksek beş kanal" — a written-out number after a ranking cue is a top-N. The cue may
        #     sit a few words back ("en çok kâr bıraktığımız on müşteri"): the whole clause before the
        #     number is looked at. A number naming a span ("son üç ay", "doksan gün") is not a count.
        if qf.limit is None:
            for k, tok in enumerate(qf.tokens):
                n = cardinal(tok)
                if n is None or n < 2 or n > 1000 or re.fullmatch(r"(19|20)\d\d", tok):
                    continue
                nxt = qf.tokens[k + 1] if k + 1 < len(qf.tokens) else ""
                if nxt and (stem(nxt) in _TIME_WORDS or short_root(nxt) in _TIME_WORDS or cardinal(nxt) is not None):
                    continue
                if not _rank_cue_before(qf.tokens, k, 7):
                    continue
                if number_role(qf.tokens, k) == "value":
                    # "toplamı yüzü aşan", "yüzde yirmi iskonto", "bini geçen": the number is what a
                    # column is compared with. Read as a top-N it cut the answer at that many rows
                    # without anyone having asked for a cap.
                    sq.explanation.append(f"'{tok}' karşılaştırma değeri olarak okundu ({n}); satır sınırı konmadı")
                    continue
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
        # "son iki yılda nasıl değişti": a change over a window of whole years is read year by year —
        # one figure for the window would answer "how much", not "how did it change".
        if not sq.grain and sq.temporal and re.search(r"\b(nasil degis|degisim|degisti|degismis|seyri|trend)", fold(question)):
            t0 = sq.temporal[0]
            if getattr(t0, "start", None) and getattr(t0, "end", None) and (t0.end.year - t0.start.year) >= 2 and t0.start.month == 1 and t0.start.day == 1:
                sq.grain = "YEAR"
                sq.explanation.append("çok yıllık pencerede değişim soruldu → yıl bazında kırılım")
        # "bu ara", "son günlerde": a period the person did not bound. Left to whoever writes the
        # statement, a range was picked silently and the figure looked like an answer to the question;
        # the range is the person's to give, so it is asked for — once, with examples.
        for t in sq.temporal:
            if t.ambiguous and t.text:
                ask = f"‘{t.text}’ için hangi dönemi kastediyorsunuz? (ör. son 30 gün, bu ay, bu çeyrek, bu yıl)"
                if ask not in sq.clarification:
                    sq.clarification.append(ask)
                    sq.explanation.append(f"'{t.text}' belirsiz bir dönem: tarih aralığı soruldu")
        if not sq.temporal and sq.grain == "YEAR" and _YEARLY_BREAKDOWN.search(fold(question)):
            span = self._all_years(sq, today or date.today())
            if span is not None:
                sq.temporal = [span]
                sq.explanation.append(
                    f"yıllık kırılım istendi, dönem söylenmedi → verinin tüm yılları ({span.params['from']}–{span.params['to']})")
        # A default period belongs to a question about something that *happens* on a date: a
        # certified measure (ciro, tahsilat, sevk). A question about master data — which customers,
        # which price lists, how many products carry a unit — has no date to restrict, and a year added
        # to it was a restriction nobody asked for that the gate then could not find on any column.
        # A count the resolver composed from "kaç" is not a certified measure either.
        placed = [s_ for s_ in hits if s_.mapping is not None]
        # A state measure (stock on hand) is a balance over every movement: it has no period of its own,
        # and a default year put on it made the gate refuse the statement — or, worse, a model date it.
        # Nor is a measure the resolver composed over a card's column ("liste fiyatları", "önerilen
        # baskı adedi"): an attribute of a record, not something that happened on a date.
        undated = bool(placed) and not any(s_.semantic_type == SemanticType.METRIC
                                           and s_.status in ("CERTIFIED", "INFERRED")
                                           and (s_.explain or {}).get("source") != "count_cue"
                                           and not (s_.mapping.extra or {}).get("state_measure")
                                           and not (s_.mapping.extra or {}).get("undated")   # a cost on a card, not an event
                                           for s_ in placed)
        default_applied = False
        if not sq.temporal and self.default_temporal is not None and not undated:
            fallback = self.default_temporal() if callable(self.default_temporal) else self.default_temporal
            if fallback is not None:
                sq.temporal = [fallback]
                default_applied = True
                sq.explanation.append(f"dönem belirtilmedi → varsayılan {fallback.primitive} uygulandı")
        elif not sq.temporal and undated:
            sq.explanation.append("dönem belirtilmedi ve soru tarihli bir ölçü sormuyor → tüm kayıtlar üzerinden")
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
        price_rank: Optional[bool] = None
        for k, token in enumerate(qf.tokens):
            if stem(token) not in {stem("pahali"), stem("ucuz")}:
                continue
            proven = any(s.status == "CERTIFIED" and s.mapping and s.span[0] <= k < s.span[1]
                         for s in sq.slots)
            # "en pahalı beş yazar" beside a measure of money is a ranking by that measure, not a
            # price judgment needing a threshold: the superlative says which end of the order.
            ranked = (k > 0 and fold(qf.tokens[k - 1]) == "en"
                      and any(s.semantic_type == SemanticType.METRIC and s.mapping for s in sq.slots))
            if ranked:
                price_rank = stem(token) == stem("pahali")
                consumed.add(k)
                sq.explanation.append(f"'en {token}' → ölçüye göre {'azalan' if price_rank else 'artan'} sıralama")
                continue
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
            if _GROUP_MARKERS.fullmatch(st) or _GROUP_MARKERS.fullmatch(tok):
                continue
            if tok.upper() in self.column_names:
                # A word that is literally a column name is already answered — but only on a table
                # this question reads. Matched against every column in the catalog, "tahsilat" was
                # swallowed by an unrelated table's column and never reached the person or the data.
                placed = {s_.mapping.entity for s_ in hits if s_.mapping}
                on_placed = any(tok.upper() in {c.name.upper() for c in self.by_entity[e].columns}
                                for e in placed if e in self.by_entity)
                if on_placed or not placed:
                    if not placed and tok not in sq.unresolved:
                        sq.unresolved.append(tok)      # nothing placed: still a word to account for
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
            if fold(tok) in (_RECORD_VERBS | _RECORD_CONVERBS) and not is_negative(tok):
                # "bu yıl açılan ama hâlâ …", "geçen yıl alıp …": the participle or converb stands beside
                # the period, not a noun, and says only that the record came to exist then — which the
                # period already restricts. Left as an undefined word it sent a fully defined question to
                # the model (or, for "alıp", bound it to a wrong value label).
                if tok not in sq.ignored:
                    sq.ignored.append(tok)
                sq.explanation.append(f"'{tok}' kaydın oluşumunu anlatan fiil; kayıtları daraltmaz")
                continue
            if tok not in sq.unresolved:
                sq.unresolved.append(tok)

        # 6b) a word the vocabulary has no entry for, looked for in the data itself. What the catalog
        #     does not define, the schema may still contain: the question is then about a column
        #     nobody wrote down, not about something this deployment has no answer for.
        self._from_data(sq, index, qf, consumed)

        # 6c) "karşılıksız çıkan VEYA protesto olan çekler": two labels of one column joined by "or" are one
        #     restriction to either — not two restrictions that contradict each other (which refused the
        #     question as ambiguous). The first label takes both value sets; the second is folded into it.
        ors = {k for k, t in enumerate(qf.tokens) if fold(t) in ("veya", "yahut", "veyahut")}
        ors |= {k for k, t in enumerate(qf.tokens[:-1]) if fold(t) == "ya" and fold(qf.tokens[k + 1]) == "da"}
        if ors:
            labels = sorted((h for h in hits if h.semantic_type == SemanticType.DIMENSION_VALUE and h.mapping and h.mapping.column
                             and h.span and (h.mapping.operator or "IN").upper() in ("IN", "=")), key=lambda h: h.span[0])
            for a in list(labels):
                for b in list(labels):
                    if a is b or a not in hits or b not in hits or a.span[0] >= b.span[0]:
                        continue
                    same = (a.mapping.entity, a.mapping.column.upper()) == (b.mapping.entity, b.mapping.column.upper())
                    if same and any(a.span[1] <= k < b.span[0] for k in ors):
                        merged = list(dict.fromkeys([*a.mapping.values, *b.mapping.values]))
                        a.mapping = Mapping(concept_id=a.mapping.concept_id, entity=a.mapping.entity, table_pattern=a.mapping.table_pattern,
                                            column=a.mapping.column, operator="IN", values=merged, extra=dict(a.mapping.extra or {}))
                        a.term = f"{a.term} veya {b.term}"
                        a.span = (a.span[0], b.span[1])
                        a.status = "INFERRED" if "INFERRED" in (a.status, b.status) else a.status
                        hits.remove(b)
                        sq.explanation.append(f"'{a.term}': aynı kolonda iki etiket 'veya' ile birleşti → {a.mapping.entity}.{a.mapping.column} IN ({', '.join(merged)})")
            sq.slots = hits

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

        # A count the resolver composed ("bekleyen sipariş adedi") is dated like any measure of its
        # entity: without a binding the gate had nothing to check the period against, and a period
        # the question stated could be dropped from the statement unnoticed.
        bound_entities = metric_entities | {s.mapping.entity for s in sq.metrics if s.mapping and s.status == "COMPOSED"}
        if sq.temporal and bound_entities:
            metric_entities = bound_entities
        if sq.temporal and metric_entities:
            # One binding per measured entity: a question over two facts is bounded on both, or the
            # period check silently covers neither.
            bindings = [b for e in sorted(metric_entities) if (b := self.conventions.temporal_binding(e))]
            if bindings:
                sq.temporal_binding = bindings[0]
                if len(bindings) > 1:
                    sq.temporal_binding["also"] = bindings[1:]
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

        # 8b) "son üç ayda satılan adet, aynı dönemde üretilen adedin ne kadarı?": two measures and a
        #     word asking for one over the other. The first measure named is the numerator, the second
        #     the denominator — the shape Turkish gives it ("X, Y'nin ne kadarı", "X'in Y'ye oranı").
        #     Answered as two totals the question "how much of" became "how much"; the ratio is asked.
        # "iade faturalarının satış cirosuna oranı": a label and a ratio word, and the catalog certifies a
        # measure named after exactly that — "<label> oranı". The certified ratio is the answer; the label
        # is its numerator, not a filter on everything (which left only the returns and a ratio of 1).
        if _RATIO_CUE.search(fold(question)) and not sq.ratio:
            for label in [h for h in hits if h.semantic_type == SemanticType.DIMENSION_VALUE and h.mapping and h.span]:
                key = normalize_term(f"{(label.explain or {}).get('canonical') or label.term} oranı")
                senses = [(c, ms) for c, ms in (index.get(key) or []) if c.semantic_type == SemanticType.METRIC]
                if not senses:
                    continue
                named = self._slot_from_senses(key, f"{label.term} oranı", senses, label.span)
                if named is None or not named.mapping or "/" not in (named.mapping.formula or ""):
                    continue
                for old_slot in [h for h in hits if h is label or h.semantic_type == SemanticType.METRIC]:
                    hits.remove(old_slot)
                hits.append(named)
                sq.slots = hits
                # The label no longer filters anything: a "conflict" it had with another label on the
                # same column ("iade" against "satış") was the two sides of the ratio, not a contradiction.
                gone = f"{label.mapping.entity}.{(label.mapping.column or '').upper()}"
                sq.conflicts = [c for c in sq.conflicts if c.upper() != gone.upper()]
                sq.explanation.append(f"'{label.term}' + oran → sertifikalı '{key}' ölçüsü")
                break
        two = [s_ for s_ in hits if s_.semantic_type == SemanticType.METRIC and s_.mapping and s_.span and s_.span[1] > s_.span[0]]
        two.sort(key=lambda s_: s_.span[0])
        if (len(two) == 2 and two[0].concept_id != two[1].concept_id
                and _RATIO_CUE.search(fold(question)) and not any("/" in (s_.mapping.formula or "") for s_ in two)):
            sq.shape = "RATIO"
            sq.ratio = {"numerator": two[0].term, "denominator": two[1].term}
            sq.explanation.append(f"oran istendi: '{two[0].term}' / '{two[1].term}'")

        # 9) a share question needs a denominator. When no certified ratio supplies one, answering with
        #    the plain total would quietly replace "what percent" with "how much".
        if not sq.ratio and (_SHARE_CUE.search(fold(question)) or _RATIO_CUE.search(fold(question))) and not any(
            s_.semantic_type == SemanticType.METRIC and s_.mapping and "/" in (s_.mapping.formula or "") for s_ in hits
        ):
            cue = next((t for t in qf.tokens if _SHARE_CUE.fullmatch(stem(t)) or _SHARE_CUE.fullmatch(fold(t)) or _RATIO_CUE.fullmatch(fold(t))), "pay")
            # 9a) "aracılı sözleşmelerin payı yüzde kaç": one record-kind label and no measure. The share
            #     is that kind's count over the count of all such records — the label's own kind
            #     conditions on both, the label's value only on the numerator. Composed here so the
            #     deterministic path writes it and the gate does not demand the label on every reading.
            labels = [h for h in hits if h.semantic_type == SemanticType.DIMENSION_VALUE and h.mapping and h.mapping.column
                      and h.mapping.values and (h.mapping.extra or {}).get("count_key") and h.span]
            metrics_here = [h for h in hits if h.semantic_type == SemanticType.METRIC and h.mapping
                            and (h.explain or {}).get("source") != "count_cue"]
            if len(labels) == 1 and not metrics_here:
                for stray in [h for h in hits if h.semantic_type == SemanticType.METRIC and (h.explain or {}).get("source") == "count_cue"]:
                    hits.remove(stray)                # "yüzde kaç" asks a share, not how many
                lab = labels[0]; m = lab.mapping
                key = m.extra["count_key"]
                own = f"{m.entity}.{m.column} {(m.operator or 'IN').upper()} ({', '.join(str(v) for v in m.values)})"
                kind = list((m.extra or {}).get("conditions") or [])
                formula = f"COUNT(DISTINCT {m.entity}.{key})"
                num = ResolvedSlot(term=f"{lab.term} sayısı", semantic_type=SemanticType.METRIC, status="COMPOSED",
                                   mapping=Mapping(concept_id="", entity=m.entity, table_pattern=m.table_pattern, formula=formula,
                                                   extra={"func": "COUNT", "conditions": [own] + kind, "undated": True}),
                                   confidence=0.75, explain={"why": f"pay istendi → '{lab.term}' kayıtları {key} üzerinden sayıldı", "source": "share_of_label"})
                den = ResolvedSlot(term="toplam kayıt sayısı", semantic_type=SemanticType.METRIC, status="COMPOSED",
                                   mapping=Mapping(concept_id="", entity=m.entity, table_pattern=m.table_pattern, formula=formula,
                                                   extra={"func": "COUNT", "conditions": kind, "undated": True}),
                                   confidence=0.75, explain={"why": f"payda: aynı türden bütün kayıtlar ({key})", "source": "share_of_label"})
                hits.remove(lab)
                hits.extend([num, den])
                sq.slots = hits
                sq.shape = "RATIO"
                sq.ratio = {"numerator": num.term, "denominator": den.term}
                sq.explanation.append(f"'{cue}' → '{lab.term}' payı: {own} olan kayıt sayısı / aynı türden bütün kayıtlar")
        if not sq.ratio and _SHARE_CUE.search(fold(question)) and not any(
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
        sq.order_desc = qf.order_desc if price_rank is None else price_rank
        for s in hits:
            sq.explanation.append(self._why(s))
        if sq.unresolved:
            sq.explanation.append("katalogda karşılığı olmayan terimler: " + ", ".join(sq.unresolved))
        if sq.unhandled:
            sq.explanation.append("karşılanamayan niteleyiciler: " + ", ".join(sq.unhandled))
        metrics_before = [s_ for s_ in sq.slots if s_.semantic_type == SemanticType.METRIC and s_.mapping]
        self._keep_to_one_source(sq, qf)
        # The default year was put on a measure the source rule has since handed to the model (an ERP
        # word in a CRM question): with no dated measure left, the year is a restriction nobody asked for.
        if default_applied and metrics_before and any(m not in sq.slots for m in metrics_before) and not any(s_.semantic_type == SemanticType.METRIC and s_.mapping and s_.status in ("CERTIFIED", "INFERRED")
                                       and (s_.explain or {}).get("source") != "count_cue"
                                       and not (s_.mapping.extra or {}).get("state_measure") and not (s_.mapping.extra or {}).get("undated")
                                       for s_ in sq.slots):
            sq.temporal = []
            sq.explanation.append("varsayılan dönem geri alındı: tarihli ölçü kalmadı → tüm kayıtlar üzerinden")
        # A measure asked beside named columns is asked *per* those columns: "kartında indirim yüzdesi
        # tanımlı müşteriler … ne kadar iskonto alıyor" is one line per customer with the card's rate
        # and the discount actually taken — not one average over all of them, and not a question the
        # deterministic compiler must hand to the model for lack of "bazında". After the source rule:
        # a lone word certified on the other database is the model's, not a breakdown.
        if any(s_.semantic_type == SemanticType.METRIC and s_.mapping for s_ in sq.slots):
            added = []
            for slot in sq.slots:
                if slot.semantic_type == SemanticType.COLUMN and slot.mapping and slot.mapping.column and slot not in sq.group_by:
                    sq.group_by.append(slot)
                    slot.explain["role"] = "subject_group_by"
                    added.append(slot.term)
            if added:
                sq.explanation.append("ölçü, sorudaki kolonlar bazında kırılacak: " + ", ".join(added))
            # The column a composed measure was built from is the measure, not a breakdown of it:
            # grouping "ortalama telif tutarı" by telif tutarı gives one row per distinct amount.
            measured = {re.sub(r"^\w+\((?:\w+\.)?(\w+)\)$", r"\1", (s_.mapping.formula or "")).upper()
                        for s_ in sq.slots if s_.semantic_type == SemanticType.METRIC and s_.mapping and s_.status == "COMPOSED"}
            sq.group_by = [g for g in sq.group_by if not (g.mapping and g.mapping.column and g.mapping.column.upper() in measured)]
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
                    # Two concepts spelling the same restriction are one obligation; the gate must not be
                    # asked to prove it twice and a repair must not be told to write it twice.
                    key = (mapping.entity, mapping.column, (mapping.operator or "IN").upper(), tuple(sorted(str(v) for v in mapping.values)))
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
            if fold(tok) in _COPULA:
                consumed.add(k)          # "olan", "olduğu": grammar that links words, never a restriction
                continue
            if is_negative(tok) and _negated_light_verb(tok) and k not in consumed:
                # "iptal edilmemiş": the light verb is grammar and would be skipped below with the
                # stopwords — but its negation belongs to the state label placed just before it.
                flipped = self._negate_left_state(tok, k, [s_ for s_ in sq.slots if getattr(s_, "span", None) and s_.span[1] == k])
                if flipped is not None:
                    consumed.add(k)
                    sq.explanation.append(flipped.explain["why"])
                    continue
            if (any(tok in tokenize(t.text) for t in qf.temporal)
                    or (stem(tok) in STOPWORDS_S | MODIFIERS_S
                        and not self._modifies_a_noun(qf.tokens, k, consumed))):
                continue
            if fold(tok) in _DEGREE_ADVERBS:
                # "tamamen sevk edilmemiş", "hâlâ bekleyen": an adverb of degree or time qualifies the
                # verb beside it, and that verb's phrase is what the catalog defines. Handed to the
                # model as a condition of its own, "tamamen" became SHIPPEDAMOUNT = 0 in two runs out
                # of three — "not shipped at all" — where the certified phrase already says "not
                # fully shipped".
                consumed.add(k)
                continue
            if fold(tok) in _COMPARATORS:
                # A magnitude comparison ("maliyetin altında", "limitin üzerinde", "eşiği aşan"): a
                # condition on the rows, not grammar. It counts as one only next to a resolved measure —
                # "en yüksek" is a ranking (handled above by the price/superlative reader) and "yüz
                # liranın altında" carries its own number, which the value reader already took. With a
                # measure beside it and no threshold number of its own, the catalog names no value for
                # it, so it is handed to the model as an obligation: a `-- yorum:` saying how it compared
                # and a real restriction the gate then demands (see SemanticQuery.model_qualifiers).
                # Dropped as before (is_domain_candidate → ignored), the measure was served with the
                # comparison missing and the answer looked complete.
                ranking = k > 0 and fold(qf.tokens[k - 1]) == "en"
                near_number = any(0 <= j < len(qf.tokens) and cardinal(qf.tokens[j]) is not None
                                  for j in (k - 1, k - 2))
                near_measure = any(s.semantic_type == SemanticType.METRIC and s.mapping and s.span
                                   and abs(s.span[1] - k) <= 2 for s in sq.slots)
                if near_measure and not ranking and not near_number \
                        and not any(mq.get("position") == k for mq in sq.model_qualifiers):
                    lo, hi = max(0, k - 2), min(len(qf.tokens), k + 2)
                    sq.model_qualifiers.append({"token": tok, "position": k, "negative": is_negative(tok),
                                                "phrase": " ".join(qf.tokens[lo:hi])})
                    sq.explanation.append(
                        f"'{tok}' bir büyüklük karşılaştırması (ölçü ↔ eşik/kolon); katalogda değeri yok → "
                        "model bunu yorumlayıp gerçek bir kısıtla (WHERE/HAVING) uygulamalı, kapı hem "
                        "yorumu hem kısıtı arar")
                    consumed.add(k)
                    continue
            if not self._modifier_candidate(qf.tokens, k, consumed):
                continue
            if cardinal(tok) is not None:
                consumed.add(k)          # "doksan gün": a number, whatever its ending looks like
                continue
            covering = [s for s in sq.slots if s.span[0] <= k < s.span[1]]
            if k in consumed and not covering:
                continue  # a previously explained report/time/trend cue
            if covering and all(s.status == "CERTIFIED" and s.span == (k, k + 1) for s in covering) and not (is_participle(tok) or is_negative(tok)):
                # A certified noun ending in -en is not an unresolved modifier.
                continue
            # "faturası hâlâ kesilmemiş": a stopword between the thing and its verb does not separate them.
            k_left = k
            while k_left > 0 and fold(qf.tokens[k_left - 1]) in STOPWORDS_S:
                k_left -= 1
            left = [s for s in sq.slots if s.span and s.span[1] in (k, k_left)]
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
            elif is_negative(tok) and _negated_light_verb(tok) and (flipped := self._negate_left_state(tok, k, left)) is not None:
                # "iptal edilmemiş": the state noun matched the label "iptal edildi" on its own and the
                # negation sat on the light verb beside it. The label is the same; its sense is the
                # complement. Read as placed, the answer was the cancelled invoices — the opposite.
                consumed.add(k)
                record.update(decision="SEMANTIC", evidence_source="catalog", concept_ids=[flipped.concept_id],
                              resolved_as="DIMENSION_VALUE:INFERRED", negated_label=True)
                sq.explanation.append(flipped.explain["why"])
            elif is_negative(tok) and (undone := self._negated_label(tok, k, index)) is not None:
                # "tamamlanmadı" over a certified status label "tamamlandı" (STATUS IN (3)): the rows
                # outside that state, said as the label's negation — not a word left to the model,
                # which read it as "not yet accounted" and answered a different question.
                sq.slots.append(undone)
                consumed.add(k)
                record.update(decision="SEMANTIC", evidence_source="catalog", concept_ids=[undone.concept_id],
                              resolved_as="DIMENSION_VALUE:INFERRED", negated_label=True)
                sq.explanation.append(undone.explain["why"])
            elif is_negative(tok) and (_negated_light_verb(tok) or _negated_record_verb(tok)) and (absent := next((s_ for s_ in left if s_.mapping
                    and s_.semantic_type in (SemanticType.METRIC, SemanticType.DIMENSION_VALUE, SemanticType.ENTITY)), None)) is not None \
                    and not re.search(rf"\b{re.escape(stem(fold(absent.term.split()[0])))}\w*\s+(olan|bulunan|olup)\b", fold(" ".join(qf.tokens))):
                # "hedefi olan ürünlerde hiç hedef girilmemiş aylar": the thing negated also exists,
                # affirmed, in the same sentence — the absence is of a value inside the record (an
                # empty month), not of the record. That reading is the model's, with a yorum line.
                # "hiç sevkiyat almamış müşteriler": the light verb carries the negation and the thing
                # negated is the measure just before it — the customers with no shipment record at all.
                # Read as a verb root ("al" → a purchase measure) or left to the model, this became
                # "order lines with nothing shipped yet", a different question with a longer answer.
                sq.shape = "ABSENCE"
                absent.explain["absent"] = True
                record.update(decision="ABSENCE", evidence_source="catalog", verb_root=str(absent.explain.get("normalized") or absent.term),
                              absent_entity=absent.mapping.entity, concept_ids=[absent.concept_id])
                if len(sq.temporal) == 1 and (sq.temporal[0].params or {}).get("default"):
                    sq.temporal = []             # "never" is not "not this year"
                    sq.explanation.append("yokluk sorusu: varsayılan dönem uygulanmadı, tüm kayıtlara bakılır")
                sq.explanation.append(f"'{absent.term} {tok}': {absent.mapping.entity} kaydı hiç olmayan kayıtlar isteniyor (NOT EXISTS)")
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
            elif not is_negative(tok) and fold(tok) in _RECORD_VERBS and (left or right or covering or self._modifies_a_noun(qf.tokens, k, consumed)):
                # "açılan sipariş", "kesilen fatura", "iade alan müşteri": the verb says how the record
                # came to exist or reached the subject, not which records to keep. Every order was
                # opened; a customer with returns already has the return filter beside the verb.
                record.update(decision="GRAMMATICAL", evidence_source="record_verb")
                sq.explanation.append(f"'{tok}' kaydın oluşumunu anlatan fiil; kayıtları daraltmaz")
            elif (named := self._column_for_state(sq, qf, k)) is not None and named.get("mention"):
                # "planlanan ciro": the participle and the noun after it are together the name of a
                # column. That is a measure being named, not a condition on the rows.
                sq.candidates.append({"term": f"{tok} {qf.tokens[k + 1]}", "column": named["column"],
                                      "entities": [named["entity"]], "source": "column_description"})
                record.update(decision="SEMANTIC", evidence_source="column_description_name",
                              resolved_as=f"{named['entity']}.{named['column']}")
                sq.explanation.append(named["why"])
            elif named is not None:
                # The source names this state on a column but never writes out what its values mean
                # ("CANCELLED — İptal Edilmiş"). Which number is which is the source's business, so
                # the word is carried to the model as that column, and the gate refuses an answer that
                # does not restrict it. Nothing is dropped and no value is invented here.
                sq.qualifier_columns.append(named)
                record.update(decision="COLUMN", evidence_source="column_description",
                              resolved_as=f"{named['entity']}.{named['column']}")
                sq.explanation.append(named["why"])
            elif (state := self._state_from_verb(sq, qf, k)) is not None:
                # "iptal edilmemiş fatura", "onaylanan sipariş", "bekleyen ürün": the state the word
                # names is a value the source itself labels on one of this entity's coded columns.
                sq.slots.append(state)
                record.update(decision="SEMANTIC", evidence_source="value_label",
                              resolved_as=f"{state.mapping.entity}.{state.mapping.column} "
                                          f"{state.mapping.operator} {state.mapping.values}")
                sq.explanation.append(state.explain["why"])
            if record["decision"] == "UNKNOWN":
                # Nothing in the catalog explains the word. It is handed to the model as an obligation
                # rather than put back to the person (see SemanticQuery.model_qualifiers): the model
                # must say how it read it and restrict the answer by it, and the gate checks both.
                lo, hi = max(0, k - 2), min(len(qf.tokens), k + 2)
                sq.model_qualifiers.append({"token": tok, "position": k, "negative": is_negative(tok),
                                            "phrase": " ".join(qf.tokens[lo:hi])})
                record.update(decision="MODEL", evidence_source="model_obligation")
                sq.explanation.append(f"'{tok}' katalogda tanımlı değil → sorguyu yazan model yorumlayacak; "
                                      "yorumu cevabın üstünde gösterilir ve cevap sertifikasız sayılır")
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
            explain={"normalized": key, "canonical": c.term, "sense": c.sense_id, "version": c.version, "support": support, "evidence_types": sorted({e.evidence_type for e in ev}), "alternatives": alternatives},
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

    def _state_from_verb(self, sq: SemanticQuery, qf: Any, k: int) -> Optional[ResolvedSlot]:
        """"iptal edilmemiş" → the coded value the source labels "İptal Edildi", or nothing.

        A participle usually names a *state* a record is in, and a state this deployment records is a
        value with a label: the source writes "İptal Edildi", "Onaylandı", "Beklemede" next to the code
        it stores. So the word is matched against those labels — never against a column name, never
        against a word this system invented — on the entities the question is already about.

        The word that carries the meaning is not always the participle: in "iptal edilmemiş" the verb
        is a light one ("edilmemiş") and the noun before it says what happened. Polarity always comes
        from the verb, so "edilmemiş" turns the match into an exclusion.

        Nothing is guessed. Two different columns answering to the same word is ambiguity, and this
        returns nothing so the question is asked rather than decided.
        """
        tokens = qf.tokens
        tok = tokens[k]
        negative = is_negative(tok)
        # "iptal edilmemiş", "sevk edilen": the verb is an auxiliary and the noun before it says what
        # happened. The auxiliary itself is never a key — "edil" would match any label written in the
        # passive — so it contributes polarity and nothing else.
        keys = self._state_keys(tokens, k)
        if not keys:
            return None

        entities = self._state_entities(sq, tokens, k)
        if not entities:
            return None

        found: dict[tuple[str, str], list[str]] = {}
        for entity in entities:
            for prof in self.tables_of.get(entity, []):
                for col in prof.columns:
                    labels = col.value_labels or {}
                    if not labels or col.sensitive:
                        continue
                    hits = [str(code) for code, label in labels.items() if label and self._text_answers(str(label), keys)]
                    if hits:
                        found.setdefault((entity, col.name.upper()), []).extend(hits)
        if len(found) != 1:
            return None                      # nothing to say, or two readings: the question gets asked
        (entity, column), codes = next(iter(found.items()))
        prof = self.by_entity.get(entity)
        if prof is None:
            return None
        codes = sorted(set(codes))
        labels = (prof.column(column).value_labels if prof.column(column) else {}) or {}
        named = ", ".join(f"{c}={labels.get(c, c)}" for c in codes)
        mapping = Mapping("", entity, prof.table_pattern, column=column,
                          operator="NOT IN" if negative else "IN", values=codes)
        slot = ResolvedSlot(term=tok, semantic_type=SemanticType.DIMENSION_VALUE, status="INFERRED",
                            mapping=mapping, confidence=0.6, span=(k, k + 1))
        slot.explain = {
            "source": "value_label",
            "why": (f"'{tok}' {'dışında tutuldu' if negative else 'durumu'}: kaynağın kendi etiketi "
                    f"{entity}.{column} → {named}"),
            "matchedCodes": codes, "labels": {c: labels.get(c) for c in codes}, "negative": negative,
        }
        return slot

    def _state_keys(self, tokens: list[str], k: int) -> set[str]:
        """The words that carry the state, without the auxiliary that only carries tense and polarity."""
        keys: set[str] = set()
        for w in [tokens[k]] + ([tokens[k - 1]] if k > 0 else []):
            for form in (verb_root(w), stem(w), short_root(w)):
                if form and len(form) >= 3 and not any(form.startswith(root) for root in _AUXILIARY_ROOTS):
                    keys.add(form)
        return keys

    def _state_entities(self, sq: SemanticQuery, tokens: list[str], k: int, *, any_source: bool = False) -> set[str]:
        entities = {s.mapping.entity for s in sq.slots if s.mapping}
        entities |= {s.mapping.entity for s in sq.group_by if s.mapping}
        # The question also names its subject in words the vocabulary may not have mapped yet: an
        # entity whose own name — the source's word for the table — appears in the question. Mapped
        # slots alone are not enough: "planlanan ciro" maps "ciro" to the ERP's invoices while the
        # planned figure lives on a CRM table the question names by another word.
        nouns = {stem(t) for i, t in enumerate(tokens) if i != k and len(t) > 2 and stem(t) not in STOPWORDS_S}
        # A question already placed in one database stays there: "iptal edilmemiş satış faturaları"
        # reached a CRM sales-support table through the word "satış", and the invoice question was
        # refused for a condition on a table it never read.
        placed = {self._source_of(e) for e in entities}
        for entity, prof in self.by_entity.items():
            if placed and not any_source and self._source_of(entity) not in placed:
                continue
            if nouns & self._entity_name_stems(prof):
                entities.add(entity)
        return entities

    def _keep_to_one_source(self, sq: SemanticQuery, qf) -> None:
        """The measure decides which database a question reads; a single word certified on the other
        one does not pull that database in.

        "kâr" is certified on a CRM scenario column and "müşteri" on a CRM account table; "en çok kâr
        bıraktığımız on müşteri, maliyet düştükten sonra" computes a cost — an ERP measure over sales
        lines. Kept as slots, those words made the gate look for the period on tables the answer never
        reads, and the question was refused. Where every measure sits in one source, a one-word column
        slot from the other source is handed to the model to read within the measure's source, under
        a `-- yorum` line the person sees. A multi-word certified phrase is deliberate and stays; so
        does everything when the measures themselves span both databases, or there is no measure."""
        metrics = [s for s in sq.slots if s.mapping is not None and s.mapping.entity and s.semantic_type == SemanticType.METRIC
                   and (s.explain or {}).get("source") != "count_cue"]
        homes = {self._source_of(m.mapping.entity) for m in metrics}
        named: list[str] = []
        if not metrics:
            # A count the resolver composed from "adedi" is not a measure the question named: "baskı
            # adedi arttıkça telif yüzdemiz" asks about the royalty column, and the one source holding
            # a certified column the question names is the source the question is about.
            columns = [s for s in sq.slots if s.mapping is not None and s.mapping.entity
                       and s.semantic_type == SemanticType.COLUMN and s.status in ("CERTIFIED", "INFERRED")]
            # One word matched to one column does not name a database. The vocabulary holds thousands
            # of everyday one-word names ("risk", "limit") approved for one table's column, and the
            # same word is ordinary speech about the other server's data: "risk limitini aşmış cari
            # hesaplar" is an ERP question that two such words carried to the CRM, where the model was
            # shown 292 tables and none of the right ones. A phrase is deliberate; a lone word decides
            # only when nothing else in the question speaks (see the fallback below).
            placed = [s for s in sq.slots if s.mapping is not None and s.mapping.entity and getattr(s, "span", None)
                      and s.semantic_type != SemanticType.DEFAULT_FILTER and s.status in ("CERTIFIED", "INFERRED")]
            column_homes = {self._source_of(s.mapping.entity) for s in placed if self._names_a_source(s)}
            elsewhere = {self._source_of(s.mapping.entity) for s in placed} - column_homes
            if len(column_homes) == 1 and not elsewhere:
                homes = column_homes
                sq.source_hint = next(iter(homes))
        if not metrics and len(homes) != 1:
            # No measure: the things the question names decide. "Fiyat listesinde tanımlı fiyatın
            # altında kesilen faturalar" names invoices — an ERP thing — and "fiyat listesi" is a
            # word both databases use. The entities the plain words reach (outside any placed
            # phrase) say which database the question is about.
            covered = {k for s in sq.slots if getattr(s, "span", None) for k in range(s.span[0], s.span[1])}
            votes, named = self._source_votes(qf, covered)
            plain = dict(votes)
            # A certified phrase names its database as surely as a table's own word does: "fiziki
            # arşivde emanete verilmiş" is three CRM things, and the plain "kayıtlar" beside them is
            # one ERP word, not the question's subject.
            for s_ in sq.slots:
                if s_.mapping is not None and s_.mapping.entity and s_.status == "CERTIFIED" and getattr(s_, "span", None) \
                        and s_.semantic_type != SemanticType.DEFAULT_FILTER:
                    src = self._source_of(s_.mapping.entity)
                    # a phrase or a table's own word is a full voice; a lone word is half of one — two
                    # of them weigh what one deliberate phrase does, and one alone decides nothing
                    # against a table the question names in plain words
                    votes[src] = votes.get(src, 0) + (1 if self._names_a_source(s_) else 0.5)
            ranked = sorted(votes.items(), key=lambda kv: -kv[1])
            homes = {ranked[0][0]} if ranked and (len(ranked) == 1 or ranked[0][1] >= 2 * ranked[1][1]) else set()
            if not homes and ranked and votes.get("", 0) == ranked[0][1] and plain.get("", 0) > 0:
                homes = {""}                   # a tie with a table's own word on the ERP side goes to the connection's own database
            if len(homes) == 1:
                sq.source_hint = next(iter(homes))
        if len(homes) > 1:
            # Measures on both sides: "sevkiyatlarda liste fiyatı üzerinden indirim" names an ERP
            # measure by one word and two CRM things by phrase. The side the question names more
            # certified things on, by a clear margin, is the side it is about.
            tally: dict[str, int] = {}
            for s_ in sq.slots:
                if s_.mapping is not None and s_.mapping.entity and s_.status == "CERTIFIED" and s_.semantic_type != SemanticType.DEFAULT_FILTER:
                    src = self._source_of(s_.mapping.entity)
                    tally[src] = tally.get(src, 0) + 1
            ranked = sorted(tally.items(), key=lambda kv: -kv[1])
            if len(ranked) >= 2 and ranked[0][1] >= 2 * ranked[1][1]:
                homes = {ranked[0][0]}
                sq.source_hint = ranked[0][0]
                sq.explanation.append(f"iki kaynakta da ölçü var; soru {ranked[0][0] or 'ana veri tabanı'} tarafında daha çok tanımlı şey adlandırıyor → o kaynak seçildi")
            elif re.search(r"\b(oran|yuzde|puan|pay)", fold(" ".join(qf.tokens))):
                # A rate is asked and one side certifies a rate: "kaç puan indirim" is the discount
                # ratio, not the shipped quantity that happens to share the word "sevkiyat".
                ratio_homes = {self._source_of(m.mapping.entity) for m in metrics if "/" in (m.mapping.formula or "")}
                if len(ratio_homes) == 1:
                    homes = ratio_homes
                    sq.source_hint = next(iter(homes))
                    sq.explanation.append(f"oran soruldu; sertifikalı oran ölçüsü {next(iter(homes)) or 'ana veri tabanı'} tarafında → o kaynak seçildi")
        if len(homes) != 1:
            return
        home = next(iter(homes))
        others = [s for s in list(sq.slots) + list(sq.group_by)
                  if s.mapping is not None and s.mapping.entity and s.semantic_type != SemanticType.DEFAULT_FILTER
                  and self._source_of(s.mapping.entity) != home]
        homes_entities = {m.mapping.entity for m in metrics} | {e for e in (named if not metrics else []) if e}
        # Everything the question placed on the home side is something a bridge may land on: the
        # breakdown ("kitap bazında" → the product card) as much as the measure's own table.
        homes_entities |= {s.mapping.entity for s in list(sq.slots) + list(sq.group_by)
                           if s.mapping is not None and s.mapping.entity and s.semantic_type != SemanticType.DEFAULT_FILTER
                           and self._source_of(s.mapping.entity) == home}
        for lone in {id(s): s for s in others}.values():
            span = getattr(lone, "span", None)
            if lone.semantic_type == SemanticType.METRIC and (lone.explain or {}).get("source") == "count_cue":
                sq.slots.remove(lone)                     # a count composed on the other source's table
                continue
            if not span or span[1] - span[0] > 2:
                continue                                  # a certified phrase of three or more words is meant
            if span[1] - span[0] >= 2 and lone.status == "CERTIFIED" \
                    and lone.semantic_type in (SemanticType.METRIC, SemanticType.COLUMN):
                # A deliberate two-word certified measure or column names its own subject: "telif
                # yüzdemiz" is exactly what "baskı adedi arttıkça … ne kadar yükseliyor" asks about,
                # certified on the CRM royalty table. Handing it to the other side dropped the word
                # and then refused the question as "telif tanımlı değil" — for a question plainly about
                # that database. A lone word or a two-word value *filter* is still passed over below;
                # only a certified analytical axis of two or more words is kept here.
                continue
            if lone in sq.group_by and (lone.explain or {}).get("role") != "rank_group_by":
                continue                                  # "kanal bazında": the grouping is the question's structure
            if self._linked_across(lone.mapping.entity, homes_entities):
                continue                                  # the catalog measured a bridge: the question may span both
            if lone in sq.slots:
                sq.slots.remove(lone)
            if lone in sq.group_by:
                sq.group_by.remove(lone)
            word = fold(qf.tokens[span[0]]) if span[0] < len(qf.tokens) else fold(lone.term)
            if word and word not in sq.unresolved:
                sq.unresolved.append(word)
            where = f"{lone.mapping.entity}.{lone.mapping.column}" if lone.mapping.column else lone.mapping.entity
            sq.explanation.append(f"'{lone.term}' katalogda {self._source_of(lone.mapping.entity) or 'ana veri tabanı'} tarafında {where} olarak tanımlı; "
                                  f"ölçü {home or 'ana veri tabanı'} verisinde → bu kelimeyi sorguyu yazan model o kaynakta yorumlayacak")

    @staticmethod
    def _names_a_source(slot: ResolvedSlot) -> bool:
        """May this slot say which database the question is about? A table's own word (an ENTITY), a
        measure, and any phrase of two words or more may; one word matched to one column or label may
        not — it keeps its meaning if the question turns out to be about its source, and is handed to
        the model (with the reason on the trace) if it does not."""
        if slot.semantic_type in (SemanticType.ENTITY, SemanticType.METRIC):
            return True
        span = getattr(slot, "span", None)
        return bool(span) and span[1] - span[0] >= 2

    def _source_votes(self, qf, covered: set[int]) -> tuple[dict[str, int], list[str]]:
        """Which database the question's plain words name, read from the tables' own names.

        "Fiyat listesinde tanımlı fiyatın altında kesilen faturalar": "fatura" is the ERP invoice
        table's own name and "fiyat" the price list's; the CRM has a price list too, so that word is
        no vote. Table names are the source's own words for its things — the certified vocabulary,
        mined from both databases, says "fatura" in eleven CRM terms and four ERP terms and would
        vote the wrong way. One vote per word, for a source whose tables alone answer to it."""
        votes: dict[str, int] = {}
        named: list[str] = []
        for k, tok in enumerate(qf.tokens):
            if k in covered or not is_domain_candidate(tok) or _COUNT_CUE.fullmatch(fold(tok)):
                continue
            forms = {f for f in (stem(tok), short_root(tok)) if f and len(f) >= 3}
            hit: dict[str, list[str]] = {}
            for prof in self.by_entity.values():
                if is_shadow_copy(prof.entity) or not (self._entity_name_stems(prof) & forms):
                    continue
                hit.setdefault(self._source_of(prof.entity), []).append(prof.entity)
            if len(hit) == 1:
                src, ents = next(iter(hit.items()))
                votes[src] = votes.get(src, 0) + 1
                named += ents
        return votes, named

    def _linked_across(self, entity: str, others: set[str]) -> bool:
        """Has the catalog measured a cross-source relationship between `entity` and any of `others`?"""
        for a, bs in ((entity, others), *((o, {entity}) for o in others)):
            prof = self.by_entity.get(a)
            for rel in (prof.relationships if prof is not None else []) or []:
                if rel.get("cross_source") and str(rel.get("ref_entity") or "").upper() in {b.upper() for b in bs}:
                    return True
        # The bridge rarely lands on the table the question named: targets are kept by barcode, the
        # barcode table is what the catalog measured against them, and the product card is one join
        # further. A measured bridge whose far end joins, inside its own source, to a table of the
        # question is the same bridge; without this step every such question lost its other half.
        def bare(name: str) -> str:
            return re.sub(r"^LG_", "", str(name or "").upper())
        wanted = {bare(o) for o in others}
        for landing in self._bridge_landings(entity):
            if bare(landing) in wanted:
                return True
            for candidate in (n for n in self.by_entity if bare(n) == bare(landing)):
                for other in (n for n in self.by_entity if bare(n) in wanted):
                    if self.conventions.join_path(candidate, other):
                        return True
        return False

    def _bridge_landings(self, entity: str) -> set[str]:
        """Tables on the other source that a measured cross-source relationship ties `entity` to."""
        found: set[str] = set()
        prof = self.by_entity.get(entity)
        for rel in (prof.relationships if prof is not None else []) or []:
            if rel.get("cross_source") and rel.get("ref_entity"):
                found.add(str(rel["ref_entity"]))
        for other in self.profiles:
            for rel in other.relationships or []:
                if rel.get("cross_source") and str(rel.get("ref_entity") or "").upper() == entity.upper():
                    found.add(other.entity)
        return found

    def _source_of(self, entity: str) -> str:
        prof = self.by_entity.get(entity)
        schema = (prof.schema_name or "") if prof is not None else ""
        return schema.split(".")[0].upper() if "." in schema else ""

    _NAME_CACHE: dict[tuple[str, str], frozenset[str]] = {}

    @classmethod
    def _entity_name_stems(cls, prof) -> frozenset[str]:
        key = (prof.entity or "", prof.description or "")
        found = cls._NAME_CACHE.get(key)
        if found is None:
            found = cls._NAME_CACHE[key] = frozenset(cls._entity_name_stems_uncached(prof))
        return found

    @staticmethod
    def _entity_name_stems_uncached(prof) -> set[str]:
        """The words a table is *called*, not every word written about it.

        A CRM description is a sentence ("Bir müşteriyi veya potansiyel müşteriyi temsil eden
        işletme"); matched word by word, half the catalog answered to "müşteri" and a state word found
        a column on a table the question never read. The name is the description's first phrase when
        it is a short one — the source's own title for the table — and the entity's own words.
        """
        title = (prof.description or "").split(".")[0].strip()
        words = tokenize(title) if 0 < len(tokenize(title)) <= 3 else []
        base = re.sub(r"(?i)^(new_|lg_)|base$", "", prof.entity or "")
        return {stem(w) for w in words} | {stem(w) for w in tokenize(base.replace("_", " "))}

    _FORMS_CACHE: dict[str, tuple[frozenset[str], ...]] = {}

    @classmethod
    def _text_forms(cls, text: str) -> tuple[frozenset[str], ...]:
        """Each word of a description, as the forms a key may meet it in. Descriptions do not change
        between questions, and stemming every word of every column on every question was most of
        the time a question took (14 of 19 seconds, measured on the production catalog)."""
        found = cls._FORMS_CACHE.get(text)
        if found is None:
            found = tuple(frozenset(f for f in (fold(part), stem(part), short_root(part)) if f)
                          for part in tokenize(text or ""))
            if len(cls._FORMS_CACHE) < 200_000:
                cls._FORMS_CACHE[text] = found
        return found

    @classmethod
    def _text_answers(cls, text: str, keys: set[str]) -> bool:
        for forms in cls._text_forms(text):
            # Same root, or one is the other with a Turkish suffix on it. Four letters was not enough:
            # "verilen" reached "Veri" columns and "açılan" reached "Açıklama".
            if any(key == f or (len(key) >= 5 and f.startswith(key)) or (len(f) >= 5 and key.startswith(f))
                   for key in keys for f in forms if f):
                return True
        return False

    def _column_for_state(self, sq: SemanticQuery, qf: Any, k: int) -> Optional[dict[str, Any]]:
        """"termin tarihi geçen" → the column the source describes as "Termin Tarihi", or nothing.

        A source that ships no dictionary for its codes still says what each column is for, in its own
        words. That is enough to know *where* the question is answered and not enough to know *which
        value* answers it, so this returns the column and stops: the model writes the predicate from
        the same description, and the gate refuses any answer that does not restrict this column.

        The meaning of a participle usually sits in the words around it — "makbuz numarası
        girilmemiş", "termin tarihi geçen", "planlanan ciro" — so the neighbours are scored together:
        a column whose description contains more of them wins, and a tie between two columns is
        ambiguity, which returns nothing so the person is asked.

        When the word *after* the participle is part of the match and the column holds an amount
        ("planlanan ciro"), the phrase is that column's name — a measure being named, not a condition
        — and the result says so (`mention`), so no restriction is demanded of the answer.
        """
        tokens = qf.tokens
        tok = tokens[k]
        # The participle's own root ("girilmemiş" → "giril" is an auxiliary and gives nothing;
        # "planlanan" → "planla" does) — scored beside its neighbours, never alone against many.
        own = {f for f in (verb_root(tok), stem(tok), short_root(tok))
               if f and len(f) >= 3 and not any(f.startswith(r) for r in _AUXILIARY_ROOTS)}
        neighbours: dict[int, set[str]] = {}
        for i in (k - 2, k - 1, k + 1):
            if 0 <= i < len(tokens) and i != k:
                w = tokens[i]
                if len(w) <= 2 or cardinal(w) is not None or stem(w) in STOPWORDS_S or is_participle(w):
                    continue
                forms = {f for f in (stem(w), short_root(w), fold(w)) if f and len(f) >= 3}
                if forms:
                    neighbours[i] = forms
        if not neighbours and not own:
            return None

        def hits(text: str, forms: set[str]) -> bool:
            return self._text_answers(text, forms)

        placed = {self._source_of(s_.mapping.entity) for s_ in list(sq.slots) + list(sq.group_by) if s_.mapping}
        scored: dict[tuple[str, str], tuple[int, bool, str, str]] = {}
        for entity in self._state_entities(sq, tokens, k, any_source=True):
            for prof in self.tables_of.get(entity, []):
                for col in prof.columns:
                    if col.sensitive or not col.description:
                        continue
                    matched = [i for i, forms in neighbours.items() if hits(col.description, forms)]
                    if not matched:
                        # The verb alone says little: "kalmamış" met "Depoda Kalma Süresi". The state
                        # is named by the noun beside it, so without one there is no reading here.
                        continue
                    score = len(matched) + (1 if own and hits(col.description, own) else 0)
                    key = (entity, col.name.upper())
                    if key not in scored or score > scored[key][0]:
                        scored[key] = (score, (k + 1) in matched, col.description, col.data_type or "")
        if not scored:
            return None
        best = max(v[0] for v in scored.values())
        top = [(key, v) for key, v in scored.items() if v[0] == best]
        if len(top) != 1:
            return None                      # two columns answer equally well: the person decides
        if best < 2 and len(scored) > 1:
            return None                      # one shared word is not enough to pick among several
        (entity, column), (score, after, description, data_type) = top[0]
        prof = self.by_entity.get(entity)
        if prof is None:
            return None
        amount = bool(re.search(r"money|decimal|numeric|float|real", data_type, re.I))
        mention = after and amount
        if not mention and placed and self._source_of(entity) not in placed:
            # A measure may be named from the other database — the question then needs both. A
            # condition may not: it would restrict a table the answer does not read.
            return None
        return {"token": tok, "entity": entity, "column": column, "tablePattern": prof.table_pattern,
                "description": description, "negative": is_negative(tok), "mention": mention, "score": score,
                "why": (f"'{tok}' {'ölçünün adı' if mention else 'niteleyicisi'}: {entity}.{column} "
                        f"(kaynağın açıklaması: {description})"
                        + ("" if mention else "; hangi değerin ne demek olduğu sorguda belirlenecek"))}

    def _metric_from_verb(self, tok: str, k: int, index: dict[str, list[tuple[Concept, list[Mapping]]]]) -> Optional[ResolvedSlot]:
        """"satan" → the measure the catalog keys on the same root ("satış"), or nothing.

        The form of the word gets us here; the catalog decides. A root that reaches no certified
        measure, or reaches two different ones, returns nothing rather than a guess — and a negative
        never bridges, because "satmayan" is the opposite of "satış" and bridging it would invert the
        answer. What comes back is a measure slot, not a verdict that the word was noise: nothing is
        dropped, and which concept was used is written into the slot.
        """
        for _ in (0,):
            if _COUNT_CUE.fullmatch(fold(tok)):
                continue        # "adedi" asks how many; it is not the verbal form of the quantity measure "adet"
            if stem(tok) in _ENTITY_WORDS or short_root(tok) in _ENTITY_WORDS:
                continue        # "kartı" is the customer's card, not a past tense of "kâr"
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
        if {fold(tok), st} & (STOPWORDS_S | MODIFIERS_S | METRIC_VOCAB_S) or _COUNT_CUE.fullmatch(fold(tok)):
            return None         # a generic word ("sayı", "toplam", "tane") must not select one specific concept
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

    @staticmethod
    def _temporal_positions(qf: Any) -> set[int]:
        """Token positions the temporal parser spent: the words of every period it read, and — when it
        read a breakdown grain — the calendar word that carries it ("ay ay", "aylık", "günlük")."""
        out: set[int] = set()
        folded = [fold(t) for t in qf.tokens]
        for period in qf.temporal or []:
            words = [fold(w) for w in tokenize(getattr(period, "text", "") or "")]
            if not words:
                continue
            for i in range(len(folded) - len(words) + 1):
                if folded[i:i + len(words)] == words:
                    out.update(range(i, i + len(words)))
        if getattr(qf, "grain", None):
            unit = {"MONTH": "ay", "DAY": "gun", "WEEK": "hafta", "QUARTER": "ceyrek", "YEAR": "yil"}.get(qf.grain, "")
            for k, w in enumerate(folded):
                if unit and stem(w) == stem(unit) or short_root(qf.tokens[k]) == unit:
                    out.add(k)
        return out

    def _count_metric(self, qf: Any, hits: list[ResolvedSlot], consumed: set[int]) -> Optional[ResolvedSlot]:
        index = self.store.certified_index(self.tenant_id, self.datasource_id)
        entity = None
        # "bekleyen sipariş adedi": the thing counted is the resolved term the count word follows.
        count_key = None
        for k, tok in enumerate(qf.tokens):
            if not _COUNT_CUE.fullmatch(fold(tok)):
                continue
            before = [h for h in hits if h.mapping and h.span and h.span[1] == k and h.semantic_type != SemanticType.METRIC]
            if before:
                entity = before[0].mapping.entity
                # The catalog may say how this thing is counted: an order is a document, its lines are
                # not orders — "count_key" on the concept names the column whose distinct values are one
                # each ("ORDFICHEREF" on the order-line filter counts orders, not lines).
                count_key = (before[0].mapping.extra or {}).get("count_key")
                break
        for k, tok in enumerate(qf.tokens):
            if entity:
                break
            # A word a certified phrase already covers is that phrase's word, not a table of its own:
            # "YK onayında bekleyen sözleşmeler kaç tane" counts contracts, whatever "YK" alone recalls.
            if k in consumed or not is_domain_candidate(tok) or _COUNT_CUE.fullmatch(fold(tok)):
                continue                       # "tane" asks how many; it names nothing
            entity = self._entity_of_word(tok, index)
        entity = entity or self._primary_entity(hits)
        prof = self.by_entity.get(entity or "")
        if prof is None:
            return None
        key = next((c.name for c in prof.columns if c.is_primary_key), None)
        if count_key and any(_LINE_UNIT.fullmatch(fold(t)) for t in qf.tokens):
            count_key = None                   # "kaç kalem": lines are counted, not the documents they belong to
        if count_key and prof.column(count_key) is not None:
            key = prof.column(count_key).name
        formula = f"COUNT(DISTINCT {entity}.{key})" if key else f"COUNT(*)"
        m = Mapping(concept_id="", entity=entity, table_pattern=prof.table_pattern, formula=formula)
        return ResolvedSlot(
            term="kayıt sayısı", semantic_type=SemanticType.METRIC, status="COMPOSED", mapping=m, confidence=0.75,
            explain={"why": f"soru adet soruyor → {entity} kayıtları {('anahtar ' + key) if key else 'satır'} üzerinden sayıldı"
                            + (" (kavramın sayım anahtarı)" if count_key else ""),
                     "source": "count_cue"},
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

    def _negate_left_state(self, tok: str, k: int, left: list[ResolvedSlot]) -> Optional[ResolvedSlot]:
        """A negated light verb ("edilmemiş", "verilmedi", "olmamış") right after a state label slot
        turns that slot into its complement, in place; None when nothing to its left is such a slot."""
        for slot in left:
            m = slot.mapping
            if slot.semantic_type != SemanticType.DIMENSION_VALUE or m is None or not m.column:
                continue
            if (m.operator or "IN").upper() not in ("IN", "="):
                continue
            # A label names a *state* of the record ("iptal", "tamamlandı") and its negation is the
            # other state. A label that names the record's *kind* — a document type, a set the catalog
            # counts by a key ("sipariş") — is not a state: "sipariş vermemiş" is a customer with no such
            # record at all, which the absence branch reads; flipped here it became "orders of another
            # type", a filter nobody asked for. The catalog marks a kind with `count_key`.
            if (m.extra or {}).get("count_key"):
                continue
            slot.mapping = Mapping(concept_id=m.concept_id, entity=m.entity, table_pattern=m.table_pattern, column=m.column,
                                   operator="NOT IN", values=list(m.values), extra=dict(m.extra or {}))
            slot.status = "INFERRED"
            slot.confidence = min(slot.confidence, 0.75)
            slot.span = (slot.span[0], k + 1)
            slot.term = f"{slot.term} {tok}"
            slot.explain = {**(slot.explain or {}), "source": "negated_label",
                            "why": f"'{slot.term}' olumsuz: durumun dışı → {m.entity}.{m.column} NOT IN ({', '.join(map(str, m.values))})"}
            return slot
        return None

    def _negated_label(self, tok: str, k: int, index: dict[str, list[tuple[Concept, list[Mapping]]]]) -> Optional[ResolvedSlot]:
        """The certified state label this negated verb undoes, as a NOT IN slot — or None.

        Labels are certified in their affirmative form ("tamamlandı", "iptal edildi", "kapandı"); people
        ask for the other side ("tamamlanmadı", "iptal edilmemiş", "kapanmamış"). The negated verb's
        root minus its negation infix is the label's verb root. One label on one entity, or nothing —
        two labels answering the same root are the person's choice, not a guess."""
        root = verb_root(tok) or ""
        base = re.sub(r"(ma|me)$", "", root)
        if len(base) < 4:
            return None
        hits: list[tuple[Concept, Mapping]] = []
        for key, senses in index.items():
            for c, maps in senses:
                if c.semantic_type != SemanticType.DIMENSION_VALUE or not maps or is_negative(c.term):
                    continue
                label_root = verb_root(c.term) or stem(c.term)
                if not label_root or len(label_root) < 4:
                    continue
                if label_root == base or label_root.startswith(base) or base.startswith(label_root):
                    hits.append((c, maps[0]))
        concepts = {c.id for c, _ in hits}
        entities = {m.entity for _, m in hits}
        if len(concepts) != 1 or len(entities) != 1:
            return None
        c, m = hits[0]
        if (m.operator or "IN").upper() not in ("IN", "="):
            return None
        undone = Mapping(concept_id=m.concept_id, entity=m.entity, table_pattern=m.table_pattern, column=m.column,
                         operator="NOT IN", values=list(m.values), extra=dict(m.extra or {}))
        return ResolvedSlot(term=tok, semantic_type=SemanticType.DIMENSION_VALUE, status="INFERRED", concept_id=c.id,
                            mapping=undone, confidence=min(c.confidence, 0.75), span=(k, k + 1),
                            explain={"why": f"'{tok}' olumsuz: '{c.term}' durumunun dışı → {m.entity}.{m.column} NOT IN ({', '.join(map(str, m.values))})",
                                     "source": "negated_label"})

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
            if agg == "SUM" and re.search(r"oran|yuzde|ortalama|puan|katsayi|fiyat|birim", fold(f"{source_term} {column}")):
                agg = "AVG"                    # a rate summed over rows is a number nobody asked for
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
            folded = fold(question)
            asked_to_compare = _COMPARE_TO.search(folded) or _COMPARE_CUE.search(folded)
            if not asked_to_compare and any(is_negative(t) for t in qf.tokens):
                # "Geçen yıl alıp bu yıl hiç sipariş vermemiş": two periods, each the condition of a
                # different part of an absence question — not two figures to set side by side.
                sq.explanation.append("iki dönem var ama soru bir yokluk soruyor → her dönem kendi koşuluna ait")
                return
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
            # "kaç tane": a counting word asks how many, it does not name a column. Read as one, it met
            # NEW_ADET on a gift-product table and the count was taken there instead of on the subject.
            if _COUNT_CUE.fullmatch(fold(w)):
                return False
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
            # A backup or test copy ("AAAA_KASA_TEST") carries the same column names as the table it
            # was copied from and scores like it. Offered as the reading of a word, it sent the model to
            # a table nobody uses, and the model gave up. Copies stay only when nothing else answers.
            real = {k: v for k, v in best.items() if not is_shadow_copy(k[0])}
            if real:
                best = real
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
