"""Environment-driven settings. Nothing here reads a database; everything is overridable in tests."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class SemanticSettings:
    store_dsn: str = ""
    tenant_id: str = "default"
    datasource_id: str = "logo"
    project_dir: Optional[Path] = None            # legacy wren project (models/*.yml, knowledge/) — import only
    connection_file: str = ""                     # JSON: {datasource, host, port, database, user, password, driver…}
    llm_base: str = "http://172.17.0.1:8020/v1"
    llm_key: str = ""
    llm_model: str = "nanobaseai-bi-llm"
    llm_timeout: float = 240.0
    min_support: int = 3                          # hard gate: validated_query_support >= 3
    certify_threshold: float = 0.6
    strict_miss: bool = False                     # refuse SQL when a value term is unresolved
    recall_enabled: bool = True                   # Memory ON/OFF (validated pairs as few-shot)
    recall_limit: int = 4
    max_rows: int = 500
    dialect: str = "tsql"
    schema_name: str = "dbo"
    table_like: str = "LG_411_%"
    context: dict[str, str] = field(default_factory=lambda: {"firm": "411", "period": "01"})
    summary_mode: str = "fast"                    # fast (deterministic) | llm
    enum_max_distinct: int = 64

    @classmethod
    def from_env(cls) -> "SemanticSettings":
        project = _env("SEMANTIC_PROJECT_DIR") or _env("WREN_PROJECT")
        dsn = _env("SEMANTIC_STORE_DSN") or _env("NANOBASE_META_DSN")
        if not dsn:
            dsn = "sqlite:///" + str(Path(_env("SEMANTIC_STORE_PATH", ".semantic_layer.db")).resolve())
        ctx = {"firm": _env("SEMANTIC_FIRM", "411"), "period": _env("SEMANTIC_PERIOD", "01")}
        return cls(
            store_dsn=dsn,
            tenant_id=_env("SEMANTIC_TENANT_ID", "default"),
            datasource_id=_env("SEMANTIC_DATASOURCE_ID", "logo"),
            project_dir=Path(project).resolve() if project else None,
            connection_file=_env("SEMANTIC_CONNECTION_FILE") or _env("WREN_CONNECTION_FILE"),
            llm_base=_env("OPENAI_API_BASE", "http://172.17.0.1:8020/v1").rstrip("/"),
            llm_key=_env("OPENAI_API_KEY", ""),
            llm_model=_env("LLM_MODEL_NAME", "nanobaseai-bi-llm"),
            llm_timeout=float(_env("LLM_TIMEOUT_SEC", "240")),
            min_support=int(_env("SEMANTIC_MIN_SUPPORT", "3")),
            certify_threshold=float(_env("SEMANTIC_CERTIFY_THRESHOLD", "0.6")),
            strict_miss=_bool("SEMANTIC_STRICT_MISS", False),
            recall_enabled=_bool("SEMANTIC_RECALL", True),
            recall_limit=int(_env("SEMANTIC_RECALL_LIMIT", "4")),
            max_rows=int(_env("SEMANTIC_MAX_ROWS", "500")),
            dialect=_env("SEMANTIC_DIALECT", "tsql"),
            schema_name=_env("SEMANTIC_SCHEMA", "dbo"),
            table_like=_env("SEMANTIC_TABLE_LIKE", "LG_411_%"),
            context=ctx,
            summary_mode=_env("SEMANTIC_SUMMARY_MODE", "fast"),
            enum_max_distinct=int(_env("SEMANTIC_ENUM_MAX_DISTINCT", "64")),
        )
