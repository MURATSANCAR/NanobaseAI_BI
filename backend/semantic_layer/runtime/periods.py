"""Which physical tables a logical entity's question needs.

A source often splits one entity across several tables that share a naming pattern and differ only in
context — a fiscal period each is the common case, and a year-partitioned warehouse is the same shape.
Nothing here knows what the context means: it compares the period a question asks about with the time
window each table was *measured* to hold, so a source that partitions by year, by branch or not at all
is handled by the same rule.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from semantic_layer.models import SchemaProfile
from semantic_layer.naming import source_rank


def _window(p: SchemaProfile) -> Optional[tuple[date, date]]:
    """The period a table holds: its declaration when the data did not refute it (see
    `semantic_layer.coverage`), else the measured min/max — a statistic, and the reason the
    forward-dated-row guard in `tables_for` exists."""
    declared = getattr(p, "declared_window", None)
    if declared:
        try:
            # declared ranges are half-open; the chooser works with inclusive last days
            return date.fromisoformat(str(declared[0])[:10]), date.fromisoformat(str(declared[1])[:10]) - timedelta(days=1)
        except ValueError:
            pass
    if not p.time_window:
        return None
    try:
        return date.fromisoformat(str(p.time_window[0])[:10]), date.fromisoformat(str(p.time_window[1])[:10])
    except ValueError:
        return None


def spans(profiles: list[SchemaProfile]) -> Optional[tuple[date, date]]:
    """The whole period these tables cover between them."""
    ws = [w for w in (_window(p) for p in profiles) if w]
    return (min(w[0] for w in ws), max(w[1] for w in ws)) if ws else None


def scope_floor() -> Optional[date]:
    """The first day this deployment answers for, when it says so (SEMANTIC_FULL_SCOPE_FROM=2021-01-01).

    A catalog may hold older copies than the business reads ("everything" is 2021–2026 here while the
    scan also found 2015–2020). That is a statement about the deployment, not about a question."""
    import os
    raw = os.environ.get("SEMANTIC_FULL_SCOPE_FROM", "").strip()
    try:
        return date.fromisoformat(raw[:10]) if raw else None
    except ValueError:
        return None


def full_scope(groups: list[list[SchemaProfile]], today: Optional[date] = None) -> Optional[tuple[date, date]]:
    """[start, end) of everything the partitioned entities in `groups` hold — for a question that named
    no period and cannot be answered from one copy. Only entities kept in more than one copy count: a
    single table is read whole whatever the period. The end is clipped to the end of the current year
    so a forward-dated row does not stretch the claim; the start to the deployment's floor."""
    found = [s for g in groups if len(g) > 1 and (s := spans(g))]
    if not found:
        return None
    today = today or date.today()
    start = min(s[0] for s in found)
    end = min(max(s[1] for s in found) + timedelta(days=1), date(today.year + 1, 1, 1))
    floor = scope_floor()
    if floor and floor > start:
        start = floor
    return (start, end) if start < end else None


def whole_scope(q) -> bool:
    """Did this question get the whole scope instead of a period of its own?"""
    return bool(q is not None and getattr(q, "period_scope", None) and not (getattr(q, "temporal", None) or []))


def asked_bounds(q) -> tuple[Optional[date], Optional[date]]:
    """(first, last) the copies of an entity are chosen by: the question's own period, else the whole
    scope a period-less, year-crossing question was given (`period_scope`). One place, so the prompt,
    the deterministic compiler and the physical rewrite cannot disagree about which copies are read."""
    if q is None:
        return None, None
    temporal = getattr(q, "temporal", None) or []
    if whole_scope(q):
        scope = q.period_scope
        try:
            return date.fromisoformat(str(scope["start"])[:10]), date.fromisoformat(str(scope["end"])[:10])
        except (KeyError, ValueError):
            return None, None
    first = min((t.start for t in temporal if t.start), default=None)
    last = max((t.end for t in temporal if t.end), default=None)
    return first, last


def declared_firms(profiles, start: date, end: date) -> set[str]:
    """The source copies (placeholder n0) a person declared to hold some of [start, end). A measured
    window cannot say this for a card table — customers begin on the same old day in every copy and
    overlap everything — while the declaration is exact: the 2020 copy ends where 2021 begins."""
    out: set[str] = set()
    for p in profiles:
        d = getattr(p, "declared_window", None)
        firm = str((p.context or {}).get("n0") or "")
        if not d or not firm:
            continue
        try:
            a, b = date.fromisoformat(str(d[0])[:10]), date.fromisoformat(str(d[1])[:10])
        except ValueError:
            continue
        if a < end and start < b:
            out.add(firm)
    return out


def tables_for_question(available: list[SchemaProfile], q, groups) -> list[SchemaProfile]:
    """`tables_for` under the question's own period, or under its whole scope (see `asked_bounds`)."""
    first, last = asked_bounds(q)
    if whole_scope(q) and first and last:
        return tables_for(available, first, last, whole=True,
                          firms=declared_firms((p for g in groups for p in g), first, last))
    return tables_for(available, first, last)


def tables_for(profiles: list[SchemaProfile], start: Optional[date] = None, end: Optional[date] = None,
               *, whole: bool = False, firms: Optional[set[str]] = None) -> list[SchemaProfile]:
    """The tables a question about [start, end) has to read.

    With no period asked, the most recent table is used rather than all of them: "how are sales doing"
    means now, and reading ten years to answer it is a different question and a much slower one. When a
    period is given, every table whose measured window overlaps it is included — a range that crosses a
    partition boundary reads both sides.
    """
    if len(profiles) <= 1:
        return list(profiles)
    dated = [(p, _window(p)) for p in profiles]
    if (start is None) != (end is None):
        # One bound only — `DATE_ >= '2015-01-01'` with no ceiling, or a ceiling alone — is an open
        # period, not no period: every copy on the open side is read. Taken as "no period" it read the
        # newest copy alone and 2021–2025 vanished from an answer that asked for everything since 2015.
        start = start or date(1900, 1, 1)
        end = end or date(2999, 12, 31)
    if start is None or end is None:
        known = [(p, w) for p, w in dated if w]
        if not known:
            # No copy of this table has a measured window (a table with no date of its own: the risk
            # limits, the item–warehouse parameters). "Now" is still the newest firm's copy — read from
            # every copy, a question about customers over their risk limit answered from 2015's books.
            def firm_no(p):
                f = str((p.context or {}).get("n0") or "")
                return int(f) if f.isdigit() else -1
            newest = max(firm_no(p) for p in profiles)
            return [p for p in profiles if firm_no(p) == newest] if newest >= 0 else list(profiles)
        # The current copy is the one measured furthest forward *up to today*: a forward-dated row
        # (a 2030 due date) is clipped, so it cannot make an old copy look current, and master data
        # copied whole into every firm (items, customers, price lists — all beginning on the same old
        # day) does not tie eight ways on "begins latest" and get read eight times. A tie left after
        # clipping goes to the newest firm number, the way the copies were created.
        today = date.today().isoformat()

        def rank(p, w):
            end_ = min(str(w[1] or "")[:10], today) if w[1] else ""
            firm = str((p.context or {}).get("n0") or "")
            return (end_, int(firm) if firm.isdigit() else -1, str(w[0] or "")[:10])

        best = max(rank(p, w) for p, w in known)
        return [p for p, w in known if rank(p, w) == best]
    hit = [p for p, w in dated if w and w[0] < end and start <= w[1]]
    if whole:
        # The whole scope is read with no date filter behind it, so a copy that merely spills into
        # the span (the 2020 firm with a handful of rows dated January 2021) would bring its whole
        # year along. A copy belongs to the scope when it begins inside it; if none does — a card
        # table that begins on the same old day in every copy — the overlap rule stands.
        inside = [p for p, w in dated if w and start <= w[0] < end]
        if inside:
            hit = inside
        declared = [p for p in hit if str((p.context or {}).get("n0") or "") in (firms or set())]
        if declared:
            hit = declared
    # A table whose period was never measured cannot be ruled out — but it can be set aside once a
    # measured table covers what was asked. Carried along regardless, an unmeasured 2026 table joined
    # every question about 2015, and the total came back as three years added together with nothing
    # about it looking wrong. Unknown is a reason to keep a table when nothing else answers, not a
    # reason to add it to something that does.
    if not hit:
        hit = [p for p, w in dated if not w]
    return _one_per_window(hit)


def _one_per_window(chosen: list[SchemaProfile]) -> list[SchemaProfile]:
    """Two tables covering the same period are copies of it, not two halves of it.

    A partitioned source is expected to overlap at the edges — a range that crosses a boundary reads
    both sides, and that is the whole point. Two tables measured to hold the *same* window are a
    different thing: a migration that was run twice, an old company code kept beside its replacement.
    Reading both adds the period to itself, and the answer comes back at twice the real figure with
    nothing about it looking wrong.

    So where windows coincide, one is read. A table whose name says it is a backup or a test is never
    the one kept while a plain table is on offer, and a view is not kept over the table beneath it —
    otherwise the choice falls to whichever name sorts first, and LV_ sorts after LG_. Among equals,
    the one with more rows is kept, because the copy that was still being written to is the one that
    has the later corrections in it.
    """
    # Keyed by table name throughout: SchemaProfile is a plain dataclass, so it compares by value and
    # cannot be hashed or used as a dict key.
    groups: dict[tuple, list[SchemaProfile]] = {}
    for p in chosen:
        w = _window(p)
        # to the month: a re-import rarely lands on the same day, and never in a different quarter
        # A table with no date column has no period, so two of them cannot be two halves of one:
        # they are copies, and reading both adds the same rows to themselves. Keyed by pattern,
        # not by name: two patterns are two different things, while two firms of one pattern are
        # the same reference rows twice. Unioning those doubled every figure joined through them,
        # and matched one firm's facts to another firm's rows, where an identifier of the same
        # name means something else entirely.
        key = (w[0].year, w[0].month, w[1].year, w[1].month) if w else ("undated", p.table_pattern)
        groups.setdefault(key, []).append(p)
    keep: set[str] = set()
    for key, members in groups.items():
        if len(members) == 1:
            keep.update(m.table_name for m in members)
            continue
        keep.add(max(members, key=_preference).table_name)
    return [p for p in chosen if p.table_name in keep]


def _preference(p: SchemaProfile) -> tuple:
    """Best-first ordering for two tables that hold the same period. Higher is better."""
    # an unmeasured row count is what a view looks like here: the count comes from the base tables
    rank = source_rank(p.table_name, is_view=p.row_count is None)
    return (-rank, p.row_count or 0, p.table_name)


def duplicates_of(chosen: list[SchemaProfile], available: list[SchemaProfile]) -> list[tuple[SchemaProfile, SchemaProfile]]:
    """(read, skipped) for every period this source keeps more than one copy of.

    A copy that is not read has to be named. It is the one thing here a person could disagree with —
    which of two company codes holds the real 2015 — and an answer that silently picked one is an
    answer nobody can check.
    """
    taken = {p.table_name for p in chosen}
    out = []
    for kept in chosen:
        w = _window(kept)
        if not w:
            continue
        for other in available:
            if other.table_name in taken:
                continue
            o = _window(other)
            if o and (o[0].year, o[0].month, o[1].year, o[1].month) == (w[0].year, w[0].month, w[1].year, w[1].month):
                out.append((kept, other))
    return out


def describe(chosen: list[SchemaProfile], available: list[SchemaProfile]) -> str:
    """What an answer should say about which tables it read, when there was a choice."""
    if len(available) <= 1 or not chosen:
        return ""
    parts = []
    if len(chosen) == len(available):
        parts.append(f"{chosen[0].entity}: {len(chosen)} dönem tablosu birlikte okundu")
    else:
        names = ", ".join(sorted(p.table_name for p in chosen))
        parts.append(f"{chosen[0].entity}: dönemle kesişen tablolar okundu ({names})")
    # Never a silent choice between two copies of the same year.
    for kept, skipped in duplicates_of(chosen, available):
        parts.append(f"aynı dönemin ikinci kopyası okunmadı: {skipped.table_name} "
                     f"(okunan: {kept.table_name}) — iki kez sayılmasın diye")
    return "; ".join(parts)


__all__ = ["tables_for", "spans", "describe", "duplicates_of", "full_scope", "asked_bounds", "whole_scope", "scope_floor", "declared_firms", "tables_for_question"]
