"""SAP datasource configuration contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ODataDatasourceConfig:
    datasource_id: str
    base_url: str
    odata_version: str = "V4"
    deployment_type: str = "PRIVATE_EDITION"
    communication_scenario: str = ""
    credential_secret_ref: str = ""
    user: str = ""
    password: str = ""
    bearer_token: str | None = None
    verify_tls: bool = True
    allowed_services: list[str] = field(default_factory=list)
    allowed_entity_sets: list[str] = field(default_factory=list)
    source_status: str = "PUBLISHED"
    database_type: str = "SAP_S4HANA_ODATA"
    label: str = ""

    @classmethod
    def from_datasource(cls, ds: dict[str, Any]) -> ODataDatasourceConfig:
        entities = ds.get("allowed_entity_sets") or ds.get("allowed_entities") or []
        if isinstance(entities, set):
            entities = sorted(entities)
        services = ds.get("allowed_services") or ds.get("allowedServices") or []
        return cls(
            datasource_id=str(ds.get("id") or ""),
            base_url=str(ds.get("base_url") or ds.get("host") or "").rstrip("/"),
            odata_version=str(ds.get("odata_version") or ds.get("odataVersion") or "V4"),
            deployment_type=str(
                ds.get("deployment_type") or ds.get("deploymentType") or "PRIVATE_EDITION"
            ),
            communication_scenario=str(
                ds.get("communication_scenario") or ds.get("communicationScenario") or ""
            ),
            credential_secret_ref=str(
                ds.get("credential_secret_ref") or ds.get("credentialSecretRef") or ""
            ),
            user=str(ds.get("user") or ""),
            password=str(ds.get("password") or ""),
            bearer_token=ds.get("bearer_token"),
            verify_tls=bool(ds.get("verify_tls", True)),
            allowed_services=[str(s) for s in services],
            allowed_entity_sets=[str(e) for e in entities],
            source_status=str(ds.get("source_status") or ds.get("sourceStatus") or "PUBLISHED"),
            database_type=str(ds.get("database_type") or "SAP_S4HANA_ODATA"),
            label=str(ds.get("label") or ds.get("id") or ""),
        )


@dataclass
class HanaDatasourceConfig:
    datasource_id: str
    host: str
    port: int
    user: str
    password: str
    database_name: str = ""
    encrypt: bool = True
    validate_certificate: bool = True
    allowed_schemas: list[str] = field(default_factory=list)
    allowed_views: list[str] = field(default_factory=list)
    size_profile: str = "MEDIUM"
    workload_class: str = "NANOBASE_INTERACTIVE_QUERY"
    require_workload_class: bool = True
    deployment_type: str = "ON_PREMISE"
    database_type: str = "SAP_HANA"
    label: str = ""

    @classmethod
    def from_datasource(cls, ds: dict[str, Any]) -> HanaDatasourceConfig:
        schemas = ds.get("allowed_schemas") or ds.get("allowedSchemas") or []
        views = ds.get("allowed_views") or ds.get("allowedViews") or ds.get("allowed_tables") or []
        if isinstance(views, set):
            views = sorted(views)
        if isinstance(schemas, set):
            schemas = sorted(schemas)
        return cls(
            datasource_id=str(ds.get("id") or ""),
            host=str(ds.get("host") or ""),
            port=int(ds.get("port") or 30015),
            user=str(ds.get("user") or ""),
            password=str(ds.get("password") or ""),
            database_name=str(ds.get("database") or ds.get("databaseName") or ""),
            encrypt=bool(ds.get("encrypt", True)),
            validate_certificate=bool(
                ds.get("validate_certificate")
                if ds.get("validate_certificate") is not None
                else ds.get("ssl_validate", True)
            ),
            allowed_schemas=[str(s) for s in schemas],
            allowed_views=[str(v) for v in views],
            size_profile=str(ds.get("size_profile") or ds.get("sizeProfile") or "MEDIUM").upper(),
            workload_class=str(
                ds.get("workload_class") or ds.get("workloadClass") or "NANOBASE_INTERACTIVE_QUERY"
            ),
            require_workload_class=bool(
                ds.get("require_workload_class")
                if ds.get("require_workload_class") is not None
                else True
            ),
            deployment_type=str(
                ds.get("deployment_type") or ds.get("deploymentType") or "ON_PREMISE"
            ),
            database_type=str(ds.get("database_type") or "SAP_HANA"),
            label=str(ds.get("label") or ds.get("id") or ""),
        )
