"""Semantic versioning (MAJOR.MINOR.PATCH) + immutable publish manifest."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from nanobase_api.semantic_catalog.domain.errors import ValidationError
from nanobase_api.semantic_catalog.domain.status import AssetStatus, transition

ChangeKind = Literal["MAJOR", "MINOR", "PATCH"]


class VersionBump(str, Enum):
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    PATCH = "PATCH"


def parse_semver(version: str) -> tuple[int, int, int]:
    parts = (version or "").strip().split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValidationError(f"Geçersiz semantic version: {version}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def format_semver(major: int, minor: int, patch: int) -> str:
    return f"{major}.{minor}.{patch}"


def bump_version(current: str, kind: VersionBump | ChangeKind) -> str:
    major, minor, patch = parse_semver(current)
    k = VersionBump(kind) if not isinstance(kind, VersionBump) else kind
    if k == VersionBump.MAJOR:
        return format_semver(major + 1, 0, 0)
    if k == VersionBump.MINOR:
        return format_semver(major, minor + 1, 0)
    return format_semver(major, minor, patch + 1)


def classify_change(
    *,
    metric_meaning_changed: bool = False,
    calculation_changed: bool = False,
    mandatory_filter_changed: bool = False,
    currency_policy_changed: bool = False,
    join_meaning_changed: bool = False,
    asset_added: bool = False,
    synonym_added: bool = False,
    verified_query_added: bool = False,
    metadata_only: bool = False,
) -> VersionBump:
    if any(
        [
            metric_meaning_changed,
            calculation_changed,
            mandatory_filter_changed,
            currency_policy_changed,
            join_meaning_changed,
        ]
    ):
        return VersionBump.MAJOR
    if any([asset_added, synonym_added, verified_query_added]):
        return VersionBump.MINOR
    if metadata_only:
        return VersionBump.PATCH
    return VersionBump.PATCH


@dataclass
class ManifestAsset:
    type: str
    code: str
    version: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "code": self.code, "version": self.version, "sha256": self.sha256}


@dataclass
class SemanticVersion:
    id: str
    tenant_id: str
    datasource_id: str
    version: str
    schema_version: str
    assets: list[ManifestAsset] = field(default_factory=list)
    status: AssetStatus = AssetStatus.DRAFT
    published_by: str | None = None
    published_at: str | None = None
    manifest_sha256: str | None = None
    is_active: bool = False

    def transition_to(self, target: AssetStatus) -> None:
        self.status = transition(self.status, target)

    def build_manifest(self) -> dict[str, Any]:
        body = {
            "semanticVersion": self.version,
            "tenantId": self.tenant_id,
            "datasourceId": self.datasource_id,
            "schemaVersion": self.schema_version,
            "publishedAt": self.published_at,
            "publishedBy": self.published_by,
            "assets": [a.to_dict() for a in sorted(self.assets, key=lambda x: (x.type, x.code))],
        }
        raw = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        body["manifestSha256"] = digest
        self.manifest_sha256 = digest
        return body

    def seal(self) -> dict[str, Any]:
        """Immutable manifest — must not change after publish."""
        if self.status == AssetStatus.PUBLISHED and self.manifest_sha256:
            raise ValidationError("Published manifest immutable'dır.")
        return self.build_manifest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenantId": self.tenant_id,
            "datasourceId": self.datasource_id,
            "version": self.version,
            "schemaVersion": self.schema_version,
            "status": self.status.value,
            "isActive": self.is_active,
            "publishedBy": self.published_by,
            "publishedAt": self.published_at,
            "manifestSha256": self.manifest_sha256,
            "assets": [a.to_dict() for a in self.assets],
        }
