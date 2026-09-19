"""Candidates from the CRM's saved views: a Turkish name over a FetchXML filter.

'4 - YK Onayında Bekleyen Sözleşmeler' → new_sozlesme: statecode = 0 AND new_sozlesmestatusu = 4.
The name is the business's own word for that state; the filter is its definition.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Iterator, Optional

from semantic_layer.models import SemanticType
from semantic_layer.rule_miner.common import Candidate, Catalog, clean_view_name, norm_value, sql_values, usable_term

_SIMPLE_OPS = {"eq": "IN", "in": "IN", "ne": "NOT IN", "not-in": "NOT IN"}
_STATE_FIRST = ("statuscode", "statecode")


def parse_fetch(xml: str) -> Optional[tuple[str, list[tuple[str, str, list[str]]], list[str]]]:
    """→ (entity, [(attribute, operator, values)], [unsupported operators])."""
    try:
        root = ET.fromstring(xml or "")
    except ET.ParseError:
        return None
    ent = root.find("entity")
    if ent is None or not ent.get("name"):
        return None
    conds: list[tuple[str, str, list[str]]] = []
    other: list[str] = []
    for flt in ent.findall("filter"):
        if (flt.get("type") or "and").lower() != "and":
            other.append("or-filter")
            continue
        for c in flt.findall("condition"):
            attr, op = c.get("attribute") or "", (c.get("operator") or "").lower()
            if not attr:
                continue
            if op in _SIMPLE_OPS:
                vals = [c.get("value")] if c.get("value") is not None else [v.text for v in c.findall("value") if v.text]
                vals = [norm_value(str(v)) for v in vals if v is not None and str(v).strip()]
                if vals:
                    conds.append((attr, _SIMPLE_OPS[op], vals))
                    continue
            other.append(op)
    return ent.get("name"), conds, other


def candidates(name: str, fetch_xml: str, catalog: Catalog, *, source_kind: str = "saved_query") -> list[Candidate]:
    parsed = parse_fetch(fetch_xml)
    if parsed is None:
        return []
    entity, conds, other = parsed
    term = clean_view_name(name)
    if not usable_term(term) or other:
        return []                                              # a view with a filter we cannot express is not a definition
    prof = catalog.crm(entity)
    if prof is None:
        return []
    conds = [c for c in conds if Catalog.has_column(prof, c[0])]
    if not conds:
        return []
    # GUID values (owner = current user, a specific product list) are a person's list, not a business state.
    if any(re.fullmatch(r"\{?[0-9a-fA-F-]{36}\}?", v) for _, _, vals in conds for v in vals):
        return []
    conds.sort(key=lambda c: (c[0].lower() not in _STATE_FIRST, c[0]))
    head, *rest = conds
    extra = [f"{prof.entity}.{a.upper()} {op} ({sql_values(vals)})" for a, op, vals in rest]
    return [Candidate(term, SemanticType.DIMENSION_VALUE, prof.entity, prof.table_pattern, head[0].upper(), head[1], head[2],
                      conditions=extra, source=f"{source_kind}:{name}", kind=source_kind, schema=prof.schema_name or "")]


def fetch(connector) -> list[tuple[str, str, str]]:
    """(kind, name, fetchxml) for the customizable system views and every personal view."""
    sql = ("SELECT 'saved_query' AS kind, Name, FetchXml FROM SavedQueryBase WHERE StateCode = 0 AND FetchXml IS NOT NULL "
           "AND IsCustomizable = 1 AND QueryType = 0 "
           "UNION ALL SELECT 'user_query', Name, FetchXml FROM UserQueryBase WHERE FetchXml IS NOT NULL")
    _, rows, _ = connector.execute(sql, 20000)
    return [(r["kind"], r["Name"] or "", r["FetchXml"] or "") for r in rows]
