"""Logical query plan — dialect-independent scenario definition."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from nanobase_api.scenario_engine.domain.errors import ValidationError
from nanobase_api.scenario_engine.domain.family import ScenarioFamily


@dataclass
class SortSpec:
    field: str
    direction: str = "DESC"

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "direction": self.direction.upper()}


@dataclass
class LogicalPlan:
    family: str
    entity: str
    date_role: str | None = None
    period: str | None = None
    metric: str | None = None
    aggregation: str | None = None
    dimension: str | None = None
    mandatory_filters: list[str] = field(default_factory=list)
    status_filter: str | None = None
    projection: list[str] = field(default_factory=list)
    sort: SortSpec | None = None
    limit: int = 100
    top_n: int | None = None
    join_path: list[str] = field(default_factory=list)
    aging_bucket: str | None = None
    comparison_period: str | None = None
    physical_table: str | None = None
    date_column: str | None = None
    metric_column: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        try:
            ScenarioFamily(self.family)
        except ValueError as e:
            raise ValidationError(f"Unknown scenario family: {self.family}") from e
        if self.limit < 1 or self.limit > 10_000:
            raise ValidationError("limit must be between 1 and 10000")
        if self.sort and self.sort.direction.upper() not in ("ASC", "DESC"):
            raise ValidationError("sort.direction must be ASC or DESC")

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "family": self.family,
            "entity": self.entity,
            "dateRole": self.date_role,
            "period": self.period,
            "metric": self.metric,
            "aggregation": self.aggregation,
            "dimension": self.dimension,
            "mandatoryFilters": list(self.mandatory_filters),
            "statusFilter": self.status_filter,
            "projection": list(self.projection),
            "sort": self.sort.to_dict() if self.sort else None,
            "limit": self.limit,
            "topN": self.top_n,
            "joinPath": list(self.join_path),
            "agingBucket": self.aging_bucket,
            "comparisonPeriod": self.comparison_period,
            "physicalTable": self.physical_table,
            "dateColumn": self.date_column,
            "metricColumn": self.metric_column,
        }
        if self.extra:
            d["extra"] = dict(self.extra)
        return {k: v for k, v in d.items() if v is not None and v != [] and v != {}}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> LogicalPlan:
        sort_raw = raw.get("sort")
        sort = None
        if isinstance(sort_raw, dict):
            sort = SortSpec(
                field=str(sort_raw.get("field") or "metric"),
                direction=str(sort_raw.get("direction") or "DESC"),
            )
        return cls(
            family=str(raw["family"]),
            entity=str(raw["entity"]),
            date_role=raw.get("dateRole") or raw.get("date_role"),
            period=raw.get("period"),
            metric=raw.get("metric"),
            aggregation=raw.get("aggregation"),
            dimension=raw.get("dimension"),
            mandatory_filters=list(raw.get("mandatoryFilters") or raw.get("mandatory_filters") or []),
            status_filter=raw.get("statusFilter") or raw.get("status_filter"),
            projection=list(raw.get("projection") or []),
            sort=sort,
            limit=int(raw.get("limit") or 100),
            top_n=raw.get("topN") if raw.get("topN") is not None else raw.get("top_n"),
            join_path=list(raw.get("joinPath") or raw.get("join_path") or []),
            aging_bucket=raw.get("agingBucket") or raw.get("aging_bucket"),
            comparison_period=raw.get("comparisonPeriod") or raw.get("comparison_period"),
            physical_table=raw.get("physicalTable") or raw.get("physical_table"),
            date_column=raw.get("dateColumn") or raw.get("date_column"),
            metric_column=raw.get("metricColumn") or raw.get("metric_column"),
            extra=dict(raw.get("extra") or {}),
        )

    def fingerprint(self) -> str:
        raw = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
