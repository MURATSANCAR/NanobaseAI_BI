"""Faz 6/7/3+: NL → plan → (optional) Query Gateway execute → explain.

DB-GPT chat_with_db_execute is NOT used for customer SQL execution.
Supports NANOBASE_TEXT2SQL_EXECUTION_MODE=QUERY_GATEWAY|PLAN_ONLY.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Optional

import httpx
from sqlalchemy.engine import Engine

from nanobase_api.config import ExecutionMode, get_settings
from nanobase_api.infrastructure.text2sql_adapter import WorkflowTextToSqlAdapter
from nanobase_api.workflows import DEFAULT_SCHEMA_HINT

QG_BASE = os.environ.get("QUERY_GATEWAY_BASE", "http://127.0.0.1:8792").rstrip("/")
SECRETS = Path(os.environ.get("SECRETS_ROOT", "/data/nanobaseai/bi/secrets"))

_HINTS_CACHE: dict[str, str] | None = None
_engine_adapter = WorkflowTextToSqlAdapter()


def _schema_hint_for(datasource_id: str) -> str:
    global _HINTS_CACHE
    if datasource_id in ("bi_reporting", "", "default"):
        return DEFAULT_SCHEMA_HINT
    if _HINTS_CACHE is None:
        _HINTS_CACHE = {}
        hints_path = SECRETS / "neon-schema-hints.json"
        if hints_path.is_file():
            try:
                raw = json.loads(hints_path.read_text(encoding="utf-8"))
                for sid, tables in (raw or {}).items():
                    lines = [f"Tables for datasource '{sid}' (PostgreSQL):"]
                    for tname, cols in list((tables or {}).items())[:25]:
                        col_s = ", ".join(str(c).split(":")[0] for c in (cols or [])[:10])
                        lines.append(f"- {tname}({col_s})")
                    lines.append("Only SELECT/WITH. Prefer LIMIT 50. Dialect: PostgreSQL.")
                    _HINTS_CACHE[str(sid)] = "\n".join(lines)
            except Exception:
                pass
    return _HINTS_CACHE.get(datasource_id) or (
        f"PostgreSQL datasource '{datasource_id}'. Only SELECT/WITH. Prefer LIMIT 50."
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _persist_conversation(
    meta_engine: Engine | None,
    *,
    tenant_id: str,
    session_id: str,
    message: str,
    datasource_id: str,
    reply: str | None = None,
    sql: str | None = None,
    execution_mode: str,
    executed: bool,
) -> None:
    if meta_engine is None:
        return
    try:
        from nanobase_api.infrastructure.conversation_repo import ConversationRepository

        repo = ConversationRepository(meta_engine)
        repo.ensure_session(
            tenant_id=tenant_id,
            conversation_id=session_id,
            title=message[:80],
            datasource_id=datasource_id,
        )
        if reply is None:
            repo.add_message(
                tenant_id=tenant_id,
                conversation_id=session_id,
                role="user",
                content=message,
                datasource_id=datasource_id,
            )
        else:
            repo.add_message(
                tenant_id=tenant_id,
                conversation_id=session_id,
                role="assistant",
                content=reply,
                datasource_id=datasource_id,
                sql_text=sql,
            )
            repo.save_plan(
                tenant_id=tenant_id,
                conversation_id=session_id,
                datasource_id=datasource_id,
                question=message,
                sql_text=sql,
                dialect="postgresql",
                execution_mode=execution_mode,
                executed=executed,
            )
    except Exception:
        pass


async def stream_chat_via_gateway(
    message: str,
    session_id: str,
    datasource_id: str,
    *,
    with_explain: bool = True,
    meta_engine: Engine | None = None,
    tenant_id: str = "default",
    user_id: str | None = None,
) -> AsyncIterator[bytes]:
    settings = get_settings()
    mode = settings.execution_mode
    execution_id = str(uuid.uuid4())

    yield _sse(
        "status",
        {
            "type": "STATUS",
            "phase": "preparing",
            "engine": "nanobase_workflows",
            "execution_id": execution_id,
            "execution_mode": mode.value,
        },
    ).encode()

    _persist_conversation(
        meta_engine,
        tenant_id=tenant_id,
        session_id=session_id,
        message=message,
        datasource_id=datasource_id,
        execution_mode=mode.value,
        executed=False,
    )

    sql: Optional[str] = None
    sql_source = "nl2sql_plan"
    plan: dict[str, Any] | None = None
    verified_meta: dict[str, Any] | None = None
    retrieval_meta: dict[str, Any] = {}

    if meta_engine is not None:
        try:
            from nanobase_api.semantic import lookup_verified_sql

            verified_meta = lookup_verified_sql(meta_engine, message, datasource_id)
            if verified_meta and verified_meta.get("sql"):
                sql = str(verified_meta["sql"])
                sql_source = "verified_sql"
                yield _sse(
                    "status",
                    {
                        "phase": "verified_cache_hit",
                        "verified_id": verified_meta.get("id"),
                        "sql": sql,
                    },
                ).encode()
        except Exception as e:
            yield _sse("status", {"phase": "verified_lookup_skip", "detail": str(e)[:200]}).encode()

    if not sql:
        yield _sse(
            "status",
            {"phase": "schema_retrieval", "datasource_id": datasource_id},
        ).encode()
        retrieved = ""
        try:
            from nanobase_api.schema_retrieve import retrieve_schema_context

            retrieval_meta = await retrieve_schema_context(message, datasource_id)
            retrieved = str(retrieval_meta.get("hint_extra") or "")
            tables = retrieval_meta.get("tables") or []
            yield _sse(
                "status",
                {
                    "phase": "schema_retrieval_done",
                    "ok": retrieval_meta.get("ok"),
                    "collection": retrieval_meta.get("collection"),
                    "tables": tables,
                    "hit_count": len(retrieval_meta.get("hits") or []),
                },
            ).encode()
            yield _sse(
                "schema_context",
                {"type": "SCHEMA_CONTEXT", "payload": {"tables": tables}},
            ).encode()
        except Exception as e:
            yield _sse("status", {"phase": "schema_retrieval_skip", "detail": str(e)[:200]}).encode()

        yield _sse(
            "status",
            {"phase": "nl2sql_plan", "workflow": "nanobase-nl2sql-plan", "datasource_id": datasource_id},
        ).encode()
        try:
            plan = await _engine_adapter.generate_sql_plan(
                question=message,
                datasource_id=datasource_id,
                schema_hint=_schema_hint_for(datasource_id),
                retrieved_schema=retrieved or None,
            )
        except Exception as e:
            yield _sse("error", {"type": "ERROR", "message": f"nl2sql-plan failed: {e}"}).encode()
            return
        sql = str(plan.get("sql") or "").strip()
        plan["retrieval"] = {
            "collection": retrieval_meta.get("collection"),
            "tables": retrieval_meta.get("tables") or [],
            "hit_count": len(retrieval_meta.get("hits") or []),
        }
        yield _sse("status", {"phase": "plan_ready", "plan": plan}).encode()
        yield _sse(
            "sql_generated",
            {"type": "SQL_GENERATED", "payload": {"sql": sql, "sql_source": sql_source}},
        ).encode()
        if not sql:
            yield _sse("error", {"message": "No SQL from nl2sql-plan", "plan": plan}).encode()
            return

    # PLAN_ONLY: skip gateway execute
    if mode == ExecutionMode.PLAN_ONLY:
        reply = (
            "SQL planı üretildi. Production execution kapalı "
            f"(NANOBASE_TEXT2SQL_EXECUTION_MODE={mode.value}).\n\nSQL:\n{sql}"
        )
        yield _sse(
            "answer_delta",
            {"type": "ANSWER_DELTA", "payload": {"text": reply}},
        ).encode()
        result = {
            "session_id": session_id,
            "reply": reply,
            "intent": "query",
            "sql": sql,
            "sql_error": None,
            "query_result": {"columns": [], "rows": []},
            "widgets": [],
            "answer_blocks": [{"type": "text", "text": reply}],
            "engine": "nanobase_plan_only",
            "workflows": {"plan": plan, "explain": None},
            "sql_source": sql_source,
            "verified_sql_id": (verified_meta or {}).get("id"),
            "datasource_id": datasource_id,
            "execution_mode": mode.value,
            "execution_id": execution_id,
            "insights": [],
            "warnings": ["EXECUTION_DISABLED"],
        }
        try:
            from nanobase_api.infrastructure.audit_repo import AuditRepository

            if meta_engine is not None:
                AuditRepository(meta_engine).record(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    action="SQL_EXECUTION_BLOCKED",
                    ok=True,
                    session_id=session_id,
                    extra={"execution_mode": mode.value, "datasource_id": datasource_id},
                )
        except Exception:
            pass
        _persist_conversation(
            meta_engine,
            tenant_id=tenant_id,
            session_id=session_id,
            message=message,
            datasource_id=datasource_id,
            reply=reply,
            sql=sql,
            execution_mode=mode.value,
            executed=False,
        )
        yield _sse("completed", {"type": "COMPLETED", "payload": {"durationMs": None}}).encode()
        yield _sse("done", result).encode()
        return

    yield _sse("status", {"phase": "validating", "sql": sql, "sql_source": sql_source}).encode()
    async with httpx.AsyncClient(timeout=60.0) as client:
        vr = await client.post(
            f"{QG_BASE}/api/v1/query/validate",
            json={"datasource_id": datasource_id, "sql": sql},
        )
        vj = vr.json()
        if vr.status_code >= 400 or not vj.get("ok"):
            yield _sse(
                "error",
                {"message": vj.get("error") or vj.get("detail") or "SQL rejected by gateway", "sql": sql},
            ).encode()
            return

        safe_sql = vj.get("sql") or sql
        yield _sse("status", {"phase": "executing", "sql": safe_sql, "via": "query_gateway"}).encode()
        er = await client.post(
            f"{QG_BASE}/api/v1/query/execute",
            json={"datasource_id": datasource_id, "sql": safe_sql},
        )
        ej = er.json()
        if er.status_code >= 400 or not ej.get("ok"):
            yield _sse(
                "error",
                {"message": ej.get("detail") or ej.get("error") or "execute failed", "sql": safe_sql},
            ).encode()
            return

        explain_plan_text = None
        if with_explain:
            yield _sse("status", {"phase": "gateway_explain"}).encode()
            xr = await client.post(
                f"{QG_BASE}/api/v1/query/execute",
                json={"datasource_id": datasource_id, "sql": safe_sql, "explain": True},
            )
            if xr.status_code == 200:
                xj = xr.json()
                explain_plan_text = "\n".join(
                    str(list(row.values())[0]) for row in (xj.get("rows") or []) if row
                )

    rows = ej.get("rows") or []
    cols = ej.get("columns") or []

    yield _sse(
        "status", {"phase": "result_explain", "workflow": "nanobase-result-explain"}
    ).encode()
    try:
        explained = await _engine_adapter.explain_result(
            question=message,
            executed_sql=safe_sql,
            columns=cols,
            rows=rows,
            truncated=bool(ej.get("truncated")),
        )
    except Exception as e:
        explained = {
            "workflow": "nanobase-result-explain",
            "answer": f"Sonuç alındı ({len(rows)} satır). Açıklama üretilemedi: {e}",
            "insights": [],
            "warnings": ["explain_failed"],
        }

    reply = explained.get("answer") or ""
    if explain_plan_text:
        reply = f"{reply}\n\nSQL:\n{safe_sql}\n\nEXPLAIN:\n{explain_plan_text}"
    else:
        reply = f"{reply}\n\nSQL:\n{safe_sql}"

    yield _sse(
        "answer_delta",
        {"type": "ANSWER_DELTA", "payload": {"text": reply[:500]}},
    ).encode()

    result = {
        "session_id": session_id,
        "reply": reply,
        "intent": "query",
        "sql": safe_sql,
        "sql_error": None,
        "query_result": {"columns": cols, "rows": rows},
        "widgets": [],
        "answer_blocks": [
            {"type": "text", "text": reply},
            {"type": "table", "columns": cols, "rows": rows},
        ],
        "engine": "nanobase_gateway",
        "workflows": {
            "plan": plan,
            "explain": explained,
        },
        "sql_source": sql_source,
        "verified_sql_id": (verified_meta or {}).get("id"),
        "datasource_id": datasource_id,
        "explain": explain_plan_text,
        "insights": explained.get("insights") or [],
        "warnings": explained.get("warnings") or [],
        "execution_mode": mode.value,
        "execution_id": execution_id,
    }
    _persist_conversation(
        meta_engine,
        tenant_id=tenant_id,
        session_id=session_id,
        message=message,
        datasource_id=datasource_id,
        reply=reply,
        sql=safe_sql,
        execution_mode=mode.value,
        executed=True,
    )
    try:
        from nanobase_api.infrastructure.audit_repo import AuditRepository

        if meta_engine is not None:
            AuditRepository(meta_engine).record(
                tenant_id=tenant_id,
                user_id=user_id,
                action="QUERY_COMPLETED",
                ok=True,
                session_id=session_id,
                extra={"datasource_id": datasource_id, "execution_id": execution_id},
            )
    except Exception:
        pass

    yield _sse("status", {"phase": "finalizing"}).encode()
    yield _sse("completed", {"type": "COMPLETED", "payload": {}}).encode()
    yield _sse("done", result).encode()
