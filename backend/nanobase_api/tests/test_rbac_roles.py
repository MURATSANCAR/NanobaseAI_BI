#!/usr/bin/env python3
"""Portal role normalization + source-admin gate."""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("AUTH_MODE", "jwt")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("NANOBASE_ENV", "development")


def test_normalize_portal_roles():
    from nanobase_api.auth.principal import (
        ROLE_ADMIN,
        ROLE_DATA_ANALYST,
        ROLE_DATA_ENGINEER,
        normalize_roles,
    )

    assert ROLE_ADMIN in normalize_roles(["admin"])
    assert ROLE_DATA_ENGINEER in normalize_roles(["manager"])
    assert ROLE_DATA_ANALYST in normalize_roles(["developer"])
    assert len(normalize_roles(["qa"])) == 0
    assert ROLE_DATA_ENGINEER in normalize_roles(["DATA_ENGINEER"])
    print("normalize_portal_roles ok")


def test_require_source_admin():
    from nanobase_api.auth.principal import (
        RequestPrincipal,
        ROLE_DATA_ANALYST,
        ROLE_DATA_ENGINEER,
        require_source_admin,
    )
    from nanobase_api.errors import ApiError

    eng = RequestPrincipal("u", "t", frozenset({ROLE_DATA_ENGINEER}))
    require_source_admin(eng)

    analyst = RequestPrincipal("u", "t", frozenset({ROLE_DATA_ANALYST}))
    try:
        require_source_admin(analyst)
        raise AssertionError("expected FORBIDDEN")
    except ApiError as e:
        assert e.code == "FORBIDDEN"
    print("require_source_admin ok")


def test_jwt_portal_role_claim():
    from nanobase_api.auth.principal import ROLE_DATA_ENGINEER, mint_dev_token, verify_jwt

    tok = mint_dev_token(user_id="m1", tenant_id="t1", roles=["manager"])
    p = verify_jwt(tok)
    assert ROLE_DATA_ENGINEER in p.roles
    print("jwt_portal_role_claim ok")


if __name__ == "__main__":
    test_normalize_portal_roles()
    test_require_source_admin()
    test_jwt_portal_role_claim()
    print("all rbac tests ok")
