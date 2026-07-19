"""Structured audit events (no raw SQL / no result rows)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from query_gateway.config.settings import Settings, get_settings
from query_gateway.domain.errors import AUDIT_WRITE_FAILED, GatewayError

_log = logging.getLogger("query_gateway.audit")


class AuditLogger:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._path = self.settings.secrets_root.parent / "logs" / "query-gateway-audit.jsonl"
        self._memory: list[dict[str, Any]] = []

    def record(self, event: dict[str, Any]) -> None:
        # strip dangerous keys
        safe = {
            k: v
            for k, v in event.items()
            if k.lower() not in ("sql", "password", "rows", "raw_sql")
        }
        _log.info("audit %s", json.dumps(safe, default=str))
        self._memory.append(safe)
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(safe, default=str) + "\n")
        except Exception as e:
            if self.settings.audit_required:
                raise GatewayError(
                    AUDIT_WRITE_FAILED,
                    "Audit yazılamadı.",
                    status=503,
                    retryable=True,
                ) from e


_audit: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    global _audit
    if _audit is None:
        _audit = AuditLogger()
    return _audit
