"""Query Gateway settings (fail-closed defaults)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return str(raw).lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    port: int = 8792
    secrets_root: Path = field(default_factory=lambda: Path("/data/nanobaseai/bi/secrets"))
    redis_url: str = "redis://127.0.0.1:6379/0"
    policy_version: str = "2026.07.1"

    # Limits
    max_rows: int = 1000
    preview_max_rows: int = 100
    max_columns: int = 100
    max_cell_bytes: int = 16 * 1024
    max_payload_bytes: int = 5 * 1024 * 1024
    statement_timeout_ms: int = 15_000
    lock_timeout_ms: int = 1_000
    explain_timeout_ms: int = 3_000
    max_joins: int = 8
    max_subquery_depth: int = 6
    max_cte_count: int = 10
    max_sql_bytes: int = 100 * 1024
    max_limit: int = 1000

    # Auth
    service_jwt_secret: str = ""
    service_jwt_issuer: str = "nanobase-backend"
    service_jwt_audience: str = "nanobase-query-gateway"
    hmac_secret: str = ""
    auth_required: bool = True
    replay_required: bool = True
    replay_ttl_s: int = 120
    jwt_ttl_s: int = 60
    timestamp_skew_s: int = 60

    # Secrets / vault
    vault_addr: str = ""
    vault_token: str = ""
    vault_fail_closed: bool = True
    require_qualified_tables: bool = True
    reject_wildcard_select: bool = True

    # Pool
    pool_size: int = 5
    pool_max_overflow: int = 5
    pool_timeout_s: float = 5.0
    pool_recycle_s: int = 1800
    pool_idle_ttl_s: int = 600

    # Cost profiles (total cost / plan rows)
    cost_max_rows_small: float = 1_000_000
    cost_max_rows_medium: float = 5_000_000
    cost_max_rows_large: float = 10_000_000
    cost_max_total_small: float = 50_000
    cost_max_total_medium: float = 250_000
    cost_max_total_large: float = 1_000_000

    # Observability
    audit_required: bool = True
    contract_version: str = "1"

    @classmethod
    def from_env(cls) -> "Settings":
        root = Path(os.environ.get("SECRETS_ROOT", "/data/nanobaseai/bi/secrets"))
        jwt_secret = os.environ.get("QG_SERVICE_JWT_SECRET") or os.environ.get("QG_HMAC_SECRET") or ""
        hmac_secret = os.environ.get("QG_HMAC_SECRET") or jwt_secret
        return cls(
            port=int(os.environ.get("QUERY_GATEWAY_PORT", "8792")),
            secrets_root=root,
            redis_url=os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"),
            policy_version=os.environ.get("QG_POLICY_VERSION", "2026.07.1"),
            max_rows=int(os.environ.get("QG_MAX_ROWS", "1000")),
            max_limit=int(os.environ.get("QG_MAX_LIMIT", os.environ.get("QG_MAX_ROWS", "1000"))),
            statement_timeout_ms=int(
                float(os.environ.get("QG_STATEMENT_TIMEOUT_S", "15")) * 1000
            ),
            service_jwt_secret=jwt_secret,
            hmac_secret=hmac_secret,
            auth_required=_env_bool("QG_AUTH_REQUIRED", True),
            replay_required=_env_bool("QG_REPLAY_REQUIRED", True),
            vault_addr=(os.environ.get("VAULT_ADDR") or "").rstrip("/"),
            vault_token=os.environ.get("VAULT_TOKEN") or "",
            vault_fail_closed=_env_bool("QG_VAULT_FAIL_CLOSED", True),
            # Default False: existing chat SQL often uses bare table names; enable via env for strict tenants.
            require_qualified_tables=_env_bool("QG_REQUIRE_QUALIFIED_TABLES", False),
            reject_wildcard_select=_env_bool("QG_REJECT_WILDCARD", True),
            audit_required=_env_bool("QG_AUDIT_REQUIRED", False),
        )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def reset_settings() -> None:
    global _settings
    _settings = None
