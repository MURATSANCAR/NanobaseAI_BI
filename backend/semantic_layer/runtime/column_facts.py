"""A condition that rests on a column which carries no information is not an answer.

Two ways a column can say nothing, and both are knowable before anyone reads the result:

  * **measured** — the scan found it empty (`null_ratio` ≈ 1 in every profiled copy of the table). A
    filter `X < today` on such a column returns zero rows, and "0 rows" then reads as "there are
    none" when the truth is "nobody records this".
  * **declared** — a person wrote, on the column itself, that its content is not what its name says
    (a due date the ERP fills with the order date, a status nobody maintains). No scan measures this
    today; the statement lives where every other human word about a column lives, a schema
    annotation, and is recognised by its opening words (`DATA_NOTE_MARKERS`).

Neither refuses the question. The rows are still what the database holds; what changes is that the
answer says, in the same breath, which of its conditions could not mean what was asked. Nothing here
knows a table, a column or a word of any question: it reads the SQL that ran, the profile the scan
wrote and the annotations people wrote.
"""

from __future__ import annotations

import os
from typing import Any, Iterable, Optional

from sqlglot import exp

from semantic_layer.normalize import fold

#: An annotation that opens with one of these is a statement about the column's *data*, not its
#: meaning; the rest of the sentence is shown to the person who asked, verbatim.
DATA_NOTE_MARKERS = ("veri notu:", "data note:")


def _empty_at() -> float:
    try:
        return float(os.environ.get("SEMANTIC_EMPTY_COLUMN_NULL_RATIO", "0.999"))
    except ValueError:
        return 0.999


def declared_note(text: Optional[str]) -> str:
    """The sentence after the marker, or "" when the annotation is an ordinary description."""
    raw = (text or "").strip()
    low = fold(raw)
    for marker in DATA_NOTE_MARKERS:
        if low.startswith(fold(marker)):
            return raw[len(marker):].strip()
    return ""


def _is_null_test(conj: exp.Expression) -> bool:
    """`X IS NULL` asks for the empty rows on purpose; an empty column satisfies it honestly."""
    return isinstance(conj, exp.Is) and isinstance(conj.expression, exp.Null)


def predicate_column_notes(sql: str, profiles: Iterable[Any], annotations: Optional[dict] = None,
                           *, sources: Optional[dict] = None, result_is_empty: bool = True) -> list[dict[str, str]]:
    """One note per (table, column) a condition or a GROUP BY key of `sql` depends on and that carries no
    information. `annotations` is the runtime's `{(entity, COLUMN|None): text}` map.

    The scan measures `null_ratio` on a sample, so "empty" is a claim the result can refute: rows that
    came back through a condition on the column prove it holds values. A measured note is therefore
    given only when the result agrees (`result_is_empty`); a declared one is a person's statement and
    is always given."""
    from semantic_layer.history.sql_facts import parse_sql
    from semantic_layer.runtime.audit import _columns_of, _ent, _occurrences, repair_table_qualifiers

    try:
        tree = repair_table_qualifiers(parse_sql(sql))
        occurrences = _occurrences(tree, sources or {})
    except Exception:  # noqa: BLE001 — a note is never a reason to fail an answer
        return []
    by_entity: dict[str, list[Any]] = {}
    for p in profiles or []:
        by_entity.setdefault(_ent(getattr(p, "entity", "") or ""), []).append(p)
        by_entity.setdefault(_ent(getattr(p, "table_name", "") or ""), []).append(p)
    said = {(_ent(str(k[0])), str(k[1]).upper()): v for k, v in (annotations or {}).items() if k and k[1]}
    threshold = _empty_at()
    notes: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for occ in occurrences:
        entity = _ent(occ.entity or occ.table)
        # A breakdown by such a column is as empty of meaning as a filter on it: the GROUP BY keys of
        # the SELECT this table sits in count as depended-on, next to its own conditions.
        group = occ.select.args.get("group")
        local = [o for o in occurrences if o.select is occ.select]
        keys = [c for g in (group.expressions if group is not None else []) for c in _columns_of(g)
                if (c.table or "").upper() == (occ.alias or "").upper() or (not c.table and len(local) == 1)]
        for conj in list(occ.conjuncts) + keys:
            if _is_null_test(conj):
                continue
            for col in ([conj] if isinstance(conj, exp.Column) else _columns_of(conj)):
                name = col.name.upper()
                if (entity, name) in seen:
                    continue
                declared = declared_note(said.get((entity, name)))
                if declared:
                    seen.add((entity, name))
                    notes.append({"kind": "DECLARED", "entity": entity, "column": name,
                                  "message": f"{name}: {declared}"})
                    continue
                ratios = []
                label = ""
                for p in by_entity.get(entity, []):
                    c = p.column(name) if hasattr(p, "column") else None
                    if c is None or c.null_ratio is None or not (getattr(p, "row_count", None) or 0):
                        continue
                    ratios.append(float(c.null_ratio))
                    label = label or (c.description or "")
                if result_is_empty and ratios and min(ratios) >= threshold:
                    seen.add((entity, name))
                    shown = f"{label} ({name})" if label and fold(label) != fold(name) else name
                    notes.append({"kind": "EMPTY_COLUMN", "entity": entity, "column": name,
                                  "message": f"{shown} alanı taranan kayıtlarda dolu değil; bu koşul mevcut veriyle "
                                             f"ölçülemez, sonuç 'yok' anlamına gelmez."})
    return notes


def nothing_came_back(records: list[dict[str, Any]], total: int) -> bool:
    """No rows, or the single row an aggregate returns over nothing (every value NULL or 0)."""
    if not total or not records:
        return True
    return total == 1 and all(v is None or v == 0 for v in records[0].values())


def notes_text(notes: list[dict[str, str]]) -> str:
    if not notes:
        return ""
    return " Veri notu: " + " ".join(dict.fromkeys(n["message"] for n in notes))


__all__ = ["DATA_NOTE_MARKERS", "declared_note", "predicate_column_notes", "nothing_came_back", "notes_text"]
