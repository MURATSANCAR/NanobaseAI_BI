"""Question → facts: candidate terms (1..3-grams within a clause), explicit code hints
("toptan (KOD 8)"), metric words, limit/order hints and temporal slots."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from semantic_layer.normalize import (
    METRIC_VOCAB_S,
    MODIFIERS_S,
    STOPWORDS_S,
    clauses,
    fold,
    ngrams,
    stem,
    tokenize,
)
from semantic_layer.runtime.temporal import parse_temporal

# "SPECODE 5" and "speccode 5" are the same request. Column names are upper case in the database and
# lower case in the way people type, and requiring capitals meant a stated filter was read as ordinary
# words and quietly dropped. Any word may be proposed here; whether it names a real column is settled
# against the profile by whoever consumes this, which is the only place that can know.
_CODE_HINT = re.compile(r"\b([A-Za-z][A-Za-z0-9_]{2,})\s*(?:=|:)?\s*((?:\d+\s*(?:,|/|ve|veya)\s*)*\d+)\b")
_EXPLICIT = re.compile(r"((?:[a-z]+\s+){0,3}[a-z]+)\s*\(\s*([a-z][a-z0-9_]{2,})\s*((?:\d+\s*(?:,|/|ve|veya)\s*)*\d+)\s*\)")
# A ranking cue followed by a number is a top-N. The noun after the number is deliberately not
# enumerated: which nouns a customer ranks by is their data's business, not this parser's.
_LIMIT = re.compile(r"\b(?:ilk|en cok satan|en cok|en fazla|en az|top|en yuksek|en dusuk|bastaki|basta)\s+(?:\w+\s+)?(\d{1,3})\b|\b(\d{1,3})\s+(?:\w+)\s+(?:listele|goster|ver|getir|sirala)\b")

GENERIC_S = frozenset(
    stem(w)
    for w in """
    fatura faturalar musteri musteriler cari cariler tedarikci kitap kitaplar urun urunler malzeme
    stok kanal kanallar yayinevi siparis siparisler satir satirlar hareket belge tablo kolon
    deger degeri kod kodu ad adi unvan tarih satan satilan satis alim alinan verilen
    rakam rakami sutun sutunu hane kalem baslik bilgi bilgisi
    """.split()
)


@dataclass
class QuestionFacts:
    tokens: list[str]
    terms: list[tuple[int, int, str]]                 # (start, end, stemmed n-gram)
    surface: dict[str, str]                           # stemmed n-gram → surface text (first seen)
    explicit_codes: list[tuple[str, tuple[str, ...]]]  # (COLUMN, values) stated in the question
    explicit_bindings: list[tuple[str, str, tuple[str, ...]]]  # (term, COLUMN, values) "toptan (KOD 8)"
    metric_words: list[str]
    temporal: list = field(default_factory=list)
    grain: Optional[str] = None
    limit: Optional[int] = None
    order_desc: bool = True
    numbers: list[str] = field(default_factory=list)


def _split_codes(raw: str) -> tuple[str, ...]:
    vals = re.split(r"\s*(?:,|/|ve|veya)\s*", raw.strip())
    return tuple(sorted({v for v in vals if v}, key=lambda x: (0, float(x)) if x.replace(".", "").isdigit() else (1, x)))


def is_content_word(w: str) -> bool:
    return w not in STOPWORDS_S and w not in MODIFIERS_S and not w.isdigit()


def extract_question_facts(question: str) -> QuestionFacts:
    raw = question or ""
    folded = fold(raw)
    temporal, grain = parse_temporal(raw)
    time_words = set()
    for slot in temporal:
        time_words.update(tokenize(slot.text))

    tokens: list[str] = []
    terms: list[tuple[int, int, str]] = []
    surface: dict[str, str] = {}
    for clause in clauses(raw):
        ctoks = tokenize(clause)
        base = len(tokens)
        tokens.extend(ctoks)
        stems = [stem(t) for t in ctoks]
        for i, j, _ in ngrams(ctoks, 3):
            window = ctoks[i:j]
            wst = stems[i:j]
            if any(w in time_words or w in STOPWORDS_S or w.isdigit() for w in window):
                continue
            if all(w in MODIFIERS_S for w in wst):
                continue
            key = " ".join(wst)
            terms.append((base + i, base + j, key))
            surface.setdefault(key, " ".join(window))

    explicit_codes = []
    for match in _CODE_HINT.finditer(raw):
        # Month names can also be physical column names in a wide ERP schema.
        # A parsed date must not acquire a second, unrelated COLUMN = YEAR meaning.
        phrase = fold(match.group(0)).strip()
        if "=" not in phrase and ":" not in phrase and any(
                re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", fold(t.text)) for t in temporal):
            continue
        col, vals = match.groups()
        explicit_codes.append((col.upper(), _split_codes(vals)))
    explicit_bindings: list[tuple[str, str, tuple[str, ...]]] = []
    for phrase, col, vals in _EXPLICIT.findall(folded):
        codes = _split_codes(vals)
        words = [stem(w) for w in phrase.split() if is_content_word(stem(w))]
        # drop leading generic words ("yalniz toptan satis faturalari" → "toptan satis fatura")
        while words and (words[0] in GENERIC_S or words[0] in METRIC_VOCAB_S):
            words.pop(0)
        specific = [w for w in words if w not in GENERIC_S and w not in METRIC_VOCAB_S]
        if len(specific) == 1:
            explicit_bindings.append((specific[0], col.upper(), codes))
        if len(words) > 1:
            explicit_bindings.append((" ".join(words[-3:]), col.upper(), codes))
        if len(specific) > 1 and specific != words[-3:]:
            explicit_bindings.append((" ".join(specific), col.upper(), codes))

    metric_words = sorted({stem(t) for t in tokens if stem(t) in METRIC_VOCAB_S})
    limit = None
    m = _LIMIT.search(folded)
    if m:
        limit = int(m.group(1) or m.group(2))
    order_desc = not bool(re.search(r"\b(artan|kucukten buyuge|en az|en dusuk)\b", folded))
    numbers = [t for t in tokens if t.isdigit() and not re.match(r"^20\d\d$", t)]
    return QuestionFacts(tokens, terms, surface, explicit_codes, explicit_bindings, metric_words, temporal, grain, limit, order_desc, numbers)


def question_terms(question: str) -> set[str]:
    return {t for _, _, t in extract_question_facts(question).terms}
