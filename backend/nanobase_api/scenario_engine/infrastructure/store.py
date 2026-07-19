"""In-memory scenario registry (tests + bootstrap; SQL repo can mirror later)."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any

from nanobase_api.scenario_engine.domain.scenario import (
    PublishBatch,
    ScenarioCompilation,
    ScenarioInstance,
    ScenarioParaphrase,
)
from nanobase_api.scenario_engine.domain.status import ScenarioStatus, is_retrieval_eligible


@dataclass
class ScenarioStore:
    instances: dict[str, ScenarioInstance] = field(default_factory=dict)
    paraphrases: dict[str, ScenarioParaphrase] = field(default_factory=dict)
    compilations: dict[str, ScenarioCompilation] = field(default_factory=dict)
    batches: dict[str, PublishBatch] = field(default_factory=dict)
    active_version: dict[tuple[str, str], str] = field(default_factory=dict)  # (tenant, ds) -> batch_id
    builds: dict[str, dict[str, Any]] = field(default_factory=dict)
    usage: dict[str, dict[str, Any]] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock)

    def save_instance(self, inst: ScenarioInstance) -> None:
        with self._lock:
            self.instances[inst.id] = inst

    def get_instance(self, scenario_id: str) -> ScenarioInstance | None:
        return self.instances.get(scenario_id)

    def list_instances(
        self,
        *,
        tenant_id: str,
        datasource_id: str,
        status: ScenarioStatus | None = None,
    ) -> list[ScenarioInstance]:
        out = [
            i
            for i in self.instances.values()
            if i.tenant_id == tenant_id and i.datasource_id == datasource_id
        ]
        if status is not None:
            out = [i for i in out if i.status == status]
        return out

    def save_paraphrase(self, p: ScenarioParaphrase) -> None:
        with self._lock:
            self.paraphrases[p.id] = p

    def find_by_normalized_hash(
        self, *, tenant_id: str, datasource_id: str, qhash: str
    ) -> ScenarioParaphrase | None:
        for p in self.paraphrases.values():
            if (
                p.tenant_id == tenant_id
                and p.datasource_id == datasource_id
                and p.normalized_hash == qhash
                and is_retrieval_eligible(p.status)
            ):
                return p
        return None

    def paraphrases_for_scenario(self, scenario_id: str) -> list[ScenarioParaphrase]:
        return [p for p in self.paraphrases.values() if p.scenario_id == scenario_id]

    def save_compilation(self, c: ScenarioCompilation) -> None:
        with self._lock:
            self.compilations[c.id] = c

    def get_compilation(self, scenario_id: str, dialect: str = "postgres") -> ScenarioCompilation | None:
        for c in self.compilations.values():
            if c.scenario_id == scenario_id and c.dialect == dialect:
                return c
        return None

    def save_batch(self, b: PublishBatch) -> None:
        with self._lock:
            self.batches[b.id] = b

    def set_active_batch(self, tenant_id: str, datasource_id: str, batch_id: str) -> None:
        with self._lock:
            self.active_version[(tenant_id, datasource_id)] = batch_id

    def get_active_batch_id(self, tenant_id: str, datasource_id: str) -> str | None:
        return self.active_version.get((tenant_id, datasource_id))

    def mark_stale_by_column(
        self, tenant_id: str, datasource_id: str, column_ref: str
    ) -> list[str]:
        """Mark published scenarios that depend on column_ref as STALE."""
        stale_ids: list[str] = []
        with self._lock:
            for inst in self.instances.values():
                if inst.tenant_id != tenant_id or inst.datasource_id != datasource_id:
                    continue
                if inst.status != ScenarioStatus.PUBLISHED:
                    continue
                plan = inst.logical_plan
                refs = [
                    plan.physical_table or "",
                    plan.date_column or "",
                    plan.metric_column or "",
                    *plan.projection,
                ]
                blob = " ".join(refs)
                if column_ref in blob or column_ref.split(".")[-1] in plan.projection:
                    inst.transition_to(ScenarioStatus.STALE)
                    stale_ids.append(inst.id)
                    for p in self.paraphrases_for_scenario(inst.id):
                        if p.status == ScenarioStatus.PUBLISHED:
                            p.status = ScenarioStatus.STALE
        return stale_ids

    def suggested_questions(
        self, *, tenant_id: str, datasource_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for inst in self.list_instances(
            tenant_id=tenant_id, datasource_id=datasource_id, status=ScenarioStatus.PUBLISHED
        ):
            out.append(
                {
                    "scenarioId": inst.id,
                    "scenarioCode": inst.scenario_code,
                    "category": inst.category,
                    "question": inst.canonical_question,
                    "family": inst.family,
                    "riskTier": inst.risk_tier.value,
                }
            )
            if len(out) >= limit:
                break
        return out

    def record_usage(self, scenario_id: str, *, field: str, latency_ms: float | None = None) -> None:
        with self._lock:
            u = self.usage.setdefault(
                scenario_id,
                {
                    "match_count": 0,
                    "execution_count": 0,
                    "success_count": 0,
                    "gateway_rejection_count": 0,
                    "fallback_count": 0,
                    "avg_latency_ms": None,
                },
            )
            if field in u and isinstance(u[field], int):
                u[field] += 1
            if latency_ms is not None:
                prev = u.get("avg_latency_ms")
                u["avg_latency_ms"] = latency_ms if prev is None else (prev + latency_ms) / 2


_STORE: ScenarioStore | None = None


def get_scenario_store() -> ScenarioStore:
    global _STORE
    if _STORE is None:
        _STORE = ScenarioStore()
    return _STORE


def reset_scenario_store() -> ScenarioStore:
    global _STORE
    _STORE = ScenarioStore()
    return _STORE
