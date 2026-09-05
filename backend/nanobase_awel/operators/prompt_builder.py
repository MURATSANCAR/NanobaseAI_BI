"""Load versioned Jinja2 (or plain) prompts from package."""

from __future__ import annotations

from pathlib import Path

_PROMPTS = Path(__file__).resolve().parents[1] / "prompts"


def _read(rel: str) -> str:
    path = _PROMPTS / rel
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


def render_simple(template: str, **kwargs: str) -> str:
    out = template
    for k, v in kwargs.items():
        out = out.replace("{{ " + k + " }}", v).replace("{{" + k + "}}", v)
    return out


def sql_plan_prompts(*, dialect: str = "postgres") -> tuple[str, str]:
    dialect_l = (dialect or "postgres").lower().replace("postgresql", "postgres")
    if dialect_l == "oracle":
        system = _read("sql-plan/v1-oracle/system.jinja2") or (
            "You are nanobase-oracle-sql-plan-v1. Output valid JSON only. "
            "Oracle SELECT only. FETCH FIRST. No LIMIT/hints/DB links/PL/SQL."
        )
        user_tpl = _read("sql-plan/v1-oracle/user.jinja2") or (
            "{{ context_blocks }}\n\nQuestion: {{ question }}\n\n"
            "Return ONLY JSON. dialect must be oracle."
        )
        return system, user_tpl
    if dialect_l in ("odata", "s4_odata", "sap_odata"):
        system = _read("sql-plan/v1-s4-odata/system.jinja2") or (
            "You are nanobase-s4-odata-plan-v1. Output valid JSON logical OData plan only."
        )
        user_tpl = _read("sql-plan/v1-s4-odata/user.jinja2") or (
            "{{ context_blocks }}\n\nQuestion: {{ question }}\n\n"
            "Return ONLY JSON. dialect must be odata."
        )
        return system, user_tpl
    if dialect_l in ("mssql", "tsql", "sqlserver"):
        system = _read("sql-plan/v1-mssql/system.jinja2") or (
            "You are nanobase-mssql-sql-plan-v1. Output valid JSON only. Single T-SQL SELECT; "
            "TOP N for row caps, never LIMIT; schema-qualify tables (dbo.TABLE)."
        )
        user_tpl = _read("sql-plan/v1-mssql/user.jinja2") or (
            "{{ context_blocks }}\n\nQuestion: {{ question }}\n\n"
            "Return ONLY JSON. dialect must be mssql."
        )
        return system, user_tpl
    if dialect_l in ("hana", "sap_hana"):
        system = _read("sql-plan/v1-hana/system.jinja2") or (
            "You are nanobase-hana-sql-plan-v1. Output valid JSON only. HANA SELECT only."
        )
        user_tpl = _read("sql-plan/v1-hana/user.jinja2") or (
            "{{ context_blocks }}\n\nQuestion: {{ question }}\n\n"
            "Return ONLY JSON. dialect must be hana."
        )
        return system, user_tpl
    system = _read("sql-plan/v1/system.jinja2") or (
        "You are nanobase-sql-plan-v1. Output valid JSON only. Never execute SQL. "
        "Never invent tables/columns. No SELECT *. No DML/DDL. Schema-qualified tables preferred."
    )
    user_tpl = _read("sql-plan/v1/user.jinja2") or (
        "{{ context_blocks }}\n\nQuestion: {{ question }}\n\n"
        "Return ONLY JSON: status, sql, dialect, tables, columns, functions, assumptions, "
        "warnings, ambiguities, clarificationQuestion, confidence."
    )
    return system, user_tpl


def sql_repair_prompts(*, dialect: str = "postgres") -> tuple[str, str]:
    dialect_l = (dialect or "postgres").lower().replace("postgresql", "postgres")
    if dialect_l == "oracle":
        system = _read("sql-repair/v1-oracle/system.jinja2") or (
            "You are nanobase-oracle-sql-repair-v1. Fix Oracle SQL. Output JSON only."
        )
        user_tpl = _read("sql-repair/v1-oracle/user.jinja2") or (
            "Question: {{ question }}\nPrevious SQL:\n{{ previous_sql }}\n"
            "Gateway error: {{ error_code }} — {{ error_message }}\n"
            "Attempt: {{ attempt }}\nAuthorized context:\n{{ context }}\n\n"
            "Return ONLY JSON plan with corrected Oracle sql. dialect must be oracle."
        )
        return system, user_tpl
    if dialect_l in ("odata", "s4_odata", "sap_odata"):
        system = _read("sql-repair/v1-s4-odata/system.jinja2") or (
            "You are nanobase-s4-odata-repair-v1. Fix OData plan. Output JSON only."
        )
        user_tpl = _read("sql-repair/v1-s4-odata/user.jinja2") or (
            "Question: {{ question }}\nPrevious plan:\n{{ previous_sql }}\n"
            "Gateway error: {{ error_code }} — {{ error_message }}\n"
            "Attempt: {{ attempt }}\nAuthorized context:\n{{ context }}\n\n"
            "Return ONLY JSON. dialect must be odata."
        )
        return system, user_tpl
    if dialect_l in ("mssql", "tsql", "sqlserver"):
        system = _read("sql-repair/v1-mssql/system.jinja2") or (
            "You are nanobase-mssql-sql-repair-v1. Fix T-SQL (TOP N, never LIMIT). Output JSON only."
        )
        user_tpl = _read("sql-repair/v1-mssql/user.jinja2") or (
            "Question: {{ question }}\nPrevious SQL:\n{{ previous_sql }}\n"
            "Gateway error: {{ error_code }} — {{ error_message }}\n"
            "Attempt: {{ attempt }}\nAuthorized context:\n{{ context }}\n\n"
            "Return ONLY JSON. dialect must be mssql."
        )
        return system, user_tpl
    if dialect_l in ("hana", "sap_hana"):
        system = _read("sql-repair/v1-hana/system.jinja2") or (
            "You are nanobase-hana-sql-repair-v1. Fix HANA SQL. Output JSON only."
        )
        user_tpl = _read("sql-repair/v1-hana/user.jinja2") or (
            "Question: {{ question }}\nPrevious SQL:\n{{ previous_sql }}\n"
            "Gateway error: {{ error_code }} — {{ error_message }}\n"
            "Attempt: {{ attempt }}\nAuthorized context:\n{{ context }}\n\n"
            "Return ONLY JSON. dialect must be hana."
        )
        return system, user_tpl
    system = _read("sql-repair/v1/system.jinja2") or (
        "You are nanobase-sql-repair-v1. Fix SQL for the given gateway error. "
        "Output valid JSON only. Do not expand authorization scope. Never execute SQL."
    )
    user_tpl = _read("sql-repair/v1/user.jinja2") or (
        "Question: {{ question }}\nPrevious SQL:\n{{ previous_sql }}\n"
        "Gateway error: {{ error_code }} — {{ error_message }}\n"
        "Attempt: {{ attempt }}\nAuthorized context:\n{{ context }}\n\n"
        "Return ONLY JSON plan (status PLANNED or AMBIGUOUS) with corrected sql."
    )
    return system, user_tpl


def result_explain_prompts(*, dialect: str = "postgres") -> tuple[str, str]:
    dialect_l = (dialect or "postgres").lower()
    if dialect_l in ("odata", "hana", "sap_hana", "s4_odata", "sap"):
        system = _read("result-explain/v1-sap/system.jinja2") or (
            "You are nanobase-sap-result-explain-v1. Explain ONLY the given SAP result in Turkish."
        )
        user_tpl = _read("result-explain/v1-sap/user.jinja2") or (
            "Question: {{ question }}\nPlan/SQL:\n{{ sql }}\nSummary:\n{{ summary }}\n"
            "Sample rows:\n{{ sample_rows }}\nTruncated: {{ truncated }}\n\n"
            "Return ONLY JSON with keys answer, insights, warnings."
        )
        return system, user_tpl
    system = _read("result-explain/v1/system.jinja2") or (
        "You are nanobase-result-explain-v1. Explain ONLY the given result in Turkish. "
        "Do not invent numbers. Do not reconstruct masked values. Output JSON: answer, insights, warnings."
    )
    user_tpl = _read("result-explain/v1/user.jinja2") or (
        "Question: {{ question }}\nSQL:\n{{ sql }}\nSummary:\n{{ summary }}\n"
        "Sample rows:\n{{ sample_rows }}\nTruncated: {{ truncated }}\n\n"
        "Return ONLY JSON with keys answer, insights, warnings."
    )
    return system, user_tpl
