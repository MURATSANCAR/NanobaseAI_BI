"""Unit tests for team / public share link store."""

from __future__ import annotations

from pathlib import Path

import pytest

from nanobase_api import shares as shares_mod


@pytest.fixture()
def shares_tmpdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRETS_ROOT", str(tmp_path))
    return tmp_path


def test_create_list_delete_share(shares_tmpdir: Path):
    created = shares_mod.create_share(
        resource_type="superset_dashboard",
        resource_id="42",
        ttl_hours=24,
        tenant_id="acme",
    )
    assert created["token"]
    assert created["resource_id"] == "42"
    assert created["password_protected"] is False
    assert created["expires_at"]

    listed = shares_mod.list_shares(tenant_id="acme")
    assert len(listed) == 1
    assert listed[0]["token"] == created["token"]
    assert shares_mod.list_shares(tenant_id="other") == []

    assert shares_mod.delete_share(created["token"], tenant_id="acme") is True
    assert shares_mod.list_shares(tenant_id="acme") == []


def test_unlimited_ttl_and_password(shares_tmpdir: Path):
    created = shares_mod.create_share(
        resource_type="superset_dashboard",
        resource_id="7",
        ttl_hours=0,
        password="secret",
        tenant_id="default",
    )
    assert created["expires_at"] is None
    assert created["password_protected"] is True
    entry = shares_mod.get_share(created["token"])
    assert entry is not None
    assert shares_mod.verify_password(entry, "secret") is True
    assert shares_mod.verify_password(entry, "wrong") is False


def test_record_view_and_limit(shares_tmpdir: Path):
    created = shares_mod.create_share(
        resource_type="chat_answer",
        resource_id="art-1",
        ttl_hours=1,
        tenant_id="default",
        max_views=1,
        payload={"answer_md": "hello"},
    )
    token = created["token"]
    entry = shares_mod.record_view(token, ip="1.2.3.4", user_agent="pytest")
    assert entry is not None
    assert entry["view_count"] == 1
    views = shares_mod.list_views(token)
    assert views is not None
    assert views["view_count"] == 1
    assert len(views["views"]) == 1
    with pytest.raises(PermissionError, match="share_view_limit"):
        shares_mod.record_view(token)


def test_legacy_budget_share_readable(shares_tmpdir: Path):
    legacy_dir = shares_tmpdir / "budget-shares"
    legacy_dir.mkdir(parents=True)
    token = "legacyTokenValue123456789012"
    (legacy_dir / f"{token}.json").write_text(
        '{"token":"%s","resource_type":"budget_pack","resource_id":"2026:base::en",'
        '"tenant_id":"default","expires_at":null,"password_hash":null}' % token,
        encoding="utf-8",
    )
    entry = shares_mod.get_share(token)
    assert entry is not None
    assert entry["resource_type"] == "budget_pack"
