"""PostgreSQL read-only execute with RLS GUC + EXPLAIN cost guard."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import psycopg2
import psycopg2.extras

from query_gateway.config.settings import Settings, get_settings
from query_gateway.domain.errors import (
    COLUMN_NOT_FOUND,
    DATABASE_CONNECTION_LOST,
    DATABASE_PERMISSION_DENIED,
    DATABASE_UNAVAILABLE,
    QUERY_TIMEOUT,
    TABLE_OR_VIEW_NOT_FOUND,
    GatewayError,
)
from query_gateway.infrastructure.database.explain_parser import analyze_explain_json
from query_gateway.infrastructure.database.pool_registry import PoolRegistry, get_pool_registry

log = logging.getLogger("query_gateway.postgres_executor")


def _map_psycopg_error(exc: BaseException) -> GatewayError:
    """Classify DB errors: timeout vs connection vs SQL vs unavailable."""
    msg = str(exc)
    low = msg.lower()
    pgcode = getattr(exc, "pgcode", None) or ""

    if (
        "timeout" in low
        or "canceling statement" in low
        or "query_canceled" in low
        or pgcode == "57014"
    ):
        return GatewayError(
            QUERY_TIMEOUT,
            f"Sorgu zaman aşımı: {msg[:240]}",
            status=408,
            retryable=True,
        )

    # Connection-class
    if isinstance(exc, (psycopg2.OperationalError, psycopg2.InterfaceError)) or pgcode in (
        "08000",
        "08003",
        "08006",
        "57P01",
        "57P02",
        "57P03",
    ):
        return GatewayError(
            DATABASE_CONNECTION_LOST,
            f"Veritabanı bağlantısı koptu/erişilemedi: {msg[:240]}",
            status=503,
            retryable=True,
        )

    if pgcode in ("42P01",) or "does not exist" in low and "relation" in low:
        return GatewayError(
            TABLE_OR_VIEW_NOT_FOUND,
            f"Tablo/view bulunamadı: {msg[:240]}",
            status=400,
        )
    if pgcode in ("42703",) or ("column" in low and "does not exist" in low):
        return GatewayError(
            COLUMN_NOT_FOUND,
            f"Kolon bulunamadı: {msg[:240]}",
            status=400,
        )
    if pgcode in ("42501",) or "permission denied" in low:
        return GatewayError(
            DATABASE_PERMISSION_DENIED,
            f"Yetki reddedildi: {msg[:240]}",
            status=403,
        )

    # Remaining SQL/runtime errors — not "database unavailable"
    return GatewayError(
        "SQL_EXECUTION_FAILED",
        f"Sorgu çalıştırılamadı: {msg[:320]}",
        status=400,
        retryable=False,
    )


def execute_postgres_ro(
    ds: dict[str, Any],
    sql: str,
    *,
    tenant_id: str | None,
    timeout_ms: int,
    max_rows: int,
    size_profile: str = "medium",
    run_explain: bool = True,
    settings: Settings | None = None,
    registry: PoolRegistry | None = None,
    parameters: dict[str, Any] | None = None,
) -> tuple[list[str], list[dict[str, Any]], bool, int]:
    """Returns columns, rows, truncated, execution_time_ms."""
    settings = settings or get_settings()
    registry = registry or get_pool_registry()
    t0 = time.time()
    from query_gateway.infrastructure.parser.bind_params import (
        assert_binds_present,
        extract_bind_names,
        probe_sql_for_parse,
        to_psycopg_sql,
        validate_parameters,
    )

    bind_params = validate_parameters(parameters)
    has_binds = bool(extract_bind_names(sql)) or bool(bind_params)
    if has_binds:
        assert_binds_present(sql, bind_params)
        exec_sql = to_psycopg_sql(sql)
        explain_sql = probe_sql_for_parse(sql, bind_params)
        exec_args: dict[str, Any] | None = bind_params
    else:
        exec_sql = sql
        explain_sql = sql
        exec_args = None

    ds_id, conn = registry.get_postgres_conn(ds)
    try:
        conn.set_session(readonly=True, autocommit=False)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("BEGIN")
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(f"SET LOCAL statement_timeout = '{int(timeout_ms)}ms'")
            cur.execute(f"SET LOCAL lock_timeout = '{int(settings.lock_timeout_ms)}ms'")
            cur.execute(
                f"SET LOCAL idle_in_transaction_session_timeout = '{int(timeout_ms + 5000)}ms'"
            )
            if tenant_id:
                # set_config is safer than interpolating into SET LOCAL
                cur.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))

            if run_explain:
                cur.execute(f"SET LOCAL statement_timeout = '{int(settings.explain_timeout_ms)}ms'")
                try:
                    cur.execute(f"EXPLAIN (FORMAT JSON) {explain_sql}")
                    explain_row = cur.fetchone()
                    plan = None
                    if explain_row:
                        plan = list(explain_row.values())[0]
                        if isinstance(plan, str):
                            plan = json.loads(plan)
                    analyze_explain_json(plan, size_profile=size_profile, settings=settings)
                except GatewayError:
                    conn.rollback()
                    raise
                except Exception as e:
                    conn.rollback()
                    mapped = _map_psycopg_error(e)
                    if mapped.code == QUERY_TIMEOUT:
                        mapped.message = f"EXPLAIN zaman aşımı: {str(e)[:200]}"
                    elif mapped.code == "SQL_EXECUTION_FAILED":
                        # EXPLAIN SQL errors — keep as parse/exec, not UNAVAILABLE
                        mapped.message = f"EXPLAIN başarısız: {str(e)[:240]}"
                    log.warning(
                        "explain_failed code=%s ds=%s err=%s",
                        mapped.code,
                        ds.get("id") or ds_id,
                        str(e)[:200],
                    )
                    raise mapped from e
                cur.execute(f"SET LOCAL statement_timeout = '{int(timeout_ms)}ms'")

            try:
                if exec_args is not None:
                    cur.execute(exec_sql, exec_args)
                else:
                    cur.execute(exec_sql)
            except Exception as e:
                conn.rollback()
                mapped = _map_psycopg_error(e)
                log.warning(
                    "execute_failed code=%s ds=%s err=%s",
                    mapped.code,
                    ds.get("id") or ds_id,
                    str(e)[:240],
                )
                raise mapped from e

            if cur.description is None:
                conn.rollback()
                return [], [], False, int((time.time() - t0) * 1000)

            cols = [d.name for d in cur.description]
            rows_raw = [dict(r) for r in cur.fetchmany(max_rows + 1)]
            truncated = len(rows_raw) > max_rows
            rows_raw = rows_raw[:max_rows]
            conn.rollback()
            return cols, rows_raw, truncated, int((time.time() - t0) * 1000)
    except GatewayError:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        mapped = _map_psycopg_error(e)
        if mapped.code not in (
            QUERY_TIMEOUT,
            DATABASE_CONNECTION_LOST,
            TABLE_OR_VIEW_NOT_FOUND,
            COLUMN_NOT_FOUND,
            DATABASE_PERMISSION_DENIED,
            "SQL_EXECUTION_FAILED",
        ):
            mapped = GatewayError(
                DATABASE_UNAVAILABLE,
                f"Veritabanı kullanılamıyor: {str(e)[:240]}",
                status=503,
                retryable=True,
            )
        log.error("postgres_ro_outer code=%s err=%s", mapped.code, str(e)[:240])
        raise mapped from e
    finally:
        registry.put_postgres_conn(ds_id, conn)
