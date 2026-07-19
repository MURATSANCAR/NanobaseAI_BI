"""Seed live KPI widgets for the active BI datasource (Superset canvas side panel)."""

from __future__ import annotations

from typing import Any

import httpx

# Safe SELECT-only packs keyed by datasource_id. Titles are TR operator-facing.
_WIDGET_SPECS: dict[str, list[dict[str, Any]]] = {
    "bi_reporting": [
        {
            "id": "br_customers",
            "type": "kpi",
            "title": "Müşteriler",
            "sql": "SELECT COUNT(*)::bigint AS value FROM customers",
            "value_key": "value",
            "format": "number",
        },
        {
            "id": "br_orders",
            "type": "kpi",
            "title": "Siparişler",
            "sql": "SELECT COUNT(*)::bigint AS value FROM orders",
            "value_key": "value",
            "format": "number",
        },
        {
            "id": "br_invoice_gross",
            "type": "kpi",
            "title": "Fatura tutarı (brüt)",
            "sql": "SELECT COALESCE(SUM(gross_amount), 0) AS value FROM invoices",
            "value_key": "value",
            "format": "currency",
        },
        {
            "id": "br_products",
            "type": "kpi",
            "title": "Ürünler",
            "sql": "SELECT COUNT(*)::bigint AS value FROM products",
            "value_key": "value",
            "format": "number",
        },
        {
            "id": "br_top_products",
            "type": "bar",
            "title": "En çok satılan ürünler",
            "sql": (
                "SELECT p.product_name AS label, COUNT(*)::int AS value "
                "FROM order_items oi "
                "JOIN products p ON p.product_id = oi.product_id "
                "GROUP BY 1 ORDER BY 2 DESC LIMIT 6"
            ),
            "x_key": "label",
            "y_key": "value",
        },
    ],
    "erp": [
        {
            "id": "erp_musteriler",
            "type": "kpi",
            "title": "Müşteriler",
            "sql": "SELECT COUNT(*)::bigint AS value FROM musteriler",
            "value_key": "value",
            "format": "number",
        },
        {
            "id": "erp_faturalar",
            "type": "kpi",
            "title": "Faturalar",
            "sql": "SELECT COUNT(*)::bigint AS value FROM faturalar",
            "value_key": "value",
            "format": "number",
        },
        {
            "id": "erp_siparisler",
            "type": "kpi",
            "title": "Satış siparişleri",
            "sql": "SELECT COUNT(*)::bigint AS value FROM satis_siparisleri",
            "value_key": "value",
            "format": "number",
        },
        {
            "id": "erp_iller",
            "type": "bar",
            "title": "Fatura — illere göre",
            "sql": (
                "SELECT d.ad AS label, COUNT(*)::int AS value "
                "FROM faturalar f "
                "JOIN musteriler m ON m.id = f.musteri_id "
                "JOIN iller d ON d.id = m.il_id "
                "GROUP BY 1 ORDER BY 2 DESC LIMIT 6"
            ),
            "x_key": "label",
            "y_key": "value",
        },
        {
            "id": "erp_aylik",
            "type": "bar",
            "title": "Aylık fatura adedi",
            "sql": (
                "SELECT DATE_TRUNC('month', fatura_tarihi)::date::text AS label, "
                "COUNT(*)::int AS value "
                "FROM faturalar GROUP BY 1 ORDER BY 1 DESC LIMIT 6"
            ),
            "x_key": "label",
            "y_key": "value",
        },
    ],
    "sigorta": [
        {
            "id": "sig_musteriler",
            "type": "kpi",
            "title": "Müşteriler",
            "sql": "SELECT COUNT(*)::bigint AS value FROM musteriler",
            "value_key": "value",
            "format": "number",
        },
        {
            "id": "sig_policeler",
            "type": "kpi",
            "title": "Poliçeler",
            "sql": "SELECT COUNT(*)::bigint AS value FROM policeler",
            "value_key": "value",
            "format": "number",
        },
        {
            "id": "sig_hasar",
            "type": "kpi",
            "title": "Hasar talepleri",
            "sql": "SELECT COUNT(*)::bigint AS value FROM hasar_talepleri",
            "value_key": "value",
            "format": "number",
        },
        {
            "id": "sig_acenteler",
            "type": "kpi",
            "title": "Acenteler",
            "sql": "SELECT COUNT(*)::bigint AS value FROM acenteler",
            "value_key": "value",
            "format": "number",
        },
        {
            "id": "sig_hasar_durum",
            "type": "bar",
            "title": "Hasar durumu dağılımı",
            "sql": (
                "SELECT durum AS label, COUNT(*)::int AS value "
                "FROM hasar_talepleri GROUP BY 1 ORDER BY 2 DESC LIMIT 6"
            ),
            "x_key": "label",
            "y_key": "value",
        },
    ],
}


def _normalize_rows(payload: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        result = payload.get("result") or {}
        if isinstance(result, dict):
            rows = result.get("rows") or []
        else:
            rows = []
    out_rows: list[dict[str, Any]] = []
    for r in rows:
        if isinstance(r, dict):
            out_rows.append(r)
        elif isinstance(r, (list, tuple)) and payload.get("columns"):
            cols = payload["columns"]
            out_rows.append({str(cols[i]): r[i] for i in range(min(len(cols), len(r)))})
    cols = payload.get("columns")
    if not isinstance(cols, list) or not cols:
        cols = list(out_rows[0].keys()) if out_rows else []
    return [str(c) for c in cols], out_rows


async def build_source_widgets(
    *,
    datasource_id: str,
    qg_base: str,
    tenant_id: str = "default",
) -> dict[str, Any]:
    sid = (datasource_id or "bi_reporting").strip()
    specs = _WIDGET_SPECS.get(sid) or _WIDGET_SPECS.get("bi_reporting") or []
    widgets: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    async with httpx.AsyncClient(timeout=25.0) as client:
        for spec in specs:
            sql = str(spec["sql"])
            try:
                r = await client.post(
                    f"{qg_base.rstrip('/')}/api/v1/query/execute",
                    json={
                        "datasource_id": sid,
                        "sql": sql,
                        "tenant_id": tenant_id,
                    },
                )
                data = r.json() if r.content else {}
                if r.status_code >= 400 or not data.get("ok"):
                    errors.append(
                        {
                            "id": str(spec["id"]),
                            "message": str(
                                data.get("detail") or data.get("error") or f"HTTP {r.status_code}"
                            )[:240],
                        }
                    )
                    continue
                columns, rows = _normalize_rows(data)
                w: dict[str, Any] = {
                    "id": spec["id"],
                    "type": spec["type"],
                    "title": spec["title"],
                    "sql": sql,
                    "format": spec.get("format"),
                    "value_key": spec.get("value_key"),
                    "x_key": spec.get("x_key"),
                    "y_key": spec.get("y_key"),
                    "refreshed_at": None,
                    "data": {
                        "columns": columns,
                        "rows": rows,
                        "row_count": len(rows),
                    },
                }
                widgets.append(w)
            except Exception as e:
                errors.append({"id": str(spec["id"]), "message": str(e)[:240]})

    return {
        "datasource_id": sid,
        "widgets": widgets,
        "count": len(widgets),
        "errors": errors,
    }
