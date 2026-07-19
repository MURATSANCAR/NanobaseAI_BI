from __future__ import annotations

import pytest

from query_gateway.config.settings import reset_settings
from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.parser.sqlglot_parser import fingerprint, parse_sql, apply_limit
from query_gateway.infrastructure.policy.engine import (
    DatasourcePolicy,
    load_policy_bundle,
    validate_parsed,
)
from query_gateway.infrastructure.result.masking import mask_value


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("QG_AUTH_REQUIRED", "false")
    monkeypatch.setenv("QG_REJECT_WILDCARD", "true")
    reset_settings()


POLICY = DatasourcePolicy(
    datasource_id="bi_reporting",
    allowed_schemas={"public", "analytics"},
    allowed_tables={"public.customers", "analytics.invoices", "customers"},
    column_modes={"public.customers.email": "MASKED:EMAIL"},
)


def test_simple_aggregate():
    p = parse_sql("SELECT COUNT(*) AS c FROM public.customers")
    assert "public.customers" in p.tables
    assert not p.has_wildcard
    w = validate_parsed(p, POLICY, load_policy_bundle())
    assert isinstance(w, list)


def test_reject_wildcard():
    p = parse_sql("SELECT * FROM public.customers")
    with pytest.raises(GatewayError) as ei:
        validate_parsed(p, POLICY, load_policy_bundle())
    assert ei.value.code == "WILDCARD_NOT_ALLOWED"


def test_reject_cte_delete():
    with pytest.raises(GatewayError):
        parse_sql("WITH x AS (DELETE FROM public.customers RETURNING *) SELECT * FROM x")


def test_reject_pg_sleep():
    p = parse_sql("SELECT pg_sleep(1)")
    with pytest.raises(GatewayError) as ei:
        validate_parsed(p, POLICY, load_policy_bundle())
    assert ei.value.code == "FUNCTION_NOT_ALLOWED"


def test_fingerprint_stable():
    p = parse_sql("SELECT COUNT(*) FROM public.customers")
    a = fingerprint(
        dialect="postgres",
        normalized_sql=p.normalized_sql,
        policy_version="1",
        datasource_id="x",
    )
    b = fingerprint(
        dialect="postgres",
        normalized_sql=p.normalized_sql,
        policy_version="1",
        datasource_id="x",
    )
    assert a == b and a.startswith("sha256:")


def test_limit_rewrite():
    p = parse_sql("SELECT id FROM public.customers ORDER BY id")
    sql = apply_limit(p.tree, max_limit=1001, dialect="postgres")
    assert "LIMIT 1001" in sql.upper()


def test_mask_email_phone_iban():
    assert "@" in mask_value("murat@example.com", "EMAIL")
    assert "***" in mask_value("05321234567", "PHONE")
    assert "TR12" in mask_value("TR120006200000000012345678", "IBAN")
