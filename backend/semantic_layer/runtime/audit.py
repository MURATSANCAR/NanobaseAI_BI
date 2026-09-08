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

def _period_in_sql(period: dict, sql: str) -> bool:
    """Is this period actually restricted in the statement?

    Read from the literals the query carries: the compiler and the model both write the boundary as
    a date, and a year-grain period may be written as the year alone. Textual on purpose — the point
    is to catch a period that is *absent*, and a period nobody wrote cannot be present under another
    spelling.
    """
    start = str(period.get("start") or "")
    if not start:
        return False
    return start[:10] in sql or (period.get("grain") == "YEAR" and start[:4] in sql)


def unmet_obligations(sq: SemanticQuery, sql: str) -> list[str]:
    """What the question asked for and the statement does not deliver.

    Separate from `audit_sql`, which reports disagreements: this reports *absences*, and only where
    the question stated the requirement plainly enough that its absence cannot be a matter of style.
    A comparison is the first of them — "geçen yıla göre" names two periods, and a statement carrying
    one of them answers a different question while looking like a complete answer.

    It checks that both periods reached the statement. Whether the two figures are then presented
    side by side is the compiler's shape, not something readable from the SQL text; that part is
    guaranteed structurally by the multi-period path rather than audited here.
    """
    out: list[str] = []
    comp = getattr(sq, "comparison", None)
    if comp:
        current, reference = comp.get("current"), comp.get("reference")
        if not current:
            out.append(str(comp.get("why") or "karşılaştırma için ikinci dönem belirlenemedi"))
        else:
            missing = [p for p in (current, reference) if p and not _period_in_sql(p, sql)]
            if missing:
                names = ", ".join(f"{p.get('start')}–{p.get('end')}" for p in missing)
                out.append(f"karşılaştırma istendi ama sorguda şu dönem yok: {names}")
    return out
