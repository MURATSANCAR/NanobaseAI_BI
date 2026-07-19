"""Structured OData URL builder — no string concatenation of user host/path."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from urllib.parse import quote, urlencode, urlparse, urlunparse

from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.sap.contracts.datasource import ODataDatasourceConfig
from query_gateway.infrastructure.sap.contracts.query import ODataFilter, ODataLogicalPlan
from query_gateway.infrastructure.sap.odata.policy_engine import (
    INTERACTIVE_TOP,
    MAX_TOP,
    ODATA_POLICY_VIOLATION,
    validate_odata_plan,
)


def _escape_odata_string(value: str) -> str:
    return value.replace("'", "''")


def _literal(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return ",".join(_literal(v) for v in value)
    return f"'{_escape_odata_string(str(value))}'"


def _filter_expr(f: ODataFilter) -> str:
    op = f.normalized_op()
    field = f.field
    if op == "EQ":
        return f"{field} eq {_literal(f.value)}"
    if op == "NE":
        return f"{field} ne {_literal(f.value)}"
    if op == "GT":
        return f"{field} gt {_literal(f.value)}"
    if op == "GE":
        return f"{field} ge {_literal(f.value)}"
    if op == "LT":
        return f"{field} lt {_literal(f.value)}"
    if op == "LE":
        return f"{field} le {_literal(f.value)}"
    if op == "IN":
        vals = f.value if isinstance(f.value, list) else [f.value]
        parts = " or ".join(f"{field} eq {_literal(v)}" for v in vals)
        return f"({parts})"
    if op == "STARTSWITH":
        return f"startswith({field},{_literal(f.value)})"
    if op == "CONTAINS":
        return f"contains({field},{_literal(f.value)})"
    raise GatewayError(ODATA_POLICY_VIOLATION, f"Unsupported filter op: {op}", status=400)


def build_odata_request(
    plan: ODataLogicalPlan,
    cfg: ODataDatasourceConfig,
    *,
    filterable_fields: set[str] | None = None,
) -> dict[str, Any]:
    warnings = validate_odata_plan(plan, cfg, filterable_fields=filterable_fields)
    top = max(1, min(int(plan.top or INTERACTIVE_TOP), MAX_TOP))

    base = urlparse(cfg.base_url)
    # Path is only entity set relative to service root — never user-controlled host
    entity_segment = quote(plan.entity_set, safe="")
    path = base.path.rstrip("/") + "/" + entity_segment

    params: list[tuple[str, str]] = []
    params.append(("$select", ",".join(plan.select)))
    if plan.filters:
        params.append(("$filter", " and ".join(_filter_expr(f) for f in plan.filters)))
    if plan.orderby:
        params.append(("$orderby", ",".join(plan.orderby)))
    params.append(("$top", str(top)))
    if plan.expand:
        params.append(("$expand", ",".join(plan.expand)))
    if plan.count:
        params.append(("$count", "true"))
    params.append(("$format", "json"))

    query = urlencode(params, safe=",'$() /")
    url = urlunparse((base.scheme, base.netloc, path, "", query, ""))

    return {
        "method": "GET",
        "url": url,
        "path": path,
        "entitySet": plan.entity_set,
        "service": plan.service,
        "query": dict(params),
        "top": top,
        "warnings": warnings,
        "plan": plan.to_dict(),
    }
