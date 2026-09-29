"""Which firm codes of a firm-per-year source belong to this installation.

A Logo server keeps every company the accounting office works for in one database: each company and each
fiscal year is its own three-digit firm (LG_411_… = TİMAŞ 2026, LG_413_… = another company's 2026, LG_999_… a
test firm). Nothing in the names tells one company from another, and "the highest number covering a year" —
the rule used to find which firm holds a year — then picks a test firm or a neighbour's books.

``SEMANTIC_FIRMS`` names the firms that are this company's books (``015,016,105,…,411``). Set, every place that
discovers firms (period table, ``sys.tables``, the catalog scan) keeps only those; empty keeps all of them, which
is only right on a server that holds a single company. ``SEMANTIC_EXCLUDE_CONTEXT`` stays the narrower tool: of
the company's own firms, the duplicate years accounting does not keep its books in (015/016).
"""
from __future__ import annotations

import os
from typing import Any, Optional


def _codes(raw: str) -> set[int]:
    return {int(p.strip()) for p in (raw or "").split(",") if p.strip().isdigit()}


def included_firms() -> Optional[set[int]]:
    """``SEMANTIC_FIRMS`` as numbers; None = not set (every firm counts)."""
    codes = _codes(os.environ.get("SEMANTIC_FIRMS", ""))
    return codes or None


def excluded_firms(default: str = "015,016") -> set[int]:
    return _codes(os.environ.get("SEMANTIC_EXCLUDE_CONTEXT", default))


def firm_in_scope(firm: Any, *, exclude_default: str = "015,016") -> bool:
    """True when ``firm`` (411, "411", "015") is one of this company's firms and not an excluded duplicate year."""
    try:
        n = int(str(firm).strip())
    except (TypeError, ValueError):
        return False
    inc = included_firms()
    if inc is not None and n not in inc:
        return False
    return n not in excluded_firms(exclude_default)
