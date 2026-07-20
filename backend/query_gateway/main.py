"""Nanobase Query Gateway ASGI app (Faz 5 harden + legacy routes)."""

from __future__ import annotations

import os
import time
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from query_gateway.api.exception_handlers import register_exception_handlers
from query_gateway.api.v1 import execution as execution_routes
from query_gateway.api.v1 import health as health_routes
from query_gateway.api.v1 import validation as validation_routes
from query_gateway.config.settings import get_settings
from query_gateway.guardrails import validate_and_rewrite
from query_gateway.infrastructure.database.datasources import load_datasources
from query_gateway.infrastructure.database.pool_registry import get_pool_registry
from query_gateway import sap as sap_mod

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
    from starlette.responses import Response

    REQ_COUNTER = Counter("query_gateway_requests_total", "QG requests", ["route", "status"])
    PROM_OK = True
except Exception:  # pragma: no cover
    PROM_OK = False
    REQ_COUNTER = None


class LegacyExecuteRequest(BaseModel):
    datasource_id: str = Field(..., min_length=1)
    sql: str = Field(..., min_length=1)
    explain: bool = False
    max_limit: Optional[int] = None
    timeout_s: Optional[float] = None
    parameters: Optional[dict[str, Any]] = None


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Nanobase Query Gateway", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get("PORTAL_CORS_ORIGINS", "*").split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(health_routes.router)
    app.include_router(validation_routes.router)
    app.include_router(execution_routes.router)

    @app.on_event("shutdown")
    def _shutdown() -> None:
        get_pool_registry().close_all()

    if PROM_OK:

        @app.get("/metrics")
        def metrics() -> Response:
            return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    # ---- Legacy routes (Oracle/SAP/alerts) ----

    @app.get("/health")
    def health() -> dict[str, Any]:
        ds = load_datasources(settings)
        oracle_ready = False
        hana_ready = False
        try:
            import oracledb  # noqa: F401

            oracle_ready = True
        except ImportError:
            pass
        try:
            from hdbcli import dbapi  # noqa: F401

            hana_ready = True
        except ImportError:
            pass
        return {
            "ok": True,
            "service": "query_gateway",
            "version": app.version,
            "datasources": sorted(ds.keys()),
            "oracle_driver": oracle_ready,
            "hana_driver": hana_ready,
            "odata_ready": True,
            "max_limit": settings.max_limit,
            "timeout_s": settings.statement_timeout_ms / 1000.0,
            "faz5": True,
        }

    @app.get("/api/v1/query/datasources")
    def list_datasources() -> dict[str, Any]:
        ds = load_datasources(settings)
        return {
            "datasources": [
                {
                    "id": d["id"],
                    "driver": d.get("driver") or "postgresql",
                    "dialect": d.get("dialect"),
                    "host": d.get("host"),
                    "port": d.get("port"),
                    "database": d.get("database"),
                    "service_name": d.get("service_name"),
                    "user": d.get("user"),
                    "sslmode": d.get("sslmode"),
                    "label": d.get("label"),
                }
                for d in ds.values()
            ]
        }

    def _parse_odata_request(raw: str) -> tuple[str, dict[str, str]]:
        s = (raw or "").strip()
        if s.upper().startswith("GET "):
            s = s[4:].strip()
        if "?" in s:
            entity, qs = s.split("?", 1)
            from urllib.parse import parse_qsl

            q = {k: v for k, v in parse_qsl(qs, keep_blank_values=True)}
        else:
            entity, q = s, {}
        return entity.strip(), q

    def _serialize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for r in rows:
            item: dict[str, Any] = {}
            for k, v in r.items():
                if hasattr(v, "isoformat"):
                    item[k] = v.isoformat()
                elif isinstance(v, (bytes, memoryview)):
                    item[k] = bytes(v).decode("utf-8", errors="replace")
                else:
                    item[k] = v
            out.append(item)
        return out

    def _cap_rows(cols: list[str], rows_raw: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
        truncated = len(rows_raw) > settings.max_rows
        rows_raw = rows_raw[: settings.max_rows]
        cells = len(rows_raw) * max(len(cols), 1)
        max_cells = int(os.environ.get("QG_MAX_CELLS", "50000"))
        if cells > max_cells:
            keep = max(1, max_cells // max(len(cols), 1))
            rows_raw = rows_raw[:keep]
            truncated = True
        return rows_raw, truncated

    def _execute_postgres_legacy(
        ds: dict[str, Any],
        sql: str,
        *,
        timeout_s: float,
        explain: bool,
        parameters: dict[str, Any] | None = None,
    ):
        import psycopg2
        import psycopg2.extras
        import re

        exec_sql = f"EXPLAIN (FORMAT TEXT) {sql}" if explain else sql
        # Named :param → %(param)s for psycopg2
        bind = dict(parameters or {})
        if bind:
            exec_sql = re.sub(r":([A-Za-z_][A-Za-z0-9_]*)", r"%(\1)s", exec_sql)
        conn = psycopg2.connect(
            host=ds["host"],
            port=ds["port"],
            dbname=ds["database"],
            user=ds["user"],
            password=ds["password"],
            sslmode=ds.get("sslmode") or "prefer",
            connect_timeout=10,
        )
        try:
            conn.set_session(readonly=True, autocommit=True)
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(f"SET statement_timeout = '{int(timeout_s * 1000)}'")
                if bind and not explain:
                    cur.execute(exec_sql, bind)
                else:
                    cur.execute(exec_sql)
                if cur.description is None:
                    return [], [], False
                cols = [d.name for d in cur.description]
                rows_raw = [dict(r) for r in cur.fetchmany(settings.max_rows + 1)]
                rows_raw, truncated = _cap_rows(cols, rows_raw)
                return cols, _serialize_rows(rows_raw), truncated
        finally:
            conn.close()

    def _execute_oracle(ds: dict[str, Any], sql: str, *, timeout_s: float, explain: bool):
        try:
            import oracledb
        except ImportError as e:
            raise HTTPException(503, "oracledb not installed") from e
        conn = oracledb.connect(user=ds["user"], password=ds["password"], dsn=ds["dsn"])
        try:
            conn.call_timeout = int(timeout_s * 1000)
            with conn.cursor() as cur:
                if explain:
                    cur.execute(f"EXPLAIN PLAN FOR {sql}")
                    try:
                        cur.execute(
                            "SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY(NULL, NULL, 'BASIC'))"
                        )
                        rows = cur.fetchmany(settings.max_rows + 1)
                        cols = [d[0].lower() for d in (cur.description or [])]
                        dict_rows = [dict(zip(cols, r)) for r in rows]
                        dict_rows, truncated = _cap_rows(cols, dict_rows)
                        return cols, _serialize_rows(dict_rows), truncated
                    except Exception:
                        return (
                            ["plan"],
                            [{"plan": "EXPLAIN PLAN FOR accepted"}],
                            False,
                        )
                cur.execute(sql)
                if cur.description is None:
                    return [], [], False
                cols = [d[0].lower() for d in cur.description]
                rows = cur.fetchmany(settings.max_rows + 1)
                dict_rows = [dict(zip(cols, r)) for r in rows]
                dict_rows, truncated = _cap_rows(cols, dict_rows)
                return cols, _serialize_rows(dict_rows), truncated
        finally:
            conn.close()

    @app.post("/api/v1/query/validate")
    def validate_sql(body: LegacyExecuteRequest) -> dict[str, Any]:
        ds = load_datasources(settings).get(body.datasource_id)
        if not ds:
            raise HTTPException(404, f"datasource not registered: {body.datasource_id}")
        max_limit = min(body.max_limit or settings.max_limit, settings.max_limit)
        if ds.get("driver") == "odata":
            entity, q = _parse_odata_request(body.sql)
            err = sap_mod.validate_odata_path(entity, ds.get("allowed_entities"))
            return {
                "ok": err is None,
                "sql": body.sql,
                "error": err,
                "tables": [entity] if entity else [],
                "dialect": "odata",
                "odata_query": q,
            }
        sql_for_guard = body.sql
        if body.parameters:
            try:
                from query_gateway.infrastructure.parser.bind_params import probe_sql_for_parse

                sql_for_guard = probe_sql_for_parse(body.sql, body.parameters)
            except Exception:
                sql_for_guard = body.sql
        result = validate_and_rewrite(
            sql_for_guard,
            dialect=ds["dialect"],
            allowed_tables=ds.get("allowed_tables"),
            max_limit=max_limit,
        )
        return {
            "ok": result.ok,
            "sql": result.sql if result.ok else body.sql,
            "error": result.error,
            "tables": result.tables,
            "dialect": ds["dialect"],
            "parameters": body.parameters or {},
        }

    @app.post("/api/v1/query/execute")
    def execute_sql(body: LegacyExecuteRequest) -> dict[str, Any]:
        ds = load_datasources(settings).get(body.datasource_id)
        if not ds:
            raise HTTPException(404, f"datasource not registered: {body.datasource_id}")
        max_limit = min(body.max_limit or settings.max_limit, settings.max_limit)
        timeout_s = min(body.timeout_s or (settings.statement_timeout_ms / 1000.0), 60.0)
        driver = ds.get("driver") or "postgresql"
        t0 = time.time()

        if driver == "odata":
            try:
                entity, q = _parse_odata_request(body.sql)
                result = sap_mod.execute_odata(
                    ds, entity=entity, query=q, timeout_s=timeout_s, max_rows=max_limit
                )
            except Exception as e:
                raise HTTPException(400, f"odata failed: {e}") from e
            return {
                "ok": True,
                "sql": body.sql,
                "columns": result["columns"],
                "rows": result["rows"],
                "row_count": result["row_count"],
                "truncated": result["truncated"],
                "elapsed_ms": int((time.time() - t0) * 1000),
                "tables": [entity],
                "explain": False,
                "datasource_id": body.datasource_id,
                "dialect": "odata",
                "driver": "odata",
            }

        sql_for_guard = body.sql
        if body.parameters:
            try:
                from query_gateway.infrastructure.parser.bind_params import probe_sql_for_parse

                sql_for_guard = probe_sql_for_parse(body.sql, body.parameters)
            except Exception:
                sql_for_guard = body.sql
        guard = validate_and_rewrite(
            sql_for_guard,
            dialect=ds["dialect"],
            allowed_tables=ds.get("allowed_tables"),
            max_limit=max_limit,
        )
        if not guard.ok:
            raise HTTPException(400, guard.error or "sql rejected")

        # Keep original named-bind template for drivers that accept parameters
        exec_sql = body.sql if body.parameters else guard.sql
        try:
            if driver == "oracle":
                cols, rows, truncated = _execute_oracle(
                    ds, exec_sql if body.parameters else guard.sql, timeout_s=timeout_s, explain=body.explain
                )
            elif driver == "hana":
                cols, rows, truncated = sap_mod.execute_hana(
                    ds,
                    exec_sql if body.parameters else guard.sql,
                    timeout_s=timeout_s,
                    max_rows=settings.max_rows,
                    max_cells=int(os.environ.get("QG_MAX_CELLS", "50000")),
                    explain=body.explain,
                )
            else:
                cols, rows, truncated = _execute_postgres_legacy(
                    ds,
                    exec_sql if body.parameters else guard.sql,
                    timeout_s=timeout_s,
                    explain=body.explain,
                    parameters=body.parameters,
                )
        except HTTPException:
            raise
        except Exception as e:
            # Structured code so BI chat repair can retry (bare HTTP 400 was not repairable).
            from query_gateway.infrastructure.database.postgres_executor import (
                _map_psycopg_error,
            )

            raise _map_psycopg_error(e) from e

        return {
            "ok": True,
            "sql": guard.sql,
            "columns": cols,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
            "elapsed_ms": int((time.time() - t0) * 1000),
            "tables": guard.tables,
            "explain": body.explain,
            "datasource_id": body.datasource_id,
            "dialect": ds["dialect"],
            "driver": driver,
        }

    return app


app = create_app()
