"""SQL → facts (sqlglot). Predicates, conditional aggregates, joins, time ranges, grain, limit.

Model spellings (dbo_LG_411_01_INVOICE) and physical spellings (dbo.LG_411_01_INVOICE) both map onto
logical entities so the mined evidence is period/firm independent.
"""

from __future__ import annotations

import re
from typing import Optional

import sqlglot
from sqlglot import exp

from semantic_layer.models import Aggregate, Predicate, SqlFacts, TimeRange
from semantic_layer.naming import logical_table

_DATE_LIKE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_AGG_FUNCS = {exp.Sum: "SUM", exp.Count: "COUNT", exp.Avg: "AVG", exp.Min: "MIN", exp.Max: "MAX"}
_CMP = {exp.EQ: "=", exp.NEQ: "<>", exp.GT: ">", exp.GTE: ">=", exp.LT: "<", exp.LTE: "<="}


def parse_sql(sql: str) -> exp.Expression:
    last: Exception | None = None
    for dialect in ("tsql", None, "postgres"):
        try:
            return sqlglot.parse_one(sql, read=dialect)
        except Exception as e:  # noqa: BLE001
            last = e
    raise ValueError(f"SQL parse failed: {last}")


def _literal(node: exp.Expression) -> Optional[str]:
    if isinstance(node, exp.Literal):
        return str(node.this)
    if isinstance(node, exp.Neg) and isinstance(node.this, exp.Literal):
        return "-" + str(node.this.this)
    if isinstance(node, exp.Boolean):
        return "1" if node.this else "0"
    if isinstance(node, exp.Null):
        return "NULL"
    if isinstance(node, exp.Cast) and isinstance(node.this, exp.Literal):
        return str(node.this.this)
    return None


class _Scope:
    def __init__(self, tree: exp.Expression, column_index: Optional[dict[str, set[str]]]):
        self.alias_to_entity: dict[str, str] = {}
        self.entities: list[str] = []
        self.patterns: dict[str, str] = {}
        self.context: dict[str, str] = {}
        self.column_index = {k.upper(): {c.upper() for c in v} for k, v in (column_index or {}).items()}
        for t in tree.find_all(exp.Table):
            name = t.name
            if not name:
                continue
            lt = logical_table((t.db + "." if t.db else "") + name)
            self.patterns[lt.entity] = lt.table_pattern
            self.context.update(lt.context)
            if lt.entity not in self.entities:
                self.entities.append(lt.entity)
            self.alias_to_entity[name.upper()] = lt.entity
            if t.alias:
                self.alias_to_entity[t.alias.upper()] = lt.entity

    def entity_for(self, col: exp.Column) -> str:
        if col.table:
            ent = self.alias_to_entity.get(col.table.upper())
            if ent:
                return ent
            return logical_table(col.table).entity
        if len(self.entities) == 1:
            return self.entities[0]
        cname = col.name.upper()
        owners = [e for e in self.entities if cname in self.column_index.get(e, set())]
        if len(owners) == 1:
            return owners[0]
        # Logo heuristics: header amounts live on INVOICE, line amounts on STLINE
        if cname in ("NETTOTAL", "GROSSTOTAL", "TOTALVAT") and "INVOICE" in self.entities:
            return "INVOICE"
        if cname in ("AMOUNT", "TOTAL", "OUTCOST", "PRICE", "LINETYPE", "STOCKREF") and "STLINE" in self.entities:
            return "STLINE"
        return owners[0] if owners else (self.entities[0] if self.entities else "UNKNOWN")


def _normalise_formula(node: exp.Expression, scope: _Scope) -> str:
    """Rewrite column refs as ENTITY.COLUMN and render dialect-neutral SQL."""
    def tx(n: exp.Expression) -> exp.Expression:
        if isinstance(n, exp.Column):
            ent = scope.entity_for(n)
            return exp.Column(this=exp.to_identifier(n.name.upper()), table=exp.to_identifier(ent))
        return n
    clone = node.copy().transform(tx)
    return clone.sql(dialect=None).replace('"', "")


def _predicates_from(cond: exp.Expression, scope: _Scope, source: str, alias: Optional[str]) -> list[Predicate]:
    out: list[Predicate] = []
    for part in _split_and(cond):
        p = _single_predicate(part, scope, source, alias)
        if p:
            out.append(p)
    return out


def _split_and(node: exp.Expression) -> list[exp.Expression]:
    if isinstance(node, exp.And):
        return _split_and(node.left) + _split_and(node.right)
    if isinstance(node, exp.Paren):
        return _split_and(node.this)
    return [node]


def _single_predicate(node: exp.Expression, scope: _Scope, source: str, alias: Optional[str]) -> Optional[Predicate]:
    if isinstance(node, exp.Paren):
        return _single_predicate(node.this, scope, source, alias)
    if isinstance(node, exp.In) and isinstance(node.this, exp.Column):
        vals = [v for v in (_literal(x) for x in node.expressions) if v is not None]
        if vals:
            return Predicate(scope.entity_for(node.this), node.this.name.upper(), "IN", tuple(sorted(vals, key=_sortkey)), source, alias)
    if isinstance(node, exp.Not) and isinstance(node.this, exp.In) and isinstance(node.this.this, exp.Column):
        inner = node.this
        vals = [v for v in (_literal(x) for x in inner.expressions) if v is not None]
        if vals:
            return Predicate(scope.entity_for(inner.this), inner.this.name.upper(), "NOT IN", tuple(sorted(vals, key=_sortkey)), source, alias)
    for cls, op in _CMP.items():
        if isinstance(node, cls):
            left, right = node.left, node.right
            if isinstance(left, exp.Column) and not isinstance(right, exp.Column):
                v = _literal(right)
                if v is not None:
                    return Predicate(scope.entity_for(left), left.name.upper(), op, (v,), source, alias)
            if isinstance(right, exp.Column) and not isinstance(left, exp.Column):
                v = _literal(left)
                if v is not None:
                    flip = {">": "<", "<": ">", ">=": "<=", "<=": ">="}.get(op, op)
                    return Predicate(scope.entity_for(right), right.name.upper(), flip, (v,), source, alias)
    if isinstance(node, exp.Or):
        # col = a OR col = b  → IN
        parts = _split_or(node)
        cols = set()
        vals = []
        for p in parts:
            if isinstance(p, exp.EQ) and isinstance(p.left, exp.Column):
                cols.add((scope.entity_for(p.left), p.left.name.upper()))
                v = _literal(p.right)
                if v is not None:
                    vals.append(v)
        if len(cols) == 1 and len(vals) == len(parts):
            ent, col = next(iter(cols))
            return Predicate(ent, col, "IN", tuple(sorted(vals, key=_sortkey)), source, alias)
    if isinstance(node, exp.Between) and isinstance(node.this, exp.Column):
        lo, hi = _literal(node.args["low"]), _literal(node.args["high"])
        if lo is not None and hi is not None:
            return Predicate(scope.entity_for(node.this), node.this.name.upper(), "BETWEEN", (lo, hi), source, alias)
    return None


def _split_or(node: exp.Expression) -> list[exp.Expression]:
    if isinstance(node, exp.Or):
        return _split_or(node.left) + _split_or(node.right)
    if isinstance(node, exp.Paren):
        return _split_or(node.this)
    return [node]


def _sortkey(v: str):
    try:
        return (0, float(v))
    except ValueError:
        return (1, v)


def _agg_func(node: exp.Expression) -> str:
    for cls, name in _AGG_FUNCS.items():
        if isinstance(node, cls):
            if cls is exp.Count and isinstance(node.this, exp.Distinct):
                return "COUNT_DISTINCT"
            return name
    if isinstance(node, exp.Div):
        return "RATIO"
    if isinstance(node, (exp.Sub, exp.Add, exp.Mul)):
        return "EXPR"
    if isinstance(node, exp.Alias):
        return _agg_func(node.this)
    return "EXPR"


def _grain_of(expr: exp.Expression) -> Optional[str]:
    s = expr.sql(dialect=None).upper()
    if "DATEFROMPARTS" in s or ("YEAR" in s and "MONTH" in s) or "DATE_TRUNC('MONTH'" in s or "EOMONTH" in s:
        return "MONTH"
    if re.search(r"\bMONTH\(", s) or "EXTRACT(MONTH" in s:
        return "MONTH"
    if "CAST(" in s and " AS DATE)" in s:
        return "DAY"
    if "DATE_TRUNC('DAY'" in s or re.search(r"\bDAY\(", s):
        return "DAY"
    if re.search(r"\bYEAR\(", s) or "EXTRACT(YEAR" in s:
        return "YEAR"
    if "DATEPART(WEEK" in s or "WEEK" in s:
        return "WEEK"
    return None


def extract_sql_facts(sql: str, column_index: Optional[dict[str, set[str]]] = None) -> SqlFacts:
    facts = SqlFacts()
    try:
        tree = parse_sql(sql)
    except Exception as e:  # noqa: BLE001
        facts.parse_error = str(e)[:300]
        return facts
    scope = _Scope(tree, column_index)
    facts.tables = list(scope.entities)
    facts.table_patterns = dict(scope.patterns)
    facts.context = dict(scope.context)

    # WHERE / HAVING (all SELECT scopes incl. CTE/subqueries)
    for where in tree.find_all(exp.Where):
        facts.predicates.extend(_predicates_from(where.this, scope, "where", None))
    for having in tree.find_all(exp.Having):
        facts.predicates.extend(_predicates_from(having.this, scope, "having", None))

    # JOIN conditions
    for join in tree.find_all(exp.Join):
        on = join.args.get("on")
        if on is None:
            continue
        for part in _split_and(on):
            if isinstance(part, exp.EQ) and isinstance(part.left, exp.Column) and isinstance(part.right, exp.Column):
                a, b = part.left, part.right
                facts.joins.append((scope.entity_for(a), a.name.upper(), scope.entity_for(b), b.name.upper()))

    # SELECT expressions (every SELECT scope incl. CTEs): aggregates + CASE conditions bound to aliases
    selects = list(tree.find_all(exp.Select))
    select = tree if isinstance(tree, exp.Select) else (selects[0] if selects else None)
    for sel in selects:
        for e in sel.expressions:
            alias = e.alias if isinstance(e, exp.Alias) else None
            inner = e.this if isinstance(e, exp.Alias) else e
            conds: list[Predicate] = []
            for case in inner.find_all(exp.Case):
                for cond in case.args.get("ifs") or []:
                    conds.extend(_predicates_from(cond.this, scope, "case", alias))
            has_agg = any(isinstance(n, tuple(_AGG_FUNCS)) for n in inner.find_all(*tuple(_AGG_FUNCS)))
            cols = sorted({c.name.upper() for c in inner.find_all(exp.Column) if c.name})
            if not has_agg:
                first = next((c for c in inner.find_all(exp.Column) if c.name), None)
                if first is not None and first.name.upper() not in {p[2] for p in facts.projections if p[0] == alias}:
                    facts.projections.append((alias, scope.entity_for(first), first.name.upper()))
            if has_agg:
                ents = {scope.entity_for(c) for c in inner.find_all(exp.Column) if c.name}
                facts.aggregates.append(
                    Aggregate(alias=alias, func=_agg_func(inner), entity=(next(iter(ents)) if len(ents) == 1 else None), formula=_normalise_formula(inner, scope), columns=cols, conditions=conds)
                )
            facts.predicates.extend(conds)

    # GROUP BY → grain
    for g in tree.find_all(exp.Group):
        for ge in g.expressions:
            facts.group_by.append(_normalise_formula(ge, scope))
            gr = _grain_of(ge)
            if gr and not facts.grain:
                facts.grain = gr

    # WHERE predicates that only scope the CASE branches (TRCODE IN (2,3,7,8,9) around CASE 7,8,9 / 2,3)
    case_vals: dict[tuple[str, str], set[str]] = {}
    for p in facts.predicates:
        if p.source == "case" and p.operator in ("=", "IN"):
            case_vals.setdefault((p.entity, p.column), set()).update(p.values)
    retagged: list[Predicate] = []
    for p in facts.predicates:
        key = (p.entity, p.column)
        if p.source == "where" and p.operator in ("=", "IN") and key in case_vals and case_vals[key] and case_vals[key] <= set(p.values) and set(p.values) != case_vals[key]:
            retagged.append(Predicate(p.entity, p.column, p.operator, p.values, "scope", p.alias))
        elif p.source == "where" and p.operator in ("=", "IN") and key in case_vals and len(case_vals[key]) > 1 and set(p.values) == case_vals[key]:
            retagged.append(Predicate(p.entity, p.column, p.operator, p.values, "scope", p.alias))
        else:
            retagged.append(p)
    facts.predicates = retagged

    # time ranges from date predicates
    by_col: dict[tuple[str, str], TimeRange] = {}
    keep: list[Predicate] = []
    for p in facts.predicates:
        if p.operator in (">=", ">", "<", "<=", "BETWEEN") and any(_DATE_LIKE.match(v) for v in p.values):
            tr = by_col.setdefault((p.entity, p.column), TimeRange(p.entity, p.column))
            if p.operator in (">=", ">"):
                tr.start = p.values[0]
            elif p.operator in ("<", "<="):
                tr.end = p.values[0]
            elif p.operator == "BETWEEN":
                tr.start, tr.end = p.values[0], p.values[1]
            continue
        keep.append(p)
    facts.predicates = keep
    facts.time_ranges = list(by_col.values())
    for tr in facts.time_ranges:
        tr.grain = facts.grain

    lim = tree.find(exp.Limit)
    if lim is not None:
        v = _literal(lim.expression)
        facts.limit = int(v) if v and v.isdigit() else None
    else:
        top = select.args.get("limit") if select is not None else None
        if isinstance(top, exp.Limit):
            v = _literal(top.expression)
            facts.limit = int(v) if v and v.isdigit() else None
    return facts


def is_value_predicate(p: Predicate) -> bool:
    """Predicates that can carry a business-term meaning (enum codes, flags, text codes)."""
    if p.operator not in ("=", "IN", "<>", "NOT IN"):
        return False
    if p.source == "scope":
        return False
    if any(_DATE_LIKE.match(v) for v in p.values):
        return False
    if any(v.upper() == "NULL" for v in p.values):
        return False
    return True
