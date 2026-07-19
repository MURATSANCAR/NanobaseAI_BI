"""Exact / semantic scenario matcher with composite confidence score."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from nanobase_api.scenario_engine.domain.scenario import normalize_question, question_hash
from nanobase_api.scenario_engine.domain.status import ScenarioStatus, is_retrieval_eligible
from nanobase_api.scenario_engine.infrastructure.qdrant_publisher import ScenarioQdrantPublisher
from nanobase_api.scenario_engine.infrastructure.store import ScenarioStore, get_scenario_store

_ENTITY_TOKENS = {
    "fatura": "invoice",
    "faturalar": "invoice",
    "faturaları": "invoice",
    "müşteri": "customer",
    "musteri": "customer",
    "ürün": "product",
    "urun": "product",
}

_PERIOD_TOKENS = {
    "bugün": "TODAY",
    "bugun": "TODAY",
    "bugüne": "TODAY",
    "bugunki": "TODAY",
    "dün": "YESTERDAY",
    "dun": "YESTERDAY",
    "geçen ay": "PREVIOUS_MONTH",
    "gecen ay": "PREVIOUS_MONTH",
    "bu ay": "CURRENT_MONTH",
    "vadesi": "AGING",
    "ödenmemiş": "UNPAID",
    "odenmemis": "UNPAID",
    "iptal": "CANCELLED",
}


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


def _entity_match(question: str, entity: str) -> float:
    q = normalize_question(question)
    for tok, ent in _ENTITY_TOKENS.items():
        if tok in q and ent == entity:
            return 1.0
    return 0.2 if entity in q else 0.0


def _period_match(question: str, period: str | None) -> float:
    if not period:
        return 0.5
    q = normalize_question(question)
    for phrase, kind in _PERIOD_TOKENS.items():
        if phrase in q and (kind == period or kind in ("AGING", "UNPAID", "CANCELLED")):
            return 1.0
    return 0.3


def composite_score(
    *,
    vector_sim: float,
    exact_token: float,
    entity: float,
    period: float,
    slot_completeness: float,
    popularity: float = 0.0,
    historical_success: float = 0.0,
    ambiguity_penalty: float = 0.0,
) -> float:
    score = (
        0.35 * vector_sim
        + 0.20 * exact_token
        + 0.15 * entity
        + 0.15 * period
        + 0.10 * slot_completeness
        + 0.03 * popularity
        + 0.02 * historical_success
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

        # 1) Exact normalized hash
        qh = question_hash(q)
        para = self.store.find_by_normalized_hash(
            tenant_id=tenant_id, datasource_id=datasource_id, qhash=qh
        )
        if para is not None:
            inst = self.store.get_instance(para.scenario_id)
            if inst and is_retrieval_eligible(inst.status):
                if schema_version and inst.schema_version != schema_version:
                    return MatchResult(matched=False, route="AWEL", detail={"reason": "schema_mismatch"})
                self.store.record_usage(inst.id, field="match_count")
                return MatchResult(
                    matched=True,
                    scenario_id=inst.id,
                    scenario_code=inst.scenario_code,
                    confidence=0.99,
                    route="PRECOMPILED_SCENARIO",
                    logical_plan=inst.logical_plan.to_dict(),
                    detail={"matchType": "exact"},
                )

        # 2) Verified paraphrase fuzzy (in-store token overlap)
        published = self.store.list_instances(
            tenant_id=tenant_id, datasource_id=datasource_id, status=ScenarioStatus.PUBLISHED
        )
        best: MatchResult | None = None
        for inst in published:
            if schema_version and inst.schema_version != schema_version:
                continue
            if semantic_version and inst.semantic_version != semantic_version:
                continue
            candidates = [inst.canonical_question] + [
                p.text for p in self.store.paraphrases_for_scenario(inst.id) if is_retrieval_eligible(p.status)
            ]
            for text in candidates:
                tok = _token_overlap(q, text)
                if tok < 0.55:
                    continue
                ent = _entity_match(q, inst.logical_plan.entity)
                per = _period_match(q, inst.logical_plan.period)
                score = composite_score(
                    vector_sim=tok,
                    exact_token=tok,
                    entity=ent,
                    period=per,
                    slot_completeness=1.0 if inst.logical_plan.period else 0.8,
                )
                if best is None or score > best.confidence:
                    best = MatchResult(
                        matched=score >= 0.90,
                        scenario_id=inst.id,
                        scenario_code=inst.scenario_code,
                        confidence=score,
                        route="PRECOMPILED_SCENARIO" if score >= 0.90 else "AWEL",
                        logical_plan=inst.logical_plan.to_dict(),
                        detail={"matchType": "paraphrase_token"},
                    )

        # 3) Qdrant vector
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
                    vec = float(top.get("score") or 0)
                    score = composite_score(
                        vector_sim=vec,
                        exact_token=_token_overlap(q, inst.canonical_question),
                        entity=_entity_match(q, inst.logical_plan.entity),
                        period=_period_match(q, inst.logical_plan.period),
                        slot_completeness=0.9,
                    )
                    if best is None or score > best.confidence:
                        best = MatchResult(
                            matched=score >= 0.90,
                            scenario_id=inst.id,
                            scenario_code=inst.scenario_code,
                            confidence=score,
                            route="PRECOMPILED_SCENARIO" if score >= 0.90 else "SLOT_VALIDATE",
                            logical_plan=inst.logical_plan.to_dict(),
                            detail={"matchType": "semantic", "vectorScore": vec},
                        )

        # 4) Intent family heuristic
        if best is None:
            intent = self._intent_family(q)
            if intent:
                for inst in published:
                    if inst.family == intent["family"] and inst.logical_plan.entity == intent["entity"]:
                        if intent.get("period") and inst.logical_plan.period != intent["period"]:
                            continue
                        score = 0.91
                        best = MatchResult(
                            matched=True,
                            scenario_id=inst.id,
                            scenario_code=inst.scenario_code,
                            confidence=score,
                            route="PRECOMPILED_SCENARIO",
                            logical_plan=inst.logical_plan.to_dict(),
                            detail={"matchType": "intent_family"},
                        )
                        break

        if best is None:
            return MatchResult(matched=False, route="AWEL", confidence=0.0, detail={"matchType": "none"})

        threshold = 0.99 if financial_critical else 0.97
        if best.confidence >= threshold:
            best.matched = True
            best.route = "PRECOMPILED_SCENARIO"
        elif best.confidence >= 0.90:
            best.matched = True
            best.route = "SLOT_VALIDATE"
        else:
            best.matched = False
            best.route = "AWEL"

        if best.matched and best.scenario_id:
            self.store.record_usage(best.scenario_id, field="match_count")
        return best

    def _intent_family(self, question: str) -> dict[str, str] | None:
        q = normalize_question(question)
        entity = None
        for tok, ent in _ENTITY_TOKENS.items():
            if tok in q:
                entity = ent
                break
        if entity is None:
            return None
        period = None
        for phrase, kind in _PERIOD_TOKENS.items():
            if phrase in q and kind.endswith("MONTH") or kind in ("TODAY", "YESTERDAY"):
                if phrase in q:
                    period = kind if kind not in ("AGING", "UNPAID", "CANCELLED") else None
                    break
        # detect via patterns more carefully
        if "gecen ay" in q or "geçen ay" in normalize_question(question):
            period = "PREVIOUS_MONTH"
        elif "bugun" in q or "bugün" in question.lower():
            period = "TODAY"
        family = "LIST_ENTITY"
        if "kaç" in q or "sayısı" in q or "sayisi" in q:
            family = "COUNT_ENTITY"
        elif "toplam" in q:
            family = "SUM_MEASURE"
        elif "vadesi" in q:
            family = "AGING"
        elif "iptal" in q:
            family = "STATUS_FILTER"
        elif "odenmemis" in q or "ödenmemiş" in question.lower():
            family = "STATUS_FILTER"
        out: dict[str, str] = {"family": family, "entity": entity}
        if period:
            out["period"] = period
        return out
