"""Classifier, combination, compiler, status machine tests."""

from __future__ import annotations

import pytest

from nanobase_api.scenario_engine.domain.errors import InvalidTransitionError
from nanobase_api.scenario_engine.domain.status import ScenarioStatus, transition
from nanobase_api.scenario_engine.infrastructure.combination import plan_invoice_combinations
from nanobase_api.scenario_engine.infrastructure.compiler import (
    PostgresLogicalPlanCompiler,
    get_compiler,
)
from nanobase_api.scenario_engine.infrastructure.relationship_graph import build_relationship_graph
from nanobase_api.scenario_engine.infrastructure.schema_snapshot import invoice_analytics_snapshot
from nanobase_api.scenario_engine.infrastructure.semantic_classifier import classify_schema
from nanobase_api.scenario_engine.infrastructure.validators import validate_static_ast


def test_invoice_classification_business_date():
    snap = invoice_analytics_snapshot()
    clf = classify_schema(snap)
    inv = clf.entity_map()["invoice"]
    assert inv.business_date == "analytics.invoices.invoice_date"
    assert inv.dates.get("dueDate") == "analytics.invoices.due_date"


def test_combination_pruned_not_cartesian():
    snap = invoice_analytics_snapshot()
    clf = classify_schema(snap)
    graph = build_relationship_graph(snap)
    planned = plan_invoice_combinations(clf, graph)
    assert 10 <= len(planned) <= 200
    codes = {p.scenario_code for p in planned}
    assert "invoice.list.previous_month" in codes
    assert "invoice.list.unpaid" in codes


def test_postgres_compile_list_period_binds():
    snap = invoice_analytics_snapshot()
    clf = classify_schema(snap)
    graph = build_relationship_graph(snap)
    planned = plan_invoice_combinations(clf, graph)
    target = next(p for p in planned if p.scenario_code == "invoice.list.previous_month")
    compiled = PostgresLogicalPlanCompiler().compile(target.logical_plan)
    assert ":period_start" in compiled.sql_template
    assert ":period_end" in compiled.sql_template
    assert "LIMIT :fetch_limit" in compiled.sql_template
    assert "SUM(" not in compiled.sql_template.upper() or "LIST" in target.family.value
    static = validate_static_ast(target.logical_plan, compiled)
    assert static.passed, static.detail


def test_no_sum_on_identifier():
    from nanobase_api.scenario_engine.domain.logical_plan import LogicalPlan

    plan = LogicalPlan(
        family="SUM_MEASURE",
        entity="invoice",
        aggregation="SUM",
        metric_column="analytics.invoices.invoice_id",
        physical_table="analytics.invoices",
        period="TODAY",
        date_column="analytics.invoices.invoice_date",
        mandatory_filters=["exclude_cancelled_invoices"],
        # status_column must be explicit since the 2026-08-11 fix — the
        # compiler refuses to guess it (that guess produced 219 broken
        # published erp scenarios). This test is about the SUM-on-identifier
        # static rule, so provide a valid one.
        extra={"status_column": "status"},
    )
    compiled = PostgresLogicalPlanCompiler().compile(plan)
    static = validate_static_ast(plan, compiled)
    assert not static.passed


def test_generated_to_published_forbidden():
    with pytest.raises(InvalidTransitionError):
        transition(ScenarioStatus.GENERATED, ScenarioStatus.PUBLISHED)


def test_oracle_stub_raises():
    from nanobase_api.scenario_engine.domain.errors import ValidationError
    from nanobase_api.scenario_engine.domain.logical_plan import LogicalPlan

    plan = LogicalPlan(family="COUNT_ENTITY", entity="invoice", physical_table="analytics.invoices")
    with pytest.raises(ValidationError):
        get_compiler("oracle").compile(plan)
