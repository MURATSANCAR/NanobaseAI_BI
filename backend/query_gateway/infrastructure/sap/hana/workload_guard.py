"""HANA workload class policy."""

from __future__ import annotations

import os

from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.sap.contracts.datasource import HanaDatasourceConfig

HANA_WORKLOAD_POLICY_MISSING = "HANA_WORKLOAD_POLICY_MISSING"

DEFAULT_TIMEOUT_S = 15


def enforce_workload_policy(cfg: HanaDatasourceConfig) -> dict[str, int | str]:
    if cfg.require_workload_class and not cfg.workload_class:
        raise GatewayError(
            HANA_WORKLOAD_POLICY_MISSING,
            "HANA workload class required for production execute.",
            status=403,
        )
    # Env can force missing-policy chaos / ops mode
    if os.environ.get("SAP_HANA_REQUIRE_WORKLOAD", "1") == "1" and not cfg.workload_class:
        raise GatewayError(
            HANA_WORKLOAD_POLICY_MISSING,
            "HANA workload policy missing.",
            status=403,
        )
    return {
        "workloadClass": cfg.workload_class or "NANOBASE_INTERACTIVE_QUERY",
        "statementTimeoutS": DEFAULT_TIMEOUT_S,
    }
