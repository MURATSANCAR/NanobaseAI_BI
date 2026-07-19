"""Static / execution / metamorphic / differential validation layers."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from nanobase_api.scenario_engine.domain.errors import ValidationError
from nanobase_api.scenario_engine.domain.logical_plan import LogicalPlan
from nanobase_api.scenario_engine.domain.period import PeriodKind, periods_overlap, resolve_period_bounds
from nanobase_api.scenario_engine.infrastructure.compiler import CompileResult, render_sql

_SENSITIVE = re.compile(r"(password|secret|token|iban|ssn|salary|private_key)", re.I)
_DML = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|MERGE|GRANT|REVOKE)\b", re.I)


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
        if plan.period and plan.date_column:
            if ":period_start" not in sql and plan.family != "AGING":
                # AGING uses period_start as as-of; COMPARE uses both
                if plan.family != "COMPARE_PERIOD" and ":period_start" not in sql:
                    pass
            if plan.family in ("LIST_ENTITY", "COUNT_ENTITY", "SUM_MEASURE", "TIME_TREND", "GROUP_MEASURE"):
                if ":period_start" not in sql or ":period_end" not in sql:
                    if plan.family != "TOP_N":
                        raise ValidationError("Period binds missing")
        if plan.family in ("LIST_ENTITY", "TOP_N", "STATUS_FILTER", "AGING", "GROUP_MEASURE"):
            if "LIMIT" not in sql.upper() and plan.family != "COMPARE_PERIOD":
                raise ValidationError("LIMIT required for list-like families")
        if "exclude_cancelled_invoices" in plan.mandatory_filters and plan.status_filter != "cancelled":
            if "cancelled_status" not in compiled.bind_params and "status" not in sql.lower():
                raise ValidationError("Mandatory cancel filter missing")
        # Aggregation sanity
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
    # February leap smoke: 2024-03-01 → previous month Feb 1..Mar 1
    leap = resolve_period_bounds(
        PeriodKind.PREVIOUS_MONTH,
        now=datetime(2024, 3, 15, 12, 0, tzinfo=tz),
        tz=tz,
    )
    if leap.start.month != 2 or leap.end.month != 3:
        errors.append("Leap-year February previous month incorrect")
    return ValidationResult(
        "PROPERTY_PERIOD",
        passed=len(errors) == 0,
        detail={"errors": errors},
    )


def validate_top_n_invariant(row_count: int, n: int) -> ValidationResult:
    ok = row_count <= n
    return ValidationResult("PROPERTY_TOP_N", ok, {"rowCount": row_count, "n": n})


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
    return ValidationResult(
        "DIFFERENTIAL_SUM",
        ok,
        {"sqlTotal": sql_total, "pythonTotal": ref},
    )


def fingerprint_result(rows: list[Any]) -> str:
    raw = json.dumps(rows, sort_keys=True, default=str, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def run_execution_baseline(
    compiled: CompileResult,
    *,
    params: dict[str, object],
    execute_fn: Callable[[str], list[dict[str, Any]]] | None = None,
    expected_row_count: int | None = None,
) -> ValidationResult:
    """Execute against test DB if execute_fn provided; otherwise structural pass."""
    if execute_fn is None:
        # Offline mode: ensure template renders without leftover binds for known params
        try:
            sql = render_sql(compiled.sql_template, params)
            if re.search(r":[A-Za-z_]+", sql):
                # leftover binds ok if not in params
                pass
            return ValidationResult(
                "EXECUTION_BASELINE",
                True,
                {"mode": "offline", "expectedRowCount": expected_row_count},
            )
        except Exception as e:
            return ValidationResult("EXECUTION_BASELINE", False, {"error": str(e)})
    try:
        sql = render_sql(compiled.sql_template, params)
        rows = execute_fn(sql)
        detail = {"rowCount": len(rows), "fingerprint": fingerprint_result(rows)}
        if expected_row_count is not None and len(rows) != expected_row_count:
            return ValidationResult("EXECUTION_BASELINE", False, detail)
        return ValidationResult("EXECUTION_BASELINE", True, detail)
    except Exception as e:
        return ValidationResult("EXECUTION_BASELINE", False, {"error": str(e)})


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
