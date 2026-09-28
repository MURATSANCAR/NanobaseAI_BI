"""Model çıktısının temizliği: sessiz/uğultulu parçada modelin uydurduğu kalıp cümleler ve takılıp tekrar eden öbekler.

Anlamı değiştiren hiçbir düzeltme burada yapılmaz (noktalama, özel ad ve biçim portal tarafındaki isteğe bağlı Zeki AI
düzeltmesinin işi; o da sayı denetiminden geçer).
"""
from __future__ import annotations

import re

#: Konuşma olmayan parçada Türkçe altyazı verisinden öğrenilmiş kalıplar. Parçanın BÜTÜNÜ bunlardan biriyse atılır;
#: gerçek konuşmanın içinde geçen aynı kelimeler silinmez.
_PHANTOMS = [
    r"alt ?yaz[ıi]\s*m\.?\s*k\.?",
    r"alt ?yaz[ıi](lar)?\s*[:\-]\s*[\w .]{0,30}",
    r"abone olmay[ıi] unutmay[ıi]n(ız)?",
    r"izledi[ğg]iniz i[çc]in te[şs]ekk[üu]r ederim",
    r"izledi[ğg]iniz i[çc]in te[şs]ekk[üu]rler",
    r"bir sonraki videoda g[öo]r[üu][şs]mek [üu]zere",
    r"m\.?\s*k\.?",
]
_PHANTOM_RE = re.compile(r"^\W*(?:" + "|".join(_PHANTOMS) + r")\W*$", re.IGNORECASE)


def is_phantom(text: str) -> bool:
    t = text.strip().replace("İ", "i").replace("I", "ı").lower()
    return bool(_PHANTOM_RE.match(t)) if t else True


def squash_repeats(text: str, max_repeat: int = 3) -> str:
    """Aynı 1–8 kelimelik öbek art arda `max_repeat`'ten fazla geçiyorsa bu modelin takılmasıdır, tek kopyaya iner
    («evet evet evet» kalır; yirmi kez yazılmış cümle bire iner). En kısa periyot önce denenir: iki kelimelik öbeğin
    döngüsü dört kelimelik öbeğin döngüsü sanılıp yarım bırakılmasın."""
    words = text.split()
    if len(words) < 3:
        return text.strip()
    out: list[str] = []
    i = 0
    while i < len(words):
        cut = False
        for n in range(1, 9):
            gram = words[i:i + n]
            if len(gram) < n:
                continue
            reps = 1
            while words[i + reps * n:i + (reps + 1) * n] == gram:
                reps += 1
            if reps > max_repeat:
                out.extend(gram)
                i += reps * n
                cut = True
                break
        if not cut:
            out.append(words[i])
            i += 1
    return " ".join(out)


def clean(text: str) -> str:
    t = " ".join((text or "").split())
    if is_phantom(t):
        return ""
    return squash_repeats(t)


def join(parts: list[str]) -> str:
    return " ".join(p for p in (x.strip() for x in parts) if p)
