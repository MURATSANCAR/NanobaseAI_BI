"""Dimension + join rule entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from nanobase_api.semantic_catalog.domain.errors import ValidationError
from nanobase_api.semantic_catalog.domain.status import AssetStatus, transition

JoinType = Literal["INNER", "LEFT", "RIGHT", "FULL"]
Relationship = Literal["ONE_TO_ONE", "ONE_TO_MANY", "MANY_TO_ONE", "MANY_TO_MANY"]
Cardinality = Literal["LOW", "MEDIUM", "HIGH"]


@dataclass
class JoinCondition:
    left: str
    operator: str
    right: str

    def to_dict(self) -> dict[str, Any]:
        return {"left": self.left, "operator": self.operator, "right": self.right}


@dataclass
class JoinRule:
    id: str
    tenant_id: str
    datasource_id: str
    code: str
    from_table: str
    to_table: str
    join_type: JoinType
    conditions: list[JoinCondition]
    relationship: Relationship = "MANY_TO_ONE"
    status: AssetStatus = AssetStatus.DRAFT
    version: int = 1

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValidationError("Join rule code zorunludur.")
        if not self.conditions:
            raise ValidationError("Join rule en az bir condition gerektirir.")
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
            "fromTable": self.from_table,
            "toTable": self.to_table,
            "joinType": self.join_type,
            "conditions": [c.to_dict() for c in self.conditions],
            "relationship": self.relationship,
            "status": self.status.value,
            "version": self.version,
        }


@dataclass
class Dimension:
    id: str
    tenant_id: str
    datasource_id: str
    code: str
    name: str
    table: str
    column: str
    join_rule_code: str | None = None
    cardinality: Cardinality = "LOW"
    status: AssetStatus = AssetStatus.DRAFT
    version: int = 1

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValidationError("Dimension code zorunludur.")
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
            "name": self.name,
            "source": {"table": self.table, "column": self.column},
            "joinRuleCode": self.join_rule_code,
            "cardinality": self.cardinality,
            "status": self.status.value,
            "version": self.version,
        }
