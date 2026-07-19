"""Oracle execution port (Protocol)."""

from __future__ import annotations

from typing import Any, Protocol

from query_gateway.infrastructure.oracle.profile import OracleConnectionProfile


class OracleExecutionPort(Protocol):
    async def validate_connection(
        self,
        profile: OracleConnectionProfile,
    ) -> dict[str, Any]:
        ...

    async def explain(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        ...

    async def execute(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        ...
