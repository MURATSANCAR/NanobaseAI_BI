"""End-to-end scenario build pipeline for a datasource."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from nanobase_api.scenario_engine.application.staged_pipeline import run_staged_build
from nanobase_api.scenario_engine.infrastructure.schema_snapshot import SchemaSnapshot
from nanobase_api.scenario_engine.infrastructure.store import ScenarioStore, get_scenario_store

ExecuteFn = Callable[[str, Optional[Dict[str, object]]], List[Dict[str, Any]]]


def start_build(
    *,
    tenant_id: str,
    datasource_id: str,
    store: ScenarioStore | None = None,
    snapshot: SchemaSnapshot | None = None,
    execute_fn: ExecuteFn | None = None,
    auto_publish: bool = True,
    semantic_version: str = "7.3.0",
    force: bool = False,
) -> dict[str, Any]:
    """Run the 8-stage pipeline synchronously (API sync fallback / tests)."""
    return run_staged_build(
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        store=store,
        snapshot=snapshot,
        execute_fn=execute_fn,
        auto_publish=auto_publish,
        semantic_version=semantic_version,
        force=force,
    )


def get_build(build_id: str, store: ScenarioStore | None = None) -> dict[str, Any] | None:
    store = store or get_scenario_store()
    return store.builds.get(build_id)
