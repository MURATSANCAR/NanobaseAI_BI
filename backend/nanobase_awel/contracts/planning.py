from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class PlanStatus(str, Enum):
    PLANNED = "PLANNED"
    AMBIGUOUS = "AMBIGUOUS"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"
    UNSUPPORTED = "UNSUPPORTED"
    FAILED = "FAILED"


class RetrievalScope(BaseModel):
    allowedSchemas: list[str] = Field(default_factory=list)
    allowedDocumentTypes: list[str] = Field(
        default_factory=lambda: ["TABLE", "COLUMN", "RELATIONSHIP", "BUSINESS_TERM", "VERIFIED_SQL"]
    )
    maxDocuments: int = 30


class GenerationConfig(BaseModel):
    promptVersion: str = "sql-plan-v1"
    modelProfile: str = "qwen35b-text2sql-v1"


class ConversationContext(BaseModel):
    summary: str = ""
    recentTurns: list[dict[str, Any]] = Field(default_factory=list)
    structured: dict[str, Any] = Field(default_factory=dict)


class SqlPlanningRequest(BaseModel):
    requestId: str = ""
    traceId: str = ""
    executionId: str = ""
    tenantId: str = "default"
    userId: Optional[str] = None
    datasourceId: str
    conversationId: Optional[str] = None
    question: str = Field(..., min_length=1, max_length=8192)
    dialect: str = "postgres"
    language: str = "tr"
    metadataVersion: str = ""
    conversationContext: ConversationContext = Field(default_factory=ConversationContext)
    retrievalScope: RetrievalScope = Field(default_factory=RetrievalScope)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    schemaHint: str = ""
    retrievedSchema: str = ""
    allowedTables: list[str] = Field(default_factory=list)
    allowedColumns: list[str] = Field(default_factory=list)


class SqlPlan(BaseModel):
    status: PlanStatus = PlanStatus.PLANNED
    sql: Optional[str] = None
    dialect: str = "postgres"
    tables: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    functions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    clarificationQuestion: Optional[str] = None
    confidence: Optional[float] = None
    promptVersion: str = "sql-plan-v1"
    modelProfile: str = "qwen35b-text2sql-v1"
    metadataVersion: str = ""
    workflow: str = "nanobase-sql-plan-v1"
    executes: bool = False
    retrieval_used: bool = False

    @field_validator("confidence")
    @classmethod
    def _clamp_conf(cls, v: float | None) -> float | None:
        if v is None:
            return v
        return max(0.0, min(1.0, float(v)))

    def to_legacy_dict(self) -> dict[str, Any]:
        return {
            "workflow": self.workflow,
            "status": self.status.value,
            "sql": self.sql or "",
            "dialect": self.dialect,
            "tables": self.tables,
            "columns": self.columns,
            "functions": self.functions,
            "assumptions": self.assumptions,
            "warnings": self.warnings,
            "ambiguities": self.ambiguities,
            "clarificationQuestion": self.clarificationQuestion,
            "confidence": self.confidence if self.confidence is not None else 0.5,
            "promptVersion": self.promptVersion,
            "modelProfile": self.modelProfile,
            "metadataVersion": self.metadataVersion,
            "executes": False,
            "retrieval_used": self.retrieval_used,
        }
