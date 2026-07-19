"""Shadow performance validation: EXPLAIN/timeout on read-replica only; discard results."""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Optional

ExecuteFn = Callable[[str, Optional[dict[str, object]]], list[dict[str, Any]]]


def shadow_perf_enabled() -> bool:
    return os.environ.get("SCENARIO_SHADOW_PERF", "").lower() in ("1", "true", "yes")


def run_shadow_explain(
    execute_fn: ExecuteFn,
    sql_template: str,
    params: dict[str, object],
    *,
    timeout_ms: int = 5000,
) -> dict[str, Any]:
    """
    Run EXPLAIN (or lightweight probe) against reporting clone.
    Never publishes; results are discarded after metrics.
    """
    if not shadow_perf_enabled():
        return {"skipped": True}
    t0 = time.perf_counter()
    try:
        from nanobase_api.scenario_engine.infrastructure.compiler import render_sql

        # Prefer EXPLAIN without executing the plan against production traffic
        explain_sql = f"EXPLAIN {render_sql(sql_template, params)}"
        _ = execute_fn(explain_sql, None)
        elapsed = (time.perf_counter() - t0) * 1000
        return {
            "ok": True,
            "elapsedMs": elapsed,
            "timeoutMs": timeout_ms,
            "withinBudget": elapsed <= timeout_ms,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "discarded": True}
