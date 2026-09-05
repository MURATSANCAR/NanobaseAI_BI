from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ResultExplanationRequest(BaseModel):
    requestId: str = ""
    executionId: str = ""
    tenantId: str = "default"
    datasourceId: str = ""
    question: str
    executedSql: str
    columns: list[Any] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    truncated: bool = False
    language: str = "tr"
    promptVersion: str = "result-explain-v1"
    modelProfile: str = "nanobaseai-bi-explain-v1"


class ResultExplanation(BaseModel):
    workflow: str = "nanobase-result-explain-v1"
    answer: str
    insights: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    executes: bool = False
    fidelityPassed: bool = True
    usedFallback: bool = False
    summary: dict[str, Any] = Field(default_factory=dict)

    def to_legacy_dict(self) -> dict[str, Any]:
        return {
            "workflow": self.workflow,
            "answer": self.answer,
            "insights": self.insights,
            "warnings": self.warnings,
            "executes": False,
            "fidelityPassed": self.fidelityPassed,
            "usedFallback": self.usedFallback,
            "summary": self.summary,
        }
