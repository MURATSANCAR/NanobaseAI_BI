"""SEMANTIC_FIRMS: a Logo server that keeps several companies' books in one database.

The period rows below are the shape of the production Logo (192.168.0.25, 2026-09-29): TİMAŞ's years sit next to
another company's (413, 212), a consolidation firm (311, 021) and a test firm (999). "The highest firm number that
covers a year" then answers 2026 with the test firm — unless the installation says which firms are its own.
"""
from __future__ import annotations

import os
from datetime import datetime

import pytest

from semantic_layer.firm_scope import firm_in_scope, included_firms

TIMAS = "015,016,105,115,171,181,191,201,211,411"

PERIODS = [  # FIRMNR, BEGDATE, ENDDATE (ACTIVE = 1)
    (15, "2015-01-01", "2015-12-31"), (105, "2015-01-01", "2015-12-31"),
    (21, "2021-01-01", "2025-12-31"), (211, "2021-01-01", "2025-12-31"), (212, "2021-01-01", "2025-12-31"),
    (996, "2021-01-01", "2025-12-31"),
    (311, "2026-01-01", "2026-12-31"), (411, "2026-01-01", "2026-12-31"), (413, "2026-01-01", "2026-12-31"),
    (999, "2026-01-01", "2026-12-31"),
]


@pytest.fixture
def env():
    saved = {k: os.environ.get(k) for k in ("SEMANTIC_FIRMS", "SEMANTIC_EXCLUDE_CONTEXT")}
    yield os.environ
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _budget_run(sql):
    assert "L_CAPIPERIOD" in sql
    return [{"FIRMNR": f, "BEGDATE": datetime.fromisoformat(b), "ENDDATE": datetime.fromisoformat(e)}
            for f, b, e in PERIODS]


def _rows():
    return [{"firmnr": f, "begdate": datetime.fromisoformat(b), "enddate": datetime.fromisoformat(e)}
            for f, b, e in PERIODS]


def test_without_the_list_the_test_firm_wins_2026(env):
    """The failure the setting exists for: unset, the rule is unchanged and a shared server answers wrongly."""
    from semantic_bridge.budget_sources import firms_by_year

    env.pop("SEMANTIC_FIRMS", None)
    env.pop("SEMANTIC_EXCLUDE_CONTEXT", None)
    got = firms_by_year(_budget_run)
    assert got[2026] == "999" and got[2023] == "996"


def test_the_company_s_own_firms_hold_every_year(env):
    from semantic_bridge.budget_sources import firms_by_year
    from semantic_bridge.events_sources import firms_by_year as events_firms
    from semantic_bridge.school_visits_sources import firms_by_year as school_firms

    env["SEMANTIC_FIRMS"] = TIMAS
    env.pop("SEMANTIC_EXCLUDE_CONTEXT", None)          # default 015,016: 2015 is 105, not 015
    want = {2015: "105", 2021: "211", 2022: "211", 2023: "211", 2024: "211", 2025: "211", 2026: "411"}
    assert firms_by_year(_budget_run) == want
    assert events_firms(_rows()) == want
    assert school_firms(_rows()) == want


def test_firm_codes_are_read_however_they_are_spelled(env):
    env["SEMANTIC_FIRMS"] = " 015, 411 ,x"
    env["SEMANTIC_EXCLUDE_CONTEXT"] = "015"
    assert included_firms() == {15, 411}
    assert firm_in_scope("411") and firm_in_scope(411)
    assert not firm_in_scope("015"), "an excluded duplicate year stays out even when it is the company's"
    assert not firm_in_scope("413") and not firm_in_scope(None) and not firm_in_scope("")


def test_the_catalog_scan_leaves_other_companies_tables_out(env):
    """Scanned, LG_413_01_INVOICE would be one more "copy" of the invoice table for the runtime to union."""
    from semantic_layer.profiler.profiler import Profiler

    class _Conn:
        dialect, default_schema = "tsql", "dbo"
        quote_l = quote_r = '"'

        def list_tables(self, schema, like=None):
            return [("dbo", n) for n in ("LG_411_01_INVOICE", "LG_413_01_INVOICE", "LG_999_ITEMS",
                                         "LG_XT1001_411", "LG_XT1001_413", "L_CAPIFIRM", "V_SatisRaporu_2026",
                                         "EOS_DAGITIM_MALIYET_211", "EOS_DAGITIM_MALIYET_019",
                                         "NY_KITAP_TELIF_021", "AA_CARI_EKSTRE_320")]
        def columns(self, schema, table): return [{"name": "ID", "data_type": "int"}]
        def primary_keys(self, schema, table): return ["ID"]
        def foreign_keys(self, schema): return []
        def row_count(self, schema, table): return 5
        def row_counts(self, schema): return {}
        def table_comments(self, schema): return {}
        def column_comments(self, schema): return {}
        def sample_rows(self, schema, table, limit=20): return []
        def indexes(self, schema): return {}
        def top_values(self, *a, **k): return []

    env["SEMANTIC_FIRMS"] = TIMAS
    env.pop("SEMANTIC_EXCLUDE_CONTEXT", None)
    names = {p.table_name for p in Profiler(_Conn()).profile("d", "dbo")}
    assert names == {"LG_411_01_INVOICE", "LG_XT1001_411", "L_CAPIFIRM", "V_SatisRaporu_2026",
                     "EOS_DAGITIM_MALIYET_211", "NY_KITAP_TELIF_021", "AA_CARI_EKSTRE_320"}, names


def test_a_number_is_a_firm_only_where_the_name_says_so(env):
    """Canlı katalogdan (2026-09-29): hesap kodu (320 satıcılar, 710 direkt ilk madde) ve kısa yıl (021) taşıyan
    rapor tabloları şirketin kendisinindir; aynı ad kalıbı TİMAŞ firmasıyla da varsa sayı firma yeridir."""
    from semantic_layer.firm_scope import foreign_tables

    env["SEMANTIC_FIRMS"] = TIMAS
    names = ["LG_411_ITEMS", "LG_212_ITEMS", "LG_999_SYSLOG", "EOS_URETIM_FISI_211", "EOS_URETIM_FISI_203",
             "AA_CARI_EKSTRE_320", "AA_CARI_EKSTRE_120", "EOS_YR_KASA_710", "NY_GIDERLER_021_01", "L_TABLELAYS_411",
             "L_TABLELAYS_413", "V_SatisRaporu_2026"]
    assert foreign_tables(names) == {"LG_212_ITEMS", "LG_999_SYSLOG", "EOS_URETIM_FISI_203", "L_TABLELAYS_413"}
    env.pop("SEMANTIC_FIRMS")
    assert foreign_tables(names) == set(), "ayar yoksa hiçbir tablo yabancı sayılmaz"


def test_deleting_profiles_takes_their_coverage_with_them():
    from datetime import datetime, timezone

    import sqlalchemy as sa

    from semantic_layer.models import SchemaProfile
    from semantic_layer.store import schema as S
    from semantic_layer.store.catalog_store import open_store

    st = open_store("sqlite://")
    now = datetime.now(timezone.utc)
    for n in ("LG_411_01_INVOICE", "LG_413_01_INVOICE"):
        st.upsert_profile(SchemaProfile(datasource_id="logo", table_name=n, table_pattern="LG_{n0}_{n1}_INVOICE",
                                        entity="INVOICE", schema_name="dbo", columns=[], scanned_at=now))
        with st.engine.begin() as c:
            c.execute(S.sl_coverage.insert().values(id=n, tenant_id="t", datasource_id="logo", table_name=n,
                                                    entity="INVOICE", declared_from="2026-01-01", declared_to="2027-01-01",
                                                    status="declared", updated_at=now))
    assert st.delete_profiles("logo", ["LG_413_01_INVOICE"]) == 1
    assert [p.table_name for p in st.list_profiles("logo")] == ["LG_411_01_INVOICE"]
    with st.engine.connect() as c:
        assert [r[0] for r in c.execute(sa.select(S.sl_coverage.c.table_name))] == ["LG_411_01_INVOICE"]
    assert st.delete_profiles("logo", []) == 0
