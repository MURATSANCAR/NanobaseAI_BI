"""Regressions reported by the live question corpus: date ownership is evidence."""
from copy import deepcopy
from datetime import date

import pytest
from semantic_layer.conventions import Conventions
from semantic_layer.models import ColumnProfile
from semantic_layer.runtime.audit import unmet_obligations
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.tests.conftest import DS, TENANT, PROJECT
from semantic_layer.tests.test_runtime import catalog  # noqa: F401


def configured(profiles):
    conv = Conventions.from_profiles(profiles)
    conv.load_equivalences(PROJECT / "equivalences.yml")
    return conv


@pytest.mark.parametrize("name", ["CAPIBLOCK_CREADEDDATE", "CAPIBLOCK_MODIFIEDDATE", "created_at", "UPDATED_AT"])
def test_maintenance_dates_never_become_default_business_dates(profiles, name):
    profiles = deepcopy(profiles)
    inv = next(p for p in profiles if p.entity == "INVOICE")
    inv.columns.insert(0, ColumnProfile(name=name, data_type="datetime"))
    conv = Conventions.from_profiles(profiles)
    assert conv.time_column("INVOICE") == "DATE_"
    conv.time_hint["INVOICE"] = name
    assert conv.time_column("INVOICE") == "DATE_"


@pytest.mark.parametrize("question", ["hangi kanaldan en çok kazanıyoruz", "hangi müşteriden en çok iade geldi"])
def test_without_a_measure_a_card_date_is_not_a_temporal_obligation(catalog, profiles, question):
    profiles = deepcopy(profiles)
    card = next(p for p in profiles if p.entity == "CLCARD")
    card.columns.append(ColumnProfile(name="CAPIBLOCK_CREADEDDATE", data_type="datetime"))
    card.time_window = ("2010-01-01", "2011-01-01")
    from semantic_layer.models import TemporalSlot
    default = TemporalSlot(text="bu yıl", primitive="YEAR", start=date(2026,1,1), end=date(2027,1,1), grain="YEAR")
    sq = SemanticResolver(catalog, TENANT, DS, profiles, default_temporal=default).resolve(question, today=date(2026,9,9))
    assert not sq.metrics, sq.to_dict()
    assert sq.temporal_binding is None
    assert sq.data_coverage == [] and not sq.out_of_scope
    assert Conventions.from_profiles(profiles).time_column("CLCARD") is None


def sale_plan(catalog, profiles):
    return SemanticResolver(catalog, TENANT, DS, profiles, conventions=configured(profiles)).resolve(
        "bu yıl en çok satan 10 kitap", today=date(2026,7,20))


def test_line_grain_answer_can_use_its_declared_business_date(catalog, profiles):
    sq = sale_plan(catalog, profiles)
    assert sq.temporal_binding["entity"] == "INVOICE", sq.to_dict()
    sql = """SELECT ITEMS.NAME, SUM(STLINE.AMOUNT) AS adet
        FROM LG_411_01_STLINE AS STLINE
        JOIN LG_411_ITEMS AS ITEMS ON ITEMS.LOGICALREF = STLINE.STOCKREF
        WHERE STLINE.DATE_ >= '2026-01-01' AND STLINE.DATE_ < '2027-01-01'
        GROUP BY ITEMS.NAME ORDER BY adet DESC LIMIT 10"""
    assert unmet_obligations(sq, sql) == []
    assert unmet_obligations(sq, sql.replace("STLINE.DATE_", "ITEMS.CAPIBLOCK_CREADEDDATE"))


def joined_query(join):
    return f"""SELECT SUM(INVOICE.NETTOTAL) FROM LG_411_01_INVOICE AS INVOICE
        JOIN LG_411_01_STLINE AS STLINE ON {join}
        WHERE STLINE.DATE_ >= '2026-01-01' AND STLINE.DATE_ < '2027-01-01'"""


def test_equivalent_date_requires_the_declared_relationship_if_header_is_present(catalog, profiles):
    sq = sale_plan(catalog, profiles)
    assert unmet_obligations(sq, joined_query("STLINE.INVOICEREF = INVOICE.LOGICALREF")) == []
    assert unmet_obligations(sq, joined_query("STLINE.CLIENTREF = INVOICE.CLIENTREF"))
    assert unmet_obligations(sq, joined_query("1 = 1"))


def test_a_plain_foreign_key_does_not_declare_date_equivalence(catalog, profiles):
    sq = SemanticResolver(catalog, TENANT, DS, profiles).resolve("2026 satış tutarı", today=date(2026,7,20))
    assert sq.temporal_binding["alternatives"] == []
    assert unmet_obligations(sq, joined_query("STLINE.INVOICEREF = INVOICE.LOGICALREF"))


def test_unused_alternative_cte_does_not_prove_a_period(catalog, profiles):
    sq = sale_plan(catalog, profiles)
    sql = """WITH unused AS (SELECT * FROM LG_411_01_STLINE AS STLINE
             WHERE STLINE.DATE_ >= '2026-01-01' AND STLINE.DATE_ < '2027-01-01')
             SELECT SUM(INVOICE.NETTOTAL) FROM LG_411_01_INVOICE AS INVOICE"""
    assert unmet_obligations(sq, sql)


def test_runtime_loads_the_datasource_date_declaration(catalog, logo_connector, settings):
    from semantic_bridge.app import Runtime
    runtime = Runtime(settings, store=catalog, connector=logo_connector, llm=None)
    binding = runtime.conventions.temporal_binding("INVOICE")
    assert binding["alternatives"][0]["entity"] == "STLINE"


def test_equivalent_date_cannot_hide_a_period_dropped_by_the_header_where(catalog, profiles):
    sq = SemanticResolver(catalog, TENANT, DS, profiles, conventions=configured(profiles)).resolve(
        "geçen yıla göre satış tutarı", today=date(2026,7,20))
    sql = """SELECT SUM(CASE WHEN s.DATE_ >= '2026-01-01' AND s.DATE_ < '2027-01-01' THEN i.NETTOTAL END),
             SUM(CASE WHEN s.DATE_ >= '2025-01-01' AND s.DATE_ < '2026-01-01' THEN i.NETTOTAL END)
             FROM LG_411_01_INVOICE i JOIN LG_411_01_STLINE s ON s.INVOICEREF = i.LOGICALREF"""
    assert unmet_obligations(sq, sql) == []
    assert unmet_obligations(sq, sql + " WHERE i.DATE_ >= '2025-01-01' AND i.DATE_ < '2026-01-01'")


def test_profiler_measures_business_dates_not_maintenance_dates():
    from unittest.mock import Mock
    from semantic_layer.profiler.profiler import Profiler
    connector = Mock(supports_execution=True, dialect="sqlite")
    connector.q.side_effect = lambda value: f'"{value}"'
    connector.execute.return_value = ([], [{"a": "2026-01-01", "b": "2026-08-17"}], False)
    columns = [ColumnProfile(name="CAPIBLOCK_CREADEDDATE", data_type="datetime"),
               ColumnProfile(name="DATE_", data_type="datetime")]
    assert Profiler(connector)._time_window("", "fact", columns) == ("2026-01-01", "2026-08-17")
    sql = connector.execute.call_args.args[0]
    assert "DATE_" in sql and "CAPIBLOCK" not in sql


def return_plan(profiles):
    from semantic_layer.models import Mapping, ResolvedSlot, SemanticQuery, SemanticType
    mapping = Mapping(concept_id="return", entity="STLINE", table_pattern="LG_{n0}_{n1}_STLINE",
                      column="TRCODE", operator="IN", values=["2", "3"])
    slot = ResolvedSlot(term="iade", semantic_type=SemanticType.DIMENSION_VALUE, status="CERTIFIED",
                        concept_id="return", mapping=mapping,
                        explain={"equivalent_bindings": configured(profiles).filter_bindings(mapping)})
    return SemanticQuery(question="hangi müşteriden en çok iade geldi", tenant_id=TENANT, datasource_id=DS, slots=[slot])


def test_declared_return_codes_can_be_filtered_at_invoice_grain(profiles):
    sq = return_plan(profiles)
    sql = """SELECT c.CODE, SUM(i.NETTOTAL) FROM LG_411_01_INVOICE i
             JOIN LG_411_CLCARD c ON c.LOGICALREF = i.CLIENTREF
             WHERE i.TRCODE IN (2,3) GROUP BY c.CODE"""
    assert unmet_obligations(sq, sql) == []
    assert unmet_obligations(sq, sql.replace("IN (2,3)", "IN (2,3,7)"))
    assert unmet_obligations(sq, sql.replace("IN (2,3)", "IN (1,6)"))
    assert unmet_obligations(sq, sql.replace("i.TRCODE", "c.TRCODE"))
    assert unmet_obligations(sq, "WITH unused AS (" + sql + ") SELECT 1")


def test_customer_counts_can_use_the_same_declared_return_filter(profiles):
    sql = """SELECT COUNT(DISTINCT c.LOGICALREF) FROM LG_411_01_INVOICE i
             JOIN LG_411_CLCARD c ON c.LOGICALREF = i.CLIENTREF WHERE i.TRCODE IN (2,3)"""
    assert unmet_obligations(return_plan(profiles), sql) == []
