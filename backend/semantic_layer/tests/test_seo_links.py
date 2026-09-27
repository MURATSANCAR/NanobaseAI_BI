"""SEO & GEO → site içi bağlantılar (seo_geo/links.py): ağsız, veritabansız, düz veriyle."""
from semantic_bridge.seo_geo import links, tech

SITE = "https://timas.com.tr"
BASE = "https://timas.com.tr/kuyucakli-yusuf"


# ------------------------------------------------------------------ adres normalleştirme
def test_relative_link_becomes_absolute_without_fragment_or_trailing_slash():
    assert links.normalize_link("/roman/#ust", BASE, SITE) == "https://timas.com.tr/roman"
    assert links.normalize_link("sabahattin-ali", "https://timas.com.tr/yazar/", SITE) == "https://timas.com.tr/yazar/sabahattin-ali"
    assert links.normalize_link("../roman", "https://timas.com.tr/a/b", SITE) == "https://timas.com.tr/roman"


def test_tracking_params_dropped_other_params_kept():
    u = links.normalize_link("/roman?utm_source=menu&gclid=x&sayfa=2&fbclid=y", BASE, SITE)
    assert u == "https://timas.com.tr/roman?sayfa=2"
    assert links.normalize_link("/roman?utm_medium=a", BASE, SITE) == "https://timas.com.tr/roman"


def test_host_equality_ignores_www_and_default_port():
    assert links.normalize_link("https://www.timas.com.tr/roman", BASE, SITE) == "https://timas.com.tr/roman"
    assert links.normalize_link("https://timas.com.tr:443/roman", "https://www.timas.com.tr/", SITE) == "https://www.timas.com.tr/roman"
    assert links.url_key("https://www.timas.com.tr/Roman/") == links.url_key("http://timas.com.tr/roman")


def test_non_page_links_skipped():
    for href in ("https://baska-site.com/roman", "mailto:a@b.c", "tel:123", "javascript:void(0)", "#", "",
                 "/img/kapak.jpg", "/rest1/product/get", "//cdn.timas.com.tr/a.css", "ftp://timas.com.tr/x"):
        assert links.normalize_link(href, BASE, SITE) is None, href


def test_parse_page_collects_anchor_text_with_fallbacks():
    p = tech.parse_page('<a href="/a">Roman <b>kitapları</b></a><a href="/b"><img src="k.jpg" alt="Kapak"></a>'
                        '<a href="/c" aria-label="Sepet"></a><a href="/d" rel="nofollow">x')
    assert p["links"] == ["/a", "/b", "/c", "/d"]  # eski davranış aynı
    assert [(a["href"], a["text"]) for a in p["anchors"]] == [("/a", "Roman kitapları"), ("/b", "Kapak"), ("/c", "Sepet"), ("/d", "x")]
    assert p["anchors"][3]["rel"] == "nofollow"


def test_edges_group_by_target_drop_self_and_track_nofollow():
    anchors = [
        {"href": "/icimizdeki-seytan", "text": "", "rel": ""},
        {"href": "/icimizdeki-seytan/?utm_source=x", "text": "İçimizdeki Şeytan", "rel": ""},
        {"href": "/kuyucakli-yusuf#yorum", "text": "Yorumlar", "rel": ""},          # kendine
        {"href": "/sepet", "text": "Sepet", "rel": "nofollow"},
        {"href": "https://baska.com/", "text": "dış", "rel": ""},
    ]
    edges = {e["dst"]: e for e in links.edges_from_page(anchors, BASE, SITE)}
    assert set(edges) == {"https://timas.com.tr/icimizdeki-seytan", "https://timas.com.tr/sepet"}
    e = edges["https://timas.com.tr/icimizdeki-seytan"]
    assert e["count"] == 2 and e["anchor"] == "İçimizdeki Şeytan" and e["anchors"] == ["", "İçimizdeki Şeytan"]
    assert not e["nofollow"] and edges["https://timas.com.tr/sepet"]["nofollow"]
    assert all(x["nofollow"] for x in links.edges_from_page(anchors, BASE, SITE, page_nofollow=True))


# ------------------------------------------------------------------ bağlantı metni
def test_generic_and_empty_anchor_detection():
    for t in ("Tıklayın", "BURAYA TIKLAYINIZ!", "detay", "Devamını oku »", "İncele", "2", "45,00 TL", "read more"):
        assert links.classify_anchor(t) == "generic", t
    for t in ("", "   ", "»", None):
        assert links.classify_anchor(t) == "empty", t
    for t in ("Kuyucaklı Yusuf", "Roman", "Sabahattin Ali kitapları"):
        assert links.classify_anchor(t) == "ok", t


# ------------------------------------------------------------------ BFS
def test_click_depth_bfs_and_path():
    out = {"h": {"a", "b"}, "a": {"c"}, "b": {"c", "d"}, "c": {"e"}, "e": {"h"}, "x": {"y"}}
    depth, parent = links.click_depths(out, "h")
    assert depth == {"h": 0, "a": 1, "b": 1, "c": 2, "d": 2, "e": 3}
    assert "x" not in depth and "y" not in depth  # anasayfadan ulaşılamayan
    assert links.path_to(parent, "e") == ["h", "a", "c", "e"]


# ------------------------------------------------------------------ bütün analiz
def _u(p: str) -> str:
    return f"{SITE}/{p}" if p else f"{SITE}/"


PAGES = [
    {"url": _u(""), "final": _u(""), "status": 200, "kind": "home", "productId": None, "linksKnown": True},
    {"url": _u("roman"), "final": _u("roman"), "status": 200, "kind": "category", "productId": None, "linksKnown": True},
    {"url": _u("sabahattin-ali"), "final": _u("sabahattin-ali"), "status": 200, "kind": "author", "productId": None, "linksKnown": True},
    # ürünün kayıtlı adresi yönleniyor: bağlantılar son adrese sayılır
    {"url": _u("kuyucakli-yusuf-eski"), "final": _u("kuyucakli-yusuf"), "status": 200, "kind": "product", "productId": "1",
     "linksKnown": True},
    # bu özellikten önce taranmış: bağlantıları bilinmiyor
    {"url": _u("sirca-kosk"), "final": _u("sirca-kosk"), "status": 200, "kind": "product", "productId": "4", "linksKnown": False},
]
EDGES = [
    {"src": _u(""), "dst": _u("roman"), "anchors": ["Roman"], "nofollow": False},
    {"src": _u(""), "dst": _u("kurk-mantolu-madonna"), "anchors": ["Kürk Mantolu Madonna"], "nofollow": True},
    {"src": _u("roman"), "dst": _u("kuyucakli-yusuf"), "anchors": ["", "Kuyucaklı Yusuf"], "nofollow": False},
    {"src": _u("roman"), "dst": _u("sabahattin-ali"), "anchors": ["Sabahattin Ali"], "nofollow": False},
    {"src": _u("sabahattin-ali"), "dst": _u("kuyucakli-yusuf"), "anchors": ["Kuyucaklı Yusuf"], "nofollow": False},
    {"src": _u("sabahattin-ali"), "dst": _u("sabahattin-ali?pg=2"), "anchors": ["2"], "nofollow": False},
    {"src": _u("kuyucakli-yusuf"), "dst": "https://www.timas.com.tr/icimizdeki-seytan", "anchors": ["İncele"], "nofollow": False},
]
PRODUCTS = [
    {"id": "1", "name": "Kuyucaklı Yusuf", "url": _u("kuyucakli-yusuf-eski"), "sales": 500, "authorId": "10", "categoryId": "5"},
    {"id": "2", "name": "İçimizdeki Şeytan", "url": _u("icimizdeki-seytan"), "sales": 300, "authorId": "10", "categoryId": "5"},
    {"id": "3", "name": "Kürk Mantolu Madonna", "url": _u("kurk-mantolu-madonna"), "sales": 900, "authorId": "10"},
    {"id": "4", "name": "Sırça Köşk", "url": _u("sirca-kosk"), "sales": 10, "authorId": "11"},
]
LINK_PAGES = [
    {"type": "model", "id": "10", "name": "Sabahattin Ali", "url": _u("sabahattin-ali")},
    {"type": "category", "id": "5", "name": "Roman", "url": _u("roman")},
]


def _run(monkeypatch=None, missing=None):
    return links.analyse(SITE, PAGES, EDGES, PRODUCTS, LINK_PAGES, missing)


def test_orphans_with_partial_coverage():
    r = _run(missing={tech._key(_u("kurk-mantolu-madonna"))})
    orphans = {o["id"]: o for o in r["lists"]["orphans"]}
    # 3: yalnız nofollow bağlantı; 4: taranan hiçbir sayfadan bağlantı yok (kendisi eski taramadan)
    assert set(orphans) == {"3", "4"}
    o = orphans["3"]
    assert o["nofollowInlinks"] == 1 and o["inlinks"] == 0 and o["inSitemap"] is False
    assert o["authorPageCrawled"] is True and o["authorUrl"] == _u("sabahattin-ali")
    assert orphans["4"]["authorPageCrawled"] is None and orphans["4"]["inSitemap"] is True
    assert [o["id"] for o in r["lists"]["orphans"]] == ["3", "4"]  # satışa göre
    s = r["summary"]
    assert s["crawledPages"] == 4 and s["techPages"] == 5
    cov = s["coverage"]
    assert cov["byKind"]["product"] == {"crawled": 1, "of": 4}   # sırça köşk bağlantısı bilinmediği için taranmış sayılmaz
    assert cov["byKind"]["author"] == {"crawled": 1, "of": 1} and cov["byKind"]["category"] == {"crawled": 1, "of": 1}
    assert cov["crawled"] == 3 and cov["of"] == 6 and cov["share"] == 0.5
    assert s["series"]["available"] is False


def test_inlinks_follow_redirect_alias_and_www():
    r = _run()
    weak = {w["id"]: w for w in r["lists"]["weak"]}
    assert weak["1"]["inlinks"] == 2 and weak["1"]["crawled"] is True   # eski adres → son adres
    assert weak["2"]["inlinks"] == 1                                      # www'li bağlantı
    assert [w["id"] for w in r["lists"]["weak"]] == ["3", "1", "2", "4"]  # çok satan önce


def test_deep_pages_and_path(monkeypatch):
    monkeypatch.setattr(links, "DEEP_CLICKS", 2)
    r = _run()
    deep = {d["url"]: d for d in r["lists"]["deep"]}
    d = deep[_u("icimizdeki-seytan")]
    assert d["depth"] == 3
    assert d["path"] == [_u(""), _u("roman"), _u("kuyucakli-yusuf"), "https://www.timas.com.tr/icimizdeki-seytan"]
    assert _u("roman") not in deep


def test_no_depth_without_home_crawl():
    pages = [p for p in PAGES if p["kind"] != "home"]
    r = links.analyse(SITE, pages, [e for e in EDGES if e["src"] != _u("")], PRODUCTS, LINK_PAGES)
    assert r["summary"]["homeCrawled"] is False and r["lists"]["deep"] == []
    assert all(w["depth"] is None for w in r["lists"]["weak"])


def test_author_book_consistency():
    rows = _run()["lists"]["author"]
    assert len(rows) == 1
    a = rows[0]
    assert a["id"] == "10" and a["pageCrawled"] and a["books"] == 3 and a["linkedBooks"] == 1
    assert [b["id"] for b in a["missingBooks"]] == ["3", "2"]
    assert [b["id"] for b in a["booksWithoutAuthorLink"]] == ["1"]   # kitap sayfası yazarına bağlantı vermiyor
    assert a["paginated"] is True
    assert _run()["summary"]["authorsWithoutPage"] == 1              # yazar 11'in sayfası yok


def test_author_links_unknown_when_author_page_not_crawled():
    books = [{"id": "1", "name": "A", "url": "u1", "key": "k1", "sales": 5, "authorId": "10"}]
    pages = {"10": {"id": "10", "name": "Y", "url": "ua", "key": "ka"}}
    # yazar sayfası taranmadı, kitap tarandı ve yazara bağlantı veriyor → sorun yok
    assert links.author_links(books, pages, {"k1": {"ka"}}, {"k1"}) == []
    rows = links.author_links(books, pages, {"k1": set()}, {"k1"})
    assert rows[0]["linkedBooks"] is None and rows[0]["missingBooks"] == [] and rows[0]["booksWithoutAuthorLink"][0]["id"] == "1"


def test_anchor_quality_rows():
    r = _run()
    rows = {x["url"]: x for x in r["lists"]["anchors"]}
    assert set(rows) == {_u("icimizdeki-seytan"), _u("sabahattin-ali?pg=2")}
    x = rows[_u("icimizdeki-seytan")]
    assert x["anchors"] == {"ok": 0, "generic": 1, "empty": 0} and x["examples"] == ["İncele"]
    texts = {t["text"]: t["count"] for t in r["summary"]["anchorTexts"]}
    assert texts["incele"] == 1 and texts["(sayı)"] == 1
    assert r["summary"]["emptyAnchorLinks"] == 1   # kuyucaklı yusuf'a boş metinli görsel bağlantı (aynı sayfada metinli de var)


def test_url_detail_inlinks_and_outlinks():
    g = _run()["graph"]
    d = links.url_detail(g, _u("kuyucakli-yusuf-eski"))
    assert d["crawled"] and d["depth"] == 2
    assert sorted(i["url"] for i in d["inlinks"]) == [_u("roman"), _u("sabahattin-ali")]
    assert [(o["url"], o["anchorClass"]) for o in d["outlinks"]] == [("https://www.timas.com.tr/icimizdeki-seytan", "generic")]
    assert d["item"]["kind"] == "product" and d["item"]["id"] == "1"
