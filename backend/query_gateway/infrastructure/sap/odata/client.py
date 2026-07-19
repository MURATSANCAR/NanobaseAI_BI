"""Read-only OData HTTP client."""

from __future__ import annotations

import time
from typing import Any

import httpx

from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.sap.contracts.datasource import ODataDatasourceConfig
from query_gateway.infrastructure.sap.contracts.query import ODataLogicalPlan
from query_gateway.infrastructure.sap.odata.error_mapper import (
    SAP_SERVICE_UNAVAILABLE,
    map_odata_http_error,
)
from query_gateway.infrastructure.sap.odata.pagination import validate_next_link
from query_gateway.infrastructure.sap.odata.policy_engine import assert_read_only_method
from query_gateway.infrastructure.sap.odata.query_builder import build_odata_request
from query_gateway.infrastructure.sap.odata.result_normalizer import normalize_odata_rows

ODATA_POLICY_VIOLATION = "ODATA_POLICY_VIOLATION"


def fetch_metadata(cfg: ODataDatasourceConfig, *, timeout_s: float = 30.0) -> str:
    assert_read_only_method("GET")
    url = cfg.base_url.rstrip("/") + "/$metadata"
    headers, auth = _auth(cfg)
    try:
        with httpx.Client(timeout=timeout_s, verify=cfg.verify_tls) as client:
            r = client.get(url, headers=headers, auth=auth)
    except httpx.RequestError as e:
        raise GatewayError(SAP_SERVICE_UNAVAILABLE, "SAP metadata unreachable.", status=503) from e
    if r.status_code >= 400:
        raise map_odata_http_error(r.status_code, r.text)
    return r.text


def execute_odata_plan(
    cfg: ODataDatasourceConfig,
    plan: ODataLogicalPlan,
    *,
    timeout_s: float = 15.0,
    max_rows: int = 100,
    max_pages: int = 1,
    filterable_fields: set[str] | None = None,
) -> dict[str, Any]:
    t0 = time.time()
    built = build_odata_request(plan, cfg, filterable_fields=filterable_fields)
    assert_read_only_method(built["method"])
    headers, auth = _auth(cfg)
    headers["Accept"] = "application/json"

    rows_raw: list[dict[str, Any]] = []
    url = built["url"]
    select_opt = built["query"].get("$select")
    pages = 0

    try:
        with httpx.Client(timeout=timeout_s, verify=cfg.verify_tls) as client:
            while url and pages < max_pages and len(rows_raw) < max_rows:
                r = client.get(url, headers=headers, auth=auth)
                if r.status_code >= 400:
                    raise map_odata_http_error(r.status_code, r.text)
                data = r.json()
                chunk = _extract_rows(data)
                rows_raw.extend(chunk)
                pages += 1
                next_link = None
                if isinstance(data, dict):
                    next_link = data.get("@odata.nextLink") or data.get("odata.nextLink")
                    if not next_link and isinstance(data.get("d"), dict):
                        next_link = data["d"].get("__next")
                if not next_link or len(rows_raw) >= max_rows:
                    break
                url = validate_next_link(
                    next_link,
                    base_url=cfg.base_url,
                    entity_set=plan.entity_set,
                    original_select=select_opt,
                    page_index=pages,
                )
    except httpx.RequestError as e:
        raise GatewayError(SAP_SERVICE_UNAVAILABLE, "SAP OData unreachable.", status=503) from e

    truncated = len(rows_raw) > max_rows
    rows_raw = rows_raw[:max_rows]
    rows = normalize_odata_rows(rows_raw)
    cols: list[str] = []
    for item in rows:
        for k in item:
            if k not in cols:
                cols.append(k)

    return {
        "columns": cols,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
        "pages": pages,
        "executionTimeMs": int((time.time() - t0) * 1000),
        "urlPath": built["path"],
        "warnings": built.get("warnings") or [],
        "plan": built.get("plan"),
    }


def _auth(cfg: ODataDatasourceConfig) -> tuple[dict[str, str], tuple[str, str] | None]:
    headers: dict[str, str] = {}
    auth = None
    if cfg.bearer_token:
        headers["Authorization"] = f"Bearer {cfg.bearer_token}"
    elif cfg.user and cfg.password:
        auth = (cfg.user, cfg.password)
    return headers, auth


def _extract_rows(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    if isinstance(data.get("value"), list):
        return [x for x in data["value"] if isinstance(x, dict)]
    d = data.get("d")
    if isinstance(d, dict) and isinstance(d.get("results"), list):
        return [x for x in d["results"] if isinstance(x, dict)]
    if isinstance(d, list):
        return [x for x in d if isinstance(x, dict)]
    return []
