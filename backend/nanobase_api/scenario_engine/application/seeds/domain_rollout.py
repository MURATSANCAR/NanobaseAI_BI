"""Post-invoice domain rollout order (Faz B).

Invoice go/no-go must pass before enabling these generators.
"""

from __future__ import annotations

import os

from nanobase_api.scenario_engine.domain.family import ScenarioFamily
from nanobase_api.scenario_engine.domain.logical_plan import LogicalPlan, SortSpec
from nanobase_api.scenario_engine.domain.period import PeriodKind
from nanobase_api.scenario_engine.domain.risk import RiskTier
from nanobase_api.scenario_engine.infrastructure.combination import PlannedScenario
from nanobase_api.scenario_engine.infrastructure.dialects import DOMAIN_ROLLOUT, next_domain_after
from nanobase_api.scenario_engine.infrastructure.relationship_graph import RelationshipGraph
from nanobase_api.scenario_engine.infrastructure.semantic_classifier import (
    ClassificationResult,
    measure_columns,
    projectable_columns,
)

# invoice always on; unlock via SCENARIO_ENABLED_DOMAINS=invoice,customer,...
_DEFAULT = frozenset({"invoice"})


def _enabled() -> frozenset[str]:
    raw = os.environ.get("SCENARIO_ENABLED_DOMAINS", "invoice")
    parts = {p.strip().lower() for p in raw.split(",") if p.strip()}
    return frozenset(parts) or _DEFAULT


ENABLED_DOMAINS: frozenset[str] = _DEFAULT  # mutated at import for tests via is_domain_enabled


def is_domain_enabled(domain: str) -> bool:
    return domain in _enabled()


def unlock_next_domain(current: str = "invoice") -> str | None:
    nxt = next_domain_after(current)
    return nxt


def rollout_plan() -> list[str]:
    return list(DOMAIN_ROLLOUT)


def _entity_table(classification: ClassificationResult, entity: str):
    return classification.entity_map().get(entity)


def _plan_list_count_sum(
    *,
    entity: str,
    table_fqn: str,
    biz_date: str | None,
    amount_col: str | None,
    category: str,
    risk: RiskTier = RiskTier.B,
    projection: list[str] | None = None,
) -> list[PlannedScenario]:
    out: list[PlannedScenario] = []
    periods = (
        PeriodKind.TODAY,
        PeriodKind.CURRENT_MONTH,
        PeriodKind.PREVIOUS_MONTH,
        PeriodKind.CURRENT_YEAR,
    )
    if not biz_date:
        return out
    proj = projection or [biz_date.split(".")[-1]]
    for period in periods:
        out.append(
            PlannedScenario(
                scenario_code=f"{entity}.list.{period.value.lower()}",
                family=ScenarioFamily.LIST_ENTITY,
                logical_plan=LogicalPlan(
                    family=ScenarioFamily.LIST_ENTITY.value,
                    entity=entity,
                    date_role="BUSINESS_DATE",
                    period=period.value,
                    projection=proj,
                    sort=SortSpec(field=biz_date.split(".")[-1], direction="DESC"),
                    limit=100,
                    physical_table=table_fqn,
                    date_column=biz_date,
                ),
                risk_tier=risk,
                category=category,
            )
        )
        out.append(
            PlannedScenario(
                scenario_code=f"{entity}.count.{period.value.lower()}",
                family=ScenarioFamily.COUNT_ENTITY,
                logical_plan=LogicalPlan(
                    family=ScenarioFamily.COUNT_ENTITY.value,
                    entity=entity,
                    date_role="BUSINESS_DATE",
                    period=period.value,
                    physical_table=table_fqn,
                    date_column=biz_date,
                    limit=1,
                ),
                risk_tier=risk,
                category=category,
            )
        )
        if amount_col:
            out.append(
                PlannedScenario(
                    scenario_code=f"{entity}.sum.{period.value.lower()}",
                    family=ScenarioFamily.SUM_MEASURE,
                    logical_plan=LogicalPlan(
                        family=ScenarioFamily.SUM_MEASURE.value,
                        entity=entity,
                        date_role="BUSINESS_DATE",
                        period=period.value,
                        aggregation="SUM",
                        metric_column=amount_col,
                        physical_table=table_fqn,
                        date_column=biz_date,
                        limit=1,
                    ),
                    risk_tier=risk,
                    category=category,
                )
            )
    return out


def plan_unlocked_domain_combinations(
    classification: ClassificationResult,
    graph: RelationshipGraph,
) -> list[PlannedScenario]:
    """Generate scenarios for unlocked domains after invoice (customer→finance)."""
    _ = graph
    out: list[PlannedScenario] = []
    enabled = _enabled()

    # customer
    if "customer" in enabled:
        cust = _entity_table(classification, "customer")
        if cust and cust.scenario_eligible:
            biz = cust.dates.get("businessDate") or cust.dates.get("createdAt")
            proj = [c.name for c in projectable_columns(cust)[:6]]
            out.extend(
                _plan_list_count_sum(
                    entity="customer",
                    table_fqn=cust.fqn,
                    biz_date=biz,
                    amount_col=None,
                    category="Müşteriler",
                    risk=RiskTier.B,
                    projection=proj or None,
                )
            )

    # payment
    if "payment" in enabled:
        pay = _entity_table(classification, "payment")
        if pay and pay.scenario_eligible:
            biz = pay.dates.get("businessDate")
            measures = measure_columns(pay)
            amt = measures[0].fqn if measures else None
            proj = [c.name for c in projectable_columns(pay)[:6]]
            out.extend(
                _plan_list_count_sum(
                    entity="payment",
                    table_fqn=pay.fqn,
                    biz_date=biz,
                    amount_col=amt,
                    category="Ödemeler",
                    risk=RiskTier.B,
                    projection=proj or None,
                )
            )

    # product / order / stock — smoke generators
    for entity, category in (
        ("product", "Ürünler"),
        ("order", "Siparişler"),
        ("stock", "Stok"),
    ):
        if entity not in enabled:
            continue
        ent = _entity_table(classification, entity)
        if ent is None or not ent.scenario_eligible:
            continue
        biz = ent.dates.get("businessDate") or ent.dates.get("createdAt")
        proj = [c.name for c in projectable_columns(ent)[:6]]
        out.extend(
            _plan_list_count_sum(
                entity=entity,
                table_fqn=ent.fqn,
                biz_date=biz,
                amount_col=None,
                category=category,
                risk=RiskTier.B,
                projection=proj or None,
            )
        )

    # finance — Tier C (review zorunlu, asla auto-publish)
    if "finance" in enabled:
        fin = _entity_table(classification, "finance") or _entity_table(classification, "ledger")
        if fin and fin.scenario_eligible:
            biz = fin.dates.get("businessDate") or fin.dates.get("createdAt")
            proj = [c.name for c in projectable_columns(fin)[:6]]
            out.extend(
                _plan_list_count_sum(
                    entity="finance",
                    table_fqn=fin.fqn,
                    biz_date=biz,
                    amount_col=None,
                    category="Finans",
                    risk=RiskTier.C,
                    projection=proj or None,
                )
            )
            # Ratio / ledger style — force Tier C
            if biz:
                out.append(
                    PlannedScenario(
                        scenario_code="finance.ratio.current_month",
                        family=ScenarioFamily.SUM_MEASURE,
                        logical_plan=LogicalPlan(
                            family=ScenarioFamily.SUM_MEASURE.value,
                            entity="finance",
                            date_role="BUSINESS_DATE",
                            period=PeriodKind.CURRENT_MONTH.value,
                            aggregation="SUM",
                            physical_table=fin.fqn,
                            date_column=biz,
                            limit=1,
                            extra={"ledger_ratio": True},
                        ),
                        risk_tier=RiskTier.C,
                        category="Finans",
                    )
                )

    return out
