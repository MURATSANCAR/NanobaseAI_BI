"""Zeki AI'ın yazdığı pazarlama metninin denetimi (model çıktısı ekrana gitmeden önce).

Dört kural, cümle düzeyinde; kuralı bozan cümle **düşer** ve nedeniyle kayda geçer (sayısı ekranda görünür):

1. **Alıntı birebir olmalı.** «…», "…" ya da “…” içindeki her alıntı kaynak metinlerde (CRM'deki arka kapak, spot,
   alıntılar, kitabın en önemli cümlesi, föy…) boşluk ve tırnak farkı gözetilmeden birebir aranır; bulunmayan alıntının
   cümlesi düşer.
2. **Rakamı model üretmez.** Cümledeki her sayı ya kaynak metinlerde ya da modele verilen olgu listesinde (karne
   rakamları) geçmeli; geçmeyen sayının cümlesi düşer. Yıl, sıra ve hashtag içindeki sayılar da bu kurala tabidir.
3. **Kanıtsız üstünlük iddiası yok** («en çok satan», «bir numara», «rekor»…; Ticari Reklam ve Haksız Ticari
   Uygulamalar Yönetmeliği kapsamı — hukuk birimine doğrulatılacak). Liste yönetim ayarıyla genişletilir.
4. **Ekranda teknoloji adı yok** (model, sağlayıcı, altyapı adı). Ürün adı «Zeki AI»dır.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

# Teknoloji adı listesi, harf katlama ve sayı denetimi tek yerde (`semantic_bridge.zeki_text`); bu modül pazarlama
# metnine özgü kuralları (alıntı, kanıtsız iddia) ekler. Eski içe aktarma yolları (`guard.fold`, `guard.TECH_NAMES`,
# `guard.has_tech_name`, `guard.check`) çalışmaya devam eder.
from semantic_bridge import zeki_text as Z
from semantic_bridge.zeki_text import TECH_NAMES, fold, has_tech_name  # noqa: F401 — eski yol

#: Kanıtsız üstünlük kalıpları (küçük harf, Türkçe harf katlanmış biçimde aranır).
CLAIMS = (
    "en cok satan", "cok satan", "coksatan", "bir numara", "1 numara", "numara bir", "rekor", "en basarili kitap",
    "en populer", "herkesin okudugu", "tartismasiz", "essiz", "benzersiz", "piyasadaki tek", "alaninda tek",
)

_QUOTE = re.compile(r"«([^»]{3,})»|“([^”]{3,})”|\"([^\"]{3,})\"")
_NUM = re.compile(r"\d+(?:[.,]\d+)*")
_SENT = re.compile(r"(?<=[.!?…])\s+(?=\S)")


def _squash(s: str) -> str:
    """Alıntı karşılaştırması: harf katlama + noktalama/boşluk sadeleştirme."""
    return re.sub(r"[^\w]+", " ", fold(s)).strip()


def numbers_in(s: str) -> set[str]:
    """Eski yazım anahtarı («1.250», «1250», «12,5» → ayraçsız). Denetim artık değer üzerinden (`zeki_text`); bu işlev
    yalnız geriye dönük uyum için kalır."""
    return {re.sub(r"[.,]", "", n) for n in _NUM.findall(s or "")}


def check(text_: str, sources: Iterable[str], facts: Iterable[str] = (), extra_claims: Iterable[str] = ()) -> dict[str, Any]:
    """Metni cümle cümle denetler. Dönen: temiz metin, düşen cümleler (neden), sayaçlar."""
    corpus = [s for s in sources if s]
    corpus_sq = " \n ".join(_squash(s) for s in corpus)
    allowed = Z.Facts(list(corpus) + [f if isinstance(f, (int, float)) else str(f) for f in facts])
    claims = tuple(fold(c) for c in (*CLAIMS, *extra_claims) if str(c).strip())
    dropped: list[dict[str, str]] = []
    out_lines: list[str] = []
    for line in str(text_ or "").splitlines():
        if not line.strip():
            out_lines.append("")
            continue
        kept = []
        for sent in _SENT.split(line):
            why = _reason(sent, corpus_sq, allowed, claims)
            if why:
                dropped.append({"cumle": sent.strip()[:600], "neden": why})
            else:
                kept.append(sent)
        if kept:
            out_lines.append(" ".join(kept))
    clean = re.sub(r"\n{3,}", "\n\n", "\n".join(out_lines)).strip()
    counts: dict[str, int] = {}
    for d in dropped:
        counts[d["neden"]] = counts.get(d["neden"], 0) + 1
    return {"metin": clean, "dusen": dropped, "sayac": counts, "dusenSayisi": len(dropped)}


def _reason(sent: str, corpus_sq: str, allowed: "Z.Facts", claims: tuple[str, ...]) -> str | None:
    f = fold(sent)
    for name in TECH_NAMES:
        if re.search(r"(?<![a-z0-9])" + re.escape(name), f):
            return "teknoloji-adi"
    for c in claims:
        if re.search(r"(?<![a-z0-9])" + re.escape(c) + r"(?![a-z0-9])", f):
            return "kanitsiz-iddia"
    for m in _QUOTE.finditer(sent):
        q = _squash(next(g for g in m.groups() if g))
        if q and q not in corpus_sq:
            return "alinti-bulunamadi"
    if Z.unsupported(sent, allowed):
        return "kaynaksiz-rakam"
    return None
