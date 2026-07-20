from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkflowError(Exception):
    code: str
    message: str
    retryable: bool = False
    details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
        }


OUTPUT_PARSE_FAILED = "OUTPUT_PARSE_FAILED"
SCHEMA_REFERENCE_FAILED = "SCHEMA_REFERENCE_FAILED"
INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"
METADATA_VERSION_CONFLICT = "METADATA_VERSION_CONFLICT"
TEXT_TO_SQL_MODEL_UNAVAILABLE = "TEXT_TO_SQL_MODEL_UNAVAILABLE"
SCHEMA_RETRIEVAL_UNAVAILABLE = "SCHEMA_RETRIEVAL_UNAVAILABLE"
REPAIR_NOT_ALLOWED = "REPAIR_NOT_ALLOWED"
REPAIR_LIMIT_EXCEEDED = "REPAIR_LIMIT_EXCEEDED"
FIDELITY_FAILED = "FIDELITY_FAILED"
VALIDATION_ERROR = "VALIDATION_ERROR"

REPAIRABLE_CODES = frozenset(
    {
        "SQL_PARSE_FAILED",
        "COLUMN_NOT_FOUND",
        "TABLE_NOT_FOUND",
        "TABLE_OR_VIEW_NOT_FOUND",
        "AMBIGUOUS_COLUMN",
        "FUNCTION_NOT_ALLOWED",
        "WILDCARD_NOT_ALLOWED",
        "JOIN_POLICY_VIOLATION",
        "QUERY_COST_EXCEEDED",
        "QUERY_TIMEOUT",
        "QUERY_POLICY_REJECTED",
        "SQL_EXECUTION_FAILED",
    }
)

NON_REPAIRABLE_CODES = frozenset(
    {
        "TENANT_ACCESS_DENIED",
        "SCHEMA_NOT_ALLOWED",
        "TABLE_NOT_ALLOWED",
        "COLUMN_NOT_ALLOWED",
        "SERVICE_AUTHENTICATION_FAILED",
        "VAULT_UNAVAILABLE",
        "DATABASE_UNAVAILABLE",
        "DATABASE_CONNECTION_LOST",
    }
)
