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
        "4500" if _TEXT2SQL_PREFER in ("arctic", "text2sql") else "6500",
    )
)


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

    # Prefetched retrieval from chat may be large; compact for Text2SQL models.
    if _TEXT2SQL_COMPACT and retrieval.get("hits"):
        retrieval = {
            **retrieval,
            "hits": (retrieval.get("hits") or [])[:12],
            "hint_extra": str(retrieval.get("hint_extra") or hint)[:_TEXT2SQL_CONTEXT_CHARS],
        }
        hint = str(retrieval.get("hint_extra") or "")

    guidance = build_planning_guidance(
        req.question,
        list(retrieval.get("tables") or []) + list(req.allowedTables or []),
    )

    context_blocks = build_sanitized_context(
        question=req.question,
        schema_hint=req.schemaHint,
        retrieval={**retrieval, "hint_extra": hint},
        conversation_turns=req.conversationContext.recentTurns,
        semantic_context=semantic_ctx or None,
        planning_guidance=guidance or None,
    )
    if _TEXT2SQL_COMPACT and len(context_blocks) > _TEXT2SQL_CONTEXT_CHARS + 500:
        context_blocks = context_blocks[: _TEXT2SQL_CONTEXT_CHARS + 500]

    system, user_tpl = sql_plan_prompts(dialect=req.dialect)
    if _TEXT2SQL_COMPACT:
        system = (
            system
            + "\nHard constraints: ONE PostgreSQL statement only. No semicolon chains. "
            "JSON only with a single SELECT/WITH in sql."
        )
    user = render_simple(user_tpl, context_blocks=context_blocks, question=req.question)

    try:
        raw = await chat_completion(
            system, user, temperature=0.0, max_tokens=768, purpose="sql_plan"
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
                system, retry_user, temperature=0.0, max_tokens=768, purpose="sql_plan"
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
                system, retry_user, temperature=0.0, max_tokens=768, purpose="sql_plan"
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
    else:
        plan.workflow = PLAN_WORKFLOW
    plan.retrieval_used = bool(retrieval.get("hits") or hint)

    allowed = set(req.allowedTables) | set(retrieval.get("tables") or [])
    if plan.status == PlanStatus.PLANNED:
        plan = validate_plan_references(plan, allowed_tables=allowed or None, context_text=context_blocks)

    return plan
