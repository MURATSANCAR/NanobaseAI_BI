"""SEO & GEO → rehber içerikler (semantic_bridge/seo_geo/guides.py): niyet, kümeleme, kitap seçimi, JSON-LD,
gerçeklik denetimi. Model çağrılmaz; sahte istemciyle ayrıştırma sınanır."""
import json

from semantic_bridge.seo_geo import guides

LIM = {"title_min": 30, "title_max": 65, "meta_min": 120, "meta_max": 160, "desc_min_words": 150}


def row(q, imp, pos=8.0, clicks=0):
    return {"keys": [q], "impressions": imp, "clicks": clicks, "position": pos}


# ------------------------------------------------------------------ niyet
def test_list_intent_is_detected_with_or_without_turkish_letters():
    for q in ("9-11 yaş için değerler eğitimi kitapları", "yeni baslayanlar icin tasavvuf kitaplari",
              "en iyi tarihi romanlar", "hangi kitabı okumalıyım", "okunması gereken klasikler",
              "3. sınıf okuma kitapları", "gençler için roman önerileri", "10 yaş kitap önerisi"):
        assert guides.is_list_intent(q), q


def test_single_book_and_navigational_queries_are_not_guides():
    for q in ("kürk mantolu madonna", "timaş yayınları kitapları", "www.timas.com.tr", "fi kitabı özeti"):
        assert not guides.is_list_intent(q), q


def test_ages_from_numbers_classes_and_school_levels():
    assert guides.ages("9-11 yaş değerler eğitimi") == (9, 11)
    assert guides.ages("10 yaşındaki çocuklar için") == (10, 10)
    assert guides.ages("3. sınıf okuma kitapları") == (8, 9)
    assert guides.ages("ortaokul kitap önerileri") == (10, 14)
    assert guides.ages("tasavvuf kitapları") is None


# ------------------------------------------------------------------ kümeleme
def test_near_duplicates_cluster_and_rank_by_impressions():
    ts = guides.topics([
        row("değerler eğitimi kitapları", 300, 12.0),
        row("degerler egitimi kitap onerileri", 120, 7.5),
        row("tasavvuf kitapları", 500, 4.0),
        row("kürk mantolu madonna", 9000),                       # niyet yok
    ], [])
    assert [t["title"] for t in ts] == ["Tasavvuf kitapları", "Değerler eğitimi kitapları"]
    values = ts[1]
    assert values["impressions"] == 420 and len(values["queries"]) == 2 and values["position"] == 7.5
    assert len({t["key"] for t in ts}) == 2


def test_different_ages_or_genres_stay_apart():
    ts = guides.topics([row("9 yaş kitap önerileri", 50), row("12 yaş kitap önerileri", 40),
                        row("roman önerileri", 30), row("tarihi roman önerileri", 20)], [])
    assert len(ts) == 4


def test_author_name_queries_are_left_to_author_pages():
    exclude = [{guides.stem("Sabahattin"), guides.stem("Ali")}]
    ts = guides.topics([row("sabahattin ali kitapları", 900), row("çocuk kitapları", 50)], [], exclude)
    assert [t["title"] for t in ts] == ["Çocuk kitapları"]


def test_geo_questions_become_topics_and_merge_with_search():
    ts = guides.topics([row("tasavvuf kitapları", 80)], ["Yeni başlayanlar için tasavvuf kitapları hangileri?"])
    assert len(ts) == 1 and ts[0]["sources"] == ["arama", "soru"]


def test_topic_key_is_stable():
    a = guides.topics([row("değerler eğitimi kitapları", 10)], [])[0]["key"]
    b = guides.topics([row("Değerler Eğitimi Kitapları", 99)], [])[0]["key"]
    assert a == b


# ------------------------------------------------------------------ kitap seçimi
def book(id_, **kw):
    base = {"id": id_, "name": f"Kitap {id_}", "author": "Yazar", "brand": "Timaş Çocuk", "sales": 0}
    return {**base, **kw}


def test_book_scoring_uses_genre_and_age_and_explains_why():
    topic = guides.topics([row("9-11 yaş değerler eğitimi kitapları", 10)], [])[0]
    good = book("1", genres="Değerler Eğitimi, Hikâye", ageFrom=9, ageTo=12)
    wrong_age = book("2", genres="Değerler Eğitimi", ageFrom=3, ageTo=6)
    no_match = book("3", genres="Polisiye", ageFrom=9, ageTo=11)
    s, why = guides.score_book(topic, good)
    assert s > 0 and any(w.startswith("Tür: Değerler Eğitimi") for w in why) and "Yaş: 9–12" in why
    assert guides.score_book(topic, wrong_age)[0] == 0
    assert guides.score_book(topic, no_match)[0] == 0


def test_candidates_skip_crm_flagged_and_prefer_sales_on_tie():
    topic = guides.topics([row("tasavvuf kitapları", 10)], [])[0]
    cat = [book("1", genres="Tasavvuf", sales=10), book("2", genres="Tasavvuf", sales=500),
           book("3", genres="Tasavvuf", sales=9999, statusFlag="cekildi"), book("4", genres="Roman")]
    ids = [b["id"] for b in guides.candidates(topic, cat)]
    assert ids == ["2", "1"]


def test_age_only_topic_needs_book_age():
    topic = guides.topics([row("lise kitap önerileri", 10)], [])[0]
    assert topic["ages"] == [14, 18]
    assert guides.score_book(topic, book("1", ageFrom=15, ageTo=18))[0] > 0
    assert guides.score_book(topic, book("2"))[0] == 0


# ------------------------------------------------------------------ JSON-LD
def test_jsonld_is_built_by_code_from_selected_books():
    fields = {"SeoTitle": "Tasavvuf kitapları", "SeoDescription": "Açıklama", "Faq": [{"q": "Nereden başlamalı?", "a": "İlk kitaptan."}]}
    books = [book("1", url="https://www.timas.com.tr/a"), book("2", isbn="9786050000000")]
    ld = guides.jsonld(fields, books)
    lst, faq = ld
    assert lst["@type"] == "ItemList" and lst["numberOfItems"] == 2
    assert lst["itemListElement"][0] == {"@type": "ListItem", "position": 1, "url": "https://www.timas.com.tr/a", "name": "Kitap 1"}
    assert lst["itemListElement"][1]["item"]["@type"] == "Book" and lst["itemListElement"][1]["item"]["isbn"] == "9786050000000"
    assert faq["@type"] == "FAQPage" and faq["mainEntity"][0]["acceptedAnswer"]["text"] == "İlk kitaptan."


def test_jsonld_without_faq_has_only_item_list():
    assert [x["@type"] for x in guides.jsonld({"SeoTitle": "T"}, [book("1")])] == ["ItemList"]


def test_export_html_escapes_and_embeds_jsonld():
    fields = {"SeoTitle": "A <b> & B", "SeoDescription": "d", "Intro": "giriş", "Books": {"1": "metin </script>"}, "Faq": []}
    books = [book("1", url="https://x/a")]
    out = guides.export_html(fields, books, guides.jsonld(fields, books), "hazir")
    assert "A &lt;b&gt; &amp; B" in out and "application/ld+json" in out and "henüz onaylanmadı" in out
    assert "metin &lt;/script&gt;" in out


# ------------------------------------------------------------------ gerçeklik denetimi
def test_reality_check_flags_numbers_and_names_missing_from_the_book_record():
    topic = guides.topics([row("tasavvuf kitapları", 10)], [])[0]
    books = [book("1", name="Kalbin Yolu", author="Ayşe Yılmaz", genres="Tasavvuf", pages=240)]
    fields = {"SeoTitle": "Tasavvuf kitapları", "SeoDescription": "Kalbin Yolu ile tasavvufa giriş.",
              "Intro": "Bu listede Ayşe Yılmaz imzalı bir kitap var.",
              "Books": {"1": "Kalbin Yolu, 240 sayfa. Kitap 1998 yılında Nobel ödülü aldı."},
              "Faq": [{"q": "Kaç sayfa?", "a": "Kitap 240 sayfadır."}]}
    r = guides.reality(topic, books, fields)
    assert r["general"] == []
    assert "1998" in r["books"]["1"] and "Nobel" in r["books"]["1"] and "240" not in r["books"]["1"]


def test_reality_check_is_per_book():
    """Bir kitabın bilgisi başka kitabın paragrafına taşınırsa işaretlenir."""
    topic = guides.topics([row("tasavvuf kitapları", 10)], [])[0]
    books = [book("1", name="Kalbin Yolu", author="Ayşe Yılmaz"), book("2", name="Sessiz Ev", author="Mehmet Kaya")]
    fields = {"SeoTitle": "t", "SeoDescription": "", "Intro": "", "Faq": [],
              "Books": {"1": "Kalbin Yolu okuru sade bir dille karşılar.", "2": "Sessiz Ev, Kalbin Yolu gibi Yılmaz imzası taşır."}}
    r = guides.reality(topic, books, fields)
    assert "1" not in r["books"] and "Yılmaz" in r["books"]["2"]


# ------------------------------------------------------------------ model cevabı
class FakeLlm:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def chat(self, messages, max_tokens=0, temperature=0):
        self.calls += 1
        return self.replies.pop(0)


def test_suggest_parses_keeps_known_books_and_enforces_limits():
    reply = json.dumps({"SeoTitle": "Yeni Başlayanlar İçin Tasavvuf Kitapları: Seçkin Bir Liste | Timaş Yayınları Seçkisi",
                        "SeoDescription": "x" * 200, "Intro": "giriş",
                        "Books": [{"id": "1", "text": "p1"}, {"id": "99", "text": "uydurma"}],
                        "Faq": [{"q": "a?", "a": "b"}, {"q": "c?", "a": "d"}, {"q": "e?", "a": "f"}]}, ensure_ascii=False)
    llm = FakeLlm(["<think>…</think>" + reply, reply])
    topic = guides.topics([row("tasavvuf kitapları", 10)], [])[0]
    f = guides.suggest(llm, topic, [book("1")], LIM)
    assert f["Books"] == {"1": "p1"} and len(f["SeoTitle"]) <= 65 and len(f["SeoDescription"]) <= 160
    assert llm.calls == 2   # sınır dışı → bir düzeltme turu


def test_clean_fields_keeps_only_known_keys_as_plain_text():
    out = guides.clean_fields({"SeoTitle": "<b>T</b>", "Evil": "x", "Books": {"1": "<p>m</p>"}, "Faq": [{"q": "s?", "a": ""}, {}]})
    assert out == {"SeoTitle": "T", "Books": {"1": "m"}, "Faq": [{"q": "s?", "a": ""}]}
