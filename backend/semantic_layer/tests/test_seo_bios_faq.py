"""SEO & GEO → yazar biyografileri (seo_geo/bios.py) ve kitap soru–cevapları (seo_geo/faq.py): ad eşleşmesi,
CRM kaynak süzgeci (yalnız Yazar, kişisel alan yok), gerçeklik denetimi, JSON-LD, sınav sorusu dışlama, sıra.
Model çağrılmaz; sahte istemciyle ayrıştırma ve düzeltme turu sınanır."""
import json

from semantic_bridge.seo_geo import bios, faq

LIM = {"title_min": 30, "title_max": 65, "meta_min": 120, "meta_max": 160, "desc_min_words": 150}
YAZAR, CIZER, UZMAN = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222", "33333333-3333-3333-3333-333333333333"


class FakeLlm:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages, **kw):
        self.calls.append(messages)
        return self.replies.pop(0)


# ------------------------------------------------------------------ ad eşleşmesi
def test_name_key_folds_turkish_case_and_drops_titles():
    assert bios.name_key("İlber Ortaylı") == bios.name_key("ILBER ORTAYLI") == bios.name_key("Prof. Dr. İlber Ortaylı") == "ilber ortayli"
    assert bios.name_key("ŞULE GÜRBÜZ") == bios.name_key("Şule  Gürbüz") == "sule gurbuz"
    assert bios.name_key("Doç. Dr. Cemil Meriç") == "cemil meric"
    assert bios.name_key("Dr") == "dr"   # yalnız unvan olan ad boşalmaz


def test_model_keys_split_multiple_authors():
    assert bios.model_keys("Cemil Meriç, Prof. Dr. İlber Ortaylı") == {"cemil meric", "ilber ortayli"}


def _prod(pid, ean, name, sales, model, model_id="0"):
    return {"id": pid, "ean": ean, "name": name, "url": f"https://timas.com.tr/{pid}", "isbn": ean, "sales": sales,
            "model": model, "modelId": model_id}


def _src(key, name, books, bio="x" * 300):
    return {"key": key, "name": name, "bioLong": bio, "bioShort": None, "biography": None, "books": [{"ean": e, "primary": True} for e in books]}


def test_build_authors_matches_tsoft_model_and_reports_unmatched():
    products = [_prod("1", "9786050000001", "Kitap A", 50, "İLBER ORTAYLI", "77"),
                _prod("2", "9786050000002", "Kitap B", 500, "İlber Ortaylı"),
                _prod("3", "9786050000003", "Kitap C", 10, "Timaş Editör Kurulu")]
    links = [{"link": "ilber-ortayli", "table_id": "77", "title": "İlber Ortaylı Kitapları | Timaş"}]
    srcs = [_src("a", "Prof. Dr. İlber Ortaylı", ["9786050000001", "9786050000002"]),
            _src("b", "Ayşe Yılmaz", ["9786050000003"]),
            _src("c", "Satışta Kitabı Yok", ["9786059999999"])]
    same = {"ilber ortayli": {"wikidata": "https://www.wikidata.org/wiki/Q1", "wikipedia": None}}
    rows = bios.build_authors(srcs, products, links, same, "https://timas.com.tr")
    assert [r["key"] for r in rows] == ["a", "b"]          # satıştan aza; satışta kitabı olmayan yok
    a = rows[0]
    assert a["matched"] and a["sales"] == 550 and a["page"]["url"] == "https://timas.com.tr/ilber-ortayli"
    assert [b["name"] for b in a["books"]] == ["Kitap B", "Kitap A"]
    assert a["sameAs"] == ["https://www.wikidata.org/wiki/Q1"]
    assert not rows[1]["matched"] and rows[1]["page"] is None
    assert bios.match_report(rows) == {"matched": 1, "unmatched": 1}


# ------------------------------------------------------------------ CRM kaynak süzgeci
def test_only_author_type_participations_are_taken():
    types = [{"id": YAZAR.lower(), "name": "Yazar"}, {"id": CIZER, "name": "Çizer"}, {"id": UZMAN, "name": "Uzman Editör"}]
    ids = bios.author_type_ids(types)
    assert ids == {YAZAR}
    rows = [{"contact_id": "C1", "type_id": YAZAR, "ean": "978-605-000-0001", "is_primary": 1},
            {"contact_id": "C2", "type_id": CIZER, "ean": "9786050000001", "is_primary": 0},
            {"contact_id": "C3", "type_id": UZMAN, "ean": "9786050000001", "is_primary": 0},
            {"contact_id": "C1", "type_id": YAZAR, "ean": "9786050000009", "is_primary": 0},
            {"contact_id": "C4", "type_id": YAZAR, "ean": None, "is_primary": 0}]
    books = bios.author_books(rows, ids)
    assert set(books) == {"C1"}
    assert {b["ean"]: b["primary"] for b in books["C1"]} == {"9786050000001": True, "9786050000009": False}


def test_source_record_keeps_no_personal_contact_data():
    row = {"contact_id": "{ABC-1}", "name": "Ayşe <b>Yılmaz</b>", "bio_long": "<p>İstanbul'da doğdu.</p><p>1990'da mezun oldu.</p>",
           "bio_short": None, "biography": None, "telephone1": "0555", "emailaddress1": "a@b.c", "address1_line1": "Sokak 1"}
    rec = bios.source_record(row, [{"ean": "9786050000001", "primary": True}])
    assert set(rec) == {"contactId", "name", "bioLong", "bioShort", "biography", "books"}
    dump = json.dumps(rec, ensure_ascii=False)
    assert "0555" not in dump and "a@b.c" not in dump and "Sokak" not in dump
    assert rec["name"] == "Ayşe Yılmaz" and rec["contactId"] == "abc-1"
    assert rec["bioLong"] == "İstanbul'da doğdu.\n\n1990'da mezun oldu."


def test_contact_sql_selects_only_name_and_bio_and_reads_type_from_table():
    sql = bios.contact_sql("crm.dbo.", {YAZAR})
    for bad in ("telephone", "email", "address", "mobile"):
        assert bad not in sql.lower()
    assert YAZAR in sql and "new_ozgecmis" in sql
    assert "katilimcitipi" in bios.type_sql("crm.dbo.").lower()


def test_same_name_contacts_merge_into_one_author():
    recs = [{"contactId": "b", "name": "Ali Veli", "bioLong": "kısa", "bioShort": None, "biography": None, "books": [{"ean": "1", "primary": True}]},
            {"contactId": "a", "name": "ALİ VELİ", "bioLong": "daha uzun özgeçmiş", "bioShort": None, "biography": None, "books": [{"ean": "2", "primary": False}]}]
    out = bios.merge_same_name(recs)
    assert len(out) == 1 and out[0]["contactId"] == "a" and out[0]["bioLong"] == "daha uzun özgeçmiş"
    assert {b["ean"] for b in out[0]["books"]} == {"1", "2"}


def test_read_uses_author_label_and_active_books_only():
    calls = []

    def execute(sql, limit):
        calls.append(sql)
        if "new_katilimcitipiBase t" in sql and "ContactBase" not in sql:
            return None, [{"id": YAZAR, "name": "Yazar"}, {"id": CIZER, "name": "Çizer"}], False
        if "new_eserkatilimBase e JOIN" in sql:
            return None, [{"contact_id": "C1", "type_id": YAZAR, "ean": "9786050000001", "is_primary": 1},
                          {"contact_id": "C2", "type_id": YAZAR, "ean": "9786050000002", "is_primary": 1}], False
        return None, [{"contact_id": "C1", "name": "Ayşe Yılmaz", "bio_long": "Özgeçmiş", "bio_short": None, "biography": None},
                      {"contact_id": "C2", "name": "Mehmet Kaya", "bio_long": "Özgeçmiş", "bio_short": None, "biography": None}], False

    out = bios.read("crm.dbo", execute, {"9786050000001"})
    assert [r["name"] for r in out] == ["Ayşe Yılmaz"]
    assert CIZER not in calls[-1]


# ------------------------------------------------------------------ biyografi taslağı
BIO_SRC = {"name": "Ayşe Yılmaz", "text": "Ayşe Yılmaz 1975'te İstanbul'da doğdu. Boğaziçi Üniversitesi'nde tarih okudu."}
BOOKS = [{"id": "1", "name": "Sessiz Şehir", "url": "https://timas.com.tr/sessiz-sehir", "isbn": "9786050000001", "sales": 10}]


def _bio(n):
    return " ".join(["Ayşe Yılmaz tarih okudu ve yazdı."] * (n // 6 + 1))


def test_bio_suggest_repairs_once_and_cuts_summary():
    short = json.dumps({"Bio": "Çok kısa.", "Summary": "Kısa."})
    good = json.dumps({"Bio": _bio(150), "Summary": "Ayşe Yılmaz, İstanbul'da doğmuş, Boğaziçi Üniversitesi'nde tarih okumuş ve Sessiz Şehir adlı kitabı Timaş'tan çıkmış bir yazardır; eserleri tarih üzerinedir."})
    llm = FakeLlm(short, good)
    fields = bios.suggest(llm, BIO_SRC, BOOKS, LIM)
    assert len(llm.calls) == 2 and "Düzelt" in llm.calls[1][-1]["content"]
    assert 120 <= bios.words(fields["Bio"]) <= 220
    assert len(fields["Summary"]) <= LIM["meta_max"]


def test_bio_reality_flags_invented_numbers_and_names():
    fields = {"Bio": "Ayşe Yılmaz 1975'te İstanbul'da doğdu. Yazar 2003 yılında Sait Faik Ödülü aldı.",
              "Summary": "Ayşe Yılmaz, Sessiz Şehir kitabının yazarıdır."}
    miss = bios.reality(BIO_SRC, BOOKS, fields)
    assert "2003" in miss and "Sait" in miss
    assert "1975" not in miss and "Sessiz" not in miss and "İstanbul" not in miss


def test_bio_prompt_carries_book_titles_and_limits():
    p = bios.build_prompt(BIO_SRC, BOOKS, LIM)
    assert "Sessiz Şehir" in p and "120–220" in p and "120–160" in p and "Boğaziçi" in p


def test_person_jsonld_is_built_by_code():
    ld = bios.person_jsonld("Ayşe Yılmaz", "Özet.", "https://timas.com.tr/ayse-yilmaz",
                            ["https://www.wikidata.org/wiki/Q1", "https://www.wikidata.org/wiki/Q1"])
    assert ld == {"@context": "https://schema.org", "@type": "Person", "name": "Ayşe Yılmaz", "description": "Özet.",
                  "url": "https://timas.com.tr/ayse-yilmaz", "mainEntityOfPage": "https://timas.com.tr/ayse-yilmaz",
                  "sameAs": ["https://www.wikidata.org/wiki/Q1"]}
    assert "url" not in bios.person_jsonld("X", None, None, []) and "sameAs" not in bios.person_jsonld("X", None, None, [])


def test_bio_export_html_lists_books_and_escapes_script():
    ld = bios.person_jsonld("A </script>", "Özet", None, [])
    out = bios.export_html("A", {"Bio": "Bir.\n\nİki.", "Summary": "Özet"}, BOOKS, ld, "hazir")
    assert "DİKKAT" in out and "<p>Bir.</p>" in out and "<p>İki.</p>" in out
    assert 'href="https://timas.com.tr/sessiz-sehir"' in out and "</script>\"" not in out


def test_bio_queue_orders_by_sales_and_skips_no_bio_and_drafted():
    rows = [{"key": "a", "name": "A", "sales": 5, "hasBio": True}, {"key": "b", "name": "B", "sales": 90, "hasBio": False},
            {"key": "c", "name": "C", "sales": 50, "hasBio": True}, {"key": "d", "name": "D", "sales": 70, "hasBio": True}]
    assert [a["key"] for a in bios.queue(rows, {"d"})] == ["c", "a"]


def test_short_bio_is_a_crm_task_not_a_draft():
    rows = bios.build_authors([_src("a", "A B", ["9786050000001"], bio="Kısa.")],
                              [_prod("1", "9786050000001", "K", 5, "A B")], [], {}, "https://timas.com.tr")
    assert not rows[0]["hasBio"] and rows[0]["task"] == bios.NO_BIO_TASK


# ------------------------------------------------------------------ kitap soru–cevapları
P = {"ProductId": "42", "ProductName": "Sessiz Şehir", "Model": "Ayşe Yılmaz", "Brand": "Timaş Çocuk", "Barcode": "9786050000001",
     "SeoLink": "sessiz-sehir", "CountTotalSales": "120", "ShortDescription": "Bir şehir masalı."}
C = {"authors": "Ayşe Yılmaz", "translators": None, "pages": 128, "ageFrom": 9, "ageTo": 12, "audience": "Çocuk",
     "genres": "Roman", "originalTitle": None, "spot": "Sessiz bir şehirde geçen bir dostluk hikâyesi.", "summary": None,
     "promo": None, "highlights": None, "statusFlag": None, "rights": "var",
     "kitapsorusu": "Kahramanın köpeğinin adı nedir? a) Pamuk b) Karam", "new_kitapsorusu": "Soru: 3. bölümde ne oldu?"}


def test_faq_record_never_carries_crm_quiz_questions():
    b = faq.book_record(P, C, "https://timas.com.tr", None)
    dump = json.dumps(b, ensure_ascii=False) + faq.build_prompt(b)
    assert "Pamuk" not in dump and "bölümde" not in dump and "kitapsorusu" not in dump
    assert b["url"] == "https://timas.com.tr/sessiz-sehir" and b["ages"] == "9–12 yaş" and b["pages"] == 128


def test_quiz_style_questions_are_detected():
    for q in ("Aşağıdakilerden hangisi kahramanın arkadaşıdır?", "Kahraman kaçıncı bölümde şehre döner?",
              "Köpeğin adı nedir? a) Pamuk b) Karam c) Boncuk", "Boşluğu doldurunuz: Şehir ___ idi.",
              "Doğru mu yanlış mı: kahraman şehirden ayrılır."):
        assert faq.is_quiz(q), q
    for q in ("Kitap kaç yaş için uygun?", "Sessiz Şehir ne anlatıyor?", "Kitabın yazarı kim?", "Kaç sayfa?",
              "Çeviri mi, özgün adı ne?"):
        assert not faq.is_quiz(q), q


def test_faq_suggest_drops_quiz_and_repairs_count():
    first = json.dumps({"Faq": [{"q": "Aşağıdakilerden hangisi doğrudur?", "a": "A"}, {"q": "Yazarı kim?", "a": "Ayşe Yılmaz."}]})
    second = json.dumps({"Faq": [{"q": "Yazarı kim?", "a": "Ayşe Yılmaz."}, {"q": "Kaç sayfa?", "a": "128 sayfa."},
                                 {"q": "Kaç yaş için uygun?", "a": "9–12 yaş."}]})
    b = faq.book_record(P, C, "https://timas.com.tr", None)
    llm = FakeLlm(first, second)
    out = faq.suggest(llm, b)
    assert [f["q"] for f in out] == ["Yazarı kim?", "Kaç sayfa?", "Kaç yaş için uygun?"]
    assert "Düzelt" in llm.calls[1][-1]["content"]


def test_faq_reality_is_per_question():
    b = faq.book_record(P, C, "https://timas.com.tr", None)
    miss = faq.reality(b, [{"q": "Kaç sayfa?", "a": "Kitap 128 sayfadır."},
                           {"q": "Ödül aldı mı?", "a": "Kitap 2019 yılında Tübitak Ödülü aldı."}])
    assert miss[0] == []
    assert "2019" in miss[1] and "Tübitak" in miss[1]


def test_faqpage_jsonld_built_by_code():
    ld = faq.faq_jsonld([{"q": "Yazarı kim?", "a": "Ayşe Yılmaz."}, {"q": "", "a": "boş"}], "https://timas.com.tr/x")
    assert ld["@type"] == "FAQPage" and ld["url"] == "https://timas.com.tr/x"
    assert ld["mainEntity"] == [{"@type": "Question", "name": "Yazarı kim?", "acceptedAnswer": {"@type": "Answer", "text": "Ayşe Yılmaz."}}]


def test_faq_state_and_priority_skip_flagged_non_books_and_sourceless():
    site = "https://timas.com.tr"
    ok = faq.book_record({**P, "ProductId": "1", "CountTotalSales": "10"}, C, site, None)
    top = faq.book_record({**P, "ProductId": "2", "CountTotalSales": "900"}, C, site, None)
    flagged = faq.book_record({**P, "ProductId": "3", "CountTotalSales": "5000"}, {**C, "statusFlag": "cekildi"}, site, None)
    promo = faq.book_record({**P, "ProductId": "4", "CountTotalSales": "4000"}, {**C, "rights": "kitap_degil"}, site, None)
    no_crm = faq.book_record({**P, "ProductId": "5", "CountTotalSales": "3000"}, None, site, None)
    empty = faq.book_record({**P, "ProductId": "6", "CountTotalSales": "2000", "ShortDescription": ""}, {**C, "spot": None}, site, None)
    assert faq.state(flagged)[0] == "atlandi" and faq.state(promo)[0] == "atlandi"
    assert faq.state(no_crm)[0] == "kaynak_yok" and faq.state(empty)[0] == "kaynak_yok"
    assert [b["id"] for b in faq.queue([ok, top, flagged, promo, no_crm, empty], set())] == ["2", "1"]
    assert [b["id"] for b in faq.queue([ok, top], {"2"})] == ["1"]
