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

    def list_entries(
        self,
        *,
        tenant_id: str | None = None,
        limit: int = 100,
        action: str | None = None,
    ) -> list[dict[str, Any]]:
        """Recent audit rows shaped for the BI Audit page FE contract."""
        lim = max(1, min(int(limit or 100), 500))
        act = (action or "").strip()
        # FE filter chips → DB action families
        action_aliases: dict[str, list[str]] = {
            "query": ["query", "QUERY_COMPLETED", "QUERY_FAILED", "QUESTION_SUBMITTED"],
            "chat": ["chat", "QUESTION_SUBMITTED", "CHAT", "QUERY_COMPLETED"],
            "export": ["export", "EXPORT", "query_export"],
            "schema_refresh": ["schema_refresh", "SCHEMA_REFRESH", "schema.scan"],
        }
        aliases = action_aliases.get(act.lower()) if act else None

        sql = """
            SELECT action, ok, session_id, source, error, duration_ms,
                   extra_json, created_at, sql_fingerprint
            FROM bi_audit_events
            WHERE (:tenant IS NULL OR tenant_id = :tenant OR tenant_id IS NULL)
        """
        params: dict[str, Any] = {"tenant": (tenant_id or "").strip() or None, "lim": lim}
        if aliases:
            keys = []
            for i, name in enumerate(aliases):
                key = f"a{i}"
                keys.append(f":{key}")
                params[key] = name.lower()
            sql += f" AND lower(action) IN ({', '.join(keys)})"
        elif act:
            sql += " AND lower(action) = lower(:act)"
            params["act"] = act
        sql += " ORDER BY created_at DESC LIMIT :lim"

        with self._engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()

        out: list[dict[str, Any]] = []
        for r in rows:
            extra: dict[str, Any] = {}
            raw_extra = r.get("extra_json")
            if isinstance(raw_extra, dict):
                extra = raw_extra
            elif isinstance(raw_extra, str) and raw_extra.strip():
                try:
                    parsed = json.loads(raw_extra)
                    if isinstance(parsed, dict):
                        extra = parsed
                except json.JSONDecodeError:
                    extra = {}
            sql_text = extra.get("sql") or extra.get("sql_preview") or r.get("sql_fingerprint")
            row_count = extra.get("row_count") or extra.get("rows")
            try:
                row_count_i = int(row_count) if row_count is not None else None
            except (TypeError, ValueError):
                row_count_i = None
            created = r.get("created_at")
            out.append(
                {
                    "at": created.isoformat() if hasattr(created, "isoformat") else str(created or ""),
                    "action": str(r.get("action") or ""),
                    "sql": str(sql_text)[:500] if sql_text else None,
                    "session_id": r.get("session_id"),
                    "duration_ms": r.get("duration_ms"),
                    "row_count": row_count_i,
                    "ok": bool(r.get("ok")),
                    "error": r.get("error"),
                    "source": r.get("source"),
                }
            )
        return out

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
