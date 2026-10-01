"""Yandex Webmaster: ayrıştırma, site seçimi, Google karşılaştırması, hata metni."""
from __future__ import annotations

import httpx
import pytest

from semantic_bridge.seo_geo import yandex as y

_REAL_CLIENT = httpx.Client


def test_query_rows_sorted_and_position():
    raw = {"count": 2, "queries": [
        {"query_text": "timaş yayınları", "indicators": {"TOTAL_SHOWS": 100.0, "TOTAL_CLICKS": 10.0, "AVG_SHOW_POSITION": 2.34}},
        {"query_text": "kitap", "indicators": {"TOTAL_SHOWS": 50.0, "TOTAL_CLICKS": 20.0, "AVG_SHOW_POSITION": 0}},
        {"query_text": " ", "indicators": {}},
    ]}
    rows = y.query_rows(raw)
    assert [r["key"] for r in rows] == ["kitap", "timaş yayınları"]
    assert rows[0]["position"] is None and rows[0]["ctr"] == 0.4
    assert rows[1]["position"] == 2.3


def test_series_merges_indicators_by_day():
    raw = {"indicators": {
        "TOTAL_SHOWS": [{"date": "2026-09-02T00:00:00.000+03:00", "value": 5}, {"date": "2026-09-01T00:00:00.000+03:00", "value": 3}],
        "TOTAL_CLICKS": [{"date": "2026-09-01T00:00:00.000+03:00", "value": 1}],
    }}
    assert y.series(raw, {"TOTAL_SHOWS": "impressions", "TOTAL_CLICKS": "clicks"}) == [
        {"date": "2026-09-01", "impressions": 3, "clicks": 1},
        {"date": "2026-09-02", "impressions": 5, "clicks": 0},
    ]


def test_problem_rows_only_present_ordered_by_severity():
    raw = {"problems": {
        "NO_REGIONS": {"severity": "RECOMMENDATION", "state": "PRESENT", "last_state_update": "2026-09-30T10:00:00,000+0300"},
        "SOFT_404": {"severity": "POSSIBLE_PROBLEM", "state": "ABSENT"},
        "SLOW_AVG_RESPONSE_TIME": {"severity": "CRITICAL", "state": "PRESENT"},
        "NEW_UNKNOWN": {"severity": "FATAL", "state": "PRESENT"},
    }}
    rows = y.problem_rows(raw)
    assert [r["code"] for r in rows] == ["NEW_UNKNOWN", "SLOW_AVG_RESPONSE_TIME", "NO_REGIONS"]
    assert rows[0]["label"] == "NEW_UNKNOWN" and rows[2]["since"] == "2026-09-30"


def test_pick_host_prefers_verified_https_and_ignores_www():
    hosts = [
        {"host_id": "http:timas.com.tr:80", "ascii_host_url": "http://timas.com.tr/", "verified": True},
        {"host_id": "https:www.timas.com.tr:443", "ascii_host_url": "https://www.timas.com.tr/", "verified": False},
        {"host_id": "https:timas.com.tr:443", "ascii_host_url": "https://timas.com.tr/", "verified": True},
        {"host_id": "https:baska.com:443", "ascii_host_url": "https://baska.com/", "verified": True},
    ]
    assert y.pick_host(hosts, "https://timas.com.tr")["host_id"] == "https:timas.com.tr:443"
    assert y.pick_host(hosts, "https://yok.com") is None


def test_compare_and_totals():
    google = [{"keys": ["Kitap"], "clicks": 3, "impressions": 30, "position": 2.0},
              {"keys": ["yalnız google"], "clicks": 1, "impressions": 5, "position": 4.0}]
    yandex = [{"key": "kitap", "clicks": 1, "impressions": 9, "position": 9.0}]
    out = y.compare(google, yandex)
    assert out["onlyGoogle"] == 1 and out["worse"] == 1 and out["items"][0]["gap"] == 7.0
    daily = [{"date": f"2026-09-{d:02d}", "clicks": 1, "impressions": 2} for d in range(1, 31)]
    t = y.totals(daily, days=10)
    assert (t["clicks"], t["prevClicks"], t["start"]) == (10, 10, "2026-09-21")


def test_call_maps_errors_and_masks_token(monkeypatch):
    def fake(status, body):
        def handler(request):
            assert request.headers["Authorization"] == "OAuth sir"
            return httpx.Response(status, json=body)
        monkeypatch.setattr(y.httpx, "Client", lambda **kw: _REAL_CLIENT(transport=httpx.MockTransport(handler), **kw))

    fake(401, {"error_code": "INVALID_OAUTH_TOKEN"})
    with pytest.raises(y.YandexError, match="jetonu geçersiz"):
        y.yandex_call("/user", "sir")
    fake(404, {"error_code": "HOST_NOT_INDEXED"})
    with pytest.raises(y.YandexError, match="henüz veri"):
        y.yandex_call("/user/1/hosts/x/summary", "sir")
    fake(500, {"error_message": "boom sir"})
    with pytest.raises(y.YandexError) as e:
        y.yandex_call("/user", "sir")
    assert "sir" not in str(e.value).replace("OAuth", "")
