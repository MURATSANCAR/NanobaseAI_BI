"""FastAPI routes for /api/v1/semantic/* — governance catalog."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import JSONResponse

from nanobase_api.auth.principal import (
    ROLE_ADMIN,
    ROLE_BUSINESS_REVIEWER,
    ROLE_SEMANTIC_PUBLISHER,
    ROLE_TECHNICAL_REVIEWER,
    RequestPrincipal,
    get_current_principal,
    require_roles,
)
from nanobase_api.errors import ApiError
from nanobase_api.semantic_catalog import SEMANTIC_CONTRACT_VERSION
from nanobase_api.semantic_catalog.application.seed_unpaid_slice import seed_unpaid_invoice_slice
from nanobase_api.semantic_catalog.application.services import (
    add_promotion_review,
    compile_metric_sql,
    create_candidate_from_feedback,
    publish_promotion,
    validate_metric,
)
from nanobase_api.semantic_catalog.domain.errors import DomainError
from nanobase_api.semantic_catalog.domain.metric import Metric
from nanobase_api.semantic_catalog.domain.promotion import PromotionPhase, PromotionRequest
from nanobase_api.semantic_catalog.domain.status import AssetStatus
from nanobase_api.semantic_catalog.infrastructure.catalog_store import get_catalog_store
from nanobase_api.semantic_catalog.infrastructure.qdrant_publisher import SemanticQdrantPublisher
from nanobase_api.semantic_catalog.infrastructure.schema_impact_analyzer import apply_schema_impact

router = APIRouter(prefix="/api/v1/semantic", tags=["semantic-catalog"])

_publisher = SemanticQdrantPublisher(client=None, fail_on_error=False)


def _contract_headers(response: Response) -> None:
    response.headers["X-Nanobase-Semantic-Contract-Version"] = SEMANTIC_CONTRACT_VERSION


def _domain_error(e: DomainError) -> JSONResponse:
    status = 403 if e.code == "FORBIDDEN" else 400
    if e.code == "SEMANTIC_CONFLICT":
        status = 409
    return JSONResponse({"ok": False, "code": e.code, "error": e.message}, status_code=status)


@router.get("/status")
async def semantic_gov_status(response: Response) -> dict[str, Any]:
    _contract_headers(response)
    store = get_catalog_store()
    return {
        "ok": True,
        "enabled": True,
        "engine": "semantic_catalog",
        "contractVersion": SEMANTIC_CONTRACT_VERSION,
        "metrics": len(store.metrics),
        "businessTerms": len(store.business_terms),
        "filters": len(store.filters),
        "candidates": len(store.candidates),
        "promotions": len(store.promotions),
        "versions": len(store.versions),
    }


@router.post("/bootstrap/unpaid-invoice-slice")
async def bootstrap_slice(
    response: Response,
    body: dict[str, Any] | None = None,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> dict[str, Any]:
    """Seed vertical slice as DRAFT (or published for test tenant)."""
    _contract_headers(response)
    require_roles(principal, ROLE_ADMIN, ROLE_SEMANTIC_PUBLISHER, "DATA_ANALYST")
    body = body or {}
    store = get_catalog_store()
    ids = seed_unpaid_invoice_slice(
        store,
        tenant_id=body.get("tenantId") or principal.tenant_id,
        datasource_id=body.get("datasourceId") or "default",
        published=bool(body.get("published")),
    )
    return {"ok": True, **ids}


@router.get("/metrics")
async def list_metrics(
    response: Response,
    datasource_id: str = "default",
    principal: RequestPrincipal = Depends(get_current_principal),
) -> dict[str, Any]:
    _contract_headers(response)
    store = get_catalog_store()
    items = [
        m.to_dict()
        for m in store.metrics.values()
        if m.tenant_id == principal.tenant_id and m.datasource_id == datasource_id
    ]
    return {"metrics": items}


@router.get("/business-terms")
async def list_terms(
    response: Response,
    datasource_id: str = "default",
    principal: RequestPrincipal = Depends(get_current_principal),
) -> dict[str, Any]:
    _contract_headers(response)
    store = get_catalog_store()
    items = [
        t.to_dict()
        for t in store.business_terms.values()
        if t.tenant_id == principal.tenant_id and t.datasource_id == datasource_id
    ]
    return {"businessTerms": items}


@router.get("/filter-rules")
async def list_filters(
    response: Response,
    datasource_id: str = "default",
    principal: RequestPrincipal = Depends(get_current_principal),
) -> dict[str, Any]:
    _contract_headers(response)
    store = get_catalog_store()
    items = [
        f.to_dict()
        for f in store.filters.values()
        if f.tenant_id == principal.tenant_id and f.datasource_id == datasource_id
    ]
    return {"filterRules": items}


@router.post("/metrics/{metric_id}/validate")
async def validate_metric_endpoint(
    metric_id: str,
    response: Response,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> Any:
    _contract_headers(response)
    store = get_catalog_store()
    metric = store.metrics.get(metric_id)
    if not metric or metric.tenant_id != principal.tenant_id:
        raise ApiError("NOT_FOUND", "Metric bulunamadı.", status_code=404)
    return validate_metric(store, metric)


@router.post("/metrics/{metric_id}/submit-review")
async def submit_metric_review(
    metric_id: str,
    response: Response,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> dict[str, Any]:
    _contract_headers(response)
    store = get_catalog_store()
    metric = store.metrics.get(metric_id)
    if not metric or metric.tenant_id != principal.tenant_id:
        raise ApiError("NOT_FOUND", "Metric bulunamadı.", status_code=404)
    if metric.status not in (AssetStatus.READY_FOR_REVIEW, AssetStatus.VALIDATING):
        # Allow from READY_FOR_REVIEW
        if metric.status != AssetStatus.READY_FOR_REVIEW:
            raise ApiError("INVALID_STATE", f"Metric status: {metric.status.value}", status_code=400)
    promo = PromotionRequest(
        id=f"promo-{metric_id}",
        tenant_id=metric.tenant_id,
        datasource_id=metric.datasource_id,
        asset_type="METRIC",
        asset_id=metric.id,
        requires_dual_approval=True,
        phase=PromotionPhase.AWAITING_BUSINESS_REVIEW,
        created_by=principal.user_id,
        status=AssetStatus.READY_FOR_REVIEW,
    )
    store.promotions[promo.id] = promo
    return {"ok": True, "promotionRequest": promo.to_dict()}


@router.post("/verified-query-candidates")
async def create_candidate(
    body: dict[str, Any],
    response: Response,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> Any:
    _contract_headers(response)
    store = get_catalog_store()
    try:
        cand = create_candidate_from_feedback(
            store,
            tenant_id=principal.tenant_id,
            datasource_id=str(body.get("datasourceId") or "default"),
            question=str(body.get("question") or ""),
            logical_plan=dict(body.get("logicalPlan") or {"metric": "unpaid_invoice_amount"}),
            user_id=principal.user_id,
            execution_id=body.get("executionId"),
            sql_fingerprint=body.get("sqlFingerprint"),
        )
        return {"ok": True, "candidate": cand.to_dict()}
    except DomainError as e:
        return _domain_error(e)


@router.post("/verified-query-candidates/{candidate_id}/validate")
async def validate_candidate(
    candidate_id: str,
    response: Response,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> dict[str, Any]:
    _contract_headers(response)
    store = get_catalog_store()
    cand = store.candidates.get(candidate_id)
    if not cand or cand.tenant_id != principal.tenant_id:
        raise ApiError("NOT_FOUND", "Candidate bulunamadı.", status_code=404)
    cand.status = AssetStatus.READY_FOR_REVIEW
    # Move related promotion forward
    for p in store.promotions.values():
        if p.asset_id == candidate_id:
            p.phase = PromotionPhase.AWAITING_BUSINESS_REVIEW
            p.status = AssetStatus.READY_FOR_REVIEW
    return {"ok": True, "candidate": cand.to_dict()}


@router.post("/promotion-requests/{promotion_id}/reviews")
async def post_review(
    promotion_id: str,
    body: dict[str, Any],
    response: Response,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> Any:
    _contract_headers(response)
    decision = str(body.get("decision") or "").upper()
    role = str(body.get("role") or "").upper()
    if role == "BUSINESS_REVIEWER":
        require_roles(principal, ROLE_BUSINESS_REVIEWER, ROLE_ADMIN)
    elif role == "TECHNICAL_REVIEWER":
        require_roles(principal, ROLE_TECHNICAL_REVIEWER, ROLE_ADMIN)
    else:
        raise ApiError("BAD_REQUEST", "role BUSINESS_REVIEWER veya TECHNICAL_REVIEWER olmalı.", status_code=400)
    # ADMIN acting as reviewer still subject to same-user dual-approve rule in domain
    store = get_catalog_store()
    try:
        promo = add_promotion_review(
            store,
            promotion_id=promotion_id,
            reviewer_user_id=principal.user_id,
            role=role,
            decision=decision,
            comment=str(body.get("comment") or ""),
        )
        # If metric asset and both approved, mark APPROVED
        if promo.phase.value == "READY_TO_PUBLISH":
            metric = store.metrics.get(promo.asset_id)
            if metric:
                metric.status = AssetStatus.APPROVED
                store.save_metric(metric)
            for f in store.filters.values():
                if f.tenant_id == promo.tenant_id and f.status in (
                    AssetStatus.DRAFT,
                    AssetStatus.READY_FOR_REVIEW,
                    AssetStatus.VALIDATING,
                ):
                    # Approve related slice filters when metric approved
                    if f.code == "exclude_cancelled_invoices":
                        f.status = AssetStatus.APPROVED
                        store.save_filter(f)
            for t in store.business_terms.values():
                if t.tenant_id == promo.tenant_id and t.normalized_name == "odenmemis_fatura":
                    if t.status != AssetStatus.PUBLISHED:
                        t.status = AssetStatus.APPROVED
                        store.save_term(t)
        return {"ok": True, "promotionRequest": promo.to_dict()}
    except DomainError as e:
        return _domain_error(e)


@router.post("/promotion-requests/{promotion_id}/publish")
async def publish(
    promotion_id: str,
    response: Response,
    body: dict[str, Any] | None = None,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> Any:
    _contract_headers(response)
    require_roles(principal, ROLE_SEMANTIC_PUBLISHER, ROLE_ADMIN)
    body = body or {}
    store = get_catalog_store()
    try:
        version = publish_promotion(
            store,
            promotion_id=promotion_id,
            publisher_user_id=principal.user_id,
            publisher_roles=set(principal.roles),
            schema_version=str(body.get("schemaVersion") or "sha256:bootstrap"),
            semantic_version_label=str(body.get("semanticVersion") or "7.0.0"),
            qdrant_publisher=_publisher,
        )
        return {"ok": True, "semanticVersion": version.to_dict(), "manifest": version.build_manifest()}
    except DomainError as e:
        return _domain_error(e)


@router.get("/versions")
async def list_versions(
    response: Response,
    datasource_id: str = "default",
    principal: RequestPrincipal = Depends(get_current_principal),
) -> dict[str, Any]:
    _contract_headers(response)
    store = get_catalog_store()
    items = [
        v.to_dict()
        for v in store.versions.values()
        if v.tenant_id == principal.tenant_id and v.datasource_id == datasource_id
    ]
    active = store.get_active_version(principal.tenant_id, datasource_id)
    return {"versions": items, "active": active.to_dict() if active else None}


@router.post("/versions/{version_id}/rollback")
async def rollback_version(
    version_id: str,
    response: Response,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> dict[str, Any]:
    _contract_headers(response)
    require_roles(principal, ROLE_SEMANTIC_PUBLISHER, ROLE_ADMIN)
    store = get_catalog_store()
    version = store.versions.get(version_id)
    if not version or version.tenant_id != principal.tenant_id:
        raise ApiError("NOT_FOUND", "Version bulunamadı.", status_code=404)
    store.set_active_version(version)
    return {"ok": True, "active": version.to_dict()}


@router.post("/compile")
async def compile_endpoint(
    body: dict[str, Any],
    response: Response,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> Any:
    _contract_headers(response)
    store = get_catalog_store()
    try:
        result = compile_metric_sql(
            store,
            tenant_id=principal.tenant_id,
            datasource_id=str(body.get("datasourceId") or "default"),
            metric_code=str(body.get("metric") or "unpaid_invoice_amount"),
            period=body.get("period"),
            dimension_filters=body.get("dimensionFilters"),
        )
        return {"ok": True, **result}
    except DomainError as e:
        return _domain_error(e)


@router.post("/series")
async def series_endpoint(
    body: dict[str, Any],
    response: Response,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> Any:
    """Governed metric time series (forecasting plan Faz 1.3).

    {"metric": "total_revenue", "datasourceId": "bi_reporting", "grain": "month",
     "historyMonths": 36, "dimensionFilters": {"branch_city": "İstanbul"}}
    → rows [{"period": "2023-09-01", "value": 123.0}, ...] oldest→newest, SQL + logical plan.
    """
    _contract_headers(response)
    from nanobase_api.application.series import SeriesError, load_metric_series

    try:
        out = await load_metric_series(
            tenant_id=principal.tenant_id,
            datasource_id=str(body.get("datasourceId") or "bi_reporting"),
            metric_code=str(body.get("metric") or "total_revenue"),
            grain=str(body.get("grain") or "month"),
            history_periods=int(body.get("historyMonths") or body.get("historyPeriods") or 36),
            dimension_filters=body.get("dimensionFilters") or {},
        )
        return {"ok": True, **out}
    except SeriesError as e:
        return JSONResponse({"ok": False, "code": e.code, "error": e.message}, status_code=400)


@router.post("/schema-impact")
async def schema_impact(
    body: dict[str, Any],
    response: Response,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> dict[str, Any]:
    _contract_headers(response)
    require_roles(principal, ROLE_ADMIN, ROLE_TECHNICAL_REVIEWER, ROLE_SEMANTIC_PUBLISHER)
    store = get_catalog_store()
    report = apply_schema_impact(
        store,
        tenant_id=principal.tenant_id,
        datasource_id=str(body.get("datasourceId") or "default"),
        old_schema=dict(body.get("oldSchema") or {}),
        new_schema=dict(body.get("newSchema") or {}),
        publish_lock_held=bool(body.get("publishLockHeld")),
    )
    return {"ok": True, **report.to_dict()}


@router.get("/promotion-requests")
async def list_promotions(
    response: Response,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> dict[str, Any]:
    _contract_headers(response)
    store = get_catalog_store()
    items = [p.to_dict() for p in store.promotions.values() if p.tenant_id == principal.tenant_id]
    return {"promotionRequests": items}


@router.get("/retrieval/context")
async def retrieval_context(
    response: Response,
    question: str = "",
    datasource_id: str = "default",
    principal: RequestPrincipal = Depends(get_current_principal),
) -> dict[str, Any]:
    """Published semantic context for AWEL (priority over physical schema)."""
    _contract_headers(response)
    store = get_catalog_store()
    active = store.get_active_version(principal.tenant_id, datasource_id)
    version_label = active.version if active else None
    metrics = store.list_published_metrics(principal.tenant_id, datasource_id)
    filters = store.list_published_filters(principal.tenant_id, datasource_id)
    terms = store.list_published_terms(principal.tenant_id, datasource_id)
    # Exclude STALE
    metrics = [m for m in metrics if m.status == AssetStatus.PUBLISHED]
    hits = _publisher.retrieve(
        tenant_id=principal.tenant_id,
        datasource_id=datasource_id,
        semantic_version=version_label,
        query_text=question,
    )
    return {
        "semanticVersion": version_label,
        "metrics": [m.to_dict() for m in metrics],
        "filterRules": [f.to_dict() for f in filters if f.status == AssetStatus.PUBLISHED],
        "businessTerms": [t.to_dict() for t in terms if t.status == AssetStatus.PUBLISHED],
        "retrievalHits": hits,
        "priority": [
            "PUBLISHED_METRIC",
            "MANDATORY_FILTER",
            "VERIFIED_LOGICAL_PLAN",
            "APPROVED_JOIN",
            "PHYSICAL_SCHEMA",
        ],
    }
