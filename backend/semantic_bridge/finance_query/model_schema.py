"""Closed output shapes supplied to the model server, not just described in a prompt."""
from .contracts import METRICS, DIMENSIONS


def obj(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


PLAN_SCHEMA = obj({
    "metrics": {"type": "array", "items": {"type": "string", "enum": list(METRICS)}},
    "dimensions": {"type": "array", "items": {"type": "string", "enum": list(DIMENSIONS)}},
    "sale_kind": {"type": "string", "enum": ["all", "wholesale", "retail"]},
    "filters": {"type": "array", "items": obj({
        "dimension": {"type": "string", "enum": ["book", "channel", "customer", "author", "publisher"]},
        "op": {"type": "string", "enum": ["eq", "contains"]},
        "value": {"type": "string"},
    })},
    "limit": {"anyOf": [{"type": "null"}, {"type": "integer", "minimum": 1, "maximum": 1000}]},
    "order_by": {"anyOf": [{"type": "null"}, {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,63}$"}]},
    "descending": {"type": "boolean"},
    "derived": {"type": "array", "maxItems": 8, "items": obj({
        "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,63}$"},
        "op": {"type": "string", "enum": ["ratio", "difference", "percent_change"]},
        "left": {"type": "string", "enum": list(METRICS)},
        "right": {"type": "string", "enum": list(METRICS)},
        "scale": {"type": "number", "enum": [1, 100]},
    })},
    "having": {"type": "array", "maxItems": 8, "items": obj({
        "metric": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,63}$"},
        "op": {"type": "string", "enum": ["gt", "gte", "lt", "lte", "eq", "neq"]},
        "value": {"type": "string", "pattern": "^-?[0-9]+(\\.[0-9]+)?$"},
    })},
    "comparison": {"anyOf": [{"type": "null"}, obj({
        "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,63}$"},
        "op": {"type": "string", "enum": ["difference", "percent_change"]},
        "metric": {"type": "string", "enum": list(METRICS)},
        "base_period": {"type": "integer", "minimum": 0, "maximum": 2},
        "target_period": {"type": "integer", "minimum": 0, "maximum": 2},
    })]},
    "uncovered": {"type": "array", "items": {"type": "string"}},
    "clarification": {"type": "string"},
})
REVIEW_SCHEMA = obj({"ok": {"type": "boolean"}, "missing": {"type": "array", "items": {"type": "string"}}})

from .crm_query import CRM_PLAN_SCHEMA
PLAN_SCHEMA["properties"]["crm"] = {"anyOf": [{"type": "null"}, CRM_PLAN_SCHEMA]}
PLAN_SCHEMA["required"].append("crm")
