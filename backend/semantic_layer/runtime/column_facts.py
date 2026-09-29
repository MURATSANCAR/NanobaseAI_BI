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
    """One note per (table, column) a condition, a GROUP BY key or a summed measure of `sql` depends on and that
    carries no information (or, for a measure, little). `annotations` is the runtime's `{(entity, COLUMN|None): text}` map.
    A declared note on a summed column is a statement about the measure's coverage («yalnız N kayıtta dolu»)
    and is always given, like one on a condition.

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
        mine = (occ.alias or "").upper()
        keys = [c for g in (group.expressions if group is not None else []) for c in _columns_of(g)
                if (c.table or "").upper() == mine or (not c.table and len(local) == 1)]
        measures = [c for c in _measure_columns(occ.select) if (c.table or "").upper() == mine or (not c.table and len(local) == 1)]
        measure_ids = {id(c) for c in measures}
        for conj in list(occ.conjuncts) + keys + measures:
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
                label, real = "", name
                for p in by_entity.get(entity, []):
                    c = p.column(name) if hasattr(p, "column") else None
                    if c is None or c.null_ratio is None or not (getattr(p, "row_count", None) or 0):
                        continue
                    ratios.append(float(c.null_ratio))
                    label = label or (c.description or "")
                    real = c.name or name
                if not ratios or min(ratios) < threshold:
                    continue
                shown = f"{label} ({real})" if label and fold(label) != fold(real) else real
                if result_is_empty:
                    seen.add((entity, name))
                    what = "bu ölçü mevcut veriyle hesaplanamaz" if id(col) in measure_ids else "bu koşul mevcut veriyle ölçülemez"
                    notes.append({"kind": "EMPTY_COLUMN", "entity": entity, "column": name,
                                  "message": f"{shown} alanı taranan kayıtlarda dolu değil; {what}, sonuç 'yok' anlamına gelmez."})
                elif id(col) in measure_ids:
                    # 2026-09-30 (A044 sınıfı): the measure itself sums a column the scan saw empty, and rows came
                    # back — so it is filled somewhere, on few rows. The total is the total of those rows only;
                    # without this the figure reads as the whole business («etkinlik giderleri» = 9.275 ₺). How
                    # few and when is the catalog's declared note (above) where one has been written.
                    seen.add((entity, name))
                    notes.append({"kind": "SPARSE_MEASURE", "entity": entity, "column": name,
                                  "message": f"{shown} alanı katalog taramasında boş görüldü; sonuç yalnız bu alanın "
                                             f"dolu olduğu kayıtları topluyor — kapsamı sınırlı, bütün kayıtların "
                                             f"toplamı değildir."})
    return notes


def _measure_columns(select: exp.Select) -> list[exp.Column]:
    """Columns whose values a SUM/AVG of this SELECT adds up — not the ones a CASE only tests, and not those of
    a nested SELECT (that one is an occurrence of its own)."""
    out: list[exp.Column] = []
    for agg in select.find_all(exp.Sum, exp.Avg):
        if agg.find_ancestor(exp.Select) is not select:
            continue
        inner = agg.this
        if not isinstance(inner, exp.Expression):
            continue
        tested = {id(c) for pred in inner.find_all(exp.Predicate) for c in pred.find_all(exp.Column)}
        out += [c for c in inner.find_all(exp.Column) if c.name and id(c) not in tested]
    return out


def scope_notes(sq: Any) -> list[dict[str, str]]:
    """What the resolver changed about the measure's scope and the person must read with the number: a slot
    that carries `explain.scope_note` (a sibling measure read in place of the one named, because only it
    reaches the breakdown asked for). Kept out of the model's log line — it is part of the answer."""
    out: list[dict[str, str]] = []
    for s in getattr(sq, "slots", None) or []:
        note = str(((getattr(s, "explain", None) or {}).get("scope_note")) or "").strip()
        if note and not any(n["message"] == note for n in out):
            m = getattr(s, "mapping", None)
            out.append({"kind": "MEASURE_SCOPE", "entity": _ent(getattr(m, "entity", "") or "") if m else "",
                        "column": "", "message": note})
    return out


def _ent(name: str) -> str:
    from semantic_layer.runtime.audit import _ent as ent
    return ent(name)


def nothing_came_back(records: list[dict[str, Any]], total: int) -> bool:
    """No rows, or the single row an aggregate returns over nothing (every value NULL or 0)."""
    if not total or not records:
        return True
    return total == 1 and all(v is None or v == 0 for v in records[0].values())


def notes_text(notes: list[dict[str, str]]) -> str:
    if not notes:
        return ""
    return " Veri notu: " + " ".join(dict.fromkeys(n["message"] for n in notes))


__all__ = ["DATA_NOTE_MARKERS", "declared_note", "predicate_column_notes", "nothing_came_back", "notes_text", "scope_notes"]
