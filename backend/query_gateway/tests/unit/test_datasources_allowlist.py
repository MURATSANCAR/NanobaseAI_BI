"""BI_REPORTING_TABLES allowlist coverage.

Regression for a real deploy gap found 2026-08-11: the deterministic
semantic-metric SQL for total_revenue/total_quantity_sold queries
public.v_sales_revenue_lines, but the view wasn't in this allowlist — the
Gateway rejected it with "table not allowlisted", which then fell into the
LLM-based repair loop, defeating the entire point of a byte-identical
compiled query (a deterministic query should never need repair).
"""

from __future__ import annotations

from query_gateway.infrastructure.database.datasources import BI_REPORTING_TABLES


def test_sales_revenue_lines_view_is_allowlisted():
    assert "v_sales_revenue_lines" in BI_REPORTING_TABLES
    assert "analytics.v_sales_revenue_lines" in BI_REPORTING_TABLES
    assert "public.v_sales_revenue_lines" in BI_REPORTING_TABLES
