import pytest

from semantic_layer.history.miner import HistoryMiner
from semantic_layer.history.question_facts import extract_question_facts
from semantic_layer.history.sql_facts import extract_sql_facts
from semantic_layer.history.sources import load_project_pairs
from semantic_layer.models import ValidatedPair
from semantic_layer.naming import logical_table
from semantic_layer.tests.conftest import PROJECT

def _conventions():
    """Conventions as the profiler would have produced them for this fixture schema."""
    from semantic_layer.conventions import Conventions
    from semantic_layer.models import ColumnProfile, SchemaProfile

    def prof(entity, pattern, columns):
        return SchemaProfile(datasource_id="d", table_name=pattern, table_pattern=pattern, entity=entity, columns=columns, primary_key=["LOGICALREF"])

    def col(name, typ="int", values=None, pk=False):
        return ColumnProfile(name=name, data_type=typ, top_values=[(v, 1) for v in (values or [])], distinct_count=len(values) if values else None, is_primary_key=pk)

    return Conventions.from_profiles([
        prof("INVOICE", "INVOICE", [col("LOGICALREF", pk=True), col("TRCODE", "smallint", ["1", "2", "3", "7", "8", "9"]), col("CANCELLED", "smallint", ["0", "1"]), col("NETTOTAL", "float"), col("DATE_", "datetime"), col("CLIENTREF")]),
        prof("STLINE", "STLINE", [col("LOGICALREF", pk=True), col("TRCODE", "smallint", ["2", "3", "7", "8"]), col("LINETYPE", "smallint", ["0", "2", "4"]), col("CANCELLED", "smallint", ["0", "1"]), col("AMOUNT", "float"), col("TOTAL", "float"), col("DATE_", "datetime"), col("STOCKREF")]),
        prof("CLCARD", "CLCARD", [col("LOGICALREF", pk=True), col("SPECODE2", "varchar(11)", ["KITAPCI", "E-TICARET", "DAGITICI"]), col("CODE", "varchar(17)"), col("DEFINITION_", "varchar(51)")]),
        prof("ITEMS", "ITEMS", [col("LOGICALREF", pk=True), col("CODE", "varchar(25)"), col("NAME", "varchar(51)"), col("SPECODE", "varchar(11)")]),
    ])


IDX = {"INVOICE": {"TRCODE", "NETTOTAL", "DATE_", "CANCELLED", "CLIENTREF", "LOGICALREF"}, "STLINE": {"TRCODE", "LINETYPE", "AMOUNT", "TOTAL", "DATE_", "CANCELLED", "STOCKREF"}, "CLCARD": {"LOGICALREF", "SPECODE2", "CODE", "DEFINITION_"}, "ITEMS": {"LOGICALREF", "CODE", "NAME", "SPECODE"}}


def test_logical_table_patterns():
    lt = logical_table("dbo_LG_411_01_INVOICE", "dbo")
    assert (lt.entity, lt.table_pattern, lt.context) == ("INVOICE", "LG_{n0}_{n1}_INVOICE", {"n0": "411", "n1": "01"})
    assert logical_table("[dbo].[LG_411_CLCARD]").table_pattern == "LG_{n0}_CLCARD"
    assert logical_table("dbo.LG_002_03_STLINE").physical({"n0": "411", "n1": "01"}) == "LG_411_01_STLINE"


def test_sql_facts_case_aliases_scope_and_time():
    sql = '''SELECT DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1) AS ay,
      SUM(CASE WHEN "TRCODE" = 7 THEN "NETTOTAL" ELSE 0 END) AS perakende_toplam,
      SUM(CASE WHEN "TRCODE" = 8 THEN "NETTOTAL" ELSE 0 END) AS toptan_toplam
      FROM dbo_LG_411_01_INVOICE WHERE "CANCELLED" = 0 AND "TRCODE" IN (7, 8) AND "DATE_" >= '2026-01-01' AND "DATE_" < '2027-01-01'
      GROUP BY DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1) ORDER BY 1'''
    f = extract_sql_facts(sql, IDX)
    assert f.tables == ["INVOICE"] and f.grain == "MONTH"
    case = {(p.column, p.values, p.alias) for p in f.predicates if p.source == "case"}
    assert ("TRCODE", ("7",), "perakende_toplam") in case and ("TRCODE", ("8",), "toptan_toplam") in case
    assert any(p.source == "scope" and p.values == ("7", "8") for p in f.predicates)  # WHERE only scopes the CASE branches
    assert f.time_ranges[0].start == "2026-01-01" and f.time_ranges[0].end == "2027-01-01"
    assert {a.alias for a in f.aggregates} == {"perakende_toplam", "toptan_toplam"}


def test_sql_facts_joins_limit_and_projections():
    sql = 'SELECT it."CODE" AS stok_kodu, SUM(sl."AMOUNT") AS adet FROM dbo_LG_411_01_STLINE sl JOIN dbo_LG_411_ITEMS it ON it."LOGICALREF" = sl."STOCKREF" WHERE sl."CANCELLED" = 0 AND sl."LINETYPE" = 0 AND sl."TRCODE" IN (7,8) GROUP BY it."CODE" ORDER BY adet DESC LIMIT 10'
    f = extract_sql_facts(sql, IDX)
    assert ("ITEMS", "LOGICALREF", "STLINE", "STOCKREF") in f.joins
    assert f.limit == 10
    assert ("stok_kodu", "ITEMS", "CODE") in f.projections
    assert f.aggregates[0].formula == "SUM(STLINE.AMOUNT)"


def test_question_facts_explicit_binding_and_limit():
    qf = extract_question_facts("Temmuz 2026'da en çok satan 15 kitap; yalnız toptan satış faturaları (TRCODE 8), adede göre azalan.")
    assert ("toptan", "TRCODE", ("8",)) in qf.explicit_bindings
    assert qf.limit == 15 and qf.order_desc is True
    assert qf.temporal[0].primitive == "MONTH"


def test_miner_binds_terms_to_predicates_and_metrics():
    pairs = [
        ValidatedPair("p1", "Perakende (TRCODE 7) ile toptan (TRCODE 8) satışları ay bazında karşılaştır", '''SELECT SUM(CASE WHEN "TRCODE" = 7 THEN "NETTOTAL" ELSE 0 END) AS perakende_toplam, SUM(CASE WHEN "TRCODE" = 8 THEN "NETTOTAL" ELSE 0 END) AS toptan_toplam FROM dbo_LG_411_01_INVOICE WHERE "CANCELLED" = 0 AND "TRCODE" IN (7,8)'''),
        ValidatedPair("p2", "2026 toplam net ciro nedir?", '''SELECT SUM(CASE WHEN "TRCODE" IN (7,8,9) THEN "NETTOTAL" ELSE -"NETTOTAL" END) AS net_ciro FROM dbo_LG_411_01_INVOICE WHERE "CANCELLED" = 0 AND "TRCODE" IN (2,3,7,8,9)'''),
        ValidatedPair("p3", "Aylık net ciro", '''SELECT SUM(CASE WHEN "TRCODE" IN (7,8,9) THEN "NETTOTAL" ELSE -"NETTOTAL" END) AS net_ciro FROM dbo_LG_411_01_INVOICE WHERE "CANCELLED" = 0 AND "TRCODE" IN (2,3,7,8,9) GROUP BY MONTH("DATE_")'''),
        ValidatedPair("p4", "Kanal bazında net ciro nedir?", '''SELECT c."SPECODE2" AS kanal, SUM(CASE WHEN i."TRCODE" IN (7,8,9) THEN i."NETTOTAL" ELSE -i."NETTOTAL" END) AS net_ciro FROM dbo_LG_411_01_INVOICE i JOIN dbo_LG_411_CLCARD c ON c."LOGICALREF" = i."CLIENTREF" WHERE i."CANCELLED" = 0 AND i."TRCODE" IN (2,3,7,8,9) GROUP BY c."SPECODE2"'''),
    ]
    res = HistoryMiner(IDX, conventions=_conventions()).mine(pairs)
    by = {(c.term, c.entity, c.column, c.values): c for c in res.correlations}
    assert by[("toptan", "INVOICE", "TRCODE", ("8",))].explicit_support == 1
    assert by[("perakende", "INVOICE", "TRCODE", ("7",))].alias_support >= 1
    assert not any(c.values == ("7", "8") for c in res.correlations if c.term in ("toptan", "perakende"))  # scope predicate never binds
    net = [m for m in res.metrics if m.term == "net ciro"]
    assert net and net[0].support == 3 and net[0].entity == "INVOICE" and "INVOICE.TRCODE IN (2,3,7,8,9)" in net[0].conditions
    assert any(c.term == "kanal" and c.column == "SPECODE2" for c in res.columns)
    assert [p.key() for p, _ in res.default_filters] == ["INVOICE.CANCELLED = (0)"]  # TRCODE is scope, never a default


@pytest.mark.skipif(not PROJECT.exists(), reason="operator project not present")
def test_miner_on_real_project_knowledge():
    pairs = load_project_pairs(PROJECT)
    assert len(pairs) >= 40
    res = HistoryMiner(IDX, conventions=_conventions()).mine(pairs)
    assert res.parse_errors == []
    terms = {(c.term, c.entity, c.column, c.values) for c in res.correlations}
    assert ("toptan", "INVOICE", "TRCODE", ("8",)) in terms
    assert ("perakende", "INVOICE", "TRCODE", ("7",)) in terms
    assert ("iade", "INVOICE", "TRCODE", ("2", "3")) in terms
    assert any(m.term == "net ciro" and m.support >= 3 for m in res.metrics)
