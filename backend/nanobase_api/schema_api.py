"""Schema introspection for Nanobase API (via Query Gateway datasources / local RO)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras


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
                LIMIT 300
                """
            )
            rels = list(cur.fetchall())
            tables: list[dict[str, Any]] = []
            nodes: list[dict[str, Any]] = []
            for rel in rels:
                sch, name = rel["table_schema"], rel["table_name"]
                cur.execute(
                    """
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position
                    LIMIT 80
                    """,
                    (sch, name),
                )
                cols = [
                    {
                        "name": c["column_name"],
                        "type": c["data_type"],
                        "nullable": c["is_nullable"] == "YES",
                    }
                    for c in cur.fetchall()
                ]
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
                nodes.append({"id": fq, "label": fq, "type": "table"})
        return {
            "tables": tables,
            "dialect": "postgresql",
            "source_id": datasource_id,
            "table_count": len(tables),
            "graph": {"nodes": nodes, "edges": []},
            "engine": "nanobase_api",
        }
    finally:
        conn.close()
