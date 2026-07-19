"""Bootstrap invoice vertical slice — run build pipeline against analytics snapshot."""

from __future__ import annotations

from typing import Any

from nanobase_api.scenario_engine.application.build_pipeline import start_build
from nanobase_api.scenario_engine.infrastructure.schema_snapshot import invoice_analytics_snapshot
from nanobase_api.scenario_engine.infrastructure.store import ScenarioStore, get_scenario_store


def seed_invoice_scenario_slice(
    *,
    tenant_id: str = "default",
    datasource_id: str = "bi_reporting",
    store: ScenarioStore | None = None,
    auto_publish: bool = True,
) -> dict[str, Any]:
    store = store or get_scenario_store()
    return start_build(
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        store=store,
        snapshot=invoice_analytics_snapshot(),
        auto_publish=auto_publish,
        semantic_version="7.3.0",
    )
