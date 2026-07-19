"""HANA schema indexer bridge → query_gateway SAP metadata scanner."""

from __future__ import annotations

from typing import Any


def scan_to_documents(ds: dict[str, Any], *, tenant_id: str = "default") -> list[dict[str, Any]]:
    from query_gateway.infrastructure.sap.hana.metadata_scanner import (
        scan_hana_metadata,
        to_qdrant_documents,
    )

    scan = scan_hana_metadata(ds)
    return to_qdrant_documents(scan, tenant_id=tenant_id)
