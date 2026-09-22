"""Sayfa düzeni — final-read layout problems, measured from the PDF's geometry and renders.

Deterministic throughout (no model): every finding carries the measurement that produced it.

  folio      printed page numbers vs physical page order: a folio that breaks the book's
             constant offset (missing/duplicated/misordered pages), odd folios on left pages
  margin     text closer to the trim edge than the printer's safe zone (TrimBox from the PDF;
             the page edge when the PDF has none); the binding side separately
  body       running text in a size or line spacing different from the rest of the book
  age        running text x-height (measured on the render, mm) below the conventional value
             for the youngest reader of the declared age band (AGE_RANGE in the catalogue)
  widow      a paragraph's last line alone at the top of a page (dul satır)
  orphan     a paragraph's first line alone at the bottom of a page (öksüz satır)
  contrast   text whose colour against the illustration under it fails WCAG 1.4.3
             (text colour and background both measured on renders: the page as printed and
             the same page with its text removed)

Thresholds and the measurements behind them: docs/son-okuma/layout.md.
"""

from __future__ import annotations

import re
import statistics as st

import numpy as np
import pymupdf

from .. import db
from ._layout_lines import Line, body_style, book, norm_bbox, page_lines, unreliable

NAME = "layout"
VERSION = "1"
LABEL = "Sayfa düzeni"

MM = 72 / 25.4
SAFE_MM = 5.0            # printers' safe zone inside the trim (3-6 mm quoted; 5 mm the common spec)
GUTTER_MM = 10.0         # binding side: perfect binding hides 3-6 mm, plus the safe zone
SIZE_TOL_PT = 0.5        # body size difference a reader notices (0.2-0.3 pt scaling is invisible)
LEAD_TOL = 0.08          # line spacing differing by more than 8% from the book's for that size
WCAG_NORMAL, WCAG_LARGE = 4.5, 3.0
RENDER_ZOOM = 150 / 72   # 150 dpi: enough for glyph-level masks at body sizes >= 9 pt


# ------------------------------------------------------------------ helpers
def _ink(l: Line) -> int:
    return sum(1 for c, _ in l.chars if not c.isspace())


def _is_body(l: Line, font: str, size: float) -> bool:
    """A line of running text: at least part of it in the book's body font and size (a line
    may end a lettered speech bubble phrase in a display font and still be running text)."""
    return not l.text.strip().isdigit() and any(
        f == font and abs(sz - size) <= 1.0 and t.strip() for t, sz, f, _, _ in l.spans)


def _age_band(generation_id: str) -> tuple[int | None, int | None, str | None]:
    rows = db.all_rows("SELECT claim FROM claim WHERE generation_id=%s AND kind='METADATA'"
                       " AND subject='AGE_RANGE' AND status IN ('VERIFIED','EDITOR_APPROVED','EDITOR_CORRECTED')",
                       generation_id) or []
    text = " ".join(r["claim"] for r in rows)
    if not text:
        b = db.one("SELECT b.age_group FROM book b JOIN book_version v ON v.book_id=b.id"
                   " JOIN generation g ON g.book_version_id=v.id WHERE g.id=%s", generation_id)
        text = (b or {}).get("age_group") or ""
    nums = [int(n) for n in re.findall(r"\d{1,2}", text)]
    return (min(nums), max(nums), text) if nums else (None, None, None)


def conventional_xheight_mm(age: int) -> float:
    """x-height conventionally printed for a reader of this age: about 4 mm at 5 falling to
    adult size (about 2 mm) at 11 (Hughes & Wilkins 2000; Wilkins et al. 2009, J. Res. Reading
    32:402). Wilkins et al. argue these are already too small; used here as a floor."""
    return max(2.0, 4.0 - (age - 5) * (2.0 / 6.0))


def _lum(rgb: np.ndarray) -> np.ndarray:
    """WCAG relative luminance of sRGB 0..255 pixels."""
    c = rgb.astype(np.float32) / 255.0
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]


def _contrast(a, b):
    hi, lo = np.maximum(a, b), np.minimum(a, b)
    return (hi + 0.05) / (lo + 0.05)


def _pix(page: pymupdf.Page, zoom: float, clip=None) -> np.ndarray:
    pm = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csRGB, alpha=False,
                         clip=clip)
    return np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.height, pm.width, 3)


# ------------------------------------------------------------------ folios
def _folios(doc, LP) -> tuple[dict[int, tuple[int, Line]], dict]:
    """Page numbers: digit-only lines in the top or bottom 15% of the trim, in the style
    (font, size) most such lines share. Returns {page: (number, line)}."""
    cands = []
    for p, lines in LP.items():
        t = doc[p - 1].trimbox
        for l in lines:
            s = l.text.strip()
            if s.isdigit() and len(s) <= 4 and (l.y1 < t.y0 + t.height * 0.15 or l.y0 > t.y1 - t.height * 0.15):
                cands.append((p, int(s), l))
    styles: dict = {}
    for p, n, l in cands:
        styles[(l.font, round(l.size))] = styles.get((l.font, round(l.size)), 0) + 1
    if not styles:
        return {}, {}
    style = max(styles, key=styles.get)
    out = {}
    for p, n, l in cands:
        if (l.font, round(l.size)) == style and p not in out:
            out[p] = (n, l)
    return out, {"font": style[0], "size": style[1]}


def check_folios(doc, LP, add) -> dict:
    fol, style = _folios(doc, LP)
    if len(fol) < 3:
        return {"folios": len(fol)}
    offsets = [n - p for p, (n, _) in fol.items()]
    mode = max(set(offsets), key=offsets.count)
    seen: dict[int, int] = {}
    for p, (n, l) in sorted(fol.items()):
        if n in seen:
            add(p, "ERROR", f"Sayfa numarası {n} iki kez basılmış (s.{seen[n]} ve s.{p}).", str(n), l.bbox,
                rule="folio_duplicate", printed=n, other_page=seen[n])
        elif n - p != mode:
            add(p, "ERROR", f"Sayfa numarası sırası bozuk: bu fiziksel sayfada {p + mode} beklenirken"
                f" {n} basılmış.", str(n), l.bbox, suggestion=str(p + mode), rule="folio_sequence",
                printed=n, expected=p + mode)
        seen.setdefault(n, p)
    # odd folios belong on right-hand (recto) pages; PDF page 1 is a recto
    if mode % 2 == 1:
        p0 = min(fol)
        add(p0, "WARN", "Tek sayfa numaraları sol (çift) sayfalara düşüyor; kitapta tek numaralar"
            " sağ sayfada olur.", str(fol[p0][0]), fol[p0][1].bbox, rule="folio_parity", offset=mode)
    # position: the same height on every page, mirrored or centred horizontally
    ys = [l.baseline for _, l in fol.values()]
    ymode = st.median(ys)
    for p, (n, l) in fol.items():
        if abs(l.baseline - ymode) > 2.0:
            add(p, "INFO", f"Sayfa numarası diğer sayfalardan farklı yükseklikte"
                f" ({abs(l.baseline - ymode) / MM:.1f} mm).", str(n), l.bbox, rule="folio_position")
    return {"folios": len(fol), "folio_offset": mode, "folio_style": style}


# ------------------------------------------------------------------ margins
def check_margins(doc, LP, add) -> dict:
    closest = []
    for p, lines in LP.items():
        page = doc[p - 1]
        t = page.trimbox if page.trimbox and page.trimbox.width > 0 else page.rect
        recto = p % 2 == 1
        for l in lines:
            d = {"top": l.y0 - t.y0, "bottom": t.y1 - l.y1,
                 "gutter": (l.x0 - t.x0) if recto else (t.x1 - l.x1),
                 "outer": (t.x1 - l.x1) if recto else (l.x0 - t.x0)}
            side = min(d, key=d.get)
            mm = d[side] / MM
            closest.append(mm)
            limit = GUTTER_MM if side == "gutter" else SAFE_MM
            if mm < 0:
                add(p, "ERROR", f"Metin kesim çizgisinin dışına taşıyor ({side_tr(side)}, {mm:.1f} mm).",
                    l.text[:60], l.bbox, rule="margin_outside_trim", side=side, mm=round(mm, 1))
            elif mm < limit:
                add(p, "WARN", f"Metin kesim çizgisine {mm:.1f} mm yakın ({side_tr(side)}; güvenli alan"
                    f" {limit:.0f} mm).", l.text[:60], l.bbox, rule="margin_safe_zone", side=side,
                    mm=round(mm, 1), limit_mm=limit)
    closest.sort()
    return {"margin_mm_min": round(closest[0], 1) if closest else None,
            "margin_mm_p05": round(closest[len(closest) // 20], 1) if closest else None}


def side_tr(side: str) -> str:
    return {"top": "üst", "bottom": "alt", "gutter": "cilt payı tarafı", "outer": "dış kenar"}[side]


# ------------------------------------------------------------------ body text consistency
def check_body(doc, LP, font, size, add) -> dict:
    """Pages whose running text (the book's body font) is set in another size or leading."""
    per_page = {}
    lead_all: dict[float, list[float]] = {}
    for p, lines in LP.items():
        body = [l for l in lines if l.font == font and not l.text.strip().isdigit()]
        if sum(_ink(l) for l in body) < 80:          # a caption or a few words: not a text page
            continue
        w: dict[float, int] = {}
        for l in body:
            w[round(l.size, 1)] = w.get(round(l.size, 1), 0) + _ink(l)
        psize = max(w, key=w.get)
        main = [l for l in body if abs(l.size - psize) < 0.05]
        leads = [b.baseline - a.baseline for a, b in zip(main, main[1:])
                 if 0.8 * psize < b.baseline - a.baseline < 1.9 * psize
                 and min(a.x1, b.x1) > max(a.x0, b.x0)]
        per_page[p] = (psize, st.median(leads) if len(leads) >= 3 else None, main)
        if len(leads) >= 3:
            lead_all.setdefault(round(psize), []).append(st.median(leads))
    book_lead = {s: st.median(v) for s, v in lead_all.items()}
    for p, (psize, lead, main) in per_page.items():
        bb = (min(l.x0 for l in main), min(l.y0 for l in main), max(l.x1 for l in main),
              max(l.y1 for l in main))
        if abs(psize - size) >= SIZE_TOL_PT:
            add(p, "WARN", f"Gövde metni bu sayfada {psize:g} pt; kitabın geri kalanında {size:g} pt.",
                main[0].text[:60], bb, rule="body_size", size=psize, book_size=size)
        ref = book_lead.get(round(psize))
        if lead and ref and abs(lead - ref) / ref > LEAD_TOL:
            add(p, "WARN", f"Satır aralığı bu sayfada {lead:.1f} pt; kitapta aynı puntoda {ref:.1f} pt"
                f" (%{abs(lead - ref) / ref * 100:.0f} fark).", main[0].text[:60], bb, rule="leading",
                leading=round(lead, 1), book_leading=round(ref, 1))
    return {"body_font": font, "body_size": size, "body_pages": len(per_page),
            "book_leading": {str(k): round(v, 2) for k, v in book_lead.items()}}


# ------------------------------------------------------------------ x-height vs age
def measure_xheight(doc, LP, font, size, limit: int = 0) -> float | None:
    """Median x-height (mm) of the body font, measured on 600 dpi renders of x-height letters
    (no ascender/descender) over plain background."""
    zoom = 600 / 72
    hs = []
    for p, lines in LP.items():
        for l in lines:
            if l.font != font or abs(l.size - size) > 0.3:
                continue
            for c, bb in l.chars:
                if c not in "xzvwunmrcsaeo":
                    continue
                img = _pix(doc[p - 1], zoom, pymupdf.Rect(bb)).astype(np.float32).mean(axis=2)
                if img.size == 0:
                    continue
                bg = np.median(img)
                ink = np.abs(img - bg) > 0.4 * max(1.0, abs(img.min() - bg), abs(img.max() - bg))
                rows = np.where(ink.sum(axis=1) > 0)[0]
                if len(rows) == 0:
                    continue
                hs.append((rows[-1] - rows[0] + 1) / zoom / MM)
                if len(hs) >= 60:
                    return round(st.median(hs), 2)
    return round(st.median(hs), 2) if len(hs) >= 10 else None


def check_age(generation_id, doc, LP, font, size, add) -> dict:
    lo, hi, band = _age_band(generation_id)
    xh = measure_xheight(doc, LP, font, size)
    out = {"age_band": band, "body_xheight_mm": xh}
    if lo is None or xh is None:
        return out
    need = conventional_xheight_mm(lo)
    out["conventional_xheight_mm"] = round(need, 2)
    if xh < need * 0.9:
        first = min(p for p, ls in LP.items() if any(l.font == font for l in ls))
        l0 = next(l for l in LP[first] if l.font == font)
        add(first, "WARN", f"Gövde metninin x-yüksekliği {xh:.1f} mm ({size:g} pt); {band} için en küçük"
            f" okur ({lo} yaş) kitaplarında alışılan yaklaşık {need:.1f} mm.", l0.text[:60], l0.bbox,
            rule="age_type_size", xheight_mm=xh, conventional_mm=round(need, 2), age_min=lo)
    return out


# ------------------------------------------------------------------ widows / orphans
_END = re.compile(r"[.!?…:”\"»)]\s*$")
_OPEN = tuple("–—-“\"«")


def para_end(line: Line, nxt: Line | None, size: float) -> bool:
    """Does `line` end its paragraph? It must end a sentence, and the next line must show a
    new paragraph: a dialogue dash/quote, a first-line indent (relative to `line`, so text
    wrapped around a picture does not look indented), or `line` stops short of the next
    line's right edge (justified text). With no next line, the sentence end decides."""
    if not _END.search(line.text):
        return False
    if nxt is None:
        return True
    return (nxt.text.startswith(_OPEN) or nxt.x0 - line.x0 > size * 0.6
            or line.x1 < nxt.x1 - size * 1.5 or nxt.baseline - line.baseline > size * 2.2)


def check_widows(doc, LP, font, size, add) -> dict:
    """Across each page break, in the book's running text: orphan = the paragraph's first line
    is the only one on the page; widow = its last line is the only one on the next page."""
    pages = sorted(LP)
    body = {p: [l for l in LP[p] if _is_body(l, font, size)] for p in pages}
    n_w = n_o = 0
    for p in pages:
        cur, nxt = body.get(p) or [], body.get(p + 1) or []
        if len(cur) < 2 or len(nxt) < 2:
            continue
        last, first = cur[-1], nxt[0]
        if para_end(last, first, size) or not (first.text[:1].islower() or last.text.endswith(("-", "\u00ad"))
                                                or not _END.search(last.text)):
            continue                                   # the paragraph does not run over the break
        if para_end(cur[-2], last, size):
            n_o += 1
            add(p, "WARN", "Öksüz satır: paragrafın ilk satırı sayfanın sonunda tek başına kalmış"
                f" (paragraf s.{p + 1}'de devam ediyor).", last.text[:60], last.bbox, rule="orphan",
                next_page=p + 1)
        if para_end(first, nxt[1], size):
            n_w += 1
            add(p + 1, "WARN", "Dul satır: paragrafın son satırı sayfanın başında tek başına kalmış"
                f" (paragraf s.{p}'de başlıyor).", first.text[:60], first.bbox, rule="widow", prev_page=p)
    return {"widows": n_w, "orphans": n_o}


# ------------------------------------------------------------------ contrast
def _textless(doc_path: str, p: int) -> pymupdf.Page:
    d = pymupdf.open(doc_path)
    page = d[p - 1]
    page.add_redact_annot(page.rect)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
    page._keep_doc = d                                  # keep the document alive with the page
    return page


def _runs(l: Line) -> list[tuple[str, int, tuple]]:
    """A line split into colour runs: (text, sRGB colour, bbox)."""
    out: list[list] = []
    for text, size, font, color, bb in l.spans:
        if out and out[-1][1] == color:
            r = out[-1]
            r[0] += text
            r[2] = (min(r[2][0], bb[0]), min(r[2][1], bb[1]), max(r[2][2], bb[2]), max(r[2][3], bb[3]))
        else:
            out.append([text, color, tuple(bb)])
    return [tuple(r) for r in out if sum(ch.isalpha() for ch in r[0]) >= 2]


def run_contrast(printed: np.ndarray, bare: np.ndarray, bb, baseline: float, size: float,
                 zoom: float) -> dict | None:
    """Text colour = glyph-core pixels that change when the text is removed; background = the
    text-free render under the run's x-height band. WCAG contrasts: median and worst 10%."""
    H, W = printed.shape[:2]
    x0, x1 = max(0, int(bb[0] * zoom)), min(W, int(bb[2] * zoom) + 1)
    y0, y1 = max(0, int((baseline - size * 0.55) * zoom)), min(H, int(baseline * zoom) + 1)
    if x1 - x0 < 4 or y1 - y0 < 3:
        return None
    a = printed[y0:y1, x0:x1].astype(np.int16)
    b = bare[y0:y1, x0:x1].astype(np.int16)
    d = np.abs(a - b).max(axis=2)
    changed = d > 40
    if changed.sum() < 12:
        return {"hidden": True}
    core = changed & (d >= np.percentile(d[changed], 60))   # anti-aliased edges mix ink and paper
    text_l = float(np.median(_lum(a[core].astype(np.uint8))))
    bg_l = _lum(b.astype(np.uint8)).ravel()
    c = _contrast(text_l, bg_l)
    return {"hidden": False, "text_lum": round(text_l, 3), "bg_lum_med": round(float(np.median(bg_l)), 3),
            "bg_lum_sd": round(float(bg_l.std()), 3), "c_med": round(float(np.median(c)), 2),
            "c_p10": round(float(np.percentile(c, 10)), 2)}


def measure_contrast(doc, bv, LP, zoom: float = RENDER_ZOOM) -> list[dict]:
    out = []
    for p, lines in LP.items():
        cand = [l for l in lines if not l.stroked_only and _ink(l) >= 2]
        if not cand:
            continue
        printed = _pix(doc[p - 1], zoom)
        bare = _pix(_textless(bv["file_path"], p), zoom)
        for l in cand:
            for text, color, bb in _runs(l):
                m = run_contrast(printed, bare, bb, l.baseline, l.size, zoom)
                if m is None:
                    continue
                m.update(page=p, line=l, text=text, color=f"#{color:06x}", bbox=bb,
                         large=l.size >= 18 or (l.size >= 14 and l.bold))
                out.append(m)
    return out


def check_contrast(doc, bv, LP, add) -> dict:
    """One finding per page and text colour (a page sets all its speech in one colour: one
    finding, not one per line). Severity from WCAG 1.4.3: under 3:1 (the floor even for large
    text) WARN; under 4.5:1 for text smaller than 18 pt (14 pt bold) INFO. A run whose median
    passes but whose worst 10% of background falls under 3:1 sits partly on a dark/light patch
    of the picture: INFO."""
    ms = measure_contrast(doc, bv, LP)
    groups: dict = {}
    n_hidden = 0
    for m in ms:
        p = m["page"]
        if m["hidden"]:
            n_hidden += 1
            add(p, "WARN", "Metin sayfada görünmüyor: resmin ya da başka bir nesnenin altında kalmış olabilir.",
                m["text"][:60], m["bbox"], rule="text_hidden")
            continue
        if m["line"].outlined:
            continue                                   # an outline around the letters carries the contrast
        need = WCAG_LARGE if m["large"] else WCAG_NORMAL
        if m["c_med"] < WCAG_LARGE:
            kind = ("contrast_low", "WARN")
        elif m["c_med"] < need:
            kind = ("contrast_low", "INFO")
        elif m["c_p10"] < WCAG_LARGE and m["bg_lum_sd"] >= 0.02:
            kind = ("contrast_busy", "INFO")
        else:
            continue
        groups.setdefault((p, m["color"], kind), []).append(m)
    n_warn = 0
    for (p, color, (rule, sev)), g in sorted(groups.items(), key=lambda kv: kv[0][0]):
        worst = min(g, key=lambda m: m["c_med"] if rule == "contrast_low" else m["c_p10"])
        bb = (min(m["bbox"][0] for m in g), min(m["bbox"][1] for m in g),
              max(m["bbox"][2] for m in g), max(m["bbox"][3] for m in g))
        det = {k: worst[k] for k in ("text_lum", "bg_lum_med", "bg_lum_sd", "c_med", "c_p10")}
        det.update(color=color, lines=len(g), over_picture=worst["bg_lum_sd"] >= 0.02)
        n_warn += sev == "WARN"
        if rule == "contrast_low":
            where = "resmin" if det["over_picture"] else "zeminin"
            msg = (f"Metin rengi ({color}) ile {where} arasında kontrast düşük: {worst['c_med']:.1f}:1"
                   f" (WCAG en az {WCAG_LARGE:g}:1, küçük metinde {WCAG_NORMAL:g}:1); {len(g)} satır.")
        else:
            msg = (f"Metnin bir kısmı resmin kontrastı düşük bölgesine denk geliyor: en kötü %10'luk"
                   f" kısımda {worst['c_p10']:.1f}:1; {len(g)} satır.")
        add(p, sev, msg, worst["text"][:60], bb, rule=rule, **det)
    return {"contrast_runs": len(ms), "contrast_groups": len(groups), "contrast_warn": n_warn,
            "hidden": n_hidden}


# ------------------------------------------------------------------ run
async def run(generation_id: str):
    doc, bv, health = book(generation_id)
    LP = {p: page_lines(doc[p - 1], p) for p in range(1, doc.page_count + 1) if not unreliable(health, p)}
    font, size = body_style(LP)
    findings: list[dict] = []

    def add(page, sev, msg, quote, bb, suggestion=None, **details):
        findings.append({"page": page, "severity": sev, "message": msg, "quote": quote,
                         "bbox": norm_bbox(doc[page - 1], bb), "suggestion": suggestion, "details": details})

    stats = {"pages": doc.page_count, "pages_skipped_unreliable_layer": sorted(set(range(1, doc.page_count + 1)) - set(LP)),
             "has_trimbox": doc[0].trimbox != doc[0].rect}
    stats.update(check_folios(doc, LP, add))
    stats.update(check_margins(doc, LP, add))
    stats.update(check_body(doc, LP, font, size, add))
    stats.update(check_age(generation_id, doc, LP, font, size, add))
    stats.update(check_widows(doc, LP, font, size, add))
    stats.update(check_contrast(doc, bv, LP, add))
    by: dict = {}
    for f in findings:
        k = f"{f['severity']}:{f['details'].get('rule')}"
        by[k] = by.get(k, 0) + 1
    stats["findings_by_rule"] = by
    return findings, stats
