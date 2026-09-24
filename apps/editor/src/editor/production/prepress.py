"""Baskı öncesi: ekran PDF'inden matbaaya gidecek PDF (CMYK, PDF/X, kesim işaretli).

1. Kesim işaretleri: her sayfa, taşma payının dışına 10 mm'lik kenar (slug) eklenerek büyütülür; kesim
   köşelerine, taşma payının 1 mm dışından başlayan 5 mm'lik ince çizgiler çizilir (kayıt siyahı).
2. CMYK + PDF/X-3: Ghostscript pdfwrite, çıktı niyeti (OutputIntent) matbaanın ICC profiliyle.
   Profil EDITOR_CMYK_ICC ile verilir; verilmezse Ghostscript'in varsayılan CMYK profili kullanılır ve ön
   kontrol bunu uyarı olarak gösterir (matbaa profili sorulmalı).
3. Kutular: MediaBox kenar dahil, BleedBox kesim + taşma, TrimBox kesim.

Ekran PDF'i (RGB, işaretsiz) önizleme ve stüdyo içindir; bu PDF baskı içindir.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

PT_PER_MM = 72 / 25.4
SLUG = 10.0                 # kesim işaretleri için taşmanın dışındaki kenar (mm)
MARK_GAP = 1.0              # işaret, taşma kenarından bu kadar uzakta başlar (mm)
MARK_LEN = 5.0
GS_DEFAULT_ICC = ("/usr/share/color/icc/ghostscript/default_cmyk.icc",
                  "/usr/share/ghostscript/iccprofiles/default_cmyk.icc")


def icc_profile() -> tuple[str, bool]:
    """(profil yolu, matbaa profili mi). EDITOR_CMYK_ICC yoksa Ghostscript varsayılanı."""
    own = os.environ.get("EDITOR_CMYK_ICC", "")
    if own and Path(own).exists():
        return own, True
    for p in GS_DEFAULT_ICC:
        if Path(p).exists():
            return p, False
    raise RuntimeError("CMYK ICC profili bulunamadı (EDITOR_CMYK_ICC ya da ghostscript profilleri)")


def add_marks(src: Path, dst: Path, bleed_mm: float) -> None:
    """Taşma paylı sayfaları kenarla büyütür, kesim işaretlerini çizer, kutuları yazar."""
    import pymupdf
    s = pymupdf.open(src)
    out = pymupdf.open()
    b, g, L, sl = (v * PT_PER_MM for v in (bleed_mm, MARK_GAP, MARK_LEN, SLUG))
    for i, page in enumerate(s):
        w, h = page.rect.width, page.rect.height                 # kesim + 2×taşma
        np_ = out.new_page(width=w + 2 * sl, height=h + 2 * sl)
        np_.show_pdf_page(pymupdf.Rect(sl, sl, sl + w, sl + h), s, i)
        tx0, ty0, tx1, ty1 = sl + b, sl + b, sl + w - b, sl + h - b   # kesim çizgileri
        ex0, ey0, ex1, ey1 = sl - g, sl - g, sl + w + g, sl + h + g   # işaretin başladığı yer (taşma dışı)
        shape = np_.new_shape()
        for x in (tx0, tx1):
            shape.draw_line((x, ey0), (x, ey0 - L))
            shape.draw_line((x, ey1), (x, ey1 + L))
        for y in (ty0, ty1):
            shape.draw_line((ex0, y), (ex0 - L, y))
            shape.draw_line((ex1, y), (ex1 + L, y))
        shape.finish(color=(0, 0, 0), width=0.25)
        shape.commit()
    out.save(dst, garbage=3, deflate=True)
    set_boxes(dst, bleed_mm)


def set_boxes(pdf: Path, bleed_mm: float) -> None:
    """Kenarlı sayfada: BleedBox = kesim + taşma, TrimBox = kesim."""
    import pymupdf
    doc = pymupdf.open(pdf)
    sl, b = SLUG * PT_PER_MM, bleed_mm * PT_PER_MM
    for page in doc:
        r = page.rect
        page.set_bleedbox(pymupdf.Rect(r.x0 + sl, r.y0 + sl, r.x1 - sl, r.y1 - sl))
        page.set_trimbox(pymupdf.Rect(r.x0 + sl + b, r.y0 + sl + b, r.x1 - sl - b, r.y1 - sl - b))
    doc.saveIncr()


def _pdfx_def(icc: str, title: str, workdir: Path) -> Path:
    """Ghostscript PDF/X tanımı: çıktı niyeti ICC profiliyle (Ghostscript'in PDFX_def.ps kalıbı)."""
    ps = workdir / "pdfx_def.ps"
    esc = title.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    ps.write_text(f"""%!
/ICCProfile ({icc}) def
[ /Title ({esc}) /DOCINFO pdfmark
[/_objdef {{icc_PDFX}} /type /stream /OBJ pdfmark
[{{icc_PDFX}} <</N 4>> /PUT pdfmark
[{{icc_PDFX}} ICCProfile (r) file /PUT pdfmark
[/_objdef {{OutputIntent_PDFX}} /type /dict /OBJ pdfmark
[{{OutputIntent_PDFX}} <<
  /Type /OutputIntent /S /GTS_PDFX
  /OutputCondition (CMYK) /OutputConditionIdentifier (Custom) /RegistryName (http://www.color.org)
  /DestOutputProfile {{icc_PDFX}}
>> /PUT pdfmark
[{{Catalog}} <</OutputIntents [ {{OutputIntent_PDFX}} ]>> /PUT pdfmark
""")
    return ps


def to_cmyk_pdfx(src: Path, dst: Path, title: str) -> dict:
    """Ghostscript ile CMYK + PDF/X-3. Dönen: {icc, printer_profile, seconds}."""
    import time
    gs = shutil.which("gs")
    if not gs:
        raise RuntimeError("ghostscript (gs) yok")
    icc, own = icc_profile()
    t = time.time()
    ps = _pdfx_def(icc, title, dst.parent)
    cmd = [gs, "-dPDFX", "-dBATCH", "-dNOPAUSE", "-dNOSAFER", "-dQUIET", "-sDEVICE=pdfwrite",
           "-sColorConversionStrategy=CMYK", "-sProcessColorModel=DeviceCMYK", "-dPDFSETTINGS=/prepress",
           f"-sOutputICCProfile={icc}", "-dAutoRotatePages=/None", "-dCompatibilityLevel=1.4",
           "-dDownsampleColorImages=false", "-dDownsampleGrayImages=false", "-dEmbedAllFonts=true",
           f"-sOutputFile={dst}", str(ps), str(src)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if r.returncode != 0 or not dst.exists():
        raise RuntimeError(f"ghostscript: {r.stderr[-600:] or r.stdout[-600:]}")
    return {"icc": Path(icc).name, "printer_profile": own, "seconds": round(time.time() - t, 1)}


def make(src: Path, dst: Path, bleed_mm: float, title: str) -> dict:
    """Ekran PDF'inden baskı PDF'i: işaretler → CMYK/PDF-X → kutular (Ghostscript kutuları sıfırlayabilir)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    marked = dst.with_suffix(".isaretli.pdf")
    add_marks(src, marked, bleed_mm)
    info = to_cmyk_pdfx(marked, dst, title)
    set_boxes(dst, bleed_mm)
    marked.unlink(missing_ok=True)
    return info


def check(pdf: Path) -> dict:
    """Baskı PDF'inin denetimi: çıktı niyeti var mı, görseller CMYK mı, fontlar gömülü mü, kutular yazılı mı."""
    import pymupdf
    doc = pymupdf.open(pdf)
    cat = doc.pdf_catalog()
    has_intent = "OutputIntents" in doc.xref_object(cat)
    non_cmyk, total = 0, 0
    for page in doc:
        for img in page.get_images(full=True):
            total += 1
            cs = (img[5] or "").lower()
            if cs and "cmyk" not in cs and "devicen" not in cs and "separation" not in cs and "gray" not in cs:
                non_cmyk += 1
    unembedded = [f[3] for p in doc for f in p.get_fonts(full=True) if f[1] in ("n/a", "")]
    trim_ok = all(p.trimbox != p.mediabox and p.bleedbox != p.mediabox for p in doc)
    return {"output_intent": has_intent, "images": total, "non_cmyk_images": non_cmyk,
            "unembedded_fonts": sorted(set(unembedded)), "boxes": trim_ok, "pages": doc.page_count}
