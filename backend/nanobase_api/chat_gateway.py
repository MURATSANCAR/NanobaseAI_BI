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

from nanobase_api.chat_widgets import widgets_from_query_result
from nanobase_api.config import ExecutionMode, get_settings
from nanobase_api.infrastructure.text2sql_adapter import WorkflowTextToSqlAdapter
from nanobase_api.workflows import DEFAULT_SCHEMA_HINT
from nanobase_awel.contracts.errors import WorkflowError
from nanobase_awel.operators import model_queue as model_queue_mod

QG_BASE = os.environ.get("QUERY_GATEWAY_BASE", "http://127.0.0.1:8792").rstrip("/")
SECRETS = Path(os.environ.get("SECRETS_ROOT", "/data/nanobaseai/bi/secrets"))

_HINTS_CACHE: dict[str, str] | None = None
_engine_adapter = WorkflowTextToSqlAdapter()


def _build_provenance(
    plan: dict[str, Any] | None,
    *,
    executed: bool,
    execution_mode: str | None = None,
    extra_warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Map SqlPlan dict → FE provenance for SQL panel / hero."""
    p = plan or {}
    warnings = [str(w) for w in (p.get("warnings") or [])]
    if extra_warnings:
        warnings.extend(str(w) for w in extra_warnings)
    conf = p.get("confidence")
    try:
        conf_f = float(conf) if conf is not None else None
    except (TypeError, ValueError):
        conf_f = None
    return {
        "type": "sql_plan",
        "selected_tables": [str(t) for t in (p.get("tables") or [])],
        "columns": [str(c) for c in (p.get("columns") or [])],
        "assumptions": [str(a) for a in (p.get("assumptions") or [])],
        "ambiguities": [str(a) for a in (p.get("ambiguities") or [])],
        "warnings": warnings,
        "confidence": conf_f,
        "dialect": str(p.get("dialect") or "") or None,
        "executed": bool(executed),
        "execution_mode": execution_mode,
    }


def _with_provenance(
    result: dict[str, Any],
    plan: dict[str, Any] | None,
    *,
    executed: bool,
    execution_mode: str | None = None,
    extra_warnings: list[str] | None = None,
) -> dict[str, Any]:
    out = dict(result)
    prov = _build_provenance(
        plan, executed=executed, execution_mode=execution_mode, extra_warnings=extra_warnings
    )
    out["provenance"] = prov
    if extra_warnings:
        existing = list(out.get("warnings") or [])
        for w in extra_warnings:
            if w not in existing:
                existing.append(w)
        out["warnings"] = existing
    return out


def _schema_hint_for(datasource_id: str) -> str:
    global _HINTS_CACHE
    dialect = _dialect_for_datasource(datasource_id)
    if dialect == "oracle":
        return (
            f"Oracle datasource '{datasource_id}'. "
            "Only SELECT/WITH. Owner-qualify (NANOBASE_REPORTING.*). "
            "Use FETCH FIRST n ROWS ONLY. No LIMIT, ILIKE, hints, DB links, or PL/SQL."
        )
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
    if datasource_id in _HINTS_CACHE:
        return _HINTS_CACHE[datasource_id]
    # Local reporting seed hint only when that datasource id is the configured reporting id
    try:
        from nanobase_api.infrastructure.datasource_registry import reporting_datasource_id

        if datasource_id in ("", "default") or datasource_id == reporting_datasource_id():
            return DEFAULT_SCHEMA_HINT
    except Exception:
        if datasource_id in ("", "default"):
            return DEFAULT_SCHEMA_HINT
    return (
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


def _user_guide_reply(code: str, message: str | None = None) -> str | None:
    try:
        from nanobase_awel.operators.planning_guidance import user_guidance_for_gateway_error

        return user_guidance_for_gateway_error(code, message)
    except Exception:
        return None


def _normalize_gateway_error(code: str, message: str | None) -> tuple[str, str]:
    """Map legacy/HTTP execute failures into repairable AWEL codes."""
    msg = str(message or "")
    low = msg.lower()
    c = str(code or "QUERY_POLICY_REJECTED")
    if "missing from-clause entry" in low:
        return "UNDEFINED_TABLE_ALIAS", msg
    if "cannot cast" in low:
        return "QUERY_TYPE_CONVERSION_FAILED", msg
    if c.startswith("HTTP_") or c in ("INTERNAL_ERROR", "REJECTED"):
        if "column" in low and "does not exist" in low:
            return "COLUMN_NOT_FOUND", msg
        if "relation" in low and "does not exist" in low:
            return "TABLE_OR_VIEW_NOT_FOUND", msg
        if "syntax error" in low:
            return "SQL_PARSE_FAILED", msg
        if "execution failed" in low:
            return "SQL_EXECUTION_FAILED", msg
    return c, msg


async def _expand_retrieval_for_missing_tables(
    *,
    code: str,
    message: str,
    retrieval_meta: dict[str, Any],
    authorized_context: str,
    message_question: str,
    datasource_id: str,
    tenant_id: str,
    schema_hint: str,
) -> tuple[dict[str, Any], str, bool]:
    """Index-backed table expand on TABLE_OR_VIEW_NOT_FOUND (no static catalogs)."""
    if code not in ("TABLE_OR_VIEW_NOT_FOUND", "SCHEMA_REFERENCE_FAILED"):
        return retrieval_meta, authorized_context, False
    try:
        from nanobase_awel.retrieval.authorized import (
            expand_tables_from_index,
            parse_missing_tables_from_error,
            build_sanitized_context,
        )

        missing = parse_missing_tables_from_error(message)
        if not missing:
            return retrieval_meta, authorized_context, False
        expanded = await expand_tables_from_index(
            missing,
            tenant_id=tenant_id or "default",
            datasource_id=datasource_id,
            existing=retrieval_meta,
        )
        if not expanded.get("expanded_tables"):
            return retrieval_meta, authorized_context, False
        new_ctx = build_sanitized_context(
            question=message_question,
            schema_hint=schema_hint or "",
            retrieval=expanded,
        )
        return expanded, new_ctx or authorized_context, True
    except Exception:
        return retrieval_meta, authorized_context, False


async def _yield_user_guidance(
    *,
    session_id: str,
    execution_id: str,
    plan: dict[str, Any],
    mode: Any,
    reply: str,
    code: str,
    sql: str | None,
) -> AsyncIterator[bytes]:
    """Soft-fail with guidance instead of a hard error (cost/timeout/unavailable)."""
    yield _sse(
        "status",
        {
            "phase": "user_guidance",
            "type": "USER_GUIDANCE",
            "code": code,
            "message": reply,
        },
    ).encode()
    result = _with_provenance(
        {
            "session_id": session_id,
            "reply": reply,
            "intent": "clarify",
            "sql": sql,
            "sql_error": f"{code}: {reply}",
            "needs_clarification": True,
            "query_result": {"columns": [], "rows": []},
            "widgets": [],
            "answer_blocks": [{"type": "text", "text": reply}],
            "engine": "nanobase_awel",
            "workflows": {"plan": plan},
            "execution_id": execution_id,
            "gateway_code": code,
        },
        plan,
        executed=False,
        execution_mode=getattr(mode, "value", str(mode)),
    )
    yield _sse("completed", {"type": "COMPLETED", "payload": {"guidance": True, "code": code}}).encode()
    yield _sse("done", result).encode()


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
    prepared_sql: str | None = None,
    template_id: str | None = None,
    prepared_params: dict[str, Any] | None = None,
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
    bind_parameters: dict[str, Any] | None = None
    scenario_followups: list[str] = []

    # FE template / prepared-script fast path: skip schema retrieval + LLM plan.
    prepared = (prepared_sql or "").strip()
    if prepared:
        sql = prepared
        sql_source = "prepared_sql"
        if isinstance(prepared_params, dict) and prepared_params:
            bind_parameters = dict(prepared_params)
        verified_meta = {
            "id": template_id or "prepared",
            "sql": sql,
            "source": "prepared_sql",
            "parameters": bind_parameters or {},
        }
        yield _sse(
            "status",
            {
                "phase": "prepared_sql_hit",
                "type": "STATUS",
                "template_id": template_id,
                "sql": sql,
                "has_bind_params": bool(bind_parameters),
            },
        ).encode()
        yield _sse(
            "sql_generated",
            {"type": "SQL_GENERATED", "payload": {"sql": sql, "sql_source": sql_source}},
        ).encode()

    # Precompiled scenario engine — before semantic metric / AWEL
    if not sql:
        try:
            from nanobase_api.scenario_engine.application.runtime import try_precompiled_scenario
            from nanobase_api.scenario_engine.infrastructure.metrics import (
                SCENARIO_FALLBACK_AWEL,
                SCENARIO_EXACT_MATCH,
                inc,
            )

            scenario_hit = try_precompiled_scenario(
                message,
                tenant_id=tenant_id,
                datasource_id=datasource_id,
            )
            if scenario_hit and (scenario_hit.get("sqlTemplate") or scenario_hit.get("sql")):
                sql = str(scenario_hit.get("sqlTemplate") or scenario_hit["sql"])
                sql_source = "precompiled_scenario"
                bind_parameters = dict(scenario_hit.get("parameters") or scenario_hit.get("bindParams") or {})
                scenario_followups = list(scenario_hit.get("followUps") or [])
                verified_meta = {
                    "id": scenario_hit.get("scenarioId"),
                    "sql": sql,
                    "source": "precompiled_scenario",
                    "logicalPlan": scenario_hit.get("logicalPlan"),
                    "parameters": bind_parameters,
                }
                if float(scenario_hit.get("confidence") or 0) >= 0.99:
                    inc(SCENARIO_EXACT_MATCH)
                yield _sse(
                    "status",
                    {
                        "phase": "scenario_hit",
                        "scenario_id": scenario_hit.get("scenarioId"),
                        "scenario_code": scenario_hit.get("scenarioCode"),
                        "confidence": scenario_hit.get("confidence"),
                        "route": scenario_hit.get("route"),
                        "sql": sql,
                        "sql_source": sql_source,
                        "followUps": scenario_followups,
                        "has_bind_params": bool(bind_parameters),
                    },
                ).encode()
            else:
                inc(SCENARIO_FALLBACK_AWEL)
        except Exception as e:
            yield _sse("status", {"phase": "scenario_lookup_skip", "detail": str(e)[:200]}).encode()

    # Faz 7: logical metric compile (never run legacy physical verified SQL as source of truth)
    try:
        from nanobase_awel.retrieval.semantic import (
            retrieve_semantic_context,
            try_compile_resolved_metric,
        )

        if not sql and settings.semantic_catalog_enabled:
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

    # Learned cache: exact / similar prior successful questions (skip NL→SQL LLM)
    if meta_engine is not None and not sql:
        try:
            from nanobase_api.infrastructure.learned_query_cache import lookup as learned_lookup

            hit = learned_lookup(
                meta_engine,
                tenant_id=tenant_id,
                datasource_id=datasource_id,
                question=message,
            )
            if hit and hit.sql:
                sql = hit.sql
                sql_source = "learned_cache"
                verified_meta = {
                    "id": hit.id,
                    "sql": sql,
                    "source": "learned_cache",
                    "match": hit.match,
                    "score": hit.score,
                    "prior_question": hit.question,
                }
                yield _sse(
                    "status",
                    {
                        "phase": "learned_cache_hit",
                        "learned_id": hit.id,
                        "match": hit.match,
                        "score": hit.score,
                        "prior_question": hit.question[:200],
                        "sql": sql,
                        "sql_source": sql_source,
                    },
                ).encode()
                yield _sse(
                    "sql_generated",
                    {
                        "type": "SQL_GENERATED",
                        "payload": {"sql": sql, "sql_source": sql_source},
                    },
                ).encode()
        except Exception as e:
            yield _sse("status", {"phase": "learned_lookup_skip", "detail": str(e)[:200]}).encode()

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
            result = _with_provenance(
                {
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
                },
                plan,
                executed=False,
                execution_mode=mode.value,
            )
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
            result = _with_provenance(
                {
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
                    "execution_mode": "ORACLE_PLAN_ONLY",
                },
                plan,
                executed=False,
                execution_mode="ORACLE_PLAN_ONLY",
            )
            yield _sse("final", result).encode()
            yield _sse("done", result).encode()
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
            result = _with_provenance(
                {
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
                    "execution_mode": "SAP_PLAN_ONLY",
                },
                plan,
                executed=False,
                execution_mode="SAP_PLAN_ONLY",
            )
            yield _sse("final", result).encode()
            yield _sse("done", result).encode()
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
        result = _with_provenance(
            {
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
            },
            plan,
            executed=False,
            execution_mode=mode.value,
            extra_warnings=["EXECUTION_DISABLED"],
        )
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

    # Normalize LLM SQL escapes before Gateway validate (literal \n breaks sqlglot).
    try:
        from nanobase_awel.operators.structured_parser import normalize_single_select_sql

        sql = normalize_single_select_sql(sql) or sql
    except Exception:
        pass

    seed_reject: tuple[str, str] | None = None
    did_schema_expand = False
    try:
        from nanobase_awel.operators.sql_shape_guard import guard_sql_shape

        allowed = list((retrieval_meta or {}).get("tables") or []) or list(
            (plan or {}).get("tables") or []
        )
        col_map = (retrieval_meta or {}).get("table_columns") or None
        guarded = guard_sql_shape(
            sql,
            allowed_tables=allowed,
            question=message,
            table_columns=col_map,
        )
        if guarded.warnings and isinstance(plan.get("warnings"), list):
            plan["warnings"].extend(guarded.warnings)
        elif guarded.warnings:
            plan["warnings"] = list(guarded.warnings)
        sql = guarded.sql
        if guarded.blocked and guarded.code:
            from nanobase_awel.workflows.sql_repair import is_repairable as _shape_repairable

            code = str(guarded.code)
            msg = str(guarded.message or "SQL shape rejected")
            yield _sse(
                "status",
                {
                    "phase": "sql_shape_guard",
                    "type": "SQL_REJECTED",
                    "code": code,
                    "message": msg,
                },
            ).encode()
            if code in ("TABLE_OR_VIEW_NOT_FOUND", "SCHEMA_REFERENCE_FAILED") and not did_schema_expand:
                retrieval_meta, authorized_context, did_exp = await _expand_retrieval_for_missing_tables(
                    code=code,
                    message=msg,
                    retrieval_meta=retrieval_meta or {},
                    authorized_context=authorized_context,
                    message_question=message,
                    datasource_id=datasource_id,
                    tenant_id=tenant_id or "default",
                    schema_hint=_schema_hint_for(datasource_id),
                )
                if did_exp:
                    did_schema_expand = True
                    yield _sse(
                        "status",
                        {
                            "phase": "schema_expand",
                            "type": "STATUS",
                            "expanded_tables": list(retrieval_meta.get("expanded_tables") or []),
                        },
                    ).encode()
                    g_exp = guard_sql_shape(
                        sql,
                        allowed_tables=list(retrieval_meta.get("tables") or []),
                        question=message,
                        table_columns=retrieval_meta.get("table_columns") or None,
                    )
                    sql = g_exp.sql
                    if g_exp.warnings:
                        plan.setdefault("warnings", []).extend(list(g_exp.warnings))
                    if not g_exp.blocked:
                        code = ""
                        msg = ""
                    else:
                        code = str(g_exp.code or code)
                        msg = str(g_exp.message or msg)
                        yield _sse(
                            "status",
                            {
                                "phase": "sql_shape_guard",
                                "type": "SQL_REJECTED",
                                "code": code,
                                "message": msg,
                            },
                        ).encode()
            if code and _shape_repairable(code):
                seed_reject = (code, msg)
            elif code:
                guide = _user_guide_reply(code, msg)
                if guide:
                    async for chunk in _yield_user_guidance(
                        session_id=session_id,
                        execution_id=execution_id,
                        plan=plan,
                        mode=mode,
                        reply=guide,
                        code=code,
                        sql=sql,
                    ):
                        yield chunk
                    return
                yield _sse(
                    "error",
                    {
                        "message": msg,
                        "code": code,
                        "sql": sql,
                        "type": "QUERY_POLICY_REJECTED",
                    },
                ).encode()
                return
    except Exception:
        seed_reject = None

    yield _sse("status", {"phase": "validating", "sql": sql, "sql_source": sql_source}).encode()
    from nanobase_api.infrastructure.query_gateway_client import QueryGatewayClient
    from nanobase_awel.workflows.sql_repair import is_repairable

    qg = QueryGatewayClient(QG_BASE)
    repair_attempts = 0
    max_repairs = 2
    last_error_fp = ""
    conn_retried = False
    safe_sql = sql
    ej: dict = {}
    explain_plan_text = None

    while True:
        if seed_reject:
            code, msg = seed_reject
            seed_reject = None
            vj = {"ok": False, "code": code, "message": msg}
        else:
            vj = await qg.validate(
                sql=safe_sql,
                datasource_id=datasource_id,
                execution_id=execution_id,
                tenant_id=tenant_id,
                parameters=bind_parameters,
            )
        if not vj.get("ok"):
            code = str(vj.get("code") or "QUERY_POLICY_REJECTED")
            msg = vj.get("message") or vj.get("error") or vj.get("detail") or "SQL rejected by gateway"
            code, msg = _normalize_gateway_error(code, str(msg))
            if (
                code in ("TABLE_OR_VIEW_NOT_FOUND", "SCHEMA_REFERENCE_FAILED")
                and not did_schema_expand
            ):
                retrieval_meta, authorized_context, did_exp = await _expand_retrieval_for_missing_tables(
                    code=code,
                    message=str(msg),
                    retrieval_meta=retrieval_meta or {},
                    authorized_context=authorized_context,
                    message_question=message,
                    datasource_id=datasource_id,
                    tenant_id=tenant_id or "default",
                    schema_hint=_schema_hint_for(datasource_id),
                )
                if did_exp:
                    did_schema_expand = True
                    yield _sse(
                        "status",
                        {
                            "phase": "schema_expand",
                            "type": "STATUS",
                            "expanded_tables": list(retrieval_meta.get("expanded_tables") or []),
                        },
                    ).encode()
            err_fp = f"{code}|{str(msg)[:160]}"
            yield _sse(
                "status",
                {"phase": "sql_rejected", "type": "SQL_REJECTED", "code": code, "message": msg},
            ).encode()
            if (
                repair_attempts < max_repairs
                and is_repairable(code)
                and err_fp != last_error_fp
            ):
                repair_attempts += 1
                last_error_fp = err_fp
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
                    guide = _user_guide_reply(code, str(msg))
                    if guide:
                        async for chunk in _yield_user_guidance(
                            session_id=session_id,
                            execution_id=execution_id,
                            plan=plan,
                            mode=mode,
                            reply=guide,
                            code=code,
                            sql=safe_sql,
                        ):
                            yield chunk
                        return
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
                # Re-apply shape guard on repaired SQL
                try:
                    from nanobase_awel.operators.sql_shape_guard import guard_sql_shape

                    g2 = guard_sql_shape(
                        new_sql,
                        allowed_tables=list((retrieval_meta or {}).get("tables") or []),
                        question=message,
                        table_columns=(retrieval_meta or {}).get("table_columns") or None,
                    )
                    new_sql = g2.sql
                    if g2.blocked and g2.code:
                        code2 = str(g2.code)
                        msg2 = str(g2.message or "")
                        if not is_repairable(code2) or repair_attempts >= max_repairs:
                            guide = _user_guide_reply(code2, msg2)
                            if guide:
                                async for chunk in _yield_user_guidance(
                                    session_id=session_id,
                                    execution_id=execution_id,
                                    plan=plan,
                                    mode=mode,
                                    reply=guide,
                                    code=code2,
                                    sql=new_sql,
                                ):
                                    yield chunk
                                return
                            yield _sse(
                                "error",
                                {
                                    "message": msg2,
                                    "code": code2,
                                    "sql": new_sql,
                                    "type": "QUERY_POLICY_REJECTED",
                                },
                            ).encode()
                            return
                        safe_sql = new_sql
                        seed_reject = (code2, msg2)
                        yield _sse(
                            "status",
                            {
                                "phase": "sql_shape_guard",
                                "type": "SQL_REJECTED",
                                "code": code2,
                                "message": msg2,
                            },
                        ).encode()
                        continue
                except Exception:
                    pass
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
            guide = _user_guide_reply(code, str(msg))
            if guide:
                async for chunk in _yield_user_guidance(
                    session_id=session_id,
                    execution_id=execution_id,
                    plan=plan,
                    mode=mode,
                    reply=guide,
                    code=code,
                    sql=safe_sql,
                ):
                    yield chunk
                return
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
                parameters=bind_parameters,
            )
        except Exception as e:
            code = "QUERY_POLICY_REJECTED"
            msg = str(e)
            guide = _user_guide_reply(code, msg)
            if guide:
                async for chunk in _yield_user_guidance(
                    session_id=session_id,
                    execution_id=execution_id,
                    plan=plan,
                    mode=mode,
                    reply=guide,
                    code=code,
                    sql=safe_sql,
                ):
                    yield chunk
                return
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
        if not ej.get("ok"):
            code = str(ej.get("code") or "QUERY_POLICY_REJECTED")
            msg = (
                ej.get("message")
                or ej.get("detail")
                or ej.get("error")
                or "execute failed"
            )
            code, msg = _normalize_gateway_error(code, str(msg))
            # One automatic retry for transient connection loss on read-only SELECT.
            if code == "DATABASE_CONNECTION_LOST" and not conn_retried:
                conn_retried = True
                yield _sse(
                    "status",
                    {
                        "phase": "execute_retry",
                        "type": "STATUS",
                        "code": code,
                        "message": "Bağlantı koptu; sorgu bir kez yeniden deneniyor.",
                    },
                ).encode()
                try:
                    ej = await qg.execute(
                        sql=safe_sql,
                        datasource_id=datasource_id,
                        execution_id=execution_id,
                        tenant_id=tenant_id,
                        parameters=bind_parameters,
                    )
                    if ej.get("ok"):
                        break
                    code = str(ej.get("code") or code)
                    msg = ej.get("message") or ej.get("detail") or ej.get("error") or msg
                except Exception as e2:
                    msg = str(e2)
            yield _sse(
                "status",
                {
                    "phase": "execute_failed",
                    "type": "EXECUTE_FAILED",
                    "code": code,
                    "message": msg,
                },
            ).encode()
            err_fp = f"{code}|{str(msg)[:160]}"
            if (
                repair_attempts < max_repairs
                and is_repairable(code)
                and err_fp != last_error_fp
            ):
                repair_attempts += 1
                last_error_fp = err_fp
                yield _sse(
                    "status",
                    {
                        "phase": "repairing_sql",
                        "type": "STATUS",
                        "attempt": repair_attempts,
                        "workflow": "nanobase-sql-repair-v1",
                        "after": "execute",
                    },
                ).encode()
                repair_box = []
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
                        request_id=f"{execution_id}-repair-exec-{repair_attempts}",
                        out=repair_box,
                    ):
                        yield chunk
                except Exception as e:
                    guide = _user_guide_reply(code, str(msg))
                    if guide:
                        async for chunk in _yield_user_guidance(
                            session_id=session_id,
                            execution_id=execution_id,
                            plan=plan,
                            mode=mode,
                            reply=guide,
                            code=code,
                            sql=safe_sql,
                        ):
                            yield chunk
                        return
                    yield _sse(
                        "error",
                        {"message": str(e), "code": code, "type": "QUERY_POLICY_REJECTED"},
                    ).encode()
                    return
                if repair_box and repair_box[0] is not None:
                    new_sql = str(repair_box[0].get("sql") or "").strip()
                    if new_sql and new_sql != safe_sql:
                        try:
                            from nanobase_awel.operators.sql_shape_guard import guard_sql_shape

                            g3 = guard_sql_shape(
                                new_sql,
                                allowed_tables=list((retrieval_meta or {}).get("tables") or []),
                                question=message,
                                table_columns=(retrieval_meta or {}).get("table_columns") or None,
                            )
                            new_sql = g3.sql
                            if g3.blocked and g3.code:
                                code3 = str(g3.code)
                                msg3 = str(g3.message or "")
                                if not is_repairable(code3) or repair_attempts >= max_repairs:
                                    guide = _user_guide_reply(code3, msg3)
                                    if guide:
                                        async for chunk in _yield_user_guidance(
                                            session_id=session_id,
                                            execution_id=execution_id,
                                            plan=plan,
                                            mode=mode,
                                            reply=guide,
                                            code=code3,
                                            sql=new_sql,
                                        ):
                                            yield chunk
                                        return
                                    yield _sse(
                                        "error",
                                        {
                                            "message": msg3,
                                            "code": code3,
                                            "sql": new_sql,
                                            "type": "QUERY_POLICY_REJECTED",
                                        },
                                    ).encode()
                                    return
                                safe_sql = new_sql
                                seed_reject = (code3, msg3)
                                continue
                        except Exception:
                            pass
                        safe_sql = new_sql
                        yield _sse(
                            "status",
                            {"phase": "sql_repaired", "type": "SQL_REPAIRED", "sql": safe_sql},
                        ).encode()
                        yield _sse(
                            "sql_generated",
                            {
                                "type": "SQL_GENERATED",
                                "payload": {"sql": safe_sql, "sql_source": "repair"},
                            },
                        ).encode()
                        continue
            guide = _user_guide_reply(code, str(msg))
            if guide:
                async for chunk in _yield_user_guidance(
                    session_id=session_id,
                    execution_id=execution_id,
                    plan=plan,
                    mode=mode,
                    reply=guide,
                    code=code,
                    sql=safe_sql,
                ):
                    yield chunk
                return
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
        break

    if with_explain:
        yield _sse("status", {"phase": "gateway_explain"}).encode()
        try:
            xj = await qg.execute(
                sql=safe_sql,
                datasource_id=datasource_id,
                explain=True,
                parameters=bind_parameters,
            )
            explain_plan_text = "\n".join(
                str(list(row.values())[0]) for row in (xj.get("rows") or []) if row
            )
        except Exception:
            explain_plan_text = None

    rows = ej.get("rows") or []
    cols = ej.get("columns") or []

    # Prepared / compiled SQL already skipped NL→SQL LLM; skip answer LLM too
    # (deterministic summary is enough — Qwen explain was the remaining 10–25s).
    _fast_answer_sources = {
        "prepared_sql",
        "precompiled_scenario",
        "verified_sql",
        "semantic_metric_compiler",
        "learned_cache",
    }
    if sql_source in _fast_answer_sources:
        from nanobase_awel.operators.answer_fidelity_validator import (
            deterministic_fallback_answer,
        )
        from nanobase_awel.operators.result_summarizer import summarize_result

        col_names = [str(c.get("name") if isinstance(c, dict) else c) for c in cols]
        summary = summarize_result(
            col_names, rows, truncated=bool(ej.get("truncated")), max_sample=100
        )
        answer = deterministic_fallback_answer(
            summary=summary,
            columns=col_names,
            rows=rows,
            truncated=bool(ej.get("truncated")),
        )
        explained = {
            "workflow": "nanobase-result-explain-v1",
            "answer": answer,
            "insights": [],
            "warnings": ["deterministic_fast_path", f"sql_source={sql_source}"],
        }
        yield _sse(
            "status",
            {
                "phase": "generating_answer",
                "workflow": "nanobase-result-explain-v1",
                "fast_path": True,
                "sql_source": sql_source,
            },
        ).encode()
    else:
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

    chart_title = (message or "").replace("\n", " ").strip()[:80] or "Chat sonucu"
    widgets = widgets_from_query_result(
        columns=cols,
        rows=rows if isinstance(rows, list) else [],
        sql=safe_sql,
        title=chart_title,
    )

    yield _sse(
        "answer_delta",
        {"type": "ANSWER_DELTA", "payload": {"text": reply[:500]}},
    ).encode()

    result = _with_provenance(
        {
            "session_id": session_id,
            "reply": reply,
            "intent": "query",
            "sql": safe_sql,
            "sql_error": None,
            "query_result": {"columns": cols, "rows": rows},
            "widgets": widgets,
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
        },
        plan,
        executed=True,
        execution_mode=mode.value,
        extra_warnings=[str(w) for w in (explained.get("warnings") or [])],
    )
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
    # Learn successful Q→SQL for next exact/similar asks (skip LLM)
    try:
        from nanobase_api.infrastructure.learned_query_cache import (
            remember as learned_remember,
            remember_scenario_paraphrase,
        )

        if meta_engine is not None and safe_sql and rows is not None:
            learned_remember(
                meta_engine,
                tenant_id=tenant_id,
                datasource_id=datasource_id,
                question=message,
                sql=safe_sql,
                sql_source=sql_source,
            )
        if sql_source == "precompiled_scenario" and verified_meta:
            remember_scenario_paraphrase(
                tenant_id=tenant_id,
                datasource_id=datasource_id,
                question=message,
                scenario_id=str(verified_meta.get("id") or "") or None,
            )
    except Exception:
        pass
    try:
        from nanobase_api.infrastructure.audit_repo import AuditRepository

        if meta_engine is not None:
            AuditRepository(meta_engine).record(
                tenant_id=tenant_id,
                user_id=user_id,
                action="QUERY_COMPLETED",
                ok=True,
                session_id=session_id,
                extra={
                    "datasource_id": datasource_id,
                    "execution_id": execution_id,
                    "sql_source": sql_source,
                },
            )
    except Exception:
        pass

    yield _sse("status", {"phase": "finalizing"}).encode()
    yield _sse("completed", {"type": "COMPLETED", "payload": {}}).encode()
    yield _sse("done", result).encode()
