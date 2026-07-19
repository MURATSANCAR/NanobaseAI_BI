"""Backward-compatible facade → nanobase_awel (no customer DB execute).

DB-GPT chat_with_db_execute is never used here.
"""

from __future__ import annotations

from typing import Any, Optional

from nanobase_api.infrastructure.text2sql_adapter import WorkflowTextToSqlAdapter

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

_adapter = WorkflowTextToSqlAdapter()


async def nl2sql_plan(
    *,
    question: str,
    conversation_context: list[dict[str, Any]] | None = None,
    datasource_context: dict[str, Any] | None = None,
    allowed_schemas: list[str] | None = None,
    allowed_tables: list[str] | None = None,
    schema_hint: str | None = None,
    retrieved_schema: str | None = None,
) -> dict[str, Any]:
    from nanobase_api.infrastructure.active_source import prefer_datasource_id

    ds_id = prefer_datasource_id((datasource_context or {}).get("datasource_id"))
    return await _adapter.generate_sql_plan(
        question=question,
        datasource_id=ds_id,
        schema_hint=schema_hint or DEFAULT_SCHEMA_HINT,
        retrieved_schema=retrieved_schema,
        conversation_context=conversation_context,
        allowed_tables=allowed_tables,
    )


async def result_explain(
    *,
    question: str,
    executed_sql: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    truncated: bool = False,
) -> dict[str, Any]:
    return await _adapter.explain_result(
        question=question,
        executed_sql=executed_sql,
        columns=columns,
        rows=rows,
        truncated=truncated,
    )
