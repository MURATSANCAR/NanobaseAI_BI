"""Typed, SQL-free operations evaluated after complete base aggregates."""
from dataclasses import dataclass

@dataclass(frozen=True)
class DerivedMetric:
    id: str
    op: str
    left: str
    right: str
    scale: float = 1.0

@dataclass(frozen=True)
class MetricPredicate:
    metric: str
    op: str
    value: str

@dataclass(frozen=True)
class PeriodComparison:
    op: str
    metric: str
    id: str
    base_period: int = 0
    target_period: int = 1
