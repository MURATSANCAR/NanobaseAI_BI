"""AWEL semantic retrieval — published catalog only."""

from __future__ import annotations

import json
from typing import Any


def format_semantic_context_block(payload: dict[str, Any]) -> str:
    """Render published metrics/filters/terms for prompt priority block."""
    lines: list[str] = []
    version = payload.get("semanticVersion")
    if version:
        lines.append(f"active_semantic_version: {version}")
    for m in payload.get("metrics") or []:
        lines.append(
            f"METRIC {m.get('code')}: {m.get('name')} | agg={m.get('aggregation')} | "
            f"source={m.get('sourceExpression')} | filters={m.get('defaultFilters')} | "
            f"time={m.get('time')} | nullPolicy={m.get('nullPolicy')}"
        )
    for f in payload.get("filterRules") or []:
        mand = "MANDATORY" if f.get("mandatory") else "optional"
        lines.append(f"FILTER {f.get('code')} ({mand}): {f.get('description')} expr={f.get('expression')}")
    for t in payload.get("businessTerms") or []:
        lines.append(
            f"TERM {t.get('normalizedName')}: {t.get('name')} synonyms={t.get('synonyms')} — {t.get('description')}"
        )
    for hit in payload.get("retrievalHits") or []:
        lines.append(f"HIT {hit.get('document_type')}/{hit.get('code')}: {hit.get('text', '')[:200]}")
    return "\n".join(lines)


async def retrieve_semantic_context(
    question: str,
    *,
    tenant_id: str,
    datasource_id: str,
) -> dict[str, Any]:
    """Load published semantic assets from in-process catalog store."""
    try:
        from nanobase_api.semantic_catalog.domain.status import AssetStatus
        from nanobase_api.semantic_catalog.infrastructure.catalog_store import get_catalog_store

        store = get_catalog_store()
        active = store.get_active_version(tenant_id, datasource_id)
        metrics = [
            m.to_dict()
            for m in store.list_published_metrics(tenant_id, datasource_id)
            if m.status == AssetStatus.PUBLISHED
        ]
        filters = [
            f.to_dict()
            for f in store.list_published_filters(tenant_id, datasource_id)
            if f.status == AssetStatus.PUBLISHED
        ]
        terms = [
            t.to_dict()
            for t in store.list_published_terms(tenant_id, datasource_id)
            if t.status == AssetStatus.PUBLISHED
        ]
        # Intent hint: unpaid invoice keywords
        q = (question or "").lower()
        resolved_metric = None
        if any(x in q for x in ("ödenmemiş", "odenmemis", "açık fatura", "unpaid", "kalan fatura")):
            if any(m.get("code") == "unpaid_invoice_amount" for m in metrics):
                resolved_metric = "unpaid_invoice_amount"
        payload = {
            "ok": True,
            "semanticVersion": active.version if active else None,
            "metrics": metrics,
            "filterRules": filters,
            "businessTerms": terms,
            "resolvedMetric": resolved_metric,
            "retrievalHits": [],
        }
        payload["hint_extra"] = format_semantic_context_block(payload)
        return payload
    except Exception as e:
        return {"ok": False, "error": str(e)[:300], "hint_extra": "", "metrics": []}


def try_compile_resolved_metric(
    *,
    tenant_id: str,
    datasource_id: str,
    metric_code: str,
    period: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    try:
        from nanobase_api.semantic_catalog.application.services import compile_metric_sql
        from nanobase_api.semantic_catalog.infrastructure.catalog_store import get_catalog_store

        return compile_metric_sql(
            get_catalog_store(),
            tenant_id=tenant_id,
            datasource_id=datasource_id,
            metric_code=metric_code,
            period=period,
        )
    except Exception:
        return None
