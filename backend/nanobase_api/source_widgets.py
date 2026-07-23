"""Seed live KPI widgets for the active BI datasource (Superset canvas side panel)."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

SECRETS = Path(os.environ.get("SECRETS_ROOT", "/data/nanobaseai/bi/secrets"))

# Optional demo packs keyed by datasource_id (exact match only — never cross-fallback).
# Additional / custom sources: SECRETS/source-widgets.json → {"sources": {"my_ds": [...]}}
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
            "id": "erp_personel",
            "type": "kpi",
            "title": "Personel",
            "sql": "SELECT COUNT(*)::bigint AS value FROM personeller",
            "value_key": "value",
            "format": "number",
        },
        {
            "id": "erp_stok",
            "type": "kpi",
            "title": "Stok satırları",
            "sql": "SELECT COUNT(*)::bigint AS value FROM stok_bakiyeleri",
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
            "id": "sig_araclar",
            "type": "kpi",
            "title": "Araçlar",
            "sql": "SELECT COUNT(*)::bigint AS value FROM araclar",
            "value_key": "value",
            "format": "number",
        },
        {
            "id": "sig_hasar_durum",
            "type": "donut",
            "title": "Hasar durumu dağılımı",
            "sql": (
                "SELECT durum AS label, COUNT(*)::int AS value "
                "FROM hasar_talepleri GROUP BY 1 ORDER BY 2 DESC LIMIT 6"
            ),
            "x_key": "label",
            "y_key": "value",
            "label_key": "label",
            "value_key": "value",
        },  # value_key used by pie/donut + KPI path
        {
            "id": "sig_poliçe_aylik",
            "type": "bar",
            "title": "Aylık yeni poliçe",
            "sql": (
                "SELECT DATE_TRUNC('month', baslangic_tarihi)::date::text AS label, "
                "COUNT(*)::int AS value "
                "FROM policeler GROUP BY 1 ORDER BY 1 DESC LIMIT 6"
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


_ALLOWED_TYPES = frozenset(
    {
        "kpi",
        "card",
        "metric",
        "gauge",
        "bar",
        "column",
        "stacked_bar",
        "stacked_column",
        "line",
        "area",
        "combo",
        "pie",
        "donut",
        "table",
        "matrix",
        "scatter",
        "funnel",
        "treemap",
        "waterfall",
    }
)

_TYPE_OVERRIDES_PATH = SECRETS / "source-widget-types.json"
_PINNED_WIDGETS_PATH = SECRETS / "source-widgets-pinned.json"


def _widget_specs_for(datasource_id: str) -> list[dict[str, Any]]:
    """Resolve widget SQL pack for a datasource — exact id only, no other-DS fallback."""
    sid = str(datasource_id or "").strip()
    if not sid:
        return []
    path = SECRETS / "source-widgets.json"
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            specs = (raw.get("sources") or {}).get(sid)
            if isinstance(specs, list):
                return [s for s in specs if isinstance(s, dict)]
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    packs = dict(_WIDGET_SPECS)
    try:
        from nanobase_api.infrastructure.datasource_registry import reporting_datasource_id

        rid = reporting_datasource_id()
        if rid != "bi_reporting" and "bi_reporting" in packs:
            packs[rid] = packs.pop("bi_reporting")
    except Exception:
        pass
    return list(packs.get(sid) or [])


def _load_pinned_widgets() -> dict[str, list[dict[str, Any]]]:
    if not _PINNED_WIDGETS_PATH.is_file():
        return {}
    try:
        raw = json.loads(_PINNED_WIDGETS_PATH.read_text(encoding="utf-8"))
        sources = raw.get("sources") if isinstance(raw, dict) else None
        if not isinstance(sources, dict):
            return {}
        out: dict[str, list[dict[str, Any]]] = {}
        for sid, specs in sources.items():
            if not isinstance(specs, list):
                continue
            clean = [s for s in specs if isinstance(s, dict) and str(s.get("id") or "").strip()]
            if clean:
                out[str(sid)] = clean
        return out
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def _save_pinned_widgets(data: dict[str, list[dict[str, Any]]]) -> None:
    SECRETS.mkdir(parents=True, exist_ok=True)
    payload = {"sources": data, "updated_at": datetime.now(timezone.utc).isoformat()}
    tmp = _PINNED_WIDGETS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_PINNED_WIDGETS_PATH)


def _pinned_specs_for(datasource_id: str) -> list[dict[str, Any]]:
    sid = str(datasource_id or "").strip()
    if not sid:
        return []
    return list(_load_pinned_widgets().get(sid) or [])


def pin_chat_widget(
    *,
    datasource_id: str,
    sql: str,
    title: str,
    widget_type: str = "table",
    x_key: str | None = None,
    y_key: str | None = None,
    value_key: str | None = None,
    label_key: str | None = None,
    widget_id: str | None = None,
) -> dict[str, Any]:
    """Persist a chat result as a live source-canvas widget (survives refresh)."""
    from nanobase_api.infrastructure.active_source import prefer_datasource_id

    sid = prefer_datasource_id(datasource_id)
    safe_sql = str(sql or "").strip()
    if not safe_sql:
        raise ValueError("sql_required")
    wtype = str(widget_type or "table").strip().lower() or "table"
    if wtype not in _ALLOWED_TYPES:
        wtype = "table"
    label = str(title or "").replace("\n", " ").strip()[:120] or "Chat sonucu"
    wid = str(widget_id or "").strip()
    if not wid:
        digest = hashlib.sha1(f"{sid}|{safe_sql}|{label}|{wtype}".encode("utf-8")).hexdigest()[:12]
        wid = f"chat_{digest}"

    spec: dict[str, Any] = {
        "id": wid,
        "type": wtype,
        "title": label,
        "sql": safe_sql,
        "source": "chat",
    }
    if x_key:
        spec["x_key"] = str(x_key)
    if y_key:
        spec["y_key"] = str(y_key)
    if value_key:
        spec["value_key"] = str(value_key)
    if label_key:
        spec["label_key"] = str(label_key)
    if wtype in {"kpi", "card", "metric"} and not spec.get("value_key"):
        spec["value_key"] = "value"
        spec["format"] = "number"

    pinned = _load_pinned_widgets()
    bucket = list(pinned.get(sid) or [])
    bucket = [s for s in bucket if str(s.get("id")) != wid]
    bucket.insert(0, spec)
    # Cap growth so chat pins don't unbounded-grow the canvas.
    pinned[sid] = bucket[:40]
    _save_pinned_widgets(pinned)
    return {"ok": True, "datasource_id": sid, "widget": spec}


def _load_type_overrides() -> dict[str, dict[str, str]]:
    if not _TYPE_OVERRIDES_PATH.is_file():
        return {}
    try:
        raw = json.loads(_TYPE_OVERRIDES_PATH.read_text(encoding="utf-8"))
        sources = raw.get("sources") if isinstance(raw, dict) else None
        if not isinstance(sources, dict):
            return {}
        out: dict[str, dict[str, str]] = {}
        for sid, mapping in sources.items():
            if not isinstance(mapping, dict):
                continue
            clean = {
                str(wid): str(wtype).strip().lower()
                for wid, wtype in mapping.items()
                if str(wtype).strip().lower() in _ALLOWED_TYPES
            }
            if clean:
                out[str(sid)] = clean
        return out
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def _save_type_overrides(data: dict[str, dict[str, str]]) -> None:
    SECRETS.mkdir(parents=True, exist_ok=True)
    payload = {"sources": data, "updated_at": datetime.now(timezone.utc).isoformat()}
    tmp = _TYPE_OVERRIDES_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_TYPE_OVERRIDES_PATH)


def save_widget_type(
    *,
    datasource_id: str,
    widget_id: str,
    widget_type: str,
) -> dict[str, Any]:
    """Persist visual type override for a source widget (survives refresh)."""
    from nanobase_api.infrastructure.active_source import prefer_datasource_id

    sid = prefer_datasource_id(datasource_id)
    wid = str(widget_id or "").strip()
    wtype = str(widget_type or "").strip().lower()
    if not wid:
        raise ValueError("bi_widget_id_required")
    if wtype not in _ALLOWED_TYPES:
        raise ValueError("bi_widget_type_invalid")
    # Ensure widget exists in pack or chat-pinned list for this source
    known = {str(s.get("id")) for s in _widget_specs_for(sid)}
    known |= {str(s.get("id")) for s in _pinned_specs_for(sid)}
    if known and wid not in known:
        raise ValueError("bi_widget_not_found")

    # Chat-pinned widgets store type on the spec itself.
    pinned = _load_pinned_widgets()
    pinned_bucket = list(pinned.get(sid) or [])
    pinned_hit = False
    for spec in pinned_bucket:
        if str(spec.get("id")) == wid:
            spec["type"] = wtype
            pinned_hit = True
            break
    if pinned_hit:
        pinned[sid] = pinned_bucket
        _save_pinned_widgets(pinned)
        return {"ok": True, "datasource_id": sid, "widget_id": wid, "type": wtype}

    overrides = _load_type_overrides()
    bucket = dict(overrides.get(sid) or {})
    bucket[wid] = wtype
    overrides[sid] = bucket
    _save_type_overrides(overrides)
    return {"ok": True, "datasource_id": sid, "widget_id": wid, "type": wtype}


async def build_source_widgets(
    *,
    datasource_id: str,
    qg_base: str,
    tenant_id: str = "default",
) -> dict[str, Any]:
    from nanobase_api.infrastructure.active_source import prefer_datasource_id

    sid = prefer_datasource_id(datasource_id)
    # Chat-pinned widgets first so newly added charts appear at the top of the canvas.
    specs = list(_pinned_specs_for(sid)) + list(_widget_specs_for(sid))
    seen_ids: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for spec in specs:
        wid = str(spec.get("id") or "").strip()
        if not wid or wid in seen_ids:
            continue
        seen_ids.add(wid)
        deduped.append(spec)
    specs = deduped
    type_overrides = _load_type_overrides().get(sid) or {}
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
                wid = str(spec["id"])
                wtype = type_overrides.get(wid) or str(spec["type"])
                w: dict[str, Any] = {
                    "id": wid,
                    "type": wtype,
                    "title": spec["title"],
                    "sql": sql,
                    "format": spec.get("format"),
                    "value_key": spec.get("value_key"),
                    "x_key": spec.get("x_key"),
                    "y_key": spec.get("y_key"),
                    "label_key": spec.get("label_key"),
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
