"""Redaksiyon PDF okuması: yanlış harf eşlemesi ve InDesign çıktısının okuma kusurları (2026-09-30).

İki gerçek kitapta ölçülen sınıflar, testin içinde elle kurulan PDF'lerle: süslü başlık glifinin özel alan (PUA)
karakterine eşlenmesi, ToUnicode'u olmayan fontta glif adının metne sızması, noktalı İ'nin «I» diye eşlenmesi, sayfa
dışındaki metin, aynı yere iki kez basılan metin, kenara asılan tirenin önüne okuyucunun koyduğu boşluk, büyük ilk
harf, çizim sırasında sona kalan başlık ve cümlenin ortasındaki süs yazısı. Kitaba özel hiçbir şey yoktur.
"""

from __future__ import annotations

import io

import pytest
from pypdf import PdfReader

from semantic_bridge import editorial_desk_structure as st
from semantic_bridge import editorial_pdf_text as pt


class _Pdf:
    """Nesne nesne PDF: numaralar ekleme sırasıyla; sayfalar sonda kurulur."""

    def __init__(self) -> None:
        self.objs: list[bytes] = []

    def obj(self, body: str | bytes) -> int:
        self.objs.append(body.encode("latin-1") if isinstance(body, str) else body)
        return len(self.objs)

    def stream(self, head: str, data: bytes) -> int:
        return self.obj(f"<< {head} /Length {len(data)} >>\nstream\n".encode("latin-1") + data + b"\nendstream")

    def build(self, pages: list[str], fonts: dict[str, int], size: tuple[int, int] = (400, 600)) -> bytes:
        pages_id = self.obj(b"null")
        res = " ".join(f"/{k} {v} 0 R" for k, v in fonts.items())
        kids = []
        for ops in pages:
            c = self.stream("", ops.encode("latin-1"))
            kids.append(self.obj(f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {size[0]} {size[1]}] "
                                 f"/Resources << /Font << {res} >> >> /Contents {c} 0 R >>"))
        self.objs[pages_id - 1] = (f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] "
                                   f"/Count {len(kids)} >>").encode()
        cat = self.obj(f"<< /Type /Catalog /Pages {pages_id} 0 R >>")
        out = bytearray(b"%PDF-1.4\n")
        offsets = []
        for n, b in enumerate(self.objs, 1):
            offsets.append(len(out))
            out += f"{n} 0 obj\n".encode() + b + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(self.objs) + 1}\n0000000000 65535 f \n".encode()
        for o in offsets:
            out += f"{o:010d} 00000 n \n".encode()
        out += f"trailer\n<< /Size {len(self.objs) + 1} /Root {cat} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        return bytes(out)

    def helvetica(self) -> int:
        return self.obj("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")


def cmap(pairs: dict[int, str], width: int = 1) -> bytes:
    return pt.cmap_bytes(pairs, width)


def reader(data: bytes) -> PdfReader:
    return PdfReader(io.BytesIO(data))


def text_of(data: bytes) -> str:
    r = reader(data)
    pt.repair_reader(r)
    return "".join(p.extract_text() for p in r.pages)


# ---------------------------------------------------------------------------------------------- font onarımı

def test_glyph_name_reading() -> None:
    assert pt.glyph_unicode("/A.alt4") == "A"
    assert pt.glyph_unicode("Idotaccent.alt2") == "İ"
    assert pt.glyph_unicode("quoteleft.alt2") == "‘"
    assert pt.glyph_unicode("uni015F.ss01") == "ş"
    assert pt.glyph_unicode("f_i") == "fi"
    assert pt.glyph_unicode(".notdef") is None and pt.glyph_unicode("zzqq.alt") is None


def test_cmap_round_trip_with_ranges() -> None:
    raw = (b"1 begincodespacerange <0000> <FFFF> endcodespacerange\n"
           b"2 beginbfchar <0003> <0049> <0004> <00540065> endbfchar\n"
           b"2 beginbfrange <0010> <0012> <0041> <0020> <0021> [<015F> <0131>] endbfrange\n")
    m, width = pt.parse_cmap(raw)
    assert width == 2
    assert m == {3: "I", 4: "Te", 0x10: "A", 0x11: "B", 0x12: "C", 0x20: "ş", 0x21: "ı"}
    assert pt.parse_cmap(pt.cmap_bytes(m, width)) == (m, width)


def test_decorative_glyphs_mapped_to_private_use_are_read_from_glyph_names() -> None:
    """Başlık fontu: ToUnicode alternatif harfleri PUA'ya eşliyor; /Differences glifin adını taşıyor."""
    p = _Pdf()
    f1 = p.helvetica()
    tu = p.stream("", cmap({1: "\ue000", 2: "\ue001", 3: "\ue002", 4: "\ue003", 5: "K"}))
    deco = p.obj(f"<< /Type /Font /Subtype /Type1 /BaseFont /Deco /Encoding << /Type /Encoding /Differences "
                 f"[1 /B.alt4 /A.alt2 /L.alt3 /Idotaccent.alt3 /K] >> /ToUnicode {tu} 0 R >>")
    # ToUnicode'u olmayan font: okuyucu bilmediği adı olduğu gibi yazıyordu («/quoteleft.alt2»)
    bare = p.obj("<< /Type /Font /Subtype /Type1 /BaseFont /Bare /Encoding << /Type /Encoding "
                 "/BaseEncoding /WinAnsiEncoding /Differences [30 /quoteleft.alt2] >> >>")
    data = p.build(["BT /F2 20 Tf 1 0 0 1 50 500 Tm <0102030405> Tj ET\n"
                    "BT /F3 12 Tf 1 0 0 1 50 400 Tm <1E> Tj (Kalp) Tj ET"], {"F1": f1, "F2": deco, "F3": bare})
    before = "".join(pg.extract_text() for pg in reader(data).pages)
    assert "\ue000" in before and "quoteleft.alt2" in before
    after = text_of(data)
    assert "BALİK" in after and "‘Kalp" in after
    assert pt.unreadable(after) == 0


def test_unrecoverable_private_use_is_counted_not_hidden() -> None:
    p = _Pdf()
    tu = p.stream("", cmap({0x41: "\ue000", 0x42: "A"}))
    f = p.obj(f"<< /Type /Font /Subtype /Type1 /BaseFont /X /Encoding /WinAnsiEncoding /ToUnicode {tu} 0 R >>")
    # satırlar birbirinden farklı: aynı kısa satır üç kez tekrarlansa sayfa üst bilgisi sayılıp atılırdı
    body = "\n".join("BT /F1 12 Tf 1 0 0 1 50 {} Tm <41{}> Tj ET".format(500 - 14 * i, "42" * (3 + i)) for i in range(3))
    s = st.pdf_structure(reader(p.build([body], {"F1": f})))
    assert s.unreadable_chars == 3
    assert s.report()["unreadable_chars"] == 3


def _ttf_with_dotted_i() -> tuple[bytes, list[str]]:
    fb_mod = pytest.importorskip("fontTools.fontBuilder")
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    def rect(x0: int, y0: int, x1: int, y1: int):
        pen = TTGlyphPen(None)
        pen.moveTo((x0, y0)); pen.lineTo((x0, y1)); pen.lineTo((x1, y1)); pen.lineTo((x1, y0)); pen.closePath()
        return pen.glyph()

    def composite(*names: str):
        pen = TTGlyphPen(glyphs)
        for n in names:
            pen.addComponent(n, (1, 0, 0, 1, 0, 0))
        return pen.glyph()

    order = [".notdef", "I", "dotaccent", "Idotaccent", "circumflex", "Icircumflex", "dotlessi", "i"]
    glyphs = {".notdef": rect(0, 0, 400, 700), "I": rect(50, 0, 150, 700), "dotaccent": rect(60, 760, 140, 840),
              "circumflex": rect(0, 760, 240, 840), "dotlessi": rect(50, 0, 150, 500)}
    glyphs.update(Idotaccent=composite("I", "dotaccent"), Icircumflex=composite("I", "circumflex"),
                  i=composite("dotlessi", "dotaccent"))
    fb = fb_mod.FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({0x49: "I"})
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({n: (400, 0) for n in order})
    fb.setupHorizontalHeader(ascent=900, descent=-100)
    fb.setupOS2()
    fb.setupPost()
    fb.setupNameTable({"familyName": "Tst", "styleName": "Regular"})
    buf = io.BytesIO()
    fb.save(buf)
    return buf.getvalue(), order


def test_dotted_capital_i_is_read_from_the_glyph_outline() -> None:
    """CID font: noktalı İ ve noktalı i ToUnicode'da «I» / «ı» yazılmış; şapkalı Î noktaya benzemez, dokunulmaz."""
    ttf, order = _ttf_with_dotted_i()
    g = {n: i for i, n in enumerate(order)}
    p = _Pdf()
    ff = p.stream("", ttf)
    fd = p.obj(f"<< /Type /FontDescriptor /FontName /Tst /Flags 32 /FontBBox [0 -100 1000 900] /ItalicAngle 0 "
               f"/Ascent 900 /Descent -100 /CapHeight 700 /StemV 80 /FontFile2 {ff} 0 R >>")
    desc = p.obj(f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /Tst /CIDSystemInfo << /Registry (Adobe) "
                 f"/Ordering (Identity) /Supplement 0 >> /FontDescriptor {fd} 0 R /CIDToGIDMap /Identity /DW 400 >>")
    tu = p.stream("", cmap({g["I"]: "I", g["Idotaccent"]: "I", g["Icircumflex"]: "I", g["dotlessi"]: "ı",
                            g["i"]: "ı"}, 2))
    f = p.obj(f"<< /Type /Font /Subtype /Type0 /BaseFont /Tst /Encoding /Identity-H /DescendantFonts [{desc} 0 R] "
              f"/ToUnicode {tu} 0 R >>")
    codes = "".join(f"{g[n]:04X}" for n in ("Idotaccent", "I", "Icircumflex", "dotlessi", "i"))
    data = p.build([f"BT /F1 20 Tf 1 0 0 1 50 500 Tm <{codes}> Tj ET"], {"F1": f})
    assert text_of(data).strip() == "İIIıi"


def test_dot_shape() -> None:
    body = (50, 0, 150, 700)
    assert pt.has_dot_above([body, (60, 760, 140, 840)])
    assert not pt.has_dot_above([body, (0, 760, 240, 840)])        # şapka: geniş
    assert not pt.has_dot_above([body, (60, -200, 140, -120)])     # altta: çengel/nokta değil
    assert not pt.has_dot_above([body])


# ---------------------------------------------------------------------------------------------- satır okuma

LONG = "the quiet harbour kept its boats and nets in rows along the old stone wall by the sea"


def test_off_page_overprinted_and_hanging_hyphen() -> None:
    """Sayfa kutusunun dışındaki kopya okunmaz, aynı yere ikinci kez basılan metin atılır, kenara asılmış tirenin
    önündeki okuyucu boşluğu atılır ve kelime birleşir."""
    p = _Pdf()
    f1 = p.helvetica()
    ops = ["BT /F1 12 Tf 1 0 0 1 40 560 Tm (Dedication line) Tj ET",
           "BT /F1 12 Tf 1 0 0 1 40 560 Tm (Dedication line) Tj ET",            # dolgu + kontur
           "BT /F1 12 Tf 1 0 0 1 -220 300 Tm (Imprint copy on pasteboard) Tj ET",
           "BT /F1 12 Tf 1 0 0 1 520 300 Tm (Spread text from next page) Tj ET",
           f"BT /F1 12 Tf 1 0 0 1 40 500 Tm ({LONG} birlik) Tj ET",
           "BT /F1 12 Tf 1 0 0 1 395 500 Tm (-) Tj ET",
           f"BT /F1 12 Tf 1 0 0 1 40 486 Tm (te {LONG} end.) Tj ET"]
    s = st.pdf_structure(reader(p.build(["\n".join(ops)], {"F1": f1})))
    text = "\n".join(b for _, b in s.chapters)
    assert text.count("Dedication line") == 1
    assert "pasteboard" not in text and "Spread text" not in text
    assert "birlikte" in text and "birlik -" not in text


def test_drop_cap_drawn_after_its_lines_joins_the_top_line() -> None:
    p = _Pdf()
    f1 = p.helvetica()
    ops = [f"BT /F1 12 Tf 1 0 0 1 80 500 Tm (ears ago {LONG}) Tj ET",
           f"BT /F1 12 Tf 1 0 0 1 80 486 Tm ({LONG} and more) Tj ET",
           f"BT /F1 12 Tf 1 0 0 1 40 472 Tm ({LONG} end.) Tj ET",
           "BT /F1 36 Tf 1 0 0 1 40 486 Tm (Y) Tj ET"]                       # iki satır boyu, sonra çizilmiş
    s = st.pdf_structure(reader(p.build(["\n".join(ops)], {"F1": f1})))
    text = "\n".join(b for _, b in s.chapters)
    assert text.startswith("Years ago the quiet")
    assert "\nY\n" not in text


def test_single_letter_at_body_size_is_not_a_drop_cap() -> None:
    lines = [st.Line(0, "A", 12.0, y=500, x=40), st.Line(0, "Anchor: a heavy thing", 12.0, y=486, x=40),
             st.Line(0, "O", 12.0, y=470, x=40), st.Line(0, "went home", 12.0, y=456, x=40)]
    assert [ln.text for ln in st.join_drop_caps(lines, 12.0)] == [ln.text for ln in lines]


def test_heading_drawn_after_body_takes_its_place_on_the_page() -> None:
    """Başlık sayfanın metninden sonra çizilmiş: eskiden önceki bölüme ait sayılıyor, bölüm ortadan başlıyordu."""
    p = _Pdf()
    f1 = p.helvetica()
    pages = []
    for n in range(1, 4):
        body = [f"BT /F1 12 Tf 1 0 0 1 40 {420 - 14 * k} Tm (Chapter {n} line {k} {LONG}.) Tj ET" for k in range(6)]
        pages.append("\n".join(body + [f"BT /F1 24 Tf 1 0 0 1 40 480 Tm (Title Number {n}) Tj ET"]))
    s = st.pdf_structure(reader(p.build(pages, {"F1": f1})))
    assert s.source == "typography"
    assert [t for t, _ in s.chapters] == ["Title Number 1", "Title Number 2", "Title Number 3"]
    assert all(b.startswith(f"Chapter {i} line 0") for i, (_, b) in enumerate(s.chapters, 1))


def test_two_columns_keep_drawing_order() -> None:
    lines = [st.Line(0, "left column first line of text here", 12.0, y=500, x=40),
             st.Line(0, "left column second line of text here", 12.0, y=486, x=40),
             st.Line(0, "right column first line of text here", 12.0, y=500, x=220)]
    assert st.reading_order(lines, 400) == lines


def test_display_type_inside_a_sentence_is_not_a_heading() -> None:
    """Resimli kitap: «Poor hen, THE MONSTER'S NAME heard that day.» — büyük punto cümlenin parçası."""
    run = [st.Line(1, "THE MONSTER'S", 30.0), st.Line(1, "NAME", 30.0)]
    assert st.in_sentence(run, st.Line(1, "Poor hen,", 12.0), st.Line(1, "heard that day.", 12.0))
    assert st.in_sentence([st.Line(1, "The stone rolled,", 30.0), st.Line(1, "rolled...", 30.0)], None, None)
    assert st.in_sentence([st.Line(1, "lar! Vzzzz.", 30.0)], st.Line(1, "geliyor-", 12.0), st.Line(1, "Then", 12.0))
    # iki satırlık başlığın ilk satırı virgülle bitebilir; küçük harfle başlayan başlık da vardır
    assert not st.in_sentence([st.Line(1, "BAHAR GELMIS,", 14.0), st.Line(1, "DUNYA DUMDUZ OYSA", 14.0)],
                              st.Line(0, "boyledir.", 11.5), st.Line(1, "Bahar geldi.", 11.5))
    assert not st.in_sentence([st.Line(1, "birinci bolum BABAM VE YILDIZ SARAYI", 20.0)],
                              st.Line(0, "bitti.", 11.0), st.Line(1, "Babam", 11.0))
    assert not st.in_sentence([st.Line(1, "BALIK TUTMAYI OGRET...", 30.0)], st.Line(0, "bitti.", 12.0),
                              st.Line(1, "Bana balik", 12.0))
    assert not st.in_sentence([st.Line(1, "The Old Fisherman", 30.0)], None, st.Line(2, "\u201cGood morning.\u201d", 12.0))
    # önceki bölüm cümleyle bitmiş: küçük harfle başlayan gövde tek başına başlığı süs yazısı yapmaz
    assert not st.in_sentence([st.Line(1, "Cocukluk", 20.0)], st.Line(0, "herkes ona bakti.", 11.0),
                              st.Line(1, "elma armut kiraz", 11.0))


# ---------------------------------------------------------------------------------------------- 26 kitaplık kabul seti

def test_short_narrow_lines_and_hyphens_join() -> None:
    """Dar sütun (resim yanı): bütün satırlar kısa; küçük harfle süren satır aynı cümledir, heceleme birleşir."""
    lines = ["Birkac dakika gecti.", "Karni agriyormusca-", "sina kivranmaya bas-", "ladi. Yerinde duramiyordu.",
             "Uzun bir satir burada duruyor ve paragrafin olcusunu belirliyor tam olarak."]
    assert st.reflow(lines).split("\n")[:2] == ["Birkac dakika gecti.",
                                                 "Karni agriyormuscasina kivranmaya basladi. Yerinde duramiyordu."]


def _lines(*texts: str) -> list:
    return [st.Line(0, t, 11.0, y=500 - 14 * i, x=40) for i, t in enumerate(texts)]


def test_spaced_line_end_hyphen_is_syllable_break_when_book_has_no_spaced_dash() -> None:
    lines = st.mend_spaced_hyphens(_lines("uyumak yerine sosyal med -", "yada vakit harcadiniz", "annem kalkip mut -",
                                          "fağa gitti."))
    assert [ln.text for ln in lines][::2] == ["uyumak yerine sosyal med-", "annem kalkip mut-"]


def test_spaced_line_end_hyphen_uses_book_vocabulary_when_book_uses_spaced_dash() -> None:
    lines = _lines("masraflarin buyuk bir kismi - ki bunu bil - sonra kismi geldi,", "kisminin buyuk kismi -",
                   "masraflarin sayisi ve niteligi,", "uykulu ve şaş -", "kın gozlerle bakti, sonra şaşkın kaldi.",
                   "yine masraflarin ve kismi - ki bu da - yetti.")
    out = [ln.text for ln in st.mend_spaced_hyphens(lines)]
    assert out[1].endswith("kismi -")            # iki parça da kelime, birleşik hâli yok: ara çizgisi
    assert out[3].endswith("şaş-")               # birleşik hâli («şaşkın») kitapta geçiyor: heceleme


def test_private_use_letter_resolved_from_book_vocabulary() -> None:
    pua = "\uf002"
    lines = _lines(f"Sevgi Nasil A{pua}ka Donu{pua}ur?", f"A{pua}k Acilari Payla{pua}anlara Gelir",
                   "Bu kitapta ask degil aşk yazilir; aşka donuşur, paylaşanlara gelir.",
                   f"B\uf003LINMEZ {pua}EY")
    out = [ln.text for ln in st.resolve_private_letters(lines)]
    assert out[0] == "Sevgi Nasil Aşka Donuşur?" and out[1] == "Aşk Acilari Paylaşanlara Gelir"
    assert "\uf003" in out[3]                    # sözlükte karşılığı olmayan karakter kalır, okunamadı sayılır
    assert out[3].endswith("ŞEY")                 # büyük harfli kelimede büyük hâli


def test_dialog_and_quote_lines_are_not_headings_or_title_continuations() -> None:
    p = _Pdf()
    f1 = p.helvetica()
    pages = []
    for n in range(1, 4):
        body = [f"BT /F1 12 Tf 1 0 0 1 40 {420 - 14 * k} Tm (Part {n} line {k} {LONG}.) Tj ET" for k in range(6)]
        pages.append("\n".join([f"BT /F1 24 Tf 1 0 0 1 40 500 Tm (TITLE NUMBER {n}) Tj ET",
                                f"BT /F1 18 Tf 1 0 0 1 40 470 Tm (\"Big quoted line {n}) Tj ET"] + body))
    pages.append("\n".join(["BT /F1 24 Tf 1 0 0 1 40 500 Tm (- China?) Tj ET"]
                           + [f"BT /F1 12 Tf 1 0 0 1 40 {420 - 14 * k} Tm (Tail line {k} {LONG}.) Tj ET" for k in range(6)]))
    s = st.pdf_structure(reader(p.build(pages, {"F1": f1})))
    assert [t for t, _ in s.chapters] == ["TITLE NUMBER 1", "TITLE NUMBER 2", "TITLE NUMBER 3"]


def test_smaller_title_line_above_the_chapter_number_joins_the_title() -> None:
    p = _Pdf()
    f1 = p.helvetica()
    pages = []
    for n in range(1, 4):
        body = [f"BT /F1 12 Tf 1 0 0 1 40 {400 - 14 * k} Tm (Part {n} line {k} {LONG}.) Tj ET" for k in range(6)]
        pages.append("\n".join([f"BT /F1 18 Tf 1 0 0 1 40 520 Tm (UPPER TITLE {n}) Tj ET",
                                f"BT /F1 28 Tf 1 0 0 1 40 500 Tm (CHAPTER {n}) Tj ET",
                                f"BT /F1 18 Tf 1 0 0 1 40 480 Tm (LOWER TITLE) Tj ET"] + body))
    s = st.pdf_structure(reader(p.build(pages, {"F1": f1})))
    assert [t for t, _ in s.chapters] == [f"CHAPTER {n} — UPPER TITLE {n} LOWER TITLE" for n in (1, 2, 3)]


def test_font_without_text_mapping_is_unreadable_not_garbage() -> None:
    """Harf tablosu olmayan CID font (resimdeki Çince yazı): anlamsız harf yerine «�»."""
    p = _Pdf()
    f1 = p.helvetica()
    desc = p.obj("<< /Type /Font /Subtype /CIDFontType0 /BaseFont /Koz /CIDSystemInfo << /Registry (Adobe) "
                 "/Ordering (Japan1) /Supplement 6 >> /FontDescriptor << /Type /FontDescriptor /FontName /Koz "
                 "/Flags 4 /FontBBox [0 0 1000 1000] /ItalicAngle 0 /Ascent 900 /Descent -100 /CapHeight 700 "
                 "/StemV 80 >> >>")
    cid = p.obj(f"<< /Type /Font /Subtype /Type0 /BaseFont /Koz /Encoding /Identity-H /DescendantFonts [{desc} 0 R] >>")
    ops = [f"BT /F1 12 Tf 1 0 0 1 40 {500 - 14 * k} Tm (Line {k} {LONG}.) Tj ET" for k in range(3)]
    ops.append("BT /F2 30 Tf 1 0 0 1 40 300 Tm <084F4B1F0F6C> Tj ET")
    s = st.pdf_structure(reader(p.build(["\n".join(ops)], {"F1": f1, "F2": cid})))
    text = "\n".join(b for _, b in s.chapters)
    assert "\ufffd\ufffd\ufffd" in text and "\u084f" not in text and s.unreadable_chars == 3


def test_symbol_font_bullets() -> None:
    p = _Pdf()
    tu = p.stream("", cmap({0xD8: "\uf0d8"}))
    wing = p.obj(f"<< /Type /Font /Subtype /Type1 /BaseFont /ABCDEF+Wingdings-Regular /ToUnicode {tu} 0 R >>")
    f1 = p.helvetica()
    data = p.build(["BT /F2 12 Tf 1 0 0 1 40 500 Tm <D8> Tj /F1 12 Tf ( Madde) Tj ET"], {"F1": f1, "F2": wing})
    assert text_of(data).strip() == "• Madde"


def test_small_l_standing_in_for_dotless_i() -> None:
    """Fontunda ı olmayan başlık: dizgici ı yerine küçültülmüş «l» basmış (iki kez: dolgu + kontur)."""
    p = _Pdf()
    f1 = p.helvetica()
    ops = ["BT /F1 28 Tf 1 0 0 1 100 500 Tm (Bal) Tj ET", "BT /F1 20 Tf 1 0 0 1 140.5 500 Tm (l) Tj ET",
           "BT /F1 20 Tf 1 0 0 1 140.5 500 Tm (l) Tj ET", "BT /F1 28 Tf 1 0 0 1 145 500 Tm (\\370k) Tj ET",
           "BT /F1 28 Tf 1 0 0 1 100 460 Tm (Normal l harfi kalir) Tj ET"]
    ops += [f"BT /F1 12 Tf 1 0 0 1 40 {400 - 14 * k} Tm (Line {k} {LONG}.) Tj ET" for k in range(3)]
    s = st.pdf_structure(reader(p.build(["\n".join(ops)], {"F1": f1})))
    text = "\n".join(f"{t}\n{b}" for t, b in s.chapters)
    assert "Balıøk" in text and "Normal l harfi" in text
