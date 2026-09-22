"""Printed-line geometry from the PDF's digital layer, shared by the `hyphenation` and
`layout` checks. Read-only: opens the book's PDF, never writes.

What counts as a printed line: horizontal text (dir = (1, 0)) whose glyphs are really drawn.
MuPDF marks every glyph (span "char_flags"): 16 filled, 32 stroked, 64 clipped away.
A glyph that is neither filled nor stroked, fully clipped, or has alpha 0 is not on the page
(overset frames behind artwork, hidden layers); measured on the six books this removes
3.498 alpha-0 and 2.706 clipped glyphs of one book and small numbers elsewhere.
Overprinted copies (the same line drawn twice: fill + outline) are kept once.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pymupdf

from .. import db
from ..document import _open_version

FILLED, STROKED, CLIPPED = 16, 32, 64


@dataclass
class Line:
    page: int
    text: str
    chars: list            # [(c, (x0,y0,x1,y1))] visible glyphs in order
    x0: float
    y0: float
    x1: float
    y1: float
    baseline: float
    size: float            # dominant (by glyph count) font size
    font: str
    color: int             # dominant sRGB fill colour
    bold: bool
    stroked_only: bool
    spans: list = field(default_factory=list)   # (text, size, font, color, bbox)
    start: tuple = ("", 0.0)   # (font, size) of the first printed glyph
    end: tuple = ("", 0.0)     # (font, size) of the last printed glyph (a hyphenated word's style)
    outlined: bool = False     # drawn twice, fill + stroke (an outline effect around the letters)

    @property
    def bbox(self):
        return (self.x0, self.y0, self.x1, self.y1)


def visible(span: dict) -> bool:
    f = span.get("char_flags", FILLED)
    return span.get("alpha", 255) != 0 and bool(f & (FILLED | STROKED)) and not f & CLIPPED


def page_lines(page: pymupdf.Page, page_no: int) -> list[Line]:
    out: list[Line] = []
    seen: dict = {}
    raw = page.get_text("rawdict", flags=pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_PRESERVE_IMAGES)
    for b in raw["blocks"]:
        for ln in b.get("lines", []):
            if abs(ln["dir"][1]) > 0.01 or ln["dir"][0] <= 0:
                continue
            spans = [s for s in ln["spans"] if visible(s)]
            for s in spans:
                s["text"] = "".join(c["c"] for c in s["chars"])
            chars, at, twice = [], set(), False
            for s in spans:
                for c in s["chars"]:
                    k = (c["c"], round(c["origin"][0], 1), round(c["origin"][1], 1))
                    if k in at and not c["c"].isspace():
                        twice = True                     # the same glyph drawn again in place
                        continue
                    at.add(k)
                    chars.append((c["c"], tuple(c["bbox"])))
            text = "".join(c for c, _ in chars)
            if not text.strip():
                continue
            ink = [bb for c, bb in chars if not c.isspace()]
            x0, y0 = min(b[0] for b in ink), min(b[1] for b in ink)
            x1, y1 = max(b[2] for b in ink), max(b[3] for b in ink)
            key = (text.strip(), round(x0), round(y0))
            if key in seen:
                dup_stroked = all(not s.get("char_flags", FILLED) & FILLED for s in spans)
                if dup_stroked != seen[key].stroked_only:
                    seen[key].outlined = True        # one copy filled, one copy stroked
                continue
            weight: dict = {}
            for s in spans:
                n = sum(1 for c in s["chars"] if not c["c"].isspace())
                k = (round(s["size"], 1), s["font"], s["color"], bool(s.get("char_flags", 0) & 8),
                     not s.get("char_flags", FILLED) & FILLED)
                weight[k] = weight.get(k, 0) + n
            size, font, color, bold, stroked_only = max(weight, key=weight.get)
            inked = [s for s in spans if s["text"].strip()]
            base = [s["origin"][1] for s in spans if s["text"].strip()]
            out.append(Line(page_no, text.rstrip(), chars, x0, y0, x1, y1,
                            sorted(base)[len(base) // 2] if base else y1, size, font, color, bold,
                            stroked_only,
                            [(s["text"], s["size"], s["font"], s["color"], tuple(s["bbox"]))
                             for s in spans if s["text"].strip()],
                            *[(s["font"], round(s["size"], 1)) for s in (inked[0], inked[-1])]))
            seen[key] = out[-1]
            out[-1].outlined = twice
            if any((s.get("char_flags", 0) & (FILLED | STROKED)) == FILLED | STROKED for s in spans):
                out[-1].outlined = True              # fill-and-stroke in one pass
    out.sort(key=lambda l: (round(l.baseline), l.x0))
    return out


def book(generation_id: str) -> tuple[pymupdf.Document, dict, dict[int, dict]]:
    """The generation's PDF, its book_version row and each page's layer health."""
    gen = db.one("SELECT book_version_id FROM generation WHERE id=%s", generation_id)
    if gen is None:
        raise KeyError(f"generation {generation_id} not found")
    doc, bv = _open_version(str(gen["book_version_id"]))
    health = {r["page_no"]: (r["layer_health"] or {}) for r in db.all_rows(
        "SELECT page_no, layer_health FROM page WHERE book_version_id=%s", gen["book_version_id"])}
    return doc, bv, health


def unreliable(health: dict[int, dict], page_no: int) -> bool:
    return bool((health.get(page_no) or {}).get("layer_unreliable"))


def body_style(lines_by_page: dict[int, list[Line]]) -> tuple[str, float]:
    """The book's running-text style: the (font, size) that prints the most glyphs."""
    w: dict = {}
    for lines in lines_by_page.values():
        for l in lines:
            k = (l.font, round(l.size * 2) / 2)
            w[k] = w.get(k, 0) + sum(1 for c, _ in l.chars if not c.isspace())
    return max(w, key=w.get) if w else ("", 0.0)


def norm_bbox(page: pymupdf.Page, bb) -> list[int]:
    W, H = page.rect.width, page.rect.height
    return [max(0, min(1000, round(v))) for v in
            (bb[0] / W * 1000, bb[1] / H * 1000, bb[2] / W * 1000, bb[3] / H * 1000)]
