"""HANA SQL fail-closed policy (token + structural guards)."""

from __future__ import annotations

import re
from typing import Any

from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.sap import FORBIDDEN_RAW_SAP_TABLES

HANA_POLICY_VIOLATION = "HANA_POLICY_VIOLATION"

_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|UPSERT|MERGE|CREATE|ALTER|DROP|TRUNCATE|"
    r"CALL|EXEC|EXECUTE|DO\b|IMPORT|EXPORT|BACKUP|RESTORE|GRANT|REVOKE|"
    r"CREATE\s+REMOTE\s+SOURCE|REPLACE\s+PROCEDURE|CREATE\s+PROCEDURE|"
    r"CREATE\s+FUNCTION|ANONYMOUS\s+BLOCK)\b",
    re.I,
)

_SQLSCRIPT = re.compile(
    r"\b(DECLARE|BEGIN\s+.*?END\s*;|EXECUTE\s+IMMEDIATE|USING\s+SQLSCRIPT|"
    r"TABLE\s+VARIABLE|ARRAY\s*\()\b",
    re.I | re.S,
)

_REMOTE = re.compile(
    r"(REMOTE_SOURCE|VIRTUAL\s+TABLE|CREATE\s+VIRTUAL|\b_SYS_|\.\$|\bSYS\.|\bM_[A-Z0-9_]+)",
    re.I,
)

_COMMENT_STRIP = re.compile(r"/\*.*?\*/|--.*?$", re.S | re.M)

ALLOWED_FUNCTIONS = frozenset(
    {
        "COUNT",
        "SUM",
        "AVG",
        "MIN",
        "MAX",
        "ROUND",
        "CEIL",
        "FLOOR",
        "ABS",
        "COALESCE",
        "NULLIF",
        "LOWER",
        "UPPER",
        "TRIM",
        "LENGTH",
        "SUBSTRING",
        "CONCAT",
        "TO_DATE",
        "TO_TIMESTAMP",
        "ADD_DAYS",
        "ADD_MONTHS",
        "YEAR",
        "MONTH",
        "DAYOFMONTH",
        "CURRENT_DATE",
        "ROW_NUMBER",
        "RANK",
        "DENSE_RANK",
        "LAG",
        "LEAD",
        "CAST",
        "IFNULL",
    }
)

CONTROLLED_FUNCTIONS = frozenset(
    {
        "CONVERT_CURRENCY",
        "JSON_VALUE",
        "JSON_QUERY",
        "SERIES_GENERATE",
        "STRING_AGG",
    }
)

DENIED_FUNCTIONS = frozenset(
    {
        "SESSION_CONTEXT",
        "XSJS",
        "EXECUTE_DYNAMIC",
    }
)


def _strip_comments(sql: str) -> str:
    return _COMMENT_STRIP.sub(" ", sql or "")


def enforce_hana_sql_policy(sql: str, parsed: Any | None = None) -> list[str]:
    warnings: list[str] = []
    cleaned = _strip_comments(sql)
    if not cleaned.strip():
        raise GatewayError(HANA_POLICY_VIOLATION, "Empty SQL.", status=400)

    if _FORBIDDEN_KEYWORDS.search(cleaned):
        raise GatewayError(HANA_POLICY_VIOLATION, "DML/DDL/SQLScript statement denied.", status=400)
    if _SQLSCRIPT.search(cleaned):
        raise GatewayError(HANA_POLICY_VIOLATION, "SQLScript constructs denied.", status=400)
    if _REMOTE.search(cleaned):
        raise GatewayError(HANA_POLICY_VIOLATION, "Remote/virtual/SYS access denied.", status=400)

    upper = cleaned.upper()
    for table in FORBIDDEN_RAW_SAP_TABLES:
        if re.search(rf"\b{table}\b", upper):
            raise GatewayError(
                HANA_POLICY_VIOLATION,
                f"Raw SAP table access denied: {table}",
                status=403,
            )

    # Must look like SELECT / WITH
    head = cleaned.lstrip().upper()
    if not (head.startswith("SELECT") or head.startswith("WITH")):
        raise GatewayError(HANA_POLICY_VIOLATION, "Only SELECT/WITH allowed.", status=400)

    # Function scan
    for fn in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", cleaned):
        name = fn.upper()
        if name in DENIED_FUNCTIONS:
            raise GatewayError(HANA_POLICY_VIOLATION, f"Function denied: {name}", status=400)
        if name in CONTROLLED_FUNCTIONS:
            warnings.append(f"controlled_function:{name}")
        # Unknown functions outside allowlist that look like UDFs — deny common dangerous ones
        if name.startswith("SYS_") or name.startswith("_SYS"):
            raise GatewayError(HANA_POLICY_VIOLATION, f"System function denied: {name}", status=400)

    if parsed is not None:
        for t in getattr(parsed, "tables", []) or []:
            base = str(t).split(".")[-1].upper()
            if base in FORBIDDEN_RAW_SAP_TABLES:
                raise GatewayError(
                    HANA_POLICY_VIOLATION,
                    f"Raw SAP table access denied: {base}",
                    status=403,
                )

    return warnings


def assert_view_allowlisted(sql: str, allowed_views: list[str] | set[str] | None) -> None:
    if not allowed_views:
        return
    allowed = {v.upper() for v in allowed_views}
    # Extract schema.view-like tokens
    refs = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)\b", sql)
    for ref in refs:
        if ref.upper() not in allowed and ref.split(".")[-1].upper() not in {
            a.split(".")[-1] for a in allowed
        }:
            # Allow if any allowed view matches fully
            if ref.upper() not in allowed:
                # Only enforce when it looks like a reporting object
                if "NANOBASE" in ref.upper() or "CV_" in ref.upper() or "V_" in ref.upper():
                    raise GatewayError(
                        HANA_POLICY_VIOLATION,
                        f"View not allowlisted: {ref}",
                        status=403,
                    )
