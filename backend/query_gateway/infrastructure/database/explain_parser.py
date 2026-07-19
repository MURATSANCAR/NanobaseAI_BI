"""EXPLAIN (FORMAT JSON) cost guard."""

from __future__ import annotations

from typing import Any

from query_gateway.config.settings import Settings
from query_gateway.domain.errors import QUERY_COST_EXCEEDED, GatewayError


def _walk_plan(node: dict[str, Any], acc: dict[str, Any]) -> None:
    acc["total_cost"] = max(acc["total_cost"], float(node.get("Total Cost") or 0))
    acc["plan_rows"] = max(acc["plan_rows"], float(node.get("Plan Rows") or 0))
    ntype = str(node.get("Node Type") or "")
    if ntype == "Nested Loop" and not node.get("Join Filter") and not node.get("Filter"):
        # may still be OK with Index Cond
        pass
    join_type = str(node.get("Join Type") or "")
    if join_type.upper() == "CROSS" or ntype == "Nested Loop" and node.get("Join Filter") == "true":
        acc["cross_join"] = True
    if ntype == "Seq Scan":
        filt = node.get("Filter") or node.get("Index Cond")
        rel = str(node.get("Relation Name") or "")
        if not filt and rel:
            acc["filterless_seq"].append(rel)
    for child in node.get("Plans") or []:
        if isinstance(child, dict):
            _walk_plan(child, acc)


def analyze_explain_json(plan_json: Any, *, size_profile: str, settings: Settings) -> dict[str, Any]:
    if isinstance(plan_json, list) and plan_json:
        root = plan_json[0].get("Plan") if isinstance(plan_json[0], dict) else None
    elif isinstance(plan_json, dict):
        root = plan_json.get("Plan") or plan_json
    else:
        root = None
    if not isinstance(root, dict):
        raise GatewayError(QUERY_COST_EXCEEDED, "EXPLAIN plan okunamadı.", status=400)

    acc: dict[str, Any] = {
        "total_cost": 0.0,
        "plan_rows": 0.0,
        "cross_join": False,
        "filterless_seq": [],
    }
    _walk_plan(root, acc)

    profile = (size_profile or "medium").lower()
    max_rows = {
        "small": settings.cost_max_rows_small,
        "medium": settings.cost_max_rows_medium,
        "large": settings.cost_max_rows_large,
        "very_large": settings.cost_max_rows_large * 2,
    }.get(profile, settings.cost_max_rows_medium)
    max_cost = {
        "small": settings.cost_max_total_small,
        "medium": settings.cost_max_total_medium,
        "large": settings.cost_max_total_large,
        "very_large": settings.cost_max_total_large * 2,
    }.get(profile, settings.cost_max_total_medium)

    if acc["cross_join"]:
        raise GatewayError(QUERY_COST_EXCEEDED, "EXPLAIN: cross join tespit edildi.", status=400)
    if acc["plan_rows"] > max_rows:
        raise GatewayError(
            QUERY_COST_EXCEEDED,
            "Sorgu tahmini satır sayısı eşiği aşıyor.",
            status=400,
        )
    if acc["total_cost"] > max_cost:
        raise GatewayError(
            QUERY_COST_EXCEEDED,
            "Sorgu tahmini maliyeti eşiği aşıyor.",
            status=400,
        )
    return acc
