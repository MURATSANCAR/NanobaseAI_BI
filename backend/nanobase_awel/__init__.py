"""Nanobase controlled text2sql workflows (no customer DB execute)."""

WORKFLOW_VERSION = "1"
PLAN_WORKFLOW = "nanobase-sql-plan-v1"
REPAIR_WORKFLOW = "nanobase-sql-repair-v1"
EXPLAIN_WORKFLOW = "nanobase-result-explain-v1"
ORACLE_PLAN_WORKFLOW = "nanobase-oracle-sql-plan-v1"
ORACLE_REPAIR_WORKFLOW = "nanobase-oracle-sql-repair-v1"

__all__ = [
    "WORKFLOW_VERSION",
    "PLAN_WORKFLOW",
    "REPAIR_WORKFLOW",
    "EXPLAIN_WORKFLOW",
    "ORACLE_PLAN_WORKFLOW",
    "ORACLE_REPAIR_WORKFLOW",
]
