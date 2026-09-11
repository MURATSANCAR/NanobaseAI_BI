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
# Turkish attaches the whole case paradigm to a time word — "ay" becomes aya, ayda, aydan, ayın, ayki —
# so the ending is written once as grammar instead of being spelled out on every phrase. Without it
# "geçen aya göre" carries no period at all, and the question loses the thing it is comparing.
_CASE = r"(?:ki|ku|nin|nun|nde|nda|ndan|nden|in|un|da|de|ta|te|dan|den|tan|ten|ya|ye|i|u|a|e)?"
# ...and softens a final k before a vowel ("çeyrek" → "çeyreği"), which folds to g.
_QUARTER = r"ceyre[kg]"
# "geçen ay", "son ay" and "önceki ay" are the same period said three ways. Listing the words that mean
# "the one before this one" is grammar; which period they attach to is what carries the meaning.
_PREV = r"(?:gecen|son|onceki|gecmis)"
_YEAR = r"(20\d{2})"

PRIMITIVES = (
    "TODAY", "YESTERDAY", "LAST_N_DAYS", "THIS_WEEK", "LAST_WEEK", "THIS_MONTH", "LAST_MONTH", "LAST_N_YEARS",
    "THIS_QUARTER", "LAST_QUARTER", "THIS_YEAR", "LAST_YEAR", "MTD", "QTD", "YTD",
    "YEAR", "MONTH", "MONTH_RANGE", "RANGE", "AMBIGUOUS_RECENT",
)


def _month_start(y: int, m: int) -> date:
    return date(y, m, 1)


def _next_month(y: int, m: int) -> date:
    return date(y + (m // 12), (m % 12) + 1, 1)


def _quarter_start(d: date) -> date:
    q = (d.month - 1) // 3
    return date(d.year, q * 3 + 1, 1)


def _grain_hint(text: str) -> Optional[str]:
    # Tekil "yıla/haftaya/çeyreğe göre" karşılaştırmadır ("geçen yıla göre"); kırılım değil.
    # Kırılımı yalnız çoğul biçim anlatır: "yıllara göre".
    if re.search(r"\b(ay bazinda|aylar bazinda|aylik|ay ay|aya gore|aylara gore|aylara bol\w*|ay kiriliminda|her ay)\b", text):
        return "MONTH"
    if re.search(r"\b(gunluk|gun bazinda|gun gun|gune gore|gunlere gore)\b", text):
        return "DAY"
    if re.search(r"\b(haftalik|hafta bazinda|hafta hafta|haftalara gore)\b", text):
        return "WEEK"
    if re.search(r"\b(ceyrek bazinda|ceyreklik|ceyreklere gore)\b", text):
        return "QUARTER"
    if re.search(r"\b(yillik|yil bazinda|yil yil|yillara gore)\b", text):
        return "YEAR"
    return None


#: What sits between two periods that are the ends of one span: "ile", "ila", a dash, and the day
#: numbers of a full date ("1 ocak 2025 ile 31 aralik 2026" — the day is not part of either period).
#: "ve" is deliberately absent: "2025 ve 2026" can mean one span or two figures side by side, and
#: guessing which would silently change the question. It stays two periods.
_RANGE_GAP = re.compile(r"^[\s\-]*(?:ile|ila|arasi\w*)?[\s\-]*\d{0,2}\.?[\s\-]*(?:ile|ila|arasi\w*)?[\s\-]*$")
_RANGE_WORD = re.compile(r"(?:^|\s)(?:ile|ila|aras\w*)")
_RANGE_AFTER = re.compile(r"^\s*(?:\w{1,4}\s+)?aras\w*")


def _join_ranges(found: list, text: str) -> list:
    """Two periods that are the two ends of one span become one period.

    "1 ocak 2025 ile 31 aralik 2026 arasindaki ciro" parses as two months, and the two reach the
    model as two separate periods: it writes a column for January 2025 and a column for December
    2026 and answers a question nobody asked. Only the span was ever asked for, and the months at
    its ends are its bounds, not its subject.

    The join is made only where the question says so — "ile"/"ila"/a dash between them and an
    "aras…" after, or the range word between them. Anything else and they stay separate.
    """
    if len(found) < 2:
        return found
    out = list(found)
    i = 0
    while i < len(out) - 1:
        (a_start, a_end, a), (b_start, b_end, b) = out[i], out[i + 1]
        gap = text[a_end:b_start]
        after = text[b_end:b_end + 24]
        joined = _RANGE_GAP.match(gap) and (_RANGE_WORD.search(gap) or _RANGE_AFTER.match(after))
        if joined and a.start and b.end and a.start < b.end:
            span = TemporalSlot(text[a_start:b_end].strip(), "RANGE", a.start, b.end, None,
                                params={"from": a.text, "to": b.text})
            out[i:i + 2] = [(a_start, b_end, span)]
            continue
        i += 1
    return out


def parse_temporal(question: str, today: Optional[date] = None) -> tuple[list[TemporalSlot], Optional[str]]:
    """Return (slots, grain). Slots are ordered by position in the question."""
    today = today or date.today()
    text = " " + fold(question) + " "
    text = re.sub(r"[–—-]", "-", text)
    found: list[tuple[int, int, TemporalSlot]] = []
    taken: list[tuple[int, int]] = []

    def free(a: int, b: int) -> bool:
        return all(b <= s or a >= e for s, e in taken)

    def add(m: re.Match, slot: TemporalSlot) -> None:
        if free(m.start(), m.end()):
            taken.append((m.start(), m.end()))
            found.append((m.start(), m.end(), slot))

    # A compound date phrase owns its entire span. Otherwise the year,
    # year-to-date and "today" become three competing periods.
    for m in re.finditer(rf"\b(?:{_YEAR}\s+)?yil\s*basindan\s+(?:bugune(?:\s+kadar)?|bu\s+yana|beri|itibaren)\b", text):
        year = int(m.group(1)) if m.group(1) else today.year
        start, end = date(year, 1, 1), today + timedelta(days=1)
        add(m, TemporalSlot(m.group(0).strip(), "YTD", start if start < end else None,
                            end if start < end else None, "DAY", ambiguous=start >= end,
                            params={"year":year}))
    for m in re.finditer(rf"\b{_YEAR}\s+ytd\b", text):
        year = int(m.group(1))
        # A historical/future YTD needs its cutoff specified; a bare year must
        # not turn it silently into a complete year or the current year's YTD.
        known = year == today.year
        add(m, TemporalSlot(m.group(0).strip(), "YTD", date(year,1,1) if known else None,
                            today + timedelta(days=1) if known else None, "DAY", ambiguous=not known,
                            params={"year":year}))

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
    for m in re.finditer(r"\bson\s+(\d{1,2})\s+yil\w*", text):
        n = max(1, min(20, int(m.group(1))))
        add(m, TemporalSlot(m.group(0).strip(), "LAST_N_YEARS", date(today.year - n + 1, 1, 1), date(today.year + 1, 1, 1), "YEAR", params={"n": n}))
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
        rf"\bbugun{_CASE}\b": ("TODAY", today, today + timedelta(days=1), "DAY"),
        rf"\bdun{_CASE}\b": ("YESTERDAY", today - timedelta(days=1), today, "DAY"),
        rf"\bbu hafta{_CASE}\b": ("THIS_WEEK", today - timedelta(days=today.weekday()), today - timedelta(days=today.weekday()) + timedelta(days=7), "WEEK"),
        rf"\b{_PREV} hafta{_CASE}\b": ("LAST_WEEK", today - timedelta(days=today.weekday() + 7), today - timedelta(days=today.weekday()), "WEEK"),
        rf"\bbu ay{_CASE}\b": ("THIS_MONTH", _month_start(today.year, today.month), _next_month(today.year, today.month), "MONTH"),
        rf"\b{_PREV} ay{_CASE}\b": ("LAST_MONTH", _month_start(*((today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1))), _month_start(today.year, today.month), "MONTH"),
        rf"\bbu {_QUARTER}{_CASE}\b": ("THIS_QUARTER", _quarter_start(today), _next_month(_quarter_start(today).year, _quarter_start(today).month + 2), "QUARTER"),
        rf"\bbu yil{_CASE}\b": ("THIS_YEAR", date(today.year, 1, 1), date(today.year + 1, 1, 1), "YEAR"),
        rf"\b{_PREV} yil{_CASE}\b": ("LAST_YEAR", date(today.year - 1, 1, 1), date(today.year, 1, 1), "YEAR"),
        r"\b(ay basindan( beri| bu yana| itibaren)?|mtd)\b": ("MTD", _month_start(today.year, today.month), today + timedelta(days=1), "DAY"),
        r"\b(yil basindan( beri| bu yana| itibaren)?|ytd|yilbasindan)\b": ("YTD", date(today.year, 1, 1), today + timedelta(days=1), "DAY"),
        r"\b(ceyrek basindan( beri| bu yana)?|qtd)\b": ("QTD", _quarter_start(today), today + timedelta(days=1), "DAY"),
    }
    for pat, (prim, start, end, grain) in simple.items():
        for m in re.finditer(pat, text):
            add(m, TemporalSlot(m.group(0).strip(), prim, start, end, grain))
    # last quarter
    for m in re.finditer(rf"\b{_PREV} {_QUARTER}{_CASE}\b", text):
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
    found = _join_ranges(found, text)
    slots = [s for _, _, s in found]
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
