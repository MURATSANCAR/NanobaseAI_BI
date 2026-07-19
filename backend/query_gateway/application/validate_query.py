"""Validate SQL against parser + policy (no DB execute)."""

from __future__ import annotations

from typing import Any

from query_gateway.config.settings import Settings, get_settings
from query_gateway.domain.errors import DATASOURCE_NOT_FOUND, GatewayError
from query_gateway.infrastructure.audit.logger import get_audit_logger
from query_gateway.infrastructure.database.datasources import load_datasources
from query_gateway.infrastructure.parser.sqlglot_parser import fingerprint, parse_sql, apply_limit
from query_gateway.infrastructure.policy.engine import (
    load_policy_bundle,
    policy_from_datasource_cfg,
    validate_parsed,
)


def validate_query(
    *,
    execution_id: str,
    datasource_id: str,
    sql: str,
    tenant_id: str | None = None,
    user_id: str | None = None,
    max_rows: int | None = None,
    settings: Settings | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    bundle = load_policy_bundle(settings)
    ds_map = load_datasources(settings)
    ds = ds_map.get(datasource_id)
    if not ds:
        raise GatewayError(
            DATASOURCE_NOT_FOUND,
            "Datasource bulunamadı.",
            status=404,
            execution_id=execution_id,
            trace_id=trace_id,
            policy_version=bundle.policy_version,
        )

    dialect = "postgres" if (ds.get("driver") or "").startswith("postgres") else ds.get("dialect") or "postgres"
    if dialect not in ("postgres", "postgresql"):
        # Internal v1 Postgres-first; legacy API still handles oracle/hana
        dialect = "postgres" if ds.get("driver") == "postgresql" else str(ds.get("dialect") or "postgres")

    parsed = parse_sql(sql, dialect="postgres" if "postgres" in str(dialect) else str(dialect))
    cfg = dict(ds)
    # ensure allowed_tables set for policy
    if isinstance(cfg.get("allowed_tables"), set):
        cfg["allowed_tables"] = sorted(cfg["allowed_tables"])
    ds_policy = policy_from_datasource_cfg(datasource_id, cfg, bundle)
    warnings = validate_parsed(parsed, ds_policy, bundle)

    limit = min(max_rows or settings.max_rows, settings.max_limit)
    # fingerprint on normalized before limit rewrite
    fp = fingerprint(
        dialect=parsed.dialect,
        normalized_sql=parsed.normalized_sql,
        policy_version=ds_policy.policy_version,
        datasource_id=datasource_id,
    )
    limited_sql = apply_limit(parsed.tree, max_limit=limit + 1, dialect=parsed.dialect)

    audit = get_audit_logger()
    audit.record(
        {
            "executionId": execution_id,
            "event": "QUERY_VALIDATED",
            "tenantId": tenant_id,
            "userId": user_id,
            "datasourceId": datasource_id,
            "sqlFingerprint": fp,
            "statementType": "SELECT",
            "tables": parsed.tables,
            "policyVersion": ds_policy.policy_version,
            "result": "APPROVED",
            "traceId": trace_id,
        }
    )

    return {
        "executionId": execution_id,
        "status": "APPROVED",
        "statementType": "SELECT",
        "normalizedSql": limited_sql,
        "sqlFingerprint": fp,
        "schemas": parsed.schemas,
        "tables": parsed.tables,
        "columns": parsed.columns,
        "functions": parsed.functions,
        "warnings": warnings,
        "policyVersion": ds_policy.policy_version,
    }
