"""Deterministic Turkish text measures for the age-fit check (no model, no database).

Everything here is a pure function of a string, so the same code measures an analysed
book (page spans) and a calibration corpus (a PDF's text layer).

- Syllables: Turkish writes one vowel per syllable, so the vowel count IS the syllable
  count (exact for native words; the rare loan with two adjacent vowels, "saat", is
  written with two syllables anyway). A vowel-less token (an abbreviation, "TV") counts 1.
- Words: letter runs, an apostrophe suffix kept with its stem ("Ali'nin" = one word),
  digits dropped (a number is read, but no formula counts it).
- Sentences: split after . ! ? … (a run of them is one end), after a dialogue line and at
  a paragraph end (a heading or a line without a full stop still ends there).
"""
from __future__ import annotations

import math
import re

VOWELS = set("aeıioöuüâîûAEIİOÖUÜÂÎÛ")
_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?", re.U)
_END = re.compile(r"(?<=[.!?…])[\"”’»)]*\s+|(?<=[.!?…][\"”’»)])\s*|(?<=[a-zçğıöşü][.!?])(?=[A-ZÇĞİÖŞÜ])")
# a sentence whose words were broken at a line end and never rejoined ("ne- sonra"): the
# reading order around a drawing is uncertain, so its length is not the author's sentence
BROKEN = re.compile(r"[^\W\d_]-\s+[^\W\d_]")
# letters glued to digits ("106yılla", "önce4"). Case changes inside a word are NOT used:
# stylised story text does that on purpose ("macerAHAHAHA", "YaPrAk BaNkAsI").
_GLUE = re.compile(r"[^\W\d_]\d|\d[^\W\d_]")
TOC = re.compile(r"\.{4,}\s*\d")
_DASH = re.compile(r"^\s*[-–—]\s*")
_QUOTED = re.compile(r"[“\"«]([^”\"»]{1,600})[”\"»]")

# Where a declared band is printed: "RAF: 6-10 YAŞ", "6 - 10 Yaş", "8+ yaş", "9-12 yaş için".
BAND = re.compile(r"(?<!\d)(\d{1,2})\s*(?:[-–—]|ile)\s*(\d{1,2})\s*ya[şs]", re.I)
BAND_PLUS = re.compile(r"(?<!\d)(\d{1,2})\s*\+\s*ya[şs]", re.I)

# Front/back matter that is not text the child reads as the story: imprint, author bio.
IMPRINT = re.compile(r"\bISBN\b|Sertifika\s*No|Yayın\s+Yönetmeni|Kültür\s+Bakanlığı|©|"
                     r"Eserin\s+her\s+hakkı|İzinsiz\s+yayımlanamaz|Baskı\s+ve\s+Cilt", re.I)
BIO = re.compile(r"(?:\b(?:1[89]\d\d|20[0-3]\d)\b.{0,80}\b(?:doğdu|doğan|dünyaya\s+gel\w*)\b)|"
                 r"(?:\b(?:doğdu|doğan|dünyaya\s+gel\w*)\b.{0,200}\b(?:mezun|üniversite|fakülte|bölüm)\w*)", re.I | re.S)
IMPRINT_LINE = re.compile(r"\bTel\s*:|@\w|www\.|\.com\b|Yayın\s+No|\bRaf\b", re.I)


def syllables(word: str) -> int:
    return max(1, sum(ch in VOWELS for ch in word))


_MARKER = re.compile(r"\[[^\]\n]{1,40}\]")      # a reader's own marker: "[okunamadı]"


def words(text: str) -> list[str]:
    return _WORD.findall(_MARKER.sub(" ", text))


# Turkish words of one or two letters (and common interjections). Anything else that short
# is a fragment of a word: a text layer that broke words apart ("Çocu kla r, bur a").
SHORT_WORDS = set("o a e ey ah oh of ay ha he hı hu bu şu ve de da ki mi mı mu mü ne on iş at su ya "
                  "al en iz ok öz üç ön ad ağ ak an ar as az el er es ev ez il in it iç ol öl ot oy "
                  "öd ör öp ul un ut uç üs üz yo ye ma na pa ba".split())


def fragment_share(text: str) -> float:
    ws = words(text)
    return sum(len(w) <= 2 and w.casefold() not in SHORT_WORDS for w in ws) / len(ws) if ws else 0.0


def garbled(paragraph: str) -> bool:
    """A paragraph whose words are broken apart: >= 25% of its (>= 5) tokens are fragments.
    Measured on the six analysed books: 19 of 4,201 paragraphs pass 0.25 — 13 scrambled
    text-layer speech bubbles, 2 contact/price lines, 4 deliberately syllabified or
    letter-coded lines ("tır-tıl gö-rün-ce") whose word count would be wrong anyway. Just
    below, at 0.2, ordinary sentences start to fall in ("Sadece ... et veriliyormuş")."""
    ws = words(paragraph)
    # or two or more letter-digit joins ("106yılla", "önce4")
    return len(ws) >= 5 and (fragment_share(paragraph) >= 0.25 or len(_GLUE.findall(paragraph)) >= 2)


def one_letter_share(text: str) -> float:
    """Share of one-letter tokens. Turkish has almost none ("o", "a"); a text layer that
    spaces letters out or breaks words into fragments ("Çocu kla r") is full of them."""
    ws = words(text)
    return sum(len(w) == 1 for w in ws) / len(ws) if ws else 0.0


def sentences(paragraph: str) -> list[str]:
    out = []
    for line in re.split(r"\n+", paragraph):
        line = line.strip()
        if not line:
            continue
        out.extend(s for s in _END.split(line) if s and words(s))
    return out


_CLOSED = re.compile(r"[.!?…:;][\"”’»)]*\s*$")


def stream(paragraphs: list[str]) -> list[str]:
    """Paragraphs as the reader meets them: a layout block that stops mid-sentence (a
    picture-book line broken around a drawing) runs on into the next one; a dialogue
    line and a closed sentence stand alone."""
    out: list[str] = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if out and not _CLOSED.search(out[-1]) and not _DASH.match(p) and not _DASH.match(out[-1]):
            out[-1] = out[-1] + " " + p
        else:
            out.append(p)
    return out


def is_heading(paragraph: str) -> bool:
    """A chapter title: short, no sentence end, all capitals ("İLK DENEY")."""
    w = words(paragraph)
    letters = [c for c in paragraph if c.isalpha()]
    return (0 < len(w) <= 6 and not re.search(r"[.!?…:]\s*$", paragraph.strip())
            and bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.8)


def is_matter(paragraph: str) -> str | None:
    """Why a paragraph is not story text (imprint, author/illustrator bio, broken text layer)."""
    if IMPRINT.search(paragraph) or IMPRINT_LINE.search(paragraph):
        return "imprint"
    if BIO.search(paragraph):
        return "bio"
    if garbled(paragraph):
        return "garbled"
    if TOC.search(paragraph):
        return "contents"
    return None


def declared_band(text: str) -> tuple[int, int] | None:
    """The first plausible printed age band in `text` (low <= high, both within 0..18)."""
    for m in BAND.finditer(text):
        lo, hi = int(m.group(1)), int(m.group(2))
        if 0 <= lo < hi <= 18:
            return lo, hi
    m = BAND_PLUS.search(text)
    if m and int(m.group(1)) <= 18:
        return int(m.group(1)), 18
    return None


def dialogue_words(paragraph: str) -> int:
    """Words spoken by a character: a dash-led line, or text between quotation marks."""
    n = 0
    for line in re.split(r"\n+", paragraph):
        if _DASH.match(line):
            n += len(words(line))
        else:
            n += sum(len(words(q)) for q in _QUOTED.findall(line))
    return n


def measure(paragraphs: list[str], zipf=None, rare_below: float = 3.0) -> dict:
    """Counts and the Turkish formulas over a list of paragraphs.

    `zipf(word) -> float` (wordfreq.zipf_frequency for 'tr') makes the rare-word share;
    a capitalised word is left out of it (a name is not vocabulary)."""
    n_sent = n_words = n_syl = long5 = h3 = h4 = h5 = h6 = dia = rare = lower = 0
    sent_lens: list[int] = []
    for p in stream(paragraphs):
        dia += dialogue_words(p)
        for s in sentences(p):
            ws = words(s)
            if not ws:
                continue
            n_sent += 1
            sent_lens.append(len(ws))
            for w in ws:
                k = syllables(w)
                n_words += 1
                n_syl += k
                h3 += k == 3
                h4 += k == 4
                h5 += k == 5
                h6 += k >= 6
                long5 += k >= 5
                if zipf is not None and w[:1].islower():
                    lower += 1
                    if zipf(w.lower().replace("’", "'")) < rare_below:
                        rare += 1
    if not n_words or not n_sent:
        return {"sentences": n_sent, "words": n_words}
    asl, asw = n_words / n_sent, n_syl / n_words
    # Bezirci–Yılmaz (2010): YOD = sqrt(OKS * ((H3*0.84)+(H4*1.5)+(H5*3.5)+(H6*26.25))),
    # OKS = words per sentence, Hn = n-syllable words PER SENTENCE; YOD ~ school grade.
    per = n_sent
    yod = math.sqrt(asl * (h3 / per * 0.84 + h4 / per * 1.5 + h5 / per * 3.5 + h6 / per * 26.25))
    return {
        "sentences": n_sent, "words": n_words, "syllables": n_syl,
        "asl": round(asl, 2), "asw": round(asw, 3),
        "max_sentence": max(sent_lens),
        "p90_sentence": sorted(sent_lens)[int(0.9 * (len(sent_lens) - 1))],
        # Ateşman (1997): 198.825 − 40.175·(syllables/word) − 2.610·(words/sentence)
        "atesman": round(198.825 - 40.175 * asw - 2.610 * asl, 1),
        # Çetinkaya–Uzun (2010): 118.823 − 25.987·(syllables/word) − 0.971·(words/sentence)
        "cetinkaya": round(118.823 - 25.987 * asw - 0.971 * asl, 1),
        "yod": round(yod, 2),
        "long_word_share": round(long5 / n_words, 4),
        "dialogue_share": round(min(1.0, dia / n_words), 3),
        "one_letter_share": round(one_letter_share(" ".join(paragraphs)), 4),
        **({"rare_share": round(rare / lower, 4) if lower else 0.0} if zipf is not None else {}),
    }
