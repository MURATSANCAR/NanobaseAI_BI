"""SEO & GEO → izleme ve haftalık rapor (seo_geo/watch.py): dedektörler düz veriyle, tekilleştirme ve kenar bildirimi
bellek içi SQLite ile, hafta sınırları İstanbul saatiyle."""
from datetime import date, datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from semantic_bridge.seo_geo import tech, watch

UTC = timezone.utc


def series(values, start=date(2026, 8, 1)):
    return [(start + timedelta(days=i), float(v)) for i, v in enumerate(values)]


def alternating(n):
    return [95 if i % 2 == 0 else 105 for i in range(n)]


# ------------------------------------------------------------------ sağlam istatistik
def test_robust_z_uses_median_and_mad():
    ref = alternating(28)                        # medyan 100, MAD 5
    assert watch.robust_z(70, ref) == pytest.approx(0.6745 * -30 / 5)
    assert watch.robust_z(100, ref) == 0


def test_robust_z_flat_series_falls_back():
    assert watch.robust_z(100, [100] * 20) == 0
    assert watch.robust_z(50, [100] * 20) == float("-inf")
    ref = [100] * 19 + [200]                     # MAD 0 → ortalama mutlak sapma
    assert watch.robust_z(90, ref) == pytest.approx(-10 / (1.253314 * 5))


def test_fill_series_fills_missing_days_with_zero():
    s = watch.fill_series([("2026-09-03", 7), ("2026-09-01", 5)])
    assert s == [(date(2026, 9, 1), 5.0), (date(2026, 9, 2), 0.0), (date(2026, 9, 3), 7.0)]


# ------------------------------------------------------------------ tıklama düşüşü ve tek gün sapması
def test_drop_last_week_vs_previous_28_days():
    evs = watch.detect_clicks(series(alternating(28) + [70] * 7))
    drop = [e for e in evs if e["key"] == "gsc:drop"]
    assert len(drop) == 1 and drop[0]["severity"] == "yüksek"
    assert drop[0]["data"]["change"] == pytest.approx(-0.3)


def test_drop_twice_the_threshold_is_critical():
    evs = watch.detect_clicks(series(alternating(28) + [50] * 7))
    assert [e["severity"] for e in evs if e["key"] == "gsc:drop"] == ["kritik"]


def test_small_dip_is_not_an_event():
    assert watch.detect_clicks(series(alternating(28) + [90] * 7)) == []


def test_short_history_is_not_compared():
    assert watch.detect_clicks(series([100] * 10 + [0] * 3)) == []       # 14 günden kısa geçmiş


def test_single_day_anomaly_on_own_series():
    vals = alternating(40)
    vals[-1] = 20
    evs = watch.detect_clicks(series(vals))
    assert len(evs) == 1
    e = evs[0]
    day = date(2026, 8, 1) + timedelta(days=39)
    assert e["key"] == f"gsc:day:{day.isoformat()}"
    assert e["severity"] == "yüksek"                # z ≈ −10,8 ≤ −7


def test_mild_anomaly_is_medium():
    vals = alternating(40)
    vals[-1] = 70                                    # z ≈ −4,05
    evs = watch.detect_clicks(series(vals))
    assert [e["severity"] for e in evs] == ["orta"]


# ------------------------------------------------------------------ düzey karşılaştırması: 404/5xx, sitemap
def test_level_detector():
    assert watch.level_detector(5, None, rising=True) == (False, 5)
    assert watch.level_detector(7, 5, rising=True) == (True, 5)
    assert watch.level_detector(4, 5, rising=True) == (False, 4)
    assert watch.level_detector(850, 1000, rising=False, pct=0.1) == (True, 1000)
    assert watch.level_detector(950, 1000, rising=False, pct=0.1) == (False, 950)


def test_tech_errors_rise_and_settle():
    evs, st = watch.detect_tech({"not_found": 3, "server_error": 0}, {})
    assert evs == [] and st["ref"] == {"not_found": 3, "server_error": 0}
    evs, st = watch.detect_tech({"not_found": 5, "server_error": 0}, st)
    assert [(e["key"], e["severity"]) for e in evs] == [("tech:not_found", "yüksek")]
    assert st["ref"]["not_found"] == 3
    evs, st = watch.detect_tech({"not_found": 5, "server_error": 2}, st)
    assert {e["key"]: e["severity"] for e in evs} == {"tech:not_found": "yüksek", "tech:server_error": "kritik"}
    evs, st = watch.detect_tech({"not_found": 3, "server_error": 0}, st)
    assert evs == [] and st["ref"] == {"not_found": 3, "server_error": 0}


def test_sitemap_errors_and_url_drop():
    snap = {"partial": False, "totalUrls": 1000, "sitemaps": [
        {"url": "https://t/sitemap.xml", "parent": None, "status": 200, "kind": "index", "error": None},
        {"url": "https://t/s2.xml", "parent": "https://t/sitemap.xml", "status": 404, "kind": None, "error": "404 döndü"}]}
    evs, st = watch.detect_sitemaps(snap, {})
    assert [(e["key"], e["severity"]) for e in evs] == [("sitemap:err:https://t/s2.xml", "yüksek")]
    assert st["urls"] == 1000
    ok = {"partial": False, "totalUrls": 850, "sitemaps": [snap["sitemaps"][0]]}
    evs, st = watch.detect_sitemaps(ok, st)
    assert [e["key"] for e in evs] == ["sitemap:drop"] and st["urls"] == 1000
    evs, st = watch.detect_sitemaps({**ok, "totalUrls": 950}, st)
    assert evs == [] and st["urls"] == 950
    evs, st2 = watch.detect_sitemaps({**ok, "totalUrls": 10, "partial": True}, st)
    assert evs == [] and st2 == st                   # yarım okuma karşılaştırılmaz


def test_top_level_sitemap_missing_is_critical():
    snap = {"partial": False, "totalUrls": 0,
            "sitemaps": [{"url": "https://t/sitemap.xml", "parent": None, "status": 404, "error": "404 döndü"}]}
    evs, _ = watch.detect_sitemaps(snap, {})
    assert [e["severity"] for e in evs] == ["kritik"]


# ------------------------------------------------------------------ robots.txt
PATHS = [{"label": "Anasayfa", "url": "https://timas.com.tr/"}, {"label": "Ürün", "url": "https://timas.com.tr/kuyucakli-yusuf"}]


def robots_snap(text, status=200):
    return {"status": status, "text": text, **tech.evaluate_bots(text, PATHS)}


def test_robots_first_read_only_records_baseline():
    evs, st = watch.detect_robots(robots_snap("User-agent: *\nDisallow: /arama\n"), {})
    assert evs == []
    assert "Googlebot" in st["everAllowed"] and "OAI-SearchBot" in st["everAllowed"]
    assert "GPTBot" not in st["everAllowed"]          # eğitim botu izlenmez


def test_robots_change_and_newly_blocked_search_bot():
    _, st = watch.detect_robots(robots_snap("User-agent: *\nDisallow: /arama\n"), {})
    text2 = "User-agent: *\nDisallow: /arama\n\nUser-agent: OAI-SearchBot\nDisallow: /\n\nUser-agent: GPTBot\nDisallow: /\n"
    evs, st = watch.detect_robots(robots_snap(text2), st)
    by = {e["key"].split(":")[1]: e for e in evs}
    assert set(by) == {"text", "block"}
    assert by["text"]["hold"] is True and by["text"]["severity"] == "orta"
    assert "Disallow: /" in by["text"]["data"]["added"]
    assert by["block"]["key"] == "robots:block:OAI-SearchBot" and by["block"]["severity"] == "yüksek"
    # aynı metin: değişiklik olayı yok, kapalı bot olayı sürer
    evs, st = watch.detect_robots(robots_snap(text2), st)
    assert [e["key"] for e in evs] == ["robots:block:OAI-SearchBot"]


def test_blocking_googlebot_is_critical():
    _, st = watch.detect_robots(robots_snap("User-agent: *\nAllow: /\n"), {})
    evs, _ = watch.detect_robots(robots_snap("User-agent: Googlebot\nDisallow: /\n"), st)
    assert {e["key"]: e["severity"] for e in evs}["robots:block:Googlebot"] == "kritik"


def test_bot_blocked_from_the_start_is_not_an_event():
    text = "User-agent: PerplexityBot\nDisallow: /\n"
    _, st = watch.detect_robots(robots_snap(text), {})
    evs, _ = watch.detect_robots(robots_snap(text), st)
    assert evs == []


def test_unreachable_robots_is_not_a_change():
    _, st = watch.detect_robots(robots_snap("User-agent: *\nDisallow: /arama\n"), {})
    evs, st2 = watch.detect_robots({"status": None, "text": "", "bots": []}, st)
    assert evs == [] and st2 == st
    evs, st3 = watch.detect_robots({"status": 503, "text": "", "bots": []}, st)
    assert [e["key"] for e in evs] == ["robots:5xx"] and st3 == st


# ------------------------------------------------------------------ yapay zekâ cevapları
def geo_row(rid, day, mentioned=False, cited=False, q="q1", engine="gemini", ok=True):
    return {"id": rid, "question_id": q, "engine": engine, "asked_at": datetime(2026, 9, day, 3, tzinfo=UTC),
            "ok": ok, "mentioned": mentioned, "cited": cited}


def test_geo_lost_mention():
    rows = [geo_row("r1", 1, mentioned=True), geo_row("r2", 8)]
    evs = watch.detect_geo(rows, {"q1": "Osmanlı tarihi için hangi kitaplar?"})
    assert [(e["key"], e["severity"]) for e in evs] == [("geo:q1:gemini:r2", "orta")]


def test_geo_lost_citation_is_high_and_key_is_stable():
    rows = [geo_row("r1", 1, mentioned=True, cited=True), geo_row("r2", 8), geo_row("r3", 15),
            geo_row("r4", 20, mentioned=True, ok=False)]      # başarısız ölçüm sayılmaz
    evs = watch.detect_geo(rows, {"q1": "soru"})
    assert [(e["key"], e["severity"]) for e in evs] == [("geo:q1:gemini:r2", "yüksek")]


def test_geo_no_event_when_mentioned_again_or_never_or_deleted():
    assert watch.detect_geo([geo_row("r1", 1, mentioned=True), geo_row("r2", 8), geo_row("r3", 15, mentioned=True)],
                            {"q1": "soru"}) == []
    assert watch.detect_geo([geo_row("r1", 1), geo_row("r2", 8)], {"q1": "soru"}) == []
    assert watch.detect_geo([geo_row("r1", 1, mentioned=True), geo_row("r2", 8)], {}) == []


def test_geo_engines_are_separate():
    rows = [geo_row("a1", 1, mentioned=True, engine="gemini"), geo_row("a2", 8, mentioned=True, engine="gemini"),
            geo_row("b1", 1, mentioned=True, engine="openai"), geo_row("b2", 8, engine="openai")]
    evs = watch.detect_geo(rows, {"q1": "soru"}, {"openai": "ChatGPT (OpenAI)"})
    assert [e["key"] for e in evs] == ["geo:q1:openai:b2"]
    assert evs[0]["title"].startswith("ChatGPT (OpenAI):")


# ------------------------------------------------------------------ CRM ve hız
def test_crm_new_flags_after_baseline():
    known = [{"ean": "9786050000001", "flag": "cekildi", "name": "Eski", "product_id": "1"}]
    evs, st = watch.detect_crm(known, {})
    assert evs == [] and st["baseline"] == ["9786050000001:cekildi"]
    new = known + [{"ean": "9786050000002", "flag": "bizim_degil", "name": "Yeni", "product_id": "2"}]
    evs, st = watch.detect_crm(new, st)
    assert [e["key"] for e in evs] == ["crm:9786050000002:bizim_degil"]
    assert evs[0]["link"].endswith("urun=2")


def test_speed_crossing_into_poor():
    evs, st = watch.detect_speed({"phone": {"lcp": "poor", "inp": "good", "cls": "ni"}},
                                 {"phone": {"lcp": "ni", "inp": "good", "cls": "ni"}}, {})
    assert [e["key"] for e in evs] == ["speed:phone:lcp"] and st["crossed"] == ["phone:lcp"]
    evs, st = watch.detect_speed({"phone": {"lcp": "poor"}}, {"phone": {"lcp": "poor"}}, st)
    assert [e["key"] for e in evs] == ["speed:phone:lcp"]            # geçişten sonra kötü kaldıkça açık
    evs, st = watch.detect_speed({"phone": {"lcp": "good"}}, {"phone": {"lcp": "poor"}}, st)
    assert evs == [] and st["crossed"] == []


def test_speed_poor_from_the_start_is_not_a_crossing():
    assert watch.detect_speed({"desktop": {"cls": "poor"}}, {"desktop": {"cls": "poor"}}, {})[0] == []
    assert watch.detect_speed({"desktop": {"cls": "poor"}}, {}, {})[0] == []


# ------------------------------------------------------------------ tekilleştirme ve kenar bildirimi
AT = datetime(2026, 9, 27, 2, 0, tzinfo=UTC)


def ev(key, kind="gsc", severity="orta", hold=False):
    return watch.event(kind, severity, f"olay {key}", "ayrıntı", "/seo-geo/izleme", key, hold=hold)


def test_reconcile_new_seen_reopen_resolve_hold_and_not_ran():
    existing = {
        "a": {"kind": "gsc", "resolved_at": None, "last_seen": AT - timedelta(days=1), "hold": False},
        "b": {"kind": "gsc", "resolved_at": AT - timedelta(days=3), "last_seen": AT - timedelta(days=4), "hold": False},
        "c": {"kind": "tech", "resolved_at": None, "last_seen": AT - timedelta(days=1), "hold": False},
        "d": {"kind": "robots", "resolved_at": None, "last_seen": AT - timedelta(days=2), "hold": True},
        "e": {"kind": "robots", "resolved_at": None, "last_seen": AT - timedelta(days=10), "hold": True},
        "f": {"kind": "geo", "resolved_at": None, "last_seen": AT - timedelta(days=1), "hold": False},
    }
    ops = watch.reconcile(existing, [ev("a"), ev("b"), ev("n"), ev("n")], {"gsc", "tech", "robots"}, AT)
    got = {k: op for op, k, _ in ops}
    assert got == {"a": "seen", "b": "reopen", "n": "new", "c": "resolve", "e": "resolve"}
    assert len(ops) == 5                              # aynı anahtar bir kez; d bekler, f'nin dedektörü koşmadı


def test_pending_orders_by_severity_and_skips_notified_or_resolved():
    rows = [{"id": "1", "severity": "orta", "resolved_at": None, "notified_at": None, "first_seen": "1"},
            {"id": "2", "severity": "kritik", "resolved_at": None, "notified_at": None, "first_seen": "2"},
            {"id": "3", "severity": "kritik", "resolved_at": None, "notified_at": AT, "first_seen": "0"},
            {"id": "4", "severity": "yüksek", "resolved_at": AT, "notified_at": None, "first_seen": "0"}]
    assert [r["id"] for r in watch.pending(rows)] == ["2", "1"]


class _Seo:
    def __init__(self, engine, conf):
        self._engine, self._conf = engine, conf
        self.nightly = []

    def engine(self):
        return self._engine

    def tenant(self):
        return "t"

    def conf(self, key):
        return self._conf.get(key, "")


def test_edge_notification_waits_for_smtp_and_fires_once(monkeypatch):
    eng = sa.create_engine("sqlite://")
    w = watch.Watch(_Seo(eng, {"SEO_ALERT_RECIPIENTS": "seo@timas.com.tr", "ALERT_LINK": "http://192.168.0.55/timas/"}))
    sent: list[tuple[list[str], str, str]] = []
    result = {"v": "no_smtp"}

    def fake_send(to, subject, text, html_body=None):
        if result["v"] == "sent":
            sent.append((to, subject, text))
        return result["v"]

    monkeypatch.setattr(watch, "send_mail", fake_send)
    a = ev("gsc:drop", severity="yüksek")

    assert w.apply([a], {"gsc"})["new"] == 1
    assert w.notify() == "no_smtp"                    # ayar yok: bekler
    result["v"] = "sent"
    assert w.notify() == "sent" and len(sent) == 1    # sonraki tur gönderir
    assert sent[0][0] == ["seo@timas.com.tr"]
    assert "http://192.168.0.55/timas/seo-geo/izleme" in sent[0][2]

    assert w.apply([a], {"gsc"})["seen"] == 1
    assert w.notify() == "nothing" and len(sent) == 1  # sürmesi yeni bildirim değil

    assert w.apply([], {"tech"})["resolve"] == 0      # dedektörü koşmadı: açık kalır
    assert w.apply([], {"gsc"})["resolve"] == 1
    assert w.apply([a], {"gsc"})["reopen"] == 1
    assert w.notify() == "sent" and len(sent) == 2     # kapanıp yeniden açılan yeniden bildirilir

    with eng.connect() as c:
        rows = c.execute(sa.select(watch.EVENTS)).mappings().all()
    assert len(rows) == 1 and rows[0]["resolved_at"] is None and rows[0]["notify_result"] == "sent"


def test_no_recipient_keeps_events_pending(monkeypatch):
    eng = sa.create_engine("sqlite://")
    w = watch.Watch(_Seo(eng, {}))
    monkeypatch.setattr(watch, "send_mail", lambda to, *a, **k: "no_recipient" if not to else "sent")
    w.apply([ev("x")], {"gsc"})
    assert w.notify() == "no_recipient"
    with eng.connect() as c:
        assert c.execute(sa.select(watch.EVENTS.c.notified_at)).scalar() is None


def test_state_roundtrip():
    w = watch.Watch(_Seo(sa.create_engine("sqlite://"), {}))
    assert w.get_state("tech") == {}
    w.put_state("tech", {"ref": {"not_found": 3}})
    w.put_state("tech", {"ref": {"not_found": 4}})
    assert w.get_state("tech") == {"ref": {"not_found": 4}}


# ------------------------------------------------------------------ haftalık rapor: İstanbul hafta sınırları
def test_week_bounds_monday_after_midnight_istanbul():
    at = datetime(2026, 9, 27, 22, 30, tzinfo=UTC)    # İstanbul: 28.09 Pazartesi 01:30
    assert watch.week_bounds(at) == (date(2026, 9, 21), date(2026, 9, 27))
    assert watch.is_report_day(at, 1)


def test_week_bounds_sunday_night_week_not_finished():
    at = datetime(2026, 9, 27, 20, 0, tzinfo=UTC)     # İstanbul: 27.09 Pazar 23:00
    assert watch.week_bounds(at) == (date(2026, 9, 14), date(2026, 9, 20))
    assert not watch.is_report_day(at, 1) and watch.is_report_day(at, 7)


def test_local_range_is_istanbul_midnight_in_utc():
    a, b = watch.local_range_utc(date(2026, 9, 21), date(2026, 9, 27))
    assert a == datetime(2026, 9, 20, 21, 0, tzinfo=UTC)
    assert b == datetime(2026, 9, 27, 21, 0, tzinfo=UTC)


def test_report_day_setting():
    assert watch.report_day("") == 1
    assert watch.report_day("3") == 3
    assert watch.report_day("9") == 1
    assert watch.report_day("pazartesi") == 1


def test_compare_windows_last_7_available_days():
    s = series([10] * 7 + [12] * 7)
    imps = {d: 100.0 for d, _ in s}
    out = watch.compare_windows(s, imps)
    assert out["current"]["clicks"] == 84 and out["previous"]["clicks"] == 70
    assert out["clicksPct"] == pytest.approx(0.2) and out["impressionsPct"] == 0
    assert watch.compare_windows(s[:10], imps) is None


def test_query_movers():
    prev = [{"keys": ["a"], "clicks": 10}, {"keys": ["b"], "clicks": 5}]
    cur = [{"keys": ["a"], "clicks": 4}, {"keys": ["c"], "clicks": 7}]
    m = watch.query_movers(prev, cur)
    assert [(x["query"], x["delta"]) for x in m["gainers"]] == [("c", 7)]
    assert [(x["query"], x["delta"]) for x in m["losers"]] == [("a", -6), ("b", -5)]
    m1 = watch.query_movers(prev, cur, top=1)
    assert [x["query"] for x in m1["losers"]] == ["a"] and m1["losersTotal"] == 2


def test_report_html_escapes_values():
    summary = {"week": {"start": "2026-09-21", "end": "2026-09-27"},
               "google": {"available": False, "reason": "yok"},
               "queries": {"available": True, "top": 10, "gainersTotal": 1, "losersTotal": 0,
                           "gainers": [{"query": "<script>x</script>", "clicks": 5, "prevClicks": 1, "delta": 4}], "losers": []},
               "proposals": {"approvedThisWeek": 2, "pending": 5}, "crm": {"available": False},
               "tech": {"available": False}, "geo": {"engines": []}, "alerts": {"open": 0, "items": []}}
    subject, text, body = watch.render_report(summary, "http://h/timas")
    assert "21.09.2026–27.09.2026" in subject
    assert "<script>" not in body and "&lt;script&gt;" in body
    assert "http://h/timas/seo-geo/izleme?sekme=rapor" in text


def test_recipients_and_portal_root():
    assert watch.recipients("a@x.com; b@y.org, bad  A@x.com") == ["a@x.com", "b@y.org"]
    assert watch.portal_root("http://192.168.0.55/timas/uyarilar") == "http://192.168.0.55/timas"
    assert watch.portal_root("https://bi.example.com/x") == "https://bi.example.com"
    assert watch.portal_root("") == ""
