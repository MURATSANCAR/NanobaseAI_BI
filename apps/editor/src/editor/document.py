"""book_document tools: intake, page manifest, text layer, rendering, OCR."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pymupdf

from . import db, prompts, schemas, source
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
                 age_group: str | None = None) -> dict:
    """Creates (or finds) the book and its content version (sha256 of the file)."""
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
                         (title,)).fetchone()
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


def _open_version(book_version_id: str) -> tuple[pymupdf.Document, dict]:
    bv = db.one("SELECT * FROM book_version WHERE id=%s", book_version_id)
    if bv is None:
        raise KeyError(f"book_version {book_version_id} not found")
    return pymupdf.open(bv["file_path"]), bv


def _pages_dir(bv: dict) -> Path:
    d = Path(bv["file_path"]).parent / "pages"
    d.mkdir(parents=True, exist_ok=True)
    return d


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
    z = 100 / 72
    pm = page.get_pixmap(matrix=pymupdf.Matrix(z, z), colorspace=pymupdf.csGRAY, alpha=False)
    w, h, buf = pm.width, pm.height, bytearray(pm.samples)
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            if not any(sp["text"].strip() and sp.get("alpha", 255) != 0 for sp in ln["spans"]):
                continue
            x0, y0, x1, y1 = (int(v * z) for v in ln["bbox"])
            xa, xb = max(0, x0 - 2), min(w, x1 + 2)
            for y in range(max(0, y0 - 2), min(h, y1 + 2)):
                buf[y * w + xa: y * w + xb] = b"\xff" * (xb - xa)
    mx, my = int(w * .08), int(h * .08)
    ink = sum(1 for y in range(my, h - my) for v in buf[y * w + mx: y * w + w - mx] if v < 235)
    return ink / max(1, (w - 2 * mx) * (h - 2 * my))


def region_ink_ratio(png_path: str, bbox: list[int]) -> float:
    """Ink share inside a model-given bbox (0..1000 normalised) of a rendered page."""
    if not bbox or len(bbox) != 4 or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        return 0.0
    pm = pymupdf.Pixmap(pymupdf.csGRAY, pymupdf.Pixmap(png_path))
    w, h, buf = pm.width, pm.height, pm.samples
    x0, x1 = int(bbox[0] / 1000 * w), max(int(bbox[2] / 1000 * w), int(bbox[0] / 1000 * w) + 1)
    y0, y1 = int(bbox[1] / 1000 * h), max(int(bbox[3] / 1000 * h), int(bbox[1] / 1000 * h) + 1)
    ink = sum(1 for y in range(y0, min(h, y1)) for v in buf[y * w + x0: y * w + min(w, x1)] if v < 235)
    return ink / max(1, (min(w, x1) - x0) * (min(h, y1) - y0))


def render_page(book_version_id: str, page_no: int, long_side_px: int = TARGET_LONG_SIDE_PX) -> dict:
    doc, bv = _open_version(book_version_id)
    page = doc[page_no - 1]
    zoom = long_side_px / max(page.rect.width, page.rect.height)
    out = _pages_dir(bv) / f"p{page_no:04d}.png"
    if not out.exists():
        page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False).save(out)
    return {"page_no": page_no, "path": str(out), "dpi": round(72 * zoom)}


def create_page_manifest(book_version_id: str) -> dict:
    """One row per page: size, text-layer size, images, OCR need, rendered PNG."""
    doc, bv = _open_version(book_version_id)
    rows = []
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text") or ""
        n_chars = len(text.strip())
        n_img = len(page.get_images(full=True))
        img_area = 0.0
        for info in page.get_image_info():
            x0, y0, x1, y1 = info["bbox"]
            img_area += max(0.0, x1 - x0) * max(0.0, y1 - y0)
        coverage = min(1.0, img_area / (page.rect.width * page.rect.height))
        # OCR when there is no usable text layer on a page that has pictures, or
        # the layer is letter-spaced / broken, or a picture covers most of the page
        # (text drawn inside illustrations is not in the text layer).
        needs_ocr = ((n_chars < 30 and n_img > 0) or _spaced_ratio(text) > 0.3 or coverage > 0.6
                     or _garbled_ratio(text) > 0.02)
        r = render_page(book_version_id, i)
        rows.append((bv["id"], i, page.rect.width, page.rect.height, n_chars, n_img, needs_ocr,
                     r["path"], r["dpi"], nontext_ink_ratio(page)))
    with db.tx() as c:
        for row in rows:
            c.execute(
                "INSERT INTO page(book_version_id, page_no, width_pt, height_pt, text_layer_chars,"
                " image_count, needs_ocr, render_path, render_dpi, nontext_ink) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                " ON CONFLICT (book_version_id, page_no) DO UPDATE SET text_layer_chars=EXCLUDED."
                "text_layer_chars, image_count=EXCLUDED.image_count, needs_ocr=EXCLUDED.needs_ocr,"
                " render_path=EXCLUDED.render_path, render_dpi=EXCLUDED.render_dpi,"
                " nontext_ink=EXCLUDED.nontext_ink", row)
    return {"book_version_id": book_version_id, "page_count": len(rows),
            "needs_ocr": [r[1] for r in rows if r[6]],
            "no_text_layer": [r[1] for r in rows if r[4] < 30]}


def _page_lines(page: pymupdf.Page) -> list[dict]:
    lines = []
    for b in page.get_text("dict", sort=True)["blocks"]:
        for ln in b.get("lines", []):
            # alpha 0 = invisible text (overset frames behind artwork): not on the page
            spans = [s for s in ln["spans"] if s["text"].strip() and s.get("alpha", 255) != 0]
            if not spans:
                continue
            text = re.sub(r"\s+", " ", "".join(s["text"] for s in spans)).strip()
            lines.append({"text": text, "x0": ln["bbox"][0], "y0": ln["bbox"][1], "x1": ln["bbox"][2],
                          "y1": ln["bbox"][3], "size": max(s["size"] for s in spans)})
    return lines


def paragraphs_from_layout(page: pymupdf.Page) -> list[str]:
    """Rebuild paragraphs from line geometry. InDesign exports put each line in
    its own block; we re-join lines, undo end-of-line hyphenation, attach drop
    caps, drop page numbers and keep headings (larger type) separate."""
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
            new = (heading != prev_heading) or gap > step * 1.6 or gap < -step or indented
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


def extract_text_layer(generation_id: str, book_version_id: str) -> dict:
    """Page text + paragraphs from the PDF text layer (rebuilt from line layout)."""
    doc, _ = _open_version(book_version_id)
    pages_with_text = 0
    with db.tx() as c:
        for i, page in enumerate(doc, start=1):
            if _garbled_ratio(page.get_text("text") or "") > 0.02:
                continue  # unreadable encoding: OCR provides this page's paragraphs
            paras = paragraphs_from_layout(page)
            if not paras:
                continue
            pages_with_text += 1
            c.execute("INSERT INTO page_text(generation_id, book_version_id, page_no, source, text)"
                      " VALUES (%s,%s,%s,'TEXT_LAYER',%s) ON CONFLICT DO NOTHING",
                      (generation_id, book_version_id, i, "\n\n".join(paras)))
            for k, t in enumerate(paras, start=1):
                c.execute("INSERT INTO paragraph(generation_id, page_no, idx, text, source)"
                          " VALUES (%s,%s,%s,%s,'TEXT_LAYER') ON CONFLICT DO NOTHING",
                          (generation_id, i, k, t))
    return {"pages_with_text": pages_with_text, "page_count": doc.page_count}


async def run_ocr(generation_id: str, book_version_id: str, page_no: int) -> dict:
    """OCR one page with book-vision-fast (Qwen3-VL OCR). Stored as source OCR;
    becomes the page's paragraphs only if the text layer had none."""
    r = render_page(book_version_id, page_no)
    png = Path(r["path"]).read_bytes()
    ref, body = prompts.render("ocr_page", page_no=str(page_no))
    out, call_id = await Llm(generation_id).chat(
        "book-vision-fast",
        [{"role": "user", "content": [image_part(png), {"type": "text", "text": body}]}],
        prompt=ref, schema=schemas.OCR, pages=[page_no], max_tokens=4096, temperature=0.0)
    blocks = [b for b in out["blocks"] if b["text"].strip()]
    text = "\n\n".join(b["text"].strip() for b in blocks)
    with db.tx() as c:
        if text:
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
    return {"page_no": page_no, "blocks": len(blocks), "chars": len(text),
            "in_image_text": [b["text"] for b in blocks if b["kind"] not in ("body", "heading")]}


def page_text_numbered(generation_id: str, page_no: int) -> str:
    try:
        return source.numbered(source.read(generation_id,page_no)[0])
    except KeyError:
        # Existing context callers ask for the neighbouring page past the book.
        return "(sayfa yok)"


def get_page_bundle(generation_id: str, page_no: int) -> dict:
    """Everything the ledger knows about one page (no image bytes)."""
    gen = db.one("SELECT book_version_id FROM generation WHERE id=%s", generation_id)
    if gen is None:
        raise KeyError(f"generation {generation_id} not found")
    page = db.one("SELECT page_no, width_pt, height_pt, text_layer_chars, image_count, needs_ocr,"
                  " render_path FROM page WHERE book_version_id=%s AND page_no=%s",
                  gen["book_version_id"], page_no)
    reading = source.read(generation_id,page_no)[0]
    return {
        "page": page,
        "source_reading": reading,
        "paragraphs": reading["spans"],
        "legacy_paragraphs": db.all_rows("SELECT idx, text, source FROM paragraph WHERE generation_id=%s"
                                  " AND page_no=%s ORDER BY idx", generation_id, page_no),
        "ocr": db.one("SELECT text FROM page_text WHERE generation_id=%s AND page_no=%s AND "
                      "source='OCR'", generation_id, page_no),
        "scans": db.all_rows("SELECT pass, alias, uncertain, uncertainty_reasons, result FROM "
                             "page_scan WHERE generation_id=%s AND page_no=%s ORDER BY pass",
                             generation_id, page_no),
        "regions": db.all_rows("SELECT id, label, kind, bbox, description FROM visual_region "
                               "WHERE generation_id=%s AND page_no=%s", generation_id, page_no),
    }
