"""The critic reads a query for the ways it can return the wrong number."""
from __future__ import annotations

from semantic_layer.models import ColumnProfile, SchemaProfile
from semantic_layer.runtime.critic import review


def _t(entity, name, cols, pk="LOGICALREF", rels=()):
    return SchemaProfile(datasource_id="d", table_name=name, table_pattern=name, entity=entity, schema_name="dbo",
                         columns=[ColumnProfile(name=n, data_type=dt, is_primary_key=(n == pk)) for n, dt in cols],
                         primary_key=[pk], relationships=list(rels))


STLINE = _t("STLINE", "LG_411_01_STLINE", [("LOGICALREF", "int"), ("STOCKREF", "int"), ("TOTAL", "decimal(18,2)"), ("SPECODE", "nvarchar(17)")],
            rels=[{"column": "STOCKREF", "ref_entity": "ITEMS", "ref_column": "LOGICALREF"}])
ITEMS = _t("ITEMS", "LG_411_ITEMS", [("LOGICALREF", "int"), ("CODE", "nvarchar(25)"), ("PRICE", "float")])
P = [STLINE, ITEMS]


def test_a_sum_on_the_many_side_of_a_join_is_fine():
    sql = "SELECT i.CODE, SUM(s.TOTAL) FROM dbo.LG_411_01_STLINE s JOIN dbo.LG_411_ITEMS i ON s.STOCKREF = i.LOGICALREF GROUP BY i.CODE"
    assert [f.kind for f in review(sql, P)] == []


def test_a_sum_on_the_keyed_side_is_inflated_once_per_matching_row():
    """The item price is joined onto every sales line of that item and summed once per line."""
    sql = "SELECT i.CODE, SUM(i.PRICE) FROM dbo.LG_411_01_STLINE s JOIN dbo.LG_411_ITEMS i ON s.STOCKREF = i.LOGICALREF GROUP BY i.CODE"
    f = review(sql, P)
    assert f and f[0].kind == "FANOUT" and f[0].severity == "block"
    assert "ITEMS" in f[0].message


def test_count_star_over_a_fan_out_is_inflated_but_count_distinct_is_not():
    base = "FROM dbo.LG_411_01_STLINE s JOIN dbo.LG_411_ITEMS i ON s.STOCKREF = i.LOGICALREF"
    assert any(f.kind == "FANOUT" for f in review(f"SELECT COUNT(*) {base}", P))
    assert not review(f"SELECT COUNT(DISTINCT i.LOGICALREF) {base}", P)


def test_a_sum_over_a_code_column_is_not_a_number():
    f = review("SELECT SUM(s.SPECODE) FROM dbo.LG_411_01_STLINE s", P)
    assert f and f[0].kind == "NON_NUMERIC" and "SPECODE" in f[0].message


def test_a_column_the_table_does_not_have():
    f = review("SELECT s.NETTOTAL FROM dbo.LG_411_01_STLINE s", P)
    assert [x.kind for x in f] == ["UNKNOWN_COLUMN"]


def test_a_join_the_catalog_knows_nothing_about_is_only_a_warning_and_only_when_the_graph_exists():
    # STLINE has relationships recorded, so a join on a column it does not link through is suspect
    sql = "SELECT SUM(s.TOTAL) FROM dbo.LG_411_01_STLINE s JOIN dbo.LG_411_ITEMS i ON s.SPECODE = i.CODE"
    f = review(sql, P)
    assert any(x.kind == "UNKNOWN_JOIN" and x.severity == "warn" for x in f)
    # with no relationships anywhere the graph is still being filled: say nothing
    bare = [_t("STLINE", "LG_411_01_STLINE", [("LOGICALREF", "int"), ("SPECODE", "nvarchar(17)"), ("TOTAL", "decimal")]),
            _t("ITEMS", "LG_411_ITEMS", [("LOGICALREF", "int"), ("CODE", "nvarchar(25)")])]
    assert not any(x.kind == "UNKNOWN_JOIN" for x in review(sql, bare))


def test_unreadable_sql_gets_no_findings_not_a_refusal():
    assert review("SELECT FROM WHERE (((", P) == []


def test_a_clean_single_table_aggregate_has_nothing_to_say():
    assert review("SELECT SUM(TOTAL) AS ciro FROM dbo.LG_411_01_STLINE WHERE STOCKREF > 0", P) == []
