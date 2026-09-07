"""Which columns a question is about — by the words in them, and by the values inside them.

Vector search over table descriptions was measured against this schema and did not work. Three
hundred Logo tables describe themselves in the same vocabulary — reference, date, amount, code, fiche
— so their embeddings sit on top of each other and every score lands between 0.35 and 0.58, which is
another way of saying nothing matched. Embedding a four-hundred-column table as one blob buries the
one column that would have answered.

What separates them is narrower and more literal:

  * the column's own name and the sentence written about it, weighted by how rare each word is —
    "iskonto" appears in a handful of columns and "referans" in nine thousand, and a scorer that does
    not know the difference is not scoring anything;
  * the values the column actually holds. No table description in this database contains the word
    Trendyol. `CLFLINE.TRADINGGRP` does, in its data, and that is the only thing in the catalog that
    can route a question about Trendyol sales to the right column.

A value hit therefore outranks a description hit: matching what a column *contains* is stronger
evidence than matching what someone wrote *about* it.

Everything is read from the catalog and held in memory — no service, no index to keep in step, and a
deployment without a profiled catalog gets nothing rather than a guess.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any, Iterable, Optional

from semantic_layer.normalize import STOPWORDS, content_tokens, fold, stem, tokenize

#: Words this schema repeats everywhere, on top of the general stop list: they are in nine thousand
#: column descriptions and separate none of them.
_NOISE = frozenset("""
kayit kaydi alan kolon tablo deger degeri referans referansi fiziksel adres numara numarasi kodu
record reference logical physical field value code number card line
""".split())


def tokens(text: str) -> list[str]:
    """Folded, de-stopped, stemmed — and the raw word kept beside its stem.

    Turkish is agglutinative and the first version of this ignored that: "şehirlerde" did not match
    "şehir", "çeklerin" did not match "çek", and questions asking in ordinary Turkish returned
    nothing at all. `stem` is the repository's own, applied to both sides so a catalog term and a
    question token meet in the same form. The unstemmed word travels too, because an exact value like
    "trendyol" must keep matching itself.
    """
    out: list[str] = []
    for t in content_tokens(tokenize(text)):
        if len(t) < 3 or t in _NOISE:
            continue
        out.append(t)
        root = stem(t)
        if root != t and len(root) >= 3 and root not in _NOISE:
            out.append(root)
    return out


def _split_identifier(name: str) -> list[str]:
    """`TOTALDISCOUNTS` → total, discounts. A Logo column name is words with the spaces removed."""
    n = fold(name).replace("_", " ")
    parts = re.findall(r"[a-z]+|\d+", n)
    out = list(parts) + [stem(p) for p in parts if len(p) > 4]
    # the common compounds, so a question about discounts reaches TOTALDISCOUNTS
    for word in ("total", "net", "gross", "amount", "price", "date", "code", "ref", "line", "type",
                 "discount", "vat", "cost", "rate", "client", "item", "stock", "trading", "group"):
        for p in parts:
            if word in p and word != p:
                out.append(word)
    return [t for t in out if len(t) > 2 and t not in _NOISE and t not in STOPWORDS]


class ColumnIndex:
    """BM25 over one document per column, plus an exact index of the values columns hold."""

    K1 = 1.4
    B = 0.72
    #: A value match is evidence about the data itself, not about how someone described it.
    VALUE_WEIGHT = 3.0
    #: Below this a hit says more about the corpus than about the question.
    MIN_SCORE = 1.0

    def __init__(self, profiles: Iterable[Any], annotations: Optional[dict] = None):
        self.docs: list[tuple[str, str]] = []          # (entity, column)
        self.terms: list[Counter] = []
        self.lengths: list[int] = []
        self.df: Counter = Counter()
        # value → the columns that hold it, exactly
        self.values: dict[str, set[int]] = defaultdict(set)
        annotations = annotations or {}
        seen: set[tuple[str, str]] = set()

        for prof in profiles:
            for col in getattr(prof, "columns", []) or []:
                key = (prof.entity, col.name.upper())
                if key in seen:
                    continue
                seen.add(key)
                said = annotations.get((prof.entity, col.name.upper())) or ""
                bag = Counter(_split_identifier(col.name))
                for text in (said, col.description or "", getattr(col, "unit", "") or ""):
                    bag.update(tokens(text))
                for entry in (getattr(col, "derived", None) or []):
                    bag.update(tokens(entry.get("text", "")))
                i = len(self.docs)
                for value, _count in (col.meaningful_values() or []):
                    for t in tokens(value):
                        self.values[t].add(i)
                        bag[t] += 1
                if not bag:
                    continue
                self.docs.append(key)
                self.terms.append(bag)
                self.lengths.append(sum(bag.values()))
                self.df.update(bag.keys())

        self.avg_len = (sum(self.lengths) / len(self.lengths)) if self.lengths else 1.0
        self.n = max(1, len(self.docs))

    def _idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def search(self, question: str, limit: int = 12) -> list[dict[str, Any]]:
        """The columns this question is most likely about, best first, each with why."""
        asked = tokens(question)
        if not asked or not self.docs:
            return []
        scores: dict[int, float] = defaultdict(float)
        matched: dict[int, set[str]] = defaultdict(set)
        value_hit: dict[int, set[str]] = defaultdict(set)

        for term in set(asked):
            idf = self._idf(term)
            for i, bag in enumerate(self.terms):
                tf = bag.get(term)
                if not tf:
                    continue
                norm = tf * (self.K1 + 1) / (tf + self.K1 * (1 - self.B + self.B * self.lengths[i] / self.avg_len))
                scores[i] += idf * norm
                matched[i].add(term)
            # a term that is a value in some column is the strongest signal there is
            for i in self.values.get(term, ()):
                scores[i] += self.VALUE_WEIGHT * idf
                value_hit[i].add(term)

        ranked = sorted(scores.items(), key=lambda kv: -kv[1])[:limit]
        out = []
        for i, score in ranked:
            if score < self.MIN_SCORE:
                break
            entity, column = self.docs[i]
            out.append({
                "entity": entity, "column": column, "score": round(score, 2),
                "matched": sorted(matched[i]),
                "values": sorted(value_hit[i]),
            })
        return out

    def entities(self, question: str, limit: int = 6) -> list[tuple[str, float]]:
        """The same answer rolled up to tables, which is what a prompt is built from."""
        best: dict[str, float] = {}
        for hit in self.search(question, limit=limit * 6):
            e = hit["entity"]
            best[e] = max(best.get(e, 0.0), hit["score"])
        return sorted(best.items(), key=lambda kv: -kv[1])[:limit]
