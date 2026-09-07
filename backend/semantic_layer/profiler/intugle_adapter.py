"""Intugle as an optional discovery plug-in — evidence in, never authority.

What it adds on top of our own profiler: link prediction across tables that share no key naming and no
foreign keys, and an LLM-written business glossary per column. Both are consumed as *evidence*:

    predicted link  → SchemaProfile.relationships + PROFILE evidence on the relationship concept
    glossary text   → ColumnProfile.description  + DOC evidence on concepts that map to that column

Nothing it produces can certify a concept: the Evidence Engine still requires validated queries (or a
documented mapping with a profile fit) before anything becomes CERTIFIED.

It is optional by construction: the package is imported lazily, the pipeline runs identically without it,
and it is expected to live in the offline worker's environment — never in the API's runtime path.
The upstream API is young, so every field is read defensively through the accessors below; when the shape
does not match, the adapter reports what it could not read instead of guessing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from semantic_layer.models import Evidence, EvidenceType, SchemaProfile

log = logging.getLogger(__name__)


@dataclass
class IntugleReport:
    available: bool = False
    ran: bool = False
    links_added: int = 0
    links_seen: int = 0
    glossary_added: int = 0
    evidence: int = 0
    tables: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "ran": self.ran,
            "tables": self.tables,
            "links_seen": self.links_seen,
            "links_added": self.links_added,
            "glossary_added": self.glossary_added,
            "evidence": self.evidence,
            "errors": self.errors[:5],
        }


def available() -> bool:
    try:
        import intugle  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------- defensive accessors

def _attr(obj: Any, *names: str) -> Any:
    for n in names:
        if isinstance(obj, dict) and n in obj:
            return obj[n]
        if hasattr(obj, n):
            return getattr(obj, n)
    return None


def _endpoint(obj: Any) -> tuple[Optional[str], Optional[str]]:
    """A link endpoint may be an object, a dict, or a 'table.column' string."""
    if obj is None:
        return None, None
    if isinstance(obj, str):
        parts = obj.split(".")
        return (parts[-2].upper(), parts[-1].upper()) if len(parts) >= 2 else (obj.upper(), None)
    table = _attr(obj, "table", "table_name", "dataset", "entity", "source_table")
    column = _attr(obj, "column", "column_name", "field", "source_column")
    return (str(table).upper() if table else None, str(column).upper() if column else None)


def _links_of(model: Any) -> list[Any]:
    for name in ("links", "predicted_links", "relationships", "link_predictions"):
        value = _attr(model, name)
        if value:
            return list(value.values()) if isinstance(value, dict) else list(value)
    return []


def _glossary_of(model: Any) -> dict[str, str]:
    value = _attr(model, "glossary", "business_glossary", "column_glossary")
    out: dict[str, str] = {}
    if isinstance(value, dict):
        for k, v in value.items():
            text = v if isinstance(v, str) else (_attr(v, "description", "business_description", "text") or "")
            if text:
                out[str(k).upper()] = str(text)
    elif isinstance(value, Iterable):
        for item in value or []:
            table, column = _endpoint(item)
            text = _attr(item, "description", "business_description", "text")
            if column and text:
                out[f"{table}.{column}" if table else column] = str(text)
    return out


def _entity_of(profiles: list[SchemaProfile], table: Optional[str]) -> Optional[SchemaProfile]:
    if not table:
        return None
    key = table.upper()
    for p in profiles:
        if key in (p.entity.upper(), p.table_name.upper(), p.table_pattern.upper()):
            return p
    return None


# ---------------------------------------------------------------------- run

def run(profiles: list[SchemaProfile], *, datasets: Optional[dict[str, Any]] = None, connection_cfg: Optional[dict[str, Any]] = None, min_confidence: float = 0.8) -> IntugleReport:
    """Build Intugle's semantic model over the same tables we profiled and merge what it discovers.

    `datasets` / `connection_cfg` are passed through to SemanticModel untouched: how a deployment points
    Intugle at its data (files, a DSN, a warehouse) is deployment configuration, not our concern."""
    report = IntugleReport(available=available(), tables=len(profiles))
    if not report.available:
        return report
    try:  # pragma: no cover - exercised through a stub in tests
        from intugle import SemanticModel  # type: ignore

        spec = datasets if datasets is not None else (connection_cfg if connection_cfg is not None else {p.table_name: {"table": p.table_name, "schema": p.schema_name} for p in profiles})
        model = SemanticModel(spec)
        build = _attr(model, "build")
        if callable(build):
            build()
        else:  # some releases expose the stages individually
            for stage in ("profile", "predict_links", "generate_glossary"):
                fn = _attr(model, stage)
                if callable(fn):
                    fn()
        report.ran = True
    except Exception as e:  # noqa: BLE001
        report.errors.append(f"build failed: {str(e)[:200]}")
        log.warning("intugle build failed: %s", e)
        return report

    for link in _links_of(model):
        report.links_seen += 1
        confidence = _attr(link, "confidence", "score", "probability")
        if confidence is not None and float(confidence) < min_confidence:
            continue
        src_table, src_col = _endpoint(_attr(link, "source", "from", "left", "source_table"))
        dst_table, dst_col = _endpoint(_attr(link, "target", "to", "right", "target_table"))
        src, dst = _entity_of(profiles, src_table), _entity_of(profiles, dst_table)
        if not (src and dst and src_col and dst_col):
            continue
        col, ref_col = src.column(src_col), dst.column(dst_col)
        if col is None or ref_col is None:
            continue
        if any(r["column"].upper() == col.name.upper() for r in src.relationships):
            continue
        # store the column names as the source spells them, exactly like our own profiler does
        src.relationships.append({"column": col.name, "ref_entity": dst.entity, "ref_column": ref_col.name, "source": "intugle", "confidence": float(confidence) if confidence is not None else None})
        col.ref_entity, col.ref_column = dst.entity, ref_col.name
        report.links_added += 1

    glossary = _glossary_of(model)
    for key, text in glossary.items():
        table, _, column = key.rpartition(".")
        target = _entity_of(profiles, table) if table else None
        candidates = [target] if target else profiles
        for p in candidates:
            col = p.column(column)
            if col is not None and not col.description:
                # a third party's reading of what the column means — a person's own words override it
                col.add_derived("intugle", text.strip()[:500])
                report.glossary_added += 1
                break
    return report


def attach_evidence(store: Any, tenant_id: str, datasource_id: str, profiles: list[SchemaProfile], report: IntugleReport) -> IntugleReport:
    """Record what Intugle contributed as PROFILE evidence on the matching relationship concepts, so a
    later audit can see which link came from where — and so the engine can weigh it like any other hint."""
    if not report.ran:
        return report
    from semantic_layer.models import SemanticType

    for concept in store.find_concepts(tenant_id, datasource_id, semantic_type=SemanticType.RELATIONSHIP, limit=100000):
        for mapping in store.list_mappings(concept.id):
            prof = _entity_of(profiles, mapping.entity)
            if prof is None or not mapping.column:
                continue
            rel = next((r for r in prof.relationships if r["column"].upper() == mapping.column.upper() and r.get("source") == "intugle"), None)
            if rel is None:
                continue
            store.add_evidence(Evidence(concept.id, EvidenceType.PROFILE, "intugle:link", support_count=1, weight=float(rel.get("confidence") or 0.8), payload={"ref": f'{rel["ref_entity"]}.{rel["ref_column"]}', "confidence": rel.get("confidence")}))
            report.evidence += 1
    return report
