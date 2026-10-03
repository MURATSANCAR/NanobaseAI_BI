"""Okuma denetimi düzeltmeleri A — sayfa yapısı (2026-10-03, 25 kitap denetimi). Sahte sayfa/dizgi verisiyle; PDF ve
DB gerekmez. Her sınıf için hem düzeltme hem yanlış pozitif sınırı sınanır:

- K2 sayfa başlığı/altlığı (`running_head`, `source`, `chapters`): yazar/kitap adı sayfa kenarında gövde sayılmaz.
- K4 özel ad testi (`naming.is_proper_name`): çok sözcüklü ad cümle başında da kanıttır.
- K9 bölüm başlığı (`chapters`): iki parçalı başlık, alt başlık, iç kapak, dipnot imi, fotoğraf altı.
- K5 kapsam dışı sayfa (`page_scope`): teşekkür, tek satırlık epigraf, yayınevi notu, yazar notu/etkinlik/ek; uç
  sayfa (`outputs.edge_pages`).
"""
from types import SimpleNamespace

from editor import chapters as typeset
from editor import naming, outputs, page_scope, running_head, source

BODY = ("Sabah erkenden kalktı ve dükkânın kepengini yavaşça kaldırdı, içeri serin bir koku doldu; sokak "
        "henüz uyanmamıştı ve martılar çatıların üstünde dönüp duruyordu.")
NONFIC = ("Ahlak, insanın yapıp etmelerini ve bu yapıp etmelerin dayandığı huyları inceleyen bir ilimdir; "
          "bu bölümde onun kaynakları ele alınır ve düşünürlerin görüşleri sırayla değerlendirilir.")


# ------------------------------------------------------------------ K2 sayfa başlığı/altlığı
def _memoir(n=60):
    """Sol (çift) sayfada yazar adı, sağ (tek) sayfada kitap adı; sayfa numarası başlığın içinde ya da ayrı blok."""
    texts = {}
    for p in range(1, n + 1):
        head = f"{p} AYŞE YILMAZ" if p % 2 == 0 else f"BABAMIN EVİ {p}"
        texts[p] = f"{head}\n\n{BODY}\n\n{BODY}"
    texts[1] = "BABAMIN EVİ"                       # iç kapak: tek bloklu sayfa sayfa başlığı taşımaz
    texts[2] = "Ayşe Yılmaz Babamın Evi\n\nISBN 978-605-00-0000-0"
    return texts


def test_book_level_running_heads_by_parity_and_page_numbers():
    marks = running_head.detect_texts(_memoir())
    assert marks[10] == {"top"} and marks[11] == {"top"}
    assert 1 not in marks                           # iç kapak
    assert 2 not in marks                           # künye: «Ayşe Yılmaz Babamın Evi» başka anahtar
    assert sum(1 for m in marks.values() if "top" in m) == 58


def test_running_foot_and_letter_spaced_head():
    texts = {p: f"{BODY}\n\nD İ J İ T A L  D Ü N Y A | {p}" for p in range(1, 41)}
    marks = running_head.detect_texts(texts)
    assert all(marks[p] == {"bottom"} for p in range(1, 41))


def test_chapter_heads_on_the_free_side():
    """Çift sayfada kitap adı, tek sayfada bölüm adı (bölüm başına birkaç sayfa)."""
    texts = {}
    for p in range(1, 61):
        chapter = "AÇIKLIK" if p <= 30 else "KABUL"
        head = "TAKILI ZİHİN" if p % 2 == 0 else chapter
        texts[p] = f"{head}\n\n{BODY}"
    marks = running_head.detect_texts(texts)
    assert marks[3] == {"top"} and marks[33] == {"top"}


def test_no_running_head_in_picture_book_or_dialogue():
    # her sayfa tek blok (resimli kitap): aday yok
    assert running_head.detect_texts({p: "Tavşan zıpladı, havuç yedi." for p in range(1, 31)}) == {}
    # tekrarlanan konuşma satırı cümle gibi biter ya da çizgiyle açılır: aday değil
    texts = {p: f"— Geliyorum!\n\n{BODY}\n\nKapıyı açtı." for p in range(1, 41)}
    assert running_head.detect_texts(texts) == {}
    # kitapta kitap başlığı yokken tek yüzde 3 kez tekrar eden kısa satır sayfa başlığı değildir
    texts = {p: f"{BODY}\n\n{BODY}" for p in range(1, 61)}
    for p in (11, 13, 15):
        texts[p] = f"Ertesi gün\n\n{BODY}"
    assert running_head.detect_texts(texts) == {}


def test_window_edges_match_full_text():
    long = f"23 AYŞE YILMAZ\n\n{BODY * 6}\n\n{BODY * 6}\n\nAYŞE YILMAZ"
    full = running_head.edges_of(long)
    win = running_head.edge_texts(long[:running_head.WINDOW], long[-running_head.WINDOW:], len(long))
    assert full == win == {"top": "23 AYŞE YILMAZ", "bottom": "AYŞE YILMAZ"}


def _proj(text, running=frozenset()):
    return source.project_page("g", {"page_no": 4, "needs_ocr": False},
                               [{"source": "TEXT_LAYER", "text": text}], None, running)


def test_source_marks_running_head_span_and_reading_skips_it():
    page = _proj(f"4 AYŞE YILMAZ\n\n{BODY}", {"top"})
    assert [s["role"] for s in page["spans"]] == ["running_head", "body"]
    assert "AYŞE YILMAZ" not in source.numbered(page) and "[s4 p2]" in source.numbered(page)
    assert source.body_text([page]) == BODY
    # rol span kimliğine girmez: eski kanıtın span bağı geçerli kalır
    assert page["spans"][0]["span_id"] == _proj(f"4 AYŞE YILMAZ\n\n{BODY}")["spans"][0]["span_id"]


def test_characters_named_only_by_running_heads_are_hidden():
    page = _proj(f"4 AYŞE YILMAZ\n\n{BODY} Ali geldi.", {"top"})
    head, body = page["spans"]
    ref = lambda s: {"spans": [{"span_id": s["span_id"]}]}  # noqa: E731
    chars = [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}]
    mentions = [{"character_id": "a", "page_no": 4, "quote": "AYŞE YILMAZ", "kind": "TEXT", "source_refs": ref(head)},
                {"character_id": "a", "page_no": 4, "quote": "AYŞE YILMAZ", "kind": "TEXT", "source_refs": {}},
                {"character_id": "b", "page_no": 4, "quote": "AYŞE YILMAZ", "kind": "TEXT", "source_refs": ref(head)},
                {"character_id": "b", "page_no": 4, "quote": "Ali geldi", "kind": "TEXT", "source_refs": ref(body)},
                {"character_id": "c", "page_no": 4, "quote": "kadın", "kind": "VISUAL", "source_refs": {}}]
    assert running_head.characters_only_in_heads(chars, mentions, [page]) == {"a"}   # d: anması yok, hüküm yok


def _pg(lines, h=600.0):
    return SimpleNamespace(rect=SimpleNamespace(height=h), lines=lines)


def _ln(text, y0, size=10.0, x0=60.0):
    return {"text": text, "y0": y0, "size": size, "x0": x0, "x1": x0 + 6 * len(text)}


def _body(y0, n=18):
    return [_ln(BODY[:90], y0 + 14 * k) for k in range(n)]


def test_body_size_running_head_is_not_a_chapter_and_opening_keeps_its_title():
    """Sayfa başlığı gövde puntosunda («AYŞE YILMAZ» 10 pt, sayfanın tepesinde): bölüm adı sağ sayfanın başlığıysa
    bölümün açılış sayfasındaki aynı ad (aşağıda, büyük) ayıklanmaz."""
    doc = []
    for p in range(1, 41):
        chapter = "GECE" if p < 21 else "ŞAFAK"
        if p in (5, 21):
            doc.append(_pg([_ln(chapter, 150, 16.0)] + _body(200, 14)))
        else:
            doc.append(_pg([_ln("AYŞE YILMAZ" if p % 2 == 0 else chapter, 30)] + _body(60)))
    pages = [{"page_no": i, "spans": [{"text": ln["text"]} for ln in d.lines]} for i, d in enumerate(doc, 1)]
    found = typeset.chapters_from_pages(pages, typeset.page_headings(doc, lambda p: p.lines))
    assert [(c["title"], c["page_from"]) for c in found if c["title"] != "Başlıksız başlangıç"] == \
        [("GECE", 5), ("ŞAFAK", 21)]


# ------------------------------------------------------------------ K4 özel ad testi
def test_multi_word_name_at_sentence_starts_is_a_name():
    text = "Ayşe Yılmaz kapıyı açtı. Sonra oturdu.\nAyşe Yılmaz pencereye baktı."
    assert naming.usage("Ayşe Yılmaz", text) == (0, 0)
    assert naming.is_proper_name("Ayşe Yılmaz", text, min_share=0.8, min_uses=2)


def test_sentence_start_lowercase_rest_and_labels_are_no_evidence():
    assert not naming.is_proper_name("Kitabın Yazarı", "Kitabın yazarı geldi. Kitabın yazarı gitti.",
                                     min_share=0.8, min_uses=1)
    # künye etiketi («Yayın Yönetmeni: …») kullanım değil
    assert not naming.is_proper_name("Yayın Yönetmeni", "Yayın Yönetmeni: Can Can\nYayın Yönetmeni: Ali Veli",
                                     min_share=0.8, min_uses=1)
    # tek sözcüklü ad için cümle başı kanıt değildir (eski kural)
    assert not naming.is_proper_name("Ben", "Ben geldim. Ben gittim.", min_share=0.8, min_uses=1)


def test_running_head_does_not_count_for_the_name_test():
    pages = [_proj(f"4 ayşe yılmaz\n\n{BODY} Ona Ayşe Yılmaz dedi.", {"top"})]
    body = source.body_text(pages)
    assert naming.usage("Ayşe Yılmaz", body) == (1, 1)


# ------------------------------------------------------------------ K9 bölüm başlığı
def _h(title, size=16.0, kind="sunk"):
    return {"title": title, "size": size, "kind": kind}


def _text_pages(n):
    return [{"page_no": p, "spans": [{"text": BODY}]} for p in range(1, n + 1)]


def test_heading_split_over_pages_by_a_conjunction_is_one_chapter():
    heads = {3: _h("ÖNSÖZ"), 5: _h("VE TEŞEKKÜR"), 7: _h("BİRİNCİ YOL")}
    found = typeset.chapters_from_pages(_text_pages(12), heads)
    assert [(c["title"], c["page_from"], c["page_to"]) for c in found][1:] == \
        [("ÖNSÖZ VE TEŞEKKÜR", 3, 6), ("BİRİNCİ YOL", 7, 12)]
    # bağlaçla başlayan uzun başlık ya da uzak sayfadaki başlık ayrı bölümdür
    heads = {3: _h("ÖNSÖZ"), 9: _h("Ve Sonra Hiç Kimse Kalmadı")}
    assert len(typeset.chapters_from_pages(_text_pages(12), heads)) == 3


def test_title_page_label_takes_the_name_but_a_named_title_keeps_no_subtitle():
    pages = _text_pages(10)
    pages[2]["spans"] = []                          # s3: başlık sayfası
    heads = {3: _h("Birinci Bölüm", kind="page"), 4: _h("AŞKIN MAHİYETİ", 14.0, "head")}
    assert typeset.chapters_from_pages(pages, heads)[1]["title"] == "Birinci Bölüm AŞKIN MAHİYETİ"
    heads = {3: _h("Birinci Bölüm AŞKIN MAHİYETİ", kind="page"), 4: _h("AŞK, İNSANIN YAŞADIĞI", 14.0, "head")}
    assert typeset.chapters_from_pages(pages, heads)[1]["title"] == "Birinci Bölüm AŞKIN MAHİYETİ"


def test_inner_cover_footnote_mark_and_accents():
    heads = {3: _h("DARWIN VE OSMANLILAR Bilim Tarihi Yazıları", kind="page"),
             5: _h("İBN SÎNÂ AHLAKIN ELİFBESİ", kind="page"), 9: _h("DARWIN DERSAADET’TE1"),
             15: _h("DARWIN Mİ YIKTI?1"), 20: _h("0.7 UCU OLAN VAR MI?")}
    pages = _text_pages(30)
    for p in (3, 5):
        pages[p - 1]["spans"] = []
    titles = [c["title"] for c in typeset.chapters_from_pages(pages, heads, "Darwin ve Osmanlılar")]
    assert titles == ["Başlıksız başlangıç", "İBN SÎNÂ AHLAKIN ELİFBESİ", "DARWIN DERSAADET’TE", "DARWIN Mİ YIKTI?",
                      "0.7 UCU OLAN VAR MI?"]
    titles = [c["title"] for c in typeset.chapters_from_pages(pages, heads, "İbn Sina")]
    assert "İBN SÎNÂ AHLAKIN ELİFBESİ" not in titles


def test_small_caption_and_unfinished_line_are_not_openings():
    L = {"body": 11.5, "step": 15.0, "top": 0.12}
    caption = {"lines": [_ln("Hatıratın yazarı Ayşe", 315, 9.5), _ln("çocukluğu (10- 11 yaşlarında)", 327, 9.5)],
               "h": 671.0}
    assert typeset._opening(caption, L) is None
    big = {"lines": [_ln("ALBÜM VE BELGELER", 300, 14.0)], "h": 671.0}
    assert typeset._opening(big, L)["title"] == "ALBÜM VE BELGELER"
    thanks = {"lines": [_ln("Bu kitabın oluşmasında;", 169, 11.5)] + [
        _ln(BODY[:80], 199 + 15 * k, 11.5) for k in range(12)], "h": 668.0}
    assert typeset._opening(thanks, L)["title"] == ""


# ------------------------------------------------------------------ K5 kapsam dışı sayfalar
def _nonfic(n=120):
    return {p: [NONFIC, NONFIC] for p in range(1, n + 1)}


def test_thanks_dedication_and_thanks_page():
    assert page_scope.is_dedication(["Nevin Şahin ve Baybora Örs’e Teşekkürlerimle."])
    assert page_scope.is_acknowledgement(["Bu kitabın oluşmasında;", "Bilgi ve birikimlerinden yararlandığım "
                                          "değerli Doğan Cüceloğlu’na...", "Her aşamada destek olan sevgili Tuba "
                                          "Kaya’ya...", "Editörüm Ayşe Tuba’ya...", "teşekkür ederim."])
    assert page_scope.is_acknowledgement(["TEŞEKKÜR", NONFIC])
    # romanda diyalog: tek «teşekkür ederim» ve tek yönelme eki yetmez
    assert not page_scope.is_acknowledgement(["— Teşekkür ederim, dedi Ali’ye.", BODY])
    # «Teşekkür Etmenin Gücü» başlıklı gövde bölümü teşekkür değil
    assert page_scope.apparatus_kind("Teşekkür Etmenin Gücü") is None


def test_epigraph_without_source_line():
    assert page_scope.is_epigraph(["“Kalp kırmak Kâbe yıkmaktan beterdir.”"])
    assert page_scope.is_epigraph(["Bildiğim tek şey, hiçbir şey bilmediğimdir.", "Sokrates"], suggested=True)
    # bölüm başlığı sayfası, yayınevi/yer satırı, adres, tek sözcüklü tırnak: epigraf değil
    for lines in (["BİRİNCİ BÖLÜM İNSAN OLMAYA DAİR"], ["TİMAŞ YAYINLARI İSTANBUL 2026"], ["timas.com.tr/cocuk"],
                  ["“Merhaba!”"], ["ÖNSÖZ", NONFIC]):
        assert not page_scope.is_epigraph(lines, suggested=True), lines


def test_front_pages_in_classify():
    pages = _nonfic()
    pages[5] = ["Annem Ayşe’ye ve babam Ali’ye Teşekkürlerimle."]
    pages[6] = ["“Kalp kırmak Kâbe yıkmaktan beterdir.”"]
    pages[7] = ["YENİ BASKIYA ÖNSÖZ", NONFIC]
    pages[8] = [NONFIC]
    pages[9] = ["TEŞEKKÜR", NONFIC]
    pages[30] = ["Bu konuda en kapsamlı çalışma Örnek Yayınları tarafından 2. baskısıyla yeniden yayımlandı ve "
                 "kaynakça bölümünde ayrıntılı biçimde tartışılan bütün belgeleri okurun önüne koydu.", NONFIC]
    found = page_scope.classify(pages, set(range(1, 121)), 120, ["Deneme"], [],
                                [{"title": "YENİ BASKIYA ÖNSÖZ", "page_from": 7, "page_to": 8},
                                 {"title": "TEŞEKKÜR", "page_from": 9, "page_to": 9},
                                 {"title": "Birinci Bölüm", "page_from": 10, "page_to": 120}])
    assert found[5][1] == "ithaf" and found[6][1] == "epigraf"
    assert found[7] == ("NON_STORY", "yayınevi notu") and found[8][1] == "yayınevi notu"
    assert found[9] == ("NON_STORY", "teşekkür")
    assert 30 not in found and 60 not in found and 10 not in found      # kurgu dışı gövde kalır


def test_back_apparatus_sections_but_not_body_chapters():
    n = 200
    pages = _nonfic(n)
    sections = [{"title": "Ekonomik Yapı", "page_from": 10, "page_to": 40},
                {"title": "Etkinlik Bağımlılığı Nedir?", "page_from": 41, "page_to": 80},
                {"title": "Sözlü Tarih", "page_from": 81, "page_to": 120},
                {"title": "EK", "page_from": 30, "page_to": 32},           # ön yarıda «Ek»: gövde
                {"title": "Bölüm Sonu Etkinliği: Denge Kutusu", "page_from": 121, "page_to": 122},
                {"title": "Yazarın Notu", "page_from": 185, "page_to": 187},
                {"title": "Sözlük", "page_from": 188, "page_to": 190},
                {"title": "EK A: Gelir-Gider Tablosu", "page_from": 191, "page_to": 200}]
    found = page_scope.classify(pages, set(range(1, n + 1)), n, ["Deneme"], [], sections)
    for p in (10, 30, 41, 81, 120, 184):
        assert p not in found, p
    assert {p: found[p][1] for p in (121, 122, 185, 188, 191, 200)} == {
        121: "etkinlik", 122: "etkinlik", 185: "yazar notu", 188: "sözlük", 191: "ek", 200: "ek"}
    # yanlış bölüm sınırı gövdeyi götürmesin: sınırdan uzun bölümün yalnız açılış sayfası
    long = [{"title": "Yazarın Notu", "page_from": 371, "page_to": 400}]
    got = page_scope.apparatus_pages({p: [NONFIC] for p in range(1, 401)}, long, 400)
    assert set(got) == set(range(371, 401))
    got = page_scope.apparatus_pages({p: [NONFIC] for p in range(1, 101)},
                                     [{"title": "Etkinlikler", "page_from": 60, "page_to": 100}], 100)
    assert set(got) == {60}


def test_apparatus_heading_without_sections_and_running_head_stripped():
    pages = {p: ["DENEME KİTABI", BODY, BODY] for p in range(1, 101)}
    pages[97] = ["DENEME KİTABI", "Yazarın Notu", BODY]       # sayfa başlığının altında bölüm başlığı
    found = page_scope.classify(pages, {97}, 100, ["Deneme"], [])
    assert found[97] == ("NON_STORY", "yazar notu")
    assert 50 not in found


def test_summary_edges_skip_suggested_preface():
    claims = [{"source_pages": [p]} for p in range(5, 205)]
    (a, b), _ = outputs.edge_pages(claims, {5, 6, 7})
    assert a == 8
    assert outputs.edge_pages(claims, set(range(1, 300))) == outputs.edge_pages(claims)  # hepsi öneriyse yok sayılır
    assert outputs.edge_skip({"scope": {"edge_excluded_pages": [5, 6]}}) == {5, 6}
