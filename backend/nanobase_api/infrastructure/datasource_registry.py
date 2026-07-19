"""Dynamic datasource registry from secrets maps — no hardcoded source id lists."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

SECRETS = Path(os.environ.get("SECRETS_ROOT", "/data/nanobaseai/bi/secrets"))


def reporting_datasource_id() -> str:
    """Product default id for the optional local reporting RO database.

    Overridable via REPORTING_DATASOURCE_ID — never hardcode this name at call sites.
    """
    return (os.environ.get("REPORTING_DATASOURCE_ID") or "bi_reporting").strip() or "bi_reporting"


def registered_ro_datasource_ids() -> set[str]:
    """All datasource ids present in secrets RO maps (+ local reporting if configured)."""
    ids: set[str] = set()
    if local_reporting_entry():
        ids.add(reporting_datasource_id())
    for map_name in (
        "neon-ro.datasources.json",
        "oracle-ro.datasources.json",
        "sap-ro.datasources.json",
    ):
        path = SECRETS / map_name
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            sources = raw.get("sources") if isinstance(raw, dict) else None
            if not isinstance(sources, dict):
                sources = raw if isinstance(raw, dict) else {}
            for sid in sources:
                if sid and isinstance(sources.get(sid), dict):
                    ids.add(str(sid))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
    return ids


def is_registered_ro_datasource(datasource_id: str) -> bool:
    sid = str(datasource_id or "").strip()
    if not sid:
        return False
    # Legacy alias used in some checklists → reporting id
    if sid == "nanobase_test":
        sid = reporting_datasource_id()
    return sid in registered_ro_datasource_ids()


def _mark_managed(entry: dict[str, Any]) -> dict[str, Any]:
    entry["managed"] = True
    entry["protected"] = True
    return entry


def local_reporting_entry() -> dict[str, Any] | None:
    """Optional on-prem reporting RO — only if password file exists."""
    ro = SECRETS / "reporting-ro.password"
    if not ro.is_file():
        return None
    sid = reporting_datasource_id()
    return _mark_managed(
        {
            "id": sid,
            "label": os.environ.get("REPORTING_LABEL") or f"{sid} (RO)",
            "driver": "postgresql",
            "dialect": "postgresql",
            "host": os.environ.get("REPORTING_HOST", "127.0.0.1"),
            "port": int(os.environ.get("REPORTING_PORT", "5435")),
            "database": os.environ.get("REPORTING_DB", sid),
            "username": os.environ.get("REPORTING_RO_USER", f"{sid}_ro"),
            "ssl": False,
            "secret_ref": f"file:{ro}",
            "tenant_id": "default",
            "project_id": "default",
            "password_masked": "********",
            "deployment": "onprem",
        }
    )


def merge_gateway_ro_sources(by_id: dict[str, dict[str, Any]]) -> set[str]:
    """Merge Neon/Oracle/SAP/local RO maps into sources dict. Returns managed ids."""
    managed: set[str] = set()

    reporting = local_reporting_entry()
    if reporting:
        sid = str(reporting["id"])
        managed.add(sid)
        by_id.setdefault(sid, reporting)
        by_id[sid] = {**by_id[sid], **{k: reporting[k] for k in ("managed", "protected")}}

    neon = SECRETS / "neon-ro.datasources.json"
    if neon.is_file():
        try:
            raw = json.loads(neon.read_text(encoding="utf-8"))
            for sid, cfg in (raw.get("sources") or {}).items():
                if not isinstance(cfg, dict) or not cfg.get("host"):
                    continue
                sid_s = str(sid)
                managed.add(sid_s)
                entry = _mark_managed(
                    {
                        "id": sid_s,
                        "label": cfg.get("label") or sid_s,
                        "driver": "postgresql",
                        "dialect": "postgresql",
                        "host": cfg.get("host") or "",
                        "port": int(cfg.get("port") or 5432),
                        "database": cfg.get("database") or cfg.get("dbname") or "neondb",
                        "username": cfg.get("user") or cfg.get("username") or "",
                        "ssl": True,
                        "secret_ref": cfg.get("password_file")
                        or f"file:{SECRETS}/neon-{sid_s}.password",
                        "tenant_id": "default",
                        "project_id": "default",
                        "password_masked": "********",
                        "deployment": "cloud",
                    }
                )
                if sid_s in by_id:
                    by_id[sid_s] = {
                        **by_id[sid_s],
                        "managed": True,
                        "protected": True,
                        # Keep RO credentials authoritative when map has them
                        "username": entry["username"] or by_id[sid_s].get("username"),
                        "secret_ref": entry["secret_ref"] or by_id[sid_s].get("secret_ref"),
                        "host": entry["host"] or by_id[sid_s].get("host"),
                        "port": entry["port"] or by_id[sid_s].get("port"),
                        "database": entry["database"] or by_id[sid_s].get("database"),
                    }
                else:
                    by_id[sid_s] = entry
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    ora_map = SECRETS / "oracle-ro.datasources.json"
    if ora_map.is_file():
        try:
            raw = json.loads(ora_map.read_text(encoding="utf-8"))
            for sid, cfg in (raw.get("sources") or raw).items():
                if not isinstance(cfg, dict):
                    continue
                sid_s = str(sid)
                managed.add(sid_s)
                entry = _mark_managed(
                    {
                        "id": sid_s,
                        "label": cfg.get("label") or sid_s,
                        "driver": "oracle",
                        "dialect": "oracle",
                        "host": cfg.get("host") or "",
                        "port": int(cfg.get("port") or 1522),
                        "database": cfg.get("service_name") or cfg.get("database") or "",
                        "username": cfg.get("user") or cfg.get("username") or "",
                        "ssl": True,
                        "secret_ref": cfg.get("password_file")
                        or f"file:{SECRETS}/oracle-adb.password",
                        "tenant_id": "default",
                        "project_id": "default",
                        "password_masked": "********",
                        "deployment": "cloud",
                    }
                )
                by_id[sid_s] = {**by_id.get(sid_s, {}), **entry}
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    sap_map = SECRETS / "sap-ro.datasources.json"
    if sap_map.is_file():
        try:
            raw = json.loads(sap_map.read_text(encoding="utf-8"))
            for sid, cfg in (raw.get("sources") or raw).items():
                if not isinstance(cfg, dict):
                    continue
                sid_s = str(sid)
                driver = (cfg.get("driver") or "").lower()
                managed.add(sid_s)
                if driver in ("hana", "sap_hana", "hdb"):
                    entry = _mark_managed(
                        {
                            "id": sid_s,
                            "label": cfg.get("label") or sid_s,
                            "driver": "hana",
                            "dialect": "hana",
                            "host": cfg.get("host") or "",
                            "port": int(cfg.get("port") or 443),
                            "database": cfg.get("database") or "",
                            "username": cfg.get("user") or cfg.get("username") or "",
                            "ssl": True,
                            "secret_ref": cfg.get("password_file") or "",
                            "tenant_id": "default",
                            "project_id": "default",
                            "password_masked": "********",
                            "deployment": "cloud",
                        }
                    )
                elif driver in ("odata", "cds", "cds_odata"):
                    entry = _mark_managed(
                        {
                            "id": sid_s,
                            "label": cfg.get("label") or sid_s,
                            "driver": "odata",
                            "dialect": "odata",
                            "host": cfg.get("base_url") or cfg.get("url") or "",
                            "port": 443,
                            "database": "",
                            "username": cfg.get("user") or cfg.get("username") or "",
                            "ssl": True,
                            "secret_ref": cfg.get("password_file")
                            or cfg.get("token_file")
                            or "",
                            "tenant_id": "default",
                            "project_id": "default",
                            "password_masked": "********",
                            "deployment": "cloud",
                        }
                    )
                else:
                    continue
                by_id[sid_s] = {**by_id.get(sid_s, {}), **entry}
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    for sid, row in by_id.items():
        if sid in managed:
            row["managed"] = True
            row["protected"] = True
        else:
            row.setdefault("managed", False)
            row.setdefault("protected", False)
    return managed


def resolve_pg_connect_cfg(datasource_id: str) -> dict[str, Any] | None:
    """Postgres connect cfg for schema introspection — map-driven, any id."""
    sid = str(datasource_id or "").strip()
    if not sid:
        return None

    neon = SECRETS / "neon-ro.datasources.json"
    if neon.is_file():
        try:
            raw = json.loads(neon.read_text(encoding="utf-8"))
            cfg = (raw.get("sources") or {}).get(sid)
            if isinstance(cfg, dict) and cfg.get("host"):
                return cfg
        except (OSError, json.JSONDecodeError):
            pass

    if sid == reporting_datasource_id():
        ro = SECRETS / "reporting-ro.password"
        if ro.is_file():
            return {
                "host": os.environ.get("REPORTING_HOST", "127.0.0.1"),
                "port": int(os.environ.get("REPORTING_PORT", "5435")),
                "database": os.environ.get("REPORTING_DB", sid),
                "user": os.environ.get("REPORTING_RO_USER", f"{sid}_ro"),
                "password": ro.read_text(encoding="utf-8").strip(),
                "sslmode": "disable",
            }
    return None
