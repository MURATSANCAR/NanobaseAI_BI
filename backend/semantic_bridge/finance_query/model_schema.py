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
    "order_by": {"anyOf": [{"type": "null"}, {"type": "string", "enum": list(METRICS)}]},
    "descending": {"type": "boolean"},
    "uncovered": {"type": "array", "items": {"type": "string"}},
    "clarification": {"type": "string"},
})
REVIEW_SCHEMA = obj({"ok": {"type": "boolean"}, "missing": {"type": "array", "items": {"type": "string"}}})
