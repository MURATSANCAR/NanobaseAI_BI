"""PostgreSQL read-only execute with RLS GUC + EXPLAIN cost guard."""

from __future__ import annotations

import json
import time
from typing import Any

import psycopg2.extras

from query_gateway.config.settings import Settings, get_settings
from query_gateway.domain.errors import DATABASE_UNAVAILABLE, QUERY_TIMEOUT, GatewayError
from query_gateway.infrastructure.database.explain_parser import analyze_explain_json
from query_gateway.infrastructure.database.pool_registry import PoolRegistry, get_pool_registry


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
                    if "timeout" in str(e).lower() or "canceling" in str(e).lower():
                        raise GatewayError(
                            QUERY_TIMEOUT,
                            "EXPLAIN zaman aşımı.",
                            status=408,
                            retryable=True,
                        ) from e
                    raise GatewayError(
                        QUERY_TIMEOUT if "cancel" in str(e).lower() else DATABASE_UNAVAILABLE,
                        "EXPLAIN başarısız.",
                        status=400,
                    ) from e
                cur.execute(f"SET LOCAL statement_timeout = '{int(timeout_ms)}ms'")

            try:
                if exec_args is not None:
                    cur.execute(exec_sql, exec_args)
                else:
                    cur.execute(exec_sql)
            except Exception as e:
                conn.rollback()
                msg = str(e).lower()
                if "timeout" in msg or "canceling statement" in msg:
                    raise GatewayError(QUERY_TIMEOUT, "Sorgu zaman aşımı.", status=408, retryable=True) from e
                raise GatewayError(
                    DATABASE_UNAVAILABLE,
                    "Sorgu çalıştırılamadı.",
                    status=400,
                ) from e

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
        raise GatewayError(
            DATABASE_UNAVAILABLE,
            "Veritabanı kullanılamıyor.",
            status=503,
            retryable=True,
        ) from e
    finally:
        registry.put_postgres_conn(ds_id, conn)
