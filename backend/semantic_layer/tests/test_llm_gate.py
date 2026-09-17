"""Many modules, one model: who gets the next slot, what a refusal from the provider changes, and
what keeps a long call from being taken for a dead one."""

from __future__ import annotations

import threading
import time
from datetime import timedelta

import pytest
import sqlalchemy as sa

from semantic_layer.runtime.llm_queue import BATCH, INTERACTIVE, NORMAL, LeaseCancelled, LlmQueue, QueuedLlm, _now, classify
from semantic_layer.store import schema as S

Q = S.sl_llm_queue


class Recorder:
    """A model that writes down who it served, in order, and how many at once."""

    def __init__(self, delay: float = 0.05):
        self.delay = delay
        self.order: list[str] = []
        self.now = 0
        self.peak = 0
        self.by_tag: dict[str, int] = {}
        self._lock = threading.Lock()
        self.model = "recorder"

    def chat(self, messages, **_):
        tag = messages[-1]["content"]
        with self._lock:
            self.now += 1
            self.peak = max(self.peak, self.now)
            self.order.append(tag)
        try:
            time.sleep(self.delay)
            return f"ok:{tag}"
        finally:
            with self._lock:
                self.now -= 1


def _hold(queue: LlmQueue, purpose: str, started: threading.Event, release: threading.Event, **kw) -> threading.Thread:
    def run():
        with queue.lease(purpose=purpose, **kw):
            started.set()
            release.wait(timeout=30)
    t = threading.Thread(target=run)
    t.start()
    return t


def _wait_until(predicate, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def test_purpose_says_module_and_priority():
    assert classify("nl2sql") == ("nl2sql", INTERACTIVE)
    assert classify("nl2sql:selector") == ("nl2sql", INTERACTIVE)
    assert classify("bg:language-pool") == ("language-pool", BATCH)
    assert classify("std:Reports") == ("reports", NORMAL)
    assert classify("") == ("genel", INTERACTIVE)


def test_one_module_flooding_does_not_make_the_others_wait_for_all_of_it(gate_engine):
    """Ten prompts from one module, then one each from two others, a single slot. Arrival order would
    serve the late modules 11th and 12th; taking turns serves them 2nd and 3rd."""
    llm = Recorder(delay=0.05)
    queue = LlmQueue(gate_engine, slots=1, poll_seconds=0.02)
    started, release = threading.Event(), threading.Event()
    holder = _hold(queue, "kalabalik", started, release)
    assert started.wait(5)
    threads = []
    for tag, module in [(f"kalabalik-{i}", "kalabalik") for i in range(10)] + [("rapor-1", "rapor"), ("sohbet-1", "sohbet")]:
        t = threading.Thread(target=QueuedLlm(llm, queue, purpose=module).chat, args=([{"role": "user", "content": tag}],))
        t.start()
        threads.append(t)
        time.sleep(0.03)                  # arrival order is fixed: the flood first, the others last
    assert _wait_until(lambda: queue.status()["waiting"] == 12)
    release.set()
    holder.join(10)
    for t in threads:
        t.join(30)
    assert len(llm.order) == 12 and llm.peak == 1
    assert llm.order.index("rapor-1") <= 2 and llm.order.index("sohbet-1") <= 2, llm.order
    flood = [t for t in llm.order if t.startswith("kalabalik")]
    assert flood == [f"kalabalik-{i}" for i in range(10)], "within a module, arrival order still holds"


def test_unattended_work_cannot_take_the_last_slots(gate_engine):
    queue = LlmQueue(gate_engine, slots=4, reserve=1, poll_seconds=0.02)
    release = threading.Event()
    started = [threading.Event() for _ in range(5)]
    holders = [_hold(queue, "bg:gece", started[i], release) for i in range(5)]
    try:
        assert _wait_until(lambda: queue.status()["running"] == 3)
        time.sleep(0.5)
        state = queue.status()
        assert state["running"] == 3 and state["waiting"] == 2, "background took a reserved slot"
        person = threading.Event()
        holders.append(_hold(queue, "nl2sql", person, release))
        assert person.wait(5), "a person waited although a slot was kept for them"
        assert queue.status()["running"] == 4
    finally:
        release.set()
        for t in holders:
            t.join(15)
    assert all(e.is_set() for e in started), "background work never ran"


def test_a_single_slot_still_runs_background_work(gate_engine):
    queue = LlmQueue(gate_engine, slots=1, poll_seconds=0.02)
    assert queue.reserve == 0
    with queue.lease(purpose="bg:gece") as ticket:
        assert ticket.priority == BATCH


def test_module_cap_is_off_unless_configured(gate_engine):
    queue = LlmQueue(gate_engine, slots=3, reserve=0, module_max=1, poll_seconds=0.02)
    release = threading.Event()
    a1, a2, b1 = threading.Event(), threading.Event(), threading.Event()
    holders = [_hold(queue, "a", a1, release), _hold(queue, "a", a2, release), _hold(queue, "b", b1, release)]
    try:
        assert _wait_until(lambda: queue.status()["running"] == 2)
        time.sleep(0.4)
        assert b1.is_set() and (a1.is_set() != a2.is_set()), "module cap of 1 let two of the same module run"
    finally:
        release.set()
        for t in holders:
            t.join(15)


def test_a_long_call_is_not_taken_for_a_dead_one(gate_engine):
    """Lease 1s, call 3s. Judged by the lease, the ticket is reclaimed mid-call and a second call is
    admitted over the slot limit — 26 times in the week before this was written."""
    llm = Recorder(delay=3.0)
    queue = LlmQueue(gate_engine, slots=1, lease_seconds=1, poll_seconds=0.05)
    queue.RUNNING_HEARTBEAT_SEC = 0.3
    client = QueuedLlm(llm, queue)
    threads = [threading.Thread(target=client.chat, args=([{"role": "user", "content": f"uzun-{i}"}],)) for i in range(2)]
    for t in threads:
        t.start()
        time.sleep(0.1)
    for t in threads:
        t.join(20)
    assert llm.peak == 1, "the running ticket was reclaimed while its call was alive"
    with gate_engine.connect() as conn:
        assert conn.execute(sa.select(sa.func.count()).select_from(Q).where(Q.c.status == "ABANDONED")).scalar() == 0


def test_a_holder_that_stopped_beating_is_reclaimed_within_the_grace(gate_engine):
    queue = LlmQueue(gate_engine, slots=1, lease_seconds=3600, poll_seconds=0.02)
    long_ago = _now() - timedelta(seconds=queue.RUNNING_HEARTBEAT_GRACE_SEC + 5)
    with gate_engine.begin() as conn:
        conn.execute(Q.insert().values(id="olu", tenant_id="t", datasource_id="d", purpose="nl2sql", status="RUNNING", beats=True,
                                       enqueued_at=long_ago, started_at=long_ago, heartbeat_at=long_ago, worker="olu:1"))
    t0 = time.monotonic()
    with queue.lease(purpose="nl2sql"):
        pass
    assert time.monotonic() - t0 < 5, "waited for an hour-long lease although the holder had stopped beating"
    with gate_engine.connect() as conn:
        assert conn.execute(sa.select(Q.c.status).where(Q.c.id == "olu")).scalar() == "ABANDONED"


def test_a_ticket_from_older_code_is_still_judged_by_the_lease(gate_engine):
    queue = LlmQueue(gate_engine, slots=1, lease_seconds=3600, poll_seconds=0.02, max_wait_seconds=1)
    a_while = _now() - timedelta(seconds=300)
    with gate_engine.begin() as conn:
        conn.execute(Q.insert().values(id="eski", tenant_id="t", datasource_id="d", purpose="bg:eski", status="RUNNING", beats=None,
                                       enqueued_at=a_while, started_at=a_while, heartbeat_at=a_while, worker="eski:1"))
    with pytest.raises(TimeoutError):                   # no heartbeat for 300s, lease 3600s: still held
        with queue.lease(purpose="bg:yeni"):
            pass
    with gate_engine.connect() as conn:
        assert conn.execute(sa.select(Q.c.status).where(Q.c.id == "eski")).scalar() == "RUNNING"


def test_a_refusal_from_the_provider_slows_every_process(gate_engine):
    a = LlmQueue(gate_engine, slots=8, poll_seconds=0.02)
    b = LlmQueue(gate_engine, slots=8, poll_seconds=0.02, worker="baska-surec:2")
    for _ in range(8):                                  # eight calls refused in the same second: one event
        a.pressure(429, 1.0)
    state = b.status()
    assert state["effectiveSlots"] == 4 and state["cooldownUntil"], state
    assert state["lastPressure"]["status"] == 429
    t0 = time.monotonic()
    with b.lease(purpose="nl2sql"):                     # the other process waits out the pause too
        waited = time.monotonic() - t0
    assert 0.5 <= waited < 5, waited


def test_slots_come_back_one_at_a_time_as_calls_succeed(gate_engine):
    queue = LlmQueue(gate_engine, slots=4, poll_seconds=0.02)
    queue.PRESSURE_WINDOW_SEC = 0
    queue.RAISE_EVERY_SEC = 0
    queue.pressure(504, 0.01)
    queue.pressure(504, 0.01)
    assert queue.status()["effectiveSlots"] == 1
    seen = []
    for _ in range(3):
        queue.success()
        seen.append(queue.status()["effectiveSlots"])
    assert seen == [2, 3, 4]
    with gate_engine.connect() as conn:
        row = conn.execute(sa.select(S.sl_llm_gate)).first()
    assert row.effective_slots is None and row.pressure_count == 0
    queue.success()                                     # clean gate: costs no write, changes nothing
    assert queue.status()["effectiveSlots"] == 4


def test_reduced_slots_are_what_admission_uses(gate_engine):
    queue = LlmQueue(gate_engine, slots=4, reserve=0, poll_seconds=0.02)
    queue.pressure(429, 0.2)                            # 4 → 2
    release = threading.Event()
    started = [threading.Event() for _ in range(4)]
    holders = [_hold(queue, "nl2sql", started[i], release) for i in range(4)]
    try:
        assert _wait_until(lambda: queue.status()["running"] == 2)
        time.sleep(0.6)
        assert queue.status()["running"] == 2, "admitted past the reduced slot count"
    finally:
        release.set()
        for t in holders:
            t.join(15)


def test_a_waiter_can_withdraw(gate_engine):
    queue = LlmQueue(gate_engine, slots=1, poll_seconds=0.02)
    started, release, cancel = threading.Event(), threading.Event(), threading.Event()
    holder = _hold(queue, "nl2sql", started, release)
    assert started.wait(5)
    outcome: list[str] = []

    def waiter():
        try:
            with queue.lease(purpose="nl2sql", cancel=cancel):
                outcome.append("ran")
        except LeaseCancelled:
            outcome.append("cancelled")

    t = threading.Thread(target=waiter)
    t.start()
    assert _wait_until(lambda: queue.status()["waiting"] == 1)
    cancel.set()
    t.join(5)
    release.set()
    holder.join(10)
    assert outcome == ["cancelled"]
    assert queue.status()["waiting"] == 0


def test_what_one_request_waited_is_not_shown_to_another(gate_engine):
    llm = Recorder(delay=0.3)
    queue = LlmQueue(gate_engine, slots=1, poll_seconds=0.02)
    shared = QueuedLlm(llm, queue)
    seen: dict[str, int] = {}

    def ask(tag):
        shared.chat([{"role": "user", "content": tag}])
        seen[tag] = shared.last_wait_ms

    first = threading.Thread(target=ask, args=("ilk",))
    first.start()
    time.sleep(0.1)
    second = threading.Thread(target=ask, args=("ikinci",))
    second.start()
    first.join(10)
    second.join(10)
    assert seen["ikinci"] >= 150 > seen["ilk"], seen
    assert shared.last_wait_ms == 0, "this thread asked nothing"


def test_twelve_modules_at_once_never_exceed_the_slots(gate_engine):
    """The shape of the request that started this: many modules, all sending at the same moment."""
    llm = Recorder(delay=0.05)
    queue = LlmQueue(gate_engine, slots=3, reserve=1, poll_seconds=0.02)
    results: dict[str, str] = {}
    errors: list[str] = []

    def ask(module, i, purpose):
        tag = f"{module}-{i}"
        try:
            results[tag] = QueuedLlm(llm, queue, purpose=purpose).chat([{"role": "user", "content": tag}])
        except Exception as e:  # noqa: BLE001
            errors.append(f"{tag}: {e}")

    threads = []
    for m in range(12):
        purpose = f"bg:modul{m}" if m % 3 == 0 else f"std:modul{m}" if m % 3 == 1 else f"modul{m}"
        for i in range(4):
            threads.append(threading.Thread(target=ask, args=(f"modul{m}", i, purpose)))
    for t in threads:
        t.start()
    for t in threads:
        t.join(120)
    assert not errors, errors
    assert len(results) == 48 and all(v.startswith("ok:") for v in results.values())
    assert llm.peak <= 3, f"{llm.peak} calls at once with 3 slots"
    with gate_engine.connect() as conn:
        left = dict(conn.execute(sa.select(Q.c.status, sa.func.count()).group_by(Q.c.status)).fetchall())
    assert left == {"DONE": 48}, left


def test_the_queue_brings_its_own_tables_and_columns(tmp_path):
    """A timed script opens the store without creating anything. If it runs on this version before
    the bridge was restarted, the ticket table is the old one and the gate table does not exist."""
    engine = sa.create_engine(f"sqlite:///{tmp_path}/eski.db")
    with engine.begin() as conn:
        conn.execute(sa.text("""CREATE TABLE sl_llm_queue (id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64) NOT NULL,
            datasource_id VARCHAR(128) NOT NULL, user_id VARCHAR(128), purpose VARCHAR(64) NOT NULL, question TEXT,
            status VARCHAR(16) NOT NULL DEFAULT 'WAITING', enqueued_at DATETIME NOT NULL, started_at DATETIME,
            finished_at DATETIME, heartbeat_at DATETIME, worker VARCHAR(128))"""))
        conn.execute(sa.text("INSERT INTO sl_llm_queue (id, tenant_id, datasource_id, purpose, status, enqueued_at) VALUES ('eski1','t','d','bg:eski','DONE','2026-09-01 00:00:00')"))
    queue = LlmQueue(engine, slots=1, poll_seconds=0.02)
    with queue.lease(purpose="std:rapor") as ticket:
        assert ticket.module == "rapor" and ticket.priority == NORMAL
    queue.pressure(429, 0.01)
    assert queue.status()["lastPressure"]["status"] == 429
    LlmQueue(engine, slots=1)                           # a second opener finds everything in place
