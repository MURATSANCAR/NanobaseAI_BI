"""Generic SQL shape guard (datasource-agnostic).

Applied after LLM plan and before Query Gateway validate:
- Unwrap outer ``SELECT * FROM (<subquery>)`` wrappers (policy rejects SELECT *).
- Flag physical tables not present in the authorized retrieval allowlist.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class ShapeGuardResult:
    sql: str
    warnings: list[str] = field(default_factory=list)
    blocked: bool = False
    code: str | None = None
    message: str | None = None


_SELECT_STAR_PREFIX = re.compile(r"(?is)^\s*select\s*\*\s*from\s*\(\s*")
# Allow ``) AS q LIMIT 1000`` wrappers the LLM often emits around WITH/SELECT.
_TRAILING_ALIAS = re.compile(
    r"(?is)^\s*(?:(?:as\s+)?[a-zA-Z_][\w]*)?\s*(?:limit\s+\d+\s*)?;?\s*$"
)

_SCHEMA_LIKE = frozenset(
    {
        "public",
        "dbo",
        "analytics",
        "reporting",
        "pg_catalog",
        "information_schema",
        "sys",
        "sap",
    }
)

# Qualified refs that are never table aliases in our dialect surface.
_NON_ALIAS_LEFT = _SCHEMA_LIKE | {
    "date",
    "time",
    "timestamp",
    "interval",
    "array",
    "row",
    "json",
    "jsonb",
}



def _parse_any_dialect(sql_text: str):
    """Parse as PostgreSQL first, then T-SQL (TOP N etc.) — plans may target SQL Server."""
    import sqlglot as _sg

    try:
        return _sg.parse_one(sql_text, read="postgres")
    except Exception:
        return _sg.parse_one(sql_text, read="tsql")

def _norm_table(name: str) -> str:
    t = (name or "").strip().strip('"').strip("`").strip("[").strip("]").lower()
    if "." in t:
        return t
    return t


def _short(name: str) -> str:
    t = _norm_table(name)
    return t.rsplit(".", 1)[-1] if "." in t else t


def unwrap_select_star_subquery(sql: str) -> tuple[str, bool]:
    """If SQL is SELECT * FROM (<select|with...>) [AS alias], return inner statement."""
    text = (sql or "").strip().rstrip(";").strip()
    m = _SELECT_STAR_PREFIX.match(text)
    if not m:
        return text, False
    start = m.end()
    depth = 1
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                inner = text[start:i].strip().rstrip(";").strip()
                trailing = text[i + 1 :]
                if not _TRAILING_ALIAS.match(trailing):
                    return text, False
                if re.search(r"(?is)^\s*(with|select)\b", inner):
                    return inner, True
                return text, False
        i += 1
    return text, False


def _table_refs_sqlglot(sql: str) -> list[str] | None:
    """AST-based physical table refs; None when sqlglot can't parse.

    Replaces regex extraction as primary: the regex mishandles nested
    ``EXTRACT(... FROM CAST(...))`` (extracts ``cast`` as a table), flags table
    functions (``FROM generate_series(...)``), and silently skips short-schema
    refs like ``erp.fatura``.
    """
    try:
        import sqlglot
        from sqlglot import exp
    except ImportError:  # pragma: no cover
        return None
    text = (sql or "").strip()
    if not text:
        return []
    try:
        tree = _parse_any_dialect(text)
    except Exception:
        return None
    cte_names: set[str] = set()
    for cte in tree.find_all(exp.CTE):
        alias = cte.alias or getattr(cte, "alias_or_name", None)
        if alias:
            cte_names.add(str(alias).strip('"').lower())
    refs: list[str] = []
    seen: set[str] = set()
    for t in tree.find_all(exp.Table):
        # FROM func(...) parses as Table(this=Func) — a table function, not a ref.
        if isinstance(t.this, exp.Func):
            continue
        name = (t.name or "").strip('"').lower()
        if not name or name in cte_names:
            continue
        schema = (t.db or "").strip('"').lower()
        fq = f"{schema}.{name}" if schema else name
        if fq not in seen:
            seen.add(fq)
            refs.append(fq)
    return refs


def extract_table_refs(sql: str) -> list[str]:
    """Best-effort physical table names from FROM/JOIN (no CTE aliases)."""
    ast_refs = _table_refs_sqlglot(sql)
    if ast_refs is not None:
        return ast_refs
    text = sql or ""
    # Drop comments so prose like "from the context" never becomes a table ref.
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"--[^\n]*", " ", text)
    # Mask function-internal FROM (EXTRACT/TRIM/SUBSTRING) — not table refs.
    text = re.sub(
        r"(?is)\b(extract|trim|substring)\s*\((?:[^()]|\([^()]*\))*?\bfrom\b",
        lambda m: re.sub(r"(?i)\bfrom\b", "FRX", m.group(0)),
        text,
    )

    # CTE names to exclude
    cte_names: set[str] = set()
    for m in re.finditer(r"(?is)\bwith\s+([a-zA-Z_][\w]*)\s+as\s*\(", text):
        cte_names.add(m.group(1).lower())
    for m in re.finditer(r"(?is),\s*([a-zA-Z_][\w]*)\s+as\s*\(", text):
        cte_names.add(m.group(1).lower())

    refs: list[str] = []
    for m in re.finditer(
        r"(?is)\b(?:from|join)\s+((?:\"?[a-zA-Z_][\w]*\"?\.)?\"?[a-zA-Z_][\w]*\"?)",
        text,
    ):
        raw = m.group(1).replace('"', "")
        n = _norm_table(raw)
        if not n or _short(n) in cte_names:
            continue
        if "." in n:
            left, _right = n.split(".", 1)
            if left not in _SCHEMA_LIKE and len(left) <= 4:
                # f.fatura_tarihi / af.created_at — column ref, not schema.table
                continue
        refs.append(n)
    # de-dupe preserve order
    out: list[str] = []
    seen: set[str] = set()
    for r in refs:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def _allowlist_match(ref: str, allowed: set[str]) -> bool:
    if not allowed:
        return True
    r = _norm_table(ref)
    rs = _short(r)
    for a in allowed:
        an = _norm_table(a)
        if r == an or rs == _short(an) or r.endswith("." + _short(an)) or an.endswith("." + rs):
            return True
    return False


def _strip_strings_and_comments(sql: str) -> str:
    text = sql or ""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"--[^\n]*", " ", text)
    text = re.sub(r"'(?:[^']|'')*'", "''", text)
    text = re.sub(r'"(?:[^"]|"")*"', '""', text)
    return text


def _depth_at_positions(text: str) -> list[int]:
    depths: list[int] = [0] * (len(text) + 1)
    depth = 0
    for i, ch in enumerate(text):
        depths[i] = depth
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        depths[i + 1] = depth
    return depths


def _select_scope_spans(text: str) -> list[tuple[int, int, int]]:
    """Return (start, end, base_depth) for each SELECT/WITH-select scope body."""
    depths = _depth_at_positions(text)
    spans: list[tuple[int, int, int]] = []
    for m in re.finditer(r"(?is)\bselect\b", text):
        start = m.start()
        base = depths[start]
        end = len(text)
        i = m.end()
        while i < len(text):
            if text[i] == ")" and depths[i] == base:
                end = i
                break
            # Sibling UNION/INTERSECT/EXCEPT at same depth ends this select arm.
            if depths[i] == base and re.match(
                r"(?is)\b(union|intersect|except)\b", text[i : i + 10]
            ):
                end = i
                break
            i += 1
        spans.append((start, end, base))
    return spans


_FROM_CLAUSE_END = re.compile(
    r"(?is)^(where|group\s+by|order\s+by|having|limit|offset|fetch|window|qualify|"
    r"union|intersect|except|join|inner|left|right|full|cross|natural|on|using)\b"
)

_RELATION_WITH_ALIAS = re.compile(
    r"(?is)^\s*((?:\"?[a-zA-Z_][\w]*\"?\.)?\"?[a-zA-Z_][\w]*\"?)"
    r"(?:\s+(?:as\s+)?(\"?[a-zA-Z_][\w]*\"?))?\s*$"
)


def _register_relation(aliases: set[str], rel: str, alias_raw: str | None) -> None:
    if alias_raw:
        aliases.add(alias_raw.replace('"', "").lower())
    short = _short(rel)
    if short and short not in _NON_ALIAS_LEFT:
        aliases.add(short.lower())
    # schema.table also exposes table short name
    if "." in rel:
        aliases.add(rel.lower())


def _comma_join_relations(
    fragment: str, *, base_depth: int, depths: list[int], abs_start: int, aliases: set[str]
) -> None:
    """Register ``FROM a x, b y`` comma-list relations (LLMs emit these routinely;
    only the first relation used to be registered → false UNDEFINED_TABLE_ALIAS)."""
    for fm in re.finditer(r"(?is)\bfrom\s+", fragment):
        kw_at = abs_start + fm.start()
        if kw_at >= len(depths) or depths[kw_at] != base_depth:
            continue
        i = fm.end()
        # Find the end of this FROM clause at the same paren depth.
        while i < len(fragment):
            abs_i = abs_start + i
            if abs_i < len(depths) and depths[abs_i] == base_depth and _FROM_CLAUSE_END.match(
                fragment[i : i + 12]
            ):
                break
            i += 1
        clause = fragment[fm.end() : i]
        # Split on top-level commas within the clause.
        parts: list[str] = []
        buf: list[str] = []
        depth0 = 0
        for ch in clause:
            if ch == "(":
                depth0 += 1
            elif ch == ")":
                depth0 -= 1
            if ch == "," and depth0 == 0:
                parts.append("".join(buf))
                buf = []
            else:
                buf.append(ch)
        parts.append("".join(buf))
        for part in parts[1:]:  # first relation is handled by the FROM/JOIN regex
            pm = _RELATION_WITH_ALIAS.match(part)
            if pm:
                alias2 = pm.group(2)
                if alias2 and _FROM_CLAUSE_END.match(alias2):
                    alias2 = None
                _register_relation(aliases, pm.group(1).replace('"', ""), alias2)


def _aliases_in_scope(fragment: str, *, base_depth: int, depths: list[int], abs_start: int) -> set[str]:
    """FROM/JOIN relation names + aliases at the select's own depth (not nested)."""
    aliases: set[str] = set()
    for m in re.finditer(
        r"(?is)\b(?:from|join)\s+"
        r"((?:\"?[a-zA-Z_][\w]*\"?\.)?\"?[a-zA-Z_][\w]*\"?)"
        r"(?:\s+(?:as\s+)?(\"?[a-zA-Z_][\w]*\"?))?",
        fragment,
    ):
        rel_at = abs_start + m.start(1)
        if rel_at >= len(depths) or depths[rel_at] != base_depth:
            continue
        rel = m.group(1).replace('"', "")
        _register_relation(aliases, rel, m.group(2))
    _comma_join_relations(
        fragment, base_depth=base_depth, depths=depths, abs_start=abs_start, aliases=aliases
    )
    return aliases


def _qualified_alias_refs(
    fragment: str, *, base_depth: int, depths: list[int], abs_start: int
) -> set[str]:
    refs: set[str] = set()
    for m in re.finditer(r"(?is)\b([a-zA-Z_][\w]*)\.([a-zA-Z_][\w]*)", fragment):
        at = abs_start + m.start(1)
        if at >= len(depths) or depths[at] != base_depth:
            continue
        left = m.group(1).lower()
        if left in _NON_ALIAS_LEFT:
            continue
        refs.add(left)
    return refs


def find_undefined_table_aliases(sql: str) -> list[str]:
    """Return table-alias names used as ``alias.col`` but missing from that SELECT's FROM/JOIN.

    Catches the common multi-CTE LLM bug, e.g. ``SELECT m.il_id ... FROM musteri_ciro mc``.
    Outer-query aliases are inherited so correlated subqueries are not false-positives.
    """
    text = _strip_strings_and_comments(sql or "")
    if not text.strip():
        return []
    depths = _depth_at_positions(text)
    spans = _select_scope_spans(text)
    own_scopes: list[set[str]] = []
    for start, end, base in spans:
        fragment = text[start:end]
        own_scopes.append(
            _aliases_in_scope(fragment, base_depth=base, depths=depths, abs_start=start)
        )

    bad: list[str] = []
    seen: set[str] = set()
    for idx, (start, end, base) in enumerate(spans):
        fragment = text[start:end]
        scope = set(own_scopes[idx])
        # Inherit FROM aliases from enclosing SELECT scopes (correlation).
        for j, (s2, e2, b2) in enumerate(spans):
            if b2 < base and s2 <= start and end <= e2:
                scope |= own_scopes[j]
        if not own_scopes[idx]:
            # SELECT without its own FROM (VALUES / SELECT 1) — skip.
            continue
        for ref in sorted(
            _qualified_alias_refs(fragment, base_depth=base, depths=depths, abs_start=start)
        ):
            if ref in scope:
                continue
            key = f"{ref}@{start}"
            if key in seen:
                continue
            seen.add(key)
            bad.append(ref)
    out: list[str] = []
    seen2: set[str] = set()
    for a in bad:
        if a not in seen2:
            seen2.add(a)
            out.append(a)
    return out


def rewrite_order_by_select_aliases(sql: str) -> tuple[str, bool]:
    """Rewrite ``ORDER BY alias`` to ordinal when alias is a SELECT output alias.

    Fixes Postgres errors like ``column "toplam_deger" does not exist`` when the
    name is only a select-list alias (common LLM slip in CTEs).
    """
    try:
        import sqlglot
        from sqlglot import exp
    except ImportError:  # pragma: no cover
        return sql, False

    text = (sql or "").strip()
    if not text or not re.search(r"(?is)\border\s+by\b", text):
        return text, False
    try:
        tree = _parse_any_dialect(text)
    except Exception:
        return text, False

    changed = False
    for select in tree.find_all(exp.Select):
        alias_to_ord: dict[str, int] = {}
        for i, proj in enumerate(select.expressions or [], start=1):
            alias = None
            if isinstance(proj, exp.Alias):
                alias = proj.alias
            elif hasattr(proj, "alias_or_name"):
                # bare column projected as itself is fine for ORDER BY name
                continue
            if not alias:
                continue
            alias_to_ord[str(alias).strip('"').lower()] = i
        if not alias_to_ord or not select.args.get("order"):
            continue
        order = select.args["order"]
        expressions = list(getattr(order, "expressions", None) or [])
        new_exprs = []
        for ordered in expressions:
            # ordered is usually Ordered(this=col, desc=...)
            this = getattr(ordered, "this", ordered)
            name = None
            if isinstance(this, exp.Column) and not this.table:
                name = str(this.name or "").lower()
            elif isinstance(this, exp.Identifier):
                name = str(this.this or "").lower()
            if name and name in alias_to_ord:
                ordinal = exp.Literal.number(alias_to_ord[name])
                if isinstance(ordered, exp.Ordered):
                    ordered.set("this", ordinal)
                    new_exprs.append(ordered)
                else:
                    new_exprs.append(exp.Ordered(this=ordinal))
                changed = True
            else:
                new_exprs.append(ordered)
        if changed:
            order.set("expressions", new_exprs)

    if not changed:
        return text, False
    try:
        return tree.sql(dialect="postgres"), True
    except Exception:
        return text, False


def guard_sql_shape(
    sql: str,
    *,
    allowed_tables: Iterable[str] | None = None,
    question: str | None = None,
    table_columns: dict[str, list[str]] | None = None,
    complete_tables: Iterable[str] | None = None,
    dialect: str = "postgres",
) -> ShapeGuardResult:
    """Sanitize / soft-block SQL before Gateway validate.

    ``complete_tables``: tables whose column list in ``table_columns`` is known
    to be exhaustive. When provided, COLUMN_NOT_FOUND hard-blocks only for those
    tables; misses on partially-retrieved tables become soft warnings (the
    Gateway owns the real catalog). When omitted, the caller vouches for
    completeness and the legacy hard-block behavior applies.
    """
    warnings: list[str] = []
    text = (sql or "").strip()
    if not text:
        return ShapeGuardResult(sql="", blocked=True, code="SQL_PARSE_FAILED", message="Boş SQL.")

    unwrapped, did_unwrap = unwrap_select_star_subquery(text)
    if did_unwrap:
        text = unwrapped
        warnings.append("unwrapped_select_star_subquery")

    rewritten, did_order = rewrite_order_by_select_aliases(text)
    if did_order:
        text = rewritten
        warnings.append("rewrote_order_by_select_alias")

    # Still has bare SELECT * projection at top level (not COUNT(*))
    if re.search(r"(?is)^\s*select\s+\*", text) or re.search(r"(?is)^\s*with\b[\s\S]+\)\s*select\s+\*", text):
        # Try one more unwrap pass
        unwrapped2, did2 = unwrap_select_star_subquery(text)
        if did2:
            text = unwrapped2
            warnings.append("unwrapped_select_star_subquery")
        elif re.search(r"(?is)select\s+\*\s+from", text):
            return ShapeGuardResult(
                sql=text,
                warnings=warnings,
                blocked=True,
                code="WILDCARD_NOT_ALLOWED",
                message="SELECT * üretim ortamında izinli değildir.",
            )

    allowed = {_norm_table(t) for t in (allowed_tables or []) if t}
    # Tables explicitly named in the user question are treated as in-scope even if
    # retrieval missed them (generic; no static catalog).
    qlow = (question or "").lower()
    if allowed:
        refs = extract_table_refs(text)
        bad: list[str] = []
        for r in refs:
            if _allowlist_match(r, allowed):
                continue
            short = _short(r)
            if qlow and short and re.search(rf"(?<![a-z0-9_]){re.escape(short)}(?![a-z0-9_])", qlow):
                warnings.append(f"table_mentioned_in_question:{short}")
                continue
            bad.append(r)
        if bad:
            return ShapeGuardResult(
                sql=text,
                warnings=warnings,
                blocked=True,
                code="TABLE_OR_VIEW_NOT_FOUND",
                message=(
                    "Yetkisiz veya bilinmeyen tablo referansı: "
                    + ", ".join(bad[:6])
                    + ". Yalnızca yetkili şema bağlamındaki tabloları kullanın."
                ),
            )

    # Catch ``alias.col`` where alias is not introduced in that SELECT's FROM/JOIN
    # (Postgres: missing FROM-clause entry). Repairable before execute.
    undefined = find_undefined_table_aliases(text)
    if undefined:
        return ShapeGuardResult(
            sql=text,
            warnings=warnings,
            blocked=True,
            code="UNDEFINED_TABLE_ALIAS",
            message=(
                "SQL'de tanımsız tablo alias'ı var: "
                + ", ".join(undefined[:8])
                + ". Her SELECT/CTE içinde kullanılan alias FROM/JOIN'de tanımlanmalı "
                "(ör. m.il_id yazdıysanız FROM ... AS m olmalı)."
            ),
        )

    if table_columns:
        try:
            from nanobase_awel.operators.schema_reference_validator import find_unknown_columns

            unknown = find_unknown_columns(text, dict(table_columns), dialect=dialect)
        except Exception:
            unknown = []
        if unknown:
            if complete_tables is None:
                complete = None
            else:
                complete = {_norm_table(t) for t in complete_tables if t}
                complete |= {_short(t) for t in complete}
            hard: list[tuple[str, str, list[str]]] = []
            for fq, col, sample in unknown:
                if complete is None or _norm_table(fq) in complete or _short(fq) in complete:
                    hard.append((fq, col, sample))
                else:
                    # Partial retrieval must not be enforced as exhaustive —
                    # that blocks valid SQL and steers repairs to a
                    # wrong-but-retrieved column (silent wrong answers).
                    warnings.append(f"column_not_in_retrieval:{fq}.{col}")
            if hard:
                fq, col, sample = hard[0]
                sample_s = ", ".join(sample[:12]) if sample else "(none)"
                return ShapeGuardResult(
                    sql=text,
                    warnings=warnings,
                    blocked=True,
                    code="COLUMN_NOT_FOUND",
                    message=(
                        f"Kolon bulunamadı: {fq}.{col}. Bu tabloda bilinen kolonlar: {sample_s}"
                    ),
                )

    return ShapeGuardResult(sql=text, warnings=warnings)
