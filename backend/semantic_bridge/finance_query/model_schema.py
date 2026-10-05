"""Closed output shapes supplied to the model server, not just described in a prompt."""
from .contracts import METRICS, DIMENSIONS, CODED_DIMENSIONS


def obj(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


PLAN_SCHEMA = obj({
    "metrics": {"type": "array", "items": {"type": "string", "enum": list(METRICS)}},
    "dimensions": {"type": "array", "items": {"type": "string", "enum": list(DIMENSIONS)}},
    "sale_kind": {"type": "string", "enum": ["all", "wholesale", "retail"]},
    "filters": {"type": "array", "items": obj({
        "dimension": {"type": "string", "enum": ["book", "channel", "customer", "author", "publisher", "subbrand", *CODED_DIMENSIONS]},
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
from .relational_plan import RELATIONAL_SCHEMA

ANALYTIC_SCHEMA = obj({
    "op": {"type": "string", "enum": ["contribution", "top_remainder"]},
    "metric": {"type": "string", "enum": list(METRICS)},
    "group_by": {"type": "array", "items": {"type": "string"}},
    "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,63}$"},
    "limit": {"anyOf": [{"type": "null"}, {"type": "integer", "minimum": 1, "maximum": 100}]},
    "label": {"type": "string"},
})
for field, schema in {
    "relational_query": {"anyOf": [{"type": "null"}, RELATIONAL_SCHEMA]},
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

# Every alternative is a complete closed object. The model grammar compiler
# does not reliably intersect sibling properties with partial anyOf constraints.
_EMPTY_ARRAY = {"type": "array", "maxItems": 0}
_NULL = {"type": "null"}
_EXECUTION_ARRAYS = ("metrics", "dimensions", "filters", "derived", "having", "analytics")
_SOURCE_BRANCHES = ("crm", "logo_report", "crm_report", "relational_query")


def _closed_variant(base, changes, late=()):
    properties = deepcopy(base["properties"])
    for key, change in changes.items():
        existing = properties[key]
        if change.get("type") == "object" and "anyOf" in existing:
            # Selecting a source branch must retain its full nested properties.
            existing = next(value for value in existing["anyOf"] if value.get("type") == "object")
        if change.get("type") == "null":
            properties[key] = {"type":"null"}
        else:
            properties[key] = {**deepcopy(existing), **deepcopy(change)}
    if late:
        # `late` keys move to just after the last source branch; every other key keeps its place.
        order = [key for key in properties if key not in late]
        at = order.index("crm_report") + 1
        properties = {key: properties[key] for key in [*order[:at], *late, *order[at:]]}
    return obj(properties)


# Constrained decoding writes properties in schema order. In a non-metric alternative "filters" must
# stay empty, but it came before the source branches: the model wanted to write the question's
# condition there, the grammar allowed only whitespace, and it emitted blank lines until max_tokens
# (2026-10-05, vLLM 0.27.1: «Bu yıl kaç sipariş iptal edildi?» 6/6 PLAN_INVALID, up to 261k chars).
# In those alternatives "filters" now follows the branches; nothing else moves. Measured on 15 CRM
# questions (no-thinking attempt): 0 loops, same branch choice as the original order on every question.
# Moving the other empty arrays back or the branches forward changed the choice (3-8 of 15 went to crm).
_LATE = ("filters",)


def _leaf_variants(base):
    alternatives = [_closed_variant(base, {
        **{key: _NULL for key in _SOURCE_BRANCHES},
        "metrics": {"type":"array", "minItems":1},
    })]
    for selected in _SOURCE_BRANCHES:
        alternatives.append(_closed_variant(base, {
            **{key:_EMPTY_ARRAY for key in _EXECUTION_ARRAYS},
            **{key:{"type":"object"} if key == selected else _NULL for key in _SOURCE_BRANCHES},
            **{key:_NULL for key in ("comparison","limit","order_by")},
        }, late=_LATE))
    alternatives.append(_closed_variant(base, {
        **{key:_EMPTY_ARRAY for key in _EXECUTION_ARRAYS},
        **{key:_NULL for key in (*_SOURCE_BRANCHES,"comparison","limit","order_by")},
    }, late=_LATE))
    return alternatives


_leaf_definition = {"anyOf":_leaf_variants(LEAF_PLAN_SCHEMA)}
# Share the complete leaf alternatives rather than copying their source schemas
# into every root alternative. References resolve in the final request document.
PLAN_SCHEMA["properties"]["sections"]["items"]["properties"]["plan"] = {"$ref":"#/$defs/leaf_plan"}
_coverage_base = PLAN_SCHEMA["properties"]["coverage"]["items"]
PLAN_SCHEMA["properties"]["coverage"]["items"] = {"anyOf":[
    _closed_variant(_coverage_base, {"sections":{"type":"array","minItems":1},"gap_index":_NULL}),
    _closed_variant(_coverage_base, {"sections":_EMPTY_ARRAY,"gap_index":{"type":"integer","minimum":0,"maximum":19}}),
]}
# The integer coverage variant replaces (rather than intersects) the nullable
# source union; its complete type is explicit for constrained decoding.
PLAN_SCHEMA["properties"]["coverage"]["items"]["anyOf"][1]["properties"]["gap_index"] = {"type":"integer","minimum":0,"maximum":19}
_single_base = _closed_variant(PLAN_SCHEMA,{key:_EMPTY_ARRAY for key in ("sections","gaps","coverage")})
_root_alternatives = _leaf_variants(_single_base)
_root_alternatives.append(_closed_variant(PLAN_SCHEMA,{
    **{key:_EMPTY_ARRAY for key in (*_EXECUTION_ARRAYS,"uncovered")},
    **{key:_NULL for key in (*_SOURCE_BRANCHES,"comparison","limit","order_by")},
    "clarification":{"type":"string","maxLength":0},
    "sections":{"type":"array","minItems":1,"maxItems":4},
    "coverage":{"type":"array","minItems":1,"maxItems":30},
}, late=_LATE))
PLAN_SCHEMA = {"type":"object", "anyOf":_root_alternatives, "$defs":{"leaf_plan":_leaf_definition}}
