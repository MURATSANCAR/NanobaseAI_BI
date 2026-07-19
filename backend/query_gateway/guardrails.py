"""SQL guardrails for Nanobase Query Gateway (sqlglot)."""

from __future__ import annotations

import re
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

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
class GuardResult:
    ok: bool
    sql: str
    error: str | None = None
    tables: list[str] | None = None


def _normalize_ident(name: str) -> str:
    return name.strip().strip('"').strip("`").lower()


def validate_and_rewrite(
    sql: str,
    *,
    dialect: str = "postgres",
    allowed_tables: set[str] | None = None,
    max_limit: int = 500,
) -> GuardResult:
    """Allow only single SELECT/WITH; enforce table allowlist + LIMIT."""
    raw = (sql or "").strip().rstrip(";")
    if not raw:
        return GuardResult(False, "", "empty SQL")
    if ";" in raw:
        return GuardResult(False, raw, "multiple statements not allowed")

    try:
        trees = sqlglot.parse(raw, read=dialect)
    except ParseError as e:
        return GuardResult(False, raw, f"parse error: {e}")

    if not trees or trees[0] is None:
        return GuardResult(False, raw, "unable to parse SQL")
    if len(trees) != 1:
        return GuardResult(False, raw, "multiple statements not allowed")

    tree = trees[0]
    if not isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        # WITH ... SELECT arrives as Select with ctes
        if not isinstance(tree, exp.Query):
            return GuardResult(False, raw, "only SELECT/WITH queries are allowed")

    for node_type in FORBIDDEN_TYPES:
        if list(tree.find_all(node_type)):
            return GuardResult(False, raw, f"forbidden statement type: {node_type.__name__}")

    # Reject INTO / FOR UPDATE style mutations if present
    sql_l = raw.lower()
    bad_clauses = (
        " into ",
        " for update",
        " for share",
        " nextval(",
        " setval(",
        " pg_sleep(",
        " dbms_lock",
        " utl_http",
        " utl_file",
        " execute immediate",
    )
    for bad in bad_clauses:
        if bad in f" {sql_l} ":
            return GuardResult(False, raw, f"forbidden clause: {bad.strip()}")

    # CTE / subquery aliases are not physical tables — skip allowlist for them.
    cte_aliases: set[str] = set()
    for cte in tree.find_all(exp.CTE):
        alias = cte.alias or getattr(cte, "alias_or_name", None)
        if alias:
            cte_aliases.add(_normalize_ident(str(alias)))

    tables: set[str] = set()
    for t in tree.find_all(exp.Table):
        name = _normalize_ident(t.name) if t.name else ""
        schema = _normalize_ident(t.db) if t.db else ""
        if name:
            tables.add(name)
            if schema:
                tables.add(f"{schema}.{name}")

    if allowed_tables is not None:
        # allow bare table or schema.table if either form is allowlisted
        allowed_norm = {_normalize_ident(x) for x in allowed_tables}
        for tname in tables:
            bare = tname.split(".")[-1]
            if bare in cte_aliases:
                continue
            if tname not in allowed_norm and bare not in allowed_norm:
                return GuardResult(False, raw, f"table not allowlisted: {tname}")

    # Ensure LIMIT
    rewritten = tree
    if isinstance(rewritten, exp.Union):
        # wrap union
        rewritten = exp.select("*").from_(rewritten.subquery(alias="q"))

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

    out_sql = rewritten.sql(dialect=dialect)
    return GuardResult(True, out_sql, None, sorted(tables))
