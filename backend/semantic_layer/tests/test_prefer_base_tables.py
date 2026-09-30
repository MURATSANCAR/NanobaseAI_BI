"""Çıplak Logo adı görünüme verilmişken asıl tablonun kolonlarıyla okunursa asıl tablo kastedilmiştir (B019, 2026-09-29)."""
from __future__ import annotations

from semantic_layer.models import ColumnProfile, SchemaProfile
from semantic_layer.runtime.critic import prefer_base_tables, review


def _p(table, entity, cols):
    return SchemaProfile(datasource_id="d", table_name=table, table_pattern=table, entity=entity, schema_name="dbo",
                         columns=[ColumnProfile(name=c, data_type="int") for c in cols], row_count=10)


VIEW = _p("LV_191_01_CLFLINE", "CLFLINE", ["CLIENTREF", "DATE_", "TOTAL"])
BASE = _p("LG_411_01_CLFLINE", "LG_CLFLINE", ["LOGICALREF", "CLIENTREF", "DATE_", "AMOUNT", "SIGN", "CANCELLED", "TRCODE"])
PROFILES = [VIEW, BASE]


def test_columns_only_the_ledger_has_point_the_bare_name_at_it():
    sql = "SELECT SUM(CASE WHEN l.SIGN = 0 THEN l.AMOUNT ELSE -l.AMOUNT END) FROM CLFLINE AS l WHERE l.CANCELLED = 0"
    out = prefer_base_tables(sql, PROFILES)
    assert "LG_CLFLINE" in out
    assert not [f for f in review(out, PROFILES, "tsql") if f.kind == "UNKNOWN_COLUMN"]
    assert [f for f in review(sql, PROFILES, "tsql") if f.kind == "UNKNOWN_COLUMN"], "önceki hâl: görünümde kolon yok diye ret"


def test_a_statement_that_reads_the_views_own_columns_keeps_the_view():
    sql = "SELECT l.CLIENTREF, SUM(l.TOTAL) FROM CLFLINE l GROUP BY l.CLIENTREF"
    assert prefer_base_tables(sql, PROFILES) == sql


def test_a_column_neither_has_is_left_for_the_reviewer_to_refuse():
    sql = "SELECT SUM(l.NOPE) FROM CLFLINE l"
    assert prefer_base_tables(sql, PROFILES) == sql


def test_unreadable_sql_is_returned_unchanged():
    assert prefer_base_tables("SELEC FROM", PROFILES) == "SELEC FROM"
