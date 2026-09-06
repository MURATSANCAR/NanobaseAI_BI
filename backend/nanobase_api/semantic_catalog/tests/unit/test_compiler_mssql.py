"""MetricCompiler T-SQL (SQL Server) output — TOP, ISNULL, DATEFROMPARTS buckets, N'' literals."""

from __future__ import annotations

from nanobase_api.semantic_catalog.domain.filter_rule import FilterExpression, FilterRule
from nanobase_api.semantic_catalog.domain.metric import Metric, SourceExpression, TimeSemantics
from nanobase_api.semantic_catalog.domain.status import AssetStatus
from nanobase_api.semantic_catalog.infrastructure.metric_compiler import CompileRequest, MetricCompiler


def _metric():
    filt_sales = FilterRule(
        id="fr1", tenant_id="t", datasource_id="logo", code="sales_invoices_only", description="",
        expression=FilterExpression(field="dbo.LG_411_01_INVOICE.TRCODE", operator="IN", values=[7, 8, 9]),
        mandatory=True, status=AssetStatus.PUBLISHED,
    )
    filt_cancel = FilterRule(
        id="fr2", tenant_id="t", datasource_id="logo", code="not_cancelled", description="",
        expression=FilterExpression(field="dbo.LG_411_01_INVOICE.CANCELLED", operator="=", values=[0]),
        mandatory=True, status=AssetStatus.PUBLISHED,
    )
    m = Metric(
        id="m1", tenant_id="t", datasource_id="logo", code="total_revenue", name="Toplam Ciro", description="",
        aggregation="SUM", source=SourceExpression(table="dbo.LG_411_01_INVOICE", column="NETTOTAL"),
        default_filter_codes=["sales_invoices_only", "not_cancelled"], null_policy="ZERO",
        time=TimeSemantics(time_field="dbo.LG_411_01_INVOICE.DATE_"), status=AssetStatus.PUBLISHED,
    )
    return m, [filt_sales, filt_cancel]


def test_mssql_scalar():
    m, f = _metric()
    r = MetricCompiler().compile(CompileRequest(metric=m, filters=f, dialect="mssql"))
    sql = r.sql
    assert sql.startswith("SELECT\n    SUM(ISNULL(l.NETTOTAL, 0)) AS total_revenue")
    assert "FROM dbo.LG_411_01_INVOICE l" in sql
    assert "l.TRCODE IN (7, 8, 9)" in sql and "l.CANCELLED = 0" in sql
    assert not sql.endswith(";") and "LIMIT" not in sql and '"' not in sql


def test_mssql_month_series_with_period_and_dimension():
    m, f = _metric()
    r = MetricCompiler().compile(
        CompileRequest(metric=m, filters=f, dialect="mssql", time_grain="month",
                       period={"from": "2023-09-01", "to": "2026-09-01"}, dimension_filters={"CITY": "İstanbul"})
    )
    sql = r.sql
    assert "DATEFROMPARTS(YEAR(l.DATE_), MONTH(l.DATE_), 1) AS period" in sql
    assert "GROUP BY DATEFROMPARTS(YEAR(l.DATE_), MONTH(l.DATE_), 1)" in sql
    assert "ORDER BY DATEFROMPARTS(YEAR(l.DATE_), MONTH(l.DATE_), 1) ASC" in sql
    assert "l.DATE_ >= '2023-09-01'" in sql and "l.DATE_ < '2026-09-01'" in sql
    assert "l.CITY = N'İstanbul'" in sql
    assert r.logical_plan["dialect"] == "mssql" and r.logical_plan["timeGrain"] == "month"


def test_mssql_top_n_ranking():
    m, f = _metric()
    r = MetricCompiler().compile(CompileRequest(metric=m, filters=f, dialect="mssql", group_by=["CLIENTREF"], limit=10))
    sql = r.sql
    assert sql.startswith("SELECT TOP 10\n")
    assert "GROUP BY l.CLIENTREF" in sql
    assert "ORDER BY SUM(ISNULL(l.NETTOTAL, 0)) DESC, l.CLIENTREF ASC" in sql


def test_mssql_fingerprint_stable_and_parseable():
    m, f = _metric()
    c = MetricCompiler()
    a = c.compile(CompileRequest(metric=m, filters=f, dialect="tsql", time_grain="quarter"))
    b = c.compile(CompileRequest(metric=m, filters=f, dialect="sqlserver", time_grain="quarter"))
    assert a.sql == b.sql and a.ast_fingerprint == b.ast_fingerprint
    import sqlglot

    sqlglot.parse_one(a.sql, read="tsql")  # must be valid T-SQL
