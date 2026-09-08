"""Audit generated SQL against the certified facts the resolver already found.

The prompt asks the model to honour the catalog; this checks whether it did. The check is deliberately
one-sided: a certified value binding is a *fact*, so SQL that restricts the same column to a set with
nothing in common with that fact is answering a different question, however well-formed it is.

Nothing here knows any customer's tables. It compares what the resolver certified for this question
with what the SQL actually says, both read through the same predicate extractor the miner uses.
"""

from __future__ import annotations

from typing import Any

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


# Obligations are deliberately conservative. A syntactically valid but unsupported
# expression is not proof that the requested restriction survived compilation.
from sqlglot import exp
from semantic_layer.history.sql_facts import parse_sql, _split_and, _literal, _Scope, _predicates_from, _normalise_formula


class _AnswerScope(_Scope):
    """Only sources reachable from the answer; unused CTE aliases prove nothing."""
    def __init__(self, tree):
        from sqlglot.optimizer.scope import build_scope, Scope
        from semantic_layer.naming import logical_table
        super().__init__(tree, None)
        self.alias_to_entity = {}
        self.entities = []
        root = build_scope(tree)
        def entities(source):
            if isinstance(source, exp.Table):
                return {logical_table((source.db + "." if source.db else "") + source.name).entity}
            if isinstance(source, Scope):
                if source.union_scopes:
                    return set().union(*(entities(s) for s in source.union_scopes))
                return set().union(*(entities(s) for _, s in source.selected_sources.values()))
            return set()
        if root:
            for alias, (_, source) in root.selected_sources.items():
                names = entities(source)
                entity = next(iter(names)) if len(names) == 1 else "UNKNOWN"
                self.alias_to_entity[alias.upper()] = entity
                if entity not in self.entities:
                    self.entities.append(entity)

    def entity_for(self, col):
        if col.table:
            return self.alias_to_entity.get(col.table.upper(), "UNKNOWN")
        return self.entities[0] if len(self.entities) == 1 else "UNKNOWN"


def _measure_columns(node):
    if isinstance(node, exp.Column):
        return [node]
    if isinstance(node, exp.Case):
        children = [branch.args["true"] for branch in node.args.get("ifs") or []]
        if node.args.get("default") is not None:
            children.append(node.args["default"])
    else:
        children = list(node.iter_expressions())
    return [column for child in children for column in _measure_columns(child)]


def _accepts_bound_column(tree, scope, binding, alias, column, *, require_measure=True):
    entity = scope.entity_for(exp.column(column, table=alias or None)).upper()
    if entity == binding["entity"].upper() and column == binding["column"].upper():
        return True
    for candidate in binding.get("alternatives", []):
        if entity != candidate["entity"].upper() or column != candidate["column"].upper():
            continue
        if binding["entity"] not in scope.entities:
            if not require_measure:
                return True
            # A line-grain answer need not join its header just to repeat the date.
            # The declared alternative must actually own the output measure.
            if any(scope.entity_for(c).upper() == entity for projection in tree.expressions
                   for agg in projection.find_all(exp.AggFunc) for c in _measure_columns(agg)):
                return True
            continue
        expected = tuple(str(x).upper() for x in candidate["join"])
        for join in tree.args.get("joins") or []:
            on = join.args.get("on")
            if on is None:
                continue
            for part in _split_and(on):
                if not isinstance(part, exp.EQ) or not isinstance(part.left, exp.Column) or not isinstance(part.right, exp.Column):
                    continue
                left, right = part.left, part.right
                edge = (scope.entity_for(left).upper(), left.name.upper(), scope.entity_for(right).upper(), right.name.upper())
                if edge == expected or edge[2:] + edge[:2] == expected:
                    return True
    return False


def _bounded_columns(condition, period):
    bounds = {}
    for part in _split_and(condition):
        if not isinstance(part, (exp.GTE, exp.GT, exp.LT, exp.LTE)):
            continue
        if not isinstance(part.left, exp.Column):
            continue
        key = (part.left.table.upper(), part.left.name.upper())
        bounds.setdefault(key, {}).setdefault(type(part), set()).add(_literal(part.right))
    return {key for key, b in bounds.items()
            if b.get(exp.GTE) == {period.get("start")} and b.get(exp.LT) == {period.get("end")}
            and not b.get(exp.GT) and not b.get(exp.LTE)}


def _admits_period(node, columns, period):
    """A global WHERE must not discard rows needed by either conditional measure."""
    if node is None:
        return True
    if isinstance(node, (exp.Where, exp.Paren)):
        return _admits_period(node.this, columns, period)
    if isinstance(node, exp.And):
        return _admits_period(node.left, columns, period) and _admits_period(node.right, columns, period)
    if isinstance(node, exp.Or):
        return _admits_period(node.left, columns, period) or _admits_period(node.right, columns, period)
    relevant = [c for c in node.find_all(exp.Column) if (c.table.upper(), c.name.upper()) in columns]
    if not relevant:
        return True
    if isinstance(node, (exp.GTE, exp.LT)) and isinstance(node.left, exp.Column):
        value = _literal(node.right)
        if value and len(value) == 10:
            return value <= period["start"] if isinstance(node, exp.GTE) else value >= period["end"]
    return False


def _aggregate_case(aggregate):
    inner = aggregate.this
    if isinstance(inner, exp.Distinct) and len(inner.expressions) == 1:
        inner = inner.expressions[0]
    return inner


def _formula(node, scope):
    def canonical(n):
        if isinstance(n, exp.Count) and isinstance(n.this, exp.Literal):
            n.set("this", exp.Star())
        return n
    return _normalise_formula(node.copy().transform(canonical), scope)


def _period_outputs(tree, period, scope, binding=None):
    """Output positions whose every aggregate is bounded by this exact period.

    A date in a comment, an unused CTE, WHERE, or an unrelated CASE is not
    evidence for a separately presented measure. Unsupported SQL fails closed.
    """
    if not isinstance(tree, exp.Select):
        return {}
    outputs = {}
    for pos, projection in enumerate(tree.expressions):
        aggregates = list(projection.find_all(exp.AggFunc))
        if not aggregates:
            continue
        columns = None
        for aggregate in aggregates:
            case = _aggregate_case(aggregate)
            if not isinstance(case, exp.Case) or len(case.args.get("ifs") or []) != 1:
                columns = set()
                break
            branch = case.args["ifs"][0]
            default = case.args.get("default")
            if default is not None and not isinstance(default, exp.Null) and _literal(default) != "0":
                columns = set()
                break
            found = _bounded_columns(branch.this, period)
            columns = found if columns is None else columns & found
        related_columns = {(alias, candidate["column"].upper())
                           for alias in scope.alias_to_entity
                           for candidate in ([binding] + binding.get("alternatives", []))
                           if _accepts_bound_column(tree, scope, binding, alias, candidate["column"].upper())} if binding else set()
        if columns and _admits_period(tree.args.get("where"), columns | related_columns, period):
            inner = projection.this if isinstance(projection, exp.Alias) else projection
            def unwrap(n):
                if isinstance(n, exp.AggFunc) and isinstance(_aggregate_case(n), exp.Case):
                    value = _aggregate_case(n).args["ifs"][0].args["true"].copy()
                    n.set("this", exp.Distinct(expressions=[value]) if isinstance(n.this, exp.Distinct) else value)
                return n
            formula = _formula(inner.copy().transform(unwrap), scope)
            outputs[pos] = (columns, formula)
    return outputs


def unmet_obligations(sq: SemanticQuery, sql: str) -> list[str]:
    """Fail closed when the final SQL does not demonstrate a resolved requirement."""
    out: list[str] = []
    try:
        tree = parse_sql(sql)
    except Exception:
        return ["sorgu ayrıştırılamadı; soru koşulları doğrulanamadı"]
    comp = sq.comparison
    if comp:
        current, reference = comp.get("current"), comp.get("reference")
        comp["satisfied"] = False
        if not current or not reference:
            out.append(str(comp.get("why") or "karşılaştırmanın iki dönemi belirlenemedi"))
        else:
            scope = _AnswerScope(tree)
            left, right = _period_outputs(tree, current, scope, sq.temporal_binding), _period_outputs(tree, reference, scope, sq.temporal_binding)
            expected = {_formula(parse_sql(s.mapping.formula), _Scope(tree, None)) for s in sq.metrics
                        if s.mapping and s.mapping.formula}
            def correct_column(columns):
                binding = sq.temporal_binding
                if binding:
                    return any(_accepts_bound_column(tree, scope, binding, alias, col) for alias, col in columns)
                return any((not comp.get("dateColumn") or col == comp["dateColumn"].upper())
                           and (not comp.get("entity") or scope.entity_for(exp.column(col, table=alias or None)).upper() == comp["entity"].upper())
                           for alias, col in columns)
            proven = {af for a, (ac, af) in left.items() for b, (bc, bf) in right.items()
                      if a != b and af == bf and correct_column(ac & bc)}
            matched = (current.get("start"), current.get("end")) != (reference.get("start"), reference.get("end")) and bool(proven) and (not expected or expected <= proven)
            if not matched:
                out.append(f"karşılaştırma dönemleri ayrı ölçü sütunlarında doğrulanamadı: "
                           f"{current.get('start')}–{current.get('end')}, "
                           f"{reference.get('start')}–{reference.get('end')}")
            comp["satisfied"] = matched

    if not comp and sq.temporal and sq.temporal_binding:
        scope = _AnswerScope(tree)
        where = tree.args.get("where") if isinstance(tree, exp.Select) else None
        binding = sq.temporal_binding
        for period in sq.temporal:
            columns = _bounded_columns(where.this, period.to_dict()) if where else set()
            if not any(_accepts_bound_column(tree, scope, binding, alias, col) for alias, col in columns):
                out.append(f"'{period.text}' dönemi doğru tarih sütununda doğrulanamadı")

    # Do not collect predicates from all scopes: an unused CTE or a SELECT CASE
    # cannot establish a restriction on the rows of the actual answer.
    if sq.filters:
        if not isinstance(tree, exp.Select):
            out.append("sonuç kapsamındaki filtreler doğrulanamadı")
        else:
            scope = _AnswerScope(tree)
            where = tree.args.get("where")
            predicates = _predicates_from(where.this, scope, "where", None) if where else []
            for slot in sq.filters:
                m = slot.mapping
                if not m or not m.column or slot.status not in ("CERTIFIED", "INFERRED"):
                    continue
                equivalents = slot.explain.get("equivalent_bindings", [])
                binding = {"entity": m.entity, "column": m.column, "alternatives": equivalents}
                if any(p.entity.upper() == alt["entity"].upper() and p.column.upper() == alt["column"].upper()
                       and p.operator.upper() in ({"=", "IN"} if alt["operator"].upper() in ("=", "IN") else {alt["operator"].upper()})
                       and _values(p) == {str(v).upper() for v in alt["values"]}
                       and any(_accepts_bound_column(tree, scope, binding, alias, p.column.upper(), require_measure=False)
                               for alias, entity in scope.alias_to_entity.items() if entity.upper() == p.entity.upper())
                       for alt in equivalents for p in predicates):
                    continue
                expected = {str(v).strip().upper() for v in m.values}
                op = (m.operator or "IN").upper()
                compatible = {"=", "IN"} if op in ("=", "IN") else {op}
                covered = any(p.entity.upper() == m.entity.upper() and p.column.upper() == m.column.upper()
                              and p.operator.upper() in compatible and _values(p) == expected for p in predicates)
                # A pivot legitimately puts alternative restrictions in distinct
                # aggregate outputs. Each requested restriction must have its own.
                if not covered:
                    matches = []
                    for projection in tree.expressions:
                        aggregates = list(projection.find_all(exp.AggFunc))
                        if not aggregates:
                            continue
                        conditions = []
                        for agg in aggregates:
                            case = _aggregate_case(agg)
                            if not isinstance(case, exp.Case) or len(case.args.get("ifs") or []) != 1:
                                break
                            default = case.args.get("default")
                            if default is not None and not isinstance(default, exp.Null) and _literal(default) != "0":
                                break
                            conditions.append(case.args["ifs"][0].this)
                        else:
                            matches.append(all(any(p.entity.upper() == m.entity.upper() and p.column.upper() == m.column.upper()
                                                   and p.operator.upper() in compatible and _values(p) == expected
                                                   for p in _predicates_from(c, scope, "case", None)) for c in conditions))
                            continue
                        matches.append(False)
                    pivot_values = {tuple(sorted(str(v).upper() for v in s.mapping.values)) for s in sq.filters
                                    if s.mapping and s.mapping.entity == m.entity and s.mapping.column == m.column}
                    covered = bool(matches) and (any(matches) if len(pivot_values) > 1 else all(matches))
                if not covered:
                    out.append(f"'{slot.term}' koşulu sonuç kapsamında doğrulanamadı: {m.entity}.{m.column} {op} {sorted(expected)}")
    if sq.shape == "ABSENCE":
        # Presence of the word NOT is insufficient: until a correlated anti-join
        # is certified against the plan, do not serve a positive list as absence.
        expected = (sq.absence_contract or {}).get("sql")
        if not expected or parse_sql(expected) != tree:
            out.append("yokluk koşulunun varlık, ilişki ve dönem kapsamı doğrulanamadı")
    if sq.unhandled or sq.clarification:
        out.append("çözümlenmemiş soru koşulları var; netleştirme gerekiyor")
    return out


__all__ = ["audit_sql", "unmet_obligations"]
