"""Deterministic Turkish temporal parser → temporal primitives.

Never guesses: "son günler" is AMBIGUOUS_RECENT, not "7 days". Ranges are [start, end) dates.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from typing import Optional

from semantic_layer.models import TemporalSlot
from semantic_layer.normalize import cardinal, fold

MONTHS = {
    "ocak": 1, "subat": 2, "mart": 3, "nisan": 4, "mayis": 5, "haziran": 6,
    "temmuz": 7, "agustos": 8, "eylul": 9, "ekim": 10, "kasim": 11, "aralik": 12,
}
_MONTH_RE = "|".join(MONTHS)
# Turkish attaches the whole case paradigm to a time word — "ay" becomes aya, ayda, aydan, ayın, ayki —
# so the ending is written once as grammar instead of being spelled out on every phrase. Without it
# "geçen aya göre" carries no period at all, and the question loses the thing it is comparing.
# The locative + "ki" pair ("bu çeyrekteki", "bu yıldaki", "geçen haftadaki") is one more ending of the
# same kind; without it "bu çeyrekteki ciro geçen çeyreğe göre" lost its current period and the
# comparison came back as the previous quarter alone.
_CASE = r"(?:ndaki|ndeki|daki|deki|taki|teki|ki|ku|nin|nun|nde|nda|ndan|nden|in|un|da|de|ta|te|dan|den|tan|ten|ya|ye|i|u|a|e)?"
# ...and softens a final k before a vowel ("çeyrek" → "çeyreği"), which folds to g.
_QUARTER = r"ceyre[kg]"
# "geçen ay", "son ay" and "önceki ay" are the same period said three ways. Listing the words that mean
# "the one before this one" is grammar; which period they attach to is what carries the meaning.
# "bir önceki hafta" is the same period as "önceki hafta"; the "bir" belongs to the phrase, otherwise
# it is left behind as a stray word wherever the phrase is read or rewritten.
_PREV = r"(?:bir\s+onceki|gecen|son|onceki|gecmis)"
_YEAR = r"(20\d{2})"

PRIMITIVES = (
    "TODAY", "YESTERDAY", "DAY_BEFORE_YESTERDAY", "LAST_N_DAYS", "THIS_WEEK", "LAST_WEEK", "THIS_MONTH", "LAST_MONTH", "LAST_N_YEARS",
    "THIS_QUARTER", "LAST_QUARTER", "THIS_YEAR", "LAST_YEAR", "MTD", "QTD", "YTD",
    "YEAR", "MONTH", "MONTH_RANGE", "RANGE", "DATE", "AMBIGUOUS_RECENT",
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
#: "20 ağustos ve 21 ağustos arasındaki": "ve" joins two ends only when "aras…" follows the second.
_VE_GAP = re.compile(r"^[\s\-]*ve[\s\-]*$")
#: A time of day written after a date ("20.08.2026 03:00:00", "20 ağustos 2026 saat 03:00").
_TIME = r"(?:\s+(?:saat\s+)?(\d{1,2})[:.](\d{2})(?:[:.](\d{2}))?(?![\d.]))?"


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
        joined = (_RANGE_GAP.match(gap) and (_RANGE_WORD.search(gap) or _RANGE_AFTER.match(after))) \
            or (_VE_GAP.match(gap) and _RANGE_AFTER.match(after))
        if joined and a.start and b.end and a.start < b.end:
            params = {"from": a.text, "to": b.text}
            for side, slot in (("from_time", a), ("to_time", b)):
                if (slot.params or {}).get("time"):
                    params[side] = slot.params["time"]
            span = TemporalSlot(text[a_start:b_end].strip(), "RANGE", a.start, b.end, None, params=params)
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

    # "yılbaşından 31 ağustosa kadar", "31 ağustosa kadar", "ağustos sonuna kadar": a range that ends
    # on a named day. The end is inclusive of that day; the start is the start of the year unless the
    # phrase says otherwise. Read before the bare year and YTD forms, which would otherwise take the
    # year and leave "31 ağustos" as unread words.
    for m in re.finditer(rf"\b(?:{_YEAR}\s+)?(?:yil\s*basindan\s+)?(\d{{1,2}})\s+({_MONTH_RE})\w*\s+kadar\b", text):
        year = int(m.group(1)) if m.group(1) else today.year
        day, mo = int(m.group(2)), MONTHS[m.group(3)]
        try:
            last = date(year, mo, day)
        except ValueError:
            continue
        add(m, TemporalSlot(m.group(0).strip(), "YEAR_TO_DAY", date(year, 1, 1), last + timedelta(days=1), "DAY",
                            params={"year": year, "through": last.isoformat()}))
    for m in re.finditer(rf"\b(?:{_YEAR}\s+)?(?:yil\s*basindan\s+)?({_MONTH_RE})\s+sonuna\s+kadar\b", text):
        year = int(m.group(1)) if m.group(1) else today.year
        mo = MONTHS[m.group(2)]
        add(m, TemporalSlot(m.group(0).strip(), "YEAR_TO_MONTH_END", date(year, 1, 1), _next_month(year, mo), "DAY",
                            params={"year": year, "through_month": mo}))
    # "2025 yılını da aynı şekilde 8 aylık": the first N months of that year — the mirror of a
    # partial current year, said the way people say it.
    for m in re.finditer(rf"\b{_YEAR}\s*(?:yilini|yilinin|yilinda|yili|yil)?\s*(?:da\s+|de\s+)?(?:ayni\s+sekilde\s+)?(?:ilk\s+)?(\d{{1,2}})\s+ay(?:lik|lik\s+olarak|i|ini|inda|lari)?\b", text):
        year, n = int(m.group(1)), int(m.group(2))
        if not 1 <= n <= 12:
            continue
        add(m, TemporalSlot(m.group(0).strip(), "FIRST_N_MONTHS", date(year, 1, 1), _next_month(year, n), "MONTH",
                            params={"year": year, "n": n}))
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

    # --- one named day: "17 ağustos 2026", "17.08.2026", "17/08/2026". Read before the month forms,
    # which would otherwise take "ağustos 2026" and answer for the whole month. A day without a year
    # takes the year written elsewhere in the question, else the current one (same as a bare month).
    # "10 ocak ayında" is a count before a month, not a day: a following "ay…" leaves it to the month.
    y_any = re.findall(_YEAR, text)
    # The time of day written after it ("… 03:00", "saat 03:00") is part of the date phrase: kept in params
    # so the question can be asked about it, never read as a word nobody defined.
    def timed(params: dict, hh, mm, ss) -> dict:
        if hh is not None and int(hh) < 24 and int(mm) < 60:
            params["time"] = f"{int(hh):02d}:{int(mm):02d}" + (f":{int(ss):02d}" if ss else "")
        return params

    for m in re.finditer(rf"\b(\d{{1,2}})\s+({_MONTH_RE})\w*(?:\s+{_YEAR})?{_TIME}\b(?!\s+ay)", text):
        y = int(m.group(3)) if m.group(3) else (int(y_any[0]) if y_any else today.year)
        try:
            day = date(y, MONTHS[m.group(2)], int(m.group(1)))
        except ValueError:
            continue
        add(m, TemporalSlot(m.group(0).strip(), "DATE", day, day + timedelta(days=1), "DAY",
                            params=timed({"date": day.isoformat(), "year_assumed": not m.group(3) and not y_any},
                                         m.group(4), m.group(5), m.group(6))))
    # "17.08.2026", "17/08/2026", and a slip of the keyboard "21.008.2026" (a zero too many is still August).
    for m in re.finditer(rf"\b(\d{{1,2}})[./](0?\d{{1,2}})[./]{_YEAR}{_TIME}", text):
        try:
            day = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
        add(m, TemporalSlot(m.group(0).strip(), "DATE", day, day + timedelta(days=1), "DAY",
                            params=timed({"date": day.isoformat()}, m.group(4), m.group(5), m.group(6))))
    # ISO: "2026-08-20", "2026-08-20 03:00:00" (dashes were folded to "-" above).
    for m in re.finditer(rf"\b{_YEAR}-(\d{{1,2}})-(\d{{1,2}}){_TIME}", text):
        try:
            day = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        add(m, TemporalSlot(m.group(0).strip(), "DATE", day, day + timedelta(days=1), "DAY",
                            params=timed({"date": day.isoformat()}, m.group(4), m.group(5), m.group(6))))

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
    # "son üç ay", "son on beş gün": people write the count out as often as they type it.
    _N = r"(\d{1,3}|[a-z]+(?:\s+[a-z]+)?)"

    def _count(raw: str) -> Optional[int]:
        raw = raw.strip()
        if raw.isdigit():
            return int(raw)
        words = raw.split()
        total = 0
        for w in words:
            v = cardinal(w)
            if v is None:
                return None
            total += v
        return total or None

    for m in re.finditer(rf"\bson\s+{_N}\s+gun\w*", text):
        n = _count(m.group(1))
        if n is None:
            continue
        add(m, TemporalSlot(m.group(0).strip(), "LAST_N_DAYS", today - timedelta(days=n), today + timedelta(days=1), "DAY", params={"n": n}))
    for m in re.finditer(rf"\bson\s+{_N}\s+yil\w*", text):
        n = _count(m.group(1))
        if n is None:
            continue
        n = max(1, min(20, n))
        add(m, TemporalSlot(m.group(0).strip(), "LAST_N_YEARS", date(today.year - n + 1, 1, 1), date(today.year + 1, 1, 1), "YEAR", params={"n": n}))
    for m in re.finditer(rf"\bson\s+{_N}\s+ay\w*", text):
        n = _count(m.group(1))
        if n is None:
            continue
        # The N months ending with the current one: "son üç ay" on 17 September is July, August and
        # September. Counted from one month earlier it read four months, and a sold-to-produced ratio
        # over "the same period" silently carried an extra month.
        y, mo = today.year, today.month
        start_m = mo - n + 1
        while start_m <= 0:
            start_m += 12
            y -= 1
        add(m, TemporalSlot(m.group(0).strip(), "LAST_N_MONTHS", _month_start(y, start_m), _next_month(today.year, today.month), "MONTH", params={"n": n}))
    for m in re.finditer(rf"\bson\s+{_N}\s+hafta\w*", text):
        n = _count(m.group(1))
        if n is None:
            continue
        add(m, TemporalSlot(m.group(0).strip(), "LAST_N_WEEKS", today - timedelta(days=7 * n), today + timedelta(days=1), "WEEK", params={"n": n}))
    # Forward-looking windows. Everything above this line looks backwards, and a question that looks
    # forward — "önümüzdeki otuz gün içinde vadesi dolacak alacaklar", "önümüzdeki üç ayda vadesi
    # gelecek çekler" — therefore read as having no period at all, whereupon the default year put a
    # *past* window on a question about what is coming. A due date is a date like any other: the
    # window simply starts today and runs forward.
    # Only the words anchored to *now*. "sonraki ay", "izleyen ay" are relative to whatever date the
    # sentence was just talking about ("irsaliye tarihi bir ayda, fatura tarihi sonraki ayda"), and
    # read as next calendar month they put a filter on a question that asked for a relationship
    # between two dates. A relative-to-a-date window is a different reading and is not guessed here.
    _AHEAD = r"(?:onumuzdeki|gelecek)"
    for unit, prim, days in ((r"gun\w*", "NEXT_N_DAYS", 1), (r"hafta\w*", "NEXT_N_WEEKS", 7)):
        for m in re.finditer(rf"\b{_AHEAD}\s+{_N}\s+{unit}", text):
            n = _count(m.group(1))
            if n is None:
                continue
            add(m, TemporalSlot(m.group(0).strip(), prim, today, today + timedelta(days=days * n + 1),
                                "DAY" if days == 1 else "WEEK", params={"n": n}))
    for m in re.finditer(rf"\b{_AHEAD}\s+{_N}\s+ay\w*", text):
        n = _count(m.group(1))
        if n is None:
            continue
        y, mo = today.year, today.month + n
        while mo > 12:
            mo -= 12
            y += 1
        add(m, TemporalSlot(m.group(0).strip(), "NEXT_N_MONTHS", today, _next_month(y, mo), "MONTH", params={"n": n}))
    for m in re.finditer(rf"\b{_AHEAD}\s+{_N}\s+yil\w*", text):
        n = _count(m.group(1))
        if n is None:
            continue
        n = max(1, min(20, n))
        add(m, TemporalSlot(m.group(0).strip(), "NEXT_N_YEARS", today, date(today.year + n + 1, 1, 1), "YEAR", params={"n": n}))
    _next_m = _next_month(today.year, today.month)
    _monday = today - timedelta(days=today.weekday())
    _ahead_simple = {
        rf"\b{_AHEAD}\s+hafta\w*\b": ("NEXT_WEEK", _monday + timedelta(days=7), _monday + timedelta(days=14), "WEEK"),
        rf"\b{_AHEAD}\s+ay\w*\b": ("NEXT_MONTH", _next_m, _next_month(_next_m.year, _next_m.month), "MONTH"),
        rf"\b{_AHEAD}\s+yil\w*\b": ("NEXT_YEAR", date(today.year + 1, 1, 1), date(today.year + 2, 1, 1), "YEAR"),
    }
    for pat, (prim, start, end, grain) in _ahead_simple.items():
        for m in re.finditer(pat, text):
            add(m, TemporalSlot(m.group(0).strip(), prim, start, end, grain))
    for m in re.finditer(r"\bson\s+(gunler|gunlerde|donem|donemde|zamanlar|zamanlarda|haftalar)\b", text):
        add(m, TemporalSlot(m.group(0).strip(), "AMBIGUOUS_RECENT", None, None, None, ambiguous=True))
    # "bu ara", "bu sıralar", "yakın zamanda", "geçenlerde": a recent stretch nobody put a number on.
    for m in re.finditer(r"\b(bu ara|bu aralar|bu siralar|bu gunlerde|yakin zamanda|yakinlarda|gecenlerde)\b", text):
        add(m, TemporalSlot(m.group(0).strip(), "AMBIGUOUS_RECENT", None, None, None, ambiguous=True))
    simple = {
        rf"\bbugun{_CASE}\b": ("TODAY", today, today + timedelta(days=1), "DAY"),
        rf"\bdun{_CASE}\b": ("YESTERDAY", today - timedelta(days=1), today, "DAY"),
        # "bir önceki gün" is yesterday; "önceki gün" / "evvelsi gün" is the day before it (TDK).
        # The longer phrase is listed first so it owns its span before the shorter one can.
        rf"\bbir onceki gun{_CASE}\b": ("YESTERDAY", today - timedelta(days=1), today, "DAY"),
        rf"\b(?:onceki|evvelsi|evvelki) gun{_CASE}\b": ("DAY_BEFORE_YESTERDAY", today - timedelta(days=2), today - timedelta(days=1), "DAY"),
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
    found = _mark_same_period(found, text)
    slots = [s for _, _, s in found]
    slots, _ = anchor_same_period(slots)
    slots, _ = anchor_previous(slots)
    grain = _grain_hint(text)
    if grain is None:
        for s in slots:
            if s.primitive in ("MONTH_RANGE",):
                grain = None  # a range does not imply a breakdown
    return slots, grain


#: "geçen yılın aynı dönemi", "önceki ayın aynı günleri": the other period, one unit back.
_SAME_AFTER = re.compile(r"^\s+ayni\s+(?:donem|zaman|sure|gun|ay|hafta)\w*")
_SAME_UNITS = {"YEAR": 12, "QUARTER": 3, "MONTH": 1}


def _shift_back(d: date, grain: str) -> date:
    if grain == "WEEK":
        return d - timedelta(days=7)
    months = _SAME_UNITS[grain]
    y, m = divmod(d.month - 1 - months, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _mark_same_period(found: list, text: str) -> list:
    """A previous-unit phrase followed by "aynı dönem…" is not that unit: it names a shift, and it
    takes the words "aynı dönemine" into its own span so nothing else reads them."""
    out = []
    for a, b, s in found:
        m = _SAME_AFTER.match(text[b:])
        if m and s.primitive in ("LAST_YEAR", "LAST_QUARTER", "LAST_MONTH", "LAST_WEEK") and s.grain:
            s = TemporalSlot((s.text + " " + m.group(0).strip()).strip(), s.primitive, s.start, s.end, s.grain,
                             s.ambiguous, params={**(s.params or {}), "same_period": True})
            b += m.end()
        out.append((a, b, s))
    return out


def anchor_same_period(slots: list[TemporalSlot]) -> tuple[list[TemporalSlot], Optional[str]]:
    """"Aralık 2025 ile Ocak 2026 arası … geçen yılın aynı dönemine göre": the second period is the first
    one a year back (Aralık 2024–Ocak 2025), not the whole of last year. Same for a month, a quarter and a
    week back ("geçen ayın aynı dönemi"). Needs exactly one other period to shift; otherwise the phrase
    keeps its calendar reading and the comparison step decides as before."""
    marked = [i for i, s in enumerate(slots) if (s.params or {}).get("same_period")]
    if len(slots) != 2 or len(marked) != 1:
        return slots, None
    r, a = slots[marked[0]], slots[1 - marked[0]]
    if not (a.start and a.end) or r.grain not in ("YEAR", "QUARTER", "MONTH", "WEEK"):
        return slots, None
    start, end = _shift_back(a.start, r.grain), _shift_back(a.end, r.grain)
    moved = TemporalSlot(r.text, r.primitive, start, end, a.grain, r.ambiguous,
                         params={**(r.params or {}), "same_as": a.text})
    out = list(slots)
    out[marked[0]] = moved
    return out, f"'{r.text}' '{a.text}' döneminin bir {r.grain} öncesi: {start.isoformat()}–{end.isoformat()}"


#: "önceki X" / "bir önceki X" — the X before another one. Unlike "geçen X" it is not anchored to today.
_RELATIVE_PREV = re.compile(r"^(?:bir\s+)?onceki\b")


def _unit_before(start: date, grain: str) -> Optional[tuple[date, date]]:
    """The calendar unit of `grain` that ends where `start` begins."""
    if grain == "DAY":
        return start - timedelta(days=1), start
    if grain == "WEEK":
        return start - timedelta(days=7), start
    if grain in ("MONTH", "QUARTER", "YEAR"):
        months = {"MONTH": 1, "QUARTER": 3, "YEAR": 12}[grain]
        y, m = divmod(start.month - 1 - months, 12)
        return date(start.year + y, m + 1, 1), start
    return None


def anchor_previous(slots: list[TemporalSlot]) -> tuple[list[TemporalSlot], Optional[str]]:
    """Two periods where one is "(bir) önceki X": that one is the X before the other, not before today.

    "Geçen haftaki tahsilat bir önceki haftaya göre" parsed both phrases against today, so both were
    last week and the comparison set a week beside itself. "Önceki" names a position relative to the
    period it is compared with; "geçen" names one relative to today. The same holds for every grain:
    "2025 ciro bir önceki yıla göre" is 2024, "dünkü satış önceki güne göre" is the day before
    yesterday. Only a pair of the same grain is re-anchored — "bu ay önceki yıla göre" has nothing to
    count back from — and only when exactly one of the two is relative.
    Returns (slots, explanation or None)."""
    if len(slots) != 2:
        return slots, None
    # "bir önceki yılın aynı ayı" was already placed by anchor_same_period; counting back again would
    # turn July 2025 into June 2026.
    rel = [i for i, s in enumerate(slots)
           if _RELATIVE_PREV.match(s.text or "") and not (s.params or {}).get("same_as")]
    if len(rel) != 1:
        return slots, None
    r, a = slots[rel[0]], slots[1 - rel[0]]
    if not (a.start and a.end and a.grain and a.grain == r.grain):
        return slots, None
    span = _unit_before(a.start, a.grain)
    if span is None or (r.start, r.end) == span:
        return slots, None
    moved = TemporalSlot(r.text, r.primitive, span[0], span[1], r.grain, r.ambiguous,
                         params={**(r.params or {}), "relative_to": a.text})
    out = list(slots)
    out[rel[0]] = moved
    return out, (f"'{r.text}' '{a.text}' dönemine göre okundu: {span[0].isoformat()}–{span[1].isoformat()} "
                 f"(bugüne göre değil)")


def describe(slot: TemporalSlot) -> str:
    if slot.ambiguous:
        return f"'{slot.text}' belirsiz bir dönem — kaç gün/ay olduğunu belirtin"
    if slot.start and slot.end:
        return f"'{slot.text}' → {slot.primitive} [{slot.start.isoformat()}, {slot.end.isoformat()})"
    return f"'{slot.text}' → {slot.primitive}"


def month_count(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


__all__ = ["parse_temporal", "anchor_previous", "anchor_same_period", "describe", "TemporalSlot", "PRIMITIVES", "MONTHS", "month_count", "calendar"]
