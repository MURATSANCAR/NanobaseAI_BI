"""Nanobase BI ↔ DB-GPT bridge (all-in on DB-GPT for BI SPA).

Default listen :8789 on portal (nginx `/bi-api/` + `/api/v1/bi/` + `/api/v1/llm/`).
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

DBGPT_BASE = os.environ.get("DBGPT_BASE", "http://127.0.0.1:5670").rstrip("/")
LLM_BASE = os.environ.get("OPENAI_API_BASE", "http://127.0.0.1:8010/v1").rstrip("/")
LLM_KEY = os.environ.get("OPENAI_API_KEY", "nanobase-local")
LLM_MODEL = os.environ.get("LLM_MODEL_NAME", "nanobaseai-bi-llm")
EMBED_URL = os.environ.get("BI_EMBED_URL", "http://127.0.0.1:8083/v1/embeddings")
EMBED_KEY = os.environ.get("BI_EMBED_API_KEY", "")
BRIDGE_PORT = int(os.environ.get("BRIDGE_PORT", "8789"))
SOURCES_FILE = Path(
    os.environ.get(
        "BI_SOURCES_FILE",
        str(Path(__file__).resolve().parents[2] / "configs" / "sources" / "local" / "connection.local.json"),
    )
)
ACTIVE_DB = {"id": (os.environ.get("NANOBASE_ACTIVE_DB") or "").strip()}

app = FastAPI(title="NanobaseAI BI API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("PORTAL_CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# One shared client (keepalive) instead of a client per request; closed on shutdown.
_HTTP_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)
_STREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=30.0)
_http_client: Optional[httpx.AsyncClient] = None


def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0), limits=_HTTP_LIMITS)
    return _http_client


@app.on_event("shutdown")
async def _close_http_client() -> None:
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
    _http_client = None


def _load_sources() -> dict[str, Any]:
    if SOURCES_FILE.is_file():
        return json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    return {"active_id": ACTIVE_DB.get("id") or "", "sources": {}}


def _sources_list_payload() -> dict[str, Any]:
    raw = _load_sources()
    sources_map = raw.get("sources") or {}
    active = str(raw.get("active_id") or ACTIVE_DB.get("id") or "").strip()
    if not active and sources_map:
        active = sorted(str(k) for k in sources_map.keys())[0]
    ACTIVE_DB["id"] = active
    items = []
    for sid, s in sources_map.items():
        items.append(
            {
                "id": s.get("id") or sid,
                "label": s.get("label") or sid,
                "driver": s.get("driver") or "postgresql",
                "dialect": s.get("dialect") or "postgresql",
                "host": s.get("host"),
                "port": s.get("port"),
                "database": s.get("database"),
                "username": s.get("username"),
                "ssl": bool(s.get("ssl", True)),
                "deployment": s.get("deployment") or "cloud",
                "secret_ref": s.get("secret_ref"),
                "tenant_id": s.get("tenant_id") or "default",
                "project_id": s.get("project_id") or "default",
                "password_masked": "********" if s.get("password") else None,
            }
        )
    return {"active_id": ACTIVE_DB["id"], "sources": items}


def _active_db_id() -> str:
    """Resolve the active datasource from the sources file (shared across
    uvicorn workers); fall back to the in-process value."""
    active = str(_load_sources().get("active_id") or ACTIVE_DB.get("id") or "").strip()
    if active:
        ACTIVE_DB["id"] = active
    return active


async def _dbgpt_json(method: str, path: str, *, json_body: Any = None, timeout: float = 120.0) -> Any:
    url = f"{DBGPT_BASE}{path}"
    resp = await get_http_client().request(method, url, json=json_body, timeout=timeout)
    resp.raise_for_status()
    if not resp.content:
        return None
    return resp.json()


async def _probe(url: str, headers: Optional[dict[str, str]] = None) -> bool:
    try:
        r = await get_http_client().get(url, headers=headers or {}, timeout=3.0)
        return r.status_code < 500
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Health / portal (BI SPA uses /bi-api → these stubs)
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, Any]:
    dbgpt_ok = await _probe(f"{DBGPT_BASE}/")
    llm_ok = await _probe(f"{LLM_BASE}/models", {"Authorization": f"Bearer {LLM_KEY}"})
    return {
        "ok": True,
        "bridge": True,
        "dbgpt": dbgpt_ok,
        "llm": llm_ok,
        "dbgpt_base": DBGPT_BASE,
        "llm_base": LLM_BASE,
        "engine": "nanobaseai-bi",
    }


@app.get("/api/v1/bi/health")
@app.get("/api/v1/bi/status")
async def bi_status() -> dict[str, Any]:
    h = await health()
    return {
        "ok": True,
        "status": "ready" if h["dbgpt"] and h["llm"] else ("degraded" if h["dbgpt"] else "down"),
        "engine": "nanobaseai-bi",
        "dbgpt": h["dbgpt"],
        "llm": h["llm"],
        "llm_model": LLM_MODEL,
        "active_source": ACTIVE_DB["id"],
    }


@app.get("/api/v1/portal/bootstrap")
async def portal_bootstrap() -> dict[str, Any]:
    return {
        "auth_required": False,
        "portal_users_enabled": False,
        "portal_auto_login": True,
        "httponly_api_key": False,
        "portal_modules": ["bi"],
        "modules": ["bi"],
        "features": {"bi": True},
        "supported_locales": ["tr", "en"],
    }


@app.get("/api/v1/portal/runtime-config")
async def runtime_config() -> dict[str, Any]:
    return {
        "apiKey": "nanobaseai-bi-local",
        "apiKeyConfigured": True,
        "authMode": "bearer",
        "portalAutoLogin": True,
        "authenticated": True,
        "role": "admin",
        "modules": ["bi"],
    }


@app.post("/api/v1/portal/auth/login")
async def portal_login(request: Request) -> dict[str, Any]:
    body: dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:
        pass
    user = str(body.get("username") or body.get("email") or "bi-local")
    return {
        "token": "nanobaseai-bi-local",
        "access_token": "nanobaseai-bi-local",
        "api_key": "nanobaseai-bi-local",
        "user": {"id": "local", "username": user, "role": "admin", "roles": ["admin"]},
        "session": {"id": "local", "token": "nanobaseai-bi-local"},
    }


@app.post("/api/v1/portal/auth/logout")
async def portal_logout() -> dict[str, Any]:
    return {"ok": True}


@app.post("/api/v1/portal/session")
async def portal_session_create() -> dict[str, Any]:
    return {"ok": True, "token": "nanobaseai-bi-local"}


@app.delete("/api/v1/portal/session")
async def portal_session_clear() -> dict[str, Any]:
    return {"ok": True}


@app.get("/api/v1/portal/auth/me")
@app.get("/api/v1/portal/me")
async def portal_me() -> dict[str, Any]:
    return {"id": "local", "username": "bi-local", "role": "admin", "roles": ["admin"]}


@app.get("/api/v1/portal/users")
async def portal_users() -> list[Any]:
    return [{"id": "local", "username": "bi-local", "role": "admin"}]


@app.get("/api/v1/llm/status")
async def llm_status() -> dict[str, Any]:
    ok = await _probe(f"{LLM_BASE}/models", {"Authorization": f"Bearer {LLM_KEY}"})
    return {
        "busy": False,
        "ok": ok,
        "model": LLM_MODEL,
        "api_base": LLM_BASE,
        "engine": "nanobaseai-bi-llm",
        "via": "nanobaseai-bi",
    }


@app.post("/api/v1/llm/cancel")
async def llm_cancel() -> dict[str, Any]:
    return {"ok": True}


# OpenAI-compat embedding shim → BGE-M3 contract service (texts[] API)
@app.post("/v1/embeddings")
async def openai_embeddings(request: Request) -> JSONResponse:
    body = await request.json()
    raw = body.get("input") or body.get("texts") or []
    texts = raw if isinstance(raw, list) else [str(raw)]
    headers = {"Content-Type": "application/json"}
    if EMBED_KEY:
        headers["Authorization"] = f"Bearer {EMBED_KEY}"
    r = await get_http_client().post(
        EMBED_URL, headers=headers, json={"texts": texts}, timeout=60.0
    )
    if r.status_code >= 400:
        return JSONResponse({"error": r.text[:400]}, status_code=r.status_code)
    data = r.json()
    vectors = data.get("embeddings") or []
    return JSONResponse(
        {
            "object": "list",
            "model": data.get("model") or "BAAI/bge-m3",
            "data": [{"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vectors)],
            "usage": {"prompt_tokens": 0, "total_tokens": 0},
        }
    )


# ---------------------------------------------------------------------------
# Sources / connection / schema
# ---------------------------------------------------------------------------


@app.get("/api/v1/bi/sources")
async def sources_list() -> dict[str, Any]:
    return _sources_list_payload()


@app.put("/api/v1/bi/sources/{source_id}")
async def sources_upsert(source_id: str, request: Request) -> dict[str, Any]:
    body = await request.json()
    raw = _load_sources()
    sources = raw.setdefault("sources", {})
    sources[source_id] = {**sources.get(source_id, {}), **body, "id": source_id}
    try:
        SOURCES_FILE.parent.mkdir(parents=True, exist_ok=True)
        SOURCES_FILE.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    except OSError:
        pass
    return {"ok": True, "id": source_id}


@app.post("/api/v1/bi/sources/{source_id}/activate")
async def sources_activate(source_id: str) -> dict[str, Any]:
    ACTIVE_DB["id"] = source_id
    raw = _load_sources()
    raw["active_id"] = source_id
    try:
        SOURCES_FILE.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    except OSError:
        pass
    return {"ok": True, "active_id": source_id}


@app.get("/api/v1/bi/connection")
async def connection_get() -> dict[str, Any]:
    payload = _sources_list_payload()
    for s in payload["sources"]:
        if s["id"] == payload["active_id"]:
            return s
    return payload["sources"][0] if payload["sources"] else {}


@app.put("/api/v1/bi/connection")
async def connection_save(request: Request) -> dict[str, Any]:
    body = await request.json()
    sid = str(body.get("id") or ACTIVE_DB.get("id") or "").strip()
    if not sid:
        return {"ok": False, "error": "datasource id required"}
    return await sources_upsert(sid, request)


@app.post("/api/v1/bi/connection/test")
async def connection_test() -> dict[str, Any]:
    try:
        await _dbgpt_json("GET", "/api/v1/chat/db/list")
        return {"ok": True, "message": "OK (NanobaseAI BI datasource registry)", "dialect": "postgresql"}
    except Exception as e:
        return {"ok": False, "message": str(e), "dialect": "postgresql"}


@app.get("/api/v1/bi/schema")
async def schema_get() -> dict[str, Any]:
    db = _active_db_id()
    tables: list[dict[str, Any]] = []
    try:
        data = await _dbgpt_json("GET", f"/api/v1/editor/db/tables?db_name={db}")
        rows = data.get("data") if isinstance(data, dict) else data
        if isinstance(rows, list):
            for t in rows:
                name = t.get("table_name") or t.get("name") or str(t)
                cols = t.get("columns") or t.get("column_info") or []
                columns = []
                if isinstance(cols, list):
                    for c in cols:
                        if isinstance(c, dict):
                            columns.append(
                                {
                                    "name": c.get("name") or c.get("column_name") or "col",
                                    "type": c.get("type") or c.get("column_type") or "text",
                                    "type_display": c.get("type_display")
                                    or c.get("type")
                                    or c.get("column_type")
                                    or "text",
                                    "nullable": c.get("nullable", True),
                                    "max_length": c.get("max_length")
                                    or c.get("character_maximum_length"),
                                    "precision": c.get("precision") or c.get("numeric_precision"),
                                    "scale": c.get("scale") or c.get("numeric_scale"),
                                }
                            )
                        else:
                            columns.append({"name": str(c), "type": "text"})
                tables.append({"name": name, "schema": t.get("schema") or "public", "columns": columns})
    except Exception:
        tables = []
    return {"tables": tables, "dialect": "postgresql", "source_id": db, "graph": {"nodes": [], "edges": []}}


@app.post("/api/v1/bi/schema/refresh")
async def schema_refresh() -> dict[str, Any]:
    try:
        await _dbgpt_json("POST", "/api/v1/chat/db/refresh", json_body={"db_name": _active_db_id()})
    except Exception:
        pass
    schema = await schema_get()
    return {"ok": True, "tables": len(schema.get("tables") or [])}


@app.get("/api/v1/bi/templates")
async def templates() -> list[Any]:
    return []


@app.get("/api/v1/bi/chat/sessions")
async def chat_sessions() -> list[Any]:
    try:
        data = await _dbgpt_json("POST", "/api/v1/serve/conversation/list", json_body={})
        rows = data.get("data") if isinstance(data, dict) else data
        out = []
        if isinstance(rows, list):
            for r in rows:
                out.append(
                    {
                        "id": r.get("conv_uid") or r.get("id"),
                        "title": r.get("user_input") or r.get("title") or "Chat",
                        "updated_at": r.get("gmt_modified") or r.get("updated_at"),
                    }
                )
        return out
    except Exception:
        return []


@app.get("/api/v1/bi/chat/{session_id}")
async def chat_history(session_id: str) -> dict[str, Any]:
    try:
        data = await _dbgpt_json(
            "POST",
            "/api/v1/serve/conversation/messages/history",
            json_body={"conv_uid": session_id},
        )
        msgs = data.get("data") if isinstance(data, dict) else data
        return {"session_id": session_id, "messages": msgs or []}
    except Exception:
        return {"session_id": session_id, "messages": []}


@app.get("/api/v1/bi/chat/{session_id}/pending")
async def chat_pending(session_id: str) -> dict[str, Any]:
    return {"pending": False, "session_id": session_id}


@app.delete("/api/v1/bi/chat/{session_id}")
async def chat_delete(session_id: str) -> dict[str, Any]:
    try:
        await _dbgpt_json("POST", "/api/v1/serve/conversation/delete", json_body={"conv_uid": session_id})
    except Exception:
        pass
    return {"ok": True}


@app.patch("/api/v1/bi/chat/{session_id}")
async def chat_rename(session_id: str, request: Request) -> dict[str, Any]:
    return {"ok": True, "id": session_id}


# ---------------------------------------------------------------------------
# Soft capabilities (DB-GPT has no native budgets/Superset SaaS layer)
# Return shaped empties so FE pages load; chat remains the real BI surface.
# ---------------------------------------------------------------------------


@app.get("/api/v1/bi/analytics/status")
async def analytics_status() -> dict[str, Any]:
    # Shaped for FE (api.bi.analytics.status). Production uses nanobase_api overlay.
    return {
        "enabled": False,
        "url": None,
        "health": {"ok": False, "message": "analytics_disabled", "dashboard_count": 0},
    }


@app.get("/api/v1/bi/analytics/dashboards")
async def analytics_dashboards() -> dict[str, Any]:
    return {"dashboards": []}


@app.get("/api/v1/bi/analytics/charts")
async def analytics_charts() -> dict[str, Any]:
    return {"charts": []}


@app.get("/api/v1/bi/analytics/datasets")
async def analytics_datasets() -> dict[str, Any]:
    return {"datasets": []}


@app.get("/api/v1/bi/budgets")
@app.get("/api/v1/bi/alerts")
@app.get("/api/v1/bi/shares")
@app.get("/api/v1/bi/schedules")
@app.get("/api/v1/bi/glossary")
@app.get("/api/v1/bi/queries")
@app.get("/api/v1/bi/audit")
@app.get("/api/v1/bi/anomalies")
@app.get("/api/v1/bi/comments")
async def list_empty() -> list[Any]:
    return []


@app.get("/api/v1/bi/budgets/summary")
async def budget_summary() -> dict[str, Any]:
    return {"years": [], "totals": {}, "engine": "nanobaseai-bi"}


@app.get("/api/v1/bi/briefing")
async def briefing() -> dict[str, Any]:
    # Shaped for FE morning briefing; production nanobase_api overlays this route.
    return {
        "dashboard_id": "default",
        "attention": [],
        "insights": [],
        "delta_summary": {"up": 0, "down": 0, "flat": 0},
        "data_pulse": {
            "db_ready": False,
            "table_count": 0,
            "source_label": None,
            "top_tables": [],
        },
        "actions": [],
        "anomaly_count": 0,
        "alert_count": 0,
        "action_count": 0,
    }


@app.get("/api/v1/bi/semantic/metrics")
@app.get("/api/v1/bi/semantic/joins")
@app.get("/api/v1/bi/semantic/templates")
async def semantic_empty() -> list[Any]:
    return []


@app.get("/api/v1/bi/semantic/status")
async def semantic_status() -> dict[str, Any]:
    return {"ok": True, "enabled": False, "engine": "nanobaseai-bi", "message": "Semantic layer via NanobaseAI BI chat/schema."}


# ---------------------------------------------------------------------------
# Chat → DB-GPT
# ---------------------------------------------------------------------------


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _empty_chat_result(session_id: str, reply: str, sql: Optional[str] = None) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "reply": reply,
        "intent": "query",
        "widgets": [],
        "answer_blocks": [{"type": "text", "text": reply}],
        "sql": sql,
        "sql_error": None,
        "query_result": None,
    }


async def _stream_dbgpt_chat(message: str, session_id: str, db_name: str) -> AsyncIterator[bytes]:
    yield _sse("status", {"phase": "preparing"}).encode()
    yield _sse("status", {"phase": "planning"}).encode()

    body = {
        "user_input": message,
        "conv_uid": session_id,
        "chat_mode": "chat_with_db_execute",
        "select_param": db_name,
        "model_name": LLM_MODEL,
        "incremental": True,
        "temperature": 0.2,
        "max_new_tokens": 2048,
    }

    url = f"{DBGPT_BASE}/api/v1/chat/completions"
    reply_parts: list[str] = []
    sql: Optional[str] = None

    try:
        async with get_http_client().stream(
            "POST", url, json=body, timeout=_STREAM_TIMEOUT
        ) as resp:
            if resp.status_code >= 400:
                text = await resp.aread()
                msg = text.decode(errors="replace")[:800]
                yield _sse("error", {"message": f"NanobaseAI BI engine HTTP {resp.status_code}: {msg}"}).encode()
                return

            yield _sse("status", {"phase": "generating_sql"}).encode()
            buffer = ""
            async for chunk in resp.aiter_text():
                buffer += chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if not payload or payload == "[DONE]":
                        continue
                    try:
                        obj = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    content = ""
                    choices = obj.get("choices") or []
                    if choices:
                        msg_obj = choices[0].get("message") or choices[0].get("delta") or {}
                        content = str(msg_obj.get("content") or "")
                    if content:
                        reply_parts.append(content)
                        yield _sse("token", {"t": content}).encode()
                    if "```sql" in content.lower() or content.strip().upper().startswith("SELECT"):
                        sql = (sql or "") + content

        reply = "".join(reply_parts).strip() or "No response from NanobaseAI BI engine."
        result = _empty_chat_result(session_id, reply, sql=sql)
        yield _sse("status", {"phase": "finalizing"}).encode()
        yield _sse("done", result).encode()
    except httpx.HTTPError as e:
        yield _sse("error", {"message": f"NanobaseAI BI engine unreachable: {e}"}).encode()
    except Exception as e:
        yield _sse("error", {"message": str(e)}).encode()


@app.post("/api/v1/bi/chat/stream")
async def chat_stream(request: Request) -> StreamingResponse:
    body = await request.json()
    message = str(body.get("message") or "").strip()
    session_id = str(body.get("session_id") or uuid.uuid4())
    db_name = _active_db_id()
    if not db_name:
        return {"ok": False, "error": "no active datasource"}
    if not message:

        async def _err() -> AsyncIterator[bytes]:
            yield _sse("error", {"message": "empty message"}).encode()

        return StreamingResponse(_err(), media_type="text/event-stream")

    return StreamingResponse(
        _stream_dbgpt_chat(message, session_id, db_name),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/v1/bi/chat")
async def chat(request: Request) -> JSONResponse:
    body = await request.json()
    message = str(body.get("message") or "").strip()
    session_id = str(body.get("session_id") or uuid.uuid4())
    reply_parts: list[str] = []
    async for chunk in _stream_dbgpt_chat(message, session_id, _active_db_id()):
        text = chunk.decode()
        if "event: token" in text:
            try:
                data_line = [ln for ln in text.split("\n") if ln.startswith("data:")][0]
                reply_parts.append(json.loads(data_line[5:].strip()).get("t", ""))
            except Exception:
                pass
        if "event: done" in text:
            try:
                data_line = [ln for ln in text.split("\n") if ln.startswith("data:")][0]
                return JSONResponse(json.loads(data_line[5:].strip()))
            except Exception:
                break
        if "event: error" in text:
            try:
                data_line = [ln for ln in text.split("\n") if ln.startswith("data:")][0]
                return JSONResponse(json.loads(data_line[5:].strip()), status_code=502)
            except Exception:
                return JSONResponse({"message": "chat failed"}, status_code=502)
    return JSONResponse(_empty_chat_result(session_id, "".join(reply_parts) or "Empty reply"))


@app.api_route("/api/v1/bi/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def bi_stub(full_path: str, request: Request) -> JSONResponse:
    """Graceful degradation for remaining BI SaaS routes not in DB-GPT."""
    if request.method == "GET":
        return JSONResponse([])
    return JSONResponse({"ok": True, "engine": "nanobaseai-bi", "limited": True, "path": full_path})


def main() -> None:
    import uvicorn

    uvicorn.run("bridge.app:app", host=os.environ.get("BRIDGE_HOST", "0.0.0.0"), port=BRIDGE_PORT, reload=False)


if __name__ == "__main__":
    main()
