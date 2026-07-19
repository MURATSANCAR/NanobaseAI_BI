"""Unit tests for Oracle profile, parser policy, synonym, result normalizer."""

from __future__ import annotations

from decimal import Decimal

import pytest

from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.oracle.parser_policy import enforce_oracle_sql_policy
from query_gateway.infrastructure.oracle.plan_guard import analyze_oracle_plan, _parse_plan_rows
from query_gateway.infrastructure.oracle.profile import (
    build_profile_from_datasource,
    validate_oracle_username,
)
from query_gateway.infrastructure.oracle.result_normalizer import (
    normalize_oracle_value,
    number_nanobase_type,
)
from query_gateway.infrastructure.oracle.synonym_resolver import resolve_synonym
from query_gateway.infrastructure.parser.sqlglot_parser import parse_sql, apply_limit
from query_gateway.config.settings import Settings


def test_reject_sys_user():
    with pytest.raises(GatewayError) as ei:
        validate_oracle_username("SYS")
    assert ei.value.code == "DATASOURCE_AUTHENTICATION_FAILED"


def test_reject_admin_user():
    with pytest.raises(GatewayError):
        validate_oracle_username("ADMIN")


def test_service_name_required():
    with pytest.raises(GatewayError):
        build_profile_from_datasource(
            {
                "id": "x",
                "user": "NANOBASE_QUERY_RO",
                "password": "p",
                "host": "h",
            }
        )


def test_cdb_root_rejected():
    with pytest.raises(GatewayError):
        build_profile_from_datasource(
            {
                "id": "x",
                "user": "NANOBASE_QUERY_RO",
                "password": "p",
                "host": "h",
                "service_name": "CDB$ROOT",
            }
        )


def test_valid_thin_profile():
    p = build_profile_from_datasource(
        {
            "id": "ora1",
            "user": "NANOBASE_QUERY_RO",
            "password": "secret",
            "host": "oracle-scan.internal",
            "port": 1521,
            "service_name": "FINPDB.internal",
            "allowedOwners": ["NANOBASE_REPORTING"],
            "connectionMode": "THIN",
        }
    )
    assert p.connection_mode == "THIN"
    assert p.connect_dsn() == "oracle-scan.internal:1521/FINPDB.internal"
    assert p.allowed_owners == ["NANOBASE_REPORTING"]


def test_reject_db_link():
    with pytest.raises(GatewayError) as ei:
        enforce_oracle_sql_policy(
            "SELECT * FROM NANOBASE_REPORTING.V_INVOICE@REMOTE_DB"
        )
    assert "link" in ei.value.message.lower() or ei.value.code == "STATEMENT_NOT_ALLOWED"


def test_reject_hint():
    with pytest.raises(GatewayError):
        enforce_oracle_sql_policy(
            "SELECT /*+ PARALLEL(32) */ INVOICE_ID FROM NANOBASE_REPORTING.V_INVOICE"
        )


def test_reject_plsql():
    with pytest.raises(GatewayError):
        enforce_oracle_sql_policy("BEGIN EXECUTE IMMEDIATE 'DROP TABLE X'; END;")


def test_reject_utl_http():
    with pytest.raises(GatewayError):
        enforce_oracle_sql_policy(
            "SELECT UTL_HTTP.REQUEST('https://example.com') FROM DUAL"
        )


def test_reject_for_update_via_parser():
    with pytest.raises(GatewayError):
        parse_sql(
            "SELECT INVOICE_ID FROM NANOBASE_REPORTING.V_INVOICE FOR UPDATE",
            dialect="oracle",
        )


def test_oracle_select_and_fetch_first():
    parsed = parse_sql(
        "SELECT INVOICE_ID, TOTAL_AMOUNT FROM NANOBASE_REPORTING.V_INVOICE "
        "ORDER BY INVOICE_DATE DESC",
        dialect="oracle",
    )
    limited = apply_limit(parsed.tree, max_limit=101, dialect="oracle")
    assert "FETCH" in limited.upper() or "LIMIT" in limited.upper()


def test_number_types():
    assert number_nanobase_type(10, 0) == "INTEGER"
    assert number_nanobase_type(18, 2) == "DECIMAL"
    assert number_nanobase_type(None, None) == "DECIMAL"


def test_decimal_fidelity():
    v = normalize_oracle_value(Decimal("12345.67"), type_name="NUMBER", scale=2)
    assert v == "12345.67"


def test_blob_rejected():
    v = normalize_oracle_value(b"abc", type_name="BLOB")
    assert isinstance(v, dict) and v.get("rejected")


def test_clob_truncated():
    big = "x" * 5000
    v = normalize_oracle_value(big, type_name="CLOB", max_clob=4096)
    assert isinstance(v, dict)
    assert v["truncated"] is True
    assert len(v["value"]) == 4096


def test_public_synonym_rejected():
    with pytest.raises(GatewayError):
        resolve_synonym(
            "PUBLIC",
            "INVOICES",
            allowed_owners={"NANOBASE_REPORTING"},
            fetch_synonym=lambda o, n: None,
            fetch_object_type=lambda o, n: None,
        )


def test_remote_synonym_rejected():
    with pytest.raises(GatewayError):
        resolve_synonym(
            "NANOBASE_REPORTING",
            "INVOICES",
            allowed_owners={"NANOBASE_REPORTING"},
            fetch_synonym=lambda o, n: {
                "table_owner": "NANOBASE_REPORTING",
                "table_name": "V_INVOICES",
                "db_link": "REMOTE",
            },
            fetch_object_type=lambda o, n: "VIEW",
        )


def test_synonym_resolves_view():
    res = resolve_synonym(
        "NANOBASE_REPORTING",
        "INVOICES",
        allowed_owners={"NANOBASE_REPORTING"},
        fetch_synonym=lambda o, n: {
            "table_owner": "NANOBASE_REPORTING",
            "table_name": "V_INVOICES",
            "db_link": None,
        },
        fetch_object_type=lambda o, n: "VIEW" if n == "V_INVOICES" else "SYNONYM",
    )
    assert res.resolved_object == "V_INVOICES"
    assert res.resolved_type == "VIEW"


def test_circular_synonym():
    def fetch(o, n):
        return {
            "table_owner": "NANOBASE_REPORTING",
            "table_name": "INVOICES" if n == "INVOICES2" else "INVOICES2",
            "db_link": None,
        }

    with pytest.raises(GatewayError):
        resolve_synonym(
            "NANOBASE_REPORTING",
            "INVOICES",
            allowed_owners={"NANOBASE_REPORTING"},
            fetch_synonym=fetch,
            fetch_object_type=lambda o, n: "SYNONYM",
        )


def test_plan_rejects_cartesian():
    with pytest.raises(GatewayError):
        _parse_plan_rows([(0, "MERGE JOIN CARTESIAN", "", "T", 1, 1)])
    with pytest.raises(GatewayError):
        _parse_plan_rows([(0, "MERGE JOIN", "CARTESIAN", None, 100, 1_000_000)])


def test_plan_analyze_row_limit():
    settings = Settings()
    summary = {"max_cost": 10, "max_rows": 99_999_999, "max_depth": 2, "filterless_full": []}
    with pytest.raises(GatewayError):
        analyze_oracle_plan(summary, size_profile="small", settings=settings)
