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

bridge_mod.ACTIVE_DB["id"] = os.environ.get("NANOBASE_ACTIVE_DB", "bi_reporting")


def _meta_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(META_DSN, pool_pre_ping=True, pool_size=5)
    return _engine


_orig_sources_list = bridge_mod._sources_list_payload
_orig_health = bridge_mod.health


def _sources_list_payload_overlay(tenant_id: str | None = None) -> dict:
    base = _orig_sources_list()
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
                }
    except Exception:
        pass

    if "bi_reporting" not in by_id:
        by_id["bi_reporting"] = {
            "id": "bi_reporting",
            "label": "BI Reporting (RO)",
            "driver": "postgresql",
            "dialect": "postgresql",
            "host": "127.0.0.1",
            "port": 5435,
            "database": "bi_reporting",
            "username": "bi_reporting_ro",
            "ssl": False,
            "secret_ref": "file:/data/nanobaseai/bi/secrets/reporting-ro.password",
            "tenant_id": "default",
            "project_id": "default",
            "password_masked": "********",
            "deployment": "onprem",
        }

    # Faz 8: surface Oracle RO sources registered for Query Gateway (no passwords)
    try:
        secrets = Path(os.environ.get("SECRETS_ROOT", "/data/nanobaseai/bi/secrets"))
        ora_map = secrets / "oracle-ro.datasources.json"
        if ora_map.is_file():
            raw = json.loads(ora_map.read_text(encoding="utf-8"))
            for sid, cfg in (raw.get("sources") or raw).items():
                if not isinstance(cfg, dict):
                    continue
                by_id[str(sid)] = {
                    "id": str(sid),
                    "label": cfg.get("label") or str(sid),
                    "driver": "oracle",
                    "dialect": "oracle",
                    "host": cfg.get("host") or "",
                    "port": int(cfg.get("port") or 1522),
                    "database": cfg.get("service_name") or cfg.get("database") or "",
                    "username": cfg.get("user") or cfg.get("username") or "",
                    "ssl": True,
                    "secret_ref": cfg.get("password_file")
                    or f"file:{secrets}/oracle-adb.password",
                    "tenant_id": "default",
                    "project_id": "default",
                    "password_masked": "********",
                    "deployment": "cloud",
                }
        sap_map = secrets / "sap-ro.datasources.json"
        if sap_map.is_file():
            raw = json.loads(sap_map.read_text(encoding="utf-8"))
            for sid, cfg in (raw.get("sources") or raw).items():
                if not isinstance(cfg, dict):
                    continue
                driver = (cfg.get("driver") or "").lower()
                if driver in ("hana", "sap_hana", "hdb"):
                    by_id[str(sid)] = {
                        "id": str(sid),
                        "label": cfg.get("label") or str(sid),
                        "driver": "hana",
                        "dialect": "hana",
                        "host": cfg.get("host") or "",
                        "port": int(cfg.get("port") or 443),
                        "database": cfg.get("database") or "",
                        "username": cfg.get("user") or cfg.get("username") or "",
                        "ssl": True,
                        "secret_ref": cfg.get("password_file") or "",
                        "tenant_id": "default",
                        "project_id": "default",
                        "password_masked": "********",
                        "deployment": "cloud",
                    }
                elif driver in ("odata", "cds", "cds_odata"):
                    by_id[str(sid)] = {
                        "id": str(sid),
                        "label": cfg.get("label") or str(sid),
                        "driver": "odata",
                        "dialect": "odata",
                        "host": cfg.get("base_url") or cfg.get("url") or "",
                        "port": 443,
                        "database": "",
                        "username": cfg.get("user") or cfg.get("username") or "",
                        "ssl": True,
                        "secret_ref": cfg.get("password_file") or cfg.get("token_file") or "",
                        "tenant_id": "default",
                        "project_id": "default",
                        "password_masked": "********",
                        "deployment": "cloud",
                    }
    except Exception:
        pass

    active = os.environ.get("NANOBASE_ACTIVE_DB") or bridge_mod.ACTIVE_DB.get("id") or "bi_reporting"
    if active not in by_id:
        active = next(iter(by_id), "bi_reporting")
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

# Remove bridge catch-all + chat/semantic stubs + health so overlays bind cleanly
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
    "/api/v1/bi/sources",
    "/api/v1/bi/sources/{source_id}",
    "/api/v1/bi/sources/{source_id}/activate",
    "/api/v1/bi/connection/test",
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
from nanobase_api.schema_api import fetch_schema  # noqa: E402
from nanobase_api import budgets as budgets_mod  # noqa: E402
from nanobase_api import alerts as alerts_mod  # noqa: E402
from nanobase_api import workflows as workflows_mod  # noqa: E402
from nanobase_api.secrets_resolver import secrets_status  # noqa: E402
from nanobase_api.auth import get_current_principal, RequestPrincipal  # noqa: E402
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
    return {"status": "UP", "service": "nanobase_api"}


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


@app.get("/api/v1/bi/health")
@app.get("/api/v1/bi/status")
async def bi_status() -> dict:
    h = await _health_overlay()
    ready = await health_ready()
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
        "auth_mode": get_settings().auth_mode.value,
        "execution_mode": get_settings().execution_mode.value,
        "active_source": bridge_mod.ACTIVE_DB.get("id"),
        "llm_model": os.environ.get("LLM_MODEL_NAME", "nanobase-qwen36-35b-a3b-mtp"),
        "checks": ready.get("checks"),
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
    body = await request.json()
    return _ds_service().upsert_source(principal, source_id, body)


@app.delete("/api/v1/bi/sources/{source_id}")
async def sources_delete_api(
    source_id: str,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> dict:
    return _ds_service().delete_source(principal, source_id)


async def _test_datasource(principal: RequestPrincipal, sid: str) -> dict:
    try:
        return _ds_service().test_connection(principal, sid)
    except ApiError as e:
        if e.code == "DATASOURCE_NOT_FOUND" and sid in ("bi_reporting", "erp", "sigorta"):
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
    sid = bridge_mod.ACTIVE_DB.get("id") or "bi_reporting"
    try:
        body = await request.json()
        sid = str(body.get("datasource_id") or body.get("id") or sid)
    except Exception:
        pass
    return await _test_datasource(principal, sid)


@app.post("/api/v1/bi/sources/{source_id}/activate")
async def sources_activate_api(source_id: str) -> dict:
    bridge_mod.ACTIVE_DB["id"] = source_id
    return {"ok": True, "active_id": source_id}


@app.post("/api/v1/bi/sources/{source_id}/scan")
async def sources_scan_api(
    source_id: str,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> dict:
    return await _scan_service().start_scan(principal, source_id)


@app.get("/api/v1/bi/schema-scans/{scan_id}")
async def schema_scan_status_api(
    scan_id: str,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> dict:
    return _scan_service().get_status(principal, scan_id)


@app.get("/api/v1/bi/schema")
async def schema_get() -> JSONResponse:
    ds = bridge_mod.ACTIVE_DB.get("id") or "bi_reporting"
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
async def schema_refresh() -> JSONResponse:
    ds = bridge_mod.ACTIVE_DB.get("id") or "bi_reporting"
    try:
        schema = fetch_schema(ds)
        return JSONResponse(
            {"ok": True, "tables": schema.get("table_count") or len(schema.get("tables") or []), "source_id": ds}
        )
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:300]}, status_code=503)


@app.post("/api/v1/bi/query/validate")
@app.post("/api/v1/query/validate")
async def proxy_query_validate(request: Request) -> JSONResponse:
    body = await request.json()
    if "datasource_id" not in body:
        body["datasource_id"] = bridge_mod.ACTIVE_DB.get("id") or "bi_reporting"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{QG_BASE}/api/v1/query/validate", json=body)
        return JSONResponse(r.json(), status_code=r.status_code)


@app.post("/api/v1/bi/query/execute")
@app.post("/api/v1/query/execute")
async def proxy_query_execute(request: Request) -> JSONResponse:
    body = await request.json()
    if "datasource_id" not in body:
        body["datasource_id"] = bridge_mod.ACTIVE_DB.get("id") or "bi_reporting"
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{QG_BASE}/api/v1/query/execute", json=body)
        try:
            data = r.json()
        except Exception:
            data = {"ok": False, "error": r.text[:400]}
        return JSONResponse(data, status_code=r.status_code)


@app.post("/api/v1/bi/chat/stream")
async def chat_stream_gateway(
    request: Request,
    principal: RequestPrincipal = Depends(get_current_principal),
) -> StreamingResponse:
    """Faz 6/7/3: verified cache | LLM → Query Gateway validate/execute/explain."""
    body = await request.json()
    message = str(body.get("message") or "").strip()
    session_id = str(body.get("session_id") or uuid.uuid4())
    ds = str(body.get("db_name") or bridge_mod.ACTIVE_DB.get("id") or "bi_reporting")
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
    ds = datasource_id or bridge_mod.ACTIVE_DB.get("id") or "bi_reporting"
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
    rating = int(body.get("rating") or 0)
    if not question or rating not in (-1, 1):
        return JSONResponse(
            {"ok": False, "code": "VALIDATION_ERROR", "error": "question and rating (-1|1) required"},
            status_code=400,
        )
    try:
        result = semantic_mod.save_feedback(
            _meta_engine(),
            datasource_id=str(
                body.get("datasource_id") or bridge_mod.ACTIVE_DB.get("id") or "bi_reporting"
            ),
            question=question,
            rating=rating,
            sql_text=(str(body["sql"]) if body.get("sql") else None),
            session_id=(str(body["session_id"]) if body.get("session_id") else None),
            comment=(str(body["comment"]) if body.get("comment") else None),
            promote_verified=bool(body.get("promote_verified")),
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


@app.get("/api/v1/bi/budgets")
async def budgets_list(
    fiscal_year: int | None = None,
    kind: str | None = None,
    status: str | None = None,
    scenario: str | None = None,
) -> JSONResponse:
    try:
        items = budgets_mod.list_budgets(
            _meta_engine(),
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
    fiscal_year: int | None = None, scenario: str | None = None
) -> JSONResponse:
    try:
        return JSONResponse(
            budgets_mod.budget_summary(
                _meta_engine(), fiscal_year=fiscal_year, scenario=scenario
            )
        )
    except Exception as e:
        return JSONResponse({"error": str(e)[:300]}, status_code=503)


@app.post("/api/v1/bi/budgets")
async def budgets_upsert(request: Request) -> JSONResponse:
    body = await request.json()
    try:
        return JSONResponse(budgets_mod.upsert_budget(_meta_engine(), body))
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:400]}, status_code=500)


@app.delete("/api/v1/bi/budgets/{budget_id}")
async def budgets_delete(budget_id: str) -> JSONResponse:
    try:
        budgets_mod.delete_budget(_meta_engine(), budget_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:300]}, status_code=500)


@app.post("/api/v1/bi/budgets/sync-from-source")
async def budgets_sync_from_source(request: Request) -> JSONResponse:
    """Pull erp.butce_planlari via Query Gateway into bi_budgets."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    ds = str(body.get("datasource_id") or "erp")
    sql = (
        "SELECT id, mali_yil, departman_kod, butce_kodu, kalem_adi, tur, "
        "planlanan_tutar, para_birimi FROM butce_planlari"
    )
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{QG_BASE}/api/v1/query/execute",
                json={"datasource_id": ds, "sql": sql, "max_limit": 500},
            )
            data = r.json()
        if r.status_code >= 400 or not data.get("ok"):
            return JSONResponse(
                {"ok": False, "error": data.get("detail") or data.get("error") or "gateway failed"},
                status_code=400,
            )
        result = budgets_mod.sync_from_erp_butce(_meta_engine(), data.get("rows") or [])
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:400]}, status_code=500)


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
    ds = str(body.get("datasource_id") or bridge_mod.ACTIVE_DB.get("id") or "bi_reporting")
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
    ds = str(body.get("datasource_id") or bridge_mod.ACTIVE_DB.get("id") or "bi_reporting")
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


# Soft catch-all AFTER real routes (empty stubs for remaining FE SaaS paths)
@app.api_route("/api/v1/bi/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def bi_limited(full_path: str) -> JSONResponse:
    return JSONResponse({"ok": True, "engine": "nanobase_api", "limited": True, "path": full_path})
