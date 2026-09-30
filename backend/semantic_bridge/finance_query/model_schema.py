"""Closed output shapes supplied to the model server, not just described in a prompt."""
from .contracts import METRICS, DIMENSIONS


def obj(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


PLAN_SCHEMA = obj({
    "metrics": {"type": "array", "items": {"type": "string", "enum": list(METRICS)}},
    "dimensions": {"type": "array", "items": {"type": "string", "enum": list(DIMENSIONS)}},
    "sale_kind": {"type": "string", "enum": ["all", "wholesale", "retail"]},
    "filters": {"type": "array", "items": obj({
        "dimension": {"type": "string", "enum": ["book", "channel", "customer", "author", "publisher", "subbrand"]},
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

from copy import deepcopy
from .logo_reports import LOGO_REPORT_SCHEMA
from .crm_reports import CRM_REPORT_SCHEMA

ANALYTIC_SCHEMA = obj({
    "op": {"type": "string", "enum": ["contribution", "top_remainder"]},
    "metric": {"type": "string", "enum": list(METRICS)},
    "group_by": {"type": "array", "items": {"type": "string"}},
    "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,63}$"},
    "limit": {"anyOf": [{"type": "null"}, {"type": "integer", "minimum": 1, "maximum": 100}]},
    "label": {"type": "string"},
})
for field, schema in {
    "logo_report": {"anyOf": [{"type": "null"}, LOGO_REPORT_SCHEMA]},
    "crm_report": {"anyOf": [{"type": "null"}, CRM_REPORT_SCHEMA]},
    "analytics": {"type": "array", "maxItems": 3, "items": ANALYTIC_SCHEMA},
}.items():
    PLAN_SCHEMA["properties"][field] = schema
    PLAN_SCHEMA["required"].append(field)

# Finite nesting: root can hold leaves, but leaves cannot hold more sections.
LEAF_PLAN_SCHEMA = deepcopy(PLAN_SCHEMA)
GAP_SCHEMA = obj({
    "status": {"type": "string", "enum": ["UNSUPPORTED_CAPABILITY", "NEEDS_CLARIFICATION"]},
    "reason": {"type": "string", "minLength": 1, "maxLength": 1200},
})
for field, schema in {
    "sections": {"type": "array", "maxItems": 4, "items": obj({
        "title": {"type": "string", "minLength": 1, "maxLength": 120},
        "question": {"type": "string", "minLength": 1, "maxLength": 3000},
        "plan": LEAF_PLAN_SCHEMA,
    })},
    "gaps": {"type": "array", "maxItems": 20, "items": GAP_SCHEMA},
    "coverage": {"type": "array", "maxItems": 30, "items": obj({
        "requirement": {"type": "string", "minLength": 1, "maxLength": 1200},
        "sections": {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 3}},
        "gap_index": {"anyOf": [{"type": "null"}, {"type": "integer", "minimum": 0, "maximum": 19}]},
    })},
}.items():
    PLAN_SCHEMA["properties"][field] = schema
    PLAN_SCHEMA["required"].append(field)

# Constrain branch choice during generation, before semantic validation. Root
# properties/required/additionalProperties remain the single authoritative shape;
# each anyOf branch only narrows those properties, without dropping invalid data.
_EMPTY_ARRAY = {"type": "array", "maxItems": 0}
_NULL = {"type": "null"}
_EMPTY_TEXT = {"type": "string", "maxLength": 0}
_EXECUTION_ARRAYS = ("metrics", "dimensions", "filters", "derived", "having", "analytics")
_SOURCE_BRANCHES = ("crm", "logo_report", "crm_report")


def _leaf_choices():
    choices = []
    # Metric computation is the only branch with root arithmetic and dimensions.
    choices.append({"type": "object", "properties": {
        **{key: deepcopy(_NULL) for key in _SOURCE_BRANCHES},
        "metrics": {"type": "array", "minItems": 1},
    }})
    # Each source/report carries its own fields, limits and conditions. Two
    # selected sources cannot silently masquerade as one leaf.
    for selected in _SOURCE_BRANCHES:
        choices.append({"type": "object", "properties": {
            **{key: deepcopy(_EMPTY_ARRAY) for key in _EXECUTION_ARRAYS},
            **{key: {"type": "object"} if key == selected else deepcopy(_NULL) for key in _SOURCE_BRANCHES},
            **{key: deepcopy(_NULL) for key in ("comparison", "limit", "order_by")},
        }})
    # A boundary response is allowed without executable metrics; the existing
    # validator still requires an actual clarification/unsupported explanation.
    choices.append({"type": "object", "properties": {
        **{key: deepcopy(_EMPTY_ARRAY) for key in _EXECUTION_ARRAYS},
        **{key: deepcopy(_NULL) for key in (*_SOURCE_BRANCHES, "comparison", "limit", "order_by")},
    }})
    return choices


LEAF_PLAN_SCHEMA["anyOf"] = _leaf_choices()
_single_choices = _leaf_choices()
for choice in _single_choices:
    choice["properties"].update({key: deepcopy(_EMPTY_ARRAY) for key in ("sections", "gaps", "coverage")})
_composite_choice = {"type": "object", "properties": {
    **{key: deepcopy(_EMPTY_ARRAY) for key in (*_EXECUTION_ARRAYS, "uncovered")},
    **{key: deepcopy(_NULL) for key in (*_SOURCE_BRANCHES, "comparison", "limit", "order_by")},
    "clarification": deepcopy(_EMPTY_TEXT),
    "sections": {"type": "array", "minItems": 1, "maxItems": 4},
    "coverage": {"type": "array", "minItems": 1, "maxItems": 30},
}}
PLAN_SCHEMA["anyOf"] = [*_single_choices, _composite_choice]
# A coverage entry targets section(s) OR a gap, never neither or both.
PLAN_SCHEMA["properties"]["coverage"]["items"]["anyOf"] = [
    {"type": "object", "properties": {"sections": {"type": "array", "minItems": 1}, "gap_index": deepcopy(_NULL)}},
    {"type": "object", "properties": {"sections": deepcopy(_EMPTY_ARRAY), "gap_index": {"type": "integer", "minimum": 0, "maximum": 19}}},
]
