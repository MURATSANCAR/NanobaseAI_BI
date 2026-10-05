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


# ---------------------------------------------------------------- K16: iç kapakta künye/imza satırları
def _cover_book(cover: list[dict], n: int = 12) -> list:
    """1 iç kapak (verilen satırlar) · 2..n metin. Başka açılış yok: tek bölümlü resimli kitap."""
    return [_page(cover)] + [_page(_body(60)) for _ in range(n - 1)]


def _found(doc, titles, names=()):
    return typeset.chapters_from_pages(_pages(doc), typeset.page_headings(doc, _lines), titles, names)


def test_inner_cover_with_author_and_illustrator_is_not_a_chapter():
    """K16 «Levent Adana'da»: «ADANA’DA Mustafa Orakçı Çizer: Derya Işık Özbay» bölüm adı oluyordu. Kıvrık kesme
    (U+2019) ve seri adıyla başlayan kitap adı: «ADANA’DA» ↔ «Levent Adana'da»."""
    doc = _cover_book([{"text": "ADANA’DA", "y0": 190, "size": 29.0},
                       {"text": "Mustafa Orakçı", "y0": 255, "size": 16.0},
                       {"text": "Çizer: Derya Işık Özbay", "y0": 280, "size": 13.0}])
    assert [c["title"] for c in _found(doc, ["Levent Adana'da"], ["Mustafa Orakçı"])] == ["Kitap"]
    # künye TITLE iddiası da kitabın adıdır
    assert [c["title"] for c in _found(doc, ["kitap 5", "ADANA’DA"], ["Mustafa Orakçı"])] == ["Kitap"]
    # adı tutmasa da tek açılış ilk sayfalardaki başlık sayfasıysa iç kapaktır
    assert [c["title"] for c in _found(doc, "Başka Ad")] == ["Kitap"]


def test_byline_is_cut_from_the_title():
    s = typeset._strip_byline
    assert s("ADANA’DA Mustafa Orakçı Çizer: Derya Işık Özbay", ["Mustafa Orakçı"]) == "ADANA’DA"
    assert s("Kayıp Şehir Resimleyen: Ayşe Kaya") == "Kayıp Şehir"
    assert s("Kayıp Şehir ÇEVİREN: Ali Can") == "Kayıp Şehir"
    assert s("Kayıp Şehir Yayına Hazırlayan: Ali Can") == "Kayıp Şehir"
    assert s("Yazan: Ali Can") == ""
    assert s("Mustafa Orakçı Kayıp Şehir", ["Mustafa Orakçı"]) == "Kayıp Şehir"
    # yanlış pozitif sınırları: «Yazar» kelimesi geçen gerçek ad, ekli ad, yazarı olmayan ad, tek kelimelik ad
    assert s("Yazarın Dönüşü", ["Mustafa Orakçı"]) == "Yazarın Dönüşü"
    assert s("Mustafa Kemal'in Çocukluğu", ["Ali Can"]) == "Mustafa Kemal'in Çocukluğu"
    assert s("Mustafa Kemal'in Çocukluğu", ["Mustafa Kemal"]) == "Mustafa Kemal'in Çocukluğu"
    assert s("Derya Kıyısında", ["Derya"]) == "Derya Kıyısında"
    # imza yoksa başlık olduğu gibi kalır (sondaki çizgi dahil)
    assert s("EK 2: Selanik Vilayeti –Kuruş-", ["Ali Can"]) == "EK 2: Selanik Vilayeti –Kuruş-"


def test_real_chapters_survive_the_byline_rule():
    doc = [
        _page([{"text": "Çiçekçi Kadın", "y0": 200, "size": 24.0},
               {"text": "Yazar: Ali Can", "y0": 260, "size": 13.0}]),
        _page(_body(60)),
        _page([{"text": "Yazarın Dönüşü", "y0": 250, "size": 16.0}]),
        _page(_body(60)), _page(_body(60)),
        _page([{"text": "Mustafa Kemal'in Çocukluğu", "y0": 250, "size": 16.0}]),
        _page(_body(60)), _page(_body(60)),
    ]
    found = [(c["title"], c["page_from"]) for c in _found(doc, "Çiçekçi Kadın", ["Ali Can"])]
    assert ("Yazarın Dönüşü", 3) in found and ("Mustafa Kemal'in Çocukluğu", 6) in found
    assert not any("Çiçekçi" in t or "Ali Can" in t for t, _ in found)


def test_scattered_letter_heading_is_not_a_chapter_name():
    """Dalgalı dizilmiş resimli kitap başlığı harf harf okunur («G İ D İ E»): zayıf adayken bölüm açmaz."""
    assert typeset._scattered("G İ D İ E") and typeset._scattered("U Ğ")
    assert not any(typeset._scattered(t) for t in ("1.", "A", "Ali ve Veli", "II. Kısım", "C Vitamini"))
    heads = {3: {"title": "G İ D İ E", "size": 25.0, "kind": "head"},
             8: {"title": "Yağ Camii", "size": 25.0, "kind": "head"}}
    pages = [{"page_no": i, "spans": [{"text": LONG}]} for i in range(1, 13)]
    assert [c["title"] for c in typeset.chapters_from_pages(pages, heads)] == ["Başlıksız başlangıç", "Yağ Camii"]


# ------------------------------------------------------------------ 56 kitap denetimi (2026-10-03)
def _starts(heads: dict, n: int = 40, texts: dict | None = None):
    pages = [{"page_no": i, "spans": [{"text": (texts or {}).get(i, LONG)}]} for i in range(1, n + 1)]
    return [(c["title"], c["page_from"]) for c in typeset.chapters_from_pages(pages, heads)]


def test_repeated_single_letter_or_roman_chapter_names_are_numbered():
    heads = {p: {"title": "I", "size": 20.0, "kind": "page"} for p in (13, 19, 25, 31)}
    assert [t for t, _ in _starts(heads)][1:] == ["I", "II", "III", "IV"]
    heads = {p: {"title": "x", "size": 20.0, "kind": "page"} for p in (13, 19, 25)}
    assert [t for t, _ in _starts(heads)][1:] == ["1. Bölüm", "2. Bölüm", "3. Bölüm"]
    # iki kez tekrar ya da anlamlı ad: dokunulmaz
    heads = {13: {"title": "I", "size": 20.0, "kind": "page"}, 19: {"title": "I", "size": 20.0, "kind": "page"}}
    assert [t for t, _ in _starts(heads)][1:] == ["I", "I"]
    heads = {p: {"title": "NE YAPMALI?", "size": 20.0, "kind": "sunk"} for p in (13, 19, 25)}
    assert [t for t, _ in _starts(heads)][1:] == ["NE YAPMALI?"] * 3


def test_lower_case_mid_sentence_line_is_not_a_chapter_name():
    heads = {13: {"title": "KEŞİF GÖREVİ", "size": 14.0, "kind": "sunk"},
             19: {"title": "nasıl kaçabileceğini düşünürken uzun süre uyuyama- dı ancak", "size": 10.0,
                  "kind": "sunk"},
             25: {"title": "YENİ GÜN", "size": 14.0, "kind": "sunk"}}
    assert [t for t, _ in _starts(heads)] == ["Başlıksız başlangıç", "KEŞİF GÖREVİ", "YENİ GÜN"]
    # başlıkları bilerek küçük harfle dizilmiş kitap: uzun küçük harfli başlık da başlıktır
    heads = {13: {"title": "arayış", "size": 14.0, "kind": "sunk"},
             19: {"title": "yol içre yol, sır içre sır", "size": 14.0, "kind": "sunk"},
             25: {"title": "kalkmak için düşmek gerek", "size": 14.0, "kind": "sunk"}}
    assert [t for t, _ in _starts(heads)][1:] == ["arayış", "yol içre yol, sır içre sır", "kalkmak için düşmek gerek"]
    # satır sonu bölünmesi her kitapta gövdedir
    assert typeset._mid_sentence("ne yapacağını bilemeden bekle- di", True)
    assert not typeset._mid_sentence("Anne-Baba", False)


def test_dedication_page_does_not_open_a_chapter():
    heads = {2: {"title": "Siyah Lale’ye ithaf olunur…", "size": 12.0, "kind": "page"},
             12: {"title": "BİR DELİLİK YAPMALIYIM", "size": 16.0, "kind": "page"}}
    texts = {2: "Siyah Lale’ye ithaf olunur…"}
    assert [t for t, _ in _starts(heads, texts=texts)] == ["Başlıksız başlangıç", "BİR DELİLİK YAPMALIYIM"]
    # ithaf sözü olmadan, ilk sayfalarda «Ad'a» satırı
    heads = {1: {"title": "Annem Ayşe’ye", "size": 12.0, "kind": "page"},
             12: {"title": "Birinci Gün", "size": 16.0, "kind": "page"}}
    assert [t for t, _ in _starts(heads, texts={1: "Annem Ayşe’ye"})] == ["Başlıksız başlangıç", "Birinci Gün"]


def test_weakly_scattered_heading_is_not_a_chapter_name():
    for t in ("KS DE T O", "İ L Gİ R E", "LARI UN K A MU", "e v miş git", "M Zİ Bİ ÜKOSMAN Y"):
        assert typeset._scattered_weak(t), t
    for t in ("1. BÖLÜM", "BÖLÜM 12", "5. Paylaşma", "Ali ve Su", "NE YAPMALI?", "A'dan Z'ye", "Ve Kazanan...",
              "II. Kısım", "C Vitamini", "O da Ben", "1. FASL"):
        assert not typeset._scattered_weak(t), t
    heads = {13: {"title": "KS DE T O", "size": 20.0, "kind": "page"},
             19: {"title": "Yağ Camii", "size": 20.0, "kind": "page"}}
    assert [t for t, _ in _starts(heads)] == ["Başlıksız başlangıç", "Yağ Camii"]


def test_part_of_the_book_title_needs_half_of_its_letters():
    assert typeset._is_book_title("ADANA’DA", "Levent Adana'da")
    assert typeset._is_book_title("Adana'da", "Levent Adana’da") and typeset._is_book_title("LEVENT ADANA'DA", "Levent Adana'da")
    assert not typeset._is_book_title("Giriş", "Giriş Sanatı Üzerine")
    assert not typeset._is_book_title("Adana", "Levent Adana'da")


def test_perde_page_with_roman_part_number_and_parenthesized_line():
    """Perde sayfası «II. BÖLÜM / BEN YÜRÜRKEN / (Yıldırım Bayezid Han)»: «I.» sıra noktası cümle sonu değil, ayraç
    içi alt satır başlık sayfasını bozmaz ama ada girmez; sonraki sayfanın «I» alt başlığı bölüm adı olmaz (Devlerin
    Savaşı'nda bütün bölümler «I» adını alıyordu)."""
    assert typeset._title_like("II. BÖLÜM") and not typeset._sentence("II. BÖLÜM BEN YÜRÜRKEN")
    assert typeset._title_like("Gabriel G. Marquez") and not typeset._title_like("Kapıyı açtı. Sonra")
    doc = [
        _page(_body(60)), _page(_body(60)),
        _page([_ln("II. BÖLÜM", 193, 16.0, 185, 273), _ln("BEN YÜRÜRKEN", 222, 16.0, 159, 299),
               _ln("(Yıldırım Bayezid Han)", 303, 11.5, 176, 282)]),
        _page([]),
        _page([_ln("I", 191, 14.0, 226, 232)] + _body(240, 14)),
        _page(_body(60)),
    ]
    found = typeset.chapters_from_pages(_pages(doc), typeset.page_headings(doc, _lines), "Devlerin Savaşı")
    assert ("II. BÖLÜM BEN YÜRÜRKEN", 3) in [(c["title"], c["page_from"]) for c in found]
    assert not any(c["title"] == "I" for c in found)


def test_continued_title_page_does_not_repeat_the_title():
    """Yan çevrilmiş ek tablosunun ikinci sayfası «EK 2: … (Devam)»: önceki başlığın sürmesi, ada eklenmez."""
    title = "EK 2: Selanik Vilayeti Toplam Gelir-Gider"
    doc = [
        *[_page(_body(60)) for _ in range(8)],
        _page([_ln(title, 219, BODY, 76, 90)]),
        _page([_ln(title + " (Devam)", 197, BODY, 50, 63)]),
        _page(_body(60)),
    ]
    found = typeset.chapters_from_pages(_pages(doc), typeset.page_headings(doc, _lines), "Taşra Maliyesi")
    assert [(c["title"], c["page_from"], c["page_to"]) for c in found if c["page_from"] == 9] == [(title, 9, 11)]


def test_word_space_given_only_by_position_between_spans():
    """Aynı satırda iki parça arasındaki kelime arası karakter değil, konumla verilmişse boşluk konur
    («dergisinin» + «okurlarına» yapışıyordu); bitişik parçalar (üst simge, italik geçişi) bitişik kalır."""
    from editor.document import _join_spans
    a = {"bbox": (75, 0, 107, 11), "size": 11.0}
    b = {"bbox": (110, 0, 160, 11), "size": 11.0}
    c = {"bbox": (160.2, 0, 166, 8), "size": 7.0}
    assert _join_spans([a, b, c], ["dergisinin", "okurlarına", "18"]) == "dergisinin okurlarına18"
    assert _join_spans([a, b], ["dergisinin", "okurlarına"], horizontal=False) == "dergisininokurlarına"


def test_unreadable_and_sentence_openings_and_contents_are_not_chapters():
    """Bozuk kodlamalı başlık («ýaý.$%+ý,%2»), resimli kitabın iri puntolu ilk cümlesi, «İÇINDEKILER» (karışık İ/I)
    bölüm açmaz; cümle biçimli başlık yazımı çoğunluktaysa (şiir dizeleri) başlıklar kalır."""
    assert typeset._garbled("ýaý.$%+ý,%2") and typeset._garbled("L{9KJ\x03F7Hw7B7H?")
    assert not typeset._garbled("Kitaplardan Nefret Ediyorum") and not typeset._garbled("NE YAPMALI?")
    assert typeset._sentence_like("Çengel zıplaya zıplaya zıpladı")
    assert not typeset._sentence_like("Balığı Olmayan Kız") and not typeset._sentence_like("üçüncü baskıya önsöz")
    assert typeset._skip("İÇINDEKILER", "x", 50, 200)

    def book(first_lines):
        doc = [_page(_body(60)) for _ in range(8)]
        for t in first_lines:
            doc += [_page([_ln(t, 180, 14.0)] + _body(240, 14)), _page(_body(60))]
        return doc
    pic = book(["Çengel zıplaya zıplaya zıpladı"])
    found = typeset.chapters_from_pages(_pages(pic), typeset.page_headings(pic, _lines), "Çengel")
    assert [c["title"] for c in found] == ["Kitap"]
    poems = book(["Kalbimizden âleme bakan göz kör olur", "Kalmadı bizden başka düşman dünyada",
                  "Yedi başlı ejderha yürüdü bahçemize"])
    found = typeset.chapters_from_pages(_pages(poems), typeset.page_headings(poems, _lines), "Çanakkale")
    assert "Kalmadı bizden başka düşman dünyada" in [c["title"] for c in found]
