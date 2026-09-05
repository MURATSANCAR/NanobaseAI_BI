"""Microsoft SQL Server read-only executor (pymssql).

Order: SHOWPLAN cost guard → session limits → execute inside a transaction that
is ALWAYS rolled back → row cap. SQL Server has no read-only transaction mode,
so read-only-ness rests on (1) the parser/policy layer admitting SELECT only,
(2) the unconditional ROLLBACK, and (3) the recommended db_datareader login.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from query_gateway.config.settings import Settings, get_settings
from query_gateway.domain.errors import (
    DATABASE_UNAVAILABLE,
    QUERY_COST_EXCEEDED,
    QUERY_TIMEOUT,
    GatewayError,
)

MSSQL_PLAN_VALIDATION_UNAVAILABLE = "MSSQL_PLAN_VALIDATION_UNAVAILABLE"

_CONN_LOCK = threading.Lock()
_CONN_CACHE: dict[str, Any] = {}


def _connect(ds: dict[str, Any], *, settings: Settings, timeout_ms: int) -> Any:
    import pymssql

    return pymssql.connect(
        server=str(ds.get("host") or "127.0.0.1"),
        port=int(ds.get("port") or 1433),
        user=str(ds.get("user") or ""),
        password=str(ds.get("password") or ""),
        database=str(ds.get("database") or "master"),
        login_timeout=int(settings.pool_timeout_s) + 5,
        timeout=max(1, int(timeout_ms / 1000) + 1),
        tds_version=str(ds.get("tds_version") or "7.4"),
        charset="UTF-8",
        as_dict=True,
        appname="nanobaseai-bi-gateway",
        autocommit=False,
    )


def _acquire(ds: dict[str, Any], *, settings: Settings, timeout_ms: int) -> tuple[str, Any]:
    ds_id = str(ds.get("id") or "mssql")
    with _CONN_LOCK:
        conn = _CONN_CACHE.pop(ds_id, None)
    if conn is not None:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchall()
            return ds_id, conn
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
    try:
        return ds_id, _connect(ds, settings=settings, timeout_ms=timeout_ms)
    except Exception as e:  # noqa: BLE001
        raise GatewayError(
            DATABASE_UNAVAILABLE,
            f"SQL Server bağlantısı kurulamadı: {str(e)[:200]}",
            status=503,
            retryable=True,
        ) from e


def _release(ds_id: str, conn: Any, *, discard: bool = False) -> None:
    if discard:
        try:
            conn.close()
        except Exception:
            pass
        return
    with _CONN_LOCK:
        old = _CONN_CACHE.get(ds_id)
        _CONN_CACHE[ds_id] = conn
    if old is not None and old is not conn:
        try:
            old.close()
        except Exception:
            pass


def invalidate(ds_id: str) -> None:
    with _CONN_LOCK:
        conn = _CONN_CACHE.pop(ds_id, None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass


# --- plan guard ---------------------------------------------------------------


def analyze_showplan(rows: list[dict[str, Any]], *, size_profile: str, settings: Settings) -> dict[str, Any]:
    """SHOWPLAN_ALL rows → same verdicts as the Postgres EXPLAIN guard.

    Row 1 (NodeId 1) is the statement: EstimateRows = estimated result rows.
    Scan operators whose Argument carries no WHERE: predicate are "filterless".
    """
    if not rows:
        raise GatewayError(QUERY_COST_EXCEEDED, "SHOWPLAN çıktısı okunamadı.", status=400)
    root = rows[0]
    plan_rows = float(root.get("EstimateRows") or 0)
    total_cost = float(root.get("TotalSubtreeCost") or 0)
    filterless: list[str] = []
    max_scan_rows = 0.0
    for r in rows[1:]:
        op = str(r.get("PhysicalOp") or r.get("LogicalOp") or "")
        arg = str(r.get("Argument") or "")
        if "Scan" in op and "OBJECT:" in arg and "WHERE:" not in arg:
            obj = arg.split("OBJECT:", 1)[1].split(")", 1)[0].strip("([] ")
            filterless.append(obj.replace("[", "").replace("]", ""))
            max_scan_rows = max(max_scan_rows, float(r.get("EstimateRows") or 0))
    profile = (size_profile or "medium").lower()
    max_rows = {
        "small": settings.cost_max_rows_small,
        "medium": settings.cost_max_rows_medium,
        "large": settings.cost_max_rows_large,
        "very_large": settings.cost_max_rows_large * 2,
    }.get(profile, settings.cost_max_rows_medium)
    if filterless and max_scan_rows >= max(50_000.0, max_rows * 0.01):
        rels = ", ".join(sorted(set(filterless))[:8])
        raise GatewayError(
            QUERY_COST_EXCEEDED,
            (
                f"Plan: filtresiz tablo taraması ({rels}), tahmini satır={int(max_scan_rows)}. "
                "Tarih/predicate ekleyin veya üst belge toplam kolonlarını kullanın."
            ),
            status=400,
            details=[{"filterless_scan": filterless, "plan_rows": max_scan_rows}],
        )
    if plan_rows > max_rows:
        raise GatewayError(
            QUERY_COST_EXCEEDED,
            "Sorgu tahmini satır sayısı eşiği aşıyor. Tarih aralığını daraltın.",
            status=400,
        )
    return {"plan_rows": plan_rows, "total_cost": total_cost, "filterless": filterless}


def _map_error(e: Exception) -> GatewayError:
    msg = str(e)
    low = msg.lower()
    if "timeout" in low or "timed out" in low:
        return GatewayError(QUERY_TIMEOUT, "Sorgu zaman aşımına uğradı.", status=408, retryable=True)
    if "login failed" in low or "adaptive server" in low or "connection" in low and "closed" in low:
        return GatewayError(DATABASE_UNAVAILABLE, f"SQL Server bağlantı hatası: {msg[:200]}", status=503, retryable=True)
    if "permission" in low or "denied" in low:
        return GatewayError("PERMISSION_DENIED", f"SQL Server yetki hatası: {msg[:200]}", status=403)
    if "invalid object name" in low:
        return GatewayError("TABLE_OR_VIEW_NOT_FOUND", f"Tablo/görünüm bulunamadı: {msg[:200]}", status=400)
    if "invalid column name" in low:
        return GatewayError("COLUMN_NOT_FOUND", f"Kolon bulunamadı: {msg[:200]}", status=400)
    return GatewayError("SQL_EXECUTION_FAILED", f"Sorgu çalıştırılamadı: {msg[:320]}", status=400, retryable=False)


def execute_mssql_ro(
    ds: dict[str, Any],
    sql: str,
    *,
    tenant_id: str | None,
    timeout_ms: int,
    max_rows: int,
    size_profile: str = "medium",
    run_explain: bool = True,
    settings: Settings | None = None,
    parameters: dict[str, Any] | None = None,
) -> tuple[list[str], list[dict[str, Any]], bool, int]:
    """Returns columns, rows, truncated, execution_time_ms."""
    settings = settings or get_settings()
    if parameters:
        raise GatewayError("BIND_PARAMS_UNSUPPORTED", "SQL Server yolunda bind parametreleri henüz desteklenmiyor.", status=400)
    t0 = time.time()
    ds_id, conn = _acquire(ds, settings=settings, timeout_ms=timeout_ms)
    discard = False
    try:
        cur = conn.cursor()
        cur.execute("SET NOCOUNT ON; SET ARITHABORT ON; SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
        cur.execute(f"SET LOCK_TIMEOUT {int(settings.lock_timeout_ms)}")

        if run_explain:
            try:
                cur.execute("SET SHOWPLAN_ALL ON")
                cur.execute(sql)
                plan_rows = list(cur.fetchall() or [])
                cur.execute("SET SHOWPLAN_ALL OFF")
            except GatewayError:
                raise
            except Exception as e:  # noqa: BLE001
                discard = True
                mapped = _map_error(e)
                if mapped.code in ("TABLE_OR_VIEW_NOT_FOUND", "COLUMN_NOT_FOUND", "SQL_EXECUTION_FAILED"):
                    raise mapped from e
                raise GatewayError(
                    MSSQL_PLAN_VALIDATION_UNAVAILABLE,
                    f"SQL Server plan doğrulaması çalıştırılamadı: {str(e)[:160]}",
                    status=503,
                    retryable=True,
                ) from e
            analyze_showplan(plan_rows, size_profile=size_profile, settings=settings)

        try:
            cur.execute(sql)
            fetched = list(cur.fetchmany(max_rows + 1) or [])
        except Exception as e:  # noqa: BLE001
            mapped = _map_error(e)
            if mapped.code in (QUERY_TIMEOUT, DATABASE_UNAVAILABLE):
                discard = True
            raise mapped from e
        columns = [str(d[0]) for d in (cur.description or [])]
        truncated = len(fetched) > max_rows
        rows = fetched[:max_rows]
        out_rows: list[dict[str, Any]] = []
        for r in rows:
            if isinstance(r, dict):
                out_rows.append({str(k): (v.decode("utf-8", "replace") if isinstance(v, bytes) else v) for k, v in r.items()})
            else:
                out_rows.append({c: (v.decode("utf-8", "replace") if isinstance(v, bytes) else v) for c, v in zip(columns, r)})
        return columns, out_rows, truncated, int((time.time() - t0) * 1000)
    finally:
        try:
            conn.rollback()
        except Exception:
            discard = True
        _release(ds_id, conn, discard=discard)


def showplan_text(ds: dict[str, Any], sql: str, *, settings: Settings | None = None, timeout_ms: int = 15_000) -> list[dict[str, Any]]:
    """Legacy explain=True shape: one row per plan line under the key "QUERY PLAN"."""
    settings = settings or get_settings()
    ds_id, conn = _acquire(ds, settings=settings, timeout_ms=timeout_ms)
    discard = False
    try:
        cur = conn.cursor()
        cur.execute("SET SHOWPLAN_ALL ON")
        cur.execute(sql)
        rows = list(cur.fetchall() or [])
        cur.execute("SET SHOWPLAN_ALL OFF")
        out = []
        for r in rows:
            txt = r.get("StmtText") if isinstance(r, dict) else (r[0] if r else "")
            est = r.get("EstimateRows") if isinstance(r, dict) else None
            out.append({"QUERY PLAN": f"{txt}" + (f"  (rows={int(est)})" if est else "")})
        return out
    except Exception as e:  # noqa: BLE001
        discard = True
        raise _map_error(e) from e
    finally:
        try:
            conn.rollback()
        except Exception:
            discard = True
        _release(ds_id, conn, discard=discard)
