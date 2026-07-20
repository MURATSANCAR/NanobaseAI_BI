"""Table/column reference check against authorized retrieval (pre-Gateway)."""

from __future__ import annotations

import re

from nanobase_awel.contracts.errors import SCHEMA_REFERENCE_FAILED, WorkflowError
from nanobase_awel.contracts.planning import PlanStatus, SqlPlan

try:
    import sqlglot
    from sqlglot import exp
except ImportError:  # pragma: no cover
    sqlglot = None
    exp = None


def _norm(name: str) -> str:
    return name.strip().strip('"').strip("`").lower()


def _expand_table_keys(allowed: set[str]) -> set[str]:
    expanded: set[str] = set()
    for a in allowed:
        expanded.add(a)
        bare = a.split(".")[-1]
        expanded.add(bare)
        if "." not in a:
            expanded.add(f"public.{a}")
    return expanded


def find_unknown_columns(
    sql: str,
    table_columns: dict[str, list[str]] | None,
) -> list[tuple[str, str, list[str]]]:
    """Return (table_fq, bad_column, allowed_sample) for physical-table column misses.

    CTE/alias columns are ignored. Only qualified ``alias.col`` / ``table.col`` refs
    against known physical tables in ``table_columns`` are checked.
    """
    if sqlglot is None or exp is None or not table_columns:
        return []
    sql_text = (sql or "").strip()
    if not sql_text:
        return []
    try:
        tree = sqlglot.parse_one(sql_text, read="postgres")
    except Exception:
        return []

    # alias/table → fq key in table_columns
    col_map: dict[str, list[str]] = {}
    for k, cols in table_columns.items():
        nk = _norm(k)
        col_map[nk] = [c.lower() for c in cols]
        col_map[_norm(k.split(".")[-1])] = col_map[nk]

    cte_names: set[str] = set()
    for cte in tree.find_all(exp.CTE):
        alias = cte.alias or getattr(cte, "alias_or_name", None)
        if alias:
            cte_names.add(_norm(str(alias)))

    alias_to_fq: dict[str, str] = {}
    for t in tree.find_all(exp.Table):
        name = _norm(t.name) if t.name else ""
        schema = _norm(t.db) if t.db else ""
        if not name or name in cte_names:
            continue
        fq = f"{schema}.{name}" if schema else name
        # Resolve to a key present in col_map
        resolved = fq if fq in col_map else (name if name in col_map else "")
        if not resolved:
            # try public.name
            pub = f"public.{name}"
            resolved = pub if pub in col_map else ""
        if not resolved:
            continue
        alias_to_fq[name] = resolved
        if schema:
            alias_to_fq[fq] = resolved
        a = t.alias_or_name
        if a and _norm(str(a)) != name:
            alias_to_fq[_norm(str(a))] = resolved

    bad: list[tuple[str, str, list[str]]] = []
    seen: set[str] = set()
    for col in tree.find_all(exp.Column):
        cname = _norm(col.name) if col.name else ""
        table = _norm(col.table) if col.table else ""
        if not cname or not table:
            continue
        if table in cte_names:
            continue
        fq = alias_to_fq.get(table)
        if not fq:
            continue
        allowed = col_map.get(fq) or []
        if not allowed:
            continue
        if cname in allowed:
            continue
        key = f"{fq}.{cname}"
        if key in seen:
            continue
        seen.add(key)
        bad.append((fq, cname, list(allowed)[:24]))
    return bad


def validate_plan_references(
    plan: SqlPlan,
    *,
    allowed_tables: set[str] | None,
    context_text: str,
    table_columns: dict[str, list[str]] | None = None,
) -> SqlPlan:
    if plan.status != PlanStatus.PLANNED or not plan.sql:
        return plan

    allowed = {_norm(t) for t in (allowed_tables or set())}
    # also harvest identifiers from context
    for m in re.finditer(r"\b([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)\b", context_text.lower()):
        allowed.add(m.group(1))
    for m in re.finditer(r"-\s*([a-z_][a-z0-9_]*)\(", context_text.lower()):
        allowed.add(m.group(1))
    allowed = _expand_table_keys(allowed)

    if sqlglot is None:
        return plan

    sql_text = (plan.sql or "").strip()
    # Models sometimes wrap SQL in markdown / prose — peel a SELECT/WITH block.
    if sql_text and not re.match(r"(?is)^(with|select)\b", sql_text):
        m = re.search(r"(?is)\b((?:with|select)\b[\s\S]{8,8000})", sql_text)
        if m:
            sql_text = m.group(1).strip().rstrip(";")
            plan.sql = sql_text
            plan.warnings = [*(plan.warnings or []), "sql_extracted_before_validate"]

    try:
        tree = sqlglot.parse_one(sql_text, read="postgres")
    except Exception as e:
        # Soft-fail: Gateway still validates; hard-fail blocked usable Arctic drafts.
        plan.warnings = [*(plan.warnings or []), f"sql_parse_soft_fail:{type(e).__name__}"]
        return plan

    cte_aliases: set[str] = set()
    for cte in tree.find_all(exp.CTE):
        alias = cte.alias or getattr(cte, "alias_or_name", None)
        if alias:
            cte_aliases.add(_norm(str(alias)))

    found_tables: set[str] = set()
    for t in tree.find_all(exp.Table):
        name = _norm(t.name) if t.name else ""
        schema = _norm(t.db) if t.db else ""
        if not name or name in cte_aliases:
            continue
        fq = f"{schema}.{name}" if schema else name
        found_tables.add(fq)
        found_tables.add(name)

    if allowed:
        for t in found_tables:
            bare = t.split(".")[-1]
            if bare in cte_aliases:
                continue
            if t not in allowed and bare not in allowed and f"public.{bare}" not in allowed:
                raise WorkflowError(
                    SCHEMA_REFERENCE_FAILED,
                    f"Yetkisiz veya bilinmeyen tablo referansı: {t}",
                )

    cols = table_columns
    if cols is None and context_text:
        # Best-effort harvest "table: col1, col2" lines from authorized hint.
        cols = {}
        for m in re.finditer(
            r"(?m)^\s{0,4}((?:[a-z_][\w]*\.)?[a-z_][\w]*)\s*:\s*([a-z_][\w,\s]+)$",
            context_text.lower(),
        ):
            cols[m.group(1)] = [c.strip() for c in m.group(2).split(",") if c.strip()]
    unknown = find_unknown_columns(sql_text, cols)
    if unknown:
        fq, col, _sample = unknown[0]
        # Soft warn here so chat shape-guard can hard-block with repairable COLUMN_NOT_FOUND
        # while keeping plan.sql available for the repair loop.
        plan.warnings = [*(plan.warnings or []), f"column_not_in_retrieval:{fq}.{col}"]

    # sync declared tables if empty
    if not plan.tables and found_tables:
        plan.tables = sorted(found_tables)
    return plan
