"""All HANA malicious SQL must REJECT."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.sap.hana.parser_policy import enforce_hana_sql_policy

CORPUS = Path(__file__).parent / "corpus" / "hana_malicious.sql.jsonl"


def _load() -> list[dict]:
    if not CORPUS.is_file():
        from query_gateway.tests.security.generate_hana_corpus import main

        main()
    return [json.loads(line) for line in CORPUS.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.mark.parametrize("case", _load(), ids=lambda c: f"{c['category']}_{abs(hash(c['sql'])) % 10**8}")
def test_hana_adversarial_reject(case: dict):
    with pytest.raises(GatewayError):
        enforce_hana_sql_policy(case["sql"])
