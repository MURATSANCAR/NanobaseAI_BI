"""All OData adversarial plans must REJECT."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.sap.contracts.datasource import ODataDatasourceConfig
from query_gateway.infrastructure.sap.contracts.query import ODataLogicalPlan
from query_gateway.infrastructure.sap.odata.policy_engine import validate_odata_plan
from query_gateway.infrastructure.sap.odata.query_builder import build_odata_request

CORPUS = Path(__file__).parent / "corpus" / "odata_malicious.jsonl"

CFG = ODataDatasourceConfig(
    datasource_id="sap_cds_odata",
    base_url="https://s4.example.internal/sap/opu/odata/sap/API_JOURNALENTRYITEM_SRV",
    allowed_services=["API_JOURNALENTRYITEM_SRV"],
    allowed_entity_sets=["JournalEntryItem", "ReceivableItem"],
    source_status="PUBLISHED",
)


def _load() -> list[dict]:
    if not CORPUS.is_file():
        from query_gateway.tests.security.generate_odata_corpus import main

        main()
    return [json.loads(line) for line in CORPUS.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.mark.parametrize("case", _load(), ids=lambda c: f"{c['category']}_{hash(json.dumps(c['plan'], sort_keys=True)) % 10**8}")
def test_odata_adversarial_reject(case: dict):
    plan = ODataLogicalPlan.from_dict(case["plan"])
    with pytest.raises(GatewayError):
        build_odata_request(plan, CFG)
