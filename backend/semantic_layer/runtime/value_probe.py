"""What a word in the question actually looks like in the data.

The catalog is inventoried once, at scan time, and a question arrives months later using a word
nobody wrote down. Asked about a product category by the word people say for it, a deployment can
refuse — the term is not in the certified vocabulary — while the answer sits in a code column the
scan already read, spelled slightly differently from the way the question spelled it.

So before the prompt is built, an unplaced word is looked for in the data: a bounded search over the
text columns most likely to hold it, returning the exact spelling and how many rows carry it. The
model is then told a fact rather than left to guess at capitalisation, spacing and suffixes.

This is what a person does when they open the database and run one SELECT before writing a query,
and it is the step that separates knowing the schema from knowing the data. It never decides
anything: it adds facts to the prompt, and a term it cannot find changes nothing.

Bounded on purpose. A handful of columns, a short deadline, top matches only. Sensitive columns are
never searched — a question containing a name must not turn into a scan for that name — and any
failure leaves the prompt exactly as it would have been.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

from semantic_layer.models import SchemaProfile
from semantic_layer.normalize import fold

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValueHit:
    entity: str
    column: str
    value: str
    rows: int

    def as_fact(self) -> str:
        return f'{self.entity}.{self.column} = "{self.value}" ({self.rows} kayıt)'


class ValueProbe:
    """Looks an unplaced word up in the data. Construct with the live connector."""

    #: Types a value search makes sense on. A code column is text; a total is not a word anybody says.
    TEXT_TYPES = ("char", "nchar", "varchar", "nvarchar", "text", "ntext")

    def __init__(self, connector: Any, profiles: list[SchemaProfile], *,
                 max_columns: int = 0, budget_seconds: float = 0.0, top: int = 0):
        self.c = connector
        self.profiles = profiles
        self.max_columns = max_columns or int(os.environ.get("SEMANTIC_PROBE_COLUMNS", "12"))
        self.budget = budget_seconds or float(os.environ.get("SEMANTIC_PROBE_SECONDS", "6"))
        self.top = top or int(os.environ.get("SEMANTIC_PROBE_TOP", "4"))

    def _candidates(self, entities: list[str], columns: Any, question: str) -> list[tuple[SchemaProfile, Any]]:
        """Which columns are worth looking in, best first.

        A column that already holds a short list of distinct values is where a category lives, and one
        the question's own words reached is likelier still. Everything else is a long tail this is
        deliberately bounded against — the point is one quick look, not a search of the database.
        """
        wanted = set(entities)
        # One profile per entity. An entity split one table per fiscal year has a dozen profiles and
        # every one of them carries the same columns; walked as they come, twelve candidate slots go
        # to twelve copies of one column and the search never reaches a second. The fullest table is
        # the one to look in — the others hold the same shape with fewer rows.
        best: dict[str, SchemaProfile] = {}
        for prof in self.profiles:
            if wanted and prof.entity not in wanted:
                continue
            seen = best.get(prof.entity)
            if seen is None or (prof.row_count or 0) > (seen.row_count or 0):
                best[prof.entity] = prof
        scored: list[tuple[float, SchemaProfile, Any]] = []
        reached: set[tuple[str, str]] = set()
        if columns is not None:
            try:
                reached = {(h["entity"], str(h["column"]).upper()) for h in columns.search(question, limit=40)}
            except Exception:  # noqa: BLE001
                reached = set()
        for p in best.values():
            for col in p.columns:
                if col.sensitive or not col.data_type:
                    continue
                if not any(col.data_type.lower().startswith(t) for t in self.TEXT_TYPES):
                    continue
                # Every text column is a candidate; the ranking decides which are looked at first
                # within the budget. Scoring only the inventoried ones and dropping the rest was a
                # shortcut that quietly excluded exactly the columns worth searching: a category code
                # is inventoried and a customer name is not, so a question naming a company found
                # nothing while a question naming a code worked.
                rank = 1.0
                if (p.entity, col.name.upper()) in reached:
                    rank += 2.0
                if col.is_enum():
                    rank += 1.5          # a short value list is what a category looks like
                elif col.top_values:
                    rank += 0.5
                scored.append((rank, p, col))
        scored.sort(key=lambda x: (-x[0], x[1].entity, x[2].name))
        return [(p, c) for _, p, c in scored[: self.max_columns]]

    def find(self, term: str, entities: list[str], columns: Any = None, question: str = "") -> list[ValueHit]:
        """Rows whose value contains `term`, as facts. Empty when nothing matches or anything fails."""
        term = (term or "").strip()
        if len(term) < 3 or self.c is None:
            return []
        started = time.perf_counter()
        hits: list[ValueHit] = []
        seen: set[tuple[str, str, str]] = set()
        for prof, col in self._candidates(entities, columns, question or term):
            if time.perf_counter() - started > self.budget:
                log.debug("value probe budget spent on %r after %d hits", term, len(hits))
                break
            # The inventory the scan already took answers this without touching the database. Both
            # sides are folded: the question arrives with its Turkish characters already flattened by
            # the resolver ("çocuk" → "cocuk") while the data keeps them, so comparing them as typed
            # finds nothing and the question is refused over an accent.
            needle = fold(term)
            for value, count in (col.top_values or []):
                if needle in fold(str(value)):
                    key = (prof.entity, col.name, str(value))
                    if key not in seen:
                        seen.add(key)
                        hits.append(ValueHit(prof.entity, col.name, str(value), int(count)))
            if len(hits) >= self.top:
                break
            # A column whose complete value set was inventoried has already answered: the scan read
            # every distinct value there is, so asking the database again can only return the same
            # rows more slowly. Everything else is asked.
            if col.is_enum() and col.top_values:
                continue
            try:
                for value, count in self._like(prof, col.name, term):
                    key = (prof.entity, col.name, str(value))
                    if key not in seen:
                        seen.add(key)
                        hits.append(ValueHit(prof.entity, col.name, str(value), int(count)))
            except Exception as e:  # noqa: BLE001
                log.debug("value probe failed on %s.%s: %s", prof.entity, col.name, e)
            if len(hits) >= self.top:
                break
        return hits[: self.top]

    def _like(self, prof: SchemaProfile, column: str, term: str) -> list[tuple[str, int]]:
        if not hasattr(self.c, "search_values"):
            return []
        return self.c.search_values(prof.schema_name, prof.table_name, column, term, self.top)


def facts_block(hits: list[ValueHit]) -> str:
    """What the prompt is told. One line per value, exact spelling, with how many rows carry it."""
    if not hits:
        return "(yok)"
    lines = ["Sorudaki sözcükler veride şu değerlere karşılık geliyor — yazımlarını aynen kullan:"]
    lines += [f"- {h.as_fact()}" for h in hits]
    return "\n".join(lines)
