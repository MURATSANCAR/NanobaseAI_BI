"""A question that names no period is about now — and "now" moves.

The deployment pinned its default to a single year in an environment file. A service left running
across New Year would answer January's "geçen ay ciro" against the previous year and say nothing
about it: the number looks ordinary and is wrong by twelve months.
"""

from __future__ import annotations

import datetime as dt

from semantic_layer.models import TemporalSlot
from semantic_layer.runtime.resolver import SemanticResolver


def _slot(year: int) -> TemporalSlot:
    return TemporalSlot(text="varsayılan", primitive="YEAR", start=dt.date(year, 1, 1),
                        end=dt.date(year + 1, 1, 1), grain="YEAR", params={"year": year, "default": True})


def _resolver(store, profiles, default):
    return SemanticResolver(store, "t", "ds", profiles, default_temporal=default)


def test_a_moving_default_is_read_at_question_time_not_at_startup(store, retail_profiles):
    """The whole failure was a value decided once. A callable is asked again for every question, so
    the day the year turns over the next answer already knows."""
    years = iter([2026, 2027])
    r = _resolver(store, retail_profiles, lambda: _slot(next(years)))
    first = r.resolve("toplam ciro")
    second = r.resolve("toplam ciro")
    assert first.temporal[0].params["year"] == 2026
    assert second.temporal[0].params["year"] == 2027, "the default was frozen at construction"


def test_a_pinned_year_still_pins(store, retail_profiles):
    r = _resolver(store, retail_profiles, _slot(2019))
    assert r.resolve("toplam ciro").temporal[0].params["year"] == 2019


def test_no_default_leaves_an_undated_question_undated(store, retail_profiles):
    r = _resolver(store, retail_profiles, None)
    assert r.resolve("toplam ciro").temporal == []


def test_a_question_that_names_its_own_period_is_not_overridden(store, retail_profiles):
    """The default only fills a gap. A question that says which year it means keeps it."""
    r = _resolver(store, retail_profiles, lambda: _slot(2026))
    out = r.resolve("2019 toplam ciro")
    assert out.temporal, "the stated period disappeared"
    assert all(t.params.get("default") is not True for t in out.temporal)


def test_the_explanation_names_the_period_it_chose(store, retail_profiles):
    """Filling in a period silently is how a right-looking number turns out to be about another year:
    the answer has to say which year it assumed."""
    r = _resolver(store, retail_profiles, lambda: _slot(2026))
    out = r.resolve("toplam ciro")
    joined = " ".join(out.explanation)
    assert "dönem belirtilmedi" in joined
    assert "2026" in joined, joined
