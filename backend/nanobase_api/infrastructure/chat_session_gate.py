"""Per-session chat FIFO gate for production.

Ensures one chat/stream pipeline per (tenant, session) at a time.
The next message waits (SSE session_queued) until the previous finishes with
done/error or the client disconnects and releases the lock.

Stale owners (hung streams / lost disconnect) are reclaimed after
``stale_owner_s`` so Hazır / fast-path questions are never blocked forever.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


@dataclass
class _SessionWaiter:
    id: str
    event: asyncio.Event = field(default_factory=asyncio.Event)
    cancelled: bool = False
    enqueued_at: float = field(default_factory=time.monotonic)


@dataclass
class _SessionState:
    owner: str | None = None
    owner_since: float | None = None
    waiters: list[_SessionWaiter] = field(default_factory=list)


class ChatSessionGate:
    """Strict FIFO: acquire → work → release wakes the next waiter."""

    def __init__(self, *, stale_owner_s: float = 120.0) -> None:
        self._lock = asyncio.Lock()
        self._sessions: dict[str, _SessionState] = {}
        self._stale_owner_s = max(30.0, float(stale_owner_s))

    @staticmethod
    def _key(tenant_id: str, session_id: str) -> str:
        return f"{tenant_id or 'default'}::{session_id or 'anon'}"

    def stats(self) -> dict[str, Any]:
        busy = sum(1 for s in self._sessions.values() if s.owner)
        waiting = sum(len(s.waiters) for s in self._sessions.values())
        return {
            "busy_sessions": busy,
            "waiting": waiting,
            "tracked": len(self._sessions),
            "stale_owner_s": self._stale_owner_s,
        }

    def _reclaim_stale_unlocked(self, st: _SessionState) -> bool:
        """If owner held too long, drop it and promote next waiter. Returns True if reclaimed."""
        if not st.owner or st.owner_since is None:
            return False
        age = time.monotonic() - st.owner_since
        if age < self._stale_owner_s:
            return False
        st.owner = None
        st.owner_since = None
        while st.waiters:
            nxt = st.waiters.pop(0)
            if nxt.cancelled:
                continue
            st.owner = nxt.id
            st.owner_since = time.monotonic()
            nxt.event.set()
            break
        return True

    async def acquire(
        self,
        *,
        tenant_id: str,
        session_id: str,
        request_id: str | None = None,
        timeout_s: float = 1800.0,
    ) -> AsyncIterator[tuple[str, dict[str, Any] | None]]:
        """Yield ('waiting', payload)* then ('acquired', None). Caller must release."""
        key = self._key(tenant_id, session_id)
        waiter = _SessionWaiter(id=request_id or str(uuid.uuid4()))

        async with self._lock:
            st = self._sessions.setdefault(key, _SessionState())
            self._reclaim_stale_unlocked(st)
            if st.owner is None and not st.waiters:
                st.owner = waiter.id
                st.owner_since = time.monotonic()
                immediate = True
                pos = 0
            else:
                st.waiters.append(waiter)
                immediate = False
                pos = len(st.waiters)

        if immediate:
            yield ("acquired", None)
            return

        yield (
            "waiting",
            {
                "phase": "session_queued",
                "position": pos,
                "message": (
                    "Önceki sorunuzun cevabı tamamlanıyor; "
                    "bu mesaj sıraya alındı ve sonuç geldikten sonra işlenecek."
                ),
                "elapsed_sec": 0,
            },
        )

        deadline = time.monotonic() + max(30.0, timeout_s)
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    await self._cancel(key, waiter)
                    raise TimeoutError(
                        "Önceki soru çok uzun sürdü; lütfen mevcut cevap gelsin veya durdurun, "
                        "sonra tekrar deneyin."
                    )
                try:
                    await asyncio.wait_for(waiter.event.wait(), timeout=min(2.0, remaining))
                except asyncio.TimeoutError:
                    async with self._lock:
                        st = self._sessions.get(key)
                        if st:
                            # Promote if the holder vanished / hung past stale window.
                            if self._reclaim_stale_unlocked(st) and st.owner == waiter.id:
                                yield ("acquired", None)
                                return
                        pos = (st.waiters.index(waiter) + 1) if st and waiter in st.waiters else 0
                    yield (
                        "waiting",
                        {
                            "phase": "session_queued",
                            "position": pos,
                            "message": (
                                "Önceki sorunuzun cevabı tamamlanıyor; "
                                "bu mesaj sırada bekliyor."
                            ),
                            "elapsed_sec": int(time.monotonic() - waiter.enqueued_at),
                        },
                    )
                    continue
                if waiter.cancelled:
                    raise asyncio.CancelledError()
                async with self._lock:
                    st = self._sessions.get(key)
                    owned = bool(st and st.owner == waiter.id)
                if owned:
                    yield ("acquired", None)
                    return
                waiter.event.clear()
        except asyncio.CancelledError:
            await self._cancel(key, waiter)
            raise

    async def release(self, *, tenant_id: str, session_id: str, request_id: str | None = None) -> None:
        key = self._key(tenant_id, session_id)
        async with self._lock:
            st = self._sessions.get(key)
            if not st:
                return
            if request_id and st.owner and st.owner != request_id:
                return
            st.owner = None
            st.owner_since = None
            while st.waiters:
                nxt = st.waiters.pop(0)
                if nxt.cancelled:
                    continue
                st.owner = nxt.id
                st.owner_since = time.monotonic()
                nxt.event.set()
                break
            if st.owner is None and not st.waiters:
                self._sessions.pop(key, None)

    async def force_release(self, *, tenant_id: str, session_id: str) -> bool:
        """Admin/debug: drop owner and wake next waiter."""
        key = self._key(tenant_id, session_id)
        async with self._lock:
            st = self._sessions.get(key)
            if not st:
                return False
            st.owner = None
            st.owner_since = None
            while st.waiters:
                nxt = st.waiters.pop(0)
                if nxt.cancelled:
                    continue
                st.owner = nxt.id
                st.owner_since = time.monotonic()
                nxt.event.set()
                break
            if st.owner is None and not st.waiters:
                self._sessions.pop(key, None)
            return True

    async def _cancel(self, key: str, waiter: _SessionWaiter) -> None:
        async with self._lock:
            waiter.cancelled = True
            st = self._sessions.get(key)
            if not st:
                return
            if waiter in st.waiters:
                st.waiters.remove(waiter)
            if st.owner == waiter.id:
                st.owner = None
                st.owner_since = None
                while st.waiters:
                    nxt = st.waiters.pop(0)
                    if nxt.cancelled:
                        continue
                    st.owner = nxt.id
                    st.owner_since = time.monotonic()
                    nxt.event.set()
                    break
            if st.owner is None and not st.waiters:
                self._sessions.pop(key, None)


_GATE: ChatSessionGate | None = None


def get_chat_session_gate() -> ChatSessionGate:
    global _GATE
    if _GATE is None:
        import os

        stale = float(os.environ.get("CHAT_SESSION_STALE_OWNER_S") or "120")
        _GATE = ChatSessionGate(stale_owner_s=stale)
    return _GATE


def reset_chat_session_gate_for_tests() -> ChatSessionGate:
    global _GATE
    _GATE = ChatSessionGate(stale_owner_s=120.0)
    return _GATE
