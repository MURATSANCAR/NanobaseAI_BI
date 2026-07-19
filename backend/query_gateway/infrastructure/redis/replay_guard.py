"""Redis replay protection."""

from __future__ import annotations

from typing import Protocol

from query_gateway.config.settings import Settings
from query_gateway.domain.errors import REPLAY_REQUEST_DETECTED, GatewayError


class RedisLike(Protocol):
    def set(self, name: str, value: str, nx: bool = False, ex: int | None = None) -> bool | None: ...


class InMemoryReplayStore:
    def __init__(self) -> None:
        self._keys: dict[str, float] = {}

    def set(self, name: str, value: str, nx: bool = False, ex: int | None = None) -> bool | None:
        import time

        now = time.time()
        # expire
        expired = [k for k, t in self._keys.items() if t < now]
        for k in expired:
            del self._keys[k]
        if nx and name in self._keys:
            return False
        self._keys[name] = now + (ex or 120)
        return True


def check_and_store_replay(
    store: RedisLike | None,
    settings: Settings,
    request_id: str,
) -> None:
    if not request_id:
        raise GatewayError(REPLAY_REQUEST_DETECTED, "Request ID gerekli.", status=401)
    if store is None:
        if settings.replay_required:
            raise GatewayError(
                REPLAY_REQUEST_DETECTED,
                "Replay koruması kullanılamıyor.",
                status=503,
                retryable=True,
            )
        return
    key = f"replay:{request_id}"
    ok = store.set(key, "1", nx=True, ex=settings.replay_ttl_s)
    if ok is False:
        raise GatewayError(
            REPLAY_REQUEST_DETECTED,
            "Tekrarlayan istek tespit edildi.",
            status=409,
        )
