"""Validate SQL against parser + policy (no DB execute)."""

from __future__ import annotations

from typing import Any

from query_gateway.config.settings import Settings, get_settings
from query_gateway.domain.errors import DATASOURCE_NOT_FOUND, SCHEMA_NOT_ALLOWED, GatewayError
from query_gateway.infrastructure.audit.logger import get_audit_logger
from query_gateway.infrastructure.database.datasources import load_datasources
from query_gateway.infrastructure.oracle.parser_policy import enforce_oracle_sql_policy
from query_gateway.infrastructure.oracle.profile import build_profile_from_datasource
from query_gateway.infrastructure.parser.sqlglot_parser import fingerprint, parse_sql, apply_limit
from query_gateway.infrastructure.policy.engine import (
    load_policy_bundle,
    policy_from_datasource_cfg,
    validate_parsed,
)
from query_gateway.infrastructure.sap.hana.parser_policy import enforce_hana_sql_policy
from query_gateway.infrastructure.sap.hana.profile import build_hana_profile
from query_gateway.infrastructure.sap.odata.executor import validate_odata_only


def _resolve_dialect(ds: dict[str, Any]) -> str:
    driver = (ds.get("driver") or "").lower()
    dialect = str(ds.get("dialect") or "").lower()
    if driver == "oracle" or dialect == "oracle":
        return "oracle"
    if driver in ("mssql", "sqlserver", "tsql") or dialect in ("mssql", "tsql", "sqlserver"):
        return "mssql"
    if driver in ("hana", "sap_hana", "hdb") or dialect in ("hana", "sap_hana"):
        return "hana"
    if driver in ("odata", "cds", "cds_odata") or dialect == "odata":
        return "odata"
    if driver.startswith("postgres") or dialect in ("postgres", "postgresql"):
        return "postgres"
    return dialect or "postgres"


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
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    from query_gateway.infrastructure.parser.bind_params import (
        extract_bind_names,
        probe_sql_for_parse,
        validate_parameters,
    )

    bind_params = validate_parameters(parameters)
    sql_template = sql
    # Parse with typed literals when named binds present; keep template for execute.
    parse_sql_text = (
        probe_sql_for_parse(sql_template, bind_params)
        if extract_bind_names(sql_template) or bind_params
        else sql_template
    )
    ds_map = load_datasources(settings)
    ds = ds_map.get(datasource_id)
    if not ds:
        bundle = load_policy_bundle(settings)
        raise GatewayError(
            DATASOURCE_NOT_FOUND,
            "Datasource bulunamadı.",
            status=404,
            execution_id=execution_id,
            trace_id=trace_id,
            policy_version=bundle.policy_version,
        )

    dialect = _resolve_dialect(ds)
    if dialect == "oracle":
        # Fail-closed profile validation (forbidden users, SERVICE_NAME, owners)
        build_profile_from_datasource(ds)
    if dialect == "hana":
        # Sandbox may disable cert validation
        if ds.get("ssl_validate") is False:
            ds = dict(ds)
            ds["allow_insecure_tls"] = True
            ds["validate_certificate"] = False
        build_hana_profile(ds)

    if dialect == "odata":
        od = validate_odata_only(ds, sql)
        bundle = load_policy_bundle(settings, dialect="postgres")
        fp = fingerprint(
            dialect="odata",
            normalized_sql=od["normalizedSql"],
            policy_version=bundle.policy_version,
            datasource_id=datasource_id,
        )
        get_audit_logger().record(
            {
                "executionId": execution_id,
                "event": "QUERY_VALIDATED",
                "tenantId": tenant_id,
                "userId": user_id,
                "datasourceId": datasource_id,
                "sqlFingerprint": fp,
                "statementType": "ODATA_GET",
                "tables": [od.get("plan", {}).get("entitySet")],
                "policyVersion": bundle.policy_version,
                "result": "APPROVED",
                "traceId": trace_id,
                "dialect": "odata",
            }
        )
        return {
            "executionId": execution_id,
            "status": "APPROVED",
            "statementType": "ODATA_GET",
            "normalizedSql": od["normalizedSql"],
            "sqlFingerprint": fp,
            "schemas": [],
            "tables": [od.get("plan", {}).get("entitySet")],
            "columns": (od.get("plan") or {}).get("select") or [],
            "functions": [],
            "warnings": od.get("warnings") or [],
            "policyVersion": bundle.policy_version,
            "dialect": "odata",
            "plan": od.get("plan"),
        }

    # HANA uses postgres sqlglot dialect for AST; policy is HANA-specific.
    # SQL Server parses/writes as sqlglot "tsql" (TOP N instead of LIMIT).
    parse_dialect = "postgres" if dialect == "hana" else ("tsql" if dialect == "mssql" else dialect)
    bundle = load_policy_bundle(settings, dialect=dialect if dialect != "odata" else "postgres")
    parsed = parse_sql(parse_sql_text, dialect=parse_dialect)
    cfg = dict(ds)
    if isinstance(cfg.get("allowed_tables"), set):
        cfg["allowed_tables"] = sorted(cfg["allowed_tables"])
    if isinstance(cfg.get("allowed_views"), set):
        cfg["allowed_tables"] = sorted(
            set(cfg.get("allowed_tables") or []) | set(cfg["allowed_views"])
        )
    # Oracle: also allow owner.table from allowed_owners when tables list uses uppercase
    if dialect == "oracle" and cfg.get("allowed_owners"):
        owners = {str(o).lower() for o in cfg["allowed_owners"]}
        schemas = set(cfg.get("allowed_schemas") or [])
        schemas |= owners
        cfg["allowed_schemas"] = sorted(schemas)
    if dialect in ("hana", "mssql") and cfg.get("allowed_schemas"):
        cfg["allowed_schemas"] = [str(s).lower() for s in cfg["allowed_schemas"]]

    ds_policy = policy_from_datasource_cfg(datasource_id, cfg, bundle)
    warnings = validate_parsed(parsed, ds_policy, bundle)
    if dialect == "mssql":
        # allowed_tables="*" still confines queries to the configured schemas (dbo by default).
        allowed_schemas = {str(x).lower() for x in (cfg.get("allowed_schemas") or [])}
        bad = sorted({str(sch).lower() for sch in (parsed.schemas or []) if str(sch).lower() not in allowed_schemas})
        if allowed_schemas and bad:
            raise GatewayError(
                SCHEMA_NOT_ALLOWED,
                f"Şema izinli değil: {', '.join(bad)} (izinli: {', '.join(sorted(allowed_schemas))}).",
                status=403,
                execution_id=execution_id,
                trace_id=trace_id,
                policy_version=bundle.policy_version,
            )
    if dialect == "oracle":
        warnings.extend(enforce_oracle_sql_policy(parse_sql_text, parsed))
    if dialect == "hana":
        warnings.extend(enforce_hana_sql_policy(parse_sql_text, parsed))

    limit = min(max_rows or settings.max_rows, settings.max_limit)
    fp = fingerprint(
        dialect=dialect,
        normalized_sql=parsed.normalized_sql,
        policy_version=ds_policy.policy_version,
        datasource_id=datasource_id,
    )
    limited_probe = apply_limit(parsed.tree, max_limit=limit + 1, dialect=parse_dialect)
    # Prefer original template for execution when binds are used
    limited_sql = sql_template if bind_params or extract_bind_names(sql_template) else limited_probe

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
            "dialect": dialect,
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
        "dialect": dialect,
        "sqlTemplate": sql_template,
        "parameters": bind_params,
        "probeSql": limited_probe if bind_params or extract_bind_names(sql_template) else limited_sql,
    }
