"""SEO & GEO → Bing Webmaster okuması ve IndexNow (semantic_bridge/seo_geo/bing.py): saf yardımcılar."""
import logging

from semantic_bridge.seo_geo import bing


# ------------------------------------------------------------------ Bing ayrıştırma

def test_parse_date_with_and_without_offset():
    assert bing.parse_date("/Date(1316156400000-0700)/") == "2011-09-16"
    assert bing.parse_date("/Date(1316156400000)/") == "2011-09-16"
    assert bing.parse_date("\\/Date(1316156400000+0300)\\/") == "2011-09-16"
    assert bing.parse_date("2026-09-20T00:00:00") == "2026-09-20"
    assert bing.parse_date(None) is None
    assert bing.parse_date("dün") is None


def test_unwrap_d_and_type_fields():
    body = {"d": [{"__type": "QueryStats:#Microsoft.Bing.Webmaster.Api", "Query": "kitap", "Clicks": 3}]}
    assert bing.unwrap(body) == [{"Query": "kitap", "Clicks": 3}]
    assert bing.unwrap({"d": {"__type": "x", "DailyQuota": 10, "MonthlyQuota": 300}}) == {"DailyQuota": 10, "MonthlyQuota": 300}
    assert bing.unwrap({"d": None}) is None
    # Sarmalsız cevap da okunur
    assert bing.unwrap([{"Query": "a"}]) == [{"Query": "a"}]


def _q(query, date_ms, clicks, imp, pos):
    return {"__type": "QueryStats", "Query": query, "Date": f"/Date({date_ms})/", "Clicks": clicks,
            "Impressions": imp, "AvgImpressionPosition": pos, "AvgClickPosition": -1}


DAY = 86_400_000
T0 = 1_788_480_000_000  # 2026-09-04 UTC


def test_stat_rows_and_aggregate_weighted_position_and_period():
    raw = {"d": [_q("Sefiller", T0, 2, 10, 4), _q("sefiller", T0 + 7 * DAY, 3, 30, 8),
                 _q("eski", T0 - 60 * DAY, 100, 100, 1), _q("yok", T0, 0, 5, -1), _q("", T0, 1, 1, 1)]}
    rows = bing.stat_rows(raw)
    assert len(rows) == 4 and rows[-1]["position"] is None
    agg, since, end = bing.aggregate(rows, days=28)
    assert end == "2026-09-11" and since == "2026-08-15"
    by = {r["key"].lower(): r for r in agg}
    assert "eski" not in by                                   # dönem dışı
    s = by["sefiller"]
    assert (s["clicks"], s["impressions"]) == (5, 40)
    assert s["position"] == 7.0                               # (4*10 + 8*30) / 40
    assert by["yok"]["position"] is None


def test_daily_and_totals_previous_period():
    raw = {"d": [{"Date": f"/Date({T0 + i * DAY})/", "Clicks": 1, "Impressions": 10} for i in range(56)]}
    daily = bing.daily_rows(raw)
    t = bing.totals(daily, days=28)
    assert (t["clicks"], t["impressions"], t["prevClicks"]) == (28, 280, 28)
    assert bing.totals([])["clicks"] == 0


def test_crawl_issue_flags():
    assert bing.issue_labels(4 | 16) == ["4xx hata", "robots.txt engelli"]
    assert bing.issue_labels(0) == []
    rows = bing.issue_rows({"d": [{"Url": "https://timas.com.tr/x", "Issues": 8, "HttpCode": 500, "InLinks": 2}, {"Url": ""}]})
    assert rows == [{"url": "https://timas.com.tr/x", "httpCode": 500, "issues": ["5xx hata"], "inLinks": 2}]


def test_compare_flags_much_worse_bing_and_counts_only_google():
    google = [{"keys": ["Sefiller"], "clicks": 50, "impressions": 900, "ctr": 0.05, "position": 2.0},
              {"keys": ["küçük prens"], "clicks": 10, "impressions": 300, "ctr": 0.03, "position": 3.0},
              {"keys": ["yalnız google"], "clicks": 1, "impressions": 20, "ctr": 0.05, "position": 5.0}]
    bing_rows = [{"key": "sefiller", "clicks": 1, "impressions": 40, "ctr": 0.02, "position": 11.0},
                 {"key": "KÜÇÜK PRENS", "clicks": 3, "impressions": 30, "ctr": 0.1, "position": 4.0}]
    out = bing.compare(google, bing_rows, gap=5)
    assert out["onlyGoogle"] == 1 and out["worse"] == 1
    first = out["items"][0]
    assert first["query"] == "Sefiller" and first["gap"] == 9.0 and first["worse"] is True
    assert out["items"][1]["worse"] is False


def test_norm_query_turkish_case():
    assert bing.norm_query("  İSTANBUL   Kitapları ") == "istanbul kitapları"
    assert bing.norm_query("IŞIK") == "ışık"


def test_api_key_is_masked_in_httpx_log():
    rec = logging.LogRecord("httpx", logging.INFO, __file__, 1, 'HTTP Request: GET %s "HTTP/1.1 200 OK"',
                            ("https://ssl.bing.com/webmaster/api.svc/json/GetQueryStats?siteUrl=x&apikey=SECRET123",), None)
    bing._Redact().filter(rec)
    assert "SECRET123" not in rec.getMessage() and "apikey=***" in rec.getMessage()


# ------------------------------------------------------------------ IndexNow

def test_key_validation():
    assert bing.valid_key("a1b2c3d4")
    assert bing.valid_key("abc-DEF-0123456789")
    assert bing.valid_key("x" * 128)
    assert not bing.valid_key("short7")
    assert not bing.valid_key("x" * 129)
    assert not bing.valid_key("has space1")
    assert not bing.valid_key("with_underscore")
    assert not bing.valid_key("")


def test_key_file_url_and_body_match():
    assert bing.key_file_url("https://timas.com.tr/", "abcd1234") == "https://timas.com.tr/abcd1234.txt"
    assert bing.key_matches("﻿abcd1234\r\n", "abcd1234")
    assert not bing.key_matches("<html>abcd1234</html>", "abcd1234")
    assert not bing.key_matches("", "abcd1234")


def test_fingerprint_changes_only_on_seo_fields():
    p = {"ProductName": "Sefiller", "SeoTitle": "Sefiller | Timaş", "SellingPrice": "250", "StatViews": 10}
    fp = bing.fingerprint(p)
    assert bing.fingerprint({**p, "StatViews": 999}) == fp          # görüntülenme sayısı SEO'yu değiştirmez
    assert bing.fingerprint({**p, "SellingPrice": "275"}) != fp
    assert bing.fingerprint({**p, "SeoTitle": "Sefiller"}) != fp
    assert bing.fingerprint(dict(reversed(list(p.items())))) == fp  # alan sırası önemsiz


def test_diff_state_new_changed_gone():
    old = {"1": "a", "2": "b", "3": "c", "4": bing.GONE}
    current = {"1": ("a", "u1"), "2": ("B", "u2"), "5": ("e", "u5"), "4": ("d", "u4")}
    d = bing.diff_state(old, current)
    assert d == {"new": ["5"], "changed": ["2", "4"], "gone": ["3"]}
    # Zaten "gone" olan tekrar kuyruğa girmez
    assert bing.diff_state({"9": bing.GONE}, {})["gone"] == []


def test_batches_split_at_protocol_limit():
    urls = [f"https://timas.com.tr/k{i}" for i in range(25_001)]
    parts = bing.batches(urls)
    assert [len(p) for p in parts] == [10_000, 10_000, 5_001]
    assert sum(parts, []) == urls
    assert bing.batches([]) == []


def test_same_host_filters_foreign_and_duplicates():
    urls = ["https://timas.com.tr/a", "https://www.timas.com.tr/b", "https://timas.com.tr/a", "", "https://TIMAS.com.tr/c"]
    assert bing.same_host(urls, "timas.com.tr") == ["https://timas.com.tr/a", "https://TIMAS.com.tr/c"]


def test_product_url():
    assert bing.product_url({"SeoLink": "sefiller"}, "https://timas.com.tr/") == "https://timas.com.tr/sefiller"
    assert bing.product_url({"Url": "https://timas.com.tr/x"}, "https://timas.com.tr") == "https://timas.com.tr/x"
    assert bing.product_url({}, "https://timas.com.tr") is None
