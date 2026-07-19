#!/usr/bin/env python3
"""Faz 3 unit checks (no live DB required for auth/fingerprint-style tests)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

os.environ.setdefault("AUTH_MODE", "jwt")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("NANOBASE_ENV", "development")


def test_jwt_tenant():
    from nanobase_api.auth import mint_dev_token, verify_jwt
    from nanobase_api.errors import ApiError

    tok_a = mint_dev_token(user_id="u1", tenant_id="tenant-a")
    p = verify_jwt(tok_a)
    assert p.tenant_id == "tenant-a"
    tok_b = mint_dev_token(user_id="u2", tenant_id="tenant-b")
    p2 = verify_jwt(tok_b)
    assert p2.tenant_id == "tenant-b"
    try:
        verify_jwt("not.a.jwt")
        raise AssertionError("expected fail")
    except ApiError as e:
        assert e.code == "UNAUTHORIZED"
    print("jwt_tenant ok")


def test_execution_mode_guard():
    os.environ["NANOBASE_ENV"] = "production"
    os.environ["NANOBASE_TEXT2SQL_EXECUTION_MODE"] = "TEST_DIRECT"
    from nanobase_api import config

    config.get_settings.cache_clear()
    try:
        config.get_settings()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as e:
        assert "TEST_DIRECT" in str(e)
    os.environ["NANOBASE_TEXT2SQL_EXECUTION_MODE"] = "QUERY_GATEWAY"
    config.get_settings.cache_clear()
    assert config.get_settings().execution_mode.value == "QUERY_GATEWAY"
    print("execution_mode ok")


def test_audit_masking():
    from nanobase_api.infrastructure.audit_repo import _mask_extra

    m = _mask_extra({"password": "secret", "datasource_id": "x", "token": "abc"})
    assert m["password"] == "***"
    assert m["token"] == "***"
    assert m["datasource_id"] == "x"
    print("audit_mask ok")


if __name__ == "__main__":
    test_jwt_tenant()
    test_execution_mode_guard()
    test_audit_masking()
    print("all faz3 unit ok")
