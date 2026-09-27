"""SEO & GEO → Google taraması (seo_geo/crawlbot.py): ağsız, saf fonksiyonlar."""
from datetime import datetime, timedelta, timezone

import pytest

from semantic_bridge.seo_geo import crawlbot as cb

URL = "https://timas.com.tr/kuyucakli-yusuf"
AT = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)


def _body(**ix):
    base = {"verdict": "PASS", "coverageState": "Submitted and indexed", "robotsTxtState": "ALLOWED",
            "indexingState": "INDEXING_ALLOWED", "lastCrawlTime": "2026-09-20T08:15:00Z", "pageFetchState": "SUCCESSFUL",
            "googleCanonical": URL, "userCanonical": URL, "crawledAs": "MOBILE",
            "referringUrls": ["https://timas.com.tr/yazar/sabahattin-ali"], "sitemap": ["https://timas.com.tr/sitemap.xml"]}
    base.update(ix)
    return {"inspectionResult": {"inspectionResultLink": "https://search.google.com/x", "indexStatusResult": base,
                                 "richResultsResult": {"verdict": "FAIL", "detectedItems": [
                                     {"richResultType": "Product snippets", "items": [
                                         {"name": "Kuyucaklı Yusuf", "issues": [
                                             {"issueMessage": "Missing field \"review\"", "severity": "WARNING"}]}]}]}}}


# ------------------------------------------------------------------ denetim cevabı
def test_parse_indexed_page():
    r = cb.parse_inspection(_body(), URL)
    assert r["status"] == "indexed"
    assert r["last_crawl"] == datetime(2026, 9, 20, 8, 15, tzinfo=timezone.utc)
    assert r["crawled_as"] == "MOBILE" and not r["canonical_mismatch"]
    assert r["rich"]["types"] == ["Product snippets"]
    assert r["rich"]["issues"][0]["severity"] == "WARNING"
    assert r["data"]["referringUrls"] and r["data"]["link"]


def test_parse_canonical_mismatch_and_missing_user_canonical():
    r = cb.parse_inspection(_body(googleCanonical="https://timas.com.tr/kuyucakli-yusuf-2",
                                  coverageState="Duplicate, Google chose different canonical than user",
                                  verdict="NEUTRAL"), URL)
    assert r["canonical_mismatch"] and r["status"] == "duplicate"
    # Kullanıcı canonical'ı yoksa denetlenen adresle karşılaştırılır; sondaki / ve büyük harf fark sayılmaz.
    assert not cb.canonical_mismatch(URL, "https://TIMAS.com.tr/kuyucakli-yusuf/", None)
    assert cb.canonical_mismatch(URL, "https://timas.com.tr/baska", None)
    assert not cb.canonical_mismatch(URL, None, "https://timas.com.tr/x")


@pytest.mark.parametrize("coverage,extra,expected", [
    ("Crawled - currently not indexed", {}, "crawled_not_indexed"),
    ("Discovered - currently not indexed", {}, "discovered_not_crawled"),
    ("Tarandı - şu anda dizine eklenmedi", {}, "crawled_not_indexed"),
    ("Keşfedildi - şu anda dizine eklenmedi", {}, "discovered_not_crawled"),
    ("URL is unknown to Google", {}, "unknown"),
    ("Excluded by ‘noindex’ tag", {"indexingState": "BLOCKED_BY_META_TAG"}, "noindex"),
    ("Blocked by robots.txt", {"robotsTxtState": "DISALLOWED"}, "robots_blocked"),
    ("Indexed, though blocked by robots.txt", {"robotsTxtState": "DISALLOWED"}, "indexed"),
    ("Not found (404)", {"pageFetchState": "NOT_FOUND"}, "not_found"),
    ("Soft 404", {"pageFetchState": "SOFT_404"}, "soft_404"),
    ("Server error (5xx)", {"pageFetchState": "SERVER_ERROR"}, "fetch_error"),
    ("Page with redirect", {}, "redirect"),
    ("Alternate page with proper canonical tag", {}, "alternate"),
    ("Indexed, not submitted in sitemap", {}, "indexed"),
])
def test_classify(coverage, extra, expected):
    r = cb.parse_inspection(_body(coverageState=coverage, verdict="NEUTRAL", **extra), URL)
    assert r["status"] == expected, coverage


def test_empty_response_is_other():
    r = cb.parse_inspection({}, URL)
    assert r["status"] == "other" and r["last_crawl"] is None and r["rich"] is None


# ------------------------------------------------------------------ gün ve kota
def test_istanbul_day_boundary():
    # 20:59 UTC = 23:59 İstanbul (aynı gün), 21:00 UTC = ertesi gün 00:00.
    assert cb.istanbul_day(datetime(2026, 9, 27, 20, 59, tzinfo=timezone.utc)) == "2026-09-27"
    assert cb.istanbul_day(datetime(2026, 9, 27, 21, 0, tzinfo=timezone.utc)) == "2026-09-28"
    assert cb.istanbul_day(datetime(2026, 9, 27, 21, 30)) == "2026-09-28"  # saat dilimsiz = UTC


def test_quota():
    assert cb.daily_limit("") == cb.DEFAULT_DAILY and cb.daily_limit("abc") == cb.DEFAULT_DAILY
    assert cb.daily_limit(" 500 ") == 500 and cb.daily_limit("-3") == 0
    assert cb.remaining(1700, 1800) == 100
    assert cb.remaining(1900, 1800) == 0
    assert cb.remaining(10, 1800, stopped="quota") == 0


# ------------------------------------------------------------------ sıra
def test_queue_priority():
    old = AT - timedelta(days=cb.RECENT_DAYS + 1)
    fresh = AT - timedelta(days=2)
    products = [{"url": "u/az", "productId": "1", "sales": 5}, {"url": "u/cok", "productId": "2", "sales": 900},
                {"url": "u/taze", "productId": "3", "sales": 5000}, {"url": "u/eski", "productId": "4", "sales": 900}]
    pages = [{"url": "p/yazar", "kind": "author"}, {"url": "home/", "kind": "home"}, {"url": "p/kat", "kind": "category"}]
    inspected = {"u/taze": fresh, "u/eski": old, "p/kat": AT - timedelta(days=1)}
    q = [t["url"] for t in cb.build_queue(products, pages, inspected, AT)]
    # 1) bakılmamış/eski ürünler satışa göre (eşit satışta hiç bakılmamış, sonra eski denetim önce),
    # 2) sayfalar (anasayfa önce), 3) yakında bakılanlar en eskiden.
    assert q == ["u/cok", "u/eski", "u/az", "home/", "p/yazar", "u/taze", "p/kat"]


def test_queue_dedup_and_skips_missing_url():
    q = cb.build_queue([{"url": "a", "productId": "1", "sales": 1}, {"url": "a", "productId": "2", "sales": 9},
                        {"url": None, "productId": "3", "sales": 99}], [{"url": "a", "kind": "author"}], {}, AT)
    assert [t["url"] for t in q] == ["a"] and q[0]["kind"] == "product"


# ------------------------------------------------------------------ özet
def _row(status, days=None, kind="product", pid="1", mismatch=False, error=None, crawled_as="MOBILE", rich=None):
    return {"status": status, "last_crawl": (AT - timedelta(days=days)) if days is not None else None, "kind": kind,
            "product_id": pid, "canonical_mismatch": mismatch, "error": error, "crawled_as": crawled_as, "rich": rich}


def test_summarize():
    rows = [_row("indexed", 3), _row("indexed", 45, pid="2"), _row("crawled_not_indexed", 10, pid="3", mismatch=True),
            _row("discovered_not_crawled", None, pid="4", crawled_as=None),
            _row("indexed", 5, kind="author", pid=None, crawled_as="DESKTOP",
                 rich={"issues": [{"message": "x"}, {"message": "y"}]}),
            _row("indexed", 1, pid="5", error="Google 500")]
    prods = {"1": {"sales": 10}, "2": {"sales": 50}, "3": {"sales": 0}, "4": {"sales": 7}, "5": {"sales": 1}}
    s = cb.summarize(rows, prods, AT)
    assert s["total"] == 6 and s["inspected"] == 5 and s["errors"] == 1
    assert s["indexed"] == 3 and s["indexedShare"] == pytest.approx(3 / 5)
    assert s["crawledNotIndexed"] == 1 and s["discoveredNotCrawled"] == 1 and s["canonicalMismatch"] == 1
    assert s["staleSellers"] == 2           # 45 gün + hiç taranmamış (satışı olan); satışsız ve hatalı sayılmaz
    assert s["crawledAs"] == {"MOBILE": 3, "DESKTOP": 1}
    assert s["richIssues"] == 2 and s["richIssuePages"] == 1
    ages = {a["label"]: a["count"] for a in s["crawlAge"]}
    assert ages["0–7 gün"] == 2 and ages["8–14 gün"] == 1 and ages["31–90 gün"] == 1 and ages["Hiç taranmamış"] == 1
    assert {b["status"]: b["count"] for b in s["byStatus"]}["error"] == 1


def test_age_bucket_edges():
    assert cb.age_bucket(None) == "Hiç taranmamış"
    assert cb.age_bucket(7) == "0–7 gün" and cb.age_bucket(8) == "8–14 gün"
    assert cb.age_bucket(30) == "15–30 gün" and cb.age_bucket(31) == "31–90 gün" and cb.age_bucket(400) == "90 günden eski"
    assert not cb.is_stale(_row("indexed", 30), AT) and cb.is_stale(_row("indexed", 31), AT)


# ------------------------------------------------------------------ kullanıcı ajanı → bot
@pytest.mark.parametrize("ua,bot", [
    ("Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 (KHTML, like Gecko) "
     "Chrome/120.0.0.0 Mobile Safari/537.36 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", "googlebot_mobile"),
    ("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", "googlebot_desktop"),
    ("Googlebot-Image/1.0", "googlebot_media"),
    ("Mozilla/5.0 (compatible; GoogleOther)", "google_other"),
    ("Mozilla/5.0 (Linux; Android 10) Mobile Safari (compatible; AdsBot-Google-Mobile)", "google_other"),
    ("Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)", "bingbot"),
    ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2; +https://openai.com/gptbot)", "gptbot"),
    ("Mozilla/5.0 (compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot)", "oai_search"),
    ("Mozilla/5.0 (compatible; ChatGPT-User/1.0; +https://openai.com/bot)", "chatgpt_user"),
    ("Mozilla/5.0 (compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)", "perplexity"),
    ("Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)", "claudebot"),
    ("Mozilla/5.0 (compatible; Claude-SearchBot/1.0)", "claude_search"),
    ("Mozilla/5.0 (Macintosh) (Applebot/0.1; +http://www.apple.com/go/applebot)", "applebot"),
    ("Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)", "yandex"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0", None),
    (None, None),
])
def test_bot_of(ua, bot):
    assert cb.bot_of(ua) == bot


def test_status_class():
    assert cb.status_class(200) == "2xx" and cb.status_class("404") == "4xx" and cb.status_class("?") == "diğer"


# ------------------------------------------------------------------ Cloudflare
def _cf(rows):
    return {"data": {"viewer": {"zones": [{"rows": rows}]}}, "errors": None}


def test_cf_parse_and_aggregate():
    g = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    gm = "Mozilla/5.0 (Linux; Android) Mobile Safari (compatible; Googlebot/2.1)"
    rows = cb.cf_parse(200, _cf([
        {"count": 120, "dimensions": {"userAgent": g, "edgeResponseStatus": 200, "verifiedBotCategory": "Search Engine Crawler"}},
        {"count": 5, "dimensions": {"userAgent": g, "edgeResponseStatus": 404, "verifiedBotCategory": ""}},
        {"count": 30, "dimensions": {"userAgent": gm, "edgeResponseStatus": 301, "verifiedBotCategory": "Search Engine Crawler"}},
        {"count": 9, "dimensions": {"userAgent": "curl/8", "edgeResponseStatus": 200}},
    ]))
    paths = cb.cf_parse(200, _cf([
        {"count": 50, "dimensions": {"userAgent": g, "clientRequestPath": "/kuyucakli-yusuf"}},
        {"count": 70, "dimensions": {"userAgent": g, "clientRequestPath": "/"}},
        {"count": 10, "dimensions": {"userAgent": gm, "clientRequestPath": "/"}},
    ]))
    out = cb.aggregate_bots(rows, paths, verified_field=True)
    assert set(out) == {"googlebot_desktop", "googlebot_mobile"}
    d = out["googlebot_desktop"]
    assert d["requests"] == 125 and d["verified"] == 120 and d["status"] == {"200": 120, "404": 5}
    assert d["topPaths"][0] == {"path": "/", "count": 70}
    assert out["googlebot_mobile"]["status"] == {"301": 30}
    # Plan doğrulanmış alan vermiyorsa sayı yok (None): ekran "kendini … olarak tanıtan" der.
    assert cb.aggregate_bots(rows, None, verified_field=False)["googlebot_desktop"]["verified"] is None


def test_aggregate_top_paths_limit_is_explicit():
    g = "Googlebot/2.1"
    paths = [{"count": i, "dimensions": {"userAgent": g, "clientRequestPath": f"/p{i}"}} for i in range(1, 8)]
    out = cb.aggregate_bots([{"count": 1, "dimensions": {"userAgent": g, "edgeResponseStatus": 200}}], paths, False, top=3)
    assert [p["path"] for p in out["googlebot_desktop"]["topPaths"]] == ["/p7", "/p6", "/p5"]


@pytest.mark.parametrize("status,body,kind", [
    (403, {"errors": [{"message": "Authentication error"}]}, "auth"),
    (200, {"data": None, "errors": [{"message": "not authorized for that account", "extensions": {"code": "authz"}}]}, "auth"),
    (200, {"data": None, "errors": [{"message": "zone does not have access to the field verifiedBotCategory"}]}, "plan"),
    (200, {"data": None, "errors": [{"message": "Cannot query field \"userAgent\" on type \"ZoneHttpRequestsAdaptiveGroupsDimensions\""}]}, "plan"),
    (200, {"data": None, "errors": [{"message": "cannot request data older than 259200s"}]}, "range"),
    (200, {"data": {"viewer": {"zones": []}}, "errors": None}, "auth"),
    (502, "bad gateway", "net"),
])
def test_cf_errors(status, body, kind):
    with pytest.raises(cb.CfError) as e:
        cb.cf_parse(status, body)
    assert e.value.kind == kind


def test_cf_filter_and_query():
    f = cb.cf_filter("2026-09-26", cb.hosts_of("https://www.timas.com.tr"))
    assert f["datetime_geq"] == "2026-09-26T00:00:00Z" and f["datetime_lt"] == "2026-09-27T00:00:00Z"
    assert f["clientRequestHTTPHost_in"] == ["timas.com.tr", "www.timas.com.tr"]
    assert {"userAgent_like": "%Googlebot%"} in f["OR"] and {"userAgent_like": "%ClaudeBot%"} in f["OR"]
    q = cb.cf_query(["userAgent", "edgeResponseStatus"])
    assert "httpRequestsAdaptiveGroups" in q and "userAgent edgeResponseStatus" in q and "limit: 10000" in q
    assert "clientRequestHTTPHost_in" not in cb.cf_filter("2026-09-26", [])


def test_every_bot_token_maps_to_a_bot():
    for t in cb.UA_TOKENS:
        assert cb.bot_of(f"Mozilla/5.0 (compatible; {t}/1.0)"), t
