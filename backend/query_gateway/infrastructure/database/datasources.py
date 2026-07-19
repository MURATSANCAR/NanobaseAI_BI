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
            ds["bi_reporting"] = {
                "id": "bi_reporting",
                "driver": "postgresql",
                "host": os.environ.get("REPORTING_HOST", "127.0.0.1"),
                "port": int(os.environ.get("REPORTING_PORT", "5435")),
                "database": os.environ.get("REPORTING_DB", "bi_reporting"),
                "user": os.environ.get("REPORTING_RO_USER", "bi_reporting_ro"),
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
                dsn = (cfg.get("dsn") or "").strip()
                host = cfg.get("host")
                service = cfg.get("service_name") or cfg.get("service") or cfg.get("database")
                if not pw or not user:
                    continue
                if not dsn and not (host and service):
                    continue
                port = int(cfg.get("port") or 1522)
                if not dsn:
                    dsn = f"{host}:{port}/{service}"
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
                    "sslmode": cfg.get("sslmode") or "tcps",
                    "dialect": "oracle",
                    "allowed_tables": _allowed_tables(cfg, DEFAULT_ORACLE_SSB_TABLES),
                    "label": cfg.get("label") or sid,
                }
            else:
                driver = (cfg.get("driver") or cfg.get("dialect") or "").lower()
                try:
                    pw = resolve_password(cfg, settings) if cfg.get("secret_ref") or cfg.get("password") else ""
                except Exception:
                    pw = str(cfg.get("password") or "")
                if driver in ("hana", "sap_hana", "hdb"):
                    if not (cfg.get("host") and (cfg.get("user") or cfg.get("username")) and pw):
                        continue
                    ds[str(sid)] = {
                        "id": str(sid),
                        "driver": "hana",
                        "host": cfg["host"],
                        "port": int(cfg.get("port") or 443),
                        "database": cfg.get("database") or "",
                        "user": cfg.get("user") or cfg.get("username"),
                        "password": pw,
                        "sslmode": "require",
                        "dialect": sap_mod.HANA_SQLGLOT_DIALECT,
                        "allowed_tables": _allowed_tables(cfg, sap_mod.DEFAULT_HANA_TABLES),
                        "encrypt": bool(cfg.get("encrypt", True)),
                        "ssl_validate": bool(cfg.get("ssl_validate", False)),
                        "label": cfg.get("label") or sid,
                    }
                elif driver in ("odata", "cds", "cds_odata"):
                    base_url = (cfg.get("base_url") or cfg.get("url") or "").rstrip("/")
                    if not base_url:
                        continue
                    token = cfg.get("bearer_token")
                    if not token and cfg.get("token_file"):
                        token = Path(cfg["token_file"]).read_text(encoding="utf-8").strip()
                    ds[str(sid)] = {
                        "id": str(sid),
                        "driver": "odata",
                        "host": base_url,
                        "port": 443,
                        "database": "",
                        "base_url": base_url,
                        "user": cfg.get("user") or cfg.get("username") or "",
                        "password": pw,
                        "bearer_token": token,
                        "sslmode": "require",
                        "verify_tls": bool(cfg.get("verify_tls", True)),
                        "dialect": "odata",
                        "allowed_entities": set(
                            cfg.get("allowed_entities") or cfg.get("allowed_tables") or []
                        ),
                        "label": cfg.get("label") or sid,
                    }
    return ds
