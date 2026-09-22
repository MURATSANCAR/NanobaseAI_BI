"""Shared reading layer for the spelling checks (spelling, name_spelling).

Two things live here:
- `Lexicon`: is a Turkish word form valid? Two open analysers, either one accepting is
  enough: Zemberek's morphology through zeyrek (MIT; Zemberek lexicon Apache-2.0) and the
  hunspell tr_TR dictionary of tdd-ai (MPL-2.0, read with spylls, MIT). Turkish is
  agglutinative; a plain word list cannot say whether "ortalamamızda" exists, a morphological
  analyser can. Measured on six books (docs/son-okuma/spelling.md): each analyser alone
  rejects correct forms the other accepts (zeyrek: "herhâlde"-style circumflex forms are
  fine but "okurkenki" is not; hunspell: "sitemkâr", "herhâlde"), so a form is invalid only
  when BOTH reject it.
- `read_book`: the book's canonical text (source.read) as a token stream with positions,
  line-break hyphens joined (also across lines, spans and pages), sentence starts marked and
  garbled text-layer spans set aside.

No model calls, no writes.
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .. import source

# --- lexicon -------------------------------------------------------------------------

_LOWER = str.maketrans({"I": "ı", "İ": "i"})
_UPPER = str.maketrans({"ı": "I", "i": "İ"})
_CIRC = str.maketrans({"â": "a", "î": "i", "û": "u", "Â": "A", "Î": "İ", "Û": "U"})


def lower_tr(w: str) -> str:
    return w.translate(_LOWER).lower()


def upper_tr(w: str) -> str:
    return w.translate(_UPPER).upper()


def cap_tr(w: str) -> str:
    return upper_tr(w[:1]) + lower_tr(w[1:])


def _dict_path() -> str:
    for p in (os.environ.get("EDITOR_HUNSPELL_TR"), "/app/data/hunspell/tr_TR"):
        if p and Path(p + ".dic").exists():
            return p
    raise RuntimeError("hunspell tr_TR sözlüğü yok (EDITOR_HUNSPELL_TR=<yol>/tr_TR)")


class Lexicon:
    def __init__(self):
        import logging
        logging.getLogger("zeyrek").setLevel(logging.ERROR)
        import zeyrek
        from spylls.hunspell import Dictionary
        self.an = zeyrek.MorphAnalyzer()
        self.hs = Dictionary.from_files(_dict_path())
        self._z: dict[str, list] = {}
        self._h: dict[str, bool] = {}

    def analyses(self, w: str) -> list:
        w = lower_tr(w)
        if w not in self._z:
            try:
                self._z[w] = list(self.an._parse(w))
            except Exception:  # noqa: BLE001 - an analyser crash on one form is "no analysis"
                self._z[w] = []
        return self._z[w]

    def hun(self, w: str) -> bool:
        if w not in self._h:
            try:
                self._h[w] = bool(self.hs.lookup(w) or self.hs.lookup(lower_tr(w))
                                  or self.hs.lookup(cap_tr(w)))
            except Exception:  # noqa: BLE001
                self._h[w] = False
        return self._h[w]

    def valid(self, w: str) -> bool:
        if not w:
            return False
        if self.analyses(w) or self.hun(w):
            return True
        w2 = w.translate(_CIRC)
        return w2 != w and bool(self.analyses(w2) or self.hun(w2))

    def common(self, w: str) -> bool:
        """Valid as an ordinary (not proper-noun) word."""
        if any(a.dict_item.secondary_pos is None or a.dict_item.secondary_pos.value != "Prop"
               for a in self.analyses(w)):
            return True
        return self.hun(lower_tr(w))

    def proper(self, w: str) -> bool:
        """Known as a proper noun (lexicon), in any inflection."""
        return any(a.dict_item.secondary_pos is not None and a.dict_item.secondary_pos.value == "Prop"
                   for a in self.analyses(w))

    def stems(self, w: str) -> list[str]:
        return [a.stem for a in self.analyses(w) if getattr(a, "stem", None)]

    def suggest(self, w: str) -> list[str]:
        try:
            out = [s for s in self.hs.suggest(w)]
        except Exception:  # noqa: BLE001
            return []
        return [s for s in out if " " not in s and "-" not in s]


@lru_cache(maxsize=1)
def lexicon() -> Lexicon:
    return Lexicon()


def edit_distance(a: str, b: str) -> int:
    """Damerau (adjacent transposition) Levenshtein."""
    la, lb = len(a), len(b)
    d = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = i
    for j in range(lb + 1):
        d[0][j] = j
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            c = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + c)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[la][lb]


# --- reading -------------------------------------------------------------------------

APOS = "'’`"
HYPH = "-­‐‑"
# a word: letters, inner apostrophe (proper-noun suffix) or inner hyphen (compound / spelled
# out syllables); a trailing line-break hyphen is kept on the token so it can be joined
WORD = re.compile(rf"[^\W\d_]+(?:[{APOS}{HYPH}][^\W\d_]+)*[{HYPH}]?")
# not prose: web addresses, e-mail, hashtags, handles
NOT_PROSE = re.compile(r"(?:https?://|www\.)\S+|\S+@\S+|[#@]\w+|\b[\w.-]+\.(?:com|net|org|tr|edu|gov)\b\S*",
                       re.I)
SENT_END = re.compile(r"[.!?…:]['\"”’»)\]]*\s*$")
LIGATURE_GAP = re.compile(r"([ﬀ-ﬆ])\s+(?=\w)")


@dataclass
class Tok:
    page: int
    span: int              # span idx on the page (source.read)
    src: str               # TEXT_LAYER / OCR
    start: int             # offsets in the span text (after NFKC)
    end: int
    text: str              # as printed (hyphen-joined words keep both parts in `printed`)
    word: str = ""         # the word without a line-break hyphen, parts joined
    base: str = ""         # before the apostrophe
    suffix: str = ""       # after the apostrophe ('' when none)
    apos: str = ""         # the apostrophe character used
    sent_start: bool = False
    printed: str = ""      # the printed form, e.g. "söy-/ledi"
    joined_with: tuple | None = None  # (page, span, start, end) of the second part
    garbled: bool = False  # inside a span judged unreadable (see read_book)
    fragment: bool = False  # line-end or line-start piece we could not join
    extra: dict = field(default_factory=dict)


def _norm(t: str) -> str:
    t = LIGATURE_GAP.sub(r"\1", t)          # "reﬂ ekslerim": extraction gap after a ligature
    t = unicodedata.normalize("NFKC", t)
    return t


def spans_of(pages: list[dict]) -> list[dict]:
    """Spans to read, in page order. On a page with a text layer, OCR spans are the OCR
    supplements the layer did not contain (source.py keeps only those as spans)."""
    out = []
    for p in pages:
        for s in p["spans"]:
            out.append({"page": p["page_no"], "idx": s["idx"], "src": s["source"],
                        "text": _norm(s["text"]), "raw": s["text"],
                        "supplement": bool(s.get("reading_order"))})
    return out


def _mask(text: str) -> str:
    return NOT_PROSE.sub(lambda m: " " * len(m.group()), text)


def tokenize(span: dict) -> list[Tok]:
    text = _mask(span["text"])
    toks = []
    for m in WORD.finditer(text):
        s = m.group()
        t = Tok(span["page"], span["idx"], span["src"], m.start(), m.end(), s)
        before = text[:m.start()].rstrip()
        t.sent_start = (not before and span.get("_starts_sentence", True)) or bool(before and SENT_END.search(before))
        toks.append(t)
    return toks


def _split_apos(t: Tok) -> None:
    w = t.word
    m = re.match(rf"^(.*?)([{APOS}])(.*)$", w)
    if m and m.group(1) and m.group(3):
        t.base, t.apos, t.suffix = m.group(1), m.group(2), m.group(3)
    else:
        t.base, t.apos, t.suffix = w, "", ""


def read_book(generation_id: str, lex: Lexicon | None = None) -> dict:
    """Pages, spans and a token stream. Line-break hyphens are joined within a span, across
    spans and across pages ("söy-" at the end of page 95, "ledi" at the top of page 96):
    a dangling "xxx-" is joined with the nearest following lowercase span start (same page,
    then the next page) that makes a valid word; unmatched pieces are marked `fragment` and
    never reported (they are layout, not spelling)."""
    lex = lex or lexicon()
    pages = source.read(generation_id)
    spans = spans_of(pages)
    prev_end = ""
    for i, s in enumerate(spans):
        # a span starts a sentence when the previous span (same page) ended one; spans are often
        # single printed lines, so a lowercase start after an unfinished line is a continuation
        same = i > 0 and spans[i - 1]["page"] == s["page"]
        s["_starts_sentence"] = (not same) or bool(SENT_END.search(prev_end)) or not prev_end.strip()
        prev_end = s["text"]
        s["toks"] = tokenize(s)
        for t in s["toks"]:
            t.word = t.text.rstrip(HYPH)
            t.printed = t.text
    # join line-break hyphens
    for i, s in enumerate(spans):
        toks = s["toks"]
        # inside a span: "ARIYOR- SUN", "baba-\nsı"
        j = 0
        while j < len(toks) - 1:
            a, b = toks[j], toks[j + 1]
            gap = s["text"][a.end:b.start]
            if a.text[-1] in HYPH and gap.strip() == "" and b.text[:1].isalpha() and \
                    (b.text[:1].islower() or a.word.isupper()):
                joined = a.word + b.word
                if lex.valid(re.split(rf"[{APOS}]", joined)[0]) or not (lex.valid(a.word) and lex.valid(b.word)):
                    a.word = joined
                    a.printed = a.text + " " + b.text
                    a.joined_with = (b.page, b.span, b.start, b.end)
                    a.end = b.end
                    del toks[j + 1]
                    continue
            j += 1
        # a word broken at the end of a line/span: with a hyphen ("söy-" / "ledi"), or with the
        # hyphen lost by the layer ("oluşturabi" / "liyor", often across an illustration page).
        # The partner is the first lowercase span start on this page or the next page that
        # carries text, whose join is a word.
        last = toks[-1] if toks else None
        dangling = last is not None and (last.text[-1] in HYPH or (
            last.text[:1].isalpha() and not lex.valid(re.split(rf"[{APOS}]", last.word)[0])))
        if dangling:
            a = last
            partner = None
            text_pages = []
            for k in range(i + 1, len(spans)):
                o = spans[k]
                if o["page"] != a.page and o["page"] not in text_pages:
                    text_pages.append(o["page"])
                if len(text_pages) > 1:
                    break
                if o["toks"] and o["toks"][0].text[:1].islower() and not o["toks"][0].extra.get("taken"):
                    b = o["toks"][0]
                    joined = a.word + b.word
                    if lex.valid(re.split(rf"[{APOS}]", joined)[0]):
                        partner = (o, b)
                        break
            if partner:
                o, b = partner
                a.word = a.word + b.word
                a.printed = a.text + " / " + b.text
                a.joined_with = (b.page, b.span, b.start, b.end)
                b.extra["taken"] = True
                o["toks"] = o["toks"][1:]
            elif a.text[-1] in HYPH:
                a.fragment = True
    # letter-spaced words split by the reader or the layer ("KİTA P", "Hiç işim" is not this:
    # both parts must be non-words and the join a word): layout, not spelling
    for s in spans:
        toks = s["toks"]
        for a, b in zip(toks, toks[1:]):
            if s["text"][a.end:b.start] == " " and not lex.valid(a.word) and not lex.valid(b.word) \
                    and lex.valid(a.word + b.word):
                a.fragment = b.fragment = True
    # lowercase span starts that are not words and have no partner: pieces of a word broken
    # at a line end without a hyphen, or of a layer that lost the hyphen
    for s in spans:
        for t in s["toks"]:
            _split_apos(t)
        if s["toks"] and not s["_starts_sentence"]:
            t = s["toks"][0]
            if t.text[:1].islower() and not lex.valid(t.base):
                t.fragment = True
    # garbled spans (layout noise, not spelling):
    # - an unreliable layer interleaves artwork letters with the text or loses the spaces of
    #   a speech bubble ("kadarhızlıdüzyo ld ak oşa", "içinçokbasitbir"): a span with a word
    #   that is three or more words glued together, or where many lowercase forms are not
    #   words (GARBLE_MIN_BAD / GARBLE_RATIO);
    # - an OCR reading that looped ("okunamadı okunamadı okunamadı ..."): the same word three
    #   or more times in a row in an OCR span is the reader's loop, not the book.
    for s in spans:
        low = [t for t in s["toks"] if t.base[:1].islower() and len(t.base) > 0]
        bad = [t for t in low if not lex.valid(t.base) and not re.search(r"(.)\1\1", t.base)]
        s["bad_ratio"] = len(bad) / len(low) if low else 0.0
        glued = [t.base for t in bad if len(segment(lex, lower_tr(t.base), 3)) >= 3]
        words = [lower_tr(t.word) for t in s["toks"]]
        loop = s["src"] == "OCR" and any(words[k] == words[k + 1] == words[k + 2] for k in range(len(words) - 2))
        s["garbled"] = bool(glued) or loop or (len(bad) >= GARBLE_MIN_BAD and s["bad_ratio"] >= GARBLE_RATIO)
        s["garble_reason"] = ("yapışık sözcükler: " + ", ".join(glued[:3])) if glued else \
            ("OCR döngüsü" if loop else ("bozuk katman" if s["garbled"] else None))
        for t in s["toks"]:
            t.garbled = s["garbled"]
    return {"pages": pages, "spans": spans, "tokens": [t for s in spans for t in s["toks"]]}


def segment(lex: "Lexicon", w: str, min_part: int = 2) -> list[str]:
    """Split a form into the fewest valid words (each at least `min_part` letters); [] when
    impossible. "içinçokbasitbir" -> [için, çok, basit, bir]."""
    n = len(w)
    best: list[list[str] | None] = [None] * (n + 1)
    best[0] = []
    for i in range(1, n + 1):
        for j in range(max(0, i - 24), i - min_part + 1):
            if best[j] is not None and lex.valid(w[j:i]) and \
                    (best[i] is None or len(best[j]) + 1 < len(best[i])):
                best[i] = best[j] + [w[j:i]]
    return best[n] or []


# A span is garbled when at least GARBLE_MIN_BAD of its lowercase words are not words and
# they are at least GARBLE_RATIO of them (measured: docs/son-okuma/spelling.md, "Bozuk katman").
GARBLE_MIN_BAD = 3
GARBLE_RATIO = 0.25


def context(span_text: str, start: int, end: int, width: int = 160) -> str:
    a = max(0, start - width)
    b = min(len(span_text), end + width)
    return ("…" if a else "") + span_text[a:b].replace("\n", " ") + ("…" if b < len(span_text) else "")
