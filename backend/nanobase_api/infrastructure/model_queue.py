"""Production LLM concurrency queue with tenant fairness and backpressure.

Limits (env):
  MODEL_MAX_CONCURRENCY   — simultaneous planner/explain LLM calls (default 2)
  MODEL_QUEUE_LIMIT       — max waiting requests globally (default 100)
  GLOBAL_QUEUE_LIMIT      — alias for MODEL_QUEUE_LIMIT
  TENANT_QUEUE_LIMIT      — max waiting+active per tenant (default 20)
  MODEL_QUEUE_TIMEOUT     — max seconds waiting in queue (default 120)
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


class ModelQueueFullError(Exception):
    """Queue rejected the request (limit exceeded)."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class ModelQueueTimeoutError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass
class _Waiter:
    id: str
    tenant_id: str
    user_id: str | None
    enqueued_at: float
    event: asyncio.Event = field(default_factory=asyncio.Event)
    acquired: bool = False
    cancelled: bool = False


class ModelQueue:
    def __init__(
        self,
        *,
        max_concurrency: int | None = None,
        queue_limit: int | None = None,
        tenant_limit: int | None = None,
        queue_timeout_s: float | None = None,
    ) -> None:
        self.max_concurrency = max(
            1,
            int(
                max_concurrency
                if max_concurrency is not None
                else os.environ.get("MODEL_MAX_CONCURRENCY", "2")
            ),
        )
        self.queue_limit = max(
            1,
            int(
                queue_limit
                if queue_limit is not None
                else os.environ.get(
                    "GLOBAL_QUEUE_LIMIT",
                    os.environ.get("MODEL_QUEUE_LIMIT", "100"),
                )
            ),
        )
        self.tenant_limit = max(
            1,
            int(
                tenant_limit
                if tenant_limit is not None
                else os.environ.get("TENANT_QUEUE_LIMIT", "20")
            ),
        )
        self.queue_timeout_s = float(
            queue_timeout_s
            if queue_timeout_s is not None
            else os.environ.get("MODEL_QUEUE_TIMEOUT", "120")
        )
        self._lock = asyncio.Lock()
        self._active = 0
        self._waiters: list[_Waiter] = []
        self._tenant_active: dict[str, int] = {}
        self._tenant_waiting: dict[str, int] = {}

    def stats(self) -> dict[str, Any]:
        return {
            "active": self._active,
            "waiting": len(self._waiters),
            "maxConcurrency": self.max_concurrency,
            "queueLimit": self.queue_limit,
            "tenantLimit": self.tenant_limit,
            "queueTimeoutSec": self.queue_timeout_s,
        }

    def _tenant_load(self, tenant_id: str) -> int:
        return self._tenant_active.get(tenant_id, 0) + self._tenant_waiting.get(tenant_id, 0)

    def position_of(self, waiter: _Waiter) -> int:
        try:
            return self._waiters.index(waiter) + 1
        except ValueError:
            return 0

    async def acquire(
        self,
        *,
        tenant_id: str,
        user_id: str | None = None,
        request_id: str | None = None,
    ) -> "_Slot":
        async for kind, payload in self.acquire_with_progress(
            tenant_id=tenant_id, user_id=user_id, request_id=request_id
        ):
            if kind == "acquired":
                return payload  # type: ignore[return-value]
        raise RuntimeError("model queue acquire failed")

    async def acquire_with_progress(
        self,
        *,
        tenant_id: str,
        user_id: str | None = None,
        request_id: str | None = None,
        lang: str = "tr",
    ):
        """Yield ('waiting', status_dict) while queued, then ('acquired', Slot)."""
        waiter = _Waiter(
            id=request_id or str(uuid.uuid4()),
            tenant_id=tenant_id or "default",
            user_id=user_id,
            enqueued_at=time.monotonic(),
        )
        async with self._lock:
            if self._tenant_load(waiter.tenant_id) >= self.tenant_limit:
                raise ModelQueueFullError(
                    "TENANT_QUEUE_FULL",
                    "Şirket hesabınızda şu anda çok fazla eşzamanlı soru var. "
                    "Lütfen sıradaki cevaplar gelsin, sonra tekrar deneyin.",
                )
            if self._active < self.max_concurrency and not self._waiters:
                self._active += 1
                self._tenant_active[waiter.tenant_id] = self._tenant_active.get(waiter.tenant_id, 0) + 1
                waiter.acquired = True
                yield (
                    "acquired",
                    _Slot(self, waiter),
                )
                return

            if len(self._waiters) >= self.queue_limit:
                raise ModelQueueFullError(
                    "MODEL_QUEUE_FULL",
                    "Şu anda çok fazla soru bekliyor. Lütfen kısa süre sonra tekrar deneyin.",
                )

            self._waiters.append(waiter)
            self._tenant_waiting[waiter.tenant_id] = self._tenant_waiting.get(waiter.tenant_id, 0) + 1
            pos = self.position_of(waiter)
            depth = len(self._waiters) + self._active

        yield (
            "waiting",
            {
                "phase": "queued",
                "position": pos,
                "queue_depth": depth,
                "message": wait_message(lang=lang),
                "elapsed_sec": 0,
            },
        )

        deadline = time.monotonic() + self.queue_timeout_s
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    await self._cancel_waiter(waiter)
                    raise ModelQueueTimeoutError(
                        "Bekleme süresi doldu. Sistem yoğun; lütfen yeniden sorun."
                    )
                promoted = await self._try_promote(waiter)
                if promoted:
                    yield ("acquired", _Slot(self, waiter))
                    return
                async with self._lock:
                    pos = self.position_of(waiter)
                    depth = len(self._waiters) + self._active
                elapsed = int(time.monotonic() - waiter.enqueued_at)
                yield (
                    "waiting",
                    {
                        "phase": "queued",
                        "position": pos,
                        "queue_depth": depth,
                        "message": wait_message(lang=lang),
                        "elapsed_sec": elapsed,
                    },
                )
                try:
                    await asyncio.wait_for(waiter.event.wait(), timeout=min(1.0, remaining))
                except asyncio.TimeoutError:
                    pass
                waiter.event.clear()
        except asyncio.CancelledError:
            await self._cancel_waiter(waiter)
            raise

    async def _cancel_waiter(self, waiter: _Waiter) -> None:
        async with self._lock:
            if waiter.acquired:
                return
            waiter.cancelled = True
            if waiter in self._waiters:
                self._waiters.remove(waiter)
                self._tenant_waiting[waiter.tenant_id] = max(
                    0, self._tenant_waiting.get(waiter.tenant_id, 1) - 1
                )
            self._wake_next_unlocked()

    async def _try_promote(self, waiter: _Waiter) -> bool:
        async with self._lock:
            if waiter.cancelled or waiter.acquired:
                return waiter.acquired
            if waiter not in self._waiters:
                return False
            if self._active >= self.max_concurrency:
                return False
            # Fairness: only promote if first in line (FIFO)
            if self._waiters[0] is not waiter:
                return False
            self._waiters.pop(0)
            self._tenant_waiting[waiter.tenant_id] = max(
                0, self._tenant_waiting.get(waiter.tenant_id, 1) - 1
            )
            self._active += 1
            self._tenant_active[waiter.tenant_id] = self._tenant_active.get(waiter.tenant_id, 0) + 1
            waiter.acquired = True
            return True

    def _wake_next_unlocked(self) -> None:
        if self._waiters and self._active < self.max_concurrency:
            self._waiters[0].event.set()

    async def release(self, waiter: _Waiter) -> None:
        async with self._lock:
            if not waiter.acquired:
                if waiter in self._waiters:
                    self._waiters.remove(waiter)
                    self._tenant_waiting[waiter.tenant_id] = max(
                        0, self._tenant_waiting.get(waiter.tenant_id, 1) - 1
                    )
                return
            waiter.acquired = False
            self._active = max(0, self._active - 1)
            self._tenant_active[waiter.tenant_id] = max(
                0, self._tenant_active.get(waiter.tenant_id, 1) - 1
            )
            self._wake_next_unlocked()

    async def snapshot_for(self, waiter: _Waiter | None) -> dict[str, Any]:
        async with self._lock:
            pos = self.position_of(waiter) if waiter and not waiter.acquired else 0
            return {
                "position": pos,
                "queue_depth": len(self._waiters) + self._active,
                "waiting": len(self._waiters),
                "active": self._active,
                "max_concurrency": self.max_concurrency,
            }


class _Slot:
    def __init__(self, queue: ModelQueue, waiter: _Waiter) -> None:
        self._queue = queue
        self._waiter = waiter
        self._released = False

    @property
    def waiter(self) -> _Waiter:
        return self._waiter

    async def snapshot(self) -> dict[str, Any]:
        return await self._queue.snapshot_for(self._waiter if not self._waiter.acquired else None)

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        await self._queue.release(self._waiter)

    async def __aenter__(self) -> "_Slot":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.release()


_QUEUE: ModelQueue | None = None


def get_model_queue() -> ModelQueue:
    global _QUEUE
    if _QUEUE is None:
        _QUEUE = ModelQueue()
    return _QUEUE


def reset_model_queue_for_tests() -> ModelQueue:
    """Test helper — replace singleton."""
    global _QUEUE
    _QUEUE = ModelQueue()
    return _QUEUE


USER_WAIT_MESSAGE_TR = (
    "Şu anda başka bir işlem yapıyorum; size en kısa zamanda cevap vereceğim."
)
USER_WAIT_MESSAGE_EN = (
    "I'm currently handling another request; I'll answer you as soon as possible."
)


def wait_message(*, lang: str = "tr") -> str:
    return USER_WAIT_MESSAGE_EN if (lang or "").lower().startswith("en") else USER_WAIT_MESSAGE_TR
