"""Faz 6/7+: NL → plan workflow → Query Gateway execute → explain workflow.

DB-GPT chat_with_db_execute is NOT used for customer SQL execution.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, AsyncIterator, Optional

import httpx
from sqlalchemy.engine import Engine

from nanobase_api.workflows import DEFAULT_SCHEMA_HINT, nl2sql_plan, result_explain

QG_BASE = os.environ.get("QUERY_GATEWAY_BASE", "http://127.0.0.1:8792").rstrip("/")
SECRETS = Path(os.environ.get("SECRETS_ROOT", "/data/nanobaseai/bi/secrets"))

_HINTS_CACHE: dict[str, str] | None = None


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


async def stream_chat_via_gateway(
    message: str,
    session_id: str,
    datasource_id: str,
    *,
    with_explain: bool = True,
    meta_engine: Engine | None = None,
) -> AsyncIterator[bytes]:
    yield _sse("status", {"phase": "preparing", "engine": "nanobase_workflows"}).encode()

    sql: Optional[str] = None
    sql_source = "nl2sql_plan"
    plan: dict[str, Any] | None = None
    verified_meta: dict[str, Any] | None = None

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
            {"phase": "nl2sql_plan", "workflow": "nanobase-nl2sql-plan", "datasource_id": datasource_id},
        ).encode()
        try:
            plan = await nl2sql_plan(
                question=message,
                schema_hint=_schema_hint_for(datasource_id),
                datasource_context={"datasource_id": datasource_id},
            )
        except Exception as e:
            yield _sse("error", {"message": f"nl2sql-plan failed: {e}"}).encode()
            return
        sql = str(plan.get("sql") or "").strip()
        yield _sse("status", {"phase": "plan_ready", "plan": plan}).encode()
        if not sql:
            yield _sse("error", {"message": "No SQL from nl2sql-plan", "plan": plan}).encode()
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
        explained = await result_explain(
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
    }
    yield _sse("status", {"phase": "finalizing"}).encode()
    yield _sse("done", result).encode()
