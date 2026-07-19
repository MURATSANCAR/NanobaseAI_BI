"""HANA metadata scanner — allowed schemas/views only."""

from __future__ import annotations

import hashlib
from typing import Any

from query_gateway.infrastructure.sap import FORBIDDEN_RAW_SAP_TABLES, PUBLISHED_ONLY
from query_gateway.infrastructure.sap.hana.pool import acquire, release
from query_gateway.infrastructure.sap.hana.profile import build_hana_profile


def scan_hana_metadata(ds: dict[str, Any], *, timeout_ms: int = 15_000) -> dict[str, Any]:
    cfg = build_hana_profile(ds)
    conn = acquire(cfg, timeout_ms=timeout_ms)
    views: list[dict[str, Any]] = []
    try:
        cur = conn.cursor()
        schema_filter = cfg.allowed_schemas
        if schema_filter:
            placeholders = ",".join(["?"] * len(schema_filter))
            cur.execute(
                f"""
                SELECT SCHEMA_NAME, VIEW_NAME, COMMENTS
                FROM SYS.VIEWS
                WHERE SCHEMA_NAME IN ({placeholders})
                """,
                tuple(schema_filter),
            )
        else:
            cur.execute("SELECT SCHEMA_NAME, VIEW_NAME, COMMENTS FROM SYS.VIEWS")
        for schema, name, comment in cur.fetchall() or []:
            qname = f"{schema}.{name}"
            if name.upper() in FORBIDDEN_RAW_SAP_TABLES:
                continue
            if cfg.allowed_views:
                allowed = {v.upper() for v in cfg.allowed_views}
                if qname.upper() not in allowed and name.upper() not in allowed:
                    continue
            views.append(
                {
                    "schema": schema,
                    "name": name,
                    "qualifiedName": qname,
                    "comment": comment,
                    "status": PUBLISHED_ONLY,
                    "objectType": "VIEW",
                }
            )
        cur.close()
    finally:
        release(cfg, conn)

    fp_src = "|".join(sorted(v["qualifiedName"] for v in views))
    fingerprint = hashlib.sha256(fp_src.encode("utf-8")).hexdigest()
    return {
        "database_type": "SAP_HANA",
        "views": views,
        "fingerprint": fingerprint,
        "datasource_id": cfg.datasource_id,
    }


def to_qdrant_documents(scan: dict[str, Any], *, tenant_id: str = "default") -> list[dict[str, Any]]:
    docs = []
    for v in scan.get("views") or []:
        if v.get("status") != PUBLISHED_ONLY:
            continue
        docs.append(
            {
                "id": f"hana:{v['qualifiedName']}",
                "payload": {
                    "database_type": "SAP_HANA",
                    "schema": v["schema"],
                    "name": v["name"],
                    "qualified_name": v["qualifiedName"],
                    "tenant_id": tenant_id,
                    "status": PUBLISHED_ONLY,
                },
            }
        )
    return docs
