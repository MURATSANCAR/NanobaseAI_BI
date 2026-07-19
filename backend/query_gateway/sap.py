"""SAP HANA + CDS-OData RO helpers — thin shim over infrastructure.sap (Faz 9)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from query_gateway.infrastructure.sap import DEFAULT_HANA_TABLES, HANA_SQLGLOT_DIALECT
from query_gateway.infrastructure.sap.contracts.datasource import ODataDatasourceConfig
from query_gateway.infrastructure.sap.odata.client import execute_odata_plan
from query_gateway.infrastructure.sap.odata.policy_engine import legacy_to_logical_plan

__all__ = [
    "HANA_SQLGLOT_DIALECT",
    "DEFAULT_HANA_TABLES",
    "execute_hana",
    "execute_odata",
    "validate_odata_path",
]


def validate_odata_path(entity: str, allowed: set[str] | None) -> str | None:
    entity = (entity or "").strip().lstrip("/")
    if not entity or ".." in entity or ";" in entity:
        return "invalid entity path"
    if entity.lower().startswith("http") or "://" in entity:
        return "absolute url denied"
    bare = entity.split("(")[0].rstrip("/").lower()
    if allowed is not None:
        allowed_n = {a.lower().rstrip("/") for a in allowed}
        if bare not in allowed_n and entity.lower() not in allowed_n:
            return f"entity not allowlisted: {bare}"
    return None


def execute_hana(
    ds: dict[str, Any],
    sql: str,
    *,
    timeout_s: float,
    max_rows: int,
    max_cells: int,
    explain: bool,
) -> tuple[list[str], list[dict[str, Any]], bool]:
    """Legacy execute path — delegates to hardened executor when enabled."""
    import os

    os.environ.setdefault("SAP_HANA_EXECUTION_ENABLED", "1")
    os.environ.setdefault("SAP_EXECUTION_ENABLED", "1")
    if ds.get("ssl_validate") is False:
        ds = dict(ds)
        ds["allow_insecure_tls"] = True
        ds["validate_certificate"] = False

    from query_gateway.infrastructure.sap.hana.executor import execute_hana_ro

    cols, rows, truncated, _ms = execute_hana_ro(
        ds,
        sql,
        timeout_ms=int(timeout_s * 1000),
        max_rows=max_rows,
        run_explain=explain,
    )
    cells = len(rows) * max(len(cols), 1)
    if cells > max_cells:
        keep = max(1, max_cells // max(len(cols), 1))
        rows = rows[:keep]
        truncated = True
    return cols, rows, truncated


def execute_odata(
    ds: dict[str, Any],
    *,
    entity: str,
    query: dict[str, str],
    timeout_s: float,
    max_rows: int,
) -> dict[str, Any]:
    err = validate_odata_path(entity, ds.get("allowed_entities") or ds.get("allowed_entity_sets"))
    if err:
        raise ValueError(err)

    q = {k: v for k, v in query.items() if k.startswith("$")}
    top = int(q.get("$top") or max_rows)
    q["$top"] = str(max(1, min(top, max_rows)))
    if "$select" not in q:
        raise ValueError("$select is required")
    legacy = entity + "?" + urlencode(q)
    cfg = ODataDatasourceConfig.from_datasource(ds)
    if not cfg.allowed_entity_sets and ds.get("allowed_entities"):
        cfg.allowed_entity_sets = sorted(ds["allowed_entities"])
    plan = legacy_to_logical_plan(
        legacy, service=(cfg.allowed_services[0] if cfg.allowed_services else "")
    )
    cfg.source_status = cfg.source_status or "PUBLISHED"
    result = execute_odata_plan(cfg, plan, timeout_s=timeout_s, max_rows=max_rows)
    return {
        "columns": result["columns"],
        "rows": result["rows"],
        "row_count": result["row_count"],
        "truncated": result["truncated"],
        "url": result.get("urlPath"),
    }
