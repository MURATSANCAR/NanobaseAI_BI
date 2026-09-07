"""Schema introspection for Nanobase API (via Query Gateway datasources / local RO)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import psycopg2
import psycopg2.extras


# How many relations one schema response carries. ERP schemas run to thousands of tables; the cap
# exists to keep a single HTTP response finite, and the response says when it bit. There is no cap
# on columns: a Logo table has 100–222 of them, and cutting at 80 hid two thirds of STLINE.
_MAX_TABLES = int(os.environ.get("BI_SCHEMA_API_MAX_TABLES", "2000") or "2000")


def _pg_connect(cfg: dict[str, Any]):
    pw = cfg.get("password") or ""
    if not pw and cfg.get("password_file"):
        pw = Path(cfg["password_file"]).read_text(encoding="utf-8").strip()
    return psycopg2.connect(
        host=cfg["host"],
        port=int(cfg.get("port") or 5432),
        dbname=cfg.get("database") or cfg.get("dbname") or "postgres",
        user=cfg["user"],
        password=pw,
        sslmode=cfg.get("sslmode") or "prefer",
        connect_timeout=10,
    )


def _datasource_cfg(datasource_id: str) -> dict[str, Any] | None:
    from nanobase_api.infrastructure.datasource_registry import resolve_pg_connect_cfg

    return resolve_pg_connect_cfg(datasource_id)


def format_column_type(
    *,
    data_type: str,
    udt_name: str | None = None,
    character_maximum_length: Optional[int] = None,
    numeric_precision: Optional[int] = None,
    numeric_scale: Optional[int] = None,
    datetime_precision: Optional[int] = None,
) -> str:
    """Human-readable SQL type: varchar(50), numeric(18,2), timestamp(6), …"""
    dt = (data_type or "text").strip().lower()
    udt = (udt_name or "").strip().lower()
    char_len = character_maximum_length
    prec = numeric_precision
    scale = numeric_scale
    dt_prec = datetime_precision

    if char_len is not None:
        if "text" in dt or udt in ("text", "citext"):
            return "citext" if udt == "citext" else "text"
        if udt == "bpchar" or dt in ("character", "char"):
            return f"char({int(char_len)})"
        if udt == "varchar" or "varying" in dt or dt == "varchar":
            return f"varchar({int(char_len)})"
        return f"{udt or dt}({int(char_len)})"

    if prec is not None and (udt == "numeric" or dt in ("numeric", "decimal") or "numeric" in dt):
        if scale is not None and int(scale) > 0:
            return f"numeric({int(prec)},{int(scale)})"
        return f"numeric({int(prec)})"

    if dt_prec is not None and any(x in dt for x in ("timestamp", "time", "interval")):
        # Avoid noisy timestamp(6) without timezone label when udt is clearer
        base = udt or dt.replace(" without time zone", "").replace(" with time zone", "tz")
        if "timestamptz" in udt or "with time zone" in dt:
            return f"timestamptz({int(dt_prec)})"
        if "timestamp" in dt or udt.startswith("timestamp"):
            return f"timestamp({int(dt_prec)})"
        if "time" in dt:
            return f"time({int(dt_prec)})"

    if udt in ("int2", "int4", "int8", "bool", "uuid", "json", "jsonb", "bytea", "date"):
        return {
            "int2": "smallint",
            "int4": "integer",
            "int8": "bigint",
            "bool": "boolean",
        }.get(udt, udt)

    return udt or dt


def _column_payload(c: dict[str, Any]) -> dict[str, Any]:
    char_len = c.get("character_maximum_length")
    prec = c.get("numeric_precision")
    scale = c.get("numeric_scale")
    dt_prec = c.get("datetime_precision")
    data_type = str(c.get("data_type") or "text")
    udt = str(c.get("udt_name") or "") or None
    # information_schema fills numeric_precision for ints too — only expose for numeric/decimal
    is_numeric = (udt == "numeric") or data_type.lower() in ("numeric", "decimal")
    max_length = int(char_len) if char_len is not None else None
    precision = int(prec) if prec is not None and is_numeric else None
    scale_i = int(scale) if scale is not None and is_numeric else None
    datetime_prec = int(dt_prec) if dt_prec is not None else None
    type_display = format_column_type(
        data_type=data_type,
        udt_name=udt,
        character_maximum_length=max_length,
        numeric_precision=precision,
        numeric_scale=scale_i,
        datetime_precision=datetime_prec,
    )
    return {
        "name": c["column_name"],
        "type": data_type,
        "udt_name": udt,
        "type_display": type_display,
        "nullable": c.get("is_nullable") == "YES",
        "max_length": max_length,
        "character_maximum_length": max_length,
        "precision": precision,
        "numeric_precision": precision,
        "scale": scale_i,
        "numeric_scale": scale_i,
        "datetime_precision": datetime_prec,
    }


def fetch_schema(datasource_id: str) -> dict[str, Any]:
    cfg = _datasource_cfg(datasource_id)
    if not cfg:
        return {
            "tables": [],
            "dialect": "postgresql",
            "source_id": datasource_id,
            "graph": {"nodes": [], "edges": []},
            "error": "datasource not configured for schema introspection",
        }

    conn = _pg_connect(cfg)
    try:
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT table_schema, table_name, table_type
                FROM information_schema.tables
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                  AND table_type IN ('BASE TABLE', 'VIEW')
                ORDER BY table_schema, table_name
                LIMIT %s
                """,
                (_MAX_TABLES + 1,),
            )
            rels = list(cur.fetchall())
            # Ask for one more than we will return, so the caller can be told the list is cut
            # instead of reading a truncated catalogue as the whole database.
            truncated = len(rels) > _MAX_TABLES
            rels = rels[:_MAX_TABLES]
            tables: list[dict[str, Any]] = []
            nodes: list[dict[str, Any]] = []
            for rel in rels:
                sch, name = rel["table_schema"], rel["table_name"]
                cur.execute(
                    """
                    SELECT column_name, data_type, udt_name, is_nullable,
                           character_maximum_length, numeric_precision, numeric_scale,
                           datetime_precision
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (sch, name),
                )
                cols = [_column_payload(c) for c in cur.fetchall()]
                fq = f"{sch}.{name}" if sch != "public" else name
                tables.append(
                    {
                        "name": name,
                        "schema": sch,
                        "full_name": fq,
                        "table_type": rel["table_type"],
                        "columns": cols,
                    }
                )
                nodes.append(
                    {
                        "id": fq,
                        "label": fq,
                        "type": "table",
                        "columns": cols,
                    }
                )
        return {
            "tables": tables,
            "dialect": "postgresql",
            "source_id": datasource_id,
            "table_count": len(tables),
            "table_list_truncated": truncated,
            "graph": {"nodes": nodes, "edges": []},
            "engine": "nanobase_api",
        }
    finally:
        conn.close()
