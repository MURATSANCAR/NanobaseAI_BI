"""Oracle session state reset for pool safety."""

from __future__ import annotations

from typing import Any


MODULE_NAME = "NANOBASE_QUERY_GATEWAY"


def reset_session_before(conn: Any, *, execution_id: str | None = None) -> None:
    """Bring a checked-out session to a known state before query use."""
    try:
        conn.rollback()
    except Exception:
        pass
    try:
        conn.module = MODULE_NAME
        conn.action = (execution_id or "")[:32]
        conn.client_identifier = ""
        conn.clientinfo = "nanobase-query-gateway"
    except Exception:
        pass


def reset_session_after(conn: Any) -> None:
    """Clear tenant/session markers before returning to pool."""
    try:
        conn.rollback()
    except Exception:
        pass
    try:
        clear_tenant_context(conn)
    except Exception:
        pass
    try:
        conn.action = ""
        conn.client_identifier = ""
    except Exception:
        pass


def clear_tenant_context(conn: Any) -> None:
    """Best-effort clear of Nanobase application context (no-op if package missing)."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                "BEGIN DBMS_SESSION.CLEAR_CONTEXT('NANOBASE_CTX', NULL, 'TENANT_ID'); END;"
            )
            cur.execute(
                "BEGIN DBMS_SESSION.CLEAR_CONTEXT('NANOBASE_CTX', NULL, 'USER_ID'); END;"
            )
            cur.execute(
                "BEGIN DBMS_SESSION.CLEAR_CONTEXT('NANOBASE_CTX', NULL, 'EXECUTION_ID'); END;"
            )
    except Exception:
        # Context package may not exist in all test DBs; ignore on cleanup.
        pass
