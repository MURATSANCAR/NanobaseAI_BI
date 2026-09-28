"""Sorgu bilgisi — soru cevabı ve `/run_sql` (genel bakış kartları, pano, planlı rapor, uyarı değeri).

Gösterilen/kopyalanan SQL köprünün Logo/CRM'de koşturduğu FİZİKSEL metindir (mantıksal metin SSMS'te aynı sonucu
vermez); iki sunuculu cevapta her parça kendi veritabanında ayrı sorgu, birleştirme hesap. Ayrıca `hesap(dis=…)`:
SQL'i olmayan rakamın kaynağı adıyla yazılır.
"""
from __future__ import annotations

import json

import pytest

from semantic_bridge import provenance as P
from semantic_bridge import soru_kaynak as SK

LOGICAL = "SELECT SUM(net_ciro) AS net FROM satis WHERE yil = 2026"
PHYSICAL = ("SELECT SUM(CASE WHEN I.[TRCODE] IN (7,8,9) THEN I.[NETTOTAL] ELSE -I.[NETTOTAL] END) AS net "
            "FROM [dbo].[LG_411_01_INVOICE] AS I WHERE I.[CANCELLED]=0 AND I.[DATE_]>='2026-01-01'")


def _answer(**over):
    a = {"id": "r1", "type": "TEXT_TO_SQL", "sql": LOGICAL, "physicalSql": PHYSICAL, "summary": "Net ciro 848,1 Mn ₺.",
         "columns": [{"name": "net", "type": "decimal"}], "records": [{"net": 848_100_000.5}], "shownRows": 1,
         "rowCount": 1, "totalRows": 1, "dbMs": 1240, "computedAt": 1790000000.0, "ageSec": 0.2, "latency_ms": 4100,
         "timings": {"compile_ms": 20, "run_sql_ms": 1300}, "repairs": 0, "semantic": {"critic": [{"score": 3}]},
         "neden": {"ok": False}, "dataEnd": None, "presentation": {"kind": "kpi", "value": 848_100_000.5},
         "comparison": None, "queryId": "q1"}
    a.update(over)
    return a


def _ok(out, ignore):
    k = out["kaynaklar"]
    assert not k.get("error"), k
    assert P.uncovered_numbers(out, ignore) == []
    assert P.problems(out) == []
    json.dumps(out, default=str)
    return k


def test_answer_shows_physical_sql_with_use_line_not_logical():
    out = P.ekle(_answer(), SK.for_answer(_answer(), "TIGERDB", "TIMAS_MSCRM"))
    k = _ok(out, SK.CEVAP_NOT_RAKAM)
    s = k["sources"]["soru"]
    assert s["connection"] == "logo" and s["database"] == "TIGERDB"
    assert s["sql"].startswith("USE [TIGERDB];\n") and "LG_411_01_INVOICE" in s["sql"]
    assert LOGICAL not in json.dumps(k)  # mantıksal metin gösterilmez
    assert s["stats"]["rows"] == 1 and s["stats"]["dbMs"] == 1240
    assert k["fields"]["records"] == "soru" and k["fields"]["summary"] == "soru"


def test_crm_answer_goes_to_crm_database():
    crm_sql = "SELECT COUNT(*) AS n FROM [timas_mscrm].[dbo].[new_projeBase] AS p WHERE p.statecode = 0"
    ans = _answer(physicalSql=crm_sql, records=[{"n": 12}])
    k = SK.for_answer(ans, "TIGERDB", "TIMAS_MSCRM").to_dict()
    assert k["sources"]["soru"]["connection"] == "crm"
    assert k["sources"]["soru"]["sql"].startswith("USE [TIMAS_MSCRM];")


def test_federated_answer_lists_each_part_on_its_own_server():
    parts = [{"name": "satis", "source": "logo", "ms": 800, "sql": PHYSICAL},
             {"name": "proje", "source": "crm", "ms": 120,
              "sql": "SELECT p.new_projeid FROM [timas_mscrm].[dbo].[new_projeBase] AS p"}]
    ans = _answer(federated=True, dbParts=parts, physicalSql='{"parts": []}')
    out = P.ekle(ans, SK.for_answer(ans, "TIGERDB", "TIMAS_MSCRM"))
    k = _ok(out, SK.CEVAP_NOT_RAKAM)
    assert k["fields"]["records"] == "hesap:soru.birlesim"
    assert {s["connection"] for s in k["sources"].values()} == {"logo", "crm"}
    assert all('"parts"' not in s["sql"] for s in k["sources"].values())


def test_not_executed_or_textual_answer():
    assert SK.for_answer({"type": "TEXT", "summary": "Ben Zeki AI"}, "A", "B") is None
    out = P.bagla(_answer(physicalSql=None), lambda: SK.for_answer(_answer(physicalSql=None), "A", "B"))
    assert out["kaynaklar"]["error"]  # sessiz geçmez: pencere nedenini yazar
    assert out["records"] == [{"net": 848_100_000.5}]  # rakam düşmez


def test_run_sql_result():
    res = {"columns": [{"name": "ay"}], "records": [{"ay": 1, "net_ciro": 10.5}], "totalRows": 1, "truncated": False,
           "physicalSql": PHYSICAL, "dbMs": 90, "cached": True, "computedAt": 1790000000.0, "ageSec": 3.0}
    out = P.ekle(dict(res), SK.for_run(res, "TIGERDB", None))
    k = _ok(out, SK.RUN_NOT_RAKAM)
    s = k["sources"]["sorgu"]
    assert "Önbellekten" in s["description"] and s["sql"].startswith("USE [TIGERDB];")


def test_external_source_formula_without_sql():
    k = P.Kaynaklar()
    ref = k.hesap("talep", "Açık talep = durumu kapanmamış talepler", dis="Destek masası talepleri, anlık okuma")
    k.alan("acik", ref)
    out = P.ekle({"acik": 4}, k)
    assert P.uncovered_numbers(out) == [] and P.problems(out) == []
    assert out["kaynaklar"]["formulas"]["talep"]["external"].startswith("Destek masası")
    with pytest.raises(P.ProvenanceError):
        P.Kaynaklar().hesap("x", "x", dis="vLLM çıktısı")
    # dış kaynak adı verilmeyen girdisiz hesap hâlâ sorun sayılır
    k2 = P.Kaynaklar()
    k2.alan("a", k2.hesap("y", "y"))
    assert P.problems(P.ekle({"a": 1}, k2)) == ["hesap:y: girdisi yok"]
