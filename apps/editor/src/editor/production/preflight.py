"""Ön baskı denetimi. FAIL basımı durdurur, WARN editöre gösterilir.

- Sayfa sayısı forma katı; her sayfa kesim + 2×taşma boyunda; TrimBox/BleedBox yazılı.
- Bütün fontlar gömülü.
- Metin eksiksiz: iç sayfa PDF'inden okunan kelime dizisi kitabın kelime dizisini sırasıyla içerir
  (dizgi bir kelime bile düşürmemiş, eklememiş).
- Resim çözünürlüğü: üretim 250 dpi altındaysa (büyütülmüş) WARN, 120 altı FAIL.
- Editör onayı (studio.refresh_preflight): onaylanmamış resim FAIL.
- Künyede kaynağı olmayan alan FAIL.
- Sahne tarifinin sayfa metninde alıntısı bulunmayan resim WARN.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

WORD = re.compile(r"[0-9A-Za-zÇĞİÖŞÜÂÎÛçğıöşüâîû]+")
PT_PER_MM = 72 / 25.4


def _words(s: str) -> list[str]:
    """Karşılaştırma için kelimeler. Tireler iki tarafta da yok sayılır: dizgi gerçek bir tireden satır
    kırabilir («aha-⏎hahaha») ya da heceleyerek tire ekleyebilir; ikisi de metin kaybı değildir."""
    # Dizginin hece tiresi satır sonuna yapışıktır («ola-⏎cak»); yazarın tiresinden sonra boşluk gelir
    # («AhA- ⏎HAHA»), o bir kelime ayrımıdır, birleşmez.
    s = re.sub(r"[-\u2010\u2011\u00ad]\n\s*", "", s)
    s = re.sub(r"[-\u2010\u2011\u00ad]", "", s)
    return [w.casefold() for w in WORD.findall(s)]


BRAND = "Zeki AI"
_TOOL_TAGS = re.compile(r"(<(?:xmp:CreatorTool|pdf:Producer)>)[^<]*(</)")
_TOOL_ATTRS = re.compile(r'((?:xmp:CreatorTool|pdf:Producer)=")[^"]*(")')
_META_KEYS = ("title", "author", "subject", "keywords", "creationDate", "modDate", "trapped")


def brand(doc) -> None:
    """Belge özelliklerinde üretici «Zeki AI»: dizgi ve dönüştürücü yazılımın adı PDF'te görünmez
    (kullanıcı kuralı 2026-09-25: kullandığımız model/ürün/teknoloji adı müşteriye gösterilmez)."""
    meta = {k: v for k, v in (doc.metadata or {}).items() if k in _META_KEYS and v}
    doc.set_metadata({**meta, "producer": BRAND, "creator": BRAND})
    xmp = doc.get_xml_metadata()
    if xmp:
        xmp = _TOOL_TAGS.sub(rf"\g<1>{BRAND}\g<2>", xmp)
        doc.set_xml_metadata(_TOOL_ATTRS.sub(rf"\g<1>{BRAND}\g<2>", xmp))


def set_boxes(pdf: Path, bleed_mm: float) -> None:
    """Her sayfaya TrimBox (kesim) ve BleedBox (taşma) yazar; matbaa kesimi buradan okur."""
    import pymupdf
    doc = pymupdf.open(pdf)
    b = bleed_mm * PT_PER_MM
    for page in doc:
        r = page.rect
        page.set_bleedbox(r)
        page.set_trimbox(pymupdf.Rect(r.x0 + b, r.y0 + b, r.x1 - b, r.y1 - b))
    brand(doc)
    doc.saveIncr()


def _page_text(page, drop: list[dict], keep: list[dict]) -> str:
    """Sayfanın metni, `drop` kutularındaki yazı (efekt yazı, şekil yazısı) hariç; `keep` kutularıyla örtüşen yer
    okunur. Kutular mm; satır yapısı get_text() ile aynı (satır sonu tireleri `_words` birleştirir)."""
    def inside(x, y, bx):
        return bx["x"] <= x <= bx["x"] + bx["w"] and bx["y"] <= y <= bx["y"] + bx["h"]

    lines = []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            parts = []
            for sp in ln["spans"]:
                x0, y0, x1, y1 = sp["bbox"]
                cx, cy = (x0 + x1) / 2 / PT_PER_MM, (y0 + y1) / 2 / PT_PER_MM
                if any(inside(cx, cy, bx) for bx in drop) and not any(inside(cx, cy, bx) for bx in keep):
                    continue
                parts.append(sp["text"])
            if parts:
                lines.append("".join(parts))
    return "\n".join(lines)


def check(interior: Path, cover: Path | None, ms, spec, renders: list[dict], kunye_missing: list[str],
          scenes: list) -> dict:
    import pymupdf
    out = []

    def add(name, status, detail):
        out.append({"name": name, "status": status, "detail": detail})

    doc = pymupdf.open(interior)
    n = doc.page_count
    add("Sayfa sayısı", "OK" if n % spec.signature == 0 else "FAIL", f"{n} sayfa, forma {spec.signature}")
    W, H = (spec.trim_w + 2 * spec.bleed) * PT_PER_MM, (spec.trim_h + 2 * spec.bleed) * PT_PER_MM
    bad = [i + 1 for i, p in enumerate(doc) if abs(p.rect.width - W) > 0.5 or abs(p.rect.height - H) > 0.5]
    add("Sayfa boyu (kesim + taşma)", "FAIL" if bad else "OK",
        f"{spec.trim_w:g}×{spec.trim_h:g} mm + {spec.bleed:g} mm" + (f"; farklı: {bad}" if bad else ""))
    trim_missing = [i + 1 for i, p in enumerate(doc) if p.trimbox == p.mediabox]
    add("Kesim kutusu (TrimBox)", "FAIL" if trim_missing else "OK",
        "her sayfada" if not trim_missing else f"eksik: {trim_missing[:10]}")
    fonts = {f[3]: f[1] for p in doc for f in p.get_fonts(full=True)}
    unembedded = sorted(name for name, ext in fonts.items() if ext in ("n/a", ""))
    add("Fontlar gömülü", "FAIL" if unembedded else "OK",
        ", ".join(sorted({re.sub(r"^[A-Z]{6}\+", "", f) for f in fonts})) if not unembedded else f"gömülmemiş: {unembedded}")
    skip = ms.element_rects() if hasattr(ms, "element_rects") else {}
    pdf_words = _words("\n".join(_page_text(p, *skip[i]) if i in skip else p.get_text() for i, p in enumerate(doc)))
    book_words = _words(ms.text().replace("## ", ""))
    sm = SequenceMatcher(None, book_words, pdf_words, autojunk=False)
    covered = sum(bl.size for bl in sm.get_matching_blocks())
    lost = len(book_words) - covered
    miss_sample = []
    for tag, i1, i2, _, _ in sm.get_opcodes():
        if tag in ("delete", "replace"):
            miss_sample.append(" ".join(book_words[i1:i2])[:60])
    add("Metin eksiksiz", "OK" if lost == 0 else "FAIL",
        f"{len(book_words)} kelimenin {covered}'i sırasıyla PDF'te" + (f"; eksik: {miss_sample[:5]}" if lost else ""))
    low = [(r["key"], r["dpi"]) for r in renders if r.get("dpi") and r["dpi"] < 250]
    worst = min((d for _, d in low), default=300)
    add("Resim çözünürlüğü", "FAIL" if worst < 120 else "WARN" if low else "OK",
        "bütün resimler ≥250 dpi üretildi" if not low else
        f"{len(low)} resim düşük çözünürlükte üretilip 300 dpi'ya büyütüldü (en düşük üretim {worst} dpi)")
    add("Künye", "FAIL" if kunye_missing else "OK",
        "tam" if not kunye_missing else "kaynağı olmayan alan: " + ", ".join(kunye_missing))
    ungrounded = [s.page for s in scenes if not s.grounded]
    add("Resim–metin bağı", "WARN" if ungrounded else "OK",
        "her resmin sahnesi sayfanın cümlesine bağlı" if not ungrounded else f"alıntısı tutmayan sayfa: {ungrounded}")
    if not (getattr(ms, "author", None) or "").strip():
        add("Yazar adı", "WARN", "yazar adı girilmemiş; kapakta ve sırtta yazar satırı basılmadı — künyeden girin")
    if cover is not None:
        c = pymupdf.open(cover)
        add("Kapak açılımı", "OK" if c.page_count == 1 else "FAIL",
            f"{c[0].rect.width / PT_PER_MM:.1f}×{c[0].rect.height / PT_PER_MM:.1f} mm")
    status = "FAIL" if any(x["status"] == "FAIL" for x in out) else "WARN" if any(x["status"] == "WARN" for x in out) else "OK"
    return {"status": status, "checks": out}
