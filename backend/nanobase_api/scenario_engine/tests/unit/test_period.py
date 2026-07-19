"""Period resolver unit + property-style tests."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from nanobase_api.scenario_engine.domain.period import (
    PeriodKind,
    periods_overlap,
    resolve_period_bounds,
)

TZ = ZoneInfo("Europe/Istanbul")


def test_today_half_open():
    now = datetime(2026, 7, 19, 15, 30, tzinfo=TZ)
    b = resolve_period_bounds(PeriodKind.TODAY, now=now, tz=TZ)
    assert b.start < b.end
    assert b.start.day == 19
    assert b.end.day == 20


def test_previous_month_calendar_not_rolling_30():
    now = datetime(2026, 7, 19, 12, 0, tzinfo=TZ)
    prev = resolve_period_bounds(PeriodKind.PREVIOUS_MONTH, now=now, tz=TZ)
    curr = resolve_period_bounds(PeriodKind.CURRENT_MONTH, now=now, tz=TZ)
    assert prev.start.month == 6 and prev.start.day == 1
    assert prev.end == curr.start
    assert not periods_overlap(prev, curr)


def test_february_leap_year():
    now = datetime(2024, 3, 15, 12, 0, tzinfo=TZ)
    prev = resolve_period_bounds(PeriodKind.PREVIOUS_MONTH, now=now, tz=TZ)
    assert prev.start == datetime(2024, 2, 1, 0, 0, tzinfo=TZ)
    assert prev.end == datetime(2024, 3, 1, 0, 0, tzinfo=TZ)


def test_year_boundaries():
    now = datetime(2026, 1, 1, 0, 0, tzinfo=TZ)
    prev_y = resolve_period_bounds(PeriodKind.PREVIOUS_YEAR, now=now, tz=TZ)
    assert prev_y.start.year == 2025
    assert prev_y.end.year == 2026


@pytest.mark.parametrize(
    "month,day",
    [(1, 1), (1, 31), (2, 28), (2, 29), (12, 31), (6, 30), (7, 1)],
)
def test_random_month_starts(month, day):
    year = 2024 if (month, day) == (2, 29) else 2026
    if month == 2 and day == 29 and year != 2024:
        pytest.skip("not leap")
    try:
        now = datetime(year, month, day, 10, 0, tzinfo=TZ)
    except ValueError:
        pytest.skip("invalid date")
    b = resolve_period_bounds(PeriodKind.CURRENT_MONTH, now=now, tz=TZ)
    assert b.start < b.end
