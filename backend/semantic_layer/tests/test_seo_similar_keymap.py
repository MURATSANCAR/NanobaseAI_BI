"""SEO & GEO → benzer kitaplar (seo_geo/similar.py) ve sorgu–sayfa eşlemesi (seo_geo/keymap.py): ağsız, veritabansız."""
from semantic_bridge.seo_geo import keymap, similar

SITE = "https://timas.com.tr"


def _p(pid, name, sales=0, ean=None, author=None, author_id=None, active=True, url=None, code=None):
    return {"id": pid, "code": code or f"K{pid}", "name": name, "url": url or f"{SITE}/{pid}-kitap", "sales": sales,
            "author": author, "authorId": author_id, "ean": ean, "active": active}


def _b(book_id, kind="Kitap", rights="var", flag=None):
    return {"bookId": book_id, "kind": kind, "rights": rights, "statusFlag": flag}


# ------------------------------------------------------------------ benzer kitaplar: sıralama
def test_emsal_first_both_directions_then_theme_then_author_ranked_by_sales():
    products = [
        _p("1", "Dinle", 100, "E1", "Ahmet Yazar", "10"),
        _p("2", "Mesnevi-i Şerif", 50, "E2", "Mevlana", "20"),
        _p("3", "Mevlana İle Bir Ömür", 500, "E3", "Başka Yazar", "30"),
        _p("4", "Gönül Bahçesi", 900, "E4", "Üçüncü Yazar", "40"),
        _p("5", "Ahmet'in Öteki Kitabı", 5, "E5", "Ahmet Yazar", "10"),
    ]
    books = {f"E{i}": _b(f"B{i}") for i in range(1, 6)}
    src = {"emsal": [("B1", "B2"), ("B3", "B1")], "tema": [("B1", "Tasavvuf"), ("B4", "Tasavvuf")]}
    out = similar.build(products, books, src, None)
    row = next(r for r in out["rows"] if r["id"] == "1")
    ids = [s["id"] for s in row["suggestions"]]
    assert ids == ["3", "2", "4", "5"]                      # emsal (satışa göre, iki yön) → tema → yazar
    assert [s["reason"] for s in row["suggestions"]] == ["emsal", "emsal", "tema", "yazar"]
    assert "emsal gösteriyor" in row["suggestions"][0]["reasonText"]   # B3 → B1: geri yön
    assert "emsali" in row["suggestions"][1]["reasonText"]             # B1 → B2: ileri yön
    assert row["emsalTotal"] == 2
    assert all(s["linked"] is None for s in row["suggestions"])        # bağlantı grafiği yok: bilinmiyor


def test_per_book_limit_is_applied_and_reported():
    products = [_p("0", "Kaynak", 1, "E0", "Yazar", "9")] + [_p(str(i), f"Kitap Adı {chr(65 + i)} Başka", i, f"E{i}", "Yazar", "9")
                                                          for i in range(1, 12)]
    out = similar.build(products, {}, {}, None, per_book=3)
    row = next(r for r in out["rows"] if r["id"] == "0")
    assert [s["id"] for s in row["suggestions"]] == ["11", "10", "9"]
    assert out["summary"]["perBook"] == 3


def test_theme_requires_overlapping_age_when_ages_known():
    products = [_p("1", "Kahraman Çocuk", 1, "E1"), _p("2", "Genç Kaşif", 10, "E2"), _p("3", "Büyükler İçin", 99, "E3")]
    books = {f"E{i}": _b(f"B{i}") for i in range(1, 4)}
    src = {"tema": [("B1", "Genç Kahramanlar"), ("B2", "Genç Kahramanlar"), ("B3", "Genç Kahramanlar")],
           "yas": [("B1", "9 Yaş"), ("B2", "9 Yaş"), ("B3", "18 Yaş")]}
    row = next(r for r in similar.build(products, books, src, None)["rows"] if r["id"] == "1")
    assert [s["id"] for s in row["suggestions"]] == ["2"]
    assert "9 Yaş" in row["suggestions"][0]["reasonText"]


# ------------------------------------------------------------------ benzer kitaplar: eleme
def test_editions_set_links_and_non_books_are_excluded():
    products = [
        _p("1", "Dinle", 10, "E1"),
        _p("2", "Dinle (Ciltli)", 99, "E2"),           # aynı kitabın başka baskısı
        _p("3", "Dinle Seti", 98, "E3"),               # set bağıyla bağlı
        _p("4", "Boş Koli", 97, "E4"),                 # CRM'de kitap değil
        _p("5", "Geri İstenen", 96, "E5"),             # yayın durumu uyarılı
        _p("6", "Satışta Olmayan", 95, "E6", active=False),
        _p("7", "Mesnevi", 1, "E7"),
    ]
    books = {"E1": _b("B1"), "E2": _b("B2"), "E3": _b("B3", kind="Set"), "E4": _b("B4", kind="Pazarlama Materyalleri"),
             "E5": _b("B5", flag="geri_istendi"), "E6": _b("B6"), "E7": _b("B7")}
    src = {"emsal": [("B1", x) for x in ("B2", "B3", "B4", "B5", "B6", "B7")], "set": [("B3", "B1")]}
    out = similar.build(products, books, src, None)
    row = next(r for r in out["rows"] if r["id"] == "1")
    assert [s["id"] for s in row["suggestions"]] == ["7"]
    assert {e["why"] for e in row["excluded"]} == {"baski", "set"}
    assert out["summary"]["skipped"] == {"kitap_degil": 1, "durum": 1, "satista_degil": 1}


def test_same_barcode_is_an_edition():
    products = [_p("1", "Birinci Ad", 1, "978"), _p("2", "Tamamen Başka Ad", 5, "978", "Y", "1"),
                _p("3", "Üçüncü", 3, "979", "Y", "1")]
    products[0].update(author="Y", authorId="1")
    row = next(r for r in similar.build(products, {}, {}, None)["rows"] if r["id"] == "1")
    assert [s["id"] for s in row["suggestions"]] == ["3"]


def test_series_key_from_title():
    assert similar.series_key("Kayıp Kıta 2 - Karanlık Orman") == "kayip kita"
    assert similar.series_key("Kayıp Kıta 3") == "kayip kita"
    assert similar.series_key("Aşk 2") is None           # çok kısa dizi adı tahmin edilmez
    assert similar.series_key("Dinle") is None


# ------------------------------------------------------------------ benzer kitaplar: sayfada zaten var mı
def test_already_linked_detection_with_normalised_urls():
    products = [_p("1", "Kaynak", 1, "E1", url=f"{SITE}/kaynak-kitap"),
                _p("2", "Bağlı Hedef", 50, "E2", url=f"{SITE}/bagli-hedef"),
                _p("3", "Yetim Hedef", 40, "E3", url=f"{SITE}/yetim-hedef")]
    books = {f"E{i}": _b(f"B{i}") for i in range(1, 4)}
    src = {"emsal": [("B1", "B2"), ("B1", "B3")]}
    edges = [  # www, sondaki "/" ve büyük harf farkı yok sayılır
        {"page": "https://www.timas.com.tr/Kaynak-Kitap/", "src": "https://www.timas.com.tr/kaynak-kitap",
         "dst": "https://www.timas.com.tr/bagli-hedef/", "nofollow": False},
        {"page": f"{SITE}/baska", "src": f"{SITE}/baska", "dst": f"{SITE}/kaynak-kitap", "nofollow": False},
    ]
    row = next(r for r in similar.build(products, books, src, edges)["rows"] if r["id"] == "1")
    by = {s["id"]: s for s in row["suggestions"]}
    assert by["2"]["linked"] is True and by["2"]["inlinks"] == 1 and not by["2"]["orphan"]
    assert by["3"]["linked"] is False and by["3"]["orphan"] is True
    assert row["toAdd"] == 1 and row["alreadyLinked"] == 1 and row["orphanTargets"] == 1
    assert row["crawled"] is True


def test_source_not_crawled_is_unknown_and_views_prioritise_orphans():
    products = [_p("1", "Az Satan", 1, "E1"), _p("2", "Çok Satan", 100, "E2"), _p("3", "Yetim", 5, "E3")]
    books = {f"E{i}": _b(f"B{i}") for i in range(1, 4)}
    src = {"emsal": [("B1", "B3"), ("B2", "B1")]}
    edges = [{"page": f"{SITE}/1-kitap", "src": f"{SITE}/1-kitap", "dst": f"{SITE}/2-kitap", "nofollow": False}]
    # 1. kitap yeterince bağlantı alıyor (zayıf değil); 3. kitap yetim
    edges += [{"page": f"{SITE}/p{i}", "src": f"{SITE}/p{i}", "dst": f"{SITE}/1-kitap", "nofollow": False}
              for i in range(similar.WEAK_INLINKS)]
    rows = similar.build(products, books, src, edges)["rows"]
    two = next(r for r in rows if r["id"] == "2")
    assert two["crawled"] is False and all(s["linked"] is None for s in two["suggestions"])
    order = [r["id"] for r in similar.view_rows(rows, "eklenecek", set())]
    assert order[0] == "1"                      # yetim hedefe bağlantı eklenecek kitap önde
    assert "1" not in [r["id"] for r in similar.view_rows(rows, "eklenecek", {"1"})]
    assert [r["id"] for r in similar.view_rows(rows, "yetimler", set())][0] == "1"


def test_csv_rows_one_line_per_pair():
    rows = similar.csv_rows([{"source": {"id": "1", "code": "K1", "name": "Dinle", "url": f"{SITE}/dinle"},
                              "targets": [{"id": "2", "code": "K2", "name": "Mesnevi", "url": f"{SITE}/mesnevi",
                                           "reason": "emsal", "reasonText": "CRM'de bu kitabın emsali", "linked": False},
                                          {"id": "3", "code": "K3", "name": "Ömür", "url": f"{SITE}/omur", "reason": "yazar",
                                           "linked": True}],
                              "decidedBy": "a", "decidedAt": "2026-09-28"}])
    assert [r[3] for r in rows] == ["K2", "K3"]
    assert rows[0][7] == "eklenmeli" and rows[1][7] == "zaten bağlı" and rows[1][6] == "Aynı yazar"


def test_read_crm_keeps_emsal_when_theme_table_fails():
    def execute(sql, limit):
        if "temaBase" in sql:
            raise RuntimeError("yok")
        if "emsalkitap3Base" in sql:
            return ["a", "b"], [{"a": "{aa-1}", "b": "bb-2"}, {"a": "x", "b": "x"}], False
        return ["a", "b"], [], False
    data, errors = similar.read_crm("CRM.dbo", execute)
    assert data["emsal"] == [("AA-1", "BB-2")]
    assert "tema" in errors and "tema" not in data


# ------------------------------------------------------------------ sorgu–sayfa: arama türü
def _index():
    products = [
        {"id": "1", "name": "Kürk Mantolu Madonna", "url": f"{SITE}/kurk-mantolu-madonna", "author": "Sabahattin Ali",
         "authorId": "7", "sales": 100, "active": True},
        {"id": "2", "name": "Dinle", "url": f"{SITE}/dinle", "author": "Hasan Ali Toptaş", "authorId": "8", "sales": 10,
         "active": True},
        {"id": "3", "name": "Eski Kitap", "url": f"{SITE}/eski-kitap", "author": "Kayıp Yazar", "authorId": "9", "sales": 1,
         "active": False},
    ]
    link_pages = [{"type": "model", "id": "7", "name": "Sabahattin Ali", "url": f"{SITE}/sabahattin-ali"},
                  {"type": "category", "id": "30", "name": "Roman", "url": f"{SITE}/roman"},
                  {"type": "blog", "id": "40", "name": "Okuma Listesi", "url": f"{SITE}/blog/okuma-listesi"}]
    return keymap.build_index(products, link_pages)


def test_intent_classification():
    ix = _index()
    assert keymap.classify_intent("kürk mantolu madonna", ix)["intent"] == "kitap"
    assert keymap.classify_intent("Kürk Mantolu Madonna Sabahattin Ali PDF", ix)["intent"] == "kitap"
    assert keymap.classify_intent("sabahattin ali kitapları", ix)["intent"] == "yazar"
    assert keymap.classify_intent("dinle hasan ali toptaş", ix)["intent"] == "kitap"
    assert keymap.classify_intent("müzik dinle", ix)["intent"] != "kitap"     # tek kelimelik ad başka sözle geçerse kitap değil
    assert keymap.classify_intent("en iyi roman önerileri", ix)["intent"] == "bilgi"
    assert keymap.classify_intent("roman", ix)["intent"] == "kategori"
    assert keymap.classify_intent("Timaş Yayınları", ix)["intent"] == "marka"
    assert keymap.classify_intent("uzay gemisi", ix)["intent"] == "diger"


def _rows(query, *pages):
    return [{"keys": [query, url], "clicks": c, "impressions": i, "position": 3.0} for url, c, i in pages]


def test_wrong_page_ranking_for_author_and_book_queries():
    ix = _index()
    items = keymap.analyse(_rows("sabahattin ali kitapları", (f"{SITE}/kurk-mantolu-madonna", 20, 200),
                                 (f"{SITE}/sabahattin-ali", 5, 100)), ix)
    assert items[0]["kind"] == "yanlis"
    assert items[0]["target"]["url"] == f"{SITE}/sabahattin-ali" and items[0]["ranking"]["type"] == "product"
    items = keymap.analyse(_rows("kürk mantolu madonna", (f"{SITE}/roman", 9, 120)), ix)
    assert items[0]["kind"] == "yanlis" and items[0]["target"]["id"] == "1"
    items = keymap.analyse(_rows("kürk mantolu madonna", (f"{SITE}/Kurk-Mantolu-Madonna/?utm_source=x", 9, 120)), ix)
    assert items[0]["kind"] == "eslesme"


def test_gap_detection():
    ix = _index()
    # yazarın ürünü var ama yazar sayfası yok
    items = keymap.analyse(_rows("hasan ali toptaş", (f"{SITE}/dinle", 3, 80)), ix)
    assert items[0]["kind"] == "bosluk" and items[0]["target"] is None and "sayfası yok" in items[0]["reason"]
    # soru/liste araması, uyan kategori yok ve ürün sayfası sıralanıyor → rehber önerisi
    items = keymap.analyse(_rows("okunması gereken kitaplar", (f"{SITE}/dinle", 3, 80)), ix)
    assert items[0]["kind"] == "bosluk" and "rehber" in items[0]["reason"].lower()
    # liste araması blog sayfasına düşüyorsa doğru
    items = keymap.analyse(_rows("okunması gereken kitaplar", (f"{SITE}/blog/okuma-listesi", 3, 80)), ix)
    assert items[0]["kind"] == "eslesme"
    # kitap satışta değil, satıştaki baskısı yok
    items = keymap.analyse(_rows("eski kitap kayıp yazar", (f"{SITE}/eski-kitap", 1, 50)), ix)
    assert items[0]["kind"] == "bosluk"


def test_low_impression_queries_are_not_mapped_and_ranking_page_is_most_clicked():
    ix = _index()
    rows = _rows("roman", (f"{SITE}/roman", 1, 10), (f"{SITE}/dinle", 0, 10))
    assert keymap.analyse(rows, ix, min_impr=30) == []
    rows = _rows("roman", (f"{SITE}/dinle", 1, 400), (f"{SITE}/roman", 7, 20))
    it = keymap.analyse(rows, ix)[0]
    assert it["ranking"]["url"] == f"{SITE}/roman" and it["kind"] == "eslesme" and len(it["pages"]) == 2


def test_keymap_csv_skips_matched_without_decision():
    ix = _index()
    items = keymap.analyse(_rows("roman", (f"{SITE}/roman", 7, 40)) + _rows("hasan ali toptaş", (f"{SITE}/dinle", 3, 80)), ix)
    rows = keymap.csv_rows(items, {})
    assert [r[0] for r in rows] == ["hasan ali toptaş"]
    dec = {keymap.query_id("Roman"): {"status": "onaylandi", "target": f"{SITE}/roman", "decidedBy": "a",
                                       "decidedAt": "2026-09-28", "note": ""}}
    assert len(keymap.csv_rows(items, dec)) == 2
