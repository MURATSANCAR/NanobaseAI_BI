"""ARQ worker for schema scans and staged scenario builds."""

from __future__ import annotations

import os
from typing import Any

from arq.connections import RedisSettings

from nanobase_api.application.schema_scans import execute_schema_scan


async def run_schema_scan(ctx, scan_id: str, datasource_id: str, tenant_id: str) -> str:
    execute_schema_scan(scan_id, datasource_id, tenant_id)
    return scan_id


async def run_scenario_build(
    ctx,
    build_id: str,
    datasource_id: str,
    tenant_id: str,
    auto_publish: bool = True,
) -> str:
    """Full pipeline (compat) — also used as final orchestrator."""
    from nanobase_api.scenario_engine.application.build_pipeline import start_build
    from nanobase_api.scenario_engine.infrastructure.reporting_exec import reporting_dsn
    from nanobase_api.scenario_engine.infrastructure.schema_snapshot import (
        invoice_analytics_snapshot,
        snapshot_from_pg,
    )
    from nanobase_api.scenario_engine.infrastructure.store import get_scenario_store

    store = get_scenario_store()
    snap = invoice_analytics_snapshot()
    dsn = reporting_dsn()
    if dsn:
        try:
            snap = snapshot_from_pg(dsn, datasource_id=datasource_id)
        except Exception:
            pass
    result = start_build(
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        store=store,
        snapshot=snap,
        auto_publish=auto_publish,
        force=True,
    )
    store.builds[build_id] = {**result, "id": build_id, "pipelineBuildId": result.get("id")}
    return build_id


async def scenario_discovery(ctx, build_id: str, datasource_id: str, tenant_id: str) -> dict[str, Any]:
    from nanobase_api.scenario_engine.infrastructure.reporting_exec import reporting_dsn
    from nanobase_api.scenario_engine.infrastructure.schema_snapshot import (
        invoice_analytics_snapshot,
        snapshot_from_pg,
    )
    from nanobase_api.scenario_engine.infrastructure.semantic_classifier import classify_schema
    from nanobase_api.scenario_engine.infrastructure.store import get_scenario_store

    store = get_scenario_store()
    snap = invoice_analytics_snapshot()
    dsn = reporting_dsn()
    if dsn:
        try:
            snap = snapshot_from_pg(dsn, datasource_id=datasource_id)
        except Exception:
            pass
    clf = classify_schema(snap)
    store.builds[build_id] = {
        "id": build_id,
        "phase": "DISCOVERY",
        "schemaVersion": clf.schema_version,
        "tenantId": tenant_id,
        "datasourceId": datasource_id,
        "status": "RUNNING",
    }
    return {"schemaVersion": clf.schema_version, "tables": len(clf.tables)}


async def scenario_combination_generation(
    ctx, build_id: str, datasource_id: str, tenant_id: str
) -> dict[str, Any]:
    # Staged jobs ultimately call full build for consistency / idempotency
    return {"delegated": "run_scenario_build", "buildId": build_id}


async def scenario_sql_compilation(ctx, build_id: str, datasource_id: str, tenant_id: str) -> str:
    return build_id


async def scenario_static_validation(ctx, build_id: str, datasource_id: str, tenant_id: str) -> str:
    return build_id


async def scenario_execution_validation(ctx, build_id: str, datasource_id: str, tenant_id: str) -> str:
    return build_id


async def scenario_performance_validation(ctx, build_id: str, datasource_id: str, tenant_id: str) -> str:
    return build_id


async def scenario_question_generation(ctx, build_id: str, datasource_id: str, tenant_id: str) -> str:
    return build_id


async def scenario_embedding_publish(ctx, tenant_id: str, datasource_id: str) -> int:
    from nanobase_api.scenario_engine.domain.status import ScenarioStatus
    from nanobase_api.scenario_engine.infrastructure.qdrant_publisher import ScenarioQdrantPublisher
    from nanobase_api.scenario_engine.infrastructure.store import get_scenario_store

    store = get_scenario_store()
    instances = store.list_instances(
        tenant_id=tenant_id, datasource_id=datasource_id, status=ScenarioStatus.PUBLISHED
    )
    paraphrases = []
    for inst in instances:
        paraphrases.extend(
            [p for p in store.paraphrases_for_scenario(inst.id) if p.status == ScenarioStatus.PUBLISHED]
        )
    result = ScenarioQdrantPublisher().publish(instances=instances, paraphrases=paraphrases)
    return int(result.get("upserted") or 0)


async def run_scenario_embedding_publish(ctx, tenant_id: str, datasource_id: str) -> int:
    return await scenario_embedding_publish(ctx, tenant_id, datasource_id)


class WorkerSettings:
    functions = [
        run_schema_scan,
        run_scenario_build,
        scenario_discovery,
        scenario_combination_generation,
        scenario_sql_compilation,
        scenario_static_validation,
        scenario_execution_validation,
        scenario_performance_validation,
        scenario_question_generation,
        scenario_embedding_publish,
        run_scenario_embedding_publish,
    ]
    redis_settings = RedisSettings.from_dsn(os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"))
    max_jobs = 2
    job_timeout = 900
