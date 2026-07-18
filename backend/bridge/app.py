"""Nanobase BI ↔ DB-GPT bridge.

Listens on :8787 (Vite/nginx default). Speaks the FE `/api/v1/bi/*` (+ portal stub)
contract and calls DB-GPT on :5670.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

DBGPT_BASE = os.environ.get("DBGPT_BASE", "http://127.0.0.1:5670").rstrip("/")
BRIDGE_PORT = int(os.environ.get("BRIDGE_PORT", "8787"))
SOURCES_FILE = Path(
    os.environ.get(
        "BI_SOURCES_FILE",
        str(Path(__file__).resolve().parents[2] / "configs" / "sources" / "local" / "connection.local.json"),
    )
)
ACTIVE_DB = {"id": "erp"}

app = FastAPI(title="Nanobase BI → DB-GPT bridge", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("PORTAL_CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load_sources() -> dict[str, Any]:
    if SOURCES_FILE.is_file():
        return json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    return {"active_id": "erp", "sources": {}}


def _sources_list_payload() -> dict[str, Any]:
    raw = _load_sources()
    sources_map = raw.get("sources") or {}
    active = raw.get("active_id") or ACTIVE_DB["id"]
    ACTIVE_DB["id"] = str(active)
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


async def _dbgpt_json(
    method: str,
    path: str,
    *,
    json_body: Any = None,
    timeout: float = 120.0,
) -> Any:
    url = f"{DBGPT_BASE}{path}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.request(method, url, json=json_body)
        resp.raise_for_status()
        if not resp.content:
            return None
        return resp.json()


# ---------------------------------------------------------------------------
# Health / portal stubs (FE bootstrap)
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, Any]:
    dbgpt_ok = False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{DBGPT_BASE}/")
            dbgpt_ok = r.status_code < 500
    except Exception:
        dbgpt_ok = False
    return {"ok": True, "bridge": True, "dbgpt": dbgpt_ok, "dbgpt_base": DBGPT_BASE}


@app.get("/api/v1/bi/health")
@app.get("/api/v1/bi/status")
async def bi_status() -> dict[str, Any]:
    h = await health()
    return {
        "ok": True,
        "status": "ready" if h["dbgpt"] else "degraded",
        "engine": "dbgpt",
        "dbgpt": h["dbgpt"],
        "active_source": ACTIVE_DB["id"],
    }


@app.get("/api/v1/portal/bootstrap")
async def portal_bootstrap() -> dict[str, Any]:
    return {
        "portal_auto_login": True,
        "auth_mode": "bearer",
        "modules": ["bi"],
        "features": {"bi": True},
        "runtime_config": {"api_base": "", "cookie_auth": False},
    }


@app.get("/api/v1/portal/runtime-config")
async def runtime_config() -> dict[str, Any]:
    return {"api_base": "", "cookie_auth": False, "modules": ["bi"]}


@app.post("/api/v1/portal/auth/login")
async def portal_login(request: Request) -> dict[str, Any]:
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    user = str(body.get("username") or body.get("email") or "bi-local")
    return {
        "token": "dbgpt-bridge-local",
        "access_token": "dbgpt-bridge-local",
        "user": {"id": "local", "username": user, "role": "admin", "roles": ["admin"]},
        "session": {"id": "local", "token": "dbgpt-bridge-local"},
    }


@app.get("/api/v1/portal/auth/me")
@app.get("/api/v1/portal/me")
async def portal_me() -> dict[str, Any]:
    return {"id": "local", "username": "bi-local", "role": "admin", "roles": ["admin"]}


@app.get("/api/v1/llm/status")
async def llm_status() -> dict[str, Any]:
    return {"busy": False, "model": os.environ.get("LLM_MODEL_NAME", "nanobase-qwen36-35b-a3b-mtp")}


@app.post("/api/v1/llm/cancel")
async def llm_cancel() -> dict[str, Any]:
    return {"ok": True}


# ---------------------------------------------------------------------------
# Sources / connection → DB-GPT datasources
# ---------------------------------------------------------------------------


@app.get("/api/v1/bi/sources")
async def sources_list() -> dict[str, Any]:
    return _sources_list_payload()


@app.post("/api/v1/bi/sources/{source_id}/activate")
async def sources_activate(source_id: str) -> dict[str, Any]:
    ACTIVE_DB["id"] = source_id
    raw = _load_sources()
    raw["active_id"] = source_id
    if SOURCES_FILE.parent.is_dir():
        try:
            SOURCES_FILE.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        except OSError:
            pass
    return {"ok": True, "active_id": source_id}


@app.get("/api/v1/bi/connection")
async def connection_get() -> dict[str, Any]:
    payload = _sources_list_payload()
    active = payload["active_id"]
    for s in payload["sources"]:
        if s["id"] == active:
            return s
    return payload["sources"][0] if payload["sources"] else {}


@app.post("/api/v1/bi/connection/test")
async def connection_test() -> dict[str, Any]:
    return {"ok": True, "message": "OK (bridge)", "dialect": "postgresql"}


@app.get("/api/v1/bi/schema")
async def schema_get() -> dict[str, Any]:
    return {"tables": [], "dialect": "postgresql", "source_id": ACTIVE_DB["id"]}


@app.post("/api/v1/bi/schema/refresh")
async def schema_refresh() -> dict[str, Any]:
    return {"ok": True, "tables": 0}


@app.get("/api/v1/bi/templates")
async def templates() -> list[Any]:
    return []


@app.get("/api/v1/bi/chat/sessions")
async def chat_sessions() -> list[Any]:
    try:
        data = await _dbgpt_json("POST", "/api/v1/serve/conversation/list", json_body={})
        if isinstance(data, dict) and "data" in data:
            return data["data"] or []
        return data if isinstance(data, list) else []
    except Exception:
        return []


@app.get("/api/v1/bi/chat/{session_id}")
async def chat_history(session_id: str) -> dict[str, Any]:
    return {"session_id": session_id, "messages": []}


@app.delete("/api/v1/bi/chat/{session_id}")
async def chat_delete(session_id: str) -> dict[str, Any]:
    return {"ok": True}


# ---------------------------------------------------------------------------
# Chat → DB-GPT chat_with_db_execute
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
        "model_name": os.environ.get("LLM_MODEL_NAME", "nanobase-qwen36-35b-a3b-mtp"),
        "incremental": True,
        "temperature": 0.2,
        "max_new_tokens": 2048,
    }

    url = f"{DBGPT_BASE}/api/v1/chat/completions"
    reply_parts: list[str] = []
    sql: Optional[str] = None

    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", url, json=body) as resp:
                if resp.status_code >= 400:
                    text = await resp.aread()
                    msg = text.decode(errors="replace")[:800]
                    yield _sse("error", {"message": f"DB-GPT HTTP {resp.status_code}: {msg}"}).encode()
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
                        # Best-effort SQL sniff
                        if "```sql" in content.lower() or content.strip().upper().startswith("SELECT"):
                            sql = (sql or "") + content

        reply = "".join(reply_parts).strip() or "No response from DB-GPT."
        result = _empty_chat_result(session_id, reply, sql=sql)
        yield _sse("status", {"phase": "finalizing"}).encode()
        yield _sse("done", result).encode()
    except httpx.HTTPError as e:
        yield _sse("error", {"message": f"DB-GPT unreachable at {DBGPT_BASE}: {e}"}).encode()
    except Exception as e:
        yield _sse("error", {"message": str(e)}).encode()


@app.post("/api/v1/bi/chat/stream")
async def chat_stream(request: Request) -> StreamingResponse:
    body = await request.json()
    message = str(body.get("message") or "").strip()
    session_id = str(body.get("session_id") or uuid.uuid4())
    db_name = ACTIVE_DB["id"] or "erp"
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
    async for chunk in _stream_dbgpt_chat(message, session_id, ACTIVE_DB["id"]):
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


# Catch-all stub so unused BI pages degrade gracefully
@app.api_route("/api/v1/bi/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def bi_stub(full_path: str, request: Request) -> JSONResponse:
    if request.method == "GET":
        return JSONResponse([])
    return JSONResponse({"ok": True, "stub": True, "path": full_path})


def main() -> None:
    import uvicorn

    uvicorn.run(
        "bridge.app:app",
        host=os.environ.get("BRIDGE_HOST", "0.0.0.0"),
        port=BRIDGE_PORT,
        reload=False,
    )


if __name__ == "__main__":
    main()
