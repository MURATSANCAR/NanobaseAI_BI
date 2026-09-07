"""Logical ↔ physical table naming — derived from the observed names, never from a customer's schema.

Any name is split on `_`; all-numeric segments become positional placeholders and the trailing
non-numeric segments become the entity:

    LG_411_01_INVOICE  → entity INVOICE, pattern LG_{n0}_{n1}_INVOICE, context {n0: 411, n1: 01}
    LG_411_CARDS       → entity CARDS,   pattern LG_{n0}_CARDS,        context {n0: 411}
    sales_2024_orders  → entity ORDERS,  pattern SALES_{n0}_ORDERS,    context {n0: 2024}
    customers          → entity CUSTOMERS, pattern CUSTOMERS,          context {}

so the catalog stores meaning against `entity.column` and a pattern, and the same catalog compiles
against another firm / period / year by swapping the context. Placeholders can be given operator
labels (SEMANTIC_PATTERN_LABELS=firm,period) purely for display.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

_NUMERIC = re.compile(r"^\d+$")
_SPLIT = re.compile(r"[_\s]+")


@dataclass(frozen=True)
class LogicalTable:
    entity: str
    table_pattern: str
    context: dict[str, str]
    schema_name: str = ""

    def physical(self, context: dict[str, str] | None = None) -> str:
        ctx = dict(self.context)
        ctx.update(context or {})
        return physical_name(self.table_pattern, ctx)


def strip_quotes(name: str) -> str:
    return (name or "").strip().strip('"').strip("[]").strip("`")


def split_schema(name: str, schema_name: str = "") -> tuple[str, str]:
    """'[dbo].[LG_411_01_INVOICE]' / 'dbo.T' / 'dbo_T' (MDL model spelling) → (schema, table)."""
    raw = strip_quotes(name)
    if "." in raw:
        parts = [strip_quotes(p) for p in raw.split(".")]
        return (parts[-2] or schema_name), parts[-1]
    if schema_name:
        prefix = f"{schema_name}_"
        if raw.lower().startswith(prefix.lower()):
            return schema_name, raw[len(prefix):]
    return schema_name, raw


def logical_table(name: str, schema_name: str = "", *, known_schemas: Iterable[str] = ()) -> LogicalTable:
    """Split a physical/MDL name into entity + pattern + context. Unknown shapes map onto themselves."""
    schema, raw = split_schema(name, schema_name)
    if not schema:
        for candidate in known_schemas:
            if raw.lower().startswith(f"{candidate.lower()}_"):
                schema, raw = candidate, raw[len(candidate) + 1:]
                break
    up = raw.upper()
    segments = [s for s in _SPLIT.split(up) if s]
    numeric = [i for i, s in enumerate(segments) if _NUMERIC.match(s)]
    if not numeric or len(numeric) == len(segments):
        return LogicalTable(up, up, {}, schema)
    context: dict[str, str] = {}
    pattern: list[str] = []
    for k, i in enumerate(numeric):
        context[f"n{k}"] = segments[i]
    order = {i: f"n{k}" for k, i in enumerate(numeric)}
    for i, seg in enumerate(segments):
        pattern.append("{" + order[i] + "}" if i in order else seg)
    tail = segments[numeric[-1] + 1:]
    entity = "_".join(tail) if tail else "_".join(s for i, s in enumerate(segments) if i not in order)
    return LogicalTable(entity or up, "_".join(pattern), context, schema)


def physical_name(table_pattern: str, context: dict[str, str]) -> str:
    out = table_pattern
    for k, v in (context or {}).items():
        out = out.replace("{" + k + "}", str(v))
    return out


def mdl_model_name(table_pattern: str, context: dict[str, str], schema_name: str = "") -> str:
    """Flat model spelling used by exported knowledge (dbo_LG_411_01_INVOICE)."""
    phys = physical_name(table_pattern, context)
    return f"{schema_name}_{phys}" if schema_name else phys


def entity_of(name: str, schema_name: str = "") -> str:
    return logical_table(name, schema_name).entity


def label_context(context: dict[str, str], labels: Optional[list[str]] = None) -> dict[str, str]:
    """Positional placeholders → operator labels for display ({n0: 411} → {firm: 411})."""
    if not labels:
        return dict(context)
    out = {}
    for key, value in (context or {}).items():
        idx = int(key[1:]) if key.startswith("n") and key[1:].isdigit() else -1
        out[labels[idx] if 0 <= idx < len(labels) else key] = value
    return out


def disambiguate(entities: list[tuple[str, str]]) -> dict[str, str]:
    """(entity, pattern) pairs → unique entity names; collisions keep their leading segments
    (A_{n0}_ORDERS / B_{n0}_ORDERS → A_ORDERS / B_ORDERS)."""
    by_entity: dict[str, list[str]] = {}
    for entity, pattern in entities:
        by_entity.setdefault(entity, []).append(pattern)
    out: dict[str, str] = {}
    for entity, patterns in by_entity.items():
        if len(set(patterns)) <= 1:
            for p in patterns:
                out[p] = entity
            continue
        for p in set(patterns):
            prefix = [s for s in p.split("_") if s and not s.startswith("{")][:-len(entity.split("_"))]
            out[p] = ("_".join(prefix + entity.split("_"))) if prefix else entity
    return out


# A name that announces itself as a copy: a backup taken by hand, a table left over from a test, a
# staging table that was never cleaned up. These hold real rows and a real schema, so nothing here
# excludes them — but where a question could be answered from either them or the table they were
# copied from, the copy is not the one to read, and it is not the one to offer a model as a
# candidate. The markers are the ones people actually type, in both languages this catalog sees.
_SHADOW_MARKERS = (
    "yedek", "yedekk", "backup", "bckp", "bak", "copy", "kopya",
    "old", "eski", "test", "temp", "tmp", "deneme", "sil", "arsiv", "arşiv",
)


def is_shadow_copy(name: str, markers: Iterable[str] = ()) -> bool:
    """True when a table name carries a backup/test/temp marker as a whole segment or a prefix.

    Segment-wise, so ORDERS_TEST and BCKP_030826LG_411_01_STLINE match while TEMPLATES, LATEST and
    BAKERY_SALES do not — a substring test would quietly demote real tables.
    """
    words = tuple(m.lower() for m in (markers or _SHADOW_MARKERS))
    for seg in (s for s in _SPLIT.split(strip_quotes(name).lower()) if s):
        # trailing digits are part of the marker: YEDEK1, TEMP2, BAK_2024
        core = seg.rstrip("0123456789") or seg
        if core in words:
            return True
        # a dated prefix glued to the real name: BCKP_030826LG_411_01_STLINE
        if any(core.startswith(w) and core[len(w):].isdigit() for w in words):
            return True
    return False


def source_rank(name: str, *, is_view: bool = False, markers: Iterable[str] = ()) -> int:
    """How much a physical table deserves to be the one read. Lower is better.

    0 — a base table that does not announce itself as a copy.
    1 — a view: the same rows seen through someone else's shaping, fine to read but not the source.
    2 — a table whose name says it is a backup, a test or a staging leftover.

    This orders a choice that would otherwise fall to whichever name sorts first, which is how a
    view came to be preferred over the table under it.
    """
    if is_shadow_copy(name, markers):
        return 2
    return 1 if is_view else 0
