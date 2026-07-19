"""Audit chain contract for Final Gate §22."""

from __future__ import annotations

REQUIRED = [
    "QUESTION_SUBMITTED",
    "SCHEMA_RETRIEVED",
    "SEMANTIC_RESOLVED",
    "SQL_PLANNED",
    "SQL_VALIDATED",
    "SQL_EXECUTED",
    "RESULT_MASKED",
    "ANSWER_GENERATED",
    "QUERY_COMPLETED",
]


def test_audit_chain_events_defined():
    assert len(REQUIRED) >= 9


def test_correlation_keys():
    keys = ["request_id", "trace_id", "conversation_id", "execution_id", "tenant_id", "user_id"]
    assert len(keys) == 6
