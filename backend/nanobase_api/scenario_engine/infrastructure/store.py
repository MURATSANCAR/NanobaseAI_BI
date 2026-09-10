"""Scenario registry: in-memory cache with optional SQL write-through."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Protocol

from nanobase_api.scenario_engine.domain.scenario import (
    PublishBatch,
    ScenarioCompilation,
    ScenarioInstance,
    ScenarioParaphrase,
)
from nanobase_api.scenario_engine.domain.status import ScenarioStatus, is_retrieval_eligible

log = logging.getLogger(__name__)

# Ayni satir icin ust uste bu kadar SQL yazma hatasindan sonra devre acilir.
_MIRROR_FAIL_LIMIT = 3


class ScenarioSqlPort(Protocol):
    def tables_ready(self) -> bool: ...
    def upsert_instance(self, inst: ScenarioInstance) -> None: ...
    def upsert_paraphrase(self, p: ScenarioParaphrase) -> None: ...
    def upsert_compilation(self, c: ScenarioCompilation) -> None: ...
    def upsert_batch(self, b: PublishBatch) -> None: ...
    def set_active_version(
        self, tenant_id: str, datasource_id: str, batch_id: str, schema_version: str, semantic_version: str
    ) -> None: ...
    def save_usage(
        self, scenario_id: str, usage: dict[str, Any], *, tenant_id: str, datasource_id: str
    ) -> None: ...
    def hydrate(self) -> dict[str, Any]: ...


@dataclass
class ScenarioStore:
    instances: dict[str, ScenarioInstance] = field(default_factory=dict)
    paraphrases: dict[str, ScenarioParaphrase] = field(default_factory=dict)
    compilations: dict[str, ScenarioCompilation] = field(default_factory=dict)
    batches: dict[str, PublishBatch] = field(default_factory=dict)
    active_version: dict[tuple[str, str], str] = field(default_factory=dict)
    builds: dict[str, dict[str, Any]] = field(default_factory=dict)
    usage: dict[str, dict[str, Any]] = field(default_factory=dict)
    sql_repo: ScenarioSqlPort | None = None
    backend: str = "memory"
    _lock: RLock = field(default_factory=RLock)
    _hydrated: bool = False
    _mirror_failures: dict[tuple[str, str], int] = field(default_factory=dict, repr=False)

    def _mirror(self, op: str, key: str, write) -> None:
        """SQL aynasina yaz; israrla dusen satiri bir sure sonra birak.

        Bellekteki kopya cagiran tarafindan zaten yazildi ve yetkili olan o.
        Bir satir DB kisitini ihlal ediyorsa (eksik ust kayit, PUBLISHED hash
        cakismasi) eskiden her yenileme turunda sessizce yeniden denenirdi;
        PostgreSQL her denemede dusen ifadenin tamamini loga basiyordu. Bir
        konteyner logunu uc gunde 24 GB'a cikaran mekanizma buydu.
        """
        if self.sql_repo is None:
            return
        slot = (op, key)
        with self._lock:
            if self._mirror_failures.get(slot, 0) >= _MIRROR_FAIL_LIMIT:
                return
        try:
            write()
        except Exception as e:
            with self._lock:
                fails = self._mirror_failures.get(slot, 0) + 1
                self._mirror_failures[slot] = fails
            if fails >= _MIRROR_FAIL_LIMIT:
                log.warning(
                    "scenario SQL mirror %s %s: %d denemede basarisiz, birakiliyor: %s",
                    op, key, fails, e,
                )
            return
        with self._lock:
            self._mirror_failures.pop(slot, None)

    def reset_mirror_failures(self) -> None:
        """Dusen yazmalarin nedeni giderildiginde write-through'u yeniden kur."""
        with self._lock:
            self._mirror_failures.clear()

    def mirror_failure_count(self) -> int:
        """Su an devresi acik olan satir sayisi (saglik ucu icin)."""
        with self._lock:
            return sum(1 for v in self._mirror_failures.values() if v >= _MIRROR_FAIL_LIMIT)

    def attach_sql(self, repo: ScenarioSqlPort, *, hydrate: bool = True) -> None:
        self.sql_repo = repo
        self.backend = "sql"
        if hydrate and repo.tables_ready():
            data = repo.hydrate()
            with self._lock:
                self.instances = dict(data.get("instances") or {})
                self.paraphrases = dict(data.get("paraphrases") or {})
                self.compilations = dict(data.get("compilations") or {})
                self.batches = dict(data.get("batches") or {})
                self.active_version = dict(data.get("active_version") or {})
                self.usage = dict(data.get("usage") or {})
                self._hydrated = True

    def save_instance(self, inst: ScenarioInstance) -> None:
        with self._lock:
            self.instances[inst.id] = inst
        self._mirror("instance", inst.id, lambda: self.sql_repo.upsert_instance(inst))

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
        self._mirror("paraphrase", p.id, lambda: self.sql_repo.upsert_paraphrase(p))

    def find_by_normalized_hash(
        self, *, tenant_id: str, datasource_id: str, qhash: str
    ) -> ScenarioParaphrase | None:
        hits = self.find_all_by_normalized_hash(
            tenant_id=tenant_id, datasource_id=datasource_id, qhash=qhash
        )
        return hits[0] if hits else None

    def find_all_by_normalized_hash(
        self, *, tenant_id: str, datasource_id: str, qhash: str
    ) -> list[ScenarioParaphrase]:
        return [
            p
            for p in self.paraphrases.values()
            if (
                p.tenant_id == tenant_id
                and p.datasource_id == datasource_id
                and p.normalized_hash == qhash
                and is_retrieval_eligible(p.status)
            )
        ]

    def paraphrases_for_scenario(self, scenario_id: str) -> list[ScenarioParaphrase]:
        return [p for p in self.paraphrases.values() if p.scenario_id == scenario_id]

    def save_compilation(self, c: ScenarioCompilation) -> None:
        with self._lock:
            self.compilations[c.id] = c
        self._mirror("compilation", c.id, lambda: self.sql_repo.upsert_compilation(c))

    def get_compilation(self, scenario_id: str, dialect: str = "postgres") -> ScenarioCompilation | None:
        for c in self.compilations.values():
            if c.scenario_id == scenario_id and c.dialect == dialect:
                return c
        return None

    def save_batch(self, b: PublishBatch) -> None:
        with self._lock:
            self.batches[b.id] = b
        self._mirror("batch", b.id, lambda: self.sql_repo.upsert_batch(b))

    def set_active_batch(self, tenant_id: str, datasource_id: str, batch_id: str) -> None:
        with self._lock:
            self.active_version[(tenant_id, datasource_id)] = batch_id
            batch = self.batches.get(batch_id)
        if batch is not None:
            self._mirror(
                "active_version",
                f"{tenant_id}/{datasource_id}",
                lambda: self.sql_repo.set_active_version(
                    tenant_id,
                    datasource_id,
                    batch_id,
                    batch.schema_version,
                    batch.semantic_version,
                ),
            )

    def get_active_batch_id(self, tenant_id: str, datasource_id: str) -> str | None:
        return self.active_version.get((tenant_id, datasource_id))

    def mark_stale_by_column(
        self, tenant_id: str, datasource_id: str, column_ref: str
    ) -> list[str]:
        stale_ids: list[str] = []
        with self._lock:
            for inst in list(self.instances.values()):
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
                            self._mirror(
                                "paraphrase", p.id, lambda p=p: self.sql_repo.upsert_paraphrase(p)
                            )
                    self._mirror(
                        "instance", inst.id, lambda inst=inst: self.sql_repo.upsert_instance(inst)
                    )
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
            usage_snap = dict(u)
            inst = self.instances.get(scenario_id)
        if self.sql_repo is not None and inst is not None:
            self._mirror(
                "usage",
                scenario_id,
                lambda: self.sql_repo.save_usage(
                    scenario_id,
                    usage_snap,
                    tenant_id=inst.tenant_id,
                    datasource_id=inst.datasource_id,
                ),
            )


_STORE: ScenarioStore | None = None


def get_scenario_store() -> ScenarioStore:
    global _STORE
    if _STORE is None:
        _STORE = ScenarioStore()
        _try_attach_meta_sql(_STORE)
    return _STORE


def reset_scenario_store() -> ScenarioStore:
    global _STORE
    _STORE = ScenarioStore()
    _try_attach_meta_sql(_STORE)
    return _STORE


def _try_attach_meta_sql(store: ScenarioStore) -> None:
    """Attach SQL repo. Memory only when SCENARIO_SQL_DISABLED=1 (unit tests).

    Fail-closed when SCENARIO_REQUIRE_SQL=1 and meta DSN missing / attach fails.
    """
    if os.environ.get("SCENARIO_SQL_DISABLED", "").lower() in ("1", "true", "yes"):
        store.backend = "memory"
        return
    require = os.environ.get("SCENARIO_REQUIRE_SQL", "").lower() in ("1", "true", "yes")
    dsn = os.environ.get("NANOBASE_META_DSN")
    if not dsn:
        if require:
            raise RuntimeError(
                "SCENARIO_REQUIRE_SQL=1 but NANOBASE_META_DSN is not set (fail-closed)"
            )
        return
    try:
        from sqlalchemy import create_engine

        from nanobase_api.scenario_engine.infrastructure.sql_scenario_repo import SqlScenarioRepository

        engine = create_engine(dsn, pool_pre_ping=True, pool_size=3)
        repo = SqlScenarioRepository(engine)
        if repo.tables_ready():
            store.attach_sql(repo, hydrate=True)
        elif require:
            raise RuntimeError("SCENARIO_REQUIRE_SQL=1 but scenario SQL tables are not ready")
    except RuntimeError:
        raise
    except Exception as e:
        if require:
            raise RuntimeError(f"SCENARIO_REQUIRE_SQL=1 but SQL attach failed: {e}") from e
