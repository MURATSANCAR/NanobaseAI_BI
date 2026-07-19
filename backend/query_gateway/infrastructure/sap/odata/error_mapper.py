"""Map OData/HTTP errors to GatewayError codes."""

from __future__ import annotations

from query_gateway.domain.errors import GatewayError

SAP_SERVICE_UNAVAILABLE = "SAP_SERVICE_UNAVAILABLE"
SAP_METADATA_VERSION_CONFLICT = "SAP_METADATA_VERSION_CONFLICT"
SAP_UNAUTHORIZED = "SAP_UNAUTHORIZED"
ODATA_EXECUTION_FAILED = "ODATA_EXECUTION_FAILED"


def map_odata_http_error(status: int, body: str = "") -> GatewayError:
    snippet = (body or "")[:200]
    if status in (401, 403):
        return GatewayError(SAP_UNAUTHORIZED, f"SAP OData auth failed ({status}).", status=403)
    if status in (502, 503, 504):
        return GatewayError(
            SAP_SERVICE_UNAVAILABLE,
            "SAP service unavailable.",
            status=503,
        )
    if status == 409:
        return GatewayError(
            SAP_METADATA_VERSION_CONFLICT,
            "SAP metadata version conflict.",
            status=409,
        )
    return GatewayError(
        ODATA_EXECUTION_FAILED,
        f"OData HTTP {status}: {snippet}",
        status=400,
    )
