"""Fair access to the shared language model.

One GPU-backed model serves every user of the deployment. Without ordering, two people asking at the same
moment collide: the second request either waits inside the model server's socket or fails outright. This
queue makes the wait explicit, ordered and visible:

* every request that needs the model takes a numbered ticket, ordered by the time it arrived;
* at most `slots` tickets run at once (one, unless the model server has more capacity);
* everyone else waits — nobody is rejected, and the caller can be told the position in line;
* a worker that dies does not block the queue: its ticket goes stale and is reclaimed.

The ticket table lives in the shared catalog database, so ordering holds across uvicorn workers and across
processes (the bridge and the nightly worker compete fairly for the same model).

Answers that come from the certified catalog never take a ticket — the queue only ever holds the questions
that genuinely need a model.
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Optional

import sqlalchemy as sa

from semantic_layer.models import new_id
from semantic_layer.store import schema as S

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: Any) -> Optional[datetime]:
    """SQLite hands back naive datetimes; treat stored timestamps as UTC so arithmetic is safe."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return None


@dataclass
class Ticket:
    id: str
    position: int          # 0 while running, 1 = next in line
    waited_ms: int
    ahead: int


class LlmQueue:
    """Time-ordered admission control for the model. Backed by the catalog database; degrades to a
    process-local lock when no database is available (tests, offline tooling)."""

    def __init__(
        self,
        engine: Optional[sa.Engine] = None,
        *,
        slots: int = 1,
        lease_seconds: int = 900,
        max_wait_seconds: int = 1800,
        poll_seconds: float = 0.25,
        worker: Optional[str] = None,
    ):
        self.engine = engine
        self.slots = max(1, slots)
        self.lease_seconds = lease_seconds
        self.max_wait_seconds = max_wait_seconds
        self.poll_seconds = poll_seconds
        self._base_poll = poll_seconds
        self.worker = worker or f"{socket.gethostname()}:{os.getpid()}"
        self._local = threading.Semaphore(self.slots)

    @classmethod
    def from_env(cls, engine: Optional[sa.Engine] = None) -> "LlmQueue":
        return cls(
            engine,
            slots=int(os.environ.get("SEMANTIC_LLM_SLOTS", "1")),
            lease_seconds=int(os.environ.get("SEMANTIC_LLM_LEASE_SEC", "900")),
            max_wait_seconds=int(os.environ.get("SEMANTIC_LLM_MAX_WAIT_SEC", "1800")),
        )

    # ------------------------------------------------------------------ public
    @contextmanager
    def lease(self, *, purpose: str, tenant_id: str = "default", datasource_id: str = "default", user_id: Optional[str] = None, question: Optional[str] = None, on_wait: Optional[Any] = None) -> Iterator[Ticket]:
        """Block until it is this caller's turn, then run. Always releases, including on error."""
        if self.engine is None:
            acquired_at = time.perf_counter()
            self._local.acquire()
            try:
                yield Ticket(id="local", position=0, waited_ms=int((time.perf_counter() - acquired_at) * 1000), ahead=0)
            finally:
                self._local.release()
            return
        ticket_id = self._enqueue(purpose, tenant_id, datasource_id, user_id, question)
        self.poll_seconds = self._base_poll
        started = time.perf_counter()
        try:
            ahead = self._wait_for_turn(ticket_id, on_wait)
            yield Ticket(id=ticket_id, position=0, waited_ms=int((time.perf_counter() - started) * 1000), ahead=ahead)
        finally:
            self._finish(ticket_id)

    def status(self, limit: int = 20) -> dict[str, Any]:
        """What the queue looks like right now — for the operator and for the waiting user."""
        if self.engine is None:
            return {"backend": "process", "slots": self.slots, "running": self.slots - self._local._value, "waiting": 0, "queue": []}
        with self.engine.connect() as conn:
            self._reclaim(conn)
            rows = [dict(r._mapping) for r in conn.execute(
                sa.select(S.sl_llm_queue)
                .where(S.sl_llm_queue.c.status.in_(("WAITING", "RUNNING")))
                .order_by(S.sl_llm_queue.c.enqueued_at)
                .limit(limit)
            )]
        running = [r for r in rows if r["status"] == "RUNNING"]
        waiting = [r for r in rows if r["status"] == "WAITING"]
        return {
            "backend": "database",
            "slots": self.slots,
            "running": len(running),
            "waiting": len(waiting),
            "queue": [
                {
                    "position": 0 if r["status"] == "RUNNING" else i + 1,
                    "purpose": r["purpose"],
                    "user": r["user_id"],
                    "status": r["status"],
                    "enqueuedAt": _aware(r["enqueued_at"]).isoformat() if r["enqueued_at"] else None,
                    "waitingMs": int((_now() - _aware(r["enqueued_at"])).total_seconds() * 1000) if r["enqueued_at"] and r["status"] == "WAITING" else 0,
                }
                for i, r in enumerate(waiting)
            ] + [
                {"position": 0, "purpose": r["purpose"], "user": r["user_id"], "status": "RUNNING", "startedAt": _aware(r["started_at"]).isoformat() if r["started_at"] else None}
                for r in running
            ],
        }

    # ------------------------------------------------------------------ internals
    def _enqueue(self, purpose: str, tenant_id: str, datasource_id: str, user_id: Optional[str], question: Optional[str]) -> str:
        ticket_id = new_id("llmq")
        with self.engine.begin() as conn:
            conn.execute(S.sl_llm_queue.insert().values(
                id=ticket_id, tenant_id=tenant_id, datasource_id=datasource_id, user_id=user_id,
                purpose=purpose, question=(question or "")[:500], status="WAITING",
                enqueued_at=_now(), heartbeat_at=_now(), worker=self.worker,
            ))
        return ticket_id

    def _reclaim(self, conn: sa.Connection, *, exclude_id: Optional[str] = None) -> None:
        """A ticket whose worker stopped reporting is abandoned, so one crash cannot stop the line.
        The caller's own ticket is never reclaimed — it is being held by a thread that is right here."""
        running_cutoff = _now() - timedelta(seconds=max(1, self.lease_seconds))
        waiting_cutoff = _now() - timedelta(seconds=max(60, self.lease_seconds))
        stale = sa.or_(
            sa.and_(S.sl_llm_queue.c.status == "RUNNING", sa.or_(S.sl_llm_queue.c.heartbeat_at.is_(None), S.sl_llm_queue.c.heartbeat_at < running_cutoff)),
            sa.and_(S.sl_llm_queue.c.status == "WAITING", sa.or_(S.sl_llm_queue.c.heartbeat_at.is_(None), S.sl_llm_queue.c.heartbeat_at < waiting_cutoff)),
        )
        stmt = S.sl_llm_queue.update().where(stale).values(status="ABANDONED", finished_at=_now())
        if exclude_id:
            stmt = stmt.where(S.sl_llm_queue.c.id != exclude_id)
        conn.execute(stmt)

    def _wait_for_turn(self, ticket_id: str, on_wait: Optional[Any]) -> int:
        deadline = time.monotonic() + self.max_wait_seconds
        announced = False
        ahead_at_start = 0
        while True:
            with self.engine.begin() as conn:
                self._reclaim(conn, exclude_id=ticket_id)
                running = conn.execute(
                    sa.select(sa.func.count()).select_from(S.sl_llm_queue).where(S.sl_llm_queue.c.status == "RUNNING")
                ).scalar() or 0
                waiting = [dict(r._mapping) for r in conn.execute(
                    sa.select(S.sl_llm_queue.c.id, S.sl_llm_queue.c.enqueued_at)
                    .where(S.sl_llm_queue.c.status == "WAITING")
                    .order_by(S.sl_llm_queue.c.enqueued_at, S.sl_llm_queue.c.id)
                )]
                order = [r["id"] for r in waiting]
                if ticket_id not in order:              # someone marked it done: take the turn rather than stall
                    conn.execute(S.sl_llm_queue.update().where(S.sl_llm_queue.c.id == ticket_id).values(status="RUNNING", started_at=_now(), heartbeat_at=_now(), worker=self.worker))
                    return ahead_at_start
                ahead = order.index(ticket_id)
                if not announced:
                    ahead_at_start = ahead
                    announced = True
                if running < self.slots and ahead < (self.slots - running):
                    conn.execute(S.sl_llm_queue.update().where(S.sl_llm_queue.c.id == ticket_id).values(status="RUNNING", started_at=_now(), heartbeat_at=_now(), worker=self.worker))
                    return ahead_at_start
                conn.execute(S.sl_llm_queue.update().where(S.sl_llm_queue.c.id == ticket_id).values(heartbeat_at=_now()))
            if on_wait is not None:
                try:
                    on_wait(ahead)
                except Exception:  # noqa: BLE001
                    pass
            # Back off: a request that has been waiting for minutes does not need four checks a second
            # on the production database. Starts responsive, settles to a light poll.
            self.poll_seconds = min(self.poll_seconds * 1.5, 5.0)
            if time.monotonic() > deadline:
                # Never fail the user's question on queueing alone: take the slot and let the model decide.
                log.warning("llm queue wait exceeded %ss for %s — proceeding", self.max_wait_seconds, ticket_id)
                with self.engine.begin() as conn:
                    conn.execute(S.sl_llm_queue.update().where(S.sl_llm_queue.c.id == ticket_id).values(status="RUNNING", started_at=_now(), heartbeat_at=_now(), worker=self.worker))
                return ahead_at_start
            time.sleep(self.poll_seconds)

    def _finish(self, ticket_id: str) -> None:
        try:
            with self.engine.begin() as conn:
                conn.execute(S.sl_llm_queue.update().where(S.sl_llm_queue.c.id == ticket_id).values(status="DONE", finished_at=_now()))
        except Exception as e:  # noqa: BLE001
            log.warning("llm queue release failed for %s: %s", ticket_id, e)


class QueuedLlm:
    """Wraps any LLM client so every call goes through the queue. The wrapped client is unaware."""

    def __init__(self, llm: Any, queue: LlmQueue, *, purpose: str = "nl2sql", tenant_id: str = "default", datasource_id: str = "default"):
        self.llm = llm
        self.queue = queue
        self.purpose = purpose
        self.tenant_id = tenant_id
        self.datasource_id = datasource_id
        self.model = getattr(llm, "model", "")
        self.last_wait_ms = 0
        self.last_ahead = 0

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        with self.queue.lease(purpose=self.purpose, tenant_id=self.tenant_id, datasource_id=self.datasource_id,
                              user_id=kwargs.pop("user_id", None), question=_first_user_message(messages)) as ticket:
            self.last_wait_ms, self.last_ahead = ticket.waited_ms, ticket.ahead
            return self.llm.chat(messages, **kwargs)


def _first_user_message(messages: list[dict[str, str]]) -> str:
    for m in reversed(messages or []):
        if m.get("role") == "user":
            return str(m.get("content") or "")[:500]
    return ""
