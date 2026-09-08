"""The shared model is handed out in arrival order: nobody is rejected, nobody overtakes."""

from __future__ import annotations

import threading
import time

import pytest
import sqlalchemy as sa

from semantic_layer.runtime.llm_queue import LlmQueue, QueuedLlm
from semantic_layer.store import schema as S
from semantic_layer.store.catalog_store import open_store


class SlowLlm:
    """A model that can only do one thing at a time — exactly what the queue exists to protect."""

    def __init__(self, delay: float = 0.15):
        self.delay = delay
        self.concurrent = 0
        self.max_concurrent = 0
        self.order: list[str] = []
        self._lock = threading.Lock()
        self.model = "slow"

    def chat(self, messages, **_):
        with self._lock:
            self.concurrent += 1
            self.max_concurrent = max(self.max_concurrent, self.concurrent)
        try:
            time.sleep(self.delay)
            text = messages[-1]["content"]
            self.order.append(text)
            return f"ok:{text}"
        finally:
            with self._lock:
                self.concurrent -= 1


@pytest.fixture
def queue_store(tmp_path):
    store = open_store(f"sqlite:///{tmp_path}/queue.db")
    return store


def _ask(llm, text, results, idx):
    results[idx] = llm.chat([{"role": "user", "content": text}])


def test_requests_are_serialised_and_ordered(queue_store):
    llm = SlowLlm()
    queue = LlmQueue(queue_store.engine, slots=1, poll_seconds=0.02)
    client = QueuedLlm(llm, queue)
    results: dict[int, str] = {}
    threads = []
    for i in range(4):
        t = threading.Thread(target=_ask, args=(client, f"soru-{i}", results, i))
        threads.append(t)
        t.start()
        time.sleep(0.05)          # arrival order is the queue order
    for t in threads:
        t.join(timeout=20)
    assert len(results) == 4 and all(v.startswith("ok:") for v in results.values())
    assert llm.max_concurrent == 1, "model was called concurrently despite the queue"
    assert llm.order == [f"soru-{i}" for i in range(4)], "requests were not served in arrival order"


def test_nobody_is_rejected_when_the_model_is_busy(queue_store):
    started, release = threading.Event(), threading.Event()

    class HeldLlm(SlowLlm):
        def chat(self, messages, **kwargs):
            if messages[-1]["content"] == "uzun":
                started.set()
                assert release.wait(timeout=10), "test did not release the model"
            return super().chat(messages, **kwargs)

    llm = HeldLlm(delay=0.01)
    queue = LlmQueue(queue_store.engine, slots=1, poll_seconds=0.02)
    client = QueuedLlm(llm, queue)
    results: dict[int, str] = {}
    a = threading.Thread(target=_ask, args=(client, "uzun", results, 0))
    b = threading.Thread(target=_ask, args=(client, "beklesin", results, 1))
    a.start()
    try:
        assert started.wait(timeout=5), "first request never reached the model"
        assert queue.status()["running"] == 1
        b.start()
        deadline = time.monotonic() + 5
        waiting = queue.status()
        while waiting["waiting"] != 1 and time.monotonic() < deadline:
            time.sleep(0.01)
            waiting = queue.status()
        assert waiting["waiting"] == 1 and waiting["queue"][0]["position"] == 1
    finally:
        release.set()
        a.join(timeout=20)
        if b.ident is not None:
            b.join(timeout=20)
    assert results[1] == "ok:beklesin"
    assert client.last_wait_ms > 0


def test_a_dead_worker_does_not_block_the_line(queue_store):
    queue = LlmQueue(queue_store.engine, slots=1, lease_seconds=0, poll_seconds=0.02)
    with queue_store.engine.begin() as conn:                                  # a ticket left RUNNING by a crash
        conn.execute(S.sl_llm_queue.insert().values(
            id="ghost", tenant_id="t", datasource_id="d", purpose="nl2sql", status="RUNNING",
            enqueued_at=sa.func.now(), started_at=sa.func.now(), heartbeat_at=None, worker="dead",
        ))
    llm = SlowLlm(delay=0.01)
    assert QueuedLlm(llm, queue).chat([{"role": "user", "content": "devam"}]) == "ok:devam"
    with queue_store.engine.connect() as conn:
        ghost = conn.execute(sa.select(S.sl_llm_queue.c.status).where(S.sl_llm_queue.c.id == "ghost")).scalar()
    assert ghost == "ABANDONED"


def test_catalog_answers_never_take_a_ticket(queue_store, profiles):
    """A question the catalog can answer must not queue behind a model call."""
    from semantic_layer.runtime.compiler import DeterministicCompiler
    queue = LlmQueue(queue_store.engine, slots=1, poll_seconds=0.02)
    before = queue.status()
    comp = DeterministicCompiler(profiles, {}, "sqlite")
    assert comp is not None and before["waiting"] == 0
    with queue_store.engine.connect() as conn:
        assert conn.execute(sa.select(sa.func.count()).select_from(S.sl_llm_queue)).scalar() == 0


def test_background_work_yields_to_anyone_waiting(store):
    """The schema reader can take all night; a person's question cannot take a minute longer because a
    batch of it happened to arrive first. Background tickets sort after interactive ones, whatever
    time they arrived."""
    import threading

    from semantic_layer.runtime.llm_queue import LlmQueue

    q = LlmQueue(store.engine, slots=1, poll_seconds=0.05, lease_seconds=30)
    order: list[str] = []
    gate = threading.Event()

    def run(purpose: str, name: str, hold: float = 0.0):
        with q.lease(purpose=purpose):
            order.append(name)
            if hold:
                gate.wait(timeout=5)

    first = threading.Thread(target=run, args=("bg:nightly", "bg-1", 0.3))
    first.start()
    import time as _t

    _t.sleep(0.15)                      # bg-1 is running and holding the only slot
    rest = [threading.Thread(target=run, args=("bg:nightly", "bg-2")),
            threading.Thread(target=run, args=("nl2sql", "insan"))]
    for t in rest:
        t.start()
        _t.sleep(0.1)                   # bg-2 arrives BEFORE the person does
    gate.set()
    first.join(timeout=10)
    for t in rest:
        t.join(timeout=10)
    assert order[0] == "bg-1"
    assert order.index("insan") < order.index("bg-2"), order
