"""Named bind parameter helpers for Query Gateway.

Templates use :name placeholders. Validation rewrites to typed literals for sqlglot.
Execution rewrites to psycopg2 %(name)s with a validated scalar dict.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from query_gateway.domain.errors import GatewayError

# Match :name but not Postgres casts (::type)
_BIND_RE = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")


def _segments(sql: str) -> list[tuple[str, bool]]:
    """`sql` split into (text, is_code) runs — code being everything outside string literals,
    quoted identifiers and comments.

    A colon inside a literal is part of the text, not a placeholder. Substituted blindly,
    `SELECT ':status' AS label` declares a bind named `status` that the caller never sent — so a
    valid statement is refused for a missing parameter — and rewriting turns the literal itself into
    something else. A time of day, a URL or a JSON fragment in a WHERE clause is enough to trigger it.
    """
    out: list[tuple[str, bool]] = []
    buf: list[str] = []
    i, n = 0, len(sql)

    def flush() -> None:
        if buf:
            out.append(("".join(buf), True))
            buf.clear()

    while i < n:
        ch = sql[i]
        if ch == "'":
            flush()
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":   # doubled quote escapes itself
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            out.append((sql[i:j], False))
            i = j
            continue
        if ch in '"`':
            flush()
            j = sql.find(ch, i + 1)
            j = n if j == -1 else j + 1
            out.append((sql[i:j], False))
            i = j
            continue
        if ch == "[":
            flush()
            j = sql.find("]", i + 1)
            j = n if j == -1 else j + 1
            out.append((sql[i:j], False))
            i = j
            continue
        if sql.startswith("--", i):
            flush()
            j = sql.find("\n", i)
            j = n if j == -1 else j
            out.append((sql[i:j], False))
            i = j
            continue
        if sql.startswith("/*", i):
            flush()
            j = sql.find("*/", i + 2)
            j = n if j == -1 else j + 2
            out.append((sql[i:j], False))
            i = j
            continue
        buf.append(ch)
        i += 1
    flush()
    return out


def _sub_code(sql: str, repl) -> str:
    """Apply `repl` to placeholders in code, leaving literals, identifiers and comments untouched."""
    return "".join(_BIND_RE.sub(repl, text) if code else text for text, code in _segments(sql or ""))

_ALLOWED = (str, int, float, bool, date, datetime, type(None))


def validate_parameters(parameters: dict[str, Any] | None) -> dict[str, Any]:
    if not parameters:
        return {}
    out: dict[str, Any] = {}
    for k, v in parameters.items():
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", str(k)):
            raise GatewayError("INVALID_BIND_PARAM", f"Geçersiz parametre adı: {k}", status=400)
        if not isinstance(v, _ALLOWED):
            raise GatewayError(
                "INVALID_BIND_PARAM",
                f"Parametre tipi desteklenmiyor: {k}={type(v).__name__}",
                status=400,
            )
        out[str(k)] = v
    return out


def extract_bind_names(sql_template: str) -> list[str]:
    names: list[str] = []
    for text, code in _segments(sql_template or ""):
        if code:
            names.extend(_BIND_RE.findall(text))
    return list(dict.fromkeys(names))


def to_psycopg_sql(sql_template: str) -> str:
    """Convert :name binds to %(name)s for psycopg2."""

    def repl(m: re.Match[str]) -> str:
        return f"%({m.group(1)})s"

    return _sub_code(sql_template, repl)


def probe_sql_for_parse(sql_template: str, parameters: dict[str, Any] | None = None) -> str:
    """Replace binds with typed SQL literals so sqlglot can parse the template."""
    params = validate_parameters(parameters)
    names = extract_bind_names(sql_template)

    def lit(name: str) -> str:
        if name not in params:
            # Unknown bind — use NULL for structural parse
            if name.endswith("limit") or name == "fetch_limit":
                return "1"
            if "status" in name:
                return "'x'"
            return "NULL"
        v = params[name]
        if v is None:
            return "NULL"
        if isinstance(v, bool):
            return "TRUE" if v else "FALSE"
        if isinstance(v, (int, float)):
            return str(v)
        if isinstance(v, datetime):
            return f"'{v.isoformat()}'"
        if isinstance(v, date):
            return f"'{v.isoformat()}'"
        s = str(v).replace("'", "''")
        return f"'{s}'"

    def repl(m: re.Match[str]) -> str:
        return lit(m.group(1))

    return _sub_code(sql_template, repl)


def assert_binds_present(sql_template: str, parameters: dict[str, Any]) -> None:
    needed = set(extract_bind_names(sql_template))
    missing = needed - set(parameters.keys())
    # Allow missing only if we will use defaults in probe — for execute, require all
    if missing:
        raise GatewayError(
            "MISSING_BIND_PARAM",
            f"Eksik bind parametreleri: {sorted(missing)}",
            status=400,
        )
