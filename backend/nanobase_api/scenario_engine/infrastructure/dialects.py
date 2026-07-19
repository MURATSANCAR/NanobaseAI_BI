"""Multi-dialect compiler registry — Postgres live; Oracle/HANA/OData Faz 4 stubs."""

from __future__ import annotations

from nanobase_api.scenario_engine.domain.errors import ValidationError
from nanobase_api.scenario_engine.domain.logical_plan import LogicalPlan
from nanobase_api.scenario_engine.infrastructure.compiler import (
    CompileResult,
    HanaLogicalPlanCompiler,
    ODataLogicalPlanCompiler,
    OracleLogicalPlanCompiler,
    PostgresLogicalPlanCompiler,
    get_compiler,
)

__all__ = [
    "CompileResult",
    "SUPPORTED_DIALECTS",
    "compile_for_dialect",
    "get_compiler",
]

SUPPORTED_DIALECTS = ("postgres", "oracle", "hana", "odata")

# Domains unlocked after invoice go/no-go (§38–39)
DOMAIN_ROLLOUT = (
    "invoice",
    "customer",
    "payment",
    "product",
    "order",
    "stock",
    "finance",
)


def compile_for_dialect(plan: LogicalPlan, dialect: str) -> CompileResult:
    """Compile or raise ValidationError if dialect not enabled for slice."""
    return get_compiler(dialect).compile(plan)


def oracle_enabled() -> bool:
    import os

    return os.environ.get("SCENARIO_ORACLE_ENABLED", "").lower() in ("1", "true", "yes")


def expand_oracle_compiler(plan: LogicalPlan) -> CompileResult:
    """Faz 4: map binds to Oracle style (:name remains; FETCH FIRST for limit)."""
    if not oracle_enabled():
        return OracleLogicalPlanCompiler().compile(plan)
    pg = PostgresLogicalPlanCompiler().compile(plan)
    sql = pg.sql_template
    # Rough translation for vertical expansion
    sql = sql.replace("LIMIT :fetch_limit", "FETCH FIRST :fetch_limit ROWS ONLY")
    sql = sql.replace("COALESCE(", "NVL(")
    sql = sql.replace("date_trunc('month',", "TRUNC(")
    fp = pg.ast_fingerprint  # re-fingerprint would be ideal; keep for now
    return CompileResult(
        sql_template=sql,
        dialect="oracle",
        ast_fingerprint=fp,
        bind_params=pg.bind_params,
        logical_plan=plan.to_dict(),
    )


def hana_compile_stub(plan: LogicalPlan) -> CompileResult:
    return HanaLogicalPlanCompiler().compile(plan)


def odata_compile_stub(plan: LogicalPlan) -> CompileResult:
    return ODataLogicalPlanCompiler().compile(plan)


def next_domain_after(current: str) -> str | None:
    try:
        idx = DOMAIN_ROLLOUT.index(current)
    except ValueError:
        return DOMAIN_ROLLOUT[0]
    if idx + 1 >= len(DOMAIN_ROLLOUT):
        return None
    return DOMAIN_ROLLOUT[idx + 1]
