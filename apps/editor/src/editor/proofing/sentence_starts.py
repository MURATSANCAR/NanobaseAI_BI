"""Cümle başı tekdüzeliği: art arda cümlelerin aynı sözcükle başlaması («Sonra … Sonra …», «Ama … Ama …»).

Hat:
1. Cümleler (deterministik): `_spelling_text.read_book` belirteç akışı, cümle başı işaretleri; bozuk span ve
   hikâye dışı sayfa dışarıda. Her cümlenin ilk sözcüğü Zemberek köküne iner (özel ad kendi yazımıyla).
2. Aday: sözcüğün kitapta cümle başlatma oranı p; art arda k cümle onunla başlıyorsa tesadüf olasılığı
   p^(k−1) < `EDITOR_WORD_ECHO_ALPHA` (0,05). Sık başlangıç («Ben») ancak uzun dizide, seyrek olan
   («Sonra») iki cümlede bile aday olur.
3. Yargı (model, kapalı soru, iki sırada ortalama): tekdüzelik mi (düzeltilmeli), bilinçli yineleme mi
   (vurgu, sıralama, şiir, tekerleme, çocuk kitabında ritim)? `p ≥ KEEP` → WARN.

«Hep dedi» gibi konuşma fiili tekdüzeliği ayrıca aranmaz: kitap genelinde `word_overuse`, yakında
`word_variety` yakalar. Ölçüm: ÖLÇÜM BEKLİYOR — docs/son-okuma/sentence_starts.md.
"""

from __future__ import annotations

import asyncio
import collections

from .. import book_type, db
from ..llm import Llm
from . import _continuity as C
from . import _doc_context as D
from . import _messages as M
from . import _spelling_judge as J
from . import _spelling_text as T
from . import _word_variety as W

NAME = "sentence_starts"
VERSION = "1"
LABEL = "Cümle başları"

ALPHA = C.setting("word_echo_alpha", 0.05)                  # EDITOR_WORD_ECHO_ALPHA
PARALLEL = C.setting("word_variety_parallel", 4)            # EDITOR_WORD_VARIETY_PARALLEL

MONOTONE = "Evet: tekdüze; okur fark eder, cümle başları çeşitlendirilmeli."
DELIBERATE = ("Hayır: bilinçli yineleme (vurgu, sıralama, şiir, tekerleme, çocuk kitabında ritim) ya da "
              "başka türlü kurulamaz.")


def _sentences(generation_id: str, lex) -> dict:
    bk = T.read_book(generation_id, lex)
    story = {p["page_no"] for p in C.story_pages(bk["pages"])}
    toks = bk["tokens"]
    dup = W.duplicate_supplements(bk["spans"])
    on_page, nth = collections.Counter(), []
    for t in toks:
        k = (t.page, W.norm_word(t.word))
        nth.append(on_page[k])
        on_page[k] += 1
    sents = []                     # (ilk belirteç sırası, son belirteç sırası)
    for i, t in enumerate(toks):
        if t.sent_start or i == 0:
            if sents:
                sents[-1][1] = i - 1
            sents.append([i, i])
    if sents:
        sents[-1][1] = len(toks) - 1
    starts = []
    for a, b in sents:
        t = toks[a]
        if t.garbled or t.fragment or t.page not in story or (t.page, t.span) in dup:
            continue
        if t.base[:1].islower():
            continue          # küçük harfle «başlayan» cümle konuşma çizgisinden sonraki devamdır («… dedim»)
        o = W.Occ(a, t.page, t.span, t.start, t.end, len(starts), W.lower_tr(t.base), t.word, "", "")
        o.extra = {"nth": nth[a], "total": on_page[(t.page, W.norm_word(t.word))],
                   "joined": t.joined_with is not None,
                   # cümle başında büyük harf karar vermez; kesmeli büyük harf özel addır («Ali'nin»)
                   "name": W.word_kind(t.base, t.apos, True) == "name", "end": (toks[b].page, toks[b].span)}
        starts.append(o)
    forms = {o.form for o in starts if not o.extra["name"]}
    cands = {f: W.candidates(lex.analyses(f)) for f in forms}
    chosen = W.choose_lemmas(cands, collections.Counter(o.form for o in starts))
    for o in starts:
        o.lemma = chosen.get(o.form, (o.form,))[0] if not o.extra["name"] else o.word
    return {"starts": starts, "span_keys": [(s["page"], s["idx"]) for s in bk["spans"]],
            "span_text": {(s["page"], s["idx"]): s["text"] for s in bk["spans"]}, "sentences": len(sents)}


def prompt(what: str, word: str, k: int, marked: str, x: str, y: str) -> str:
    return (f"Okuduğun metin {what}; redaksiyonunu yapan deneyimli bir editörsün. Aşağıdaki pasajda art arda "
            f"{k} cümle «{word}» ile başlıyor ([[ ]] içinde).\n\nPasaj: «{marked}»\n\n"
            f"Bu cümle başları tekdüze mi?\nA) {x}\nB) {y}\nYalnız A ya da B yaz.")


async def run(generation_id: str):
    from .word_variety import _boxes
    lex = T.lexicon()
    rd = await asyncio.to_thread(_sentences, generation_id, lex)
    starts: list[W.Occ] = rd["starts"]
    stats = collections.Counter({"sentences": rd["sentences"], "sentence_starts": len(starts)})
    runs = W.start_runs([o.lemma for o in starts], ALPHA)
    stats["candidates"] = len(runs)
    if not runs:
        return [], dict(stats)
    prof = await D.profile(generation_id)
    what = book_type.describe(prof)
    llm = Llm(D.llm_gid(generation_id))
    sem = asyncio.Semaphore(PARALLEL)

    async def judge(i, j, chance):
        run_ = starts[i:j]
        plain, marked = W.passage(rd["span_keys"], rd["span_text"], run_, run_[-1].extra["end"])
        async with sem:
            p, _ = await J._ab(llm, lambda x, y: prompt(what, run_[0].word, len(run_), marked, x, y),
                               MONOTONE, DELIBERATE, sorted({o.page for o in run_}))
        return run_, plain, marked, chance, p

    judged = await asyncio.gather(*(judge(*r) for r in runs))
    kept = [j for j in judged if j[-1] >= J.KEEP]
    stats["dropped_as_deliberate"] = len(judged) - len(kept)
    bv = await asyncio.to_thread(D.book_version, generation_id)
    boxes = await asyncio.to_thread(_boxes, bv, [o for k_ in kept for o in k_[0]]) if bv else {}
    findings = []
    for run_, plain, marked, chance, p in kept:
        here = run_[1].page
        findings.append(M.put(NAME, {
            "page": here, "severity": "WARN", "quote": plain, "bbox": boxes.get(run_[1].idx),
            "details": {"lemma": run_[0].lemma, "count": len(run_), "chance": round(chance, 4), "p_monotone": round(p, 3),
                        "passage_marked": marked, "pages": sorted({o.page for o in run_}),
                        "group": f"cümle başı · {run_[0].lemma}", "confidence": round(p, 3),
                        "marks": [boxes[o.idx] for o in run_ if o.page == here and o.idx in boxes]}}))
        stats["kept"] += 1
    findings.sort(key=lambda f: f["page"])
    return findings, dict(stats)
