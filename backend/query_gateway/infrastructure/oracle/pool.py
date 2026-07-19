"""Oracle Thin Mode connection pool (sync; compatible with sync Gateway handlers).

Async pool (create_pool_async) is Thin-only and reserved for a future async
surface; the hardened path uses sync Thin pools so it matches Postgres execute.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from query_gateway.config.settings import Settings, get_settings
from query_gateway.domain.errors import DATABASE_UNAVAILABLE, GatewayError
from query_gateway.infrastructure.oracle.profile import OracleConnectionProfile, build_profile_from_datasource
from query_gateway.infrastructure.oracle.session import reset_session_after, reset_session_before


class OraclePoolHandle:
    def __init__(self, pool: Any, created_at: float, mode: str) -> None:
        self.pool = pool
        self.created_at = created_at
        self.last_used = created_at
        self.mode = mode


class OraclePoolRegistry:
    """Per-datasource Thin Mode sync pools. Thick Mode must use a separate process."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._pools: dict[str, OraclePoolHandle] = {}
        self._lock = threading.Lock()
        self._process_mode: str | None = None

    def _ensure_mode(self, mode: str) -> None:
        mode = mode.upper()
        if self._process_mode is None:
            self._process_mode = mode
            if mode == "THICK":
                try:
                    import oracledb

                    oracledb.init_oracle_client()
                except Exception as e:
                    raise GatewayError(
                        DATABASE_UNAVAILABLE,
                        "Oracle Thick Mode başlatılamadı.",
                        status=503,
                    ) from e
            return
        if self._process_mode != mode:
            raise GatewayError(
                DATABASE_UNAVAILABLE,
                "Thin ve Thick Mode aynı process içinde birlikte kullanılamaz.",
                status=503,
            )

    def acquire(self, ds: dict[str, Any]):
        try:
            import oracledb
        except ImportError as e:
            raise GatewayError(DATABASE_UNAVAILABLE, "oracledb yok.", status=503) from e

        profile = build_profile_from_datasource(ds)
        self._ensure_mode(profile.connection_mode)
        ds_id = str(ds["id"])

        with self._lock:
            handle = self._pools.get(ds_id)
            if handle is None:
                try:
                    pool = oracledb.create_pool(
                        user=profile.user,
                        password=profile.password,
                        dsn=profile.connect_dsn(),
                        min=self.settings.pool_size,
                        max=self.settings.pool_size,
                        increment=0,
                        getmode=oracledb.POOL_GETMODE_TIMEDWAIT,
                        wait_timeout=int(self.settings.pool_timeout_s * 1000),
                        timeout=self.settings.pool_idle_ttl_s,
                        max_lifetime_session=self.settings.pool_recycle_s,
                        ping_interval=60,
                    )
                except Exception as e:
                    raise GatewayError(
                        DATABASE_UNAVAILABLE,
                        "Oracle bağlantı havuzu açılamadı.",
                        status=503,
                        retryable=True,
                    ) from e
                handle = OraclePoolHandle(pool, time.time(), profile.connection_mode)
                self._pools[ds_id] = handle
            handle.last_used = time.time()
            try:
                conn = handle.pool.acquire()
            except Exception as e:
                raise GatewayError(
                    DATABASE_UNAVAILABLE,
                    "Oracle bağlantısı alınamadı.",
                    status=503,
                    retryable=True,
                ) from e
            try:
                conn.call_timeout = profile.call_timeout_ms
            except Exception:
                pass
            reset_session_before(conn)
            return ds_id, conn, profile

    def release(self, ds_id: str, conn: Any, *, discard: bool = False) -> None:
        with self._lock:
            handle = self._pools.get(ds_id)
            if not handle:
                try:
                    conn.close()
                except Exception:
                    pass
                return
            try:
                if discard:
                    handle.pool.drop(conn)
                else:
                    try:
                        reset_session_after(conn)
                    except Exception:
                        try:
                            handle.pool.drop(conn)
                            return
                        except Exception:
                            return
                    handle.pool.release(conn)
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
                    handle.pool.close()
                except Exception:
                    pass

    def close_all(self) -> None:
        with self._lock:
            for ds_id in list(self._pools.keys()):
                self.invalidate(ds_id)


_oracle_registry: OraclePoolRegistry | None = None


def get_oracle_pool_registry() -> OraclePoolRegistry:
    global _oracle_registry
    if _oracle_registry is None:
        _oracle_registry = OraclePoolRegistry()
    return _oracle_registry
