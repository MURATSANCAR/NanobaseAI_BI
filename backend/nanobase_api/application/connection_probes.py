"""Dialect connection probes — reuse Query Gateway pools/clients, not full executors."""

from __future__ import annotations

from typing import Any, Callable

import psycopg2

from nanobase_api.errors import ApiError
from query_gateway.domain.errors import GatewayError


def row_to_probe_ds(row: dict[str, Any], password: str, *, connection_url: str = "") -> dict[str, Any]:
    """Map bi_sources row (+ resolved password) to a QG-style datasource dict."""
    driver = str(row.get("driver") or row.get("dialect") or "postgresql").lower()
    ds: dict[str, Any] = {
        "id": str(row.get("id") or ""),
        "driver": driver,
        "dialect": str(row.get("dialect") or driver),
        "host": str(row.get("host") or ""),
        "port": int(row.get("port") or _default_port(driver)),
        "database": str(row.get("database") or ""),
        "username": str(row.get("username") or ""),
        "user": str(row.get("username") or ""),
        "password": password,
        "ssl": bool(row.get("ssl")),
        "sslmode": "require" if row.get("ssl") else "prefer",
        "ssl_mode": "REQUIRE" if row.get("ssl") else "DISABLE",
        "label": str(row.get("label") or row.get("id") or ""),
    }
    if driver in ("oracle",):
        ds["service_name"] = str(row.get("database") or "")
        if connection_url.strip():
            ds["dsn"] = connection_url.strip()
    if driver in ("odata", "cds", "cds_odata", "sap_s4hana_odata"):
        base = connection_url.strip() or str(row.get("host") or "").rstrip("/")
        ds["base_url"] = base
        ds["host"] = base
        ds["verify_tls"] = bool(row.get("ssl", True))
    if driver in ("hana", "sap_hana", "hdb"):
        ds["encrypt"] = bool(row.get("ssl", True))
        ds["validate_certificate"] = bool(row.get("ssl", True))
    return ds


def _default_port(driver: str) -> int:
    if driver == "oracle":
        return 1521
    if driver in ("hana", "sap_hana", "hdb"):
        return 30015
    if driver in ("odata", "cds", "cds_odata"):
        return 443
    return 5432


def map_probe_error(exc: BaseException, *, driver: str) -> ApiError:
    """User-facing Turkish errors; never leak secrets."""
    msg = str(exc) or type(exc).__name__
    low = msg.lower()
    if isinstance(exc, GatewayError):
        code = getattr(exc, "code", "") or ""
        detail = getattr(exc, "message", None) or msg
        if "oracledb yok" in detail.lower() or code.endswith("DRIVER") or "hdbcli" in detail.lower():
            return ApiError(
                "DATASOURCE_CONNECTION_FAILED",
                f"Bağlantı sürücüsü eksik ({driver}). Sunucu yöneticisine başvurun.",
                status_code=503,
            )
        if "authentication" in detail.lower() or "yasak oracle" in detail.lower() or "401" in detail:
            return ApiError(
                "DATASOURCE_CONNECTION_FAILED",
                "Veritabanı kimlik bilgileri doğrulanamadı.",
                status_code=400,
            )
        if "zorunlu" in detail.lower() or "invalid" in detail.lower() or "SERVICE_NAME" in detail:
            return ApiError("DATASOURCE_CONNECTION_FAILED", detail[:200], status_code=400)
        if "unreachable" in detail.lower() or "unavailable" in detail.lower() or "503" in str(
            getattr(exc, "status", "")
        ):
            return ApiError(
                "DATASOURCE_CONNECTION_FAILED",
                "Veritabanına erişilemedi (ağ veya servis kullanılamıyor).",
                status_code=400,
            )
        return ApiError("DATASOURCE_CONNECTION_FAILED", detail[:200], status_code=400)

    if "password" in low or "auth" in low or "ora-01017" in low or "28p01" in low or "401" in low:
        return ApiError(
            "DATASOURCE_CONNECTION_FAILED",
            "Veritabanı kimlik bilgileri doğrulanamadı.",
            status_code=400,
        )
    if "timeout" in low or "timed out" in low:
        return ApiError(
            "DATASOURCE_CONNECTION_FAILED",
            "Bağlantı zaman aşımına uğradı.",
            status_code=400,
        )
    if "oracledb" in low or "hdbcli" in low or "no module named" in low:
        return ApiError(
            "DATASOURCE_CONNECTION_FAILED",
            f"Bağlantı sürücüsü eksik ({driver}). Sunucu yöneticisine başvurun.",
            status_code=503,
        )
    return ApiError(
        "DATASOURCE_CONNECTION_FAILED",
        "Veritabanı bağlantı testi başarısız.",
        status_code=400,
    )


def probe_postgres(ds: dict[str, Any]) -> dict[str, Any]:
    conn = psycopg2.connect(
        host=ds["host"],
        port=int(ds["port"]),
        dbname=ds.get("database") or "",
        user=ds.get("user") or ds.get("username") or "",
        password=ds.get("password") or "",
        connect_timeout=5,
        sslmode=ds.get("sslmode") or ("require" if ds.get("ssl") else "prefer"),
    )
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1, version()")
        ver = cur.fetchone()[1]
        cur.close()
    finally:
        conn.close()
    return {
        "databaseType": "POSTGRESQL",
        "databaseVersion": str(ver)[:120],
    }


def probe_oracle(ds: dict[str, Any]) -> dict[str, Any]:
    from query_gateway.infrastructure.oracle.pool import get_oracle_pool_registry

    registry = get_oracle_pool_registry()
    ds_id, conn, _profile = registry.acquire(ds)
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM DUAL")
        cur.fetchone()
        ver = ""
        try:
            cur.execute("SELECT BANNER FROM v$version WHERE ROWNUM = 1")
            row = cur.fetchone()
            if row:
                ver = str(row[0])[:120]
        except Exception:
            ver = "Oracle"
        cur.close()
    finally:
        registry.release(ds_id, conn)
    return {"databaseType": "ORACLE", "databaseVersion": ver or "Oracle"}


def probe_hana(ds: dict[str, Any]) -> dict[str, Any]:
    from query_gateway.infrastructure.sap.contracts.datasource import HanaDatasourceConfig
    from query_gateway.infrastructure.sap.hana import pool as hana_pool

    cfg = HanaDatasourceConfig.from_datasource(ds)
    conn = hana_pool.acquire(cfg, timeout_ms=15_000)
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM DUMMY")
        cur.fetchone()
        ver = "SAP HANA"
        try:
            cur.execute("SELECT VERSION FROM SYS.M_DATABASE")
            row = cur.fetchone()
            if row:
                ver = str(row[0])[:120]
        except Exception:
            pass
        cur.close()
    finally:
        hana_pool.release(cfg, conn)
    return {"databaseType": "SAP_HANA", "databaseVersion": ver}


def probe_odata(ds: dict[str, Any]) -> dict[str, Any]:
    from query_gateway.infrastructure.sap.contracts.datasource import ODataDatasourceConfig
    from query_gateway.infrastructure.sap.odata.client import fetch_metadata

    cfg = ODataDatasourceConfig.from_datasource(ds)
    if not cfg.base_url:
        raise ApiError(
            "DATASOURCE_CONNECTION_FAILED",
            "OData base URL zorunludur.",
            status_code=400,
        )
    meta = fetch_metadata(cfg, timeout_s=15.0)
    version = "OData"
    if "Version=" in meta[:500]:
        version = "OData (metadata OK)"
    elif meta:
        version = f"OData ({len(meta)} bytes metadata)"
    return {"databaseType": "SAP_S4HANA_ODATA", "databaseVersion": version}


_PROBES: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "postgresql": probe_postgres,
    "postgres": probe_postgres,
    "oracle": probe_oracle,
    "hana": probe_hana,
    "sap_hana": probe_hana,
    "hdb": probe_hana,
    "odata": probe_odata,
    "cds": probe_odata,
    "cds_odata": probe_odata,
    "sap_s4hana_odata": probe_odata,
}


def run_probe(ds: dict[str, Any]) -> dict[str, Any]:
    driver = str(ds.get("driver") or ds.get("dialect") or "").lower()
    fn = _PROBES.get(driver)
    if not fn:
        raise ApiError(
            "DATASOURCE_CONNECTION_FAILED",
            f"Connection test bu sürücü için desteklenmiyor: {driver or '?'}.",
            status_code=400,
        )
    try:
        return fn(ds)
    except ApiError:
        raise
    except Exception as e:
        raise map_probe_error(e, driver=driver) from e


def load_gateway_datasource(datasource_id: str) -> dict[str, Any] | None:
    """Return QG registry entry (password already resolved) or None."""
    try:
        from query_gateway.infrastructure.database.datasources import load_datasources

        reg = load_datasources()
        return reg.get(datasource_id)
    except Exception:
        return None
