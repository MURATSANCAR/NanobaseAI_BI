"""Satır sonu heceleme — line-end word breaks checked against TDK syllabification.

Works on the PDF's digital layer geometry (what is really at the end of each printed line),
never on re-flowed text. For every line that ends in a hyphen glyph attached to a letter, the
continuation is found geometrically (the next line of the same text frame, or the first line
of the next page), the word is rebuilt and the break is compared with the deterministic TDK
syllable boundaries (_hyphenation_tr).

Findings
  ERROR  break not at a syllable boundary (e.g. "kütü-phane")
  WARN   a single letter left at the line end or start ("a-", "-a")
  WARN   hyphen after an apostrophe ("Ankara'-"): TDK keeps only the apostrophe
  WARN   a hyphenated word continues after the reader turns the leaf (odd page -> next page)
  WARN   the hyphen glyph is an en/em dash or minus ("kita–" / "bı—")
  WARN   a hyphenation hyphen left inside a line after re-flow ("kitap- ları")
  INFO   a proper noun or its apostrophe suffix is broken (TDK allows it; house styles avoid it)
  INFO   a hyphenated word continues on the facing page (same spread)
  INFO   more than three hyphenated line ends in a row ("merdiven")

Pages whose text layer is unreliable (page.layer_health.layer_unreliable) are skipped:
the glyph codes there are not the printed letters. Precision measured on six books:
see docs/son-okuma/hyphenation.md.
"""

from __future__ import annotations

import re

from .. import db
from . import _hyphenation_tr as tr
from ._layout_lines import Line, book, norm_bbox, page_lines, unreliable

NAME = "hyphenation"
VERSION = "1"
LABEL = "Satır sonu heceleme"

HYPHENS = "-\u00ad\u2010\u2011"   # hyphen-minus, soft hyphen (InDesign exports it), hyphen, nb-hyphen
LOOKALIKE = "\u2012\u2013\u2014\u2212"   # figure dash, en dash, em dash, minus
APOS = "'’‘`´"
LADDER = 3   # more than this many consecutive hyphenated line ends (InDesign default limit, Bringhurst)

_TAIL = re.compile(r"(\S*?)([" + HYPHENS + LOOKALIKE + r"])$")
_LEAD = re.compile(r"^([^\W\d_]+)(?:([" + APOS + r"])([^\W\d_]*))?")
_PUA = re.compile("[\ue000-\uf8ff\U000f0000-\U0010ffff]")
_STRAY = re.compile(r"(?<![^\W\d_])([^\W\d_]{2,})([-\u00ad\u2010]) ([a-zçğıöşüâîû][^\W\d_]*)")


def _same_style(a: Line, b: Line) -> bool:
    """Could `b` continue the word that ends `a`? The style of a's last glyph and b's first
    glyph: size within 20% (never a folio or a drop cap). A line's dominant style is not
    enough: a line may end a lettered phrase in another font and go on in the body font."""
    return abs(a.end[1] - b.start[1]) <= a.end[1] * 0.2 and not b.text.strip().isdigit()


def _continuation(lines: list[Line], i: int) -> Line | None:
    """The next line of the same text frame: below, overlapping horizontally, same style,
    within 2.2 line-heights (measured leading on the six books: 1.1-1.6 x size)."""
    cur = lines[i]
    best = None
    for l in lines:
        dy = l.baseline - cur.baseline
        if dy <= cur.end[1] * 0.3 or dy > cur.end[1] * 2.2 or not _same_style(cur, l):
            continue
        if l.x1 <= cur.x0 or l.x0 >= cur.x1:
            continue
        if best is None or (l.baseline, l.x0) < (best.baseline, best.x0):
            best = l
    return best


def _next_page_first(lines: list[Line], cur: Line) -> Line | None:
    """First line in reading order on the next page printed in the same style."""
    same = [l for l in lines if l.start[0] == cur.end[0] and abs(l.start[1] - cur.end[1]) <= cur.end[1] * 0.1
            and not l.text.strip().isdigit()]
    return min(same, key=lambda l: (l.baseline, l.x0)) if same else None


def _proper_names(generation_id: str) -> set[str]:
    rows = db.all_rows("SELECT canonical_name AS name, aliases FROM character WHERE generation_id=%s", generation_id) or []
    out = set()
    for r in rows:
        for w in re.findall(r"[^\W\d_]{3,}", " ".join([r.get("name") or "", *(r.get("aliases") or [])])):
            if w[:1].isupper():
                out.add(tr.lower_tr(w))
    return out


class _Vocab:
    """How the book itself prints each word: lower-case, capitalised mid-sentence, or only
    capitalised at sentence starts. Line-end breaks are joined first. A word the book never
    prints in lower case but capitalises mid-sentence is a proper noun (an invented name);
    a word printed lower-case elsewhere is not (Haklısınız at a sentence start)."""

    def __init__(self, lines_by_page: dict[int, list[Line]]):
        self.lower: dict[str, int] = {}
        self.cap: dict[str, int] = {}
        self.cap_mid: dict[str, int] = {}
        text = []
        for lines in lines_by_page.values():
            for l in lines:
                if not _PUA.search(l.text):
                    text.append(l.text)
            text.append("\n\n")
        joined = re.sub(r"([^\W\d_])[-\u00ad\u2010] *\n *([a-zçğıöşüâîû])", r"\1\2", "\n".join(text))
        prev = "."
        for m in re.finditer(r"[^\W\d_]+|[.!?…:“\"«(\-\u2013\u2014]|\n\n", joined):
            w = m.group(0)
            if not w[0].isalpha():
                prev = "."
                continue
            lw = tr.lower_tr(w)
            if w.isupper() and len(w) > 1:
                pass                                        # all caps says nothing
            elif w[0].isupper():
                self.cap[lw] = self.cap.get(lw, 0) + 1
                if prev != ".":
                    self.cap_mid[lw] = self.cap_mid.get(lw, 0) + 1
            else:
                self.lower[lw] = self.lower.get(lw, 0) + 1
            prev = w


def _sentence_start(prev_text: str) -> bool:
    t = prev_text.rstrip(" “\"'«(—–-")
    return not t or t[-1] in ".!?…:"


def analyse_break(left_line: str, right_line: str) -> dict | None:
    """Classify one line-end break. Returns None when the line does not end in a word break."""
    m = _TAIL.search(left_line.rstrip())
    if not m:
        return None
    token, dash = m.group(1), m.group(2)
    # the word is the run of letters/apostrophes/hyphens that ends the line ("ardından.Kuşla-")
    token = re.sub(r"^[^\w]*", "", re.split(r"[^\w'’‘\-\u00ad\u2010\u2011]", token)[-1])
    if not token or not (token[-1].isalpha() or token[-1] in APOS):
        return None                                  # " -" or "1990-": punctuation, not a break
    lead = _LEAD.match(right_line.lstrip("“\"«(‘"))
    if not lead:
        return None
    r_letters, r_apos, r_suffix = lead.group(1), lead.group(2), lead.group(3) or ""
    if any(h in token[:-1] for h in HYPHENS):
        return {"kind": "compound"}                  # SEV-Mİ-YO- / ön-: a word with hard hyphens
    apos_left = token[-1] in APOS
    stem_left = token.rstrip(APOS)
    in_apos = next((k for k, ch in enumerate(stem_left) if ch in APOS), None)
    if in_apos is not None:                           # Ali'nin-ki: broken inside the suffix
        stem, left_part = stem_left[:in_apos], stem_left[in_apos + 1:]
        word, cut = left_part + r_letters, len(left_part)
        return {"kind": "in_suffix", "dash": dash, "word": stem + stem_left[in_apos] + word,
                "cut": cut, "stem": stem, "left": token, "right": r_letters}
    if not stem_left.isalpha():
        return None
    if r_letters[:1].isupper() and not stem_left.isupper():
        return {"kind": "not_a_break"}                # "iki-" + "Üç": a new word, not a continuation
    if apos_left:
        return {"kind": "apos_hyphen", "dash": dash, "word": stem_left + "'" + r_letters,
                "stem": stem_left, "left": token, "right": r_letters}
    word = stem_left + r_letters
    return {"kind": "break", "dash": dash, "word": word, "cut": len(stem_left),
            "stem": word, "left": token, "right": r_letters,
            "apos_after": bool(r_apos), "suffix": r_suffix}


async def run(generation_id: str):
    doc, bv, health = book(generation_id)
    names = _proper_names(generation_id)
    lines_by_page = {}
    skipped = []
    for pno in range(1, doc.page_count + 1):
        if unreliable(health, pno):
            skipped.append(pno)
            continue
        lines_by_page[pno] = page_lines(doc[pno - 1], pno)

    vocab = _Vocab(lines_by_page)
    findings: list[dict] = []
    stats = {"pages": doc.page_count, "pages_skipped_unreliable_layer": skipped,
             "line_end_breaks": 0, "checked": 0, "compound": 0, "unresolved": 0, "not_syllabifiable": 0,
             "lines_unreadable_glyphs": 0}

    def add(page, sev, msg, quote, bb, suggestion=None, **details):
        findings.append({"page": page, "severity": sev, "message": msg, "quote": quote,
                         "bbox": norm_bbox(doc[page - 1], bb), "suggestion": suggestion,
                         "details": details})

    for pno, lines in lines_by_page.items():
        run_len, run_start = 0, None
        for i, cur in enumerate(lines):
            if _PUA.search(cur.text):
                stats["lines_unreadable_glyphs"] += 1        # custom-encoded font: not letters
                run_len = 0
                continue
            # stray hyphenation hyphen inside a line (left over after re-flow)
            for m in _STRAY.finditer(cur.text):
                word = m.group(1) + m.group(3)
                b = tr.syllable_breaks(word)
                # "-hatta söylenen- gözlüklü" is TDK's parenthetical dash (attached kısa çizgi):
                # a stray break is only one whose two halves make a word the book prints whole
                opened = re.search(r"(?:^|\s)[-\u2010][^\W\d_]", cur.text[:m.start()] + " " +
                                   (lines[i - 1].text if i else ""))
                if (b and len(m.group(1)) in b and m.group(2) in HYPHENS and not opened
                        and vocab.lower.get(tr.lower_tr(word), 0) + vocab.cap.get(tr.lower_tr(word), 0) > 0):
                    add(pno, "WARN", "Satır içinde heceleme çizgisi kalmış (metin yeniden akmış olabilir).",
                        m.group(0), cur.bbox, suggestion=word, rule="stray_hyphen")
            ends_dash = cur.text.rstrip()[-1:] in HYPHENS + LOOKALIKE
            if not ends_dash:
                run_len = 0
                continue
            nxt = _continuation(lines, i)
            turn = None
            if nxt is None and pno + 1 in lines_by_page:
                nxt = _next_page_first(lines_by_page[pno + 1], cur)
                turn = pno + 1 if nxt is not None else None
            if nxt is None:
                if cur.text.rstrip()[-1] in HYPHENS and re.search(r"[^\W\d_][" + HYPHENS + r"]$", cur.text):
                    stats["unresolved"] += 1
                run_len = 0
                continue
            a = analyse_break(cur.text, nxt.text)
            if a is None or a["kind"] in ("not_a_break",):
                run_len = 0
                continue
            stats["line_end_breaks"] += 1
            if a["kind"] == "compound":
                stats["compound"] += 1
                run_len = 0
                continue
            quote = f"{a['left']}{a.get('dash', '-')} / {nxt.text[:len(a['right']) + 12]}"
            run_len += 1
            if run_len == 1:
                run_start = cur
            if run_len == LADDER + 1:
                add(pno, "INFO", f"Art arda {LADDER}'ten fazla satır sonu heceleme çizgisiyle bitiyor"
                    " (merdiven).", run_start.text[-20:], (run_start.x0, run_start.y0, cur.x1, cur.y1),
                    rule="ladder")
            if a["dash"] in LOOKALIKE:
                add(pno, "WARN", f"Satır sonu bölmede kısa çizgi yerine “{a['dash']}” (U+{ord(a['dash']):04X})"
                    " kullanılmış.", quote, cur.bbox, suggestion=f"{a['left']}-", rule="lookalike_dash",
                    char=f"U+{ord(a['dash']):04X}")
            if a["kind"] == "apos_hyphen":
                add(pno, "WARN", "Kesme işaretinden sonra kısa çizgi kullanılmış; TDK: satır sonunda"
                    " yalnız kesme işareti kalır.", quote, cur.bbox, suggestion=f"{a['left']}",
                    rule="apostrophe_hyphen")
                continue
            if a["kind"] == "in_suffix":
                add(pno, "INFO", "Özel adın kesmeyle ayrılan eki satır sonunda bölünmüş; bölme"
                    " kesme işaretinde yapılabilir.", quote, cur.bbox,
                    suggestion=f"{a['stem']}’ / {a['word'][len(a['stem']) + 1:]}", rule="apostrophe_suffix")
                continue
            word, cut = a["word"], a["cut"]
            breaks = tr.syllable_breaks(word)
            if breaks is None:
                stats["not_syllabifiable"] += 1
                continue
            stats["checked"] += 1
            allowed = tr.allowed_breaks(word) or []
            if cut not in breaks:
                near = min(allowed, key=lambda k: abs(k - cut)) if allowed else None
                add(pno, "ERROR", f"“{word}” hece sınırında bölünmemiş (heceler: {tr.hyphenate(word)}).",
                    quote, cur.bbox, suggestion=(f"{word[:near]}- / {word[near:]}" if near else
                                                 f"{word} (bölmeden)"),
                    rule="not_syllable_boundary", word=word, cut=cut, syllables=tr.hyphenate(word))
            elif cut < 2 or len(word) - cut < 2:
                add(pno, "WARN", "Satır sonunda ya da başında tek harf bırakılmış (TDK: tek harf bırakılmaz).",
                    quote, cur.bbox, suggestion=(f"{word[:allowed[0]]}- / {word[allowed[0]:]}" if allowed
                                                 else f"{word} (bölmeden)"),
                    rule="single_letter", word=word, cut=cut)
            before = cur.text.rstrip()[:-(len(a["left"]) + 1)].rstrip()
            if not before and i > 0:
                before = lines[i - 1].text
            lw = tr.lower_tr(word)
            proper = (word[:1].isupper() and not word.isupper() and
                      (a["apos_after"] or lw in names or
                       (vocab.lower.get(lw, 0) == 0 and (vocab.cap_mid.get(lw, 0) > 0
                                                          or not _sentence_start(before)))))
            if proper:
                add(pno, "INFO", f"Özel ad “{word}” satır sonunda bölünmüş (TDK'ye aykırı değil;"
                    " yayınevi üslubu çoğunlukla bölmez).", quote, cur.bbox, rule="proper_noun", word=word)
            if turn is not None:
                leaf = pno % 2 == 1          # odd PDF page = recto: the next page is behind the leaf
                add(pno, "WARN" if leaf else "INFO",
                    ("Bölünen kelime sayfa çevrilince devam ediyor (s." if leaf else
                     "Bölünen kelime karşı sayfada devam ediyor (s.") + f"{turn}); sayfanın son satırı"
                    " bölünmemeli.", quote, cur.bbox, rule="page_turn" if leaf else "spread_break",
                    next_page=turn)
    stats["findings_by_rule"] = {}
    for f in findings:
        r = f["details"].get("rule")
        stats["findings_by_rule"][r] = stats["findings_by_rule"].get(r, 0) + 1
    return findings, stats
