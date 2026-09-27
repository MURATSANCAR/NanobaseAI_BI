"""Kalıp ifade tekrarı: aynı söz öbeğinin kitap boyunca yinelenmesi («kalbi küt küt attı», «gözleri parladı»).

Yakın tekrardan (`word_variety`) farkı: mesafe aranmaz; öbek kitabın neresinde olursa olsun yinelenirse
okur kalıbı fark eder.

Hat:
1. Kök dizisi (deterministik): `word_variety._read` (Zemberek kök; özel ad, bozuk span, hikâye dışı sayfa
   dışarıda — bunlar öbeği koparır). «kalbi küt küt attı» ile «kalbim küt küt atıyordu» aynı öbektir.
2. Aday (`_word_variety.repeated_phrases`): tek cümlede, bitişik, en az 3 sözcük ve en az 2 içerik
   sözcüğü, kitapta en az 2 geçiş; yalnız en uzun hâl; öbekte en az bir fiil (fiilsiz ad öbeği terimdir).
3. Yargı (model, kapalı soru, iki sırada ortalama): göze batan kalıp anlatım mı (çeşitlendirilmeli), yoksa
   deyim, ad, terim, nakarat ya da bilinçli yineleme mi? `p ≥ KEEP` → WARN.

Ölçüm: ÖLÇÜM BEKLİYOR — docs/son-okuma/phrase_repeats.md.
"""

from __future__ import annotations

import asyncio
import collections

from .. import book_type, db
from ..llm import Llm
from . import _continuity as C
from . import _messages as M
from . import _spelling_judge as J
from . import _spelling_text as T
from . import _word_variety as W

NAME = "phrase_repeats"
VERSION = "1"
LABEL = "Tekrarlanan söz öbeği"

CONTEXT_CHARS = C.setting("word_context_chars", 70)         # EDITOR_WORD_CONTEXT_CHARS
PARALLEL = C.setting("word_variety_parallel", 4)            # EDITOR_WORD_VARIETY_PARALLEL

CLICHE = "Evet: kalıp anlatım; tekrarı okurun gözüne batar, çeşitlendirilmeli."
FINE = "Hayır: deyim, ad, terim, nakarat, bilinçli yineleme ya da başka türlü söylenemez."


def prompt(what: str, phrase: str, count: int, examples: list[str], x: str, y: str) -> str:
    return (f"Okuduğun metin {what}; redaksiyonunu yapan deneyimli bir editörsün. «{phrase}» söz öbeği (ekleri "
            f"değişerek) kitapta {count} kez geçiyor. Örnekler ([[ ]] içinde):\n"
            + "\n".join(f"- {e}" for e in examples)
            + f"\n\nBu yineleme göze batan bir kalıp anlatım mı?\nA) {x}\nB) {y}\nYalnız A ya da B yaz.")


def _surface(occs: list[W.Occ], span_text: dict, i: int, n: int) -> tuple[str, str]:
    """Öbeğin basıldığı hâli ve [[ ]] işaretli bağlamı."""
    a, b = occs[i], occs[i + n - 1]
    if (a.page, a.span) == (b.page, b.span):
        txt = span_text[(a.page, a.span)]
        return " ".join(txt[a.start:b.end].split()), W.marked_context(txt, a.start, b.end, CONTEXT_CHARS)
    words = " ".join(o.word for o in occs[i:i + n])
    return words, "[[" + words + "]]"


async def run(generation_id: str):
    from .word_variety import _boxes, _read
    lex = T.lexicon()
    rd = await asyncio.to_thread(_read, generation_id, lex)
    occs: list[W.Occ] = rd["occs"]
    stats = collections.Counter()
    seq = [(o.idx, o.sent, o.lemma, o.pos in W.CONTENT_POS) for o in occs]
    # kalıp anlatım bir eylem ya da betimleme kalıbıdır («gözler önüne seriyor», «kalbi küt küt attı»);
    # fiilsiz ad öbeği terimdir («sosyal medya», «yapay zekâ»), tekrarı redaksiyon konusu değildir
    all_found = W.repeated_phrases(seq)
    found = [(n, pos) for n, pos in all_found if any(occs[pos[0] + k].pos == "Verb" for k in range(n))]
    stats["skip_no_verb"] = len(all_found) - len(found)
    stats["candidates"] = len(found)
    if not found:
        return [], dict(stats)
    prof = await book_type.profile(generation_id)
    what = book_type.describe(prof)
    llm = Llm(generation_id)
    sem = asyncio.Semaphore(PARALLEL)
    span_text = rd["span_text"]

    async def judge(n, pos):
        shown = [_surface(occs, span_text, i, n) for i in pos]
        ex = [m for _, m in shown[:3]]
        async with sem:
            p, _ = await J._ab(llm, lambda x, y: prompt(what, shown[0][0], len(pos), ex, x, y), CLICHE, FINE,
                               sorted({occs[i].page for i in pos[:3]}))
        return n, pos, shown, p

    judged = await asyncio.gather(*(judge(n, pos) for n, pos in found))
    kept = [j for j in judged if j[-1] >= J.KEEP]
    stats["dropped_as_fine"] = len(judged) - len(kept)
    bv = str(db.one("SELECT book_version_id FROM generation WHERE id=%s", generation_id)["book_version_id"])
    second = [occs[pos[1] + k] for n, pos, _, _ in kept for k in range(n)]
    boxes = await asyncio.to_thread(_boxes, bv, second)
    findings = []
    for n, pos, shown, p in kept:
        here = occs[pos[1]].page
        pages = [occs[i].page for i in pos]
        marks = [boxes[occs[pos[1] + k].idx] for k in range(n) if occs[pos[1] + k].idx in boxes]
        findings.append(M.put(NAME, {
            "page": here, "severity": "WARN", "quote": shown[1][0], "bbox": marks[0] if marks else None,
            "details": {"phrase": [occs[pos[0] + k].lemma for k in range(n)], "count": len(pos), "pages": pages,
                        "occurrences": [{"page": occs[i].page, "text": t, "context": m} for i, (t, m) in zip(pos, shown)],
                        "p_cliche": round(p, 3), "group": "kalıp · " + " ".join(occs[pos[0] + k].lemma for k in range(n)),
                        "confidence": round(p, 3), "marks": marks}}))
        stats["kept"] += 1
    findings.sort(key=lambda f: f["page"])
    return findings, dict(stats)
