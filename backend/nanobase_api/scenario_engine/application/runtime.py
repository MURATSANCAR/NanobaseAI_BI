"""Runtime helper: match → resolve params → cached template → gateway-ready binds."""

from __future__ import annotations

from typing import Any

from nanobase_api.scenario_engine.application.followups import followup_suggestions
from nanobase_api.scenario_engine.application.matcher import MatchResult, ScenarioMatcher
from nanobase_api.scenario_engine.application.param_resolver import resolve_parameters
from nanobase_api.scenario_engine.domain.status import ScenarioStatus, is_retrieval_eligible
from nanobase_api.scenario_engine.infrastructure.compiler import get_compiler
from nanobase_api.scenario_engine.infrastructure.metrics import (
    SCENARIO_CACHE_HIT,
    SCENARIO_FALLBACK_AWEL,
    SCENARIO_RUNTIME_FAILURES,
    inc,
)
from nanobase_api.scenario_engine.infrastructure.redis_cache import (
    CachedPlan,
    cache_key,
    get_plan_cache,
)
from nanobase_api.scenario_engine.infrastructure.store import get_scenario_store


def try_precompiled_scenario(
    question: str,
    *,
    tenant_id: str,
    datasource_id: str,
    dialect: str = "postgres",
    financial_critical: bool = False,
) -> dict[str, Any] | None:
    """Return gateway-ready template + bind params, or None to fall back to AWEL.

    Never string-concatenates parameters into SQL for the chat/execute path.
    """
    store = get_scenario_store()
    matcher = ScenarioMatcher(store=store)
    match: MatchResult = matcher.match(
        question,
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        financial_critical=financial_critical,
    )
    if not match.matched or match.route == "AWEL" or not match.scenario_id:
        inc(SCENARIO_FALLBACK_AWEL)
        if match.scenario_id:
            store.record_usage(match.scenario_id, field="fallback_count")
        return None

    inst = store.get_instance(match.scenario_id)
    if inst is None or not is_retrieval_eligible(inst.status):
        inc(SCENARIO_RUNTIME_FAILURES)
        return None
    if inst.status == ScenarioStatus.STALE:
        inc(SCENARIO_RUNTIME_FAILURES)
        return None

    params = resolve_parameters(question, inst.logical_plan)
    binds = params.to_bind_dict()

    cache = get_plan_cache()
    key = cache_key(
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        scenario_id=inst.id,
        dialect=dialect,
        schema_version=inst.schema_version,
        semantic_version=inst.semantic_version,
        policy_version=inst.policy_version,
    )
    cached = cache.get(key)
    if cached is not None:
        inc(SCENARIO_CACHE_HIT)
    else:
        comp = store.get_compilation(inst.id, dialect=dialect)
        if comp is None:
            try:
                compiled = get_compiler(dialect).compile(inst.logical_plan)
            except Exception:
                inc(SCENARIO_RUNTIME_FAILURES)
                return None
            sql_template = compiled.sql_template
            ast_fp = compiled.ast_fingerprint
            bind_params = compiled.bind_params
        else:
            sql_template = comp.sql_template
            ast_fp = comp.ast_fingerprint
            bind_params = comp.bind_params
        cached = CachedPlan(
            scenario_id=inst.id,
            dialect=dialect,
            sql_template=sql_template,
            ast_fingerprint=ast_fp,
            schema_version=inst.schema_version,
            semantic_version=inst.semantic_version,
            policy_version=inst.policy_version,
            bind_params=bind_params,
        )
        cache.put(key, cached)

    store.record_usage(inst.id, field="execution_count")

    return {
        "sql": cached.sql_template,  # template with :binds — Gateway executes with parameters
        "sqlTemplate": cached.sql_template,
        "bindParams": binds,
        "parameters": binds,
        "scenarioId": inst.id,
        "scenarioCode": inst.scenario_code,
        "confidence": match.confidence,
        "route": match.route,
        "logicalPlan": inst.logical_plan.to_dict(),
        "astFingerprint": cached.ast_fingerprint,
        "schemaVersion": inst.schema_version,
        "semanticVersion": inst.semantic_version,
        "sqlSource": "precompiled_scenario",
        "followUps": followup_suggestions(inst.logical_plan),
    }
