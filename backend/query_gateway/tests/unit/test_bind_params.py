"""Named bind parameter helpers."""

from __future__ import annotations

import pytest

from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.parser.bind_params import (
    assert_binds_present,
    extract_bind_names,
    probe_sql_for_parse,
    to_psycopg_sql,
    validate_parameters,
)


def test_extract_ignores_postgres_cast():
    sql = 'SELECT x::date FROM t WHERE d >= :period_start AND d < :period_end'
    names = extract_bind_names(sql)
    assert names == ["period_start", "period_end"]


def test_to_psycopg():
    sql = "SELECT 1 WHERE x = :id AND y::int > 0"
    assert "%(id)s" in to_psycopg_sql(sql)
    assert "::int" in to_psycopg_sql(sql)


def test_reject_non_scalar():
    with pytest.raises(GatewayError):
        validate_parameters({"x": {"nested": 1}})


def test_probe_and_assert():
    sql = "SELECT * FROM t WHERE a >= :period_start AND a < :period_end LIMIT :fetch_limit"
    params = {"period_start": "2026-06-01", "period_end": "2026-07-01", "fetch_limit": 10}
    probe = probe_sql_for_parse(sql, params)
    assert ":period_start" not in probe
    assert_binds_present(sql, params)
    with pytest.raises(GatewayError):
        assert_binds_present(sql, {"period_start": "2026-06-01"})
