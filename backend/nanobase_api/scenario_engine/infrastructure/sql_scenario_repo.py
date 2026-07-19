"""PostgreSQL persistence for sc_scenario_* tables."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from nanobase_api.scenario_engine.domain.logical_plan import LogicalPlan
from nanobase_api.scenario_engine.domain.risk import RiskTier
from nanobase_api.scenario_engine.domain.scenario import (
    PublishBatch,
    ScenarioCompilation,
    ScenarioInstance,
    ScenarioParaphrase,
)
from nanobase_api.scenario_engine.domain.status import ScenarioStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SqlScenarioRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def tables_ready(self) -> bool:
        try:
            with self._engine.connect() as conn:
                row = conn.execute(
                    text("SELECT to_regclass('public.sc_scenario_instance') IS NOT NULL")
                ).scalar()
                return bool(row)
        except Exception:
            return False

    def upsert_instance(self, inst: ScenarioInstance) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO sc_scenario_instance (
                      id, tenant_id, datasource_id, scenario_code, family, logical_plan_json,
                      schema_version, semantic_version, policy_version, risk_tier, status,
                      category, canonical_question, generator_version, version, updated_at
                    ) VALUES (
                      :id, :tenant_id, :datasource_id, :scenario_code, :family, :logical_plan_json,
                      :schema_version, :semantic_version, :policy_version, :risk_tier, :status,
                      :category, :canonical_question, :generator_version, :version, :now
                    )
                    ON CONFLICT (id) DO UPDATE SET
                      scenario_code = EXCLUDED.scenario_code,
                      family = EXCLUDED.family,
                      logical_plan_json = EXCLUDED.logical_plan_json,
                      schema_version = EXCLUDED.schema_version,
                      semantic_version = EXCLUDED.semantic_version,
                      policy_version = EXCLUDED.policy_version,
                      risk_tier = EXCLUDED.risk_tier,
                      status = EXCLUDED.status,
                      category = EXCLUDED.category,
                      canonical_question = EXCLUDED.canonical_question,
                      generator_version = EXCLUDED.generator_version,
                      version = EXCLUDED.version,
                      updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "id": inst.id,
                    "tenant_id": inst.tenant_id,
                    "datasource_id": inst.datasource_id,
                    "scenario_code": inst.scenario_code,
                    "family": inst.family,
                    "logical_plan_json": json.dumps(inst.logical_plan.to_dict(), ensure_ascii=False),
                    "schema_version": inst.schema_version,
                    "semantic_version": inst.semantic_version,
                    "policy_version": inst.policy_version,
                    "risk_tier": inst.risk_tier.value,
                    "status": inst.status.value,
                    "category": inst.category,
                    "canonical_question": inst.canonical_question,
                    "generator_version": inst.generator_version,
                    "version": inst.version,
                    "now": _now(),
                },
            )

    def upsert_paraphrase(self, p: ScenarioParaphrase) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO sc_scenario_paraphrase (
                      id, scenario_id, tenant_id, datasource_id, language, text,
                      normalized_text, normalized_question_hash, embedding_id, status
                    ) VALUES (
                      :id, :scenario_id, :tenant_id, :datasource_id, :language, :text,
                      :normalized_text, :normalized_question_hash, :embedding_id, :status
                    )
                    ON CONFLICT (id) DO UPDATE SET
                      text = EXCLUDED.text,
                      normalized_text = EXCLUDED.normalized_text,
                      normalized_question_hash = EXCLUDED.normalized_question_hash,
                      embedding_id = EXCLUDED.embedding_id,
                      status = EXCLUDED.status
                    """
                ),
                {
                    "id": p.id,
                    "scenario_id": p.scenario_id,
                    "tenant_id": p.tenant_id,
                    "datasource_id": p.datasource_id,
                    "language": p.language,
                    "text": p.text,
                    "normalized_text": p.normalized_text,
                    "normalized_question_hash": p.normalized_hash,
                    "embedding_id": p.embedding_id,
                    "status": p.status.value,
                },
            )

    def upsert_compilation(self, c: ScenarioCompilation) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO sc_scenario_compilation (
                      id, scenario_id, dialect, sql_template, ast_fingerprint,
                      validation_status, bind_params_json
                    ) VALUES (
                      :id, :scenario_id, :dialect, :sql_template, :ast_fingerprint,
                      :validation_status, :bind_params_json
                    )
                    ON CONFLICT (id) DO UPDATE SET
                      sql_template = EXCLUDED.sql_template,
                      ast_fingerprint = EXCLUDED.ast_fingerprint,
                      validation_status = EXCLUDED.validation_status,
                      bind_params_json = EXCLUDED.bind_params_json
                    """
                ),
                {
                    "id": c.id,
                    "scenario_id": c.scenario_id,
                    "dialect": c.dialect,
                    "sql_template": c.sql_template,
                    "ast_fingerprint": c.ast_fingerprint,
                    "validation_status": c.validation_status,
                    "bind_params_json": json.dumps(c.bind_params),
                },
            )

    def upsert_batch(self, b: PublishBatch) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO sc_scenario_publish_batch (
                      id, tenant_id, datasource_id, schema_version, semantic_version,
                      status, scenario_count, checksum, error, updated_at
                    ) VALUES (
                      :id, :tenant_id, :datasource_id, :schema_version, :semantic_version,
                      :status, :scenario_count, :checksum, :error, :now
                    )
                    ON CONFLICT (id) DO UPDATE SET
                      status = EXCLUDED.status,
                      scenario_count = EXCLUDED.scenario_count,
                      checksum = EXCLUDED.checksum,
                      error = EXCLUDED.error,
                      updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "id": b.id,
                    "tenant_id": b.tenant_id,
                    "datasource_id": b.datasource_id,
                    "schema_version": b.schema_version,
                    "semantic_version": b.semantic_version,
                    "status": b.status.value,
                    "scenario_count": b.scenario_count,
                    "checksum": b.checksum,
                    "error": b.error,
                    "now": _now(),
                },
            )

    def set_active_version(
        self, tenant_id: str, datasource_id: str, batch_id: str, schema_version: str, semantic_version: str
    ) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO sc_scenario_version (
                      id, tenant_id, datasource_id, active_batch_id, schema_version, semantic_version
                    ) VALUES (
                      :id, :tenant_id, :datasource_id, :batch_id, :schema_version, :semantic_version
                    )
                    ON CONFLICT (tenant_id, datasource_id) DO UPDATE SET
                      active_batch_id = EXCLUDED.active_batch_id,
                      schema_version = EXCLUDED.schema_version,
                      semantic_version = EXCLUDED.semantic_version
                    """
                ),
                {
                    "id": f"ver-{tenant_id}-{datasource_id}"[:64],
                    "tenant_id": tenant_id,
                    "datasource_id": datasource_id,
                    "batch_id": batch_id,
                    "schema_version": schema_version,
                    "semantic_version": semantic_version,
                },
            )

    def save_usage(self, scenario_id: str, usage: dict[str, Any], *, tenant_id: str, datasource_id: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO sc_scenario_usage_stat (
                      id, scenario_id, tenant_id, datasource_id,
                      match_count, execution_count, success_count,
                      gateway_rejection_count, fallback_count, avg_latency_ms, updated_at
                    ) VALUES (
                      :id, :scenario_id, :tenant_id, :datasource_id,
                      :match_count, :execution_count, :success_count,
                      :gateway_rejection_count, :fallback_count, :avg_latency_ms, :now
                    )
                    ON CONFLICT (id) DO UPDATE SET
                      match_count = EXCLUDED.match_count,
                      execution_count = EXCLUDED.execution_count,
                      success_count = EXCLUDED.success_count,
                      gateway_rejection_count = EXCLUDED.gateway_rejection_count,
                      fallback_count = EXCLUDED.fallback_count,
                      avg_latency_ms = EXCLUDED.avg_latency_ms,
                      updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "id": f"usage-{scenario_id}"[:64],
                    "scenario_id": scenario_id,
                    "tenant_id": tenant_id,
                    "datasource_id": datasource_id,
                    "match_count": int(usage.get("match_count") or 0),
                    "execution_count": int(usage.get("execution_count") or 0),
                    "success_count": int(usage.get("success_count") or 0),
                    "gateway_rejection_count": int(usage.get("gateway_rejection_count") or 0),
                    "fallback_count": int(usage.get("fallback_count") or 0),
                    "avg_latency_ms": usage.get("avg_latency_ms"),
                    "now": _now(),
                },
            )

    def save_validation_run(
        self, *, run_id: str, scenario_id: str, layer: str, passed: bool, detail: dict[str, Any] | None = None
    ) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO sc_scenario_validation_run (id, scenario_id, layer, passed, detail_json)
                    VALUES (:id, :scenario_id, :layer, :passed, :detail_json)
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {
                    "id": run_id,
                    "scenario_id": scenario_id,
                    "layer": layer,
                    "passed": passed,
                    "detail_json": json.dumps(detail or {}, ensure_ascii=False),
                },
            )

    def hydrate(self) -> dict[str, Any]:
        """Load catalog into memory dicts for ScenarioStore boot."""
        if not self.tables_ready():
            return {
                "instances": {},
                "paraphrases": {},
                "compilations": {},
                "batches": {},
                "active_version": {},
                "usage": {},
            }
        instances: dict[str, ScenarioInstance] = {}
        paraphrases: dict[str, ScenarioParaphrase] = {}
        compilations: dict[str, ScenarioCompilation] = {}
        batches: dict[str, PublishBatch] = {}
        active_version: dict[tuple[str, str], str] = {}
        usage: dict[str, dict[str, Any]] = {}

        with self._engine.connect() as conn:
            for row in conn.execute(text("SELECT * FROM sc_scenario_instance")).mappings():
                plan = LogicalPlan.from_dict(json.loads(row["logical_plan_json"]))
                instances[row["id"]] = ScenarioInstance(
                    id=row["id"],
                    tenant_id=row["tenant_id"],
                    datasource_id=row["datasource_id"],
                    scenario_code=row["scenario_code"],
                    family=row["family"],
                    logical_plan=plan,
                    schema_version=row["schema_version"],
                    semantic_version=row["semantic_version"],
                    policy_version=row["policy_version"] or "2026.07.1",
                    risk_tier=RiskTier(row["risk_tier"]),
                    status=ScenarioStatus(row["status"]),
                    category=row["category"] or "",
                    canonical_question=row["canonical_question"] or "",
                    generator_version=row["generator_version"] or "1.0.0",
                    version=int(row["version"] or 1),
                )
            for row in conn.execute(text("SELECT * FROM sc_scenario_paraphrase")).mappings():
                paraphrases[row["id"]] = ScenarioParaphrase(
                    id=row["id"],
                    scenario_id=row["scenario_id"],
                    language=row["language"],
                    text=row["text"],
                    status=ScenarioStatus(row["status"]),
                    embedding_id=row["embedding_id"],
                    tenant_id=row["tenant_id"],
                    datasource_id=row["datasource_id"],
                )
            for row in conn.execute(text("SELECT * FROM sc_scenario_compilation")).mappings():
                binds = json.loads(row["bind_params_json"] or "[]")
                compilations[row["id"]] = ScenarioCompilation(
                    id=row["id"],
                    scenario_id=row["scenario_id"],
                    dialect=row["dialect"],
                    sql_template=row["sql_template"],
                    ast_fingerprint=row["ast_fingerprint"],
                    validation_status=row["validation_status"],
                    bind_params=list(binds),
                )
            for row in conn.execute(text("SELECT * FROM sc_scenario_publish_batch")).mappings():
                batches[row["id"]] = PublishBatch(
                    id=row["id"],
                    tenant_id=row["tenant_id"],
                    datasource_id=row["datasource_id"],
                    schema_version=row["schema_version"],
                    semantic_version=row["semantic_version"],
                    status=ScenarioStatus(row["status"]),
                    scenario_count=int(row["scenario_count"] or 0),
                    checksum=row["checksum"],
                    error=row["error"],
                )
            for row in conn.execute(text("SELECT * FROM sc_scenario_version")).mappings():
                if row["active_batch_id"]:
                    active_version[(row["tenant_id"], row["datasource_id"])] = row["active_batch_id"]
            try:
                for row in conn.execute(text("SELECT * FROM sc_scenario_usage_stat")).mappings():
                    usage[row["scenario_id"]] = {
                        "match_count": int(row["match_count"] or 0),
                        "execution_count": int(row["execution_count"] or 0),
                        "success_count": int(row["success_count"] or 0),
                        "gateway_rejection_count": int(row["gateway_rejection_count"] or 0),
                        "fallback_count": int(row["fallback_count"] or 0),
                        "avg_latency_ms": row["avg_latency_ms"],
                    }
            except Exception:
                pass

        return {
            "instances": instances,
            "paraphrases": paraphrases,
            "compilations": compilations,
            "batches": batches,
            "active_version": active_version,
            "usage": usage,
        }
