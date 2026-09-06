"""Read-only SQL guardrails + physicalisation (model names → physical tables, dialect transpile)."""

from __future__ import annotations

import re
from typing import Optional

import sqlglot
from sqlglot import exp

from semantic_layer.models import SchemaProfile
from semantic_layer.naming import logical_table, physical_name

_DENY = re.compile(r"(?i)\b(insert|update|delete|drop|alter|truncate|merge|exec|execute|grant|revoke|create|into|openrowset|openquery|opendatasource|xp_\w+|sp_\w+|bulk|shutdown|dbcc|waitfor|kill|backup|restore)\b")
_COMMENT = re.compile(r"--|/\*|\*/")


def validate_sql(sql: str) -> tuple[bool, str]:
    s = (sql or "").strip().rstrip(";").strip()
    if not s:
        return False, "empty"
    if not re.match(r"(?is)^\s*(with|select)\b", s):
        return False, "only SELECT/WITH allowed"
    if ";" in s:
        return False, "multiple statements"
    if _COMMENT.search(s):
        return False, "comments not allowed"
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
