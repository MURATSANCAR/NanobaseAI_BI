"""Basılı kitabın e-kitabı (editor.production.epub_source): basılı künyeden e-künye, yayınevinin kapağı; Arapça
ibare, dipnot çizgisi, alt marka logosu. Veritabanı yok (kapak ve künye okuması sahte); dizgili test editor-py
imajında koşar."""

from __future__ import annotations

import json
import zipfile

import pytest

from test_plan import FONTS, _job, typeset_only  # noqa: F401 - ortak iş kurulumu

from editor.production import epub as E  # noqa: E402
from editor.production import epub_edit as X  # noqa: E402
from editor.production import epub_source as S  # noqa: E402
from editor.production import plan as P  # noqa: E402

# Yayınevi künyesinin okunmuş paragrafları (gerçek kitaptan, sayfa 2; satır sırası basılıdaki gibi).
KUNYE = [
    "ÇİÇEKÇİ KADIN Minyoung Kang", "Dünya Roman - Öykü",
    "TİMAŞ YAYINLARI | 6543 Edebiyat Kitaplığı - Dünya Edebiyatı Dizisi | 132",
    "PROJE EDİTÖRÜ Ayşe Tuba Ayman", "EDİTÖR Dilruba Aydın", "ÇEVİRİ Selen Demirtaş",
    "KAPAK TASARIMI Rabia Erdohan", "İÇ TASARIM Kısmet Gül Albayrak", "1. BASKI Ağustos 2026, İstanbul", "ISBN",
    "TİMAŞ YAYINLARI Bahçelievler Mah. Zübeyde Hanım Cad. No: 8 Üsküdar / İstanbul Telefon: (0212) 511 24 24",
    "timas.com.tr timas@timas.com.tr timasyayingrubu", "Kültür Bakanlığı Yayıncılık Sertifika No: 45587",
    "Bu kitap Literature Translation Institute of Korea (LTI Korea) desteğiyle yayımlanmıştır.",
    "BASKI VE CİLT Çınar Matbaacılık İkitelli OSB Mah. Çevre Sosyal Tesisler S.k.",
    "Çevre Sanayi Sitesi Sosyal Tesisler No: 3 Başakşehir / İstanbul Telefon: (0212) 628 96 00 Matbaa Sertifika No: 45103",
    "YAYIN HAKLARI © Minyoung Kang, 2026 ... anlaşma kapsamında Timaş Basım Ticaret ve Sanayi A.Ş.'ye aittir.",
]


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("EDITOR_FONT_DIR", str(FONTS))
    monkeypatch.setenv("EPUB_HOUSE_DIR", str(tmp_path / "sablon"))
    monkeypatch.delenv("EPUB_HOUSE", raising=False)


def test_print_kunye_keeps_publisher_lines_and_drops_print_only():
    rows = S.parse_kunye(KUNYE, "Çiçekçi Kadın", "Minyoung Kang")
    labels = [k for k, _ in rows]
    assert labels[0] == S.SERIES_KEY
    assert ["PROJE EDİTÖRÜ", "EDİTÖR", "ÇEVİRİ", "KAPAK TASARIMI", "İÇ TASARIM", "TİMAŞ YAYINLARI"] == \
        [k for k in labels if k and k != S.SERIES_KEY and k != "YAYIN HAKLARI"]
    text = json.dumps(rows, ensure_ascii=False)
    for gone in ("BASKI", "Ağustos 2026", "Çınar", "Matbaa", "Dünya Roman", "ÇİÇEKÇİ KADIN"):
        assert gone not in text, gone
    assert ("KAPAK TASARIMI", "Rabia Erdohan") in rows and rows[-1][0] == "YAYIN HAKLARI"
    assert rows[-1][1].endswith("aittir.")                       # telif cümlesi yarım kalmaz
    assert (None, "timas.com.tr timas@timas.com.tr timasyayingrubu") in rows


def test_print_kunye_html_puts_eisbn_before_publisher_address():
    items = S.parse_kunye(KUNYE, "Çiçekçi Kadın", "Minyoung Kang")
    html = "".join(E.house_kunye_print(E.HOUSES["timas"], items, "9786050843231", []))
    assert html.index("TİMAŞ YAYINLARI | 6543") < html.index(">KAPAK TASARIMI<") < html.index(">E-ISBN<") \
        < html.index("Bahçelievler") < html.index(">YAYIN HAKLARI<")
    assert "Edebiyat Kitaplığı - Dünya Edebiyatı Dizisi | 132" in html and "978-6050843231" in html


def test_split_label():
    assert S.split_label("KAPAK TASARIMI Rabia Erdohan") == ("KAPAK TASARIMI", "Rabia Erdohan")
    assert S.split_label("Kültür Bakanlığı Yayıncılık") == (None, "Kültür Bakanlığı Yayıncılık")
    assert S.split_label("ISBN") == (None, "ISBN")


def test_arabic_is_marked_right_to_left():
    html = E.run_html({"text": "Hadis: غمط الناس بطر الحق dedi."}, {})
    assert '<span class="arapca" lang="ar" dir="rtl">غمط الناس بطر الحق</span>' in html and html.startswith("Hadis:")


def test_notes_start_with_rule():
    nb = E.NoteBook("notlar.xhtml")
    nb.add(1, "Not.", None)
    assert nb.html().startswith('<hr class="e-dipnot-cizgi"/>')


def test_imprint_logo_from_kunye(tmp_path):
    base = tmp_path / "sablon" / "timas"
    base.mkdir(parents=True)
    (base / "logo.svg").write_text("<svg/>")
    (base / "logo-akademi.png").write_bytes(b"png")
    (base / "logolar.json").write_text(json.dumps([{"ad": "Timaş Akademi", "dosya": "logo-akademi.png"},
                                                   {"ad": "Kötü", "dosya": "../disari.png"}]))
    assert E.house_logo("timas", "TİMAŞ YAYINLARI | 5350 Timaş Akademi | 4").name == "logo-akademi.png"
    assert E.house_logo("timas", "Edebiyat Kitaplığı").name == "logo.svg"


@typeset_only
def test_print_book_ebook_uses_publisher_cover_and_kunye(tmp_path, monkeypatch):
    """Basılı kitabın e-kitabı: yayınevinin kapağı, basılı künye (kapak tasarımcısı adıyla, yapay zekâ satırı yok),
    stüdyonun resimleri yok, sayfa listesi okunmuş kitabın basılı sayfalarından."""
    from PIL import Image
    import io
    d, ms = _job(tmp_path, child=False)
    P.freeze(d, "sınama")
    m = json.loads((d / "manuscript.json").read_text())
    m["source"] = {"kind": "generation", "generation_id": "g1"}
    for ci, ch in enumerate(m["chapters"]):
        for bi, b in enumerate(ch["blocks"]):
            b["pages"] = [10 + ci * 5 + bi // 3]
    (d / "manuscript.json").write_text(json.dumps(m, ensure_ascii=False))
    buf = io.BytesIO()
    Image.new("RGB", (600, 900), (200, 30, 30)).save(buf, "JPEG")
    monkeypatch.setattr(S, "original_cover", lambda ms_: (buf.getvalue(), ".jpg", {"source": "yayınevi sitesi"}))
    monkeypatch.setattr(S, "print_kunye", lambda d_: S.parse_kunye(KUNYE, "Çiçekçi Kadın", "Minyoung Kang"))
    from editor.production import studio
    monkeypatch.setattr(S, "print_manuscript", lambda d_, wait=True, signature=None: studio._manuscript(d_))
    monkeypatch.setattr(S, "print_bios", lambda d_: [{"name": "Minyoung Kang", "text": "Seulde yaşar."}])
    assert X.source_mode(d, X.load(d)) == "basili"
    out = E.build(d, "reflow", "e")
    assert out["source"] == "basili"
    z = zipfile.ZipFile(d / "epub" / "kitap.epub")
    kun = z.read("OEBPS/text/kunye.xhtml").decode()
    assert "Rabia Erdohan" in kun and "ZEKİ AI" not in kun and "Matbaa" not in kun
    assert "Seulde yaşar." in z.read("OEBPS/text/yazar.xhtml").decode()               # basılı kitabın tanıtımı
    assert z.read("OEBPS/images/kapak.jpg") == buf.getvalue()
    names = z.namelist()
    assert not [n for n in names if n.startswith("OEBPS/images/a_") or n.startswith("OEBPS/images/g_")]
    nav = z.read("OEBPS/nav.xhtml").decode()
    assert ">10<" in nav and 'epub:type="page-list"' in nav                          # basılı sayfa numaraları
    E.check(d / "epub" / "kitap.epub")
    X.change(d, X.load(d)["rev"], [{"op": "source", "source": "studyo"}], "e")
    out = E.build(d, "reflow", "e")
    assert out["source"] == "studyo" and "ZEKİ AI" in zipfile.ZipFile(d / "epub" / "kitap.epub").read(
        "OEBPS/text/kunye.xhtml").decode()
