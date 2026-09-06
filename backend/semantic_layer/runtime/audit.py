"""Audit generated SQL against the certified facts the resolver already found.

The prompt asks the model to honour the catalog; this checks whether it did. The check is deliberately
one-sided: a certified value binding is a *fact*, so SQL that restricts the same column to a set with
nothing in common with that fact is answering a different question, however well-formed it is.

Nothing here knows any customer's tables. It compares what the resolver certified for this question
with what the SQL actually says, both read through the same predicate extractor the miner uses.
"""

from __future__ import annotations

from typing import Any, Optional

from semantic_layer.history.sql_facts import extract_sql_facts
from semantic_layer.models import SemanticQuery, SemanticType


def _values(pred: Any) -> set[str]:
    return {str(v).strip().strip("'").upper() for v in pred.values}


def audit_sql(sq: SemanticQuery, sql: str, *, conventions: Any = None) -> list[str]:
    """Contradictions between the certified reading of the question and the SQL. Empty means agreement.

    A missing predicate is not reported: the model may express the same restriction through a join, a
    CASE or a subquery, and guessing about that would cost more good answers than it saves bad ones.
    Only a direct disagreement on the same column is reported, which cannot be a matter of style.
    """
    facts = extract_sql_facts(sql, conventions=conventions)
    if facts.parse_error:
        return []
    by_column: dict[tuple[str, str], list[Any]] = {}
    for p in facts.predicates:
        if p.operator.upper() in ("IN", "=") and p.values:
            by_column.setdefault((p.entity.upper(), p.column.upper()), []).append(p)

    problems: list[str] = []
    for slot in sq.slots:
        m = slot.mapping
        if slot.semantic_type != SemanticType.DIMENSION_VALUE or slot.status != "CERTIFIED" or not m or not m.column:
            continue
        if (m.operator or "IN").upper() not in ("IN", "="):
            continue
        certified = {str(v).strip().upper() for v in m.values}
        found = by_column.get((m.entity.upper(), m.column.upper()))
        if not found or not certified:
            continue
        # every predicate on that column in the SQL — if none of them overlaps the certified set, the
        # query is asking about something the question did not ask about
        if any(_values(p) & certified for p in found):
            continue
        said = " / ".join(", ".join(sorted(_values(p))) for p in found)
        problems.append(
            f"'{slot.term}' katalogda {m.entity}.{m.column} = {', '.join(sorted(certified))} demek, "
            f"üretilen SQL ise aynı kolonu {said} olarak sınırlıyor"
        )
    return problems


__all__ = ["audit_sql"]
