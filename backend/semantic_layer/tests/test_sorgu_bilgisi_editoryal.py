"""Sorgu bilgisi — editoryal önbellek parçaları, destek masası bağlamı ve kurul pazar raporu: Logo/CRM'de koşan metin
(değerleri yerinde) kayda girer; önbellekten gelen rakamın asıl okuması parça kaydıyla saklanır.
"""
from __future__ import annotations

import json

from semantic_bridge import editorial_home as EH
from semantic_bridge import provenance as P
from semantic_bridge import sorgu_izi as IZ
from semantic_bridge import support as S

CRM_SQL = "SELECT p.new_projeId AS id FROM Timas_MSCRM.dbo.new_projeBase AS p WHERE p.statecode = 0"


def test_snapshot_part_keeps_the_sql_that_built_it(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_HOME_CACHE_DIR", str(tmp_path))

    def build():
        IZ.dis("crm", CRM_SQL, rows=12, ms=40)
        return {"items": [{"n": 12}], "total": 12}

    snap = EH.EditorialHomeSnapshots(lambda: ["t1"], lambda: {"contracts": build}, sources=("editorial.py",))
    snap.refresh(force=True)
    part = snap.read()["parts"]["contracts"]
    assert part["data"]["total"] == 12
    assert part["sql"] and part["sql"][0]["sql"] == CRM_SQL and part["sql"][0]["rows"] == 12
    out = {"parts": snap.read()["parts"]}
    onceki = [x for p in out["parts"].values() for x in (p.get("sql") or [])]
    k = IZ.tam_kaynak(None, [], [], out, prefix="portal.editoryal.masam", title="Masam", text="Sözleşmeler.",
                      logo_db=None, crm_db="CRMDB", onceki=onceki)
    o = P.ekle(out, k)
    assert P.uncovered_numbers(o) == [] and P.problems(o) == []
    src = list(k.sources.values())[0]
    assert src["sql"].startswith("USE [CRMDB];") and src["stats"]["rows"] == 12


def test_support_source_reports_the_executed_text():
    class Conn:
        def close(self):
            pass

    rows = [{"Siparis": "S-1", "Adet": 3}]
    src = S.Source(lambda: Conn(), lambda: Conn(), lambda st: None)
    import semantic_bridge.field_sales as FS

    orig_runner, orig_close = FS._runner, FS._close
    FS._runner = lambda conn: (lambda sql: rows)
    FS._close = lambda conn: None
    try:
        with IZ.izle_dis() as got:
            out = src.crm(lambda run: run("SELECT s.name AS Siparis FROM Timas_MSCRM.dbo.SalesOrderBase AS s "
                                          "WHERE s.emailaddress = N'a@b.com'"))
    finally:
        FS._runner, FS._close = orig_runner, orig_close
    assert out and got and got[0]["connection"] == "crm" and got[0]["rows"] == 1
    k = P.Kaynaklar()
    ids = IZ.dis_kaydet(k, got, "destek.baglam", "Müşteri bağlamı", None, "CRMDB")
    assert ids and "N'a@b.com'" in k.sources[ids[0]]["sql"]


def test_report_sources_come_from_saved_texts():
    content = {"scenarios": {"baz": 1500}, "sorgular": [
        {"connection": "crm", "sql": CRM_SQL, "rows": 42, "ms": 800, "at": 1790000000.0},
        {"connection": "logo", "sql": "SELECT SUM(x.adet) AS adet FROM dbo.LG_411_SATIS_2026 AS x", "rows": 1, "ms": 900,
         "at": 1790000000.0}]}
    out = {"id": "r1", "status": "hazir", "content": content}
    k = IZ.tam_kaynak(None, [], content["sorgular"], out, prefix="rapor.pazar", title="Pazar raporu", text="Senaryolar.",
                      logo_db="TIGERDB", crm_db="CRMDB")
    o = P.ekle(out, k)
    assert P.uncovered_numbers(o) == [] and P.problems(o) == []
    assert {s["connection"] for s in k.sources.values()} == {"crm", "logo"}
    json.dumps(o, default=str)
