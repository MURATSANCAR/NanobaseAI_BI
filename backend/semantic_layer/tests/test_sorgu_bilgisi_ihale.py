"""M33 İhale: her rakamın sorgu bilgisi. Stok/fiyatın asıl SQL'i eşleştirme anında çalışan metindir."""
from __future__ import annotations

from semantic_bridge import provenance as P
from semantic_bridge import tenders as T
from semantic_bridge import tenders_kaynak as K
from semantic_bridge import tenders_sources as src
from semantic_layer.tests.test_tenders import TN, _enrich, _files, _ready_tender, engine  # noqa: F401 — fikstürler


def _check(out):
    k = out["kaynaklar"]
    assert not k.get("error"), k
    assert P.uncovered_numbers(out, K.NOT_RAKAM) == []
    assert P.problems(out) == []
    return k


def test_logged_runner_keeps_executed_text():
    sink: list = []
    run = src.logged("logo", lambda sql: [{"a": 1}, {"a": 2}], sink)
    assert run("SELECT 1") == [{"a": 1}, {"a": 2}]
    assert sink[0]["sql"] == "SELECT 1" and sink[0]["rows"] == 2 and sink[0]["conn"] == "logo"


def test_detail_items_have_the_match_time_logo_sql(engine):  # noqa: F811
    t = _ready_tender(engine)
    sql = src.stock_sql("411", ["15201.01.0001", "15201.01.0002"])
    T.record_reads(engine, t["id"], "ayse", [{"conn": "logo", "sql": sql, "rows": 2, "dbMs": 30, "at": "2026-09-28T10:00:00"}])
    d = T.detail(engine, TN, t["id"])
    k = _check(P.ekle(d, K.for_detail(engine, TN, t["id"], d, "TIGERDB", None)))
    stock = k["sources"]["ihale.okuma.1"]
    assert stock["sql"].startswith("USE [TIGERDB];") and "LG_411_01_STLINE" in stock["sql"] and "'15201.01.0001'" in stock["sql"]
    assert "ihale.okuma.1" in k["sources"]["ihale.okumaIsleri"]["origin"]
    assert k["sources"]["ihale.kalemler"]["origin"] == ["ihale.okumaIsleri"]
    assert {"kalemler[]", "toplamlar", "uygunlukPuani", "kararOzeti", "fiyatOrani"} <= set(k["fields"])


def test_list_calendar_results_documents_checklist(engine):  # noqa: F811
    t = _ready_tender(engine)
    lst = T.list_tenders(engine, TN, durum="acik")
    k = _check(P.ekle(lst, K.for_list(engine, TN, dict(durum="acik", il="", kurum_turu="", son=""))))
    assert {"sayac.yediGun", "sayac.onayBekleyen"} <= set(k["fields"])
    for out, build in ((T.calendar(engine, TN, 90), lambda o: K.for_calendar(engine, TN, o)),
                       (T.results(engine, TN), lambda o: K.for_results(engine, TN, o)),
                       (T.documents(engine, TN), lambda o: K.for_documents(engine, TN, o)),
                       (T.checklist(engine, TN, t["id"]), lambda o: K.for_checklist(engine, TN, t["id"]))):
        _check(P.ekle(out, build(out)))


def test_public_sales_uses_the_stored_reads():
    reads: list = []
    logo = src.logged("logo", lambda sql: [{"FIRMNR": 411, "BEGDATE": "2026-01-01", "ENDDATE": "2026-12-31"}]
                      if "L_CAPIPERIOD" in sql else [{"ref": 7, "kod": "K1", "unvan": "Okul", "il": "İstanbul", "kanal": "KURUM",
                                                      "ciro": 100.0, "adet": 4, "fatura": 1}], reads)
    crm = src.logged("crm", lambda sql: [] if "IN (2,3,4)" not in sql else [{"rol": 2, "sayi": 3}], reads)
    out = src.read_public_sales(logo, crm, "Timas_MSCRM.dbo", 2026)
    assert len(out["sorgular"]) >= 3 and any("LG_411_01_STLINE" in q["sql"] for q in out["sorgular"])
    view = {**out, "toplamCiro": 100.0, "toplamAdet": 4.0, "cariSayisi": 1, "kaynakCiro": {"crm": 0.0, "kanal": 100.0, "ikisi": 0.0},
            "iller": [{"il": "İstanbul", "ciro": 100.0, "adet": 4.0, "cari": 1}]}
    k = _check(P.ekle(view, K.for_public_sales(view, "TIGERDB", "CRMDB")))
    assert any(s["connection"] == "crm" and s["sql"].startswith("USE [CRMDB];") for s in k["sources"].values())
