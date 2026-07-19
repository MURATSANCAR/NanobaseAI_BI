"""Unit tests for RAC retry / descriptor helpers."""

from __future__ import annotations

from query_gateway.infrastructure.oracle.rac import (
    RacConnectionProfile,
    should_retry_oracle,
    thick_mode_deployment_note,
)


def test_tns_descriptor_multi_host():
    p = RacConnectionProfile(
        service_name="FINPDB",
        hosts=["host1", "host2"],
        port=1521,
    )
    dsn = p.tns_descriptor()
    assert "SERVICE_NAME=FINPDB" in dsn
    assert "HOST=host1" in dsn
    assert "HOST=host2" in dsn


def test_no_retry_after_execution_started():
    assert should_retry_oracle(execution_started=True, error_code="DATABASE_UNAVAILABLE") is False


def test_retry_pre_execution_unavailable():
    assert should_retry_oracle(execution_started=False, error_code="DATABASE_UNAVAILABLE") is True


def test_thick_note():
    note = thick_mode_deployment_note()
    assert note["process"] == "query-gateway-oracle-thick"
