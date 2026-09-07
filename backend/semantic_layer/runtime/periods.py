"""Which physical tables a logical entity's question needs.

A source often splits one entity across several tables that share a naming pattern and differ only in
context — a fiscal period each is the common case, and a year-partitioned warehouse is the same shape.
Nothing here knows what the context means: it compares the period a question asks about with the time
window each table was *measured* to hold, so a source that partitions by year, by branch or not at all
is handled by the same rule.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from semantic_layer.models import SchemaProfile


def _window(p: SchemaProfile) -> Optional[tuple[date, date]]:
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


def tables_for(profiles: list[SchemaProfile], start: Optional[date] = None, end: Optional[date] = None) -> list[SchemaProfile]:
    """The tables a question about [start, end) has to read.

    With no period asked, the most recent table is used rather than all of them: "how are sales doing"
    means now, and reading ten years to answer it is a different question and a much slower one. When a
    period is given, every table whose measured window overlaps it is included — a range that crosses a
    partition boundary reads both sides.
    """
    if len(profiles) <= 1:
        return list(profiles)
    dated = [(p, _window(p)) for p in profiles]
    if start is None or end is None:
        known = [(p, w) for p, w in dated if w]
        if not known:
            return list(profiles)
        # by where each period *begins*, not where it ends: a single forward-dated row can push an old
        # table's window years into the future and make it look like the current one
        latest = max(w[0] for _, w in known)
        return [p for p, w in known if w[0] == latest]
    hit = [p for p, w in dated if w and w[0] < end and start <= w[1]]
    # a table whose window was never measured cannot be ruled out, so it travels with the rest
    hit += [p for p, w in dated if not w]
    return _one_per_window(hit, dict(dated))


def _one_per_window(chosen: list[SchemaProfile], windows: dict) -> list[SchemaProfile]:
    """Two tables covering the same period are copies of it, not two halves of it.

    A partitioned source is expected to overlap at the edges — a range that crosses a boundary reads
    both sides, and that is the whole point. Two tables measured to hold the *same* window are a
    different thing: a migration that was run twice, an old company code kept beside its replacement.
    Reading both adds the period to itself, and the answer comes back at twice the real figure with
    nothing about it looking wrong.

    So where windows coincide, one is read. The one with more rows is kept, because the copy that was
    still being written to is the one that has the later corrections in it.
    """
    groups: dict[tuple, list[SchemaProfile]] = {}
    for p in chosen:
        w = windows.get(p)
        # to the month: a re-import rarely lands on the same day, and never on a different quarter
        key = (w[0].year, w[0].month, w[1].year, w[1].month) if w else ("undated", p.table_name)
        groups.setdefault(key, []).append(p)
    out = []
    for key, members in groups.items():
        if len(members) == 1 or key[0] == "undated":
            out.extend(members)
            continue
        out.append(max(members, key=lambda p: (p.row_count or 0, p.table_name)))
    return [p for p in chosen if p in out]


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


__all__ = ["tables_for", "spans", "describe", "duplicates_of"]
