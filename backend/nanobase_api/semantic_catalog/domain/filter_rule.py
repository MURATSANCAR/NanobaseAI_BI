"""Filter rule entity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nanobase_api.semantic_catalog.domain.errors import ValidationError
from nanobase_api.semantic_catalog.domain.status import AssetStatus, transition


@dataclass
class FilterExpression:
    field: str
    operator: str
    values: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"field": self.field, "operator": self.operator, "values": list(self.values)}


@dataclass
class FilterRule:
    id: str
    tenant_id: str
    datasource_id: str
    code: str
    description: str
    expression: FilterExpression
    mandatory: bool = False
    status: AssetStatus = AssetStatus.DRAFT
    version: int = 1

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValidationError("Filter rule code zorunludur.")
        if isinstance(self.status, str):
            self.status = AssetStatus(self.status)

    def transition_to(self, target: AssetStatus) -> None:
        self.status = transition(self.status, target)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenantId": self.tenant_id,
            "datasourceId": self.datasource_id,
            "code": self.code,
            "description": self.description,
            "expression": self.expression.to_dict(),
            "mandatory": self.mandatory,
            "status": self.status.value,
            "version": self.version,
        }
