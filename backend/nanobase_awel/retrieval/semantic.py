"""AWEL semantic retrieval — published catalog only."""

from __future__ import annotations

import json
import re
from typing import Any

_UNPAID_INVOICE_INTENT = re.compile(
    # No trailing \b on the Turkish stems: agglutinative suffixes ("faturaların",
    # "faturası") sit directly against the root with no boundary, so \b there
    # would silently stop matching almost every real inflected form. A leading
    # \b still blocks matching mid-word. Faithful to the original plain
    # substring check this replaced (`x in q for x in (...)`), just de-duped.
    r"(?i)\b(ödenmemiş|odenmemis|açık\s*fatura|acik\s*fatura|kalan\s*fatura)|\bunpaid\b"
)
_REVENUE_INTENT = re.compile(
    r"(?i)\b(ciro|satış\s*geliri|satis\s*geliri|toplam\s*satış|toplam\s*satis)|\brevenue\b"
)
# "adet"/"miktar" alone are too generic ("sipariş adetleri" = order COUNT, not
# quantity sold) — require "satılan"/"satış adedi" so this only fires for
# genuine quantity-of-goods-sold questions.
_QUANTITY_METRIC_INTENT = re.compile(
    r"(?i)satılan|satilan|satış\s*adedi|satis\s*adedi|\bquantity\b"
)

# HAVING/threshold filters ("cirosu 20000 TL üzerinde") are a real, supported
# question shape — just not one this resolver attempts. A wrong threshold
# extraction would confidently serve a wrong financial figure as "verified
# truth", which is a worse failure than falling through to the LLM plan path.
_THRESHOLD_HINT = re.compile(
    r"(?i)\büzerinde\b|\büstünde\b|\baltında\b|\bbüyük\b|\bküçük\b|\bfazla\b|[<>]"
)

# (dimension code, detector pattern, real column on v_sales_revenue_lines).
# Order matters: "category" is checked before "product" so the compound
# phrase "ürün kategorisine göre" (product category) resolves to ONE
# dimension (category), not two — see _detect_dimensions.
_DIMENSION_CANDIDATES: list[tuple[str, "re.Pattern[str]", str]] = [
    ("category", re.compile(r"(?i)\bkategori"), "product_category"),
    ("segment", re.compile(r"(?i)\bsegment"), "segment"),
    ("customer", re.compile(r"(?i)\bmüşteri|\bmusteri"), "customer_name"),
    ("product", re.compile(r"(?i)\bürün|\burun"), "product_name"),
    ("city", re.compile(r"(?i)\bşehir|\bsehir|\bülke|\bulke"), "customer_country"),
]
_RANK_N = re.compile(r"(?i)\bilk\s*(\d+)|\btop\s*(\d+)")
_RANK_SUPERLATIVE = re.compile(r"(?i)\ben\s*(yüksek|yuksek|çok|cok|fazla)")


def _detect_dimensions(q: str) -> list[str]:
    has_category = bool(re.search(r"(?i)\bkategori", q))
    found: list[str] = []
    for code, pattern, _col in _DIMENSION_CANDIDATES:
        if code == "product" and has_category:
            continue  # "ürün kategorisi" is the ONE compound dimension "category"
        if pattern.search(q) and code not in found:
            found.append(code)
    return found


def _dimension_column(code: str) -> str | None:
    for c, _pattern, col in _DIMENSION_CANDIDATES:
        if c == code:
            return col
    return None


def _detect_rank_limit(q: str) -> int | None:
    m = _RANK_N.search(q)
    if m:
        n = m.group(1) or m.group(2)
        try:
            return max(1, int(n))
        except (TypeError, ValueError):
            return None
    if _RANK_SUPERLATIVE.search(q):
        return 1
    return None


def resolve_revenue_intent(question: str) -> dict[str, Any] | None:
    """{'metricCode', 'groupBy', 'limit', 'orderDesc'} for a revenue/quantity
    aggregate this compiler can answer deterministically, or None to fall
    through to the LLM plan path.

    Deliberately conservative in what it WILL resolve: MetricCompiler only
    compiles GROUP BY over columns already flattened onto the metric's source
    view, ORDER BY the aggregate value, and LIMIT — no HAVING/threshold
    filtering (_THRESHOLD_HINT), no multi-dimension breakdowns (len(dims)>1).
    Both are real, supported question shapes; they just stay on the LLM path
    rather than risk a wrong resolution confidently serving a wrong answer.
    """
    q = question or ""
    if _THRESHOLD_HINT.search(q):
        return None
    dims = _detect_dimensions(q)
    if len(dims) > 1:
        return None
    group_by = [_dimension_column(dims[0])] if dims else []
    limit = _detect_rank_limit(q)
    if _QUANTITY_METRIC_INTENT.search(q):
        metric_code = "total_quantity_sold"
    elif _REVENUE_INTENT.search(q):
        metric_code = "total_revenue"
    else:
        return None
    return {"metricCode": metric_code, "groupBy": group_by, "limit": limit, "orderDesc": True}


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
        # Intent hint: keyword-matched, deliberately conservative — a wrong
        # resolution silently serves the wrong metric as "verified truth".
        q = question or ""
        resolved_metric = None
        resolved_group_by: list[str] = []
        resolved_limit: int | None = None
        resolved_order_desc = True
        if _UNPAID_INVOICE_INTENT.search(q):
            if any(m.get("code") == "unpaid_invoice_amount" for m in metrics):
                resolved_metric = "unpaid_invoice_amount"
        else:
            intent = resolve_revenue_intent(q)
            if intent and any(m.get("code") == intent["metricCode"] for m in metrics):
                resolved_metric = intent["metricCode"]
                resolved_group_by = list(intent["groupBy"])
                resolved_limit = intent["limit"]
                resolved_order_desc = intent["orderDesc"]
        payload = {
            "ok": True,
            "semanticVersion": active.version if active else None,
            "metrics": metrics,
            "filterRules": filters,
            "businessTerms": terms,
            "resolvedMetric": resolved_metric,
            "resolvedGroupBy": resolved_group_by,
            "resolvedLimit": resolved_limit,
            "resolvedOrderDesc": resolved_order_desc,
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
    group_by: list[str] | None = None,
    limit: int | None = None,
    order_desc: bool = True,
    time_grain: str | None = None,
    dimension_filters: dict[str, Any] | None = None,
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
            dimension_filters=dimension_filters,
            group_by=group_by,
            limit=limit,
            order_desc=order_desc,
            time_grain=time_grain,
        )
    except Exception:
        return None
