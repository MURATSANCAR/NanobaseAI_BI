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
        latest = max(w[1] for _, w in known)
        return [p for p, w in known if w[1] == latest]
    hit = [p for p, w in dated if w and w[0] < end and start <= w[1]]
    # a table whose window was never measured cannot be ruled out, so it travels with the rest
    hit += [p for p, w in dated if not w]
    return hit or []


def describe(chosen: list[SchemaProfile], available: list[SchemaProfile]) -> str:
    """What an answer should say about which tables it read, when there was a choice."""
    if len(available) <= 1 or not chosen:
        return ""
    if len(chosen) == len(available):
        return f"{chosen[0].entity}: {len(chosen)} dönem tablosu birlikte okundu"
    names = ", ".join(sorted(p.table_name for p in chosen))
    return f"{chosen[0].entity}: dönemle kesişen tablolar okundu ({names})"


__all__ = ["tables_for", "spans", "describe"]
