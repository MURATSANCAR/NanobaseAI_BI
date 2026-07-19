"""Nanobase BI API — production FastAPI surface (Faz 3/4).

Reuses the bridge route surface and overlays bi_meta datasources.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from bridge import app as bridge_mod  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

app = bridge_mod.app
app.title = "Nanobase BI API"
app.version = "0.10.0"

from nanobase_api.errors import ApiError, api_error_handler  # noqa: E402

app.add_exception_handler(ApiError, api_error_handler)

META_DSN = os.environ.get(
    "NANOBASE_META_DSN",
    "postgresql+psycopg2://bi_meta@127.0.0.1:5434/bi_meta",
)
_engine = None

from nanobase_api.infrastructure.active_source import (  # noqa: E402
    prefer_datasource_id,
    resolve_active_id,
    resolve_schema_datasource_id,
    write_persisted_active,
)
from nanobase_api.infrastructure.datasource_registry import (  # noqa: E402
    merge_gateway_ro_sources,
)


def _active_ds(*candidates: str | None) -> str:
    """Resolve request/active datasource — never a hardcoded source name."""
    return prefer_datasource_id(
        *candidates,
        memory_id=bridge_mod.ACTIVE_DB.get("id"),
    )

bridge_mod.ACTIVE_DB["id"] = resolve_active_id(
    memory_id=None,
    known_ids=None,
)


def _meta_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(META_DSN, pool_pre_ping=True, pool_size=5)
    return _engine


_orig_sources_list = bridge_mod._sources_list_payload
_orig_health = bridge_mod.health


def _sources_list_payload_overlay(tenant_id: str | None = None) -> dict:
    # Bridge _sources_list_payload stamps ACTIVE_DB from a *different*
    # connection.local.json than nanobase secrets — remember and restore.
    remembered = str(bridge_mod.ACTIVE_DB.get("id") or "").strip()
    base = _orig_sources_list()
    if remembered:
        bridge_mod.ACTIVE_DB["id"] = remembered
    by_id = {s["id"]: s for s in (base.get("sources") or [])}

    try:
        with _meta_engine().connect() as conn:
            if tenant_id:
                rows = conn.execute(
                    text(
                        """
                        SELECT id, label, driver, dialect, host, port, database,
                               username, ssl, secret_ref, tenant_id, project_id
                        FROM bi_sources
                        WHERE tenant_id = :tenant_id
                        ORDER BY label
                        """
                    ),
                    {"tenant_id": tenant_id},
                ).mappings()
            else:
                rows = conn.execute(
                    text(
                        """
                        SELECT id, label, driver, dialect, host, port, database,
                               username, ssl, secret_ref, tenant_id, project_id
                        FROM bi_sources
                        ORDER BY label
                        """
                    )
                ).mappings()
            for r in rows:
                by_id[r["id"]] = {
                    "id": r["id"],
                    "label": r["label"],
                    "driver": r["driver"],
                    "dialect": r["dialect"],
                    "host": r["host"],
                    "port": r["port"],
                    "database": r["database"],
                    "username": r["username"],
                    "ssl": bool(r["ssl"]),
                    "secret_ref": r["secret_ref"],
                    "tenant_id": r["tenant_id"],
                    "project_id": r["project_id"] or "default",
                    "password_masked": "********" if r["secret_ref"] else None,
                    "deployment": "cloud",
                    "managed": False,
                    "protected": False,
                }
    except Exception:
        pass

    # Neon / Oracle / SAP / local reporting — whatever is registered in secrets maps
    merge_gateway_ro_sources(by_id)

    active = resolve_active_id(
        memory_id=bridge_mod.ACTIVE_DB.get("id"),
        known_ids=set(by_id.keys()),
    )
    bridge_mod.ACTIVE_DB["id"] = active

    return {"active_id": active, "sources": list(by_id.values())}


async def _health_overlay():
    h = await _orig_health()
    meta_ok = False
    try:
        with _meta_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
            meta_ok = True
    except Exception:
        meta_ok = False
    return {
        **h,
        "service": "nanobase_api",
        "bridge": False,
        "meta": meta_ok,
        "engine": "nanobase_api",
        "active_source": bridge_mod.ACTIVE_DB.get("id"),
    }


bridge_mod._sources_list_payload = _sources_list_payload_overlay
bridge_mod.health = _health_overlay

# Remove bridge catch-all + chat/semantic/analytics stubs + health so overlays bind cleanly
_REMOVE_PATHS = {
    "/health",
    "/api/v1/bi/health",
    "/api/v1/bi/status",
    "/api/v1/bi/schema",
    "/api/v1/bi/schema/refresh",
    "/api/v1/bi/{full_path:path}",
    "/api/v1/bi/chat/stream",
    "/api/v1/bi/chat",
    "/api/v1/bi/glossary",
    "/api/v1/bi/semantic/metrics",
    "/api/v1/bi/semantic/joins",
    "/api/v1/bi/semantic/templates",
    "/api/v1/bi/semantic/status",
    "/api/v1/bi/budgets",
    "/api/v1/bi/budgets/summary",
    "/api/v1/bi/alerts",
    "/api/v1/bi/audit",
    "/api/v1/bi/sources",
    "/api/v1/bi/sources/{source_id}",
    "/api/v1/bi/sources/{source_id}/activate",
    "/api/v1/bi/connection/test",
    "/api/v1/bi/analytics/status",
    "/api/v1/bi/analytics/dashboards",
    "/api/v1/bi/analytics/charts",
    "/api/v1/bi/analytics/datasets",
    "/api/v1/bi/briefing",
}
_app_routes = list(app.router.routes)
for _route in _app_routes:
    path = getattr(_route, "path", "") or ""
    if path.rstrip("/") in _REMOVE_PATHS or path in _REMOVE_PATHS:
        app.router.routes.remove(_route)

# ---------------------------------------------------------------------------
# Query Gateway proxy (Faz 5) — customer SQL never executes outside gateway
# ---------------------------------------------------------------------------
import uuid  # noqa: E402

import httpx  # noqa: E402
from fastapi import Request  # noqa: E402
from fastapi.responses import JSONResponse, StreamingResponse  # noqa: E402

from nanobase_api.chat_gateway import stream_chat_via_gateway  # noqa: E402
from nanobase_api import semantic as semantic_mod  # noqa: E402
from nanobase_api.semantic_catalog.api import router as semantic_catalog_router  # noqa: E402
from nanobase_api.analytics_api import router as analytics_router  # noqa: E402

app.include_router(semantic_catalog_router)
app.include_router(analytics_router)
from nanobase_api.schema_api import fetch_schema  # noqa: E402
from nanobase_api import budgets as budgets_mod  # noqa: E402
from nanobase_api import budget_actuals as budget_actuals_mod  # noqa: E402
from nanobase_api import budget_ops as budget_ops_mod  # noqa: E402
from nanobase_api import budget_fx as budget_fx_mod  # noqa: E402
from nanobase_api import budget_lines as budget_lines_mod  # noqa: E402
from nanobase_api.infrastructure.budget_schema import ensure_budget_tables  # noqa: E402
from nanobase_api import alerts as alerts_mod  # noqa: E402
from nanobase_api import workflows as workflows_mod  # noqa: E402
from nanobase_api.secrets_resolver import secrets_status  # noqa: E402
from nanobase_api.auth import (  # noqa: E402
    RequestPrincipal,
    get_current_principal,
    require_source_admin,
)
from nanobase_api.application.datasources import DatasourceService  # noqa: E402
from nanobase_api.application.schema_scans import SchemaScanService  # noqa: E402
from nanobase_api.infrastructure.sources_repo import SourcesRepository  # noqa: E402
from nanobase_api.infrastructure.secret_store import FileVaultSecretStore  # noqa: E402
from nanobase_api.infrastructure.audit_repo import AuditRepository  # noqa: E402
from nanobase_api.infrastructure.schema_scan_repo import SchemaScanRepository  # noqa: E402
from nanobase_api.infrastructure.schema_indexer_adapter import SchemaIndexerAdapter  # noqa: E402
from nanobase_api.config import get_settings  # noqa: E402
from fastapi import Depends  # noqa: E402

QG_BASE = os.environ.get("QUERY_GATEWAY_BASE", "http://127.0.0.1:8792").rstrip("/")
app.version = "0.10.0"


def _ds_service() -> DatasourceService:
    eng = _meta_engine()
    return DatasourceService(SourcesRepository(eng), FileVaultSecretStore(), AuditRepository(eng))


def _scan_service() -> SchemaScanService:
    eng = _meta_engine()
    return SchemaScanService(
        SchemaScanRepository(eng),
        SourcesRepository(eng),
        SchemaIndexerAdapter(),
        AuditRepository(eng),
    )


@app.get("/health")
@app.get("/api/v1/bi/health/live")
async def health_live() -> dict:
    meta_ok = False
    try:
        with _meta_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        meta_ok = True
    except Exception:
        meta_ok = False
    return {
        "status": "UP" if meta_ok else "DOWN",
        "service": "nanobase_api",
        "engine": "nanobase_api",
        "meta": meta_ok,
    }


@app.get("/api/v1/bi/health/ready")
async def health_ready() -> dict:
    checks: dict[str, str] = {}
    try:
        with _meta_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["metadataDatabase"] = "UP"
    except Exception:
        checks["metadataDatabase"] = "DOWN"
    qg_ok = False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{QG_BASE}/health")
            qg_ok = r.status_code == 200
    except Exception:
        qg_ok = False
    checks["queryGateway"] = "UP" if qg_ok else "DOWN"
    redis_ok = False
    try:
        import redis as redis_lib

        redis_lib.Redis.from_url(get_settings().redis_url, socket_timeout=1).ping()
        redis_ok = True
    except Exception:
        redis_ok = False
    checks["redis"] = "UP" if redis_ok else "DOWN"
    status = "UP" if checks["metadataDatabase"] == "UP" else "DOWN"
    if status == "UP" and (checks["queryGateway"] == "DOWN" or checks["redis"] == "DOWN"):
        status = "DEGRADED"
    return {"status": status, "checks": checks}


async def _probe_datasource_live(sid: str) -> dict:
    """Lightweight SELECT 1 via Query Gateway for FE connection.ok banners."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.post(
                f"{QG_BASE}/api/v1/query/execute",
                json={"datasource_id": sid, "sql": "SELECT 1 AS ok"},
            )
            data = r.json() if r.content else {}
            ok = r.status_code == 200 and bool(data.get("ok"))
            msg = None
            if not ok:
                msg = (
                    data.get("error")
                    or data.get("message")
                    or data.get("detail")
                    or f"datasource probe failed ({r.status_code})"
                )
                if isinstance(msg, dict):
                    msg = str(msg.get("message") or msg)[:240]
                else:
                    msg = str(msg)[:240]
            return {
                "ok": ok,
                "dialect": "postgresql",
                "message": msg,
                "code": None if ok else "CONNECTION_FAILED",
                "datasource_id": sid,
            }
    except Exception as e:
        return {
            "ok": False,
            "dialect": "postgresql",
            "message": str(e)[:240],
            "code": "CONNECTION_FAILED",
            "datasource_id": sid,
        }


def _schema_pulse(sid: str) -> dict:
    try:
        schema = fetch_schema(sid)
    except Exception as e:
        return {
            "schema_ready": False,
            "schema_cached": False,
            "table_count": 0,
            "error": str(e)[:200],
            "source_label": sid,
        }
    tables = schema.get("tables") or []
    table_count = int(schema.get("table_count") or len(tables) or 0)
    ready = table_count > 0 and not schema.get("error")
    return {
        "schema_ready": ready,
        "schema_cached": ready,
        "table_count": table_count,
        "source_label": sid,
        "top_tables": [
            (t.get("name") or t.get("table_name") or "")
            for t in tables[:8]
            if isinstance(t, dict)
        ],
        "error": schema.get("error"),
    }


@app.get("/api/v1/bi/health")
@app.get("/api/v1/bi/status")
async def bi_status() -> dict:
    h = await _health_overlay()
    ready = await health_ready()
    active = _active_ds()
    sources_payload = _sources_list_payload_overlay()
    sources = sources_payload.get("sources") or []
    conn = await _probe_datasource_live(str(active))
    pulse = _schema_pulse(str(active))
    settings = get_settings()
    return {
        "ok": True,
        "status": "ready" if ready.get("status") in ("UP", "DEGRADED") and h.get("meta") else "degraded",
        "engine": "nanobase_api",
        "service": "nanobase_api",
        "meta": h.get("meta"),
        "dbgpt": h.get("dbgpt"),
        "llm": h.get("llm"),
        "query_gateway": ready.get("checks", {}).get("queryGateway") == "UP",
        "redis": ready.get("checks", {}).get("redis") == "UP",
        "auth_mode": settings.auth_mode.value,
        "execution_mode": settings.execution_mode.value,
        "active_source": active,
        "llm_model": os.environ.get("LLM_MODEL_NAME", "nanobase-qwen36-35b-a3b-mtp"),
        "model_queue": __import__(
            "nanobase_awel.operators.model_queue", fromlist=["get_model_queue"]
        )
        .get_model_queue()
        .stats(),
        "checks": ready.get("checks"),
        "analytics": {
            "enabled": settings.superset_enabled,
            "url": settings.superset_public_url or None,
            "health": {"ok": bool(settings.superset_enabled)},
        },
        "engine_mode": "superset" if settings.superset_enabled else None,
        # FE contract (BiConnectionBanner / BiOpsHealthPanel / briefing)
        "database_configured": len(sources) > 0,
        "connection": conn,
        "schema_ready": pulse["schema_ready"],
        "schema_cached": pulse["schema_cached"],
        "table_count": pulse["table_count"],
        "warnings": [],
        "capabilities": {
            "chat": True,
            "schema": True,
            "analytics": bool(settings.superset_enabled),
            "share": bool(settings.public_share_enabled),
        },
    }


@app.get("/api/v1/bi/ops-health")
async def bi_ops_health(dashboard_id: str = "default") -> dict:
    """FE ops strip / settings panel — was falling through to limited catch-all."""
    active = _active_ds()
    conn = await _probe_datasource_live(str(active))
    pulse = _schema_pulse(str(active))
    db_ready = bool(conn.get("ok"))
    return {
        "dashboard_id": dashboard_id,
        "anomaly_count": 0,
        "alert_count": 0,
        "action_count": 0,
        "db_ready": db_ready,
        "data_pulse": {
            "db_ready": db_ready,
            "table_count": pulse["table_count"],
            "source_label": pulse["source_label"],
            "top_tables": pulse.get("top_tables") or [],
        },
        "delta_summary": [],
        "actions": [],
    }


@app.get("/api/v1/bi/briefing")
async def bi_briefing(dashboard_id: str = "default", locale: str = "tr") -> dict:
    """Minimal briefing pulse so morning strip does not show 'db not connected'."""
    _ = locale
    active = _active_ds()
    conn = await _probe_datasource_live(str(active))
    pulse = _schema_pulse(str(active))
    db_ready = bool(conn.get("ok"))
    return {
        "dashboard_id": dashboard_id,
        "attention": [],
        "insights": [],
        "delta_summary": {"up": 0, "down": 0, "flat": 0},
        "data_pulse": {
            "db_ready": db_ready,
            "table_count": pulse["table_count"],
            "source_label": pulse["source_label"],
            "top_tables": pulse.get("top_tables") or [],
        },
        "actions": [],
        "anomaly_count": 0,
        "alert_count": 0,
        "action_count": 0,
    }


@app.get("/api/v1/bi/suggestions")
async def chat_suggestions_api(
    datasource_id: str | None = None,
    limit: int = 6,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> dict:
    """Quick suggestions for active (or given) datasource: learned + cold-start defaults.

    Not under /chat/... — that prefix collides with bridge GET /chat/{session_id}.
    """
    from nanobase_api.suggestions import build_suggestions

    sid = _active_ds(datasource_id)
    return build_suggestions(
        engine=_meta_engine(),
        tenant_id=principal.tenant_id,
        datasource_id=sid,
        limit=limit,
    )


@app.get("/api/v1/bi/alert-suggestions")
async def alert_suggestions_api(
    datasource_id: str | None = None,
    limit: int = 3,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> dict:
    """Threshold-alert chips for the active (or given) datasource / project."""
    from nanobase_api.suggestions import build_alert_suggestions

    _ = principal
    sid = _active_ds(datasource_id)
    return build_alert_suggestions(datasource_id=sid, limit=limit)


@app.get("/api/v1/bi/model-queue/status")
async def model_queue_status() -> dict:
    """Public queue depth for ops / UI (no secrets)."""
    from nanobase_awel.operators.model_queue import USER_WAIT_MESSAGE_TR, get_model_queue

    q = get_model_queue()
    st = q.stats()
    return {
        "ok": True,
        **st,
        "userWaitMessage": USER_WAIT_MESSAGE_TR,
        "saturated": st["waiting"] > 0 or st["active"] >= st["maxConcurrency"],
    }


@app.get("/api/v1/bi/sources")
async def sources_list_api(
    principal: RequestPrincipal = Depends(get_current_principal),
) -> dict:
    # Tenant-scoped meta merge + shared builtins/maps from overlay
    overlay = _sources_list_payload_overlay(tenant_id=principal.tenant_id)
    return {
        "active_id": overlay.get("active_id") or bridge_mod.ACTIVE_DB.get("id"),
        "sources": overlay.get("sources") or [],
    }


@app.put("/api/v1/bi/sources/{source_id}")
async def sources_upsert_api(
    source_id: str,
    request: Request,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> dict:
    require_source_admin(principal)
    body = await request.json()
    return _ds_service().upsert_source(principal, source_id, body)


@app.delete("/api/v1/bi/sources/{source_id}")
async def sources_delete_api(
    source_id: str,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> dict:
    require_source_admin(principal)
    return _ds_service().delete_source(principal, source_id)


async def _qg_registered_datasource_ids() -> set[str]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{QG_BASE}/health")
            if r.status_code >= 400:
                return set()
            return {str(x) for x in (r.json() or {}).get("datasources") or []}
    except Exception:
        return set()


async def _test_datasource(principal: RequestPrincipal, sid: str) -> dict:
    require_source_admin(principal)
    try:
        return _ds_service().test_connection(principal, sid)
    except ApiError as e:
        # Any Gateway-registered source (not a fixed name list) can be probed via QG
        if e.code == "DATASOURCE_NOT_FOUND" and sid in await _qg_registered_datasource_ids():
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    f"{QG_BASE}/api/v1/query/execute",
                    json={"datasource_id": sid, "sql": "SELECT 1 AS ok"},
                )
                ok = r.status_code == 200 and (r.json() or {}).get("ok")
            return {
                "success": bool(ok),
                "ok": bool(ok),
                "databaseType": "POSTGRESQL",
                "via": "query_gateway",
            }
        raise


@app.post("/api/v1/bi/sources/{source_id}/test")
async def sources_test_api(
    source_id: str,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> dict:
    return await _test_datasource(principal, source_id)


@app.post("/api/v1/bi/connection/test")
async def connection_test_api(
    request: Request,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> dict:
    sid = _active_ds()
    try:
        body = await request.json()
        sid = str(body.get("datasource_id") or body.get("id") or sid)
    except Exception:
        pass
    return await _test_datasource(principal, sid)


@app.post("/api/v1/bi/sources/{source_id}/activate")
async def sources_activate_api(source_id: str) -> dict:
    sid = str(source_id or "").strip()
    if not sid:
        raise ApiError("SOURCE_ID_REQUIRED", "source_id required", status=400)
    bridge_mod.ACTIVE_DB["id"] = sid
    write_persisted_active(sid)
    # Return list shape FE expects after activate
    overlay = _sources_list_payload_overlay()
    return {
        "ok": True,
        "active_id": overlay.get("active_id") or sid,
        "sources": overlay.get("sources") or [],
    }


@app.post("/api/v1/bi/sources/{source_id}/scan")
async def sources_scan_api(
    source_id: str,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> dict:
    require_source_admin(principal)
    return await _scan_service().start_scan(principal, source_id)


@app.get("/api/v1/bi/schema-scans/{scan_id}")
async def schema_scan_status_api(
    scan_id: str,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> dict:
    return _scan_service().get_status(principal, scan_id)


def _schema_datasource_id(request: Request | None = None, body: dict | None = None) -> str:
    q = ""
    b = ""
    if request is not None:
        q = str(request.query_params.get("datasource_id") or request.query_params.get("db_name") or "").strip()
    if isinstance(body, dict):
        b = str(body.get("datasource_id") or body.get("db_name") or "").strip()
    return resolve_schema_datasource_id(
        query_datasource_id=q or None,
        body_datasource_id=b or None,
        memory_id=bridge_mod.ACTIVE_DB.get("id"),
    )


@app.get("/api/v1/bi/schema")
async def schema_get(request: Request) -> JSONResponse:
    ds = _schema_datasource_id(request)
    try:
        return JSONResponse(fetch_schema(ds))
    except Exception as e:
        return JSONResponse(
            {
                "tables": [],
                "dialect": "postgresql",
                "source_id": ds,
                "graph": {"nodes": [], "edges": []},
                "error": str(e)[:400],
            },
            status_code=503,
        )


@app.post("/api/v1/bi/schema/refresh")
async def schema_refresh(request: Request) -> JSONResponse:
    body: dict = {}
    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}
    ds = _schema_datasource_id(request, body)
    try:
        schema = fetch_schema(ds)
        return JSONResponse(
            {"ok": True, "tables": schema.get("table_count") or len(schema.get("tables") or []), "source_id": ds}
        )
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:300]}, status_code=503)


@app.post("/api/v1/bi/query/validate")
@app.post("/api/v1/query/validate")
async def proxy_query_validate(
    request: Request,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    """Portal-authenticated proxy — never expose Query Gateway without principal."""
    _ = principal
    body = await request.json()
    if "datasource_id" not in body:
        body["datasource_id"] = _active_ds()
    from nanobase_api.infrastructure.query_gateway_client import QueryGatewayClient

    qg = QueryGatewayClient(QG_BASE)
    data = await qg.validate(
        sql=str(body.get("sql") or ""),
        datasource_id=str(body.get("datasource_id")),
        tenant_id=principal.tenant_id,
    )
    status = 200 if data.get("ok") else 400
    return JSONResponse(data, status_code=status)


@app.post("/api/v1/bi/query/execute")
@app.post("/api/v1/query/execute")
async def proxy_query_execute(
    request: Request,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    """Portal-authenticated proxy — never expose Query Gateway without principal."""
    body = await request.json()
    if "datasource_id" not in body:
        body["datasource_id"] = _active_ds()
    from nanobase_api.infrastructure.query_gateway_client import QueryGatewayClient

    qg = QueryGatewayClient(QG_BASE)
    try:
        data = await qg.execute(
            sql=str(body.get("sql") or ""),
            datasource_id=str(body.get("datasource_id")),
            tenant_id=principal.tenant_id,
            explain=bool(body.get("explain")),
        )
        return JSONResponse(data, status_code=200 if data.get("ok") else 400)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:400]}, status_code=400)


@app.post("/api/v1/bi/chat/stream")
async def chat_stream_gateway(
    request: Request,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> StreamingResponse:
    """Faz 6/7/3: verified cache | LLM → Query Gateway validate/execute/explain."""
    body = await request.json()
    message = str(body.get("message") or "").strip()
    session_id = str(body.get("session_id") or uuid.uuid4())
    ds = str(body.get("db_name") or _active_ds())
    if not message:

        async def _err():
            yield (
                f"event: error\ndata: {json.dumps({'message': 'empty message'})}\n\n"
            ).encode()

        return StreamingResponse(_err(), media_type="text/event-stream")

    try:
        from nanobase_api.infrastructure.audit_repo import AuditRepository

        AuditRepository(_meta_engine()).record(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            action="QUESTION_SUBMITTED",
            ok=True,
            session_id=session_id,
            extra={"datasource_id": ds},
        )
    except Exception:
        pass

    return StreamingResponse(
        stream_chat_via_gateway(
            message,
            session_id,
            ds,
            meta_engine=_meta_engine(),
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
        ),
        media_type="text/event-stream",
    )


# ---------------------------------------------------------------------------
# Semantic catalog + verified SQL + feedback (Faz 7)
# ---------------------------------------------------------------------------


@app.get("/api/v1/bi/semantic/status")
async def semantic_status() -> JSONResponse:
    try:
        return JSONResponse(semantic_mod.semantic_status(_meta_engine()))
    except Exception as e:
        return JSONResponse(
            {"ok": False, "enabled": False, "engine": "nanobase_api", "error": str(e)[:300]},
            status_code=503,
        )


@app.get("/api/v1/bi/glossary")
async def glossary_list() -> JSONResponse:
    try:
        return JSONResponse({"entries": semantic_mod.list_glossary(_meta_engine())})
    except Exception as e:
        return JSONResponse({"entries": [], "error": str(e)[:300]}, status_code=503)


@app.get("/api/v1/bi/semantic/metrics")
async def semantic_metrics() -> JSONResponse:
    try:
        return JSONResponse({"metrics": semantic_mod.list_metrics(_meta_engine())})
    except Exception as e:
        return JSONResponse({"metrics": [], "error": str(e)[:300]}, status_code=503)


@app.get("/api/v1/bi/semantic/joins")
async def semantic_joins() -> JSONResponse:
    try:
        return JSONResponse({"joins": semantic_mod.list_joins(_meta_engine())})
    except Exception as e:
        return JSONResponse({"joins": [], "error": str(e)[:300]}, status_code=503)


@app.get("/api/v1/bi/semantic/verified-sql")
async def verified_sql_list(datasource_id: str | None = None) -> JSONResponse:
    ds = datasource_id or _active_ds()
    try:
        with _meta_engine().connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT id, question_display, sql_text, hit_count, status, updated_at
                    FROM bi_verified_sql
                    WHERE datasource_id = :ds AND status = 'verified'
                    ORDER BY hit_count DESC, updated_at DESC
                    LIMIT 100
                    """
                ),
                {"ds": ds},
            ).mappings()
            items = [
                {
                    "id": r["id"],
                    "question": r["question_display"],
                    "sql": r["sql_text"],
                    "hit_count": r["hit_count"],
                    "status": r["status"],
                    "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
                }
                for r in rows
            ]
        return JSONResponse({"items": items, "datasource_id": ds})
    except Exception as e:
        return JSONResponse({"items": [], "error": str(e)[:300]}, status_code=503)


@app.post("/api/v1/bi/query/feedback")
@app.post("/api/v1/bi/feedback")
async def query_feedback(
    request: Request,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    body = await request.json()
    question = str(body.get("question") or "").strip()
    try:
        rating = int(body.get("rating"))
    except (TypeError, ValueError):
        return JSONResponse(
            {"ok": False, "code": "VALIDATION_ERROR", "error": "question and rating (-1|0|1) required"},
            status_code=400,
        )
    comment = str(body["comment"]).strip() if body.get("comment") is not None else ""
    if not question or rating not in (-1, 0, 1):
        return JSONResponse(
            {"ok": False, "code": "VALIDATION_ERROR", "error": "question and rating (-1|0|1) required"},
            status_code=400,
        )
    if rating in (-1, 0) and len(comment) < 5:
        return JSONResponse(
            {
                "ok": False,
                "code": "VALIDATION_ERROR",
                "error": "Kısmi veya yanlış geri bildirim için en az 5 karakterlik açıklama gerekli.",
            },
            status_code=400,
        )
    try:
        result = semantic_mod.save_feedback(
            _meta_engine(),
            datasource_id=str(
                body.get("datasource_id") or _active_ds()
            ),
            question=question,
            rating=rating,
            sql_text=(str(body["sql"]) if body.get("sql") else None),
            session_id=(str(body["session_id"]) if body.get("session_id") else None),
            comment=(comment or None),
            promote_verified=bool(body.get("promote_verified")),
            tenant_id=principal.tenant_id,
        )
        try:
            AuditRepository(_meta_engine()).record(
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                action="FEEDBACK_SUBMITTED",
                ok=True,
                session_id=str(body["session_id"]) if body.get("session_id") else None,
                extra={"rating": rating, "promote_verified": bool(body.get("promote_verified"))},
            )
        except Exception:
            pass
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:400]}, status_code=500)


# ---------------------------------------------------------------------------
# Budgets + Alerts (bi_meta)
# ---------------------------------------------------------------------------


def _budget_err(exc: Exception, *, status: int = 400) -> JSONResponse:
    code = str(exc)
    if code.startswith("bi_"):
        return JSONResponse({"ok": False, "error": code, "code": code}, status_code=status)
    return JSONResponse({"ok": False, "error": code[:400]}, status_code=500)


@app.on_event("startup")
async def _budget_schema_startup() -> None:
    try:
        ensure_budget_tables(_meta_engine())
    except Exception:
        pass


@app.get("/api/v1/bi/budgets")
async def budgets_list(
    fiscal_year: int | None = None,
    kind: str | None = None,
    status: str | None = None,
    scenario: str | None = None,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    try:
        items = budgets_mod.list_budgets(
            _meta_engine(),
            tenant_id=principal.tenant_id,
            fiscal_year=fiscal_year,
            kind=kind,
            status=status,
            scenario=scenario,
        )
        return JSONResponse({"budgets": items, "engine": "nanobase_api"})
    except Exception as e:
        return JSONResponse({"budgets": [], "error": str(e)[:300]}, status_code=503)


@app.get("/api/v1/bi/budgets/summary")
async def budgets_summary(
    fiscal_year: int | None = None,
    scenario: str | None = None,
    reporting_currency: str | None = None,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    try:
        return JSONResponse(
            budgets_mod.budget_summary(
                _meta_engine(),
                tenant_id=principal.tenant_id,
                fiscal_year=fiscal_year,
                scenario=scenario,
                reporting_currency=reporting_currency,
            )
        )
    except Exception as e:
        return JSONResponse({"error": str(e)[:300]}, status_code=503)


@app.post("/api/v1/bi/budgets")
async def budgets_upsert(
    request: Request,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    body = await request.json()
    try:
        return JSONResponse(
            budgets_mod.upsert_budget(
                _meta_engine(), body, tenant_id=principal.tenant_id, actor=principal.user_id
            )
        )
    except ValueError as e:
        return _budget_err(e)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:400]}, status_code=500)


@app.delete("/api/v1/bi/budgets/{budget_id}")
async def budgets_delete(
    budget_id: str,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    try:
        budgets_mod.delete_budget(_meta_engine(), budget_id, tenant_id=principal.tenant_id)
        return JSONResponse({"ok": True})
    except ValueError as e:
        return _budget_err(e)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:300]}, status_code=500)


@app.post("/api/v1/bi/budgets/validate-sql")
async def budgets_validate_sql(
    request: Request,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    body = await request.json()
    try:
        result = await budget_actuals_mod.validate_budget_sql(
            str(body.get("sql") or ""),
            datasource_id=_active_ds(body.get("datasource_id")),
            tenant_id=principal.tenant_id,
        )
        return JSONResponse(result)
    except ValueError as e:
        return _budget_err(e)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:400]}, status_code=500)


@app.post("/api/v1/bi/budgets/refresh-actuals")
async def budgets_refresh_all(
    fiscal_year: int | None = None,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    try:
        result = await budget_actuals_mod.refresh_all(
            _meta_engine(),
            tenant_id=principal.tenant_id,
            fiscal_year=fiscal_year,
            datasource_id=_active_ds(),
        )
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:400]}, status_code=500)


@app.post("/api/v1/bi/budgets/{budget_id}/refresh-actuals")
async def budgets_refresh_one(
    budget_id: str,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    try:
        row = await budget_actuals_mod.refresh_one(
            _meta_engine(),
            budget_id,
            tenant_id=principal.tenant_id,
            datasource_id=_active_ds(),
        )
        return JSONResponse(row)
    except ValueError as e:
        return _budget_err(e)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:400]}, status_code=500)


@app.post("/api/v1/bi/budgets/{budget_id}/approve")
async def budgets_approve(
    budget_id: str,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    try:
        row = await budget_ops_mod.approve_budget(
            _meta_engine(),
            budget_id,
            tenant_id=principal.tenant_id,
            actor=principal.user_id,
            datasource_id=_active_ds(),
        )
        return JSONResponse(row)
    except ValueError as e:
        return _budget_err(e)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:400]}, status_code=500)


@app.post("/api/v1/bi/budgets/{budget_id}/lock")
async def budgets_lock(
    budget_id: str,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    try:
        return JSONResponse(
            budget_ops_mod.set_budget_locked(
                _meta_engine(),
                budget_id,
                locked=True,
                tenant_id=principal.tenant_id,
                actor=principal.user_id,
            )
        )
    except ValueError as e:
        return _budget_err(e)


@app.post("/api/v1/bi/budgets/{budget_id}/unlock")
async def budgets_unlock(
    budget_id: str,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    try:
        return JSONResponse(
            budget_ops_mod.set_budget_locked(
                _meta_engine(),
                budget_id,
                locked=False,
                tenant_id=principal.tenant_id,
                actor=principal.user_id,
            )
        )
    except ValueError as e:
        return _budget_err(e)


@app.get("/api/v1/bi/budgets/{budget_id}/change-log")
async def budgets_change_log(
    budget_id: str,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    return JSONResponse(
        {
            "entries": budgets_mod.list_change_log(
                _meta_engine(), budget_id, tenant_id=principal.tenant_id
            )
        }
    )


@app.get("/api/v1/bi/budgets/{budget_id}/history")
async def budgets_history(
    budget_id: str,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    # Shape-compatible empty until actuals history snapshots are wired
    _ = (budget_id, principal)
    return JSONResponse({"points": []})


@app.get("/api/v1/bi/budgets/{budget_id}/breakdown")
async def budgets_breakdown(
    budget_id: str,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    _ = (budget_id, principal)
    return JSONResponse({"rows": [], "columns": []})


@app.get("/api/v1/bi/budgets/{budget_id}/periods")
async def budgets_periods_get(
    budget_id: str,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    return JSONResponse(
        {
            "periods": budget_lines_mod.list_periods(
                _meta_engine(), budget_id, tenant_id=principal.tenant_id
            )
        }
    )


@app.put("/api/v1/bi/budgets/{budget_id}/periods")
async def budgets_periods_put(
    budget_id: str,
    request: Request,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    body = await request.json()
    try:
        periods = budget_lines_mod.save_periods(
            _meta_engine(),
            budget_id,
            list(body.get("periods") or []),
            tenant_id=principal.tenant_id,
        )
        return JSONResponse({"periods": periods})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:400]}, status_code=500)


@app.get("/api/v1/bi/budgets/{budget_id}/commitments")
async def budgets_commitments_get(
    budget_id: str,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    return JSONResponse(
        {
            "commitments": budget_lines_mod.list_commitments(
                _meta_engine(), budget_id, tenant_id=principal.tenant_id
            )
        }
    )


@app.post("/api/v1/bi/budgets/{budget_id}/commitments")
async def budgets_commitments_post(
    budget_id: str,
    request: Request,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    body = await request.json()
    try:
        row = budget_lines_mod.save_commitment(
            _meta_engine(), budget_id, body, tenant_id=principal.tenant_id
        )
        return JSONResponse(row)
    except ValueError as e:
        return _budget_err(e)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:400]}, status_code=500)


@app.delete("/api/v1/bi/budgets/{budget_id}/commitments/{commitment_id}")
async def budgets_commitments_delete(
    budget_id: str,
    commitment_id: str,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    try:
        budget_lines_mod.delete_commitment(
            _meta_engine(), budget_id, commitment_id, tenant_id=principal.tenant_id
        )
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:300]}, status_code=500)


@app.post("/api/v1/bi/budgets/transfer")
async def budgets_transfer(
    request: Request,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    body = await request.json()
    try:
        return JSONResponse(
            budget_ops_mod.transfer_allocated(
                _meta_engine(),
                tenant_id=principal.tenant_id,
                from_budget_id=str(body.get("from_budget_id") or ""),
                to_budget_id=str(body.get("to_budget_id") or ""),
                amount=float(body.get("amount") or 0),
                actor=principal.user_id,
            )
        )
    except ValueError as e:
        return _budget_err(e)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:400]}, status_code=500)


@app.post("/api/v1/bi/budgets/clone-year")
async def budgets_clone_year(
    request: Request,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    body = await request.json()
    try:
        return JSONResponse(
            budget_ops_mod.clone_budgets_year(
                _meta_engine(),
                tenant_id=principal.tenant_id,
                from_year=int(body.get("from_year")),
                to_year=int(body.get("to_year")),
                copy_actuals_sql=bool(body.get("copy_actuals_sql", True)),
                scenario=body.get("scenario"),
                actor=principal.user_id,
            )
        )
    except ValueError as e:
        return _budget_err(e)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:400]}, status_code=500)


@app.get("/api/v1/bi/budgets/narrative")
async def budgets_narrative(
    fiscal_year: int,
    locale: str = "en",
    scenario: str | None = None,
    reporting_currency: str | None = None,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    return JSONResponse(
        budget_ops_mod.build_budget_narrative(
            _meta_engine(),
            tenant_id=principal.tenant_id,
            fiscal_year=fiscal_year,
            locale=locale,
            scenario=scenario,
            reporting_currency=reporting_currency,
        )
    )


@app.get("/api/v1/bi/budgets/actuals-templates")
async def budgets_actuals_templates(
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    _ = principal
    return JSONResponse(
        {
            "templates": [
                {
                    "id": "literal_zero",
                    "kind": "demo",
                    "label_key": "bi.budget.template.none",
                    "sql": "SELECT 0 AS actual",
                    "demo": True,
                }
            ]
        }
    )


@app.get("/api/v1/bi/budgets/related-tables")
async def budgets_related_tables(
    limit: int = 16,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    _ = (limit, principal)
    return JSONResponse({"tables": []})


@app.get("/api/v1/bi/fx-rates")
async def fx_rates_list(
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    return JSONResponse(
        {"rates": budget_fx_mod.list_fx_rates(_meta_engine(), tenant_id=principal.tenant_id)}
    )


@app.post("/api/v1/bi/fx-rates")
async def fx_rates_upsert(
    request: Request,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    body = await request.json()
    try:
        return JSONResponse(
            budget_fx_mod.upsert_fx_rate(
                _meta_engine(), body, tenant_id=principal.tenant_id
            )
        )
    except ValueError as e:
        return _budget_err(e)


@app.get("/api/v1/bi/cost-centers")
async def cost_centers_list(
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    return JSONResponse(budget_lines_mod.list_cost_centers(_meta_engine(), tenant_id=principal.tenant_id))


@app.post("/api/v1/bi/cost-centers")
async def cost_centers_save(
    request: Request,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    body = await request.json()
    try:
        return JSONResponse(
            budget_lines_mod.save_cost_center(
                _meta_engine(), body, tenant_id=principal.tenant_id
            )
        )
    except ValueError as e:
        return _budget_err(e)


@app.get("/api/v1/bi/cost-centers/rollup")
async def cost_centers_rollup(
    fiscal_year: int,
    scenario: str | None = None,
    reporting_currency: str | None = None,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    # Minimal empty rollup shape (full hierarchy is a later phase)
    summary = budgets_mod.budget_summary(
        _meta_engine(),
        tenant_id=principal.tenant_id,
        fiscal_year=fiscal_year,
        scenario=scenario,
        reporting_currency=reporting_currency,
    )
    return JSONResponse(
        {
            "tree": [],
            "flat": [],
            "unassigned": summary.get("totals") or {},
            "unassigned_count": int((summary.get("totals") or {}).get("count") or 0),
            "reporting_currency": summary.get("reporting_currency"),
            "fx_missing": summary.get("fx_missing") or [],
        }
    )


@app.post("/api/v1/bi/budgets/sync-from-source")
async def budgets_sync_from_source(
    request: Request,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    """Pull butce_planlari via authenticated Query Gateway into bi_budgets."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    ds = str(body.get("datasource_id") or _active_ds())
    fiscal_year = body.get("fiscal_year")
    scenario = str(body.get("scenario") or "base")
    do_refresh = bool(body.get("refresh"))
    sql = (
        "SELECT id, mali_yil, departman_kod, butce_kodu, kalem_adi, tur, "
        "planlanan_tutar, para_birimi FROM butce_planlari"
    )
    try:
        from nanobase_api.infrastructure.query_gateway_client import QueryGatewayClient

        qg = QueryGatewayClient(QG_BASE)
        data = await qg.execute(sql=sql, datasource_id=ds, tenant_id=principal.tenant_id)
        if not data.get("ok"):
            return JSONResponse(
                {"ok": False, "error": data.get("error") or "gateway failed"},
                status_code=400,
            )
        result = budgets_mod.sync_from_erp_butce(
            _meta_engine(),
            data.get("rows") or [],
            tenant_id=principal.tenant_id,
            datasource_id=ds,
            fiscal_year=int(fiscal_year) if fiscal_year is not None else None,
            scenario=scenario,
        )
        if do_refresh:
            refresh = await budget_actuals_mod.refresh_all(
                _meta_engine(),
                tenant_id=principal.tenant_id,
                fiscal_year=int(fiscal_year) if fiscal_year is not None else result.get("fiscal_year"),
                datasource_id=ds,
            )
            result["refresh"] = refresh
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:400]}, status_code=500)


@app.get("/api/v1/bi/audit")
async def audit_list_api(
    limit: int = 100,
    action: str | None = None,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> dict:
    """BI Audit page — recent bi_audit_events (replaces bridge empty stub)."""
    from nanobase_api.infrastructure.audit_repo import AuditRepository

    entries = AuditRepository(_meta_engine()).list_entries(
        tenant_id=principal.tenant_id,
        limit=limit,
        action=action,
    )
    return {"entries": entries, "count": len(entries)}


@app.get("/api/v1/bi/alerts")
async def alerts_list() -> JSONResponse:
    try:
        return JSONResponse({"alerts": alerts_mod.list_alerts(_meta_engine()), "engine": "nanobase_api"})
    except Exception as e:
        return JSONResponse({"alerts": [], "error": str(e)[:300]}, status_code=503)


@app.post("/api/v1/bi/alerts")
async def alerts_save(request: Request) -> JSONResponse:
    body = await request.json()
    try:
        return JSONResponse(alerts_mod.save_alert(_meta_engine(), body))
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:400]}, status_code=500)


@app.delete("/api/v1/bi/alerts/{alert_id}")
async def alerts_delete(alert_id: str) -> JSONResponse:
    try:
        alerts_mod.delete_alert(_meta_engine(), alert_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:300]}, status_code=500)


@app.post("/api/v1/bi/alerts/check-now")
async def alerts_check_now(request: Request) -> JSONResponse:
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    ds = str(body.get("datasource_id") or _active_ds())
    try:
        result = await alerts_mod.check_alerts_now(
            _meta_engine(), gateway_base=QG_BASE, datasource_id=ds
        )
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"checked": 0, "triggered": 0, "errors": [str(e)[:300]]}, status_code=500)


@app.get("/api/v1/bi/secrets/status")
async def secrets_status_api() -> JSONResponse:
    return JSONResponse({"ok": True, **secrets_status()})


@app.post("/api/v1/bi/workflows/nl2sql-plan")
async def workflow_nl2sql_plan(request: Request) -> JSONResponse:
    body = await request.json()
    question = str(body.get("question") or "").strip()
    if not question:
        return JSONResponse({"error": "question required"}, status_code=400)
    ds = str(body.get("datasource_id") or _active_ds())
    from nanobase_api.chat_gateway import _schema_hint_for

    try:
        plan = await workflows_mod.nl2sql_plan(
            question=question,
            conversation_context=body.get("conversationContext") or body.get("conversation_context"),
            datasource_context=body.get("datasourceContext")
            or {"datasource_id": ds},
            allowed_schemas=body.get("allowedSchemas") or body.get("allowed_schemas"),
            allowed_tables=body.get("allowedTables") or body.get("allowed_tables"),
            schema_hint=_schema_hint_for(ds),
        )
        return JSONResponse(plan)
    except Exception as e:
        return JSONResponse({"error": str(e)[:400]}, status_code=500)


@app.post("/api/v1/bi/workflows/result-explain")
async def workflow_result_explain(request: Request) -> JSONResponse:
    body = await request.json()
    question = str(body.get("question") or "").strip()
    sql = str(body.get("executedSql") or body.get("executed_sql") or "").strip()
    columns = body.get("columns") or []
    rows = body.get("rows") or []
    if not question:
        return JSONResponse({"error": "question required"}, status_code=400)
    try:
        out = await workflows_mod.result_explain(
            question=question,
            executed_sql=sql,
            columns=list(columns),
            rows=list(rows),
            truncated=bool(body.get("truncated")),
        )
        return JSONResponse(out)
    except Exception as e:
        return JSONResponse({"error": str(e)[:400]}, status_code=500)


@app.post("/api/v1/bi/internal/workflows/sql-plan")
async def internal_sql_plan(
    request: Request,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    """Faz 6 internal: nanobase-sql-plan-v1 (no DB execute)."""
    if request.headers.get("X-Nanobase-Workflow-Version") not in (None, "", "1"):
        return JSONResponse({"code": "CONTRACT_VERSION_NOT_SUPPORTED"}, status_code=400)
    body = await request.json()
    from nanobase_api.chat_gateway import _schema_hint_for
    from nanobase_api.infrastructure.text2sql_adapter import WorkflowTextToSqlAdapter

    question = str(body.get("question") or "").strip()
    if not question:
        return JSONResponse({"code": "VALIDATION_ERROR", "message": "question required"}, status_code=400)
    ds = str(body.get("datasourceId") or body.get("datasource_id") or _active_ds())
    try:
        plan = await WorkflowTextToSqlAdapter().generate_sql_plan(
            question=question,
            datasource_id=ds,
            schema_hint=_schema_hint_for(ds),
            conversation_context=body.get("conversationContext") or body.get("conversation_context"),
            tenant_id=principal.tenant_id,
            execution_id=str(body.get("executionId") or ""),
            allowed_tables=body.get("allowedTables") or body.get("allowed_tables"),
        )
        return JSONResponse(plan)
    except Exception as e:
        return JSONResponse({"code": "FAILED", "message": str(e)[:400]}, status_code=500)


@app.post("/api/v1/bi/internal/workflows/sql-repair")
async def internal_sql_repair(
    request: Request,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    if request.headers.get("X-Nanobase-Workflow-Version") not in (None, "", "1"):
        return JSONResponse({"code": "CONTRACT_VERSION_NOT_SUPPORTED"}, status_code=400)
    body = await request.json()
    from nanobase_api.infrastructure.text2sql_adapter import WorkflowTextToSqlAdapter

    try:
        out = await WorkflowTextToSqlAdapter().repair_sql(
            question=str(body.get("question") or ""),
            datasource_id=str(body.get("datasourceId") or body.get("datasource_id") or _active_ds()),
            previous_sql=str(body.get("previousSql") or body.get("previous_sql") or ""),
            error_code=str((body.get("gatewayError") or {}).get("code") or body.get("code") or ""),
            error_message=str(
                (body.get("gatewayError") or {}).get("safeMessage")
                or body.get("message")
                or "policy"
            ),
            attempt=int(body.get("attempt") or 1),
            authorized_context=str(body.get("authorizedContext") or ""),
            tenant_id=principal.tenant_id,
            execution_id=str(body.get("executionId") or ""),
        )
        return JSONResponse(out)
    except Exception as e:
        return JSONResponse({"code": "FAILED", "message": str(e)[:400]}, status_code=500)


@app.post("/api/v1/bi/internal/workflows/result-explain")
async def internal_result_explain(
    request: Request,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> JSONResponse:
    if request.headers.get("X-Nanobase-Workflow-Version") not in (None, "", "1"):
        return JSONResponse({"code": "CONTRACT_VERSION_NOT_SUPPORTED"}, status_code=400)
    body = await request.json()
    from nanobase_api.infrastructure.text2sql_adapter import WorkflowTextToSqlAdapter

    try:
        out = await WorkflowTextToSqlAdapter().explain_result(
            question=str(body.get("question") or ""),
            executed_sql=str(body.get("executedSql") or body.get("executed_sql") or ""),
            columns=list(body.get("columns") or []),
            rows=list(body.get("rows") or []),
            truncated=bool(body.get("truncated")),
            datasource_id=str(body.get("datasourceId") or ""),
            tenant_id=principal.tenant_id,
            execution_id=str(body.get("executionId") or ""),
        )
        return JSONResponse(out)
    except Exception as e:
        return JSONResponse({"code": "FAILED", "message": str(e)[:400]}, status_code=500)


# Soft catch-all AFTER real routes — shape-compatible empties (no bare limited stubs)
@app.api_route("/api/v1/bi/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def bi_limited(full_path: str) -> JSONResponse:
    path = (full_path or "").strip().strip("/")
    if path.startswith("budgets/import") or path.startswith("budgets/export") or path == "budgets/import-template":
        return JSONResponse(
            {"ok": False, "code": "bi_budget_feature_pending", "error": "Excel import/export is not enabled yet."},
            status_code=501,
        )
    if path == "budgets/share-pack" or path.endswith("/create-alert"):
        return JSONResponse(
            {"ok": False, "code": "bi_budget_feature_pending", "created": False, "error": "Feature pending."},
            status_code=501,
        )
    if path == "budgets/match-preview":
        return JSONResponse({"fiscal_year": 0, "matches": [], "warnings": ["bi_budget_feature_pending"]})
    if path.startswith("shares"):
        return JSONResponse({"shares": []})
    return JSONResponse({"ok": True, "engine": "nanobase_api", "limited": True, "path": full_path})
