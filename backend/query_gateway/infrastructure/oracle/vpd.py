"""Oracle VPD / application-context tenant isolation."""

from __future__ import annotations

from typing import Any

from query_gateway.domain.errors import TENANT_POLICY_MISSING, GatewayError


def set_tenant_context(
    conn: Any,
    *,
    tenant_id: str,
    user_id: str | None = None,
    execution_id: str | None = None,
    required: bool = True,
) -> None:
    """Set NANOBASE_CTX attributes. Fail-closed when required and package missing."""
    if not tenant_id:
        if required:
            raise GatewayError(
                TENANT_POLICY_MISSING,
                "Tenant context zorunludur.",
                status=403,
            )
        return
    try:
        with conn.cursor() as cur:
            # Prefer packaged setter if present; fall back to DBMS_SESSION
            try:
                cur.execute(
                    "BEGIN NANOBASE_CTX_PKG.SET_TENANT(:tid, :uid, :eid); END;",
                    tid=tenant_id,
                    uid=user_id or "",
                    eid=execution_id or "",
                )
                return
            except Exception:
                pass
            cur.execute(
                "BEGIN DBMS_SESSION.SET_CONTEXT('NANOBASE_CTX', 'TENANT_ID', :v); END;",
                v=tenant_id,
            )
            if user_id:
                cur.execute(
                    "BEGIN DBMS_SESSION.SET_CONTEXT('NANOBASE_CTX', 'USER_ID', :v); END;",
                    v=user_id,
                )
            if execution_id:
                cur.execute(
                    "BEGIN DBMS_SESSION.SET_CONTEXT('NANOBASE_CTX', 'EXECUTION_ID', :v); END;",
                    v=execution_id,
                )
            try:
                conn.client_identifier = tenant_id[:64]
            except Exception:
                pass
    except GatewayError:
        raise
    except Exception as e:
        if required:
            raise GatewayError(
                TENANT_POLICY_MISSING,
                "VPD tenant context ayarlanamadı.",
                status=403,
            ) from e
