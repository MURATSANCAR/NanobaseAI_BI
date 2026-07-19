"""SAP semantic FI pack tests."""

from __future__ import annotations

import pytest

from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.sap.semantic.currency import validate_currency_binding
from query_gateway.infrastructure.sap.semantic.fiscal_calendar import resolve_fiscal_period
from query_gateway.infrastructure.sap.semantic.reversal_policy import apply_mandatory_rules
from query_gateway.infrastructure.sap.semantic.sap_metric_compiler import compile_sap_metric
from query_gateway.infrastructure.sap.contracts.query import ODataLogicalPlan
from query_gateway.infrastructure.sap.security.authorization import enforce_company_scope


def test_currency_requires_pair():
    with pytest.raises(GatewayError):
        validate_currency_binding({"amountField": "Amt"})


def test_fiscal_ambiguous_non_calendar():
    with pytest.raises(GatewayError):
        resolve_fiscal_period(
            year=2026, period_hint="üçüncü çeyrek", fiscal_year_variant="V6"
        )


def test_fiscal_period_explicit():
    r = resolve_fiscal_period(year=2026, period_hint="P03", fiscal_year_variant="V3")
    assert r["fiscalPeriod"] == "003"


def test_mandatory_rules_injected():
    plan = ODataLogicalPlan(
        source_type="SAP_ODATA",
        service="S",
        entity_set="ReceivableItem",
        select=["CompanyCode", "AmountInCompanyCodeCurrency"],
        top=100,
    )
    out = apply_mandatory_rules(
        plan, ["exclude_reversed_documents", "exclude_unposted_documents"]
    )
    fields = {f.field for f in out.filters}
    assert "IsReversed" in fields
    assert "PostingStatus" in fields


def test_compile_open_receivable():
    metric = {
        "metric": "open_receivable_amount",
        "domain": "SAP_FI",
        "ledger": "0L",
        "currencyPolicy": "COMPANY_CODE_CURRENCY",
        "mandatoryRules": ["posted_only", "not_cleared", "exclude_reversed_documents"],
    }
    binding = {
        "sourceType": "SAP_ODATA",
        "service": "API_JOURNALENTRYITEM_SRV",
        "entitySet": "ReceivableItem",
        "amountField": "AmountInCompanyCodeCurrency",
        "currencyField": "CompanyCodeCurrency",
        "companyCodeField": "CompanyCode",
        "currencyPolicy": "COMPANY_CODE_CURRENCY",
    }
    compiled = compile_sap_metric(metric, binding, company_code="1000", top=100)
    assert compiled["plan"]["entitySet"] == "ReceivableItem"
    assert compiled["ledger"] == "0L"
    assert any(f["field"] == "CompanyCode" for f in compiled["plan"]["filters"])


def test_company_scope():
    plan = ODataLogicalPlan(
        source_type="SAP_ODATA",
        service="S",
        entity_set="ReceivableItem",
        select=["CompanyCode"],
        top=10,
    )
    # Multiple allowed codes require an explicit filter
    with pytest.raises(GatewayError):
        enforce_company_scope(plan, allowed_company_codes=["1000", "2000"])
    # with single allowed, auto-inject
    plan2 = ODataLogicalPlan(
        source_type="SAP_ODATA",
        service="S",
        entity_set="ReceivableItem",
        select=["CompanyCode"],
        top=10,
    )
    out = enforce_company_scope(plan2, allowed_company_codes=["1000"])
    assert out.filters[0].value == "1000"
