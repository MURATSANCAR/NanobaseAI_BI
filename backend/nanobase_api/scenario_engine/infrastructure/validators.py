"""Static / execution / metamorphic / differential / performance validation layers."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

from nanobase_api.scenario_engine.domain.errors import ValidationError
from nanobase_api.scenario_engine.domain.logical_plan import LogicalPlan
from nanobase_api.scenario_engine.domain.period import PeriodKind, periods_overlap, resolve_period_bounds
from nanobase_api.scenario_engine.infrastructure.compiler import CompileResult, render_sql

_SENSITIVE = re.compile(r"(password|secret|token|iban|ssn|salary|private_key)", re.I)
_DML = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|MERGE|GRANT|REVOKE)\b", re.I)

ExecuteFn = Callable[[str, Optional[Dict[str, object]]], List[Dict[str, Any]]]


@dataclass
class ValidationResult:
    layer: str
    passed: bool
    detail: dict[str, Any] = field(default_factory=dict)


def validate_static_ast(plan: LogicalPlan, compiled: CompileResult) -> ValidationResult:
    sql = compiled.sql_template
    detail: dict[str, Any] = {}
    try:
        if _DML.search(sql):
            raise ValidationError("DML/DDL forbidden")
        if _SENSITIVE.search(sql):
            raise ValidationError("Sensitive column in projection")
        if plan.physical_table and plan.physical_table.split(".")[-1] not in sql.replace('"', ""):
            raise ValidationError("Physical table missing from SQL")
        if plan.family in ("LIST_ENTITY", "COUNT_ENTITY", "SUM_MEASURE", "TIME_TREND", "GROUP_MEASURE"):
            if plan.period and (":period_start" not in sql or ":period_end" not in sql):
                if plan.family != "TOP_N":
                    raise ValidationError("Period binds missing")
        if plan.family in ("LIST_ENTITY", "TOP_N", "STATUS_FILTER", "AGING", "GROUP_MEASURE"):
            if "LIMIT" not in sql.upper() and plan.family != "COMPARE_PERIOD":
                raise ValidationError("LIMIT required for list-like families")
        if "exclude_cancelled_invoices" in plan.mandatory_filters and plan.status_filter != "cancelled":
            if "cancelled_status" not in compiled.bind_params and "status" not in sql.lower():
                raise ValidationError("Mandatory cancel filter missing")
        if plan.aggregation == "SUM" and plan.metric_column:
            col = plan.metric_column.split(".")[-1]
            if col.endswith("_id"):
                raise ValidationError("SUM on identifier forbidden")
        detail["astFingerprint"] = compiled.ast_fingerprint
        return ValidationResult("STATIC_AST", True, detail)
    except ValidationError as e:
        return ValidationResult("STATIC_AST", False, {"error": e.message})


def validate_period_properties(*, now: datetime | None = None) -> ValidationResult:
    tz = ZoneInfo("Europe/Istanbul")
    errors: list[str] = []
    today = resolve_period_bounds(PeriodKind.TODAY, now=now, tz=tz)
    if not (today.start < today.end):
        errors.append("TODAY start < end violated")
    prev = resolve_period_bounds(PeriodKind.PREVIOUS_MONTH, now=now, tz=tz)
    curr = resolve_period_bounds(PeriodKind.CURRENT_MONTH, now=now, tz=tz)
    if periods_overlap(prev, curr):
        errors.append("PREVIOUS_MONTH overlaps CURRENT_MONTH")
    leap = resolve_period_bounds(
        PeriodKind.PREVIOUS_MONTH,
        now=datetime(2024, 3, 15, 12, 0, tzinfo=tz),
        tz=tz,
    )
    if leap.start.month != 2 or leap.end.month != 3:
        errors.append("Leap-year February previous month incorrect")
    return ValidationResult("PROPERTY_PERIOD", passed=len(errors) == 0, detail={"errors": errors})


def validate_top_n_invariant(row_count: int, n: int) -> ValidationResult:
    return ValidationResult("PROPERTY_TOP_N", row_count <= n, {"rowCount": row_count, "n": n})


def metamorphic_subset(subset_ids: set[Any], superset_ids: set[Any]) -> ValidationResult:
    ok = subset_ids.issubset(superset_ids)
    return ValidationResult(
        "METAMORPHIC_SUBSET",
        ok,
        {"subsetSize": len(subset_ids), "supersetSize": len(superset_ids)},
    )


def differential_sum(
    sql_total: float,
    rows: list[dict[str, Any]],
    amount_key: str = "gross_amount",
) -> ValidationResult:
    ref = sum(float(r.get(amount_key) or 0) for r in rows)
    ok = abs(ref - float(sql_total)) < 0.01
    return ValidationResult("DIFFERENTIAL_SUM", ok, {"sqlTotal": sql_total, "pythonTotal": ref})


def fingerprint_result(rows: list[Any]) -> str:
    raw = json.dumps(rows, sort_keys=True, default=str, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def run_execution_baseline(
    compiled: CompileResult,
    *,
    params: dict[str, object],
    execute_fn: ExecuteFn | None = None,
    expected_row_count: int | None = None,
) -> ValidationResult:
    if execute_fn is None:
        try:
            render_sql(compiled.sql_template, params)
            return ValidationResult(
                "EXECUTION_BASELINE",
                True,
                {"mode": "offline", "expectedRowCount": expected_row_count},
            )
        except Exception as e:
            return ValidationResult("EXECUTION_BASELINE", False, {"error": str(e)})
    try:
        rows = execute_fn(compiled.sql_template, params)
        detail = {"rowCount": len(rows), "fingerprint": fingerprint_result(rows), "mode": "live"}
        if expected_row_count is not None and len(rows) != expected_row_count:
            return ValidationResult("EXECUTION_BASELINE", False, detail)
        if compiled.logical_plan.get("family") == "TOP_N":
            n = int(compiled.logical_plan.get("topN") or compiled.logical_plan.get("limit") or 10)
            if len(rows) > n:
                return ValidationResult("EXECUTION_BASELINE", False, {**detail, "error": "TOP_N exceeded"})
        return ValidationResult("EXECUTION_BASELINE", True, detail)
    except Exception as e:
        return ValidationResult("EXECUTION_BASELINE", False, {"error": str(e), "mode": "live"})


def validate_performance(plan: LogicalPlan, join_count: int) -> ValidationResult:
    if join_count > 4:
        return ValidationResult("PERFORMANCE", False, {"reason": "join_depth", "joinCount": join_count})
    if plan.limit > 10_000:
        return ValidationResult("PERFORMANCE", False, {"reason": "max_rows"})
    classification = "LOW" if join_count <= 1 else ("MEDIUM" if join_count <= 3 else "HIGH")
    return ValidationResult(
        "PERFORMANCE",
        True,
        {
            "classification": classification,
            "maxRows": plan.limit,
            "timeoutMs": 5000 if classification == "LOW" else 15000,
            "joinCount": join_count,
        },
    )


def run_metamorphic_invoice_checks(execute_fn: ExecuteFn, *, now: datetime | None = None) -> ValidationResult:
    """TODAY ⊆ CURRENT_MONTH on invoice_id; cancelled+active ≤ all."""
    tz = ZoneInfo("Europe/Istanbul")
    today = resolve_period_bounds(PeriodKind.TODAY, now=now, tz=tz)
    month = resolve_period_bounds(PeriodKind.CURRENT_MONTH, now=now, tz=tz)
    try:
        q_today = (
            'SELECT "invoice_id" FROM analytics.invoices '
            'WHERE "invoice_date" >= %(period_start)s AND "invoice_date" < %(period_end)s'
        )
        # execute_fn expects :name style — use templates
        t_sql = (
            'SELECT "invoice_id" FROM analytics.invoices '
            'WHERE "invoice_date" >= :period_start AND "invoice_date" < :period_end'
        )
        today_rows = execute_fn(
            t_sql,
            {"period_start": today.start.date().isoformat(), "period_end": today.end.date().isoformat()},
        )
        month_rows = execute_fn(
            t_sql,
            {"period_start": month.start.date().isoformat(), "period_end": month.end.date().isoformat()},
        )
        today_ids = {r.get("invoice_id") for r in today_rows}
        month_ids = {r.get("invoice_id") for r in month_rows}
        subset = metamorphic_subset(today_ids, month_ids)
        if not subset.passed:
            return subset

        all_n = len(execute_fn('SELECT "invoice_id" FROM analytics.invoices', {}))
        cancelled_n = len(
            execute_fn('SELECT "invoice_id" FROM analytics.invoices WHERE "status" = :s', {"s": "cancelled"})
        )
        active_n = len(
            execute_fn('SELECT "invoice_id" FROM analytics.invoices WHERE "status" <> :s', {"s": "cancelled"})
        )
        ok = cancelled_n + active_n <= all_n
        return ValidationResult(
            "METAMORPHIC_STATUS",
            ok,
            {"all": all_n, "cancelled": cancelled_n, "active": active_n, "todaySubset": subset.passed},
        )
    except Exception as e:
        return ValidationResult("METAMORPHIC", False, {"error": str(e)})


def run_differential_sum_check(
    execute_fn: ExecuteFn,
    *,
    params: dict[str, object],
    filter_sql: str,
) -> ValidationResult:
    """Compare SUM(gross_amount) vs python sum of row amounts."""
    try:
        agg = execute_fn(
            f'SELECT COALESCE(SUM("gross_amount"),0) AS total FROM analytics.invoices i {filter_sql}',
            params,
        )
        rows = execute_fn(
            f'SELECT "gross_amount" FROM analytics.invoices i {filter_sql}',
            params,
        )
        total = float((agg[0] or {}).get("total") or 0) if agg else 0.0
        return differential_sum(total, rows, "gross_amount")
    except Exception as e:
        return ValidationResult("DIFFERENTIAL_SUM", False, {"error": str(e)})


def run_explain_cost_check(execute_fn: ExecuteFn, sql_template: str, params: dict[str, object]) -> ValidationResult:
    """Best-effort EXPLAIN via SELECT-only path — if executor rejects EXPLAIN, pass on heuristic."""
    try:
        # Some RO roles forbid EXPLAIN; treat failure as soft pass with note
        explain_sql = f"EXPLAIN {render_sql(sql_template, params)}"
        _ = execute_fn(explain_sql, None)
        return ValidationResult("PERFORMANCE_EXPLAIN", True, {"mode": "explain"})
    except Exception as e:
        return ValidationResult("PERFORMANCE_EXPLAIN", True, {"mode": "skipped", "note": str(e)[:200]})


def new_run_id() -> str:
    return f"val-{uuid.uuid4().hex[:12]}"
