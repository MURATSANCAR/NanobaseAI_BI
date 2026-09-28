"""Sorgu bilgisi — M35 Kampanyalar (G5 yayılımı): her rakam ucunda kaynaksız rakam yok, SQL çalışan metnin kendisi.

Uç fonksiyonları yakalama penceresinde çağrılır (uçtaki bağla aynı: `with Y.yakala(engine)` → `KK.for_*`). Gerçek
Logo/CRM/portalda kopyala-çalıştır kabulü `scripts/acceptance/sorgu-bilgisi/g5_kampanya.py`.
"""
from __future__ import annotations

import json
from datetime import date

from semantic_bridge import kampanya as K
from semantic_bridge import kampanya_kaynak as KK
from semantic_bridge import provenance as P
from semantic_bridge import sorgu_yakala as Y
from semantic_layer.tests.test_kampanya import REF, ST, T, _camp, _seed_books
from semantic_layer.tests.test_kampanya import _no_provider, engine  # noqa: F401 — fixture


def _check(out: dict) -> dict:
    k = out.get("kaynaklar")
    assert k and not k.get("error"), k
    assert P.uncovered_numbers(out, KK.NOT_RAKAM) == []
    assert P.problems(out) == []
    assert k["sources"]
    for s in k["sources"].values():
        assert s["sql"].strip() and P.placeholders_left(s["sql"]) == [], s
        assert s["connection"] in ("logo", "crm", "portal")
    json.dumps(out, default=str)
    return k


def _with(engine, fn, build, *a, **kw):
    with Y.yakala(engine) as q:
        out = fn(*a, **kw)
    return P.ekle(out, build(engine, T, out, q))


def _setup(engine):
    _seed_books(engine)
    c = _camp(engine, baslangic="2026-10-11", bitis="2026-10-20")
    K.add_items(engine, ST, T, c["id"], [{"stok": "K1"}, {"stok": "K2", "kampanyaFiyati": 60}])
    return c


def test_list_campaign_and_simulation_have_sources(engine):
    c = _setup(engine)
    lst = _with(engine, K.list_campaigns, KK.for_list, engine, T)
    k = _check(lst)
    assert any("semantic_kampanya_campaigns" in s["sql"] for s in k["sources"].values())
    camp = _with(engine, K.get_campaign, KK.for_campaign, engine, T, c["id"])
    k = _check(camp)
    assert any("semantic_kampanya_items" in s["sql"] and c["id"] in s["sql"] for s in k["sources"].values())
    sim = _with(engine, K.simulate, KK.for_campaign, engine, ST, T, c["id"], bulk=0.2, save=False)
    _check(sim)


def test_candidates_calendar_learnings_and_results(engine, monkeypatch):
    c = _setup(engine)
    monkeypatch.setattr(K, "_special_days", lambda e, t, a, b: [])
    _check(_with(engine, K.candidates, KK.for_candidates, engine, ST, T, rules="stok,dusus", ref=REF))
    cal = _with(engine, K.calendar, KK.for_calendar, engine, T, date(2026, 10, 1), date(2026, 11, 30))
    _check(cal)
    wins = K.windows(date(2026, 10, 11), date(2026, 10, 20), 14)
    rows = [{"stok": "K1", "gun": date(2026, 10, 5), "adet": 10.0, "iade": 0.0, "tutar": 500.0, "maliyet": 300.0, "maliyetliTutar": 500.0},
            {"stok": "K1", "gun": date(2026, 10, 12), "adet": 40.0, "iade": 4.0, "tutar": 1500.0, "maliyet": 1200.0, "maliyetliTutar": 1500.0}]
    K.store_results(engine, c["id"], rows, wins, date(2026, 10, 25), "logo")
    with engine.begin() as cn:
        cn.execute(K.CAMPAIGNS.update().where(K.CAMPAIGNS.c.id == c["id"]).values(durum="bitti"))
    # Sonuç tablosunu dolduran Logo sorgusu (yenileme işinde yakalanıp saklanır) asıl sorgu olarak görünür.
    y = Y.Yakalanan()
    y.ekle("logo", "SELECT I.CODE AS stok, CAST(S.DATE_ AS date) AS gun FROM dbo.LG_411_01_STLINE AS S "
                   "JOIN dbo.LG_411_ITEMS AS I ON I.LOGICALREF = S.STOCKREF WHERE S.DATE_ >= '20261001'", 2, 30, "TIGERDB")
    assert Y.koken_yaz(engine, T, K.koken_sonuc(c["id"]), y) == 1
    with Y.yakala(engine) as q:
        res = K.results(engine, ST, T, c["id"])
    res = P.ekle(res, KK.for_results(engine, T, c["id"], res, q))
    k = _check(res)
    res_src = [s for s in k["sources"].values() if "semantic_kampanya_results" in s["sql"]]
    assert res_src and res_src[0]["origin"] and k["sources"][res_src[0]["origin"][0]]["connection"] == "logo"
    K.add_learning(engine, ST, T, "ayse", c["id"], {"ozet": "İndirim satışı dört kat artırdı."})
    _check(_with(engine, K.learnings, KK.for_learnings, engine, T))


def test_overview_summary_numbers(engine):
    _setup(engine)
    with Y.yakala(engine) as q:
        out = {**K.summary(engine, T), "onayBekleyen": K.all_campaigns(engine, T, "taslak"), "yurutulen": [],
               "takvim": {"items": [], "kampanyalar": [], "cakismalar": []},
               "status": {"fiyatKaydi": K.meta_get(engine, "snapshots"), "startedAt": 1.0}}
    out = P.ekle(out, KK.for_overview(engine, T, out, q))
    _check(out)
