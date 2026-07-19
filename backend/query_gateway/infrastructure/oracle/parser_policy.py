"""Oracle-specific SQL policy checks beyond generic sqlglot parse."""

from __future__ import annotations

import re

from query_gateway.domain.errors import FUNCTION_NOT_ALLOWED, STATEMENT_NOT_ALLOWED, GatewayError
from query_gateway.infrastructure.parser.sqlglot_parser import ParsedQuery

# Optimizer hint: /*+ ... */ (executable) vs /* normal */
HINT_RE = re.compile(r"/\*\+[^*]*\*+(?:[^/*][^*]*\*+)*/", re.IGNORECASE | re.DOTALL)
DB_LINK_RE = re.compile(r"@\s*[\w$#]+|db\s*_?\s*link", re.IGNORECASE)
PLSQL_RE = re.compile(
    r"\b(BEGIN|DECLARE|CALL|EXEC(?:UTE)?|DBMS_SQL|EXECUTE\s+IMMEDIATE)\b",
    re.IGNORECASE,
)
FORBIDDEN_FEATURES_RE = re.compile(
    r"\b(CONNECT\s+BY|START\s+WITH|MATCH_RECOGNIZE|MODEL\s+|FLASHBACK|SAMPLE\s*\(|"
    r"XMLTABLE|ALTER\s+SESSION|SET\s+CONTAINER|LOCK\s+TABLE)\b",
    re.IGNORECASE,
)
FORBIDDEN_PACKAGES = frozenset(
    {
        "UTL_FILE",
        "UTL_HTTP",
        "UTL_TCP",
        "UTL_INADDR",
        "DBMS_SCHEDULER",
        "DBMS_JOB",
        "DBMS_SQL",
        "DBMS_PIPE",
        "DBMS_LOCK",
        "DBMS_ALERT",
        "DBMS_LDAP",
        "DBMS_XSLPROCESSOR",
        "DBMS_JAVA",
        "DBMS_BACKUP_RESTORE",
        "DBMS_SYS_SQL",
        "DBMS_RLS",  # user SQL must not call RLS admin APIs
    }
)

CONTROLLED_FEATURES = frozenset({"PIVOT", "UNPIVOT", "JSON_TABLE"})


def enforce_oracle_sql_policy(sql: str, parsed: ParsedQuery | None = None) -> list[str]:
    """Raise GatewayError on Oracle policy violation; return warnings."""
    warnings: list[str] = []
    raw = sql or ""

    if HINT_RE.search(raw):
        raise GatewayError(
            STATEMENT_NOT_ALLOWED,
            "Oracle optimizer hint'lerine izin verilmez.",
            status=400,
        )
    if DB_LINK_RE.search(raw):
        raise GatewayError(
            STATEMENT_NOT_ALLOWED,
            "Database link (@) kullanımına izin verilmez.",
            status=400,
        )
    if PLSQL_RE.search(raw):
        raise GatewayError(
            STATEMENT_NOT_ALLOWED,
            "PL/SQL bloklarına izin verilmez.",
            status=400,
        )
    if FORBIDDEN_FEATURES_RE.search(raw):
        raise GatewayError(
            STATEMENT_NOT_ALLOWED,
            "İzin verilmeyen Oracle SQL özelliği.",
            status=400,
        )

    # Package.function abuse in SELECT list
    for m in re.finditer(r"\b([A-Z][A-Z0-9_$#]*)\s*\.\s*([A-Z][A-Z0-9_$#]*)\s*\(", raw.upper()):
        pkg = m.group(1)
        if pkg in FORBIDDEN_PACKAGES:
            raise GatewayError(
                FUNCTION_NOT_ALLOWED,
                f"İzin verilmeyen Oracle paketi: {pkg}.",
                status=400,
            )

    if parsed:
        for fn in parsed.functions:
            name = fn.upper()
            if name in FORBIDDEN_PACKAGES or name.startswith("UTL_") or name.startswith("DBMS_"):
                if name not in ("DBMS_XPLAN",):  # never callable from user SQL path anyway
                    raise GatewayError(
                        FUNCTION_NOT_ALLOWED,
                        f"İzin verilmeyen fonksiyon/paket: {name}.",
                        status=400,
                    )
        upper_sql = raw.upper()
        for feat in CONTROLLED_FEATURES:
            if feat in upper_sql:
                warnings.append(f"controlled_feature:{feat}")

    return warnings
