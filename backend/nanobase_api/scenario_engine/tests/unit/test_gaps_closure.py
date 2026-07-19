"""Gaps closure: scale, dialects, LLM gate, stages, SQL fail-closed."""

from __future__ import annotations

import os

import pytest

from nanobase_api.scenario_engine.application.staged_pipeline import STAGE_CHAIN, run_staged_build
from nanobase_api.scenario_engine.infrastructure.combination import plan_invoice_combinations
from nanobase_api.scenario_engine.infrastructure.compiler import get_compiler
from nanobase_api.scenario_engine.infrastructure.llm_paraphrase import equivalence_gate, maybe_llm_paraphrases
from nanobase_api.scenario_engine.infrastructure.question_grammar import generate_questions
from nanobase_api.scenario_engine.infrastructure.relationship_graph import build_relationship_graph
from nanobase_api.scenario_engine.infrastructure.schema_snapshot import invoice_analytics_snapshot
from nanobase_api.scenario_engine.infrastructure.semantic_classifier import classify_schema
from nanobase_api.scenario_engine.infrastructure.store import reset_scenario_store
from nanobase_api.scenario_engine.infrastructure.validators import validate_gateway_template
from nanobase_api.scenario_engine.domain.status import ScenarioStatus


def test_stage_chain_length():
    assert len(STAGE_CHAIN) == 8
    assert STAGE_CHAIN[0] == "scenario_discovery"
    assert STAGE_CHAIN[-1] == "scenario_embedding_publish"


def test_slim_build_still_publishes():
    store = reset_scenario_store()
    result = run_staged_build(
        tenant_id="default",
        datasource_id="bi_reporting",
        store=store,
        snapshot=invoice_analytics_snapshot(),
        auto_publish=True,
        force=True,
    )
    assert result["status"] == "COMPLETED"
    published = store.list_instances(
        tenant_id="default", datasource_id="bi_reporting", status=ScenarioStatus.PUBLISHED
    )
    assert len(published) >= 3


def test_full_scale_combination_count():
    os.environ["SCENARIO_COMBINATION_SCALE"] = "full"
    try:
        snap = invoice_analytics_snapshot()
        clf = classify_schema(snap)
        graph = build_relationship_graph(snap)
        planned = plan_invoice_combinations(clf, graph)
        assert 500 <= len(planned) <= 2000
    finally:
        os.environ["SCENARIO_COMBINATION_SCALE"] = "slim"


def test_paraphrase_expansion_volume():
    snap = invoice_analytics_snapshot()
    clf = classify_schema(snap)
    graph = build_relationship_graph(snap)
    os.environ["SCENARIO_COMBINATION_SCALE"] = "full"
    try:
        planned = plan_invoice_combinations(clf, graph)
        total = 0
        for p in planned[:200]:
            total += len(generate_questions(p.logical_plan, expand=True))
        # 200 scenarios × ~10 variants → path to 5k–20k at full set
        assert total >= 1000
        projected = int(total * (len(planned) / max(1, min(200, len(planned)))))
        assert projected >= 5000
    finally:
        os.environ["SCENARIO_COMBINATION_SCALE"] = "slim"


def test_gateway_validate_offline():
    sql = 'SELECT "invoice_id" FROM analytics.invoices WHERE "status" <> :cancelled_status LIMIT :fetch_limit'
    res = validate_gateway_template(sql, ["cancelled_status", "fetch_limit"])
    assert res.passed


def test_oracle_hana_odata_compile_flags():
    snap = invoice_analytics_snapshot()
    clf = classify_schema(snap)
    graph = build_relationship_graph(snap)
    os.environ["SCENARIO_COMBINATION_SCALE"] = "slim"
    planned = plan_invoice_combinations(clf, graph)
    plan = next(p.logical_plan for p in planned if p.family.value == "LIST_ENTITY")

    os.environ["SCENARIO_ORACLE_ENABLED"] = "1"
    oracle = get_compiler("oracle").compile(plan)
    assert "FETCH FIRST" in oracle.sql_template.upper() or "LIMIT" not in oracle.sql_template

    os.environ["SCENARIO_HANA_ENABLED"] = "1"
    hana = get_compiler("hana").compile(plan)
    assert "SELECT" in hana.sql_template.upper()

    os.environ["SCENARIO_ODATA_ENABLED"] = "1"
    odata = get_compiler("odata").compile(plan)
    assert "$top=" in odata.sql_template or "$filter=" in odata.sql_template


def test_llm_equivalence_gate():
    snap = invoice_analytics_snapshot()
    clf = classify_schema(snap)
    graph = build_relationship_graph(snap)
    planned = plan_invoice_combinations(clf, graph)
    plan = planned[0].logical_plan
    ok, _ = equivalence_gate("Geçen ayki faturaları getir.", "Geçen ayki faturaları göster.", plan)
    assert ok
    bad, detail = equivalence_gate("Geçen ayki faturaları getir.", "SELECT * FROM invoices", plan)
    assert not bad
    assert detail.get("reason") == "sql_leak"


def test_llm_paraphrase_flag_off():
    os.environ.pop("SCENARIO_LLM_PARAPHRASE", None)
    snap = invoice_analytics_snapshot()
    planned = plan_invoice_combinations(classify_schema(snap), build_relationship_graph(snap))
    assert maybe_llm_paraphrases("Faturaları getir.", planned[0].logical_plan) == []


def test_sql_require_fail_closed(monkeypatch):
    monkeypatch.setenv("SCENARIO_SQL_DISABLED", "0")
    monkeypatch.setenv("SCENARIO_REQUIRE_SQL", "1")
    monkeypatch.delenv("NANOBASE_META_DSN", raising=False)
    from nanobase_api.scenario_engine.infrastructure import store as store_mod

    store_mod._STORE = None
    with pytest.raises(RuntimeError, match="SCENARIO_REQUIRE_SQL"):
        store_mod.get_scenario_store()
    store_mod._STORE = None
    monkeypatch.setenv("SCENARIO_SQL_DISABLED", "1")
    monkeypatch.setenv("SCENARIO_REQUIRE_SQL", "0")


@pytest.mark.skipif(
    os.environ.get("NANOBASE_META_DSN") in (None, ""),
    reason="NANOBASE_META_DSN not configured",
)
def test_sql_restart_match_integration():
    """Hydrate → match → new store → still match when meta DSN present."""
    os.environ["SCENARIO_SQL_DISABLED"] = "0"
    os.environ["SCENARIO_REQUIRE_SQL"] = "0"
    from nanobase_api.scenario_engine.application.matcher import ScenarioMatcher
    from nanobase_api.scenario_engine.infrastructure import store as store_mod

    store_mod._STORE = None
    store = store_mod.get_scenario_store()
    run_staged_build(
        tenant_id="default",
        datasource_id="bi_reporting",
        store=store,
        snapshot=invoice_analytics_snapshot(),
        auto_publish=True,
        force=True,
    )
    published = store.list_instances(
        tenant_id="default", datasource_id="bi_reporting", status=ScenarioStatus.PUBLISHED
    )
    assert published
    q = published[0].canonical_question
    m1 = ScenarioMatcher(store=store).match(q, tenant_id="default", datasource_id="bi_reporting")
    assert m1.matched
    store_mod._STORE = None
    store2 = store_mod.get_scenario_store()
    m2 = ScenarioMatcher(store=store2).match(q, tenant_id="default", datasource_id="bi_reporting")
    assert m2.matched
    os.environ["SCENARIO_SQL_DISABLED"] = "1"
