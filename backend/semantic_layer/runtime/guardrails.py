"""Read-only SQL guardrails + physicalisation (model names → physical tables, dialect transpile)."""

from __future__ import annotations

import re
from typing import Optional

import sqlglot
from sqlglot import exp

from semantic_layer.models import SchemaProfile
from semantic_layer.naming import logical_table, physical_name, strip_quotes

_DENY = re.compile(r"(?i)\b(insert|update|delete|drop|alter|truncate|merge|exec|execute|grant|revoke|create|into|openrowset|openquery|opendatasource|xp_\w+|sp_\w+|bulk|shutdown|dbcc|waitfor|kill|backup|restore)\b")
_COMMENT = re.compile(r"--|/\*|\*/")


def strip_comments(sql: str) -> str:
    """Remove SQL comments outside string literals. They are stripped rather than rejected: a model
    routinely annotates its SQL, and a comment is also the classic place to hide a second statement."""
    out, i, n = [], 0, len(sql or "")
    in_str = False
    while i < n:
        ch = sql[i]
        if in_str:
            out.append(ch)
            if ch == "'":
                if i + 1 < n and sql[i + 1] == "'":
                    out.append(sql[i + 1]); i += 2; continue
                in_str = False
            i += 1
            continue
        if ch == "'":
            in_str = True; out.append(ch); i += 1; continue
        if sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j == -1 else j
            continue
        if sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            i = n if j == -1 else j + 2
            out.append(" ")
            continue
        out.append(ch); i += 1
    return "".join(out)


def allowed_tables(sql: str, profiles: list[SchemaProfile], context: dict[str, str], dialect: Optional[str] = "tsql") -> tuple[bool, str]:
    """Every table the statement reads must be one the catalog profiled. Without this the endpoint is a
    read-anything console over whatever the database login can reach."""
    known: set[str] = set()
    schemas: set[str] = set()
    for p in profiles:
        phys = physical_name(p.table_pattern, {**p.context, **(context or {})}).upper()
        known.update({p.entity.upper(), phys, p.table_name.upper()})
        if p.schema_name:
            schemas.add(p.schema_name.upper())
    for name in referenced_tables(sql, dialect):
        raw = strip_quotes(name).upper()
        bare = raw.split(".")[-1]
        candidates = {raw, bare, logical_table(raw).entity.upper()}
        for schema in schemas | {"DBO", "PUBLIC", "MAIN"}:          # model spelling: <schema>_<table>
            if bare.startswith(schema + "_"):
                candidates.add(bare[len(schema) + 1:])
        if not (candidates & known):
            return False, f"table not in the catalog: {name}"
    return True, "ok"


def validate_sql(sql: str) -> tuple[bool, str]:
    s = strip_comments(sql or "").strip().rstrip(";").strip()
    if not s:
        return False, "empty"
    if not re.match(r"(?is)^\s*(with|select)\b", s):
        return False, "only SELECT/WITH allowed"
    if ";" in s:
        return False, "multiple statements"
    if _DENY.search(s):
        return False, f"denied keyword: {_DENY.search(s).group(0)}"
    return True, "ok"


def physicalize_sql(sql: str, profiles: list[SchemaProfile], context: dict[str, str], dialect: str = "tsql") -> str:
    """Rewrite model / logical table spellings to physical ones and transpile to the target dialect.

    A model spelling (schema_TABLE), a logical entity or a stale period name all resolve to the
    physical table of the profiled pattern under the given context; LIMIT → TOP, EXTRACT → DATEPART."""
    by_entity = {p.entity: p for p in profiles}
    by_table = {p.table_name.upper(): p for p in profiles}
    for p in profiles:
        by_table[f"{p.schema_name}_{p.table_name}".upper()] = p
        by_table[f"{p.schema_name}.{p.table_name}".upper()] = p
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception:
        tree = sqlglot.parse_one(sql)
    cte_names = {c.alias.upper() for c in tree.find_all(exp.CTE) if c.alias}

    def tx(node: exp.Expression) -> exp.Expression:
        if isinstance(node, exp.Table) and node.name:
            raw = node.name
            key = ((node.db + "_") if node.db else "") + raw
            if raw.upper() in cte_names:
                return node
            prof = by_table.get(key.upper()) or by_table.get(raw.upper())
            if prof is None:
                lt = logical_table(raw)
                prof = by_entity.get(lt.entity) if lt.table_pattern != lt.entity or lt.entity in by_entity else None
            if prof is None:
                return node
            phys = physical_name(prof.table_pattern, {**prof.context, **context})
            new = exp.Table(this=exp.to_identifier(phys, quoted=True), db=exp.to_identifier(prof.schema_name, quoted=True))
            if node.alias:
                new.set("alias", exp.TableAlias(this=exp.to_identifier(node.alias)))
            return new
        return node

    out = tree.transform(tx)
    return out.sql(dialect=dialect if dialect != "generic" else None)


def strip_trailing_semicolon(sql: str) -> str:
    return (sql or "").strip().rstrip(";").strip()


def referenced_tables(sql: str, dialect: Optional[str] = "tsql") -> list[str]:
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception:
        try:
            tree = sqlglot.parse_one(sql)
        except Exception:
            return []
    ctes = {c.alias.upper() for c in tree.find_all(exp.CTE) if c.alias}
    out = []
    for t in tree.find_all(exp.Table):
        if t.name and t.name.upper() not in ctes:
            out.append(((t.db + ".") if t.db else "") + t.name)
    return list(dict.fromkeys(out))


# SQLSTATE class 08 is the standard "connection exception" class, and HYT00 is a connection timeout.
# Every ODBC/JDBC driver reports them the same way, so this is a protocol fact, not a driver quirk.
_CONNECTION_STATES = ("08S01", "08001", "08003", "08004", "08006", "08007", "HYT00", "HY000")
_CONNECTION_WORDS = (
    "communication link failure", "server is not found", "login timeout", "connection is closed",
    "connection refused", "broken pipe", "connection reset", "unable to connect", "not accessible",
)


def is_connection_error(error: object) -> bool:
    """Did the data source go away, or was the query wrong?

    They fail in the same place and mean opposite things: a wrong query can be rewritten, an
    unreachable database cannot. Asking a model to repair SQL that was already correct costs a wait
    and produces nothing, and telling a user their question was invalid when the connection dropped
    sends them looking in the wrong place.
    """
    text = str(error or "")
    if any(f"'{state}'" in text or f"[{state}]" in text for state in _CONNECTION_STATES):
        return True
    low = text.lower()
    return any(w in low for w in _CONNECTION_WORDS)
