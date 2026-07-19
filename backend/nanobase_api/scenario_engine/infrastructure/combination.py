"""Semantically valid combination planner — no blind Cartesian product."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

from nanobase_api.scenario_engine.domain.family import ScenarioFamily
from nanobase_api.scenario_engine.domain.logical_plan import LogicalPlan, SortSpec
from nanobase_api.scenario_engine.domain.period import PeriodKind
from nanobase_api.scenario_engine.domain.risk import RiskTier
from nanobase_api.scenario_engine.domain.roles import ColumnRole
from nanobase_api.scenario_engine.infrastructure.relationship_graph import RelationshipGraph
from nanobase_api.scenario_engine.infrastructure.semantic_classifier import (
    ClassificationResult,
    ClassifiedTable,
    measure_columns,
    projectable_columns,
)

# Expanded period set for scale target 500–2000 logical instances
_PERIODS = [
    PeriodKind.TODAY,
    PeriodKind.YESTERDAY,
    PeriodKind.CURRENT_WEEK,
    PeriodKind.PREVIOUS_WEEK,
    PeriodKind.CURRENT_MONTH,
    PeriodKind.PREVIOUS_MONTH,
    PeriodKind.CURRENT_QUARTER,
    PeriodKind.PREVIOUS_QUARTER,
    PeriodKind.CURRENT_YEAR,
    PeriodKind.PREVIOUS_YEAR,
    PeriodKind.MONTH_TO_DATE,
    PeriodKind.YEAR_TO_DATE,
]

_STATUS_FILTERS = ("unpaid", "cancelled", "open", "partial", "paid")
_TOP_N = (5, 10, 15, 20, 25, 50, 75, 100)
_LIST_LIMITS = (25, 50, 100, 150, 200)
_SORT_DIRS = ("DESC", "ASC")
_EXCLUDE_CANCELLED = "exclude_cancelled_invoices"


@dataclass
class PlannedScenario:
    scenario_code: str
    family: ScenarioFamily
    logical_plan: LogicalPlan
    risk_tier: RiskTier
    category: str = "Faturalar"


def _id_suffix(*parts: str) -> str:
    return ".".join(p.lower().replace(" ", "_") for p in parts if p)


def _default_projection(table: ClassifiedTable) -> list[str]:
    preferred = []
    for role in (
        ColumnRole.IDENTIFIER,
        ColumnRole.BUSINESS_IDENTIFIER,
        ColumnRole.BUSINESS_DATE,
        ColumnRole.AMOUNT,
        ColumnRole.CURRENCY,
        ColumnRole.STATUS,
    ):
        for c in projectable_columns(table):
            if c.role == role and c.name not in preferred:
                preferred.append(c.name)
    return preferred[:8] or [c.name for c in projectable_columns(table)[:6]]


def _scale_mode() -> str:
    """full (default) → 500–2000; slim → vertical-slice for fast unit tests."""
    return os.environ.get("SCENARIO_COMBINATION_SCALE", "full").lower()


def plan_invoice_combinations(
    classification: ClassificationResult,
    graph: RelationshipGraph,
) -> list[PlannedScenario]:
    """Generate pruned invoice-domain combinations (target 500–2000 in full mode)."""
    entities = classification.entity_map()
    invoice = entities.get("invoice")
    if invoice is None or not invoice.scenario_eligible:
        return []

    out: list[PlannedScenario] = []
    seen: set[str] = set()
    table = invoice.fqn
    biz_date = invoice.dates.get("businessDate")
    due_date = invoice.dates.get("dueDate")
    projection = _default_projection(invoice)
    amounts = measure_columns(invoice)
    if not amounts:
        amounts = []
    primary_amount = next((c for c in amounts if c.name == "gross_amount"), amounts[0] if amounts else None)
    remaining = next((c for c in amounts if c.name == "remaining_amount"), None)
    status_col = next((c for c in invoice.columns if c.role == ColumnRole.STATUS), None)

    periods = _PERIODS
    top_ns = _TOP_N
    limits = _LIST_LIMITS
    statuses = _STATUS_FILTERS
    sort_dirs = _SORT_DIRS
    if _scale_mode() == "slim":
        periods = [
            PeriodKind.TODAY,
            PeriodKind.PREVIOUS_MONTH,
            PeriodKind.CURRENT_MONTH,
            PeriodKind.CURRENT_YEAR,
        ]
        top_ns = (10, 20)
        limits = (100,)
        statuses = ("unpaid", "cancelled")
        sort_dirs = ("DESC",)

    def _add(p: PlannedScenario) -> None:
        if p.scenario_code in seen:
            return
        seen.add(p.scenario_code)
        out.append(p)

    # LIST by period × limit × sort (Tier A)
    if biz_date:
        for period in periods:
            for lim in limits:
                for direction in sort_dirs:
                    plan = LogicalPlan(
                        family=ScenarioFamily.LIST_ENTITY.value,
                        entity="invoice",
                        date_role="BUSINESS_DATE",
                        period=period.value,
                        mandatory_filters=[_EXCLUDE_CANCELLED],
                        projection=projection,
                        sort=SortSpec(field="invoice_date", direction=direction),
                        limit=lim,
                        physical_table=table,
                        date_column=biz_date,
                    )
                    _add(
                        PlannedScenario(
                            scenario_code=_id_suffix(
                                "invoice", "list", period.value.lower(), f"lim{lim}", direction.lower()
                            ),
                            family=ScenarioFamily.LIST_ENTITY,
                            logical_plan=plan,
                            risk_tier=RiskTier.A,
                        )
                    )
            # keep canonical short code for primary limit (compat with tests)
            plan = LogicalPlan(
                family=ScenarioFamily.LIST_ENTITY.value,
                entity="invoice",
                date_role="BUSINESS_DATE",
                period=period.value,
                mandatory_filters=[_EXCLUDE_CANCELLED],
                projection=projection,
                sort=SortSpec(field="invoice_date", direction="DESC"),
                limit=100,
                physical_table=table,
                date_column=biz_date,
            )
            _add(
                PlannedScenario(
                    scenario_code=_id_suffix("invoice", "list", period.value.lower()),
                    family=ScenarioFamily.LIST_ENTITY,
                    logical_plan=plan,
                    risk_tier=RiskTier.A,
                )
            )

    # COUNT by period (± cancel filter variants)
    if biz_date:
        for period in periods:
            for excl in (True, False):
                plan = LogicalPlan(
                    family=ScenarioFamily.COUNT_ENTITY.value,
                    entity="invoice",
                    date_role="BUSINESS_DATE",
                    period=period.value,
                    mandatory_filters=[_EXCLUDE_CANCELLED] if excl else [],
                    physical_table=table,
                    date_column=biz_date,
                    limit=1,
                )
                code = _id_suffix(
                    "invoice",
                    "count",
                    period.value.lower(),
                    "excl_cancel" if excl else "incl_cancel",
                )
                if excl:
                    # compat short code
                    _add(
                        PlannedScenario(
                            scenario_code=_id_suffix("invoice", "count", period.value.lower()),
                            family=ScenarioFamily.COUNT_ENTITY,
                            logical_plan=plan,
                            risk_tier=RiskTier.A,
                        )
                    )
                _add(
                    PlannedScenario(
                        scenario_code=code,
                        family=ScenarioFamily.COUNT_ENTITY,
                        logical_plan=plan,
                        risk_tier=RiskTier.A if excl else RiskTier.B,
                    )
                )

    # SUM by period × amount measure
    if biz_date:
        for amount in amounts or ([primary_amount] if primary_amount else []):
            if amount is None:
                continue
            for period in periods:
                plan = LogicalPlan(
                    family=ScenarioFamily.SUM_MEASURE.value,
                    entity="invoice",
                    date_role="BUSINESS_DATE",
                    period=period.value,
                    metric=f"invoice_{amount.name}",
                    aggregation="SUM",
                    metric_column=amount.fqn,
                    mandatory_filters=[_EXCLUDE_CANCELLED],
                    physical_table=table,
                    date_column=biz_date,
                    limit=1,
                )
                _add(
                    PlannedScenario(
                        scenario_code=_id_suffix("invoice", "sum", amount.name, period.value.lower()),
                        family=ScenarioFamily.SUM_MEASURE,
                        logical_plan=plan,
                        risk_tier=RiskTier.A,
                    )
                )
            # Compat short code for gross previous month
            if amount.name == "gross_amount":
                for period in (PeriodKind.TODAY, PeriodKind.PREVIOUS_MONTH, PeriodKind.CURRENT_MONTH, PeriodKind.CURRENT_YEAR):
                    plan = LogicalPlan(
                        family=ScenarioFamily.SUM_MEASURE.value,
                        entity="invoice",
                        date_role="BUSINESS_DATE",
                        period=period.value,
                        metric="invoice_gross_amount",
                        aggregation="SUM",
                        metric_column=amount.fqn,
                        mandatory_filters=[_EXCLUDE_CANCELLED],
                        physical_table=table,
                        date_column=biz_date,
                        limit=1,
                    )
                    _add(
                        PlannedScenario(
                            scenario_code=_id_suffix("invoice", "sum", period.value.lower()),
                            family=ScenarioFamily.SUM_MEASURE,
                            logical_plan=plan,
                            risk_tier=RiskTier.A,
                        )
                    )

    # Status × period LIST (pruned: status without cancel exclude when cancelled)
    if remaining or status_col:
        for st in statuses:
            plan = LogicalPlan(
                family=ScenarioFamily.STATUS_FILTER.value,
                entity="invoice",
                status_filter=st,
                mandatory_filters=[] if st == "cancelled" else [_EXCLUDE_CANCELLED],
                projection=projection,
                sort=SortSpec(field="invoice_date", direction="DESC"),
                physical_table=table,
                metric_column=(remaining.fqn if remaining and st == "unpaid" else None),
                date_column=biz_date,
                extra={"unpaid_predicate": "remaining_amount > 0"} if st == "unpaid" else {},
            )
            _add(
                PlannedScenario(
                    scenario_code=_id_suffix("invoice", "list", st),
                    family=ScenarioFamily.STATUS_FILTER,
                    logical_plan=plan,
                    risk_tier=RiskTier.A if st in ("unpaid", "cancelled") else RiskTier.B,
                )
            )
            if biz_date:
                for period in periods:
                    plan = LogicalPlan(
                        family=ScenarioFamily.STATUS_FILTER.value,
                        entity="invoice",
                        status_filter=st,
                        period=period.value,
                        date_role="BUSINESS_DATE",
                        mandatory_filters=[] if st == "cancelled" else [_EXCLUDE_CANCELLED],
                        projection=projection,
                        sort=SortSpec(field="invoice_date", direction="DESC"),
                        physical_table=table,
                        date_column=biz_date,
                        extra={"unpaid_predicate": "remaining_amount > 0"} if st == "unpaid" else {},
                    )
                    _add(
                        PlannedScenario(
                            scenario_code=_id_suffix("invoice", "list", st, period.value.lower()),
                            family=ScenarioFamily.STATUS_FILTER,
                            logical_plan=plan,
                            risk_tier=RiskTier.B,
                        )
                    )

    # Aging / overdue (Tier B)
    if due_date:
        plan = LogicalPlan(
            family=ScenarioFamily.AGING.value,
            entity="invoice",
            date_role="DUE_DATE",
            aging_bucket="OVERDUE",
            mandatory_filters=[_EXCLUDE_CANCELLED],
            projection=projection,
            sort=SortSpec(field="due_date", direction="ASC"),
            physical_table=table,
            date_column=due_date,
            extra={"unpaid_predicate": "remaining_amount > 0"},
        )
        _add(
            PlannedScenario(
                scenario_code="invoice.list.overdue",
                family=ScenarioFamily.AGING,
                logical_plan=plan,
                risk_tier=RiskTier.B,
            )
        )
        for period in (PeriodKind.CURRENT_MONTH, PeriodKind.PREVIOUS_MONTH, PeriodKind.CURRENT_YEAR):
            plan = LogicalPlan(
                family=ScenarioFamily.AGING.value,
                entity="invoice",
                date_role="DUE_DATE",
                aging_bucket="OVERDUE",
                period=period.value,
                mandatory_filters=[_EXCLUDE_CANCELLED],
                projection=projection,
                sort=SortSpec(field="due_date", direction="ASC"),
                physical_table=table,
                date_column=due_date,
                extra={"unpaid_predicate": "remaining_amount > 0"},
            )
            _add(
                PlannedScenario(
                    scenario_code=_id_suffix("invoice", "list", "overdue", period.value.lower()),
                    family=ScenarioFamily.AGING,
                    logical_plan=plan,
                    risk_tier=RiskTier.B,
                )
            )

    # TOP N × amount × period
    for amount in amounts or ([primary_amount] if primary_amount else []):
        if amount is None:
            continue
        for n in top_ns:
            plan = LogicalPlan(
                family=ScenarioFamily.TOP_N.value,
                entity="invoice",
                metric=amount.name,
                metric_column=amount.fqn,
                top_n=n,
                limit=n,
                mandatory_filters=[_EXCLUDE_CANCELLED],
                projection=projection,
                sort=SortSpec(field=amount.name, direction="DESC"),
                physical_table=table,
                date_column=biz_date,
            )
            _add(
                PlannedScenario(
                    scenario_code=_id_suffix("invoice", "top", amount.name, str(n)),
                    family=ScenarioFamily.TOP_N,
                    logical_plan=plan,
                    risk_tier=RiskTier.A,
                )
            )
            # compat
            if amount.name == "gross_amount" and n in (10, 20):
                _add(
                    PlannedScenario(
                        scenario_code=_id_suffix("invoice", "top", str(n)),
                        family=ScenarioFamily.TOP_N,
                        logical_plan=plan,
                        risk_tier=RiskTier.A,
                    )
                )
            if biz_date:
                for period in periods:
                    plan = LogicalPlan(
                        family=ScenarioFamily.TOP_N.value,
                        entity="invoice",
                        metric=amount.name,
                        metric_column=amount.fqn,
                        top_n=n,
                        limit=n,
                        period=period.value,
                        date_role="BUSINESS_DATE",
                        mandatory_filters=[_EXCLUDE_CANCELLED],
                        projection=projection,
                        sort=SortSpec(field=amount.name, direction="DESC"),
                        physical_table=table,
                        date_column=biz_date,
                    )
                    _add(
                        PlannedScenario(
                            scenario_code=_id_suffix(
                                "invoice", "top", amount.name, str(n), period.value.lower()
                            ),
                            family=ScenarioFamily.TOP_N,
                            logical_plan=plan,
                            risk_tier=RiskTier.B,
                        )
                    )

    # GROUP by city / status (Tier B)
    addr = entities.get("customer_address")
    if addr and primary_amount and biz_date:
        path = graph.path(table, addr.fqn)
        if path is not None:
            for period in periods:
                plan = LogicalPlan(
                    family=ScenarioFamily.GROUP_MEASURE.value,
                    entity="invoice",
                    metric="gross_amount",
                    aggregation="SUM",
                    metric_column=primary_amount.fqn,
                    dimension="customer_city",
                    period=period.value,
                    date_role="BUSINESS_DATE",
                    mandatory_filters=[_EXCLUDE_CANCELLED],
                    join_path=[e.from_table + "->" + e.to_table for e in path],
                    physical_table=table,
                    date_column=biz_date,
                    sort=SortSpec(field="metric", direction="DESC"),
                    extra={
                        "dimension_column": "analytics.customer_addresses.city",
                        "join_edges": [
                            {
                                "from": e.from_table,
                                "to": e.to_table,
                                "from_col": e.from_column,
                                "to_col": e.to_column,
                            }
                            for e in path
                        ],
                    },
                )
                code = (
                    "invoice.sum.by_city.previous_month"
                    if period == PeriodKind.PREVIOUS_MONTH
                    else _id_suffix("invoice", "sum", "by_city", period.value.lower())
                )
                _add(
                    PlannedScenario(
                        scenario_code=code,
                        family=ScenarioFamily.GROUP_MEASURE,
                        logical_plan=plan,
                        risk_tier=RiskTier.B,
                    )
                )

    if primary_amount and biz_date and status_col:
        for period in periods:
            plan = LogicalPlan(
                family=ScenarioFamily.GROUP_MEASURE.value,
                entity="invoice",
                metric="gross_amount",
                aggregation="SUM",
                metric_column=primary_amount.fqn,
                dimension="status",
                period=period.value,
                date_role="BUSINESS_DATE",
                mandatory_filters=[_EXCLUDE_CANCELLED],
                physical_table=table,
                date_column=biz_date,
                sort=SortSpec(field="metric", direction="DESC"),
                extra={"dimension_column": f"{table}.status"},
            )
            _add(
                PlannedScenario(
                    scenario_code=_id_suffix("invoice", "sum", "by_status", period.value.lower()),
                    family=ScenarioFamily.GROUP_MEASURE,
                    logical_plan=plan,
                    risk_tier=RiskTier.B,
                )
            )

    # Customer join list (Tier B)
    customer = entities.get("customer")
    if customer and biz_date:
        path = graph.path(table, customer.fqn)
        if path is not None:
            for period in periods:
                plan = LogicalPlan(
                    family=ScenarioFamily.LIST_ENTITY.value,
                    entity="invoice",
                    period=period.value,
                    date_role="BUSINESS_DATE",
                    mandatory_filters=[_EXCLUDE_CANCELLED],
                    projection=projection + ["customer_name"],
                    join_path=[e.from_table + "->" + e.to_table for e in path],
                    physical_table=table,
                    date_column=biz_date,
                    sort=SortSpec(field="invoice_date", direction="DESC"),
                    extra={
                        "join_edges": [
                            {
                                "from": e.from_table,
                                "to": e.to_table,
                                "from_col": e.from_column,
                                "to_col": e.to_column,
                            }
                            for e in path
                        ]
                    },
                )
                code = (
                    "invoice.list.by_customer.current_month"
                    if period == PeriodKind.CURRENT_MONTH
                    else _id_suffix("invoice", "list", "by_customer", period.value.lower())
                )
                _add(
                    PlannedScenario(
                        scenario_code=code,
                        family=ScenarioFamily.LIST_ENTITY,
                        logical_plan=plan,
                        risk_tier=RiskTier.B,
                    )
                )

    # Monthly trend + compare
    if biz_date and primary_amount:
        plan = LogicalPlan(
            family=ScenarioFamily.TIME_TREND.value,
            entity="invoice",
            metric="gross_amount",
            aggregation="SUM",
            metric_column=primary_amount.fqn,
            dimension="month",
            date_role="BUSINESS_DATE",
            mandatory_filters=[_EXCLUDE_CANCELLED],
            physical_table=table,
            date_column=biz_date,
            period=PeriodKind.CURRENT_YEAR.value,
            sort=SortSpec(field="month", direction="ASC"),
            limit=24,
        )
        _add(
            PlannedScenario(
                scenario_code="invoice.trend.monthly",
                family=ScenarioFamily.TIME_TREND,
                logical_plan=plan,
                risk_tier=RiskTier.B,
            )
        )
        plan = LogicalPlan(
            family=ScenarioFamily.COMPARE_PERIOD.value,
            entity="invoice",
            metric="gross_amount",
            aggregation="SUM",
            metric_column=primary_amount.fqn,
            period=PeriodKind.CURRENT_MONTH.value,
            comparison_period=PeriodKind.PREVIOUS_MONTH.value,
            date_role="BUSINESS_DATE",
            mandatory_filters=[_EXCLUDE_CANCELLED],
            physical_table=table,
            date_column=biz_date,
            limit=2,
        )
        _add(
            PlannedScenario(
                scenario_code="invoice.compare.current_vs_previous_month",
                family=ScenarioFamily.COMPARE_PERIOD,
                logical_plan=plan,
                risk_tier=RiskTier.B,
            )
        )
        # Additional compares
        for a, b_period in (
            (PeriodKind.CURRENT_WEEK, PeriodKind.PREVIOUS_WEEK),
            (PeriodKind.CURRENT_QUARTER, PeriodKind.PREVIOUS_QUARTER),
            (PeriodKind.CURRENT_YEAR, PeriodKind.PREVIOUS_YEAR),
        ):
            plan = LogicalPlan(
                family=ScenarioFamily.COMPARE_PERIOD.value,
                entity="invoice",
                metric="gross_amount",
                aggregation="SUM",
                metric_column=primary_amount.fqn,
                period=a.value,
                comparison_period=b_period.value,
                date_role="BUSINESS_DATE",
                mandatory_filters=[_EXCLUDE_CANCELLED],
                physical_table=table,
                date_column=biz_date,
                limit=2,
            )
            _add(
                PlannedScenario(
                    scenario_code=_id_suffix(
                        "invoice", "compare", a.value.lower(), "vs", b_period.value.lower()
                    ),
                    family=ScenarioFamily.COMPARE_PERIOD,
                    logical_plan=plan,
                    risk_tier=RiskTier.B,
                )
            )

    # Due today
    if due_date:
        plan = LogicalPlan(
            family=ScenarioFamily.LIST_ENTITY.value,
            entity="invoice",
            date_role="DUE_DATE",
            period=PeriodKind.TODAY.value,
            mandatory_filters=[_EXCLUDE_CANCELLED],
            projection=projection,
            physical_table=table,
            date_column=due_date,
            sort=SortSpec(field="due_date", direction="ASC"),
        )
        _add(
            PlannedScenario(
                scenario_code="invoice.list.due_today",
                family=ScenarioFamily.LIST_ENTITY,
                logical_plan=plan,
                risk_tier=RiskTier.A,
            )
        )

    # Cap at 2000 — prune lowest-priority Tier B period×status first if needed
    max_n = int(os.environ.get("SCENARIO_MAX_COMBINATIONS", "2000"))
    if len(out) > max_n:
        tier_a = [p for p in out if p.risk_tier == RiskTier.A]
        tier_b = [p for p in out if p.risk_tier != RiskTier.A]
        keep_b = max_n - len(tier_a)
        out = tier_a + tier_b[: max(0, keep_b)]

    return out


def new_scenario_id() -> str:
    return f"scn-{uuid.uuid4().hex[:16]}"
