"""PDF metin katmanı onarımı (`editor.pdf_repair`) ve satır kurulumunun (`document._page_lines`) kitaptan bağımsız
kuralları. Gerçek kitap gerekmez: PDF'ler pymupdf ile ya da elle yazılmış küçük PDF metniyle üretilir."""

import pymupdf

from editor import document, pdf_repair


def _raw_pdf(font_dict: str, content: str, extra: list[str] = ()) -> pymupdf.Document:
    """Tek sayfalık elle yazılmış PDF (nesne 4 font, 5 içerik, 6.. ek nesneler)."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Resources << /Font << /F1 4 0 R >> >>"
            " /Contents 5 0 R >>",
            font_dict,
            f"<< /Length {len(content)} >>\nstream\n{content}\nendstream"] + list(extra)
    out, offs = "%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out.encode("latin-1")))
        out += f"{i} 0 obj\n{o}\nendobj\n"
    x = len(out.encode("latin-1"))
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n"
    return pymupdf.open(stream=out.encode("latin-1"), filetype="pdf")


def _tounicode(pairs: dict[int, str]) -> str:
    data = pdf_repair.cmap_bytes(pairs, 1).decode("latin-1")
    return f"<< /Length {len(data)} >>\nstream\n{data}\nendstream"


def test_glyph_unicode_follows_agl():
    assert pdf_repair.glyph_unicode("A.alt4") == "A"
    assert pdf_repair.glyph_unicode("/Idotaccent.alt2") == "İ"
    assert pdf_repair.glyph_unicode("uni015F") == "ş"
    assert pdf_repair.glyph_unicode("f_i") == "fi"
    assert pdf_repair.glyph_unicode("uniE000") is None          # özel alan harf değildir
    assert pdf_repair.glyph_unicode("bilinmeyenad") is None


def test_cmap_roundtrip():
    m = {0x41: "A", 0x42: "Ş", 0x43: "fi"}
    assert pdf_repair.parse_cmap(pdf_repair.cmap_bytes(m, 2)) == (m, 2)


def test_glyph_name_repairs_private_use_mapping_in_memory():
    """Süslü glif (A.alt4) ToUnicode'da özel alana eşli: glifin adı harfi verir; belge bellekte değişir."""
    font = ("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica"
            " /Encoding << /Type /Encoding /Differences [65 /A.alt4] >> /ToUnicode 6 0 R >>")
    doc = _raw_pdf(font, "BT /F1 20 Tf 20 100 Td (AB) Tj ET", [_tounicode({0x41: "", 0x42: "B"})])
    assert "" in doc[0].get_text()
    stats = pdf_repair.repair_document(doc)
    assert stats["glyph_names"] == 1
    assert doc[0].get_text().strip() == "AB"
    assert pdf_repair.repair_document(doc) is stats                 # ikinci çağrı bir şey yapmaz


def test_healthy_font_is_untouched():
    font = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    doc = _raw_pdf(font, "BT /F1 20 Tf 20 100 Td (Kalem) Tj ET")
    before = doc.xref_object(4)
    stats = pdf_repair.repair_document(doc)
    assert not any(v for k, v in stats.items() if k != "has_dotless_i")
    assert stats["has_dotless_i"] == {"Helvetica": False}
    assert doc.xref_object(4) == before
    assert doc[0].get_text().strip() == "Kalem"


def test_dot_above_shape():
    body, dot = (0, 0, 100, 700), (10, 760, 90, 860)
    assert pdf_repair.has_dot_above([body, dot])
    assert not pdf_repair.has_dot_above([body, (-100, 760, 200, 820)])     # geniş işaret: şapka
    assert not pdf_repair.has_dot_above([body])


def test_private_letter_resolved_by_book_vocabulary():
    pua = ""
    texts = ["Aşk her şeydir.", "Bu aşk bitmez.", "Aşkın adı", f"A{pua}k ve A{pua}kın gücü", f"a{pua}k"]
    m = pdf_repair.private_letter_map(texts)
    assert m == {pua: "ş"}
    assert pdf_repair.apply_private_letters(f"A{pua}K", m) == "AŞK"
    assert pdf_repair.apply_private_letters(f"a{pua}k", m) == "aşk"
    assert pdf_repair.private_letter_map([f"x{pua}y"]) == {}           # kanıt yok: karakter kalır


def test_mac_turkish_stand_ins_take_case_from_the_book():
    """Eski Mac Türkçe fontta «İ» → «‹», «ğ» → «¤» düşer. Harf sözlükten; «‹» yalnız büyük harfli kelimelerde ve
    kelime başında geçtiği için büyük «İ», «¤» küçük harfler arasında geçtiği için «ğ»."""
    texts = ["İnsan doğru yolu bulur. İnsanın ilk aşkı. Bağlanma ihtiyacı doğru bir adım. İçinde bağ var.",
             "‹nsan Do¤ru Bir Adım", "‹nsanın Ba¤lanma", "MAH‹YET‹ ‹çinde", "do¤ru ba¤"]
    m = pdf_repair.private_letter_map(texts)
    assert m == {"‹": "İ", "¤": "ğ"}
    assert pdf_repair.apply_private_letters("‹nsanın Do¤ru Ba¤lanma ‹çinde", m) == "İnsanın Doğru Bağlanma İçinde"
    # sözlükte karşılığı olmayan «‹» (tırnak olarak) dokunulmadan kalır
    assert pdf_repair.private_letter_map(["‹merhaba› dedi", "‹selam›"]) == {}


def test_borrowed_capital_i_in_small_caps_heading():
    spans = [{"font": "Ivy-SC", "size": 10.5, "text": "yüreğ"}, {"font": "Ivy", "size": 10.5, "text": "İ"},
             {"font": "Ivy-SC", "size": 10.5, "text": "me"}, {"font": "Ivy-SC", "size": 10.5, "text": " tercüman"}]
    texts = [s["text"] for s in spans]
    document._borrowed_capital_i(spans, texts)
    assert "".join(texts) == "yüreğime tercüman"
    # pymupdf uzun font adını kısaltır: ad aynı görünse de başka puntodaki «İ» ödünçtür
    spans[1].update(font="Ivy-SC", size=10.0)
    texts = [s["text"] for s in spans]
    document._borrowed_capital_i(spans, texts)
    assert "".join(texts) == "yüreğime tercüman"
    # aynı font ve puntoda ya da büyük harf içeren satırda «İ» kalır
    spans[1]["size"] = 10.5
    texts = [s["text"] for s in spans]
    document._borrowed_capital_i(spans, texts)
    assert "".join(texts) == "yüreğİme tercüman"
    spans = [{"font": "A", "size": 10, "text": "Bir "}, {"font": "B", "size": 10, "text": "İ"},
             {"font": "A", "size": 10, "text": "stanbul"}]
    texts = [s["text"] for s in spans]
    document._borrowed_capital_i(spans, texts)
    assert texts[1] == "İ"


def test_word_space_in_its_own_size_is_kept():
    """Başlıkta kelime arası boşluk başka puntoda: ayrı span gelir ve eskiden düşüyordu («aynadayolculuk»)."""
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=200)
    x = 20.0
    for txt, size in (("aynada", 10.5), (" ", 15), ("yolculuk", 10.5)):
        page.insert_text((x, 100), txt, fontsize=size, fontname="helv")
        x += pymupdf.get_text_length(txt, fontname="helv", fontsize=size)
    doc = pymupdf.open("pdf", doc.tobytes())
    lines = document._page_lines(doc[0])
    assert [ln["text"] for ln in lines] == ["aynada yolculuk"]
    assert lines[0]["size"] == 10.5                      # boşluğun puntosu satırın puntosu sayılmaz


def test_shrunken_l_in_font_without_dotless_i_is_dotless_i():
    """ı'sı olmayan başlık fontunda dizgici ı yerine küçültülmüş «l» basar: «K» + küçük «l» + «z» = «Kız»."""
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=200)
    x = 20.0
    for ch, size in (("K", 24), ("l", 16), ("z", 24), (" ", 24), ("Kal", 24)):
        page.insert_text((x, 100), ch, fontsize=size, fontname="helv")
        x += pymupdf.get_text_length(ch, fontname="helv", fontsize=size)
    doc = pymupdf.open("pdf", doc.tobytes())
    assert "Klz" in "".join(ln["text"] for ln in document._page_lines(doc[0])).replace(" ", "")
    pdf_repair.repair_document(doc)
    assert [ln["text"] for ln in document._page_lines(doc[0])] == ["Kız Kal"]
