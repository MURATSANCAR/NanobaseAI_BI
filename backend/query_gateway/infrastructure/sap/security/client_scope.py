"""Client/MANDT scope — enforced by approved CDS/view, verified in functional tests."""

from __future__ import annotations

from query_gateway.domain.errors import GatewayError

SAP_CLIENT_SCOPE_VIOLATION = "SAP_CLIENT_SCOPE_VIOLATION"


def assert_client_not_user_controlled(plan_filters: list[dict]) -> None:
    for f in plan_filters:
        field = str(f.get("field") or "").upper()
        if field in ("MANDT", "CLIENT", "SAPCLIENT"):
            raise GatewayError(
                SAP_CLIENT_SCOPE_VIOLATION,
                "Client/MANDT must not be LLM-controlled; use approved source semantics.",
                status=403,
            )
