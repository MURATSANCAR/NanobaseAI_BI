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

#: Kanıtsız üstünlük kalıpları (küçük harf, Türkçe harf katlanmış biçimde aranır).
CLAIMS = (
    "en cok satan", "cok satan", "coksatan", "bir numara", "1 numara", "numara bir", "rekor", "en basarili kitap",
    "en populer", "herkesin okudugu", "tartismasiz", "essiz", "benzersiz", "piyasadaki tek", "alaninda tek",
)
#: Ekrana ve ekrana giden metne yazılmayan teknoloji/model/sağlayıcı adları.
TECH_NAMES = (
    "qwen", "vllm", "llama", "ollama", "openai", "chatgpt", "gpt-", "gpt4", "gpt 4", "gpt5", "claude", "anthropic", "gemini",
    "mistral", "timesfm", "temporal", "real-esrgan", "typst", "ghostscript", "hugging face", "huggingface", "transformer",
    "büyük dil modeli", "buyuk dil modeli", "dil modeli", "llm",
)

_FOLD = str.maketrans("İIıŞşĞğÜüÖöÇçÂâÎîÛû’‘`´", "iiissgguuooccaaiiuu''''")
_QUOTE = re.compile(r"«([^»]{3,})»|“([^”]{3,})”|\"([^\"]{3,})\"")
_NUM = re.compile(r"\d+(?:[.,]\d+)*")
_SENT = re.compile(r"(?<=[.!?…])\s+(?=\S)")


def fold(s: Any) -> str:
    return " ".join(str(s or "").translate(_FOLD).lower().split())


def _squash(s: str) -> str:
    """Alıntı karşılaştırması: harf katlama + noktalama/boşluk sadeleştirme."""
    return re.sub(r"[^\w]+", " ", fold(s)).strip()


def numbers_in(s: str) -> set[str]:
    """«1.250», «1250», «12,5» aynı sayı sayılır: ayırıcılar atılır."""
    return {re.sub(r"[.,]", "", n) for n in _NUM.findall(s or "")}


def check(text_: str, sources: Iterable[str], facts: Iterable[str] = (), extra_claims: Iterable[str] = ()) -> dict[str, Any]:
    """Metni cümle cümle denetler. Dönen: temiz metin, düşen cümleler (neden), sayaçlar."""
    corpus = [s for s in sources if s]
    corpus_sq = " \n ".join(_squash(s) for s in corpus)
    allowed = set()
    for s in list(corpus) + [str(f) for f in facts]:
        allowed |= numbers_in(s)
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


def _reason(sent: str, corpus_sq: str, allowed: set[str], claims: tuple[str, ...]) -> str | None:
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
    for n in numbers_in(sent):
        if n not in allowed:
            return "kaynaksiz-rakam"
    return None


def has_tech_name(s: str) -> bool:
    f = fold(s)
    return any(re.search(r"(?<![a-z0-9])" + re.escape(n), f) for n in TECH_NAMES)
