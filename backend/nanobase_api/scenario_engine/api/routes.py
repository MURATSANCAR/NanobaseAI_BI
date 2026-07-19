"""Scenario engine API routes."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, Path, Query

from nanobase_api.scenario_engine.application.build_pipeline import get_build, start_build
from nanobase_api.scenario_engine.application.matcher import ScenarioMatcher
from nanobase_api.scenario_engine.application.runtime import try_precompiled_scenario
from nanobase_api.scenario_engine.application.seeds.invoice_slice import seed_invoice_scenario_slice
from nanobase_api.scenario_engine.domain.status import ScenarioStatus
from nanobase_api.scenario_engine.infrastructure.compiler import get_compiler
from nanobase_api.scenario_engine.infrastructure.metrics import snapshot as metrics_snapshot
from nanobase_api.scenario_engine.infrastructure.store import get_scenario_store
from nanobase_api.scenario_engine.infrastructure.validators import validate_static_ast

router = APIRouter(tags=["scenario-engine"])


@router.post("/api/v1/datasources/{datasource_id}/scenario-builds")
async def create_scenario_build(
    datasource_id: str = Path(...),
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    tenant_id = str(body.get("tenantId") or "default")
    auto_publish = bool(body.get("autoPublish", True))
    use_arq = bool(body.get("async", True))

    if use_arq:
        try:
            from nanobase_api.config import get_settings

            settings = get_settings()
            if getattr(settings, "arq_enabled", False):
                from arq import create_pool
                from arq.connections import RedisSettings
                import os

                redis = await create_pool(RedisSettings.from_dsn(os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")))
                build_id = f"build-queued-{datasource_id}"
                # Pre-create build record
                store = get_scenario_store()
                store.builds[build_id] = {
                    "id": build_id,
                    "tenantId": tenant_id,
                    "datasourceId": datasource_id,
                    "status": "QUEUED",
                    "phase": "QUEUED",
                }
                await redis.enqueue_job(
                    "run_scenario_build",
                    build_id,
                    datasource_id,
                    tenant_id,
                    auto_publish,
                )
                return {"buildId": build_id, "status": "QUEUED"}
        except Exception:
            pass

    # Sync / asyncio fallback
    result = await asyncio.to_thread(
        start_build,
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        auto_publish=auto_publish,
    )
    return {"buildId": result["id"], **result}


@router.get("/api/v1/datasources/{datasource_id}/scenario-builds/{build_id}")
async def scenario_build_status(
    datasource_id: str = Path(...),
    build_id: str = Path(...),
) -> dict[str, Any]:
    b = get_build(build_id)
    if not b or b.get("datasourceId") != datasource_id:
        return {"error": "NOT_FOUND", "buildId": build_id}
    return b


@router.get("/api/v1/datasources/{datasource_id}/suggested-questions")
async def suggested_questions(
    datasource_id: str = Path(...),
    tenant_id: str = Query(default="default"),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    store = get_scenario_store()
    items = store.suggested_questions(tenant_id=tenant_id, datasource_id=datasource_id, limit=limit)
    # Group by category
    by_cat: dict[str, list[str]] = {}
    for it in items:
        by_cat.setdefault(it["category"] or "Genel", []).append(it["question"])
    return {"datasourceId": datasource_id, "questions": items, "categories": by_cat}


@router.post("/api/v1/query-scenarios/match")
async def match_scenario(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    datasource_id = str(body.get("datasourceId") or "")
    question = str(body.get("question") or "")
    tenant_id = str(body.get("tenantId") or "default")
    matcher = ScenarioMatcher()
    result = matcher.match(question, tenant_id=tenant_id, datasource_id=datasource_id)
    return result.to_dict()


@router.post("/api/v1/query-scenarios/resolve")
async def resolve_scenario(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Match + compile + bind for chat/gateway use."""
    payload = try_precompiled_scenario(
        str(body.get("question") or ""),
        tenant_id=str(body.get("tenantId") or "default"),
        datasource_id=str(body.get("datasourceId") or ""),
        dialect=str(body.get("dialect") or "postgres"),
    )
    if payload is None:
        return {"matched": False, "route": "AWEL"}
    return {"matched": True, **payload}


@router.post("/api/v1/semantic/bootstrap/invoice-scenario-slice")
async def bootstrap_invoice_slice(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    return seed_invoice_scenario_slice(
        tenant_id=str(body.get("tenantId") or "default"),
        datasource_id=str(body.get("datasourceId") or "bi_reporting"),
        auto_publish=bool(body.get("autoPublish", True)),
    )


@router.post("/internal/v1/query-scenarios/{scenario_id}/compile")
async def compile_scenario(
    scenario_id: str = Path(...),
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    store = get_scenario_store()
    inst = store.get_instance(scenario_id)
    if inst is None:
        return {"error": "NOT_FOUND"}
    dialect = str(body.get("dialect") or "postgres")
    result = get_compiler(dialect).compile(inst.logical_plan)
    return result.to_dict()


@router.post("/internal/v1/query-scenarios/{scenario_id}/validate")
async def validate_scenario(scenario_id: str = Path(...)) -> dict[str, Any]:
    store = get_scenario_store()
    inst = store.get_instance(scenario_id)
    if inst is None:
        return {"error": "NOT_FOUND"}
    comp = store.get_compilation(scenario_id)
    if comp is None:
        compiled = get_compiler("postgres").compile(inst.logical_plan)
    else:
        from nanobase_api.scenario_engine.infrastructure.compiler import CompileResult

        compiled = CompileResult(
            sql_template=comp.sql_template,
            dialect=comp.dialect,
            ast_fingerprint=comp.ast_fingerprint,
            bind_params=comp.bind_params,
            logical_plan=inst.logical_plan.to_dict(),
        )
    static = validate_static_ast(inst.logical_plan, compiled)
    return {"scenarioId": scenario_id, "static": {"passed": static.passed, "detail": static.detail}}


@router.post("/internal/v1/query-scenarios/{scenario_id}/review")
async def review_scenario(
    scenario_id: str = Path(...),
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Tier B review stub — approve / reject."""
    store = get_scenario_store()
    inst = store.get_instance(scenario_id)
    if inst is None:
        return {"error": "NOT_FOUND"}
    decision = str(body.get("decision") or "").upper()
    if decision == "APPROVE" and inst.status == ScenarioStatus.READY_FOR_REVIEW:
        inst.transition_to(ScenarioStatus.APPROVED)
        store.save_instance(inst)
        return {"scenarioId": scenario_id, "status": inst.status.value}
    if decision == "REJECT" and inst.status in (
        ScenarioStatus.READY_FOR_REVIEW,
        ScenarioStatus.APPROVED,
    ):
        inst.transition_to(ScenarioStatus.REJECTED)
        store.save_instance(inst)
        return {"scenarioId": scenario_id, "status": inst.status.value}
    return {"error": "INVALID_DECISION", "status": inst.status.value, "riskTier": inst.risk_tier.value}


@router.get("/api/v1/query-scenarios/metrics")
async def scenario_metrics() -> dict[str, Any]:
    return metrics_snapshot()


@router.get("/api/v1/query-scenarios/metrics/prometheus")
async def scenario_metrics_prometheus():
    from fastapi.responses import PlainTextResponse

    from nanobase_api.scenario_engine.infrastructure.prometheus import render_prometheus

    return PlainTextResponse(render_prometheus(), media_type="text/plain; version=0.0.4")


@router.get("/api/v1/query-scenarios/reviews")
async def list_scenario_reviews(
    datasource_id: str = Query(...),
    tenant_id: str = Query(default="default"),
) -> dict[str, Any]:
    """Tier B scenarios awaiting review."""
    store = get_scenario_store()
    items = store.list_instances(
        tenant_id=tenant_id, datasource_id=datasource_id, status=ScenarioStatus.READY_FOR_REVIEW
    )
    return {
        "items": [
            {
                "scenarioId": i.id,
                "scenarioCode": i.scenario_code,
                "family": i.family,
                "riskTier": i.risk_tier.value,
                "canonicalQuestion": i.canonical_question,
                "status": i.status.value,
            }
            for i in items
        ]
    }
