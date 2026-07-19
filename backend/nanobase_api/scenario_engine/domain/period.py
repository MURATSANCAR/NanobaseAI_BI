"""Period kinds and Europe/Istanbul bound resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

from nanobase_api.scenario_engine.domain.errors import ValidationError

DEFAULT_TZ = ZoneInfo("Europe/Istanbul")


class PeriodKind(str, Enum):
    TODAY = "TODAY"
    YESTERDAY = "YESTERDAY"
    TOMORROW = "TOMORROW"
    CURRENT_WEEK = "CURRENT_WEEK"
    PREVIOUS_WEEK = "PREVIOUS_WEEK"
    CURRENT_MONTH = "CURRENT_MONTH"
    PREVIOUS_MONTH = "PREVIOUS_MONTH"
    CURRENT_QUARTER = "CURRENT_QUARTER"
    PREVIOUS_QUARTER = "PREVIOUS_QUARTER"
    CURRENT_YEAR = "CURRENT_YEAR"
    PREVIOUS_YEAR = "PREVIOUS_YEAR"
    LAST_N_DAYS = "LAST_N_DAYS"
    NEXT_N_DAYS = "NEXT_N_DAYS"
    MONTH_TO_DATE = "MONTH_TO_DATE"
    QUARTER_TO_DATE = "QUARTER_TO_DATE"
    YEAR_TO_DATE = "YEAR_TO_DATE"
    BETWEEN = "BETWEEN"
    BEFORE = "BEFORE"
    AFTER = "AFTER"
    AS_OF = "AS_OF"


@dataclass(frozen=True)
class PeriodBounds:
    start: datetime
    end: datetime
    kind: PeriodKind
    timezone: str = "Europe/Istanbul"

    def to_bind_params(self) -> dict[str, str]:
        return {
            "period_start": self.start.isoformat(),
            "period_end": self.end.isoformat(),
        }


def _start_of_day(d: date, tz: ZoneInfo) -> datetime:
    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=tz)


def _add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    return date(y, m, 1)


def _quarter_start(d: date) -> date:
    q = (d.month - 1) // 3
    return date(d.year, q * 3 + 1, 1)


def resolve_period_bounds(
    kind: PeriodKind | str,
    *,
    now: datetime | None = None,
    tz: ZoneInfo | str = DEFAULT_TZ,
    n_days: int | None = None,
    start: date | datetime | None = None,
    end: date | datetime | None = None,
) -> PeriodBounds:
    """Resolve half-open [start, end) bounds in business timezone."""
    if isinstance(kind, str):
        kind = PeriodKind(kind)
    if isinstance(tz, str):
        tz = ZoneInfo(tz)
    if now is None:
        now = datetime.now(tz)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)

    today = now.date()

    if kind == PeriodKind.TODAY:
        s = _start_of_day(today, tz)
        return PeriodBounds(s, s + timedelta(days=1), kind, str(tz))
    if kind == PeriodKind.YESTERDAY:
        s = _start_of_day(today - timedelta(days=1), tz)
        return PeriodBounds(s, s + timedelta(days=1), kind, str(tz))
    if kind == PeriodKind.TOMORROW:
        s = _start_of_day(today + timedelta(days=1), tz)
        return PeriodBounds(s, s + timedelta(days=1), kind, str(tz))

    if kind == PeriodKind.CURRENT_WEEK:
        # Monday-start ISO week
        monday = today - timedelta(days=today.weekday())
        s = _start_of_day(monday, tz)
        return PeriodBounds(s, s + timedelta(days=7), kind, str(tz))
    if kind == PeriodKind.PREVIOUS_WEEK:
        monday = today - timedelta(days=today.weekday() + 7)
        s = _start_of_day(monday, tz)
        return PeriodBounds(s, s + timedelta(days=7), kind, str(tz))

    if kind == PeriodKind.CURRENT_MONTH:
        s = _start_of_day(date(today.year, today.month, 1), tz)
        e = _start_of_day(_add_months(today, 1), tz)
        return PeriodBounds(s, e, kind, str(tz))
    if kind == PeriodKind.PREVIOUS_MONTH:
        first_this = date(today.year, today.month, 1)
        first_prev = _add_months(first_this, -1)
        s = _start_of_day(first_prev, tz)
        e = _start_of_day(first_this, tz)
        return PeriodBounds(s, e, kind, str(tz))

    if kind == PeriodKind.CURRENT_QUARTER:
        qs = _quarter_start(today)
        s = _start_of_day(qs, tz)
        e = _start_of_day(_add_months(qs, 3), tz)
        return PeriodBounds(s, e, kind, str(tz))
    if kind == PeriodKind.PREVIOUS_QUARTER:
        qs = _quarter_start(today)
        prev = _add_months(qs, -3)
        s = _start_of_day(prev, tz)
        e = _start_of_day(qs, tz)
        return PeriodBounds(s, e, kind, str(tz))

    if kind == PeriodKind.CURRENT_YEAR:
        s = _start_of_day(date(today.year, 1, 1), tz)
        e = _start_of_day(date(today.year + 1, 1, 1), tz)
        return PeriodBounds(s, e, kind, str(tz))
    if kind == PeriodKind.PREVIOUS_YEAR:
        s = _start_of_day(date(today.year - 1, 1, 1), tz)
        e = _start_of_day(date(today.year, 1, 1), tz)
        return PeriodBounds(s, e, kind, str(tz))

    if kind == PeriodKind.MONTH_TO_DATE:
        s = _start_of_day(date(today.year, today.month, 1), tz)
        e = _start_of_day(today + timedelta(days=1), tz)
        return PeriodBounds(s, e, kind, str(tz))
    if kind == PeriodKind.QUARTER_TO_DATE:
        s = _start_of_day(_quarter_start(today), tz)
        e = _start_of_day(today + timedelta(days=1), tz)
        return PeriodBounds(s, e, kind, str(tz))
    if kind == PeriodKind.YEAR_TO_DATE:
        s = _start_of_day(date(today.year, 1, 1), tz)
        e = _start_of_day(today + timedelta(days=1), tz)
        return PeriodBounds(s, e, kind, str(tz))

    if kind == PeriodKind.LAST_N_DAYS:
        if n_days is None or n_days < 1:
            raise ValidationError("LAST_N_DAYS requires n_days >= 1")
        e = _start_of_day(today + timedelta(days=1), tz)
        s = e - timedelta(days=n_days)
        return PeriodBounds(s, e, kind, str(tz))
    if kind == PeriodKind.NEXT_N_DAYS:
        if n_days is None or n_days < 1:
            raise ValidationError("NEXT_N_DAYS requires n_days >= 1")
        s = _start_of_day(today + timedelta(days=1), tz)
        return PeriodBounds(s, s + timedelta(days=n_days), kind, str(tz))

    if kind == PeriodKind.BETWEEN:
        if start is None or end is None:
            raise ValidationError("BETWEEN requires start and end")
        sd = start.date() if isinstance(start, datetime) else start
        ed = end.date() if isinstance(end, datetime) else end
        s = _start_of_day(sd, tz)
        e = _start_of_day(ed, tz)
        if e <= s:
            raise ValidationError("BETWEEN end must be after start")
        return PeriodBounds(s, e, kind, str(tz))
    if kind == PeriodKind.BEFORE:
        if end is None:
            raise ValidationError("BEFORE requires end")
        ed = end.date() if isinstance(end, datetime) else end
        e = _start_of_day(ed, tz)
        return PeriodBounds(_start_of_day(date(1970, 1, 1), tz), e, kind, str(tz))
    if kind == PeriodKind.AFTER:
        if start is None:
            raise ValidationError("AFTER requires start")
        sd = start.date() if isinstance(start, datetime) else start
        s = _start_of_day(sd, tz)
        return PeriodBounds(s, _start_of_day(date(9999, 1, 1), tz), kind, str(tz))
    if kind == PeriodKind.AS_OF:
        if end is None and start is None:
            raise ValidationError("AS_OF requires a date")
        d = end or start
        assert d is not None
        dd = d.date() if isinstance(d, datetime) else d
        e = _start_of_day(dd + timedelta(days=1), tz)
        return PeriodBounds(_start_of_day(date(1970, 1, 1), tz), e, kind, str(tz))

    raise ValidationError(f"Unsupported period kind: {kind}")


def periods_overlap(a: PeriodBounds, b: PeriodBounds) -> bool:
    return a.start < b.end and b.start < a.end
