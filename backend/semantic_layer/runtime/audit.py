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

import re

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Optional

from sqlglot import exp
from sqlglot.optimizer.scope import Scope, build_scope

from semantic_layer.history.sql_facts import (_Scope, _grain_of, _literal, _normalise_formula, _predicates_from,
                                              _single_predicate, _split_and, extract_sql_facts, parse_sql)
from semantic_layer.models import SemanticQuery, SemanticType
from semantic_layer.naming import logical_table


def _ent(name: str) -> str:
    """An entity name as the gate compares it: upper-cased, without the source's "LG_" prefix. The catalog
    names one shape both ways (a measure on the bare name, a filter on the prefixed one) and a physical
    table reads back bare: the prefix is the source's, not the question's, and may not decide."""
    n = re.sub(r"^[A-Z0-9_]+?_DBO_", "", (name or "").upper())     # "Timas_MSCRM_dbo_NEW_X": a second source's table
    return re.sub(r"^LG_", "", n)


def _same_entity(a: str, b: str) -> bool:
    return _ent(a) == _ent(b)


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
    refs: dict[str, str] = field(default_factory=dict)   # this table's reference columns → the entity they point at


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
    unpreserved: dict[str, list[exp.Expression]] = {}
    for join in sel.args.get("joins") or []:
        on = join.args.get("on")
        # Only an inner join's ON drops rows. On the unpreserved side of an outer join it only
        # decides what the row is paired with, and the row stays in the answer.
        if on is not None and not (join.side or "").strip() and (join.kind or "").upper() != "CROSS":
            local.extend(_split_and(on))
        elif on is not None and (join.side or "").strip().upper() == "LEFT":
            # …but the joined table's *own* rows are read only where the ON admits them:
            # `LEFT JOIN STLINE sl ON sl.INVOICEREF = i.LOGICALREF AND sl.CANCELLED = 0` reads no
            # cancelled line. That is the one place a restriction on the right side can be written
            # without dropping the left side's rows, so it counts for that table alone.
            joined = (join.this.alias_or_name if isinstance(join.this, (exp.Table, exp.Subquery)) else "") or ""
            if joined:
                unpreserved[joined.upper()] = [c for c in _split_and(on) if _belongs(c, joined, False)]
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
        mine = [c for c in conj if _belongs(c, alias, single)] + [_unwrap_isnull(c) for c in unpreserved.get(alias.upper(), [])]
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
            src = sources.get(name.upper()) or sources.get(source.name.upper()) or sources.get(_ent(entity)) or sources.get("LG_" + _ent(entity)) or {}
            # A measured min/max is a statistic, not a promise: only a declared coverage stands in for a date filter.
            occ.intervals = _intervals(mine, src.get('window') if src.get('declared') else None, src.get('types') or {})
            occ.refs = dict(src.get("refs") or {})
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
    # A correlated subquery — `WHERE EXISTS (SELECT 1 FROM LG_ORFICHE o WHERE o.TRCODE IN (1) …)` — reads
    # its table under its own WHERE. Unvisited, the order filter written there was "not in the result's
    # scope" and a correct statement was refused for the very condition it carried.
    for sub in getattr(scope, "subquery_scopes", None) or []:
        out.extend(_walk(sub, [], root_alias, sources, opaque))
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
            if any(_same_entity(scope.entity_for(c), entity) for projection in tree.expressions
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
    # `DATE_ IS NOT NULL` on the period column discards nothing a period could hold: a row with no
    # date is in neither year. Read as a restriction it refused a correct comparison.
    if isinstance(node, exp.Not) and isinstance(node.this, exp.Is) and isinstance(node.this.expression, exp.Null):
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
    own = [o for o in occ if _same_entity(o.entity, entity)]
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
                aw = next((_window_of(x, alt["column"].upper()) for x in here if _same_entity(x.entity, alt["entity"])), None)
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
        theirs = [o for o in occ if _same_entity(o.entity, alt["entity"])]
        if not theirs or not all(_window_of(o, alt["column"].upper()) == want for o in theirs):
            continue
        if isinstance(tree, exp.Select) and any(_same_entity(scope.entity_for(c), alt["entity"])
                                                 for projection in tree.expressions for agg in projection.find_all(exp.AggFunc)
                                                 for c in _measure_columns(agg)):
            return True
        if not isinstance(tree, exp.Select) or not any(p.find(exp.AggFunc) for p in tree.expressions):
            return True                    # the measure is computed below the root; the sources are bounded
    return False


def _question_word_literals(sq: SemanticQuery, tree: exp.Expression) -> list[tuple[str, str]]:
    """(word, column) for every string literal compared to a column when the literal is a term of
    the question that the resolver placed on that very column — or on any column, as a bare noun."""
    from semantic_layer.normalize import fold as _f
    slot_words: dict[str, Optional[str]] = {}
    for sl in sq.slots:
        m = sl.mapping
        # A value slot ("İstanbul" → CITY = 'İstanbul') is the question's word *as* a value; only a
        # word that named a column or an entity has no value to be.
        if m is None or m.values or str(sl.semantic_type or "").upper() not in (SemanticType.COLUMN, SemanticType.ENTITY):
            continue
        col = f"{m.entity}.{m.column}" if m.column else m.entity
        for w in str(sl.term or "").split():
            slot_words[_f(w)] = col
    if not slot_words:
        return []
    out: list[tuple[str, str]] = []
    for node in tree.find_all(exp.EQ, exp.Like, exp.ILike):
        col, lit = None, None
        for side in (node.left, node.right):
            if isinstance(side, exp.Column):
                col = side
            elif isinstance(side, exp.Literal) and side.is_string:
                lit = side
        if col is None or lit is None:
            continue
        word = _f(str(lit.this).strip().strip("%"))
        if word and word in slot_words and not any(ch.isdigit() for ch in word):
            out.append((str(lit.this), col.sql()))
    return out


def _cond_columns(conditions: list[str]) -> list[str]:
    out = []
    for c in conditions:
        mm = re.match(r"^\s*([A-Za-z_][\w]*\.[A-Za-z_][\w]*)", c or "")
        if mm:
            out.append(mm.group(1))
    return out


def _state_reading(sq: SemanticQuery, o: _Occurrence) -> bool:
    """This occurrence computes a state measure of the question: it reads the measure's entity under
    the measure's own conditions only, with no period on it."""
    for metric in sq.metrics:
        m = metric.mapping
        if not m or not (m.extra or {}).get("state_measure"):
            continue
        ent = m.entity.upper()
        if o.entity.upper() not in (ent, re.sub(r"^LG_", "", ent), "LG_" + ent):
            continue
        own_cols = {c.split(".")[-1].upper() for c in _cond_columns((m.extra or {}).get("conditions") or [])}
        if _unrestricted_reading(o, own_cols):
            return True
    return False


_COND = re.compile(r"^\s*(?:[A-Za-z_]\w*\.)?([A-Za-z_]\w*)\s*(?:=|\bIN\b)\s*\(?\s*([^()<>=]*?)\s*\)?\s*$", re.I)


_COLCMP = re.compile(r"^\s*(?:[A-Za-z_]\w*\.)?([A-Za-z_]\w*)\s*(<>|!=|>=|<=|=|>|<)\s*\(?\s*(?:[A-Za-z_]\w*\.)?([A-Za-z_]\w*)\s*\)?\s*$", re.I)


def _condition_holds(cond: str, own: list[_Occurrence]) -> bool:
    """Every reading of the entity carries this catalog condition: a value test as a predicate on the
    column, a column-to-column comparison as a conjunct with the same two columns and operator."""
    mm = _COND.match(cond)
    if mm:
        col = mm.group(1).upper()
        want = {v.strip().strip("'\"").upper() for v in mm.group(2).split(",") if v.strip()}
        return all(any(p.column.upper() == col and p.operator.upper() in ("=", "IN") and _values(p) == want for p in o.preds) for o in own)
    cc = _COLCMP.match(cond)
    if cc and cc.group(3).upper() not in ("NULL",) and not cc.group(3).isdigit():
        left, op, right = cc.group(1).upper(), cc.group(2), cc.group(3).upper()
        flipped = {">": "<", "<": ">", ">=": "<=", "<=": ">=", "=": "=", "<>": "<>", "!=": "!="}[op]
        def has(o: _Occurrence) -> bool:
            for c in o.conjuncts:
                for node in c.find_all(exp.Binary):
                    if not isinstance(node, (exp.GT, exp.LT, exp.GTE, exp.LTE, exp.EQ, exp.NEQ)):
                        continue
                    a, b = node.this, node.expression
                    if not (isinstance(a, exp.Column) and isinstance(b, exp.Column)):
                        continue
                    o_ = {exp.GT: ">", exp.LT: "<", exp.GTE: ">=", exp.LTE: "<=", exp.EQ: "=", exp.NEQ: "<>"}[type(node)]
                    pair = (a.name.upper(), b.name.upper())
                    if (pair == (left, right) and o_ == op) or (pair == (right, left) and o_ == flipped):
                        return True
            return False
        return all(has(o) for o in own)
    return True                                     # a shape this proof does not read is not a refusal


def _stand_in_note(cond: str, own: list[_Occurrence], occ: list[_Occurrence]) -> str:
    """The repair hint for a condition the statement wrote on *another* table's same-named column
    (`f.TRCODE = 1` on the order header for `LG_ORFLINE.TRCODE IN (1)`). Told only "add TRCODE IN (1)",
    the model sees TRCODE = 1 already there and returns the same statement. Whether the two columns
    always agree is not something the catalog declares, so the header's column proves nothing about
    the line's rows; the hint names the alias the condition is owed on and the predicate that does
    not count."""
    mm = _COND.match(cond)
    if not mm:
        return ""
    col = mm.group(1).upper()
    want = {v.strip().strip("'\"").upper() for v in mm.group(2).split(",") if v.strip()}
    def carries(o: _Occurrence) -> bool:
        return any(p.column.upper() == col and p.operator.upper() in ("=", "IN") and _values(p) == want for p in o.preds)
    notes = []
    for o in own:
        if carries(o):
            continue
        elsewhere = [x for x in occ if x is not o and x.select is o.select and not _same_entity(x.entity, o.entity) and carries(x)]
        target = f"{o.alias}.{col}"
        if elsewhere:
            x = elsewhere[0]
            notes.append(f" Koşul şu an {x.alias}.{col} ({x.table}) üzerinde yazılı; o başka tablonun kolonudur ve "
                         f"{o.table} satırlarını kanıtlamaz. Aynı koşulu {target} üzerinde de yaz: {target} IN ({', '.join(sorted(want))}).")
        else:
            notes.append(f" Koşul {o.table} tablosunun kendi takma adıyla yazılmalı: {target} IN ({', '.join(sorted(want))}).")
    return "".join(dict.fromkeys(notes))


def _zero_admitted(having: exp.Expression) -> bool:
    """Every AND-part of this HAVING compares an aggregate to a number and a total of zero passes
    it (`<= 0`, `= 0`, `< 5`). Anything this cannot read is not a claim."""
    parts = _split_and(having)
    if not parts:
        return False
    for part in parts:
        if not isinstance(part, (exp.LTE, exp.LT, exp.EQ, exp.GTE, exp.GT, exp.NEQ)):
            return False
        left, right, kind = part.left, part.right, type(part)
        if _literal(left) is not None and right.find(exp.AggFunc) is not None:
            left, right = right, left
            kind = {exp.LTE: exp.GTE, exp.LT: exp.GT, exp.GTE: exp.LTE, exp.GT: exp.LT}.get(kind, kind)
        if left.find(exp.AggFunc) is None:
            return False
        try:
            n = float(_literal(right))
        except (TypeError, ValueError):
            return False
        ok = {exp.LTE: 0 <= n, exp.LT: 0 < n, exp.EQ: n == 0, exp.GTE: 0 >= n, exp.GT: 0 > n, exp.NEQ: n != 0}[kind]
        if not ok:
            return False
    return True


def _rowless_dropped(tree: exp.Expression, entity: str) -> Optional[str]:
    """A state measure (a balance) is zero for a record with no movement rows at all. A statement
    that keeps the records whose balance passes a test zero also passes — "none left": balance <= 0 —
    by *membership* in an aggregated reading of the movements (`key IN (SELECT … GROUP BY … HAVING
    SUM(…) <= 0)`, `EXISTS (…)`, an inner join to that derived table) silently drops every record
    that never moved: they have no group to be a member of. The same question written as
    `NOT EXISTS (… HAVING SUM(…) > 0)` keeps them, and the two answers differ by exactly those
    records. Returns the offending construct, or None."""
    def reads(sel: exp.Expression) -> bool:
        return any(_same_entity(logical_table((t.db + "." if t.db else "") + t.name).entity, entity) for t in sel.find_all(exp.Table))
    def offending(sel: Optional[exp.Expression]) -> bool:
        if not isinstance(sel, exp.Select):
            return False
        having = sel.args.get("having")
        return having is not None and reads(sel) and _zero_admitted(having.this)
    for node in tree.find_all(exp.In):
        q = node.args.get("query")
        if q is not None and not isinstance(node.parent, exp.Not) and offending(q.this if isinstance(q, exp.Subquery) else q):
            return "IN (… HAVING …)"
    for node in tree.find_all(exp.Exists):
        if not isinstance(node.parent, exp.Not) and offending(node.this):
            return "EXISTS (… HAVING …)"
    for sel in tree.find_all(exp.Select):
        for join in sel.args.get("joins") or []:
            if (join.side or "").strip() or (join.kind or "").upper() == "CROSS":
                continue
            if isinstance(join.this, exp.Subquery) and offending(join.this.this):
                return "INNER JOIN (… HAVING …)"
    # The same membership through a CTE: `WITH b AS (… HAVING SUM(…) <= 0) SELECT … FROM x JOIN b …`.
    named = {c.alias_or_name.upper() for c in tree.find_all(exp.CTE) if offending(c.this)}
    if named:
        for sel in tree.find_all(exp.Select):
            frm = sel.args.get("from_") or sel.args.get("from")      # sqlglot 30 names the arg `from_`
            sources = [frm.this] if frm is not None else []
            sources += [j.this for j in sel.args.get("joins") or [] if not (j.side or "").strip() and (j.kind or "").upper() != "CROSS"]
            if any(isinstance(t, exp.Table) and not t.db and t.name.upper() in named for t in sources):
                return "JOIN <CTE … HAVING …>"
    return None


def _other_rows(sq: SemanticQuery, o: _Occurrence) -> bool:
    """This occurrence reads rows a dated measure of the question certifiably excludes: on a column
    the measure's own conditions restrict, it keeps a disjoint set of values (the opening-balance
    document type beside a sales measure restricted to the sales document types). Whatever it is — an
    opening balance, a lookup — it is not the measure's rows, and the period the question puts on the
    measure is not a period on it."""
    for metric in sq.metrics:
        m = metric.mapping
        if not m or (m.extra or {}).get("state_measure"):
            continue
        for cond in (m.extra or {}).get("conditions") or []:
            mm = _COND.match(str(cond))
            if not mm:
                continue
            col = mm.group(1).upper()
            theirs = {v.strip().strip("'\"").upper() for v in mm.group(2).split(",") if v.strip()}
            for p in o.preds:
                if p.column.upper() == col and p.operator.upper() in ("=", "IN") and theirs and _values(p).isdisjoint(theirs):
                    return True
    return False


def _unrestricted_reading(o: _Occurrence, own_cols: set[str]) -> bool:
    """This occurrence restricts nothing but the measure's own columns — no date predicate either.
    Judged on the predicates written, not on `intervals`: a declared coverage window is recorded
    there for every table the catalog dated, and is not a restriction the statement made."""
    return all(p.column.upper() in own_cols for p in o.preds)


def _filter_proven(m, slot, occ: list[_Occurrence], tree, scope) -> bool:
    entity, column = m.entity.upper(), m.column.upper()
    expected = {str(v).strip().upper() for v in m.values}
    op = (m.operator or "IN").upper()
    compatible = {"=", "IN"} if op in ("=", "IN") else {op}
    def holds(o: _Occurrence, col: str, ops: set[str], vals: set[str]) -> bool:
        return any(p.column.upper() == col and p.operator.upper() in ops and _values(p) == vals for p in o.preds)
    own = [o for o in occ if _same_entity(o.entity, entity)]
    if own and all(holds(o, column, compatible, expected) for o in own):
        return True
    if not own:
        # The header is not read; its lines are, and the line carries the header's column under the
        # same name (Logo writes TRCODE on the order line as on the order). `LG_ORFLINE.TRCODE IN (1)`
        # is the order-type filter as surely as on LG_ORFICHE — the line points at exactly one header.
        lines = [o for o in occ if any(_same_entity(e, entity) for e in o.refs.values())]
        if lines and all(holds(o, column, compatible, expected) for o in lines):
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
        theirs = [o for o in occ if _same_entity(o.entity, alt["entity"])]
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
                matches.append(all(any(_same_entity(p.entity, entity) and p.column.upper() == column
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
                     if _same_entity(p.entity, entity) and p.column.upper() == column and p.operator.upper() in ("=", "IN")}
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
        tree = repair_table_qualifiers(parse_sql(sql))
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
        # A state measure beside a flow measure reads the same entity twice: the flow reading for the
        # period, the balance reading over every movement. The period rule judges the flow readings;
        # the balance reading — the measure's own conditions and nothing else — is the state rule's.
        dated = [o for o in occ if not _state_reading(sq, o) and not _other_rows(sq, o)]
        for binding in _bindings(sq):
            for period in sq.temporal:
                p = _period_dict(period)
                if not _period_proven(p, binding, dated, tree):
                    text = getattr(period, "text", None) or p.get("text") or f"{p.get('start')}–{p.get('end')}"
                    out.append(Unmet("period", f"'{text}' dönemi doğru tarih sütununda doğrulanamadı" + _opaque_note(occ, binding['entity']),
                                     f"{binding['entity']} kaynağını {binding['column']} >= '{p.get('start')}' AND {binding['column']} < '{p.get('end')}' ile sınırla (kaynağı okuyan her SELECT/CTE'de"
                                     + ("; durum ölçüsünün bakiyesini hesaplayan alt sorgu hariç — o tarihsiz kalır)." if len(dated) < len(occ) else ")."),
                                     binding["entity"], binding["column"]))

    # A word of the question written as a column's value: `NAME = 'kitabin'` for "bir kitabın …".
    # The word named the column (a resolved slot); the question gave no value for it. Such a filter
    # matches nothing and the empty answer looks like a true one.
    for word, column in _question_word_literals(sq, tree):
        out.append(Unmet("literal", f"'{word}' sorunun kelimesidir, {column} sütununun değeri değil",
                         f"{column} için soru bir değer vermiyor: bu filtreyi kaldır; 'bir X'in' bütün X'ler üzerinden "
                         f"kırılım ister (GROUP BY {column} ya da anahtarı), tek kaydı seçmez."))

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
            return name.upper() == "UNKNOWN" or _same_entity(name, entity)

        used = any(col.name.upper() == column and same_entity(scope.entity_for(col))
                   for node in restricting if node is not None for col in node.find_all(exp.Column))
        if not used:
            out.append(Unmet("qualifier", f"'{want.get('token')}' niteleyicisi {entity}.{column} üzerinde kısıtlanmadı",
                             f"{entity}.{column} kolonunu WHERE'de kısıtla; hangi değerin ne demek olduğunu "
                             f"kolon açıklamasından oku ({want.get('description')}).", entity, column))

    # A word the catalog cannot place: the model decides what it means, and must say so in a
    # "-- yorum:" line the person reads above the answer. "alacak" answered as the sum of invoices
    # issued looked like a receivables ageing until someone read the SQL.
    if getattr(sq, "unresolved", None):
        from semantic_layer.normalize import fold as _fold_u, stem as _stem_u
        said = [_fold_u(r) for r in re.findall(r"(?im)^\s*--\s*yorum\s*:\s*(.+?)\s*$", sql or "")]
        for word in sq.unresolved:
            w, root = _fold_u(str(word)), _stem_u(str(word))
            if not any(w in r or (root and root in r) for r in said):
                out.append(Unmet("unresolved", f"'{word}' teriminin nasıl yorumlandığı yazılmadı",
                                 f"Sorgunun başına -- yorum: '{word}' → <hangi tablo/kolon, hangi hesap> satırı ekle."))

    # Words left to the model. Two things are required of each: the model said how it read the word
    # (a "-- yorum:" line naming it), and the answer restricts something beyond what the question's
    # certified meanings already restrict — otherwise the word was dropped, whatever the comment says.
    if getattr(sq, "model_qualifiers", None):
        from semantic_layer.normalize import fold as _fold, stem as _stem
        known_entities = set()
        for t in (sources or {}):
            known_entities |= {logical_table(t).entity.upper(), re.sub(r"^(?:DBO_)?(?:LG_)?(?:\d{3}_)?(?:\d{2}_)?", "", t.upper())}
        readings = [_fold(r) for r in re.findall(r"(?im)^\s*--\s*yorum\s*:\s*(.+?)\s*$", sql or "")]
        known = {str(s.mapping.column).upper() for s in _filter_slots(sq) if s.mapping and s.mapping.column}
        known |= {str(b.get("column", "")).upper() for b in _bindings(sq)}
        restricting: set[str] = set()
        for node in tree.walk():
            node = node[0] if isinstance(node, tuple) else node
            if isinstance(node, (exp.Where, exp.Having, exp.Join)):
                for col in node.find_all(exp.Column):
                    restricting.add(col.name.upper())
            elif isinstance(node, exp.Exists):
                restricting.add("__EXISTS__")
        extra = restricting - known
        for want in sq.model_qualifiers:
            token = _fold(str(want.get("token", "")))
            root = _stem(token)
            if not any(token in r or (root and root in r) for r in readings):
                out.append(Unmet("qualifier", f"'{want.get('token')}' niteleyicisinin nasıl yorumlandığı yazılmadı",
                                 f"Sorgunun başına -- yorum: '{want.get('token')}' → <koşul> satırı ekle ve o koşulu uygula."))
            elif not extra:
                out.append(Unmet("qualifier", f"'{want.get('token')}' niteleyicisi sorguda hiçbir koşula dönüşmedi",
                                 f"'{want.get('token')}' için yazdığın yorumu WHERE, HAVING, NOT EXISTS ya da JOIN ile uygula."))
            elif want.get("kind") == "comparison" and not _has_magnitude_test(tree):
                # "maliyetin altında", "limitin üzerinde": a join key or the measure's own scope is a
                # restriction, but not this one. The word compares two magnitudes, so the statement
                # must hold an inequality between columns/aggregates (or against a number) — a period
                # bound (column vs. date literal) does not count.
                out.append(Unmet("qualifier", f"'{want.get('token')}' karşılaştırması sorguda bir eşitsizliğe dönüşmedi",
                                 f"'{want.get('token')}' için iki büyüklüğü karşılaştıran gerçek bir koşul yaz "
                                 "(WHERE/HAVING içinde <, >, <=, >=; iki kolon/ifade ya da bir sayı ile)."))
        # The reading must be the query's reading. "'tanımlı' → PRCLIST fiyat listesi ile karşılaştırma"
        # above a statement that never reads PRCLIST is a comment about a different query: the person
        # is shown a reading the answer does not use. Every table a reading names must be read.
        def _bare(name: str) -> str:
            # "Timas_MSCRM_dbo_NEW_X" is how a second source's table reads in the statement; the yorum
            # names it "NEW_X". The database and schema are the source's, not the question's.
            n = re.sub(r"^[A-Z0-9_]+?_DBO_", "", (name or "").upper())
            return re.sub(r"^(?:DBO_)?(?:LG_)?(?:\d{3}_)?(?:\d{2}_)?", "", n)
        read_here = set()
        for o in occ:
            read_here |= {o.entity.upper(), o.table.upper(), o.alias.upper(), _bare(o.entity), _bare(o.table)}
        body = re.sub(r"(?im)^\s*--.*$", "", sql or "")
        def _is_column_here(name: str) -> bool:
            # "NEW_SOZLESMETARAFIBASE.NEW_ODEME": the second part is a column the statement reads as
            # t."new_Odeme" — written somewhere in the body, never after FROM/JOIN.
            return bool(re.search(rf"[\.\[\"]?\b{re.escape(name)}\b", body, re.I)) and not re.search(rf"\b(?:FROM|JOIN)\s+[\[\]\w\.]*\b{re.escape(name)}\b", body, re.I)
        for raw in re.findall(r"(?im)^\s*--\s*yorum\s*:\s*(.+?)\s*$", sql or ""):
            named = {t.split(".")[0] for t in re.findall(r"\b([A-Z][A-Z0-9_]{3,}(?:\.[A-Za-z_]\w*)?)", raw.split("→", 1)[-1])
                     if not _is_column_here(t.split(".")[0])}
            named = {t for t in named
                     if not re.fullmatch(r"(SUM|AVG|MIN|MAX|COUNT|CASE|WHEN|THEN|ELSE|END|AND|OR|NOT|NULL|IN|IS|LIKE|BETWEEN|DISTINCT|SELECT|FROM|WHERE|JOIN|LEFT|INNER|GROUP|ORDER|HAVING|TOP|DATEDIFF|CAST|CONVERT|DAY|MONTH|YEAR|TRUE|FALSE|KDV|TL|USD|EUR|ISNULL|COALESCE|NULLIF|ABS|ROUND|FLOOR|CEILING|GETDATE|DATEADD|DATEPART|OVER|PARTITION|ROW_NUMBER|RANK|EXISTS|UNION|ALL|WITH|AS|ON|BY|ASC|DESC)", t)}
            tables = {_bare(t.split(".")[0]) for t in named if any(ch.isalpha() for ch in t)}
            tables = {t for t in tables if t in known_entities} if known_entities else tables
            missing = {t for t in tables if t not in read_here}
            if missing:
                out.append(Unmet("qualifier", f"yorumda adı geçen {', '.join(sorted(missing))} sorguda okunmuyor",
                                 f"Yorumda yazdığın {', '.join(sorted(missing))} tablosunu sorguda gerçekten oku, ya da yorumu sorgunun yaptığıyla uyumlu yaz."))

    # A state measure (stock on hand) is the balance of *all* movements: computed inside a SELECT that
    # keeps only a period or a document type, it is the balance of those rows — sales alone gave a
    # stock of minus the sales and a turnover of −1. Its entity must be read somewhere unrestricted
    # beyond the measure's own conditions; the restricted reading may stand beside it for the flow.
    for metric in sq.metrics:
        m = metric.mapping
        if not m or not (m.extra or {}).get("state_measure"):
            continue
        own_cols = {c.split(".")[-1].upper() for c in _cond_columns((m.extra or {}).get("conditions") or [])}
        readings = [o for o in occ if o.entity.upper() in (m.entity.upper(), re.sub(r"^LG_", "", m.entity.upper()), "LG_" + m.entity.upper())]
        # A reading that only tests existence ("geçen ay hiç hareket görmemiş") computes no balance:
        # the rule is about the measure being *calculated* under a filter, so only aggregating SELECTs count.
        readings = [o for o in readings if o.select is None or o.select.find(exp.AggFunc) is not None]
        dropped = _rowless_dropped(tree, m.entity)
        if dropped:
            out.append(Unmet("state", f"'{metric.term}' durum ölçüsüdür: hiç hareketi olmayan kaydın bakiyesi 0'dır ve bu koşulu sağlar, "
                             f"ama {dropped} yalnız hareketi olan kayıtları tutar; hareketsiz kayıtlar sonuçtan düşer.",
                             f"Bakiyeyi üyelikle sınama: ya NOT EXISTS (SELECT 1 FROM {m.entity} … GROUP BY anahtar HAVING <bakiye> > 0) yaz, "
                             f"ya da bakiye alt sorgusunu LEFT JOIN ile bağlayıp ISNULL(bakiye, 0) üzerinde karşılaştır.", m.entity, None))
        if readings and not any(_unrestricted_reading(o, own_cols) for o in readings):
            out.append(Unmet("state", f"'{metric.term}' durum ölçüsüdür: tarih ya da işlem türü filtresi altında hesaplanamaz; "
                             f"okunan her {m.entity} filtreli.",
                             f"{m.entity} kaynağını '{metric.term}' için ayrı bir alt sorguda, yalnız kendi koşullarıyla "
                             f"({', '.join(sorted(own_cols)) or 'koşulsuz'}) ve tarih filtresi olmadan hesapla; dönemli ölçüyü ayrı alt sorguda al, anahtar üzerinden birleştir.",
                             m.entity, None))

    for slot in _filter_slots(sq):
        m = slot.mapping
        if not m or not m.column or slot.status not in ("CERTIFIED", "INFERRED"):
            continue
        if (slot.explain or {}).get("absent"):
            continue                        # "faturası kesilmemiş": the label names what must be absent, not a filter on the rows kept
        if not _filter_proven(m, slot, occ, tree, scope):
            op = (m.operator or "IN").upper()
            vals = sorted({str(v).strip().upper() for v in m.values})
            out.append(Unmet("filter", f"'{slot.term}' koşulu sonuç kapsamında doğrulanamadı: {m.entity}.{m.column} {op} {vals}" + _opaque_note(occ, m.entity),
                             f"{m.entity} kaynağını okuyan her SELECT/CTE'nin WHERE'ine {m.column} {op} ({', '.join(vals)}) ekle.",
                             m.entity, m.column))

    # A certified filter concept may carry more than its own column: "bekleyen sipariş" is CLOSED = 0
    # *and* item lines only *and* an unshipped remainder. The main column proved above, each extra
    # condition must reach the same rows — one promotion line summed in "bekleyen tutar" is money that
    # was never ordered. Metric concepts' conditions are the measure rule's business.
    for slot in _filter_slots(sq):
        m = slot.mapping
        if not m or slot.status not in ("CERTIFIED", "INFERRED") or (slot.explain or {}).get("absent"):
            continue
        own = [o for o in occ if _same_entity(o.entity, m.entity)]
        if not own:
            continue
        for cond in (m.extra or {}).get("conditions") or []:
            if not _condition_holds(str(cond), own):
                out.append(Unmet("filter", f"'{slot.term}' kavramının koşulu sonuç kapsamında doğrulanamadı: {cond}",
                                 f"{m.entity} kaynağını okuyan her SELECT/CTE'nin WHERE'ine {cond} ekle."
                                 + _stand_in_note(str(cond), own, occ), m.entity, None))

    # A certified dimension can define which reference wins when header and line
    # values differ. Merely mentioning the target table cannot establish this.
    from semantic_layer.runtime.reference_contracts import reference_rule, reference_predicate, via_predicate
    for metric in sq.metrics:
        if not metric.mapping:
            continue
        if (metric.explain or {}).get("absent"):
            continue        # "hiç sevkiyat almamış": the measure is excluded, not attributed — no reference to rank
        fact = metric.mapping.entity
        for slot in sq.group_by:
            if not slot.mapping:
                continue
            rule = reference_rule(slot.mapping, fact, [f.mapping for f in sq.filters if f.mapping])
            if not rule:
                continue
            def equality(node, context):
                if not isinstance(node, exp.EQ):
                    return None
                # Compared as `_ent` compares entities: the rule names the target "LG_SHIPINFO", the
                # physical table reads back "SHIPINFO" — the same join, refused over the source's prefix.
                side = lambda n: re.sub(r"\bLG_(?=[A-Z])", "", _normalise_formula(n, context).upper())
                return frozenset((side(node.left), side(node.right)))
            # The rule may be honoured in a derived table or a correlated subquery, as a JOIN … ON or
            # as a WHERE equality between two columns: every SELECT of the statement is looked at.
            actual = set()
            for sel in tree.find_all(exp.Select):
                for join in sel.args.get("joins") or []:
                    if join.args.get("on") is not None:
                        actual.update(equality(part, scope) for part in _split_and(join.args["on"]))
                where = sel.args.get("where")
                if where is not None:
                    actual.update(equality(part, scope) for part in _split_and(where.this)
                                  if isinstance(part, exp.EQ) and isinstance(part.left, exp.Column) and isinstance(part.right, exp.Column))
            # A rule that declares the fact's own column reads the reference through the intermediate
            # record only where one exists. A statement joining on the fact's own column keeps every
            # row and names the same record, so it honours the rule as well as the two-step join does.
            from semantic_layer.runtime.reference_contracts import own_predicate
            direct = own_predicate(slot.mapping, fact, rule)
            expressions = (via_predicate(fact, rule), reference_predicate(slot.mapping, fact, rule))
            if direct:
                direct_tree = parse_sql(direct)
                direct_scope = _Scope(direct_tree, None)
                if "{" not in slot.mapping.table_pattern:
                    direct_scope.alias_to_entity[slot.mapping.entity.upper()] = logical_table(slot.mapping.table_pattern).entity
                if equality(direct_tree, direct_scope) in actual:
                    expressions = (direct,)
            final = expressions[-1]
            for expression in expressions:
                expected_tree = parse_sql(expression)
                expected_scope = _Scope(expected_tree, None)
                if "{" not in slot.mapping.table_pattern:
                    expected_scope.alias_to_entity[slot.mapping.entity.upper()] = logical_table(slot.mapping.table_pattern).entity
                expected = equality(expected_tree, expected_scope)
                if expected not in actual:
                    out.append(Unmet("reference", f"'{slot.term}' ilişki önceliği doğrulanamadı: {expression}", f"JOIN koşulu olarak {expression} kullan."))
                elif (expression == final
                      and (slot.mapping.extra or {}).get("join_kind") == "LEFT"
                      # Looked for where the equality itself is looked for: in every SELECT. A rule
                      # honoured inside a CTE or a derived table keeps the unassigned rows just as well,
                      # and the outer SELECT's join list does not contain it.
                      and not any(str(join.args.get("side", "")).upper() == "LEFT"
                                  and any(equality(part, scope) == expected for part in _split_and(join.args["on"]))
                                  for sel in tree.find_all(exp.Select)
                                  for join in sel.args.get("joins") or [] if join.args.get("on") is not None)):
                    # "Bu ilişkiyi" named nothing: the model made the *other* join of the statement LEFT
                    # and was refused again for the same reason.
                    out.append(Unmet("reference", f"'{slot.term}' atanmamış değerleri koruyan ilişki doğrulanamadı: {expression} LEFT JOIN değil",
                                     f"{slot.mapping.entity} tablosunu LEFT JOIN ile bağla: LEFT JOIN {slot.mapping.entity} ON {expression} "
                                     f"(INNER JOIN, {slot.mapping.entity} kaydı olmayan satırları düşürür)."))

    if not strict:
        return out + _closing(sq, tree, occ)

    # The measure itself: the certified formula, or the same number with its CASE folded into a
    # WHERE that provably reaches the rows, or its aggregate parts computed and combined on the way out.
    for metric in sq.metrics:
        m = metric.mapping
        if not m or not m.formula or metric.status not in ("CERTIFIED", "INFERRED"):
            continue
        if not any(_same_entity(o.entity, m.entity) for o in occ):
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

    return out + _closing(sq, tree, occ)


def _closing(sq, tree, occ=None) -> list[Unmet]:
    out = []
    if sq.shape == "ABSENCE":
        expected = (sq.absence_contract or {}).get("sql")
        absent = {str(m.get("absent_entity")).upper() for m in (sq.modifiers or []) if m.get("decision") == "ABSENCE" and m.get("absent_entity")}
        if expected:
            if parse_sql(expected) != tree:
                out.append(Unmet("absence", "yokluk koşulunun varlık, ilişki ve dönem kapsamı doğrulanamadı"))
        elif absent:
            # No certified contract: the statement must at least *exclude* the absent entity's rows —
            # NOT EXISTS / NOT IN over a subquery reading it, or a LEFT JOIN to it tested IS NULL.
            # Filtering its rows ("SHIPPEDAMOUNT = 0") keeps the customers who did receive shipments.
            if not _anti_joins(tree, absent):
                who = ", ".join(sorted(absent))
                out.append(Unmet("absence", f"yokluk sorusu: {who} kaydı olmayanlar NOT EXISTS / NOT IN / LEFT JOIN … IS NULL ile dışlanmalı; "
                                 f"{who} satırlarını filtrelemek 'hiç olmayan'ı vermez",
                                 f"{who} tablosunu ana sorguda okuma; WHERE NOT EXISTS (SELECT 1 FROM {who} … WHERE <anahtar eşitliği>) yaz."))
            else:
                bad = _uncorrelated_absence(tree, absent, occ or [])
                if bad:
                    out.append(Unmet("absence", bad,
                                     "Yokluk alt sorgusunu iki tabloyu birbirine bağlayan anahtar (bir tarafın referans kolonu = diğerinin anahtarı) "
                                     "üzerinden ilişkilendir; gerekirse aradaki köprü tabloyu alt sorgunun içinde oku."))
        else:
            out.append(Unmet("absence", "yokluk koşulunun varlık, ilişki ve dönem kapsamı doğrulanamadı"))
    if sq.measure_expressions:
        out.append(Unmet("expression", "hesap ifadesinin bileşenleri ve işlemi sertifikalı bir formülle doğrulanmadı"))
    return out


def _uncorrelated_absence(tree: exp.Expression, entities: set[str], occ: list) -> str:
    """A NOT EXISTS over the absent entity must be tied to the outer row by a reference the catalog
    knows: a column of one side that points at the other side's key (or at a bridge table read
    inside the subquery). Equating the two documents' customer columns ties nothing — two documents of
    the same customer are not the same order — and gave 11 "uninvoiced orders" where there were 297.
    Returns the refusal text, or "" when a real key equality is found (or nothing can be judged)."""
    refs: dict[str, dict[str, str]] = {}
    for o in occ:
        if o.refs:
            refs.setdefault(_ent(o.entity), {}).update({k.upper(): _ent(v) for k, v in o.refs.items()})
    if not refs:
        return ""
    alias_entity: dict[str, str] = {}
    for t in tree.find_all(exp.Table):
        alias_entity[(t.alias_or_name or t.name).upper()] = _ent(logical_table((t.db + "." if t.db else "") + t.name).entity)
        alias_entity[t.name.upper()] = _ent(logical_table((t.db + "." if t.db else "") + t.name).entity)
    def entity_of(col: exp.Column, inner_default: str) -> str:
        return alias_entity.get((col.table or "").upper(), inner_default)
    for node in tree.find_all(exp.Not):
        inner = node.this
        if not isinstance(inner, exp.Exists):
            continue
        sub = inner.this
        inner_tables = [t for t in sub.find_all(exp.Table)]
        inner_entities = {_ent(logical_table((t.db + "." if t.db else "") + t.name).entity) for t in inner_tables}
        if not any(any(_same_entity(e, a) for a in entities) for e in inner_entities):
            continue
        inner_default = next(iter(inner_entities)) if len(inner_entities) == 1 else ""
        pairs = []
        for eq in sub.find_all(exp.EQ):
            a, b = eq.this, eq.expression
            if isinstance(a, exp.Column) and isinstance(b, exp.Column):
                pairs.append(((entity_of(a, inner_default), a.name.upper()), (entity_of(b, inner_default), b.name.upper())))
        crossing = [(x, y) for x, y in pairs if x[0] and y[0] and x[0] != y[0]]
        if not crossing:
            return ""                          # nothing correlates by column; another rule's business
        def keyed(x, y) -> bool:
            return refs.get(x[0], {}).get(x[1]) == y[0] or refs.get(y[0], {}).get(y[1]) == x[0]
        if any(keyed(x, y) for x, y in crossing):
            return ""
        shown = ", ".join(f"{x[0]}.{x[1]} = {y[0]}.{y[1]}" for x, y in crossing[:2])
        return (f"yokluk alt sorgusu dış satıra anahtarla bağlı değil ({shown}): iki tarafı birbirine bağlayan bir referans kolonu yok; "
                f"aynı müşteri/tarih eşitliği 'bu kaydın faturası/sevkiyatı' demek değildir")
    return ""


def _anti_joins(tree: exp.Expression, entities: set[str]) -> bool:
    """Does the statement exclude rows of one of `entities` — NOT EXISTS / NOT IN over a subquery that
    reads it, or a LEFT JOIN to it whose column is tested IS NULL?"""
    def reads(node: exp.Expression) -> bool:
        return any(_same_entity(logical_table((t.db + "." if t.db else "") + t.name).entity, e)
                   for t in node.find_all(exp.Table) for e in entities)
    for node in tree.find_all(exp.Not):
        inner = node.this
        if isinstance(inner, exp.Exists) and reads(inner):
            return True
        if isinstance(inner, exp.In) and any(reads(q) for q in inner.args.get("expressions") or [] if isinstance(q, exp.Expression)) \
                or isinstance(inner, exp.In) and inner.args.get("query") is not None and reads(inner.args["query"]):
            return True
    for sel in tree.find_all(exp.Select):
        left_aliases = set()
        for join in sel.args.get("joins") or []:
            if (join.side or "").upper() == "LEFT" and isinstance(join.this, exp.Table) and reads(join.this):
                left_aliases.add((join.this.alias_or_name or "").upper())
        where = sel.args.get("where")
        if left_aliases and where is not None:
            for isn in where.find_all(exp.Is):
                col = isn.this
                if isinstance(col, exp.Column) and (col.table or "").upper() in left_aliases and isinstance(isn.expression, exp.Null):
                    return True
    return False


def _opaque_note(occ, entity: str) -> str:
    names = sorted({x for o in occ if _same_entity(o.entity, entity) for x in o.opaque})
    return f" (anlaşılmayan yapı: {', '.join(names[:3])} türetilmiş bir kolon üzerinden yazılmış)" if names else ""


def _feeding_selects(tree: exp.Expression) -> list[exp.Expression]:
    """The SELECTs the answer is actually made of: the root, its UNION branches, and — transitively — every
    derived table or CTE a reachable SELECT reads from. A CTE nobody reads proves nothing."""
    ctes = {c.alias.upper(): c.this for c in tree.find_all(exp.CTE) if c.alias}
    out: list[exp.Expression] = []
    todo = [tree]
    while todo:
        node = todo.pop()
        if isinstance(node, (exp.Subquery, exp.Paren)):
            todo.append(node.this); continue
        if isinstance(node, exp.Union):
            todo.extend([node.this, node.expression]); continue
        if not isinstance(node, exp.Select) or any(node is x for x in out):
            continue
        out.append(node)
        sources = []
        frm = node.args.get("from_") or node.args.get("from")
        if frm is not None:
            sources.append(frm.this)
        sources.extend(j.this for j in node.args.get("joins") or [])
        for src in sources:
            if isinstance(src, exp.Table) and src.name and src.name.upper() in ctes:
                todo.append(ctes[src.name.upper()])
            elif isinstance(src, (exp.Subquery, exp.Union, exp.Select)):
                todo.append(src)
    return out or [tree]


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
    # The two periods may be told apart in the answer's own SELECT — or one level down, in each CTE or
    # UNION branch that reads a source ("kasa" and "banka" are two tables: each branch carries both
    # months as CASE columns and the outer SELECT only subtracts them). Every SELECT is looked at.
    proven: set = set()
    selects = _feeding_selects(tree)
    for sel in selects:
        sc = scope if sel is tree else _AnswerScope(sel)
        left, right = _period_outputs(sel, current, sc, binding), _period_outputs(sel, reference, sc, binding)
        def correct_column(columns, sel=sel, sc=sc):
            if binding:
                return any(_accepts_bound_column(sel, sc, binding, alias, col) for alias, col in columns)
            return any((not sq.comparison.get("dateColumn") or col == sq.comparison["dateColumn"].upper())
                       and (not sq.comparison.get("entity") or sc.entity_for(exp.column(col, table=alias or None)).upper() == sq.comparison["entity"].upper())
                       for alias, col in columns)
        proven |= {af for a, (ac, af) in left.items() for b, (bc, bf) in right.items()
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

    # (a') the periods as *rows*: a feeding SELECT grouped by its date column (a month bucket), reading
    # exactly the two adjacent periods and nothing else — "kasa" and "banka" each summed per month in a
    # CTE, the outer SELECT picking the two months apart. Only where no certified measure fixes the
    # formula to look for; with one, the column shapes above are what is demanded.
    if not expected:
        cs, ce = str(current.get("start"))[:10], str(current.get("end"))[:10]
        rs, re_ = str(reference.get("start"))[:10], str(reference.get("end"))[:10]
        if re_ == cs or ce == rs:
            hull = (min(cs, rs), max(ce, re_))
            for sel in selects:
                group = sel.args.get("group")
                if group is None:
                    continue
                gcols = {c.name.upper() for e in group.expressions for c in e.find_all(exp.Column)}
                for o in occ:
                    if o.select is sel and any(_window_of(o, col) == hull for col in gcols):
                        return True, ""

    want_cur = (str(current["start"])[:10], str(current["end"])[:10])
    want_ref = (str(reference["start"])[:10], str(reference["end"])[:10])
    entity = (binding or {}).get("entity") or sq.comparison.get("entity") or ""
    column = ((binding or {}).get("column") or sq.comparison.get("dateColumn") or "").upper()
    alt_cols = {(a["entity"].upper(), a["column"].upper()) for a in (binding or {}).get("alternatives", [])}

    def period_of(o: _Occurrence):
        if _same_entity(o.entity, entity):
            return _window_of(o, column)
        if (_ent(o.entity), column) in {(_ent(e), c) for e, c in alt_cols} or any(_same_entity(o.entity, e) for e, _ in alt_cols):
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


def repair_table_qualifiers(tree: exp.Expression) -> exp.Expression:
    """`FROM Timas_MSCRM_dbo_NEW_X` … `WHERE NEW_X.statecode = 0`: the model qualified the column with
    the table's bare entity name instead of the name it read the table under. Nothing else in the
    statement can be meant, so the qualifier is rewritten to the table's own alias-or-name — for the
    gate and for the database alike, which would otherwise refuse the identifier."""
    for sel in tree.find_all(exp.Select):
        tables = [t for t in sel.find_all(exp.Table) if t.find_ancestor(exp.Select) is sel]
        known = {(t.alias_or_name or "").upper() for t in tables} | {t.name.upper() for t in tables}
        by_entity: dict[str, list[str]] = {}
        for t in tables:
            by_entity.setdefault(_ent(t.name), []).append(t.alias_or_name or t.name)
        for col in sel.find_all(exp.Column):
            q = (col.table or "")
            if not q or q.upper() in known or col.find_ancestor(exp.Select) is not sel:
                continue
            hits = by_entity.get(_ent(q), [])
            if len(hits) == 1:
                col.set("table", exp.to_identifier(hits[0]))
    return tree


def repair_qualifiers_sql(sql: str) -> str:
    """The same repair on the statement text; leading `-- yorum` lines are kept."""
    try:
        head = "".join(line + "\n" for line in (sql or "").splitlines() if line.strip().startswith("--"))
        body = "\n".join(line for line in (sql or "").splitlines() if not line.strip().startswith("--"))
        tree = parse_sql(body)
        before = tree.sql(dialect="tsql")
        after = repair_table_qualifiers(tree).sql(dialect="tsql")
        return sql if before == after else head + after
    except Exception:  # noqa: BLE001
        return sql



def _has_magnitude_test(tree) -> bool:
    """Does the statement compare two magnitudes — an inequality whose both sides read a column or an
    aggregate, or one side against a number? Period bounds (column vs. quoted date / date function)
    are not such a test."""
    for node in tree.find_all(exp.LT, exp.GT, exp.LTE, exp.GTE):
        sides = [node.this, node.expression]
        if any(s is None for s in sides):
            continue
        reads = [bool(list(s.find_all(exp.Column))) for s in sides]
        if all(reads):
            return True
        for s, r in zip(sides, reads):
            if not r:
                lit = s.this if isinstance(s, (exp.Neg, exp.Paren)) else s
                if isinstance(lit, exp.Literal) and not lit.is_string and any(reads):
                    return True
    return False

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
        refs = {str(r.get("column", "")).upper(): str(r.get("ref_entity", "")).upper()
                for r in (getattr(p, "relationships", None) or []) if r.get("column") and r.get("ref_entity")}
        entry = {"types": {c.name.upper(): (c.data_type or "") for c in getattr(p, "columns", [])},
                 "window": (str(dw[0]), str(dw[1])) if dw else ((str(w[0]), str(w[1])) if w and w[0] and w[1] else None),
                 "declared": bool(dw) or p.table_name.upper() in declared,
                 "refs": refs}
        out[p.table_name.upper()] = entry
        if getattr(p, "schema_name", ""):
            out[f"{p.schema_name}_{p.table_name}".upper()] = entry
            out[f"{p.schema_name}.{p.table_name}".upper()] = entry
        # The model writes the entity's logical name (STLINE, LG_ORFLINE): its column types and
        # references are the copies' own; a coverage window is not claimed for a name that is every copy.
        ent = str(getattr(p, "entity", "") or "").upper()
        if ent:
            out.setdefault(ent, {"types": entry["types"], "window": None, "declared": False, "refs": refs})
            out.setdefault(_ent(ent), {"types": entry["types"], "window": None, "declared": False, "refs": refs})
    return out


__all__ = ["audit_sql", "unmet_obligations", "gate_report", "Unmet", "sources_from"]
