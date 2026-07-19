"""HANA error mapping."""

from __future__ import annotations

from query_gateway.domain.errors import GatewayError

HANA_TIMEOUT = "HANA_TIMEOUT"
HANA_EXECUTION_FAILED = "HANA_EXECUTION_FAILED"
HANA_MEMORY_LIMIT = "HANA_MEMORY_LIMIT_REJECTION"


def map_hana_exception(exc: BaseException) -> GatewayError:
    msg = str(exc)
    low = msg.lower()
    if "timeout" in low or "communication timeout" in low:
        return GatewayError(HANA_TIMEOUT, "HANA statement timeout.", status=504)
    if "memory" in low and "limit" in low:
        return GatewayError(HANA_MEMORY_LIMIT, "HANA memory limit exceeded.", status=400)
    return GatewayError(HANA_EXECUTION_FAILED, "HANA execution failed.", status=400)
