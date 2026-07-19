"""Gateway error codes and exceptions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GatewayError(Exception):
    code: str
    message: str
    status: int = 400
    retryable: bool = False
    execution_id: str | None = None
    trace_id: str | None = None
    details: list[dict[str, Any]] = field(default_factory=list)
    policy_version: str | None = None

    def __str__(self) -> str:
        return self.message

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "executionId": self.execution_id,
            "traceId": self.trace_id,
            "retryable": self.retryable,
            "details": self.details,
            "policyVersion": self.policy_version,
        }


# Canonical codes
SERVICE_AUTHENTICATION_FAILED = "SERVICE_AUTHENTICATION_FAILED"
REQUEST_SIGNATURE_INVALID = "REQUEST_SIGNATURE_INVALID"
REPLAY_REQUEST_DETECTED = "REPLAY_REQUEST_DETECTED"
DATASOURCE_NOT_FOUND = "DATASOURCE_NOT_FOUND"
DATASOURCE_NOT_READY = "DATASOURCE_NOT_READY"
DATASOURCE_POLICY_NOT_FOUND = "DATASOURCE_POLICY_NOT_FOUND"
VAULT_UNAVAILABLE = "VAULT_UNAVAILABLE"
DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"
SQL_PARSE_FAILED = "SQL_PARSE_FAILED"
MULTIPLE_STATEMENTS_NOT_ALLOWED = "MULTIPLE_STATEMENTS_NOT_ALLOWED"
STATEMENT_NOT_ALLOWED = "STATEMENT_NOT_ALLOWED"
FUNCTION_NOT_ALLOWED = "FUNCTION_NOT_ALLOWED"
SCHEMA_NOT_ALLOWED = "SCHEMA_NOT_ALLOWED"
TABLE_NOT_ALLOWED = "TABLE_NOT_ALLOWED"
COLUMN_NOT_ALLOWED = "COLUMN_NOT_ALLOWED"
WILDCARD_NOT_ALLOWED = "WILDCARD_NOT_ALLOWED"
JOIN_POLICY_VIOLATION = "JOIN_POLICY_VIOLATION"
TENANT_POLICY_MISSING = "TENANT_POLICY_MISSING"
QUERY_COST_EXCEEDED = "QUERY_COST_EXCEEDED"
QUERY_TIMEOUT = "QUERY_TIMEOUT"
RESULT_LIMIT_EXCEEDED = "RESULT_LIMIT_EXCEEDED"
RESULT_MASKING_FAILED = "RESULT_MASKING_FAILED"
AUDIT_WRITE_FAILED = "AUDIT_WRITE_FAILED"
INTERNAL_ERROR = "INTERNAL_ERROR"
CONTRACT_VERSION_NOT_SUPPORTED = "CONTRACT_VERSION_NOT_SUPPORTED"
