"""Unit tests for budget phase-2 helpers (import parse, match discover, share encode)."""

from __future__ import annotations

from nanobase_api.budget_import import parse_month_column, parse_budget_file
from nanobase_api.budget_match import discover_plan_source, discover_spend_source
from nanobase_api.budget_ops import decode_budget_pack_resource_id, encode_budget_pack_resource_id


def test_parse_month_column_aliases():
    assert parse_month_column("A1") == 1
    assert parse_month_column("Ay 12") == 12
    assert parse_month_column("Month 3") == 3
    assert parse_month_column("junk") is None


def test_parse_csv_headers_tr():
    raw = (
        "Kalem adı,Mali yıl,Senaryo,Bütçe türü,Maliyet merkezi,Planlanan,Para birimi\n"
        "Cloud,2026,base,OPEX,IT,1000,TRY\n"
    ).encode("utf-8")
    parsed = parse_budget_file("budget.csv", raw)
    rows = parsed["envelopes"]
    assert len(rows) == 1
    assert rows[0]["name"]
    assert "allocated" in rows[0]


def test_encode_decode_budget_pack_resource_id():
    rid = encode_budget_pack_resource_id(
        2026, scenario="optimistic", reporting_currency="USD", locale="tr"
    )
    assert rid == "2026:optimistic:USD:tr"
    parsed = decode_budget_pack_resource_id(rid)
    assert parsed["fiscal_year"] == 2026
    assert parsed["scenario"] == "optimistic"
    assert parsed["reporting_currency"] == "USD"
    assert parsed["locale"] == "tr"
    assert decode_budget_pack_resource_id("2025")["fiscal_year"] == 2025


def test_discover_plan_and_spend_sources():
    schema = {
        "tables": [
            {
                "name": "butce_planlari",
                "full_name": "butce_planlari",
                "columns": [
                    {"name": "tur"},
                    {"name": "planlanan_tutar"},
                    {"name": "kalem_adi"},
                    {"name": "butce_kodu"},
                    {"name": "departman_kod"},
                    {"name": "mali_yil"},
                ],
            },
            {
                "name": "alis_faturalari",
                "full_name": "alis_faturalari",
                "columns": [
                    {"name": "genel_toplam"},
                    {"name": "fatura_tarihi"},
                    {"name": "butce_kodu"},
                    {"name": "departman_kod"},
                ],
            },
            {
                "name": "faturalar",
                "full_name": "faturalar",
                "columns": [{"name": "tutar"}, {"name": "tarih"}],
            },
        ]
    }
    plan = discover_plan_source(schema)
    spend = discover_spend_source(schema)
    assert plan is not None
    assert plan["table_name"] == "butce_planlari"
    assert plan["columns"]["amount"] == "planlanan_tutar"
    assert spend is not None
    assert spend["table_name"] == "alis_faturalari"
