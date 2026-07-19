"""Faz 6/7/3+: NL → plan → (optional) Query Gateway execute → explain.

DB-GPT chat_with_db_execute is NOT used for customer SQL execution.
Supports NANOBASE_TEXT2SQL_EXECUTION_MODE=QUERY_GATEWAY|PLAN_ONLY.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Optional

import httpx
from sqlalchemy.engine import Engine

from nanobase_api.config import ExecutionMode, get_settings
from nanobase_api.infrastructure.text2sql_adapter import WorkflowTextToSqlAdapter
from nanobase_api.workflows import DEFAULT_SCHEMA_HINT
from nanobase_awel.contracts.errors import WorkflowError
from nanobase_awel.operators import model_queue as model_queue_mod

QG_BASE = os.environ.get("QUERY_GATEWAY_BASE", "http://127.0.0.1:8792").rstrip("/")
SECRETS = Path(os.environ.get("SECRETS_ROOT", "/data/nanobaseai/bi/secrets"))

_HINTS_CACHE: dict[str, str] | None = None
_engine_adapter = WorkflowTextToSqlAdapter()


def _schema_hint_for(datasource_id: str) -> str:
    global _HINTS_CACHE
    dialect = _dialect_for_datasource(datasource_id)
    if dialect == "oracle":
        return (
            f"Oracle datasource '{datasource_id}'. "
            "Only SELECT/WITH. Owner-qualify (NANOBASE_REPORTING.*). "
            "Use FETCH FIRST n ROWS ONLY. No LIMIT, ILIKE, hints, DB links, or PL/SQL."
        )
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


def _dialect_for_datasource(datasource_id: str) -> str:
    """Resolve dialect from Query Gateway registry / secrets maps."""
    sid = (datasource_id or "").lower()
    if "oracle" in sid:
        return "oracle"
    if "odata" in sid or "cds" in sid or "s4" in sid:
        return "odata"
    if "hana" in sid or sid.startswith("sap_"):
        # Prefer odata when both sap + odata; hana id usually contains hana
        if "hana" in sid:
            return "hana"
    # Probe secrets maps
    ora = SECRETS / "oracle-ro.datasources.json"
    if ora.is_file():
        try:
            raw = json.loads(ora.read_text(encoding="utf-8"))
            sources = raw.get("sources") or raw
            if datasource_id in sources:
                return "oracle"
        except Exception:
            pass
    sap = SECRETS / "sap-ro.datasources.json"
    if sap.is_file():
        try:
            raw = json.loads(sap.read_text(encoding="utf-8"))
            sources = raw.get("sources") or raw
            cfg = sources.get(datasource_id) or {}
            driver = str(cfg.get("driver") or cfg.get("databaseType") or "").lower()
            if driver in ("odata", "cds", "cds_odata", "sap_s4hana_odata") or "odata" in driver:
                return "odata"
            if driver in ("hana", "sap_hana", "hdb") or "hana" in driver:
                return "hana"
        except Exception:
            pass
    return "postgres"


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _await_llm_with_queue_sse(
    coro: Awaitable[Any],
    *,
    tenant_id: str,
    user_id: str | None,
    request_id: str,
    out: list[Any],
) -> AsyncIterator[bytes]:
    """Run an LLM-backed awaitable while streaming queue wait status to the client."""
    sink: asyncio.Queue = asyncio.Queue()
    tokens = (
        model_queue_mod.progress_sink.set(sink),
        model_queue_mod.tenant_ctx.set(tenant_id or "default"),
        model_queue_mod.user_ctx.set(user_id),
        model_queue_mod.request_ctx.set(request_id),
    )
    task = asyncio.create_task(coro)  # inherits contextvars (3.11+)
    try:
        while not task.done():
            try:
                st = await asyncio.wait_for(sink.get(), timeout=0.5)
                yield _sse(
                    "status",
                    {
                        "type": "STATUS",
                        "phase": st.get("phase") or "queued",
                        "position": st.get("position"),
                        "queue_depth": st.get("queue_depth"),
                        "message": st.get("message"),
                        "elapsed_sec": st.get("elapsed_sec"),
                    },
                ).encode()
            except asyncio.TimeoutError:
                continue
        while True:
            try:
                st = sink.get_nowait()
                yield _sse(
                    "status",
                    {
                        "type": "STATUS",
                        "phase": st.get("phase") or "queued",
                        "position": st.get("position"),
                        "queue_depth": st.get("queue_depth"),
                        "message": st.get("message"),
                        "elapsed_sec": st.get("elapsed_sec"),
                    },
                ).encode()
            except asyncio.QueueEmpty:
                break
        try:
            out.append(await task)
        except WorkflowError as e:
            yield _sse(
                "error",
                {
                    "type": "ERROR",
                    "code": e.code,
                    "message": e.message,
                    "retryable": e.retryable,
                },
            ).encode()
            out.append(None)
    finally:
        model_queue_mod.progress_sink.reset(tokens[0])
        model_queue_mod.tenant_ctx.reset(tokens[1])
        model_queue_mod.user_ctx.reset(tokens[2])
        model_queue_mod.request_ctx.reset(tokens[3])
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass


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
                dialect=_dialect_for_datasource(datasource_id),
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
    semantic_meta: dict[str, Any] = {}

    # Faz 7: logical metric compile (never run legacy physical verified SQL as source of truth)
    try:
        from nanobase_api.config import get_settings
        from nanobase_awel.retrieval.semantic import (
            retrieve_semantic_context,
            try_compile_resolved_metric,
        )

        settings = get_settings()
        if settings.semantic_catalog_enabled:
            semantic_meta = await retrieve_semantic_context(
                message, tenant_id=tenant_id, datasource_id=datasource_id
            )
            metric_code = semantic_meta.get("resolvedMetric")
            flag_ok = True
            if metric_code and settings.semantic_metric_flags:
                # If any metric flags set, require explicit enable for this metric
                flag_ok = settings.semantic_metric_flags.get(metric_code, False) or not any(
                    settings.semantic_metric_flags.values()
                )
                if metric_code in settings.semantic_metric_flags:
                    flag_ok = bool(settings.semantic_metric_flags.get(metric_code))
            if metric_code and flag_ok:
                compiled = try_compile_resolved_metric(
                    tenant_id=tenant_id,
                    datasource_id=datasource_id,
                    metric_code=metric_code,
                )
                if compiled and compiled.get("sql"):
                    if settings.semantic_shadow_mode:
                        yield _sse(
                            "status",
                            {
                                "phase": "semantic_shadow",
                                "metric": metric_code,
                                "sql": compiled["sql"],
                                "astFingerprint": compiled.get("astFingerprint"),
                            },
                        ).encode()
                    else:
                        sql = str(compiled["sql"])
                        sql_source = "semantic_metric_compiler"
                        verified_meta = {
                            "id": metric_code,
                            "sql": sql,
                            "source": "semantic_compiler",
                            "logicalPlan": compiled.get("logicalPlan"),
                        }
                        yield _sse(
                            "status",
                            {
                                "phase": "semantic_metric_hit",
                                "metric": metric_code,
                                "sql": sql,
                                "semantic_version": semantic_meta.get("semanticVersion"),
                            },
                        ).encode()
    except Exception as e:
        yield _sse("status", {"phase": "semantic_lookup_skip", "detail": str(e)[:200]}).encode()

    # Legacy physical verified SQL lookup intentionally disabled (returns None).
    if meta_engine is not None and not sql:
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

    conversation_turns: list[dict[str, Any]] = []
    if meta_engine is not None:
        try:
            from nanobase_api.infrastructure.conversation_repo import ConversationRepository

            hist = ConversationRepository(meta_engine).list_recent_messages(
                tenant_id=tenant_id, conversation_id=session_id, limit=6
            )
            conversation_turns = hist
        except Exception:
            conversation_turns = []

    authorized_context = ""
    if not sql:
        yield _sse(
            "status",
            {"phase": "schema_retrieval", "type": "STATUS", "datasource_id": datasource_id},
        ).encode()
        retrieved = ""
        try:
            from nanobase_awel.retrieval.authorized import retrieve_authorized_schema

            retrieval_meta = await retrieve_authorized_schema(
                message,
                tenant_id=tenant_id,
                datasource_id=datasource_id,
            )
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

        schema_hint = _schema_hint_for(datasource_id)
        plan_dialect = _dialect_for_datasource(datasource_id)
        authorized_context = f"{schema_hint}\n{retrieved}".strip()
        plan_workflow = (
            "nanobase-oracle-sql-plan-v1"
            if plan_dialect == "oracle"
            else "nanobase-sql-plan-v1"
        )
        yield _sse(
            "status",
            {
                "phase": "generating_sql",
                "workflow": plan_workflow,
                "datasource_id": datasource_id,
                "dialect": plan_dialect,
            },
        ).encode()
        plan_box: list[Any] = []
        try:
            async for chunk in _await_llm_with_queue_sse(
                _engine_adapter.generate_sql_plan(
                    question=message,
                    datasource_id=datasource_id,
                    schema_hint=schema_hint,
                    retrieved_schema=retrieved or None,
                    conversation_context=conversation_turns,
                    tenant_id=tenant_id,
                    execution_id=execution_id,
                    allowed_tables=list(retrieval_meta.get("tables") or []),
                    prefetched_retrieval=retrieval_meta,
                    dialect=plan_dialect,
                ),
                tenant_id=tenant_id,
                user_id=user_id,
                request_id=execution_id,
                out=plan_box,
            ):
                yield chunk
        except Exception as e:
            yield _sse("error", {"type": "ERROR", "message": f"sql-plan failed: {e}"}).encode()
            return
        if not plan_box or plan_box[0] is None:
            return
        plan = plan_box[0]

        if str(plan.get("status") or "").upper() == "AMBIGUOUS":
            clarify = plan.get("clarificationQuestion") or "Soruyu biraz daha netleştirebilir misiniz?"
            yield _sse(
                "status",
                {
                    "phase": "clarification_required",
                    "type": "CLARIFICATION_REQUIRED",
                    "question": clarify,
                    "ambiguities": plan.get("ambiguities") or [],
                },
            ).encode()
            result = {
                "session_id": session_id,
                "reply": clarify,
                "intent": "clarify",
                "sql": None,
                "needs_clarification": True,
                "query_result": {"columns": [], "rows": []},
                "widgets": [],
                "answer_blocks": [{"type": "text", "text": clarify}],
                "engine": "nanobase_awel",
                "workflows": {"plan": plan},
                "execution_id": execution_id,
            }
            yield _sse("completed", {"type": "COMPLETED", "payload": {"clarification": True}}).encode()
            yield _sse("done", result).encode()
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
            yield _sse("error", {"message": "No SQL from sql-plan", "plan": plan}).encode()
            return

    # Faz 8/9: Oracle / SAP execute gated by feature flags
    plan_dialect = _dialect_for_datasource(datasource_id)
    if plan_dialect == "oracle" and mode != ExecutionMode.PLAN_ONLY:
        if not settings.oracle_execution_enabled or settings.oracle_execution_mode == "PLAN_ONLY":
            reply = (
                "Oracle SQL planı üretildi. Oracle execution kapalı "
                f"(ORACLE_EXECUTION_ENABLED={int(settings.oracle_execution_enabled)}, "
                f"ORACLE_EXECUTION_MODE={settings.oracle_execution_mode}).\n\nSQL:\n{sql}"
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
                "engine": "nanobase_oracle_plan_only",
                "workflows": {"plan": plan, "explain": None},
                "sql_source": sql_source,
                "execution_id": execution_id,
            }
            yield _sse("final", result).encode()
            _persist_conversation(
                meta_engine,
                tenant_id=tenant_id,
                session_id=session_id,
                datasource_id=datasource_id,
                message=message,
                reply=reply,
                sql=sql,
                execution_mode="ORACLE_PLAN_ONLY",
                executed=False,
            )
            return

    if plan_dialect in ("odata", "hana") and mode != ExecutionMode.PLAN_ONLY:
        sap_blocked = (
            not settings.sap_execution_enabled
            or settings.sap_execution_mode in ("PLAN_ONLY", "METADATA_ONLY")
            or (plan_dialect == "hana" and not settings.sap_hana_execution_enabled)
        )
        if sap_blocked:
            reply = (
                "SAP planı üretildi. SAP execution kapalı "
                f"(SAP_EXECUTION_ENABLED={int(settings.sap_execution_enabled)}, "
                f"SAP_EXECUTION_MODE={settings.sap_execution_mode}, "
                f"SAP_HANA_EXECUTION_ENABLED={int(settings.sap_hana_execution_enabled)}).\n\nPlan/SQL:\n{sql}"
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
                "engine": "nanobase_sap_plan_only",
                "workflows": {"plan": plan, "explain": None},
                "sql_source": sql_source,
                "execution_id": execution_id,
            }
            yield _sse("final", result).encode()
            _persist_conversation(
                meta_engine,
                tenant_id=tenant_id,
                session_id=session_id,
                datasource_id=datasource_id,
                message=message,
                reply=reply,
                sql=sql,
                execution_mode="SAP_PLAN_ONLY",
                executed=False,
            )
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
    from nanobase_api.infrastructure.query_gateway_client import QueryGatewayClient
    from nanobase_awel.workflows.sql_repair import is_repairable

    qg = QueryGatewayClient(QG_BASE)
    repair_attempts = 0
    max_repairs = 2
    last_error_code = ""
    safe_sql = sql
    ej: dict = {}
    explain_plan_text = None
    while True:
        vj = await qg.validate(
            sql=safe_sql,
            datasource_id=datasource_id,
            execution_id=execution_id,
            tenant_id=tenant_id,
        )
        if not vj.get("ok"):
            code = str(vj.get("code") or "QUERY_POLICY_REJECTED")
            msg = vj.get("message") or vj.get("error") or vj.get("detail") or "SQL rejected by gateway"
            yield _sse(
                "status",
                {"phase": "sql_rejected", "type": "SQL_REJECTED", "code": code, "message": msg},
            ).encode()
            if (
                repair_attempts < max_repairs
                and is_repairable(code)
                and code != last_error_code
            ):
                repair_attempts += 1
                last_error_code = code
                yield _sse(
                    "status",
                    {
                        "phase": "repairing_sql",
                        "type": "STATUS",
                        "attempt": repair_attempts,
                        "workflow": "nanobase-sql-repair-v1",
                    },
                ).encode()
                repair_box: list[Any] = []
                try:
                    async for chunk in _await_llm_with_queue_sse(
                        _engine_adapter.repair_sql(
                            question=message,
                            datasource_id=datasource_id,
                            previous_sql=safe_sql,
                            error_code=code,
                            error_message=str(msg)[:500],
                            attempt=repair_attempts,
                            authorized_context=authorized_context,
                            schema_hint=_schema_hint_for(datasource_id),
                            allowed_tables=list((retrieval_meta or {}).get("tables") or []),
                            tenant_id=tenant_id,
                            execution_id=execution_id,
                        ),
                        tenant_id=tenant_id,
                        user_id=user_id,
                        request_id=f"{execution_id}-repair-{repair_attempts}",
                        out=repair_box,
                    ):
                        yield chunk
                except Exception as e:
                    yield _sse(
                        "error",
                        {"message": str(e), "code": code, "type": "QUERY_POLICY_REJECTED"},
                    ).encode()
                    return
                if not repair_box or repair_box[0] is None:
                    return
                repaired = repair_box[0]
                new_sql = str(repaired.get("sql") or "").strip()
                if not new_sql or new_sql == safe_sql:
                    yield _sse(
                        "error",
                        {
                            "message": msg,
                            "code": code,
                            "sql": safe_sql,
                            "type": "QUERY_POLICY_REJECTED",
                        },
                    ).encode()
                    return
                safe_sql = new_sql
                yield _sse(
                    "status",
                    {"phase": "sql_repaired", "type": "SQL_REPAIRED", "sql": safe_sql},
                ).encode()
                yield _sse(
                    "sql_generated",
                    {"type": "SQL_GENERATED", "payload": {"sql": safe_sql, "sql_source": "repair"}},
                ).encode()
                continue
            yield _sse(
                "error",
                {
                    "message": msg,
                    "code": code,
                    "sql": safe_sql,
                    "type": "QUERY_POLICY_REJECTED",
                },
            ).encode()
            return

        yield _sse("status", {"phase": "validated", "sql": vj.get("sql") or safe_sql}).encode()
        safe_sql = vj.get("sql") or safe_sql
        yield _sse("status", {"phase": "executing", "sql": safe_sql, "via": "query_gateway"}).encode()
        try:
            ej = await qg.execute(
                sql=safe_sql,
                datasource_id=datasource_id,
                execution_id=execution_id,
                tenant_id=tenant_id,
            )
        except Exception as e:
            yield _sse(
                "error",
                {
                    "message": str(e),
                    "code": "QUERY_POLICY_REJECTED",
                    "sql": safe_sql,
                    "type": "QUERY_POLICY_REJECTED",
                },
            ).encode()
            return
        if not ej.get("ok"):
            yield _sse(
                "error",
                {
                    "message": ej.get("detail") or ej.get("error") or "execute failed",
                    "code": ej.get("code") or "QUERY_POLICY_REJECTED",
                    "sql": safe_sql,
                    "type": "QUERY_POLICY_REJECTED",
                },
            ).encode()
            return
        break

    if with_explain:
        yield _sse("status", {"phase": "gateway_explain"}).encode()
        try:
            xj = await qg.execute(
                sql=safe_sql,
                datasource_id=datasource_id,
                explain=True,
            )
            explain_plan_text = "\n".join(
                str(list(row.values())[0]) for row in (xj.get("rows") or []) if row
            )
        except Exception:
            explain_plan_text = None

    rows = ej.get("rows") or []
    cols = ej.get("columns") or []

    yield _sse(
        "status",
        {"phase": "generating_answer", "workflow": "nanobase-result-explain-v1"},
    ).encode()
    explain_box: list[Any] = []
    try:
        async for chunk in _await_llm_with_queue_sse(
            _engine_adapter.explain_result(
                question=message,
                executed_sql=safe_sql,
                columns=cols,
                rows=rows,
                truncated=bool(ej.get("truncated")),
                datasource_id=datasource_id,
                tenant_id=tenant_id,
                execution_id=execution_id,
            ),
            tenant_id=tenant_id,
            user_id=user_id,
            request_id=f"{execution_id}-explain",
            out=explain_box,
        ):
            yield chunk
        if explain_box and explain_box[0] is not None:
            explained = explain_box[0]
        else:
            explained = {
                "workflow": "nanobase-result-explain-v1",
                "answer": f"Sonuç alındı ({len(rows)} satır).",
                "insights": [],
                "warnings": ["explain_queued_or_failed"],
            }
    except Exception as e:
        explained = {
            "workflow": "nanobase-result-explain-v1",
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
