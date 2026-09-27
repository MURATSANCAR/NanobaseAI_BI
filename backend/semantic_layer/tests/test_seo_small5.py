"""SEO & GEO küçük özellikler: okur yorumları, video, satıştan kalkan kitaplar, yazar güven sinyalleri, gelen bağlantılar.
Yalnız saf kurallar; ağ ve veritabanı yok."""
import xml.etree.ElementTree as ET

from semantic_bridge.seo_geo import authors, backlinks, reviews, sunset, video


# ------------------------------------------------------------------ okur yorumları
def test_review_aggregation_counts_only_approved_and_keeps_no_identity():
    rows = [
        {"ProductId": "7", "Type": "comment", "Rate": "5", "IsApproved": "1", "CustomerName": "X", "Email": "x@y"},
        {"ProductId": "7", "Type": "comment", "Rate": "3", "IsApproved": "1"},
        {"ProductId": "7", "Type": "comment", "Rate": "1", "IsApproved": "0"},
        {"ProductId": "7", "Type": "question", "Rate": "5"},
        {"ProductId": "9", "Rate": "0"},
    ]
    agg = reviews.aggregate(rows)
    a = agg["7"]
    assert (a["comments"], a["approved"], a["rated"]) == (3, 2, 2)
    assert a["rateSum"] == 8 and a["stars"]["5"] == 1 and a["stars"]["3"] == 1 and a["stars"]["1"] == 0
    assert agg["9"]["rated"] == 0 and agg["9"]["approved"] == 1
    assert "X" not in str(agg) and "x@y" not in str(agg)


def test_review_star_scale_and_merge_with_product_record():
    assert reviews.star("4.6") == 5 and reviews.star(80) == 4 and reviews.star(0) is None
    assert reviews.product_rating({"CommentCount": "4", "CommentRate": "90"}) == (4, 4.5)
    m = reviews.merge({"CommentCount": "1", "CommentRate": "5"},
                      {"approved": 3, "rated": 2, "rateSum": 9.0, "stars": {"4": 1, "5": 1}})
    assert m["count"] == 3 and m["average"] == 4.5 and m["source"] == "yorumlar"
    assert reviews.merge({}, None) == {"count": 0, "average": None, "stars": None, "source": None}


def test_review_summary_and_lists():
    rows = [
        {"name": "A", "author": None, "sales": 500, "count": 0, "average": None, "stars": None, "schema": "tamam"},
        {"name": "B", "author": None, "sales": 50, "count": 2, "average": 5.0, "stars": {"5": 2}, "schema": "puan_yok"},
        {"name": "C", "author": None, "sales": 10, "count": 1, "average": 2.0, "stars": None, "schema": "taranmadi"},
    ]
    s = reviews.summarize(rows)
    assert s["withReviews"] == 2 and s["reviews"] == 3 and s["zeroTopSelling"] == 1 and s["schemaMissing"] == 1
    assert s["average"] == 4.0 and s["bookAverages"]["5"] == 1 and s["bookAverages"]["2"] == 1
    assert [r["name"] for r in reviews.pick(rows, "yorumsuz")] == ["A"]
    assert [r["name"] for r in reviews.pick(rows, "puansiz_sema")] == ["B"]
    assert [r["name"] for r in reviews.pick(rows, "dusuk")] == ["C"]


# ------------------------------------------------------------------ video
def test_youtube_id_parsing():
    vid = "dQw4w9WgXcQ"
    for url in (f"https://www.youtube.com/watch?v={vid}&t=10s", f"https://youtu.be/{vid}?si=abc",
                f"https://www.youtube.com/embed/{vid}", f"youtube.com/shorts/{vid}", f"https://m.youtube.com/watch?v={vid}",
                f"https://www.youtube-nocookie.com/embed/{vid}", f"https://www.youtube.com/live/{vid}"):
        assert video.youtube_id(url) == vid, url
    for bad in ("https://www.youtube.com/@timasyayinlari", "https://www.youtube.com/channel/UC123",
                "https://vimeo.com/123", "https://www.youtube.com/watch?v=short", "", None):
        assert video.youtube_id(bad) is None, bad


def test_video_object_jsonld():
    o = video.video_object("Kitap", "Spot metni", "dQw4w9WgXcQ", "https://timas.com.tr/kitap")
    assert o["@type"] == "VideoObject" and "uploadDate" not in o
    assert o["thumbnailUrl"] == ["https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"]
    assert o["embedUrl"].endswith("/embed/dQw4w9WgXcQ") and o["contentUrl"].endswith("watch?v=dQw4w9WgXcQ")
    assert o["isPartOf"]["@id"] == "https://timas.com.tr/kitap"
    assert video.description({"spot": None, "summary": "  Özet  "}, "Ad", 100) == "Özet"
    assert video.description({}, "Ad", 100).startswith("Ad")
    assert video.schema_state(["Book", "VideoObject"], True) == "var"
    assert video.schema_state(["Book"], True) == "yok" and video.schema_state(None, False) == "bilinmiyor"


def test_video_sitemap_is_valid_xml_and_groups_by_page():
    xml = video.sitemap_xml([
        {"url": "https://timas.com.tr/a?x=1&y=2", "vid": "dQw4w9WgXcQ", "title": "A & B", "description": "<b>d</b>"},
        {"url": "https://timas.com.tr/a?x=1&y=2", "vid": "dQw4w9WgXcQ", "title": "A & B", "description": "d"},
        {"url": "https://timas.com.tr/b", "vid": "aaaaaaaaaaa", "title": "B", "description": "x" * 5000},
        {"url": None, "vid": "bbbbbbbbbbb", "title": "C", "description": "d"},
    ])
    root = ET.fromstring(xml.encode())
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9", "v": "http://www.google.com/schemas/sitemap-video/1.1"}
    urls = root.findall("s:url", ns)
    assert len(urls) == 2
    assert len(urls[0].findall("v:video", ns)) == 1
    assert urls[0].find("s:loc", ns).text == "https://timas.com.tr/a?x=1&y=2"
    assert urls[0].find("v:video/v:title", ns).text == "A & B"
    assert len(urls[1].find("v:video/v:description", ns).text) <= video.SITEMAP_DESC_MAX
    assert urls[1].find("v:video/v:player_loc", ns).text.endswith("/embed/aaaaaaaaaaa")


# ------------------------------------------------------------------ satıştan kalkan
def test_sunset_reason_from_status_label_code():
    assert sunset.sunset_reason("YS07 - Baskısı bitti - yeni baskı yapılmayacak") == "baski_bitti"
    assert sunset.sunset_reason("YS05 Artık bizim ürünümüz değil") == "bizim_degil"
    assert sunset.sunset_reason("ys12: geri istendi") == "geri_istendi"
    assert sunset.sunset_reason("YS02 - Yayında") is None and sunset.sunset_reason(None) is None


def test_sunset_rules():
    ed = ("yeni-baski", "Aynı ISBN")
    assert sunset.recommend("bizim_degil", 0, ed, "yazar")[:2] == ("yeni_baski_301", "yeni-baski")
    assert sunset.recommend("bizim_degil", 50, None, "yazar")[:2] == ("yazar_301", "yazar")
    assert sunset.recommend("bizim_degil", 50, None, None)[0] == "gone_410"
    assert sunset.recommend("devredildi", 0, None, "yazar")[0] == "gone_410"
    assert sunset.recommend("baski_bitti", sunset.SEARCHED_MIN, None, "yazar")[0] == "stokta_yok"
    assert sunset.recommend("baski_bitti", sunset.SEARCHED_MIN - 1, None, "yazar")[:2] == ("yazar_301", "yazar")
    assert sunset.recommend("pasif", 0, None, None)[0] == "stokta_yok"


def test_sunset_edition_matching_excludes_self():
    prods = [
        {"ProductName": "Kayıp Şehir (Ciltli)", "Model": "Ayşe Yazar", "SeoLink": "kayip-sehir-ciltli", "Barcode": "9786050000001", "IsActive": "0"},
        {"ProductName": "Kayıp Şehir", "Model": "Ayşe Yazar", "SeoLink": "kayip-sehir", "Barcode": "9786050000002", "IsActive": "1"},
        {"ProductName": "Başka Kitap", "Model": "B", "SeoLink": "baska-kitap", "Barcode": "9786050000003", "IsActive": "1"},
        {"ProductName": "Başka Kitap", "Model": "B", "SeoLink": "baska-kitap-2", "Barcode": "9786050000003", "IsActive": "1"},
    ]
    e = sunset.Editions(prods)
    assert e.find(prods[0])[0] == "kayip-sehir"
    assert e.find(prods[1]) is None                   # yalnız kendisi
    assert e.find(prods[2])[0] == "baska-kitap-2"     # aynı ISBN'li başka ürün


def test_sunset_gsc_paths():
    got = sunset.gsc_by_path([{"keys": ["https://timas.com.tr/Kayip-Sehir/"], "impressions": 5, "clicks": 1},
                              {"keys": ["https://www.timas.com.tr/kayip-sehir"], "impressions": 7, "clicks": 0}])
    assert got["kayip-sehir"] == (12, 1)
    assert sunset.path_of("/kayip-sehir/") == "kayip-sehir"


# ------------------------------------------------------------------ yazar güven sinyalleri
def _facts(**kw):
    base = {"page": True, "pageLink": "ayse-yazar", "pageMetaOk": True, "introReady": True, "crmBio": True,
            "wikidata": "wikipedia", "sameas": (3, 3), "credits": (1, 1), "awards": 2}
    return {**base, **kw}


def test_author_checklist_full_score():
    items, score = authors.checklist(_facts())
    assert score == 100 and all(i["state"] == "ok" for i in items)


def test_author_checklist_partial_and_unknown_items_leave_denominator():
    items, score = authors.checklist(_facts(introReady=False, wikidata="wikidata", sameas=(0, 0), credits=(0, 0), awards=None))
    by = {i["id"]: i for i in items}
    assert by["bio"]["state"] == "kismi" and by["wikidata"]["state"] == "kismi"
    assert by["sameas"]["state"] == "bilinmiyor" and by["credits"]["state"] == "uymaz" and by["awards"]["state"] == "bilinmiyor"
    # bilinen: page 20 + meta 10 + bio 10/20 + wikidata 15/20 → 55/70
    assert score == round(100 * 55 / 70)


def test_author_checklist_no_page():
    items, score = authors.checklist(_facts(page=False, pageMetaOk=None, introReady=False, crmBio=False, wikidata="yok",
                                            sameas=(0, 2), credits=(0, 1), awards=0))
    assert score == 0
    assert {i["id"] for i in items if i["state"] == "eksik"} == {"page", "bio", "wikidata", "sameas", "credits", "awards"}
    assert all(i["action"] for i in items if i["state"] == "eksik")


def test_author_credit_detection():
    assert authors.credited("Ali Veli, Ayşe Kaya", "Çeviren: ALİ VELİ · Resimleyen: Ayşe Kaya") is True
    assert authors.credited("Ali Veli", "Künye: çevirmen belirtilmemiş") is False
    assert authors.credited(None, "x") is None


# ------------------------------------------------------------------ gelen bağlantılar
def test_backlink_parsing():
    rows, pages = backlinks.parse_link_counts({"d": {"__type": "LinkCounts", "Links": [
        {"__type": "LinkCount", "Count": 12, "Url": "https://timas.com.tr/a"}, {"Count": "3", "Url": ""}], "TotalPages": 2}})
    assert rows == [{"url": "https://timas.com.tr/a", "count": 12}] and pages == 2
    det, p = backlinks.parse_url_links({"d": {"Details": [{"AnchorText": " Kitap ", "Url": "https://blog.ornek.com/x"}], "TotalPages": 1}})
    assert det == [{"url": "https://blog.ornek.com/x", "anchor": "Kitap"}] and p == 1


def test_backlink_diff_only_compares_detailed_targets():
    prev = [("a", "https://x.com/1"), ("a", "https://y.com/2"), ("b", "https://z.com/3")]
    cur = [("a", "https://x.com/1"), ("a", "https://w.com/4"), ("c", "https://q.com/5")]
    d = backlinks.diff(prev, cur, {"a"})
    assert d["new"] == [("a", "https://w.com/4")] and d["lost"] == [("a", "https://y.com/2")]


def test_backlink_domains_and_url_norm():
    doms = backlinks.domains([("a", "https://www.x.com/1"), ("b", "https://x.com/2"), ("a", "https://y.org/")])
    assert doms[0] == {"domain": "x.com", "links": 2, "pages": 2}
    assert backlinks.norm_url("https://www.timas.com.tr/Kitap/") == backlinks.norm_url("timas.com.tr/kitap")
