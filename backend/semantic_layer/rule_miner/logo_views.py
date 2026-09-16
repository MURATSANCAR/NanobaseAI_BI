"""Candidates from Logo's consultant views.

Three things a view says in the consultant's own words:
  * label maps    — CASE WHEN MODULENR = 4 THEN 'FATURALAR' …  → 'faturalar' = CLFLINE.MODULENR IN (4)
  * column aliases — C.SPECODE2 KANAL, T.DATE_ 'VADE_TARİHİ'     → 'kanal' = CLCARD.SPECODE2
  * expression aliases — (CASE WHEN SIGN=0 THEN AMOUNT ELSE 0 END) 'BORC' → metric 'borç' = SUM(CASE …)
Only views reading the firm copies in the catalog are read; commented-out SQL is dropped first.
"""
from __future__ import annotations

import re
from typing import Iterable, Iterator, Optional

import sqlglot
from sqlglot import exp

from semantic_layer.models import SchemaProfile, SemanticType
from semantic_layer.rule_miner.common import Candidate, Catalog, norm_value, term_from_alias, usable_term

_HEAD = re.compile(r"(?is)^.*?create\s+view\s+.*?\bas\b")
_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_NUMERIC = re.compile(r"int|decimal|numeric|float|real|money|smallint|bigint|tinyint", re.I)
_NON_ADDITIVE = re.compile(r"PRICE|RATE|PER\b|PERC|FACT|CURR|REF$|NR$|CODE|STAT|TYPE|LEVEL|LOGICALREF", re.I)


def body_of(definition: str) -> str:
    d = _BLOCK_COMMENT.sub("", definition or "")
    d = _LINE_COMMENT.sub("", d)
    return _HEAD.sub("", d, count=1).strip()


def parse(definition: str) -> Optional[exp.Expression]:
    try:
        return sqlglot.parse_one(body_of(definition), read="tsql")
    except Exception:  # noqa: BLE001 — a view the parser cannot read yields nothing, not an error
        return None


def _sources(select: exp.Select, catalog: Catalog) -> dict[str, SchemaProfile]:
    """alias (or table name) → profile, for the base tables this SELECT reads directly."""
    out: dict[str, SchemaProfile] = {}
    from_ = select.args.get("from_") or select.args.get("from")
    nodes = ([from_.this] if from_ is not None else []) + [j.this for j in select.args.get("joins") or []]
    for n in nodes:
        if isinstance(n, exp.Table) and n.name:
            prof = catalog.logo(n.name)
            if prof is not None:
                out[(n.alias or n.name).upper()] = prof
                out.setdefault(n.name.upper(), prof)
    return out


def _owner(col: exp.Column, sources: dict[str, SchemaProfile]) -> Optional[SchemaProfile]:
    if col.table:
        return sources.get(col.table.upper())
    if len({id(p) for p in sources.values()}) == 1:
        return next(iter(sources.values()))
    return None


def _in_subquery(node: exp.Expression, select: exp.Select) -> bool:
    p = node.parent
    while p is not None and p is not select:
        if isinstance(p, (exp.Select, exp.Subquery)):
            return True
        p = p.parent
    return False


def _literal_values(node: exp.Expression) -> Optional[list[str]]:
    if isinstance(node, exp.Literal):
        return [norm_value(node.this)]
    if isinstance(node, exp.Neg) and isinstance(node.this, exp.Literal):
        return [norm_value("-" + node.this.this)]
    return None


def _condition(node: exp.Expression, sources) -> Optional[tuple[SchemaProfile, str, str, list[str]]]:
    """col = v | col IN (v, …) on a base-table column → (profile, column, operator, values)."""
    if isinstance(node, exp.Paren):
        return _condition(node.this, sources)
    if isinstance(node, exp.EQ) and isinstance(node.left, exp.Column):
        vals = _literal_values(node.right)
        prof = _owner(node.left, sources)
        if vals and prof is not None and Catalog.has_column(prof, node.left.name):
            return prof, node.left.name.upper(), "IN", vals
    if isinstance(node, exp.In) and isinstance(node.this, exp.Column) and not node.args.get("query"):
        vals: list[str] = []
        for e in node.expressions:
            v = _literal_values(e)
            if v is None:
                return None
            vals += v
        prof = _owner(node.this, sources)
        if vals and prof is not None and Catalog.has_column(prof, node.this.name):
            return prof, node.this.name.upper(), "IN", vals
    return None


def _conjuncts(node: exp.Expression) -> list[exp.Expression]:
    if isinstance(node, exp.Paren):
        return _conjuncts(node.this)
    if isinstance(node, exp.And):
        return _conjuncts(node.left) + _conjuncts(node.right)
    return [node]


def _label_maps(select: exp.Select, sources, view: str) -> Iterator[Candidate]:
    for case in select.find_all(exp.Case):
        if _in_subquery(case, select):
            continue
        operand = case.this                                      # CASE col WHEN v THEN 'x' form
        for branch in case.args.get("ifs") or []:
            label = branch.args.get("true")
            if not isinstance(label, exp.Literal) or not label.is_string:
                continue
            term = term_from_alias(label.this)
            if not usable_term(term):
                continue
            cond = branch.this
            if operand is not None and isinstance(operand, exp.Column):
                vals = _literal_values(cond)
                prof = _owner(operand, sources)
                if vals is None or prof is None or not Catalog.has_column(prof, operand.name):
                    continue
                yield Candidate(term, SemanticType.DIMENSION_VALUE, prof.entity, prof.table_pattern, operand.name.upper(), "IN", vals,
                                source=view, kind="label_map", schema=prof.schema_name or "")
                continue
            parts = [_condition(c, sources) for c in _conjuncts(cond)]
            if not parts or any(p is None for p in parts):
                continue
            head, *rest = parts
            if any(p[0].entity != head[0].entity for p in rest):
                continue
            conds = [f"{p[0].entity}.{p[1]} IN ({', '.join(p[3])})" for p in rest]
            yield Candidate(term, SemanticType.DIMENSION_VALUE, head[0].entity, head[0].table_pattern, head[1], "IN", head[3],
                            conditions=conds, source=view, kind="label_map", schema=head[0].schema_name or "")


def _aliases(select: exp.Select, sources, view: str) -> Iterator[Candidate]:
    for e in select.expressions:
        if not isinstance(e, exp.Alias) or not e.alias:
            continue
        term = term_from_alias(e.alias)
        inner = e.this
        if isinstance(inner, exp.Column):
            prof = _owner(inner, sources)
            if prof is None or not Catalog.has_column(prof, inner.name) or not usable_term(term):
                continue
            if term.replace(" ", "") == inner.name.lower().replace("_", ""):
                continue                                          # DATE_ AS DATE_: no new word
            yield Candidate(term, SemanticType.COLUMN, prof.entity, prof.table_pattern, inner.name.upper(), "COLUMN",
                            source=view, kind="column_alias", schema=prof.schema_name or "")
            continue
        if list(inner.find_all(exp.Select)) or list(inner.find_all(exp.Window)):
            continue                                              # a subselect is a rule of its own
        cols = list(inner.find_all(exp.Column))
        if not cols or not usable_term(term):
            continue
        owners = {id(_owner(c, sources)): _owner(c, sources) for c in cols}
        if len(owners) != 1 or None in owners.values() and len(owners) == 1 and next(iter(owners.values())) is None:
            continue
        prof = next(iter(owners.values()))
        if prof is None or not all(Catalog.has_column(prof, c.name) for c in cols):
            continue
        if not all(_NUMERIC.search((prof.column(c.name).data_type or "")) for c in cols if not _tested(c, inner)):
            continue                                              # an expression over text is a label, not a measure
        if any(l.is_string for l in inner.find_all(exp.Literal) if not _tested(l, inner)) or list(inner.find_all(exp.DPipe)):
            continue                                              # a CASE that yields words is a label map, read above
        if term.replace(" ", "") in {c.name.lower().replace("_", "") for c in cols}:
            continue                                              # TOTALVAT AS TOTALVAT: no new word
        expr = inner.copy()
        while isinstance(expr, exp.Paren):
            expr = expr.this
        if not isinstance(expr, exp.AggFunc) and any(_NON_ADDITIVE.search(c.name) for c in cols if not _tested(c, inner)):
            continue                                              # SUM(PRICE) is not a measure anyone asked for
        for c in expr.find_all(exp.Column):
            c.set("table", exp.to_identifier(prof.entity))
            c.set("this", exp.to_identifier(c.name.upper()))
        body = expr.sql(dialect="tsql")
        # An expression the view already aggregates is a measure as written; a row expression is
        # summed to become one.
        formula = body if isinstance(expr, exp.AggFunc) else f"SUM({body})"
        if list(expr.find_all(exp.AggFunc)) and not formula.upper().startswith(("SUM(", "COUNT(", "AVG(", "MIN(", "MAX(")):
            continue                                              # ISNULL(SUM(a) - SUM(b), 0): mixed shape, left to a person
        yield Candidate(term, SemanticType.METRIC, prof.entity, prof.table_pattern, formula=formula,
                        source=view, kind="expression_alias", schema=prof.schema_name or "")


def _tested(col: exp.Expression, top: exp.Expression) -> bool:
    """A column inside a CASE's WHEN is a condition; only the THEN values are summed."""
    p = col.parent
    while p is not None and p is not top:
        if isinstance(p, exp.If):
            return p.this is col or any(x is col for x in p.this.walk())
        p = p.parent
    return False


def candidates(name: str, definition: str, catalog: Catalog) -> list[Candidate]:
    tree = parse(definition)
    if tree is None:
        return []
    out: list[Candidate] = []
    for select in tree.find_all(exp.Select):
        sources = _sources(select, catalog)
        if not sources:
            continue
        out += list(_label_maps(select, sources, name))
        out += list(_aliases(select, sources, name))
    return out


def fetch(connector, firms: Iterable[str] = ("211", "411")) -> list[tuple[str, str]]:
    like = " OR ".join(f"m.definition LIKE '%LG\\_{f}\\_%' ESCAPE '\\'" for f in firms)
    sql = ("SELECT v.name, m.definition FROM sys.views v JOIN sys.sql_modules m ON m.object_id = v.object_id "
           "WHERE v.name NOT LIKE 'LG\\_%' ESCAPE '\\' AND v.name NOT LIKE 'LV\\_%' ESCAPE '\\' "
           "AND v.name NOT LIKE 'VW\\_%' ESCAPE '\\' AND v.name NOT LIKE 'DV\\_%' ESCAPE '\\' AND (" + like + ")")
    _, rows, _ = connector.execute(sql, 5000)
    return [(r["name"], r["definition"] or "") for r in rows]
