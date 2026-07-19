"""ARQ-aligned 8-stage scenario build pipeline (sync stage bodies)."""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

from nanobase_api.scenario_engine import GENERATOR_VERSION
from nanobase_api.scenario_engine.domain.risk import RiskTier
from nanobase_api.scenario_engine.domain.scenario import (
    ScenarioCompilation,
    ScenarioInstance,
    ScenarioParaphrase,
)
from nanobase_api.scenario_engine.domain.status import ScenarioStatus
from nanobase_api.scenario_engine.application.param_resolver import resolve_parameters
from nanobase_api.scenario_engine.application.publisher import AtomicPublisher
from nanobase_api.scenario_engine.infrastructure.baselines import apply_baseline_sql, assert_scenario_baseline
from nanobase_api.scenario_engine.infrastructure.combination import (
    new_scenario_id,
    plan_invoice_combinations,
)
from nanobase_api.scenario_engine.infrastructure.compiler import get_compiler
from nanobase_api.scenario_engine.infrastructure.metrics import (
    SCENARIO_CANDIDATES_GENERATED,
    SCENARIO_EXECUTION_VALIDATION_FAILURES,
    SCENARIO_PERFORMANCE_VALIDATION_FAILURES,
    SCENARIO_PUBLISHED,
    SCENARIO_STATIC_VALIDATION_FAILURES,
    inc,
)
from nanobase_api.scenario_engine.infrastructure.question_grammar import (
    canonical_question,
    generate_questions,
)
from nanobase_api.scenario_engine.infrastructure.relationship_graph import build_relationship_graph
from nanobase_api.scenario_engine.infrastructure.reporting_exec import make_reporting_execute_fn, reporting_dsn
from nanobase_api.scenario_engine.infrastructure.schema_snapshot import (
    SchemaSnapshot,
    invoice_analytics_snapshot,
    snapshot_from_pg,
)
from nanobase_api.scenario_engine.infrastructure.semantic_classifier import classify_schema
from nanobase_api.scenario_engine.infrastructure.store import ScenarioStore, get_scenario_store
from nanobase_api.scenario_engine.infrastructure.validators import (
    new_run_id,
    run_differential_for_plan,
    run_execution_baseline,
    run_metamorphic_invoice_checks,
    validate_gateway_template,
    validate_performance,
    validate_period_properties,
    validate_static_ast,
    run_explain_cost_check,
)

ExecuteFn = Callable[[str, Optional[Dict[str, object]]], List[Dict[str, Any]]]

STAGE_CHAIN = (
    "scenario_discovery",
    "scenario_combination_generation",
    "scenario_sql_compilation",
    "scenario_static_validation",
    "scenario_execution_validation",
    "scenario_performance_validation",
    "scenario_question_generation",
    "scenario_embedding_publish",
)


def _build_ctx(store: ScenarioStore, build_id: str) -> dict[str, Any]:
    b = store.builds.get(build_id)
    if not b:
        raise RuntimeError(f"Unknown build {build_id}")
    return b


def _fail(store: ScenarioStore, build_id: str, error: str) -> dict[str, Any]:
    b = store.builds.setdefault(build_id, {"id": build_id})
    b["status"] = "FAILED"
    b["error"] = error[:500]
    b["finishedAt"] = datetime.utcnow().isoformat() + "Z"
    return b


def _set_phase(store: ScenarioStore, build_id: str, phase: str, **extra: Any) -> dict[str, Any]:
    b = store.builds.setdefault(build_id, {"id": build_id})
    b["phase"] = phase
    b["status"] = b.get("status") or "RUNNING"
    b.update(extra)
    return b


def ensure_build(
    store: ScenarioStore,
    *,
    build_id: str,
    tenant_id: str,
    datasource_id: str,
) -> dict[str, Any]:
    b = store.builds.get(build_id)
    if b is None:
        b = {
            "id": build_id,
            "tenantId": tenant_id,
            "datasourceId": datasource_id,
            "status": "RUNNING",
            "phase": "QUEUED",
            "startedAt": datetime.utcnow().isoformat() + "Z",
            "counts": {},
            "error": None,
            "workspace": {},
        }
        store.builds[build_id] = b
    b.setdefault("workspace", {})
    b.setdefault("counts", {})
    return b


def stage_discovery(
    *,
    build_id: str,
    tenant_id: str,
    datasource_id: str,
    store: ScenarioStore | None = None,
    snapshot: SchemaSnapshot | None = None,
) -> dict[str, Any]:
    store = store or get_scenario_store()
    b = ensure_build(store, build_id=build_id, tenant_id=tenant_id, datasource_id=datasource_id)
    try:
        snap = snapshot
        if snap is None:
            snap = invoice_analytics_snapshot()
            dsn = reporting_dsn()
            if dsn:
                try:
                    snap = snapshot_from_pg(dsn, datasource_id=datasource_id)
                except Exception:
                    pass
        snap.datasource_id = datasource_id
        classification = classify_schema(snap)
        graph = build_relationship_graph(snap)
        b["workspace"]["schemaVersion"] = classification.schema_version
        b["workspace"]["classification"] = classification
        b["workspace"]["graph"] = graph
        b["workspace"]["snapshot"] = snap
        b["schemaVersion"] = classification.schema_version
        return _set_phase(store, build_id, "DISCOVERY")
    except Exception as e:
        return _fail(store, build_id, f"discovery: {e}")


def stage_combination(
    *,
    build_id: str,
    tenant_id: str,
    datasource_id: str,
    store: ScenarioStore | None = None,
    force: bool = True,
    semantic_version: str = "7.3.0",
) -> dict[str, Any]:
    store = store or get_scenario_store()
    b = _build_ctx(store, build_id)
    if b.get("status") == "FAILED":
        return b
    try:
        classification = b["workspace"]["classification"]
        graph = b["workspace"]["graph"]
        if not force:
            existing = [
                i
                for i in store.list_instances(
                    tenant_id=tenant_id, datasource_id=datasource_id, status=ScenarioStatus.PUBLISHED
                )
                if i.schema_version == classification.schema_version
                and i.generator_version == GENERATOR_VERSION
            ]
            if existing and store.get_active_batch_id(tenant_id, datasource_id):
                b["status"] = "COMPLETED"
                b["phase"] = "IDEMPOTENT_SKIP"
                b["counts"]["published"] = len(existing)
                b["finishedAt"] = datetime.utcnow().isoformat() + "Z"
                b["skipRemaining"] = True
                return b

        planned = plan_invoice_combinations(classification, graph)
        # Domain rollout extras (customer…finance) when unlocked
        try:
            from nanobase_api.scenario_engine.application.seeds.domain_rollout import (
                plan_unlocked_domain_combinations,
            )

            planned = planned + plan_unlocked_domain_combinations(classification, graph)
        except Exception:
            pass

        prop = validate_period_properties(now=datetime.now(ZoneInfo("Europe/Istanbul")))
        if not prop.passed:
            raise RuntimeError(f"Period property tests failed: {prop.detail}")

        instances: list[ScenarioInstance] = []
        for p in planned:
            if p.risk_tier == RiskTier.D:
                continue
            sid = new_scenario_id()
            cq = canonical_question(p.logical_plan)
            inst = ScenarioInstance(
                id=sid,
                tenant_id=tenant_id,
                datasource_id=datasource_id,
                scenario_code=p.scenario_code,
                family=p.family.value,
                logical_plan=p.logical_plan,
                schema_version=classification.schema_version,
                semantic_version=semantic_version,
                risk_tier=p.risk_tier,
                status=ScenarioStatus.DISCOVERED,
                category=p.category,
                canonical_question=cq,
                generator_version=GENERATOR_VERSION,
            )
            inst.transition_to(ScenarioStatus.GENERATED)
            store.save_instance(inst)
            instances.append(inst)

        b["workspace"]["instanceIds"] = [i.id for i in instances]
        b["workspace"]["plannedCodes"] = {i.id: i.scenario_code for i in instances}
        b["counts"]["candidates"] = len(instances)
        inc(SCENARIO_CANDIDATES_GENERATED, float(len(instances)))
        return _set_phase(store, build_id, "GENERATED")
    except Exception as e:
        return _fail(store, build_id, f"combination: {e}")


def stage_sql_compilation(
    *,
    build_id: str,
    store: ScenarioStore | None = None,
    dialect: str = "postgres",
) -> dict[str, Any]:
    store = store or get_scenario_store()
    b = _build_ctx(store, build_id)
    if b.get("status") == "FAILED" or b.get("skipRemaining"):
        return b
    try:
        compiler = get_compiler(dialect)
        compilations: list[str] = []
        for sid in b["workspace"].get("instanceIds") or []:
            inst = store.get_instance(sid)
            if inst is None:
                continue
            compiled = compiler.compile(inst.logical_plan)
            comp = ScenarioCompilation(
                id=f"cmp-{uuid.uuid4().hex[:12]}",
                scenario_id=sid,
                dialect=dialect,
                sql_template=compiled.sql_template,
                ast_fingerprint=compiled.ast_fingerprint,
                validation_status="PENDING",
                bind_params=compiled.bind_params,
            )
            store.save_compilation(comp)
            compilations.append(comp.id)
            b["workspace"].setdefault("compiled", {})[sid] = compiled
        b["counts"]["compilations"] = len(compilations)
        return _set_phase(store, build_id, "COMPILED")
    except Exception as e:
        return _fail(store, build_id, f"sql_compilation: {e}")


def stage_static_validation(*, build_id: str, store: ScenarioStore | None = None) -> dict[str, Any]:
    store = store or get_scenario_store()
    b = _build_ctx(store, build_id)
    if b.get("status") == "FAILED" or b.get("skipRemaining"):
        return b
    try:
        passed_ids: list[str] = []
        for sid in b["workspace"].get("instanceIds") or []:
            inst = store.get_instance(sid)
            compiled = (b["workspace"].get("compiled") or {}).get(sid)
            if inst is None or compiled is None:
                continue
            inst.transition_to(ScenarioStatus.STATIC_VALIDATING)
            static = validate_static_ast(inst.logical_plan, compiled)
            gw = validate_gateway_template(compiled.sql_template, compiled.bind_params)
            if not static.passed or not gw.passed:
                inc(SCENARIO_STATIC_VALIDATION_FAILURES)
                inst.transition_to(ScenarioStatus.FAILED)
                store.save_instance(inst)
                continue
            inst.transition_to(ScenarioStatus.STATIC_VALIDATED)
            store.save_instance(inst)
            passed_ids.append(sid)
            if store.sql_repo is not None and hasattr(store.sql_repo, "save_validation_run"):
                try:
                    store.sql_repo.save_validation_run(
                        run_id=new_run_id(),
                        scenario_id=sid,
                        layer="STATIC",
                        passed=True,
                        detail={"static": static.detail, "gateway": gw.detail},
                    )
                except Exception:
                    pass
        b["workspace"]["staticPassedIds"] = passed_ids
        b["counts"]["staticPassed"] = len(passed_ids)
        if not passed_ids:
            return _fail(store, build_id, "static_validation: no scenarios passed Gateway/AST")
        return _set_phase(store, build_id, "STATIC_VALIDATED")
    except Exception as e:
        return _fail(store, build_id, f"static_validation: {e}")


def stage_execution_validation(
    *,
    build_id: str,
    store: ScenarioStore | None = None,
    execute_fn: ExecuteFn | None = None,
) -> dict[str, Any]:
    store = store or get_scenario_store()
    b = _build_ctx(store, build_id)
    if b.get("status") == "FAILED" or b.get("skipRemaining"):
        return b
    try:
        live_fn = execute_fn if execute_fn is not None else make_reporting_execute_fn()
        require_live = os.environ.get("SCENARIO_REQUIRE_LIVE_VALIDATION", "").lower() in (
            "1",
            "true",
            "yes",
        )
        if require_live and live_fn is None:
            raise RuntimeError("SCENARIO_REQUIRE_LIVE_VALIDATION set but no reporting DSN")

        if live_fn is not None:
            apply_baseline_sql()
            meta = run_metamorphic_invoice_checks(live_fn)
            b["metamorphic"] = meta.detail
            if not meta.passed:
                raise RuntimeError(f"Metamorphic checks failed: {meta.detail}")

        passed_ids: list[str] = []
        for sid in b["workspace"].get("staticPassedIds") or []:
            inst = store.get_instance(sid)
            compiled = (b["workspace"].get("compiled") or {}).get(sid)
            if inst is None or compiled is None:
                continue
            inst.transition_to(ScenarioStatus.EXECUTION_VALIDATING)
            params = resolve_parameters(inst.canonical_question, inst.logical_plan).to_bind_dict()
            exec_res = run_execution_baseline(compiled, params=params, execute_fn=live_fn)
            if not exec_res.passed:
                inc(SCENARIO_EXECUTION_VALIDATION_FAILURES)
                inst.transition_to(ScenarioStatus.FAILED)
                store.save_instance(inst)
                continue

            # Differential SUM/GROUP before publish eligibility
            if inst.family in ("SUM_MEASURE", "GROUP_MEASURE") and live_fn is not None:
                diff = run_differential_for_plan(inst.logical_plan, compiled, params, live_fn)
                if not diff.passed:
                    inc(SCENARIO_EXECUTION_VALIDATION_FAILURES)
                    inst.transition_to(ScenarioStatus.FAILED)
                    store.save_instance(inst)
                    continue

            # Baseline table asserts when codes match
            if live_fn is not None:
                ok_b, detail_b = assert_scenario_baseline(
                    scenario_code=inst.scenario_code,
                    execute_fn=live_fn,
                    row_count=int(exec_res.detail.get("rowCount") or 0)
                    if inst.family.startswith("LIST") or inst.family in ("STATUS_FILTER", "AGING")
                    else None,
                    total_sum=None,
                )
                if not ok_b:
                    inc(SCENARIO_EXECUTION_VALIDATION_FAILURES)
                    inst.transition_to(ScenarioStatus.FAILED)
                    store.save_instance(inst)
                    b.setdefault("baselineFailures", []).append({"id": sid, "detail": detail_b})
                    continue

            inst.transition_to(ScenarioStatus.EXECUTION_VALIDATED)
            store.save_instance(inst)
            passed_ids.append(sid)

        b["workspace"]["executionPassedIds"] = passed_ids
        b["counts"]["executionPassed"] = len(passed_ids)
        if not passed_ids:
            return _fail(store, build_id, "execution_validation: none passed")
        return _set_phase(store, build_id, "EXECUTION_VALIDATED")
    except Exception as e:
        return _fail(store, build_id, f"execution_validation: {e}")


def stage_performance_validation(
    *,
    build_id: str,
    store: ScenarioStore | None = None,
    execute_fn: ExecuteFn | None = None,
) -> dict[str, Any]:
    store = store or get_scenario_store()
    b = _build_ctx(store, build_id)
    if b.get("status") == "FAILED" or b.get("skipRemaining"):
        return b
    try:
        live_fn = execute_fn if execute_fn is not None else make_reporting_execute_fn()
        passed_ids: list[str] = []
        for sid in b["workspace"].get("executionPassedIds") or []:
            inst = store.get_instance(sid)
            compiled = (b["workspace"].get("compiled") or {}).get(sid)
            if inst is None or compiled is None:
                continue
            join_count = len(inst.logical_plan.join_path)
            perf = validate_performance(inst.logical_plan, join_count)
            if not perf.passed:
                inc(SCENARIO_PERFORMANCE_VALIDATION_FAILURES)
                inst.transition_to(ScenarioStatus.FAILED)
                store.save_instance(inst)
                continue
            if live_fn is not None:
                params = resolve_parameters(inst.canonical_question, inst.logical_plan).to_bind_dict()
                _ = run_explain_cost_check(live_fn, compiled.sql_template, params)
                try:
                    from nanobase_api.scenario_engine.infrastructure.shadow_perf import (
                        run_shadow_explain,
                    )

                    b.setdefault("shadowPerf", {})[sid] = run_shadow_explain(
                        live_fn, compiled.sql_template, params
                    )
                except Exception:
                    pass

            if inst.risk_tier == RiskTier.A:
                inst.transition_to(ScenarioStatus.PERFORMANCE_VALIDATING)
                inst.transition_to(ScenarioStatus.APPROVED)
            else:
                inst.transition_to(ScenarioStatus.READY_FOR_REVIEW)
            store.save_instance(inst)
            passed_ids.append(sid)

        b["workspace"]["perfPassedIds"] = passed_ids
        b["counts"]["instances"] = len(passed_ids)
        return _set_phase(store, build_id, "VALIDATED")
    except Exception as e:
        return _fail(store, build_id, f"performance_validation: {e}")


def stage_question_generation(*, build_id: str, store: ScenarioStore | None = None) -> dict[str, Any]:
    store = store or get_scenario_store()
    b = _build_ctx(store, build_id)
    if b.get("status") == "FAILED" or b.get("skipRemaining"):
        return b
    try:
        paraphrase_ids: list[str] = []
        for sid in b["workspace"].get("perfPassedIds") or []:
            inst = store.get_instance(sid)
            if inst is None:
                continue
            for text in generate_questions(inst.logical_plan, expand=True):
                # Optional LLM paraphrase suggestions (never change SQL)
                try:
                    from nanobase_api.scenario_engine.infrastructure.llm_paraphrase import (
                        maybe_llm_paraphrases,
                    )

                    extras = maybe_llm_paraphrases(text, inst.logical_plan)
                except Exception:
                    extras = []
                for t in [text, *extras]:
                    para = ScenarioParaphrase(
                        id=f"par-{uuid.uuid4().hex[:12]}",
                        scenario_id=sid,
                        language="tr",
                        text=t,
                        status=ScenarioStatus.GENERATED,
                        tenant_id=inst.tenant_id,
                        datasource_id=inst.datasource_id,
                    )
                    store.save_paraphrase(para)
                    paraphrase_ids.append(para.id)
        b["workspace"]["paraphraseIds"] = paraphrase_ids
        b["counts"]["paraphrases"] = len(paraphrase_ids)
        return _set_phase(store, build_id, "QUESTIONS")
    except Exception as e:
        return _fail(store, build_id, f"question_generation: {e}")


def stage_embedding_publish(
    *,
    build_id: str,
    tenant_id: str,
    datasource_id: str,
    store: ScenarioStore | None = None,
    auto_publish: bool = True,
    semantic_version: str = "7.3.0",
) -> dict[str, Any]:
    store = store or get_scenario_store()
    b = _build_ctx(store, build_id)
    if b.get("status") == "FAILED" or b.get("skipRemaining"):
        return b
    try:
        schema_version = b["workspace"].get("schemaVersion") or b.get("schemaVersion") or "unknown"
        validated_for_publish: list[ScenarioInstance] = []
        for sid in b["workspace"].get("perfPassedIds") or []:
            inst = store.get_instance(sid)
            if inst is None:
                continue
            if inst.risk_tier == RiskTier.A and inst.status == ScenarioStatus.APPROVED:
                validated_for_publish.append(inst)
            # Tier C never auto-publish
            if inst.risk_tier == RiskTier.C:
                continue

        batch_info: dict[str, Any] | None = None
        if auto_publish and validated_for_publish:
            _set_phase(store, build_id, "PUBLISHING")
            pub = AtomicPublisher(store=store)
            pub_ids = {i.id for i in validated_for_publish}
            paraphrases = []
            for pid in b["workspace"].get("paraphraseIds") or []:
                p = store.paraphrases.get(pid)
                if p is not None and p.scenario_id in pub_ids:
                    paraphrases.append(p)
            batch = pub.publish_batch(
                tenant_id=tenant_id,
                datasource_id=datasource_id,
                schema_version=schema_version,
                semantic_version=semantic_version,
                instances=validated_for_publish,
                paraphrases=paraphrases,
            )
            batch_info = batch.to_dict()
            if batch.status == ScenarioStatus.PUBLISHED:
                inc(SCENARIO_PUBLISHED, float(batch.scenario_count))
            elif batch.status == ScenarioStatus.FAILED:
                return _fail(store, build_id, f"publish failed: {batch_info}")
        elif not auto_publish:
            # Questions ready; leave Tier A approved / Tier B in review
            pass

        b["status"] = "COMPLETED"
        b["phase"] = "PUBLISHED" if batch_info else "READY_FOR_REVIEW"
        b["batch"] = batch_info
        b["finishedAt"] = datetime.utcnow().isoformat() + "Z"
        # Drop heavy workspace objects before persisting long-term
        b["workspace"] = {
            k: v
            for k, v in (b.get("workspace") or {}).items()
            if k
            in (
                "schemaVersion",
                "instanceIds",
                "staticPassedIds",
                "executionPassedIds",
                "perfPassedIds",
                "paraphraseIds",
            )
        }
        return b
    except Exception as e:
        return _fail(store, build_id, f"embedding_publish: {e}")


def run_staged_build(
    *,
    tenant_id: str,
    datasource_id: str,
    store: ScenarioStore | None = None,
    snapshot: SchemaSnapshot | None = None,
    execute_fn: ExecuteFn | None = None,
    auto_publish: bool = True,
    semantic_version: str = "7.3.0",
    force: bool = False,
    build_id: str | None = None,
) -> dict[str, Any]:
    """Run all 8 stages synchronously (tests / sync API fallback)."""
    store = store or get_scenario_store()
    build_id = build_id or f"build-{uuid.uuid4().hex[:12]}"
    ensure_build(store, build_id=build_id, tenant_id=tenant_id, datasource_id=datasource_id)
    stage_discovery(
        build_id=build_id,
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        store=store,
        snapshot=snapshot,
    )
    if store.builds[build_id].get("status") == "FAILED":
        return store.builds[build_id]
    stage_combination(
        build_id=build_id,
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        store=store,
        force=force,
        semantic_version=semantic_version,
    )
    b = store.builds[build_id]
    if b.get("status") == "FAILED" or b.get("skipRemaining"):
        return b
    stage_sql_compilation(build_id=build_id, store=store)
    if store.builds[build_id].get("status") == "FAILED":
        return store.builds[build_id]
    stage_static_validation(build_id=build_id, store=store)
    if store.builds[build_id].get("status") == "FAILED":
        return store.builds[build_id]
    stage_execution_validation(build_id=build_id, store=store, execute_fn=execute_fn)
    if store.builds[build_id].get("status") == "FAILED":
        return store.builds[build_id]
    stage_performance_validation(build_id=build_id, store=store, execute_fn=execute_fn)
    if store.builds[build_id].get("status") == "FAILED":
        return store.builds[build_id]
    stage_question_generation(build_id=build_id, store=store)
    if store.builds[build_id].get("status") == "FAILED":
        return store.builds[build_id]
    return stage_embedding_publish(
        build_id=build_id,
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        store=store,
        auto_publish=auto_publish,
        semantic_version=semantic_version,
    )
