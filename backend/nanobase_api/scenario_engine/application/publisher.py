"""Atomic scenario catalog publisher."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from nanobase_api.scenario_engine.domain.risk import RiskTier
from nanobase_api.scenario_engine.domain.scenario import PublishBatch, ScenarioInstance, ScenarioParaphrase
from nanobase_api.scenario_engine.domain.status import ScenarioStatus
from nanobase_api.scenario_engine.infrastructure.qdrant_publisher import ScenarioQdrantPublisher
from nanobase_api.scenario_engine.infrastructure.redis_cache import get_plan_cache
from nanobase_api.scenario_engine.infrastructure.store import ScenarioStore, get_scenario_store


class AtomicPublisher:
    def __init__(
        self,
        store: ScenarioStore | None = None,
        qdrant: ScenarioQdrantPublisher | None = None,
    ) -> None:
        self.store = store or get_scenario_store()
        self.qdrant = qdrant or ScenarioQdrantPublisher()

    def publish_batch(
        self,
        *,
        tenant_id: str,
        datasource_id: str,
        schema_version: str,
        semantic_version: str,
        instances: list[ScenarioInstance],
        paraphrases: list[ScenarioParaphrase],
        auto_approve_tier_a: bool = True,
    ) -> PublishBatch:
        batch = PublishBatch(
            id=f"batch-{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            datasource_id=datasource_id,
            schema_version=schema_version,
            semantic_version=semantic_version,
            status=ScenarioStatus.PREPARING,
        )
        self.store.save_batch(batch)

        try:
            publishable: list[ScenarioInstance] = []
            for inst in instances:
                if inst.status not in (
                    ScenarioStatus.APPROVED,
                    ScenarioStatus.READY_FOR_REVIEW,
                    ScenarioStatus.EXECUTION_VALIDATED,
                    ScenarioStatus.PERFORMANCE_VALIDATING,
                    ScenarioStatus.READY,
                ):
                    # Only validated scenarios
                    if inst.status not in (
                        ScenarioStatus.STATIC_VALIDATED,
                        ScenarioStatus.EXECUTION_VALIDATED,
                        ScenarioStatus.APPROVED,
                        ScenarioStatus.READY_FOR_REVIEW,
                    ):
                        continue
                if inst.risk_tier == RiskTier.A and auto_approve_tier_a:
                    if inst.status != ScenarioStatus.APPROVED:
                        # walk toward APPROVED if coming from validated
                        if inst.status == ScenarioStatus.EXECUTION_VALIDATED:
                            inst.transition_to(ScenarioStatus.PERFORMANCE_VALIDATING)
                            inst.transition_to(ScenarioStatus.APPROVED)
                        elif inst.status == ScenarioStatus.READY_FOR_REVIEW:
                            inst.transition_to(ScenarioStatus.APPROVED)
                        elif inst.status == ScenarioStatus.STATIC_VALIDATED:
                            continue  # need execution
                    publishable.append(inst)
                elif inst.risk_tier == RiskTier.B:
                    if inst.status == ScenarioStatus.APPROVED:
                        publishable.append(inst)
                    else:
                        if inst.status == ScenarioStatus.EXECUTION_VALIDATED:
                            inst.transition_to(ScenarioStatus.READY_FOR_REVIEW)
                        # leave for review — not in this batch publish set
                elif inst.status == ScenarioStatus.APPROVED:
                    publishable.append(inst)

            if not publishable:
                batch.status = ScenarioStatus.FAILED
                batch.error = "No publishable scenarios after validation"
                self.store.save_batch(batch)
                return batch

            # Transition to PREPARING → READY → PUBLISHED atomically
            for inst in publishable:
                if inst.status == ScenarioStatus.APPROVED:
                    inst.transition_to(ScenarioStatus.PREPARING)
                if inst.status == ScenarioStatus.PREPARING:
                    inst.transition_to(ScenarioStatus.READY)

            checksum = self._checksum(publishable)
            batch.checksum = checksum
            batch.scenario_count = len(publishable)
            batch.status = ScenarioStatus.READY
            self.store.save_batch(batch)

            # Embeddings then flip
            pub_paras = [p for p in paraphrases if p.scenario_id in {i.id for i in publishable}]
            for inst in publishable:
                inst.transition_to(ScenarioStatus.PUBLISHED)
                self.store.save_instance(inst)
            for p in pub_paras:
                p.status = ScenarioStatus.PUBLISHED
                self.store.save_paraphrase(p)

            self.qdrant.publish(instances=publishable, paraphrases=pub_paras)

            # Atomic active version swap
            self.store.set_active_batch(tenant_id, datasource_id, batch.id)
            batch.status = ScenarioStatus.PUBLISHED
            self.store.save_batch(batch)

            get_plan_cache().invalidate_prefix(tenant_id=tenant_id, datasource_id=datasource_id)
            return batch
        except Exception as e:
            batch.status = ScenarioStatus.FAILED
            batch.error = str(e)[:500]
            self.store.save_batch(batch)
            return batch

    @staticmethod
    def _checksum(instances: list[ScenarioInstance]) -> str:
        payload = sorted(
            [
                {
                    "id": i.id,
                    "code": i.scenario_code,
                    "fp": i.logical_plan.fingerprint(),
                    "status": i.status.value,
                }
                for i in instances
            ],
            key=lambda x: x["id"],
        )
        raw = json.dumps(payload, sort_keys=True)
        return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
