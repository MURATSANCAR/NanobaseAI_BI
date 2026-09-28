"""Finansal denetim: yıl kopyasına göre Logo firması (sabit 411 yok) ve her rakamın sorgu bilgisi.

Veriler yapaydır; Logo'da kopyala-çalıştır kabulü `scripts/acceptance/sorgu-bilgisi/kabul_denetim_yonetim.py`.
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from semantic_bridge import financial_audit as FA
from semantic_bridge import financial_audit_kaynak as K
from semantic_bridge import provenance as P

PERIODS = [{"FIRMNR": 211, "BEGDATE": "2021-01-01", "ENDDATE": "2025-12-31"},
           {"FIRMNR": 411, "BEGDATE": "2026-01-01", "ENDDATE": "2026-12-31"}]


def test_firm_sql_rewrites_every_copy_name_to_the_year_firm():
    sql = "SELECT 1 FROM dbo.LG_411_01_EMFLINE L JOIN dbo.LG_411_EMUHACC A ON 1=1 JOIN dbo.LG_411_FAYEAR Y ON 1=1"
    out = FA.firm_sql(sql, "211")
    assert "LG_411" not in out and out.count("LG_211_") == 3
    with pytest.raises(ValueError):
        FA.firm_sql(sql, "21")


def test_resolve_firm_reads_logo_periods_not_a_constant():
    run = lambda sql: PERIODS  # noqa: E731
    assert FA.resolve_firm(run, 2025) == "211" and FA.resolve_firm(run, 2026) == "411"
    with pytest.raises(Exception):
        FA.resolve_firm(run, 2019)


def test_audit_years_from_setting(monkeypatch):
    monkeypatch.delenv("FINANCIAL_AUDIT_YEARS", raising=False)
    assert FA.audit_years() == [2026]
    monkeypatch.setenv("FINANCIAL_AUDIT_YEARS", "2026, 2025")
    assert FA.audit_years() == [2025, 2026]


class _Conn:
    def execute(self, sql, limit):
        assert "L_CAPIPERIOD" in sql
        return [], PERIODS, False


class _Runtime:
    def __init__(self):
        self.connector = _Conn()
        self.calls = []
        self.settings = type("S", (), {"connection_file": None})()

    def _physical(self, sql, period, scope=None):
        return sql

    def run_sql(self, sql, limit, period, scope=None, use_cache=True):
        self.calls.append((sql, scope))
        rec = {"lineRef": 7, "slipRef": 3, "slipNo": "F1", "date": "2025-03-01", "debit": 10.0, "credit": 0.0,
               "description": "x", "documentNo": "", "totalRows": 1}
        return {"records": [rec], "physicalSql": sql, "dbMs": 12}


def test_live_lines_use_the_year_copy_and_carry_their_sql(monkeypatch, tmp_path):
    monkeypatch.setenv("FINANCIAL_AUDIT_YEARS", "2025,2026")
    monkeypatch.setenv("FINANCIAL_AUDIT_DATA_DIR", str(tmp_path))
    rt = _Runtime()
    app = FastAPI()
    FA.register(app, lambda: rt, lambda request: None)
    r = TestClient(app).get("/api/v1/financial-audit/lines?year=2025&account=5")
    assert r.status_code == 200, r.text
    out = r.json()
    sql, scope = rt.calls[-1]
    assert scope == {"n0": "211"} and "LG_211_01_EMFLINE" in sql and "LG_411" not in sql
    assert out["firm"] == "211"
    k = out["kaynaklar"]
    assert not k.get("error") and P.uncovered_numbers(out, K.NOT_RAKAM) == [] and P.problems(out) == []
    src = k["sources"]["denetim.hareket"]
    assert "LG_211_01_EMFLINE" in src["sql"] and src["period"] == "2025 · Logo firma 211" and src["stats"]["dbMs"] == 12
    # açılmamış yıl reddedilir (kaynak kopyası mutabık değil)
    assert TestClient(app).get("/api/v1/financial-audit/lines?year=2024&account=5").status_code == 422


def _report() -> dict:
    q = lambda t: {"title": t, "sql": f"SELECT COUNT(*) AS n FROM dbo.LG_411_01_EMFLINE -- {t}", "rows": 3, "dbMs": 40,  # noqa: E731
                   "at": "2026-09-28T06:00:00"}
    queries = {k: q(k) for k in ("hesaplar", "fisDenge", "butunluk", "profil", "karsiHesap", "kdv", "belge.belgeler",
                                 "belge.belgeFis", "belge.hesapBelge", "belge.sabitKiymet", "derin.invoice", "derin.bank",
                                 "derin.invoiceTypes")}
    return {
        "year": 2026, "firm": "411", "revision": "r", "computedAt": "2026-09-28T06:00:00", "lastDate": "2026-08-17",
        "firstDate": "2026-01-01", "lineCount": 120, "debit": "100.00", "credit": "100.00", "dbMs": 900,
        "accounts": [{"accountRef": 5, "accountType": 1, "code": "100.01", "name": "Kasa", "lineCount": 12, "debit": "5",
                      "credit": "1", "balance": "4", "nullAmounts": 0, "openingLines": 1, "unexpectedSign": False}],
        "checks": [{"id": "trial-balance", "title": "Mizan", "affected": 0, "amount": "0", "formula": "Σ borç − Σ alacak",
                    "status": "passed"},
                   {"id": "slip-balance", "title": "Fiş", "affected": 2, "amount": "5", "formula": "fiş", "status": "finding"}],
        "ratios": [{"note": 2, "title": "Cari oran", "numerator": "10", "denominator": "5", "value": "2", "formula": "a/b",
                    "status": "calculated", "days": 12.5}],
        "closingGap": "0", "sourceIntegrity": {"sourceRows": 120, "missingSlip": 0, "cancelledSlip": 0},
        "profiles": [{"code": "100.01", "accountRef": 5, "foreignRows": 0, "missingInvoiceNumber": 1}],
        "pairChecks": {"x": {"id": "voucher-counterpart", "affected": 1}},
        "vatMonths": [{"month": 1, "balance": "3", "accounts": {"191": "3"}}],
        "supportingEvidence": {"documentProfiles": [{"documentType": 1, "rows": 4, "missingNumber": 0}],
                               "documentVoucherProfile": {"vouchers": 3, "multipleDocumentTypes": 0},
                               "accountDocumentProfiles": [{"code": "100", "rows": 2}],
                               "assetProfiles": [{"bookType": 1, "method": 1, "month": 3, "rows": 5, "assetCount": 2}],
                               "executed": {"belgeler": {"rows": 4, "dbMs": 3}}},
        "deepAudit": {"checks": [{"id": "invoice-unposted", "title": "Fatura", "detailKind": "invoice", "affected": 1,
                                  "tested": 50, "formula": "posted=0"}],
                      "sources": [{"id": "invoices", "records": 50, "sourceDataset": "invoice"}],
                      "datasets": {"invoiceTypes": [{"type": 8, "rows": 40, "unposted": 1}]}, "dbMs": 70,
                      "executed": {"invoice": {"rows": 1, "dbMs": 30}}},
        "coverage": {"items": [{"id": "note-2", "note": 2, "page": 3, "endPage": 4, "accountRefs": [5],
                                "components": [{"note": 2, "value": "2", "numerator": "10"},
                                               {"id": "account-scope", "accountCount": 1, "lineCount": 12},
                                               {"id": "balance-sign", "affected": 0, "accountRefs": [5]},
                                               {"id": "vat-1", "balance": "3"}]}],
                     "counts": {"calculated": 1}, "kindCounts": {"analysis": 1}},
        "queries": queries, "sql": [v["sql"] for v in queries.values()],
        "cached": True, "refresh": {"state": "ready", "refreshIntervalSeconds": 3600},
    }


def test_report_every_number_has_its_query():
    out = _report()
    k = P.ekle(out, K.for_report(out, "TIGERDB"))["kaynaklar"]
    assert P.uncovered_numbers(out, K.NOT_RAKAM) == []
    assert P.problems(out) == []
    h = k["sources"]["denetim.hesaplar"]
    assert h["sql"].startswith("USE [TIGERDB];") and h["period"] == "2026 · Logo firma 411" and h["stats"]["rows"] == 3
    # temel kontrol kendi sorgusundan; fiş dengesi ayrı sorgu
    assert k["formulas"]["kontrol:slip-balance"]["inputs"] == ["denetim.fisDenge"]
    assert k["fields"]["deepAudit.checks[]:invoice-unposted"].startswith("hesap:")
    assert k["fields"]["supportingEvidence.assetProfiles[]"] == "denetim.belge.sabitKiymet"
    assert {"ozet.bulgu", "ozet.gecen", "ozet.oran", "ozet.kapsam", "coverage.items[].components[]:vat"} <= set(k["fields"])
    json.dumps(out, default=str)


def test_old_report_without_query_ids_still_has_sources():
    out = _report()
    out.pop("queries")
    out.pop("firm")
    k = P.ekle(out, K.for_report(out, None))["kaynaklar"]
    assert P.problems(out) == [] and "denetim.hesaplar" in k["sources"]
    assert k["sources"]["denetim.hesaplar"]["period"] == "2026 · Logo firma 411"
