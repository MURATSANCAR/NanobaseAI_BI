"""Write-through scenario store tests."""

from __future__ import annotations

from nanobase_api.scenario_engine.application.build_pipeline import start_build
from nanobase_api.scenario_engine.domain.status import ScenarioStatus
from nanobase_api.scenario_engine.infrastructure.schema_snapshot import invoice_analytics_snapshot
from nanobase_api.scenario_engine.infrastructure.store import reset_scenario_store


class FakeScenarioSql:
    def __init__(self) -> None:
        self.instances: list[str] = []
        self.paraphrases: list[str] = []
        self.compilations: list[str] = []
        self.batches: list[str] = []
        self.active: list[tuple] = []

    def tables_ready(self) -> bool:
        return True

    def upsert_instance(self, inst) -> None:
        self.instances.append(inst.scenario_code)

    def upsert_paraphrase(self, p) -> None:
        self.paraphrases.append(p.text)

    def upsert_compilation(self, c) -> None:
        self.compilations.append(c.scenario_id)

    def upsert_batch(self, b) -> None:
        self.batches.append(b.id)

    def set_active_version(self, tenant_id, datasource_id, batch_id, schema_version, semantic_version) -> None:
        self.active.append((tenant_id, datasource_id, batch_id))

    def save_usage(self, scenario_id, usage, *, tenant_id, datasource_id) -> None:
        pass

    def hydrate(self) -> dict:
        return {
            "instances": {},
            "paraphrases": {},
            "compilations": {},
            "batches": {},
            "active_version": {},
            "usage": {},
        }


def test_write_through_on_build():
    store = reset_scenario_store()
    fake = FakeScenarioSql()
    store.attach_sql(fake, hydrate=False)
    result = start_build(
        tenant_id="default",
        datasource_id="bi_reporting",
        store=store,
        snapshot=invoice_analytics_snapshot(),
        auto_publish=True,
        force=True,
    )
    assert result["status"] == "COMPLETED"
    assert fake.instances
    assert fake.paraphrases
    assert fake.compilations
    assert fake.batches
    assert fake.active


def test_cross_tenant_exact_match_zero():
    store = reset_scenario_store()
    start_build(
        tenant_id="t1",
        datasource_id="bi_reporting",
        store=store,
        snapshot=invoice_analytics_snapshot(),
        auto_publish=True,
        force=True,
    )
    published = store.list_instances(
        tenant_id="t1", datasource_id="bi_reporting", status=ScenarioStatus.PUBLISHED
    )
    assert published
    q = store.paraphrases_for_scenario(published[0].id)[0].text
    from nanobase_api.scenario_engine.application.matcher import ScenarioMatcher

    m = ScenarioMatcher(store=store).match(q, tenant_id="other_tenant", datasource_id="bi_reporting")
    assert m.matched is False
