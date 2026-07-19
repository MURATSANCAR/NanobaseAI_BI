"""All malicious corpus SQLs must be REJECTED (never APPROVED)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from query_gateway.config.settings import reset_settings
from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.parser.sqlglot_parser import parse_sql
from query_gateway.infrastructure.policy.engine import (
    DatasourcePolicy,
    load_policy_bundle,
    validate_parsed,
)

CORPUS = Path(__file__).parent / "corpus" / "malicious.sql.jsonl"

POLICY = DatasourcePolicy(
    datasource_id="test",
    allowed_schemas={"reporting"},
    allowed_tables={"reporting.invoice", "reporting.customer"},
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
        from query_gateway.tests.security.generate_corpus import main

        main()
    rows = []
    for line in CORPUS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def test_malicious_corpus_all_rejected():
    rows = _load_corpus()
    assert len(rows) >= 500
    bundle = load_policy_bundle()
    approved: list[str] = []
    for row in rows:
        sql = row["sql"]
        try:
            parsed = parse_sql(sql, dialect="postgres")
            validate_parsed(parsed, POLICY, bundle)
            approved.append(sql)
        except GatewayError:
            continue
        except Exception:
            continue
    assert not approved, f"{len(approved)} malicious SQLs were APPROVED, e.g. {approved[:3]!r}"
