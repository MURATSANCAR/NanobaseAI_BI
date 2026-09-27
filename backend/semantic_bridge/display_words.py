"""Kolon adlarının ekrandaki Türkçe yazımı.

SQL takma adları ASCII'dir (`satis_tutari`, `gecen_yila_net_ciro`); ekran bunları alt çizgiyi boşluğa
çevirerek başlık yapınca «Satis tutari» çıkıyordu. Doğru yazım zaten katalogda: onaylı terimler ve eş
anlamlılar insanların yazdığı Türkçeyi taşır («net satış tutarı», «geçen yıl»). Buradan sözcük sözcük bir
harita çıkar: ASCII hâli → katalogda görülen Türkçe yazım. Elle yazılmış liste yok; katalog neyse harita o.

Bir ASCII sözcüğün birden çok Türkçe yazımı görülürse en sık olanı seçilir. Katalogda ASCII yazılmış
terimler («satis tutari») haritaya oy vermez: onlar tembel yazımdır, doğru yazımın rakibi değil.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Iterable

from semantic_layer.normalize import fold

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def _lower_tr(w: str) -> str:
    return w.replace("I", "ı").replace("İ", "i").lower()


def build(texts: Iterable[str]) -> dict[str, str]:
    """Metinlerdeki Türkçe harfli sözcüklerden ASCII → yazım haritası."""
    seen: dict[str, Counter[str]] = defaultdict(Counter)
    for text in texts:
        for w in _WORD.findall(text or ""):
            low = _lower_tr(w)
            key = fold(low)
            if key != low and key.isascii():
                seen[key][low] += 1
    return {k: c.most_common(1)[0][0] for k, c in seen.items()}


def catalog_texts(store: Any, tenant_id: str, datasource_id: str) -> Iterable[str]:
    """Reddedilmemiş bütün terimler ve eş anlamlıları."""
    for c in store.find_concepts(tenant_id, datasource_id, limit=100000):
        if str(getattr(c.status, "value", c.status)).upper() == "REJECTED":
            continue
        yield c.term
        yield from (c.synonyms or [])
