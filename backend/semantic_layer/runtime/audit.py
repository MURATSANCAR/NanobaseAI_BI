"""Audit generated SQL against the certified facts the resolver already found.

Two questions, asked of every statement whichever compiler wrote it:

* `audit_sql` — does the SQL *contradict* a certified fact? A value binding is a fact; SQL that
  restricts the same column to a set with nothing in common with it answers a different question.
* `unmet_obligations` — does the SQL *demonstrate* every requirement the question resolved to? A
  filter, a period, a comparison, a measure, a breakdown, a limit. Missing evidence fails closed.

Evidence is looked for where the rows actually come from. The answer is a tree of sources — base
tables, CTEs, derived tables, UNION branches — and a restriction proves itself on a base table when
it sits on the path from the answer down to that table: the WHERE of any enclosing scope, the ON of
an inner join, a CASE inside an additive aggregate. Which layer of the SQL it was written in is
style, and style is not evidence either way. Anything unreachable from the answer (an unused CTE, a
comment, a decorative CASE) proves nothing, exactly as before.

Nothing here knows any customer's tables. Entities, columns, values, date windows and equivalences
all come from the catalog and the profiles; the rules are the same for every source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Optional

from sqlglot import exp
from sqlglot.optimizer.scope import Scope, build_scope

from semantic_layer.history.sql_facts import (_Scope, _grain_of, _literal, _normalise_formula, _predicates_from,
                                              _single_predicate, _split_and, extract_sql_facts, parse_sql)
from semantic_layer.models import SemanticQuery, SemanticType
from semantic_layer.naming import logical_table


def _values(pred: Any) -> set[str]:
    return {str(v).strip().strip("'").upper() for v in pred.values}


def audit_sql(sq: SemanticQuery, sql: str, *, conventions: Any = None) -> list[str]:
    """Contradictions between the certified reading of the question and the SQL. Empty means agreement.

    A missing predicate is not reported: the model may express the same restriction through a join, a
    CASE or a subquery, and guessing about that would cost more good answers than it saves bad ones.
    Only a direct disagreement on the same column is reported, which cannot be a matter of style.
    """
    if sq.analytics:
        from semantic_layer.runtime.monthly_analysis import check
        return check(sq, sql, audit_sql, conventions=conventions)
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
        if any(_values(p) & certified for p in found):
            continue
        said = " / ".join(", ".join(sorted(_values(p))) for p in found)
        problems.append(
            f"'{slot.term}' katalogda {m.entity}.{m.column} = {', '.join(sorted(certified))} demek, "
            f"üretilen SQL ise aynı kolonu {said} olarak sınırlıyor"
        )
    return problems


# --------------------------------------------------------------------------- structured verdicts

@dataclass
class Unmet:
    """One requirement the SQL did not demonstrate. `text` is what the person reads; `hint` is what a
    model is told when it gets one chance to repair the statement."""
    kind: str                 # filter | period | comparison | measure | grain | limit | reference | absence | expression | parse
    text: str
    hint: str = ""
    entity: str = ""
    column: str = ""

    def __str__(self) -> str:
        return self.text


# --------------------------------------------------------------------------- the source tree

@dataclass
class _Occurrence:
    """One base table the answer reads, with every restriction that provably reaches it."""
    entity: str
    table: str
    alias: str
    select: exp.Select                       # the SELECT this table sits in
    root_alias: str                          # which top-level FROM/JOIN source it descends from
    conjuncts: list[exp.Expression]          # AND-parts local to this table, written against its alias
    preds: list[Any] = field(default_factory=list)          # canonical Predicate(entity, column, op, values)
    intervals: dict[str, tuple[Optional[str], Optional[str]]] = field(default_factory=dict)   # column → [lo, hi)
    opaque: list[str] = field(default_factory=list)  # restrictions above that could not be carried down (computed columns)


class _Stub:
    """A predicate extractor scope that already knows which entity a column belongs to."""
    def __init__(self, entity: str):
        self.entity = entity
    def entity_for(self, col: exp.Column) -> str:
        return self.entity


def _iso(value: Optional[str]) -> Optional[date]:
    if not value or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _plus_day(value: Optional[str]) -> Optional[str]:
    d = _iso(value)
    return (d + timedelta(days=1)).isoformat() if d else None


def _bare_column(node: exp.Expression) -> Optional[exp.Column]:
    """The column under wrappers that do not change which rows a date bound selects."""
    while isinstance(node, (exp.Paren, exp.Cast, exp.TsOrDsToDate, exp.Date)) or (
            isinstance(node, exp.Anonymous) and str(node.this).upper() in ("TRY_CAST", "CONVERT") and node.expressions):
        node = node.expressions[-1] if isinstance(node, exp.Anonymous) else node.this
    return node if isinstance(node, exp.Column) else None


def _unwrap_isnull(node: exp.Expression) -> exp.Expression:
    """`ISNULL(k, d) = v` with d == v asks the same thing of the rows as `k = v` (plus the NULLs, which
    a default filter means to exclude anyway). Anything else is left alone."""
    if isinstance(node, exp.EQ):
        left, right = node.left, node.right
        fn = left if isinstance(left, (exp.Coalesce, exp.Anonymous)) else (right if isinstance(right, (exp.Coalesce, exp.Anonymous)) else None)
        lit = right if fn is left else left
        if fn is not None and (isinstance(fn, exp.Coalesce) or str(getattr(fn, "this", "")).upper() == "ISNULL"):
            args = ([fn.this] + list(fn.expressions)) if isinstance(fn, exp.Coalesce) else list(fn.expressions)
            if len(args) == 2 and isinstance(args[0], exp.Column) and _literal(args[1]) is not None \
                    and _literal(lit) is not None and _literal(args[1]) == _literal(lit):
                return exp.EQ(this=args[0], expression=lit)
    return node


def _columns_of(node: exp.Expression) -> list[exp.Column]:
    return [c for c in node.find_all(exp.Column) if c.name]


def _belongs(conj: exp.Expression, alias: str, single: bool) -> bool:
    cols = _columns_of(conj)
    if not cols:
        return False
    return all((c.table or "").upper() == alias.upper() or (not c.table and single) for c in cols)


def _rename(conj: exp.Expression, mapping: dict[str, exp.Expression]) -> Optional[exp.Expression]:
    """Carry a conjunct written against a derived source's output names down into that source. A
    column that is a plain pass-through keeps carrying; one computed by an expression stops here —
    guessing what `ay >= 3` means for the rows underneath is exactly what this must not do."""
    ok = True
    def tx(n):
        nonlocal ok
        if isinstance(n, exp.Column):
            target = mapping.get(n.name.upper(), None)
            if target is None:
                ok = False
                return n
            return target.copy()
        return n
    out = conj.copy().transform(tx)
    return out if ok else None


def _output_map(sel: exp.Select) -> dict[str, exp.Expression]:
    """Output name → the expression it stands for, for names that are plain columns. `*` passes
    every name through unchanged."""
    out: dict[str, exp.Expression] = {}
    star = False
    for e in sel.expressions:
        if isinstance(e, exp.Star):
            star = True
            continue
        inner = e.this if isinstance(e, exp.Alias) else e
        name = (e.alias_or_name or "").upper()
        if name and isinstance(inner, exp.Column):
            out[name] = inner
    if star:
        return _Passthrough(out)
    return out


class _Passthrough(dict):
    """`SELECT *`: any name not computed here is the same column one level down."""
    def get(self, key, default=None):
        if key in self:
            return dict.get(self, key)
        return exp.column(key)


def _walk(scope: Scope, carried: list[exp.Expression], root_alias: str, sources: dict, opaque: Optional[list[str]] = None) -> list[_Occurrence]:
    opaque = list(opaque or [])
    out: list[_Occurrence] = []
    if scope.union_scopes:
        # Every branch feeds the answer; a restriction must hold on each. Names carried from above are
        # the first branch's; the others are matched by position.
        first = scope.union_scopes[0].expression
        first_names = [(e.alias_or_name or "").upper() for e in first.expressions] if isinstance(first, exp.Select) else []
        for branch in scope.union_scopes:
            sel = branch.expression
            names = [(e.alias_or_name or "").upper() for e in sel.expressions] if isinstance(sel, exp.Select) else []
            table = {a: exp.column(b) for a, b in zip(first_names, names) if a and b}
            renamed = [r for c in carried if (r := _rename(c, table)) is not None]
            out.extend(_walk(branch, renamed, root_alias, sources, opaque))
        return out
    sel = scope.expression
    if not isinstance(sel, exp.Select):
        return out
    local: list[exp.Expression] = []
    where = sel.args.get("where")
    if where is not None:
        local.extend(_split_and(where.this))
    for join in sel.args.get("joins") or []:
        on = join.args.get("on")
        # Only an inner join's ON drops rows. On the unpreserved side of an outer join it only
        # decides what the row is paired with, and the row stays in the answer.
        if on is not None and not (join.side or "").strip() and (join.kind or "").upper() != "CROSS":
            local.extend(_split_and(on))
    outputs = _output_map(sel)
    carried_here = []
    for c in carried:
        r = _rename(c, outputs)
        if r is None:
            opaque.append(c.sql())      # written above against a computed column: not evidence, not a lie either
        else:
            carried_here.append(r)
    conj = [_unwrap_isnull(c) for c in local + carried_here]
    selected = scope.selected_sources
    single = len(selected) == 1
    for alias, (node, source) in selected.items():
        mine = [c for c in conj if _belongs(c, alias, single)]
        if isinstance(source, exp.Table):
            name = (source.db + "." if source.db else "") + source.name
            entity = logical_table(name).entity
            occ = _Occurrence(entity=entity, table=source.name, alias=alias, select=sel,
                              root_alias=root_alias or alias, conjuncts=mine, opaque=list(opaque))
            stub = _Stub(entity)
            for c in mine:
                p = _single_predicate(c, stub, "where", None)
                if p is not None:
                    occ.preds.append(p)
            src = sources.get(name.upper()) or sources.get(source.name.upper()) or {}
            # A measured min/max is a statistic, not a promise: only a declared coverage stands in for a date filter.
            occ.intervals = _intervals(mine, src.get('window') if src.get('declared') else None, src.get('types') or {})
            out.append(occ)
        elif isinstance(source, Scope):
            # Written against this alias; one level down the alias is gone.
            stripped = []
            for c in mine:
                cc = c.copy()
                for col in cc.find_all(exp.Column):
                    col.set("table", None)
                stripped.append(cc)
            out.extend(_walk(source, stripped, root_alias or alias, sources, opaque))
    return out


def _through_day(lit: str, column: str, types: dict) -> Optional[str]:
    """`<= '2026-12-31'` reaches the end of that day on a DATE column. On a datetime column it stops at
    midnight and the rest of the day is outside — that is not the requested period, so no credit."""
    kind = str(types.get(column.upper(), '')).lower()
    if kind == 'date' or kind.startswith('date(') :
        return _plus_day(lit)
    return lit[:10]


def _intervals(conjuncts: list[exp.Expression], window: Optional[tuple[str, str]], types: Optional[dict] = None) -> dict[str, tuple[Optional[str], Optional[str]]]:
    types = types or {}
    """Per date column, the half-open range `[lo, hi)` these conjuncts (and the table's own measured
    window) leave. `>=`, `>`, `<`, `<=`, BETWEEN, `YEAR() =`, `YEAR() = AND MONTH() =` all read as
    ranges; anything else on the column is not a bound."""
    lo: dict[str, list[str]] = {}
    hi: dict[str, list[str]] = {}
    years: dict[str, set[int]] = {}
    months: dict[str, set[int]] = {}
    seen: set[str] = set()
    for c in conjuncts:
        if isinstance(c, (exp.GTE, exp.GT, exp.LT, exp.LTE)):
            col, lit = _bare_column(c.left), _literal(c.right)
            flip = False
            if col is None and _literal(c.left) is not None:
                col, lit, flip = _bare_column(c.right), _literal(c.left), True
            if col is None or not _iso(lit):
                continue
            kind = type(c)
            if flip:
                kind = {exp.GTE: exp.LTE, exp.GT: exp.LT, exp.LT: exp.GT, exp.LTE: exp.GTE}[kind]
            k = col.name.upper()
            seen.add(k)
            if kind is exp.GTE:
                lo.setdefault(k, []).append(lit[:10])
            elif kind is exp.GT:
                lo.setdefault(k, []).append(_plus_day(lit))
            elif kind is exp.LT:
                hi.setdefault(k, []).append(lit[:10])
            else:
                hi.setdefault(k, []).append(_through_day(lit, k, types))
        elif isinstance(c, exp.Between):
            col = _bare_column(c.this)
            a, b = _literal(c.args.get("low")), _literal(c.args.get("high"))
            if col is None or not _iso(a) or not _iso(b):
                continue
            k = col.name.upper()
            seen.add(k)
            lo.setdefault(k, []).append(a[:10])
            hi.setdefault(k, []).append(_through_day(b, k, types))
        elif isinstance(c, exp.EQ):
            fn = c.left if isinstance(c.left, (exp.Year, exp.Month)) else (c.right if isinstance(c.right, (exp.Year, exp.Month)) else None)
            lit = _literal(c.right if fn is c.left else c.left)
            col = _bare_column(fn.this) if fn is not None else None
            if col is None or lit is None or not lit.isdigit():
                continue
            k = col.name.upper()
            seen.add(k)
            (years if isinstance(fn, exp.Year) else months).setdefault(k, set()).add(int(lit))
    out: dict[str, tuple[Optional[str], Optional[str]]] = {}
    for k in seen:
        if k in years and len(years[k]) == 1:
            y = next(iter(years[k]))
            if k in months and len(months[k]) == 1:
                m = next(iter(months[k]))
                lo.setdefault(k, []).append(date(y, m, 1).isoformat())
                hi.setdefault(k, []).append((date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)).isoformat())
            elif k not in months:
                lo.setdefault(k, []).append(date(y, 1, 1).isoformat())
                hi.setdefault(k, []).append(date(y + 1, 1, 1).isoformat())
        a = max(lo[k]) if lo.get(k) else None
        b = min(hi[k]) if hi.get(k) else None
        out[k] = (a, b)
    if window and window[0] and window[1]:
        # The source itself only holds this range: a period-partitioned table needs no date filter
        # to answer for its own period. Declared ranges are half-open already.
        first, last = window[0][:10], window[1][:10]
        for k in list(out) or []:
            a, b = out[k]
            out[k] = (max(a, first) if a else first, min(b, last) if b else last)
        out.setdefault("*", (first, last))
    return out


def _window_of(occ: _Occurrence, column: str) -> tuple[Optional[str], Optional[str]]:
    if column in occ.intervals:
        return occ.intervals[column]
    return occ.intervals.get("*", (None, None))


def _occurrences(tree: exp.Expression, sources: Optional[dict] = None) -> list[_Occurrence]:
    root = build_scope(tree)
    if root is None:
        return []
    return _walk(root, [], "", sources or {})


def _join_edges(sel: exp.Select, entity_of: dict[str, str]) -> set[tuple[str, str, str, str]]:
    edges = set()
    for join in sel.args.get("joins") or []:
        on = join.args.get("on")
        if on is None:
            continue
        for part in _split_and(on):
            if isinstance(part, exp.EQ) and isinstance(part.left, exp.Column) and isinstance(part.right, exp.Column):
                a, b = part.left, part.right
                ea, eb = entity_of.get((a.table or "").upper(), ""), entity_of.get((b.table or "").upper(), "")
                edge = (ea, a.name.upper(), eb, b.name.upper())
                edges.add(edge)
                edges.add(edge[2:] + edge[:2])
    return edges


def _entities_in(sel: exp.Select, occurrences: list[_Occurrence]) -> dict[str, str]:
    return {o.alias.upper(): o.entity for o in occurrences if o.select is sel}


def _additive(agg: exp.AggFunc) -> bool:
    """Does the CASE inside this aggregate actually remove the other rows? A CASE with no ELSE (or
    ELSE NULL) does for every aggregate — NULL is skipped by all of them. `ELSE 0` only does for a
    SUM: inside AVG, MIN, MAX or COUNT the zeros are still rows."""
    case = _aggregate_case(agg)
    if not isinstance(case, exp.Case):
        return False
    default = case.args.get("default")
    if default is None or isinstance(default, exp.Null):
        return True
    return isinstance(agg, exp.Sum) and _literal(default) == "0"


# --------------------------------------------------------------------------- root-scope helpers (kept)

class _AnswerScope(_Scope):
    """Only sources reachable from the answer; unused CTE aliases prove nothing."""
    def __init__(self, tree):
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
    """Output positions whose every aggregate is bounded by this exact period through a CASE.

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
            if not isinstance(case, exp.Case) or len(case.args.get("ifs") or []) != 1 or not _additive(aggregate):
                columns = set()
                break
            branch = case.args["ifs"][0]
            found = _bounded_columns(branch.this, period)
            columns = found if columns is None else columns & found
        related_columns = {(alias, candidate["column"].upper())
                           for alias in scope.alias_to_entity
                           for candidate in ([binding] + binding.get("alternatives", []))
                           if _accepts_bound_column(tree, scope, binding, alias, candidate["column"].upper())} if binding else set()
        if columns and _admits_period(tree.args.get("where"), columns | related_columns, period):
            inner = projection.this if isinstance(projection, exp.Alias) else projection
            def unwrap(n):
                # Take the period out of the CASE and leave the rest of the condition in: a model
                # writes `CASE WHEN TRCODE IN (7,8,9) AND <period> THEN x ELSE 0 END` where the
                # deterministic compiler nests two CASEs, and both are the certified measure over
                # the period.
                if isinstance(n, exp.AggFunc) and isinstance(_aggregate_case(n), exp.Case):
                    case = _aggregate_case(n)
                    branch = case.args["ifs"][0]
                    rest = [part for part in _split_and(branch.this)
                            if not (isinstance(part, (exp.GTE, exp.GT, exp.LT, exp.LTE)) and isinstance(part.left, exp.Column)
                                    and (part.left.table.upper(), part.left.name.upper()) in columns)]
                    value = branch.args["true"].copy()
                    if rest:
                        cond = rest[0].copy()
                        for part in rest[1:]:
                            cond = exp.And(this=cond, expression=part.copy())
                        value = exp.Case(ifs=[exp.If(this=cond, true=value)], default=case.args.get("default").copy() if case.args.get("default") is not None else None)
                    n.set("this", exp.Distinct(expressions=[value]) if isinstance(n.this, exp.Distinct) else value)
                return n
            formula = _formula(inner.copy().transform(unwrap), scope)
            outputs[pos] = (columns, formula)
    return outputs


# --------------------------------------------------------------------------- obligations

def _period_dict(t) -> dict:
    return t.to_dict() if hasattr(t, "to_dict") else dict(t)


def _bindings(sq: SemanticQuery) -> list[dict]:
    b = sq.temporal_binding
    if not b:
        return []
    return [b] + list(b.get("also") or [])


def _period_proven(period: dict, binding: dict, occ: list[_Occurrence], tree) -> bool:
    """Every source of the bound entity is read for exactly this period on the declared date
    column — its own, or a declared equivalent one it is joined to in the same SELECT."""
    start, end = period.get("start"), period.get("end")
    if not start or not end:
        return True                        # nothing to check against; the resolver should have asked
    want = (str(start)[:10], str(end)[:10])
    entity, column = binding["entity"].upper(), binding["column"].upper()
    alts = binding.get("alternatives", [])
    own = [o for o in occ if o.entity.upper() == entity]
    if own:
        pieces: list[tuple[str, str]] = []
        for o in own:
            w = _window_of(o, column)
            if w == want:
                continue
            here = [x for x in occ if x.select is o.select]
            edges = _join_edges(o.select, _entities_in(o.select, here))
            ok = False
            for alt in alts:
                edge = tuple(str(x).upper() for x in alt["join"])
                if edge not in edges:
                    continue
                aw = next((_window_of(x, alt["column"].upper()) for x in here if x.entity.upper() == alt["entity"].upper()), None)
                if aw == want:
                    ok = True
                    break
                if aw and aw[0] and aw[1]:
                    w = aw
            if ok:
                continue
            if w and w[0] and w[1] and w[0] >= want[0] and w[1] <= want[1]:
                pieces.append(w)             # a slice of the period: one year-partition of a span
                continue
            return False
        # Several sources each holding a slice: together they must be exactly the period, with no
        # gap and no overlap — the union of years the deterministic compiler writes, and the
        # double-counting shape it once wrote by mistake.
        if pieces:
            pieces.sort()
            if pieces[0][0] != want[0] or pieces[-1][1] != want[1]:
                return False
            if any(pieces[i][1] != pieces[i + 1][0] for i in range(len(pieces) - 1)):
                return False
        return True
    # The bound entity is not read at all: a declared equivalent may carry the period, provided it
    # owns the measure (a line-grain answer need not join its header to repeat the date).
    scope = _AnswerScope(tree)
    for alt in alts:
        theirs = [o for o in occ if o.entity.upper() == alt["entity"].upper()]
        if not theirs or not all(_window_of(o, alt["column"].upper()) == want for o in theirs):
            continue
        if isinstance(tree, exp.Select) and any(scope.entity_for(c).upper() == alt["entity"].upper()
                                                 for projection in tree.expressions for agg in projection.find_all(exp.AggFunc)
                                                 for c in _measure_columns(agg)):
            return True
        if not isinstance(tree, exp.Select) or not any(p.find(exp.AggFunc) for p in tree.expressions):
            return True                    # the measure is computed below the root; the sources are bounded
    return False


def _filter_proven(m, slot, occ: list[_Occurrence], tree, scope) -> bool:
    entity, column = m.entity.upper(), m.column.upper()
    expected = {str(v).strip().upper() for v in m.values}
    op = (m.operator or "IN").upper()
    compatible = {"=", "IN"} if op in ("=", "IN") else {op}
    def holds(o: _Occurrence, col: str, ops: set[str], vals: set[str]) -> bool:
        return any(p.column.upper() == col and p.operator.upper() in ops and _values(p) == vals for p in o.preds)
    own = [o for o in occ if o.entity == entity]
    if own and all(holds(o, column, compatible, expected) for o in own):
        return True
    if not own and slot.semantic_type == SemanticType.DEFAULT_FILTER and not slot.explain.get("equivalent_bindings"):
        # A default row scope restricts the rows read from its entity. An answer that never reads the
        # entity has no such rows; whether it should have read them is the measure rule's question.
        return True
    # "A and B invoices": two certified values on one column asked together are one restriction to
    # their union. Written as `IN (a, b)` the SQL proves both slots at once.
    siblings = [s for s in _filter_slots(slot_owner(slot))
                if s.mapping and s.mapping.entity == m.entity and s.mapping.column == m.column
                and (s.mapping.operator or "IN").upper() in ("=", "IN")]
    union = {str(v).strip().upper() for s in siblings for v in s.mapping.values}
    if op in ("=", "IN") and len(siblings) > 1 and expected < union and own and all(holds(o, column, {"=", "IN"}, union) for o in own):
        return True
    # A declared equivalent restriction on another entity, joined by the declared edge — or standing
    # in for the entity when the answer never reads it.
    for alt in slot.explain.get("equivalent_bindings", []):
        aop = alt["operator"].upper()
        aops = {"=", "IN"} if aop in ("=", "IN") else {aop}
        avals = {str(v).upper() for v in alt["values"]}
        theirs = [o for o in occ if o.entity.upper() == alt["entity"].upper()]
        if not theirs or not all(holds(o, alt["column"].upper(), aops, avals) for o in theirs):
            continue
        if not own:
            return True
        edge = tuple(str(x).upper() for x in alt["join"])
        if all(edge in _join_edges(o.select, _entities_in(o.select, [x for x in occ if x.select is o.select])) for o in own):
            return True
    # A pivot legitimately puts alternative restrictions in distinct additive aggregates. Each
    # requested restriction must have its own.
    if isinstance(tree, exp.Select):
        matches = []
        for projection in tree.expressions:
            aggregates = list(projection.find_all(exp.AggFunc))
            if not aggregates:
                continue
            conditions = []
            for agg in aggregates:
                case = _aggregate_case(agg)
                if not isinstance(case, exp.Case) or len(case.args.get("ifs") or []) != 1 or not _additive(agg):
                    break
                conditions.append(case.args["ifs"][0].this)
            else:
                matches.append(all(any(p.entity.upper() == entity and p.column.upper() == column
                                       and p.operator.upper() in compatible and _values(p) == expected
                                       for p in _predicates_from(c, scope, "case", None)) for c in conditions))
                continue
            matches.append(False)
        pivot_values = {tuple(sorted(str(v).upper() for v in s.mapping.values)) for s in _filter_slots(slot_owner(slot))
                        if s.mapping and s.mapping.entity == m.entity and s.mapping.column == m.column}
        # A pivot is also what the SQL itself shows: other output columns restricting the same column to
        # other values ("returns" next to "sales") — the restriction belongs to its column, not to the row set.
        competing = {tuple(sorted(_values(p))) for projection in tree.expressions for agg in projection.find_all(exp.AggFunc)
                     if isinstance(_aggregate_case(agg), exp.Case)
                     for branch in _aggregate_case(agg).args.get("ifs") or []
                     for p in _predicates_from(branch.this, scope, "case", None)
                     if p.entity.upper() == entity and p.column.upper() == column and p.operator.upper() in ("=", "IN")}
        pivot = len(pivot_values) > 1 or len(competing) > 1
        if matches and (any(matches) if pivot else all(matches)):
            return True
    return False


def _filter_slots(sq):
    return sq.filters + [s for s in sq.slots if s.semantic_type == SemanticType.DEFAULT_FILTER]


def slot_owner(slot):
    return getattr(slot, "_owner", None) or _EMPTY


class _EmptyQuery:
    filters: list = []
    slots: list = []
_EMPTY = _EmptyQuery()


def _group_columns(sel: exp.Select, occ: list[_Occurrence]) -> set[tuple[str, str]]:
    """(entity, COLUMN) pairs a GROUP BY reaches, following pass-through names into derived sources."""
    found: set[tuple[str, str]] = set()
    group = sel.args.get("group")
    if group is None:
        return found
    here = {o.alias.upper(): o for o in occ if o.select is sel}
    single = len({(o.alias) for o in occ if o.select is sel}) == 1
    for g in group.expressions:
        for c in _columns_of(g):
            key = (c.table or "").upper()
            if key in here or (not key and single and here):
                o = here.get(key) or next(iter(here.values()))
                found.add((o.entity.upper(), c.name.upper()))
    return found


def _all_group_columns(tree, occ: list[_Occurrence]) -> set[tuple[str, str]]:
    found = set()
    selects = {o.select for o in occ}
    for sel in selects:
        found |= _group_columns(sel, occ)
    # A derived source that groups is also a breakdown of the answer built on it.
    return found


def _grain_present(tree, grain: str, occ: list[_Occurrence]) -> bool:
    for sel in {o.select for o in occ} | ({tree} if isinstance(tree, exp.Select) else set()):
        group = sel.args.get("group")
        if group is None:
            continue
        for g in group.expressions:
            if _grain_of(g) == grain:
                return True
        # GROUP BY a name computed in the projection (`GROUP BY ay` with `MONTH(d) AS ay`).
        by_name = {(e.alias_or_name or "").upper(): (e.this if isinstance(e, exp.Alias) else e) for e in sel.expressions}
        for g in group.expressions:
            if isinstance(g, exp.Column) and not g.table and g.name.upper() in by_name and _grain_of(by_name[g.name.upper()]) == grain:
                return True
    return False


def _found_formulas(tree, occ: list[_Occurrence]) -> set[str]:
    """Every aggregate expression the statement computes, normalised to ENTITY.COLUMN, in every scope
    the answer reads — plus the variant with a carried WHERE restriction folded back into a CASE."""
    out: set[str] = set()
    for sel in {o.select for o in occ} | ({tree} if isinstance(tree, exp.Select) else set()):
        scope = _Scope(sel, None)
        for o in occ:
            if o.select is sel:
                scope.alias_to_entity[o.alias.upper()] = o.entity
        for e in sel.expressions:
            inner = e.this if isinstance(e, exp.Alias) else e
            if not inner.find(exp.AggFunc):
                continue
            out.add(_formula(inner, scope))
            for agg in inner.find_all(exp.AggFunc):
                out.add(_formula(agg, scope))
    return out


def _strip_case(expected_tree: exp.Expression, carried: set[tuple[str, str, str, tuple]]) -> exp.Expression:
    """The certified formula's CASE, when every condition of it is already a restriction on the rows
    the aggregate reads, is the same number as the bare aggregate."""
    stub_cache: dict[str, _Stub] = {}
    def tx(n):
        if isinstance(n, exp.AggFunc) and isinstance(_aggregate_case(n), exp.Case):
            case = _aggregate_case(n)
            ifs = case.args.get("ifs") or []
            default = case.args.get("default")
            if len(ifs) != 1 or (default is not None and not isinstance(default, exp.Null) and _literal(default) != "0"):
                return n
            preds = []
            for part in _split_and(ifs[0].this):
                cols = _columns_of(part)
                if not cols:
                    return n
                ent = (cols[0].table or "").upper()
                p = _single_predicate(part, stub_cache.setdefault(ent, _Stub(ent)), "case", None)
                if p is None:
                    return n
                preds.append((p.entity.upper(), p.column.upper(), p.operator.upper(), tuple(sorted(_values(p)))))
            if all(p in carried for p in preds):
                value = ifs[0].args["true"].copy()
                m = n.copy()
                m.set("this", exp.Distinct(expressions=[value]) if isinstance(n.this, exp.Distinct) else value)
                return m
        return n
    return expected_tree.copy().transform(tx)


def _measure_proven(formula: str, tree, occ: list[_Occurrence]) -> bool:
    try:
        expected_tree = parse_sql(formula)
    except Exception:  # noqa: BLE001
        return True                        # a formula this cannot read is the catalog's problem, not the answer's
    scope = _Scope(tree, None)
    found = _found_formulas(tree, occ)
    want = _formula(expected_tree, scope)
    if want in found:
        return True
    carried = {(o.entity.upper(), p.column.upper(), p.operator.upper(), tuple(sorted(_values(p)))) for o in occ for p in o.preds}
    folded = _formula(_strip_case(expected_tree, carried), scope)
    if folded in found:
        return True
    # A ratio or difference assembled from parts: each certified aggregate computed somewhere, the
    # arithmetic done on the way out.
    parts = [_formula(a, scope) for a in expected_tree.find_all(exp.AggFunc)]
    folded_parts = [_formula(a, scope) for a in _strip_case(expected_tree, carried).find_all(exp.AggFunc)]
    if parts and (all(p in found for p in parts) or all(p in found for p in folded_parts)):
        return True
    return False


def _strict_default() -> bool:
    import os
    return os.environ.get("SEMANTIC_GATE_STRICT", "").strip().lower() in ("1", "true", "on", "yes")


def gate_report(sq: SemanticQuery, sql: str, *, sources: Optional[dict] = None, strict: Optional[bool] = None) -> list[Unmet]:
    """Every resolved requirement the SQL does not demonstrate. Empty means the answer may be served."""
    if sq.analytics:
        from semantic_layer.runtime.monthly_analysis import check
        return [Unmet("analytics", t) for t in check(sq, sql, unmet_obligations)]
    out: list[Unmet] = []
    try:
        tree = parse_sql(sql)
    except Exception:
        return [Unmet("parse", "sorgu ayrıştırılamadı; soru koşulları doğrulanamadı", "Geçerli tek bir SELECT yaz.")]
    occ = _occurrences(tree, sources)
    strict = _strict_default() if strict is None else strict
    for s in sq.slots:
        s._owner = sq                       # the pivot rule needs to see its sibling filters

    comp = sq.comparison
    if comp:
        current, reference = comp.get("current"), comp.get("reference")
        comp["satisfied"] = False
        if not current or not reference:
            out.append(Unmet("comparison", str(comp.get("why") or "karşılaştırmanın iki dönemi belirlenemedi")))
        else:
            matched, why = _comparison_proven(sq, tree, occ, current, reference)
            if not matched:
                out.append(Unmet("comparison", why, "İki dönemi ayrı sütunlarda hesapla: her ölçü için biri güncel dönem, biri karşılaştırma dönemi.",))
            comp["satisfied"] = matched

    if not comp and sq.temporal:
        for binding in _bindings(sq):
            for period in sq.temporal:
                p = _period_dict(period)
                if not _period_proven(p, binding, occ, tree):
                    text = getattr(period, "text", None) or p.get("text") or f"{p.get('start')}–{p.get('end')}"
                    out.append(Unmet("period", f"'{text}' dönemi doğru tarih sütununda doğrulanamadı" + _opaque_note(occ, binding['entity']),
                                     f"{binding['entity']} kaynağını {binding['column']} >= '{p.get('start')}' AND {binding['column']} < '{p.get('end')}' ile sınırla (kaynağı okuyan her SELECT/CTE'de).",
                                     binding["entity"], binding["column"]))

    scope = _AnswerScope(tree)
    # A qualifier the source explains on a column ("iptal edilmemiş" → CANCELLED — "İptal Edilmiş").
    # Which value means what was deliberately left to the query; that this column restricts the
    # answer is not optional, or the word was silently dropped.
    for want in getattr(sq, "qualifier_columns", None) or []:
        column, entity = str(want.get("column", "")).upper(), str(want.get("entity", "")).upper()
        restricting = [tree.args.get("where")] + list(tree.args.get("joins") or []) if isinstance(tree, exp.Select) else []
        def same_entity(name: str) -> bool:
            # A physical table reads back as INVOICE where the catalog calls the shape LG_INVOICE:
            # the prefix is the source's, not the question's, so it may not decide this.
            a, b = name.upper().removeprefix("LG_"), entity.removeprefix("LG_")
            return name.upper() == "UNKNOWN" or a == b

        used = any(col.name.upper() == column and same_entity(scope.entity_for(col))
                   for node in restricting if node is not None for col in node.find_all(exp.Column))
        if not used:
            out.append(Unmet("qualifier", f"'{want.get('token')}' niteleyicisi {entity}.{column} üzerinde kısıtlanmadı",
                             f"{entity}.{column} kolonunu WHERE'de kısıtla; hangi değerin ne demek olduğunu "
                             f"kolon açıklamasından oku ({want.get('description')}).", entity, column))

    for slot in _filter_slots(sq):
        m = slot.mapping
        if not m or not m.column or slot.status not in ("CERTIFIED", "INFERRED"):
            continue
        if not _filter_proven(m, slot, occ, tree, scope):
            op = (m.operator or "IN").upper()
            vals = sorted({str(v).strip().upper() for v in m.values})
            out.append(Unmet("filter", f"'{slot.term}' koşulu sonuç kapsamında doğrulanamadı: {m.entity}.{m.column} {op} {vals}" + _opaque_note(occ, m.entity),
                             f"{m.entity} kaynağını okuyan her SELECT/CTE'nin WHERE'ine {m.column} {op} ({', '.join(vals)}) ekle.",
                             m.entity, m.column))

    # A certified dimension can define which reference wins when header and line
    # values differ. Merely mentioning the target table cannot establish this.
    from semantic_layer.runtime.reference_contracts import reference_rule, reference_predicate, via_predicate
    for metric in sq.metrics:
        if not metric.mapping:
            continue
        fact = metric.mapping.entity
        for slot in sq.group_by:
            if not slot.mapping:
                continue
            rule = reference_rule(slot.mapping, fact)
            if not rule:
                continue
            def equality(node, context):
                if not isinstance(node, exp.EQ):
                    return None
                return frozenset((_normalise_formula(node.left, context), _normalise_formula(node.right, context)))
            actual = {equality(part, scope) for join in tree.args.get("joins") or []
                      if join.args.get("on") is not None for part in _split_and(join.args["on"])}
            for expression in (via_predicate(fact, rule), reference_predicate(slot.mapping, fact, rule)):
                expected_tree = parse_sql(expression)
                expected_scope = _Scope(expected_tree, None)
                if "{" not in slot.mapping.table_pattern:
                    expected_scope.alias_to_entity[slot.mapping.entity.upper()] = logical_table(slot.mapping.table_pattern).entity
                expected = equality(expected_tree, expected_scope)
                if expected not in actual:
                    out.append(Unmet("reference", f"'{slot.term}' ilişki önceliği doğrulanamadı: {expression}", f"JOIN koşulu olarak {expression} kullan."))
                elif (expression == reference_predicate(slot.mapping, fact, rule)
                      and (slot.mapping.extra or {}).get("join_kind") == "LEFT"
                      and not any(str(join.args.get("side", "")).upper() == "LEFT"
                                  and any(equality(part, scope) == expected for part in _split_and(join.args["on"]))
                                  for join in tree.args.get("joins") or [] if join.args.get("on") is not None)):
                    out.append(Unmet("reference", f"'{slot.term}' atanmamış değerleri koruyan ilişki doğrulanamadı", "Bu ilişkiyi LEFT JOIN olarak yaz."))

    if not strict:
        return out + _closing(sq, tree)

    # The measure itself: the certified formula, or the same number with its CASE folded into a
    # WHERE that provably reaches the rows, or its aggregate parts computed and combined on the way out.
    for metric in sq.metrics:
        m = metric.mapping
        if not m or not m.formula or metric.status not in ("CERTIFIED", "INFERRED"):
            continue
        if not any(o.entity.upper() == m.entity.upper() for o in occ):
            continue                        # reported by the period/filter rules on that entity, or by the audit
        if not _measure_proven(m.formula, tree, occ):
            out.append(Unmet("measure", f"'{metric.term}' ölçüsü sertifikalı formülle hesaplanmamış: {m.formula}",
                             f"'{metric.term}' için tam olarak şu ifadeyi kullan: {m.formula}", m.entity))

    # The breakdown the question asked for.
    if sq.grain and not sq.comparison and not _grain_present(tree, sq.grain, occ):
        out.append(Unmet("grain", f"istenen kırılım ({sq.grain}) sonuçta yok",
                         {"MONTH": "Sonucu ay bazında grupla (GROUP BY ay).", "DAY": "Sonucu gün bazında grupla.",
                          "YEAR": "Sonucu yıl bazında grupla.", "WEEK": "Sonucu hafta bazında grupla."}.get(sq.grain, "Sonucu istenen kırılımda grupla.")))
    grouped = _all_group_columns(tree, occ)
    for slot in sq.group_by:
        m = slot.mapping
        if not m or not m.column:
            continue
        if (m.entity.upper(), m.column.upper()) not in grouped:
            out.append(Unmet("grain", f"'{slot.term}' kırılımı sonuçta yok: GROUP BY {m.entity}.{m.column} bekleniyor",
                             f"Sonucu {m.entity}.{m.column} ile grupla ve o kolonu göster.", m.entity, m.column))

    # "The top N" is a limit and an order, not a suggestion.
    if sq.limit and isinstance(tree, exp.Select):
        limit = tree.args.get("limit")
        n = _literal(limit.expression) if isinstance(limit, exp.Limit) else None
        order = tree.args.get("order")
        first = order.expressions[0] if order is not None and order.expressions else None
        desc = bool(first.args.get("desc")) if first is not None else None
        if n != str(sq.limit) or first is None or desc != bool(sq.order_desc):
            out.append(Unmet("limit", f"ilk {sq.limit} için sıralama/sınır doğrulanamadı",
                             f"Ölçüye göre {'azalan' if sq.order_desc else 'artan'} sırala ve {sq.limit} satırla sınırla."))

    return out + _closing(sq, tree)


def _closing(sq, tree) -> list[Unmet]:
    out = []
    if sq.shape == "ABSENCE":
        expected = (sq.absence_contract or {}).get("sql")
        if not expected or parse_sql(expected) != tree:
            out.append(Unmet("absence", "yokluk koşulunun varlık, ilişki ve dönem kapsamı doğrulanamadı"))
    if sq.measure_expressions:
        out.append(Unmet("expression", "hesap ifadesinin bileşenleri ve işlemi sertifikalı bir formülle doğrulanmadı"))
    return out


def _opaque_note(occ, entity: str) -> str:
    names = sorted({x for o in occ if o.entity.upper() == entity.upper() for x in o.opaque})
    return f" (anlaşılmayan yapı: {', '.join(names[:3])} türetilmiş bir kolon üzerinden yazılmış)" if names else ""


def _comparison_proven(sq, tree, occ, current, reference) -> tuple[bool, str]:
    from semantic_layer.runtime.compiler import _pred_key_sql, _wrap_condition, _can_scope_formula, Dialect
    why = (f"karşılaştırma dönemleri ayrı ölçü sütunlarında doğrulanamadı: "
           f"{current.get('start')}–{current.get('end')}, {reference.get('start')}–{reference.get('end')}")
    if (current.get("start"), current.get("end")) == (reference.get("start"), reference.get("end")):
        return False, why
    scope = _AnswerScope(tree)
    measures = [s for s in sq.metrics if s.mapping and s.mapping.formula]
    scopes = [tuple(sorted(set(_pred_key_sql(s.mapping.entity, key, Dialect("tsql")) or ""
                              for key in (s.mapping.extra or {}).get("conditions", []))))
              for s in measures]
    expected = set()
    expected_formulas: list[str] = []          # one per measure, scoped the way the catalog scopes it
    for s, predicates in zip(measures, scopes):
        formula = s.mapping.formula
        if "" in predicates:
            return False, "ölçünün katalog kapsamı doğrulanamadı"
        if len(set(scopes)) > 1 and predicates:
            if not _can_scope_formula(formula):
                return False, "ölçü kapsamının bu formüle uygulanması doğrulanamadı"
            formula = _wrap_condition(formula, " AND ".join(f"({p})" for p in predicates))
        expected.add(_formula(parse_sql(formula), _Scope(tree, None)))
        expected_formulas.append(formula)
    binding = sq.temporal_binding

    # (a) one SELECT, the periods as CASE conditions inside additive aggregates
    left, right = _period_outputs(tree, current, scope, binding), _period_outputs(tree, reference, scope, binding)
    def correct_column(columns):
        if binding:
            return any(_accepts_bound_column(tree, scope, binding, alias, col) for alias, col in columns)
        return any((not sq.comparison.get("dateColumn") or col == sq.comparison["dateColumn"].upper())
                   and (not sq.comparison.get("entity") or scope.entity_for(exp.column(col, table=alias or None)).upper() == sq.comparison["entity"].upper())
                   for alias, col in columns)
    proven = {af for a, (ac, af) in left.items() for b, (bc, bf) in right.items()
              if a != b and af == bf and correct_column(ac & bc)}
    # The measure's own CASE may have been pushed into the WHERE of the rows read: the same number.
    carried = {(o.entity.upper(), p.column.upper(), p.operator.upper(), tuple(sorted(_values(p)))) for o in occ for p in o.preds}
    def satisfied(found: set[str]) -> bool:
        if not expected:
            return bool(found)
        for formula in expected_formulas:
            variants = {_formula(parse_sql(formula), _Scope(tree, None)),
                        _formula(_strip_case(parse_sql(formula), carried), _Scope(tree, None))}
            if not variants & found:
                return False
        return True
    if proven and satisfied(proven):
        return True, ""

    want_cur = (str(current["start"])[:10], str(current["end"])[:10])
    want_ref = (str(reference["start"])[:10], str(reference["end"])[:10])
    entity = (binding or {}).get("entity") or sq.comparison.get("entity") or ""
    column = ((binding or {}).get("column") or sq.comparison.get("dateColumn") or "").upper()
    alt_cols = {(a["entity"].upper(), a["column"].upper()) for a in (binding or {}).get("alternatives", [])}

    def period_of(o: _Occurrence):
        if o.entity.upper() == entity.upper():
            return _window_of(o, column)
        if (o.entity.upper(), column) in alt_cols or any(o.entity.upper() == e for e, _ in alt_cols):
            col = next((c for e, c in alt_cols if e == o.entity.upper()), column)
            return _window_of(o, col)
        return None

    # (b) one derived source per period, one output column from each
    if isinstance(tree, exp.Select):
        by_root: dict[str, list[_Occurrence]] = {}
        for o in occ:
            by_root.setdefault(o.root_alias.upper(), []).append(o)
        period_of_alias = {}
        for alias, group in by_root.items():
            periods = {period_of(o) for o in group if period_of(o) is not None}
            if len(periods) == 1:
                period_of_alias[alias] = next(iter(periods))
        got: dict[tuple, set[str]] = {}
        for e in tree.expressions:
            inner = e.this if isinstance(e, exp.Alias) else e
            cols = _columns_of(inner)
            aliases = {(c.table or "").upper() for c in cols}
            if len(aliases) != 1 or inner.find(exp.AggFunc):
                continue
            alias = next(iter(aliases))
            p = period_of_alias.get(alias)
            if p not in (want_cur, want_ref):
                continue
            # what the derived source computes under that name
            src = next((o for o in occ if o.root_alias.upper() == alias), None)
            if src is None:
                continue
            sel = src.select
            sscope = _Scope(sel, None)
            for o in occ:
                if o.select is sel:
                    sscope.alias_to_entity[o.alias.upper()] = o.entity
            for pe in sel.expressions:
                if (pe.alias_or_name or "").upper() == cols[0].name.upper():
                    pin = pe.this if isinstance(pe, exp.Alias) else pe
                    if pin.find(exp.AggFunc):
                        got.setdefault(p, set()).add(_formula(pin, sscope))
        both = got.get(want_cur, set()) & got.get(want_ref, set())
        if both and satisfied(both):
            return True, ""

    # (c) GROUP BY a period key over the union of both periods
    if isinstance(tree, exp.Select) and tree.args.get("group") is not None:
        lo = min(want_cur[0], want_ref[0])
        hi = max(want_cur[1], want_ref[1])
        adjacent = want_cur[0] == want_ref[1] or want_ref[0] == want_cur[1]
        own = [o for o in occ if period_of(o) is not None]
        if adjacent and own and all(period_of(o) == (lo, hi) for o in own):
            keyed = any(_grain_of(g) in ("YEAR", "MONTH", "DAY", "WEEK") for g in tree.args["group"].expressions)
            if keyed:
                found = _found_formulas(tree, occ)
                if satisfied(found):
                    return True, ""
    return False, why


def unmet_obligations(sq: SemanticQuery, sql: str, *, sources: Optional[dict] = None, strict: Optional[bool] = None) -> list[str]:
    """Fail closed when the final SQL does not demonstrate a resolved requirement."""
    return [u.text for u in gate_report(sq, sql, sources=sources, strict=strict)]


def sources_from(profiles, *, declared: Optional[set[str]] = None) -> dict[str, dict]:
    """What the gate may assume about each physical table: column types (whether `<= day` reaches the
    end of the day) and, only for tables in `declared`, a coverage window that stands in for a date
    filter. A measured min/max never does — an incomplete load would make an unfiltered query pass."""
    out: dict[str, dict] = {}
    declared = {d.upper() for d in (declared or set())}
    for p in profiles or []:
        w = getattr(p, "time_window", None)
        dw = getattr(p, "declared_window", None)      # set by semantic_layer.coverage.apply: declared and not refuted
        entry = {"types": {c.name.upper(): (c.data_type or "") for c in getattr(p, "columns", [])},
                 "window": (str(dw[0]), str(dw[1])) if dw else ((str(w[0]), str(w[1])) if w and w[0] and w[1] else None),
                 "declared": bool(dw) or p.table_name.upper() in declared}
        out[p.table_name.upper()] = entry
        if getattr(p, "schema_name", ""):
            out[f"{p.schema_name}_{p.table_name}".upper()] = entry
            out[f"{p.schema_name}.{p.table_name}".upper()] = entry
    return out


__all__ = ["audit_sql", "unmet_obligations", "gate_report", "Unmet", "sources_from"]
