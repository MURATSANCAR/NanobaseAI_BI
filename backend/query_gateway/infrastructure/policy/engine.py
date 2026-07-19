"""SQL policy engine (YAML + datasource allowlists)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from query_gateway.config.settings import Settings, get_settings
from query_gateway.domain.errors import (
    COLUMN_NOT_ALLOWED,
    DATASOURCE_POLICY_NOT_FOUND,
    FUNCTION_NOT_ALLOWED,
    JOIN_POLICY_VIOLATION,
    SCHEMA_NOT_ALLOWED,
    TABLE_NOT_ALLOWED,
    WILDCARD_NOT_ALLOWED,
    GatewayError,
)
from query_gateway.infrastructure.parser.sqlglot_parser import ParsedQuery


@dataclass
class FunctionPolicy:
    allowed: set[str] = field(default_factory=set)
    controlled: set[str] = field(default_factory=set)
    denied: set[str] = field(default_factory=set)


@dataclass
class DatasourcePolicy:
    datasource_id: str
    allowed_schemas: set[str] = field(default_factory=set)
    allowed_tables: set[str] = field(default_factory=set)
    column_modes: dict[str, str] = field(default_factory=dict)  # ALLOWED|MASKED|DENIED
    size_profile: str = "medium"
    policy_version: str = "2026.07.1"


@dataclass
class PolicyBundle:
    functions: FunctionPolicy
    policy_version: str
    max_joins: int = 8
    reject_wildcard: bool = True
    require_qualified: bool = True


def _policy_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "policies"


def load_policy_bundle(settings: Settings | None = None) -> PolicyBundle:
    settings = settings or get_settings()
    pdir = _policy_dir()
    fn_raw: dict[str, Any] = {}
    fn_path = pdir / "postgres-functions.yaml"
    if fn_path.is_file():
        fn_raw = yaml.safe_load(fn_path.read_text(encoding="utf-8")) or {}
    limits: dict[str, Any] = {}
    lim_path = pdir / "default-limits.yaml"
    if lim_path.is_file():
        limits = yaml.safe_load(lim_path.read_text(encoding="utf-8")) or {}
    return PolicyBundle(
        functions=FunctionPolicy(
            allowed={str(x).upper() for x in (fn_raw.get("allowed") or [])},
            controlled={str(x).upper() for x in (fn_raw.get("controlled") or [])},
            denied={str(x).upper() for x in (fn_raw.get("denied") or [])},
        ),
        policy_version=str(limits.get("policyVersion") or settings.policy_version),
        max_joins=int(limits.get("maxJoins") or settings.max_joins),
        reject_wildcard=bool(
            limits.get("rejectWildcardSelect", settings.reject_wildcard_select)
        ),
        require_qualified=bool(
            limits.get("requireQualifiedTables", settings.require_qualified_tables)
        ),
    )


def policy_from_datasource_cfg(ds_id: str, cfg: dict[str, Any], bundle: PolicyBundle) -> DatasourcePolicy:
    tables_raw = cfg.get("allowed_tables")
    if tables_raw is None:
        raise GatewayError(
            DATASOURCE_POLICY_NOT_FOUND,
            "Datasource için tablo politikası bulunamadı.",
            status=403,
            policy_version=bundle.policy_version,
        )
    if tables_raw == "*":
        allowed_tables: set[str] = set()  # empty + special later
        allow_all = True
    else:
        allow_all = False
        allowed_tables = {str(x).lower() for x in tables_raw}

    schemas = {str(x).lower() for x in (cfg.get("allowed_schemas") or [])}
    if not schemas:
        for t in allowed_tables:
            if "." in t:
                schemas.add(t.split(".", 1)[0])

    col_modes: dict[str, str] = {}
    for k, v in (cfg.get("column_policies") or cfg.get("columns") or {}).items():
        col_modes[str(k).lower()] = str(v).upper()

    return DatasourcePolicy(
        datasource_id=ds_id,
        allowed_schemas=schemas,
        allowed_tables=allowed_tables if not allow_all else {"*"},
        column_modes=col_modes,
        size_profile=str(cfg.get("size_profile") or "medium"),
        policy_version=str(cfg.get("policy_version") or bundle.policy_version),
    )


def validate_parsed(
    parsed: ParsedQuery,
    ds_policy: DatasourcePolicy,
    bundle: PolicyBundle,
) -> list[str]:
    """Raise GatewayError on violation; return warnings."""
    warnings: list[str] = []

    if parsed.has_wildcard and bundle.reject_wildcard:
        raise GatewayError(
            WILDCARD_NOT_ALLOWED,
            "SELECT * üretim ortamında izinli değildir.",
            status=400,
            policy_version=ds_policy.policy_version,
        )

    if parsed.has_cross_join or parsed.has_on_true:
        raise GatewayError(
            JOIN_POLICY_VIOLATION,
            "CROSS JOIN veya koşulsuz join izinli değildir.",
            status=400,
            policy_version=ds_policy.policy_version,
        )
    if parsed.join_count > bundle.max_joins:
        raise GatewayError(
            JOIN_POLICY_VIOLATION,
            f"Join sayısı limiti aşıldı (max {bundle.max_joins}).",
            status=400,
            policy_version=ds_policy.policy_version,
        )

    if bundle.require_qualified and parsed.unqualified_tables:
        # allow if bare name is in allowlist as public.X or schema.X only as qualified preference
        # Production default: reject unqualified
        raise GatewayError(
            TABLE_NOT_ALLOWED,
            "Şemasız tablo adı izinli değildir; schema.table kullanın.",
            status=400,
            policy_version=ds_policy.policy_version,
        )

    allow_all = "*" in ds_policy.allowed_tables
    for table in parsed.tables:
        bare = table.split(".")[-1]
        if bare in parsed.cte_aliases:
            continue
        if allow_all:
            continue
        if table not in ds_policy.allowed_tables and bare not in ds_policy.allowed_tables:
            raise GatewayError(
                TABLE_NOT_ALLOWED,
                "Sorgu izin verilmeyen bir tabloya erişiyor.",
                status=400,
                policy_version=ds_policy.policy_version,
            )
        if "." in table:
            schema = table.split(".", 1)[0]
            if ds_policy.allowed_schemas and schema not in ds_policy.allowed_schemas:
                # schema inferred from tables — soft check
                if not any(t.startswith(f"{schema}.") for t in ds_policy.allowed_tables):
                    raise GatewayError(
                        SCHEMA_NOT_ALLOWED,
                        "Sorgu izin verilmeyen bir şemaya erişiyor.",
                        status=400,
                        policy_version=ds_policy.policy_version,
                    )

    for fn in parsed.functions:
        name = fn.upper()
        # Map sqlglot class names to common fn names
        aliases = {
            "ANONYMOUS": None,
            "COUNT": "COUNT",
            "SUM": "SUM",
            "AVG": "AVG",
            "MIN": "MIN",
            "MAX": "MAX",
            "COALESCE": "COALESCE",
            "LOWER": "LOWER",
            "UPPER": "UPPER",
            "TRIM": "TRIM",
            "SUBSTRING": "SUBSTRING",
            "CONCAT": "CONCAT",
            "CAST": "CAST",
            "ROUND": "ROUND",
            "ABS": "ABS",
            "CEIL": "CEIL",
            "FLOOR": "FLOOR",
            "NULLIF": "NULLIF",
            "GREATEST": "GREATEST",
            "LEAST": "LEAST",
            "EXTRACT": "EXTRACT",
            "DATETRUNC": "DATE_TRUNC",
            "TOCHAR": "TO_CHAR",
            "TODATE": "TO_DATE",
            "ROWNUMBER": "ROW_NUMBER",
            "RANK": "RANK",
            "DENSERANK": "DENSE_RANK",
            "LAG": "LAG",
            "LEAD": "LEAD",
            "CURRENTTIMESTAMP": "CURRENT_TIMESTAMP",
            "CURRENTDATE": "CURRENT_DATE",
        }
        mapped = aliases.get(name, name)
        if mapped is None:
            continue
        if mapped in bundle.functions.denied:
            raise GatewayError(
                FUNCTION_NOT_ALLOWED,
                f"İzin verilmeyen fonksiyon: {mapped}.",
                status=400,
                policy_version=ds_policy.policy_version,
            )
        if (
            mapped not in bundle.functions.allowed
            and mapped not in bundle.functions.controlled
        ):
            # Unknown / UDF default deny
            raise GatewayError(
                FUNCTION_NOT_ALLOWED,
                f"İzin verilmeyen fonksiyon: {mapped}.",
                status=400,
                policy_version=ds_policy.policy_version,
            )
        if mapped in bundle.functions.controlled:
            warnings.append(f"controlled_function:{mapped}")

    for col in parsed.columns:
        mode = ds_policy.column_modes.get(col.lower())
        if mode == "DENIED":
            raise GatewayError(
                COLUMN_NOT_ALLOWED,
                "Sorgu izin verilmeyen bir kolona erişiyor.",
                status=400,
                policy_version=ds_policy.policy_version,
            )

    return warnings
