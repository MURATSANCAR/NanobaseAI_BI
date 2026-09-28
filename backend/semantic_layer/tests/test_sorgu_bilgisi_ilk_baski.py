"""M10 İlk baskı: özet, kitap tahmini, serbest tahmin ve kararların sorgu bilgisi (kaynaksız rakam yok, şablon yok)."""
from __future__ import annotations

from datetime import date

from semantic_bridge import provenance as P
from semantic_bridge.management import ilk_baski as IB
from semantic_bridge.management import ilk_baski_api as API
from semantic_bridge.management import ilk_baski_kaynak as K
from semantic_bridge.management import ilk_baski_model as M
from semantic_layer.tests.test_first_print import T, ds, engine  # noqa: F401 — fikstürler

DBS = {"logo": "TIGERDB", "crm": "CRMDB"}


def _eng(ds):  # noqa: F811
    eng = IB.Engine(ds, None, {}, [500, 1000, 2000], M.PARAMS)
    q = {"0.1": 0.5, "0.2": 0.7, "0.5": 1.0, "0.8": 1.4, "0.9": 2.0}
    eng.calib = {"6": {"hepsi": q, "ratios": {"hepsi": [0.5, 0.8, 1.0, 1.2, 2.0]}}, "12": {"hepsi": q}}
    return eng


def _data(eng):
    stats = {sid: {"rows": 3, "dbMs": 40, "sql": f"SELECT 1 AS n -- {sid}"} for sid, *_ in IB.SOURCES}
    stats["logo_aylik_kanal"].update({"sqlByYear": {"2023": "SELECT 2023 AS y", "2024": "SELECT 2024 AS y"},
                                      "rowsByYear": {"2023": 10, "2024": 8}, "msByYear": {"2023": 900, "2024": 700}})
    up = [r for r in (IB.summary_row(eng, b, L) for b, L in IB.upcoming_books(eng.ds, date(2024, 9, 1))) if r]
    return {"asOf": "2024-09-10", "dataEnd": "2024-09-05", "lastFullMonth": "2024-08",
            "counts": {"books": len(eng.ds.books), "launches": len(eng.ds.outcomes), "withEmsal": 1},
            "backtest": {"6": {"horizon": 6, "model": {"mdape": 0.3, "within25": 0.4, "n": 12}, "coverage80": 0.8}},
            "upcoming": up, "tracking": IB.tracking(eng), "sourceStats": stats, "warnings": []}


def test_summary_every_number_has_its_query(ds):  # noqa: F811
    eng = _eng(ds)
    data = _data(eng)
    out = {"status": {"updatedAt": 1.0, "refreshing": False, "durationMs": 5000, "nextRefreshAt": 2.0, "hasData": True},
           "ready": True, "meta": {k: data.get(k) for k in ("asOf", "dataEnd", "lastFullMonth", "counts")},
           "backtest": data["backtest"], "upcoming": data["upcoming"], "tracking": data["tracking"],
           "formulas": [], "notes": [],
           "sources": [{"id": sid, "rows": 3, "sql": None} for sid, *_ in IB.SOURCES], "can": {"decide": True}}
    k = P.ekle(out, K.for_summary(out, data, DBS, 1.0))["kaynaklar"]
    assert P.uncovered_numbers(out, K.NOT_RAKAM) == []
    assert P.problems(out) == []
    # Logo satışı yıl başına ayrı kayıt, satır ve süresiyle
    assert k["sources"]["ilkbaski.logo_aylik_kanal.2023"]["stats"]["rows"] == 10
    assert k["sources"]["ilkbaski.crm_kitaplar"]["sql"].startswith("USE [CRMDB];")
    assert {"kpi.yayimlanacak", "kpi.takip", "kpi.kotumser", "kpi.sapma"} <= set(k["fields"])


def test_forecasts_and_decisions_have_sources(ds, engine):  # noqa: F811
    eng = _eng(ds)
    data = _data(eng)
    for out, free in ((API.book_forecast(eng, "15201.01.0030"), False), (API.book_forecast(eng, "15201.01.0020"), False),
                      (API.free_forecast(eng, {"name": "Yeni", "pages": 180, "price": 90, "launch": "2025-03"}), True)):
        k = P.ekle(out, K.for_forecast(out, data, DBS, 1.0, free))["kaynaklar"]
        assert P.uncovered_numbers(out, K.NOT_RAKAM) == [], out.get("mode")
        assert P.problems(out) == []
        assert "horizons.6.channels[]" in k["fields"]
    API.create_decision(engine, T, "ali", {"code": "X1", "title": "Kitap", "units": 3000, "scenario": "oneri",
                                           "recommended": 3000})
    out = {"items": API.list_decisions(engine, T, "X1")}
    k = P.ekle(out, K.for_decisions(engine, API.decisions_stmt(T, "X1")))["kaynaklar"]
    assert P.uncovered_numbers(out) == [] and P.problems(out) == []
    assert "semantic_first_print_decisions" in k["sources"]["ilkbaski.kararlar"]["sql"] and "X1" in k["sources"]["ilkbaski.kararlar"]["sql"]


def test_old_snapshot_template_is_not_shown():
    data = {"sourceStats": {"logo_aylik_kanal": {"sql": "SELECT * FROM {satis:yil}", "rows": 1}}}
    k = P.Kaynaklar()
    assert K.sources(k, data, DBS, None) == {}
