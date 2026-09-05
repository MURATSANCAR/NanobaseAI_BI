"""nanobase-sql-plan-v1 — SQL only, no DB execute."""

from __future__ import annotations

import os
from typing import Any

from nanobase_awel import PLAN_WORKFLOW
from nanobase_awel.contracts.errors import OUTPUT_PARSE_FAILED, WorkflowError
from nanobase_awel.contracts.planning import PlanStatus, SqlPlan, SqlPlanningRequest
from nanobase_awel.operators.input_validator import validate_planning_request
from nanobase_awel.operators.llm_operator import chat_completion
from nanobase_awel.operators.planning_guidance import build_planning_guidance
from nanobase_awel.operators.prompt_builder import render_simple, sql_plan_prompts
from nanobase_awel.operators.schema_reference_validator import validate_plan_references
from nanobase_awel.operators.structured_parser import parse_sql_plan
from nanobase_awel.retrieval.authorized import build_sanitized_context, retrieve_authorized_schema

# Cap planning context to keep local LLM latency predictable under CPU contention.
_TEXT2SQL_PREFER = (os.environ.get("TEXT2SQL_PREFER") or "chat").strip().lower()
_TEXT2SQL_COMPACT = True  # always soft-cap; size via TEXT2SQL_CONTEXT_CHARS
_TEXT2SQL_CONTEXT_CHARS = int(
    os.environ.get(
        "TEXT2SQL_CONTEXT_CHARS",
        "4500" if _TEXT2SQL_PREFER in ("arctic", "text2sql") else "9000",
    )
)
# A JSON envelope + multi-CTE query easily exceeds 768 tokens; truncated output
# used to be "salvaged" into broken-but-PLANNED SQL. 2048 default, env-tunable.
_PLAN_MAX_TOKENS = int(os.environ.get("TEXT2SQL_MAX_COMPLETION_TOKENS", "2048"))

# Per-dialect single-statement constraint (the old constant claimed
# "PostgreSQL only" even for Oracle/HANA/OData prompts).
_DIALECT_STMT_RULE = {
    "postgres": "ONE PostgreSQL statement only",
    "oracle": "ONE Oracle SELECT statement only (FETCH FIRST; never LIMIT)",
    "hana": "ONE SAP HANA SELECT statement only",
    "odata": "ONE logical OData query plan only",
    "mssql": (
        "ONE Microsoft SQL Server (T-SQL) SELECT statement only: cap rows with TOP N (never LIMIT); "
        "use ISNULL/COALESCE, GETDATE(), DATEADD/DATEDIFF/DATEPART/YEAR/MONTH, CONVERT/CAST; "
        "always schema-qualify tables (dbo.TABLE); use [brackets] only for identifiers with special characters"
    ),
}

# Enum/status/segment columns are frequently filtered with a differently-cased
# literal than what's stored (question says "Enterprise", column holds
# 'enterprise') — exact equality then silently returns zero rows. Exported
# for reuse by the repair workflow.
DIALECT_CASE_INSENSITIVE_RULE = {
    "postgres": (
        "For equality filters on categorical/status/enum-like text columns, use ILIKE "
        "(or LOWER(col) = LOWER('value')) — never assume the exact stored casing."
    ),
    "oracle": (
        "For equality filters on categorical/status/enum-like text columns, wrap both sides "
        "in UPPER() (e.g. UPPER(col) = UPPER('value')) — never assume the exact stored casing."
    ),
    "hana": (
        "For equality filters on categorical/status/enum-like text columns, wrap both sides "
        "in UPPER() (e.g. UPPER(col) = UPPER('value')) — never assume the exact stored casing."
    ),
    "odata": (
        "For equality filters on categorical/status/enum-like text properties, use a "
        "case-insensitive comparison (tolower(prop) eq tolower('value'))."
    ),
    "mssql": (
        "Text comparisons follow the database collation (usually case-insensitive); when unsure, "
        "wrap both sides in UPPER() (UPPER(col) = UPPER('value')) — never assume the stored casing."
    ),
}


def normalize_dialect(dialect: str | None) -> str:
    d = (dialect or "postgres").strip().lower().replace("postgresql", "postgres")
    if d in ("odata", "s4_odata", "sap_odata"):
        return "odata"
    if d in ("hana", "sap_hana"):
        return "hana"
    if d in ("mssql", "tsql", "sqlserver", "sql_server", "mssqlserver"):
        return "mssql"
    return d if d in _DIALECT_STMT_RULE else "postgres"


def _trim_at_line(text: str, limit: int) -> tuple[str, bool]:
    """Trim to ``limit`` chars at a line boundary — a mid-line cut leaves a
    half column list that reads as authoritative and invites invented names."""
    t = (text or "").strip()
    if len(t) <= limit:
        return t, False
    cut = t.rfind("\n", 0, max(0, limit))
    if cut < limit // 2:
        cut = limit
    return t[:cut].rstrip() + "\n…[context truncated]", True


async def run_sql_plan(
    req: SqlPlanningRequest,
    *,
    skip_retrieval: bool = False,
    prefetched_retrieval: dict[str, Any] | None = None,
) -> SqlPlan:
    validate_planning_request(req)

    retrieval = prefetched_retrieval or {"ok": False, "hits": [], "tables": [], "hint_extra": ""}
    if not skip_retrieval and not prefetched_retrieval:
        max_docs = req.retrievalScope.maxDocuments
        if _TEXT2SQL_COMPACT:
            max_docs = min(max_docs or 30, 12)
        retrieval = await retrieve_authorized_schema(
            req.question,
            tenant_id=req.tenantId,
            datasource_id=req.datasourceId,
            max_documents=max_docs,
            allowed_schemas=req.retrievalScope.allowedSchemas or None,
            fail_closed=False,
        )

    hint = req.retrievedSchema or str(retrieval.get("hint_extra") or "")
    semantic_ctx = ""
    try:
        from nanobase_awel.retrieval.semantic import retrieve_semantic_context

        sem = await retrieve_semantic_context(
            req.question, tenant_id=req.tenantId, datasource_id=req.datasourceId
        )
        semantic_ctx = str(sem.get("hint_extra") or "")
    except Exception:
        semantic_ctx = ""

    guidance = build_planning_guidance(
        req.question,
        list(retrieval.get("tables") or []) + list(req.allowedTables or []),
    )

    # Budget blocks BEFORE assembly, schema-first. The previous post-assembly
    # slice cut the tail of the prompt — which is the authorized schema block
    # whenever conversation/comments are absent (i.e. almost always).
    truncated_blocks: list[str] = []
    schema_hint_text = (req.schemaHint or "").strip()
    if _TEXT2SQL_COMPACT:
        total_budget = max(_TEXT2SQL_CONTEXT_CHARS, 4000)
        semantic_ctx, cut = _trim_at_line(semantic_ctx, 2000)
        if cut:
            truncated_blocks.append("semantic_catalog")
        guidance, cut = _trim_at_line(guidance or "", 1200)
        if cut:
            truncated_blocks.append("query_guidance")
        overhead = min(len(req.question), 2000) + len(semantic_ctx) + len(guidance) + 400
        schema_budget = max(3000, total_budget - overhead)
        # Curated schemaHint is authoritative — it gets first claim on budget.
        if schema_hint_text:
            schema_hint_text, cut = _trim_at_line(
                schema_hint_text, max(1500, schema_budget // 2) if hint else schema_budget
            )
            if cut:
                truncated_blocks.append("schema_hint")
        hint_budget = max(800, schema_budget - len(schema_hint_text))
        hint, cut = _trim_at_line(hint, hint_budget)
        if cut:
            truncated_blocks.append("retrieved_schema")
        retrieval = {**retrieval, "hint_extra": hint}

    context_blocks = build_sanitized_context(
        question=req.question,
        schema_hint=schema_hint_text,
        retrieval={**retrieval, "hint_extra": hint},
        conversation_turns=req.conversationContext.recentTurns,
        semantic_context=semantic_ctx or None,
        planning_guidance=guidance or None,
    )
    # Safety net only — sized so it can never reach the schema block.
    if _TEXT2SQL_COMPACT and len(context_blocks) > _TEXT2SQL_CONTEXT_CHARS * 3:
        context_blocks = context_blocks[: _TEXT2SQL_CONTEXT_CHARS * 3]
        truncated_blocks.append("tail_overflow")

    dialect_norm = normalize_dialect(req.dialect)
    system, user_tpl = sql_plan_prompts(dialect=req.dialect)
    if _TEXT2SQL_COMPACT:
        system = (
            system
            + f"\nHard constraints: {_DIALECT_STMT_RULE[dialect_norm]}. No semicolon chains. "
            "JSON only with a single SELECT/WITH in sql. "
            f"{DIALECT_CASE_INSENSITIVE_RULE[dialect_norm]}"
        )
    user = render_simple(user_tpl, context_blocks=context_blocks, question=req.question)

    try:
        llm_meta: dict[str, Any] = {}
        raw = await chat_completion(
            system, user, temperature=0.0, max_tokens=_PLAN_MAX_TOKENS, purpose="sql_plan", meta=llm_meta
        )
        length_retry = False
        if llm_meta.get("finish_reason") == "length":
            # Completion was cut mid-output — retry with a doubled budget instead
            # of letting the parser salvage a truncated statement.
            length_retry = True
            raw = await chat_completion(
                system,
                user,
                temperature=0.0,
                max_tokens=min(_PLAN_MAX_TOKENS * 2, 4096),
                purpose="sql_plan",
            )
        try:
            plan = parse_sql_plan(
                raw,
                prompt_version=req.generation.promptVersion,
                model_profile=req.generation.modelProfile,
                metadata_version=req.metadataVersion,
            )
        except WorkflowError as pe:
            if pe.code != OUTPUT_PARSE_FAILED:
                raise
            # One forced retry when the model returns prose / broken JSON under load.
            retry_user = (
                user
                + "\n\nHARD REQUIREMENT: previous output was not valid JSON. "
                "Reply with ONLY one JSON object: status=PLANNED and sql=single SELECT/WITH "
                "(or status=AMBIGUOUS with clarificationQuestion). No markdown."
            )
            raw = await chat_completion(
                system, retry_user, temperature=0.0, max_tokens=_PLAN_MAX_TOKENS, purpose="sql_plan"
            )
            plan = parse_sql_plan(
                raw,
                prompt_version=req.generation.promptVersion,
                model_profile=req.generation.modelProfile,
                metadata_version=req.metadataVersion,
            )
            plan.warnings = [*(plan.warnings or []), "parse_retry_forced"]
        # Model sometimes claims AMBIGUOUS even when retrieval tables exist.
        tables_available = bool(retrieval.get("tables") or req.allowedTables)
        if plan.status == PlanStatus.AMBIGUOUS and tables_available and not plan.sql:
            retry_user = (
                user
                + "\n\nHARD REQUIREMENT: authorized_schema_context already lists tables. "
                "Do NOT ask for schema. status must be PLANNED with a single PostgreSQL SELECT/WITH "
                "unless a date range is truly missing for a large fact scan — then ask only for dates."
            )
            raw2 = await chat_completion(
                system, retry_user, temperature=0.0, max_tokens=_PLAN_MAX_TOKENS, purpose="sql_plan"
            )
            plan2 = parse_sql_plan(
                raw2,
                prompt_version=req.generation.promptVersion,
                model_profile=req.generation.modelProfile,
                metadata_version=req.metadataVersion,
            )
            if plan2.status == PlanStatus.PLANNED and plan2.sql:
                plan = plan2
                plan.warnings = [*(plan.warnings or []), "ambiguous_retry_forced"]
            elif plan2.status == PlanStatus.AMBIGUOUS and plan2.clarificationQuestion:
                plan = plan2
                plan.warnings = [*(plan.warnings or []), "ambiguous_date_clarification"]
    except WorkflowError:
        raise
    except Exception as e:
        raise WorkflowError(OUTPUT_PARSE_FAILED, f"Planlama başarısız: {e}") from e

    # Surface degraded context to callers/telemetry — silent starvation is how
    # "the model invents columns" bugs stay invisible.
    if truncated_blocks:
        plan.warnings = [*(plan.warnings or []), f"context_truncated:{','.join(truncated_blocks)}"]
    if length_retry:
        plan.warnings = [*(plan.warnings or []), "completion_length_retry"]
    if retrieval.get("error") or (not retrieval.get("ok") and not skip_retrieval and not req.retrievedSchema):
        plan.warnings = [*(plan.warnings or []), "schema_retrieval_degraded"]

    # Force dialect/workflow from request for specialized profiles
    dialect_l = (req.dialect or "").lower()
    if dialect_l == "oracle":
        plan.dialect = "oracle"
        plan.workflow = "nanobase-oracle-sql-plan-v1"
        plan.promptVersion = req.generation.promptVersion or "sql-plan-v1-oracle"
    elif dialect_l in ("odata", "s4_odata", "sap_odata"):
        plan.dialect = "odata"
        plan.workflow = "nanobase-s4-odata-plan-v1"
        plan.promptVersion = req.generation.promptVersion or "sql-plan-v1-s4-odata"
    elif dialect_l in ("hana", "sap_hana"):
        plan.dialect = "hana"
        plan.workflow = "nanobase-hana-sql-plan-v1"
        plan.promptVersion = req.generation.promptVersion or "sql-plan-v1-hana"
    elif dialect_l in ("mssql", "tsql", "sqlserver"):
        plan.dialect = "mssql"
        plan.workflow = "nanobase-mssql-sql-plan-v1"
        plan.promptVersion = req.generation.promptVersion or "sql-plan-v1-mssql"
    else:
        plan.workflow = PLAN_WORKFLOW
    plan.retrieval_used = bool(retrieval.get("hits") or hint)

    allowed = set(req.allowedTables) | set(retrieval.get("tables") or [])
    if plan.status == PlanStatus.PLANNED:
        plan = validate_plan_references(
            plan,
            allowed_tables=allowed or None,
            context_text=context_blocks,
            table_columns=retrieval.get("table_columns") or None,
            dialect=plan.dialect,
        )

    return plan
