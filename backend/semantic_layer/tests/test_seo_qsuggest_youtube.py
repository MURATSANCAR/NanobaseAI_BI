"""SEO & GEO → izlenen soru önerileri (qsuggest.py) ve YouTube video denetimi (youtube.py). Saf işlevler, düz veri."""
from datetime import date

from semantic_bridge.seo_geo import qsuggest as q
from semantic_bridge.seo_geo import youtube as y


# ------------------------------------------------------------------ sorgu kalıbı ve soruya çevirme

def test_question_form_queries_are_kept_and_capitalised():
    assert q.detect("hangi kitabı okumalıyım") == "soru"
    assert q.rewrite("hangi kitabı okumalıyım") == "Hangi kitabı okumalıyım?"
    assert q.rewrite("iyi bir roman nasıl seçilir") == "İyi bir roman nasıl seçilir?"
    assert q.rewrite("tatilde ne okumalı") == "Tatilde ne okumalı?"


def test_list_intent_queries_become_questions():
    assert q.rewrite("fantastik roman önerileri") == "Fantastik roman önerir misin?"
    assert q.rewrite("en iyi polisiye romanlar") == "En iyi polisiye romanlar hangileri?"
    assert q.rewrite("psikoloji kitapları") == "En iyi psikoloji kitapları hangileri?"
    assert q.rewrite("yaz tatili için kitap") == "Yaz tatili için hangi kitabı önerirsin?"
    assert q.rewrite("mutlaka okunmalı kitaplar") == "Mutlaka okunması gereken kitaplar hangileri?"
    assert q.rewrite("okunması gereken klasikler") == "Okunması gereken klasikler hangileri?"


def test_age_and_grade_mentions():
    assert q.rewrite("9 yaş kitap önerileri") == "9 yaş çocuklar için kitap önerir misin?"
    assert q.rewrite("9-12 yaş kitapları") == "9-12 yaş çocuklar için kitap önerir misin?"
    assert q.rewrite("4. sınıf okuma kitapları") == "4. sınıf öğrencileri için okuma kitabı önerir misin?"
    assert q.rewrite("14 yaş roman önerisi") == "14 yaş gençler için roman önerir misin?"


def test_non_question_brand_and_single_word_queries_are_skipped():
    assert q.rewrite("timaş yayınları") is None
    assert q.rewrite("en iyi timaş kitapları") is None
    assert q.rewrite("kürk mantolu madonna") is None
    assert q.rewrite("roman") is None
    # tek başına "ne" kitap adlarında geçer; soru sayılmaz
    assert q.detect("ne güzel bir gün") is None
    # "yasak" yaş değildir
    assert q.detect("10 yasak meyve") is None


def test_from_queries_keeps_source_query_and_impressions():
    idx = q.book_index([{"ean": "1", "name": "Uzay Macerası", "genres": "Bilim Kurgu"},
                        {"ean": "2", "name": "Kayıp Gezegen", "genres": "Bilim Kurgu, Macera"}])
    rows = [{"keys": ["bilim kurgu kitapları"], "impressions": 1200, "clicks": 30, "position": 7.26},
            {"keys": ["kürk mantolu madonna"], "impressions": 9000}]
    out = q.from_queries(rows, idx)
    assert len(out) == 1
    c = out[0]
    assert c["text"] == "En iyi bilim kurgu kitapları hangileri?"
    assert c["impressions"] == 1200 and c["basis"]["query"] == "bilim kurgu kitapları" and c["basis"]["position"] == 7.3
    assert c["books"] == 2


def test_matching_books_needs_every_topic_word():
    idx = q.book_index([{"ean": "1", "name": "A", "genres": "Macera"}, {"ean": "2", "name": "B", "genres": "Tarih"}])
    assert q.matching_books("macera romanları", idx) == 0          # "roman" hiçbir kitapta yok
    assert q.matching_books("en iyi macera kitapları", idx) == 1
    assert q.matching_books("en iyi kitaplar", idx) is None         # konu kelimesi yok: genel soru


# ------------------------------------------------------------------ tekilleştirme

def test_norm_ignores_case_turkish_letters_punctuation_and_filler():
    assert q.norm("Bana 9 yaş çocuklar için kitap önerir misin?") == q.norm("9 YAŞ ÇOCUKLAR İÇİN KİTAP ÖNERİR MİSİN")
    assert q.norm("Lütfen, roman önerir misin!") == "roman onerir misin"


def test_dedupe_drops_existing_and_keeps_best_duplicate():
    cands = [{"text": "En iyi roman kitapları hangileri?", "source": "arama", "impressions": 10, "books": 1},
             {"text": "en iyi roman kitapları hangileri", "source": "tema", "impressions": None, "books": 40},
             {"text": "Macera önerir misin?", "source": "arama", "impressions": 5, "books": None}]
    existing = {q.norm("Macera önerir misin")}
    out = q.dedupe(cands, existing)
    assert [c["source"] for c in out] == ["tema"]
    assert out[0]["norm"] == "en iyi roman kitaplari hangileri"


def test_score_orders_by_impressions_books_and_season_proximity():
    near = q.score({"books": 5, "daysUntil": 10})
    far = q.score({"books": 5, "daysUntil": 170})
    none = q.score({"books": 5, "daysUntil": None})
    assert near > far > none
    assert q.score({"impressions": 1000}) > q.score({"impressions": 10})


# ------------------------------------------------------------------ tema/yaş kalıbı kitap sayısıyla açılır

def _books(n, **facet):
    return [{"ean": f"{facet.get('p', 'x')}{i}", **{k: v for k, v in facet.items() if k != "p"}} for i in range(n)]


def test_template_needs_min_books():
    books = _books(5, p="a", themes=["Meraklı Çocuklar"], ages=["9 Yaş"]) + _books(4, p="b", themes=["Tarih Yazanlar"])
    texts = {c["text"] for c in q.facet_templates(books, min_books=5)}
    assert "«Meraklı Çocuklar» temalı en iyi kitaplar hangileri?" in texts
    assert "9 yaş çocuklar için «Meraklı Çocuklar» temalı kitap önerir misin?" in texts
    assert not any("Tarih Yazanlar" in t for t in texts)          # 4 kitap < 5
    assert {c["books"] for c in q.facet_templates(books, 5)} == {5}


def test_genre_audience_and_age_range_facets():
    books = _books(6, p="g", genres="Roman, Çocuk Kitapları", ageFrom=13, ageTo=15, audience="Yetişkin")
    texts = {c["text"] for c in q.facet_templates(books, 5)}
    assert "En iyi roman kitapları hangileri?" in texts
    assert "En iyi çocuk kitapları hangileri?" in texts             # "Kitapları" iki kez yazılmaz
    assert "13-15 yaş gençler için roman kitabı önerir misin?" in texts
    assert "Yetişkin okurlar için roman kitabı önerir misin?" in texts


def test_split_values_and_age_label():
    assert q.split_values("Roman, Hikâye; Çocuk > Masal") == ["Roman", "Hikâye", "Masal"]
    assert q.age_label("9 Yaş") == "9" and q.age_label("9-12 Yaş") == "9-12" and q.age_label("Okul öncesi") is None


def test_season_template_skips_days_without_books():
    days = [{"name": "Öğretmenler Günü", "books": 12}, {"name": "Dünya Su Günü", "books": 0}]
    out = q.season_templates(days, date(2026, 11, 1), lambda d, t: date(2026, 11, 24))
    assert [c["text"] for c in out] == ["Öğretmenler Günü için hangi kitap hediye edilir?"]
    assert out[0]["daysUntil"] == 23 and out[0]["basis"]["date"] == "2026-11-24"


def test_crm_links_sql_reads_only():
    sql = q.links_sql("db.dbo.", *q.CRM_SOURCES["yas"])
    assert sql.startswith("SELECT") and "new_new_kitap_new_yasBase" in sql and "new_yasBase" in sql
    assert not any(w in sql.upper() for w in ("INSERT", "UPDATE", "DELETE"))


def test_read_crm_links_parses_and_dedupes():
    def execute(sql, limit):
        if "temaBase" in sql:
            return None, [{"ean": "978-605-08-1234-5", "name": " Genç Kahramanlar "},
                          {"ean": "9786050812345", "name": "Genç Kahramanlar"}, {"ean": "12", "name": "Kısa"}], False
        return None, [{"ean": "9786050812345", "name": "9 Yaş"}], False

    out = q.read_crm_links("Timas_MSCRM.dbo", execute)
    assert out == [("9786050812345", "tema", "Genç Kahramanlar"), ("9786050812345", "yas", "9 Yaş")]


# ------------------------------------------------------------------ YouTube: kimlik, toplu okuma, denetim

def test_video_ids_from_all_url_forms():
    field = ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s, https://youtu.be/abcdefghijk "
             "https://www.youtube.com/embed/ABCDEFGHIJK https://youtube.com/shorts/a1b2c3d4e5f "
             "https://www.youtube.com/channel/UCxyz https://youtu.be/abcdefghijk")
    assert y.video_ids(field) == ["dQw4w9WgXcQ", "abcdefghijk", "ABCDEFGHIJK", "a1b2c3d4e5f"]
    assert y.video_ids(None) == [] and y.video_ids("bozuk") == []


def test_fetch_batches_by_50_and_marks_missing():
    ids = [f"id{i:09d}" for i in range(120)]
    calls = []

    def get(params):
        chunk = params["id"].split(",")
        calls.append(len(chunk))
        return {"items": [{"id": v, "snippet": {"title": "t", "channelId": "c", "channelTitle": "Kanal"},
                           "statistics": {"viewCount": "7"}, "status": {"privacyStatus": "public", "embeddable": True},
                           "contentDetails": {"duration": "PT1M"}} for v in chunk if v != "id000000003"]}

    rows, n = y.fetch(ids, "k", get)
    assert calls == [50, 50, 20] and n == 3
    assert len(rows) == 120
    missing = [r for r in rows if not r["found"]]
    assert [r["video_id"] for r in missing] == ["id000000003"]
    assert rows[0]["views"] == 7 and rows[0]["channel"] == "Kanal"


def test_duration_seconds():
    assert y.duration_seconds("PT1H2M3S") == 3723
    assert y.duration_seconds("PT45S") == 45
    assert y.duration_seconds("P1DT1S") == 86401
    assert y.duration_seconds(None) is None and y.duration_seconds("PT") is None


BOOK = {"id": "p1", "name": "Kayıp Gezegen (Ciltli)", "url": "https://timas.com.tr/kayip-gezegen", "sales": 3}


def _video(**kw):
    base = {"found": True, "title": "Kayıp Gezegen | Kitap Tanıtımı", "privacy": "public", "embeddable": True,
            "description": "Kitabı inceleyin: https://www.timas.com.tr/kayip-gezegen/?utm_source=yt " + "x" * 250}
    return {**base, **kw}


def test_audit_clean_video_has_no_flags():
    assert y.audit(_video(), [BOOK]) == []


def test_audit_link_rules():
    other = _video(description="Tüm kitaplar: timas.com.tr/cocuk " + "x" * 250)
    assert y.audit(other, [BOOK]) == ["kitap_linki_yok"]
    none = _video(description="Bizi takip edin https://instagram.com/timas " + "x" * 250)
    assert y.audit(none, [BOOK]) == ["link_yok", "kitap_linki_yok"]


def test_audit_title_length_privacy_and_embedding():
    v = _video(title="Yeni kitabımız çıktı", description="Kısa: https://timas.com.tr/kayip-gezegen",
               privacy="unlisted", embeddable=False)
    assert y.audit(v, [BOOK]) == ["liste_disi", "gomulemez", "baslik", "kisa"]
    assert y.audit(_video(privacy="private"), [BOOK]) == ["gizli"]


def test_audit_missing_unchecked_and_shared_video():
    two = [BOOK, {**BOOK, "id": "p2", "name": "Başka Kitap", "url": "https://timas.com.tr/baska"}]
    assert y.audit({"found": False}, [BOOK]) == ["yok"]
    assert y.audit(None, two) == ["denetlenmedi", "coklu"]
    assert "coklu" in y.audit(_video(), two)
    assert "baslik" not in y.audit(_video(), two)       # kitaplardan birinin adı başlıkta yeter


def test_title_match_ignores_case_and_turkish_letters():
    assert y.title_has_book("KAYIP GEZEGEN - fragman", "Kayıp Gezegen")
    assert not y.title_has_book("Kayıp Gezegenler", "Kayıp Gezegen")


def test_suggestion_line_and_channels():
    assert y.suggestion(BOOK["url"]) == "Kitabı timas.com.tr'de inceleyin: https://timas.com.tr/kayip-gezegen"
    assert y.suggestion(None) is None
    rows = [{"found": True, "channel_id": "A", "channel": "Timaş", "views": 10},
            {"found": True, "channel_id": "A", "channel": "Timaş", "views": 5},
            {"found": True, "channel_id": "B", "channel": "Başka", "views": 100},
            {"found": False, "channel_id": None, "views": None}]
    assert y.channels(rows) == [{"channelId": "B", "channel": "Başka", "videos": 1, "views": 100},
                                {"channelId": "A", "channel": "Timaş", "videos": 2, "views": 15}]
