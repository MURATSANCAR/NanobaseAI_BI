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


def hana_enabled() -> bool:
    import os

    return os.environ.get("SCENARIO_HANA_ENABLED", "").lower() in ("1", "true", "yes")


def odata_enabled() -> bool:
    import os

    return os.environ.get("SCENARIO_ODATA_ENABLED", "").lower() in ("1", "true", "yes")


def expand_oracle_compiler(plan: LogicalPlan) -> CompileResult:
    """Oracle compiler (FETCH FIRST / NVL) when SCENARIO_ORACLE_ENABLED=1."""
    return OracleLogicalPlanCompiler().compile(plan)


def hana_compile(plan: LogicalPlan) -> CompileResult:
    return HanaLogicalPlanCompiler().compile(plan)


def odata_compile(plan: LogicalPlan) -> CompileResult:
    return ODataLogicalPlanCompiler().compile(plan)


# Back-compat aliases
hana_compile_stub = hana_compile
odata_compile_stub = odata_compile


def next_domain_after(current: str) -> str | None:
    try:
        idx = DOMAIN_ROLLOUT.index(current)
    except ValueError:
        return DOMAIN_ROLLOUT[0]
    if idx + 1 >= len(DOMAIN_ROLLOUT):
        return None
    return DOMAIN_ROLLOUT[idx + 1]
