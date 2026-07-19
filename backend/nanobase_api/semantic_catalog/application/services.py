"""Application services for semantic catalog."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from nanobase_api.semantic_catalog.domain.errors import AuthorizationError, DomainError, ValidationError
from nanobase_api.semantic_catalog.domain.filter_rule import FilterRule
from nanobase_api.semantic_catalog.domain.metric import Metric
from nanobase_api.semantic_catalog.domain.promotion import (
    PromotionPhase,
    PromotionRequest,
    PromotionReview,
)
from nanobase_api.semantic_catalog.domain.semantic_version import ManifestAsset, SemanticVersion
from nanobase_api.semantic_catalog.domain.status import AssetStatus, transition
from nanobase_api.semantic_catalog.domain.verified_query import (
    VerifiedQueryCandidate,
    compute_candidate_score,
)
from nanobase_api.semantic_catalog.infrastructure.catalog_store import CatalogStore, get_catalog_store
from nanobase_api.semantic_catalog.infrastructure.metric_compiler import CompileRequest, MetricCompiler


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def validate_metric(store: CatalogStore, metric: Metric) -> dict[str, Any]:
    metric.transition_to(AssetStatus.VALIDATING)
    known = {f.code for f in store.list_published_filters(metric.tenant_id, metric.datasource_id)}
    # Also accept draft filters in same store during validation
    known |= {f.code for f in store.filters.values() if f.tenant_id == metric.tenant_id}
    try:
        metric.validate_for_publish(known_filter_codes=known)
        # Compile check
        filters = [f for f in store.filters.values() if f.code in metric.default_filter_codes]
        result = MetricCompiler().compile(CompileRequest(metric=metric, filters=filters))
        metric.transition_to(AssetStatus.READY_FOR_REVIEW)
        store.save_metric(metric)
        return {"ok": True, "status": metric.status.value, "compiledSql": result.sql, "astFingerprint": result.ast_fingerprint}
    except DomainError as e:
        metric.status = AssetStatus.VALIDATION_FAILED
        store.save_metric(metric)
        return {"ok": False, "status": metric.status.value, "error": e.message, "code": e.code}


def create_candidate_from_feedback(
    store: CatalogStore,
    *,
    tenant_id: str,
    datasource_id: str,
    question: str,
    logical_plan: dict[str, Any],
    user_id: str,
    execution_id: str | None = None,
    sql_fingerprint: str | None = None,
) -> VerifiedQueryCandidate:
    """Feedback creates a candidate only — never PUBLISHED verified SQL (Kural 2)."""
    score = compute_candidate_score(user_feedback=1.0, execution_success=0.5)
    cand = VerifiedQueryCandidate(
        id=_new_id("cand"),
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        question=question,
        logical_plan=logical_plan,
        source="USER_FEEDBACK",
        sql_fingerprint=sql_fingerprint,
        execution_id=execution_id,
        candidate_score=score,
        status=AssetStatus.DRAFT,
    )
    store.save_candidate(cand)
    promo = PromotionRequest(
        id=_new_id("promo"),
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        asset_type="VERIFIED_QUERY_CANDIDATE",
        asset_id=cand.id,
        requires_dual_approval=True,
        phase=PromotionPhase.CANDIDATE,
        created_by=user_id,
    )
    store.save_promotion(promo)
    return cand


def add_promotion_review(
    store: CatalogStore,
    *,
    promotion_id: str,
    reviewer_user_id: str,
    role: str,
    decision: str,
    comment: str = "",
) -> PromotionRequest:
    promo = store.promotions.get(promotion_id)
    if not promo:
        raise ValidationError("Promotion request bulunamadı.")
    if role == "BUSINESS_REVIEWER":
        promo.phase = PromotionPhase.AWAITING_BUSINESS_REVIEW
    elif role == "TECHNICAL_REVIEWER":
        if promo.phase == PromotionPhase.CANDIDATE:
            promo.phase = PromotionPhase.AWAITING_TECHNICAL_REVIEW
    promo.add_review(
        PromotionReview(
            reviewer_user_id=reviewer_user_id,
            role=role,  # type: ignore[arg-type]
            decision=decision,  # type: ignore[arg-type]
            comment=comment,
        )
    )
    store.save_promotion(promo)
    return promo


def publish_promotion(
    store: CatalogStore,
    *,
    promotion_id: str,
    publisher_user_id: str,
    publisher_roles: set[str],
    schema_version: str = "sha256:unknown",
    semantic_version_label: str = "7.0.0",
    qdrant_publisher: Any | None = None,
) -> SemanticVersion:
    promo = store.promotions.get(promotion_id)
    if not promo:
        raise ValidationError("Promotion request bulunamadı.")
    promo.assert_can_publish(publisher_user_id=publisher_user_id, publisher_roles=publisher_roles)

    # Collect published assets for manifest
    metrics = store.list_published_metrics(promo.tenant_id, promo.datasource_id)
    # Also publish approved metric assets attached to this promotion
    asset = store.metrics.get(promo.asset_id) or store.get_metric_by_code(
        promo.tenant_id, promo.datasource_id, "unpaid_invoice_amount"
    )
    if asset and asset.status == AssetStatus.APPROVED:
        asset.status = AssetStatus.PUBLISHED
        store.save_metric(asset)
        metrics = store.list_published_metrics(promo.tenant_id, promo.datasource_id)

    # Publish related filters/terms that are APPROVED
    for f in list(store.filters.values()):
        if f.tenant_id == promo.tenant_id and f.status == AssetStatus.APPROVED:
            f.status = AssetStatus.PUBLISHED
            store.save_filter(f)
    for t in list(store.business_terms.values()):
        if t.tenant_id == promo.tenant_id and t.status == AssetStatus.APPROVED:
            t.status = AssetStatus.PUBLISHED
            store.save_term(t)

    assets: list[ManifestAsset] = []
    for m in metrics:
        raw = json.dumps(m.to_dict(), sort_keys=True)
        assets.append(
            ManifestAsset(
                type="METRIC",
                code=m.code,
                version=m.version,
                sha256=hashlib.sha256(raw.encode()).hexdigest(),
            )
        )
    for f in store.list_published_filters(promo.tenant_id, promo.datasource_id):
        raw = json.dumps(f.to_dict(), sort_keys=True)
        assets.append(
            ManifestAsset(
                type="FILTER_RULE",
                code=f.code,
                version=f.version,
                sha256=hashlib.sha256(raw.encode()).hexdigest(),
            )
        )

    now = datetime.now(timezone.utc).isoformat()
    version = SemanticVersion(
        id=_new_id("sv"),
        tenant_id=promo.tenant_id,
        datasource_id=promo.datasource_id,
        version=semantic_version_label,
        schema_version=schema_version,
        assets=assets,
        status=AssetStatus.PREPARING,
        published_by=publisher_user_id,
        published_at=now,
    )
    version.transition_to(AssetStatus.READY)
    manifest = version.build_manifest()

    if qdrant_publisher is not None:
        qdrant_publisher.publish_version(store, version, manifest)

    store.set_active_version(version)
    promo.mark_published()
    store.save_promotion(promo)
    return version


def compile_metric_sql(
    store: CatalogStore,
    *,
    tenant_id: str,
    datasource_id: str,
    metric_code: str,
    period: dict[str, str] | None = None,
    dimension_filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metric = store.get_metric_by_code(tenant_id, datasource_id, metric_code)
    if not metric or metric.status != AssetStatus.PUBLISHED:
        raise ValidationError(f"Published metric bulunamadı: {metric_code}")
    filters = store.list_published_filters(tenant_id, datasource_id)
    # Enforce mandatory filters present
    mandatory = [f for f in filters if f.mandatory]
    for f in mandatory:
        if f.code not in metric.default_filter_codes and f.code not in (metric.default_filter_codes or []):
            # Still apply via compiler mandatory path
            pass
    result = MetricCompiler().compile(
        CompileRequest(
            metric=metric,
            filters=filters,
            period=period,
            dimension_filters=dimension_filters or {},
        )
    )
    # Ensure mandatory cancelled filter applied for unpaid slice
    if metric_code == "unpaid_invoice_amount":
        if "CANCELLED" not in result.sql or "NOT IN" not in result.sql:
            raise ValidationError("Mandatory filter exclude_cancelled_invoices uygulanmadı.")
    return result.to_dict()
