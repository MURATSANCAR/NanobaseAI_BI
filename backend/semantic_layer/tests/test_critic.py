"""The critic reads a query for the ways it can return the wrong number."""
from __future__ import annotations

import pytest

from semantic_layer.models import ColumnProfile, SchemaProfile
from semantic_layer.runtime.critic import review
from semantic_layer.tests.test_runtime import catalog  # noqa: F401  — the certified fixture lives there


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


def _client(catalog, logo_connector, settings, replies):
    from fastapi.testclient import TestClient

    from semantic_bridge.app import Runtime, create_app
    from semantic_layer.candidates.llm_client import FakeLlm

    llm = FakeLlm(list(replies))
    rt = Runtime(settings, store=catalog, connector=logo_connector, llm=llm)
    return TestClient(create_app(rt)), llm


#: "How many customers bought something" written as a count over the invoice join. Every customer is
#: counted once per invoice they have, so the answer is the number of invoices wearing the name of
#: the number of customers. The database returns it without complaint.
_INFLATED = ('```sql\nSELECT COUNT(*) AS musteri_sayisi FROM dbo_LG_411_01_INVOICE i '
             'JOIN dbo_LG_411_CLCARD c ON c."LOGICALREF" = i."CLIENTREF"\n```')
_CORRECT = ('```sql\nSELECT COUNT(DISTINCT c."LOGICALREF") AS musteri_sayisi FROM dbo_LG_411_01_INVOICE i '
            'JOIN dbo_LG_411_CLCARD c ON c."LOGICALREF" = i."CLIENTREF"\n```')


def test_an_inflated_count_is_sent_back_to_the_model_and_the_corrected_query_is_what_runs(
        catalog, profiles, logo_connector, settings):
    client, llm = _client(catalog, logo_connector, settings, [_INFLATED, _CORRECT])
    r = client.post("/api/v1/ask", json={"question": "Bölgesel satış dağılımı 2026"}).json()

    assert r["type"] == "TEXT_TO_SQL", r.get("explanation")
    assert r["repairs"] == 1, "the finding went back to the model as an instruction"
    assert "DISTINCT" in r["sql"], "what ran is the corrected query"
    told = llm.calls[-1][-1]["content"]
    assert "şişirilmiş" in told and "CLCARD" in told, told[:200]


def test_a_repair_that_does_not_fix_it_refuses_rather_than_returning_the_number(
        catalog, profiles, logo_connector, settings):
    client, _ = _client(catalog, logo_connector, settings, [_INFLATED, _INFLATED])
    r = client.post("/api/v1/ask", json={"question": "Bölgesel satış dağılımı 2026"}).json()

    assert r["type"] == "SQL_INVALID"
    assert "şişirilmiş" in r["explanation"], "the person is told what is wrong, not that the SQL is invalid"
    assert "doğrulanamadı" not in r["explanation"], "a reviewed refusal is not reported as a database fault"
    assert any(n["kind"] == "FANOUT" for n in r["semantic"]["critic"])


def test_one_physical_pattern_is_one_entity_even_mid_scan():
    """While a scan rewrites the catalog table by table, rows from two runs sit side by side and can
    disagree about what an entity is called — splitting one entity's years in half. The pattern is
    derived from the table name alone, so it decides."""
    from datetime import timedelta

    from semantic_bridge.app import one_entity_per_pattern
    from semantic_layer.models import utcnow

    old_ = SchemaProfile(datasource_id="d", table_name="LG_211_ITEMS", table_pattern="LG_{n0}_ITEMS",
                         entity="ITEMS", schema_name="dbo", scanned_at=utcnow() - timedelta(hours=12))
    new_ = SchemaProfile(datasource_id="d", table_name="LG_411_ITEMS", table_pattern="LG_{n0}_ITEMS",
                         entity="LG_ITEMS", schema_name="dbo", scanned_at=utcnow())
    other = SchemaProfile(datasource_id="d", table_name="LV_411_ITEMS", table_pattern="LV_{n0}_ITEMS",
                          entity="LV_ITEMS", schema_name="dbo", scanned_at=utcnow())
    out = one_entity_per_pattern([old_, new_, other])
    assert {p.table_name: p.entity for p in out} == {
        "LG_211_ITEMS": "LG_ITEMS", "LG_411_ITEMS": "LG_ITEMS", "LV_411_ITEMS": "LV_ITEMS",
    }, "both years of one pattern share the newest label; a different pattern keeps its own"
