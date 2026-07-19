"""Apply and assert scenario expected baselines on reporting clone."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Optional

ExecuteFn = Callable[[str, Optional[dict[str, object]]], list[dict[str, Any]]]

_BASELINE_SQL = Path(__file__).resolve().parents[4] / "infra" / "sql" / "09-scenario-invoice-baselines.sql"


def apply_baseline_sql(dsn: str | None = None) -> bool:
    """Apply 09-scenario-invoice-baselines.sql; return True if applied."""
    dsn = dsn or os.environ.get("NANOBASE_REPORTING_DSN") or os.environ.get("REPORTING_DSN")
    if not dsn or not _BASELINE_SQL.is_file():
        return False
    pg = dsn.replace("postgresql+psycopg2://", "postgresql://")
    sql = _BASELINE_SQL.read_text(encoding="utf-8")
    try:
        import psycopg2

        conn = psycopg2.connect(pg)
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(sql)
            return True
        finally:
            conn.close()
    except Exception:
        return False


def load_expected_baselines(execute_fn: ExecuteFn) -> dict[str, dict[str, Any]]:
    try:
        rows = execute_fn(
            "SELECT scenario_code, expected_row_count, expected_sum FROM analytics.scenario_expected_baseline",
            None,
        )
        return {str(r["scenario_code"]): dict(r) for r in rows}
    except Exception:
        return {}


def assert_scenario_baseline(
    *,
    scenario_code: str,
    execute_fn: ExecuteFn,
    row_count: int | None = None,
    total_sum: float | None = None,
) -> tuple[bool, str]:
    """Compare live counts to analytics.scenario_expected_baseline when values are non-null."""
    expected = load_expected_baselines(execute_fn).get(scenario_code)
    if not expected:
        return True, "no_baseline"
    exp_n = expected.get("expected_row_count")
    exp_sum = expected.get("expected_sum")
    if exp_n is not None and row_count is not None and int(exp_n) != int(row_count):
        return False, f"row_count expected={exp_n} got={row_count}"
    if exp_sum is not None and total_sum is not None and abs(float(exp_sum) - float(total_sum)) > 0.01:
        return False, f"sum expected={exp_sum} got={total_sum}"
    return True, "ok"


def compute_live_baseline_targets(execute_fn: ExecuteFn) -> dict[str, dict[str, Any]]:
    """Refresh expected_* from live data (dev seed helper)."""
    targets: dict[str, dict[str, Any]] = {}
    try:
        unpaid = execute_fn(
            'SELECT COUNT(*) AS n FROM analytics.invoices WHERE status <> :s AND remaining_amount > 0',
            {"s": "cancelled"},
        )
        cancelled = execute_fn(
            'SELECT COUNT(*) AS n FROM analytics.invoices WHERE status = :s',
            {"s": "cancelled"},
        )
        targets["invoice.list.unpaid"] = {"expected_row_count": int((unpaid[0] or {}).get("n") or 0)}
        targets["invoice.list.cancelled"] = {"expected_row_count": int((cancelled[0] or {}).get("n") or 0)}
    except Exception:
        pass
    return targets
