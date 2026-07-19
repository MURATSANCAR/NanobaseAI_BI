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
    return list(dict.fromkeys(_BIND_RE.findall(sql_template or "")))


def to_psycopg_sql(sql_template: str) -> str:
    """Convert :name binds to %(name)s for psycopg2."""

    def repl(m: re.Match[str]) -> str:
        return f"%({m.group(1)})s"

    return _BIND_RE.sub(repl, sql_template)


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

    return _BIND_RE.sub(repl, sql_template)


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
