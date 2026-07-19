from __future__ import annotations

from hypothesis import given, settings, strategies as st

from query_gateway.config.settings import reset_settings
from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.parser.sqlglot_parser import parse_sql
from query_gateway.infrastructure.policy.engine import (
    DatasourcePolicy,
    load_policy_bundle,
    validate_parsed,
)

POLICY = DatasourcePolicy(
    datasource_id="t",
    allowed_schemas={"reporting"},
    allowed_tables={"reporting.invoice"},
)


@settings(max_examples=40, deadline=None)
@given(st.sampled_from(["invoice", "evil", "pg_user", "customers"]))
def test_unlisted_table_never_approved(name: str):
    reset_settings()
    sql = f"SELECT id FROM reporting.{name}" if name != "invoice" else "SELECT id FROM other.invoice"
    if name == "invoice":
        sql = "SELECT id FROM other.invoice"
    bundle = load_policy_bundle()
    try:
        parsed = parse_sql(sql)
        validate_parsed(parsed, POLICY, bundle)
        raise AssertionError("should reject")
    except GatewayError:
        pass


@settings(max_examples=20, deadline=None)
@given(st.sampled_from(["DELETE", "UPDATE", "INSERT INTO", "DROP TABLE", "TRUNCATE"]))
def test_dml_prefix_never_approved(verb: str):
    reset_settings()
    sql = f"{verb} reporting.invoice"
    if verb.startswith("INSERT"):
        sql = "INSERT INTO reporting.invoice VALUES (1)"
    try:
        parse_sql(sql)
        raise AssertionError("should reject")
    except GatewayError:
        pass
