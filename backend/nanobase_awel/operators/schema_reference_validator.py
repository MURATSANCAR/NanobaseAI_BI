"""Static table/column reference check against authorized context (pre-Gateway)."""

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


def validate_plan_references(
    plan: SqlPlan,
    *,
    allowed_tables: set[str] | None,
    context_text: str,
) -> SqlPlan:
    if plan.status != PlanStatus.PLANNED or not plan.sql:
        return plan

    allowed = {_norm(t) for t in (allowed_tables or set())}
    # also harvest identifiers from context
    for m in re.finditer(r"\b([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)\b", context_text.lower()):
        allowed.add(m.group(1))
    for m in re.finditer(r"-\s*([a-z_][a-z0-9_]*)\(", context_text.lower()):
        allowed.add(m.group(1))
    # public.musteriler ↔ musteriler
    expanded: set[str] = set()
    for a in allowed:
        expanded.add(a)
        bare = a.split(".")[-1]
        expanded.add(bare)
        if "." not in a:
            expanded.add(f"public.{a}")
    allowed = expanded

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

    # sync declared tables if empty
    if not plan.tables and found_tables:
        plan.tables = sorted(found_tables)
    return plan
