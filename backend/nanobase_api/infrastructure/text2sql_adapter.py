"""TextToSqlWorkflowPort — nanobase_awel plan / repair / explain (no DB execute)."""

from __future__ import annotations

from typing import Any, Optional

from nanobase_awel.contracts.explanation import ResultExplanationRequest
from nanobase_awel.contracts.planning import ConversationContext, SqlPlanningRequest
from nanobase_awel.contracts.repair import GatewayErrorSafe, SqlRepairRequest
from nanobase_awel.workflows.result_explain import run_result_explain
from nanobase_awel.workflows.sql_plan import run_sql_plan
from nanobase_awel.workflows.sql_repair import is_repairable, run_sql_repair


class WorkflowTextToSqlAdapter:
    async def generate_sql_plan(
        self,
        *,
        question: str,
        datasource_id: str,
        schema_hint: str,
        retrieved_schema: str | None = None,
        conversation_context: list[dict[str, Any]] | str | None = None,
        tenant_id: str = "default",
        execution_id: str = "",
        allowed_tables: list[str] | None = None,
        prefetched_retrieval: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        turns: list[dict[str, Any]] = []
        if isinstance(conversation_context, list):
            turns = conversation_context
        elif isinstance(conversation_context, str) and conversation_context.strip():
            turns = [{"role": "user", "content": conversation_context}]

        req = SqlPlanningRequest(
            executionId=execution_id,
            tenantId=tenant_id,
            datasourceId=datasource_id,
            question=question,
            schemaHint=schema_hint,
            retrievedSchema=retrieved_schema or "",
            conversationContext=ConversationContext(recentTurns=turns),
            allowedTables=allowed_tables or [],
        )
        plan = await run_sql_plan(
            req,
            skip_retrieval=bool(retrieved_schema or prefetched_retrieval),
            prefetched_retrieval=prefetched_retrieval,
        )
        return plan.to_legacy_dict()

    async def repair_sql(
        self,
        *,
        question: str,
        datasource_id: str,
        previous_sql: str,
        error_code: str,
        error_message: str,
        attempt: int,
        authorized_context: str = "",
        schema_hint: str = "",
        allowed_tables: list[str] | None = None,
        tenant_id: str = "default",
        execution_id: str = "",
    ) -> dict[str, Any]:
        if not is_repairable(error_code):
            return {"ok": False, "status": "FAILED", "sql": "", "code": error_code}
        req = SqlRepairRequest(
            executionId=execution_id,
            tenantId=tenant_id,
            datasourceId=datasource_id,
            question=question,
            previousSql=previous_sql,
            gatewayError=GatewayErrorSafe(code=error_code, safeMessage=error_message[:500]),
            attempt=attempt,
            authorizedContext=authorized_context,
            schemaHint=schema_hint,
            allowedTables=allowed_tables or [],
        )
        result = await run_sql_repair(req)
        out = result.to_legacy_dict()
        out["attempt"] = result.attempt
        out["previousErrorCode"] = result.previousErrorCode
        out["ok"] = bool(result.sql)
        return out

    async def explain_result(
        self,
        *,
        question: str,
        executed_sql: str,
        columns: list[Any],
        rows: list[Any],
        truncated: bool = False,
        datasource_id: str = "",
        tenant_id: str = "default",
        execution_id: str = "",
    ) -> dict[str, Any]:
        req = ResultExplanationRequest(
            executionId=execution_id,
            tenantId=tenant_id,
            datasourceId=datasource_id,
            question=question,
            executedSql=executed_sql,
            columns=columns,
            rows=rows,
            truncated=truncated,
        )
        explained = await run_result_explain(req)
        return explained.to_legacy_dict()

    # Alias matching plan port name
    async def plan_sql(self, **kwargs: Any) -> dict[str, Any]:
        return await self.generate_sql_plan(**kwargs)
