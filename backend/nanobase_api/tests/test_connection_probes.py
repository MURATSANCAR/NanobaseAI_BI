#!/usr/bin/env python3
"""Unit tests for multi-dialect connection probes (no live DB)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

os.environ.setdefault("AUTH_MODE", "jwt")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("NANOBASE_ENV", "development")


def test_row_to_probe_ds_oracle_dsn():
    from nanobase_api.application.connection_probes import row_to_probe_ds

    row = {
        "id": "ora1",
        "driver": "oracle",
        "host": "(description=(address=(protocol=tcps)))",
        "port": 1522,
        "database": "adb1_high",
        "username": "NANOBASE_RO",
        "ssl": True,
    }
    ds = row_to_probe_ds(row, "secret", connection_url=row["host"])
    assert ds["driver"] == "oracle"
    assert ds["dsn"].startswith("(description=")
    assert ds["service_name"] == "adb1_high"
    assert ds["password"] == "secret"
    print("row_to_probe_ds_oracle_dsn ok")


def test_row_to_probe_ds_odata():
    from nanobase_api.application.connection_probes import row_to_probe_ds

    row = {
        "id": "od1",
        "driver": "odata",
        "host": "https://example.com/sap/opu/odata/sap/API",
        "port": 443,
        "database": "",
        "username": "svc",
        "ssl": True,
    }
    ds = row_to_probe_ds(row, "pw")
    assert ds["base_url"].startswith("https://")
    assert ds["user"] == "svc"
    print("row_to_probe_ds_odata ok")


def test_run_probe_unknown_driver():
    from nanobase_api.application.connection_probes import run_probe
    from nanobase_api.errors import ApiError

    try:
        run_probe({"driver": "mysql", "host": "x"})
        raise AssertionError("expected fail")
    except ApiError as e:
        assert e.code == "DATASOURCE_CONNECTION_FAILED"
        assert "desteklenmiyor" in e.message
    print("run_probe_unknown_driver ok")


def test_probe_oracle_mocked():
    from nanobase_api.application.connection_probes import probe_oracle

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.fetchone.side_effect = [(1,), ("Oracle Database 19c",)]

    registry = MagicMock()
    registry.acquire.return_value = ("ora1", mock_conn, MagicMock())

    with patch(
        "query_gateway.infrastructure.oracle.pool.get_oracle_pool_registry",
        return_value=registry,
    ):
        meta = probe_oracle(
            {
                "id": "ora1",
                "driver": "oracle",
                "user": "NANOBASE_RO",
                "password": "x",
                "host": "db.example.com",
                "port": 1521,
                "service_name": "ORCL",
                "database": "ORCL",
            }
        )
    assert meta["databaseType"] == "ORACLE"
    assert "Oracle" in meta["databaseVersion"]
    registry.release.assert_called_once()
    print("probe_oracle_mocked ok")


def test_probe_odata_mocked():
    from nanobase_api.application.connection_probes import probe_odata

    with patch(
        "query_gateway.infrastructure.sap.odata.client.fetch_metadata",
        return_value='<?xml Version="4.0"?><edmx/>',
    ):
        meta = probe_odata(
            {
                "id": "od1",
                "driver": "odata",
                "base_url": "https://example.com/odata",
                "host": "https://example.com/odata",
                "user": "u",
                "password": "p",
            }
        )
    assert meta["databaseType"] == "SAP_S4HANA_ODATA"
    print("probe_odata_mocked ok")


def test_probe_hana_mocked():
    from nanobase_api.application.connection_probes import probe_hana

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_cur.fetchone.side_effect = [(1,), ("2.0.00",)]

    with (
        patch("query_gateway.infrastructure.sap.hana.pool.acquire", return_value=mock_conn),
        patch("query_gateway.infrastructure.sap.hana.pool.release") as rel,
    ):
        meta = probe_hana(
            {
                "id": "h1",
                "driver": "hana",
                "host": "hana.example.com",
                "port": 30015,
                "user": "RO",
                "password": "x",
                "database": "PRD",
            }
        )
    assert meta["databaseType"] == "SAP_HANA"
    rel.assert_called_once()
    print("probe_hana_mocked ok")


def test_map_auth_error():
    from nanobase_api.application.connection_probes import map_probe_error

    err = map_probe_error(RuntimeError("ORA-01017: invalid username/password"), driver="oracle")
    assert "kimlik" in err.message.lower()
    print("map_auth_error ok")


if __name__ == "__main__":
    test_row_to_probe_ds_oracle_dsn()
    test_row_to_probe_ds_odata()
    test_run_probe_unknown_driver()
    test_probe_oracle_mocked()
    test_probe_odata_mocked()
    test_probe_hana_mocked()
    test_map_auth_error()
    print("all connection probe tests ok")
