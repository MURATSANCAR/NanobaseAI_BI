"""Nanobase API settings (Faz 3)."""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache


class AuthMode(str, Enum):
    DEV = "dev"
    JWT = "jwt"


class ExecutionMode(str, Enum):
    PLAN_ONLY = "PLAN_ONLY"
    TEST_DIRECT = "TEST_DIRECT"
    QUERY_GATEWAY = "QUERY_GATEWAY"


class Settings:
    def __init__(self) -> None:
        self.environment = os.environ.get("NANOBASE_ENV", "production")
        self.auth_mode = AuthMode(os.environ.get("AUTH_MODE", "dev").lower())
        self.jwt_secret = os.environ.get("JWT_SECRET", "nanobase-dev-jwt-secret-change-me")
        self.jwt_algorithm = os.environ.get("JWT_ALGORITHM", "HS256")
        self.dev_tenant_id = os.environ.get("DEV_TENANT_ID", "default")
        self.dev_user_id = os.environ.get("DEV_USER_ID", "dev-user")
        self.meta_dsn = os.environ.get(
            "NANOBASE_META_DSN",
            "postgresql+psycopg2://bi_meta@127.0.0.1:5434/bi_meta",
        )
        self.meta_async_dsn = os.environ.get(
            "NANOBASE_META_ASYNC_DSN",
            self.meta_dsn.replace("postgresql+psycopg2://", "postgresql+asyncpg://").replace(
                "postgresql://", "postgresql+asyncpg://"
            ),
        )
        self.query_gateway_base = os.environ.get("QUERY_GATEWAY_BASE", "http://127.0.0.1:8792").rstrip("/")
        self.redis_url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
        self.arq_enabled = os.environ.get("ARQ_ENABLED", "1") == "1"
        self.execution_mode = ExecutionMode(
            os.environ.get("NANOBASE_TEXT2SQL_EXECUTION_MODE", "QUERY_GATEWAY")
        )
        self.secrets_root = os.environ.get("SECRETS_ROOT", "/data/nanobaseai/bi/secrets")
        self.schema_indexer_root = os.environ.get(
            "SCHEMA_INDEXER_ROOT",
            "/data/nanobaseai/bi/frontend/tools/schema-indexer",
        )
        self.python_bin = os.environ.get(
            "NANOBASE_PYTHON",
            "/data/nanobaseai/bi/frontend/backend/.venv/bin/python",
        )
        if self.environment == "production" and self.execution_mode == ExecutionMode.TEST_DIRECT:
            raise RuntimeError("TEST_DIRECT cannot be enabled in production.")
        # Faz 7 semantic governance
        self.semantic_catalog_enabled = os.environ.get("SEMANTIC_CATALOG_ENABLED", "1") == "1"
        self.semantic_shadow_mode = os.environ.get("SEMANTIC_SHADOW_MODE", "0") == "1"
        self.semantic_metric_flags = {
            k.split(".", 1)[-1]: v.lower() in ("1", "true", "yes")
            for k, v in os.environ.items()
            if k.startswith("SEMANTIC_METRIC_")
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
