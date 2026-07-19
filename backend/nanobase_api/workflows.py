"""Controlled workflows: SQL plan and result explain (no customer DB execute).

Contracts match the locked architecture:
  - nanobase-nl2sql-plan  → SQL only
  - nanobase-result-explain → natural-language answer only

DB-GPT chat_with_db_execute is never used here.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

import httpx

LLM_BASE = os.environ.get("OPENAI_API_BASE", "http://127.0.0.1:8010/v1").rstrip("/")
LLM_KEY = os.environ.get("OPENAI_API_KEY", "nanobase-local")
LLM_MODEL = os.environ.get("LLM_MODEL_NAME", "nanobase-qwen36-35b-a3b-mtp")

DEFAULT_SCHEMA_HINT = """
Tables (PostgreSQL):
- customers(customer_id, customer_name, country, segment, created_at)
- customer_addresses(address_id, customer_id, city, is_primary)
- products(product_id, sku, product_name, category, unit_price)
- companies(company_id, company_name), branches(branch_id, company_id, city)
- sales_orders(order_id, customer_id, branch_id, order_date, status, currency)
- sales_order_items(item_id, order_id, product_id, quantity, unit_price)
- invoices(invoice_id, order_id, invoice_date, due_date, currency, gross_amount, remaining_amount, status)
- payments(payment_id, invoice_id, payment_date, amount, currency)
- currency_rates(rate_date, from_currency, to_currency, rate)
- returns(return_id, order_id, product_id, quantity, return_date)
- orders / order_items / v_order_revenue (legacy aliases)
Only SELECT/WITH. Prefer LIMIT 50.
"""


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}
    return {}


async def _chat(system: str, user: str, *, max_tokens: int = 1024) -> str:
    body = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {LLM_KEY}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.post(f"{LLM_BASE}/chat/completions", headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
    return str((((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or "")


async def nl2sql_plan(
    *,
    question: str,
    conversation_context: list[dict[str, Any]] | None = None,
    datasource_context: dict[str, Any] | None = None,
    allowed_schemas: list[str] | None = None,
    allowed_tables: list[str] | None = None,
    schema_hint: str | None = None,
) -> dict[str, Any]:
    """Produce SQL plan JSON. Does NOT execute against any database."""
    hint = schema_hint or DEFAULT_SCHEMA_HINT
    if allowed_tables:
        hint += "\nAllowed tables only: " + ", ".join(allowed_tables)
    if allowed_schemas:
        hint += "\nAllowed schemas: " + ", ".join(allowed_schemas)
    ctx = ""
    if conversation_context:
        ctx = "Conversation context:\n" + json.dumps(conversation_context[-6:], ensure_ascii=False) + "\n"
    ds = ""
    if datasource_context:
        ds = "Datasource context:\n" + json.dumps(datasource_context, ensure_ascii=False) + "\n"

    user = (
        f"{ctx}{ds}Schema:\n{hint}\n\n"
        f"Question: {question}\n\n"
        "Return ONLY JSON with keys: sql, dialect, tables, columns, assumptions, confidence.\n"
        "sql must be a single PostgreSQL SELECT/WITH. dialect usually postgresql.\n"
        "confidence is 0..1."
    )
    raw = await _chat(
        "You are nanobase-nl2sql-plan. Output valid JSON only. Never execute SQL.",
        user,
    )
    parsed = _extract_json(raw)
    sql = str(parsed.get("sql") or "").strip().rstrip(";")
    if not sql:
        # fallback extract
        m = re.search(r"(SELECT\b[\s\S]{8,4000})", raw, re.I)
        sql = m.group(1).strip().rstrip(";") if m else ""
    tables = parsed.get("tables") or []
    columns = parsed.get("columns") or []
    if not isinstance(tables, list):
        tables = []
    if not isinstance(columns, list):
        columns = []
    try:
        confidence = float(parsed.get("confidence") if parsed.get("confidence") is not None else 0.5)
    except Exception:
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))
    return {
        "workflow": "nanobase-nl2sql-plan",
        "sql": sql,
        "dialect": str(parsed.get("dialect") or "postgresql"),
        "tables": [str(t) for t in tables],
        "columns": [str(c) for c in columns],
        "assumptions": parsed.get("assumptions") if isinstance(parsed.get("assumptions"), list) else [],
        "confidence": confidence,
        "executes": False,
    }


async def result_explain(
    *,
    question: str,
    executed_sql: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    truncated: bool = False,
) -> dict[str, Any]:
    """Explain already-executed results. Does NOT run SQL."""
    sample = rows[:20]
    user = (
        f"Question: {question}\n"
        f"Executed SQL:\n{executed_sql}\n"
        f"Columns: {columns}\n"
        f"Rows (sample): {json.dumps(sample, ensure_ascii=False, default=str)}\n"
        f"Truncated: {truncated}\n\n"
        "Return ONLY JSON with keys: answer, insights, warnings.\n"
        "answer must be Turkish business language."
    )
    raw = await _chat(
        "You are nanobase-result-explain. Output valid JSON only. Never invent SQL execution.",
        user,
        max_tokens=800,
    )
    parsed = _extract_json(raw)
    answer = str(parsed.get("answer") or "").strip()
    if not answer:
        # deterministic fallback
        if rows and columns:
            first = rows[0]
            vals = ", ".join(f"{k}={first.get(k)}" for k in columns[:4])
            answer = f"Sorgu {len(rows)} satır döndürdü. İlk satır: {vals}."
        else:
            answer = "Sorgu sonuç döndürmedi."
    insights = parsed.get("insights") if isinstance(parsed.get("insights"), list) else []
    warnings = parsed.get("warnings") if isinstance(parsed.get("warnings"), list) else []
    if truncated and "truncated" not in " ".join(str(w).lower() for w in warnings):
        warnings = [*warnings, "Sonuç satır limiti nedeniyle kesilmiş olabilir."]
    return {
        "workflow": "nanobase-result-explain",
        "answer": answer,
        "insights": insights,
        "warnings": warnings,
        "executes": False,
    }
