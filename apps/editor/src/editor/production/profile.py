"""Kitap profili: yaş aralığı, tür, resim ihtiyacı, okuma düzeyi.

Üç kaynak, ayrı ayrı kaydedilir ve karşılaştırılır:
1. Yayınevinin beyanı (künye «RAF: 6-10 YAŞ», CRM) — varsa karar budur; kitabın rafını yayınevi seçer.
2. Metin ölçümü: kelime, cümle uzunluğu, hece, Ateşman okunabilirlik puanı, konuşma oranı.
3. Ana modelin okuması (production_profile istemi): yaş, tür, resim ihtiyacı, gerekçeler; her gerekçenin
   alıntısı metinde birebir aranır, bulunmayan gerekçe düşer.
Beyan ile model 2 yıldan fazla ayrışırsa `disagreement` doldurulur; editöre gösterilir, karar değişmez.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from .manuscript import Manuscript

VOWELS = re.compile(r"[aeıioöuüâîûAEIİOÖUÜÂÎÛ]")
WORD = re.compile(r"[A-Za-zÇĞİÖŞÜÂÎÛçğıöşüâîû'’]+")
GENRES = ["RESIMLI_OYKU", "ILK_OKUMA", "COCUK_ROMANI", "GENCLIK_ROMANI", "YETISKIN_ROMANI",
          "OYKU_KITABI", "SIIR", "KURGU_DISI_COCUK", "KURGU_DISI"]
ILLUSTRATION = ["HER_SAYFA", "BOLUM_BASI", "YOK"]
MODEL_TEXT_CHARS = 60000          # uzun kitapta modele baş, orta ve son bölümlerden bu kadar gider


@dataclass
class Profile:
    age_min: int
    age_max: int
    age_source: str
    genre: str
    illustration: str
    tone: list[str]
    reading: dict
    declared: dict
    model: dict
    disagreement: str | None = None
    reasons: list[dict] = field(default_factory=list)
    illustration_source: str = "model okuması"

    def to_json(self) -> dict:
        return asdict(self)


def reading_stats(ms: Manuscript) -> dict:
    blocks = [b for _, _, b in ms.blocks()]
    text = " ".join(b.text for b in blocks)
    words = WORD.findall(text)
    sentences = [s for s in re.split(r"[.!?…]+", text) if WORD.search(s)]
    syll = sum(max(1, len(VOWELS.findall(w))) for w in words)
    W, S = len(words), max(1, len(sentences))
    wps, spw = W / S, syll / max(1, W)
    # Ateşman (1997): 198,825 − 40,175·(hece/kelime) − 2,610·(kelime/cümle); 90–100 çok kolay, 70–89 kolay
    atesman = 198.825 - 40.175 * spw - 2.610 * wps
    return {"words": W, "sentences": S, "words_per_sentence": round(wps, 1),
            "syllables_per_word": round(spw, 2), "atesman": round(atesman, 1),
            "dialogue_share": round(sum(b.kind == "dialogue" for b in blocks) / max(1, len(blocks)), 2),
            "chapters": len(ms.chapters)}


def declared_age(ms: Manuscript) -> tuple[int, int] | None:
    if ms.meta.get("age_min"):
        return int(ms.meta["age_min"]), int(ms.meta.get("age_max") or ms.meta["age_min"])
    m = re.search(r"(\d{1,2})\s*[-–]\s*(\d{1,2})", ms.meta.get("AGE_RANGE") or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def _model_text(ms: Manuscript) -> str:
    full = ms.text()
    if len(full) <= MODEL_TEXT_CHARS:
        return full
    n = len(ms.chapters)
    pick = sorted({0, n // 2, n - 1})
    part = MODEL_TEXT_CHARS // len(pick)
    return "\n\n[…]\n\n".join(
        ("## " + (ms.chapters[i].title or "") + "\n\n" + "\n\n".join(b.text for b in ms.chapters[i].blocks))[:part]
        for i in pick)


SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["age_min", "age_max", "genre", "illustration", "tone", "reasons"],
    "properties": {
        "age_min": {"type": "integer"}, "age_max": {"type": "integer"},
        "genre": {"type": "string", "enum": GENRES},
        "illustration": {"type": "string", "enum": ILLUSTRATION},
        "tone": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        "reasons": {"type": "array", "maxItems": 8, "items": {
            "type": "object", "additionalProperties": False, "required": ["claim", "quote"],
            "properties": {"claim": {"type": "string"}, "quote": {"type": "string"}}}},
    },
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("’", "'")).strip().casefold()


def illustration_decision(model: str, genre: str, illustrator: str | None) -> tuple[str, str]:
    """Resim kararı. Yayınevi kaydında çizeri olan kitap resimlidir: modelin «YOK»u geçersizdir (model Word
    taslağında resim göremediği için resimsiz sanıyordu; 2026-09-25, çizeri kayıtlı 8–11 yaş romanı).
    Resimle okunan türlerde her sayfa, ötekilerde bölüm başı."""
    if illustrator and model == "YOK":
        return ("HER_SAYFA" if genre in ("RESIMLI_OYKU", "ILK_OKUMA") else "BOLUM_BASI",
                f"yayınevi kaydı: çizer {illustrator}")
    if illustrator:
        return model, f"yayınevi kaydı (çizer {illustrator}) + model okuması"
    return model, "model okuması"


async def build(ms: Manuscript, llm) -> Profile:
    from ..prompts import render
    stats = reading_stats(ms)
    ref, prompt = render("production_profile", title=ms.title, text=_model_text(ms),
                         illustrator=ms.illustrator or "(yayınevi kaydında çizer yok)")
    out, _ = await llm.chat("book-director", [{"role": "user", "content": prompt}], prompt=ref,
                            schema=SCHEMA, max_tokens=3000, thinking=False)
    full = _norm(ms.text())
    reasons = [r for r in out["reasons"] if r["quote"].strip() and _norm(r["quote"]) in full]
    decl = declared_age(ms)
    if decl:
        age_min, age_max, source = decl[0], decl[1], "yayınevi beyanı (künye/CRM)"
    else:
        age_min, age_max, source = out["age_min"], out["age_max"], "model okuması"
    gap = max(abs(age_min - out["age_min"]), abs(age_max - out["age_max"]))
    disagreement = (f"Beyan {age_min}-{age_max}, model {out['age_min']}-{out['age_max']} yaş"
                    if decl and gap > 2 else None)
    illustration, ill_source = illustration_decision(out["illustration"], out["genre"], ms.illustrator)
    return Profile(age_min=age_min, age_max=age_max, age_source=source, genre=out["genre"],
                   illustration=illustration, illustration_source=ill_source, tone=out["tone"], reading=stats,
                   declared={"age": decl, "genre": ms.meta.get("GENRE")},
                   model={k: out[k] for k in ("age_min", "age_max", "genre", "illustration")},
                   disagreement=disagreement, reasons=reasons)
