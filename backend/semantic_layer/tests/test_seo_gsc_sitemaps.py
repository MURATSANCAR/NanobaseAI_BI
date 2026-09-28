"""Search Console site haritası durumu ve zengin sonuç sorunlarının iş listesine düşmesi."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

from semantic_bridge.seo_geo import gsc_sitemaps as g
from semantic_bridge.seo_geo import worklist as w
from semantic_bridge.seo_geo.crawlbot import INSPECT

AT = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)


def test_parse_counts_are_text_in_api():
    m = g.parse_entry({"path": "https://timas.com.tr/sitemap.xml", "isSitemapsIndex": True, "errors": "3",
                       "warnings": "0", "lastDownloaded": "2026-09-27T10:00:00Z",
                       "contents": [{"type": "web", "submitted": "120"}, {"type": "image", "submitted": "30"}]})
    assert (m["errors"], m["warnings"], m["submitted"], m["isIndex"]) == (3, 0, 150, True)


def test_flags_and_summary_count_leaves_only():
    idx = g.parse_entry({"path": "i", "isSitemapsIndex": True, "errors": "5", "lastDownloaded": "2026-09-27T00:00:00Z"})
    a = g.parse_entry({"path": "a", "errors": "5", "lastDownloaded": "2026-09-27T00:00:00Z"}, parent="i")
    b = g.parse_entry({"path": "b", "warnings": "2", "lastDownloaded": "2026-09-01T00:00:00Z"}, parent="i")
    s = g.summarize([idx, a, b], AT)
    assert s["errors"] == 5 and s["warnings"] == 2  # dizinin kendi sayısı iki kez sayılmaz
    assert a["flags"] == ["hata"] and b["flags"] == ["uyari", "okunmuyor"]
    assert g.flags({"isPending": True, "lastDownloaded": None}, AT) == ["bekliyor"]


def test_deltas_against_previous_read():
    maps = [{"path": "a", "errors": 4, "warnings": 1}, {"path": "new", "errors": 0, "warnings": 0}]
    g.deltas(maps, {"a": (1, 1)})
    assert maps[0]["errorsDelta"] == 3 and maps[0]["warningsDelta"] == 0 and maps[1]["errorsDelta"] is None


def test_rich_groups_one_count_per_url_and_skip_info():
    issue = {"type": "Product snippets", "message": 'Missing field "offers"', "severity": "ERROR"}
    rows = [("u1", "p1", json.dumps({"issues": [issue, issue]})),
            ("u2", "p2", json.dumps({"issues": [issue, {"type": "x", "message": "m", "severity": "INFO"}]})),
            ("u3", "p3", None)]
    groups = w.rich_groups(rows)
    assert list(groups) == [("ERROR", "Product snippets", 'Missing field "offers"')]
    assert len(groups[("ERROR", "Product snippets", 'Missing field "offers"')]) == 2


class _Env:
    def __init__(self, eng):
        self.eng, self.tenant = eng, "t"

    def has(self, table):
        return sa.inspect(self.eng).has_table(table.name)

    def impressions_of(self, _u):
        return 0

    def sales_of(self, _p):
        return 0


def test_worklist_sources(monkeypatch):
    eng = sa.create_engine("sqlite://")
    for t in (INSPECT, g.SNAP):
        t.create(eng)
    now = AT
    rich = {"issues": [{"type": "Review snippets", "message": "Missing field \"author\"", "severity": "WARNING"}]}
    snap = {"sitemaps": [
        {"path": "https://timas.com.tr/s1.xml", "parent": None, "errors": 2, "warnings": 0, "errorsDelta": 2,
         "flags": ["hata"]},
        {"path": "https://timas.com.tr/s2.xml", "parent": None, "errors": 0, "warnings": 0, "flags": ["okunmuyor"]}]}
    with eng.begin() as c:
        c.execute(INSPECT.insert().values(tenant_id="t", url="https://timas.com.tr/k", product_id="p", kind="product",
                                          status="indexed", canonical_mismatch=False, rich_json=json.dumps(rich),
                                          inspected_at=now))
        c.execute(g.SNAP.insert().values(tenant_id="t", data_json=json.dumps(snap), saved_at=now))
    monkeypatch.setattr(w, "_sum_sales", lambda env, pids: 0.0)
    env = _Env(eng)
    r = w.src_rich_results(env)
    assert len(r) == 1 and r[0]["severity"] == "orta" and "author" in r[0]["title"]
    s = w.src_gsc_sitemaps(env)
    sev = {i["ref"].split("|")[0]: i["severity"] for i in s}
    assert sev == {"site_haritasi:hata": "kritik", "site_haritasi:okunmuyor": "orta"}


def test_obsolete_map_is_separate_and_not_summed():
    old = g.parse_entry({"path": "http://timas.com.tr/post-sitemap.xml", "errors": "1", "warnings": "11",
                         "lastDownloaded": "2020-03-20T22:33:05Z"})
    live = g.parse_entry({"path": "https://timas.com.tr/xml/sitemap/brand.xml", "warnings": "1",
                          "lastDownloaded": "2026-09-27T20:00:00Z"})
    s = g.summarize([old, live], AT)
    assert old["flags"] == ["eski"] and s["obsolete"] == 1 and s["errors"] == 0 and s["warnings"] == 1
