"""Tenant-scoped bi_sources repository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from nanobase_api.errors import ApiError


class SourcesRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list(self, *, tenant_id: str) -> list[dict[str, Any]]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT id, label, driver, dialect, host, port, database,
                           username, ssl, secret_ref, tenant_id, project_id,
                           last_test_ok, last_test_at, created_at, updated_at
                    FROM bi_sources
                    WHERE tenant_id = :tenant_id
                    ORDER BY label
                    """
                ),
                {"tenant_id": tenant_id},
            ).mappings()
            return [dict(r) for r in rows]

    def get(self, *, tenant_id: str, datasource_id: str) -> dict[str, Any]:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT id, label, driver, dialect, host, port, database,
                           username, ssl, secret_ref, tenant_id, project_id,
                           last_test_ok, last_test_at, created_at, updated_at
                    FROM bi_sources
                    WHERE tenant_id = :tenant_id AND id = :id
                    """
                ),
                {"tenant_id": tenant_id, "id": datasource_id},
            ).mappings().first()
        if not row:
            raise ApiError("DATASOURCE_NOT_FOUND", "Datasource bulunamadı.", status_code=404)
        return dict(row)

    def upsert(
        self,
        *,
        tenant_id: str,
        datasource_id: str,
        label: str,
        driver: str,
        dialect: str,
        host: str,
        port: int,
        database: str,
        username: str,
        secret_ref: str | None,
        ssl: bool,
        project_id: str = "default",
    ) -> dict[str, Any]:
        # ensure tenant exists
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO bi_tenants (id, name, status, created_at, updated_at)
                    VALUES (:id, :name, 'active', NOW(), NOW())
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {"id": tenant_id, "name": tenant_id},
            )
            masked = f"{driver}://{username}:***@{host}:{port}/{database}"
            conn.execute(
                text(
                    """
                    INSERT INTO bi_sources (
                      id, tenant_id, project_id, label, driver, host, port, database,
                      username, secret_ref, ssl, dialect, connection_url_masked,
                      created_at, updated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :label, :driver, :host, :port, :database,
                      :username, :secret_ref, :ssl, :dialect, :masked,
                      NOW(), NOW()
                    )
                    ON CONFLICT (tenant_id, id) DO UPDATE SET
                      label = EXCLUDED.label,
                      driver = EXCLUDED.driver,
                      host = EXCLUDED.host,
                      port = EXCLUDED.port,
                      database = EXCLUDED.database,
                      username = EXCLUDED.username,
                      secret_ref = COALESCE(EXCLUDED.secret_ref, bi_sources.secret_ref),
                      ssl = EXCLUDED.ssl,
                      dialect = EXCLUDED.dialect,
                      connection_url_masked = EXCLUDED.connection_url_masked,
                      updated_at = NOW()
                    """
                ),
                {
                    "id": datasource_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "label": label,
                    "driver": driver,
                    "host": host,
                    "port": port,
                    "database": database,
                    "username": username,
                    "secret_ref": secret_ref,
                    "ssl": ssl,
                    "dialect": dialect,
                    "masked": masked,
                },
            )
        return self.get(tenant_id=tenant_id, datasource_id=datasource_id)

    def delete(self, *, tenant_id: str, datasource_id: str) -> None:
        with self._engine.begin() as conn:
            res = conn.execute(
                text("DELETE FROM bi_sources WHERE tenant_id = :t AND id = :id"),
                {"t": tenant_id, "id": datasource_id},
            )
            if res.rowcount == 0:
                raise ApiError("DATASOURCE_NOT_FOUND", "Datasource bulunamadı.", status_code=404)

    def mark_test(
        self, *, tenant_id: str, datasource_id: str, ok: bool
    ) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE bi_sources
                    SET last_test_ok = :ok, last_test_at = NOW(), updated_at = NOW()
                    WHERE tenant_id = :t AND id = :id
                    """
                ),
                {"ok": ok, "t": tenant_id, "id": datasource_id},
            )
