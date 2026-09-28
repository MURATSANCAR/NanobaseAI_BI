"""M7 gelişim takibi ve hatırlatmalar: sadakat puanı, Logo satış katlaması ve gidişat, Zeki AI önerisinin okunması,
kişi başına sabah özeti (saat eşiği, günde bir kez, kapatma, gizli not), ısı haritasında sadakat sırası, yetki kuralları.

Sözleşme: sadakat yalnız CRM izinden ve yazılı kuraldan çıkar; iade adedi ve tutarı düşülür; son 12 ay veri sonundan
geriye sayılır; model cevabında öneri yoksa kayıt yazılmaz; özet boşsa gönderilmez, aynı gün ikinci kez gönderilmez,
kişi kapatınca gitmez, gizli notun konusu e-postaya girmez.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from semantic_bridge import access as A
from semantic_bridge import author_growth as G
from semantic_bridge import author_relations as R
from semantic_bridge import author_reminders as M
from semantic_layer.store.catalog_store import open_store

T = "t1"
GUID = "0a1b2c3d-1111-2222-3333-444455556666"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    for mod in (R, G, M):
        mod._ready.discard(id(e))
        mod.ensure(e)
    return e


def test_loyalty_score_follows_the_written_rule():
    today = date(2026, 9, 28)
    full = G.loyalty({"ilk": "2012-01-10", "son": "2026-03-01", "eser": 7, "sozlesme": 3, "aktif": 1}, today)
    assert full["parts"] == {"years": 30, "books": 25, "recent": 20, "active": 15, "returning": 10}
    assert full["score"] == 100 and full["band"] == "bagli"
    mid = G.loyalty({"ilk": "2021-09-01", "son": "2023-01-01", "eser": 2, "sozlesme": 1, "aktif": 0}, today)
    assert mid["parts"] == {"years": 15, "books": 10, "recent": 10, "active": 0, "returning": 0} and mid["band"] == "zayif"
    assert G.loyalty(None, today)["score"] == 0
    m = G.loyalty_map([{"kisi": GUID.upper(), "ilk": "2020-01-01", "son": "2026-01-01", "eser": 3, "sozlesme": 2, "aktif": 1}], today)
    assert m[GUID]["band"] == "bagli"


def test_crm_sql_is_read_only_and_does_not_shadow_aliases():
    s = "Timas_MSCRM.dbo"
    for q in (G.books_sql(s, GUID), G.contracts_sql(s, GUID), G.loyalty_sql(s, GUID), G.loyalty_sql(s)):
        assert q.startswith("SELECT") and "DELETE" not in q.upper() and "UPDATE " not in q.upper()
    assert "ya_e.new_Katilimsaglayan = r.new_kisi" in G.loyalty_sql(s)
    with pytest.raises(G.GrowthError):
        G.books_sql(s, "x'; DROP")


def test_sales_fold_subtracts_returns_and_trend_counts_back_from_data_end():
    rows = [
        {"kod": "A", "yil": 2026, "ay": 8, "tur": "Satış", "miktar": 100, "net": 1000},
        {"kod": "A", "yil": 2026, "ay": 8, "tur": "İade", "miktar": 10, "net": 100},
        {"kod": "B", "yil": 2025, "ay": 8, "tur": "Satış", "miktar": 50, "net": 400},
        {"kod": "B", "yil": 2024, "ay": 12, "tur": "Satış", "miktar": 7, "net": 70},
    ]
    f = G.fold_monthly(rows)
    assert f["months"]["2026-08"] == {"qty": 90.0, "net": 900.0, "retQty": 10.0}
    assert f["books"]["A"]["qty"] == 90.0 and f["books"]["B"]["qty"] == 57.0
    t = G.trend(f["months"], date(2026, 8, 17))
    assert t["window"] == {"from": "2025-09", "to": "2026-08", "prevFrom": "2024-09", "prevTo": "2025-08"}
    assert t["last12"]["qty"] == 90.0 and t["prev12"]["qty"] == 57.0
    assert t["changePct"] == pytest.approx(57.9, abs=0.1) and t["direction"] == "artis"
    assert [y["year"] for y in t["years"]] == [2024, 2025, 2026] and len(t["series"]) == 24
    assert G.trend({}, date(2026, 8, 1))["changePct"] is None


def test_advice_answer_is_parsed_or_refused():
    out = G.parse_advice('Tamam.\n{"ozet": "Satış düşüyor.", "oneriler": [{"baslik": "Yeni kitap görüşmesi", '
                         '"neden": "son 12 ay %-30", "ne_zaman": "bu ay"}, {"baslik": " "}], "riskler": ["Sözleşme bitiyor"]}')
    assert out["summary"] == "Satış düşüyor." and len(out["recommendations"]) == 1 and out["risks"] == ["Sözleşme bitiyor"]
    for bad in ("öneri yok", '{"ozet": "x", "oneriler": []}', "{bozuk"):
        with pytest.raises(G.GrowthError):
            G.parse_advice(bad)


def test_advice_is_stored_with_its_input(engine):
    inp = {"yazar": "Deniz Yazar", "satis": {"son12_adet": 10}}
    a = G.make_advice(engine, T, "ayse", GUID, inp, lambda m: '{"ozet": "o", "oneriler": [{"baslik": "b", "neden": "n"}]}')
    got = G.latest_advice(engine, T, GUID)
    assert got["id"] == a["id"] and got["input"] == inp and got["recommendations"][0]["title"] == "b"


def test_advice_input_gives_years_not_score_parts():
    g = {"loyalty": G.loyalty({"ilk": "2012-01-10", "son": "2026-03-01", "eser": 7, "sozlesme": 3, "aktif": 1}, date(2026, 9, 28)),
         "sales": {}, "books": [], "readers": {}}
    inp = G.advice_input("Deniz", g, {"timeline": [{"status": "yapildi", "private": True, "notes": "gizli"}]})
    assert inp["sadakat"]["birlikte_gecen_yil"] == pytest.approx(14.7, abs=0.1) and "parts" not in inp["sadakat"]
    assert inp["son_notlar"] == []      # gizli not modele gitmez


def test_growth_cache_is_reused_until_refresh(engine):
    calls = []

    def build():
        calls.append(1)
        return {"contactId": GUID, "n": len(calls)}

    assert G.cached(engine, T, GUID, build)["cached"] is False
    assert G.cached(engine, T, GUID, build)["cached"] is True and len(calls) == 1
    assert G.cached(engine, T, GUID, build, refresh=True)["n"] == 2


def _meeting(engine, card, user, **kw):
    body = {"cardId": card["id"], "channel": "telefon", "topic": kw.pop("topic", "Görüşme"), **kw}
    return R.create_meeting(engine, T, user, user, False, body)


def test_digest_and_send_rules(engine, monkeypatch):
    from semantic_bridge import alerts, prefs
    prefs._ready.discard(id(engine)) if hasattr(prefs, "_ready") else None
    monkeypatch.setattr(alerts, "smtp_settings", lambda: {"host": "x", "port": 25, "user": "", "password": "",
                                                          "sender": "zeki@timas.com.tr", "ssl": False, "starttls": False})
    monkeypatch.setattr(alerts, "_conf", lambda k, d="": "")
    card = R.create_card(engine, T, "ayse", {"name": "Deniz Yazar", "owner": "mehmet"})
    now = datetime.now(timezone.utc)
    tomorrow = (now.astimezone(R.TZ) + timedelta(days=1)).date().isoformat()
    yesterday = (now.astimezone(R.TZ) - timedelta(days=1)).date().isoformat()
    _meeting(engine, card, "ayse", status="planlandi", date=tomorrow, time="10:00", minutes=60, topic="Tanışma")
    _meeting(engine, card, "ayse", status="yapildi", date=yesterday, time="10:00", topic="Gizli ücret", private=True,
             nextStep="Teklif hazırla", nextDue=yesterday)
    d = M.digests(engine, T, now)
    assert [x["topic"] for x in d["ayse"]["randevu"]] == ["Tanışma"] and d["ayse"]["adim"][0]["late"] is True
    assert "mehmet" in d and d["mehmet"]["randevu"] and not d["mehmet"]["adim"]    # gizli notun adımı sorumluya gitmez
    sent = []
    directory = lambda: {"ayse": {"email": "ayse@timas.com.tr", "name": "Ayşe"}, "mehmet": {"email": "", "name": "Mehmet"}}  # noqa: E731
    late = now.astimezone(R.TZ).replace(hour=23, minute=0)
    r = M.run_due(engine, T, directory, now=late, send=lambda cfg, to, subj, text: sent.append((to, subj, text)))
    assert r["users"]["ayse"].startswith("gönderildi") and r["users"]["mehmet"] == "rehberde e-posta yok"
    assert len(sent) == 1 and "Tanışma" in sent[0][2] and "Teklif hazırla" in sent[0][2]
    again = M.run_due(engine, T, directory, now=late, send=lambda *a: sent.append(a))
    assert again["users"]["ayse"] == "zaten gönderildi" and len(sent) == 1
    early = M.run_due(engine, T, directory, now=late.replace(hour=6), send=lambda *a: sent.append(a))
    assert "skipped" in early and len(sent) == 1
    prefs.put(engine, T, M.PREF_DS, "ayse", M.PREF_KEY, False)
    assert M.enabled_for(engine, T, "ayse") is False and M.enabled_for(engine, T, "mehmet") is True


def test_private_topic_never_reaches_a_non_participant(engine):
    card = R.create_card(engine, T, "ayse", {"name": "Aday", "owner": "mehmet"})
    tomorrow = (datetime.now(R.TZ) + timedelta(days=1)).date().isoformat()
    _meeting(engine, card, "ayse", status="planlandi", date=tomorrow, time="11:00", minutes=30, topic="Gizli konu", private=True)
    d = M.digests(engine, T)
    assert d["ayse"]["randevu"][0]["topic"] == "Gizli konu" and d["mehmet"]["randevu"][0]["topic"] == "Gizli görüşme"
    subject, text = M.render("Mehmet", d["mehmet"], "", datetime.now(R.TZ).date())
    assert "Gizli konu" not in text and "Gizli görüşme" in text


def test_heatmap_orders_by_loyalty(engine):
    other = "9a1b2c3d-1111-2222-3333-444455556666"

    def fetch_all(sql):
        if "UNION ALL" in sql:
            return []
        return [{"ContactId": GUID, "FullName": "Bağlı Yazar", "sozlesme": 1, "en_yakin_bitis": None},
                {"ContactId": other, "FullName": "Yeni Yazar", "sozlesme": 1, "en_yakin_bitis": None}]

    loy = {GUID: {"score": 90, "band": "bagli"}, other: {"score": 20, "band": "zayif"}}
    top = R.heatmap("Timas_MSCRM.dbo", fetch_all, engine, T, "ayse", order="sadik", loyalty=lambda: loy)
    assert [r["name"] for r in top["items"]] == ["Bağlı Yazar", "Yeni Yazar"] and top["items"][0]["loyalty"]["score"] == 90
    weak = R.heatmap("Timas_MSCRM.dbo", fetch_all, engine, T, "ayse", order="zayif", loyalty=lambda: loy)
    assert [r["name"] for r in weak["items"]] == ["Yeni Yazar", "Bağlı Yazar"]

    def broken():
        raise RuntimeError("CRM kapalı")

    assert R.heatmap("Timas_MSCRM.dbo", fetch_all, engine, T, "ayse", loyalty=broken)["items"][0]["loyalty"] is None


def test_access_rules_for_the_new_endpoints():
    assert A.rule_for("/api/v1/editorial/authors/reminders/run-due") == A.SYSTEM
    assert "sayfa:yazar-iliskileri" in A.rule_for("/api/v1/editorial/authors/growth/x")
    assert A.features_for("POST", "/api/v1/editorial/authors/advice/x") == ["ozellik:yazar-iliski.oneri"]
    assert A.features_for("GET", "/api/v1/editorial/authors/advice/x") == []
    assert A.features_for("PUT", "/api/v1/editorial/authors/reminders/me") == []
    assert "ozellik:yazar-iliski.oneri" in A.all_keys() - A.explicit_keys()
