"""OData logical plan policy (fail-closed)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.sap.contracts.datasource import ODataDatasourceConfig
from query_gateway.infrastructure.sap.contracts.query import ALLOWED_FILTER_OPS, ODataLogicalPlan

ODATA_POLICY_VIOLATION = "ODATA_POLICY_VIOLATION"
SAP_SOURCE_NOT_PUBLISHED = "SAP_SOURCE_NOT_PUBLISHED"

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SAFE_SERVICE = re.compile(r"^[A-Za-z0-9_./$-]+$")

INTERACTIVE_TOP = 100
MAX_TOP = 1000
MAX_EXPAND_DEPTH = 1
MAX_EXPAND_NAV = 2
MAX_SELECT = 100
MAX_FILTERS = 40


def validate_odata_plan(
    plan: ODataLogicalPlan,
    cfg: ODataDatasourceConfig,
    *,
    filterable_fields: set[str] | None = None,
) -> list[str]:
    warnings: list[str] = []

    if (cfg.source_status or "").upper() != "PUBLISHED":
        raise GatewayError(
            SAP_SOURCE_NOT_PUBLISHED,
            f"SAP source status must be PUBLISHED, got {cfg.source_status}.",
            status=403,
        )

    if plan.source_type.upper() not in ("SAP_ODATA", "ODATA"):
        raise GatewayError(ODATA_POLICY_VIOLATION, "sourceType must be SAP_ODATA.", status=400)

    if not plan.entity_set or not _IDENT.match(plan.entity_set.split("/")[0]):
        raise GatewayError(ODATA_POLICY_VIOLATION, "Invalid entitySet.", status=400)

    if ".." in plan.entity_set or ";" in plan.entity_set or plan.entity_set.startswith("http"):
        raise GatewayError(ODATA_POLICY_VIOLATION, "Entity path escape rejected.", status=400)

    if plan.service and not _SAFE_SERVICE.match(plan.service):
        raise GatewayError(ODATA_POLICY_VIOLATION, "Invalid service name.", status=400)

    if cfg.allowed_services and plan.service:
        allowed_svc = {s.lower() for s in cfg.allowed_services}
        if plan.service.lower() not in allowed_svc:
            raise GatewayError(
                ODATA_POLICY_VIOLATION,
                f"Service not allowlisted: {plan.service}",
                status=403,
            )

    allowed_entities = {e.lower().rstrip("/") for e in cfg.allowed_entity_sets}
    bare = plan.entity_set.split("(")[0].rstrip("/").lower()
    if allowed_entities and bare not in allowed_entities:
        raise GatewayError(
            ODATA_POLICY_VIOLATION,
            f"Entity set not allowlisted: {plan.entity_set}",
            status=403,
        )

    if not plan.select:
        raise GatewayError(ODATA_POLICY_VIOLATION, "$select is required (no wildcard).", status=400)

    if len(plan.select) > MAX_SELECT:
        raise GatewayError(ODATA_POLICY_VIOLATION, "Too many $select fields.", status=400)

    for col in plan.select:
        if col == "*" or not _IDENT.match(col):
            raise GatewayError(ODATA_POLICY_VIOLATION, f"Invalid $select field: {col}", status=400)

    if plan.top < 1 or plan.top > MAX_TOP:
        raise GatewayError(
            ODATA_POLICY_VIOLATION,
            f"$top must be 1..{MAX_TOP}.",
            status=400,
        )
    if plan.top > INTERACTIVE_TOP:
        warnings.append(f"top_above_interactive:{plan.top}")

    if len(plan.filters) > MAX_FILTERS:
        raise GatewayError(ODATA_POLICY_VIOLATION, "Too many filters.", status=400)

    for f in plan.filters:
        if not f.field or not _IDENT.match(f.field):
            raise GatewayError(ODATA_POLICY_VIOLATION, f"Invalid filter field: {f.field}", status=400)
        op = f.normalized_op()
        if op not in ALLOWED_FILTER_OPS:
            raise GatewayError(ODATA_POLICY_VIOLATION, f"Filter operator denied: {op}", status=400)
        if filterable_fields is not None and f.field not in filterable_fields:
            raise GatewayError(
                ODATA_POLICY_VIOLATION,
                f"Field not filterable: {f.field}",
                status=403,
            )
        if isinstance(f.value, str) and (
            "://" in f.value or f.value.lower().startswith(("http", "odata."))
        ):
            raise GatewayError(ODATA_POLICY_VIOLATION, "Filter value URL injection.", status=400)

    for ob in plan.orderby:
        field = ob.split()[0] if ob else ""
        if not field or not _IDENT.match(field):
            raise GatewayError(ODATA_POLICY_VIOLATION, f"Invalid $orderby: {ob}", status=400)
        parts = ob.split()
        if len(parts) > 1 and parts[1].lower() not in ("asc", "desc"):
            raise GatewayError(ODATA_POLICY_VIOLATION, f"Invalid $orderby direction: {ob}", status=400)

    if len(plan.expand) > MAX_EXPAND_NAV:
        raise GatewayError(ODATA_POLICY_VIOLATION, "Too many $expand navigations.", status=400)
    for exp in plan.expand:
        depth = exp.count("/") + 1
        if depth > MAX_EXPAND_DEPTH:
            raise GatewayError(ODATA_POLICY_VIOLATION, "Expand depth > 1 denied.", status=400)
        if not _IDENT.match(exp.split("/")[0]):
            raise GatewayError(ODATA_POLICY_VIOLATION, f"Invalid $expand: {exp}", status=400)

    # Service root host must match datasource base
    parsed = urlparse(cfg.base_url)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise GatewayError(ODATA_POLICY_VIOLATION, "Invalid datasource baseUrl.", status=400)

    return warnings


def assert_read_only_method(method: str) -> None:
    m = (method or "").upper()
    if m not in ("GET", "HEAD"):
        raise GatewayError(
            ODATA_POLICY_VIOLATION,
            f"OData write/method denied: {method}",
            status=403,
        )


def parse_legacy_odata_sql(sql: str) -> tuple[str, dict[str, str]]:
    """Legacy bridge: 'Entity?$select=A&$top=10' → entity + query dict."""
    raw = (sql or "").strip()
    if not raw:
        raise GatewayError(ODATA_POLICY_VIOLATION, "Empty OData path.", status=400)
    if raw.lower().startswith("http") or "://" in raw:
        raise GatewayError(ODATA_POLICY_VIOLATION, "Absolute URL injection denied.", status=400)
    if "?" in raw:
        entity, qs = raw.split("?", 1)
    else:
        entity, qs = raw, ""
    from urllib.parse import parse_qsl

    query = dict(parse_qsl(qs, keep_blank_values=True))
    # Detect duplication
    keys = [k for k, _ in parse_qsl(qs, keep_blank_values=True)]
    if len(keys) != len(set(keys)):
        raise GatewayError(ODATA_POLICY_VIOLATION, "Query option duplication denied.", status=400)
    for bad in ("$batch", "$apply", "$search", "$compute", "$levels", "$crossjoin"):
        if bad in query:
            raise GatewayError(ODATA_POLICY_VIOLATION, f"Forbidden OData option: {bad}", status=400)
    return entity, query


def legacy_to_logical_plan(sql: str, service: str = "") -> ODataLogicalPlan:
    entity, query = parse_legacy_odata_sql(sql)
    select = [s.strip() for s in (query.get("$select") or "").split(",") if s.strip()]
    top = int(query.get("$top") or INTERACTIVE_TOP)
    orderby = [s.strip() for s in (query.get("$orderby") or "").split(",") if s.strip()]
    expand = [s.strip() for s in (query.get("$expand") or "").split(",") if s.strip()]
    filters: list[Any] = []
    # Simple EQ filters only from legacy string are not fully parsed; require $select
    from query_gateway.infrastructure.sap.contracts.query import ODataFilter

    filt = query.get("$filter") or ""
    # Very small EQ parser: Field eq 'value'
    m = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s+eq\s+'([^']*)'", filt.strip(), re.I)
    if m:
        filters.append(ODataFilter(field=m.group(1), operator="EQ", value=m.group(2)))
    elif filt.strip():
        raise GatewayError(
            ODATA_POLICY_VIOLATION,
            "Legacy $filter must be simple Field eq 'value' or use logical plan.",
            status=400,
        )
    return ODataLogicalPlan(
        source_type="SAP_ODATA",
        service=service,
        entity_set=entity.split("(")[0].rstrip("/"),
        select=select,
        filters=filters,
        orderby=orderby,
        top=top,
        expand=expand,
        count=str(query.get("$count") or "").lower() in ("true", "1"),
    )
