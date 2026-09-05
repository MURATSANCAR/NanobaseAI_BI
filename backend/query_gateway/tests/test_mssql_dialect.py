"""SQL Server dialect: datasource loader, dialect resolution, TOP rewrite, plan guard."""

from __future__ import annotations

import json

import pytest

from query_gateway.application.validate_query import _resolve_dialect, validate_query
from query_gateway.config.settings import Settings
from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.database.datasources import load_datasources
from query_gateway.infrastructure.database.mssql_executor import analyze_showplan
from query_gateway.infrastructure.policy.engine import load_policy_bundle


@pytest.fixture()
def mssql_settings(tmp_path):
    (tmp_path / "mssql-logo.password").write_text("s3cret", encoding="utf-8")
    (tmp_path / "mssql-ro.datasources.json").write_text(
        json.dumps(
            {
                "sources": {
                    "logo": {
                        "label": "ERP",
                        "host": "127.0.0.1",
                        "port": 14330,
                        "database": "LOGO_DB",
                        "user": "DOMAIN\\\\reader",
                        "password_file": str(tmp_path / "mssql-logo.password"),
                        "allowed_schemas": ["dbo"],
                        "allowed_tables": "*",
                        "table_patterns": ["LG_411_01_%", "LG_411_[A-Z]%"],
                        "size_profile": "large",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return Settings(secrets_root=tmp_path, auth_required=False, replay_required=False)


def test_loader_builds_mssql_datasource(mssql_settings):
    ds = load_datasources(mssql_settings)
    assert "logo" in ds
    d = ds["logo"]
    assert d["driver"] == "mssql" and d["dialect"] == "mssql"
    assert d["password"] == "s3cret"
    assert d["port"] == 14330 and d["database"] == "LOGO_DB"
    assert d["allowed_tables"] == "*"
    assert d["allowed_schemas"] == {"dbo"}
    assert d["table_patterns"] == ["LG_411_01_%", "LG_411_[A-Z]%"]


def test_resolve_dialect():
    assert _resolve_dialect({"driver": "mssql"}) == "mssql"
    assert _resolve_dialect({"driver": "postgresql", "dialect": "tsql"}) == "mssql"
    assert _resolve_dialect({"driver": "oracle"}) == "oracle"


def test_policy_bundle_mssql_functions():
    b = load_policy_bundle(dialect="mssql")
    assert "ISNULL" in b.functions.allowed and "DATEADD" in b.functions.allowed
    assert "XP_CMDSHELL" in b.functions.denied
    assert b.require_qualified is True


def test_validate_rewrites_limit_to_top(mssql_settings):
    out = validate_query(
        execution_id="e1",
        datasource_id="logo",
        sql="SELECT i.LOGICALREF, i.NETTOTAL FROM dbo.LG_411_01_INVOICE i WHERE i.DATE_ >= '2026-01-01' ORDER BY i.NETTOTAL DESC",
        max_rows=50,
        settings=mssql_settings,
    )
    assert out["status"] == "APPROVED"
    assert out["dialect"] == "mssql"
    assert "TOP 51" in out["normalizedSql"]
    assert "LIMIT" not in out["normalizedSql"].upper()
    assert "dbo.lg_411_01_invoice" in [t.lower() for t in out["tables"]]


def test_validate_keeps_explicit_top(mssql_settings):
    out = validate_query(
        execution_id="e2",
        datasource_id="logo",
        sql="SELECT TOP 5 c.CODE, c.DEFINITION_ FROM dbo.LG_411_CLCARD c",
        settings=mssql_settings,
    )
    assert "TOP 5" in out["normalizedSql"]


def test_validate_rejects_unqualified_and_dml(mssql_settings):
    with pytest.raises(GatewayError):
        validate_query(execution_id="e3", datasource_id="logo", sql="DELETE FROM dbo.LG_411_CLCARD", settings=mssql_settings)
    with pytest.raises(GatewayError):
        validate_query(execution_id="e4", datasource_id="logo", sql="SELECT CODE FROM LG_411_CLCARD", settings=mssql_settings)
    with pytest.raises(GatewayError):
        validate_query(execution_id="e5", datasource_id="logo", sql="SELECT c.CODE FROM other.LG_411_CLCARD c", settings=mssql_settings)


def test_showplan_guard():
    s = Settings()
    ok_rows = [
        {"EstimateRows": 120.0, "TotalSubtreeCost": 0.5},
        {"PhysicalOp": "Index Seek", "Argument": "OBJECT:([LOGO_DB].[dbo].[LG_411_01_INVOICE] AS [i]), SEEK:([i].[DATE_] >= ...)", "EstimateRows": 120.0},
    ]
    acc = analyze_showplan(ok_rows, size_profile="large", settings=s)
    assert acc["plan_rows"] == 120.0 and acc["filterless"] == []

    scan_rows = [
        {"EstimateRows": 1_700_000.0, "TotalSubtreeCost": 40.0},
        {"PhysicalOp": "Clustered Index Scan", "Argument": "OBJECT:([LOGO_DB].[dbo].[LG_411_01_STLINE] AS [s])", "EstimateRows": 1_700_000.0},
    ]
    with pytest.raises(GatewayError) as e:
        analyze_showplan(scan_rows, size_profile="large", settings=s)
    assert e.value.code == "QUERY_COST_EXCEEDED"
    assert "LG_411_01_STLINE" in str(e.value)

    with pytest.raises(GatewayError):
        analyze_showplan([], size_profile="medium", settings=s)
