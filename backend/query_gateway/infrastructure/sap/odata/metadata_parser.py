"""OData $metadata parser + fingerprint."""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from typing import Any

from query_gateway.infrastructure.sap import PUBLISHED_ONLY

# Common OData/EDMX namespaces
_NS = {
    "edmx": "http://docs.oasis-open.org/odata/ns/edmx",
    "edm": "http://docs.oasis-open.org/odata/ns/edm",
    "edm4": "http://docs.oasis-open.org/odata/ns/edm",
    "sap": "http://www.sap.com/Protocols/SAPData",
}


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def parse_metadata_xml(xml_text: str, *, service_name: str = "", api_version: str = "V4") -> dict[str, Any]:
    root = ET.fromstring(xml_text)
    entity_sets: list[dict[str, Any]] = []
    entity_types: dict[str, dict[str, Any]] = {}

    for el in root.iter():
        name = _local(el.tag)
        if name == "EntityType":
            et_name = el.attrib.get("Name") or ""
            props = []
            keys: list[str] = []
            for child in el:
                cname = _local(child.tag)
                if cname == "Property":
                    props.append(
                        {
                            "name": child.attrib.get("Name"),
                            "type": child.attrib.get("Type"),
                            "nullable": child.attrib.get("Nullable", "true").lower() != "false",
                            "maxLength": child.attrib.get("MaxLength"),
                            "precision": child.attrib.get("Precision"),
                            "scale": child.attrib.get("Scale"),
                            "sap:label": child.attrib.get(
                                "{http://www.sap.com/Protocols/SAPData}label"
                            )
                            or child.attrib.get("sap:label"),
                            "sap:unit": child.attrib.get(
                                "{http://www.sap.com/Protocols/SAPData}unit"
                            ),
                            "sap:semantics": child.attrib.get(
                                "{http://www.sap.com/Protocols/SAPData}semantics"
                            ),
                        }
                    )
                elif cname == "Key":
                    for pref in child:
                        if _local(pref.tag) == "PropertyRef":
                            keys.append(pref.attrib.get("Name") or "")
                elif cname == "NavigationProperty":
                    props.append(
                        {
                            "name": child.attrib.get("Name"),
                            "type": "Navigation",
                            "partner": child.attrib.get("Partner"),
                            "nullable": True,
                        }
                    )
            entity_types[et_name] = {"name": et_name, "keys": keys, "properties": props}
        elif name == "EntitySet":
            entity_sets.append(
                {
                    "name": el.attrib.get("Name"),
                    "entityType": el.attrib.get("EntityType"),
                    "status": PUBLISHED_ONLY,
                }
            )

    fingerprint = compute_metadata_fingerprint(
        service_name=service_name,
        entity_sets=entity_sets,
        entity_types=entity_types,
        api_version=api_version,
    )
    return {
        "serviceName": service_name,
        "odataVersion": api_version,
        "entitySets": entity_sets,
        "entityTypes": entity_types,
        "fingerprint": fingerprint,
    }


def compute_metadata_fingerprint(
    *,
    service_name: str,
    entity_sets: list[dict[str, Any]],
    entity_types: dict[str, dict[str, Any]],
    api_version: str,
    annotations: str = "",
) -> str:
    parts = [
        service_name,
        api_version,
        repr(sorted((e.get("name") or "") for e in entity_sets)),
    ]
    for et_name in sorted(entity_types.keys()):
        et = entity_types[et_name]
        prop_sig = sorted(
            f"{p.get('name')}:{p.get('type')}:{p.get('nullable')}" for p in et.get("properties") or []
        )
        parts.append(et_name + "|" + ",".join(et.get("keys") or []) + "|" + ";".join(prop_sig))
    parts.append(annotations)
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest


def filter_published_entities(
    metadata: dict[str, Any],
    allowed_entity_sets: set[str] | list[str] | None,
) -> dict[str, Any]:
    """Only allowed + PUBLISHED entity sets enter the catalog."""
    allowed = {a.lower() for a in (allowed_entity_sets or [])}
    sets = []
    for es in metadata.get("entitySets") or []:
        name = (es.get("name") or "").lower()
        if es.get("status") != PUBLISHED_ONLY:
            continue
        if allowed and name not in allowed:
            continue
        sets.append(es)
    out = dict(metadata)
    out["entitySets"] = sets
    return out


_CURRENCY_HINT = re.compile(r"currency|Curr", re.I)
_UNIT_HINT = re.compile(r"unit|UnitOfMeasure|BaseUnit", re.I)


def extract_measure_annotations(entity_type: dict[str, Any]) -> dict[str, Any]:
    currency_fields = []
    unit_fields = []
    amount_fields = []
    for p in entity_type.get("properties") or []:
        name = str(p.get("name") or "")
        sem = str(p.get("sap:semantics") or "")
        typ = str(p.get("type") or "")
        if "currency" in sem.lower() or _CURRENCY_HINT.search(name):
            currency_fields.append(name)
        if "unit" in sem.lower() or _UNIT_HINT.search(name):
            unit_fields.append(name)
        if "Decimal" in typ and ("Amount" in name or "amount" in name):
            amount_fields.append(name)
    return {
        "currencyFields": currency_fields,
        "unitFields": unit_fields,
        "amountFields": amount_fields,
    }
