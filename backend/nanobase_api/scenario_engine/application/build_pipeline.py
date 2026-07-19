"""End-to-end scenario build pipeline for a datasource."""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any, Callable
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
from nanobase_api.scenario_engine.infrastructure.reporting_exec import make_reporting_execute_fn
from nanobase_api.scenario_engine.infrastructure.schema_snapshot import (
    SchemaSnapshot,
    invoice_analytics_snapshot,
)
from nanobase_api.scenario_engine.infrastructure.semantic_classifier import classify_schema
from nanobase_api.scenario_engine.infrastructure.store import ScenarioStore, get_scenario_store
from nanobase_api.scenario_engine.infrastructure.validators import (
    new_run_id,
    run_execution_baseline,
    run_metamorphic_invoice_checks,
    validate_performance,
    validate_period_properties,
    validate_static_ast,
)

ExecuteFn = Callable[[str, dict[str, object] | None], list[dict[str, Any]]]


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
    store = store or get_scenario_store()
    build_id = f"build-{uuid.uuid4().hex[:12]}"
    store.builds[build_id] = {
        "id": build_id,
        "tenantId": tenant_id,
        "datasourceId": datasource_id,
        "status": "RUNNING",
        "phase": "DISCOVERED",
        "startedAt": datetime.utcnow().isoformat() + "Z",
        "counts": {},
        "error": None,
    }

    try:
        snap = snapshot or invoice_analytics_snapshot()
        snap.datasource_id = datasource_id
        classification = classify_schema(snap)
        graph = build_relationship_graph(snap)
        store.builds[build_id]["phase"] = "CLASSIFIED"
        store.builds[build_id]["schemaVersion"] = classification.schema_version

        # Idempotent: same schema+generator already published → no-op
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
                store.builds[build_id]["status"] = "COMPLETED"
                store.builds[build_id]["phase"] = "IDEMPOTENT_SKIP"
                store.builds[build_id]["counts"]["published"] = len(existing)
                store.builds[build_id]["finishedAt"] = datetime.utcnow().isoformat() + "Z"
                return store.builds[build_id]

        planned = plan_invoice_combinations(classification, graph)
        store.builds[build_id]["phase"] = "GENERATED"
        store.builds[build_id]["counts"]["candidates"] = len(planned)
        inc(SCENARIO_CANDIDATES_GENERATED, float(len(planned)))

        prop = validate_period_properties(now=datetime.now(ZoneInfo("Europe/Istanbul")))
        if not prop.passed:
            raise RuntimeError(f"Period property tests failed: {prop.detail}")

        # Live farm when DSN available; otherwise offline structural validation
        live_fn = execute_fn if execute_fn is not None else make_reporting_execute_fn()
        require_live = os.environ.get("SCENARIO_REQUIRE_LIVE_VALIDATION", "").lower() in (
            "1",
            "true",
            "yes",
        )
        if require_live and live_fn is None:
            raise RuntimeError("SCENARIO_REQUIRE_LIVE_VALIDATION set but no reporting DSN")

        if live_fn is not None:
            meta = run_metamorphic_invoice_checks(live_fn)
            store.builds[build_id]["metamorphic"] = meta.detail
            if not meta.passed:
                raise RuntimeError(f"Metamorphic checks failed: {meta.detail}")

        compiler = get_compiler("postgres")
        instances: list[ScenarioInstance] = []
        paraphrases: list[ScenarioParaphrase] = []
        compilations: list[ScenarioCompilation] = []
        validated_for_publish: list[ScenarioInstance] = []

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
            inst.transition_to(ScenarioStatus.STATIC_VALIDATING)

            compiled = compiler.compile(p.logical_plan)
            static = validate_static_ast(p.logical_plan, compiled)
            if not static.passed:
                inc(SCENARIO_STATIC_VALIDATION_FAILURES)
                inst.transition_to(ScenarioStatus.FAILED)
                store.save_instance(inst)
                continue
            inst.transition_to(ScenarioStatus.STATIC_VALIDATED)
            inst.transition_to(ScenarioStatus.EXECUTION_VALIDATING)

            params = resolve_parameters(cq, p.logical_plan).to_bind_dict()
            exec_res = run_execution_baseline(compiled, params=params, execute_fn=live_fn)
            if not exec_res.passed:
                inc(SCENARIO_EXECUTION_VALIDATION_FAILURES)
                inst.transition_to(ScenarioStatus.FAILED)
                store.save_instance(inst)
                continue
            inst.transition_to(ScenarioStatus.EXECUTION_VALIDATED)

            join_count = len(p.logical_plan.join_path)
            perf = validate_performance(p.logical_plan, join_count)
            if not perf.passed:
                inc(SCENARIO_PERFORMANCE_VALIDATION_FAILURES)
                inst.transition_to(ScenarioStatus.FAILED)
                store.save_instance(inst)
                continue

            if p.risk_tier == RiskTier.A:
                inst.transition_to(ScenarioStatus.PERFORMANCE_VALIDATING)
                inst.transition_to(ScenarioStatus.APPROVED)
            else:
                inst.transition_to(ScenarioStatus.READY_FOR_REVIEW)

            store.save_instance(inst)
            instances.append(inst)
            if inst.risk_tier == RiskTier.A:
                validated_for_publish.append(inst)

            if store.sql_repo is not None and hasattr(store.sql_repo, "save_validation_run"):
                try:
                    store.sql_repo.save_validation_run(
                        run_id=new_run_id(),
                        scenario_id=sid,
                        layer="PIPELINE",
                        passed=True,
                        detail={"static": static.detail, "execution": exec_res.detail, "perf": perf.detail},
                    )
                except Exception:
                    pass

            comp = ScenarioCompilation(
                id=f"cmp-{uuid.uuid4().hex[:12]}",
                scenario_id=sid,
                dialect="postgres",
                sql_template=compiled.sql_template,
                ast_fingerprint=compiled.ast_fingerprint,
                validation_status="PASSED",
                bind_params=compiled.bind_params,
            )
            store.save_compilation(comp)
            compilations.append(comp)

            for text in generate_questions(p.logical_plan):
                para = ScenarioParaphrase(
                    id=f"par-{uuid.uuid4().hex[:12]}",
                    scenario_id=sid,
                    language="tr",
                    text=text,
                    status=ScenarioStatus.GENERATED,
                    tenant_id=tenant_id,
                    datasource_id=datasource_id,
                )
                paraphrases.append(para)
                store.save_paraphrase(para)

        store.builds[build_id]["phase"] = "VALIDATED"
        store.builds[build_id]["counts"]["instances"] = len(instances)
        store.builds[build_id]["counts"]["paraphrases"] = len(paraphrases)
        store.builds[build_id]["counts"]["compilations"] = len(compilations)

        batch_info: dict[str, Any] | None = None
        if auto_publish and validated_for_publish:
            store.builds[build_id]["phase"] = "PUBLISHING"
            pub = AtomicPublisher(store=store)
            pub_ids = {i.id for i in validated_for_publish}
            batch = pub.publish_batch(
                tenant_id=tenant_id,
                datasource_id=datasource_id,
                schema_version=classification.schema_version,
                semantic_version=semantic_version,
                instances=validated_for_publish,
                paraphrases=[p for p in paraphrases if p.scenario_id in pub_ids],
            )
            batch_info = batch.to_dict()
            if batch.status == ScenarioStatus.PUBLISHED:
                inc(SCENARIO_PUBLISHED, float(batch.scenario_count))

        store.builds[build_id]["status"] = "COMPLETED"
        store.builds[build_id]["phase"] = "PUBLISHED" if batch_info else "READY_FOR_REVIEW"
        store.builds[build_id]["batch"] = batch_info
        store.builds[build_id]["finishedAt"] = datetime.utcnow().isoformat() + "Z"
        return store.builds[build_id]
    except Exception as e:
        store.builds[build_id]["status"] = "FAILED"
        store.builds[build_id]["error"] = str(e)[:500]
        store.builds[build_id]["finishedAt"] = datetime.utcnow().isoformat() + "Z"
        return store.builds[build_id]


def get_build(build_id: str, store: ScenarioStore | None = None) -> dict[str, Any] | None:
    store = store or get_scenario_store()
    return store.builds.get(build_id)
