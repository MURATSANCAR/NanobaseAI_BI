"""Semantically valid combination planner — no blind Cartesian product."""

from __future__ import annotations

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

# Vertical-slice period set
_PERIODS = [
    PeriodKind.TODAY,
    PeriodKind.YESTERDAY,
    PeriodKind.CURRENT_WEEK,
    PeriodKind.PREVIOUS_WEEK,
    PeriodKind.CURRENT_MONTH,
    PeriodKind.PREVIOUS_MONTH,
    PeriodKind.CURRENT_YEAR,
    PeriodKind.PREVIOUS_YEAR,
]

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


def plan_invoice_combinations(
    classification: ClassificationResult,
    graph: RelationshipGraph,
) -> list[PlannedScenario]:
    """Generate pruned invoice-domain combinations for the vertical slice."""
    entities = classification.entity_map()
    invoice = entities.get("invoice")
    if invoice is None or not invoice.scenario_eligible:
        return []
    if not invoice.business_date:
        # Ambiguous business date → only explicit date-role questions (handled below)
        pass

    out: list[PlannedScenario] = []
    table = invoice.fqn
    biz_date = invoice.dates.get("businessDate")
    due_date = invoice.dates.get("dueDate")
    projection = _default_projection(invoice)
    amounts = measure_columns(invoice)
    primary_amount = next((c for c in amounts if c.name == "gross_amount"), amounts[0] if amounts else None)
    remaining = next((c for c in amounts if c.name == "remaining_amount"), None)

    # LIST by period (Tier A) — requires business date
    if biz_date:
        for period in _PERIODS:
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
            out.append(
                PlannedScenario(
                    scenario_code=_id_suffix("invoice", "list", period.value.lower()),
                    family=ScenarioFamily.LIST_ENTITY,
                    logical_plan=plan,
                    risk_tier=RiskTier.A,
                )
            )

    # COUNT by period
    if biz_date:
        for period in (PeriodKind.TODAY, PeriodKind.PREVIOUS_MONTH, PeriodKind.CURRENT_MONTH):
            plan = LogicalPlan(
                family=ScenarioFamily.COUNT_ENTITY.value,
                entity="invoice",
                date_role="BUSINESS_DATE",
                period=period.value,
                mandatory_filters=[_EXCLUDE_CANCELLED],
                physical_table=table,
                date_column=biz_date,
                limit=1,
            )
            out.append(
                PlannedScenario(
                    scenario_code=_id_suffix("invoice", "count", period.value.lower()),
                    family=ScenarioFamily.COUNT_ENTITY,
                    logical_plan=plan,
                    risk_tier=RiskTier.A,
                )
            )

    # SUM by period
    if biz_date and primary_amount:
        for period in (PeriodKind.TODAY, PeriodKind.PREVIOUS_MONTH, PeriodKind.CURRENT_MONTH, PeriodKind.CURRENT_YEAR):
            plan = LogicalPlan(
                family=ScenarioFamily.SUM_MEASURE.value,
                entity="invoice",
                date_role="BUSINESS_DATE",
                period=period.value,
                metric="invoice_gross_amount",
                aggregation="SUM",
                metric_column=primary_amount.fqn,
                mandatory_filters=[_EXCLUDE_CANCELLED],
                physical_table=table,
                date_column=biz_date,
                limit=1,
            )
            out.append(
                PlannedScenario(
                    scenario_code=_id_suffix("invoice", "sum", period.value.lower()),
                    family=ScenarioFamily.SUM_MEASURE,
                    logical_plan=plan,
                    risk_tier=RiskTier.A,
                )
            )

    # Unpaid list
    if remaining:
        plan = LogicalPlan(
            family=ScenarioFamily.STATUS_FILTER.value,
            entity="invoice",
            status_filter="unpaid",
            mandatory_filters=[_EXCLUDE_CANCELLED],
            projection=projection,
            sort=SortSpec(field="invoice_date", direction="DESC"),
            physical_table=table,
            metric_column=remaining.fqn,
            date_column=biz_date,
            extra={"unpaid_predicate": "remaining_amount > 0"},
        )
        out.append(
            PlannedScenario(
                scenario_code="invoice.list.unpaid",
                family=ScenarioFamily.STATUS_FILTER,
                logical_plan=plan,
                risk_tier=RiskTier.A,
            )
        )

    # Cancelled
    plan = LogicalPlan(
        family=ScenarioFamily.STATUS_FILTER.value,
        entity="invoice",
        status_filter="cancelled",
        projection=projection,
        sort=SortSpec(field="invoice_date", direction="DESC"),
        physical_table=table,
        date_column=biz_date,
    )
    out.append(
        PlannedScenario(
            scenario_code="invoice.list.cancelled",
            family=ScenarioFamily.STATUS_FILTER,
            logical_plan=plan,
            risk_tier=RiskTier.A,
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
        out.append(
            PlannedScenario(
                scenario_code="invoice.list.overdue",
                family=ScenarioFamily.AGING,
                logical_plan=plan,
                risk_tier=RiskTier.B,
            )
        )

    # TOP N
    if primary_amount:
        for n in (10, 20):
            plan = LogicalPlan(
                family=ScenarioFamily.TOP_N.value,
                entity="invoice",
                metric="gross_amount",
                metric_column=primary_amount.fqn,
                top_n=n,
                limit=n,
                mandatory_filters=[_EXCLUDE_CANCELLED],
                projection=projection,
                sort=SortSpec(field="gross_amount", direction="DESC"),
                physical_table=table,
                date_column=biz_date,
            )
            out.append(
                PlannedScenario(
                    scenario_code=_id_suffix("invoice", "top", str(n)),
                    family=ScenarioFamily.TOP_N,
                    logical_plan=plan,
                    risk_tier=RiskTier.A,
                )
            )

    # GROUP by city (Tier B) — needs approved join path
    addr = entities.get("customer_address")
    if addr and primary_amount and biz_date:
        path = graph.path(table, addr.fqn)
        if path is not None:
            plan = LogicalPlan(
                family=ScenarioFamily.GROUP_MEASURE.value,
                entity="invoice",
                metric="gross_amount",
                aggregation="SUM",
                metric_column=primary_amount.fqn,
                dimension="customer_city",
                period=PeriodKind.PREVIOUS_MONTH.value,
                date_role="BUSINESS_DATE",
                mandatory_filters=[_EXCLUDE_CANCELLED],
                join_path=[e.from_table + "->" + e.to_table for e in path],
                physical_table=table,
                date_column=biz_date,
                sort=SortSpec(field="metric", direction="DESC"),
                extra={"dimension_column": "analytics.customer_addresses.city", "join_edges": [
                    {"from": e.from_table, "to": e.to_table, "from_col": e.from_column, "to_col": e.to_column}
                    for e in path
                ]},
            )
            out.append(
                PlannedScenario(
                    scenario_code="invoice.sum.by_city.previous_month",
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
            plan = LogicalPlan(
                family=ScenarioFamily.LIST_ENTITY.value,
                entity="invoice",
                period=PeriodKind.CURRENT_MONTH.value,
                date_role="BUSINESS_DATE",
                mandatory_filters=[_EXCLUDE_CANCELLED],
                projection=projection + ["customer_name"],
                join_path=[e.from_table + "->" + e.to_table for e in path],
                physical_table=table,
                date_column=biz_date,
                sort=SortSpec(field="invoice_date", direction="DESC"),
                extra={"join_edges": [
                    {"from": e.from_table, "to": e.to_table, "from_col": e.from_column, "to_col": e.to_column}
                    for e in path
                ]},
            )
            out.append(
                PlannedScenario(
                    scenario_code="invoice.list.by_customer.current_month",
                    family=ScenarioFamily.LIST_ENTITY,
                    logical_plan=plan,
                    risk_tier=RiskTier.B,
                )
            )

    # Monthly trend (Tier B)
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
        out.append(
            PlannedScenario(
                scenario_code="invoice.trend.monthly",
                family=ScenarioFamily.TIME_TREND,
                logical_plan=plan,
                risk_tier=RiskTier.B,
            )
        )

    # Period compare (Tier B)
    if biz_date and primary_amount:
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
        out.append(
            PlannedScenario(
                scenario_code="invoice.compare.current_vs_previous_month",
                family=ScenarioFamily.COMPARE_PERIOD,
                logical_plan=plan,
                risk_tier=RiskTier.B,
            )
        )

    # Explicit date-role questions when createdAt missing — still emit due_date TODAY
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
        out.append(
            PlannedScenario(
                scenario_code="invoice.list.due_today",
                family=ScenarioFamily.LIST_ENTITY,
                logical_plan=plan,
                risk_tier=RiskTier.A,
            )
        )

    return out


def new_scenario_id() -> str:
    return f"scn-{uuid.uuid4().hex[:16]}"
