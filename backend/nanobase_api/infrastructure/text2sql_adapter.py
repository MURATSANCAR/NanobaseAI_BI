"""Text-to-SQL engine adapter wrapping existing workflows."""

from __future__ import annotations

from typing import Any

from nanobase_api import workflows as workflows_mod


class WorkflowTextToSqlAdapter:
    async def generate_sql_plan(
        self,
        *,
        question: str,
        datasource_id: str,
        schema_hint: str,
        retrieved_schema: str | None = None,
        conversation_context: str | None = None,
    ) -> dict[str, Any]:
        return await workflows_mod.nl2sql_plan(
            question=question,
            schema_hint=schema_hint,
            retrieved_schema=retrieved_schema,
            conversation_context=conversation_context,
            datasource_context={"datasource_id": datasource_id},
        )

    async def explain_result(
        self,
        *,
        question: str,
        executed_sql: str,
        columns: list[Any],
        rows: list[Any],
        truncated: bool = False,
    ) -> dict[str, Any]:
        return await workflows_mod.result_explain(
            question=question,
            executed_sql=executed_sql,
            columns=columns,
            rows=rows,
            truncated=truncated,
        )
