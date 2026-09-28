"""M29 İlk dağılım: her rakamın sorgu bilgisi; tabloları dolduran Logo/CRM SQL'i okuma anında saklanır."""
from __future__ import annotations

from datetime import date

from semantic_bridge import distribution as D
from semantic_bridge import distribution_kaynak as K
from semantic_bridge import distribution_sources as src
from semantic_bridge import provenance as P
from semantic_layer.tests.test_distribution import T, FakeLogo, FakeSources, _approved, _seed, engine  # noqa: F401


def _check(out):
    k = out["kaynaklar"]
    assert not k.get("error"), k
    assert P.uncovered_numbers(out, K.NOT_RAKAM) == []
    assert P.problems(out) == []
    return k


def test_sources_log_every_executed_sql():
    runs = []
    S = D.Sources(lambda: (lambda sql: runs.append(sql) or [{"a": 1}]), lambda: (lambda sql: []), lambda: "Timas_MSCRM.dbo")
    S.logo_run()("SELECT 1 FROM dbo.LG_411_01_STLINE")
    S.crm_run()("SELECT 2")
    assert [(q["conn"], q["sql"], q["rows"]) for q in S.reads] == [("logo", "SELECT 1 FROM dbo.LG_411_01_STLINE", 1),
                                                                   ("crm", "SELECT 2", 0)]


def test_books_list_origin_is_the_refresh_reads(engine):  # noqa: F811
    _seed(engine)
    sql = "SELECT I.CODE AS stok_kodu FROM dbo.LG_411_01_STLINE L JOIN dbo.LG_411_ITEMS I ON I.LOGICALREF = L.STOCKREF"
    D.meta_set(engine, T, "logo", {"veriSonu": "2026-08-17", "sorgular": [{"conn": "logo", "sql": sql, "rows": 3, "dbMs": 9}]})
    out = D.list_books(engine, T)
    k = _check(P.ekle(out, K.for_books(engine, T, out, "TIGERDB", None)))
    assert k["sources"]["dagilim.yenileme.1"]["sql"].startswith("USE [TIGERDB];")
    assert k["sources"]["dagilim.meta"]["origin"] == ["dagilim.yenileme.1"]
    assert {"sayac.bekleyen", "sayac.liste"} <= set(k["fields"])


def test_plan_lines_tracking_region_alerts(engine, monkeypatch):  # noqa: F811
    monkeypatch.setattr(D, "today", lambda: date(2026, 8, 20))
    logo = FakeLogo()
    logo.track_rows = [dict(cari_kodu="120.01", hafta=1, sevk=200, fatura=200, iade=0)]
    plan, S = _approved(engine, logo)
    D.refresh_tracking(engine, T, S, D.get_plan_row(engine, T, plan["id"]))
    assert D.meta_get(engine, T, f"track:{plan['id']}")["satir"] == 1
    D.meta_set(engine, T, f"track:{plan['id']}", {"sorgular": [{"conn": "logo", "sql": "SELECT 1 AS n FROM dbo.LG_411_01_STLINE",
                                                          "rows": 1, "dbMs": 5}]})
    det = D.plan_detail(engine, T, plan["id"])
    assert "sorgular" not in det["basis"]  # SQL ekrana ayrı yetkide gider
    k = _check(P.ekle(det, K.for_plan(engine, T, plan["id"], det, None, None, None)))
    assert {"matris", "benzerler[]", "hedef", "guncelStok", "toplam"} <= set(k["fields"])
    ln = D.list_lines(engine, T, plan["id"])
    _check(P.ekle(ln, K.for_lines(engine, T, plan["id"], ln, None, None, None)))
    tr = D.tracking(engine, T, "N1")
    k = _check(P.ekle(tr, K.for_tracking(engine, T, tr, None, "TIGERDB", None)))
    assert any(s.startswith("dagilim.takip.") for s in k["sources"])  # takip okuması kayıtlı
    reg = D.my_region(engine, T, "veli")
    _check(P.ekle(reg, K.for_my_region(engine, T, reg, "veli", None, None)))
    D.evaluate_alerts(engine, T)
    al = D.alerts(engine, T)
    _check(P.ekle(al, K.for_alerts(engine, T, al, durum="acik", tur="", bmt=None, page=0)))
    ps = {"items": D.plans_of(engine, T, "N1")}
    _check(P.ekle(ps, K.for_plans(engine, T, "N1")))
