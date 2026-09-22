"""What the page really shows around a punctuation mark: the printed gap between glyphs.

The text layer is not the print. Measured on six books (docs/son-okuma/spelling.md, "Boşluk
ölçümü"): the layer holds space characters that the typesetter kerned to nothing
("Merhaba , Defne ." is printed "Merhaba, Defne."), and the stored page text loses the space
where a line ends after a comma ("çocuklar,\ndedi" -> "çocuklar,dedi"). A spacing finding is
therefore decided on glyph positions from the PDF (PyMuPDF rawdict): is there a visible gap
between the two glyphs, on the same printed line?
"""

from __future__ import annotations

import unicodedata
from functools import lru_cache

# A gap is a printed space when it is at least SPACE_EM of the font size. Measured over every
# text-layer line of the six books (docs, "Boşluk ölçümü"): letter-to-letter gaps inside a word
# have a 99th percentile of 0.020-0.065 em per book; gaps where the layer has a space between
# two letters have a 5th percentile of 0.17-0.26 em (1st: 0.058-0.21). 0.12 em lies between.
SPACE_EM = 0.12

_Q = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "«": '"', "»": '"'})


def _k(ch: str) -> str:
    return unicodedata.normalize("NFKC", ch).translate(_Q)


@lru_cache(maxsize=4)
def _doc(book_version_id: str):
    from ..document import _open_version
    doc, _ = _open_version(book_version_id)
    return doc


@lru_cache(maxsize=64)
def glyphs(book_version_id: str, page_no: int) -> tuple[str, list]:
    """(string of non-space glyphs, [(char, x0, x1, size, line_id)]) for one page."""
    import pymupdf
    page = _doc(book_version_id)[page_no - 1]
    out, chars = [], []
    line_id = 0
    raw = page.get_text("rawdict", flags=pymupdf.TEXT_INHIBIT_SPACES | pymupdf.TEXT_MEDIABOX_CLIP)
    for b in raw["blocks"]:
        for ln in b.get("lines", []):
            line_id += 1
            for sp in ln["spans"]:
                for c in sp["chars"]:
                    ch = c["c"]
                    if not ch.strip():
                        continue
                    for piece in _k(ch):
                        out.append((piece, c["bbox"][0], c["bbox"][2], sp["size"] or 1.0, line_id))
                        chars.append(piece)
    return "".join(chars), out


def printed_gap(book_version_id: str, page_no: int, left: str, mark: str, right: str, mode: str) -> dict:
    """Locate left+mark+right (spaces ignored) among the page's glyphs and measure the gap
    the rule is about. Returns {found, same_line, gap_em}."""
    s, gl = glyphs(book_version_id, page_no)
    L = "".join(_k(c) for c in left if c.strip())
    M = "".join(_k(c) for c in mark if c.strip())
    R = "".join(_k(c) for c in right if c.strip())
    # the shortest context that is unique on the page, growing from the mark outwards
    hit = None
    for wl, wr in ((6, 6), (10, 10), (len(L), len(R))):
        left_used = L[-wl:] if wl else ""
        needle = left_used + M + R[:wr]
        i = s.find(needle)
        if i >= 0:
            hit = (i, len(left_used))
            if s.find(needle, i + 1) < 0:
                break
    if hit is None:
        return {"found": False}
    m0 = hit[0] + hit[1]
    m1 = m0 + len(M) - 1
    if mode == "before":
        a, b = m0 - 1, m0
    else:  # after / after_open
        a, b = m1, m1 + 1
    if a < 0 or b >= len(gl):
        return {"found": True, "same_line": False, "gap_em": None}
    ga, gb = gl[a], gl[b]
    same = ga[4] == gb[4]
    gap = (gb[1] - ga[2]) / max(ga[3], gb[3]) if same else None
    return {"found": True, "same_line": same, "gap_em": None if gap is None else round(gap, 3)}


def confirms(res: dict, mode: str) -> bool | None:
    """True: the print shows the error; False: it does not (layer artefact); None: not
    measurable (text not found in the glyphs)."""
    if not res.get("found"):
        return None
    if not res["same_line"]:
        return False  # a line break is the space; nothing to report
    spaced = res["gap_em"] >= SPACE_EM
    return spaced if mode in ("before", "after_open") else not spaced
