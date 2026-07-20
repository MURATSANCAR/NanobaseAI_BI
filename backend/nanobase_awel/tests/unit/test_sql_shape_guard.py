from __future__ import annotations

from nanobase_awel.operators.sql_shape_guard import (
    extract_table_refs,
    find_undefined_table_aliases,
    guard_sql_shape,
    unwrap_select_star_subquery,
)
from nanobase_awel.workflows.sql_repair import is_repairable


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


def test_guard_allows_table_named_in_question():
    sql = "SELECT d.ad, sb.miktar FROM public.depolar d JOIN public.stok_bakiyeleri sb ON sb.depo_id=d.id"
    r = guard_sql_shape(
        sql,
        allowed_tables=["public.faturalar"],
        question="stok_bakiyeleri + urunler + depolar: net stok",
    )
    assert not r.blocked
    assert any("depolar" in w for w in r.warnings)


def test_extract_skips_cte_alias():
    sql = """
    WITH sales AS (SELECT id FROM public.faturalar)
    SELECT * FROM sales JOIN public.musteriler m ON m.id = sales.id
    """
    refs = extract_table_refs(sql)
    assert any("faturalar" in r for r in refs)
    assert any("musteriler" in r for r in refs)
    assert not any(r == "sales" or r.endswith(".sales") for r in refs)


def test_extract_ignores_extract_from_and_comments():
    sql = """
    SELECT SUM(f.genel_toplam)
    FROM public.faturalar f
    WHERE EXTRACT(YEAR FROM f.fatura_tarihi) = 2026
      AND EXTRACT(YEAR FROM odeme_tarihi) = 2026
    /* join from the context to line items */
    """
    refs = extract_table_refs(sql)
    assert refs == ["public.faturalar"]
    assert "fatura_tarihi" not in " ".join(refs)
    assert "context" not in refs
    assert "line" not in refs


def test_extract_ignores_short_alias_columns():
    sql = """
    SELECT af.genel_toplam
    FROM public.alis_faturalari af
    JOIN public.butce_planlari bp ON bp.butce_kodu = af.butce_kodu
    WHERE EXTRACT(YEAR FROM af.fatura_tarihi) = 2026
    """
    refs = extract_table_refs(sql)
    assert set(refs) == {"public.alis_faturalari", "public.butce_planlari"}


def test_unwrap_select_star_with_trailing_limit():
    sql = """
    SELECT * FROM (
      WITH x AS (SELECT id FROM public.customers)
      SELECT id FROM x LIMIT 50
    ) AS q LIMIT 1000
    """
    out, ok = unwrap_select_star_subquery(sql)
    assert ok
    assert out.lower().lstrip().startswith("with")
    assert "limit 1000" not in out.lower().split("from")[0]


def test_undefined_alias_in_cte_blocked():
    # M05-style slip: m.il_id but FROM only exposes mc
    sql = """
    WITH musteri_ciro AS (
      SELECT m.id, m.il_id, m.unvan
      FROM public.musteriler AS m
    ),
    province_dist AS (
      SELECT m.il_id, SUM(mc.toplam_ciro) AS il_ciro
      FROM musteri_ciro AS mc
      GROUP BY m.il_id
    )
    SELECT il_id, il_ciro FROM province_dist
    """
    bad = find_undefined_table_aliases(sql)
    assert "m" in bad
    r = guard_sql_shape(sql, allowed_tables=["public.musteriler"])
    assert r.blocked
    assert r.code == "UNDEFINED_TABLE_ALIAS"
    assert is_repairable("UNDEFINED_TABLE_ALIAS")


def test_correlated_subquery_alias_not_false_positive():
    sql = """
    SELECT f.id
    FROM public.faturalar AS f
    WHERE EXISTS (
      SELECT 1 FROM public.musteriler AS m WHERE m.id = f.musteri_id
    )
    """
    assert find_undefined_table_aliases(sql) == []
    r = guard_sql_shape(
        sql, allowed_tables=["public.faturalar", "public.musteriler"]
    )
    assert not r.blocked


def test_valid_multi_alias_passes():
    sql = """
    SELECT mc.il_id, SUM(mc.toplam_ciro) AS il_ciro
    FROM musteri_ciro AS mc
    GROUP BY mc.il_id
    """
    # CTE name only — no physical tables; allowlist empty skips table check
    assert find_undefined_table_aliases(sql) == []

