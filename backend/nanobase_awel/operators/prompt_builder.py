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


def sql_plan_prompts() -> tuple[str, str]:
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


def sql_repair_prompts() -> tuple[str, str]:
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


def result_explain_prompts() -> tuple[str, str]:
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
