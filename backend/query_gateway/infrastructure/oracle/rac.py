"""Oracle RAC / HA connection descriptor helpers and retry policy.

Thick Mode and full RAC failover certification are gated behind vertical-slice
live GO. This module provides safe defaults used by Thin Mode profiles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.oracle.error_mapper import EXECUTION_OUTCOME_UNKNOWN

# Retry only when SQL never started and outcome is known.
RETRYABLE_PRE_EXECUTION = frozenset(
    {
        "DATABASE_UNAVAILABLE",
        "DATASOURCE_AUTHENTICATION_FAILED",
    }
)


@dataclass
class RacConnectionProfile:
    service_name: str
    hosts: list[str]
    port: int = 1521
    use_scan: bool = True
    connection_mode: str = "THIN"  # THICK requires separate process

    def easy_connect(self) -> str:
        """Simple host/service DSN (Thin). Prefer full descriptor for multi-host."""
        if len(self.hosts) == 1:
            return f"{self.hosts[0]}:{self.port}/{self.service_name}"
        return self.tns_descriptor()

    def tns_descriptor(self) -> str:
        addresses = "\n".join(
            f"(ADDRESS=(PROTOCOL=TCP)(HOST={h})(PORT={self.port}))" for h in self.hosts
        )
        return (
            "(DESCRIPTION="
            f"(ADDRESS_LIST={addresses})"
            f"(CONNECT_DATA=(SERVICE_NAME={self.service_name}))"
            ")"
        )


def should_retry_oracle(
    *,
    execution_started: bool,
    error_code: str,
    read_only: bool = True,
) -> bool:
    """Blind SQL retry is forbidden once execution may have started."""
    if execution_started:
        return False
    if not read_only:
        return False
    return error_code in RETRYABLE_PRE_EXECUTION


def mark_outcome_unknown() -> GatewayError:
    return GatewayError(
        EXECUTION_OUTCOME_UNKNOWN,
        "Oracle sorgu sonucu bilinmiyor; otomatik retry yapılmaz.",
        status=409,
        retryable=False,
    )


def thick_mode_deployment_note() -> dict[str, Any]:
    return {
        "process": "query-gateway-oracle-thick",
        "rule": "Thin and Thick cannot share one Python process",
        "init": "oracledb.init_oracle_client() before any connection",
        "when": [
            "Advanced RAC/FAN",
            "Customer-mandated Oracle Client",
            "Wallet/network configs requiring Instant Client",
        ],
    }
