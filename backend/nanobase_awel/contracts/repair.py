from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from nanobase_awel.contracts.planning import SqlPlan


class GatewayErrorSafe(BaseModel):
    code: str
    safeMessage: str


class SqlRepairRequest(BaseModel):
    requestId: str = ""
    executionId: str = ""
    tenantId: str = "default"
    datasourceId: str
    question: str
    dialect: str = "postgres"
    previousSql: str
    gatewayError: GatewayErrorSafe
    attempt: int = Field(ge=1, le=2)
    authorizedContext: str = ""
    allowedTables: list[str] = Field(default_factory=list)
    schemaHint: str = ""
    promptVersion: str = "sql-repair-v1"
    modelProfile: str = "nanobaseai-bi-text2sql-v1"


class SqlRepairResult(SqlPlan):
    workflow: str = "nanobase-sql-repair-v1"
    attempt: int = 1
    previousErrorCode: str = ""
