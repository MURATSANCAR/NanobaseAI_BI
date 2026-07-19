"""Domain ports (Faz 3)."""

from __future__ import annotations

from typing import Any, AsyncIterator, Optional, Protocol
from uuid import UUID


class SecretStorePort(Protocol):
    async def store_datasource_password(
        self, *, tenant_id: str, datasource_id: str, password: str
    ) -> str: ...

    def resolve(self, ref: str) -> str: ...


class SchemaIndexerPort(Protocol):
    def run_scan(self, *, datasource_id: str, schemas: str | None = None) -> dict[str, Any]: ...


class TextToSqlEnginePort(Protocol):
    async def generate_sql_plan(
        self,
        *,
        question: str,
        datasource_id: str,
        schema_hint: str,
        retrieved_schema: str | None = None,
        conversation_context: str | None = None,
    ) -> dict[str, Any]: ...

    async def explain_result(
        self,
        *,
        question: str,
        executed_sql: str,
        columns: list[Any],
        rows: list[Any],
        truncated: bool = False,
    ) -> dict[str, Any]: ...


class AuditPort(Protocol):
    def record(
        self,
        *,
        tenant_id: str | None,
        user_id: str | None,
        action: str,
        ok: bool,
        source: str = "nanobase_api",
        session_id: str | None = None,
        error: str | None = None,
        duration_ms: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None: ...
