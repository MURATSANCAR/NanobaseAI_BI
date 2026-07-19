"""ARQ worker for schema scans and scenario builds."""

from __future__ import annotations

import os

from arq.connections import RedisSettings

from nanobase_api.application.schema_scans import execute_schema_scan
from nanobase_api.config import get_settings


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
    from nanobase_api.scenario_engine.application.build_pipeline import start_build
    from nanobase_api.scenario_engine.infrastructure.store import get_scenario_store

    store = get_scenario_store()
    result = start_build(
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        store=store,
        auto_publish=auto_publish,
    )
    # Preserve queued id if caller tracks it
    store.builds[build_id] = {**result, "id": build_id, "pipelineBuildId": result.get("id")}
    return build_id


async def run_scenario_embedding_publish(ctx, tenant_id: str, datasource_id: str) -> int:
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


class WorkerSettings:
    functions = [run_schema_scan, run_scenario_build, run_scenario_embedding_publish]
    redis_settings = RedisSettings.from_dsn(os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"))
    max_jobs = 2
    job_timeout = 900
