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
from nanobase_awel.workflows.sql_plan import DIALECT_CASE_INSENSITIVE_RULE, normalize_dialect


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

    dialect_norm = normalize_dialect(req.dialect)
    # Dialect MUST flow into the repair prompt — repairing an Oracle/HANA error
    # with the PostgreSQL prompt regenerates LIMIT/ILIKE and can never converge.
    system, user_tpl = sql_repair_prompts(dialect=req.dialect)
    system = system + f"\n{DIALECT_CASE_INSENSITIVE_RULE[dialect_norm]}"
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
    # Stamp dialect from the request like run_sql_plan does — never trust the
    # model's own dialect claim on the repair path.
    dialect_l = (req.dialect or "postgres").lower().replace("postgresql", "postgres")
    if dialect_l in ("odata", "s4_odata", "sap_odata"):
        plan.dialect = "odata"
    elif dialect_l in ("hana", "sap_hana"):
        plan.dialect = "hana"
    elif dialect_l == "oracle":
        plan.dialect = "oracle"
    elif dialect_l in ("mssql", "tsql", "sqlserver"):
        plan.dialect = "mssql"
    else:
        plan.dialect = "postgres"
    if plan.status == PlanStatus.PLANNED:
        plan = validate_plan_references(
            plan,
            allowed_tables=set(req.allowedTables) or None,
            context_text=req.authorizedContext or req.schemaHint,
            dialect=plan.dialect,
        )
    dump = plan.model_dump()
    dump.pop("workflow", None)
    return SqlRepairResult(
        **dump,
        workflow=REPAIR_WORKFLOW,
        attempt=req.attempt,
        previousErrorCode=req.gatewayError.code,
    )
