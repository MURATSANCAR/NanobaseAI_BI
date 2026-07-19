"""Oracle read-only executor: Plan Guard → RO txn → VPD → execute → rollback."""

from __future__ import annotations

import os
import time
from typing import Any

from query_gateway.config.settings import Settings, get_settings
from query_gateway.domain.errors import GatewayError, QUERY_TIMEOUT
from query_gateway.infrastructure.oracle.error_mapper import (
    ORACLE_PLAN_VALIDATION_UNAVAILABLE,
    map_oracle_error,
)
from query_gateway.infrastructure.oracle.plan_guard import explain_and_validate
from query_gateway.infrastructure.oracle.pool import get_oracle_pool_registry
from query_gateway.infrastructure.oracle.result_normalizer import normalize_oracle_rows
from query_gateway.infrastructure.oracle.session import reset_session_before
from query_gateway.infrastructure.oracle.vpd import set_tenant_context


def _oracle_execution_mode() -> str:
    return (os.environ.get("ORACLE_EXECUTION_MODE") or "QUERY_GATEWAY").upper()


def execute_oracle_ro(
    ds: dict[str, Any],
    sql: str,
    *,
    tenant_id: str | None,
    user_id: str | None = None,
    execution_id: str | None = None,
    timeout_ms: int,
    max_rows: int,
    size_profile: str = "medium",
    run_explain: bool = True,
    require_vpd: bool | None = None,
    settings: Settings | None = None,
) -> tuple[list[str], list[dict[str, Any]], bool, int]:
    """Returns columns, rows, truncated, execution_time_ms."""
    settings = settings or get_settings()
    mode = _oracle_execution_mode()
    if mode == "PLAN_ONLY":
        raise GatewayError(
            "ORACLE_EXECUTION_DISABLED",
            "Oracle execution PLAN_ONLY modunda; sorgu çalıştırılmaz.",
            status=403,
        )

    if require_vpd is None:
        require_vpd = bool(ds.get("require_vpd") or ds.get("requireVpd") or False)

    registry = get_oracle_pool_registry()
    t0 = time.time()

    # Plan Guard on a separate connection (PLAN_TABLE DML cannot run in RO txn).
    if run_explain:
        plan_ds = dict(ds)
        # Peek profile fields without holding the query connection yet
        from query_gateway.infrastructure.oracle.profile import build_profile_from_datasource

        peek = build_profile_from_datasource(ds)
        if peek.plan_user and peek.plan_password:
            plan_ds = {
                **ds,
                "user": peek.plan_user,
                "password": peek.plan_password,
                "id": f"{ds['id']}__plan",
            }
        plan_id, plan_conn, _ = registry.acquire(plan_ds)
        try:
            explain_and_validate(
                plan_conn,
                sql,
                size_profile=size_profile or peek.size_profile,
                settings=settings,
            )
        except GatewayError:
            raise
        except Exception as e:
            raise GatewayError(
                ORACLE_PLAN_VALIDATION_UNAVAILABLE,
                "Oracle Plan Guard çalıştırılamadı.",
                status=503,
                retryable=True,
            ) from e
        finally:
            registry.release(plan_id, plan_conn)

    ds_id, conn, profile = registry.acquire(ds)
    discard = False
    try:
        reset_session_before(conn, execution_id=execution_id)
        try:
            conn.call_timeout = int(timeout_ms)
        except Exception:
            pass

        with conn.cursor() as cur:
            # Read-only transaction must be the first SQL statement
            cur.execute("SET TRANSACTION READ ONLY")

            if tenant_id:
                set_tenant_context(
                    conn,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    execution_id=execution_id,
                    required=require_vpd,
                )

            try:
                cur.execute(sql)
            except Exception as e:
                mapped = map_oracle_error(e)
                if "timeout" in str(e).lower() or mapped.code == QUERY_TIMEOUT:
                    discard = True
                    try:
                        conn.cancel()
                    except Exception:
                        pass
                raise mapped from e

            if cur.description is None:
                conn.rollback()
                return [], [], False, int((time.time() - t0) * 1000)

            cols = [d[0] for d in cur.description]
            type_names = []
            for d in cur.description:
                t = getattr(d, "type_name", None) or getattr(d, "type", None)
                type_names.append(str(getattr(t, "name", t) or ""))

            raw_rows = cur.fetchmany(max_rows + 1)
            truncated = len(raw_rows) > max_rows
            raw_rows = raw_rows[:max_rows]
            rows = normalize_oracle_rows(cols, list(raw_rows), type_names=type_names)
            conn.rollback()
            return cols, rows, truncated, int((time.time() - t0) * 1000)
    except GatewayError:
        try:
            conn.rollback()
        except Exception:
            discard = True
        raise
    except Exception as e:
        discard = True
        try:
            conn.rollback()
        except Exception:
            pass
        raise map_oracle_error(e) from e
    finally:
        registry.release(ds_id, conn, discard=discard)
