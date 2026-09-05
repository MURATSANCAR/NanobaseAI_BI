"""ARQ worker for schema scans and staged scenario builds."""

from __future__ import annotations

import os
from typing import Any

from arq.connections import RedisSettings

from nanobase_api.application.schema_scans import execute_schema_scan
from nanobase_api.scenario_engine.application.staged_pipeline import STAGE_CHAIN


async def run_schema_scan(ctx, scan_id: str, datasource_id: str, tenant_id: str) -> str:
    execute_schema_scan(scan_id, datasource_id, tenant_id)
    return scan_id


async def _enqueue_next(
    ctx,
    current: str,
    build_id: str,
    datasource_id: str,
    tenant_id: str,
    auto_publish: bool = True,
) -> None:
    try:
        idx = STAGE_CHAIN.index(current)
    except ValueError:
        return
    if idx + 1 >= len(STAGE_CHAIN):
        return
    nxt = STAGE_CHAIN[idx + 1]
    redis = ctx.get("redis")
    if redis is None:
        return
    if nxt == "scenario_embedding_publish":
        await redis.enqueue_job(
            nxt,
            build_id,
            datasource_id,
            tenant_id,
            auto_publish,
        )
    else:
        await redis.enqueue_job(nxt, build_id, datasource_id, tenant_id, auto_publish)


def _should_continue(build: dict[str, Any]) -> bool:
    if build.get("status") == "FAILED":
        return False
    if build.get("skipRemaining"):
        return False
    return True


async def run_scenario_build(
    ctx,
    build_id: str,
    datasource_id: str,
    tenant_id: str,
    auto_publish: bool = True,
) -> str:
    """Orchestrator: only enqueue the stage chain (does not run work inline)."""
    from nanobase_api.scenario_engine.application.staged_pipeline import ensure_build
    from nanobase_api.scenario_engine.infrastructure.store import get_scenario_store

    store = get_scenario_store()
    ensure_build(store, build_id=build_id, tenant_id=tenant_id, datasource_id=datasource_id)
    store.builds[build_id]["status"] = "QUEUED"
    store.builds[build_id]["phase"] = "QUEUED"
    redis = ctx.get("redis")
    if redis is not None:
        await redis.enqueue_job(
            "scenario_discovery",
            build_id,
            datasource_id,
            tenant_id,
            auto_publish,
        )
    else:
        # Fallback: sync full pipeline when redis missing in ctx
        from nanobase_api.scenario_engine.application.staged_pipeline import run_staged_build

        run_staged_build(
            tenant_id=tenant_id,
            datasource_id=datasource_id,
            store=store,
            auto_publish=auto_publish,
            force=True,
            build_id=build_id,
        )
    return build_id


async def scenario_discovery(
    ctx, build_id: str, datasource_id: str, tenant_id: str, auto_publish: bool = True
) -> dict[str, Any]:
    from nanobase_api.scenario_engine.application.staged_pipeline import stage_discovery
    from nanobase_api.scenario_engine.infrastructure.store import get_scenario_store

    store = get_scenario_store()
    result = stage_discovery(
        build_id=build_id, tenant_id=tenant_id, datasource_id=datasource_id, store=store
    )
    if _should_continue(result):
        await _enqueue_next(ctx, "scenario_discovery", build_id, datasource_id, tenant_id, auto_publish)
    return {"phase": result.get("phase"), "status": result.get("status")}


async def scenario_combination_generation(
    ctx, build_id: str, datasource_id: str, tenant_id: str, auto_publish: bool = True
) -> dict[str, Any]:
    from nanobase_api.scenario_engine.application.staged_pipeline import stage_combination
    from nanobase_api.scenario_engine.infrastructure.store import get_scenario_store

    store = get_scenario_store()
    result = stage_combination(
        build_id=build_id,
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        store=store,
        force=True,
    )
    if _should_continue(result):
        await _enqueue_next(
            ctx, "scenario_combination_generation", build_id, datasource_id, tenant_id, auto_publish
        )
    return {"phase": result.get("phase"), "candidates": (result.get("counts") or {}).get("candidates")}


async def scenario_sql_compilation(
    ctx, build_id: str, datasource_id: str, tenant_id: str, auto_publish: bool = True
) -> dict[str, Any]:
    from nanobase_api.scenario_engine.application.staged_pipeline import stage_sql_compilation
    from nanobase_api.scenario_engine.infrastructure.store import get_scenario_store

    result = stage_sql_compilation(build_id=build_id, store=get_scenario_store())
    if _should_continue(result):
        await _enqueue_next(
            ctx, "scenario_sql_compilation", build_id, datasource_id, tenant_id, auto_publish
        )
    return {"phase": result.get("phase")}


async def scenario_static_validation(
    ctx, build_id: str, datasource_id: str, tenant_id: str, auto_publish: bool = True
) -> dict[str, Any]:
    from nanobase_api.scenario_engine.application.staged_pipeline import stage_static_validation
    from nanobase_api.scenario_engine.infrastructure.store import get_scenario_store

    result = stage_static_validation(build_id=build_id, store=get_scenario_store())
    if _should_continue(result):
        await _enqueue_next(
            ctx, "scenario_static_validation", build_id, datasource_id, tenant_id, auto_publish
        )
    return {"phase": result.get("phase")}


async def scenario_execution_validation(
    ctx, build_id: str, datasource_id: str, tenant_id: str, auto_publish: bool = True
) -> dict[str, Any]:
    from nanobase_api.scenario_engine.application.staged_pipeline import stage_execution_validation
    from nanobase_api.scenario_engine.infrastructure.store import get_scenario_store

    result = stage_execution_validation(build_id=build_id, store=get_scenario_store())
    if _should_continue(result):
        await _enqueue_next(
            ctx, "scenario_execution_validation", build_id, datasource_id, tenant_id, auto_publish
        )
    return {"phase": result.get("phase")}


async def scenario_performance_validation(
    ctx, build_id: str, datasource_id: str, tenant_id: str, auto_publish: bool = True
) -> dict[str, Any]:
    from nanobase_api.scenario_engine.application.staged_pipeline import stage_performance_validation
    from nanobase_api.scenario_engine.infrastructure.store import get_scenario_store

    result = stage_performance_validation(build_id=build_id, store=get_scenario_store())
    if _should_continue(result):
        await _enqueue_next(
            ctx, "scenario_performance_validation", build_id, datasource_id, tenant_id, auto_publish
        )
    return {"phase": result.get("phase")}


async def scenario_question_generation(
    ctx, build_id: str, datasource_id: str, tenant_id: str, auto_publish: bool = True
) -> dict[str, Any]:
    from nanobase_api.scenario_engine.application.staged_pipeline import stage_question_generation
    from nanobase_api.scenario_engine.infrastructure.store import get_scenario_store

    result = stage_question_generation(build_id=build_id, store=get_scenario_store())
    if _should_continue(result):
        await _enqueue_next(
            ctx, "scenario_question_generation", build_id, datasource_id, tenant_id, auto_publish
        )
    return {"phase": result.get("phase"), "paraphrases": (result.get("counts") or {}).get("paraphrases")}


async def scenario_embedding_publish(
    ctx,
    build_id: str,
    datasource_id: str,
    tenant_id: str,
    auto_publish: bool = True,
) -> dict[str, Any]:
    from nanobase_api.scenario_engine.application.staged_pipeline import stage_embedding_publish
    from nanobase_api.scenario_engine.infrastructure.store import get_scenario_store

    result = stage_embedding_publish(
        build_id=build_id,
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        store=get_scenario_store(),
        auto_publish=auto_publish,
    )
    return {"phase": result.get("phase"), "status": result.get("status"), "batch": result.get("batch")}


async def run_scenario_embedding_publish(ctx, tenant_id: str, datasource_id: str) -> int:
    """Compat helper: republish embeddings for already-published scenarios."""
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


async def run_forecast_reconcile(ctx, limit: int = 200) -> str:
    """Forecasting V1 Faz 6.1 — compare closed periods with stored forecasts."""
    import json as _json

    from nanobase_api.app import _meta_engine
    from nanobase_api.application.forecast_chat import reconcile_forecasts

    stats = await reconcile_forecasts(_meta_engine(), limit=limit)
    return _json.dumps(stats)


class WorkerSettings:
    functions = [
        run_forecast_reconcile,
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
