from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class QueryLimits(BaseModel):
    maxRows: Optional[int] = None
    timeoutMs: Optional[int] = None
    maxColumns: Optional[int] = None
    maxPayloadBytes: Optional[int] = None


class ValidateRequest(BaseModel):
    executionId: str = Field(..., min_length=1)
    tenantId: Optional[str] = None
    userId: Optional[str] = None
    datasourceId: str = Field(..., min_length=1)
    conversationId: Optional[str] = None
    dialect: Optional[str] = "postgres"
    sql: str = Field(..., min_length=1)
    purpose: Optional[str] = "INTERACTIVE_ANALYSIS"
    limits: Optional[QueryLimits] = None


class ValidateApproved(BaseModel):
    executionId: str
    status: Literal["APPROVED"] = "APPROVED"
    statementType: str = "SELECT"
    normalizedSql: str
    sqlFingerprint: str
    schemas: list[str] = []
    tables: list[str] = []
    columns: list[str] = []
    functions: list[str] = []
    warnings: list[str] = []
    policyVersion: str


class ExecuteRequest(BaseModel):
    executionId: str = Field(..., min_length=1)
    tenantId: Optional[str] = None
    userId: Optional[str] = None
    datasourceId: str = Field(..., min_length=1)
    conversationId: Optional[str] = None
    dialect: Optional[str] = "postgres"
    sql: str = Field(..., min_length=1)
    purpose: Optional[str] = "INTERACTIVE_ANALYSIS"
    limits: Optional[QueryLimits] = None
