"""Business term entity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nanobase_api.semantic_catalog.domain.errors import ValidationError
from nanobase_api.semantic_catalog.domain.normalize import normalize_name, normalize_synonym
from nanobase_api.semantic_catalog.domain.status import AssetStatus, transition


@dataclass
class BusinessTerm:
    id: str
    tenant_id: str
    datasource_id: str
    name: str
    description: str
    synonyms: list[str] = field(default_factory=list)
    language: str = "tr"
    status: AssetStatus = AssetStatus.DRAFT
    version: int = 1
    created_by: str | None = None
    updated_by: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValidationError("Business term name zorunludur.")
        if isinstance(self.status, str):
            self.status = AssetStatus(self.status)

    @property
    def normalized_name(self) -> str:
        return normalize_name(self.name)

    @property
    def normalized_synonyms(self) -> list[str]:
        return [normalize_synonym(s) for s in self.synonyms if s and s.strip()]

    def transition_to(self, target: AssetStatus) -> None:
        self.status = transition(self.status, target)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenantId": self.tenant_id,
            "datasourceId": self.datasource_id,
            "name": self.name,
            "normalizedName": self.normalized_name,
            "description": self.description,
            "synonyms": list(self.synonyms),
            "language": self.language,
            "status": self.status.value,
            "version": self.version,
        }
