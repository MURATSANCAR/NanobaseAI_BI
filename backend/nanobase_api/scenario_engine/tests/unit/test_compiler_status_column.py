"""Compiler must never guess a status column name.

Regression for the root cause of 219/777 broken PUBLISHED erp scenarios
(found via live-schema revalidation 2026-08-11): when discovery didn't record
``status_column`` in ``plan.extra``, the compiler silently fell back to a
hardcoded English ``"status"`` — emitting ``t."status" <> :cancelled_status``
against Turkish-columned tables (real column: ``durum``), SQL that fails on
every execution. Refusing to compile (scenario rejected → question falls back
to the LLM path) is the only safe behavior: silently dropping the mandatory
exclude-cancelled filter would instead leak cancelled rows into financial
answers.
"""

from __future__ import annotations

import pytest

from nanobase_api.scenario_engine.domain.logical_plan import LogicalPlan
from nanobase_api.scenario_engine.infrastructure.compiler import (
    CompilerColumnUnknown,
    PostgresLogicalPlanCompiler,
)


def _plan(**overrides):
    base = dict(
        family="COUNT_ENTITY",
        entity="fatura",
        physical_table="public.faturalar",
        period="CURRENT_MONTH",
        date_column="public.faturalar.fatura_tarihi",
    )
    base.update(overrides)
    return LogicalPlan(**base)


def test_mandatory_cancelled_filter_without_status_column_refuses_to_compile():
    plan = _plan(mandatory_filters=["exclude_cancelled_invoices"])
    with pytest.raises(CompilerColumnUnknown):
        PostgresLogicalPlanCompiler().compile(plan)


def test_status_filter_without_status_column_refuses_to_compile():
    plan = _plan(status_filter="paid")
    with pytest.raises(CompilerColumnUnknown):
        PostgresLogicalPlanCompiler().compile(plan)


def test_known_status_column_compiles_with_real_column_name():
    plan = _plan(
        mandatory_filters=["exclude_cancelled_invoices"],
        extra={"status_column": "durum"},
    )
    compiled = PostgresLogicalPlanCompiler().compile(plan)
    assert '"durum" <> :cancelled_status' in compiled.sql_template
    assert '"status"' not in compiled.sql_template


def test_plan_without_status_needs_compiles_fine_without_status_column():
    """Plans that never touch a status predicate must be unaffected."""
    plan = _plan()
    compiled = PostgresLogicalPlanCompiler().compile(plan)
    assert "cancelled_status" not in compiled.sql_template


def test_stage_sql_compilation_rejects_bad_scenario_but_continues():
    """One uncompilable plan must reject THAT scenario, not kill the build."""
    from nanobase_api.scenario_engine.application.staged_pipeline import (
        ensure_build,
        stage_sql_compilation,
    )
    from nanobase_api.scenario_engine.domain.scenario import ScenarioInstance
    from nanobase_api.scenario_engine.domain.status import ScenarioStatus
    from nanobase_api.scenario_engine.infrastructure.store import ScenarioStore

    store = ScenarioStore()
    build_id = "b-test-statuscol"
    ensure_build(store, build_id=build_id, tenant_id="default", datasource_id="erp")

    good = ScenarioInstance(
        id="sc-good",
        tenant_id="default",
        datasource_id="erp",
        scenario_code="fatura.count.ok",
        canonical_question="Bu ayki kaç fatura var?",
        family="COUNT_ENTITY",
        logical_plan=_plan(extra={"status_column": "durum"}, mandatory_filters=["exclude_cancelled_invoices"]),
        status=ScenarioStatus.GENERATED,
        schema_version="v1",
        semantic_version="v1",
    )
    bad = ScenarioInstance(
        id="sc-bad",
        tenant_id="default",
        datasource_id="erp",
        scenario_code="fatura.count.broken",
        canonical_question="Bu ayki kaç fatura var (iptal hariç)?",
        family="COUNT_ENTITY",
        logical_plan=_plan(mandatory_filters=["exclude_cancelled_invoices"]),  # no status_column
        status=ScenarioStatus.GENERATED,
        schema_version="v1",
        semantic_version="v1",
    )
    store.save_instance(good)
    store.save_instance(bad)
    store.builds[build_id]["workspace"]["instanceIds"] = ["sc-good", "sc-bad"]

    result = stage_sql_compilation(build_id=build_id, store=store)

    assert result.get("status") != "FAILED"
    assert result["counts"]["compilations"] == 1
    assert result["counts"]["compileRejected"] == 1
    assert store.get_instance("sc-bad").status == ScenarioStatus.REJECTED
    assert store.get_instance("sc-good").status == ScenarioStatus.GENERATED
    assert "CompilerColumnUnknown" in result["compileRejections"][0]["reason"]
