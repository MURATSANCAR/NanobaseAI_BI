"""Runtime helper: match → resolve params → cached compile → gateway-ready payload."""

from __future__ import annotations

from typing import Any

from nanobase_api.scenario_engine.application.matcher import MatchResult, ScenarioMatcher
from nanobase_api.scenario_engine.application.param_resolver import resolve_parameters
from nanobase_api.scenario_engine.domain.status import is_retrieval_eligible
from nanobase_api.scenario_engine.infrastructure.compiler import get_compiler, render_sql
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
    """Return gateway-ready SQL payload or None to fall back to AWEL."""
    store = get_scenario_store()
    matcher = ScenarioMatcher(store=store)
    match: MatchResult = matcher.match(
        question,
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        financial_critical=financial_critical,
    )
    if not match.matched or match.route == "AWEL" or not match.scenario_id:
        store.record_usage(match.scenario_id or "_none", field="fallback_count")
        return None

    inst = store.get_instance(match.scenario_id)
    if inst is None or not is_retrieval_eligible(inst.status):
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
    if cached is None:
        comp = store.get_compilation(inst.id, dialect=dialect)
        if comp is None:
            compiled = get_compiler(dialect).compile(inst.logical_plan)
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

    # Materialize for gateway clients that don't yet accept named binds —
    # values are typed/validated; still must pass Query Gateway validate.
    sql = render_sql(cached.sql_template, binds)
    store.record_usage(inst.id, field="execution_count")

    return {
        "sql": sql,
        "sqlTemplate": cached.sql_template,
        "bindParams": binds,
        "scenarioId": inst.id,
        "scenarioCode": inst.scenario_code,
        "confidence": match.confidence,
        "route": match.route,
        "logicalPlan": inst.logical_plan.to_dict(),
        "astFingerprint": cached.ast_fingerprint,
        "schemaVersion": inst.schema_version,
        "semanticVersion": inst.semantic_version,
        "sqlSource": "precompiled_scenario",
    }
