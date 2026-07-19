"""Schema scan persistence."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from nanobase_api.errors import ApiError


class SchemaScanRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create(self, *, tenant_id: str, datasource_id: str) -> dict[str, Any]:
        scan_id = str(uuid.uuid4())
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO bi_schema_scans (id, tenant_id, datasource_id, status, created_at)
                    VALUES (:id, :tenant_id, :datasource_id, 'QUEUED', NOW())
                    """
                ),
                {"id": scan_id, "tenant_id": tenant_id, "datasource_id": datasource_id},
            )
        return self.get(tenant_id=tenant_id, scan_id=scan_id)

    def get(self, *, tenant_id: str, scan_id: str) -> dict[str, Any]:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT id, tenant_id, datasource_id, status, schema_count, table_count,
                           column_count, relationship_count, indexed_document_count,
                           skipped_document_count, error, started_at, completed_at, created_at
                    FROM bi_schema_scans
                    WHERE id = :id AND tenant_id = :tenant_id
                    """
                ),
                {"id": scan_id, "tenant_id": tenant_id},
            ).mappings().first()
        if not row:
            raise ApiError("SCHEMA_SCAN_FAILED", "Schema scan bulunamadı.", status_code=404)
        return dict(row)

    def mark_running(self, scan_id: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE bi_schema_scans
                    SET status = 'RUNNING', started_at = NOW()
                    WHERE id = :id
                    """
                ),
                {"id": scan_id},
            )

    def mark_completed(self, scan_id: str, report: dict[str, Any]) -> None:
        counts = report.get("document_type_counts") or {}
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE bi_schema_scans SET
                      status = 'COMPLETED',
                      completed_at = NOW(),
                      schema_count = :schema_count,
                      table_count = :table_count,
                      column_count = :column_count,
                      relationship_count = :relationship_count,
                      indexed_document_count = :indexed,
                      skipped_document_count = :skipped,
                      error = NULL
                    WHERE id = :id
                    """
                ),
                {
                    "id": scan_id,
                    "schema_count": len(report.get("schemas") or []) or None,
                    "table_count": report.get("tables_scanned"),
                    "column_count": counts.get("COLUMN"),
                    "relationship_count": counts.get("RELATIONSHIP"),
                    "indexed": report.get("upserted") or report.get("documents_total"),
                    "skipped": report.get("skipped_unchanged"),
                },
            )

    def mark_failed(self, scan_id: str, error: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE bi_schema_scans
                    SET status = 'FAILED', completed_at = NOW(), error = :error
                    WHERE id = :id
                    """
                ),
                {"id": scan_id, "error": error[:2000]},
            )

    def has_running(self, *, tenant_id: str, datasource_id: str) -> bool:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT 1 FROM bi_schema_scans
                    WHERE tenant_id = :t AND datasource_id = :d
                      AND status IN ('QUEUED', 'RUNNING')
                    LIMIT 1
                    """
                ),
                {"t": tenant_id, "d": datasource_id},
            ).first()
        return row is not None
