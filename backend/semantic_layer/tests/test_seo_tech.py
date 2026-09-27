"""SEO & GEO → teknik sağlık (seo_geo/tech.py) ve hız (seo_geo/speed.py): ağsız, saf fonksiyonlar."""
import gzip
from datetime import datetime, timezone

import httpx

from semantic_bridge.seo_geo import speed, tech

LIM = {"title_min": 30, "title_max": 65}
URL = "https://timas.com.tr/kuyucakli-yusuf"

PAGE = """<!doctype html><html><head>
<title>Kuyucaklı Yusuf - Sabahattin Ali | Timaş Yayınları</title>
<meta name="robots" content="index, follow">
<meta property="og:image" content="https://cdn.timas.com.tr/urun/kuyucakli-yusuf-kapak.jpg">
<link rel="canonical" href="https://timas.com.tr/kuyucakli-yusuf">
<link rel="alternate" hreflang="tr" href="https://timas.com.tr/kuyucakli-yusuf">
</head><body>
<h1>Kuyucaklı Yusuf</h1>
<img src="https://cdn.timas.com.tr/urun/kuyucakli-yusuf-kapak.jpg" alt="Kuyucaklı Yusuf kitap kapağı" width="400" height="600">
<img src="/img/1234567.jpg" width="10" height="10">
<img src="/img/logo.png" alt="">
<img data-src="/img/a1b2c3d4e5f6a7b8.webp" src="data:image/gif;base64,xx" alt="x">
<a href="/kategori/roman?utm_source=menu">Roman</a>
<a href="https://baska-site.com/?utm_source=x">dış</a>
<a href="/yazar/sabahattin-ali">Yazar</a>
</body></html>"""


# ------------------------------------------------------------------ HTML
def test_parse_page_reads_head_and_images():
    p = tech.parse_page(PAGE)
    assert p["title"] == "Kuyucaklı Yusuf - Sabahattin Ali | Timaş Yayınları"
    assert p["canonicals"] == ["https://timas.com.tr/kuyucakli-yusuf"]
    assert p["robots"] == ["index, follow"]
    assert p["hreflang"] == [{"lang": "tr", "href": "https://timas.com.tr/kuyucakli-yusuf"}]
    assert p["h1"] == 1
    alts = [i["alt"] for i in p["images"]]
    assert alts == ["Kuyucaklı Yusuf kitap kapağı", None, "", "x"]
    assert p["images"][3]["src"] == "/img/a1b2c3d4e5f6a7b8.webp"  # tembel yüklemede data-src


def test_page_issues_images_tracking_and_clean_canonical():
    found, data = tech.page_issues(tech.parse_page(PAGE), URL, {}, "product", "Kuyucaklı Yusuf", LIM)
    assert "img_no_alt" in found and "img_empty_alt" in found and "img_bad_name" in found and "img_no_size" in found
    assert "tracking_links" in found and data["trackingLinks"] == ["https://timas.com.tr/kategori/roman?utm_source=menu"]
    assert not {"no_canonical", "canonical_other", "noindex", "main_img_alt", "h1_missing"} & set(found)
    assert data["canonical"]["kind"] == "self" and data["mainImage"]["alt"] == "Kuyucaklı Yusuf kitap kapağı"


def test_page_issues_noindex_header_and_main_image_alt():
    html = PAGE.replace('content="index, follow"', 'content="noindex, nofollow"').replace(
        'alt="Kuyucaklı Yusuf kitap kapağı"', 'alt="ürün görseli"')
    found, _ = tech.page_issues(tech.parse_page(html), URL, {"X-Robots-Tag": "noindex"}, "product", "Kuyucaklı Yusuf", LIM)
    assert {"noindex", "nofollow", "header_noindex", "main_img_alt"} <= set(found)


def test_canonical_kinds():
    assert tech.canonical_kind(None, URL) == "missing"
    assert tech.canonical_kind("https://timas.com.tr/kuyucakli-yusuf/", URL) == "self"
    assert tech.canonical_kind("/kuyucakli-yusuf", URL) == "relative"
    assert tech.canonical_kind("https://timas.com.tr/baska-kitap", URL) == "other"
    found, _ = tech.page_issues(tech.parse_page(
        '<link rel="canonical" href="https://timas.com.tr/kuyucakli-yusuf?utm_source=a"><title>t</title>'), URL, {}, "home", "", LIM)
    assert "canonical_tracking" in found and "canonical_other" in found and "title_length" in found


def test_alt_match_and_bad_names():
    assert tech.alt_matches_name("KUYUCAKLI YUSUF - kapak", "Kuyucaklı Yusuf")
    assert not tech.alt_matches_name("kapak", "Kuyucaklı Yusuf")
    assert tech.bad_image_name("/x/20240101_123.jpg") and tech.bad_image_name("/x/9f86d081884c7d65.png")
    assert not tech.bad_image_name("/x/kuyucakli-yusuf-kapak.jpg")


# ------------------------------------------------------------------ yönlendirme
def _client(routes):
    def handler(request: httpx.Request) -> httpx.Response:
        status, loc = routes[str(request.url)]
        return httpx.Response(status, headers={"location": loc} if loc else {}, text="<html></html>")
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


def test_redirect_chain_classification():
    a, b, c = "https://timas.com.tr/a", "https://timas.com.tr/b", "https://timas.com.tr/c"
    chain, resp = tech.fetch_chain(_client({a: (301, "/b"), b: (302, c), c: (200, None)}), a)
    assert [x["status"] for x in chain] == [301, 302, 200] and resp.status_code == 200
    assert tech.chain_issues(chain) == ["redirect_chain"]

    chain, _ = tech.fetch_chain(_client({a: (301, b), b: (200, None)}), a)
    assert tech.chain_issues(chain) == ["redirected"]

    chain, resp = tech.fetch_chain(_client({a: (301, b), b: (301, a)}), a)
    assert resp is None and tech.chain_issues(chain) == ["redirect_loop"]

    chain, _ = tech.fetch_chain(_client({a: (404, None)}), a)
    assert tech.chain_issues(chain) == ["not_found"]
    assert tech.chain_issues([{"url": a, "status": 503}]) == ["server_error"]
    assert tech.chain_issues([{"url": a, "status": 0}]) == ["fetch_error"]


def test_redirect_never_follows_api_paths():
    a = "https://timas.com.tr/a"
    chain, resp = tech.fetch_chain(_client({a: (301, "/rest1/product")}), a)
    assert resp is None and len(chain) == 1 and "redirect_loop" not in tech.chain_issues(chain)


# ------------------------------------------------------------------ robots.txt
ROBOTS = """
User-agent: *
Disallow: /arama
Disallow: /*?utm_
Allow: /arama/yardim$

User-agent: GPTBot
User-agent: CCBot
Disallow: /

User-agent: Googlebot
Disallow: /sepet
Allow: /
Sitemap: https://timas.com.tr/sitemap.xml
"""


def test_robots_groups_and_longest_match():
    p = tech.parse_robots(ROBOTS)
    assert p["sitemaps"] == ["https://timas.com.tr/sitemap.xml"]
    d = lambda agent, path: tech.robots_decision(p, agent, "https://timas.com.tr" + path)["allowed"]  # noqa: E731
    assert not d("GPTBot", "/kitap") and not d("CCBot", "/")
    assert d("Googlebot", "/arama?q=x")            # kendi grubu var: * grubu uygulanmaz
    assert not d("Googlebot", "/sepet")
    assert not d("PerplexityBot", "/arama?q=kitap")  # * grubu
    assert d("PerplexityBot", "/arama/yardim") and not d("PerplexityBot", "/arama/yardim/x")
    assert not d("Bingbot", "/kitap?utm_source=a") and d("Bingbot", "/kitap")
    assert d("Google-Extended", "/kitap")           # Googlebot grubu Google-Extended'a uygulanmaz
    assert d("GPTBot", "/robots.txt")


def test_evaluate_bots_advice_separates_training_from_visibility():
    paths = [{"label": "Anasayfa", "url": "https://timas.com.tr/"}, {"label": "Arama sonucu", "url": "https://timas.com.tr/arama?q=k"}]
    out = {b["agent"]: b for b in tech.evaluate_bots(ROBOTS + "\nUser-agent: OAI-SearchBot\nDisallow: /\n", paths)["bots"]}
    assert out["GPTBot"]["purpose"] == "training" and "görünürlüğü etkilemez" in out["GPTBot"]["advice"]
    assert out["OAI-SearchBot"]["blocked"] and "açılması önerilir" in out["OAI-SearchBot"]["advice"]
    assert not out["PerplexityBot"]["blocked"] and out["PerplexityBot"]["group"] == "genel (*)"


# ------------------------------------------------------------------ sitemap
INDEX = b"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://timas.com.tr/sitemap-urun.xml.gz</loc><lastmod>2026-09-20</lastmod></sitemap>
  <sitemap><loc>https://timas.com.tr/sitemap-kategori.xml</loc></sitemap>
</sitemapindex>"""
URLSET = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://timas.com.tr/kuyucakli-yusuf</loc><lastmod>2026-09-20T10:00:00+03:00</lastmod></url>
  <url><loc>https://www.timas.com.tr/icimizdeki-seytan/</loc><lastmod>2025-01-02</lastmod></url>
  <url><loc>https://timas.com.tr/tarihsiz</loc></url>
</urlset>"""


def test_parse_sitemap_index_and_gzip_urlset():
    idx = tech.parse_sitemap(INDEX)
    assert idx["kind"] == "index" and [e["loc"] for e in idx["entries"]][0].endswith(".xml.gz")
    us = tech.parse_sitemap(gzip.compress(URLSET))
    assert us["kind"] == "urlset" and len(us["entries"]) == 3 and us["entries"][2]["lastmod"] is None
    assert tech.parse_sitemap(b"<html>")["kind"] == "invalid"


def test_lastmod_and_url_keys():
    assert tech.parse_lastmod("2026-09-20T10:00:00+03:00") == datetime(2026, 9, 20, 7, 0, tzinfo=timezone.utc)
    assert tech.parse_lastmod("2025-01-02") == datetime(2025, 1, 2, tzinfo=timezone.utc)
    assert tech.parse_lastmod("dün") is None
    assert tech._key("https://www.timas.com.tr/Icimizdeki-Seytan/") == tech._key("http://timas.com.tr/icimizdeki-seytan")


# ------------------------------------------------------------------ hız
def test_parse_crux_record():
    body = {"record": {"key": {"origin": "https://timas.com.tr", "formFactor": "PHONE"}, "metrics": {
        "largest_contentful_paint": {"histogram": [{"start": 0, "end": 2500, "density": 0.61},
                                                   {"start": 2500, "end": 4000, "density": 0.25},
                                                   {"start": 4000, "density": 0.14}], "percentiles": {"p75": 3120}},
        "cumulative_layout_shift": {"histogram": [{"density": 0.9}, {"density": 0.06}, {"density": 0.04}],
                                    "percentiles": {"p75": "0.05"}},
        "interaction_to_next_paint": {"percentiles": {"p75": 540}},
        "navigation_types": {"fractions": {}}},
        "collectionPeriod": {"firstDate": {"year": 2026, "month": 8, "day": 29},
                             "lastDate": {"year": 2026, "month": 9, "day": 25}}}}
    out = speed.parse_crux(body)
    assert out["metrics"]["lcp"] == {"p75": 3120.0, "category": "ni", "good": 0.61, "ni": 0.25, "poor": 0.14}
    assert out["metrics"]["cls"]["p75"] == 0.05 and out["metrics"]["cls"]["category"] == "good"
    assert out["metrics"]["inp"]["category"] == "poor"
    assert out["period"] == {"first": "2026-08-29", "last": "2026-09-25"} and out["formFactor"] == "PHONE"


def test_parse_psi_and_thresholds():
    body = {"lighthouseResult": {"categories": {"performance": {"score": 0.43}}, "audits": {
        "largest-contentful-paint": {"numericValue": 5210.4}, "cumulative-layout-shift": {"numericValue": 0.1234},
        "total-blocking-time": {"numericValue": 880}}},
        "loadingExperience": {"metrics": {"CUMULATIVE_LAYOUT_SHIFT_SCORE": {"percentile": 12},
                                          "LARGEST_CONTENTFUL_PAINT_MS": {"percentile": 2400}}, "origin_fallback": True}}
    out = speed.parse_psi(body)
    assert out["score"] == 43 and out["lab"]["lcp"] == 5210 and out["lab"]["cls"] == 0.1234
    assert out["labCategory"]["lcp"] == "poor" and out["field"]["cls"] == {"p75": 0.12, "category": "ni"}
    assert out["field"]["lcp"]["category"] == "good" and out["fieldOrigin"] is True
    assert speed.category("inp", 200) == "good" and speed.category("inp", 201) == "ni" and speed.category("cls", 0.26) == "poor"


def test_chrome_images_are_not_page_issues():
    from semantic_bridge.seo_geo import tech

    logo, icon, cover = "https://x/logo.png", "https://x/i.svg", "https://x/kapak.jpg"
    pages = [{"noAlt": [], "emptyAlt": [logo, icon], "badName": [icon], "noSize": [logo]} for _ in range(9)]
    pages.append({"noAlt": [cover], "emptyAlt": [logo], "badName": [], "noSize": [logo, cover]})
    chrome = tech.chrome_images(pages)
    assert chrome == {logo, icon}
    imgs, flags = tech.without_chrome(pages[-1], chrome)
    assert flags == {"img_no_alt", "img_no_size"} and imgs["noSize"] == [cover] and imgs["chrome"] == [logo]
    # yeniden hesap: ham liste korunur, ikinci geçiş aynı sonucu verir
    again, flags2 = tech.without_chrome(imgs, chrome)
    assert flags2 == flags and again["noSizeAll"] == [logo, cover]
    assert tech.chrome_images(pages[:3]) == set()   # az sayfada şablon kararı verilmez
