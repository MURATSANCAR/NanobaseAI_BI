"""Yönetim raporları (liste, Baskı Öneri): çalışan SQL (şablon değil) ve sayaçların sorgu bilgisi."""
from __future__ import annotations

from datetime import date

from semantic_bridge import management as M
from semantic_bridge import provenance as P
from semantic_bridge.management import baski_oneri as BO
from semantic_bridge.management import kaynak as K


class _Conn:
    def __init__(self):
        self.sql = []

    def execute(self, sql, limit):
        self.sql.append(sql)
        return ["stok_kodu"], [{"stok_kodu": "15201"}], False


def test_run_keeps_the_executed_text_with_codes_and_years(tmp_path, monkeypatch):
    monkeypatch.setenv("MANAGEMENT_REPORT_CACHE_DIR", str(tmp_path))
    conn = _Conn()
    r = M.Reports(lambda: {})
    r._connector = lambda name, owner="": conn  # noqa: E731
    r._sales_years_present = lambda owner="": set(range(2015, date.today().year + 1))  # noqa: E731
    out = r._run(BO, "logo_yeni_kitap_satis", {"stok_kodlari": ["15201", "15202"]}, {})
    assert out["sql"] == conn.sql[-1]  # gösterilen = çalışan
    assert P.placeholders_left(out["sql"]) == [] and "N'15201'" in out["sql"]
    assert "{satis" not in out["sql"] and "V_SatisRaporu_" in out["sql"]


def _snap():
    stats = {sid: {"rows": 10, "dbMs": 1200, "sql": f"SELECT 1 AS n -- {sid}"} for sid, *_ in BO.SOURCES}
    stats["logo_yeni_kitap_satis"]["sql"] = "SELECT * FROM X WHERE K IN ({stok_kodlari})"  # eski önbellek: gösterilmez
    cols = [{"key": "stok_kodu", "source": "crm_kitap"}, {"key": "ort_satis_hizi", "source": "hesap:Ort. satış hızı"},
            {"key": "depo_stok", "source": "logo_depo_stok"}]
    views = [{"id": "tekrar", "title": "Baskı Tekrar", "columns": cols, "rows": [["15201", 3.5, 40], ["15202", 0, 2]]},
             {"id": "tahmin", "title": "ZEKİ AI Tahminleme", "columns": [], "rows": [],
              "explain": {"sql": [{"id": "crm_kitap", "title": "Kitap kartı", "description": "", "sql": "SELECT 2"}]}}]
    return {"id": BO.REPORT_ID, "refreshIntervalSeconds": 300, "serverTime": 1.0, "updatedAt": 2.0, "durationMs": 5100,
            "data": {"views": views, "oneriLevels": BO.ONERI_LEVELS, "sourceStats": stats, "asOf": "2026-09-28"}}


def test_report_counters_and_totals_have_sources():
    out = _snap()
    k = P.ekle(out, K.for_report(BO, out, {"logo": "TIGERDB", "crm": "CRMDB"}))["kaynaklar"]
    assert P.uncovered_numbers(out, K.NOT_RAKAM) == []
    assert P.problems(out) == []
    assert "yonetim.baski-oneri.logo_yeni_kitap_satis" not in k["sources"]  # yer tutuculu eski metin atlandı
    assert k["sources"]["yonetim.baski-oneri.crm_kitap"]["sql"].startswith("USE [CRMDB];")
    ref = k["fields"]["data.views[]:tekrar"][6:]
    assert "yonetim.baski-oneri.crm_kitap" in k["formulas"][ref]["inputs"]
    assert {"toplam:tekrar", "toplam", "data.views[]:tahmin"} <= set(k["fields"])


def test_report_list_cards():
    snap = _snap()
    items = [{"id": BO.REPORT_ID, "title": BO.TITLE, "description": "", "updatedAt": 2.0, "sources": len(BO.SOURCES),
              "refreshIntervalSeconds": 300, "views": [{"id": "tekrar", "title": "Baskı Tekrar", "rows": 2}]}]
    out = {"reports": items}
    P.ekle(out, K.for_list(items, {BO.REPORT_ID: BO}, {BO.REPORT_ID: snap}, {"logo": None, "crm": None}))
    assert P.uncovered_numbers(out, K.NOT_RAKAM) == [] and P.problems(out) == []
    assert f"reports[]:{BO.REPORT_ID}" in out["kaynaklar"]["fields"]
