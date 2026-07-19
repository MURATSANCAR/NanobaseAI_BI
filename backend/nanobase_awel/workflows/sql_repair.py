"""nanobase-sql-repair-v1 — controlled repair only."""

from __future__ import annotations

from nanobase_awel import REPAIR_WORKFLOW
from nanobase_awel.contracts.errors import (
    NON_REPAIRABLE_CODES,
    REPAIRABLE_CODES,
    REPAIR_LIMIT_EXCEEDED,
    REPAIR_NOT_ALLOWED,
    WorkflowError,
)
from nanobase_awel.contracts.planning import PlanStatus
from nanobase_awel.contracts.repair import SqlRepairRequest, SqlRepairResult
from nanobase_awel.operators.input_validator import validate_repair_request
from nanobase_awel.operators.llm_operator import chat_completion
from nanobase_awel.operators.prompt_builder import render_simple, sql_repair_prompts
from nanobase_awel.operators.schema_reference_validator import validate_plan_references
from nanobase_awel.operators.structured_parser import parse_sql_plan


def is_repairable(code: str) -> bool:
    if code in NON_REPAIRABLE_CODES:
        return False
    return code in REPAIRABLE_CODES or code.endswith("_NOT_FOUND")


async def run_sql_repair(req: SqlRepairRequest) -> SqlRepairResult:
    validate_repair_request(req)
    if not is_repairable(req.gatewayError.code):
        raise WorkflowError(REPAIR_NOT_ALLOWED, f"Repairable değil: {req.gatewayError.code}")
    if req.attempt > 2:
        raise WorkflowError(REPAIR_LIMIT_EXCEEDED, "Maksimum 2 repair denemesi.")

    system, user_tpl = sql_repair_prompts()
    user = render_simple(
        user_tpl,
        question=req.question,
        previous_sql=req.previousSql,
        error_code=req.gatewayError.code,
        error_message=req.gatewayError.safeMessage,
        attempt=str(req.attempt),
        context=req.authorizedContext or req.schemaHint,
    )
    raw = await chat_completion(
        system, user, temperature=0.0, max_tokens=2048, purpose="sql_repair"
    )
    plan = parse_sql_plan(
        raw,
        prompt_version=req.promptVersion,
        model_profile=req.modelProfile,
    )
    if plan.status == PlanStatus.PLANNED:
        plan = validate_plan_references(
            plan,
            allowed_tables=set(req.allowedTables) or None,
            context_text=req.authorizedContext or req.schemaHint,
        )
    dump = plan.model_dump()
    dump.pop("workflow", None)
    return SqlRepairResult(
        **dump,
        workflow=REPAIR_WORKFLOW,
        attempt=req.attempt,
        previousErrorCode=req.gatewayError.code,
    )
