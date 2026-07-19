"""Nanobase Query Gateway — SELECT-only SQL behind sqlglot (Postgres + Oracle).

Listen :8792 (loopback). Datasources with RO credentials only.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from query_gateway.guardrails import validate_and_rewrite
from query_gateway import sap as sap_mod

SECRETS = Path(os.environ.get("SECRETS_ROOT", "/data/nanobaseai/bi/secrets"))
GATEWAY_PORT = int(os.environ.get("QUERY_GATEWAY_PORT", "8792"))
DEFAULT_TIMEOUT_S = float(os.environ.get("QG_STATEMENT_TIMEOUT_S", "15"))
DEFAULT_MAX_LIMIT = int(os.environ.get("QG_MAX_LIMIT", "500"))
DEFAULT_MAX_ROWS = int(os.environ.get("QG_MAX_ROWS", "500"))
DEFAULT_MAX_CELLS = int(os.environ.get("QG_MAX_CELLS", "50000"))

# Default SSB (Oracle Always Free sample) allowlist — override per source in secrets JSON
DEFAULT_ORACLE_SSB_TABLES = {
    "customer",
    "ssb.customer",
    "part",
    "ssb.part",
    "supplier",
    "ssb.supplier",
    "date_dim",
    "ssb.date_dim",
    "lineorder",
    "ssb.lineorder",
    "dwdate",
    "ssb.dwdate",
}

app = FastAPI(title="Nanobase Query Gateway", version="0.9.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("PORTAL_CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ExecuteRequest(BaseModel):
    datasource_id: str = Field(..., min_length=1)
    sql: str = Field(..., min_length=1)
    explain: bool = False
    max_limit: Optional[int] = None
    timeout_s: Optional[float] = None


def _password_from_cfg(cfg: dict[str, Any]) -> str:
    if cfg.get("password"):
        return str(cfg["password"])
    ref = cfg.get("secret_ref") or cfg.get("password_file")
    if ref:
        try:
            from nanobase_api.secrets_resolver import resolve_secret

            return resolve_secret(str(ref))
        except Exception:
            # fallback: treat as file path
            p = Path(str(ref).removeprefix("file:"))
            if p.is_file():
                return p.read_text(encoding="utf-8").strip()
    return ""


def _allowed_tables(cfg: dict[str, Any], default: set[str] | None) -> set[str] | None:
    raw = cfg.get("allowed_tables")
    if raw is None:
        return default
    if raw == [] or raw == "*":
        return None if raw == "*" else set()
    return {str(x) for x in raw}


def _load_datasources() -> dict[str, dict[str, Any]]:
    """RO datasources only. Passwords from secret files / env — never from request."""
    ds: dict[str, dict[str, Any]] = {}

    ro_file = SECRETS / "reporting-ro.password"
    if ro_file.is_file() or os.environ.get("REPORTING_RO_SECRET_REF"):
        try:
            from nanobase_api.secrets_resolver import resolve_secret

            reporting_pw = resolve_secret(
                os.environ.get("REPORTING_RO_SECRET_REF"),
                default_file="reporting-ro.password",
            )
        except Exception:
            reporting_pw = ro_file.read_text(encoding="utf-8").strip() if ro_file.is_file() else ""
        if reporting_pw:
            ds["bi_reporting"] = {
            "id": "bi_reporting",
            "driver": "postgresql",
            "host": os.environ.get("REPORTING_HOST", "127.0.0.1"),
            "port": int(os.environ.get("REPORTING_PORT", "5435")),
            "database": os.environ.get("REPORTING_DB", "bi_reporting"),
            "user": os.environ.get("REPORTING_RO_USER", "bi_reporting_ro"),
            "password": reporting_pw,
            "sslmode": "disable",
            "dialect": "postgres",
            "allowed_tables": {
                "customers",
                "products",
                "orders",
                "order_items",
                "v_order_revenue",
                "companies",
                "branches",
                "customer_addresses",
                "sales_orders",
                "sales_order_items",
                "invoices",
                "payments",
                "currency_rates",
                "returns",
                "v_invoice_open",
                "analytics.customers",
                "analytics.products",
                "analytics.orders",
                "analytics.order_items",
                "analytics.v_order_revenue",
                "analytics.companies",
                "analytics.branches",
                "analytics.customer_addresses",
                "analytics.sales_orders",
                "analytics.sales_order_items",
                "analytics.invoices",
                "analytics.payments",
                "analytics.currency_rates",
                "analytics.returns",
                "analytics.v_invoice_open",
                "public.customers",
                "public.products",
                "public.orders",
                "public.order_items",
                "public.v_order_revenue",
                "public.companies",
                "public.branches",
                "public.customer_addresses",
                "public.sales_orders",
                "public.sales_order_items",
                "public.invoices",
                "public.payments",
                "public.currency_rates",
                "public.returns",
                "public.v_invoice_open",
            },
        }

    # Optional Neon / Postgres RO map
    neon_map = SECRETS / "neon-ro.datasources.json"
    if neon_map.is_file():
        try:
            extra = json.loads(neon_map.read_text(encoding="utf-8"))
            for sid, cfg in (extra.get("sources") or extra).items():
                if not isinstance(cfg, dict):
                    continue
                pw = _password_from_cfg(cfg)
                if pw and cfg.get("host"):
                    ds[str(sid)] = {
                        "id": str(sid),
                        "driver": "postgresql",
                        "host": cfg["host"],
                        "port": int(cfg.get("port") or 5432),
                        "database": cfg.get("database") or "neondb",
                        "user": cfg.get("user") or cfg.get("username"),
                        "password": pw,
                        "sslmode": cfg.get("sslmode") or "require",
                        "dialect": "postgres",
                        "allowed_tables": _allowed_tables(cfg, None),
                    }
        except Exception:
            pass

    # Optional Oracle RO map (Faz 8)
    oracle_map = SECRETS / "oracle-ro.datasources.json"
    if oracle_map.is_file():
        try:
            extra = json.loads(oracle_map.read_text(encoding="utf-8"))
            for sid, cfg in (extra.get("sources") or extra).items():
                if not isinstance(cfg, dict):
                    continue
                pw = _password_from_cfg(cfg)
                user = cfg.get("user") or cfg.get("username")
                dsn = (cfg.get("dsn") or "").strip()
                host = cfg.get("host")
                service = cfg.get("service_name") or cfg.get("service") or cfg.get("database")
                if not pw or not user:
                    continue
                if not dsn and not (host and service):
                    continue
                port = int(cfg.get("port") or 1522)
                if not dsn:
                    dsn = f"{host}:{port}/{service}"
                ds[str(sid)] = {
                    "id": str(sid),
                    "driver": "oracle",
                    "host": host or "",
                    "port": port,
                    "database": service or "",
                    "service_name": service or "",
                    "dsn": dsn,
                    "user": user,
                    "password": pw,
                    "sslmode": cfg.get("sslmode") or "tcps",
                    "dialect": "oracle",
                    "allowed_tables": _allowed_tables(cfg, DEFAULT_ORACLE_SSB_TABLES),
                    "label": cfg.get("label") or sid,
                }
        except Exception:
            pass

    # Optional SAP HANA / CDS-OData RO map (Faz 9)
    sap_map = SECRETS / "sap-ro.datasources.json"
    if sap_map.is_file():
        try:
            extra = json.loads(sap_map.read_text(encoding="utf-8"))
            for sid, cfg in (extra.get("sources") or extra).items():
                if not isinstance(cfg, dict):
                    continue
                driver = (cfg.get("driver") or cfg.get("dialect") or "").lower()
                pw = _password_from_cfg(cfg)
                if driver in ("hana", "sap_hana", "hdb"):
                    if not (cfg.get("host") and (cfg.get("user") or cfg.get("username")) and pw):
                        continue
                    ds[str(sid)] = {
                        "id": str(sid),
                        "driver": "hana",
                        "host": cfg["host"],
                        "port": int(cfg.get("port") or 443),
                        "database": cfg.get("database") or "",
                        "user": cfg.get("user") or cfg.get("username"),
                        "password": pw,
                        "sslmode": "require",
                        "dialect": sap_mod.HANA_SQLGLOT_DIALECT,
                        "allowed_tables": _allowed_tables(cfg, sap_mod.DEFAULT_HANA_TABLES),
                        "encrypt": bool(cfg.get("encrypt", True)),
                        "ssl_validate": bool(cfg.get("ssl_validate", False)),
                        "label": cfg.get("label") or sid,
                    }
                elif driver in ("odata", "cds", "cds_odata"):
                    base_url = (cfg.get("base_url") or cfg.get("url") or "").rstrip("/")
                    if not base_url:
                        continue
                    token = cfg.get("bearer_token")
                    if not token and cfg.get("token_file"):
                        token = Path(cfg["token_file"]).read_text(encoding="utf-8").strip()
                    ds[str(sid)] = {
                        "id": str(sid),
                        "driver": "odata",
                        "host": base_url,
                        "port": 443,
                        "database": "",
                        "base_url": base_url,
                        "user": cfg.get("user") or cfg.get("username") or "",
                        "password": pw,
                        "bearer_token": token,
                        "sslmode": "require",
                        "verify_tls": bool(cfg.get("verify_tls", True)),
                        "dialect": "odata",
                        "allowed_entities": set(cfg.get("allowed_entities") or cfg.get("allowed_tables") or []),
                        "label": cfg.get("label") or sid,
                    }
        except Exception:
            pass

    return ds


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
    truncated = len(rows_raw) > DEFAULT_MAX_ROWS
    rows_raw = rows_raw[:DEFAULT_MAX_ROWS]
    cells = len(rows_raw) * max(len(cols), 1)
    if cells > DEFAULT_MAX_CELLS:
        keep = max(1, DEFAULT_MAX_CELLS // max(len(cols), 1))
        rows_raw = rows_raw[:keep]
        truncated = True
    return rows_raw, truncated


def _execute_postgres(
    ds: dict[str, Any], sql: str, *, timeout_s: float, explain: bool
) -> tuple[list[str], list[dict[str, Any]], bool]:
    exec_sql = f"EXPLAIN (FORMAT TEXT) {sql}" if explain else sql
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
            cur.execute(exec_sql)
            if cur.description is None:
                return [], [], False
            cols = [d.name for d in cur.description]
            rows_raw = [dict(r) for r in cur.fetchmany(DEFAULT_MAX_ROWS + 1)]
            rows_raw, truncated = _cap_rows(cols, rows_raw)
            return cols, _serialize_rows(rows_raw), truncated
    finally:
        conn.close()


def _execute_oracle(
    ds: dict[str, Any], sql: str, *, timeout_s: float, explain: bool
) -> tuple[list[str], list[dict[str, Any]], bool]:
    try:
        import oracledb
    except ImportError as e:
        raise HTTPException(
            503, "oracledb not installed — run deploy-query-gateway.sh"
        ) from e

    # Thin mode (no Instant Client). call_timeout is milliseconds.
    oracledb.defaults.config_dir = None
    conn = oracledb.connect(
        user=ds["user"],
        password=ds["password"],
        dsn=ds["dsn"],
    )
    try:
        conn.call_timeout = int(timeout_s * 1000)
        with conn.cursor() as cur:
            if explain:
                # Oracle has no single-shot EXPLAIN result set like Postgres.
                # Return a plan note; full DBMS_XPLAN needs plan_table privilege.
                cur.execute(f"EXPLAIN PLAN FOR {sql}")
                try:
                    cur.execute(
                        "SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY(NULL, NULL, 'BASIC'))"
                    )
                    rows = cur.fetchmany(DEFAULT_MAX_ROWS + 1)
                    cols = [d[0].lower() for d in (cur.description or [])]
                    dict_rows = [dict(zip(cols, r)) for r in rows]
                    dict_rows, truncated = _cap_rows(cols, dict_rows)
                    return cols, _serialize_rows(dict_rows), truncated
                except Exception:
                    return (
                        ["plan"],
                        [{"plan": "EXPLAIN PLAN FOR accepted (DBMS_XPLAN unavailable)"}],
                        False,
                    )

            cur.execute(sql)
            if cur.description is None:
                return [], [], False
            cols = [d[0].lower() for d in cur.description]
            rows = cur.fetchmany(DEFAULT_MAX_ROWS + 1)
            dict_rows = [dict(zip(cols, r)) for r in rows]
            dict_rows, truncated = _cap_rows(cols, dict_rows)
            return cols, _serialize_rows(dict_rows), truncated
    finally:
        conn.close()


@app.get("/health")
def health() -> dict[str, Any]:
    ds = _load_datasources()
    oracle_ready = False
    hana_ready = False
    try:
        import oracledb  # noqa: F401

        oracle_ready = True
    except ImportError:
        oracle_ready = False
    try:
        from hdbcli import dbapi  # noqa: F401

        hana_ready = True
    except ImportError:
        hana_ready = False
    return {
        "ok": True,
        "service": "query_gateway",
        "version": app.version,
        "datasources": sorted(ds.keys()),
        "oracle_driver": oracle_ready,
        "hana_driver": hana_ready,
        "odata_ready": True,
        "max_limit": DEFAULT_MAX_LIMIT,
        "timeout_s": DEFAULT_TIMEOUT_S,
    }


@app.get("/api/v1/query/datasources")
def list_datasources() -> dict[str, Any]:
    ds = _load_datasources()
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


@app.post("/api/v1/query/validate")
def validate_sql(body: ExecuteRequest) -> dict[str, Any]:
    ds = _load_datasources().get(body.datasource_id)
    if not ds:
        raise HTTPException(404, f"datasource not registered for gateway: {body.datasource_id}")
    max_limit = min(body.max_limit or DEFAULT_MAX_LIMIT, DEFAULT_MAX_LIMIT)

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

    result = validate_and_rewrite(
        body.sql,
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
    }


def _parse_odata_request(raw: str) -> tuple[str, dict[str, str]]:
    """Accept 'EntitySet' or 'EntitySet?$select=a&$top=10' (optional leading GET)."""
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


@app.post("/api/v1/query/execute")
def execute_sql(body: ExecuteRequest) -> dict[str, Any]:
    ds = _load_datasources().get(body.datasource_id)
    if not ds:
        raise HTTPException(404, f"datasource not registered for gateway: {body.datasource_id}")

    max_limit = min(body.max_limit or DEFAULT_MAX_LIMIT, DEFAULT_MAX_LIMIT)
    timeout_s = min(body.timeout_s or DEFAULT_TIMEOUT_S, 60.0)
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
            "odata_url": result.get("url"),
        }

    guard = validate_and_rewrite(
        body.sql,
        dialect=ds["dialect"],
        allowed_tables=ds.get("allowed_tables"),
        max_limit=max_limit,
    )
    if not guard.ok:
        raise HTTPException(400, guard.error or "sql rejected")

    try:
        if driver == "oracle":
            cols, rows, truncated = _execute_oracle(
                ds, guard.sql, timeout_s=timeout_s, explain=body.explain
            )
        elif driver == "hana":
            cols, rows, truncated = sap_mod.execute_hana(
                ds,
                guard.sql,
                timeout_s=timeout_s,
                max_rows=DEFAULT_MAX_ROWS,
                max_cells=DEFAULT_MAX_CELLS,
                explain=body.explain,
            )
        else:
            cols, rows, truncated = _execute_postgres(
                ds, guard.sql, timeout_s=timeout_s, explain=body.explain
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"execution failed: {e}") from e

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
