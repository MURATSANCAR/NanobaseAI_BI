"""Short-lived service JWT validation."""

from __future__ import annotations

import time
from typing import Any

import jwt

from query_gateway.config.settings import Settings
from query_gateway.domain.errors import SERVICE_AUTHENTICATION_FAILED, GatewayError


def mint_service_token(
    settings: Settings,
    *,
    scopes: list[str],
    jti: str,
    ttl_s: int | None = None,
) -> str:
    if not settings.service_jwt_secret:
        raise GatewayError(
            SERVICE_AUTHENTICATION_FAILED,
            "Service JWT secret yapılandırılmamış.",
            status=503,
        )
    now = int(time.time())
    ttl = ttl_s or settings.jwt_ttl_s
    payload = {
        "iss": settings.service_jwt_issuer,
        "aud": settings.service_jwt_audience,
        "sub": "nanobase-backend",
        "jti": jti,
        "iat": now,
        "exp": now + ttl,
        "scope": scopes,
    }
    return jwt.encode(payload, settings.service_jwt_secret, algorithm="HS256")


def validate_service_token(
    token: str,
    settings: Settings,
    *,
    required_scope: str,
) -> dict[str, Any]:
    if not settings.service_jwt_secret:
        raise GatewayError(
            SERVICE_AUTHENTICATION_FAILED,
            "Service JWT secret yapılandırılmamış.",
            status=503,
        )
    try:
        payload = jwt.decode(
            token,
            settings.service_jwt_secret,
            algorithms=["HS256"],
            audience=settings.service_jwt_audience,
            issuer=settings.service_jwt_issuer,
        )
    except jwt.PyJWTError as e:
        raise GatewayError(
            SERVICE_AUTHENTICATION_FAILED,
            "Service kimlik doğrulaması başarısız.",
            status=401,
        ) from e

    scopes = payload.get("scope") or []
    if isinstance(scopes, str):
        scopes = scopes.split()
    if required_scope not in scopes:
        raise GatewayError(
            SERVICE_AUTHENTICATION_FAILED,
            "Gerekli scope yok.",
            status=403,
        )
    return payload
