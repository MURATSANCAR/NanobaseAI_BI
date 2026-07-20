from __future__ import annotations

from nanobase_awel.operators.sql_shape_guard import (
    extract_table_refs,
    guard_sql_shape,
    unwrap_select_star_subquery,
)


def test_unwrap_select_star_from_with():
    sql = """
    SELECT * FROM (
      WITH x AS (SELECT id FROM public.customers)
      SELECT id FROM x
    ) AS q
    """
    out, ok = unwrap_select_star_subquery(sql)
    assert ok
    assert out.lower().lstrip().startswith("with")
    assert "select *" not in out.lower().split("from")[0]


def test_guard_blocks_unknown_table_when_allowlist():
    sql = "SELECT a.id FROM public.customers a JOIN purchase_orders_26 p ON p.id=a.id"
    r = guard_sql_shape(sql, allowed_tables=["public.customers", "public.orders"])
    assert r.blocked
    assert r.code == "TABLE_OR_VIEW_NOT_FOUND"
    assert "purchase_orders_26" in (r.message or "")


def test_guard_allows_known_and_unwraps():
    sql = "SELECT * FROM (SELECT id, name FROM public.customers LIMIT 5) t"
    r = guard_sql_shape(sql, allowed_tables=["public.customers"])
    assert not r.blocked
    assert "unwrapped_select_star_subquery" in r.warnings
    assert "select *" not in r.sql.lower().split("from")[0]


def test_extract_skips_cte_alias():
    sql = """
    WITH sales AS (SELECT id FROM public.faturalar)
    SELECT * FROM sales JOIN public.musteriler m ON m.id = sales.id
    """
    refs = extract_table_refs(sql)
    assert any("faturalar" in r for r in refs)
    assert any("musteriler" in r for r in refs)
    assert not any(r == "sales" or r.endswith(".sales") for r in refs)
