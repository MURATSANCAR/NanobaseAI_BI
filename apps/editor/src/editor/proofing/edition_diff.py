"""Baskılar arası fark: what changed since the previous analysed version of the same book.

A new edition arrives as a new `book_version` of the same `book` (different sha256). The
check compares it with the newest earlier version, deterministically:

1. Pages are ALIGNED BY CONTENT, not by number (a page added early would otherwise make
   every later page "changed"): word-set similarity for pages with text, the
   difference of 32x32 render thumbnails for pages without, then a monotonic alignment (dynamic
   programming) that only pairs pages above ALIGN_MIN.
2. Aligned pages: word-level text diff (hyphenation, quote style and spacing normalised
   away); the renders are compared pixel by pixel with the text lines of both versions
   masked out, so a text edit is not reported twice as a picture change.
3. Pages without a partner: added / removed.
4. The imprint (ISBN, edition number, printing date) is read from the pages carrying an
   ISBN and compared field by field.

Severity: the imprint (and any text change on the imprint page) is INFO — an edition is
expected to change it; story text changes, added/removed pages and changed pictures are
WARN.

Measured 2026-09-22 (docs/son-okuma/edition_diff.md): no book in the database has two
versions, so precision and recall are UNMEASURED on a real edition pair. Each of the six
PDFs compared with itself gives 0 findings (sanity, not a measurement); injected changes
on throwaway copies were all found (mechanism test, not a measurement).
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

import numpy as np
import pymupdf

from .. import db, source

NAME = "edition_diff"
VERSION = "1"
LABEL = "Baskılar arası fark"

ISBN_RE = re.compile(r"97[89][-\s]?\d{1,5}[-\s]?\d{1,7}[-\s]?\d{1,7}[-\s]?\d")
EDITION_RE = re.compile(r"(\d{1,3})\s*\.\s*Bask[ıi]", re.I)
DATE_RE = re.compile(r"Bask[ıi]\s*[:|/]?\s*((?:Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|"
                     r"Aralık)\s+\d{4})", re.I)

# Measured thresholds (docs/son-okuma/edition_diff.md):
ALIGN_MIN = 0.5      # text pages: word-set overlap of DIFFERENT pages of one book is at most 0.233
IMAGE_MIN = 0.96     # textless pages: different pages at most 0.924, same page re-exported at least 0.992
RENDER_W = 400       # comparison raster width in px (a raster size, not a decision)
PIXEL_DELTA = 64     # grey-level difference that counts as a changed pixel (0..255)
BLOCK = 8            # px; a changed cell is one whose pixels mostly changed
CHANGED_MIN = 0.002  # share of changed cells that makes a picture "changed" (see docs)


# ------------------------------------------------------------- page features
def _words(text: str) -> list[str]:
    raw = re.sub(r"(\w)[-­]\s+(\w)", r"\1\2", text or "")
    return raw.split()


def _key(tok: str) -> str:
    return source.key(tok).strip(".,;:!?…\"'«»()[]-–—")


def _raster(page: pymupdf.Page, width: int = RENDER_W, color: bool = False) -> np.ndarray:
    """Grey (h, w) or RGB (h, w, 3) raster, `width` px wide."""
    z = width / page.rect.width
    pm = page.get_pixmap(matrix=pymupdf.Matrix(z, z), colorspace=pymupdf.csRGB if color else pymupdf.csGRAY,
                         alpha=False)
    arr = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.height, pm.stride)[:, :pm.width * pm.n]
    return arr.reshape(pm.height, pm.width, pm.n).copy() if color else arr.copy()


THUMB = 32            # page thumbnail side for pairing pages by look (see docs)


def _thumb(img: np.ndarray, side: int = THUMB) -> np.ndarray:
    """Mean grey level of a side x side grid: scale-free, and a flat page stays flat
    (a difference hash turns paper noise into random bits on blank pages)."""
    h, w = img.shape
    ys = (np.arange(side) * h / side).astype(int)
    xs = (np.arange(side) * w / side).astype(int)
    sums = np.add.reduceat(np.add.reduceat(img.astype(np.float64), ys, axis=0), xs, axis=1)
    counts = np.outer(np.diff(np.append(ys, h)), np.diff(np.append(xs, w)))
    return sums / counts


def _text_boxes(page: pymupdf.Page) -> list[tuple[float, float, float, float]]:
    """Visible text lines of the PDF layer, in page points."""
    out = []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            if any(sp["text"].strip() and sp.get("alpha", 255) != 0 for sp in ln["spans"]):
                out.append(tuple(ln["bbox"]))
    return out


def features(doc: pymupdf.Document, texts: dict[int, tuple[str, str]]) -> list[dict]:
    """One record per page: text (and where it came from), word set, render hash."""
    out = []
    for i, page in enumerate(doc, 1):
        text, src = texts.get(i, ("", "NONE"))
        words = _words(text)
        img = _raster(page)
        keys = [k for k in (_key(w) for w in words) if k]
        out.append({"page": i, "text": text, "source": src, "words": words, "keys": keys, "kset": set(keys),
                    "thumb": _thumb(img),
                    "imprint": bool(ISBN_RE.search(text))})
    return out


def image_similarity(a: dict, b: dict) -> float:
    return 1 - float(np.abs(a["thumb"] - b["thumb"]).mean()) / 255


def similarity(a: dict, b: dict) -> float:
    """How strongly two pages are "the same page", 0..1, already gated: word-set overlap
    when both have text (pairable from ALIGN_MIN), thumbnail likeness when neither has
    (pairable from IMAGE_MIN, rescaled onto the same gate). A page with text and one
    without are never paired: by look alone, text pages of one book are near-identical
    white pages (measured up to 0.993, above the re-export noise floor 0.992)."""
    if a["keys"] and b["keys"]:
        sa, sb = a["kset"], b["kset"]
        return len(sa & sb) / len(sa | sb)
    if a["keys"] or b["keys"]:
        return 0.0
    v = image_similarity(a, b)
    return ALIGN_MIN + (v - IMAGE_MIN) / (1 - IMAGE_MIN) * (1 - ALIGN_MIN) if v >= IMAGE_MIN else 0.0


def align(fa: list[dict], fb: list[dict]) -> list[tuple[int | None, int | None, float]]:
    """Monotonic alignment maximising the summed similarity of paired pages (each pair
    must reach ALIGN_MIN); unpaired pages come out as (i, None) / (None, j)."""
    n, m = len(fa), len(fb)
    sim = [[similarity(fa[i], fb[j]) for j in range(m)] for i in range(n)]
    best = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            v = max(best[i + 1][j], best[i][j + 1])
            if sim[i][j] >= ALIGN_MIN:
                v = max(v, sim[i][j] + best[i + 1][j + 1])
            best[i][j] = v
    out, i, j = [], 0, 0
    while i < n and j < m:
        if sim[i][j] >= ALIGN_MIN and abs(best[i][j] - (sim[i][j] + best[i + 1][j + 1])) < 1e-9:
            out.append((i, j, sim[i][j])); i += 1; j += 1
        elif abs(best[i][j] - best[i + 1][j]) < 1e-9:
            out.append((i, None, 0.0)); i += 1
        else:
            out.append((None, j, 0.0)); j += 1
    out += [(k, None, 0.0) for k in range(i, n)] + [(None, k, 0.0) for k in range(j, m)]
    return out


# ------------------------------------------------------------ comparisons
def _mask(img: np.ndarray, page: pymupdf.Page, boxes, pad: int = 2) -> None:
    z = img.shape[1] / page.rect.width
    for x0, y0, x1, y1 in boxes:
        img[max(0, int(y0 * z) - pad):int(y1 * z) + pad, max(0, int(x0 * z) - pad):int(x1 * z) + pad] = 255


def changed_blocks(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """BLOCK x BLOCK pixel cells in which most pixels changed by more than PIXEL_DELTA.
    Re-export noise (resampling, JPEG) is scattered; an edit to a picture is compact."""
    diff = np.abs(a.astype(np.int16) - b.astype(np.int16))
    if diff.ndim == 3:          # colour: a red shape on a mid-grey picture barely moves the grey level
        diff = diff.max(axis=2)
    diff = diff > PIXEL_DELTA
    h, w = (diff.shape[0] // BLOCK) * BLOCK, (diff.shape[1] // BLOCK) * BLOCK
    cells = diff[:h, :w].reshape(h // BLOCK, BLOCK, w // BLOCK, BLOCK).mean(axis=(1, 3))
    return cells > 0.5


def picture_change(pa: pymupdf.Page, pb: pymupdf.Page) -> dict | None:
    """Changed share and bbox (0..1000 of the new page) outside the text lines of either version."""
    a, b = _raster(pa, color=True), _raster(pb, color=True)
    if a.shape != b.shape:
        h = min(a.shape[0], b.shape[0]); a, b = a[:h], b[:h]
    boxes_a, boxes_b = _text_boxes(pa), _text_boxes(pb)
    for img, page in ((a, pa), (b, pb)):
        _mask(img, page, boxes_a); _mask(img, page, boxes_b)
    blocks = changed_blocks(a, b)
    share = float(blocks.mean())
    if share < CHANGED_MIN:
        return None
    ys, xs = np.nonzero(blocks)
    h, w = blocks.shape
    return {"share": round(share, 4), "bbox": [int(xs.min() / w * 1000), int(ys.min() / h * 1000),
                                               int((xs.max() + 1) / w * 1000), int((ys.max() + 1) / h * 1000)]}


def text_changes(a: dict, b: dict) -> list[dict]:
    """Word-level edits between two aligned pages: {old, new, before, after}."""
    sm = SequenceMatcher(None, a["keys"], b["keys"], autojunk=False)
    ka = [w for w in a["words"] if _key(w)]
    kb = [w for w in b["words"] if _key(w)]
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        out.append({"op": op, "old": " ".join(ka[i1:i2]), "new": " ".join(kb[j1:j2]),
                    "before": " ".join(kb[max(0, j1 - 4):j1]), "after": " ".join(kb[j2:j2 + 4])})
    return out


def imprint(fs: list[dict]) -> dict:
    text = "\n".join(f["text"] for f in fs if f["imprint"])
    page = next((f["page"] for f in fs if f["imprint"]), None)
    return {"page": page, "isbn": sorted({re.sub(r"[-\s]", "", m) for m in ISBN_RE.findall(text)}),
            "edition": sorted({int(m) for m in EDITION_RE.findall(text)}),
            "date": sorted({m.strip().lower() for m in DATE_RE.findall(text)})}


def _snip(words: list[str], n: int = 12) -> str:
    return " ".join(words[:n]) + (" …" if len(words) > n else "")


def compare(old_doc, new_doc, old_texts, new_texts) -> tuple[list[dict], dict]:
    fa, fb = features(old_doc, old_texts), features(new_doc, new_texts)
    pairs = align(fa, fb)
    findings: list[dict] = []
    stats = {"old_pages": len(fa), "new_pages": len(fb), "aligned": 0, "added": 0, "removed": 0,
             "shifted": 0, "text_changed_pages": 0, "picture_changed_pages": 0}
    for i, j, s in pairs:
        if i is not None and j is not None:
            a, b = fa[i], fb[j]
            stats["aligned"] += 1
            stats["shifted"] += a["page"] != b["page"]
            sev = "INFO" if (a["imprint"] or b["imprint"]) else "WARN"
            moved = f" (önceki baskıda s.{a['page']})" if a["page"] != b["page"] else ""
            srcnote = (f" Metin kaynakları farklı ({a['source']} / {b['source']}): okuma farkı olabilir."
                       if a["source"] != b["source"] else "")
            ch = text_changes(a, b) if a["keys"] != b["keys"] else []
            stats["text_changed_pages"] += bool(ch)
            for c in ch:
                what = {"replace": f"«{c['old']}» → «{c['new']}»", "delete": f"çıkarıldı: «{c['old']}»",
                        "insert": f"eklendi: «{c['new']}»"}[c["op"]]
                findings.append({"page": b["page"], "severity": sev, "quote": c["new"] or None,
                                 "message": f"{'Künye' if sev == 'INFO' else 'Metin'} değişti{moved}: {what}.{srcnote}",
                                 "suggestion": None,
                                 "details": {**c, "old_page": a["page"], "sources": [a["source"], b["source"]]}})
            pic = picture_change(old_doc[a["page"] - 1], new_doc[b["page"] - 1])
            if pic:
                stats["picture_changed_pages"] += 1
                findings.append({"page": b["page"], "severity": "WARN", "bbox": pic["bbox"],
                                 "message": f"Görsel değişti{moved}: sayfanın metin dışı alanının %"
                                            f"{pic['share'] * 100:.1f}'i önceki baskıdan farklı (resim ya da resme "
                                            f"gömülü yazı). İşaretli bölgeyi iki baskıda karşılaştırın.",
                                 "details": {"old_page": a["page"], **pic}})
        elif j is not None:
            b = fb[j]
            stats["added"] += 1
            findings.append({"page": b["page"], "severity": "INFO" if b["imprint"] else "WARN",
                             "quote": _snip(b["words"]) or None,
                             "message": "Yeni sayfa: önceki baskıda içerikçe karşılığı yok."
                                        + (f" Başı: «{_snip(b['words'])}»" if b["words"] else " (metinsiz sayfa)"),
                             "details": {"new_page": b["page"]}})
        else:
            a = fa[i]
            stats["removed"] += 1
            findings.append({"page": None, "severity": "INFO" if a["imprint"] else "WARN",
                             "message": f"Önceki baskının s.{a['page']} sayfası bu baskıda yok."
                                        + (f" Başı: «{_snip(a['words'])}»" if a["words"] else " (metinsiz sayfa)"),
                             "details": {"old_page": a["page"]}})
    ia, ib = imprint(fa), imprint(fb)
    for field, tr in (("isbn", "ISBN"), ("edition", "Baskı numarası"), ("date", "Baskı tarihi")):
        if ia[field] and ib[field] and ia[field] != ib[field]:
            extra = " (ISBN değişmesi yeni bir basım/sürüm kaydı demektir)" if field == "isbn" else ""
            findings.append({"page": ib["page"], "severity": "INFO",
                             "message": f"{tr}: {', '.join(map(str, ia[field]))} → {', '.join(map(str, ib[field]))}{extra}.",
                             "details": {"field": field, "old": ia[field], "new": ib[field]}})
    stats["imprint"] = {"old": ia, "new": ib}
    return findings, stats


# -------------------------------------------------------------------- run
def texts_of(generation_id: str | None, doc: pymupdf.Document) -> dict[int, tuple[str, str]]:
    """Page text: the generation's source reading when there is one, else the PDF layer."""
    if generation_id:
        return {p["page_no"]: ("\n\n".join(s["text"] for s in p["spans"]),
                               "/".join(sorted({s["source"] for s in p["spans"]})) or "NONE")
                for p in source.read(generation_id)}
    return {i: (pg.get_text(), "TEXT_LAYER") for i, pg in enumerate(doc, 1)}


async def run(generation_id: str):
    cur = db.one("SELECT bv.id, bv.book_id, bv.sha256, bv.file_path, bv.created_at FROM generation g"
                 " JOIN book_version bv ON bv.id=g.book_version_id WHERE g.id=%s", generation_id)
    prev = db.one("SELECT id, sha256, file_path, created_at FROM book_version WHERE book_id=%s AND sha256<>%s"
                  " AND created_at < %s ORDER BY created_at DESC LIMIT 1",
                  cur["book_id"], cur["sha256"], cur["created_at"])
    if prev is None:
        return [{"page": None, "severity": "INFO",
                 "message": "Bu kitabın önceki bir sürümü (farklı dosya) yok; baskı karşılaştırması yapılmadı."}], \
               {"previous_version": None}
    prev_gen = db.one("SELECT id FROM generation WHERE book_version_id=%s ORDER BY created_at DESC LIMIT 1",
                      prev["id"])
    old_doc, new_doc = pymupdf.open(prev["file_path"]), pymupdf.open(cur["file_path"])
    findings, stats = compare(old_doc, new_doc,
                              texts_of(str(prev_gen["id"]) if prev_gen else None, old_doc),
                              texts_of(generation_id, new_doc))
    stats["previous_version"] = {"book_version_id": str(prev["id"]), "sha256": prev["sha256"],
                                 "generation_id": str(prev_gen["id"]) if prev_gen else None}
    return findings, stats
