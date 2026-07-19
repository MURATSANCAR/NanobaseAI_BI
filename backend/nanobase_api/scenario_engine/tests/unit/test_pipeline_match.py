"""Build pipeline + matcher integration (in-memory)."""

from __future__ import annotations

from nanobase_api.scenario_engine.application.build_pipeline import start_build
from nanobase_api.scenario_engine.application.matcher import ScenarioMatcher
from nanobase_api.scenario_engine.application.param_resolver import resolve_parameters
from nanobase_api.scenario_engine.application.runtime import try_precompiled_scenario
from nanobase_api.scenario_engine.domain.status import ScenarioStatus
from nanobase_api.scenario_engine.infrastructure.schema_snapshot import invoice_analytics_snapshot
from nanobase_api.scenario_engine.infrastructure.store import reset_scenario_store


def test_invoice_build_publishes_tier_a():
    store = reset_scenario_store()
    result = start_build(
        tenant_id="default",
        datasource_id="bi_reporting",
        store=store,
        snapshot=invoice_analytics_snapshot(),
        auto_publish=True,
    )
    assert result["status"] == "COMPLETED"
    published = store.list_instances(
        tenant_id="default", datasource_id="bi_reporting", status=ScenarioStatus.PUBLISHED
    )
    assert len(published) >= 5
    assert store.get_active_batch_id("default", "bi_reporting")


def test_exact_match_previous_month():
    store = reset_scenario_store()
    start_build(
        tenant_id="default",
        datasource_id="bi_reporting",
        store=store,
        snapshot=invoice_analytics_snapshot(),
        auto_publish=True,
    )
    matcher = ScenarioMatcher(store=store)
    # Use a generated canonical/paraphrase text
    published = store.list_instances(
        tenant_id="default", datasource_id="bi_reporting", status=ScenarioStatus.PUBLISHED
    )
    target = next(i for i in published if "previous_month" in i.scenario_code and i.family == "LIST_ENTITY")
    paras = store.paraphrases_for_scenario(target.id)
    assert paras
    m = matcher.match(
        paras[0].text,
        tenant_id="default",
        datasource_id="bi_reporting",
    )
    assert m.matched
    assert m.route == "PRECOMPILED_SCENARIO"
    assert m.scenario_id == target.id


def test_runtime_resolves_sql():
    store = reset_scenario_store()
    start_build(
        tenant_id="default",
        datasource_id="bi_reporting",
        store=store,
        snapshot=invoice_analytics_snapshot(),
        auto_publish=True,
    )
    published = store.list_instances(
        tenant_id="default", datasource_id="bi_reporting", status=ScenarioStatus.PUBLISHED
    )
    target = next(i for i in published if i.scenario_code == "invoice.list.previous_month")
    q = target.canonical_question
    payload = try_precompiled_scenario(
        q, tenant_id="default", datasource_id="bi_reporting"
    )
    assert payload is not None
    assert "SELECT" in payload["sql"].upper()
    assert "precompiled_scenario" == payload["sqlSource"]


def test_param_resolver_previous_month():
    from nanobase_api.scenario_engine.domain.logical_plan import LogicalPlan
    from datetime import datetime
    from zoneinfo import ZoneInfo

    plan = LogicalPlan(
        family="LIST_ENTITY",
        entity="invoice",
        period="PREVIOUS_MONTH",
        date_column="analytics.invoices.invoice_date",
        physical_table="analytics.invoices",
    )
    p = resolve_parameters(
        "Geçen aya ait faturaları getir.",
        plan,
        now=datetime(2026, 7, 19, 12, 0, tzinfo=ZoneInfo("Europe/Istanbul")),
    )
    assert p.period_start is not None
    assert p.period_start.month == 6
    assert p.period_end.month == 7


def test_stale_on_column_dependency():
    store = reset_scenario_store()
    start_build(
        tenant_id="default",
        datasource_id="bi_reporting",
        store=store,
        snapshot=invoice_analytics_snapshot(),
        auto_publish=True,
    )
    stale = store.mark_stale_by_column(
        "default", "bi_reporting", "analytics.invoices.invoice_date"
    )
    assert stale
    for sid in stale:
        assert store.get_instance(sid).status == ScenarioStatus.STALE
