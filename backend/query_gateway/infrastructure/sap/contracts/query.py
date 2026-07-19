"""SAP logical query plan contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


ALLOWED_FILTER_OPS = frozenset({"EQ", "NE", "GT", "GE", "LT", "LE", "IN", "STARTSWITH", "CONTAINS"})


@dataclass
class ODataFilter:
    field: str
    operator: str
    value: Any

    def normalized_op(self) -> str:
        return str(self.operator or "").upper()


@dataclass
class ODataLogicalPlan:
    source_type: str
    service: str
    entity_set: str
    select: list[str] = field(default_factory=list)
    filters: list[ODataFilter] = field(default_factory=list)
    orderby: list[str] = field(default_factory=list)
    top: int = 100
    expand: list[str] = field(default_factory=list)
    count: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ODataLogicalPlan:
        filters_raw = data.get("filters") or []
        filters = [
            ODataFilter(
                field=str(f.get("field") or ""),
                operator=str(f.get("operator") or "EQ"),
                value=f.get("value"),
            )
            for f in filters_raw
            if isinstance(f, dict)
        ]
        return cls(
            source_type=str(data.get("sourceType") or data.get("source_type") or "SAP_ODATA"),
            service=str(data.get("service") or ""),
            entity_set=str(data.get("entitySet") or data.get("entity_set") or ""),
            select=[str(s) for s in (data.get("select") or [])],
            filters=filters,
            orderby=[str(o) for o in (data.get("orderby") or data.get("orderBy") or [])],
            top=int(data.get("top") or 100),
            expand=[str(e) for e in (data.get("expand") or [])],
            count=bool(data.get("count") or False),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sourceType": self.source_type,
            "service": self.service,
            "entitySet": self.entity_set,
            "select": list(self.select),
            "filters": [
                {"field": f.field, "operator": f.operator, "value": f.value} for f in self.filters
            ],
            "orderby": list(self.orderby),
            "top": self.top,
            "expand": list(self.expand),
            "count": self.count,
        }
