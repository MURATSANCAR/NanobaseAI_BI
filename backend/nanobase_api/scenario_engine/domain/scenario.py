"""Scenario registry entities."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from nanobase_api.scenario_engine.domain.errors import ValidationError
from nanobase_api.scenario_engine.domain.logical_plan import LogicalPlan
from nanobase_api.scenario_engine.domain.risk import RiskTier
from nanobase_api.scenario_engine.domain.status import ScenarioStatus, transition

_TR_MAP = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def normalize_question(text: str) -> str:
    s = (text or "").strip().translate(_TR_MAP)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def question_hash(text: str) -> str:
    return hashlib.sha256(normalize_question(text).encode("utf-8")).hexdigest()


@dataclass
class ScenarioTemplate:
    code: str
    family: str
    required_slots: list[str]
    optional_slots: list[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "family": self.family,
            "requiredSlots": list(self.required_slots),
            "optionalSlots": list(self.optional_slots),
            "description": self.description,
        }


@dataclass
class ScenarioInstance:
    id: str
    tenant_id: str
    datasource_id: str
    scenario_code: str
    family: str
    logical_plan: LogicalPlan
    schema_version: str
    semantic_version: str
    policy_version: str = "2026.07.1"
    risk_tier: RiskTier = RiskTier.A
    status: ScenarioStatus = ScenarioStatus.GENERATED
    category: str = "Faturalar"
    canonical_question: str = ""
    generator_version: str = "1.0.0"
    version: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            self.status = ScenarioStatus(self.status)
        if isinstance(self.risk_tier, str):
            self.risk_tier = RiskTier(self.risk_tier)
        if isinstance(self.logical_plan, dict):
            self.logical_plan = LogicalPlan.from_dict(self.logical_plan)
        if not self.scenario_code:
            raise ValidationError("scenario_code required")

    def transition_to(self, target: ScenarioStatus) -> None:
        self.status = transition(self.status, target)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenantId": self.tenant_id,
            "datasourceId": self.datasource_id,
            "scenarioCode": self.scenario_code,
            "family": self.family,
            "logicalPlan": self.logical_plan.to_dict(),
            "schemaVersion": self.schema_version,
            "semanticVersion": self.semantic_version,
            "policyVersion": self.policy_version,
            "riskTier": self.risk_tier.value,
            "status": self.status.value,
            "category": self.category,
            "canonicalQuestion": self.canonical_question,
            "generatorVersion": self.generator_version,
            "version": self.version,
        }


@dataclass
class ScenarioParaphrase:
    id: str
    scenario_id: str
    language: str
    text: str
    status: ScenarioStatus = ScenarioStatus.GENERATED
    embedding_id: str | None = None
    tenant_id: str = "default"
    datasource_id: str = "default"

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            self.status = ScenarioStatus(self.status)

    @property
    def normalized_text(self) -> str:
        return normalize_question(self.text)

    @property
    def normalized_hash(self) -> str:
        return question_hash(self.text)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "scenarioId": self.scenario_id,
            "language": self.language,
            "text": self.text,
            "normalizedText": self.normalized_text,
            "normalizedQuestionHash": self.normalized_hash,
            "embeddingId": self.embedding_id,
            "status": self.status.value,
            "tenantId": self.tenant_id,
            "datasourceId": self.datasource_id,
        }


@dataclass
class ScenarioCompilation:
    id: str
    scenario_id: str
    dialect: str
    sql_template: str
    ast_fingerprint: str
    validation_status: str = "PENDING"
    bind_params: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "scenarioId": self.scenario_id,
            "dialect": self.dialect,
            "sqlTemplate": self.sql_template,
            "astFingerprint": self.ast_fingerprint,
            "validationStatus": self.validation_status,
            "bindParams": list(self.bind_params),
        }


@dataclass
class CostProfile:
    classification: str = "LOW"
    max_rows: int = 100
    timeout_ms: int = 5000
    max_payload_bytes: int = 1_048_576
    estimated_rows: int | None = None
    join_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "maxRows": self.max_rows,
            "timeoutMs": self.timeout_ms,
            "maxPayloadBytes": self.max_payload_bytes,
            "estimatedRows": self.estimated_rows,
            "joinCount": self.join_count,
        }


@dataclass
class PublishBatch:
    id: str
    tenant_id: str
    datasource_id: str
    schema_version: str
    semantic_version: str
    status: ScenarioStatus = ScenarioStatus.PREPARING
    scenario_count: int = 0
    checksum: str | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            self.status = ScenarioStatus(self.status)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenantId": self.tenant_id,
            "datasourceId": self.datasource_id,
            "schemaVersion": self.schema_version,
            "semanticVersion": self.semantic_version,
            "status": self.status.value,
            "scenarioCount": self.scenario_count,
            "checksum": self.checksum,
            "error": self.error,
        }
