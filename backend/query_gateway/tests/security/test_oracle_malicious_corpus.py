"""All Oracle malicious corpus SQLs must be REJECTED (never APPROVED)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from query_gateway.config.settings import reset_settings
from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.oracle.parser_policy import enforce_oracle_sql_policy
from query_gateway.infrastructure.parser.sqlglot_parser import parse_sql
from query_gateway.infrastructure.policy.engine import (
    DatasourcePolicy,
    load_policy_bundle,
    validate_parsed,
)

CORPUS = Path(__file__).parent / "corpus" / "oracle_malicious.sql.jsonl"

POLICY = DatasourcePolicy(
    datasource_id="oracle_reporting",
    allowed_schemas={"nanobase_reporting"},
    allowed_tables={"nanobase_reporting.v_invoice", "nanobase_reporting.v_customer"},
    column_modes={},
    policy_version="2026.07.1",
)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("QG_AUTH_REQUIRED", "false")
    monkeypatch.setenv("QG_REPLAY_REQUIRED", "false")
    monkeypatch.setenv("QG_REJECT_WILDCARD", "true")
    reset_settings()


def _load_corpus() -> list[dict]:
    if not CORPUS.is_file():
        from query_gateway.tests.security.generate_oracle_corpus import main

        main()
    rows = []
    for line in CORPUS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _is_rejected(sql: str, bundle) -> bool:
    try:
        enforce_oracle_sql_policy(sql)
    except GatewayError:
        return True
    try:
        parsed = parse_sql(sql, dialect="oracle")
        enforce_oracle_sql_policy(sql, parsed)
        validate_parsed(parsed, POLICY, bundle)
        return False
    except GatewayError:
        return True
    except Exception:
        # Parse failures count as reject (safe)
        return True


def test_oracle_malicious_corpus_all_rejected():
    rows = _load_corpus()
    assert len(rows) >= 600
    bundle = load_policy_bundle(dialect="oracle")
    approved: list[str] = []
    for row in rows:
        sql = row["sql"]
        if not _is_rejected(sql, bundle):
            approved.append(sql)
    assert not approved, (
        f"{len(approved)} Oracle malicious SQLs were APPROVED, e.g. {approved[:5]!r}"
    )
