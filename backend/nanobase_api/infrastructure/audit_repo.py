"""Audit writer — uses existing bi_audit_events; never stores secrets."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

_SECRET_KEYS = re.compile(
    r"(password|token|secret|authorization|cookie|api_key|vault)",
    re.I,
)


def _mask_extra(extra: dict[str, Any] | None) -> dict[str, Any]:
    if not extra:
        return {}
    out: dict[str, Any] = {}
    for k, v in extra.items():
        if _SECRET_KEYS.search(str(k)):
            out[k] = "***"
        elif isinstance(v, str) and len(v) > 2000:
            out[k] = v[:2000] + "…"
        else:
            out[k] = v
    return out


class AuditRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

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
    ) -> None:
        masked = _mask_extra(extra)
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO bi_audit_events
                      (tenant_id, action, ok, user_id, session_id, source,
                       sql_fingerprint, error, duration_ms, extra_json, created_at)
                    VALUES
                      (:tenant_id, :action, :ok, :user_id, :session_id, :source,
                       NULL, :error, :duration_ms, :extra_json, NOW())
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "action": action[:128],
                    "ok": ok,
                    "user_id": (user_id or "")[:128] or None,
                    "session_id": (session_id or "")[:128] or None,
                    "source": source[:64],
                    "error": (error or "")[:2000] or None,
                    "duration_ms": duration_ms,
                    "extra_json": json.dumps(masked, ensure_ascii=False),
                },
            )
