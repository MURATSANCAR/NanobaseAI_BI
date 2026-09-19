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

Many modules, one model (2026-09-17). A ticket carries the module that asked and a priority:

* 0 a person is watching (a question, a chat turn) · 1 somebody reads it soon (a scheduled report)
  · 2 nobody is watching (background reading). Purposes keep saying it the old way — "bg:<module>" is 2,
  "std:<module>" is 1, anything else is 0 — or the caller passes `module=`/`priority=` outright.
* the last `reserve` slots are kept for priority 0, so unattended work can fill the model but never
  the whole of it;
* within a priority the next slot goes to the module that holds the fewest, then to the earliest
  arrival: one module sending a hundred prompts does not make the other nine wait for all of them;
* a RUNNING ticket is kept alive by a heartbeat, not by a lease that has to guess how long a model
  call may take. Measured the week before: 26 tickets reclaimed while their call was still running
  (lease 900s, client timeout 3600s), each one silently admitting a call over the slot limit;
* what the provider says about load (429/503/504/529) is shared through `sl_llm_gate`: admissions
  pause for the cooldown and the slot count is halved, then raised one at a time as calls succeed.
  Nobody's question fails because of this — it waits, which is what it would have done inside a
  retry loop anyway, except now the other seven calls are not hammering the same full queue.
"""

from __future__ import annotations

import logging
import os
import random
import re
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


INTERACTIVE, NORMAL, BATCH = 0, 1, 2

#: background tickets sort after interactive ones, whatever time they arrived. Rows written by code
#: that predates the priority column are read the way they always were: by the "bg:" prefix.
PRIORITY = sa.func.coalesce(S.sl_llm_queue.c.priority, sa.case((S.sl_llm_queue.c.purpose.like("bg:%"), BATCH), else_=INTERACTIVE))
BACKGROUND_LAST = PRIORITY

#: provider answers that mean "too much at once", as opposed to "this request is wrong"
PRESSURE_STATUSES = frozenset({429, 503, 504, 529})

GATE_ID = "default"

_MODULE_RE = re.compile(r"[^a-z0-9_.-]+")


def classify(purpose: str) -> tuple[str, int]:
    """("vocabulary", 2) from "bg:vocabulary"; ("nl2sql", 0) from "nl2sql" or "nl2sql:selector"."""
    text = (purpose or "").strip().lower()
    priority = INTERACTIVE
    if text.startswith("bg:"):
        text, priority = text[3:], BATCH
    elif text.startswith("std:"):
        text, priority = text[4:], NORMAL
    return clean_module(text.split(":", 1)[0]), priority


def clean_module(name: str) -> str:
    return _MODULE_RE.sub("-", (name or "").strip().lower())[:64].strip("-") or "genel"


class LeaseCancelled(Exception):
    """The caller withdrew while waiting for its turn."""


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
    module: str = ""
    priority: int = INTERACTIVE


class LlmQueue:
    """Time-ordered admission control for the model. Backed by the catalog database; degrades to a
    process-local lock when no database is available (tests, offline tooling)."""

    #: How long a waiting ticket may go without a heartbeat before it is presumed dead. A live waiter
    #: writes one at most every `poll_seconds` (capped at 5s), so this is six missed writes.
    WAITING_HEARTBEAT_GRACE_SEC = 30
    #: A running ticket that beats writes every RUNNING_HEARTBEAT_SEC; six missed writes and it is dead.
    RUNNING_HEARTBEAT_SEC = 10
    RUNNING_HEARTBEAT_GRACE_SEC = 60
    #: One burst of 429s is one event: eight calls refused in the same second halve the slots once.
    PRESSURE_WINDOW_SEC = 10
    #: After pressure, a slot comes back for every this-many seconds of successful calls.
    RAISE_EVERY_SEC = 30
    #: how far back "who was served last" looks when two modules compete for a slot
    FAIRNESS_WINDOW_SEC = 600

    def __init__(
        self,
        engine: Optional[sa.Engine] = None,
        *,
        slots: int = 1,
        lease_seconds: int = 900,
        max_wait_seconds: int = 1800,
        poll_seconds: float = 0.25,
        worker: Optional[str] = None,
        reserve: Optional[int] = None,
        module_max: int = 0,
    ):
        self.engine = engine
        self.slots = max(1, slots)
        self.lease_seconds = lease_seconds
        self.max_wait_seconds = max_wait_seconds
        self.poll_seconds = poll_seconds
        self._base_poll = poll_seconds
        self.worker = worker or f"{socket.gethostname()}:{os.getpid()}"
        self._local = threading.Semaphore(self.slots)
        # Slots that only a watched request may take. A quarter of them unless told otherwise; none
        # when there is a single slot, or unattended work would never run at all.
        self.reserve = max(0, min(self.slots - 1, self.slots // 4 if reserve is None else reserve))
        #: most tickets one module may hold at once; 0 = no cap (fair ordering still applies)
        self.module_max = max(0, module_max)
        self._pg = engine is not None and engine.dialect.name == "postgresql"
        self._gate_clean = False          # True once a read showed no pressure: successes need no write
        # Waiters in this process are told the moment a slot frees here, instead of finding out on
        # their next poll (up to 5s later — a fifth of a 25s call, with the slot standing empty).
        # Waiters in other processes still find out by polling.
        self._freed = threading.Condition()
        if engine is not None:
            self._ensure_schema()

    def _ensure_schema(self) -> None:
        """The queue may be opened by a process that does not create tables (the timed scripts open
        the store with create=False) before the bridge has been restarted on this version. It brings
        what it needs itself: the gate table, and the columns the ticket table has gained."""
        try:
            S.sl_llm_gate.create(self.engine, checkfirst=True)
            insp = sa.inspect(self.engine)
            if not insp.has_table(S.sl_llm_queue.name):
                S.sl_llm_queue.create(self.engine, checkfirst=True)
                return
            have = {c["name"] for c in insp.get_columns(S.sl_llm_queue.name)}
            for col in S.sl_llm_queue.columns:
                if col.name not in have:
                    with self.engine.begin() as conn:
                        conn.execute(sa.text(f"ALTER TABLE {S.sl_llm_queue.name} ADD COLUMN {col.name} {col.type.compile(dialect=self.engine.dialect)}"))
        except Exception as e:  # noqa: BLE001 — two processes adding the same column at once: the loser is fine
            log.warning("llm queue: schema check: %s", e)

    @classmethod
    def from_env(cls, engine: Optional[sa.Engine] = None) -> "LlmQueue":
        reserve = os.environ.get("SEMANTIC_LLM_INTERACTIVE_RESERVE", "").strip()
        return cls(
            engine,
            slots=int(os.environ.get("SEMANTIC_LLM_SLOTS", "1")),
            lease_seconds=int(os.environ.get("SEMANTIC_LLM_LEASE_SEC", "900")),
            max_wait_seconds=int(os.environ.get("SEMANTIC_LLM_MAX_WAIT_SEC", "1800")),
            reserve=int(reserve) if reserve else None,
            module_max=int(os.environ.get("SEMANTIC_LLM_MODULE_MAX", "0")),
        )

    # ------------------------------------------------------------------ public
    @contextmanager
    def lease(self, *, purpose: str, tenant_id: str = "default", datasource_id: str = "default", user_id: Optional[str] = None, question: Optional[str] = None, on_wait: Optional[Any] = None,
              module: Optional[str] = None, priority: Optional[int] = None, cancel: Optional[threading.Event] = None) -> Iterator[Ticket]:
        """Block until it is this caller's turn, then run. Always releases, including on error."""
        derived_module, derived_priority = classify(purpose)
        module = clean_module(module) if module else derived_module
        priority = derived_priority if priority is None else max(INTERACTIVE, min(BATCH, int(priority)))
        if self.engine is None:
            acquired_at = time.perf_counter()
            self._local.acquire()
            try:
                yield Ticket(id="local", position=0, waited_ms=int((time.perf_counter() - acquired_at) * 1000), ahead=0, module=module, priority=priority)
            finally:
                self._local.release()
            return
        ticket_id = self._enqueue(purpose, tenant_id, datasource_id, user_id, question, module, priority)
        started = time.perf_counter()
        beat_stop = threading.Event()
        try:
            ahead = self._wait_for_turn(ticket_id, on_wait, cancel)
            threading.Thread(target=self._beat, args=(ticket_id, beat_stop), name=f"llmq-beat-{ticket_id[-6:]}", daemon=True).start()
            yield Ticket(id=ticket_id, position=0, waited_ms=int((time.perf_counter() - started) * 1000), ahead=ahead, module=module, priority=priority)
        finally:
            beat_stop.set()
            self._finish(ticket_id)

    def status(self, limit: int = 20) -> dict[str, Any]:
        """What the queue looks like right now — for the operator and for the waiting user."""
        if self.engine is None:
            return {"backend": "process", "slots": self.slots, "running": self.slots - self._local._value, "waiting": 0, "queue": []}
        with self.engine.begin() as conn:
            self._reclaim(conn)
            gate = self._gate(conn)
            rows = [dict(r._mapping) for r in conn.execute(
                sa.select(S.sl_llm_queue, PRIORITY.label("prio"))
                .where(S.sl_llm_queue.c.status.in_(("WAITING", "RUNNING")))
                .order_by(PRIORITY, S.sl_llm_queue.c.enqueued_at)
            )]
        running = [r for r in rows if r["status"] == "RUNNING"]
        waiting = [r for r in rows if r["status"] == "WAITING"]
        modules: dict[str, dict[str, int]] = {}
        for r in rows:
            m = modules.setdefault(r["module"] or classify(r["purpose"])[0], {"running": 0, "waiting": 0})
            m["running" if r["status"] == "RUNNING" else "waiting"] += 1
        cooldown = _aware(gate.get("cooldown_until"))
        return {
            "backend": "database",
            "slots": self.slots,
            "effectiveSlots": self._effective(gate),
            "reservedForInteractive": self.reserve,
            "cooldownUntil": cooldown.isoformat() if cooldown and cooldown > _now() else None,
            "lastPressure": {"status": gate.get("last_status"), "at": _aware(gate["last_pressure_at"]).isoformat()} if gate.get("last_pressure_at") else None,
            "running": len(running),
            "waiting": len(waiting),
            "modules": modules,
            "queue": [
                {
                    "position": i + 1,
                    "purpose": r["purpose"],
                    "module": r["module"] or classify(r["purpose"])[0],
                    "priority": r["prio"],
                    "user": r["user_id"],
                    "status": r["status"],
                    "enqueuedAt": _aware(r["enqueued_at"]).isoformat() if r["enqueued_at"] else None,
                    "waitingMs": int((_now() - _aware(r["enqueued_at"])).total_seconds() * 1000) if r["enqueued_at"] else 0,
                }
                for i, r in enumerate(waiting[:limit])
            ] + [
                {"position": 0, "purpose": r["purpose"], "module": r["module"] or classify(r["purpose"])[0], "priority": r["prio"], "user": r["user_id"], "status": "RUNNING", "startedAt": _aware(r["started_at"]).isoformat() if r["started_at"] else None}
                for r in running[:limit]
            ],
        }

    # ------------------------------------------------------------------ provider pressure
    def pressure(self, status: int, retry_after: Optional[float] = None) -> None:
        """The provider said it is full. Every process sharing this catalog slows down with us."""
        if self.engine is None:
            return
        try:
            with self.engine.begin() as conn:
                self._lock(conn)
                gate = self._gate(conn, create=True)
                now = _now()
                last = _aware(gate.get("last_pressure_at"))
                burst = last is not None and (now - last).total_seconds() < self.PRESSURE_WINDOW_SEC
                count = int(gate.get("pressure_count") or 0) + (0 if burst else 1)
                effective = self._effective(gate)
                if not burst:
                    effective = max(1, effective // 2)
                # What the provider asked for, or 5s·2ⁿ with jitter; never past two minutes — a longer
                # outage is handled by the next refusal extending it, not by guessing up front.
                pause = float(retry_after) if retry_after else min(60.0, 5.0 * (2 ** min(count - 1, 4))) * random.uniform(0.75, 1.25)
                until = now + timedelta(seconds=min(120.0, max(1.0, pause)))
                current = _aware(gate.get("cooldown_until"))
                conn.execute(S.sl_llm_gate.update().where(S.sl_llm_gate.c.id == GATE_ID).values(
                    effective_slots=effective, pressure_count=count, last_status=int(status), last_pressure_at=now,
                    cooldown_until=max(until, current) if current else until, last_raise_at=now))
            self._gate_clean = False
            if not burst:
                log.warning("llm gate: provider answered %s — slots %d → %d, admissions paused %.0fs", status, self._effective(gate), effective, pause)
        except Exception as e:  # noqa: BLE001
            log.warning("llm gate: could not record pressure: %s", e)

    def success(self) -> None:
        """A call came back. Costs nothing while the gate is clean; otherwise earns a slot back."""
        if self.engine is None or self._gate_clean:
            return
        try:
            with self.engine.begin() as conn:
                self._lock(conn)
                gate = self._gate(conn)
                if not gate:
                    self._gate_clean = True
                    return
                now = _now()
                effective = self._effective(gate)
                values: dict[str, Any] = {"last_success_at": now}
                raised = _aware(gate.get("last_raise_at"))
                if effective < self.slots and (raised is None or (now - raised).total_seconds() >= self.RAISE_EVERY_SEC):
                    effective += 1
                    values.update(effective_slots=effective, last_raise_at=now)
                    log.info("llm gate: calls are succeeding — slots back to %d/%d", effective, self.slots)
                if effective >= self.slots:
                    values.update(effective_slots=None, pressure_count=0)
                    self._gate_clean = True
                conn.execute(S.sl_llm_gate.update().where(S.sl_llm_gate.c.id == GATE_ID).values(**values))
        except Exception as e:  # noqa: BLE001
            log.warning("llm gate: could not record success: %s", e)

    # ------------------------------------------------------------------ internals
    def _lock(self, conn: sa.Connection) -> None:
        """Admission is a read-then-write; two processes doing it at once both see the free slot.
        PostgreSQL serialises it for the length of this transaction. SQLite already has one writer."""
        if self._pg:
            conn.execute(sa.text("SELECT pg_advisory_xact_lock(hashtext('sl_llm_queue'))"))

    def _gate(self, conn: sa.Connection, *, create: bool = False) -> dict[str, Any]:
        row = conn.execute(sa.select(S.sl_llm_gate).where(S.sl_llm_gate.c.id == GATE_ID)).first()
        if row is None and create:
            conn.execute(S.sl_llm_gate.insert().values(id=GATE_ID, pressure_count=0))
            row = conn.execute(sa.select(S.sl_llm_gate).where(S.sl_llm_gate.c.id == GATE_ID)).first()
        return dict(row._mapping) if row is not None else {}

    def _effective(self, gate: dict[str, Any]) -> int:
        value = gate.get("effective_slots")
        return self.slots if value is None else max(1, min(self.slots, int(value)))

    def _enqueue(self, purpose: str, tenant_id: str, datasource_id: str, user_id: Optional[str], question: Optional[str],
                 module: Optional[str] = None, priority: Optional[int] = None) -> str:
        """Purposes beginning with "bg:" are background work and yield to anyone who is waiting."""
        if module is None or priority is None:
            module, priority = classify(purpose)
        ticket_id = new_id("llmq")
        with self.engine.begin() as conn:
            conn.execute(S.sl_llm_queue.insert().values(
                id=ticket_id, tenant_id=tenant_id, datasource_id=datasource_id, user_id=user_id,
                purpose=purpose[:64], question=(question or "")[:500], status="WAITING",
                enqueued_at=_now(), heartbeat_at=_now(), worker=self.worker,
                module=module, priority=priority, beats=True,
            ))
        return ticket_id

    def _reclaim(self, conn: sa.Connection, *, exclude_id: Optional[str] = None) -> None:
        """A ticket whose worker stopped reporting is abandoned, so one crash cannot stop the line.
        The caller's own ticket is never reclaimed — it is being held by a thread that is right here."""
        Q = S.sl_llm_queue.c
        running_cutoff = _now() - timedelta(seconds=max(1, self.lease_seconds))
        beating_cutoff = _now() - timedelta(seconds=self.RUNNING_HEARTBEAT_GRACE_SEC)
        # A waiting ticket is held by a thread that writes a heartbeat on every poll, at most five
        # seconds apart. Judging it by the *lease* — the time a model call may take — leaves the
        # tickets of a process that was killed sitting at the head of the line for a quarter of an
        # hour, and every live question queues behind the dead ones. Measured on 2026-09-16 after a
        # deployment restart: twenty dead waiters, zero running, live questions stalled seventeen
        # minutes with eight free slots.
        waiting_cutoff = _now() - timedelta(seconds=self.WAITING_HEARTBEAT_GRACE_SEC)
        stale = sa.or_(
            # a holder that beats is alive exactly as long as it beats, however long the call takes
            sa.and_(Q.status == "RUNNING", Q.beats.is_(True), Q.heartbeat_at < beating_cutoff),
            # a holder that does not (older code, a hand-written row) can only be judged by the lease
            sa.and_(Q.status == "RUNNING", Q.beats.isnot(True), sa.or_(Q.heartbeat_at.is_(None), Q.heartbeat_at < running_cutoff)),
            sa.and_(Q.status == "WAITING", sa.or_(Q.heartbeat_at.is_(None), Q.heartbeat_at < waiting_cutoff)),
        )
        stmt = S.sl_llm_queue.update().where(stale).values(status="ABANDONED", finished_at=_now())
        if exclude_id:
            stmt = stmt.where(Q.id != exclude_id)
        conn.execute(stmt)

    def _admitted(self, conn: sa.Connection, gate: dict[str, Any]) -> tuple[set[str], list[str]]:
        """Who may start now, and the whole line in serving order.

        Walks the line the way slots will actually be handed out: after each admission the module
        that got it counts one more, so the next free slot goes to somebody else's module first."""
        Q = S.sl_llm_queue.c
        held: dict[str, int] = {}
        running = 0
        for module, purpose in conn.execute(sa.select(Q.module, Q.purpose).where(Q.status == "RUNNING")):
            running += 1
            key = module or classify(purpose)[0]
            held[key] = held.get(key, 0) + 1
        # Held slots alone cannot share a single slot: when it frees, nobody holds anything and the
        # oldest ticket wins — a module that sent a hundred prompts is served a hundred times before
        # anyone else once. So the tie goes to the module that was served longest ago.
        served: dict[str, datetime] = {}
        recent = _now() - timedelta(seconds=self.FAIRNESS_WINDOW_SEC)
        for module, purpose, at in conn.execute(
                sa.select(Q.module, Q.purpose, sa.func.max(Q.started_at))
                .where(Q.status.in_(("RUNNING", "DONE")), Q.enqueued_at > recent - timedelta(seconds=self.max_wait_seconds), Q.started_at > recent)
                .group_by(Q.module, Q.purpose)):
            key, at = module or classify(purpose)[0], _aware(at)
            if at is not None and (key not in served or at > served[key]):
                served[key] = at
        never = datetime.min.replace(tzinfo=timezone.utc)
        line = [
            {"id": r.id, "module": r.module or classify(r.purpose)[0], "priority": int(r.prio), "at": _aware(r.enqueued_at) or _now()}
            for r in conn.execute(sa.select(Q.id, Q.module, Q.purpose, Q.enqueued_at, PRIORITY.label("prio")).where(Q.status == "WAITING"))
        ]
        order = [t["id"] for t in sorted(line, key=lambda t: (t["priority"], t["at"], t["id"]))]
        cooldown = _aware(gate.get("cooldown_until"))
        if cooldown is not None and cooldown > _now():
            return set(), order
        effective = self._effective(gate)
        reserve = max(0, min(self.reserve, effective - 1))
        admitted: set[str] = set()
        while running < effective:
            open_to = [
                t for t in line
                if t["id"] not in admitted
                and (t["priority"] == INTERACTIVE or running < effective - reserve)
                and (not self.module_max or held.get(t["module"], 0) < self.module_max)
            ]
            if not open_to:
                break
            nxt = min(open_to, key=lambda t: (t["priority"], held.get(t["module"], 0), served.get(t["module"], never), t["at"], t["id"]))
            admitted.add(nxt["id"])
            held[nxt["module"]] = held.get(nxt["module"], 0) + 1
            served[nxt["module"]] = _now()
            running += 1
        return admitted, order

    def _wait_for_turn(self, ticket_id: str, on_wait: Optional[Any], cancel: Optional[threading.Event] = None) -> int:
        deadline = time.monotonic() + self.max_wait_seconds
        poll = self._base_poll
        announced = False
        ahead_at_start = 0
        take = S.sl_llm_queue.update().where(S.sl_llm_queue.c.id == ticket_id)
        while True:
            if cancel is not None and cancel.is_set():
                raise LeaseCancelled(ticket_id)
            with self.engine.begin() as conn:
                self._lock(conn)
                self._reclaim(conn, exclude_id=ticket_id)
                gate = self._gate(conn)
                self._gate_clean = not gate or (gate.get("effective_slots") is None and not gate.get("pressure_count"))
                admitted, order = self._admitted(conn, gate)
                if ticket_id not in order:              # someone marked it done: take the turn rather than stall
                    conn.execute(take.values(status="RUNNING", started_at=_now(), heartbeat_at=_now(), worker=self.worker))
                    return ahead_at_start
                ahead = order.index(ticket_id)
                if not announced:
                    ahead_at_start = ahead
                    announced = True
                if ticket_id in admitted:
                    conn.execute(take.values(status="RUNNING", started_at=_now(), heartbeat_at=_now(), worker=self.worker))
                    return ahead_at_start
                conn.execute(take.values(heartbeat_at=_now()))
            if on_wait is not None:
                try:
                    on_wait(ahead)
                except Exception:  # noqa: BLE001
                    pass
            # Back off: a request that has been waiting for minutes does not need four checks a second
            # on the production database. Starts responsive, settles to a light poll.
            poll = min(poll * 1.5, 5.0)
            if time.monotonic() > deadline:
                if self._is_background_ticket(ticket_id):
                    raise TimeoutError("Background LLM work yielded after queue wait limit")
                # Never fail the user's question on queueing alone: take the slot and let the model decide.
                log.warning("llm queue wait exceeded %ss for %s — proceeding", self.max_wait_seconds, ticket_id)
                with self.engine.begin() as conn:
                    conn.execute(take.values(status="RUNNING", started_at=_now(), heartbeat_at=_now(), worker=self.worker))
                return ahead_at_start
            wake_at = time.monotonic() + poll
            with self._freed:
                while True:
                    left = wake_at - time.monotonic()
                    if left <= 0 or (cancel is not None and cancel.is_set()):
                        break
                    if self._freed.wait(left if cancel is None else min(left, 0.25)):
                        break                              # a slot was freed here: look now

    def _beat(self, ticket_id: str, stop: threading.Event) -> None:
        """Keeps a RUNNING ticket alive for as long as the call really runs."""
        while not stop.wait(self.RUNNING_HEARTBEAT_SEC):
            try:
                with self.engine.begin() as conn:
                    conn.execute(S.sl_llm_queue.update()
                                 .where(S.sl_llm_queue.c.id == ticket_id, S.sl_llm_queue.c.status == "RUNNING")
                                 .values(heartbeat_at=_now()))
            except Exception as e:  # noqa: BLE001
                log.warning("llm queue heartbeat failed for %s: %s", ticket_id, e)

    def _is_background_ticket(self, ticket_id: str) -> bool:
        with self.engine.connect() as conn:
            priority = conn.execute(sa.select(PRIORITY).where(S.sl_llm_queue.c.id == ticket_id)).scalar()
        return int(priority or 0) > INTERACTIVE

    def _finish(self, ticket_id: str) -> None:
        try:
            with self.engine.begin() as conn:
                conn.execute(S.sl_llm_queue.update().where(S.sl_llm_queue.c.id == ticket_id).values(status="DONE", finished_at=_now()))
        except Exception as e:  # noqa: BLE001
            log.warning("llm queue release failed for %s: %s", ticket_id, e)
        with self._freed:
            self._freed.notify_all()


class QueuedLlm:
    """Wraps any LLM client so every call goes through the queue. The wrapped client is unaware."""

    def __init__(self, llm: Any, queue: LlmQueue, *, purpose: str = "nl2sql", tenant_id: str = "default", datasource_id: str = "default",
                 module: Optional[str] = None, priority: Optional[int] = None):
        self.llm = llm
        self.queue = queue
        self.purpose = purpose
        self.module = module
        self.priority = priority
        self.tenant_id = tenant_id
        self.datasource_id = datasource_id
        self.model = getattr(llm, "model", "")
        # The bridge shares one wrapper between every request thread; what the last call waited is
        # only meaningful to the thread that made it.
        self._last = threading.local()
        # A client that can tell load from failure tells the queue, and through it every process.
        if hasattr(llm, "observer") and getattr(llm, "observer", None) is None:
            llm.observer = queue

    @property
    def last_wait_ms(self) -> int:
        return getattr(self._last, "wait_ms", 0)

    @property
    def last_ahead(self) -> int:
        return getattr(self._last, "ahead", 0)

    def for_module(self, module: str, *, priority: Optional[int] = None, purpose: Optional[str] = None) -> "QueuedLlm":
        """The same model and the same line, asked on behalf of another part of the product."""
        prefix = {BATCH: "bg:", NORMAL: "std:"}.get(priority if priority is not None else INTERACTIVE, "")
        return QueuedLlm(self.llm, self.queue, purpose=purpose or f"{prefix}{clean_module(module)}", tenant_id=self.tenant_id,
                         datasource_id=self.datasource_id, module=module, priority=priority)

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        cancel = kwargs.get("cancel")
        on_admitted = kwargs.pop("on_admitted", None)      # told when the wait is over and the call begins
        if cancel is not None and not _accepts_cancel(self.llm):
            kwargs.pop("cancel")
        with self.queue.lease(purpose=self.purpose, tenant_id=self.tenant_id, datasource_id=self.datasource_id,
                              user_id=kwargs.pop("user_id", None), question=_first_user_message(messages),
                              module=self.module, priority=self.priority, cancel=cancel) as ticket:
            self._last.wait_ms, self._last.ahead = ticket.waited_ms, ticket.ahead
            if on_admitted is not None:
                try:
                    on_admitted(ticket)
                except Exception:  # noqa: BLE001
                    pass
            return self.llm.chat(messages, **kwargs)


def _accepts_cancel(llm: Any) -> bool:
    return bool(getattr(llm, "supports_cancel", False))


def _first_user_message(messages: list[dict[str, str]]) -> str:
    for m in reversed(messages or []):
        if m.get("role") == "user":
            return str(m.get("content") or "")[:500]
    return ""
