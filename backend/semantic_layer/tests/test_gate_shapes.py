"""The same correct answer in every SQL shape the gate must accept, and the shapes it must refuse.

Measured 2026-09-15: 13 of 17 correct shapes were refused, 1 of 11 wrong shapes accepted. Each refusal
was a real answer thrown away — the CTE-first shape is the one the critic asks the model to write.
Every case is a hard assertion; a case the gate gets wrong goes into WRONG_TODAY as a strict xfail
until it is fixed, never silently. Design: docs/architecture/semantic-gate-design.md.
"""
from datetime import date

import pytest

from semantic_layer.models import Mapping, ResolvedSlot, SemanticQuery, TemporalSlot
from semantic_layer.runtime.audit import unmet_obligations

T = "LG_411_01_INVOICE"
F = '"CANCELLED" = 0'
P = "\"DATE_\" >= '2026-01-01' AND \"DATE_\" < '2027-01-01'"
P_PREV = "\"DATE_\" >= '2025-01-01' AND \"DATE_\" < '2026-01-01'"


def plan(*, comparison=False):
    sq = SemanticQuery(question="x", tenant_id="t", datasource_id="d",
                       slots=[ResolvedSlot("iptal edilmemiş", "DEFAULT_FILTER", "CERTIFIED",
                                           mapping=Mapping("", "INVOICE", "LG_{n0}_{n1}_INVOICE", column="CANCELLED", operator="=", values=["0"]))],
                       temporal=[TemporalSlot("2026", "YEAR", date(2026, 1, 1), date(2027, 1, 1))],
                       temporal_binding={"entity": "INVOICE", "column": "DATE_"})
    if comparison:
        sq.temporal.append(TemporalSlot("2025", "YEAR", date(2025, 1, 1), date(2026, 1, 1)))
        sq.comparison = {"current": {"start": "2026-01-01", "end": "2027-01-01"},
                         "reference": {"start": "2025-01-01", "end": "2026-01-01"}, "entity": "INVOICE", "dateColumn": "DATE_"}
    return sq


CTE_A = f'a AS (SELECT MONTH("DATE_") ay, SUM(NETTOTAL) t FROM {T} WHERE {F} AND {P} GROUP BY MONTH("DATE_"))'
CTE_B = f'b AS (SELECT MONTH("DATE_") ay, COUNT(*) n FROM {T} WHERE {F} AND {P} GROUP BY MONTH("DATE_"))'
CTE_B_UNFILTERED = f'b AS (SELECT MONTH("DATE_") ay, COUNT(*) n FROM {T} WHERE {P} GROUP BY MONTH("DATE_"))'

ACCEPT = {
    "flat": f"SELECT SUM(NETTOTAL) FROM {T} WHERE {F} AND {P}",
    "flat_alias": f"SELECT SUM(i.NETTOTAL) FROM {T} i WHERE i.{F} AND i.\"DATE_\" >= '2026-01-01' AND i.\"DATE_\" < '2027-01-01'",
    "filter_in_list": f"SELECT SUM(NETTOTAL) FROM {T} WHERE \"CANCELLED\" IN (0) AND {P}",
    "cte_unfiltered_outer_where": f"WITH f AS (SELECT * FROM {T}) SELECT SUM(NETTOTAL) FROM f WHERE {F} AND {P}",
    "cte_filtered": f"WITH f AS (SELECT * FROM {T} WHERE {F} AND {P}) SELECT SUM(NETTOTAL) FROM f",
    "cte_grouped": f"WITH m AS (SELECT MONTH(\"DATE_\") ay, SUM(NETTOTAL) t FROM {T} WHERE {F} AND {P} GROUP BY MONTH(\"DATE_\")) SELECT ay, t FROM m ORDER BY ay",
    "cte_two_used_both_filtered": f"WITH {CTE_A}, {CTE_B} SELECT a.ay, a.t, b.n FROM a JOIN b ON a.ay = b.ay",
    "derived_table": f"SELECT SUM(x.NETTOTAL) FROM (SELECT NETTOTAL FROM {T} WHERE {F} AND {P}) x",
    "join_on_filter": f"SELECT SUM(i.NETTOTAL) FROM {T} i JOIN LG_411_CLCARD c ON c.LOGICALREF = i.CLIENTREF AND i.{F} WHERE i.\"DATE_\" >= '2026-01-01' AND i.\"DATE_\" < '2027-01-01'",
    "union_both_filtered": f"SELECT SUM(NETTOTAL) FROM (SELECT NETTOTAL FROM {T} WHERE {F} AND {P} UNION ALL SELECT NETTOTAL FROM LG_411_02_INVOICE WHERE {F} AND {P}) u",
    "period_year_fn": f"SELECT SUM(NETTOTAL) FROM {T} WHERE {F} AND YEAR(\"DATE_\") = 2026",
    "period_between": f"SELECT SUM(NETTOTAL) FROM {T} WHERE {F} AND \"DATE_\" BETWEEN '2026-01-01' AND '2026-12-31'",
    "period_lte_form": f"SELECT SUM(NETTOTAL) FROM {T} WHERE {F} AND \"DATE_\" >= '2026-01-01' AND \"DATE_\" <= '2026-12-31'",
    "filter_isnull": f"SELECT SUM(NETTOTAL) FROM {T} WHERE ISNULL(\"CANCELLED\",0) = 0 AND {P}",
    # The table is declared to hold exactly 2026: the date filter is implied by the source.
    "declared_window_no_date_filter": f"SELECT SUM(NETTOTAL) FROM {T} WHERE {F}",
}
# What the gate is told about the tables. DATE_ is a DATE column, so `<= '2026-12-31'` reaches the end
# of the year; the 2026 table's coverage is declared, the 2025 table's is only measured.
SOURCES = {
    # declared ranges are half-open: [2026-01-01, 2027-01-01)
    T: {"types": {"DATE_": "date"}, "window": ("2026-01-01", "2027-01-01"), "declared": True},
    "LG_411_02_INVOICE": {"types": {"DATE_": "date"}, "window": ("2026-01-01", "2027-01-01"), "declared": True},
    "LG_211_01_INVOICE": {"types": {"DATE_": "datetime"}, "window": ("2026-01-01", "2027-01-01"), "declared": False},
}
ACCEPT_COMPARISON = {
    "cmp_case_pivot": f"SELECT SUM(CASE WHEN {P} THEN NETTOTAL ELSE 0 END) bu_yil, SUM(CASE WHEN {P_PREV} THEN NETTOTAL ELSE 0 END) gecen_yil FROM {T} WHERE {F}",
    "cmp_cte_per_period": f"WITH cur AS (SELECT SUM(NETTOTAL) t FROM {T} WHERE {F} AND {P}), prev AS (SELECT SUM(NETTOTAL) t FROM {T} WHERE {F} AND {P_PREV}) SELECT cur.t AS bu_yil, prev.t AS gecen_yil FROM cur CROSS JOIN prev",
    "cmp_group_by_year": f"SELECT YEAR(\"DATE_\") yil, SUM(NETTOTAL) t FROM {T} WHERE {F} AND \"DATE_\" >= '2025-01-01' AND \"DATE_\" < '2027-01-01' GROUP BY YEAR(\"DATE_\")",
}
REFUSE = {
    "missing_filter": f"SELECT SUM(NETTOTAL) FROM {T} WHERE {P}",
    "cte_one_of_two_unfiltered": f"WITH {CTE_A}, {CTE_B_UNFILTERED} SELECT a.ay, a.t, b.n FROM a JOIN b ON a.ay = b.ay",
    "unused_cte": f"WITH f AS (SELECT * FROM {T} WHERE {F} AND {P}) SELECT SUM(NETTOTAL) FROM {T}",
    "or_widening": f"SELECT SUM(NETTOTAL) FROM {T} WHERE ({F} AND {P}) OR TRCODE = 9",
    "filter_in_left_join_on": f"SELECT SUM(i.NETTOTAL) FROM LG_411_CLCARD c LEFT JOIN {T} i ON c.LOGICALREF = i.CLIENTREF AND i.{F} WHERE i.\"DATE_\" >= '2026-01-01' AND i.\"DATE_\" < '2027-01-01'",
    "union_one_unfiltered": f"SELECT SUM(NETTOTAL) FROM (SELECT NETTOTAL FROM {T} WHERE {F} AND {P} UNION ALL SELECT NETTOTAL FROM LG_411_02_INVOICE WHERE {P}) u",
    "wrong_period": f"SELECT SUM(NETTOTAL) FROM {T} WHERE {F} AND {P_PREV}",
    "filter_in_exists_only": f"SELECT SUM(i.NETTOTAL) FROM {T} i WHERE i.\"DATE_\" >= '2026-01-01' AND i.\"DATE_\" < '2027-01-01' AND EXISTS (SELECT 1 FROM {T} j WHERE j.{F})",
    # CASE ... ELSE 0 excludes rows from a SUM, not from a COUNT: the cancelled invoices are counted.
    "filter_in_case_under_count": f"SELECT COUNT(CASE WHEN {F} THEN 1 ELSE 0 END) FROM {T} WHERE {P}",
    # On a datetime column `<= '2026-12-31'` stops at midnight: the last day is outside the period.
    "period_lte_on_datetime": f"SELECT SUM(NETTOTAL) FROM LG_211_01_INVOICE WHERE {F} AND \"DATE_\" >= '2026-01-01' AND \"DATE_\" <= '2026-12-31'",
    # A measured min/max is not a declaration: an incomplete load would pass unfiltered.
    "measured_window_only": f"SELECT SUM(NETTOTAL) FROM LG_211_01_INVOICE WHERE {F}",
    # The restriction sits on a computed column: the gate cannot carry it down and says so.
    "filter_through_computed_column": f"WITH m AS (SELECT MONTH(\"DATE_\") ay, CANCELLED * 1 AS iptal, NETTOTAL FROM {T} WHERE {P}) SELECT SUM(NETTOTAL) FROM m WHERE iptal = 0",
}
REFUSE_COMPARISON = {
    "cmp_same_period_twice": f"SELECT SUM(CASE WHEN {P} THEN NETTOTAL ELSE 0 END) a, SUM(CASE WHEN {P} THEN NETTOTAL ELSE 0 END) b FROM {T} WHERE {F}",
}
# A comparison reads two years, so it cannot be answered from a table declared to hold one: the
# comparison shapes are checked against undeclared sources, and reading 2025 out of the 2026 table
# is one more wrong answer the declaration lets the gate catch.
SOURCES_UNDECLARED = {k: {**v, "declared": False} for k, v in SOURCES.items()}
REFUSE_COMPARISON_DECLARED = {
    "cmp_reference_year_from_a_table_declared_for_current": ACCEPT_COMPARISON["cmp_cte_per_period"],
}

# What the gate gets wrong today (measured 2026-09-15). Strict: an unexpected pass means the case moves up.
WRONG_TODAY: set[str] = set()


def _case(name):
    marks = pytest.mark.xfail(strict=True, reason="gate design gap, see semantic-gate-design.md") if name in WRONG_TODAY else ()
    return pytest.param(name, marks=marks)


@pytest.mark.parametrize("name", [_case(n) for n in ACCEPT])
def test_correct_answer_is_accepted_in_every_shape(name):
    assert unmet_obligations(plan(), ACCEPT[name], sources=SOURCES) == []


@pytest.mark.parametrize("name", [_case(n) for n in ACCEPT_COMPARISON])
def test_comparison_is_accepted_in_every_shape(name):
    assert unmet_obligations(plan(comparison=True), ACCEPT_COMPARISON[name], sources=SOURCES_UNDECLARED) == []


@pytest.mark.parametrize("name", [_case(n) for n in REFUSE])
def test_wrong_answer_is_refused(name):
    assert unmet_obligations(plan(), REFUSE[name], sources=SOURCES)


@pytest.mark.parametrize("name", [_case(n) for n in REFUSE_COMPARISON])
def test_wrong_comparison_is_refused(name):
    assert unmet_obligations(plan(comparison=True), REFUSE_COMPARISON[name], sources=SOURCES_UNDECLARED)


def test_opaque_restriction_is_named_not_blamed():
    text = "; ".join(unmet_obligations(plan(), REFUSE["filter_through_computed_column"], sources=SOURCES))
    assert "anlaşılmayan yapı" in text


def test_two_measured_entities_are_both_bounded():
    from semantic_layer.models import Mapping, ResolvedSlot
    sq = plan()
    sq.slots = []
    sq.temporal_binding = {"entity": "INVOICE", "column": "DATE_", "alternatives": [],
                           "also": [{"entity": "STLINE", "column": "DATE_", "alternatives": []}]}
    both = f"WITH a AS (SELECT SUM(NETTOTAL) t FROM {T} WHERE {P}), b AS (SELECT SUM(TOTAL) u FROM LG_411_01_STLINE WHERE {P}) SELECT a.t, b.u FROM a CROSS JOIN b"
    one = f"WITH a AS (SELECT SUM(NETTOTAL) t FROM {T} WHERE {P}), b AS (SELECT SUM(TOTAL) u FROM LG_411_01_STLINE) SELECT a.t, b.u FROM a CROSS JOIN b"
    assert unmet_obligations(sq, both) == []
    assert unmet_obligations(sq, one)


@pytest.mark.parametrize("name", list(REFUSE_COMPARISON_DECLARED))
def test_declared_coverage_refuses_a_period_the_table_cannot_hold(name):
    assert unmet_obligations(plan(comparison=True), REFUSE_COMPARISON_DECLARED[name], sources=SOURCES)


# --- a span over several year-partitions: each table holds a slice, together they must be the period
T21 = "LG_211_01_INVOICE"
SOURCES_SPAN = {
    T: {"types": {"DATE_": "date"}, "window": ("2026-01-01", "2027-01-01"), "declared": True},
    T21: {"types": {"DATE_": "date"}, "window": ("2021-01-01", "2026-01-01"), "declared": True},
}
SPAN = "\"DATE_\" >= '2024-01-01' AND \"DATE_\" < '2027-01-01'"


def span_plan():
    sq = plan()
    sq.temporal = [TemporalSlot("2024-2026", "RANGE", date(2024, 1, 1), date(2027, 1, 1))]
    return sq


def union(a, b):
    return f"SELECT SUM(NETTOTAL) FROM (SELECT NETTOTAL FROM {a} UNION ALL SELECT NETTOTAL FROM {b}) u"


def test_a_span_is_proven_by_its_partitions_together():
    sql = union(f"{T21} WHERE {F} AND {SPAN}", f"{T} WHERE {F} AND {SPAN}")
    assert unmet_obligations(span_plan(), sql, sources=SOURCES_SPAN) == []


def test_a_span_with_a_missing_partition_is_refused():
    sql = f"SELECT SUM(NETTOTAL) FROM {T21} WHERE {F} AND {SPAN}"
    assert unmet_obligations(span_plan(), sql, sources=SOURCES_SPAN)


def test_a_span_that_reads_one_year_twice_is_refused():
    # the double-counting shape: the 2026 partition read twice under the same filter
    sql = union(f"{T} WHERE {F} AND {SPAN}", f"{T} WHERE {F} AND {SPAN}")
    sq = span_plan()
    sq.temporal = [TemporalSlot("2026", "YEAR", date(2026, 1, 1), date(2027, 1, 1))]
    assert unmet_obligations(span_plan(), sql, sources=SOURCES_SPAN)


def test_a_measure_with_its_scope_inside_the_period_case_or_in_the_where():
    """What a model writes for "this year vs last": one CASE carrying both the measure's own
    condition and the period, or the condition pushed into WHERE. Both are the certified measure."""
    from semantic_layer.models import Mapping, ResolvedSlot
    sq = plan(comparison=True)
    sq.slots.append(ResolvedSlot("ciro", "METRIC", "CERTIFIED", mapping=Mapping("", "INVOICE", "LG_{n0}_{n1}_INVOICE",
                                 formula="SUM(CASE WHEN INVOICE.TRCODE IN (7, 8, 9) THEN INVOICE.NETTOTAL ELSE 0 END)")))
    merged = (f"SELECT SUM(CASE WHEN TRCODE IN (7, 8, 9) AND {P} THEN NETTOTAL ELSE 0 END) a, "
              f"SUM(CASE WHEN TRCODE IN (7, 8, 9) AND {P_PREV} THEN NETTOTAL ELSE 0 END) b FROM {T} WHERE {F}")
    pushed = (f"SELECT SUM(CASE WHEN {P} THEN NETTOTAL ELSE 0 END) a, SUM(CASE WHEN {P_PREV} THEN NETTOTAL ELSE 0 END) b "
              f"FROM {T} WHERE {F} AND TRCODE IN (7, 8, 9)")
    wrong = (f"SELECT SUM(CASE WHEN {P} THEN NETTOTAL ELSE 0 END) a, SUM(CASE WHEN {P_PREV} THEN NETTOTAL ELSE 0 END) b "
             f"FROM {T} WHERE {F}")
    assert unmet_obligations(sq, merged, sources=SOURCES_UNDECLARED) == []
    assert unmet_obligations(sq, pushed, sources=SOURCES_UNDECLARED) == []
    assert unmet_obligations(sq, wrong, sources=SOURCES_UNDECLARED)



def _lines_plan():
    return SemanticQuery(question="x", tenant_id="t", datasource_id="d",
                         slots=[ResolvedSlot("stline default cancelled", "DEFAULT_FILTER", "CERTIFIED",
                                             mapping=Mapping("", "STLINE", "LG_{n0}_{n1}_STLINE", column="CANCELLED", operator="=", values=["0"]))],
                         temporal=[TemporalSlot("2026", "YEAR", date(2026, 1, 1), date(2027, 1, 1))],
                         temporal_binding={"entity": "INVOICE", "column": "DATE_"})


def test_a_left_joins_on_restricts_the_joined_tables_own_rows():
    """2026-09-16, soru 5: `LEFT JOIN STLINE sl ON … AND sl.CANCELLED = 0` was refused as unproven —
    the ON of an outer join was read as never dropping rows. It drops none of the invoices; it is the
    only place the cancelled *lines* can be kept out without dropping invoices that have no lines."""
    base = (f'SELECT i."CLIENTREF", SUM(sl."AMOUNT" * sl."OUTCOST") AS maliyet FROM {T} i '
            'LEFT JOIN LG_411_01_STLINE sl ON sl."INVOICEREF" = i."LOGICALREF"{on} '
            f'WHERE i.{P} GROUP BY i."CLIENTREF"')
    assert unmet_obligations(_lines_plan(), base.format(on=' AND sl."CANCELLED" = 0')) == []
    assert unmet_obligations(_lines_plan(), base.format(on="")), "without the filter the lines are unrestricted"
    # A restriction on the preserved side written in the ON keeps proving nothing: those rows stay.
    inv = SemanticQuery(question="x", tenant_id="t", datasource_id="d",
                        slots=[ResolvedSlot("iptal edilmemiş", "DEFAULT_FILTER", "CERTIFIED",
                                            mapping=Mapping("", "INVOICE", "LG_{n0}_{n1}_INVOICE", column="CANCELLED", operator="=", values=["0"]))],
                        temporal=[TemporalSlot("2026", "YEAR", date(2026, 1, 1), date(2027, 1, 1))],
                        temporal_binding={"entity": "INVOICE", "column": "DATE_"})
    assert unmet_obligations(inv, base.format(on=' AND i."CANCELLED" = 0')), "an ON condition on the left side drops nothing"
