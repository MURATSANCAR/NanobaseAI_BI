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


def _closest(word: str, pool: dict[int, list[str]], limit: int) -> Optional[str]:
    best: list[str] = []
    top = limit + 1
    for n in range(len(word) - limit, len(word) + limit + 1):
        for s in pool.get(n, ()):
            if len(s) < 4:
                continue
            d = distance(word, s, limit)
            if d < top:
                best, top = [s], d
            elif d == top and s not in best:
                best.append(s)
    return best[0] if top <= limit and len(best) == 1 else None


def _slip(word: str, fixed: str) -> bool:
    """A typing slip, not a different word. Tam set 2026-09-28: "yazarların" became "yazarlar" (a customer-group
    label, a filter nobody asked for), "zararına" "kararı", "illere" and "tahsilatını" lost their endings — correct
    words the catalog does not carry, read as misspellings. A slip keeps the first letter and falls inside the word:
    one word being the start of the other is an ending, not a typo."""
    if not fixed or word[0] != fixed[0] or word.startswith(fixed) or fixed.startswith(word):
        return False
    common = next((i for i, (a, b) in enumerate(zip(word, fixed)) if a != b), min(len(word), len(fixed)))
    return common < min(len(word), len(fixed)) - 1


class Speller:
    """`stems`: bilinen kelimelerin kökleri (katalog adları, ay adları, dönem ve ölçü kelimeleri); `words`: aynı
    adların yazıldığı biçimler ("sayısı", "tutarı") — kısa bir kökün birden çok komşusu olduğunda kelimenin
    tamamı bunlarla karşılaştırılır ("saysıı": kök "say" hem "sayf" hem "sayi"ye bir harf; kelime "sayisi"ne)."""

    def __init__(self, stems: Iterable[str], words: Iterable[str] = ()):
        self.stems = frozenset(s for s in stems if s and s.isalpha() and len(s) >= 3)
        self.words = frozenset(w for w in words if w and w.isalpha() and len(w) >= 3)
        self._stems_by_len: dict[int, list[str]] = {}
        for s in self.stems:
            self._stems_by_len.setdefault(len(s), []).append(s)
        self._words_by_len: dict[int, list[str]] = {}
        for w in self.words:
            self._words_by_len.setdefault(len(w), []).append(w)

    def _exact(self, word: str) -> bool:
        return word in STOPWORDS_S or word in self.words or word in self.stems

    def _known(self, word: str) -> bool:
        return self._exact(word) or stem(word) in self.stems

    def split(self, word: str) -> Optional[str]:
        """"toplamkac" → "toplam kac", "tutarinedir" → "tutari nedir": the one cut where both halves are words
        as written; failing that, the one cut where both are known by their root."""
        for known in (self._exact, self._known):
            cuts = [f"{word[:k]} {word[k:]}" for k in range(3, len(word) - 2) if known(word[:k]) and known(word[k:])]
            if len(cuts) == 1:
                return cuts[0]
            if cuts:
                return None
        return None

    def near(self, word: str) -> Optional[str]:
        """"suabt" → "subat", "tutatrlari" → "tutarlari", "saysii" → "sayisi": the one known word, or the one known
        root with the ending kept, one letter away — and only a slip, not another word (`_slip`)."""
        if len(word) < 5 or not word.isalpha():
            return None
        whole = _closest(word, self._words_by_len, 1)
        if whole is not None and _slip(word, whole):
            return whole
        root = stem(word)
        if len(root) < 4:
            return None
        found = _closest(root, self._stems_by_len, 1)
        if found is None:
            return None
        fixed = found + word[len(root):]
        return fixed if _slip(word, fixed) else None

    def correct(self, word: str) -> Optional[str]:
        """Only called for a word the resolver could not place, so a root it shares with a known word ("saysii" →
        "say") does not make it known."""
        w = fold(word)
        if self._exact(w):
            return None
        return self.split(w) or self.near(w)
