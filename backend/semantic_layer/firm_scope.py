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
from typing import Any, Iterable, Optional


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


def _firm_token(table: str, schema: str = "") -> Optional[int]:
    from semantic_layer.naming import logical_table

    tok = logical_table(table, schema).context.get("n0", "")
    return int(tok) if len(tok) == 3 and tok.isdigit() else None


def foreign_tables(names: Iterable[str], *, schema: str = "") -> set[str]:
    """Of ``names``, the tables that are another company's copy: their firm code is not in ``SEMANTIC_FIRMS``.

    A three-digit number in a name is a firm code only where the name says so. In Logo's own firm tables
    (``LG_<firm>_…``) it always is. In the office's own report tables it may be an account (``…_320`` = suppliers,
    ``…_710`` = direct material) or a short year (``NY_KITAP_TELIF_021``) — reading those as firms drops the company's
    own reports. So outside ``LG_`` a number counts as a firm only when the same name shape also exists with one
    of this company's firms: ``EOS_DAGITIM_MALIYET_211`` next to ``…_019`` shows that the slot is the firm, and 019
    (a consolidation firm) is someone else's copy. Empty ``SEMANTIC_FIRMS`` → nothing is foreign.
    """
    own = included_firms()
    if own is None:
        return set()
    from semantic_layer.naming import logical_table

    names = list(names)
    firm_slot: set[str] = set()
    for n in names:
        tok = _firm_token(n, schema)
        if tok is not None and tok in own:
            firm_slot.add(logical_table(n, schema).table_pattern)
    out: set[str] = set()
    for n in names:
        tok = _firm_token(n, schema)
        if tok is None or tok in own:
            continue
        if n.upper().startswith("LG_") or logical_table(n, schema).table_pattern in firm_slot:
            out.add(n)
    return out

