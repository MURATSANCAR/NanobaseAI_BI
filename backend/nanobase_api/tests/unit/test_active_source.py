from __future__ import annotations

import json
from pathlib import Path

from nanobase_api.infrastructure import active_source as mod


def test_resolve_prefers_memory_over_env(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(mod, "SECRETS", tmp_path)
    monkeypatch.setattr(mod, "ACTIVE_FILE", tmp_path / "active_datasource")
    monkeypatch.setattr(mod, "_BRIDGE_SOURCES_CANDIDATES", [tmp_path / "connection.local.json"])
    monkeypatch.setenv("NANOBASE_ACTIVE_DB", "fallback_a")
    mod.write_persisted_active("ds_a")
    assert (
        mod.resolve_active_id(memory_id="ds_b", known_ids={"ds_a", "ds_b", "fallback_a"})
        == "ds_b"
    )


def test_resolve_uses_persisted_when_memory_empty(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(mod, "SECRETS", tmp_path)
    monkeypatch.setattr(mod, "ACTIVE_FILE", tmp_path / "active_datasource")
    monkeypatch.setattr(mod, "_BRIDGE_SOURCES_CANDIDATES", [tmp_path / "connection.local.json"])
    monkeypatch.delenv("NANOBASE_ACTIVE_DB", raising=False)
    mod.write_persisted_active("ds_a")
    assert mod.resolve_active_id(memory_id=None, known_ids={"ds_a", "ds_b"}) == "ds_a"
    assert (tmp_path / "active_datasource").read_text(encoding="utf-8").strip() == "ds_a"


def test_write_updates_connection_local(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(mod, "SECRETS", tmp_path)
    monkeypatch.setattr(mod, "ACTIVE_FILE", tmp_path / "active_datasource")
    conn = tmp_path / "connection.local.json"
    conn.write_text(json.dumps({"active_id": "old", "sources": {}}), encoding="utf-8")
    bridge = tmp_path / "bridge-connection.local.json"
    bridge.write_text(json.dumps({"active_id": "ds_a", "sources": {"ds_a": {}}}), encoding="utf-8")
    monkeypatch.setattr(mod, "_BRIDGE_SOURCES_CANDIDATES", [conn, bridge])
    mod.write_persisted_active("ds_b")
    assert json.loads(conn.read_text(encoding="utf-8"))["active_id"] == "ds_b"
    assert json.loads(bridge.read_text(encoding="utf-8"))["active_id"] == "ds_b"


def test_env_does_not_override_persisted(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(mod, "SECRETS", tmp_path)
    monkeypatch.setattr(mod, "ACTIVE_FILE", tmp_path / "active_datasource")
    monkeypatch.setattr(mod, "_BRIDGE_SOURCES_CANDIDATES", [tmp_path / "connection.local.json"])
    monkeypatch.setenv("NANOBASE_ACTIVE_DB", "fallback_a")
    mod.write_persisted_active("ds_a")
    assert mod.resolve_active_id(memory_id=None, known_ids={"ds_a", "fallback_a"}) == "ds_a"


def test_fallback_is_first_known_not_hardcoded_name(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(mod, "SECRETS", tmp_path)
    monkeypatch.setattr(mod, "ACTIVE_FILE", tmp_path / "active_datasource")
    monkeypatch.setattr(mod, "_BRIDGE_SOURCES_CANDIDATES", [])
    monkeypatch.delenv("NANOBASE_ACTIVE_DB", raising=False)
    assert mod.resolve_active_id(memory_id=None, known_ids={"zeta", "alpha"}) == "alpha"
