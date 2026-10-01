"""Sorgu bilgisi — M34 E-ticaret (G5 yayılımı): her rakam ucunda kaynaksız rakam yok, SQL çalışan metnin kendisi.

Uçlar TestClient ile çağrılır (bağ `P.bagla` uçta); Logo çalıştırıcısı sahte, ama gösterilen metin çalıştırıcıya giden
metnin kendisidir (yakalama). Gerçek Logo/portalda kopyala-çalıştır kabulü: `scripts/acceptance/sorgu-bilgisi/g5_eticaret.py`.
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from semantic_bridge import eticaret as E
from semantic_bridge import eticaret_kaynak as K
from semantic_bridge import eticaret_sources as src
from semantic_bridge import provenance as P
from semantic_bridge import sorgu_yakala as Y
from semantic_layer.tests.test_eticaret import T, _c, _client, _items, _p, _run
from semantic_layer.tests.test_eticaret import engine  # noqa: F401 — fixture


def _check(out: dict, ignore=K.NOT_RAKAM) -> dict:
    k = out.get("kaynaklar")
    assert k and not k.get("error"), k
    assert P.uncovered_numbers(out, ignore) == []
    assert P.problems(out) == []
    assert k["sources"]
    for s in k["sources"].values():
        assert s["sql"].strip() and P.placeholders_left(s["sql"]) == [], s
        assert s["connection"] in ("logo", "crm", "portal")
    json.dumps(out, default=str)
    return k


def _seed(engine):
    rights = {"9786050000301": {"rights": "var", "statusFlag": "cekildi", "data": {"statusLabel": "YS11 Satıştan çekildi"}}}
    items = _items([_p("30", "9786050000301", "Çekilen", price=100.0, views=100, sales=5),
                    _p("31", "9786050000318", "Stoksuz", price=100.0, views=50, sales=1)],
                   [_c("c30", "9786050000301", "Çekilen", "K30"), _c("c31", "9786050000318", "Stoksuz", "K31")],
                   stock={"K30": 5.0, "K31": 0.0}, sales={"K31": {"adet": 900.0, "ciro": 1.0}}, rights=rights)
    _run(engine, items)


def test_capture_inlines_values_and_skips_writes(engine):
    _seed(engine)
    with Y.yakala(engine) as q:
        E.list_diffs(engine, T, tur="stok")
    texts = [x["sql"] for x in q.queries]
    assert texts and all("?" not in P._STRING_OR_COMMENT.sub(" ", t) for t in texts)
    assert any("'stok'" in t and "semantic_eticaret_diffs" in t for t in texts)
    assert all(t.lstrip().upper().startswith(("SELECT", "WITH")) for t in texts)


def test_overview_diffs_item_funnel_proposals_have_sources(engine):
    _seed(engine)
    c, _ = _client(engine, {"ayse": {"ozellik:eticaret.oneri-onay"}})
    a = {"cookie": "a"}
    ov = c.get("/api/v1/eticaret/overview", headers=a).json()
    k = _check(ov)
    assert k["fields"]["gostergeler.acikFark"].startswith("hesap:")
    assert any("semantic_eticaret_items" in s["sql"] for s in k["sources"].values())
    lst = c.get("/api/v1/eticaret/diffs", headers=a).json()
    _check(lst)
    did = lst["items"][0]["id"]
    _check(c.get(f"/api/v1/eticaret/diffs/{did}", headers=a).json())
    _check(c.get("/api/v1/eticaret/items/9786050000301", headers=a).json())
    _check(c.get("/api/v1/eticaret/funnel", headers=a).json())
    _check(c.get("/api/v1/eticaret/proposals", headers=a).json())


def test_origin_is_the_night_read(engine):
    _seed(engine)
    y = Y.Yakalanan()
    y.ekle("logo", "SELECT I.CODE AS stok, 1 AS bakiye FROM dbo.LG_411_01_STLINE AS L JOIN dbo.LG_411_ITEMS AS I ON 1 = 1",
           12, 40, "TIGERDB")
    y.ekle("crm", "SELECT k.new_kitapId AS id FROM Timas_MSCRM.dbo.new_kitapBase AS k", 3, 10, "Timas_MSCRM")
    assert Y.koken_yaz(engine, T, E.KOKEN_OKUMA, y) == 2
    with Y.yakala(engine) as q:
        out = E.overview(engine, T, {})
    out = P.ekle(out, K.for_overview(engine, T, out, q))
    k = _check(out)
    items_src = [s for s in k["sources"].values() if s["connection"] == "portal" and "semantic_eticaret_items" in s["sql"]]
    assert items_src and items_src[0]["origin"]
    origin = k["sources"][items_src[0]["origin"][0]]
    assert origin["connection"] == "logo" and origin["sql"].startswith("USE [TIGERDB];")


def test_marketplace_endpoints_show_the_logo_text(engine, monkeypatch):
    _seed(engine)
    sent: list[str] = []

    def fake_runner(path, timeout=None):
        def run(sql):
            sent.append(sql)
            if "AS stok" in sql:
                return [{"stok": "K31", "ad": "Stoksuz", "satis_adet": 50, "iade_adet": 1, "ciro": 500.0, "son": date(2026, 8, 1)}]
            if "YEAR(SH.DATE_)" in sql:
                return [{"kod": "120.01", "unvan": "Kitapyurdu", "kanal": "E-TICARET", "yil": 2026, "ay": 3, "satis": 1000.0,
                         "iade": 100.0, "satis_adet": 10, "iade_adet": 1}]
            if "L_CAPIPERIOD" in sql:
                return [{"FIRMNR": 411}]
            return [{"son": date(2026, 8, 17)}]
        return run

    monkeypatch.setattr(src, "runner", fake_runner)
    monkeypatch.setattr(src, "firms_by_year", lambda run: (run("SELECT FIRMNR, BEGDATE, ENDDATE FROM L_CAPIPERIOD WHERE ACTIVE = 1"),
                                                          {2025: "211", 2026: "411"})[1])
    c, _ = _client(engine, {})
    a = {"cookie": "a"}
    m = c.get("/api/v1/eticaret/marketplaces?yil=2026", headers=a).json()
    k = _check(m)
    logo = [s for s in k["sources"].values() if s["connection"] == "logo"]
    assert logo and all(s["sql"] in sent or s["sql"].split("\n", 1)[-1] in sent for s in logo)
    assert any("LG_411_01_STLINE" in s["sql"] and "'2026-01-01'" in s["sql"] for s in logo)
    _check(c.get("/api/v1/eticaret/marketplaces/stock-risk?yil=2026", headers=a).json())
    _check(c.get("/api/v1/eticaret/marketplaces/120.01/books?yil=2026", headers=a).json())
    # Önbellekten dönen ikinci çağrı da aynı Logo metnini gösterir.
    k2 = _check(c.get("/api/v1/eticaret/marketplaces?yil=2026", headers=a).json())
    assert {s["sql"] for s in k2["sources"].values() if s["connection"] == "logo"} == {s["sql"] for s in logo}


def test_not_rakam_is_only_non_figures():
    assert not {"gostergeler", "cariler", "toplam", "items", "total", "turSayilari"} & set(K.NOT_RAKAM)
