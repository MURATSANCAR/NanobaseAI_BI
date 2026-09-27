"""Yazım hatası: çözülemeyen bir kelimenin bilinen kelimelerden hangisi olduğu (K5).

2026-09-24/25, müşteri VM'i: "2026 şuabt ayında toplamkaç adet satış", "satış ve iade faturalarının saysıı ve toplam
tutatrları" — soru doğru kurulmuştu, birkaç harf yüzünden "katalogda tanımlı değil" reddi aldı. Düzeltme yalnız
çözülemeyen kelimeye, yalnız tek bir adaya ve yalnız bilinen bir kelime dağarına karşı yapılır:
  - bitişik yazılmış iki kelime ("toplamkaç", "tutarınedir") — iki parça da bilinen kelime;
  - bir harf yer değiştirmiş, eksik ya da fazla ("şuabt" → şubat, "tutatrları" → tutarları, "saysıı" → sayısı); kök
    karşılaştırılır, ek olduğu gibi kalır. 8 harften uzun köklerde iki harf.
Hangi okumanın kabul edileceğine çağıran karar verir (çözülmeyen kelime azalmalı)."""
from __future__ import annotations

from typing import Iterable, Optional

from semantic_layer.normalize import STOPWORDS_S, fold, stem


def distance(a: str, b: str, limit: int = 2) -> int:
    """Damerau–Levenshtein (bitişik harf yer değiştirmesi bir işlem); `limit`'i aşınca limit+1."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2: list[int] = []
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        if min(cur) > limit and min(prev) > limit:     # a transposition reaches back two rows
            return limit + 1
        prev2, prev = prev, cur
    return prev[-1]


class Speller:
    """`stems`: bilinen kelimelerin kökleri (katalog adları, ay adları, dönem ve ölçü kelimeleri)."""

    def __init__(self, stems: Iterable[str]):
        self.stems = frozenset(s for s in stems if s and s.isalpha() and len(s) >= 3)
        self._by_len: dict[int, list[str]] = {}
        for s in self.stems:
            self._by_len.setdefault(len(s), []).append(s)

    def _known(self, word: str) -> bool:
        return word in STOPWORDS_S or word in self.stems or stem(word) in self.stems

    def split(self, word: str) -> Optional[str]:
        """"toplamkac" → "toplam kac": the one cut where both halves are known words."""
        cuts = [f"{word[:k]} {word[k:]}" for k in range(3, len(word) - 2)
                if self._known(word[:k]) and self._known(word[k:])]
        return cuts[0] if len(cuts) == 1 else None

    def near(self, word: str) -> Optional[str]:
        """"suabt" → "subat", "tutatrlari" → "tutarlari": the one known root within reach; the ending is kept."""
        if len(word) < 5 or not word.isalpha():
            return None
        root = stem(word)
        limit = 2 if len(root) >= 8 else 1
        best: list[str] = []
        top = limit + 1
        for n in range(len(root) - limit, len(root) + limit + 1):
            for s in self._by_len.get(n, ()):
                if len(s) < 4:
                    continue
                d = distance(root, s, limit)
                if d < top:
                    best, top = [s], d
                elif d == top and s not in best:
                    best.append(s)
        if top > limit or len(best) != 1:
            return None
        return best[0] + word[len(root):]

    def correct(self, word: str) -> Optional[str]:
        w = fold(word)
        if self._known(w):
            return None
        return self.split(w) or self.near(w)
