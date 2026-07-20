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
_TRAILING_ALIAS = re.compile(r"(?is)^\s*(?:(?:as\s+)?[a-zA-Z_][\w]*)?\s*;?\s*$")


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


def guard_sql_shape(
    sql: str,
    *,
    allowed_tables: Iterable[str] | None = None,
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
    if allowed:
        refs = extract_table_refs(text)
        bad = [r for r in refs if not _allowlist_match(r, allowed)]
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

    return ShapeGuardResult(sql=text, warnings=warnings)
