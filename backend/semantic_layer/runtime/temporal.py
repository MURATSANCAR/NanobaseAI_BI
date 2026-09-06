"""Deterministic Turkish temporal parser → temporal primitives.

Never guesses: "son günler" is AMBIGUOUS_RECENT, not "7 days". Ranges are [start, end) dates.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from typing import Optional

from semantic_layer.models import TemporalSlot
from semantic_layer.normalize import fold

MONTHS = {
    "ocak": 1, "subat": 2, "mart": 3, "nisan": 4, "mayis": 5, "haziran": 6,
    "temmuz": 7, "agustos": 8, "eylul": 9, "ekim": 10, "kasim": 11, "aralik": 12,
}
_MONTH_RE = "|".join(MONTHS)
_YEAR = r"(20\d{2})"

PRIMITIVES = (
    "TODAY", "YESTERDAY", "LAST_N_DAYS", "THIS_WEEK", "LAST_WEEK", "THIS_MONTH", "LAST_MONTH",
    "THIS_QUARTER", "LAST_QUARTER", "THIS_YEAR", "LAST_YEAR", "MTD", "QTD", "YTD",
    "YEAR", "MONTH", "MONTH_RANGE", "AMBIGUOUS_RECENT",
)


def _month_start(y: int, m: int) -> date:
    return date(y, m, 1)


def _next_month(y: int, m: int) -> date:
    return date(y + (m // 12), (m % 12) + 1, 1)


def _quarter_start(d: date) -> date:
    q = (d.month - 1) // 3
    return date(d.year, q * 3 + 1, 1)


def _grain_hint(text: str) -> Optional[str]:
    if re.search(r"\b(ay bazinda|aylik|ay ay|aya gore|ay kiriliminda|her ay)\b", text):
        return "MONTH"
    if re.search(r"\b(gunluk|gun bazinda|gun gun|gune gore)\b", text):
        return "DAY"
    if re.search(r"\b(haftalik|hafta bazinda)\b", text):
        return "WEEK"
    if re.search(r"\b(ceyrek bazinda|ceyreklik)\b", text):
        return "QUARTER"
    if re.search(r"\b(yillik|yil bazinda)\b", text):
        return "YEAR"
    return None


def parse_temporal(question: str, today: Optional[date] = None) -> tuple[list[TemporalSlot], Optional[str]]:
    """Return (slots, grain). Slots are ordered by position in the question."""
    today = today or date.today()
    text = " " + fold(question) + " "
    text = re.sub(r"[–—-]", "-", text)
    found: list[tuple[int, TemporalSlot]] = []
    taken: list[tuple[int, int]] = []

    def free(a: int, b: int) -> bool:
        return all(b <= s or a >= e for s, e in taken)

    def add(m: re.Match, slot: TemporalSlot) -> None:
        if free(m.start(), m.end()):
            taken.append((m.start(), m.end()))
            found.append((m.start(), slot))

    # --- explicit month ranges: "2026 ocak-agustos", "ocak-agustos 2026"
    for m in re.finditer(rf"{_YEAR}\s+({_MONTH_RE})\s*-\s*({_MONTH_RE})", text):
        y, m1, m2 = int(m.group(1)), MONTHS[m.group(2)], MONTHS[m.group(3)]
        add(m, TemporalSlot(m.group(0).strip(), "MONTH_RANGE", _month_start(y, m1), _next_month(y, m2), "MONTH", params={"year": y, "from": m1, "to": m2}))
    for m in re.finditer(rf"({_MONTH_RE})\s*-\s*({_MONTH_RE})\s+{_YEAR}", text):
        y, m1, m2 = int(m.group(3)), MONTHS[m.group(1)], MONTHS[m.group(2)]
        add(m, TemporalSlot(m.group(0).strip(), "MONTH_RANGE", _month_start(y, m1), _next_month(y, m2), "MONTH", params={"year": y, "from": m1, "to": m2}))
    # --- "temmuz 2026", "2026 temmuz"
    for m in re.finditer(rf"({_MONTH_RE})\s+{_YEAR}", text):
        mo, y = MONTHS[m.group(1)], int(m.group(2))
        add(m, TemporalSlot(m.group(0).strip(), "MONTH", _month_start(y, mo), _next_month(y, mo), "MONTH", params={"year": y, "month": mo}))
    for m in re.finditer(rf"{_YEAR}\s+({_MONTH_RE})", text):
        y, mo = int(m.group(1)), MONTHS[m.group(2)]
        add(m, TemporalSlot(m.group(0).strip(), "MONTH", _month_start(y, mo), _next_month(y, mo), "MONTH", params={"year": y, "month": mo}))
    # --- bare month name (current year assumed only if year appears nowhere else → keep explicit)
    for m in re.finditer(rf"\b({_MONTH_RE})(?:\s+ayi|\s+ayinda| ay)?\b", text):
        mo = MONTHS[m.group(1)]
        y_all = re.findall(_YEAR, text)
        y = int(y_all[0]) if y_all else today.year
        add(m, TemporalSlot(m.group(0).strip(), "MONTH", _month_start(y, mo), _next_month(y, mo), "MONTH", params={"year": y, "month": mo, "year_assumed": not y_all}))
    # --- relative
    for m in re.finditer(r"\bson\s+(\d{1,3})\s+gun\w*", text):
        n = int(m.group(1))
        add(m, TemporalSlot(m.group(0).strip(), "LAST_N_DAYS", today - timedelta(days=n), today + timedelta(days=1), "DAY", params={"n": n}))
    for m in re.finditer(r"\bson\s+(\d{1,2})\s+ay\w*", text):
        n = int(m.group(1))
        y, mo = today.year, today.month
        start_m = mo - n
        while start_m <= 0:
            start_m += 12
            y -= 1
        add(m, TemporalSlot(m.group(0).strip(), "LAST_N_MONTHS", _month_start(y, start_m), _next_month(today.year, today.month), "MONTH", params={"n": n}))
    for m in re.finditer(r"\bson\s+(gunler|gunlerde|donem|donemde|zamanlar|zamanlarda|haftalar)\b", text):
        add(m, TemporalSlot(m.group(0).strip(), "AMBIGUOUS_RECENT", None, None, None, ambiguous=True))
    simple = {
        r"\bbugun(ku)?\b": ("TODAY", today, today + timedelta(days=1), "DAY"),
        r"\bdun(ku)?\b": ("YESTERDAY", today - timedelta(days=1), today, "DAY"),
        r"\bbu hafta(ki)?\b": ("THIS_WEEK", today - timedelta(days=today.weekday()), today - timedelta(days=today.weekday()) + timedelta(days=7), "WEEK"),
        r"\bgecen hafta(ki)?\b": ("LAST_WEEK", today - timedelta(days=today.weekday() + 7), today - timedelta(days=today.weekday()), "WEEK"),
        r"\bbu ay(ki|in)?\b": ("THIS_MONTH", _month_start(today.year, today.month), _next_month(today.year, today.month), "MONTH"),
        r"\bgecen ay(ki|in)?\b": ("LAST_MONTH", _month_start(*((today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1))), _month_start(today.year, today.month), "MONTH"),
        r"\bbu ceyrek(te|teki)?\b": ("THIS_QUARTER", _quarter_start(today), _next_month(_quarter_start(today).year, _quarter_start(today).month + 2), "QUARTER"),
        r"\bbu yil(ki|in|da)?\b": ("THIS_YEAR", date(today.year, 1, 1), date(today.year + 1, 1, 1), "YEAR"),
        r"\bgecen yil(ki|in|da)?\b": ("LAST_YEAR", date(today.year - 1, 1, 1), date(today.year, 1, 1), "YEAR"),
        r"\b(ay basindan( beri| bu yana| itibaren)?|mtd)\b": ("MTD", _month_start(today.year, today.month), today + timedelta(days=1), "DAY"),
        r"\b(yil basindan( beri| bu yana| itibaren)?|ytd|yilbasindan)\b": ("YTD", date(today.year, 1, 1), today + timedelta(days=1), "DAY"),
        r"\b(ceyrek basindan( beri| bu yana)?|qtd)\b": ("QTD", _quarter_start(today), today + timedelta(days=1), "DAY"),
    }
    for pat, (prim, start, end, grain) in simple.items():
        for m in re.finditer(pat, text):
            add(m, TemporalSlot(m.group(0).strip(), prim, start, end, grain))
    # last quarter
    for m in re.finditer(r"\bgecen ceyrek(te|teki)?\b", text):
        qs = _quarter_start(today)
        prev_end = qs
        prev_start = _quarter_start(qs - timedelta(days=1))
        add(m, TemporalSlot(m.group(0).strip(), "LAST_QUARTER", prev_start, prev_end, "QUARTER"))
    # --- bare years ("2026", "2026 yilinda", "2026'da")
    for m in re.finditer(rf"\b{_YEAR}(?:\s*(?:yilinda|yili|yil|da|de|icin|ytd))?\b", text):
        y = int(m.group(1))
        prim = "YTD" if "ytd" in m.group(0) else "YEAR"
        add(m, TemporalSlot(m.group(0).strip(), prim, date(y, 1, 1), date(y + 1, 1, 1), "YEAR", params={"year": y}))
    found.sort(key=lambda x: x[0])
    slots = [s for _, s in found]
    grain = _grain_hint(text)
    if grain is None:
        for s in slots:
            if s.primitive in ("MONTH_RANGE",):
                grain = None  # a range does not imply a breakdown
    return slots, grain


def describe(slot: TemporalSlot) -> str:
    if slot.ambiguous:
        return f"'{slot.text}' belirsiz bir dönem — kaç gün/ay olduğunu belirtin"
    if slot.start and slot.end:
        return f"'{slot.text}' → {slot.primitive} [{slot.start.isoformat()}, {slot.end.isoformat()})"
    return f"'{slot.text}' → {slot.primitive}"


def month_count(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


__all__ = ["parse_temporal", "describe", "TemporalSlot", "PRIMITIVES", "MONTHS", "month_count", "calendar"]
