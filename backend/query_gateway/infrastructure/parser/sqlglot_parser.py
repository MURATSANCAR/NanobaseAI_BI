"""SQLGlot parse, normalize, extract, fingerprint."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from query_gateway.domain.errors import (
    MULTIPLE_STATEMENTS_NOT_ALLOWED,
    SQL_PARSE_FAILED,
    STATEMENT_NOT_ALLOWED,
    GatewayError,
)

FORBIDDEN_TYPES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.TruncateTable,
    exp.Command,
    exp.Grant,
    exp.Copy,
    exp.Merge,
    exp.Replace,
)


@dataclass
class ParsedQuery:
    tree: exp.Expression
    normalized_sql: str
    dialect: str
    schemas: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    join_count: int = 0
    has_cross_join: bool = False
    has_on_true: bool = False
    has_wildcard: bool = False
    has_select_into: bool = False
    has_for_update: bool = False
    cte_aliases: set[str] = field(default_factory=set)
    unqualified_tables: list[str] = field(default_factory=list)


def _norm(name: str) -> str:
    return name.strip().strip('"').strip("`").lower()


def parse_sql(sql: str, *, dialect: str = "postgres") -> ParsedQuery:
    raw = (sql or "").strip().rstrip(";")
    if not raw:
        raise GatewayError(SQL_PARSE_FAILED, "Boş SQL.", status=400)
    if ";" in raw:
        raise GatewayError(
            MULTIPLE_STATEMENTS_NOT_ALLOWED,
            "Birden fazla SQL ifadesine izin verilmez.",
            status=400,
        )
    if len(raw.encode("utf-8")) > 100 * 1024:
        raise GatewayError(SQL_PARSE_FAILED, "SQL boyutu limiti aşıldı.", status=400)

    try:
        trees = sqlglot.parse(raw, read=dialect)
    except ParseError as e:
        raise GatewayError(SQL_PARSE_FAILED, "SQL ayrıştırılamadı.", status=400) from e

    if not trees or trees[0] is None:
        raise GatewayError(SQL_PARSE_FAILED, "SQL ayrıştırılamadı.", status=400)
    if len(trees) != 1:
        raise GatewayError(
            MULTIPLE_STATEMENTS_NOT_ALLOWED,
            "Birden fazla SQL ifadesine izin verilmez.",
            status=400,
        )

    tree = trees[0]
    if isinstance(tree, exp.Command):
        raise GatewayError(STATEMENT_NOT_ALLOWED, "İzin verilmeyen SQL komutu.", status=400)
    if not isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.Query)):
        raise GatewayError(
            STATEMENT_NOT_ALLOWED,
            "Yalnız SELECT / WITH ... SELECT izinlidir.",
            status=400,
        )

    for node_type in FORBIDDEN_TYPES:
        if list(tree.find_all(node_type)):
            raise GatewayError(
                STATEMENT_NOT_ALLOWED,
                f"İzin verilmeyen ifade: {node_type.__name__}.",
                status=400,
            )

    # SELECT INTO
    has_into = False
    for sel in tree.find_all(exp.Select):
        if sel.args.get("into") is not None:
            has_into = True
            break

    # FOR UPDATE / FOR SHARE
    sql_l = f" {raw.lower()} "
    has_for_update = " for update" in sql_l or " for share" in sql_l
    for lock in tree.find_all(exp.Lock):
        has_for_update = True
        break

    if has_into:
        raise GatewayError(STATEMENT_NOT_ALLOWED, "SELECT INTO izinli değildir.", status=400)
    if has_for_update:
        raise GatewayError(
            STATEMENT_NOT_ALLOWED,
            "FOR UPDATE / FOR SHARE izinli değildir.",
            status=400,
        )

    cte_aliases: set[str] = set()
    for cte in tree.find_all(exp.CTE):
        alias = cte.alias or getattr(cte, "alias_or_name", None)
        if alias:
            cte_aliases.add(_norm(str(alias)))

    schemas: set[str] = set()
    tables: set[str] = set()
    unqualified: list[str] = []
    for t in tree.find_all(exp.Table):
        name = _norm(t.name) if t.name else ""
        schema = _norm(t.db) if t.db else ""
        if not name or name in cte_aliases:
            continue
        if schema:
            schemas.add(schema)
            tables.add(f"{schema}.{name}")
        else:
            tables.add(name)
            unqualified.append(name)

    columns: set[str] = set()
    has_wildcard = False
    for col in tree.find_all(exp.Column):
        cname = _norm(col.name) if col.name else ""
        if not cname or cname == "*":
            continue
        table = _norm(col.table) if col.table else ""
        if table:
            columns.add(f"{table}.{cname}")
        else:
            columns.add(cname)
    # SELECT * only (not COUNT(*) argument stars)
    for sel in tree.find_all(exp.Select):
        for proj in sel.expressions or []:
            if isinstance(proj, exp.Star):
                has_wildcard = True
            elif isinstance(proj, exp.Column) and str(getattr(proj, "name", "")) == "*":
                has_wildcard = True
            elif isinstance(proj, exp.Alias) and isinstance(proj.this, exp.Star):
                has_wildcard = True

    functions: set[str] = set()
    for fn in tree.find_all(exp.Anonymous):
        if fn.this:
            functions.add(_norm(str(fn.this)).upper())
    # sqlglot models connectors / CASE / IF as Func — those are SQL syntax, not UDFs.
    _skip_func_types = (exp.Connector,)
    for extra in ("Case", "If", "Cast", "TryCast", "Paren"):
        cls = getattr(exp, extra, None)
        if cls is not None:
            _skip_func_types = (*_skip_func_types, cls)
    for fn in tree.find_all(exp.Func):
        if isinstance(fn, _skip_func_types):
            continue
        functions.add(type(fn).__name__.upper())

    join_count = 0
    has_cross = False
    has_on_true = False
    for j in tree.find_all(exp.Join):
        join_count += 1
        kind = (j.args.get("kind") or "").upper() if j.args.get("kind") else ""
        if kind == "CROSS" or (j.args.get("on") is None and j.args.get("using") is None and kind != "CROSS"):
            # CROSS or join without condition
            if kind == "CROSS" or j.args.get("on") is None:
                if kind == "CROSS":
                    has_cross = True
                elif j.args.get("using") is None:
                    has_on_true = True  # treat as missing condition
        on = j.args.get("on")
        if on is not None and isinstance(on, exp.Boolean) and on.this is True:
            has_on_true = True
        if on is not None and on.sql(dialect=dialect).strip().upper() in ("TRUE", "1"):
            has_on_true = True

    try:
        normalized = tree.sql(dialect=dialect)
    except Exception as e:
        raise GatewayError(SQL_PARSE_FAILED, "SQL normalize edilemedi.", status=400) from e

    return ParsedQuery(
        tree=tree,
        normalized_sql=normalized,
        dialect=dialect,
        schemas=sorted(schemas),
        tables=sorted(tables),
        columns=sorted(columns),
        functions=sorted(functions),
        join_count=join_count,
        has_cross_join=has_cross,
        has_on_true=has_on_true,
        has_wildcard=has_wildcard,
        has_select_into=has_into,
        has_for_update=has_for_update,
        cte_aliases=cte_aliases,
        unqualified_tables=unqualified,
    )


def apply_limit(tree: exp.Expression, *, max_limit: int, dialect: str) -> str:
    """Rewrite AST to enforce LIMIT max_limit (caller may pass maxRows+1)."""
    rewritten: exp.Expression = tree
    if isinstance(rewritten, exp.Union):
        rewritten = exp.select("*").from_(rewritten.subquery(alias="q"))
    if not isinstance(rewritten, exp.Select):
        return rewritten.sql(dialect=dialect)

    # Skip LIMIT rewrite for pure aggregates without GROUP BY (single-row)
    has_agg = any(isinstance(n, exp.AggFunc) for n in rewritten.find_all(exp.AggFunc))
    has_group = rewritten.args.get("group") is not None
    if has_agg and not has_group and rewritten.args.get("from") is not None:
        # still allow limit if already present
        pass
    elif has_agg and not has_group and not list(rewritten.find_all(exp.Join)):
        return rewritten.sql(dialect=dialect)

    limit_node = rewritten.args.get("limit")
    if limit_node is None:
        rewritten = rewritten.limit(max_limit)
    else:
        try:
            lit = limit_node.expression
            val = int(lit.this) if isinstance(lit, exp.Literal) else max_limit
            if val <= 0 or val > max_limit:
                rewritten = rewritten.limit(max_limit)
        except Exception:
            rewritten = rewritten.limit(max_limit)
    return rewritten.sql(dialect=dialect)


def fingerprint(
    *,
    dialect: str,
    normalized_sql: str,
    policy_version: str,
    datasource_id: str,
) -> str:
    payload = f"{dialect}\n{normalized_sql}\n{policy_version}\n{datasource_id}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
