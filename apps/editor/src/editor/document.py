"""book_document tools: intake, page manifest, text layer, rendering, OCR."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import pymupdf

from . import db, pdf_repair, prompts, schemas, source
from .config import settings
from .llm import Llm, image_part

TARGET_LONG_SIDE_PX = 1600
_SPACED = re.compile(r"(?:\b\w\b ){4,}\w\b")      # "i y i k i" letter-spaced headings


def _safe_inbox_path(file_name: str) -> Path:
    """Only files inside storage/inbox are readable (no free filesystem access)."""
    inbox = settings().inbox.resolve()
    p = (inbox / Path(file_name).name).resolve()
    if p.parent != inbox or not p.is_file() or p.suffix.lower() != ".pdf":
        raise FileNotFoundError(f"{file_name}: not a PDF in the inbox")
    return p


def list_inbox() -> list[dict]:
    return [{"file_name": p.name, "bytes": p.stat().st_size}
            for p in sorted(settings().inbox.glob("*.pdf"))]


def inspect_book(file_name: str, title: str | None = None, universe: str | None = None,
                 age_group: str | None = None, merge_by_title: bool = True) -> dict:
    """Creates (or finds) the book and its content version (sha256 of the file). `merge_by_title`: a new
    content joins an existing book of the same title (a title derived from a file name does not)."""
    path = _safe_inbox_path(file_name)
    data = path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    doc = pymupdf.open(stream=data, filetype="pdf")
    meta = {k: v for k, v in (doc.metadata or {}).items() if v}
    title = title or meta.get("title") or path.stem
    with db.tx() as c:
        existing = c.execute(
            "SELECT bv.id AS book_version_id, b.id AS book_id, b.title FROM book_version bv "
            "JOIN book b ON b.id = bv.book_id WHERE bv.sha256=%s ORDER BY bv.created_at LIMIT 1",
            (sha,)).fetchone()
        if existing:
            return {**{k: str(v) for k, v in existing.items()}, "sha256": sha,
                    "page_count": doc.page_count, "new_version": False}
        book = c.execute("SELECT id FROM book WHERE title=%s ORDER BY created_at LIMIT 1",
                         (title,)).fetchone() if merge_by_title else None
        if book is None:
            book = c.execute("INSERT INTO book(title, universe, age_group) VALUES (%s,%s,%s) "
                             "RETURNING id", (title, universe, age_group)).fetchone()
        dest = settings().storage / "books" / sha[:16] / "source.pdf"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.write_bytes(data)
        bv = c.execute(
            "INSERT INTO book_version(book_id, sha256, file_path, file_bytes, page_count, pdf_meta)"
            " VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
            (book["id"], sha, str(dest), len(data), doc.page_count, db.J(meta))).fetchone()
    return {"book_id": str(book["id"]), "book_version_id": str(bv["id"]), "title": title,
            "sha256": sha, "page_count": doc.page_count, "new_version": True}


def _open_version(book_version_id: str, repair: bool = True) -> tuple[pymupdf.Document, dict]:
    """The version's PDF. `repair`: wrong letter mappings of its fonts are mended from the fonts' own
    data in memory (pdf_repair; the file is never written). Rendering does not need it."""
    bv = db.one("SELECT * FROM book_version WHERE id=%s", book_version_id)
    if bv is None:
        raise KeyError(f"book_version {book_version_id} not found")
    doc = pymupdf.open(bv["file_path"])
    if repair:
        pdf_repair.repair_document(doc)
    return doc, bv


def _pages_dir(bv: dict) -> Path:
    d = Path(bv["file_path"]).parent / "pages"
    d.mkdir(parents=True, exist_ok=True)
    return d


# Above these the text layer itself is suspect (a custom font mapped to wrong code points,
# letter-spaced headings): the same two numbers decide that a page needs OCR and whether a
# disagreeing OCR reading is a real source conflict (source.py).
GARBLED_MAX = 0.02
SPACED_MAX = 0.3


def _collapse_repeats(text: str) -> tuple[str, int]:
    """A vision model that falls into a loop writes one phrase over and over until its budget
    ends (measured: 7 of 171 OCR'd pages, one page 8.552 characters for 873 of real text). A
    phrase of at least three letters repeated ten or more times in a row is kept once.
    Shorter units and fewer repeats are left alone: a book does print "AAAAAAAA!" and dot
    leaders in a table of contents (measured on 90 random pages: every page the old rule cut
    was one of these, read the same way by all four readers). Returns (text, characters cut)."""
    def cut(m: re.Match) -> str:
        unit = m.group(1)
        return unit if len(re.findall(r"[^\W\d_]", unit)) >= 3 else m.group(0)
    out = re.sub(r"(?s)(\S.{1,120}?)(?:\s*\1){9,}", cut, text)
    return out, len(text) - len(out)


# A scrambled layer is made of valid letters, so it has to be caught by what it does to
# WORDS. Measured on 476 pages of six books — healthy pages: fragments <= 0.19, glued
# <= 0.03, and a page's stems recur elsewhere in its own book about as often as the book's
# average (0.67-0.89); scrambled pages: fragments 0.28-0.38, glued 0.05-0.32, recurring
# stems 0.40-0.53 against a book average of 0.86. The third test is relative to the book
# itself, so a book with an unusual vocabulary is not judged by another book's numbers.
FRAGMENT_MAX = 0.30        # share of words of one or two letters (healthy max measured 0.24)
GLUED_MAX = 0.04           # share of words >= 20 letters or with ".X" / ",x" inside
STEM_DROP_MAX = 0.30       # how far below the book's mean a page's recurring-stem share may fall


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"\S+", text) if re.search(r"[^\W\d_]", w)]


def _stem(word: str) -> str:
    return re.sub(r"\W", "", word).casefold()[:5]      # Turkish is agglutinative: compare stems


def layer_health(text: str, stem_pages: dict[str, int] | None = None, book_mean: float | None = None) -> dict:
    """Word-level health of a page's digital text. `stem_pages`: on how many pages of the
    book each stem occurs; `book_mean`: the book's mean recurring-stem share."""
    w = _words(text)
    if len(w) < 25:
        return {"words": len(w), "suspect": False}
    # A word cut by line-end hyphenation ("po-" + "lislere") is typesetting, not scrambling,
    # and a contents line's dot leaders ("Yasaktır.........32") are not a glued word: both
    # were measured as false alarms on healthy pages.
    letters = [re.sub(r"[\W\d_]", "", x) for x in w if not x.endswith(("-", "\u00ad"))]
    frag = sum(1 for x in letters if len(x) <= 2) / max(1, len(letters))
    glued = sum(1 for x in w if len(re.sub(r"[\W\d_]", "", x)) >= 20
                or re.search(r"[a-zçğıöşü][.,;:!?][^\W\d_]", x)) / len(w)
    out = {"words": len(w), "fragments": round(frag, 3), "glued": round(glued, 3)}
    reasons = [n for n, bad in (("FRAGMENTS", frag > FRAGMENT_MAX), ("GLUED", glued > GLUED_MAX)) if bad]
    if stem_pages is not None and book_mean is not None:
        known = sum(1 for x in w if stem_pages.get(_stem(x), 0) >= 2) / len(w)
        out.update(recurring_stems=round(known, 3), book_mean=round(book_mean, 3))
        # Unusual vocabulary alone is a reason to read the page a second time, not a verdict
        # on the layer: every book's imprint page (addresses, ISBN) trips it while being
        # perfectly good text — and an OCR'd ISBN is worse than a digital one.
        out["unusual_vocabulary"] = known < book_mean - STEM_DROP_MAX
    return {**out, "suspect": bool(reasons), "reasons": reasons}


def book_stems(texts: list[str]) -> tuple[dict[str, int], float]:
    """(stem -> number of pages it occurs on, mean recurring-stem share over the pages)."""
    pages = [[_stem(x) for x in _words(t)] for t in texts]
    df: dict[str, int] = {}
    for stems in pages:
        for st in set(stems):
            df[st] = df.get(st, 0) + 1
    shares = [sum(1 for st in stems if df[st] >= 2) / len(stems) for stems in pages if len(stems) >= 25]
    return df, (sum(shares) / len(shares) if shares else 0.0)


def _garbled_ratio(text: str) -> float:
    """Share of Private Use Area glyphs: a font with a custom encoding exports
    its text layer as unreadable symbols, so the page needs OCR instead."""
    chars = [ch for ch in text if not ch.isspace()]
    if not chars:
        return 0.0
    return sum(1 for ch in chars if 0xE000 <= ord(ch) <= 0xF8FF or ord(ch) >= 0xF0000) / len(chars)


def _spaced_ratio(text: str) -> float:
    words = text.split()
    if not words:
        return 0.0
    return sum(1 for w in words if len(w) == 1) / len(words)


def nontext_ink_ratio(page: pymupdf.Page) -> float:
    """Share of the page body (inside an 8% margin, so printer marks do not count)
    that has ink outside the visible text lines. Text-only pages measure ~0."""
    import numpy as np
    z = 100 / 72
    pm = page.get_pixmap(matrix=pymupdf.Matrix(z, z), colorspace=pymupdf.csGRAY, alpha=False)
    w, h = pm.width, pm.height
    # one grey byte per pixel, rows of `stride` bytes (== w for a grey pixmap without alpha)
    img = np.frombuffer(pm.samples, dtype=np.uint8).reshape(h, pm.stride)[:, :w].copy()
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            if not any(sp["text"].strip() and sp.get("alpha", 255) != 0 for sp in ln["spans"]):
                continue
            x0, y0, x1, y1 = (int(v * z) for v in ln["bbox"])
            xa, xb = max(0, x0 - 2), min(w, x1 + 2)
            ya, yb = max(0, y0 - 2), min(h, y1 + 2)
            if xb > xa and yb > ya:          # a line off the page masks nothing
                img[ya:yb, xa:xb] = 255
    # Vectorised 2026-10-05 (the per-pixel Python loop held the worker's GIL for seconds a page); the count is
    # the old loop's exactly (tests/test_pdf_process.py).
    mx, my = int(w * .08), int(h * .08)
    ink = int(np.count_nonzero(img[my:max(my, h - my), mx:max(mx, w - mx)] < 235))
    return ink / max(1, (w - 2 * mx) * (h - 2 * my))


def region_ink_ratio(png_path: str, bbox: list[int]) -> float:
    """Ink share inside a model-given bbox (0..1000 normalised) of a rendered page."""
    if not bbox or len(bbox) != 4 or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        return 0.0
    import numpy as np
    pm = pymupdf.Pixmap(pymupdf.csGRAY, pymupdf.Pixmap(png_path))
    w, h, buf = pm.width, pm.height, np.frombuffer(pm.samples, dtype=np.uint8)
    x0, x1 = int(bbox[0] / 1000 * w), max(int(bbox[2] / 1000 * w), int(bbox[0] / 1000 * w) + 1)
    y0, y1 = int(bbox[1] / 1000 * h), max(int(bbox[3] / 1000 * h), int(bbox[1] / 1000 * h) + 1)
    # one numpy count per row, over exactly the slices the per-pixel loop read (same result)
    ink = sum(int(np.count_nonzero(buf[y * w + x0: y * w + min(w, x1)] < 235)) for y in range(y0, min(h, y1)))
    return ink / max(1, (min(w, x1) - x0) * (min(h, y1) - y0))


#: A page whose text layer is (nearly) empty but whose body carries ink: its words were turned into drawing
#: (outlined text, vector art) or it is a drawn page without a raster picture. Measured 2026-10-03 on 38 read
#: books: such pages (layer < 30 characters, no raster image) measure 0.000–0.005 when blank or carrying only a
#: mark, and 0.006–0.4 when their text is outlined (one information book: 118 of 184 pages, 0.03–0.13 typical).
NO_LAYER_CHARS = 30
LAYERLESS_INK_MIN = 0.01


def layerless_with_ink(n_chars: int, n_images: int, ink: float | None) -> bool:
    """OCR reason NO_LAYER_WITH_INK: no usable text layer, no raster picture, but ink on the page (vector
    drawing, text set as outlines). A blank or white page never qualifies. The archive's visual-page choice
    (editor.archive.visual_pages) uses the same rule."""
    return n_chars < NO_LAYER_CHARS and n_images == 0 and ink is not None and ink >= LAYERLESS_INK_MIN


def page_is_layerless_with_ink(page: pymupdf.Page) -> bool:
    """`layerless_with_ink` measured on a PDF page (the ink is rendered only when the layer is short)."""
    if len((page.get_text("text") or "").strip()) >= NO_LAYER_CHARS or page.get_images(full=True):
        return False
    return layerless_with_ink(0, 0, nontext_ink_ratio(page))


def _version_row(book_version_id: str) -> dict:
    bv = db.one("SELECT id, file_path, page_count FROM book_version WHERE id=%s", book_version_id)
    if bv is None:
        raise KeyError(f"book_version {book_version_id} not found")
    return bv


_PNG_END = b"IEND\xaeB`\x82"


def png_complete(path: Path) -> bool:
    """A whole PNG: the signature at the start and the IEND chunk at the end. Measured 2026-10-06: one page
    image of 23.639 was 0 bytes (written while its process died); every reading sent it to the model again and
    the model answered «Failed to load image: cannot identify image file» 24 times in a row, never re-rendered."""
    try:
        size = path.stat().st_size
        if size < 64:
            return False
        with path.open("rb") as f:
            head = f.read(8)
            f.seek(size - 8)
            return head == b"\x89PNG\r\n\x1a\n" and f.read(8) == _PNG_END
    except OSError:
        return False


def _render_to(page: pymupdf.Page, out: Path, long_side_px: int) -> dict:
    """Render once and keep. Written to a temporary name and renamed into place, so a reader (another process
    rendering the same page, a model call) never sees a half-written file; an existing file that is not a whole
    PNG is rendered again."""
    zoom = long_side_px / max(page.rect.width, page.rect.height)
    if not png_complete(out):
        tmp = out.with_name(f".{out.name}.{os.getpid()}.tmp")
        try:
            page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False).save(str(tmp), output="png")
            os.replace(tmp, out)
        finally:
            tmp.unlink(missing_ok=True)
    return {"page_no": page.number + 1, "path": str(out), "dpi": round(72 * zoom)}


def render_file(path: str, page_no: int, long_side_px: int = TARGET_LONG_SIDE_PX) -> dict:
    """Render one page of the PDF at `path` next to it (pages/pNNNN.png, kept). Plain data in and out: runs in
    the worker's PDF processes (editor.pdfproc)."""
    from . import pdfproc
    doc = pdfproc.open_doc(path, repair=False)
    return _render_to(doc[page_no - 1], _pages_dir({"file_path": path}) / f"p{page_no:04d}.png", long_side_px)


def render_page(book_version_id: str, page_no: int, long_side_px: int = TARGET_LONG_SIDE_PX) -> dict:
    """The page's PNG (rendered once). The render runs in the worker's PDF processes when they are on
    (editor.pdfproc): PyMuPDF holds the GIL for the whole render."""
    from . import pdfproc
    return pdfproc.run_sync(render_file, _version_row(book_version_id)["file_path"], page_no, long_side_px)


async def render_page_async(book_version_id: str, page_no: int, long_side_px: int = TARGET_LONG_SIDE_PX) -> dict:
    import asyncio
    from . import pdfproc
    bv = await asyncio.to_thread(_version_row, book_version_id)
    return await pdfproc.run(render_file, bv["file_path"], page_no, long_side_px)


def _page_facts(page: pymupdf.Page, text: str) -> dict:
    """What the manifest measures on one page (no database, no other page)."""
    n_img = len(page.get_images(full=True))
    img_area = 0.0
    for info in page.get_image_info():
        x0, y0, x1, y1 = info["bbox"]
        img_area += max(0.0, x1 - x0) * max(0.0, y1 - y0)
    return {"page_no": page.number + 1, "text": text, "width": page.rect.width, "height": page.rect.height,
            "n_img": n_img, "coverage": min(1.0, img_area / (page.rect.width * page.rect.height)),
            "ink": nontext_ink_ratio(page)}


def manifest_chunk(path: str, page_nos: list[int], long_side_px: int = TARGET_LONG_SIDE_PX) -> list[dict]:
    """Manifest facts + rendered PNG of some pages of the PDF at `path` (a pool task, editor.pdfproc)."""
    from . import pdfproc
    doc = pdfproc.open_doc(path, repair=True)
    plain = pdfproc.open_doc(path, repair=False)
    pages_dir = _pages_dir({"file_path": path})
    out = []
    for i in page_nos:
        page = doc[i - 1]
        f = _page_facts(page, page.get_text("text") or "")
        r = _render_to(plain[i - 1], pages_dir / f"p{i:04d}.png", long_side_px)
        out.append({**f, "path": r["path"], "dpi": r["dpi"]})
    return out


def manifest_rows(bv_id, facts: list[dict]) -> list[tuple]:
    """Page rows from the measured facts: layer health against the whole book, OCR reasons."""
    stem_pages, book_mean = book_stems([f["text"] for f in facts])
    rows = []
    for f in facts:
        text, n_img, ink = f["text"], f["n_img"], f["ink"]
        health = layer_health(text, stem_pages, book_mean)
        n_chars = len(text.strip())
        # OCR when there is no usable text layer on a page that has pictures or other ink
        # (outlined text, vector drawing), or the layer is letter-spaced / broken, or a picture
        # covers most of the page (text drawn inside illustrations is not in the text layer).
        why = [n for n, hit in (("NO_LAYER_WITH_IMAGES", n_chars < NO_LAYER_CHARS and n_img > 0),
                                ("NO_LAYER_WITH_INK", layerless_with_ink(n_chars, n_img, ink)),
                                ("LETTER_SPACED", _spaced_ratio(text) > SPACED_MAX),
                                ("PICTURE_COVERS_PAGE", f["coverage"] > 0.6),
                                ("GARBLED_CHARACTERS", _garbled_ratio(text) > GARBLED_MAX),
                                ("SCRAMBLED_WORDS", health["suspect"]),
                                ("UNUSUAL_VOCABULARY", health.get("unusual_vocabulary", False))) if hit]
        needs_ocr = bool(why)
        # the layer itself cannot be trusted (as opposed to: a picture may hold more text)
        health["layer_unreliable"] = bool(set(why) & {"LETTER_SPACED", "GARBLED_CHARACTERS", "SCRAMBLED_WORDS"})
        health["ocr_reasons"] = why
        rows.append((bv_id, f["page_no"], f["width"], f["height"], n_chars, n_img, needs_ocr,
                     f["path"], f["dpi"], ink, health))
    return rows


def _store_manifest(book_version_id: str, rows: list[tuple]) -> dict:
    rows = [(*r[:10], db.J(r[10])) for r in rows]
    with db.tx() as c:
        for row in rows:
            c.execute(
                "INSERT INTO page(book_version_id, page_no, width_pt, height_pt, text_layer_chars,"
                " image_count, needs_ocr, render_path, render_dpi, nontext_ink, layer_health)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                " ON CONFLICT (book_version_id, page_no) DO UPDATE SET text_layer_chars=EXCLUDED."
                "text_layer_chars, image_count=EXCLUDED.image_count, needs_ocr=EXCLUDED.needs_ocr,"
                " render_path=EXCLUDED.render_path, render_dpi=EXCLUDED.render_dpi,"
                " nontext_ink=EXCLUDED.nontext_ink, layer_health=EXCLUDED.layer_health", row)
    return {"book_version_id": book_version_id, "page_count": len(rows),
            "needs_ocr": [r[1] for r in rows if r[6]],
            "layer_unreliable": [r[1] for r in rows if r[10].obj.get("layer_unreliable")],
            "no_text_layer": [r[1] for r in rows if r[4] < 30]}


def create_page_manifest(book_version_id: str) -> dict:
    """One row per page: size, text-layer size, images, OCR need, rendered PNG (in-process; the reading worker
    uses `create_page_manifest_async`, same rows)."""
    doc, bv = _open_version(book_version_id)
    texts = [page.get_text("text") or "" for page in doc]
    facts = []
    for i, page in enumerate(doc, start=1):
        r = render_page(book_version_id, i)
        facts.append({**_page_facts(page, texts[i - 1]), "path": r["path"], "dpi": r["dpi"]})
    return _store_manifest(book_version_id, manifest_rows(bv["id"], facts))


async def create_page_manifest_async(book_version_id: str) -> dict:
    """`create_page_manifest` with the per-page work in the worker's PDF processes (editor.pdfproc): page text,
    images, ink and the render run there a few pages per task; the database reads and writes in a thread."""
    import asyncio
    from . import pdfproc
    bv = await asyncio.to_thread(_version_row, book_version_id)
    n = await pdfproc.run(pdfproc.page_count, bv["file_path"])
    facts = await pdfproc.map_pages(manifest_chunk, bv["file_path"], range(1, n + 1))
    rows = await pdfproc.run(manifest_rows, bv["id"], facts)
    return await asyncio.to_thread(_store_manifest, book_version_id, rows)


#: A heading font without «ı»: the typesetter sets a shrunken «l» in its place («Bal» 28 pt + «l» 20 pt +
#: «ğ» 28 pt = Balığ…). A lone «l» inside a word, below this share of the preceding letters' size, in a font
#: that carries no «ı», is «ı» (same rule as the BI reading, editorial_desk_structure.pdf_lines).
_SMALL_L = 0.85


def _borrowed_capital_i(spans: list[dict], texts: list[str]) -> None:
    """A small-caps heading font without a dotted small capital: the typesetter borrows «İ» from another
    font of the family («yüreğ» + «İ» + «me», Rüzgârın Ardından). Every other letter of the line is
    lower case (small caps are lower-case letters), the «İ» is a span of its own in another font and
    touches a lower-case letter: it is «i»."""
    lone = [k for k, t in enumerate(texts) if t == "İ"]
    if not lone:
        return
    rest = "".join(t for k, t in enumerate(texts) if k not in lone)
    if not re.search(r"[^\W\d_]", rest) or any(c.isupper() for c in rest):
        return
    for k in lone:
        nb = [j for j in (k - 1, k + 1) if 0 <= j < len(spans) and texts[j].strip()]
        touching = (k > 0 and texts[k - 1][-1:].islower()) or (k + 1 < len(texts) and texts[k + 1][:1].islower())
        # another font (pymupdf shortens long names, so a size of its own also tells the borrowed glyph)
        if nb and touching and all(spans[j]["font"] != spans[k]["font"] or abs(spans[j]["size"] - spans[k]["size"]) > 0.2
                                   for j in nb):
            texts[k] = "i"


def _span_texts(page: pymupdf.Page, spans: list[dict]) -> list[str]:
    texts = [s["text"] for s in spans]
    _borrowed_capital_i(spans, texts)
    repair = getattr(page.parent, "_editor_text_repair", None)
    if not repair:
        return texts
    last = 0.0
    for k, s in enumerate(spans):
        if (s["text"].strip() == "l" and last and s["size"] <= _SMALL_L * last
                and re.search(r"[^\W\d_]$", "".join(texts[:k])) and pdf_repair.font_lacks(repair, s["font"])):
            texts[k] = "ı"
        elif s["text"].strip():
            last = s["size"]
    return texts


def book_letters(doc: pymupdf.Document) -> dict[str, str]:
    """Fontun verisinden onarılamayan karakter → kitabın sözlüğünden harf (pdf_repair.private_letter_map), belge
    başına bir kez, onarılmış (`_open_version`) belgede. Böylece okuma, bölüm başlıkları, Stüdyo ve son okuma aynı
    harfi görür (Aşk Terapi: U+F002 → ş, «¤» → ğ). Onarılmamış belgede (çizim, arşiv) hiçbir şey değişmez."""
    repair = getattr(doc, "_editor_text_repair", None)
    if repair is None:
        return {}
    if "private_letters" not in repair:
        texts = [re.sub(r"[-\xad]\n", "", p.get_text("text") or "") for p in doc]
        repair["private_letters"] = (pdf_repair.private_letter_map(texts)
                                     if any(pdf_repair.unreadable(t) or re.search(f"[{pdf_repair._SUBST}]", t)
                                            for t in texts) else {})
    return repair["private_letters"]


#: Aynı satırda iki parça arasındaki boşluk: kelime arası karakter olarak yok, yalnız konumla verilmiş
#: («dergisinin» | «okurlarına», «devlet» | «dönem»; 2026-10-03, okunmuş kitaplarda yapışık kelime). Puntonun bu
#: katından geniş açıklık kelime arasıdır; harf aralığı, italik/üst simge geçişi ve kerning bunun çok altında kalır.
_SPAN_GAP = 0.15


def _join_spans(spans: list[dict], texts: list[str], horizontal: bool = True) -> str:
    if not horizontal:                    # yan çevrilmiş satırda yatay açıklık ölçü değildir
        return "".join(texts)
    out = ""
    prev = None
    for s, t in zip(spans, texts):
        if (prev is not None and t and out and not out[-1].isspace() and not t[0].isspace()
                and s["bbox"][0] - prev["bbox"][2] > _SPAN_GAP * min(s["size"], prev["size"])):
            out += " "
        out += t
        if t.strip():
            prev = s
    return out


def _page_lines(page: pymupdf.Page) -> list[dict]:
    lines = []
    seen = set()
    letters = book_letters(page.parent) if getattr(page, "parent", None) is not None else {}
    for b in page.get_text("dict", sort=True)["blocks"]:
        for ln in b.get("lines", []):
            # alpha 0 = invisible text (overset frames behind artwork): not on the page
            visible = [s for s in ln["spans"] if s.get("alpha", 255) != 0]
            inked = [k for k, s in enumerate(visible) if s["text"].strip()]
            if not inked:
                continue
            # A word space set in another size than its words («aynada» 10.5 pt + « » 15 pt + «yolculuk»,
            # a heading) comes as a span of its own and was dropped with the empty spans: between two
            # inked spans and in a size of its own it is the word break. Other blank spans stay out
            # (measured on 26 books: keeping all of them changed 641 pages, not all for the better).
            spans = [s for k, s in enumerate(visible) if s["text"].strip() or (
                inked[0] < k < inked[-1] and abs(s["size"] - visible[k - 1]["size"]) > 0.5
                and abs(s["size"] - visible[k + 1]["size"]) > 0.5)]
            text = re.sub(r"\s+", " ", _join_spans(spans, _span_texts(page, spans), abs(ln.get("dir", (1, 0))[0] - 1) < 0.01)).strip()
            if letters:
                text = pdf_repair.apply_private_letters(text, letters)
            # Overprinted glyphs can produce two identical lines at exactly the
            # same coordinates. Preserve repeated prose elsewhere on the page.
            identity = (text, tuple(ln['bbox']))
            if identity in seen:
                continue
            seen.add(identity)
            lines.append({"text": text, "x0": ln["bbox"][0], "y0": ln["bbox"][1], "x1": ln["bbox"][2],
                          "y1": ln["bbox"][3], "size": max(s["size"] for s in spans if s["text"].strip())})
    # Label/value tables (credits, contact details): slightly different font
    # baselines must not interleave the next row's name with the current role.
    # Require a recurring pair of columns, not arbitrary multi-column prose.
    pairs = []
    for i, left in enumerate(lines):
        if len(left['text']) > 35 or left['x1']-left['x0'] > page.rect.width*.3:
            continue
        for j, right in enumerate(lines):
            if i == j or right['x0'] < left['x1'] or right['x0']-left['x1'] > page.rect.width*.15:
                continue
            overlap = min(left['y1'],right['y1'])-max(left['y0'],right['y0'])
            if overlap >= .8*min(left['y1']-left['y0'],right['y1']-right['y0']):
                pairs.append((i,j))
    consumed, merged = set(), []
    for i,j in pairs:
        left,right = lines[i],lines[j]
        peers = [(a,b) for a,b in pairs if abs(lines[a]['x0']-left['x0'])<1
                 and abs(lines[b]['x0']-right['x0'])<1]
        if len(peers)<3 or i in consumed or j in consumed:
            continue
        consumed.update((i,j))
        merged.append({'text':left['text']+' '+right['text'], 'x0':left['x0'],
            'x1':right['x1'],'y0':min(left['y0'],right['y0']),
            'y1':max(left['y1'],right['y1']),'size':max(left['size'],right['size'])})
    lines = [line for i,line in enumerate(lines) if i not in consumed]+merged
    lines.sort(key=lambda line:(line['y0'],line['x0']))
    return lines


def paragraphs_from_layout(page: pymupdf.Page, spaced: bool = False) -> list[str]:
    """Rebuild paragraphs from line geometry. InDesign exports put each line in
    its own block; we re-join lines, undo end-of-line hyphenation, attach drop
    caps, drop page numbers and keep headings (larger type) separate.

    `spaced=True`: a paragraph also starts after a line gap clearly above the line
    step (space-before paragraphs without indent: Çiçekçi Kadın, step 17.9 pt,
    paragraph gap 23.6 pt). Used by book production; the reading keeps the default."""
    lines = _page_lines(page)
    if not lines:
        return []
    sizes = sorted(l["size"] for l in lines)
    body = sizes[len(sizes) // 2]
    h = page.rect.height
    # page numbers: digits only, in the top or bottom margin
    lines = [l for l in lines if not (l["text"].isdigit() and (l["y0"] > h * 0.85 or l["y1"] < h * 0.12))]
    if not lines:
        return []
    # drop caps: one big capital letter; glue it to the nearest line starting lower-case
    caps = [l for l in lines if len(l["text"]) == 1 and l["text"].isupper() and l["size"] > body * 1.6]
    for cap in caps:
        lines.remove(cap)
        near = [l for l in lines if l["text"][:1].islower() and l["y0"] >= cap["y0"] - 2
                and l["y0"] <= cap["y1"] and l["x0"] >= cap["x0"]]
        if near:
            tgt = min(near, key=lambda l: (l["y0"], l["x0"]))
            tgt["text"] = cap["text"] + tgt["text"]
    if not lines:
        return []
    lines.sort(key=lambda l: (round(l["y0"] / 3), l["x0"]))
    gaps = sorted(b["y0"] - a["y0"] for a, b in zip(lines, lines[1:]) if 0 < b["y0"] - a["y0"] < body * 3)
    step = gaps[len(gaps) // 2] if gaps else body * 1.3
    left = min(l["x0"] for l in lines if abs(l["size"] - body) < 0.5) if any(
        abs(l["size"] - body) < 0.5 for l in lines) else min(l["x0"] for l in lines)
    paras: list[str] = []
    cur = ""
    prev = None
    for l in lines:
        heading = l["size"] > body * 1.2
        new = prev is None
        if prev is not None:
            gap = l["y0"] - prev["y0"]
            prev_heading = prev["size"] > body * 1.2
            indented = l["x0"] - left > 6 and prev["text"][-1:] in ".!?”\"…:"
            spaced_gap = spaced and gap > step + max(3.0, body * 0.25) and prev["text"][-1:] in ".!?”\"…:»"
            new = (heading != prev_heading) or gap > step * 1.6 or gap < -step or indented or spaced_gap
        if new:
            if cur:
                paras.append(cur)
            cur = l["text"]
        elif re.search(r"\w[-­]$", cur) and l["text"][:1].islower():
            cur = cur[:-1] + l["text"]
        else:
            cur = f"{cur} {l['text']}"
        prev = l
    if cur:
        paras.append(cur)
    return [re.sub(r"\s+", " ", _SPACED.sub(lambda m: m.group(0).replace(" ", ""), p)).strip()
            for p in paras if p.strip()]


def _layer_paragraphs(doc: pymupdf.Document, page_nos) -> dict[int, list[str]]:
    book = {}
    for i in page_nos:
        page = doc[i - 1]
        if _garbled_ratio(page.get_text("text") or "") > 0.02:
            continue  # unreadable encoding: OCR provides this page's paragraphs
        paras = paragraphs_from_layout(page)
        if paras:
            book[i] = paras
    return book


def text_layer_chunk(path: str, page_nos: list[int]) -> list[tuple[int, list[str]]]:
    """Paragraphs of some pages of the PDF at `path` (a pool task, editor.pdfproc)."""
    from . import pdfproc
    return list(_layer_paragraphs(pdfproc.open_doc(path, repair=True), page_nos).items())


def mend_private_letters(book: dict[int, list[str]]) -> dict[int, list[str]]:
    """A private-use character the fonts' own data could not mend: the book's own vocabulary decides."""
    letters = pdf_repair.private_letter_map([p for paras in book.values() for p in paras])
    return {i: [pdf_repair.apply_private_letters(p, letters) for p in paras] for i, paras in book.items()}


def _store_text_layer(generation_id: str, book_version_id: str, book: dict[int, list[str]]) -> int:
    pages_with_text = 0
    with db.tx() as c:
        for i, paras in book.items():
            pages_with_text += 1
            c.execute("INSERT INTO page_text(generation_id, book_version_id, page_no, source, text)"
                      " VALUES (%s,%s,%s,'TEXT_LAYER',%s) ON CONFLICT DO NOTHING",
                      (generation_id, book_version_id, i, "\n\n".join(paras)))
            for k, t in enumerate(paras, start=1):
                c.execute("INSERT INTO paragraph(generation_id, page_no, idx, text, source)"
                          " VALUES (%s,%s,%s,%s,'TEXT_LAYER') ON CONFLICT DO NOTHING",
                          (generation_id, i, k, t))
    return pages_with_text


def extract_text_layer(generation_id: str, book_version_id: str) -> dict:
    """Page text + paragraphs from the PDF text layer (rebuilt from line layout). In-process; the reading
    worker uses `extract_text_layer_async` (same rows)."""
    doc, _ = _open_version(book_version_id)
    book = mend_private_letters(_layer_paragraphs(doc, range(1, doc.page_count + 1)))
    return {"pages_with_text": _store_text_layer(generation_id, book_version_id, book), "page_count": doc.page_count}


async def extract_text_layer_async(generation_id: str, book_version_id: str) -> dict:
    """`extract_text_layer` with the page work in the worker's PDF processes (editor.pdfproc) and the database
    writes in a thread."""
    import asyncio
    from . import pdfproc
    bv = await asyncio.to_thread(_version_row, book_version_id)
    n = await pdfproc.run(pdfproc.page_count, bv["file_path"])
    book = dict(await pdfproc.map_pages(text_layer_chunk, bv["file_path"], range(1, n + 1)))
    book = await pdfproc.run(mend_private_letters, book)
    return {"pages_with_text": await asyncio.to_thread(_store_text_layer, generation_id, book_version_id, book),
            "page_count": n}


async def run_ocr(generation_id: str, book_version_id: str, page_no: int) -> dict:
    """OCR one page with book-vision-fast (Qwen3-VL OCR). Stored as source OCR;
    legacy paragraph cache is retained; source.py reads both original sources.

    Nothing here blocks the caller's loop: the render runs in the PDF processes (editor.pdfproc), file and
    database work in threads, only the model call is awaited here."""
    import asyncio
    r = await render_page_async(book_version_id, page_no)
    png = await asyncio.to_thread(Path(r["path"]).read_bytes)
    s = settings()
    if s.ocr_alias == "book-vision-fast":
        # the general VLM: our prompt and block schema
        ref, body = await asyncio.to_thread(prompts.render, "ocr_page", page_no=str(page_no))
        out, call_id = await Llm(generation_id).chat(
            s.ocr_alias,
            [{"role": "user", "content": [image_part(png), {"type": "text", "text": body}]}],
            prompt=ref, schema=schemas.OCR, pages=[page_no], max_tokens=4096, temperature=0.0)
        blocks = [b for b in out["blocks"] if b["text"].strip()]
    else:
        # an OCR specialist: its own task prompt, plain text. No layout kinds come with it,
        # so every paragraph is body text.
        text, call_id = await Llm(generation_id).chat(
            s.ocr_alias,
            [{"role": "user", "content": [image_part(png), {"type": "text", "text": s.ocr_prompt}]}],
            pages=[page_no], max_tokens=4096, temperature=0.0)
        text = re.sub(r"<[^>]+>", " ", text)
        blocks = [{"text": b.strip(), "kind": "body"} for b in re.split(r"\n\s*\n", text) if b.strip()]
    return await asyncio.to_thread(_store_ocr, generation_id, book_version_id, page_no, blocks, call_id)


def _store_ocr(generation_id: str, book_version_id: str, page_no: int, blocks: list[dict], call_id) -> dict:
    cut = 0
    for b in blocks:
        b["text"], n = _collapse_repeats(b["text"].strip())
        cut += n
    text = "\n\n".join(b["text"].strip() for b in blocks)
    with db.tx() as c:
        # Empty OCR is a completed observation, not a missing execution.
        c.execute("INSERT INTO page_text(generation_id, book_version_id, page_no, source, text,"
                  " model_call_id) VALUES (%s,%s,%s,'OCR',%s,%s) ON CONFLICT DO NOTHING",
                  (generation_id, book_version_id, page_no, text, call_id))
        has_layer = c.execute("SELECT 1 FROM paragraph WHERE generation_id=%s AND page_no=%s "
                              "AND source='TEXT_LAYER' LIMIT 1", (generation_id, page_no)).fetchone()
        if not has_layer:
            for k, b in enumerate(blocks, start=1):
                c.execute("INSERT INTO paragraph(generation_id, page_no, idx, text, source)"
                          " VALUES (%s,%s,%s,%s,'OCR') ON CONFLICT DO NOTHING",
                          (generation_id, page_no, k, b["text"].strip()))
    return {"page_no": page_no, "blocks": len(blocks), "chars": len(text), "loop_chars_removed": cut,
            "in_image_text": [b["text"] for b in blocks if b["kind"] not in ("body", "heading")]}


def page_text_numbered(generation_id: str, page_no: int) -> str:
    try:
        return source.numbered(source.read(generation_id,page_no)[0])
    except KeyError:
        # Existing context callers ask for the neighbouring page past the book.
        return "(sayfa yok)"


