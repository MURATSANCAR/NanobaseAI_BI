"""Sık kullanılan sözcükler (yazar tikleri): kitap geneli, yayınevinin öbür kitaplarına göre.

Redaksiyonun «yakın tekrar»dan ayrı sorusu: yazar bir sözcüğü (çoğu zaman bir zarf ya da fiil:
«aslında», «sanki», «birden», «gülümsemek») kitap boyunca olağandan çok mu kullanıyor?

Hat:
1. Kök (deterministik): `word_variety._read` (Zemberek kök, özel ad ve hikâye dışı sayfa dışarıda).
2. Derlem: aynı editör kurulumunun okuduğu ÖBÜR kitapların kelime haritaları (her kitabın en yeni
   başarılı `word_variety` koşusunun `stats.map`'i; bu kitap hariç). Derlem kitaba özel değildir, veridir;
   en az `EDITOR_WORD_OVERUSE_MIN_BOOKS` kitap yoksa karşılaştırma yapılmaz (stats.reason).
3. Anahtar sözcük testi: log-likelihood G² ≥ 15,13 (p < 0,0001) ve kitaptaki oran derlemdekinden büyük.
   Yalnız zarf, sıfat, fiil: adlar çoğunlukla kitabın konusudur («insan», «dünya»), tik değildir.
4. Yargı (model, kapalı soru, iki sırada ortalama): yazarın dil alışkanlığı mı (azaltılmalı), yoksa
   konunun/türün gereği mi? `p ≥ KEEP` → WARN, kitap geneli (sayfa yok).

Ölçüm: ÖLÇÜM BEKLİYOR — docs/son-okuma/word_overuse.md.
"""

from __future__ import annotations

import asyncio
import collections

from .. import book_type, db
from ..llm import Llm
from . import _continuity as C
from . import _spelling_judge as J
from . import _spelling_text as T
from . import _word_variety as W

NAME = "word_overuse"
VERSION = "1"
LABEL = "Sık kullanılan sözcükler (yazar tikleri)"

# Karşılaştırma için en az bu kadar başka kitap (daha azıyla «olağan sıklık» bilinmez).
MIN_BOOKS = C.setting("word_overuse_min_books", 3)           # EDITOR_WORD_OVERUSE_MIN_BOOKS
CONTEXT_CHARS = C.setting("word_context_chars", 70)         # EDITOR_WORD_CONTEXT_CHARS
PARALLEL = C.setting("word_variety_parallel", 4)            # EDITOR_WORD_VARIETY_PARALLEL
# Tik adayı türler: zarf, sıfat, fiil. Ad çoğunlukla konudur.
TIC_POS = ("Adv", "Adj", "Verb")

HABIT = "Evet: yazarın dil alışkanlığı; okur fark eder, redaksiyonda azaltılmalı."
NATURAL = "Hayır: kitabın konusu ya da türü gereği, terim ya da bu kitapta doğal kullanım."


def _corpus(generation_id: str) -> tuple[dict[str, int], int, int]:
    """Öbür kitapların kök sayıları, sözcük toplamı, kitap sayısı (her kitabın en yeni başarılı koşusu)."""
    rows = db.all_rows(
        "SELECT DISTINCT ON (v.book_id) r.stats FROM proof_run r JOIN generation g ON g.id=r.generation_id"
        " JOIN book_version v ON v.id=g.book_version_id"
        " WHERE r.check_name='word_variety' AND r.status='SUCCEEDED' AND v.book_id <>"
        " (SELECT v2.book_id FROM generation g2 JOIN book_version v2 ON v2.id=g2.book_version_id WHERE g2.id=%s)"
        " ORDER BY v.book_id, r.started_at DESC", generation_id)
    counts, total = collections.Counter(), 0
    for r in rows:
        st = r["stats"] or {}
        total += int(st.get("word_tokens") or 0)
        for w in st.get("map") or []:
            counts[w["lemma"]] += int(w["count"])
    return dict(counts), total, len(rows)


def prompt(what: str, lemma: str, row: dict, books: int, examples: list[str], x: str, y: str) -> str:
    other = (f"yayınevinin öbür {books} kitabında 10.000 sözcükte {row['corpus_per10k']}" if row["corpus_count"]
             else f"yayınevinin öbür {books} kitabında hiç geçmiyor")
    return (f"Okuduğun metin {what}; redaksiyonunu yapan deneyimli bir editörsün. «{lemma}» sözcüğü bu kitapta {row['count']} kez "
            f"geçiyor (10.000 sözcükte {row['per10k']}); {other}. Kitaptan örnekler ([[ ]] içinde):\n"
            + "\n".join(f"- {e}" for e in examples)
            + f"\n\nBu sık kullanım yazarın bir dil alışkanlığı (tik) mı?\nA) {x}\nB) {y}\nYalnız A ya da B yaz.")


async def run(generation_id: str):
    from .word_variety import _read          # aynı okuma katmanı: kök, tür, bağlam
    lex = T.lexicon()
    rd = await asyncio.to_thread(_read, generation_id, lex)
    occs: list[W.Occ] = rd["occs"]
    stats = collections.Counter({k: v for k, v in rd["stats"].items()})
    corpus, n_corpus, books = await asyncio.to_thread(_corpus, generation_id)
    stats["corpus_books"], stats["corpus_words"], stats["book_words"] = books, n_corpus, len(occs)
    if books < MIN_BOOKS or not occs:
        return [], {**dict(stats), "reason": f"karşılaştırma için en az {MIN_BOOKS} başka kitap gerekir ({books} var)"}

    by = collections.defaultdict(list)
    for o in occs:
        by[o.lemma].append(o)
    tic = {lem: os_ for lem, os_ in by.items()
           if any(o.pos in TIC_POS for o in os_) and not any(o.pos in W.FUNCTION_POS for o in os_)}
    rows = W.overused({lem: len(v) for lem, v in tic.items()}, len(occs), corpus, n_corpus)
    stats["candidates"] = len(rows)

    prof = await book_type.profile(generation_id)
    what = book_type.describe(prof)          # «yetişkinler için kurgu bir kitap»
    span_text = rd["span_text"]
    llm = Llm(generation_id)
    sem = asyncio.Semaphore(PARALLEL)

    def examples(os_: list[W.Occ]) -> list[W.Occ]:
        # kitabın başından, ortasından, sonundan birer örnek
        idx = sorted({0, len(os_) // 2, len(os_) - 1})
        return [os_[i] for i in idx]

    async def judge(row):
        os_ = by[row["lemma"]]
        ex = [W.marked_context(span_text[(o.page, o.span)], o.start, o.end, CONTEXT_CHARS) for o in examples(os_)]
        async with sem:
            p, _ = await J._ab(llm, lambda x, y: prompt(what, row["lemma"], row, books, ex, x, y), HABIT, NATURAL,
                               sorted({o.page for o in examples(os_)}))
        return row, ex, p

    findings = []
    for row, ex, p in await asyncio.gather(*(judge(r) for r in rows)):
        if p < J.KEEP:
            stats["dropped_as_natural"] += 1
            continue
        os_ = by[row["lemma"]]
        other = (f"yayınevinin öbür {books} kitabında 10.000 sözcükte {row['corpus_per10k']}"
                 + (f" — {row['ratio']} kat" if row["ratio"] else "")
                 if row["corpus_count"] else f"yayınevinin öbür {books} kitabında hiç geçmiyor")
        findings.append({
            "page": None, "severity": "WARN", "quote": ex[0].replace("[[", "").replace("]]", ""),
            "message": f"«{row['lemma']}» kitapta {row['count']} kez geçiyor (10.000 sözcükte {row['per10k']}); {other}.",
            "details": {**row, "pages": sorted({o.page for o in os_}), "forms": dict(collections.Counter(o.form for o in os_)),
                        "examples": ex, "corpus_books": books, "p_habit": round(p, 3),
                        "group": "yazar tikleri", "confidence": round(p, 3)}})
        stats["kept"] += 1
    findings.sort(key=lambda f: -f["details"]["g2"])
    return findings, dict(stats)
