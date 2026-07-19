"""Datasource use cases."""

from __future__ import annotations

import re
import time
from typing import Any

from nanobase_api.application.connection_probes import (
    load_gateway_datasource,
    map_probe_error,
    row_to_probe_ds,
    run_probe,
)
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

        driver = str(body.get("driver") or body.get("databaseType") or "postgresql").lower()
        connection_url = str(body.get("connection_url") or "").strip()
        # Persist Oracle TNS/EZConnect descriptor in host when provided (no schema change).
        if driver == "oracle" and connection_url.startswith("("):
            host = connection_url
        # OData: prefer explicit URL in connection_url / supabase_url style fields
        if driver in ("odata", "cds", "cds_odata", "sap_s4hana_odata"):
            url = connection_url or str(body.get("base_url") or body.get("supabase_url") or host).strip()
            if url:
                host = url.rstrip("/")

        row = self.sources.upsert(
            tenant_id=principal.tenant_id,
            datasource_id=datasource_id,
            label=str(body.get("label") or body.get("name") or datasource_id),
            driver=driver,
            dialect=str(body.get("dialect") or driver).lower(),
            host=host or "127.0.0.1",
            port=int(body.get("port") or (1521 if driver == "oracle" else 5432)),
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
            extra={"datasource_id": datasource_id, "host": host[:80] if host else ""},
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
        try:
            row = self.sources.get(tenant_id=principal.tenant_id, datasource_id=datasource_id)
        except ApiError as e:
            if e.code == "DATASOURCE_NOT_FOUND":
                return self._test_gateway_registry(principal, datasource_id, t0)
            raise

        driver = str(row.get("driver") or "postgresql").lower()
        try:
            password = self.secrets.resolve(row["secret_ref"] or "") if row.get("secret_ref") else ""
        except Exception as e:
            self._audit_test(principal, datasource_id, ok=False, error=str(e)[:200], t0=t0, db_type=driver)
            raise ApiError("DATASOURCE_CONNECTION_FAILED", "Secret çözülemedi.", status_code=400) from e

        connection_url = ""
        host = str(row.get("host") or "")
        if host.startswith("("):
            connection_url = host

        ds = row_to_probe_ds(row, password, connection_url=connection_url)
        return self._run_and_record(principal, datasource_id, ds, t0, persist_mark=True)

    def _test_gateway_registry(
        self, principal: RequestPrincipal, datasource_id: str, t0: float
    ) -> dict[str, Any]:
        ds = load_gateway_datasource(datasource_id)
        if not ds:
            raise ApiError("DATASOURCE_NOT_FOUND", "Datasource bulunamadı.", status_code=404)
        return self._run_and_record(principal, datasource_id, ds, t0, persist_mark=False)

    def _run_and_record(
        self,
        principal: RequestPrincipal,
        datasource_id: str,
        ds: dict[str, Any],
        t0: float,
        *,
        persist_mark: bool,
    ) -> dict[str, Any]:
        driver = str(ds.get("driver") or ds.get("dialect") or "").lower()
        try:
            meta = run_probe(ds)
            latency = int((time.time() - t0) * 1000)
            if persist_mark:
                self.sources.mark_test(tenant_id=principal.tenant_id, datasource_id=datasource_id, ok=True)
            self._audit_test(
                principal,
                datasource_id,
                ok=True,
                t0=t0,
                latency=latency,
                db_type=meta.get("databaseType") or driver,
            )
            return {
                "success": True,
                "ok": True,
                "databaseType": meta.get("databaseType"),
                "databaseVersion": meta.get("databaseVersion"),
                "latencyMs": latency,
            }
        except ApiError as e:
            if persist_mark:
                try:
                    self.sources.mark_test(
                        tenant_id=principal.tenant_id, datasource_id=datasource_id, ok=False
                    )
                except Exception:
                    pass
            self._audit_test(
                principal, datasource_id, ok=False, error=e.message[:200], t0=t0, db_type=driver
            )
            raise
        except Exception as e:
            err = map_probe_error(e, driver=driver)
            if persist_mark:
                try:
                    self.sources.mark_test(
                        tenant_id=principal.tenant_id, datasource_id=datasource_id, ok=False
                    )
                except Exception:
                    pass
            self._audit_test(
                principal, datasource_id, ok=False, error=str(e)[:200], t0=t0, db_type=driver
            )
            raise err from e

    def _audit_test(
        self,
        principal: RequestPrincipal,
        datasource_id: str,
        *,
        ok: bool,
        t0: float,
        error: str | None = None,
        latency: int | None = None,
        db_type: str | None = None,
    ) -> None:
        duration = latency if latency is not None else int((time.time() - t0) * 1000)
        self.audit.record(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            action="DATASOURCE_CONNECTION_TESTED",
            ok=ok,
            duration_ms=duration,
            error=error,
            extra={"datasource_id": datasource_id, "databaseType": db_type},
        )
