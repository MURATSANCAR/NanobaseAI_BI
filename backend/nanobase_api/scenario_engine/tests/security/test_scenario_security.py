"""Security invariants for scenario engine."""

from __future__ import annotations

from nanobase_api.scenario_engine.application.build_pipeline import start_build
from nanobase_api.scenario_engine.application.runtime import try_precompiled_scenario
from nanobase_api.scenario_engine.domain.logical_plan import LogicalPlan
from nanobase_api.scenario_engine.domain.status import ScenarioStatus
from nanobase_api.scenario_engine.infrastructure.compiler import (
    CompileResult,
    PostgresLogicalPlanCompiler,
)
from nanobase_api.scenario_engine.infrastructure.schema_snapshot import invoice_analytics_snapshot
from nanobase_api.scenario_engine.infrastructure.store import reset_scenario_store
from nanobase_api.scenario_engine.infrastructure.validators import validate_static_ast


def test_stale_scenario_not_executable():
    store = reset_scenario_store()
    start_build(
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
    target = published[0]
    store.mark_stale_by_column("default", "bi_reporting", target.logical_plan.date_column or "invoice_date")
    q = target.canonical_question
    # After stale, exact paraphrase hash still finds paraphrase but instance is STALE
    hit = try_precompiled_scenario(q, tenant_id="default", datasource_id="bi_reporting")
    assert hit is None


def test_dml_rejected_by_static():
    plan = LogicalPlan(
        family="LIST_ENTITY",
        entity="invoice",
        physical_table="analytics.invoices",
        projection=["invoice_id"],
    )
    bad = CompileResult(
        sql_template="DELETE FROM analytics.invoices",
        dialect="postgres",
        ast_fingerprint="x",
        bind_params=[],
        logical_plan=plan.to_dict(),
    )
    assert validate_static_ast(plan, bad).passed is False


def test_sensitive_column_rejected():
    plan = LogicalPlan(
        family="LIST_ENTITY",
        entity="invoice",
        physical_table="analytics.invoices",
        projection=["password_hash"],
    )
    compiled = PostgresLogicalPlanCompiler().compile(plan)
    # Inject sensitive into template for guard
    compiled.sql_template = compiled.sql_template.replace("invoice_id", "password_hash", 1)
    # If projection was password_hash it still compiles; static should catch sensitive keyword
    bad = CompileResult(
        sql_template='SELECT "password_hash" FROM analytics.invoices',
        dialect="postgres",
        ast_fingerprint="y",
        bind_params=[],
        logical_plan=plan.to_dict(),
    )
    assert validate_static_ast(plan, bad).passed is False


def test_no_string_concat_in_runtime_payload():
    store = reset_scenario_store()
    start_build(
        tenant_id="default",
        datasource_id="bi_reporting",
        store=store,
        snapshot=invoice_analytics_snapshot(),
        auto_publish=True,
        force=True,
    )
    published = [
        i
        for i in store.list_instances(
            tenant_id="default", datasource_id="bi_reporting", status=ScenarioStatus.PUBLISHED
        )
        if i.scenario_code == "invoice.list.previous_month"
    ]
    assert published
    q = published[0].canonical_question
    hit = try_precompiled_scenario(q, tenant_id="default", datasource_id="bi_reporting")
    assert hit is not None
    assert ":period_start" in hit["sqlTemplate"] or ":period_start" in hit["sql"]
    assert "2026-" in str(hit["parameters"].get("period_start") or hit["bindParams"].get("period_start"))
    # SQL template must not contain resolved date literals from params
    assert "2026-06-01" not in hit["sqlTemplate"]
