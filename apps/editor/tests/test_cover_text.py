"""Kapak yazısı katmanı (editor.cover_text), sentetik resimle: Türkçe büyük harf, yazı biçimi seçimi,
fontta harf kapsamı, sığdırma, renk/perde kararı. Fontlar editor-py imajında /app/data/fonts;
yoksa font gerektiren testler atlanır. Çalıştır:

    pytest apps/editor/tests/test_cover_text.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from editor import cover_text as ct  # noqa: E402

HAS_FONTS = all((ct.FONT_DIR / s.title.file).exists() for s in ct.STYLES.values())
fonts = pytest.mark.skipif(not HAS_FONTS, reason="fontlar yok (editor-py imajında koşar)")


def test_tr_upper():
    assert ct.tr_upper("çiçekçi kadın") == "ÇİÇEKÇİ KADIN"
    assert ct.tr_upper("ibn sînâ") == "İBN SÎNÂ"
    assert ct.tr_upper("Sarıoğlu") == "SARIOĞLU"


def test_style_for():
    assert ct.style_for(10, "ÖYKÜ/HİKÂYE") == "cocuk"
    assert ct.style_for(None, "Tasavvuf / Biyografi") == "klasik"
    assert ct.style_for(None, "Dünya Roman - Öykü") == "edebiyat"
    assert ct.style_for(None, None) == "edebiyat"


@fonts
@pytest.mark.parametrize("style", sorted(ct.STYLES))
def test_turkish_letters_covered(style):
    text = "ÇĞİÖŞÜ çğıöşü ÂÎÛ âîû"
    face = ct._usable(ct.STYLES[style].title, text)
    assert ct.covers(face, text)


@fonts
def test_fit_stays_inside_box():
    face = ct.STYLES["cocuk"].title
    size, lines = ct.fit("DÜNYANIN EN KORKAK HAYVANI", face, 800, 400, 1.0)
    font = ct._font(face, size)
    assert 1 <= len(lines) <= 3
    assert all(ct._width(font, ln) <= 800 for ln in lines)
    assert " ".join(lines) == "DÜNYANIN EN KORKAK HAYVANI"


@fonts
@pytest.mark.parametrize("bg,ink", [((245, 240, 230), ct.DARK), ((20, 30, 60), ct.LIGHT)])
def test_ink_follows_background(bg, ink):
    img = Image.new("RGB", (1024, 1536), bg)
    out, rep = ct.compose(img, "Gölge Tilki", "Carlie Sorosiak", style="edebiyat")
    assert rep["title"]["ink"] == ink and not rep["title"]["scrim"]
    assert rep["title"]["lines"] and rep["author"]["lines"] == ["Carlie Sorosiak"]
    x0, y0, x1, y1 = rep["title"]["box"]
    assert 0 <= x0 < x1 <= 1024 and 0 <= y0 < y1 <= int(1536 * ct.TITLE_BAND[1]) + 5


@fonts
def test_busy_background_gets_scrim():
    img = Image.new("RGB", (1024, 1536))
    px = img.load()
    for y in range(1536):                 # açık-koyu çizgili, tek renk yazının okunamayacağı zemin
        for x in range(1024):
            px[x, y] = (250, 250, 250) if (x // 12) % 2 else (10, 10, 10)
    _, rep = ct.compose(img, "İbn Sînâ", "Gürbüz Deniz", subtitle="Ahlakın Elifbesi", style="klasik")
    assert rep["title"]["scrim"] and rep["author"]["scrim"]
    assert rep["subtitle"]["lines"]


@fonts
def test_empty_author_skips_author_block():
    """Word'den açılan işte yazar adı yoksa kapak düşmez; yazar bloğu basılmaz (canlı hata 2026-09-25:
    «yazı alana sığmıyor: ''»)."""
    img = Image.new("RGB", (1200, 1800), (200, 210, 220))
    for author in ("", "   ", None):
        _, rep = ct.compose(img, "Etimesgutlu Bebek Aslan", author, None, "cocuk", draw_text=False)
        assert "author" not in rep and rep["title"]["lines"]


def test_empty_title_is_explained():
    img = Image.new("RGB", (600, 900), (200, 210, 220))
    with pytest.raises(ValueError, match="kitap adı boş"):
        ct.compose(img, "  ", "Yazar", None, "cocuk", draw_text=False)


def test_docx_title_from_file_name():
    from types import SimpleNamespace
    from editor.production.manuscript import _docx_title
    doc = SimpleNamespace(core_properties=SimpleNamespace(title=""))
    assert _docx_title(doc, "/x/girdi/Etimesgutlu_Bebek_Aslan.docx") == "Etimesgutlu Bebek Aslan"
    assert _docx_title(doc, "/x/Küçük-Prens__son.DOCX") == "Küçük Prens son"
    doc.core_properties.title = "Belge Başlığı"
    assert _docx_title(doc, "/x/a_b.docx") == "Belge Başlığı"
