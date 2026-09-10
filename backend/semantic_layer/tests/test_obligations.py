"""Adversarial obligation tests: output scope, semantics and final execution."""
from datetime import date
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from semantic_layer.models import Mapping, ResolvedSlot, SemanticQuery, SemanticType
from semantic_layer.runtime.audit import unmet_obligations
from semantic_layer.runtime.compiler import DeterministicCompiler, default_filters_provider, _wrap_condition
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.tests.test_runtime import catalog  # noqa: F401
from semantic_layer.tests.conftest import DS, TENANT


def plan(catalog, profiles, question="geçen yıla göre net ciro"):
    sq = SemanticResolver(catalog, TENANT, DS, profiles).resolve(question, today=date(2026, 7, 20))
    compiler = DeterministicCompiler(profiles, {"n0": "411", "n1": "01"}, "sqlite",
                                    default_filters=default_filters_provider(catalog, TENANT, DS))
    out = compiler.compile(sq, catalog)
    assert out is not None, sq.to_dict()
    return sq, out.sql


@pytest.mark.parametrize("mutate", [
    lambda s: s.replace("< '2027-01-01'", "< '2028-01-01'"),
    lambda s: s.replace("DATE_", "LOGICALREF"),
    lambda s: s.replace("NETTOTAL", "TOTALVAT"),
    lambda s: "SELECT 1 /* " + s + " */",
    lambda s: "WITH unused AS (" + s + ") SELECT 1",
])
def test_dates_anywhere_are_not_comparison_evidence(catalog, profiles, mutate):
    sq, sql = plan(catalog, profiles)
    assert unmet_obligations(sq, sql) == []
    assert sq.comparison["satisfied"]
    assert unmet_obligations(sq, mutate(sql))
    assert not sq.comparison["satisfied"]


def test_explicit_periods_also_create_an_obligation(catalog, profiles):
    sq, sql = plan(catalog, profiles, "2026 ve 2025 net ciro")
    assert sq.comparison
    assert unmet_obligations(sq, sql) == []
    assert unmet_obligations(sq, "SELECT SUM(NETTOTAL) FROM LG_411_01_INVOICE")


@pytest.mark.parametrize("today,start,end", [
    (date(2026, 9, 9), date(2026, 9, 1), date(2026, 10, 1)),
    (date(2027, 1, 3), date(2027, 1, 1), date(2027, 2, 1)),
    (date(2024, 3, 3), date(2024, 3, 1), date(2024, 4, 1)),
])
def test_months_use_calendar_boundaries(catalog, profiles, today, start, end):
    sq = SemanticResolver(catalog, TENANT, DS, profiles).resolve("geçen aya göre net ciro", today=today)
    assert sq.temporal[0].start == start and sq.temporal[0].end == end
    assert sq.temporal[0].grain == sq.temporal[1].grain == "MONTH"


def test_named_reference_does_not_make_next_year_current(catalog, profiles):
    sq = SemanticResolver(catalog, TENANT, DS, profiles).resolve("2019 yılına göre net ciro", today=date(2026, 7, 20))
    assert sq.comparison and sq.comparison["current"]["start"] == "2026-01-01"


def city_plan():
    return SemanticQuery(question="Ankara müşterileri", tenant_id=TENANT, datasource_id=DS, slots=[
        ResolvedSlot(term="Ankara", semantic_type=SemanticType.DIMENSION_VALUE, status="CERTIFIED",
                     concept_id="city", mapping=Mapping(concept_id="city", entity="CLCARD", table_pattern="LG_{n0}_CLCARD",
                                                         column="CITY", operator="=", values=["Ankara"]))])


@pytest.mark.parametrize("sql", [
    "SELECT * FROM LG_411_CLCARD",
    "SELECT * FROM LG_411_CLCARD WHERE CITY IN ('Ankara', 'İstanbul')",
    "SELECT * FROM LG_411_CLCARD WHERE CITY = 'Ankara' OR ACTIVE = 1",
    "WITH unused AS (SELECT * FROM LG_411_CLCARD WHERE CITY = 'Ankara') SELECT * FROM LG_411_CLCARD",
    "SELECT CASE WHEN CITY = 'Ankara' THEN 1 ELSE 0 END FROM LG_411_CLCARD",
    "SELECT * FROM LG_411_CLCARD WHERE CITY = 'İstanbul'",
])
def test_city_cannot_disappear_widen_or_move_to_unused_scope(sql):
    assert unmet_obligations(city_plan(), sql)


def test_city_bound_to_actual_answer_survives_aliases():
    assert unmet_obligations(city_plan(), "SELECT * FROM LG_411_CLCARD AS c WHERE c.CITY = 'Ankara'") == []


@pytest.mark.parametrize("fn,expected", [("AVG", 15), ("MIN", 10), ("MAX", 20), ("SUM", 30)])
def test_conditional_aggregates_do_not_include_out_of_period_zeroes(logo_db, fn, expected):
    formula = _wrap_condition(f"{fn}(v)", "y = 2026")
    sql = f"SELECT {formula} FROM (SELECT 2026 y, 10 v UNION ALL SELECT 2026,20 UNION ALL SELECT 2025,99)"
    assert logo_db.execute(sql).fetchone()[0] == expected


def test_unknown_coverage_cannot_produce_a_zero_answer(catalog, logo_connector, settings):
    from semantic_bridge.app import Runtime, create_app
    runtime = Runtime(settings, store=catalog, connector=logo_connector, llm=None)
    runtime.run_sql = Mock(side_effect=AssertionError("must not execute"))
    client = TestClient(create_app(runtime))
    body = client.post("/api/v1/ask", json={"question": "2027 yılında net ciro"}).json()
    assert body["type"] == "DATA_UNAVAILABLE", body
    assert "resultId" not in body and "records" not in body
    runtime.run_sql.assert_not_called()


def test_partial_coverage_survives_summary_and_snapshot(catalog, logo_connector, settings):
    from semantic_bridge.app import Runtime, create_app
    runtime = Runtime(settings, store=catalog, connector=logo_connector, llm=None)
    client = TestClient(create_app(runtime))
    body = client.post("/api/v1/ask", json={"question": "2026 yılında net ciro"}).json()
    assert body["type"] == "TEXT_TO_SQL", body
    assert "kısmen gözleniyor" in body["summary"]
    saved = client.get("/api/v1/result/" + body["resultId"]).json()
    assert saved["dataCoverage"] == body["dataCoverage"]
    assert saved["dataCoverage"][0]["completeness"] == "UNKNOWN"


def test_repaired_sql_is_checked_again_before_execution(catalog, logo_connector, settings, profiles):
    from semantic_bridge.app import Runtime, create_app
    from semantic_layer.models import CompiledQuery
    runtime = Runtime(settings, store=catalog, connector=logo_connector, llm=None)
    sq, sql = plan(catalog, profiles, "2026 toptan satış tutarı")
    runtime.resolver.resolve = Mock(return_value=sq)
    runtime.router.compile = Mock(return_value=CompiledQuery(sql=sql, compiler="existing_llm", certified=False))
    runtime.existing = Mock()
    runtime.existing.repair.return_value = "SELECT SUM(NETTOTAL) FROM LG_411_01_INVOICE"
    original = logo_connector.dry_run
    calls = []
    def fail_once(sql):
        calls.append(sql)
        if len(calls) == 1:
            raise ValueError("repair requested")
        return original(sql)
    logo_connector.dry_run = fail_once
    runtime.run_sql = Mock(side_effect=AssertionError("must not execute"))
    body = TestClient(create_app(runtime)).post("/api/v1/ask", json={"question": sq.question}).json()
    assert body["type"] == "INCOMPLETE_ANSWER", body
    assert "records" not in body and "resultId" not in body
    runtime.run_sql.assert_not_called()


def test_global_where_cannot_drop_a_period_while_cases_remain(catalog, profiles):
    from semantic_layer.history.sql_facts import parse_sql
    sq, sql = plan(catalog, profiles)
    tree = parse_sql(sql)
    tree.set("where", parse_sql("SELECT 1 WHERE INVOICE.DATE_ >= '2025-01-01' AND INVOICE.DATE_ < '2026-01-01'").args["where"])
    assert unmet_obligations(sq, tree.sql())


def test_grouping_by_channel_is_not_a_period_comparison(catalog, profiles):
    sq = SemanticResolver(catalog, TENANT, DS, profiles).resolve("2025 kanal bazına göre net ciro", today=date(2026, 7, 20))
    assert sq.comparison is None


def test_single_period_cannot_disappear(catalog, profiles):
    sq, sql = plan(catalog, profiles, "2026 net ciro")
    assert unmet_obligations(sq, sql) == []
    assert unmet_obligations(sq, "SELECT SUM(NETTOTAL) FROM LG_411_01_INVOICE")


def test_unrestricted_measure_cannot_hide_behind_a_filtered_measure():
    sql = "SELECT SUM(CASE WHEN CITY = 'Ankara' THEN 1 END), COUNT(*) FROM LG_411_CLCARD"
    assert unmet_obligations(city_plan(), sql)


@pytest.mark.parametrize("expression,expected", [("COUNT(*)", 2), ("COUNT(DISTINCT v)", 1)])
def test_conditional_counts_preserve_distinctness_and_ignore_other_periods(logo_db, expression, expected):
    formula = _wrap_condition(expression, "y = 2026")
    sql = f"SELECT {formula} FROM (SELECT 2026 y, 10 v UNION ALL SELECT 2026,10 UNION ALL SELECT 2025,99)"
    assert logo_db.execute(sql).fetchone()[0] == expected


@pytest.mark.parametrize("question", ["pahalı ürünler", "ucuz kitaplar"])
def test_qualitative_price_requires_a_business_definition(catalog, profiles, question):
    sq = SemanticResolver(catalog, TENANT, DS, profiles).resolve(question, today=date(2026, 7, 20))
    assert sq.clarification and "para birimini" in sq.clarification[0]


def test_unqualified_date_on_a_single_source_is_not_ambiguous(catalog, profiles):
    sq, sql = plan(catalog, profiles, "2026 net ciro")
    assert unmet_obligations(sq, sql.replace("INVOICE.", "")) == []
