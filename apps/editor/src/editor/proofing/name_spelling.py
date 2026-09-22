"""Ad yazımı tutarlılığı (the same name written the same way through the book).

A name is a capitalised form inside a sentence, a form written with a proper-noun
apostrophe anywhere in the book, or a word of a character's name in the ledger
(ed.character canonical_name/aliases, ed.character_mention surface_name). The check reports:
- a rare form one letter away from a frequent name ("Kamil" once, "Kâmil" elsewhere;
  "Irmak" / "İrmak"), two letters for long names; inflection is not a variant: a form that is
  a known name plus a case/possessive suffix ("Mert'in", "Merte") is the name (a missing
  apostrophe is the spelling check's finding);
- a name written in lowercase where the book capitalises it (and the lowercase form is not
  an ordinary word: "masal" is a word, "defne" as laurel too, so those are never flagged).

Deterministic candidates; book-director then answers two closed questions per candidate:
does the page image show this form (OCR text only), and is the variant a slip or the
author's intent (a character mishearing a name, a joke, a different person or place)?
Measured precision: docs/son-okuma/name_spelling.md.
"""

from __future__ import annotations

import asyncio
import collections

from .. import db
from ..llm import Llm
from . import _spelling_judge as J
from . import _spelling_text as T
from ._spelling_rules import FOREIGN, SUFFIX_START

NAME = "name_spelling"
VERSION = "1"
LABEL = "Ad yazımı tutarlılığı"

# a variant must be close: one edit for names of 4-7 letters, two from 8 letters on
# (measured: docs, "Uzaklık"); names under 4 letters are too dense to compare (Can/Cem/Ece)
MIN_LEN = 4
LONG = 8


def _known_names(generation_id: str) -> set[str]:
    rows = db.all_rows("SELECT canonical_name, aliases FROM character WHERE generation_id=%s", generation_id)
    rows += [{"canonical_name": r["surface_name"], "aliases": []} for r in db.all_rows(
        "SELECT DISTINCT surface_name FROM character_mention WHERE generation_id=%s AND surface_name IS NOT NULL",
        generation_id)]
    out = set()
    for r in rows:
        for n in [r["canonical_name"], *(r["aliases"] or [])]:
            for w in (n or "").replace("’", "'").split():
                w = w.split("'")[0].strip(".,;:!?\"“”()")
                if len(w) >= MIN_LEN and w[:1].isupper() and not w.isupper():
                    out.add(w)
    return out


def _is_inflection(a: str, b: str) -> bool:
    """b is a + a suffix (or the reverse), in lower case."""
    la, lb = T.lower_tr(a), T.lower_tr(b)
    if len(la) > len(lb):
        la, lb = lb, la
    return lb.startswith(la) and bool(SUFFIX_START.match(lb[len(la):]))


async def run(generation_id: str):
    lex = T.lexicon()
    bk = await asyncio.to_thread(T.read_book, generation_id, lex)
    bv = str(db.one("SELECT book_version_id FROM generation WHERE id=%s", generation_id)["book_version_id"])
    toks = [t for t in bk["tokens"] if not t.garbled and not t.fragment]
    span_of = {(s["page"], s["idx"]): s for s in bk["spans"]}
    ledger = await asyncio.to_thread(_known_names, generation_id)

    apostrophed = {t.base for t in toks if t.apos and t.base[:1].isupper() and not t.base.isupper()}
    mid = collections.Counter(t.base for t in toks if t.base[:1].isupper() and not t.base.isupper()
                              and not t.sent_start)
    names = {n for n in set(mid) | apostrophed | ledger
             if len(n) >= MIN_LEN and not FOREIGN.search(n) and (n in apostrophed or n in ledger or not lex.common(n))}

    # every occurrence of a name, with a suffix glued on without an apostrophe folded back
    occ = collections.defaultdict(list)
    by_len = sorted(names, key=len, reverse=True)
    for t in toks:
        b = t.base
        if not b[:1].isupper() or b.isupper() or len(b) < MIN_LEN or FOREIGN.search(b):
            continue
        if b not in names:
            host = next((n for n in by_len if b.startswith(n) and len(b) > len(n)
                         and SUFFIX_START.match(T.lower_tr(b[len(n):]))), None)
            if host:
                b = host
            elif t.sent_start and lex.common(b):
                continue
        occ[b].append(t)

    stats = collections.Counter()
    cands = []
    forms = sorted(occ, key=lambda f: -len(occ[f]))
    for i, rare in enumerate(forms):
        for major in forms:
            if major == rare or len(occ[major]) <= len(occ[rare]) or len(occ[major]) < 2:
                continue
            lr, lm = T.lower_tr(rare), T.lower_tr(major)
            d = T.edit_distance(lr, lm)
            limit = 2 if min(len(lr), len(lm)) >= LONG else 1
            if d == 0 and rare != major:
                d = 1  # "Irmak" / "İrmak": same letters, different capital
            if d == 0 or d > limit or _is_inflection(rare, major):
                continue
            if lex.common(rare) and rare not in names:
                stats["skip_common_word"] += 1
                continue
            for t in occ[rare]:
                cands.append({"t": t, "kind": "ad_varyantı", "rare": rare, "major": major,
                              "major_count": len(occ[major]), "rare_count": len(occ[rare])})
            stats["variant_pairs"] += 1
            break
    # lowercase use of a capitalised name
    caps = {T.lower_tr(n): n for n in occ if len(occ[n]) >= 2}
    for t in toks:
        if t.base[:1].islower() and T.lower_tr(t.base) in caps and not lex.common(t.base):
            n = caps[T.lower_tr(t.base)]
            cands.append({"t": t, "kind": "küçük_harf", "rare": t.base, "major": n,
                          "major_count": len(occ[n]), "rare_count": 1})
    stats["raw"] = len(cands)

    llm = Llm(generation_id)
    findings = []
    for c in cands:
        t = c["t"]
        span = span_of[(t.page, t.span)]
        sentence = T.context(span["text"], t.start, t.end, 160)
        det = {"kind": c["kind"], "form": c["rare"], "book_form": c["major"], "book_form_count": c["major_count"],
               "form_count": c["rare_count"], "source": t.src,
               "book_form_pages": sorted({x.page for x in occ[c["major"]]})}
        fixed_word = c["major"] + t.word[len(c["rare"]):] if t.word.startswith(c["rare"]) else c["major"]
        if t.src == "OCR":
            a = max(0, t.start - 34)
            b = min(len(span["text"]), t.end + 34)
            shown = " ".join(span["text"][a:b].split())
            alt = shown.replace(t.word, fixed_word, 1)
            v = await J.printed(llm, bv, t.page, shown, [alt])
            det["p_printed"] = v["p_printed"]
            if v["p_printed"] < J.KEEP:
                stats["dropped_not_printed"] += 1
                continue
        other = next((x for x in occ[c["major"]] if x.page != t.page), occ[c["major"]][0])
        other_sentence = T.context(span_of[(other.page, other.span)]["text"], other.start, other.end, 90)
        if c["kind"] == "ad_varyantı":
            q = (f"Kitapta bu ad {c['major_count']} kez «{c['major']}» diye yazılıyor (örnek, s.{other.page}: "
                 f"«{other_sentence}»). Bu cümlede ise «{t.word}» yazılmış. Aynı kişi/yerin adının "
                 "tutarsız yazımı mı (dizgi/yazım hatası), yoksa bilinçli mi (karakter adı yanlış "
                 "söylüyor ya da karıştırıyor, şaka, başka bir kişi ya da yer)?")
        else:
            q = (f"Kitapta «{c['major']}» özel ad olarak büyük harfle yazılıyor. Bu cümlede «{t.word}» küçük "
                 "harfle yazılmış. Özel adın küçük harfle yazılması bir yazım hatası mı?")
        v = await J.is_error(llm, t.page, sentence, q)
        det["p_error"] = v["p_error"]
        if v["p_error"] < J.KEEP:
            stats["dropped_as_intentional"] += 1
            continue
        msg = (f"«{t.word}»: kitapta bu ad {c['major_count']} kez «{c['major']}» diye yazılıyor."
               if c["kind"] == "ad_varyantı" else
               f"«{t.word}» küçük harfle yazılmış; kitapta özel ad olarak «{c['major']}».")
        findings.append({"page": t.page, "severity": "WARN", "quote": t.printed, "message": msg,
                         "suggestion": fixed_word if c["kind"] == "ad_varyantı" else
                         c["major"] + t.word[len(c["rare"]):], "details": det})
        stats["kept:" + c["kind"]] += 1
    findings.sort(key=lambda f: f["page"])
    return findings, dict(stats)
