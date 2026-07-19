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
        roles=frozenset({ROLE_DATA_ANALYST, ROLE_ADMIN, ROLE_DATA_ENGINEER}),
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
    portal = claims.get("portal_role") or claims.get("role")
    if portal:
        roles = list(roles) + [str(portal)]
    return RequestPrincipal(
        user_id=str(sub),
        tenant_id=str(tenant),
        roles=normalize_roles(roles),
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
ROLE_DATA_ENGINEER = "DATA_ENGINEER"

# Portal lowercase roles → JWT capability roles (Faz 1–4 RBAC).
_PORTAL_ROLE_MAP: dict[str, frozenset[str]] = {
    "admin": frozenset(
        {ROLE_ADMIN, ROLE_DATA_ENGINEER, ROLE_DATA_ANALYST, ROLE_SEMANTIC_PUBLISHER}
    ),
    "manager": frozenset({ROLE_DATA_ENGINEER, ROLE_DATA_ANALYST}),
    "developer": frozenset({ROLE_DATA_ANALYST}),
    "qa": frozenset(),
}


def normalize_roles(raw: list[str] | tuple[str, ...] | set[str] | frozenset[str]) -> frozenset[str]:
    """Expand portal role names and uppercase known JWT roles."""
    out: set[str] = set()
    for r in raw:
        key = str(r).strip()
        if not key:
            continue
        low = key.lower()
        if low in _PORTAL_ROLE_MAP:
            out |= set(_PORTAL_ROLE_MAP[low])
            continue
        out.add(key.upper())
    return frozenset(out)


def require_roles(principal: RequestPrincipal, *roles: str) -> None:
    """Require at least one of the given roles."""
    if not (principal.roles & set(roles)):
        raise ApiError(
            "FORBIDDEN",
            f"Gerekli roller: {', '.join(roles)}",
            status_code=403,
        )


def require_source_admin(principal: RequestPrincipal) -> None:
    """Datasource write / test / schema scan — ADMIN or DATA_ENGINEER."""
    require_roles(principal, ROLE_ADMIN, ROLE_DATA_ENGINEER)


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
