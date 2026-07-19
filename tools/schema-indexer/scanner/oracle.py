"""Oracle metadata scanner bridge for schema-indexer."""

from __future__ import annotations

from typing import Any


def scan_oracle_for_index(
    conn: Any,
    *,
    datasource_id: str,
    tenant_id: str = "default",
    allowed_owners: list[str] | None = None,
    database_unique_name: str = "",
    container_name: str = "",
    schema_version: str = "",
    semantic_version: str = "8.0.0",
) -> list[dict[str, Any]]:
    """Return Qdrant-ready documents from Oracle ALL_* views."""
    # Import from query_gateway when on PYTHONPATH; otherwise inline minimal path
    try:
        from query_gateway.infrastructure.oracle.metadata_scanner import (
            scan_oracle_metadata,
            to_qdrant_documents,
        )
    except ImportError:
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parents[3] / "backend"
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from query_gateway.infrastructure.oracle.metadata_scanner import (
            scan_oracle_metadata,
            to_qdrant_documents,
        )

    owners = allowed_owners or ["NANOBASE_REPORTING"]
    scan = scan_oracle_metadata(conn, allowed_owners=owners)
    docs = to_qdrant_documents(
        scan,
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        database_unique_name=database_unique_name,
        container_name=container_name,
        schema_version=schema_version,
        semantic_version=semantic_version,
    )
    # Fingerprint / document_key for upsert stability
    for d in docs:
        owner = d.get("owner") or ""
        obj = d.get("object_name") or d.get("synonym_name") or ""
        col = d.get("column_name") or ""
        dtype = d.get("document_type") or "OBJ"
        key = f"{datasource_id}:{dtype}:{owner}.{obj}"
        if col:
            key += f".{col}"
        d["document_key"] = key
        d["schema_name"] = owner
        d["schema"] = owner
        d["table_name"] = obj
        d["table"] = obj
        if col:
            d["column"] = col
    return docs
