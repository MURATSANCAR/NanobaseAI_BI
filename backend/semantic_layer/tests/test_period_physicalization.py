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


def test_only_the_relation_the_period_constrains_is_spread():
    """Dönem, sorunun tarihlediği satırlara aittir. Yanındaki referans tablosu hangi yıl sorulursa
    sorulsun aynı satırları tutar; o da yıllara yayılırsa her satır birden çok kez eşleşir ve rakam
    çarpılarak döner — sorguya bakan hiçbir şeyin yanlış olduğunu göremez."""
    items_old = _p("LG_211_ITEMS", "LG_{n0}_ITEMS", ("2010-01-01", "2026-01-19"), entity="ITEMS", ctx={"n0": "211"})
    items_new = _p("LG_411_ITEMS", "LG_{n0}_ITEMS", ("2010-01-01", "2026-08-17"), entity="ITEMS", ctx={"n0": "411"})
    sql = physicalize_sql(
        'SELECT SUM(s."TOTAL") FROM STLINE s JOIN ITEMS i ON i."LOGICALREF" = s."STOCKREF" '
        "WHERE s.\"DATE_\" >= '2025-01-01' AND s.\"DATE_\" < '2027-01-01'",
        [Y2021, Y2026, items_old, items_new], {}, period=(date(2025, 1, 1), date(2026, 12, 31)))
    assert "LG_211_01_STLINE" in sql and "LG_411_01_STLINE" in sql, sql   # dönemi taşıyan taraf yayılır
    # 2026-09-16: referans tablosu artık kilitli adımda yayılır — her yıl kendi firma kopyasının kartını
    # okur (LOGICALREF yalnız kopya içinde tekil) ve birleştirme firma etiketiyle sınırlanır; çoğaltma yok.
    assert sql.upper().count("LG_211_ITEMS") == 1 and sql.upper().count("LG_411_ITEMS") == 1, sql
    assert "__nb_firm = " in sql, sql


def _q4_tables():
    pay_old = _p("LG_211_01_PAYTRANS", "LG_{n0}_{n1}_PAYTRANS", ("2021-01-01", "2025-12-31"), entity="PAYTRANS", ctx={"n0": "211", "n1": "01"})
    pay_new = _p("LG_411_01_PAYTRANS", "LG_{n0}_{n1}_PAYTRANS", ("2026-01-01", "2026-08-17"), entity="PAYTRANS", ctx={"n0": "411", "n1": "01"})
    inv_old = _p("LG_211_01_INVOICE", "LG_{n0}_{n1}_INVOICE", ("2021-01-01", "2025-12-31"), entity="INVOICE", ctx={"n0": "211", "n1": "01"})
    inv_new = _p("LG_411_01_INVOICE", "LG_{n0}_{n1}_INVOICE", ("2026-01-01", "2026-08-17"), entity="INVOICE", ctx={"n0": "411", "n1": "01"})
    cl_old = _p("LG_211_CLCARD", "LG_{n0}_CLCARD", ("2010-01-01", "2026-01-19"), entity="CLCARD", ctx={"n0": "211"})
    cl_new = _p("LG_411_CLCARD", "LG_{n0}_CLCARD", ("2010-01-01", "2026-08-17"), entity="CLCARD", ctx={"n0": "411"})
    return [pay_old, pay_new, inv_old, inv_new, cl_old, cl_new]


def test_the_copy_tag_passes_through_a_subquery_that_lists_its_columns():
    """2026-09-16, soru 4: model faturaları `SELECT DISTINCT LOGICALREF, DATE_, CLIENTREF FROM INVOICE`
    alt sorgusuna aldı; etiket alt sorgunun kenarında kaldı ve 2026 faturaları 2021-25 ödeme planına
    LOGICALREF çakışmasıyla eşleşti (ortalama vade −750 gün). Etiket alt sorgudan taşınır, JOIN bağlanır."""
    sql = physicalize_sql(
        'SELECT c."SPECODE2", AVG(DATEDIFF(day, i."DATE_", p."DATE_")) FROM PAYTRANS p '
        'JOIN (SELECT DISTINCT "LOGICALREF", "DATE_", "CLIENTREF" FROM INVOICE WHERE "DATE_" >= \'2025-01-01\' AND "DATE_" < \'2027-01-01\') i '
        'ON i."LOGICALREF" = p."FICHEREF" JOIN CLCARD c ON c."LOGICALREF" = i."CLIENTREF" '
        'WHERE p."MODULENR" = 4 GROUP BY c."SPECODE2"',
        _q4_tables(), {}, period=(date(2025, 1, 1), date(2026, 12, 31)))
    low = sql.lower()
    assert "lg_211_01_paytrans" in low and "lg_411_01_paytrans" in low, sql
    assert low.count("__nb_firm as __nb_firm") == 1, sql          # the subquery now projects the tag
    assert low.count("__nb_firm = ") == 2, sql                     # i↔p and c↔i both bound to one copy


def test_the_copy_tag_passes_through_a_cte_read_under_another_alias():
    sql = physicalize_sql(
        'WITH kapanan AS (SELECT p."FICHEREF", i."CLIENTREF", i."DATE_" AS fatura_tarihi, p."DATE_" AS odeme_tarihi '
        'FROM PAYTRANS p JOIN INVOICE i ON i."LOGICALREF" = p."FICHEREF" WHERE i."DATE_" >= \'2025-01-01\' AND i."DATE_" < \'2027-01-01\') '
        'SELECT c."SPECODE2", AVG(DATEDIFF(day, k.fatura_tarihi, k.odeme_tarihi)) FROM kapanan k '
        'JOIN CLCARD c ON c."LOGICALREF" = k."CLIENTREF" GROUP BY c."SPECODE2"',
        _q4_tables(), {}, period=(date(2025, 1, 1), date(2026, 12, 31)))
    low = sql.lower()
    assert low.count("__nb_firm as __nb_firm") == 1, sql          # the CTE carries the tag out
    assert low.count("__nb_firm = ") == 2, sql                     # p↔i inside, k↔c outside


def test_a_grouped_subquery_carries_the_tag_in_its_group_by_and_a_total_does_not():
    grouped = physicalize_sql(
        'SELECT t."CLIENTREF", t.n FROM (SELECT "CLIENTREF", COUNT(*) AS n FROM INVOICE WHERE "DATE_" >= \'2025-01-01\' AND "DATE_" < \'2027-01-01\' GROUP BY "CLIENTREF") t '
        'JOIN CLCARD c ON c."LOGICALREF" = t."CLIENTREF"', _q4_tables(), {}, period=(date(2025, 1, 1), date(2026, 12, 31)))
    assert grouped.lower().count("__nb_firm = ") == 1 and "group by" in grouped.lower(), grouped
    total = physicalize_sql(
        'SELECT t.n, c."SPECODE2" FROM (SELECT COUNT(*) AS n FROM INVOICE WHERE "DATE_" >= \'2025-01-01\' AND "DATE_" < \'2027-01-01\') t '
        'JOIN CLCARD c ON 1 = 1', _q4_tables(), {}, period=(date(2025, 1, 1), date(2026, 12, 31)))
    assert "__nb_firm = " not in total, total


def test_a_lower_bound_alone_is_an_open_period_and_reads_every_copy_after_it():
    """2026-09-17, soru 7: `DATE_ >= '2015-01-01'` with no ceiling read the 2026 copy alone; 408.785
    invoices of 2021–2025 were silently missing from "which invoices"."""
    # a floor before the oldest copy asks for everything: with no period in the question that is the
    # current copy, by the same convention as no date at all (2026-09-17, eight copies and 700k rows)
    sql = physicalize_sql("SELECT COUNT(*) FROM STLINE s WHERE s.\"DATE_\" >= '2015-01-01'", [Y2021, Y2026], {}, period=None)
    assert "LG_411_01_STLINE" in sql and "LG_211_01_STLINE" not in sql, sql
    # a floor inside the data is a period the statement really asks for: both copies from there on
    sql = physicalize_sql("SELECT COUNT(*) FROM STLINE s WHERE s.\"DATE_\" >= '2024-01-01'", [Y2021, Y2026], {}, period=None)
    assert "LG_211_01_STLINE" in sql and "LG_411_01_STLINE" in sql, sql
    only_new = physicalize_sql("SELECT COUNT(*) FROM STLINE s WHERE s.\"DATE_\" >= '2026-03-01'", [Y2021, Y2026], {}, period=None)
    assert "LG_411_01_STLINE" in only_new and "LG_211_01_STLINE" not in only_new, only_new
    ceiling = physicalize_sql("SELECT COUNT(*) FROM STLINE s WHERE s.\"DATE_\" < '2025-06-01'", [Y2021, Y2026], {}, period=None)
    assert "LG_211_01_STLINE" in ceiling and "LG_411_01_STLINE" not in ceiling, ceiling


def test_copies_are_unioned_by_column_name_not_position():
    """2026-09-17: LG_171_PRODORD and LG_411_PRODORD carry the same columns in another order; `SELECT *`
    UNION ALL put a date under STATUS. Copies are projected by the names they share."""
    old = SchemaProfile(datasource_id="d", table_name="LG_211_01_STLINE", table_pattern="LG_{n0}_{n1}_STLINE", entity="STLINE", schema_name="dbo",
                        columns=[ColumnProfile(name="DATE_", data_type="datetime"), ColumnProfile(name="TOTAL", data_type="decimal"), ColumnProfile(name="OLDONLY", data_type="int")],
                        row_count=10, time_window=("2021-01-01", "2025-12-31"), context={"n0": "211", "n1": "01"})
    new = SchemaProfile(datasource_id="d", table_name="LG_411_01_STLINE", table_pattern="LG_{n0}_{n1}_STLINE", entity="STLINE", schema_name="dbo",
                        columns=[ColumnProfile(name="TOTAL", data_type="decimal"), ColumnProfile(name="DATE_", data_type="datetime"), ColumnProfile(name="NEWONLY", data_type="int")],
                        row_count=1000, time_window=("2026-01-01", "2026-08-17"), context={"n0": "411", "n1": "01"})
    sql = physicalize_sql("SELECT SUM(s.\"TOTAL\") FROM STLINE s WHERE s.\"DATE_\" >= '2025-01-01' AND s.\"DATE_\" < '2027-01-01'",
                          [old, new], {}, period=(date(2025, 1, 1), date(2026, 12, 31)))
    assert "SELECT *" not in sql.upper().replace("SELECT  *", "SELECT *"), sql
    assert sql.upper().count("[TOTAL], [DATE_]") == 2 or sql.upper().count("TOTAL, DATE_") == 2, sql
    assert "OLDONLY" not in sql and "NEWONLY" not in sql


def test_logo_empty_dates_are_not_a_period():
    sql = physicalize_sql("SELECT COUNT(*) FROM STLINE s WHERE s.\"DATE_\" > '1900-01-02'", [Y2021, Y2026], {}, period=None)
    assert "LG_411_01_STLINE" in sql and "LG_211_01_STLINE" not in sql, sql


def test_master_data_copies_that_all_begin_on_the_same_day_resolve_to_the_current_one():
    """2026-09-17, soru 7: PRCLIST/ITEMS/CLCARD are copied whole into every firm and all begin in 2010;
    'begins latest' tied and every copy was read — eight price lists joined to one year of invoices."""
    from semantic_layer.runtime.periods import tables_for
    copies = [_p(f"LG_{f}_PRCLIST", "LG_{n0}_PRCLIST", ("2014-12-29", end), entity="PRCLIST", ctx={"n0": f})
              for f, end in (("105", "2016-01-09"), ("201", "2020-12-31"), ("211", "2026-01-05"), ("411", "2026-08-12"))]
    assert [p.table_name for p in tables_for(copies, None, None)] == ["LG_411_PRCLIST"]


def test_the_current_copy_is_the_one_measured_furthest_forward_up_to_today():
    from semantic_layer.runtime.periods import tables_for
    # customers: copies whose windows begin on different old days — the one measured to 2026 is current
    cl = [_p(f"LG_{f}_CLCARD", "LG_{n0}_CLCARD", w, entity="CLCARD", ctx={"n0": f})
          for f, w in (("105", ("2014-11-18", "2016-01-15")), ("191", ("2010-01-01", "2020-01-16")), ("211", ("2010-01-01", "2026-03-12")), ("411", ("2010-01-01", "2026-08-16")))]
    assert [p.table_name for p in tables_for(cl, None, None)] == ["LG_411_CLCARD"]
    # lines: a forward-dated row pushes 2021–2025's window to 2030; clipped to today it loses to 2026
    st = [_p("LG_211_01_STLINE", "LG_{n0}_{n1}_STLINE", ("2021-01-01", "2030-03-20"), ctx={"n0": "211", "n1": "01"}),
          _p("LG_411_01_STLINE", "LG_{n0}_{n1}_STLINE", ("2026-01-01", "2027-03-23"), ctx={"n0": "411", "n1": "01"})]
    assert [p.table_name for p in tables_for(st, None, None)] == ["LG_411_01_STLINE"]


def test_a_card_table_alone_in_its_select_is_read_from_one_copy():
    """2026-09-18: "geçen yıl fatura kesilip bu yıl hiç kesilmemiş müşteriler" returned 67.308 rows for 33.573
    customers — CLCARD stood alone in FROM, the dated invoices only inside EXISTS, and the card table was
    read from both firm copies in step: every customer once per copy."""
    c21 = SchemaProfile(datasource_id="d", table_name="LG_211_CLCARD", table_pattern="LG_{n0}_CLCARD", entity="CLCARD", schema_name="dbo",
                        columns=[ColumnProfile(name="LOGICALREF", data_type="int"), ColumnProfile(name="CODE", data_type="varchar")], row_count=10, context={"n0": "211"})
    c41 = SchemaProfile(datasource_id="d", table_name="LG_411_CLCARD", table_pattern="LG_{n0}_CLCARD", entity="CLCARD", schema_name="dbo",
                        columns=[ColumnProfile(name="LOGICALREF", data_type="int"), ColumnProfile(name="CODE", data_type="varchar")], row_count=10, context={"n0": "411"})
    sql = physicalize_sql("SELECT c.CODE FROM CLCARD c WHERE EXISTS (SELECT 1 FROM STLINE s WHERE s.TOTAL > 0 AND s.DATE_ >= '2025-01-01' AND s.DATE_ < '2026-01-01') "
                          "AND NOT EXISTS (SELECT 1 FROM STLINE s2 WHERE s2.DATE_ >= '2026-01-01' AND s2.DATE_ < '2027-01-01')",
                          [Y2021, Y2026, c21, c41], {}, period=(date(2025, 1, 1), date(2026, 12, 31)))
    assert "LG_411_CLCARD" in sql and "LG_211_CLCARD" not in sql, sql
    joined = physicalize_sql("SELECT c.CODE, SUM(s.TOTAL) FROM STLINE s JOIN CLCARD c ON c.LOGICALREF = s.TOTAL GROUP BY c.CODE",
                             [Y2021, Y2026, c21, c41], {}, period=(date(2025, 1, 1), date(2026, 12, 31)))
    assert "LG_211_CLCARD" in joined and "LG_411_CLCARD" in joined, joined      # beside the dated table it stays in step


def test_an_undated_table_with_no_period_asked_is_read_from_the_newest_copy():
    """2026-09-18, soru 24 (doğrudan DB denetimi buldu): the risk-limit table has no date, so no copy had a measured
    window and *every* firm copy since 2015 was unioned — "customers over their limit" came from old books."""
    r105 = SchemaProfile(datasource_id="d", table_name="LG_105_01_CLRNUMS", table_pattern="LG_{n0}_{n1}_CLRNUMS", entity="CLRNUMS", schema_name="dbo",
                         columns=[ColumnProfile(name="ACCRISKLIMIT", data_type="float")], row_count=10, context={"n0": "105", "n1": "01"})
    r411 = SchemaProfile(datasource_id="d", table_name="LG_411_01_CLRNUMS", table_pattern="LG_{n0}_{n1}_CLRNUMS", entity="CLRNUMS", schema_name="dbo",
                         columns=[ColumnProfile(name="ACCRISKLIMIT", data_type="float")], row_count=10, context={"n0": "411", "n1": "01"})
    sql = physicalize_sql("SELECT COUNT(*) FROM CLRNUMS WHERE ACCRISKLIMIT > 0", [r105, r411], {})
    assert "LG_411_01_CLRNUMS" in sql and "LG_105_01_CLRNUMS" not in sql, sql


def test_the_catalogs_other_label_for_a_profiled_entity_resolves_to_the_same_tables():
    """2026-09-19, "geçen yıl alıp bu yıl hiç sipariş vermemiş müşteriler": the certified word pointed at
    LG_STLINE-style spelling while the profiles were relabelled to the bare name. The model wrote the name it
    was told and the server answered "Invalid object name"; the repair then moved to another table."""
    from semantic_layer.runtime.guardrails import allowed_tables
    sql = "SELECT COUNT(*) FROM LG_STLINE s WHERE s.DATE_ >= '2026-01-01' AND s.DATE_ < '2027-01-01'"
    out = physicalize_sql(sql, [Y2021, Y2026], {}, period=(date(2026, 1, 1), date(2027, 1, 1)))
    assert "LG_411_01_STLINE" in out and "LG_211_01_STLINE" not in out, out
    assert allowed_tables(sql, [Y2021, Y2026], {}, "tsql")[0]
    # the other direction: profiles under the prefixed label, SQL in the bare one
    a = _p("LG_211_01_STLINE", "LG_{n0}_{n1}_STLINE", ("2021-01-01", "2025-12-31"), entity="LG_STLINE", ctx={"n0": "211", "n1": "01"})
    b = _p("LG_411_01_STLINE", "LG_{n0}_{n1}_STLINE", ("2026-01-01", "2026-08-17"), entity="LG_STLINE", ctx={"n0": "411", "n1": "01"})
    out = physicalize_sql("SELECT COUNT(*) FROM STLINE s WHERE s.DATE_ >= '2026-01-01'", [a, b], {}, period=(date(2026, 1, 1), date(2027, 1, 1)))
    assert "LG_411_01_STLINE" in out, out
    # never a guess: a name nothing answers to stays as written and is still refused
    assert not allowed_tables("SELECT 1 FROM LG_NOPE", [Y2021, Y2026], {}, "tsql")[0]


def test_an_undated_table_beside_a_date_test_elsewhere_reads_the_current_copy():
    """A FIFO aging: the date test sits in the outer SELECT over a CTE, the balance and the payment plan
    carry none. Left on the biggest copy they read 2021–2025 and every open amount was 90+ days old."""
    old = _p("LG_211_01_STLINE", "LG_{n0}_{n1}_STLINE", ("2021-01-01", "2025-12-31"), rows=9000, ctx={"n0": "211", "n1": "01"})
    sql = physicalize_sql("WITH A AS (SELECT DATE_, TOTAL FROM STLINE) "
                          "SELECT SUM(A.TOTAL) FROM A WHERE DATEDIFF(day, A.DATE_, CAST(GETDATE() AS date)) <= 30",
                          [old, Y2026], {})
    assert "LG_411_01_STLINE" in sql and "LG_211_01_STLINE" not in sql
