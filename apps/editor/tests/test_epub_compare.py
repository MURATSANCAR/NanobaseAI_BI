"""E-kitap ↔ basılı karşılaştırması (editor.production.epub_compare): veritabanı ve model yok."""

from __future__ import annotations

import zipfile

from editor.production import epub_compare as C

BODY = ("Kadın dükkânın içini ağır ağır süzdükten sonra Yuhui'nin sorusuna cevap verdi ve pencerenin dibindeki "
        "alacalı kauçuk ağacının önünde durdu. Tam en tepedeki yeni filizlenen iri taze yaprağa uzanacakken Yuhui "
        "telaşla araya girdi.")
NOTE = ("Yazarın notu: bu hikâye aslında bir öykü hacminde filizlendi ve roman üzerinde çalışırken çıkış noktasını "
        "defalarca düşündüm, sonunda onu kitabın sonuna koymaya karar verdim.")
KUNYE = "Baskı ve Cilt Çınar Matbaacılık İkitelli OSB Sertifika No 45587 Telefon 0212 511 24 24 İstanbul 2026"


def test_missing_parts_with_page_and_reason():
    pages = [(2, KUNYE), (5, BODY), (206, NOTE)]
    epub = "İyi ki kitaplar var. " + BODY.replace("dük-", "dük")
    r = C.compare(pages, epub, {"2": "künye"})
    by = {m["pages"][0]: m for m in r["missing"]}
    assert set(by) == {2, 206}
    assert by[2]["expected"] and by[2]["reason"] == "künye"
    assert not by[206]["expected"] and by[206]["reason"] is None and "yazarın notu" in by[206]["text"]
    assert r["missing_parts"] == 1 and r["missing_words"] == by[206]["words"]


def test_typesetting_differences_are_not_missing():
    printed = BODY.replace("filizlenen", "filiz- lenen")                       # satır sonu tirelemesi
    tr_upper = printed.replace("i", "İ").replace("ı", "I").upper()             # Türkçe büyük harf
    r = C.compare([(5, tr_upper)], BODY)
    assert r["missing"] == [] and r["covered"] == 1.0


def test_epub_text_reads_spine_without_nav_and_separates_paragraphs(tmp_path):
    p = tmp_path / "k.epub"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>')
        z.writestr("OEBPS/content.opf", '<package xmlns="http://www.idpf.org/2007/opf"><manifest>'
                   '<item id="nav" href="nav.xhtml" properties="nav"/><item id="b" href="text/b.xhtml"/></manifest>'
                   '<spine><itemref idref="nav"/><itemref idref="b"/></spine></package>')
        z.writestr("OEBPS/nav.xhtml", "<html><body><p>İçindekiler</p></body></html>")
        z.writestr("OEBPS/text/b.xhtml", "<html><body><p>bir</p><p>iki<br/>üç</p></body></html>")
    t = C.epub_text(p)
    assert C.words(t) == ["bir", "iki", "üç"]


def test_publisher_promo_inside_page_is_expected():
    promo = "Yeni kitap önerimiz için karekodu telefon kameranıza okutunuz. Aynı karekod ile her hafta başka bir kitap"
    r = C.compare([(208, NOTE + " " + promo)], NOTE)
    assert len(r["missing"]) == 1 and r["missing"][0]["expected"] and r["missing"][0]["reason"] == "yayınevi tanıtımı"
    r = C.compare([(206, BODY), (208, NOTE + " " + promo)], BODY)          # not e-kitapta yok: reklamla birlikte gizlenmez
    gaps = [m for m in r["missing"] if not m["expected"]]
    assert len(gaps) == 1 and "yazarın notu" in gaps[0]["text"] and "karekod" not in gaps[0]["text"]
    assert any(m["reason"] == "yayınevi tanıtımı" for m in r["missing"])
