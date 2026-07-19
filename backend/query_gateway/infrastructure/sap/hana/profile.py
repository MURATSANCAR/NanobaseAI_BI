"""HANA connection profile — forbid SYSTEM / schema-owner style accounts."""

from __future__ import annotations

from typing import Any

from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.sap.contracts.datasource import HanaDatasourceConfig

HANA_PROFILE_INVALID = "HANA_PROFILE_INVALID"

FORBIDDEN_HANA_USERS = frozenset(
    {
        "SYSTEM",
        "SYS",
        "SAPDBCTRL",
        "_SYS_REPO",
        "_SYS_STATISTICS",
        "DBADMIN",
    }
)


def validate_hana_username(username: str | None) -> str:
    user = (username or "").strip()
    if not user:
        raise GatewayError(HANA_PROFILE_INVALID, "HANA username required.", status=400)
    if user.upper() in FORBIDDEN_HANA_USERS:
        raise GatewayError(
            HANA_PROFILE_INVALID,
            f"Forbidden HANA user: {user}",
            status=403,
        )
    if user.upper().endswith("_OWNER") or user.upper() == "SCHEMA_OWNER":
        raise GatewayError(HANA_PROFILE_INVALID, "Schema owner user denied.", status=403)
    return user


def build_hana_profile(ds: dict[str, Any]) -> HanaDatasourceConfig:
    cfg = HanaDatasourceConfig.from_datasource(ds)
    validate_hana_username(cfg.user)
    if not cfg.host:
        raise GatewayError(HANA_PROFILE_INVALID, "HANA host required.", status=400)
    if not cfg.encrypt:
        raise GatewayError(HANA_PROFILE_INVALID, "HANA TLS encrypt is required.", status=400)
    if not cfg.validate_certificate:
        # Allow only when explicitly overridden in non-prod via allow_insecure_tls
        if not ds.get("allow_insecure_tls"):
            raise GatewayError(
                HANA_PROFILE_INVALID,
                "HANA certificate validation required (set allow_insecure_tls only for sandbox).",
                status=400,
            )
    if not cfg.allowed_views and not cfg.allowed_schemas:
        raise GatewayError(
            HANA_PROFILE_INVALID,
            "allowedViews or allowedSchemas required.",
            status=400,
        )
    return cfg
