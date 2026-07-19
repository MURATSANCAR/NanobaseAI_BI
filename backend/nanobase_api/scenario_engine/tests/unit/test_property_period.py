"""Property-style period invariants (Hypothesis when available)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from nanobase_api.scenario_engine.domain.period import PeriodKind, periods_overlap, resolve_period_bounds

TZ = ZoneInfo("Europe/Istanbul")

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings
from hypothesis import strategies as st


@given(
    year=st.integers(min_value=2000, max_value=2099),
    month=st.integers(min_value=1, max_value=12),
    day=st.integers(min_value=1, max_value=28),
    hour=st.integers(min_value=0, max_value=23),
)
@settings(max_examples=40)
def test_today_start_before_end(year, month, day, hour):
    now = datetime(year, month, day, hour, 0, tzinfo=TZ)
    b = resolve_period_bounds(PeriodKind.TODAY, now=now, tz=TZ)
    assert b.start < b.end


@given(
    year=st.integers(min_value=2001, max_value=2099),
    month=st.integers(min_value=1, max_value=12),
    day=st.integers(min_value=1, max_value=28),
)
@settings(max_examples=40)
def test_prev_current_month_disjoint(year, month, day):
    now = datetime(year, month, day, 12, 0, tzinfo=TZ)
    prev = resolve_period_bounds(PeriodKind.PREVIOUS_MONTH, now=now, tz=TZ)
    curr = resolve_period_bounds(PeriodKind.CURRENT_MONTH, now=now, tz=TZ)
    assert not periods_overlap(prev, curr)
    assert prev.end == curr.start
