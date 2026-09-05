from __future__ import annotations

from nanobase_awel.operators.prompt_builder import sql_plan_prompts, sql_repair_prompts
from nanobase_awel.workflows.sql_plan import DIALECT_CASE_INSENSITIVE_RULE, _DIALECT_STMT_RULE, normalize_dialect


def test_normalize_dialect_mssql_aliases():
    for d in ("mssql", "tsql", "sqlserver", "sql_server", "MSSQL"):
        assert normalize_dialect(d) == "mssql"
    assert normalize_dialect("postgresql") == "postgres"


def test_rules_present():
    assert "TOP N" in _DIALECT_STMT_RULE["mssql"]
    assert "UPPER" in DIALECT_CASE_INSENSITIVE_RULE["mssql"]


def test_prompts_select_mssql_templates():
    system, user = sql_plan_prompts(dialect="mssql")
    assert "nanobase-mssql-sql-plan-v1" in system
    assert "TOP" in system and "LIMIT" in system
    assert "dialect must be mssql" in user
    rs, ru = sql_repair_prompts(dialect="tsql")
    assert "nanobase-mssql-sql-repair-v1" in rs
    assert "dialect must be mssql" in ru
