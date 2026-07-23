"""Runtime parameter extraction — period + dictionary entities."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from nanobase_api.scenario_engine.domain.logical_plan import LogicalPlan
from nanobase_api.scenario_engine.domain.period import PeriodKind, resolve_period_bounds

_TZ = ZoneInfo("Europe/Istanbul")

# Most specific first (YTD/MTD before bare "bugün")
_PERIOD_PATTERNS: list[tuple[re.Pattern[str], PeriodKind]] = [
    (re.compile(r"\by[ıi]l\s+başından(\s+bug[uü]ne)?(\s+kadar)?\b", re.I), PeriodKind.YEAR_TO_DATE),
    (re.compile(r"\bay\s+başından(\s+bug[uü]ne)?(\s+kadar)?\b", re.I), PeriodKind.MONTH_TO_DATE),
    (re.compile(r"\byil\s+basindan(\s+bugune)?(\s+kadar)?\b", re.I), PeriodKind.YEAR_TO_DATE),
    (re.compile(r"\bay\s+basindan(\s+bugune)?(\s+kadar)?\b", re.I), PeriodKind.MONTH_TO_DATE),
    (re.compile(r"\bbu hafta(ki|ya)?\b", re.I), PeriodKind.CURRENT_WEEK),
    (re.compile(r"\bge[cç]en hafta(ki|ya)?\b", re.I), PeriodKind.PREVIOUS_WEEK),
    (re.compile(r"\bbu ay(ki|a|ın)?\b", re.I), PeriodKind.CURRENT_MONTH),
    (re.compile(r"\bge[cç]en ay(ki|a|ın)?\b", re.I), PeriodKind.PREVIOUS_MONTH),
    (re.compile(r"\bbu y[ıi]l(ki|a|ın)?\b", re.I), PeriodKind.CURRENT_YEAR),
    (re.compile(r"\bge[cç]en y[ıi]l(ki|a|ın)?\b", re.I), PeriodKind.PREVIOUS_YEAR),
    (re.compile(r"\bbu [cç]eyrek\b", re.I), PeriodKind.CURRENT_QUARTER),
    (re.compile(r"\bge[cç]en [cç]eyrek\b", re.I), PeriodKind.PREVIOUS_QUARTER),
    (re.compile(r"\bd[uü]n(e|ki|ün)?\b", re.I), PeriodKind.YESTERDAY),
    (re.compile(r"\bbug[uü]n(e|ki|ün)?\b", re.I), PeriodKind.TODAY),
]

_CITY_RE = re.compile(
    r"\b(ankara|istanbul|i̇stanbul|berlin|amsterdam|izmir|i̇zmir)\b", re.I
)

_STATUS_MAP = {
    "iptal": "cancelled",
    "cancelled": "cancelled",
    "ödenmemiş": "unpaid",
    "odenmemis": "unpaid",
    "açık": "unpaid",
    "vadesi geçen": "overdue",
    "vadesi gecen": "overdue",
}


@dataclass
class ResolvedParams:
    period_kind: PeriodKind | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    compare_start: datetime | None = None
    compare_end: datetime | None = None
    city: str | None = None
    status: str | None = None
    fetch_limit: int = 100
    cancelled_status: str = "cancelled"
    status_value: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_bind_dict(self) -> dict[str, object]:
        out: dict[str, object] = {
            "fetch_limit": self.fetch_limit,
            "cancelled_status": self.cancelled_status,
        }
        if self.period_start is not None:
            out["period_start"] = self.period_start.date().isoformat()
        if self.period_end is not None:
            out["period_end"] = self.period_end.date().isoformat()
        if self.compare_start is not None:
            out["compare_start"] = self.compare_start.date().isoformat()
        if self.compare_end is not None:
            out["compare_end"] = self.compare_end.date().isoformat()
        if self.status_value is not None:
            out["status_value"] = self.status_value
        if self.city is not None:
            out["city"] = self.city
        return out


def detect_period_kind(question: str) -> PeriodKind | None:
    for pat, kind in _PERIOD_PATTERNS:
        if pat.search(question or ""):
            return kind
    return None


def resolve_parameters(
    question: str,
    plan: LogicalPlan,
    *,
    now: datetime | None = None,
    tz: ZoneInfo | str = _TZ,
) -> ResolvedParams:
    if isinstance(tz, str):
        tz = ZoneInfo(tz)
    kind = None
    if plan.period:
        try:
            kind = PeriodKind(plan.period)
        except ValueError:
            kind = detect_period_kind(question)
    else:
        kind = detect_period_kind(question)

    params = ResolvedParams(period_kind=kind, fetch_limit=plan.top_n or plan.limit or 100)

    if kind is not None:
        bounds = resolve_period_bounds(kind, now=now, tz=tz)
        params.period_start = bounds.start
        params.period_end = bounds.end

    if plan.family == "AGING":
        # as-of today start
        today = resolve_period_bounds(PeriodKind.TODAY, now=now, tz=tz)
        params.period_start = today.start
        params.period_end = today.end

    if plan.family == "COMPARE_PERIOD":
        curr = resolve_period_bounds(PeriodKind.CURRENT_MONTH, now=now, tz=tz)
        prev = resolve_period_bounds(PeriodKind.PREVIOUS_MONTH, now=now, tz=tz)
        params.period_start = curr.start
        params.period_end = curr.end
        params.compare_start = prev.start
        params.compare_end = prev.end

    if plan.status_filter == "cancelled":
        params.status_value = "cancelled"
        params.status = "cancelled"

    m = _CITY_RE.search(question or "")
    if m:
        city = m.group(1)
        # Normalize İstanbul
        params.city = "İstanbul" if city.lower().replace("i̇", "i") in ("istanbul",) else city.capitalize()

    qlow = (question or "").lower()
    for phrase, status in _STATUS_MAP.items():
        if phrase in qlow:
            params.status = status
            break

    # Explicit BETWEEN: "2026 Mart"
    m_month = re.search(r"(20\d{2})\s*(ocak|şubat|subat|mart|nisan|mayıs|mayis|haziran|temmuz|ağustos|agustos|eylül|eylul|ekim|kasım|kasim|aralık|aralik)", qlow)
    if m_month:
        year = int(m_month.group(1))
        months = {
            "ocak": 1, "şubat": 2, "subat": 2, "mart": 3, "nisan": 4,
            "mayıs": 5, "mayis": 5, "haziran": 6, "temmuz": 7,
            "ağustos": 8, "agustos": 8, "eylül": 9, "eylul": 9,
            "ekim": 10, "kasım": 11, "kasim": 11, "aralık": 12, "aralik": 12,
        }
        month = months[m_month.group(2)]
        start = date(year, month, 1)
        end_month = month + 1 if month < 12 else 1
        end_year = year if month < 12 else year + 1
        end = date(end_year, end_month, 1)
        bounds = resolve_period_bounds(PeriodKind.BETWEEN, start=start, end=end, tz=tz, now=now)
        params.period_kind = PeriodKind.BETWEEN
        params.period_start = bounds.start
        params.period_end = bounds.end

    return params
