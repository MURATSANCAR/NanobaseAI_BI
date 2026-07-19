"""Domain unit tests — status, metric, promotion, compiler-ready logical plan."""

from __future__ import annotations

import pytest

from nanobase_api.semantic_catalog.domain.business_term import BusinessTerm
from nanobase_api.semantic_catalog.domain.dependency import (
    DependencyEdge,
    DependencyGraph,
    DependencyKind,
    detect_synonym_conflicts,
)
from nanobase_api.semantic_catalog.domain.errors import (
    AuthorizationError,
    InvalidTransitionError,
    ValidationError,
)
from nanobase_api.semantic_catalog.domain.filter_rule import FilterExpression, FilterRule
from nanobase_api.semantic_catalog.domain.metric import (
    CurrencySemantics,
    Metric,
    SourceExpression,
    TimeSemantics,
)
from nanobase_api.semantic_catalog.domain.normalize import normalize_name
from nanobase_api.semantic_catalog.domain.promotion import (
    PromotionPhase,
    PromotionRequest,
    PromotionReview,
)
from nanobase_api.semantic_catalog.domain.semantic_version import VersionBump, bump_version, classify_change
from nanobase_api.semantic_catalog.domain.status import AssetStatus, is_retrieval_eligible, transition
from nanobase_api.semantic_catalog.domain.verified_query import (
    NormalizedIntent,
    VerifiedQuery,
    compute_candidate_score,
)


def test_draft_to_published_forbidden():
    with pytest.raises(InvalidTransitionError):
        transition(AssetStatus.DRAFT, AssetStatus.PUBLISHED)


def test_happy_path_status_chain():
    s = AssetStatus.DRAFT
    s = transition(s, AssetStatus.VALIDATING)
    s = transition(s, AssetStatus.READY_FOR_REVIEW)
    s = transition(s, AssetStatus.APPROVED)
    s = transition(s, AssetStatus.PUBLISHED)
    assert s == AssetStatus.PUBLISHED
    assert is_retrieval_eligible(s)
    assert not is_retrieval_eligible(AssetStatus.STALE)
    assert not is_retrieval_eligible(AssetStatus.DRAFT)


def test_normalize_turkish():
    assert normalize_name("Ödenmemiş Fatura") == "odenmemis_fatura"


def test_business_term_synonyms():
    t = BusinessTerm(
        id="1",
        tenant_id="t1",
        datasource_id="ds1",
        name="Ödenmemiş Fatura",
        description="...",
        synonyms=["açık fatura", "ödenmeyen fatura"],
    )
    assert t.normalized_name == "odenmemis_fatura"
    assert "acik_fatura" in t.normalized_synonyms


def test_metric_requires_time_and_currency_for_financial():
    m = Metric(
        id="1",
        tenant_id="t1",
        datasource_id="ds1",
        code="unpaid_invoice_amount",
        name="Ödenmemiş Fatura Tutarı",
        description="...",
        aggregation="SUM",
        source=SourceExpression("reporting.invoice", "remaining_amount"),
        default_filter_codes=["exclude_cancelled_invoices"],
        is_financial=True,
        multi_currency_datasource=True,
    )
    with pytest.raises(ValidationError):
        m.validate_for_publish(known_filter_codes={"exclude_cancelled_invoices"})

    m.time = TimeSemantics(time_field="reporting.invoice.invoice_date")
    m.currency = CurrencySemantics(
        amount_field="reporting.invoice.remaining_amount",
        conversion_policy="DOCUMENT_CURRENCY",
    )
    m.validate_for_publish(known_filter_codes={"exclude_cancelled_invoices"})
    plan = m.to_logical_plan()
    assert plan["metric"] == "unpaid_invoice_amount"
    assert "exclude_cancelled_invoices" in plan["filters"]


def test_sum_rejects_string_type():
    m = Metric(
        id="1",
        tenant_id="t1",
        datasource_id="ds1",
        code="x",
        name="x",
        description="",
        aggregation="SUM",
        source=SourceExpression("t", "name"),
        time=TimeSemantics("t.d"),
    )
    with pytest.raises(ValidationError):
        m.reject_sum_on_string_column("character varying")


def test_dual_approval_same_user_blocked():
    req = PromotionRequest(
        id="p1",
        tenant_id="t1",
        datasource_id="ds1",
        asset_type="METRIC",
        asset_id="m1",
        requires_dual_approval=True,
        phase=PromotionPhase.AWAITING_BUSINESS_REVIEW,
    )
    req.add_review(
        PromotionReview(reviewer_user_id="u1", role="BUSINESS_REVIEWER", decision="APPROVE")
    )
    with pytest.raises(AuthorizationError):
        req.add_review(
            PromotionReview(reviewer_user_id="u1", role="TECHNICAL_REVIEWER", decision="APPROVE")
        )


def test_dual_approval_two_users_ready():
    req = PromotionRequest(
        id="p1",
        tenant_id="t1",
        datasource_id="ds1",
        asset_type="METRIC",
        asset_id="m1",
        requires_dual_approval=True,
        phase=PromotionPhase.AWAITING_BUSINESS_REVIEW,
    )
    req.add_review(
        PromotionReview(reviewer_user_id="biz", role="BUSINESS_REVIEWER", decision="APPROVE")
    )
    req.add_review(
        PromotionReview(reviewer_user_id="tech", role="TECHNICAL_REVIEWER", decision="APPROVE")
    )
    assert req.phase == PromotionPhase.READY_TO_PUBLISH
    req.assert_can_publish(publisher_user_id="pub", publisher_roles={"SEMANTIC_PUBLISHER"})


def test_unauthorized_publish():
    req = PromotionRequest(
        id="p1",
        tenant_id="t1",
        datasource_id="ds1",
        asset_type="METRIC",
        asset_id="m1",
        phase=PromotionPhase.READY_TO_PUBLISH,
        requires_dual_approval=False,
    )
    with pytest.raises(AuthorizationError):
        req.assert_can_publish(publisher_user_id="u", publisher_roles={"DATA_ANALYST"})


def test_verified_query_requires_logical_plan():
    with pytest.raises(ValidationError):
        VerifiedQuery(
            id="1",
            tenant_id="t",
            datasource_id="d",
            verified_question_id="q",
            semantic_version="7.0.0",
            schema_version="sha",
            dialect="postgres",
            logical_plan={},
        )


def test_verified_scope_isolation():
    v = VerifiedQuery(
        id="1",
        tenant_id="t1",
        datasource_id="ds1",
        verified_question_id="q",
        semantic_version="7.0.0",
        schema_version="sha:a",
        dialect="postgres",
        logical_plan={"metric": "unpaid_invoice_amount"},
        status=AssetStatus.PUBLISHED,
    )
    assert not v.is_compatible(
        tenant_id="t2",
        datasource_id="ds1",
        semantic_version="7.0.0",
        schema_version="sha:a",
        dialect="postgres",
    )


def test_semver_bump():
    assert bump_version("7.0.0", VersionBump.MINOR) == "7.1.0"
    assert classify_change(mandatory_filter_changed=True) == VersionBump.MAJOR
    assert classify_change(synonym_added=True) == VersionBump.MINOR


def test_synonym_conflict():
    r = detect_synonym_conflicts({"m1": ["ciro", "gelir"], "m2": ["ciro"]})
    assert not r.ok


def test_dependency_cycle():
    g = DependencyGraph()
    g.add(DependencyEdge("METRIC", "a", DependencyKind.METRIC, "b"))
    g.add(DependencyEdge("METRIC", "b", DependencyKind.METRIC, "a"))
    assert g.has_cycle()


def test_candidate_score_not_auto_publish():
    s = compute_candidate_score(
        execution_success=1,
        result_equivalence=1,
        reviewer_score=1,
        repeated_usage=1,
        schema_stability=1,
        user_feedback=1,
    )
    assert s == 1.0


def test_filter_rule_mandatory():
    f = FilterRule(
        id="1",
        tenant_id="t",
        datasource_id="d",
        code="exclude_cancelled_invoices",
        description="iptal hariç",
        expression=FilterExpression(
            field="reporting.invoice.status",
            operator="NOT_IN",
            values=["CANCELLED", "VOID"],
        ),
        mandatory=True,
    )
    assert f.mandatory
    assert f.to_dict()["code"] == "exclude_cancelled_invoices"


def test_intent_fingerprint_stable():
    a = NormalizedIntent(metric="unpaid_invoice_amount", filters={"customer_city": "Ankara"})
    b = NormalizedIntent(metric="unpaid_invoice_amount", filters={"customer_city": "Ankara"})
    assert a.fingerprint() == b.fingerprint()
