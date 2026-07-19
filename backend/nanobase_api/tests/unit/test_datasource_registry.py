from __future__ import annotations

import json
from pathlib import Path

from nanobase_api.infrastructure import datasource_registry as reg


def test_merge_neon_map_is_id_agnostic(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(reg, "SECRETS", tmp_path)
    neon = {
        "sources": {
            "acme_finance": {
                "host": "ep.example.neon.tech",
                "port": 5432,
                "database": "neondb",
                "user": "bi_acme_ro",
                "password_file": str(tmp_path / "neon-acme.password"),
                "label": "Acme Finance",
            },
            "other_db": {
                "host": "ep2.example.neon.tech",
                "port": 5432,
                "database": "neondb",
                "user": "bi_other_ro",
                "password_file": str(tmp_path / "neon-other.password"),
            },
        }
    }
    (tmp_path / "neon-ro.datasources.json").write_text(json.dumps(neon), encoding="utf-8")
    by_id: dict = {}
    managed = reg.merge_gateway_ro_sources(by_id)
    assert managed == {"acme_finance", "other_db"}
    assert by_id["acme_finance"]["protected"] is True
    assert by_id["other_db"]["username"] == "bi_other_ro"
    assert "erp" not in by_id
    assert "sigorta" not in by_id


def test_reporting_only_when_password_exists(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(reg, "SECRETS", tmp_path)
    monkeypatch.setenv("REPORTING_DATASOURCE_ID", "local_analytics")
    assert reg.local_reporting_entry() is None
    (tmp_path / "reporting-ro.password").write_text("secret\n", encoding="utf-8")
    entry = reg.local_reporting_entry()
    assert entry is not None
    assert entry["id"] == "local_analytics"
    assert entry["protected"] is True


def test_resolve_pg_cfg_from_neon_map(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(reg, "SECRETS", tmp_path)
    (tmp_path / "neon-ro.datasources.json").write_text(
        json.dumps(
            {
                "sources": {
                    "warehouse_x": {
                        "host": "h",
                        "port": 5432,
                        "database": "db",
                        "user": "u",
                        "password_file": "/tmp/x",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    cfg = reg.resolve_pg_connect_cfg("warehouse_x")
    assert cfg is not None
    assert cfg["host"] == "h"
    assert reg.resolve_pg_connect_cfg("missing") is None
