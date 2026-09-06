"""Turkish-aware text normalisation, tokenisation, light stemming and n-grams.

Everything the miner and the resolver compare goes through the same functions so that
"Toptan satışları" (question) and "toptan" (catalog term) meet on equal footing.
"""

from __future__ import annotations

import re
from functools import lru_cache

_TR_MAP = str.maketrans("çğıöşüâîûÇĞİÖŞÜÂÎÛ", "cgiosuaiuCGIOSUAIU")
_APOS = re.compile(r"['’`´]")
_NON_WORD = re.compile(r"[^a-z0-9%]+")
_WS = re.compile(r"\s+")

# Content-free words (folded). Temporal words are handled by runtime.temporal before term extraction.
STOPWORDS: frozenset[str] = frozenset(
    """
    ve veya ile icin bu su o bir da de ki mi mu mi ne nedir nelerdir kac hangi hangileri hangisi
    olan olarak olup gore bazinda bazli bazinda baz kirilim kiriliminda listele goster getir ver
    ver yap hesapla karsilastir sirala sirasiyla sirayla sirada azalan artan siraya siral en cok az
    ilk son top ayrica her icin icindeki icinde uzerinde ustunde altinda arasinda arasindaki
    yalniz yalnizca sadece kimler kim nerede nasil neden var yok mi midir dir dur tur tir
    lutfen ise ama fakat ancak ya eger ozellikle daha gibi kadar bunlar sunlar onlar
    tum tumu butun toplamda genel olarak degil ile birlikte beraber
    milyon milyar bin tl usd eur uzer uzeri uzerindeki ustu altinda alti fazla dusuk yuksek
    alan eden olan yapan veren gelen giden sahip ait
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
    "larini", "lerini", "larina", "lerine", "lardan", "lerden", "larda", "lerde",
    "lari", "leri", "lar", "ler",
    "indan", "inden", "undan", "unden", "ndan", "nden", "dan", "den", "tan", "ten",
    "inin", "unun", "nin", "nun", "sina", "sine", "ina", "ine", "una", "une",
    "daki", "deki", "taki", "teki", "da", "de", "ta", "te",
    "ya", "ye", "yi", "yu", "yla", "yle", "la", "le",
    "si", "su", "in", "un", "im", "um",
    "i", "u", "a", "e",
)

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
def stem(token: str) -> str:
    """Very light suffix stripping (max three passes, never below 4 chars). Deterministic and
    symmetric: both catalog terms and question tokens go through it."""
    t = token
    if t in _PROTECTED or len(t) <= 4 or t.isdigit():
        return t
    for _ in range(3):
        for suf in _SUFFIXES:
            if t.endswith(suf) and len(t) - len(suf) >= 4:
                t = t[: -len(suf)]
                break
        else:
            break
        if t in _PROTECTED:
            break
    return t


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
