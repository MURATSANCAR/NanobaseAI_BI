"""Motorun kök hâlindeki terimlerini okunur kelimeye çevirir: "malzem" → "malzeme".

Katalog terimleri eşleştirme için köke indirilmiş ve Türkçe harflerden arındırılmış saklanır; bu doğru.
Ama onay kuyruğunda bir kişiye "satinalm" göstermek ona bir kelime değil bir kırıntı onaylatmaktır.
Okunur biçim uydurulmaz: dağıtımın kendi metinlerinden — kolon açıklamaları, gözlenen değer adları,
bilgi dokümanları — o köke uyan en sık kelime alınır. Uyan yoksa terim olduğu gibi kalır.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Iterable

from semantic_layer.normalize import fold

_WORD = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşüÂâÎîÛû]{3,}")
#: Kökle kelime arasında en çok bu kadar harf olabilir: "malzem"+"e", "satinalm"+"a", "yuzd"+"e".
_MAX_SUFFIX = 3


def _lower_tr(w: str) -> str:
    return w.replace("I", "ı").replace("İ", "i").lower()


class Vocabulary:
    def __init__(self) -> None:
        self._surface: dict[str, Counter] = defaultdict(Counter)

    @classmethod
    def from_texts(cls, texts: Iterable[str | None]) -> "Vocabulary":
        v = cls()
        for t in texts:
            if t:
                v.add(t)
        return v

    def add(self, text: str) -> None:
        for w in _WORD.findall(text):
            low = _lower_tr(w)
            self._surface[fold(low)][low] += 1

    def _best(self, key: str) -> str:
        return self._surface[key].most_common(1)[0][0]

    def word(self, token: str) -> str:
        key = fold(token)
        if key in self._surface:
            return self._best(key)
        near = [k for k in self._surface if k.startswith(key) and 0 < len(k) - len(key) <= _MAX_SUFFIX]
        if not near or len(key) < 3:
            return token
        near.sort(key=lambda k: (-sum(self._surface[k].values()), len(k)))
        return self._best(near[0])

    def readable(self, term: str) -> str:
        if not term or "." in term or "->" in term:
            return term                 # ilişki ve kolon yolları kelime değildir
        return " ".join(self.word(t) for t in term.split())
