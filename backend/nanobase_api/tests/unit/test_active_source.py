from __future__ import annotations

import json
from pathlib import Path

from nanobase_api.infrastructure import active_source as mod


def test_resolve_prefers_memory_over_env(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(mod, "SECRETS", tmp_path)
    monkeypatch.setattr(mod, "ACTIVE_FILE", tmp_path / "active_datasource")
    monkeypatch.setattr(mod, "CONNECTION_LOCAL", tmp_path / "connection.local.json")
    monkeypatch.setenv("NANOBASE_ACTIVE_DB", "bi_reporting")
    mod.write_persisted_active("erp")
    assert (
        mod.resolve_active_id(memory_id="sigorta", known_ids={"erp", "sigorta", "bi_reporting"})
        == "sigorta"
    )


def test_resolve_uses_persisted_when_memory_empty(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(mod, "SECRETS", tmp_path)
    monkeypatch.setattr(mod, "ACTIVE_FILE", tmp_path / "active_datasource")
    monkeypatch.setattr(mod, "CONNECTION_LOCAL", tmp_path / "connection.local.json")
    monkeypatch.delenv("NANOBASE_ACTIVE_DB", raising=False)
    mod.write_persisted_active("erp")
    assert mod.resolve_active_id(memory_id=None, known_ids={"erp", "sigorta"}) == "erp"
    assert (tmp_path / "active_datasource").read_text(encoding="utf-8").strip() == "erp"


def test_write_updates_connection_local(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(mod, "SECRETS", tmp_path)
    monkeypatch.setattr(mod, "ACTIVE_FILE", tmp_path / "active_datasource")
    conn = tmp_path / "connection.local.json"
    conn.write_text(json.dumps({"active_id": "bi_reporting", "sources": {}}), encoding="utf-8")
    monkeypatch.setattr(mod, "CONNECTION_LOCAL", conn)
    bridge = tmp_path / "bridge-connection.local.json"
    bridge.write_text(json.dumps({"active_id": "erp", "sources": {"erp": {}}}), encoding="utf-8")
    monkeypatch.setattr(mod, "_BRIDGE_SOURCES_CANDIDATES", [conn, bridge])
    mod.write_persisted_active("sigorta")
    raw = json.loads(conn.read_text(encoding="utf-8"))
    assert raw["active_id"] == "sigorta"
    assert json.loads(bridge.read_text(encoding="utf-8"))["active_id"] == "sigorta"


def test_env_does_not_override_persisted(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(mod, "SECRETS", tmp_path)
    monkeypatch.setattr(mod, "ACTIVE_FILE", tmp_path / "active_datasource")
    monkeypatch.setattr(mod, "CONNECTION_LOCAL", tmp_path / "connection.local.json")
    monkeypatch.setenv("NANOBASE_ACTIVE_DB", "bi_reporting")
    mod.write_persisted_active("erp")
    assert mod.resolve_active_id(memory_id=None, known_ids={"erp", "bi_reporting"}) == "erp"
