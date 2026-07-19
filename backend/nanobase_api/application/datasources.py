"""Datasource use cases."""

from __future__ import annotations

import re
import time
from typing import Any

import psycopg2

from nanobase_api.auth.principal import RequestPrincipal
from nanobase_api.errors import ApiError
from nanobase_api.infrastructure.audit_repo import AuditRepository
from nanobase_api.infrastructure.secret_store import FileVaultSecretStore
from nanobase_api.infrastructure.sources_repo import SourcesRepository

_BLOCKED_HOSTS = re.compile(
    r"^(localhost|127\.|0\.0\.0\.0|10\.|192\.168\.|169\.254\.|::1|metadata\.google)",
    re.I,
)


def _public_source(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "label": row["label"],
        "driver": row["driver"],
        "dialect": row["dialect"],
        "host": row["host"],
        "port": row["port"],
        "database": row["database"],
        "username": row["username"],
        "ssl": bool(row["ssl"]),
        "secret_ref": row.get("secret_ref"),
        "tenant_id": row["tenant_id"],
        "project_id": row.get("project_id") or "default",
        "password_masked": "********" if row.get("secret_ref") else None,
        "last_test_ok": row.get("last_test_ok"),
        "last_test_at": row.get("last_test_at").isoformat() if row.get("last_test_at") else None,
        "deployment": "cloud",
    }


class DatasourceService:
    def __init__(
        self,
        sources: SourcesRepository,
        secrets: FileVaultSecretStore,
        audit: AuditRepository,
    ) -> None:
        self.sources = sources
        self.secrets = secrets
        self.audit = audit

    def list_sources(self, principal: RequestPrincipal) -> dict[str, Any]:
        rows = self.sources.list(tenant_id=principal.tenant_id)
        return {"active_id": None, "sources": [_public_source(r) for r in rows]}

    def get_source(self, principal: RequestPrincipal, datasource_id: str) -> dict[str, Any]:
        return _public_source(self.sources.get(tenant_id=principal.tenant_id, datasource_id=datasource_id))

    def upsert_source(self, principal: RequestPrincipal, datasource_id: str, body: dict[str, Any]) -> dict[str, Any]:
        host = str(body.get("host") or "").strip()
        # Allow loopback for our own reporting/meta infra; block SSRF to cloud metadata
        if host and re.match(r"^(169\.254\.|metadata\.google)", host, re.I):
            raise ApiError("VALIDATION_ERROR", "Host engellendi (SSRF).", status_code=400)

        password = body.get("password")
        secret_ref = body.get("secret_ref")
        if password:
            secret_ref = self.secrets.store_datasource_password(
                tenant_id=principal.tenant_id,
                datasource_id=datasource_id,
                password=str(password),
            )

        row = self.sources.upsert(
            tenant_id=principal.tenant_id,
            datasource_id=datasource_id,
            label=str(body.get("label") or body.get("name") or datasource_id),
            driver=str(body.get("driver") or body.get("databaseType") or "postgresql").lower(),
            dialect=str(body.get("dialect") or "postgresql").lower(),
            host=host or "127.0.0.1",
            port=int(body.get("port") or 5432),
            database=str(body.get("database") or body.get("database_name") or ""),
            username=str(body.get("username") or ""),
            secret_ref=secret_ref,
            ssl=bool(body.get("ssl") or str(body.get("sslMode") or "").upper() == "REQUIRE"),
            project_id=str(body.get("project_id") or "default"),
        )
        self.audit.record(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            action="DATASOURCE_CREATED",
            ok=True,
            extra={"datasource_id": datasource_id, "host": host},
        )
        return {"ok": True, "id": datasource_id, "source": _public_source(row)}

    def delete_source(self, principal: RequestPrincipal, datasource_id: str) -> dict[str, Any]:
        self.sources.delete(tenant_id=principal.tenant_id, datasource_id=datasource_id)
        self.audit.record(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            action="DATASOURCE_DELETED",
            ok=True,
            extra={"datasource_id": datasource_id},
        )
        return {"ok": True}

    def test_connection(self, principal: RequestPrincipal, datasource_id: str) -> dict[str, Any]:
        t0 = time.time()
        row = self.sources.get(tenant_id=principal.tenant_id, datasource_id=datasource_id)
        if row["driver"] not in ("postgresql", "postgres"):
            raise ApiError(
                "DATASOURCE_CONNECTION_FAILED",
                "Connection test şu an yalnız PostgreSQL için destekleniyor.",
                status_code=400,
            )
        try:
            password = self.secrets.resolve(row["secret_ref"] or "")
        except Exception as e:
            self.audit.record(
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                action="DATASOURCE_CONNECTION_TESTED",
                ok=False,
                error=str(e)[:200],
                extra={"datasource_id": datasource_id},
            )
            raise ApiError("DATASOURCE_CONNECTION_FAILED", "Secret çözülemedi.", status_code=400) from e

        try:
            conn = psycopg2.connect(
                host=row["host"],
                port=int(row["port"]),
                dbname=row["database"],
                user=row["username"],
                password=password,
                connect_timeout=5,
                sslmode="require" if row["ssl"] else "prefer",
            )
            try:
                cur = conn.cursor()
                cur.execute("SELECT 1, version()")
                ver = cur.fetchone()[1]
                cur.close()
            finally:
                conn.close()
            latency = int((time.time() - t0) * 1000)
            self.sources.mark_test(tenant_id=principal.tenant_id, datasource_id=datasource_id, ok=True)
            self.audit.record(
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                action="DATASOURCE_CONNECTION_TESTED",
                ok=True,
                duration_ms=latency,
                extra={"datasource_id": datasource_id},
            )
            return {
                "success": True,
                "ok": True,
                "databaseType": "POSTGRESQL",
                "databaseVersion": str(ver)[:120],
                "latencyMs": latency,
            }
        except Exception as e:
            self.sources.mark_test(tenant_id=principal.tenant_id, datasource_id=datasource_id, ok=False)
            self.audit.record(
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                action="DATASOURCE_CONNECTION_TESTED",
                ok=False,
                error=str(e)[:200],
                extra={"datasource_id": datasource_id},
            )
            raise ApiError(
                "DATASOURCE_CONNECTION_FAILED",
                "Veritabanı bağlantı testi başarısız.",
                status_code=400,
            ) from e
