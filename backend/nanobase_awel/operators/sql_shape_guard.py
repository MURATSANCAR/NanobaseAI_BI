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


def extract_table_refs(sql: str) -> list[str]:
    """Best-effort physical table names from FROM/JOIN (no CTE aliases)."""
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
        alias_raw = m.group(2)
        if alias_raw:
            aliases.add(alias_raw.replace('"', "").lower())
        short = _short(rel)
        if short and short not in _NON_ALIAS_LEFT:
            aliases.add(short.lower())
        # schema.table also exposes table short name
        if "." in rel:
            aliases.add(rel.lower())
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


def guard_sql_shape(
    sql: str,
    *,
    allowed_tables: Iterable[str] | None = None,
    question: str | None = None,
) -> ShapeGuardResult:
    """Sanitize / soft-block SQL before Gateway validate."""
    warnings: list[str] = []
    text = (sql or "").strip()
    if not text:
        return ShapeGuardResult(sql="", blocked=True, code="SQL_PARSE_FAILED", message="Boş SQL.")

    unwrapped, did_unwrap = unwrap_select_star_subquery(text)
    if did_unwrap:
        text = unwrapped
        warnings.append("unwrapped_select_star_subquery")

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

    return ShapeGuardResult(sql=text, warnings=warnings)
