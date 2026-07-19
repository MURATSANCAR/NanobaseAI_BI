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
        self.semantic_catalog_backend = os.environ.get("SEMANTIC_CATALOG_BACKEND", "auto").lower()
        self.semantic_metric_flags = {
            k.removeprefix("SEMANTIC_METRIC_").lower(): v.lower() in ("1", "true", "yes")
            for k, v in os.environ.items()
            if k.startswith("SEMANTIC_METRIC_")
        }
        # Faz 8 Oracle rollout
        self.oracle_execution_enabled = os.environ.get("ORACLE_EXECUTION_ENABLED", "0") == "1"
        self.oracle_execution_mode = (
            os.environ.get("ORACLE_EXECUTION_MODE") or "QUERY_GATEWAY"
        ).upper()
        if self.oracle_execution_mode not in ("QUERY_GATEWAY", "PLAN_ONLY", "METADATA_ONLY"):
            self.oracle_execution_mode = "PLAN_ONLY"
        # Faz 9 SAP rollout
        self.sap_execution_enabled = os.environ.get("SAP_EXECUTION_ENABLED", "0") == "1"
        self.sap_execution_mode = (os.environ.get("SAP_EXECUTION_MODE") or "PLAN_ONLY").upper()
        if self.sap_execution_mode not in ("QUERY_GATEWAY", "PLAN_ONLY", "METADATA_ONLY"):
            self.sap_execution_mode = "PLAN_ONLY"
        self.sap_hana_execution_enabled = os.environ.get("SAP_HANA_EXECUTION_ENABLED", "0") == "1"
        self.sap_fi_execution_enabled = os.environ.get("SAP_FI_EXECUTION_ENABLED", "0") == "1"
        # Local LLM capacity / backpressure (Final Gate §25)
        # Default 1: serialize all LLM work FIFO (one after another)
        self.model_max_concurrency = max(1, int(os.environ.get("MODEL_MAX_CONCURRENCY", "1")))
        self.model_queue_limit = max(1, int(os.environ.get("MODEL_QUEUE_LIMIT", "100")))
        self.tenant_queue_limit = max(1, int(os.environ.get("TENANT_QUEUE_LIMIT", "20")))
        self.model_queue_timeout = float(os.environ.get("MODEL_QUEUE_TIMEOUT", "120"))



@lru_cache
def get_settings() -> Settings:
    return Settings()
