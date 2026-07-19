"""Request principal + JWT stub (Keycloak later)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet
from uuid import UUID

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from nanobase_api.config import AuthMode, get_settings
from nanobase_api.errors import ApiError

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class RequestPrincipal:
    user_id: str
    tenant_id: str
    roles: frozenset[str]


def _dev_principal() -> RequestPrincipal:
    s = get_settings()
    return RequestPrincipal(
        user_id=s.dev_user_id,
        tenant_id=s.dev_tenant_id,
        roles=frozenset({"DATA_ANALYST", "ADMIN"}),
    )


def verify_jwt(token: str) -> RequestPrincipal:
    s = get_settings()
    try:
        claims = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError as e:
        raise ApiError("UNAUTHORIZED", "Geçersiz veya süresi dolmuş token.", status_code=401) from e
    sub = claims.get("sub")
    tenant = claims.get("tenant_id")
    if not sub or not tenant:
        raise ApiError("UNAUTHORIZED", "Token eksik claim içeriyor (sub, tenant_id).", status_code=401)
    roles = claims.get("roles") or []
    if isinstance(roles, str):
        roles = [roles]
    return RequestPrincipal(
        user_id=str(sub),
        tenant_id=str(tenant),
        roles=frozenset(str(r) for r in roles),
    )


async def get_current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> RequestPrincipal:
    s = get_settings()
    if s.auth_mode == AuthMode.DEV:
        # Optional bearer still honored if present (for tenant isolation tests)
        if credentials and credentials.credentials and credentials.credentials.count(".") == 2:
            try:
                return verify_jwt(credentials.credentials)
            except ApiError:
                pass
        return _dev_principal()

    if not credentials or not credentials.credentials:
        raise ApiError("UNAUTHORIZED", "Bearer token gerekli.", status_code=401)
    return verify_jwt(credentials.credentials)


def require_tenant_match(principal: RequestPrincipal, resource_tenant_id: str) -> None:
    if principal.tenant_id != resource_tenant_id:
        raise ApiError(
            "TENANT_ACCESS_DENIED",
            "Bu kaynağa erişim yetkiniz yok.",
            status_code=403,
        )


ROLE_BUSINESS_REVIEWER = "BUSINESS_REVIEWER"
ROLE_TECHNICAL_REVIEWER = "TECHNICAL_REVIEWER"
ROLE_SEMANTIC_PUBLISHER = "SEMANTIC_PUBLISHER"
ROLE_ADMIN = "ADMIN"
ROLE_DATA_ANALYST = "DATA_ANALYST"


def require_roles(principal: RequestPrincipal, *roles: str) -> None:
    """Require at least one of the given roles."""
    if not (principal.roles & set(roles)):
        raise ApiError(
            "FORBIDDEN",
            f"Gerekli roller: {', '.join(roles)}",
            status_code=403,
        )


def has_role(principal: RequestPrincipal, role: str) -> bool:
    return role in principal.roles


def mint_dev_token(
    *,
    user_id: str,
    tenant_id: str,
    roles: list[str] | None = None,
) -> str:
    """Helper for tests — HS256 JWT."""
    s = get_settings()
    return jwt.encode(
        {"sub": user_id, "tenant_id": tenant_id, "roles": roles or ["DATA_ANALYST"]},
        s.jwt_secret,
        algorithm=s.jwt_algorithm,
    )
