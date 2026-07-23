"""BI analytics (Apache Superset) routes — FE contract for canvas embed."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from nanobase_api.config import get_settings
from nanobase_api.infrastructure.superset_client import SupersetError, get_superset_client
from nanobase_api.source_widgets import build_source_widgets, pin_chat_widget, save_widget_type

router = APIRouter(tags=["analytics"])

QG_BASE = os.environ.get("QUERY_GATEWAY_BASE", "http://127.0.0.1:8792").rstrip("/")


def _disabled_status() -> dict[str, Any]:
    s = get_settings()
    return {
        "enabled": False,
        "url": s.superset_public_url or None,
        "health": {"ok": False, "message": "analytics_disabled", "dashboard_count": 0},
    }


def _err(exc: SupersetError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status,
        content={"error": exc.code, "message": exc.message, "detail": exc.message},
    )


def _resolve_source_id(request: Request, body_sid: str | None = None) -> str:
    from nanobase_api.infrastructure.active_source import prefer_datasource_id

    q_sid = (request.query_params.get("datasource_id") or "").strip()
    memory = ""
    if not q_sid and not body_sid:
        try:
            from bridge import app as bridge_mod  # type: ignore

            memory = str(bridge_mod.ACTIVE_DB.get("id") or "")
        except Exception:
            memory = ""
    return prefer_datasource_id(body_sid, q_sid, memory_id=memory)


@router.get("/api/v1/bi/analytics/source-widgets")
async def analytics_source_widgets(request: Request) -> dict[str, Any]:
    """Live KPI widgets for the active (or requested) BI datasource — fills Superset widgets panel."""
    sid = _resolve_source_id(request)
    return await build_source_widgets(datasource_id=sid, qg_base=QG_BASE)


@router.patch("/api/v1/bi/analytics/source-widgets/{widget_id}")
async def analytics_patch_source_widget(widget_id: str, request: Request) -> Any:
    """Persist visual type for a source widget (applied on next list/build)."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    wtype = str((body or {}).get("type") or "").strip()
    try:
        sid = _resolve_source_id(request, str((body or {}).get("datasource_id") or "").strip() or None)
        return save_widget_type(datasource_id=sid, widget_id=widget_id, widget_type=wtype)
    except ValueError as e:
        code = str(e)
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": code, "code": code},
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(e)[:300]},
        )


@router.get("/api/v1/bi/analytics/status")
async def analytics_status() -> dict[str, Any]:
    client = get_superset_client()
    if not client.configured():
        return _disabled_status()
    health = await client.health()
    return {
        "enabled": True,
        "url": client.public_url,
        "health": health,
    }


@router.get("/api/v1/bi/analytics/dashboards")
async def analytics_dashboards() -> dict[str, Any]:
    client = get_superset_client()
    if not client.configured():
        return {"dashboards": []}
    try:
        return {"dashboards": await client.list_dashboards()}
    except SupersetError as e:
        return _err(e)


@router.post("/api/v1/bi/analytics/dashboards")
async def analytics_create_dashboard(request: Request) -> Any:
    client = get_superset_client()
    if not client.configured():
        return JSONResponse(
            status_code=503,
            content={"error": "analytics_disabled", "message": "Analytics engine is not enabled"},
        )
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    title = str((body or {}).get("title") or "NanobaseAI Panel")
    try:
        return await client.create_dashboard(title)
    except SupersetError as e:
        return _err(e)


@router.get("/api/v1/bi/analytics/charts")
async def analytics_charts() -> Any:
    client = get_superset_client()
    if not client.configured():
        return {"charts": []}
    try:
        return {"charts": await client.list_charts()}
    except SupersetError as e:
        return _err(e)


@router.get("/api/v1/bi/analytics/datasets")
async def analytics_datasets() -> Any:
    client = get_superset_client()
    if not client.configured():
        return {"datasets": []}
    try:
        return {"datasets": await client.list_datasets()}
    except SupersetError as e:
        return _err(e)


@router.post("/api/v1/bi/analytics/guest-token/{dashboard_id}")
async def analytics_guest_token(dashboard_id: int) -> Any:
    client = get_superset_client()
    if not client.configured():
        return JSONResponse(
            status_code=503,
            content={"error": "analytics_disabled", "message": "Analytics engine is not enabled"},
        )
    try:
        return await client.mint_guest_token(int(dashboard_id))
    except SupersetError as e:
        return _err(e)


@router.get("/api/v1/bi/analytics/dashboards/{dashboard_id}/charts")
async def analytics_dashboard_charts(dashboard_id: int) -> Any:
    client = get_superset_client()
    if not client.configured():
        return {"charts": []}
    try:
        return {"charts": await client.dashboard_charts(int(dashboard_id))}
    except SupersetError as e:
        return _err(e)


@router.post("/api/v1/bi/analytics/dashboards/{dashboard_id}/pin")
async def analytics_pin(dashboard_id: int, request: Request) -> Any:
    """Pin chat SQL to the native source canvas (always) and optionally Superset."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    sql = str((body or {}).get("sql") or "").strip()
    if not sql:
        return JSONResponse(
            status_code=400,
            content={"error": "sql_required", "message": "pin requires sql"},
        )
    title = str((body or {}).get("title") or "NanobaseAI Chart")
    viz_type = str((body or {}).get("viz_type") or "table")
    sid = _resolve_source_id(request, str((body or {}).get("datasource_id") or "").strip() or None)

    widget_payload = (body or {}).get("widgets")
    first_widget: dict[str, Any] = {}
    if isinstance(widget_payload, list) and widget_payload and isinstance(widget_payload[0], dict):
        first_widget = widget_payload[0]

    canvas_widget = None
    try:
        pinned = pin_chat_widget(
            datasource_id=sid,
            sql=str(first_widget.get("sql") or sql),
            title=str(first_widget.get("title") or title),
            widget_type=str(first_widget.get("type") or viz_type or "table"),
            x_key=str(first_widget.get("x_key") or "") or None,
            y_key=str(first_widget.get("y_key") or "") or None,
            value_key=str(first_widget.get("value_key") or "") or None,
            label_key=str(first_widget.get("label_key") or "") or None,
            widget_id=str(first_widget.get("id") or "") or None,
        )
        canvas_widget = pinned.get("widget")
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"error": str(e), "message": str(e)},
        )

    client = get_superset_client()
    if not client.configured():
        return {
            "action": "pin_canvas",
            "dashboard_id": int(dashboard_id or 0),
            "datasource_id": sid,
            "widget": canvas_widget,
            "count": 1,
        }

    try:
        out = await client.pin_sql_chart(
            int(dashboard_id), sql=sql, title=title, viz_type=viz_type
        )
        if isinstance(out, dict):
            out = dict(out)
            out["widget"] = canvas_widget
            out["datasource_id"] = sid
            out.setdefault("action", "pin")
            return out
        return {
            "action": "pin",
            "dashboard_id": int(dashboard_id),
            "widget": canvas_widget,
            "datasource_id": sid,
            "result": out,
        }
    except SupersetError as e:
        # Native canvas pin already succeeded — do not fail the operator flow.
        return {
            "action": "pin_canvas",
            "dashboard_id": int(dashboard_id or 0),
            "datasource_id": sid,
            "widget": canvas_widget,
            "count": 1,
            "superset_error": e.code,
            "message": e.message,
        }
    except Exception as e:
        return {
            "action": "pin_canvas",
            "dashboard_id": int(dashboard_id or 0),
            "datasource_id": sid,
            "widget": canvas_widget,
            "count": 1,
            "superset_error": "superset_unreachable",
            "message": str(e)[:240],
        }


@router.delete("/api/v1/bi/analytics/dashboards/{dashboard_id}/charts/{chart_id}")
async def analytics_remove_chart(dashboard_id: int, chart_id: int) -> Any:
    client = get_superset_client()
    if not client.configured():
        return JSONResponse(
            status_code=503,
            content={"error": "analytics_disabled", "message": "Analytics engine is not enabled"},
        )
    try:
        return await client.remove_chart(int(dashboard_id), int(chart_id))
    except SupersetError as e:
        return _err(e)


@router.put("/api/v1/bi/analytics/dashboards/{dashboard_id}/layout")
async def analytics_reorder_layout(dashboard_id: int, request: Request) -> Any:
    client = get_superset_client()
    if not client.configured():
        return JSONResponse(
            status_code=503,
            content={"error": "analytics_disabled", "message": "Analytics engine is not enabled"},
        )
    try:
        body = await request.json()
    except Exception:
        body = {}
    chart_ids = (body or {}).get("chart_ids") or []
    if not isinstance(chart_ids, list):
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_layout", "message": "chart_ids must be a list"},
        )
    try:
        return await client.reorder_layout(int(dashboard_id), [int(x) for x in chart_ids])
    except SupersetError as e:
        return _err(e)
