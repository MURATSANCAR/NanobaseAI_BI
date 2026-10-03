"""Dizgiden bölüm bulma (`editor.chapters`) ve Stüdyo'nun bu bölümlere paragraf dağıtması (`split_typeset`).

Sahte sayfa düzeniyle: PDF gerekmez. Kitaptan bağımsız dizgi alışkanlıkları sınanır: normal yazımlı başlık
(«Avokado»), sayfa başlığı tekrarı, başlık sayfası + metin sonraki sayfada, iç kapakta kitap adı."""

from types import SimpleNamespace

from editor import chapters as typeset
from editor.production.manuscript import split_typeset

H = 600.0
BODY = 10.0
LONG = "Sabah erkenden kalktı ve dükkânın kepengini yavaşça kaldırdı, içeri serin bir koku doldu."


def _body(y0: float, n: int = 20) -> list[dict]:
    return [{"text": LONG, "y0": y0 + 14 * k, "size": BODY} for k in range(n)]


def _page(lines: list[dict], header: str | None = None) -> SimpleNamespace:
    if header:
        lines = [{"text": header, "y0": 20, "size": 8.0}] + lines
    return SimpleNamespace(rect=SimpleNamespace(height=H), lines=lines)


def _lines(p):
    return p.lines


def _pages(doc):
    return [{"page_no": i, "spans": [{"text": ln["text"]} for ln in p.lines]} for i, p in enumerate(doc, 1)]


def _book():
    """1 iç kapak · 2 «Avokado» (metinden aşağıda, altında boşluk) · 3–4 metin · 5 başlık sayfası
    «Böcek Kapan Menekşe» · 6–7 metin. Her metin sayfasında küçük puntolu kitap adı tekrarlanır."""
    doc = [
        _page([{"text": "Çiçekçi Kadın", "y0": 200, "size": 24.0}]),
        _page([{"text": "Avokado", "y0": 180, "size": 14.0}] + _body(240, 14)),
        _page(_body(60), header="Çiçekçi Kadın"),
        _page(_body(60), header="Çiçekçi Kadın"),
        _page([{"text": "Böcek Kapan Menekşe", "y0": 250, "size": 16.0}]),
        _page([{"text": "Kepenk", "y0": 180, "size": 14.0}] + _body(240, 14), header="Çiçekçi Kadın"),
        _page(_body(60), header="Çiçekçi Kadın"),
    ]
    return doc


def test_mixed_case_headings_from_typesetting():
    doc = _book()
    found = typeset.chapters_from_pages(_pages(doc), typeset.page_headings(doc, _lines), "Çiçekçi Kadın")
    titles = [(c["title"], c["page_from"]) for c in found]
    assert ("Avokado", 2) in titles
    # başlık sayfası ile sonraki sayfanın açılışı tek bölüm; sonraki sayfanın başlığı («Kepenk») bölümün ilk ara
    # başlığıdır, bölüm adına eklenmez (2026-10-03: «AŞKIN MAHİYETİ AŞK, İNSANIN YAŞADIĞI…» birleşiyordu)
    assert ("Böcek Kapan Menekşe", 5) in titles
    assert next(c for c in found if c["page_from"] == 5)["page_to"] == 7
    # iç kapaktaki kitap adı ve sayfa başlığı tekrarı bölüm değil
    assert not any("Çiçekçi" in t for t, _ in titles)
    assert len([t for t, _ in titles if t != "Başlıksız başlangıç"]) == 2


def test_large_first_line_running_into_a_sentence_is_not_a_heading():
    """Sahne arasından sonra büyük puntolu ilk satır: paragraf aynı cümleyle sürer, bölüm açılmaz."""
    lead = "Dükkânı için özel bir e-posta hesabı oluşturduktan sonra"
    doc = [_page([{"text": "Avokado", "y0": 180, "size": 14.0}] + _body(240, 14)),
           _page(_body(60)),
           _page([{"text": lead, "y0": 60, "size": 16.0}] + _body(100, 18))]
    pages = _pages(doc)
    pages[2]["spans"] = [{"text": lead + " Yuhui’nin o kısa e-postası bütün haftayı değiştirdi, kimse bilmiyordu."}]
    found = typeset.chapters_from_pages(pages, typeset.page_headings(doc, _lines))
    assert [c["title"] for c in found] == ["Avokado"]


def test_plain_body_pages_are_not_openings():
    doc = [_page(_body(60)) for _ in range(5)]
    found = typeset.chapters_from_pages(_pages(doc), typeset.page_headings(doc, _lines))
    assert found == [{"title": "Kitap", "page_from": 1, "page_to": 5}]


def test_ad_and_contents_pages_are_not_chapters():
    doc = [_page([{"text": "İçindekiler", "y0": 100, "size": 16.0}]),
           _page([{"text": "Avokado", "y0": 180, "size": 14.0}] + _body(240, 14)),
           _page(_body(60)),
           _page([{"text": "Yeni kitap önerimiz için karekodu okutun", "y0": 100, "size": 16.0}])]
    found = typeset.chapters_from_pages(_pages(doc), typeset.page_headings(doc, _lines))
    assert [c["title"] for c in found if c["title"] != "Başlıksız başlangıç"] == ["Avokado"]


def test_split_typeset_takes_title_from_read_text():
    chapters = [{"title": "Başlıksız başlangıç", "page_from": 1, "page_to": 1},
                {"title": "G‹R‹Ş", "page_from": 2, "page_to": 3},
                {"title": "Avokado", "page_from": 4, "page_to": 5}]
    paras = [(1, "Annem için."), (2, "GİRİŞ"), (2, LONG), (3, LONG),
             (4, "Avokado"), (4, LONG), (5, "kaldığı yerden sürdü.")]
    out = split_typeset(chapters, paras)
    assert [c.title for c in out] == [None, "GİRİŞ", "Avokado"]
    assert all(b.text != "Avokado" for b in out[2].blocks)
    assert len(out[1].blocks) == 2


def test_split_typeset_keeps_upper_case_lines_inside_a_chapter():
    chapters = [{"title": "Avokado", "page_from": 1, "page_to": 1},
                {"title": "Agave", "page_from": 2, "page_to": 2}]
    paras = [(1, "Avokado"), (1, "DİKKAT"), (1, LONG), (2, "Agave"), (2, LONG)]
    out = split_typeset(chapters, paras)
    assert [c.title for c in out] == ["Avokado", "Agave"]
    assert out[0].blocks[0].text == "DİKKAT"


def test_split_typeset_single_book_chapter_is_no_information():
    assert split_typeset([{"title": "Kitap", "page_from": 1, "page_to": 3}], [(1, LONG)]) is None


def test_resplit_splits_only_where_layout_paragraph_starts_are_found():
    from editor.production.manuscript import resplit
    text = "Kadın durdu ve baktı. “Ah, yapraklara dikkat eder misiniz?” Yuhui saksıları işaret etti."
    parts = ["Kadın durdu ve baktı.", "“Ah, yapraklara dikkat eder misiniz?”", "Yuhui saksıları işaret etti.",
             "Bu satır okunmuş metinde yok ve atlanır."]
    assert resplit(text, parts) == parts[:3]
    assert resplit(text, ["tek"]) == [text]


def test_chapter_without_text_is_dropped():
    chapters = [{"title": "Avokado", "page_from": 1, "page_to": 1},
                {"title": "Agave", "page_from": 2, "page_to": 2},
                {"title": "Yazarın Notu", "page_from": 3, "page_to": 3}]
    out = split_typeset(chapters, [(1, "Avokado"), (1, LONG), (2, "Agave"), (2, LONG)])
    assert [c.title for c in out] == ["Avokado", "Agave"]


def test_spaced_paragraphs_from_layout():
    """Girintisiz, önünde boşluk bırakılan paragraflar: satır aralığı 18 pt, paragraf arası 24 pt."""
    import pymupdf
    from editor.document import paragraphs_from_layout
    doc = pymupdf.open()
    page = doc.new_page(width=420, height=600)
    y = 80.0
    for para in (["Kadın pencerenin dibindeki ağacın önünde", "durdu ve uzun uzun baktı."],
                 ["“Ah, yapraklara dikkat eder misiniz", "lütfen?” dedi Yuhui telaşla."],
                 ["Kadın başını iki yana salladı, sonra", "kapıya yürüdü"]):
        for line in para:
            page.insert_text((60, y), line, fontsize=11)
            y += 18
        y += 6
    assert len(paragraphs_from_layout(page)) == 1
    spaced = paragraphs_from_layout(page, spaced=True)
    assert len(spaced) == 3 and "Ah, yapraklara" in spaced[1]   # sahte PDF fontunda Türkçe harf yok


def _ln(text, y0, size, x0=60.0, x1=None):
    return {"text": text, "y0": y0, "size": size, "x0": x0, "x1": x1 if x1 is not None else x0 + 7 * len(text)}


def test_multi_line_heading_in_large_type_is_not_cut_by_its_own_leading():
    """34 pt başlığın iki satırı arası 40 pt (gövde satır aralığının iki katı): başlık bölünmez."""
    pages = [_page([_ln("BEYNİMDEN", 140, 34.0), _ln("CIZIRTILAR GELİYOR", 180, 34.0)] + _body(260, 18))
             for _ in range(1)] + [_page(_body(60)) for _ in range(3)]
    found = typeset.chapters_from_pages(_pages(pages), typeset.page_headings(pages, _lines))
    assert found[0]["title"] == "BEYNİMDEN CIZIRTILAR GELİYOR"


def test_two_line_heading_slightly_above_body_size():
    """Gövde 10 pt, başlık 11 pt iki satır, altında boşluk («YER ALTI / OYUNLARI»)."""
    doc = [_page([_ln("YER ALTI", 60, 11.0), _ln("OYUNLARI", 74, 11.0)] + _body(110, 18)),
           _page(_body(60)), _page([_ln("İLK", 60, 11.0), _ln("DENEY", 74, 11.0)] + _body(110, 18)), _page(_body(60))]
    found = typeset.chapters_from_pages(_pages(doc), typeset.page_headings(doc, _lines))
    assert [c["title"] for c in found] == ["YER ALTI OYUNLARI", "İLK DENEY"]


def test_side_label_does_not_split_the_heading():
    """Sağda «BÖLÜM 1» etiketi başlığın iki satırının arasındaki yükseklikte: başlık karışmaz."""
    doc = [_page([_ln("OSMANLI MERKEZ VE TAŞRA", 110, 16.6, 97, 300), _ln("BÖLÜM 1", 120, 25.8, 333, 400),
                  _ln("MÜLKÎ-MALÎ İDARESİ", 135, 16.6, 97, 280)] + _body(200, 18)), _page(_body(60))]
    found = typeset.chapters_from_pages(_pages(doc), typeset.page_headings(doc, _lines))
    assert found[0]["title"] == "BÖLÜM 1 OSMANLI MERKEZ VE TAŞRA MÜLKÎ-MALÎ İDARESİ"


def test_large_type_sentence_is_not_a_heading():
    """Resimli kitapta iri puntolu konuşma («Tabii ki FİLİN!») bölüm başlığı değildir."""
    assert typeset._sentence("Tabii ki FİLİN!") and typeset._sentence("O sırada sanki başında minik dikenler beliriyordu.")
    assert not any(typeset._sentence(t) for t in ("BİTTİK BİZ!", "GECELER!", "sensİz!", "1.", "Hazan Ağlar Baharında...",
                                                   "MaCeRa DeDİğİn BuDuR DoStUm!"))
