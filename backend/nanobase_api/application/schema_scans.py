"""Schema scan use cases + job enqueue."""

from __future__ import annotations

import asyncio
from typing import Any

from nanobase_api.auth.principal import RequestPrincipal
from nanobase_api.config import get_settings
from nanobase_api.errors import ApiError
from nanobase_api.infrastructure.audit_repo import AuditRepository
from nanobase_api.infrastructure.schema_indexer_adapter import SchemaIndexerAdapter
from nanobase_api.infrastructure.schema_scan_repo import SchemaScanRepository
from nanobase_api.infrastructure.sources_repo import SourcesRepository


class SchemaScanService:
    def __init__(
        self,
        scans: SchemaScanRepository,
        sources: SourcesRepository,
        indexer: SchemaIndexerAdapter,
        audit: AuditRepository,
    ) -> None:
        self.scans = scans
        self.sources = sources
        self.indexer = indexer
        self.audit = audit

    def get_status(self, principal: RequestPrincipal, scan_id: str) -> dict[str, Any]:
        row = self.scans.get(tenant_id=principal.tenant_id, scan_id=scan_id)
        return {
            "scanId": row["id"],
            "status": row["status"],
            "datasourceId": row["datasource_id"],
            "schemaCount": row.get("schema_count"),
            "tableCount": row.get("table_count"),
            "columnCount": row.get("column_count"),
            "relationshipCount": row.get("relationship_count"),
            "indexedDocumentCount": row.get("indexed_document_count"),
            "skippedDocumentCount": row.get("skipped_document_count"),
            "error": row.get("error"),
            "startedAt": row["started_at"].isoformat() if row.get("started_at") else None,
            "completedAt": row["completed_at"].isoformat() if row.get("completed_at") else None,
        }

    async def start_scan(self, principal: RequestPrincipal, datasource_id: str) -> dict[str, Any]:
        # tenant ownership when registered; allow known gateway datasources
        try:
            self.sources.get(tenant_id=principal.tenant_id, datasource_id=datasource_id)
        except ApiError as e:
            from nanobase_api.infrastructure.datasource_registry import (
                is_registered_ro_datasource,
            )

            # Allow any secrets-map / local-reporting id — not a fixed name list
            if e.code != "DATASOURCE_NOT_FOUND" or not is_registered_ro_datasource(datasource_id):
                raise
        if self.scans.has_running(tenant_id=principal.tenant_id, datasource_id=datasource_id):
            raise ApiError(
                "SCHEMA_SCAN_ALREADY_RUNNING",
                "Bu datasource için zaten bir scan çalışıyor.",
                status_code=409,
            )
        scan = self.scans.create(tenant_id=principal.tenant_id, datasource_id=datasource_id)
        self.audit.record(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            action="SCHEMA_SCAN_REQUESTED",
            ok=True,
            extra={"scan_id": scan["id"], "datasource_id": datasource_id},
        )
        await self._enqueue(scan["id"], datasource_id, principal.tenant_id)
        return {"scanId": scan["id"], "status": "QUEUED"}

    async def _enqueue(self, scan_id: str, datasource_id: str, tenant_id: str) -> None:
        settings = get_settings()
        if settings.arq_enabled:
            try:
                from arq import create_pool
                from arq.connections import RedisSettings

                redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
                try:
                    await redis.enqueue_job(
                        "run_schema_scan",
                        scan_id,
                        datasource_id,
                        tenant_id,
                    )
                    return
                finally:
                    await redis.close()
            except Exception:
                pass
        # Fallback: non-blocking asyncio task (HTTP returns immediately)
        asyncio.create_task(self._run_inline(scan_id, datasource_id, tenant_id))

    async def _run_inline(self, scan_id: str, datasource_id: str, tenant_id: str) -> None:
        await asyncio.to_thread(execute_schema_scan, scan_id, datasource_id, tenant_id)


def _enqueue_scenario_build_after_scan(*, tenant_id: str, datasource_id: str) -> None:
    """Fire-and-forget scenario build (ARQ or thread)."""
    import threading

    build_id = f"build-scan-{datasource_id}"[:64]

    def _run() -> None:
        from nanobase_api.scenario_engine.application.build_pipeline import start_build
        from nanobase_api.scenario_engine.infrastructure.reporting_exec import reporting_dsn
        from nanobase_api.scenario_engine.infrastructure.schema_snapshot import (
            invoice_analytics_snapshot,
            snapshot_from_pg,
        )
        from nanobase_api.scenario_engine.infrastructure.store import get_scenario_store

        store = get_scenario_store()
        snap = None
        dsn = reporting_dsn()
        if dsn:
            try:
                snap = snapshot_from_pg(dsn, datasource_id=datasource_id)
            except Exception:
                snap = invoice_analytics_snapshot()
        else:
            snap = invoice_analytics_snapshot()
        start_build(
            tenant_id=tenant_id,
            datasource_id=datasource_id,
            store=store,
            snapshot=snap,
            auto_publish=True,
            force=True,
        )

    settings = get_settings()
    if settings.arq_enabled:
        try:
            import asyncio

            async def _arq() -> None:
                from arq import create_pool
                from arq.connections import RedisSettings

                redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
                try:
                    await redis.enqueue_job(
                        "run_scenario_build",
                        build_id,
                        datasource_id,
                        tenant_id,
                        True,
                    )
                finally:
                    await redis.close()

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(_arq())
                else:
                    loop.run_until_complete(_arq())
                return
            except Exception:
                pass
        except Exception:
            pass
    threading.Thread(target=_run, name=f"scenario-build-{datasource_id}", daemon=True).start()


def execute_schema_scan(scan_id: str, datasource_id: str, tenant_id: str) -> None:
    """Called by ARQ worker or inline task."""
    from nanobase_api.db import get_sync_engine

    engine = get_sync_engine()
    scans = SchemaScanRepository(engine)
    indexer = SchemaIndexerAdapter()
    audit = AuditRepository(engine)
    scans.mark_running(scan_id)
    audit.record(
        tenant_id=tenant_id,
        user_id=None,
        action="SCHEMA_SCAN_STARTED",
        ok=True,
        extra={"scan_id": scan_id, "datasource_id": datasource_id},
    )
    try:
        report = indexer.run_scan(datasource_id=datasource_id)
        scans.mark_completed(scan_id, report)
        # Faz 7: schema impact → STALE marking when snapshots provided
        try:
            from nanobase_api.semantic_catalog.infrastructure.catalog_store import get_catalog_store
            from nanobase_api.semantic_catalog.infrastructure.schema_impact_analyzer import (
                apply_schema_impact,
            )

            old_schema = report.get("previous_schema") or report.get("old_schema") or {}
            new_schema = report.get("current_schema") or report.get("new_schema") or {}
            if old_schema and new_schema:
                impact = apply_schema_impact(
                    get_catalog_store(),
                    tenant_id=tenant_id,
                    datasource_id=datasource_id,
                    old_schema=old_schema,
                    new_schema=new_schema,
                    publish_lock_held=bool(report.get("publish_lock_held")),
                )
                if impact.stale_assets:
                    audit.record(
                        tenant_id=tenant_id,
                        user_id=None,
                        action="SEMANTIC_STALE_MARKED",
                        ok=True,
                        extra={
                            "scan_id": scan_id,
                            "stale": impact.stale_assets,
                            "diffs": len(impact.diffs),
                        },
                    )
        except Exception:
            pass
        audit.record(
            tenant_id=tenant_id,
            user_id=None,
            action="SCHEMA_SCAN_COMPLETED",
            ok=True,
            extra={
                "scan_id": scan_id,
                "documents_total": report.get("documents_total"),
                "points_count": report.get("points_count"),
            },
        )
        # Production: enqueue scenario rebuild after successful schema scan
        try:
            _enqueue_scenario_build_after_scan(tenant_id=tenant_id, datasource_id=datasource_id)
            audit.record(
                tenant_id=tenant_id,
                user_id=None,
                action="SCENARIO_BUILD_ENQUEUED",
                ok=True,
                extra={"scan_id": scan_id, "datasource_id": datasource_id},
            )
        except Exception:
            pass
    except Exception as e:
        scans.mark_failed(scan_id, str(e))
        audit.record(
            tenant_id=tenant_id,
            user_id=None,
            action="SCHEMA_SCAN_FAILED",
            ok=False,
            error=str(e)[:300],
            extra={"scan_id": scan_id},
        )
