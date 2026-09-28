"""A question that names no period is about now — and "now" moves.

The deployment pinned its default to a single year in an environment file. A service left running
across New Year would answer January's "geçen ay ciro" against the previous year and say nothing
about it: the number looks ordinary and is wrong by twelve months.

A default period can only restrict a date column (49d39daf, 2026-09-21): it is applied when the
question placed a dated measure on a table that has a business date, never to a question the
resolver understood nothing of — "Bakiyesi bir milyon liranın üstünde olan cariler" came back
restricted to 2026. The questions below are therefore asked of the certified fixture catalog, where
"net ciro" is a measure on the invoice and the invoice has a date; the empty catalog is the case the
default must now stay out of.
"""

from __future__ import annotations

import datetime as dt

from semantic_layer.models import TemporalSlot
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.tests.test_runtime import catalog  # noqa: F401  — the certified fixture lives there


def _slot(year: int) -> TemporalSlot:
    return TemporalSlot(text="varsayılan", primitive="YEAR", start=dt.date(year, 1, 1),
                        end=dt.date(year + 1, 1, 1), grain="YEAR", params={"year": year, "default": True})


def _resolver(store, profiles, default):
    return SemanticResolver(store, "t", "ds", profiles, default_temporal=default)


def _dated(catalog, profiles, default):
    """The certified catalog: 'net ciro' is a measure on INVOICE, and INVOICE has DATE_."""
    return SemanticResolver(catalog, TENANT, DS, profiles, default_temporal=default)


def test_a_moving_default_is_read_at_question_time_not_at_startup(catalog, profiles):
    """The whole failure was a value decided once. A callable is asked again for every question, so
    the day the year turns over the next answer already knows."""
    years = iter([2026, 2027])
    r = _dated(catalog, profiles, lambda: _slot(next(years)))
    first = r.resolve("net ciro")
    second = r.resolve("net ciro")
    assert first.temporal and first.temporal[0].params["year"] == 2026, first.explanation
    assert second.temporal and second.temporal[0].params["year"] == 2027, "the default was frozen at construction"


def test_a_pinned_year_still_pins(catalog, profiles):
    out = _dated(catalog, profiles, _slot(2019)).resolve("net ciro")
    assert out.temporal and out.temporal[0].params["year"] == 2019, out.explanation


def test_a_question_nothing_in_the_catalog_places_gets_no_default_year(store, retail_profiles):
    """Nothing placed, nothing to date: stamping this year on it restricted a question the resolver had
    not understood a word of. The answer says why no period was applied."""
    calls = []
    r = _resolver(store, retail_profiles, lambda: calls.append(1) or _slot(2026))
    out = r.resolve("toplam ciro")
    assert out.temporal == [] and not calls
    assert any("dönem belirtilmedi" in e and "hiçbir şey yok" in e for e in out.explanation), out.explanation


def test_no_default_leaves_an_undated_question_undated(store, retail_profiles):
    r = _resolver(store, retail_profiles, None)
    assert r.resolve("toplam ciro").temporal == []


def test_a_question_that_names_its_own_period_is_not_overridden(store, retail_profiles):
    """The default only fills a gap. A question that says which year it means keeps it."""
    r = _resolver(store, retail_profiles, lambda: _slot(2026))
    out = r.resolve("2019 toplam ciro")
    assert out.temporal, "the stated period disappeared"
    assert all(t.params.get("default") is not True for t in out.temporal)


def test_the_explanation_names_the_period_it_chose(catalog, profiles):
    """Filling in a period silently is how a right-looking number turns out to be about another year:
    the answer has to say which year it assumed."""
    r = _dated(catalog, profiles, lambda: _slot(2026))
    out = r.resolve("net ciro")
    joined = " ".join(out.explanation)
    assert "dönem belirtilmedi" in joined
    assert "2026" in joined, joined
