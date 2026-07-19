"""Per-datasource connection pool registry (psycopg2 ThreadedConnectionPool)."""

from __future__ import annotations

import threading
import time
from typing import Any

from query_gateway.config.settings import Settings, get_settings
from query_gateway.domain.errors import DATABASE_UNAVAILABLE, GatewayError


class PoolHandle:
    def __init__(self, pool: Any, created_at: float) -> None:
        self.pool = pool
        self.created_at = created_at
        self.last_used = created_at


class PoolRegistry:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._pools: dict[str, PoolHandle] = {}
        self._lock = threading.Lock()

    def get_postgres_conn(self, ds: dict[str, Any]):
        try:
            from psycopg2 import pool as pg_pool
        except ImportError as e:
            raise GatewayError(DATABASE_UNAVAILABLE, "psycopg2 yok.", status=503) from e

        ds_id = str(ds["id"])
        with self._lock:
            handle = self._pools.get(ds_id)
            if handle is None:
                try:
                    p = pg_pool.ThreadedConnectionPool(
                        minconn=1,
                        maxconn=self.settings.pool_size + self.settings.pool_max_overflow,
                        host=ds["host"],
                        port=ds["port"],
                        dbname=ds["database"],
                        user=ds["user"],
                        password=ds["password"],
                        sslmode=ds.get("sslmode") or "prefer",
                        connect_timeout=10,
                    )
                except Exception as e:
                    raise GatewayError(
                        DATABASE_UNAVAILABLE,
                        "Veritabanı bağlantı havuzu açılamadı.",
                        status=503,
                        retryable=True,
                    ) from e
                handle = PoolHandle(p, time.time())
                self._pools[ds_id] = handle
            handle.last_used = time.time()
            try:
                conn = handle.pool.getconn()
            except Exception as e:
                raise GatewayError(
                    DATABASE_UNAVAILABLE,
                    "Bağlantı alınamadı.",
                    status=503,
                    retryable=True,
                ) from e
            return ds_id, conn

    def put_postgres_conn(self, ds_id: str, conn: Any, *, close: bool = False) -> None:
        with self._lock:
            handle = self._pools.get(ds_id)
            if not handle:
                try:
                    conn.close()
                except Exception:
                    pass
                return
            try:
                if close:
                    handle.pool.putconn(conn, close=True)
                else:
                    # reset session state
                    try:
                        conn.rollback()
                        with conn.cursor() as cur:
                            cur.execute("RESET ALL")
                    except Exception:
                        try:
                            handle.pool.putconn(conn, close=True)
                            return
                        except Exception:
                            return
                    handle.pool.putconn(conn)
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass

    def invalidate(self, ds_id: str) -> None:
        with self._lock:
            handle = self._pools.pop(ds_id, None)
            if handle:
                try:
                    handle.pool.closeall()
                except Exception:
                    pass

    def active_pools(self) -> int:
        return len(self._pools)

    def close_all(self) -> None:
        with self._lock:
            for hid in list(self._pools.keys()):
                self.invalidate(hid)


_registry: PoolRegistry | None = None


def get_pool_registry() -> PoolRegistry:
    global _registry
    if _registry is None:
        _registry = PoolRegistry()
    return _registry
