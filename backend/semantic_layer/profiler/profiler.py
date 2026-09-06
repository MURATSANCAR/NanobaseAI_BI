"""Profiler — "what exists in this data world": tables, columns, types, enum values with frequencies,
keys, relationships and Logo table patterns. Output: SchemaProfile rows (sl_schema_profile)."""

from __future__ import annotations

import logging
from typing import Any, Optional

from semantic_layer.models import ColumnProfile, SchemaProfile
from semantic_layer.naming import infer_ref_target, logical_table
from semantic_layer.profiler.connectors import Connector, MDLConnector

log = logging.getLogger(__name__)

_ENUM_TYPES = ("smallint", "tinyint", "int", "integer", "bit", "char", "varchar", "nvarchar", "nchar", "text", "boolean", "bool")
_NEVER_ENUM = ("LOGICALREF", "DATE_", "FTIME", "CAPIBLOCK_", "SITEID", "RECSTATUS", "ORGLOGICREF", "WFSTATUS", "GUID")


def _enum_candidate(col: dict[str, Any]) -> bool:
    name = str(col["name"]).upper()
    if any(name.startswith(x) or name == x for x in _NEVER_ENUM):
        return False
    if name.endswith("REF"):
        return False
    dt = str(col.get("data_type") or "").lower()
    if dt.startswith(("varchar", "nvarchar", "char", "nchar")):
        # short codes only
        import re

        m = re.search(r"\((\d+)\)", dt)
        return bool(m) and int(m.group(1)) <= 25
    return dt.startswith(_ENUM_TYPES)


class Profiler:
    def __init__(self, connector: Connector, *, enum_max_distinct: int = 64, top_n: int = 12, max_tables: int = 300):
        self.c = connector
        self.enum_max_distinct = enum_max_distinct
        self.top_n = top_n
        self.max_tables = max_tables

    def profile(self, datasource_id: str, schema: str = "dbo", like: Optional[str] = None) -> list[SchemaProfile]:
        tables = self.c.list_tables(schema, like)[: self.max_tables]
        fks = self.c.foreign_keys(schema)
        fk_by_table: dict[str, list[dict[str, str]]] = {}
        for fk in fks:
            fk_by_table.setdefault(fk["table"].upper(), []).append(fk)
        out: list[SchemaProfile] = []
        for sch, table in tables:
            lt = logical_table(table, sch)
            pk = self.c.primary_keys(sch, table)
            cols: list[ColumnProfile] = []
            rels: list[dict[str, str]] = []
            for col in self.c.columns(sch, table):
                cp = ColumnProfile(name=col["name"], data_type=str(col.get("data_type") or ""), nullable=bool(col.get("nullable", True)), is_primary_key=col["name"] in pk or bool(col.get("pk")), description=col.get("description"))
                fk = next((f for f in fk_by_table.get(table.upper(), []) if f["column"].upper() == col["name"].upper()), None)
                if fk:
                    cp.ref_entity, cp.ref_column = logical_table(fk["ref_table"]).entity, fk["ref_column"]
                else:
                    inferred = infer_ref_target(col["name"])
                    if inferred:
                        cp.ref_entity, cp.ref_column = inferred
                if cp.ref_entity:
                    rels.append({"column": cp.name, "ref_entity": cp.ref_entity, "ref_column": cp.ref_column or "LOGICALREF"})
                if _enum_candidate(col):
                    try:
                        hint = self.c.distinct_hint(table, col["name"]) if isinstance(self.c, MDLConnector) else None
                        top = self.c.top_values(sch, table, col["name"], self.enum_max_distinct + 1)
                        if top and len(top) <= self.enum_max_distinct:
                            cp.top_values = top[: self.enum_max_distinct]
                            cp.distinct_count = hint if hint is not None else len(top)
                        elif top:
                            cp.top_values = top[: self.top_n]
                            cp.distinct_count = hint if hint is not None else len(top)
                    except Exception as e:  # noqa: BLE001
                        log.debug("top_values failed %s.%s: %s", table, col["name"], e)
                cols.append(cp)
            desc = self.c.table_description(table) if isinstance(self.c, MDLConnector) else None
            out.append(
                SchemaProfile(
                    datasource_id=datasource_id,
                    table_name=table,
                    table_pattern=lt.table_pattern,
                    entity=lt.entity,
                    schema_name=sch,
                    columns=cols,
                    primary_key=pk,
                    relationships=rels,
                    row_count=self.c.row_count(sch, table),
                    description=desc,
                    context=dict(lt.context),
                )
            )
        # drop relationships whose target entity is not profiled (keeps the graph honest)
        entities = {p.entity for p in out}
        for p in out:
            p.relationships = [r for r in p.relationships if r["ref_entity"] in entities]
            for c in p.columns:
                if c.ref_entity and c.ref_entity not in entities:
                    c.ref_entity, c.ref_column = None, None
        return out


def column_index(profiles: list[SchemaProfile]) -> dict[str, set[str]]:
    return {p.entity: {c.name.upper() for c in p.columns} for p in profiles}


def profile_summary(profiles: list[SchemaProfile]) -> dict[str, Any]:
    return {
        "tables": len(profiles),
        "columns": sum(len(p.columns) for p in profiles),
        "enum_columns": sum(1 for p in profiles for c in p.columns if c.is_enum()),
        "relationships": sum(len(p.relationships) for p in profiles),
        "entities": sorted(p.entity for p in profiles),
    }
