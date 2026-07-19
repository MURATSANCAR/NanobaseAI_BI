"""Compiler + promotion + schema impact unit tests."""

from __future__ import annotations

import pytest

from nanobase_api.semantic_catalog.application.seed_unpaid_slice import seed_unpaid_invoice_slice
from nanobase_api.semantic_catalog.application.services import (
    add_promotion_review,
    compile_metric_sql,
    create_candidate_from_feedback,
    publish_promotion,
    validate_metric,
)
from nanobase_api.semantic_catalog.domain.errors import AuthorizationError, ValidationError
from nanobase_api.semantic_catalog.domain.promotion import PromotionPhase, PromotionRequest
from nanobase_api.semantic_catalog.domain.status import AssetStatus
from nanobase_api.semantic_catalog.infrastructure.catalog_store import reset_catalog_store
from nanobase_api.semantic_catalog.infrastructure.metric_compiler import MetricCompiler
from nanobase_api.semantic_catalog.infrastructure.qdrant_publisher import SemanticQdrantPublisher
from nanobase_api.semantic_catalog.infrastructure.schema_impact_analyzer import apply_schema_impact


@pytest.fixture()
def store():
    return reset_catalog_store()


def test_compiler_deterministic_unpaid(store):
    ids = seed_unpaid_invoice_slice(store, published=True)
    metric = store.metrics[ids["metric_id"]]
    filt = store.filters[ids["filter_id"]]
    c = MetricCompiler()
    from nanobase_api.semantic_catalog.infrastructure.metric_compiler import CompileRequest

    r1 = c.compile(CompileRequest(metric=metric, filters=[filt], period={"from": "2026-01-01", "to": "2027-01-01"}))
    r2 = c.compile(CompileRequest(metric=metric, filters=[filt], period={"from": "2026-01-01", "to": "2027-01-01"}))
    assert r1.ast_fingerprint == r2.ast_fingerprint
    assert "NOT IN" in r1.sql
    assert "CANCELLED" in r1.sql
    assert "SUM" in r1.sql
    assert "COALESCE" in r1.sql


def test_compiler_1000_ast_stable(store):
    ids = seed_unpaid_invoice_slice(store, published=True)
    metric = store.metrics[ids["metric_id"]]
    filt = store.filters[ids["filter_id"]]
    c = MetricCompiler()
    from nanobase_api.semantic_catalog.infrastructure.metric_compiler import CompileRequest

    req = CompileRequest(metric=metric, filters=[filt])
    base = c.compile(req).ast_fingerprint
    for _ in range(1000):
        assert c.compile(req).ast_fingerprint == base


def test_feedback_creates_candidate_not_published(store):
    cand = create_candidate_from_feedback(
        store,
        tenant_id="default",
        datasource_id="default",
        question="ödenmemiş fatura?",
        logical_plan={"metric": "unpaid_invoice_amount"},
        user_id="u1",
    )
    assert cand.status == AssetStatus.DRAFT
    assert cand.source == "USER_FEEDBACK"
    assert all(v.status != AssetStatus.PUBLISHED for v in store.verified_queries.values())


def test_dual_review_publish_flow(store):
    ids = seed_unpaid_invoice_slice(store, published=False)
    metric = store.metrics[ids["metric_id"]]
    # Move filters/terms toward approved via validation path
    result = validate_metric(store, metric)
    assert result["ok"] is True
    promo = PromotionRequest(
        id="promo-test",
        tenant_id="default",
        datasource_id="default",
        asset_type="METRIC",
        asset_id=metric.id,
        requires_dual_approval=True,
        phase=PromotionPhase.AWAITING_BUSINESS_REVIEW,
    )
    store.promotions[promo.id] = promo
    add_promotion_review(
        store, promotion_id=promo.id, reviewer_user_id="biz", role="BUSINESS_REVIEWER", decision="APPROVE"
    )
    with pytest.raises(AuthorizationError):
        add_promotion_review(
            store, promotion_id=promo.id, reviewer_user_id="biz", role="TECHNICAL_REVIEWER", decision="APPROVE"
        )
    add_promotion_review(
        store, promotion_id=promo.id, reviewer_user_id="tech", role="TECHNICAL_REVIEWER", decision="APPROVE"
    )
    metric.status = AssetStatus.APPROVED
    store.save_metric(metric)
    store.filters[ids["filter_id"]].status = AssetStatus.APPROVED
    store.business_terms[ids["term_id"]].status = AssetStatus.APPROVED
    pub = SemanticQdrantPublisher(fail_on_error=False)
    version = publish_promotion(
        store,
        promotion_id=promo.id,
        publisher_user_id="pub",
        publisher_roles={"SEMANTIC_PUBLISHER"},
        semantic_version_label="7.0.0",
        qdrant_publisher=pub,
    )
    assert version.is_active
    assert version.manifest_sha256
    compiled = compile_metric_sql(
        store, tenant_id="default", datasource_id="default", metric_code="unpaid_invoice_amount"
    )
    assert "NOT IN" in compiled["sql"]


def test_unauthorized_publish(store):
    promo = PromotionRequest(
        id="p1",
        tenant_id="default",
        datasource_id="default",
        asset_type="METRIC",
        asset_id="x",
        phase=PromotionPhase.READY_TO_PUBLISH,
        requires_dual_approval=False,
    )
    store.promotions[promo.id] = promo
    with pytest.raises(AuthorizationError):
        publish_promotion(
            store,
            promotion_id=promo.id,
            publisher_user_id="u",
            publisher_roles={"DATA_ANALYST"},
        )


def test_schema_impact_marks_stale(store):
    ids = seed_unpaid_invoice_slice(store, published=True)
    old = {
        "reporting.invoice": {
            "columns": {
                "remaining_amount": {"type": "numeric", "nullable": True},
                "status": {"type": "text", "nullable": False},
                "invoice_date": {"type": "date", "nullable": False},
            }
        }
    }
    new = {
        "reporting.invoice": {
            "columns": {
                "status": {"type": "text", "nullable": False},
                "invoice_date": {"type": "date", "nullable": False},
            }
        }
    }
    report = apply_schema_impact(
        store,
        tenant_id="default",
        datasource_id="default",
        old_schema=old,
        new_schema=new,
    )
    assert any("unpaid_invoice_amount" in a for a in report.stale_assets)
    assert store.metrics[ids["metric_id"]].status == AssetStatus.STALE
    with pytest.raises(ValidationError):
        compile_metric_sql(
            store, tenant_id="default", datasource_id="default", metric_code="unpaid_invoice_amount"
        )


def test_comment_change_no_stale(store):
    seed_unpaid_invoice_slice(store, published=True)
    old = {"reporting.invoice": {"columns": {"remaining_amount": {"type": "numeric", "comment": "a"}}}}
    new = {"reporting.invoice": {"columns": {"remaining_amount": {"type": "numeric", "comment": "b"}}}}
    report = apply_schema_impact(
        store, tenant_id="default", datasource_id="default", old_schema=old, new_schema=new
    )
    assert report.stale_assets == []
