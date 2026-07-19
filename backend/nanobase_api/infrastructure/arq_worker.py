"""ARQ worker for schema scans."""

from __future__ import annotations

import os

from arq.connections import RedisSettings

from nanobase_api.application.schema_scans import execute_schema_scan
from nanobase_api.config import get_settings


async def run_schema_scan(ctx, scan_id: str, datasource_id: str, tenant_id: str) -> str:
    execute_schema_scan(scan_id, datasource_id, tenant_id)
    return scan_id


class WorkerSettings:
    functions = [run_schema_scan]
    redis_settings = RedisSettings.from_dsn(os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"))
    max_jobs = 2
    job_timeout = 900
