"""Verified question / query + candidate scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from nanobase_api.semantic_catalog.domain.errors import ValidationError
from nanobase_api.semantic_catalog.domain.status import AssetStatus, transition

CandidateSource = Literal[
    "USER_FEEDBACK",
    "DATA_ENGINEER",
    "BUSINESS_ANALYST",
    "AWEL_HIGH_CONFIDENCE",
    "REPEATED_SUCCESS",
    "BENCHMARK",
    "SHADOW",
]


@dataclass
class NormalizedIntent:
    metric: str
    dimensions: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    period: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "dimensions": list(self.dimensions),
            "filters": dict(self.filters),
            "period": dict(self.period) if self.period else None,
        }

    def fingerprint(self) -> str:
        import hashlib
        import json

        raw = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class VerifiedQuestion:
    id: str
    tenant_id: str
    datasource_id: str
    question: str
    normalized_intent: NormalizedIntent
    status: AssetStatus = AssetStatus.DRAFT
    version: int = 1

    def transition_to(self, target: AssetStatus) -> None:
        self.status = transition(self.status, target)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenantId": self.tenant_id,
            "datasourceId": self.datasource_id,
            "question": self.question,
            "normalizedIntent": self.normalized_intent.to_dict(),
            "status": self.status.value,
            "version": self.version,
        }


@dataclass
class VerifiedQuery:
    id: str
    tenant_id: str
    datasource_id: str
    verified_question_id: str
    semantic_version: str
    schema_version: str
    dialect: str
    logical_plan: dict[str, Any]
    compiled_sql: str | None = None
    expected_result_fingerprint: str | None = None
    status: AssetStatus = AssetStatus.DRAFT
    version: int = 1

    def __post_init__(self) -> None:
        if not self.logical_plan:
            raise ValidationError("Verified query logical_plan zorunludur (fiziksel SQL ana kaynak olamaz).")
        if isinstance(self.status, str):
            self.status = AssetStatus(self.status)

    def transition_to(self, target: AssetStatus) -> None:
        self.status = transition(self.status, target)

    def scope_key(self) -> tuple[str, str, str, str, str]:
        return (
            self.tenant_id,
            self.datasource_id,
            self.semantic_version,
            self.schema_version,
            self.dialect,
        )

    def is_compatible(
        self,
        *,
        tenant_id: str,
        datasource_id: str,
        semantic_version: str,
        schema_version: str,
        dialect: str,
    ) -> bool:
        return self.scope_key() == (tenant_id, datasource_id, semantic_version, schema_version, dialect)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenantId": self.tenant_id,
            "datasourceId": self.datasource_id,
            "verifiedQuestionId": self.verified_question_id,
            "semanticVersion": self.semantic_version,
            "schemaVersion": self.schema_version,
            "dialect": self.dialect,
            "logicalPlan": dict(self.logical_plan),
            "compiledSql": self.compiled_sql,
            "expectedResultFingerprint": self.expected_result_fingerprint,
            "status": self.status.value,
            "version": self.version,
        }


@dataclass
class VerifiedQueryCandidate:
    id: str
    tenant_id: str
    datasource_id: str
    question: str
    logical_plan: dict[str, Any]
    source: CandidateSource
    sql_fingerprint: str | None = None
    execution_id: str | None = None
    candidate_score: float = 0.0
    status: AssetStatus = AssetStatus.DRAFT
    version: int = 1

    def transition_to(self, target: AssetStatus) -> None:
        self.status = transition(self.status, target)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenantId": self.tenant_id,
            "datasourceId": self.datasource_id,
            "question": self.question,
            "logicalPlan": dict(self.logical_plan),
            "source": self.source,
            "sqlFingerprint": self.sql_fingerprint,
            "executionId": self.execution_id,
            "candidateScore": self.candidate_score,
            "status": self.status.value,
            "version": self.version,
        }


def compute_candidate_score(
    *,
    execution_success: float = 0.0,
    result_equivalence: float = 0.0,
    reviewer_score: float = 0.0,
    repeated_usage: float = 0.0,
    schema_stability: float = 0.0,
    user_feedback: float = 0.0,
) -> float:
    """Review ranking only — never auto-publish."""
    score = (
        0.20 * execution_success
        + 0.25 * result_equivalence
        + 0.20 * reviewer_score
        + 0.15 * repeated_usage
        + 0.10 * schema_stability
        + 0.10 * user_feedback
    )
    return round(min(1.0, max(0.0, score)), 4)
