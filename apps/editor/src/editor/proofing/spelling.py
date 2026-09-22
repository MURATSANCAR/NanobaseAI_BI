"""Yazım ve noktalama (spelling and punctuation at final read).

What it reports (each a candidate for the editor, never a correction applied):
- word forms neither Turkish analyser knows (zeyrek/Zemberek morphology, hunspell tr_TR),
  with a suggestion from the dictionaries or from an attached particle ("geliyormu",
  "diyorki") or two glued words;
- a doubled syllable that turns a noun into a verb form ("ortalamamamız");
- doubled words (function words inside a line; any word across a line break);
- the vowel harmony of the separately written question particle and of "da";
- the apostrophe with proper nouns (missing, superfluous, wrong suffix consonant/vowel);
- punctuation spacing, doubled marks, four-dot ellipsis, lowercase after a full stop;
- the book's house style: one apostrophe, quote, ellipsis and dialogue-dash form.

How it avoids false alarms (measured on six books, docs/son-okuma/spelling.md):
- the children's-book language filters: stretched sounds, laughter, stylised case, the
  book's own vocabulary (a form printed on 2+ pages), names (capitalised inside a sentence);
- layout noise is set aside: garbled text-layer spans, OCR loops, line-break fragments;
- spacing is decided on the printed glyph positions, not on the text layer;
- a word-level candidate goes to book-director twice: first "what does the page image
  show" (removes OCR/layer misreadings), then "slip or choice" with the sentence. Both are
  closed two-way choices in both orders; the rules and dictionaries propose, the model only
  confirms or rejects.

Measured precision: see docs/son-okuma/spelling.md ("Ölçüm").
"""

from __future__ import annotations

import asyncio
import collections

from .. import db
from ..llm import Llm
from . import _spelling_judge as J
from . import _spelling_rules as R
from . import _spelling_text as T
from ._spelling_geometry import confirms, printed_gap

NAME = "spelling"
VERSION = "1"
LABEL = "Yazım ve noktalama"

MESSAGES = {
    "bilinmeyen_kelime": "«{word}» sözlüklerde yok; yazım hatası olabilir.",
    "tekrarlanan_hece": "«{word}» sözcüğünde bir hece iki kez yazılmış olabilir.",
    "tekrarlanan_kelime": "«{word}» art arda iki kez yazılmış.",
    "ek_uyumu": "Ek, sözcüğün ses uyumuna uymuyor ({rule}).",
    "kesme_eksik": "Özel ada gelen ek kesme işaretiyle ayrılmalı.",
    "gereksiz_kesme": "Cins isimden sonra kesme işareti kullanılmaz.",
    "büyük_harf": "Cümle büyük harfle başlamalı.",
    "tutarlılık": "Kitapta çoğunlukla «{book_majority}» kullanılmış; burada «{used}» var ({style}).",
}


def _message(c: dict) -> str:
    d = c["details"]
    if "rule" in d and c["kind"] not in MESSAGES:
        return d["rule"]
    tmpl = MESSAGES.get(c["kind"], d.get("rule", c["kind"]))
    try:
        return tmpl.format(**{"word": d.get("word", c["quote"]), **d})
    except (KeyError, IndexError):
        return tmpl


def _alt_phrases(span_text: str, c: dict) -> tuple[str, list[str]]:
    """(phrase as our text has it, the same phrase with each proposed correction) for the
    image check."""
    start, end = c["start"], c["end"]
    a = max(0, start - 34)
    b = min(len(span_text), end + 34)
    while a > 0 and not span_text[a - 1].isspace():
        a -= 1
    while b < len(span_text) and not span_text[b].isspace():
        b += 1
    shown = " ".join(span_text[a:b].split())
    target = c["details"].get("word") or span_text[start:end]
    k = span_text.find(target, max(0, start - 1))
    sugg = c["details"].get("suggestions") or ([c["suggestion"]] if c.get("suggestion") else [])
    if k < 0 or k >= b or not sugg:
        return shown, []
    return shown, [" ".join((span_text[a:k] + x + span_text[k + len(target):b]).split()) for x in sugg]


def _question(c: dict) -> str:
    d = c["details"]
    if c["kind"] == "bilinmeyen_kelime":
        s = d.get("suggestions") or []
        return (f"«{d['word']}» sözcüğü Türkçe sözlüklerde yok."
                + (f" Olası doğru yazım: «{s[0]}»." if s else "")
                + " Bu sözcük bir yazım hatası mı?")
    if c["kind"] == "tekrarlanan_hece":
        return f"«{d['word']}» yerine «{c['suggestion']}» mı yazılmalıydı (bir hece fazladan mı yazılmış)?"
    if c["kind"] == "tekrarlanan_kelime":
        return f"«{d['word']}» bir satırın sonunda ve sonraki satırın başında iki kez yazılmış. Bu bir dizgi hatası mı?"
    return f"«{c['quote']}» ifadesi bir yazım hatası mı?"


async def run(generation_id: str):
    lex = T.lexicon()
    bk = await asyncio.to_thread(T.read_book, generation_id, lex)
    bv = str(db.one("SELECT book_version_id FROM generation WHERE id=%s", generation_id)["book_version_id"])
    toks, spans = bk["tokens"], bk["spans"]
    span_of = {(s["page"], s["idx"]): s for s in spans}

    vocab = collections.defaultdict(set)
    capital_mid, names = set(), collections.Counter()
    for t in toks:
        lw = T.lower_tr(t.base)
        vocab[lw].add(t.page)
        if t.base[:1].isupper() and not t.base.isupper() and not t.sent_start:
            capital_mid.add(lw)
        if t.apos and t.base[:1].isupper() and not t.base.isupper() and not t.garbled:
            names[lw] += 1

    stats = collections.Counter()
    cands = []
    cands += R.unknown_words(toks, lex, vocab, capital_mid, stats)
    cands += R.doubled_syllables(toks, lex, vocab)
    cands += R.doubled_words(spans)
    cands += R.particle_harmony(spans, lex)
    cands += R.apostrophes(toks, lex, dict(names))
    cands += R.punctuation(spans)
    cands += R.capitals(spans)
    cands += R.house_style(spans)
    for c in cands:
        stats["raw:" + c["kind"]] += 1
    stats["garbled_spans"] = sum(1 for s in spans if s["garbled"])
    stats["fragments"] = sum(1 for t in toks if t.fragment)

    llm = Llm(generation_id)
    findings = []
    for c in cands:
        span = span_of[(c["page"], c["span"])]
        det = dict(c["details"])
        det.update({"kind": c["kind"], "source": c["src"]})
        # 1. spacing: what the printed glyphs show
        geo = c.get("geometry")
        if geo:
            res = await asyncio.to_thread(printed_gap, bv, c["page"], geo["left"], geo["mark"], geo["right"],
                                          geo["mode"])
            ok = confirms(res, geo["mode"])
            det["printed_gap"] = res
            if ok is False:
                stats["dropped_by_glyph_gap"] += 1
                continue
            if ok is None:
                stats["unmeasured_gap"] += 1
                continue  # not locatable in the glyphs: the layer text is not what is printed
        # 2. readings that may not be the print: OCR text, or a word-level guess
        if c["needs_model"] or (c["src"] == "OCR" and c["kind"] not in ("tutarlılık",)):
            shown, alts = _alt_phrases(span["text"], c)
            v = await J.printed(llm, bv, c["page"], shown, alts)
            det["p_printed"] = v["p_printed"]
            if v["p_printed"] < J.KEEP:
                stats["dropped_not_printed"] += 1
                continue
        if c["needs_model"]:
            sentence = T.context(span["text"], c["start"], c["end"], 160)
            v = await J.is_error(llm, c["page"], sentence, _question(c))
            det["p_error"] = v["p_error"]
            if v["p_error"] < J.KEEP:
                stats["dropped_as_intentional"] += 1
                continue
        findings.append({"page": c["page"], "severity": "WARN", "quote": c["quote"],
                         "message": _message(c), "suggestion": c.get("suggestion"), "details": det})
        stats["kept:" + c["kind"]] += 1
    findings.sort(key=lambda f: (f["page"] or 0, f["details"]["kind"]))
    return findings, dict(stats)
