"""OData logical plan + safe builder unit tests."""

from __future__ import annotations

import pytest

from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.sap.contracts.datasource import ODataDatasourceConfig
from query_gateway.infrastructure.sap.contracts.query import ODataFilter, ODataLogicalPlan
from query_gateway.infrastructure.sap.odata.policy_engine import (
    legacy_to_logical_plan,
    validate_odata_plan,
)
from query_gateway.infrastructure.sap.odata.query_builder import build_odata_request


def _cfg(**kwargs) -> ODataDatasourceConfig:
    base = dict(
        datasource_id="sap_cds_odata",
        base_url="https://s4.example.internal/sap/opu/odata/sap/API_JOURNALENTRYITEM_SRV",
        allowed_services=["API_JOURNALENTRYITEM_SRV"],
        allowed_entity_sets=["JournalEntryItem", "ReceivableItem"],
        source_status="PUBLISHED",
    )
    base.update(kwargs)
    return ODataDatasourceConfig(**base)


def test_build_requires_select():
    plan = ODataLogicalPlan(
        source_type="SAP_ODATA",
        service="API_JOURNALENTRYITEM_SRV",
        entity_set="JournalEntryItem",
        select=[],
        top=10,
    )
    with pytest.raises(GatewayError):
        build_odata_request(plan, _cfg())


def test_build_happy_path():
    plan = ODataLogicalPlan(
        source_type="SAP_ODATA",
        service="API_JOURNALENTRYITEM_SRV",
        entity_set="JournalEntryItem",
        select=["CompanyCode", "AmountInCompanyCodeCurrency"],
        filters=[ODataFilter(field="CompanyCode", operator="EQ", value="1000")],
        top=100,
    )
    built = build_odata_request(plan, _cfg())
    assert built["method"] == "GET"
    assert "JournalEntryItem" in built["path"]
    assert "$select" in built["url"]
    assert "CompanyCode" in built["url"]
    assert "://" in built["url"]
    assert "s4.example.internal" in built["url"]


def test_reject_absolute_url_legacy():
    with pytest.raises(GatewayError):
        legacy_to_logical_plan("https://evil.example/JournalEntryItem?$select=A")


def test_reject_host_escape_entity():
    plan = ODataLogicalPlan(
        source_type="SAP_ODATA",
        service="API_JOURNALENTRYITEM_SRV",
        entity_set="http://evil",
        select=["CompanyCode"],
        top=10,
    )
    with pytest.raises(GatewayError):
        validate_odata_plan(plan, _cfg())


def test_reject_unlisted_entity():
    plan = ODataLogicalPlan(
        source_type="SAP_ODATA",
        service="API_JOURNALENTRYITEM_SRV",
        entity_set="EvilEntity",
        select=["CompanyCode"],
        top=10,
    )
    with pytest.raises(GatewayError):
        validate_odata_plan(plan, _cfg())


def test_reject_unpublished():
    plan = ODataLogicalPlan(
        source_type="SAP_ODATA",
        service="API_JOURNALENTRYITEM_SRV",
        entity_set="JournalEntryItem",
        select=["CompanyCode"],
        top=10,
    )
    with pytest.raises(GatewayError):
        validate_odata_plan(plan, _cfg(source_status="DISCOVERED"))


def test_string_escape_in_filter():
    plan = ODataLogicalPlan(
        source_type="SAP_ODATA",
        service="API_JOURNALENTRYITEM_SRV",
        entity_set="JournalEntryItem",
        select=["CompanyCode"],
        filters=[ODataFilter(field="CompanyCode", operator="EQ", value="O'Brien")],
        top=10,
    )
    built = build_odata_request(plan, _cfg())
    assert "O''Brien" in built["url"] or "O%27%27Brien" in built["url"] or "O''Brien" in str(
        built["query"]
    )


def test_reject_expand_depth():
    plan = ODataLogicalPlan(
        source_type="SAP_ODATA",
        service="API_JOURNALENTRYITEM_SRV",
        entity_set="JournalEntryItem",
        select=["CompanyCode"],
        expand=["to_Item/to_Detail"],
        top=10,
    )
    with pytest.raises(GatewayError):
        validate_odata_plan(plan, _cfg())
