"""Simple per-datasource HANA connection borrow helpers."""

from __future__ import annotations

import threading
from typing import Any

from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.sap.contracts.datasource import HanaDatasourceConfig

HANA_DRIVER_MISSING = "HANA_DRIVER_MISSING"
HANA_CONNECTION_FAILED = "HANA_CONNECTION_FAILED"

_lock = threading.Lock()
_pools: dict[str, list[Any]] = {}
_MAX_POOL = 5


def _connect(cfg: HanaDatasourceConfig, timeout_ms: int) -> Any:
    try:
        from hdbcli import dbapi
    except ImportError as e:
        raise GatewayError(
            HANA_DRIVER_MISSING,
            "hdbcli not installed — pip/uv install hdbcli",
            status=500,
        ) from e
    try:
        return dbapi.connect(
            address=cfg.host,
            port=int(cfg.port),
            user=cfg.user,
            password=cfg.password,
            databaseName=cfg.database_name or None,
            encrypt=bool(cfg.encrypt),
            sslValidateCertificate=bool(cfg.validate_certificate),
            communicationTimeout=int(timeout_ms),
            autocommit=False,
        )
    except Exception as e:
        raise GatewayError(
            HANA_CONNECTION_FAILED,
            "HANA connection failed.",
            status=503,
        ) from e


def acquire(cfg: HanaDatasourceConfig, *, timeout_ms: int = 15_000) -> Any:
    key = cfg.datasource_id
    with _lock:
        bucket = _pools.setdefault(key, [])
        if bucket:
            return bucket.pop()
    return _connect(cfg, timeout_ms)


def release(cfg: HanaDatasourceConfig, conn: Any, *, discard: bool = False) -> None:
    if conn is None:
        return
    if discard:
        try:
            conn.close()
        except Exception:
            pass
        return
    key = cfg.datasource_id
    with _lock:
        bucket = _pools.setdefault(key, [])
        if len(bucket) < _MAX_POOL:
            try:
                conn.rollback()
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
                return
            bucket.append(conn)
            return
    try:
        conn.close()
    except Exception:
        pass


def reset_pools() -> None:
    with _lock:
        for bucket in _pools.values():
            for c in bucket:
                try:
                    c.close()
                except Exception:
                    pass
        _pools.clear()
