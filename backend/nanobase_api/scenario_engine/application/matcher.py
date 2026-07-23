"""Exact / semantic scenario matcher with composite confidence score."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nanobase_api.scenario_engine.application.intent_slots import (
    detect_family,
    detect_period,
    entity_score,
    family_compatible,
    family_score,
    period_compatible,
    period_score,
)
from nanobase_api.scenario_engine.domain.scenario import normalize_question, question_hash
from nanobase_api.scenario_engine.domain.status import ScenarioStatus, is_retrieval_eligible
from nanobase_api.scenario_engine.infrastructure.qdrant_publisher import ScenarioQdrantPublisher
from nanobase_api.scenario_engine.infrastructure.store import ScenarioStore, get_scenario_store


@dataclass
class MatchResult:
    matched: bool
    scenario_id: str | None = None
    scenario_code: str | None = None
    confidence: float = 0.0
    route: str = "AWEL"
    required_parameters: list[str] = field(default_factory=list)
    logical_plan: dict[str, Any] | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched": self.matched,
            "scenarioId": self.scenario_id,
            "scenarioCode": self.scenario_code,
            "confidence": self.confidence,
            "route": self.route,
            "requiredParameters": list(self.required_parameters),
            "logicalPlan": self.logical_plan,
            "detail": dict(self.detail),
        }


def _token_overlap(a: str, b: str) -> float:
    ta = set(normalize_question(a).split())
    tb = set(normalize_question(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def composite_score(
    *,
    vector_sim: float,
    exact_token: float,
    entity: float,
    period: float,
    family: float,
    slot_completeness: float,
    popularity: float = 0.0,
    historical_success: float = 0.0,
    ambiguity_penalty: float = 0.0,
) -> float:
    score = (
        0.22 * vector_sim
        + 0.14 * exact_token
        + 0.24 * entity
        + 0.18 * period
        + 0.14 * family
        + 0.05 * slot_completeness
        + 0.02 * popularity
        + 0.01 * historical_success
        - ambiguity_penalty
    )
    return round(max(0.0, min(1.0, score)), 4)


class ScenarioMatcher:
    def __init__(
        self,
        store: ScenarioStore | None = None,
        qdrant: ScenarioQdrantPublisher | None = None,
    ) -> None:
        self.store = store or get_scenario_store()
        self.qdrant = qdrant or ScenarioQdrantPublisher()

    def match(
        self,
        question: str,
        *,
        tenant_id: str,
        datasource_id: str,
        schema_version: str | None = None,
        semantic_version: str | None = None,
        financial_critical: bool = False,
    ) -> MatchResult:
        q = (question or "").strip()
        if not q:
            return MatchResult(matched=False, route="AWEL", detail={"reason": "empty"})

        q_period = detect_period(q)
        q_family = detect_family(q)

        # 1) Exact normalized hash (still respect period/family gates — blocks poisoned learns)
        qh = question_hash(q)
        para = self.store.find_by_normalized_hash(
            tenant_id=tenant_id, datasource_id=datasource_id, qhash=qh
        )
        if para is not None:
            inst = self.store.get_instance(para.scenario_id)
            if inst and is_retrieval_eligible(inst.status):
                if schema_version and inst.schema_version != schema_version:
                    return MatchResult(matched=False, route="AWEL", detail={"reason": "schema_mismatch"})
                plan = inst.logical_plan
                slots_ok = period_compatible(q_period, plan.period) and family_compatible(
                    q_family, inst.family
                )
                if slots_ok:
                    self.store.record_usage(inst.id, field="match_count")
                    return MatchResult(
                        matched=True,
                        scenario_id=inst.id,
                        scenario_code=inst.scenario_code,
                        confidence=0.99,
                        route="PRECOMPILED_SCENARIO",
                        logical_plan=plan.to_dict(),
                        detail={"matchType": "exact"},
                    )
                # fall through to fuzzy/intent — do not trust conflicting learned paraphrase


        # 2) Verified paraphrase / canonical fuzzy with slot gates
        published = self.store.list_instances(
            tenant_id=tenant_id, datasource_id=datasource_id, status=ScenarioStatus.PUBLISHED
        )
        best: MatchResult | None = None
        for inst in published:
            if schema_version and inst.schema_version != schema_version:
                continue
            if semantic_version and inst.semantic_version != semantic_version:
                continue
            plan = inst.logical_plan
            if not period_compatible(q_period, plan.period):
                continue
            if not family_compatible(q_family, inst.family):
                continue

            candidates = [inst.canonical_question] + [
                p.text
                for p in self.store.paraphrases_for_scenario(inst.id)
                if is_retrieval_eligible(p.status)
            ]
            best_tok = 0.0
            for text in candidates:
                best_tok = max(best_tok, _token_overlap(q, text))

            ent = entity_score(q, plan.entity, plan.physical_table)
            per = period_score(q_period, plan.period)
            fam = family_score(q_family, inst.family)

            # Need either decent paraphrase overlap OR strong entity+slots
            if best_tok < 0.35 and ent < 0.35:
                continue

            score = composite_score(
                vector_sim=max(best_tok, ent),
                exact_token=best_tok,
                entity=ent,
                period=per,
                family=fam,
                slot_completeness=1.0 if plan.period else 0.8,
            )
            # Boost when all slots lock
            if q_period and q_family and per >= 1.0 and fam >= 1.0 and ent >= 0.3:
                score = min(1.0, score + 0.22)
            elif q_family and fam >= 1.0 and ent >= 0.4 and (q_period is None or per >= 1.0):
                score = min(1.0, score + 0.22)

            if best is None or score > best.confidence:
                best = MatchResult(
                    matched=score >= 0.90,
                    scenario_id=inst.id,
                    scenario_code=inst.scenario_code,
                    confidence=score,
                    route="PRECOMPILED_SCENARIO" if score >= 0.90 else "AWEL",
                    logical_plan=plan.to_dict(),
                    detail={
                        "matchType": "slot_token",
                        "tokenOverlap": best_tok,
                        "entityScore": ent,
                        "periodScore": per,
                        "familyScore": fam,
                        "detectedPeriod": q_period.value if q_period else None,
                        "detectedFamily": q_family,
                    },
                )

        # 3) Qdrant vector (still respect period/family gates)
        if published:
            sv = schema_version or published[0].schema_version
            sem = semantic_version or published[0].semantic_version
            hits = self.qdrant.search(
                question=q,
                tenant_id=tenant_id,
                datasource_id=datasource_id,
                schema_version=sv,
                semantic_version=sem,
            )
            if hits:
                top = hits[0]
                inst = self.store.get_instance(str(top.get("scenario_id") or ""))
                if inst and is_retrieval_eligible(inst.status):
                    plan = inst.logical_plan
                    if period_compatible(q_period, plan.period) and family_compatible(
                        q_family, inst.family
                    ):
                        vec = float(top.get("score") or 0)
                        ent = entity_score(q, plan.entity, plan.physical_table)
                        score = composite_score(
                            vector_sim=vec,
                            exact_token=_token_overlap(q, inst.canonical_question),
                            entity=ent,
                            period=period_score(q_period, plan.period),
                            family=family_score(q_family, inst.family),
                            slot_completeness=0.9,
                        )
                        if best is None or score > best.confidence:
                            best = MatchResult(
                                matched=score >= 0.90,
                                scenario_id=inst.id,
                                scenario_code=inst.scenario_code,
                                confidence=score,
                                route="PRECOMPILED_SCENARIO" if score >= 0.90 else "SLOT_VALIDATE",
                                logical_plan=plan.to_dict(),
                                detail={"matchType": "semantic", "vectorScore": vec},
                            )

        # 4) Intent + entity fingerprint (no paraphrase needed)
        if best is None or best.confidence < 0.90:
            intent_hit = self._intent_match(q, published, q_period=q_period, q_family=q_family)
            if intent_hit is not None and (best is None or intent_hit.confidence > best.confidence):
                best = intent_hit

        if best is None:
            return MatchResult(matched=False, route="AWEL", confidence=0.0, detail={"matchType": "none"})

        threshold = 0.99 if financial_critical else 0.88
        if best.confidence >= threshold:
            best.matched = True
            best.route = "PRECOMPILED_SCENARIO"
        elif best.confidence >= 0.82:
            best.matched = True
            best.route = "SLOT_VALIDATE"
        else:
            best.matched = False
            best.route = "AWEL"

        if best.matched and best.scenario_id:
            self.store.record_usage(best.scenario_id, field="match_count")
        return best

    def _intent_match(
        self,
        question: str,
        published: list[Any],
        *,
        q_period,
        q_family: str | None,
    ) -> MatchResult | None:
        if not q_family:
            return None
        best: MatchResult | None = None
        for inst in published:
            plan = inst.logical_plan
            if inst.family != q_family:
                continue
            if not period_compatible(q_period, plan.period):
                continue
            ent = entity_score(question, plan.entity, plan.physical_table)
            if ent < 0.35:
                continue
            per = period_score(q_period, plan.period)
            score = composite_score(
                vector_sim=ent,
                exact_token=0.0,
                entity=ent,
                period=per,
                family=1.0,
                slot_completeness=1.0 if plan.period else 0.85,
            )
            if q_period and per >= 1.0 and ent >= 0.3:
                score = min(1.0, score + 0.22)
            elif ent >= 0.45:
                score = min(1.0, score + 0.1)
            if best is None or score > best.confidence:
                best = MatchResult(
                    matched=score >= 0.88,
                    scenario_id=inst.id,
                    scenario_code=inst.scenario_code,
                    confidence=score,
                    route="PRECOMPILED_SCENARIO" if score >= 0.88 else "AWEL",
                    logical_plan=plan.to_dict(),
                    detail={
                        "matchType": "intent_slots",
                        "entityScore": ent,
                        "detectedPeriod": q_period.value if q_period else None,
                        "detectedFamily": q_family,
                    },
                )
        return best
