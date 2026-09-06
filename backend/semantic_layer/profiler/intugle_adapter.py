"""Optional Intugle adapter — discovery primitive only (profile / predict_links / glossary).

Intugle is not a runtime dependency: when the package is missing this module reports `available=False`
and the built-in Profiler is used. When present, its link predictions and glossary become PROFILE / DOC
evidence — never certification.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


def available() -> bool:
    try:
        import intugle  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def enrich_profiles(profiles: list, connection_cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run Intugle's SemanticModel (profile → predict_links → generate_glossary) when installed and
    merge predicted links into SchemaProfile.relationships. Returns a report."""
    if not available():
        return {"available": False, "links_added": 0, "glossary": 0}
    try:  # pragma: no cover - optional heavy dependency
        from intugle import SemanticModel  # type: ignore

        model = SemanticModel({p.table_name: {"path": None} for p in profiles}) if not connection_cfg else SemanticModel(connection_cfg)
        model.build()
        added = 0
        for link in getattr(model, "links", []) or []:
            src, dst = getattr(link, "source", None), getattr(link, "target", None)
            if not src or not dst:
                continue
            for p in profiles:
                if p.table_name.upper() == str(getattr(src, "table", "")).upper():
                    rel = {"column": getattr(src, "column", ""), "ref_entity": str(getattr(dst, "table", "")).upper(), "ref_column": getattr(dst, "column", "")}
                    if rel not in p.relationships:
                        p.relationships.append(rel)
                        added += 1
        glossary = 0
        for p in profiles:
            for c in p.columns:
                desc = getattr(model, "glossary", {}).get(f"{p.table_name}.{c.name}") if hasattr(model, "glossary") else None
                if desc and not c.description:
                    c.description = str(desc)
                    glossary += 1
        return {"available": True, "links_added": added, "glossary": glossary}
    except Exception as e:  # noqa: BLE001
        log.warning("intugle enrichment failed: %s", e)
        return {"available": True, "error": str(e)[:200], "links_added": 0, "glossary": 0}
