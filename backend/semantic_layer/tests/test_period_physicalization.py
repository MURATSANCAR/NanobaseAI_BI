"""A question that spans years is resolved to tables by the compiler, not by the model."""
from __future__ import annotations

from datetime import date

from semantic_layer.models import ColumnProfile, SchemaProfile
from semantic_layer.runtime.guardrails import physicalize_sql


def _p(name, pattern, window, rows=1000, entity="STLINE", ctx=None):
    return SchemaProfile(datasource_id="d", table_name=name, table_pattern=pattern, entity=entity,
                         schema_name="dbo", columns=[ColumnProfile(name="TOTAL", data_type="decimal"),
                                                    ColumnProfile(name="DATE_", data_type="datetime")],
                         row_count=rows, time_window=window, context=ctx or {})


Y2021 = _p("LG_211_01_STLINE", "LG_{n0}_{n1}_STLINE", ("2021-01-01", "2025-12-31"), ctx={"n0": "211", "n1": "01"})
Y2026 = _p("LG_411_01_STLINE", "LG_{n0}_{n1}_STLINE", ("2026-01-01", "2026-08-17"), ctx={"n0": "411", "n1": "01"})


def test_one_year_reads_one_table():
    sql = physicalize_sql("SELECT SUM(TOTAL) FROM STLINE", [Y2021, Y2026], {},
                          period=(date(2026, 1, 1), date(2026, 12, 31)))
    assert "LG_411_01_STLINE" in sql
    assert "LG_211_01_STLINE" not in sql
    assert "UNION" not in sql.upper()


def test_a_span_across_the_boundary_reads_both_as_one_relation():
    sql = physicalize_sql("SELECT SUM(TOTAL) FROM STLINE", [Y2021, Y2026], {},
                          period=(date(2025, 1, 1), date(2026, 12, 31)))
    assert "LG_211_01_STLINE" in sql and "LG_411_01_STLINE" in sql
    assert "UNION ALL" in sql.upper(), "years are added together, not deduplicated"
    assert sql.upper().count("SUM(") == 1, "the aggregate the model wrote is untouched"


def test_the_alias_the_model_wrote_survives_so_its_own_references_still_resolve():
    sql = physicalize_sql("SELECT sl.TOTAL FROM STLINE AS sl WHERE sl.DATE_ > '2025-01-01'",
                          [Y2021, Y2026], {}, period=(date(2025, 1, 1), date(2026, 12, 31)))
    assert " sl" in sql.lower() and "sl.".upper() in sql.upper()


def test_a_year_kept_twice_is_not_added_to_itself():
    """015 and 105 are the same 2015 under two company codes. Reading both doubles the year."""
    a = _p("LG_015_01_STLINE", "LG_{n0}_{n1}_STLINE", ("2015-01-01", "2015-12-31"), rows=2538618, ctx={"n0": "015", "n1": "01"})
    b = _p("LG_105_01_STLINE", "LG_{n0}_{n1}_STLINE", ("2015-01-01", "2015-12-31"), rows=2565228, ctx={"n0": "105", "n1": "01"})
    sql = physicalize_sql("SELECT SUM(TOTAL) FROM STLINE", [a, b], {},
                          period=(date(2015, 1, 1), date(2015, 12, 31)))
    assert ("LG_105_01_STLINE" in sql) != ("LG_015_01_STLINE" in sql), "exactly one copy of the year"
    assert "UNION" not in sql.upper()


def test_a_view_or_a_copy_is_never_unioned_in_as_if_it_were_another_year():
    """The same entity also exists as a view (LV_) and as a partial copy (MS_) under other prefixes.
    Those are not other years of it, and adding them to the real table returns several times the real
    figure. Between two plain tables of the same shape the fuller one stands for the entity — there
    is no general signal that says one prefix is the vendor's and another is somebody's export, and
    on this schema the live table is the larger one by an order of magnitude."""
    live = _p("LG_411_01_STLINE", "LG_{n0}_{n1}_STLINE", ("2026-01-01", "2026-08-17"),
              rows=12195380, ctx={"n0": "411", "n1": "01"})
    view = _p("LV_411_01_STLINE", "LV_{n0}_{n1}_STLINE", ("2026-01-01", "2026-08-17"), rows=None, ctx={"n0": "411", "n1": "01"})
    copy = _p("MS_411_01_STLINE", "MS_{n0}_{n1}_STLINE", ("2026-01-01", "2026-08-17"), rows=935445, ctx={"n0": "411", "n1": "01"})
    sql = physicalize_sql("SELECT SUM(TOTAL) FROM STLINE", [live, view, copy], {},
                          period=(date(2026, 1, 1), date(2026, 12, 31)))
    assert "LG_411_01_STLINE" in sql
    assert "LV_411_01_STLINE" not in sql and "MS_411_01_STLINE" not in sql
    assert "UNION" not in sql.upper(), "a view and a copy are not years to add together"


def test_a_backup_never_stands_for_an_entity_however_many_rows_it_has():
    """Rows break a tie between plain tables; a name that says "backup" is not in that tie at all."""
    live = _p("LG_411_01_STLINE", "LG_{n0}_{n1}_STLINE", ("2026-01-01", "2026-08-17"), rows=20559,
              ctx={"n0": "411", "n1": "01"})
    bckp = _p("LG_411_01_STLINE_yedek1", "LG_{n0}_{n1}_STLINE_YEDEK1", ("2026-01-01", "2026-08-17"),
              rows=1143737, ctx={"n0": "411", "n1": "01"})
    sql = physicalize_sql("SELECT SUM(TOTAL) FROM STLINE", [bckp, live], {},
                          period=(date(2026, 1, 1), date(2026, 12, 31)))
    assert "yedek" not in sql.lower()


def test_no_period_asked_behaves_exactly_as_before():
    sql = physicalize_sql("SELECT SUM(TOTAL) FROM STLINE", [Y2021, Y2026], {})
    assert "UNION" not in sql.upper(), "without a period nothing here changes"


def test_a_physical_name_the_model_wrote_itself_is_left_alone():
    """A model given the physical table names still writes them; that must keep working."""
    sql = physicalize_sql("SELECT SUM(TOTAL) FROM dbo.LG_411_01_STLINE", [Y2021, Y2026], {},
                          period=(date(2025, 1, 1), date(2026, 12, 31)))
    assert "LG_411_01_STLINE" in sql


def test_a_model_that_spread_the_years_itself_is_not_spread_again():
    """The prompt tells the model which table holds which year, so it writes the UNION itself. If
    each branch is then expanded to the whole span again, every year is added to itself and the
    answer comes back at exactly twice the real figure with nothing about it looking wrong."""
    import re

    sql = ("SELECT SUM(TOTAL) FROM (SELECT TOTAL FROM [dbo].[LG_211_01_STLINE] "
           "UNION ALL SELECT TOTAL FROM [dbo].[LG_411_01_STLINE]) AS STLINE")
    out = physicalize_sql(sql, [Y2021, Y2026], {}, period=(date(2025, 1, 1), date(2026, 12, 31)))
    names = re.findall(r"\[dbo\]\.\[([A-Za-z0-9_]+)\]", out)
    assert sorted(names) == ["LG_211_01_STLINE", "LG_411_01_STLINE"], names
    assert len(names) == len(set(names)), "a year must not be added to itself"


def test_a_model_that_named_one_year_of_a_wider_question_is_given_the_rest():
    """The case the expansion is for: the question spans two tables and the model named one."""
    import re

    out = physicalize_sql("SELECT SUM(TOTAL) FROM [dbo].[LG_411_01_STLINE]", [Y2021, Y2026], {},
                          period=(date(2025, 1, 1), date(2026, 12, 31)))
    names = re.findall(r"\[dbo\]\.\[([A-Za-z0-9_]+)\]", out)
    assert sorted(names) == ["LG_211_01_STLINE", "LG_411_01_STLINE"], names


def test_the_model_is_told_how_far_the_data_reaches_even_though_it_picks_no_year():
    """Taking the year-to-table map out of the prompt took the coverage with it, and the model drew
    the obvious conclusion from a prompt naming only LG_411: asked how this year compares with last,
    it replied that there is no last year — with five years of it in tables the compiler supplies."""
    from semantic_layer.models import SemanticQuery
    from semantic_layer.runtime.compiler import ExistingCompiler

    c = ExistingCompiler(None, [Y2021, Y2026], {}, dialect="tsql")
    q = SemanticQuery(question="geçen yıla göre bu yıl", tenant_id="t", datasource_id="d")
    block = c.period_block(q, ["STLINE"])
    assert "2021-01-01" in block and "2026" in block, block
    assert "LG_211_01_STLINE" not in block, "the table map stays out; only the span goes in"
    assert "UNION ALL" in block, "and it is still told not to write the union itself"


def test_an_unmeasured_table_does_not_join_a_year_that_is_already_answered():
    """A table whose period was never measured cannot be ruled out — but carried along regardless it
    joined every question about every year, and a 2015 total came back as three years added
    together. Unknown is a reason to keep a table when nothing else answers, not to add it to
    something that does."""
    from datetime import date

    olculen = _p("LG_105_01_INVOICE", "LG_{n0}_{n1}_INVOICE", ("2015-01-01", "2015-12-31"),
                 rows=48194, ctx={"n0": "105", "n1": "01"})
    olculen.entity = "INVOICE"
    olculmeyen = _p("LG_411_01_INVOICE", "LG_{n0}_{n1}_INVOICE", None, rows=81801,
                    ctx={"n0": "411", "n1": "01"})
    olculmeyen.entity = "INVOICE"
    from semantic_layer.runtime.periods import tables_for

    sec = tables_for([olculen, olculmeyen], date(2015, 1, 1), date(2016, 1, 1))
    assert [p.table_name for p in sec] == ["LG_105_01_INVOICE"], [p.table_name for p in sec]

    # and with nothing measured, the unmeasured table is still the best there is
    yalniz = tables_for([olculmeyen], date(2015, 1, 1), date(2016, 1, 1))
    assert [p.table_name for p in yalniz] == ["LG_411_01_INVOICE"]
