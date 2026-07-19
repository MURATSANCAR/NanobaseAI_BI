"""Load RO datasource registry from secrets (no passwords in responses)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from query_gateway.config.settings import Settings, get_settings
from query_gateway.infrastructure.vault.secret_store import resolve_password
from query_gateway import sap as sap_mod

DEFAULT_ORACLE_SSB_TABLES = {
    "customer",
    "ssb.customer",
    "part",
    "ssb.part",
    "supplier",
    "ssb.supplier",
    "date_dim",
    "ssb.date_dim",
    "lineorder",
    "ssb.lineorder",
    "dwdate",
    "ssb.dwdate",
}

DEFAULT_ORACLE_REPORTING_TABLES = {
    "nanobase_reporting.v_invoice",
    "nanobase_reporting.v_invoices",
    "nanobase_reporting.v_customer",
    "v_invoice",
    "v_invoices",
    "v_customer",
}

BI_REPORTING_TABLES = {
    "customers",
    "products",
    "orders",
    "order_items",
    "v_order_revenue",
    "companies",
    "branches",
    "customer_addresses",
    "sales_orders",
    "sales_order_items",
    "invoices",
    "payments",
    "currency_rates",
    "returns",
    "v_invoice_open",
    "analytics.customers",
    "analytics.products",
    "analytics.orders",
    "analytics.order_items",
    "analytics.v_order_revenue",
    "analytics.companies",
    "analytics.branches",
    "analytics.customer_addresses",
    "analytics.sales_orders",
    "analytics.sales_order_items",
    "analytics.invoices",
    "analytics.payments",
    "analytics.currency_rates",
    "analytics.returns",
    "analytics.v_invoice_open",
    "public.customers",
    "public.products",
    "public.orders",
    "public.order_items",
    "public.v_order_revenue",
    "public.companies",
    "public.branches",
    "public.customer_addresses",
    "public.sales_orders",
    "public.sales_order_items",
    "public.invoices",
    "public.payments",
    "public.currency_rates",
    "public.returns",
    "public.v_invoice_open",
}


def _allowed_tables(cfg: dict[str, Any], default: set[str] | None) -> set[str] | None:
    raw = cfg.get("allowed_tables")
    if raw is None:
        return default
    if raw == [] or raw == "*":
        return None if raw == "*" else set()
    return {str(x) for x in raw}


def load_datasources(settings: Settings | None = None) -> dict[str, dict[str, Any]]:
    settings = settings or get_settings()
    secrets = settings.secrets_root
    ds: dict[str, dict[str, Any]] = {}

    ro_file = secrets / "reporting-ro.password"
    if ro_file.is_file() or os.environ.get("REPORTING_RO_SECRET_REF"):
        try:
            pw = resolve_password(
                {
                    "secret_ref": os.environ.get("REPORTING_RO_SECRET_REF")
                    or f"file:{ro_file}",
                },
                settings,
            )
        except Exception:
            pw = ro_file.read_text(encoding="utf-8").strip() if ro_file.is_file() else ""
        if pw:
            rid = (
                os.environ.get("REPORTING_DATASOURCE_ID") or "bi_reporting"
            ).strip() or "bi_reporting"
            ds[rid] = {
                "id": rid,
                "driver": "postgresql",
                "host": os.environ.get("REPORTING_HOST", "127.0.0.1"),
                "port": int(os.environ.get("REPORTING_PORT", "5435")),
                "database": os.environ.get("REPORTING_DB", rid),
                "user": os.environ.get("REPORTING_RO_USER", f"{rid}_ro"),
                "password": pw,
                "sslmode": "disable",
                "dialect": "postgres",
                "allowed_tables": set(BI_REPORTING_TABLES),
                "allowed_schemas": {"public", "analytics"},
                "size_profile": "medium",
                "column_policies": {
                    "analytics.customers.email": "MASKED",
                    "public.customers.email": "MASKED",
                    "customers.email": "MASKED",
                },
            }

    for map_name, loader in (
        ("neon-ro.datasources.json", "postgres"),
        ("oracle-ro.datasources.json", "oracle"),
        ("sap-ro.datasources.json", "sap"),
    ):
        path = secrets / map_name
        if not path.is_file():
            continue
        try:
            extra = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        items = extra.get("sources") or extra
        if not isinstance(items, dict):
            continue
        for sid, cfg in items.items():
            if not isinstance(cfg, dict):
                continue
            if loader == "postgres":
                try:
                    pw = resolve_password(cfg, settings)
                except Exception:
                    continue
                if pw and cfg.get("host"):
                    ds[str(sid)] = {
                        "id": str(sid),
                        "driver": "postgresql",
                        "host": cfg["host"],
                        "port": int(cfg.get("port") or 5432),
                        "database": cfg.get("database") or "neondb",
                        "user": cfg.get("user") or cfg.get("username"),
                        "password": pw,
                        "sslmode": cfg.get("sslmode") or "require",
                        "dialect": "postgres",
                        "allowed_tables": _allowed_tables(cfg, None),
                        "allowed_schemas": set(cfg.get("allowed_schemas") or []),
                        "column_policies": cfg.get("column_policies") or {},
                        "size_profile": cfg.get("size_profile") or "medium",
                    }
            elif loader == "oracle":
                try:
                    pw = resolve_password(cfg, settings)
                except Exception:
                    continue
                user = cfg.get("user") or cfg.get("username")
                # Reject forbidden privileged accounts at load time
                from query_gateway.infrastructure.oracle.profile import (
                    FORBIDDEN_ORACLE_USERS,
                    validate_allowed_owners,
                )

                if not pw or not user:
                    continue
                if str(user).upper() in FORBIDDEN_ORACLE_USERS:
                    continue
                dsn = (cfg.get("dsn") or "").strip()
                host = cfg.get("host")
                service = cfg.get("service_name") or cfg.get("serviceName") or cfg.get("service") or cfg.get("database")
                allow_sid = bool(cfg.get("allow_sid") or cfg.get("allowSid") or False)
                if not dsn and not (host and service) and not (allow_sid and host and cfg.get("sid")):
                    continue
                port = int(cfg.get("port") or 1521)
                if not dsn:
                    if allow_sid and cfg.get("sid"):
                        dsn = f"{host}:{port}/{cfg.get('sid')}"
                    else:
                        dsn = f"{host}:{port}/{service}"
                owners_raw = cfg.get("allowed_owners") or cfg.get("allowedOwners")
                try:
                    allowed_owners = validate_allowed_owners(
                        list(owners_raw) if owners_raw else ["NANOBASE_REPORTING"]
                    )
                except Exception:
                    continue
                default_tables = (
                    DEFAULT_ORACLE_REPORTING_TABLES
                    if "NANOBASE_REPORTING" in allowed_owners
                    else DEFAULT_ORACLE_SSB_TABLES
                )
                tables = _allowed_tables(cfg, default_tables)
                # Normalize table names to lowercase for policy engine
                if tables is not None:
                    tables = {str(t).lower() for t in tables}
                ds[str(sid)] = {
                    "id": str(sid),
                    "driver": "oracle",
                    "host": host or "",
                    "port": port,
                    "database": service or "",
                    "service_name": service or "",
                    "dsn": dsn,
                    "user": user,
                    "password": pw,
                    "sslmode": cfg.get("sslmode") or cfg.get("sslMode") or "tcps",
                    "ssl_mode": cfg.get("ssl_mode") or cfg.get("sslMode") or "REQUIRE",
                    "dialect": "oracle",
                    "connection_mode": str(
                        cfg.get("connection_mode") or cfg.get("connectionMode") or "THIN"
                    ).upper(),
                    "wallet_secret_ref": cfg.get("wallet_secret_ref") or cfg.get("walletSecretRef"),
                    "allow_sid": allow_sid,
                    "sid": cfg.get("sid"),
                    "allowed_owners": allowed_owners,
                    "allowed_schemas": {o.lower() for o in allowed_owners},
                    "allowed_tables": tables,
                    "column_policies": cfg.get("column_policies") or cfg.get("columnPolicies") or {},
                    "size_profile": cfg.get("size_profile") or cfg.get("sizeProfile") or "medium",
                    "plan_user": cfg.get("plan_user") or cfg.get("planUser"),
                    "plan_password": cfg.get("plan_password") or cfg.get("planPassword"),
                    "metadata_user": cfg.get("metadata_user") or cfg.get("metadataUser"),
                    "metadata_password": cfg.get("metadata_password") or cfg.get("metadataPassword"),
                    "container_name": cfg.get("container_name") or cfg.get("containerName"),
                    "database_unique_name": cfg.get("database_unique_name")
                    or cfg.get("databaseUniqueName"),
                    "require_vpd": bool(cfg.get("require_vpd") or cfg.get("requireVpd") or False),
                    "label": cfg.get("label") or sid,
                }
            else:
                driver = (cfg.get("driver") or cfg.get("dialect") or "").lower()
                try:
                    pw = resolve_password(cfg, settings) if cfg.get("secret_ref") or cfg.get("password") else ""
                except Exception:
                    pw = str(cfg.get("password") or "")
                if driver in ("hana", "sap_hana", "hdb", "sap_hana_sql"):
                    if not (cfg.get("host") and (cfg.get("user") or cfg.get("username")) and pw):
                        continue
                    views = (
                        cfg.get("allowed_views")
                        or cfg.get("allowedViews")
                        or cfg.get("allowed_tables")
                        or []
                    )
                    schemas = cfg.get("allowed_schemas") or cfg.get("allowedSchemas") or []
                    ds[str(sid)] = {
                        "id": str(sid),
                        "driver": "hana",
                        "database_type": cfg.get("databaseType") or "SAP_HANA",
                        "deployment_type": cfg.get("deploymentType") or cfg.get("deployment_type"),
                        "host": cfg["host"],
                        "port": int(cfg.get("port") or 443),
                        "database": cfg.get("database") or cfg.get("databaseName") or "",
                        "user": cfg.get("user") or cfg.get("username"),
                        "password": pw,
                        "sslmode": "require",
                        "dialect": "hana",
                        "allowed_tables": _allowed_tables(cfg, sap_mod.DEFAULT_HANA_TABLES),
                        "allowed_views": [str(v) for v in views],
                        "allowed_schemas": [str(s) for s in schemas],
                        "encrypt": bool(cfg.get("encrypt", True)),
                        "ssl_validate": bool(cfg.get("ssl_validate", cfg.get("validateCertificate", False))),
                        "allow_insecure_tls": bool(cfg.get("allow_insecure_tls", False)),
                        "size_profile": str(cfg.get("size_profile") or cfg.get("sizeProfile") or "MEDIUM"),
                        "workload_class": cfg.get("workload_class")
                        or cfg.get("workloadClass")
                        or "NANOBASE_INTERACTIVE_QUERY",
                        "require_workload_class": bool(
                            cfg.get("require_workload_class")
                            if cfg.get("require_workload_class") is not None
                            else True
                        ),
                        "label": cfg.get("label") or sid,
                    }
                elif driver in ("odata", "cds", "cds_odata", "sap_s4hana_odata"):
                    base_url = (cfg.get("base_url") or cfg.get("url") or "").rstrip("/")
                    if not base_url:
                        continue
                    token = cfg.get("bearer_token")
                    if not token and cfg.get("token_file"):
                        token = Path(cfg["token_file"]).read_text(encoding="utf-8").strip()
                    entities = (
                        cfg.get("allowed_entity_sets")
                        or cfg.get("allowedEntitySets")
                        or cfg.get("allowed_entities")
                        or cfg.get("allowed_tables")
                        or []
                    )
                    services = cfg.get("allowed_services") or cfg.get("allowedServices") or []
                    ds[str(sid)] = {
                        "id": str(sid),
                        "driver": "odata",
                        "database_type": cfg.get("databaseType") or "SAP_S4HANA_ODATA",
                        "deployment_type": cfg.get("deploymentType") or cfg.get("deployment_type"),
                        "host": base_url,
                        "port": 443,
                        "database": "",
                        "base_url": base_url,
                        "odata_version": cfg.get("odataVersion") or cfg.get("odata_version") or "V4",
                        "communication_scenario": cfg.get("communicationScenario")
                        or cfg.get("communication_scenario")
                        or "",
                        "credential_secret_ref": cfg.get("credentialSecretRef")
                        or cfg.get("credential_secret_ref")
                        or "",
                        "user": cfg.get("user") or cfg.get("username") or "",
                        "password": pw,
                        "bearer_token": token,
                        "sslmode": "require",
                        "verify_tls": bool(cfg.get("verify_tls", True)),
                        "dialect": "odata",
                        "allowed_entities": set(entities),
                        "allowed_entity_sets": [str(e) for e in entities],
                        "allowed_services": [str(s) for s in services],
                        "allowed_company_codes": cfg.get("allowedCompanyCodes")
                        or cfg.get("allowed_company_codes")
                        or [],
                        "source_status": cfg.get("sourceStatus") or cfg.get("source_status") or "PUBLISHED",
                        "label": cfg.get("label") or sid,
                    }
    return ds
