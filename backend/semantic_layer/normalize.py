"""Turkish-aware text normalisation, tokenisation, light stemming and n-grams.

Everything the miner and the resolver compare goes through the same functions so that
"Toptan satışları" (question) and "toptan" (catalog term) meet on equal footing.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional

_TR_MAP = str.maketrans("çğıöşüâîûÇĞİÖŞÜÂÎÛ", "cgiosuaiuCGIOSUAIU")
_APOS = re.compile(r"['’`´]")
_NON_WORD = re.compile(r"[^a-z0-9%]+")
_WS = re.compile(r"\s+")

# Content-free words (folded). Temporal words are handled by runtime.temporal before term extraction.
STOPWORDS: frozenset[str] = frozenset(
    """
    ve veya ile icin bu su o bir da de ki mi mu mi ne nedir nelerdir kac hangi hangileri hangisi
    olarak olup gore bazinda bazli bazinda baz kirilim kiriliminda listele goster getir ver
    ver yap hesapla karsilastir sirala sirasiyla sirayla sirada azalan artan siraya siral en cok az
    ilk son top ayrica her icin icindeki icinde uzerinde ustunde altinda arasinda arasindaki
    yalniz yalnizca sadece kimler kim nerede nasil neden var yok mi midir dir dur tur tir
    lutfen ise ama fakat ancak ya eger ozellikle daha gibi kadar bunlar sunlar onlar
    bul bulur dok dokum ozetle ozet incele raporla goster gosterir cikart derle
    kiyasla kiyaslar grafik grafigi tablo tablosu liste listesi rapor raporu gorsel cizelge
    yoksa taraf tarafi tarafini yani sekilde bakimindan acisindan
    tum tumu butun toplamda genel olarak degil ile birlikte beraber
    milyon milyar bin tl usd eur uzer uzeri uzerindeki ustu altinda alti fazla dusuk yuksek
    sahip ait
    """.split()
)

# Words that shape the query (aggregation / ordering / scale) but are not catalog concepts.
MODIFIERS: frozenset[str] = frozenset(
    """
    toplam toplami toplamini toplamlari ortalama ortalamasi sayisi sayi adet adedi adedini
    oran orani oranini yuzde yuzdesi pay payi payini kumulatif dagilim dagilimi
    en cok az fazla dusuk yuksek buyuk kucuk ilk son azalan artan
    """.split()
)

# Metric vocabulary — tokens that usually name a measure (kept separate from stopwords so that
# metric mining can still see them).
METRIC_VOCAB: frozenset[str] = frozenset(
    """
    ciro tutar tutari adet aded adedi miktar sayi sayisi oran orani marj marji kar maliyet iskonto
    ortalama toplam pay payi net brut satis satislar hasilat gelir gider fiyat
    """.split()
)


_SUFFIXES = (
    "larimizi", "lerimizi", "larinizi", "lerinizi", "larimiz", "lerimiz", "lariniz", "leriniz",
    "larimi", "lerimi", "larini", "lerini", "larina", "lerine", "lardan", "lerden", "larda", "lerde",
    "larindan", "lerinden", "larinda", "lerinde", "larin", "lerin", "larim", "lerim",
    "imizi", "umuzu", "imiz", "umuz", "iniz", "unuz", "miz", "muz", "niz", "nuz",
    "lari", "leri", "lar", "ler",
    "sindan", "sunden", "sundan", "sinden", "sinda", "sunda", "sinin", "sunun",
    "sini", "sunu", "sina", "suna", "sine", "sune",
    "indan", "inden", "undan", "unden", "ndan", "nden", "dan", "den", "tan", "ten",
    "inin", "unun", "nin", "nun", "sina", "sine", "ina", "ine", "una", "une",
    "ndaki", "ndeki", "daki", "deki", "taki", "teki", "nda", "nde", "da", "de", "ta", "te",
    "ya", "ye", "yi", "yu", "yla", "yle", "la", "le",
    "si", "su", "in", "un", "im", "um", "ni", "nu",
    "i", "u", "a", "e",
)

# Turkish final-consonant softening: a stem ending in p/ç/t/k voices before a vowel-initial suffix
# ("kitap" → "kitabı", "grup" → "grubu"). Stripping the suffix leaves the voiced form, so the stem is
# hardened back. Applied to catalog terms and question words alike, so the two always meet.
_HARDEN = {"b": "p", "d": "t", "g": "k"}
# Derivational endings: they build a new word from a noun rather than inflect it, so they are stripped
# only as a *fallback* key ("kârlılık" → "kârlı" → "kâr"), never in the primary stem.
_DERIVATIONS = ("liligi", "luluk", "lilik", "lulugu", "lik", "lig", "luk", "lug", "siz", "suz",
                "ci", "cu", "li", "lu", "ce", "ca")

# Never stem these (short, or stemming would collide with another word).
_PROTECTED = frozenset("toptan perakende iade net brut ciro kanal ay yil gun hafta tutar adet oran pay marj".split())


def fold(text: str) -> str:
    """Lower-case with Turkish dotted/dotless I handled, diacritics folded to ASCII."""
    s = (text or "").replace("İ", "i").replace("I", "ı")
    s = s.translate(_TR_MAP).lower()
    s = _APOS.sub(" ", s)
    return _WS.sub(" ", s).strip()


def tokenize(text: str) -> list[str]:
    s = fold(text)
    s = _NON_WORD.sub(" ", s)
    return [t for t in s.split() if t]


@lru_cache(maxsize=65536)
def is_inflection_of(token: str, root: str) -> bool:
    """Is `token` this root wearing Turkish suffixes, or a different word that merely starts the same?

    Stemming answers neither question reliably at this length: it cuts "büyümesi" back past "büyüme",
    and leaves "trendyol" whole. The reliable test is the other direction — take the root off the
    front and ask whether what remains is a suffix chain this language can produce. "büyüme|si" can
    be; "trend|yol" cannot, and a marketplace stops being read as the word "trend".
    """
    t, r = fold(token), fold(root)
    if t == r:
        return True
    for base in {r} | {r[:-1] + hard for last, hard in _HARDEN.items() if r.endswith(last)}:
        if not t.startswith(base):
            continue
        tail = t[len(base):]
        # buffer consonants Turkish inserts between a vowel-final stem and a vowel-initial suffix
        if tail[:1] in ("y", "n", "s") and tail[1:2] in "aeiouüöı":
            tail = tail[1:]
        while tail:
            for suf in _SUFFIXES:                       # longest first: _SUFFIXES is ordered that way
                if tail.startswith(suf):
                    tail = tail[len(suf):]
                    break
            else:
                break
        if not tail:
            return True
    return False


def stem(token: str) -> str:
    """Very light suffix stripping (max three passes, never below 4 chars). Deterministic and
    symmetric: both catalog terms and question tokens go through it."""
    t = token
    if t in _PROTECTED or len(t) <= 4 or t.isdigit():
        return t
    stripped = False
    for _ in range(3):
        for suf in _SUFFIXES:
            floor = 4 if len(suf) == 1 else 3
            if t.endswith(suf) and len(t) - len(suf) >= floor:
                t = t[: -len(suf)]
                stripped = True
                break
        else:
            break
        if t in _PROTECTED:
            break
    if stripped and t and t[-1] in _HARDEN and len(t) >= 3:
        t = t[:-1] + _HARDEN[t[-1]]
    return t


def derived_forms(token: str) -> list[str]:
    """Progressively undo Turkish *derivational* endings: "kârlılık" → ["karlilik", "karli", "kar"].

    People name a measure with the adjective or the abstract noun built from it ("kârlı", "kârlılığımız")
    while a catalog is keyed on the base ("kâr"). Each step is a fallback key, tried only after the
    inflected form itself missed, and every hit is reported as INFERRED.
    """
    out: list[str] = []
    for start in dict.fromkeys([fold(token), stem(token)]):
        out.extend(_undo_derivations(start))
    return list(dict.fromkeys(out))


def _undo_derivations(t: str) -> list[str]:
    out: list[str] = []
    for _ in range(3):
        for suf in _DERIVATIONS:
            if t.endswith(suf) and len(t) - len(suf) >= 3:
                t = t[: -len(suf)]
                if t and t[-1] in _HARDEN:
                    t = t[:-1] + _HARDEN[t[-1]]
                out.append(t)
                break
        else:
            break
    return out


def normalize_term(term: str) -> str:
    """Canonical key for a multi-word term: folded, tokenised, stemmed, single-spaced."""
    return " ".join(stem(t) for t in tokenize(term))


def content_tokens(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t not in STOPWORDS and not t.isdigit()]


def ngrams(tokens: list[str], n_max: int = 3) -> list[tuple[int, int, str]]:
    """All 1..n_max-grams as (start, end, text) over the given token list."""
    out: list[tuple[int, int, str]] = []
    for n in range(1, n_max + 1):
        for i in range(0, len(tokens) - n + 1):
            out.append((i, i + n, " ".join(tokens[i : i + n])))
    return out


def alias_tokens(alias: str) -> list[str]:
    """SQL alias → tokens (net_ciro → [net, ciro]; perakendeToplam → [perakende, toplam])."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", alias or "")
    return [stem(t) for t in tokenize(s.replace("_", " ")) if t not in STOPWORDS]


def stemmed(words) -> frozenset[str]:
    """Stem a vocabulary so it can be compared with stemmed question tokens."""
    return frozenset(stem(w) for w in words) | frozenset(words)


STOPWORDS_S = stemmed(STOPWORDS)
MODIFIERS_S = stemmed(MODIFIERS)
METRIC_VOCAB_S = stemmed(METRIC_VOCAB)

CLAUSE_SPLIT = re.compile(r"[,;:()?!/|\n]|\s-\s|\s–\s|\s—\s")


def clauses(text: str) -> list[str]:
    """Split a question into clauses at punctuation so n-grams never cross a comma."""
    return [c for c in (x.strip() for x in CLAUSE_SPLIT.split(text or "")) if c]


# ---------------------------------------------------------------------- Turkish word shapes
# Language-level morphology, not a domain vocabulary: these patterns describe how Turkish inflects a
# verb or forms a question, so ordinary speech ("sattık", "oldu mu", "gösterir misin") is not mistaken
# for business vocabulary the catalog is missing. Nothing here names a customer's data.

_VERB_TAILS = (
    # past / evidential / progressive / future / aorist + person endings
    "dim", "dım", "dum", "düm", "tim", "tım", "tum", "tüm",
    "din", "dın", "dun", "dün", "tin", "tın", "tun", "tün",
    "dik", "dık", "duk", "dük", "tik", "tık", "tuk", "tük",
    "diniz", "dınız", "dunuz", "dünüz", "tiniz", "tınız", "tunuz", "tünüz",
    "diler", "dılar", "tiler", "tılar",
    "di", "dı", "du", "dü", "ti", "tı", "tu", "tü",
    "mis", "mış", "mus", "muş", "miz", "muz",
    "yor", "yorum", "yoruz", "yorsun", "yorsunuz", "yorlar",
    "acak", "ecek", "acagiz", "ecegiz", "acaklar", "ecekler",
    "iyor", "uyor", "üyor",
    "ir", "ır", "ur", "ür", "er", "ar",
    "sin", "sın", "sun", "sün", "siniz", "sınız", "sunuz", "sünüz",
    "meli", "malı", "mali",
    # participles ("satan", "bekleyen", "satmayan") and converbs ("düşerken", "eleyip", "kazandığımız"):
    # a verb wearing a noun's clothes is still a verb, so it names no catalog entry.
    "mayan", "meyen", "mayacak", "meyecek", "madan", "meden", "maksizin", "meksizin",
    "digimiz", "dığımız", "digimiz", "tigimiz", "tığımız", "diginde", "dığında", "diklerini",
    "digi", "dığı", "tigi", "tığı", "dikleri", "tikleri",
    "arak", "erek", "yarak", "yerek", "irken", "ırken", "arken", "erken", "urken", "ürken", "yken", "ken",
    "yan", "yen", "an", "en", "yip", "yıp", "yup", "yüp", "ip", "ıp", "up", "üp",
)
# Bare -an/-en is not a reliable participle marker: plenty of ordinary nouns end that way ("toptan",
# "zaman", "düzen"). It stays available to verb_root, where a bridge only survives if a certified term
# backs it, but it never decides on its own that a word is grammar rather than business vocabulary.
_AMBIGUOUS_TAILS = frozenset(("an", "en"))
_QUESTION_TAILS = ("mi", "mı", "mu", "mü", "misin", "misiniz", "midir", "mıdır")
# The dental past tense is a verb marker even on a four-letter word ("oldu", "aldı", "tuttu").
_PAST_TAILS = frozenset(("di", "dı", "du", "dü", "ti", "tı", "tu", "tü"))
# Copula endings turn any word into a predicate ("iyiyiz", "hazırız") without naming anything.
_COPULA_TAILS = ("yiz", "yız", "yuz", "yüz", "yim", "yım", "yum", "yüm", "sin", "siniz", "dir", "dır")
# Pronouns and discourse words: closed word classes, so listing them is grammar, not domain knowledge.
_FUNCTION_WORDS = frozenset(
    """
    ben sen o biz siz onlar bana sana ona bize size onlara beni seni onu bizi sizi onlari
    bu su bunu sunu bunlar sunlar bunun sunun burada surada orada
    ne neden nasil nicin kim kime kimin hangi hangisi kac kacinci nerede nereye nereden
    var yok evet hayir lutfen tamam belki galiba sanki yani ayrica hem ile ise ki de da mi
    bir birkac biraz cok az daha en gibi kadar sonra once simdi hep hic asla
    bizim sizin benim senin onun bizde sizde bende sende bizden sizden
    iyi kotu guzel normal onemli onemsiz dogru yanlis yeni eski ayni farkli benzer
    hizli yavas basarili basarisiz sey seyler durum durumu genel ozel
    """.split()
)


def is_function_word(token: str) -> bool:
    return fold(token) in _FUNCTION_WORDS


def is_verb_form(token: str) -> bool:
    """Does this surface form look like an inflected verb or a question particle?"""
    t = fold(token)
    if len(t) < 3:
        return t in _QUESTION_TAILS
    if t in _QUESTION_TAILS:
        return True
    for tail in _VERB_TAILS:
        if not t.endswith(tail):
            continue
        root = t[: -len(tail)]
        # a noun that merely ends the same way ("kadar", "zaman") keeps a plausible noun root, so
        # require the root to be short enough to be a verb stem; two-letter tails need a longer word
        # still, otherwise every noun ending in -an or -ip would read as a participle.
        if tail in _AMBIGUOUS_TAILS:
            continue
        strict = len(tail) <= 2 and tail not in _PAST_TAILS
        if strict and (len(t) < 5 or not 3 <= len(root) <= 6 or stem(t) != t):
            continue
        if len(root) >= 2 and len(root) <= 7:
            return True
    return any(t.endswith(c) and len(t) - len(c) >= 2 and is_function_word(t[: -len(c)]) for c in _COPULA_TAILS)


def is_domain_candidate(token: str) -> bool:
    """Could this word name something in the business domain? Ordinary speech is not a catalog gap.

    The test runs on the inflected form *and* on its stem, so "sayıyı" is recognised as the generic
    counting word "sayı" rather than mistaken for a term the catalog is missing.
    """
    t = fold(token)
    if len(t) < 3 or t.isdigit():
        return False
    if is_function_word(t) or is_verb_form(t):
        return False
    forms = {t, stem(t), short_root(t)}
    if forms & (STOPWORDS_S | MODIFIERS_S):
        return False
    return not any(is_function_word(f) for f in forms)


def verb_root(token: str) -> Optional[str]:
    """The stem left after removing a verb inflection: "sattık" → "sat", "satıyor" → "sat".

    Used to bridge how people speak (verbs) to how a catalog is keyed (nouns). Doubled consonants from
    Turkish consonant assimilation are collapsed, so "sattık" and "satış" meet on the same root.
    """
    t = fold(token)
    best = None
    for tail in _VERB_TAILS:
        if t.endswith(tail) and len(t) - len(tail) >= 2:
            root = t[: -len(tail)]
            if best is None or len(root) < len(best):
                best = root
    if best is None:
        return None
    if len(best) >= 2 and best[-1] == best[-2]:
        best = best[:-1]                     # satt → sat
    return best if len(best) >= 3 else None


# Turkish cardinals: a closed word class, so reading them is grammar rather than domain knowledge.
_CARDINALS = {
    "bir": 1, "iki": 2, "uc": 3, "dort": 4, "bes": 5, "alti": 6, "yedi": 7, "sekiz": 8, "dokuz": 9,
    "on": 10, "yirmi": 20, "otuz": 30, "kirk": 40, "elli": 50, "altmis": 60, "yetmis": 70,
    "seksen": 80, "doksan": 90, "yuz": 100, "bin": 1000,
}


# Case endings that fit on a root too short for the stemmer's floor ("ay" → "aya", "o ayki").
_SHORT_CASES = ("larinda", "lerinde", "lardan", "lerden", "larda", "lerde", "lari", "leri", "lar", "ler",
                "ndan", "nden", "daki", "deki", "taki", "teki", "dan", "den", "tan", "ten",
                "nin", "nun", "ki", "ku", "da", "de", "ta", "te", "ya", "ye", "in", "un", "a", "e", "i", "u")


def short_root(token: str) -> str:
    """Root of a very short word the main stemmer refuses to touch: "aya" → "ay", "ayki" → "ay".

    Turkish attaches the same case endings to two-letter roots (ay, yıl, gün) as to long ones; the
    stemmer keeps a four-character floor to avoid eroding real words, so short roots are recovered here.
    """
    t = fold(token)
    for _ in range(2):
        for suf in _SHORT_CASES:
            if t.endswith(suf) and len(t) - len(suf) >= 2:
                t = t[: -len(suf)]
                break
        else:
            break
    return t


def cardinal(token: str) -> Optional[int]:
    """"beş" → 5. Written-out numbers are how people say a top-N ("en yüksek beş kanal")."""
    t = fold(token)
    if t.isdigit():
        return int(t)
    return _CARDINALS.get(t)


# A participle turns a verb into a noun's modifier ("bekleyen siparişler"), a converb chains clauses
# ("ciro düşerken"). Both carry meaning the catalog may not cover, so they are kept apart from ordinary
# verb inflection: a predicate verb can be dropped, a modifier on the subject cannot.
_PARTICIPLE_TAILS = (
    "mayan", "meyen", "mayacak", "meyecek", "yan", "yen", "an", "en",
    "irken", "ırken", "arken", "erken", "urken", "ürken", "yken",
    "digi", "dığı", "tigi", "tığı", "dikleri", "tikleri", "digimiz", "dığımız", "tigimiz", "tığımız",
    "mis", "mış", "mus", "muş",
)
# Negation infixes: "satmayan", "satmadı", "satmıyor" — the opposite of what the catalog term means.
_NEGATIVE_TAILS = (
    "mayan", "meyen", "mayacak", "meyecek", "madan", "meden", "madi", "medi", "madı", "medi",
    "miyor", "mıyor", "muyor", "müyor", "maz", "mez", "mam", "mem", "mamis", "memis", "mamış", "memiş",
)
# Lexical hints only. Whether a verb contributes a constraint needs contextual evidence.
_LIGHT_ROOTS = frozenset("et ed edil edil ol olun olus yap yapil kil bulun gerceklestir gerceklas gecir".split())


def is_participle(token: str) -> bool:
    t = fold(token)
    for tail in _PARTICIPLE_TAILS:
        if t.endswith(tail) and tail not in _AMBIGUOUS_TAILS:
            root = t[: -len(tail)]
            if len(tail) <= 2 and (len(t) < 5 or not 3 <= len(root) <= 6 or stem(t) != t):
                continue
            if 2 <= len(root) <= 7:
                return True
    return False


def is_negative(token: str) -> bool:
    t = fold(token)
    return any(t.endswith(tail) and len(t) - len(tail) >= 2 for tail in _NEGATIVE_TAILS)


def is_light_verb(token: str) -> bool:
    """Return a lexical hint, never proof that a token can be discarded."""
    root = verb_root(token)
    return bool(root) and root in _LIGHT_ROOTS
