"""Nanobase controlled text2sql workflows (no customer DB execute)."""

WORKFLOW_VERSION = "1"
PLAN_WORKFLOW = "nanobase-sql-plan-v1"
REPAIR_WORKFLOW = "nanobase-sql-repair-v1"
EXPLAIN_WORKFLOW = "nanobase-result-explain-v1"

__all__ = [
    "WORKFLOW_VERSION",
    "PLAN_WORKFLOW",
    "REPAIR_WORKFLOW",
    "EXPLAIN_WORKFLOW",
]
