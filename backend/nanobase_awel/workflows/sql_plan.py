"""nanobase-sql-plan-v1 — SQL only, no DB execute."""

from __future__ import annotations

from typing import Any

from nanobase_awel import PLAN_WORKFLOW
from nanobase_awel.contracts.errors import OUTPUT_PARSE_FAILED, WorkflowError
from nanobase_awel.contracts.planning import PlanStatus, SqlPlan, SqlPlanningRequest
from nanobase_awel.operators.input_validator import validate_planning_request
from nanobase_awel.operators.llm_operator import chat_completion
from nanobase_awel.operators.prompt_builder import render_simple, sql_plan_prompts
from nanobase_awel.operators.schema_reference_validator import validate_plan_references
from nanobase_awel.operators.structured_parser import parse_sql_plan
from nanobase_awel.retrieval.authorized import build_sanitized_context, retrieve_authorized_schema


async def run_sql_plan(
    req: SqlPlanningRequest,
    *,
    skip_retrieval: bool = False,
    prefetched_retrieval: dict[str, Any] | None = None,
) -> SqlPlan:
    validate_planning_request(req)

    retrieval = prefetched_retrieval or {"ok": False, "hits": [], "tables": [], "hint_extra": ""}
    if not skip_retrieval and not prefetched_retrieval:
        retrieval = await retrieve_authorized_schema(
            req.question,
            tenant_id=req.tenantId,
            datasource_id=req.datasourceId,
            max_documents=req.retrievalScope.maxDocuments,
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

    context_blocks = build_sanitized_context(
        question=req.question,
        schema_hint=req.schemaHint,
        retrieval={**retrieval, "hint_extra": hint},
        conversation_turns=req.conversationContext.recentTurns,
        semantic_context=semantic_ctx or None,
    )

    system, user_tpl = sql_plan_prompts(dialect=req.dialect)
    user = render_simple(user_tpl, context_blocks=context_blocks, question=req.question)

    try:
        raw = await chat_completion(system, user, temperature=0.0, max_tokens=2048)
        plan = parse_sql_plan(
            raw,
            prompt_version=req.generation.promptVersion,
            model_profile=req.generation.modelProfile,
            metadata_version=req.metadataVersion,
        )
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
