"""Faz 6/7: NL → (verified SQL cache | LLM) → Query Gateway execute → EXPLAIN.

DB-GPT chat_with_db_execute is NOT used for customer SQL execution.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, AsyncIterator, Optional

import httpx
from sqlalchemy.engine import Engine

QG_BASE = os.environ.get("QUERY_GATEWAY_BASE", "http://127.0.0.1:8792").rstrip("/")
LLM_BASE = os.environ.get("OPENAI_API_BASE", "http://127.0.0.1:8010/v1").rstrip("/")
LLM_KEY = os.environ.get("OPENAI_API_KEY", "nanobase-local")
LLM_MODEL = os.environ.get("LLM_MODEL_NAME", "nanobase-qwen36-35b-a3b-mtp")
SECRETS = Path(os.environ.get("SECRETS_ROOT", "/data/nanobaseai/bi/secrets"))

SCHEMA_HINT_REPORTING = """
Tables (PostgreSQL, search_path public/analytics):
- customers(customer_id, customer_name, country, segment, created_at)
- products(product_id, sku, product_name, category, unit_price)
- orders(order_id, customer_id, order_date, status, currency)
- order_items(order_item_id, order_id, product_id, quantity, unit_price)
- v_order_revenue(order_id, order_date, status, currency, customer_name, country, segment, revenue)
Only SELECT/WITH. Prefer LIMIT 50. Dialect: PostgreSQL.
"""

_HINTS_CACHE: dict[str, str] | None = None


def _schema_hint_for(datasource_id: str) -> str:
    global _HINTS_CACHE
    if datasource_id in ("bi_reporting", "", "default"):
        return SCHEMA_HINT_REPORTING
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


def _extract_sql(text: str) -> Optional[str]:
    m = re.search(r"```sql\s*(.*?)```", text, re.I | re.S)
    if m:
        return m.group(1).strip().rstrip(";")
    m = re.search(r'"sql"\s*:\s*"((?:\\.|[^"\\])*)"', text)
    if m:
        return bytes(m.group(1), "utf-8").decode("unicode_escape").strip().rstrip(";")
    m = re.search(r"(SELECT\b[\s\S]{8,2000})", text, re.I)
    if m:
        return m.group(1).strip().rstrip(";")
    return None


async def _generate_sql(question: str, datasource_id: str) -> str:
    hint = _schema_hint_for(datasource_id)
    prompt = (
        "You are a Text-to-SQL engine. Return ONLY a JSON object with keys "
        'thoughts, sql, display_type. sql must be a single PostgreSQL SELECT.\n'
        f"Schema:\n{hint}\n"
        f"Question: {question}\n"
    )
    body = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "Output valid JSON only. No markdown outside JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 1024,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {LLM_KEY}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.post(f"{LLM_BASE}/chat/completions", headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
    content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
    return str(content)


async def stream_chat_via_gateway(
    message: str,
    session_id: str,
    datasource_id: str,
    *,
    with_explain: bool = True,
    meta_engine: Engine | None = None,
) -> AsyncIterator[bytes]:
    yield _sse("status", {"phase": "preparing", "engine": "gateway"}).encode()

    sql: Optional[str] = None
    sql_source = "llm"
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
        yield _sse("status", {"phase": "generating_sql", "datasource_id": datasource_id}).encode()
        try:
            raw = await _generate_sql(message, datasource_id)
        except Exception as e:
            yield _sse("error", {"message": f"SQL generation failed: {e}"}).encode()
            return
        yield _sse("token", {"t": raw[:500]}).encode()
        sql = _extract_sql(raw)
        if not sql:
            yield _sse("error", {"message": "No SQL generated", "raw": raw[:800]}).encode()
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
        yield _sse("status", {"phase": "executing", "sql": safe_sql}).encode()
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

        explain_text = None
        if with_explain:
            yield _sse("status", {"phase": "explain"}).encode()
            xr = await client.post(
                f"{QG_BASE}/api/v1/query/execute",
                json={"datasource_id": datasource_id, "sql": safe_sql, "explain": True},
            )
            if xr.status_code == 200:
                xj = xr.json()
                explain_text = "\n".join(
                    str(list(row.values())[0]) for row in (xj.get("rows") or []) if row
                )

    rows = ej.get("rows") or []
    cols = ej.get("columns") or []
    reply = (
        f"SQL:\n{safe_sql}\n\n"
        f"Rows: {ej.get('row_count', 0)}"
        + (f"\n\nEXPLAIN:\n{explain_text}" if explain_text else "")
    )
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
        "sql_source": sql_source,
        "verified_sql_id": (verified_meta or {}).get("id"),
        "datasource_id": datasource_id,
        "explain": explain_text,
    }
    yield _sse("status", {"phase": "finalizing"}).encode()
    yield _sse("done", result).encode()
