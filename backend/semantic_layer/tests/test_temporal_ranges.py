"""A span asked for as "A ile B arası" is one period, not two."""
from __future__ import annotations

from datetime import date

from semantic_layer.runtime.temporal import parse_temporal

TODAY = date(2026, 9, 8)


def _slots(q):
    return [(t.primitive, t.start, t.end) for t in parse_temporal(q, TODAY)[0]]


def test_a_span_across_years_is_one_period_not_its_two_ends():
    """Parsed as two months, the two ends reached the model as two separate periods and it wrote a
    column for January 2025 and a column for December 2026 — answering a question nobody asked."""
    assert _slots("1 Ocak 2025 ile 31 Aralik 2026 arasindaki toplam net ciro") == [
        ("RANGE", date(2025, 1, 1), date(2027, 1, 1))]


def test_the_range_words_this_deployment_sees():
    for q in ("2025 ile 2026 arasindaki ciro", "Ocak 2025 - Aralik 2026 arasi ciro",
              "2025 ila 2026 arasi ciro", "ocak 2025 ile aralik 2026 arasinda ciro"):
        assert _slots(q) == [("RANGE", date(2025, 1, 1), date(2027, 1, 1))], q


def test_two_periods_joined_by_and_stay_two():
    """"2025 ve 2026" can mean one span or two figures side by side. Guessing would silently change
    the question, so it stays what it was asked as."""
    assert _slots("2025 ve 2026 toplam ciro") == [
        ("YEAR", date(2025, 1, 1), date(2026, 1, 1)), ("YEAR", date(2026, 1, 1), date(2027, 1, 1))]


def test_what_already_worked_still_works():
    assert _slots("2026 Ocak-Agustos ciro") == [("MONTH_RANGE", date(2026, 1, 1), date(2026, 9, 1))]
    assert _slots("2026 toplam net ciro") == [("YEAR", date(2026, 1, 1), date(2027, 1, 1))]
    assert _slots("Temmuz 2026 da en cok satan kitaplar") == [("MONTH", date(2026, 7, 1), date(2026, 8, 1))]
    assert _slots("son 3 ayin cirosu") == [("LAST_N_MONTHS", date(2026, 6, 1), date(2026, 10, 1))]


def test_a_single_period_is_never_joined_to_nothing():
    assert _slots("2026 arasindaki ciro") == [("YEAR", date(2026, 1, 1), date(2027, 1, 1))]
    assert _slots("ciro") == []


def test_a_span_reads_both_year_tables():
    """The point of the join: one span, and physicalisation reads every year it covers."""
    from semantic_layer.models import ColumnProfile, SchemaProfile
    from semantic_layer.runtime.guardrails import physicalize_sql

    def _p(name, ctx, window):
        return SchemaProfile(datasource_id="d", table_name=name, table_pattern="LG_{n0}_{n1}_INVOICE",
                             entity="INVOICE", schema_name="dbo", context=ctx, time_window=window,
                             columns=[ColumnProfile(name="NETTOTAL", data_type="decimal")], row_count=10)

    profs = [_p("LG_211_01_INVOICE", {"n0": "211", "n1": "01"}, ("2021-01-01", "2025-12-31")),
             _p("LG_411_01_INVOICE", {"n0": "411", "n1": "01"}, ("2026-01-01", "2026-08-17"))]
    (slot,) = parse_temporal("1 Ocak 2025 ile 31 Aralik 2026 arasindaki ciro", TODAY)[0]
    sql = physicalize_sql("SELECT SUM(NETTOTAL) FROM INVOICE", profs, {}, period=(slot.start, slot.end))
    assert "LG_211_01_INVOICE" in sql and "LG_411_01_INVOICE" in sql
