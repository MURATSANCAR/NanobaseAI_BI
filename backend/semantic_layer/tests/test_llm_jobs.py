"""A prompt left at the door: accepted at once, answered later, never lost, never run twice."""

from __future__ import annotations

import threading
import time
from datetime import timedelta

import pytest
import sqlalchemy as sa

from semantic_layer.runtime.llm_jobs import LlmJobs, _now
from semantic_layer.runtime.llm_queue import BATCH, INTERACTIVE, LlmQueue, QueuedLlm
from semantic_layer.store import schema as S

J = S.sl_llm_job
MSG = [{"role": "user", "content": "merhaba"}]


class Model:
    supports_cancel = True

    def __init__(self, delay: float = 0.05):
        self.delay = delay
        self.calls: list[str] = []
        self.now = 0
        self.peak = 0
        self.hold: threading.Event | None = None
        self.fail_with: Exception | None = None
        self._lock = threading.Lock()
        self.model = "model-a"

    def chat(self, messages, *, cancel=None, **_):
        tag = messages[-1]["content"]
        with self._lock:
            self.now += 1
            self.peak = max(self.peak, self.now)
            self.calls.append(tag)
        try:
            if self.fail_with is not None:
                raise self.fail_with
            if self.hold is not None:
                deadline = time.monotonic() + 30
                while not self.hold.is_set() and time.monotonic() < deadline:
                    if cancel is not None and cancel.is_set():
                        raise RuntimeError("cancelled in flight")
                    time.sleep(0.02)
            time.sleep(self.delay)
            return f"cevap:{tag}"
        finally:
            with self._lock:
                self.now -= 1


def _jobs(engine, model, *, slots=2, workers=3, interactive_workers=1, start=True, worker=None) -> LlmJobs:
    queue = LlmQueue(engine, slots=slots, reserve=0, poll_seconds=0.02)
    llm = QueuedLlm(model, queue)
    jobs = LlmJobs(engine, lambda: llm, workers=workers, interactive_workers=interactive_workers, worker=worker)
    jobs.IDLE_POLL_SEC = 0.05
    jobs.HEARTBEAT_SEC = 0.2
    if start:
        jobs.start()
    return jobs


@pytest.fixture
def model():
    return Model()


def test_accepted_at_once_answered_later(gate_engine, model):
    jobs = _jobs(gate_engine, model)
    try:
        t0 = time.monotonic()
        job = jobs.submit(MSG, module="Raporlar", user_id="ayse")
        assert time.monotonic() - t0 < 1 and job["status"] == "QUEUED" and job["module"] == "raporlar" and job["position"] == 1
        done = jobs.wait(job["id"], timeout=10)
        assert done["status"] == "DONE" and done["result"] == "cevap:merhaba"
        assert done["llmMs"] is not None and done["attempts"] == 1
    finally:
        jobs.stop()


def test_what_is_sent_is_checked_before_it_is_accepted(gate_engine, model):
    jobs = _jobs(gate_engine, model, start=False)
    for bad in (None, [], [{"role": "robot", "content": "x"}], [{"role": "user", "content": 5}]):
        with pytest.raises(ValueError):
            jobs.submit(bad, module="m")
    with pytest.raises(ValueError):
        jobs.submit(MSG, module="m", priority="acil")


def test_the_same_prompt_in_flight_is_the_same_job(gate_engine, model):
    model.hold = threading.Event()
    jobs = _jobs(gate_engine, model)
    try:
        a = jobs.submit(MSG, module="m", user_id="ayse")
        b = jobs.submit(MSG, module="m", user_id="ayse")
        assert b["id"] == a["id"] and b["deduplicated"] and not a["deduplicated"]
        other_user = jobs.submit(MSG, module="m", user_id="mehmet")
        other_module = jobs.submit(MSG, module="n", user_id="ayse")
        unshared = jobs.submit(MSG, module="m", user_id="ayse", dedup=False)
        assert len({a["id"], other_user["id"], other_module["id"], unshared["id"]}) == 4
        model.hold.set()
        assert jobs.wait(a["id"], timeout=10)["status"] == "DONE"
        again = jobs.submit(MSG, module="m", user_id="ayse")
        assert again["id"] != a["id"], "a finished job is not reused unless the caller asks for it"
        jobs.wait(again["id"], timeout=10)
        cached = jobs.submit(MSG, module="m", user_id="ayse", cache_ttl_sec=60)
        assert cached["deduplicated"] and cached["status"] == "DONE" and cached["result"] == "cevap:merhaba"
    finally:
        model.hold.set()
        jobs.stop()


def test_identical_submits_at_the_same_instant_make_one_job(gate_engine, model):
    jobs = _jobs(gate_engine, model, start=False)
    ids: list[str] = []
    go = threading.Barrier(8)

    def submit():
        go.wait(5)
        ids.append(jobs.submit(MSG, module="m", user_id="ayse")["id"])

    threads = [threading.Thread(target=submit) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(20)
    if gate_engine.dialect.name == "postgresql":
        assert len(set(ids)) == 1, ids
    with gate_engine.connect() as conn:
        assert conn.execute(sa.select(sa.func.count()).select_from(J)).scalar() == len(set(ids))


def test_a_waiting_job_can_be_cancelled(gate_engine, model):
    jobs = _jobs(gate_engine, model, start=False)
    job = jobs.submit(MSG, module="m")
    assert jobs.cancel(job["id"])["status"] == "CANCELLED"
    jobs.start()
    try:
        time.sleep(0.4)
        assert model.calls == [] and jobs.get(job["id"])["status"] == "CANCELLED"
    finally:
        jobs.stop()


def test_a_running_job_can_be_cancelled_and_frees_its_slot(gate_engine, model):
    model.hold = threading.Event()
    jobs = _jobs(gate_engine, model, slots=1)
    try:
        first = jobs.submit([{"role": "user", "content": "uzun"}], module="m")
        deadline = time.monotonic() + 5
        while model.now == 0 and time.monotonic() < deadline:
            time.sleep(0.02)
        assert model.now == 1
        t0 = time.monotonic()
        assert jobs.cancel(first["id"])["status"] == "CANCELLED"
        model_freed = time.monotonic() + 5
        while model.now and time.monotonic() < model_freed:
            time.sleep(0.02)
        assert model.now == 0 and time.monotonic() - t0 < 3, "the cancelled call kept the model"
        model.hold.set()
        second = jobs.submit([{"role": "user", "content": "sonraki"}], module="m")
        assert jobs.wait(second["id"], timeout=10)["status"] == "DONE"
        assert jobs.get(first["id"])["status"] == "CANCELLED", "the late result overwrote the cancellation"
    finally:
        model.hold.set()
        jobs.stop()


def test_a_failing_model_fails_the_job_out_loud(gate_engine, model):
    model.fail_with = RuntimeError("LLM HTTP 404: function not found")
    jobs = _jobs(gate_engine, model)
    try:
        done = jobs.wait(jobs.submit(MSG, module="m")["id"], timeout=10)
        assert done["status"] == "FAILED" and "404" in done["error"] and done["result"] is None
    finally:
        jobs.stop()


def test_jobs_survive_a_restart(gate_engine, model):
    before = _jobs(gate_engine, model, start=False)
    ids = [before.submit([{"role": "user", "content": f"s{i}"}], module="m")["id"] for i in range(5)]
    del before                                           # the process that accepted them is gone
    after = _jobs(gate_engine, model)
    try:
        assert all(after.wait(i, timeout=15)["status"] == "DONE" for i in ids)
        assert sorted(model.calls) == [f"s{i}" for i in range(5)], "a job ran twice or not at all"
    finally:
        after.stop()


def test_a_job_whose_runner_died_goes_back_in_line(gate_engine, model):
    jobs = _jobs(gate_engine, model, start=False)
    job = jobs.submit(MSG, module="m")
    stale = _now() - timedelta(seconds=jobs.STALE_AFTER_SEC + 5)
    with gate_engine.begin() as conn:                    # claimed by a runner that then died
        conn.execute(J.update().where(J.c.id == job["id"]).values(status="RUNNING", attempts=1, started_at=stale, heartbeat_at=stale, worker="olu:1"))
    jobs.start()
    try:
        done = jobs.wait(job["id"], timeout=15)
        assert done["status"] == "DONE" and done["attempts"] == 2
    finally:
        jobs.stop()


def test_three_dead_runners_and_the_job_is_failed(gate_engine, model):
    jobs = _jobs(gate_engine, model, start=False)
    job = jobs.submit(MSG, module="m")
    stale = _now() - timedelta(seconds=jobs.STALE_AFTER_SEC + 5)
    with gate_engine.begin() as conn:
        conn.execute(J.update().where(J.c.id == job["id"]).values(status="RUNNING", attempts=jobs.MAX_ATTEMPTS, started_at=stale, heartbeat_at=stale))
    jobs._sweep()
    view = jobs.get(job["id"])
    assert view["status"] == "FAILED" and "kayboldu" in view["error"] and model.calls == []


def test_a_live_runner_in_another_process_is_left_alone(gate_engine, model):
    jobs = _jobs(gate_engine, model, start=False)
    job = jobs.submit(MSG, module="m")
    with gate_engine.begin() as conn:
        conn.execute(J.update().where(J.c.id == job["id"]).values(status="RUNNING", attempts=1, started_at=_now(), heartbeat_at=_now(), worker="baska:2"))
    jobs._sweep()
    assert jobs.get(job["id"])["status"] == "RUNNING"


def test_stopping_the_runner_puts_its_jobs_back_not_out(gate_engine, model):
    model.hold = threading.Event()
    jobs = _jobs(gate_engine, model, slots=1)
    job = jobs.submit(MSG, module="m")
    deadline = time.monotonic() + 5
    while model.now == 0 and time.monotonic() < deadline:
        time.sleep(0.02)
    jobs.stop()
    deadline = time.monotonic() + 5
    while jobs.get(job["id"])["status"] != "QUEUED" and time.monotonic() < deadline:
        time.sleep(0.05)
    view = jobs.get(job["id"])
    assert view["status"] == "QUEUED" and view["attempts"] == 0, view
    model.hold.set()
    again = _jobs(gate_engine, model, slots=1)
    try:
        assert again.wait(job["id"], timeout=10)["status"] == "DONE"
    finally:
        again.stop()


def test_a_backlog_of_unattended_work_does_not_block_a_person(gate_engine, model):
    """Every general worker is busy with batch jobs that will not finish; the interactive-only worker
    is still free, and the model has a slot for it."""
    model.hold = threading.Event()
    jobs = _jobs(gate_engine, model, slots=3, workers=2, interactive_workers=1)
    try:
        for i in range(6):
            jobs.submit([{"role": "user", "content": f"toplu-{i}"}], module="gece", priority=BATCH)
        deadline = time.monotonic() + 5
        while model.now < 2 and time.monotonic() < deadline:
            time.sleep(0.02)
        person = jobs.submit([{"role": "user", "content": "insan"}], module="sohbet", priority=INTERACTIVE)
        assert person["position"] == 1, "a person's job is first in line whatever arrived before it"
        deadline = time.monotonic() + 5
        while "insan" not in model.calls and time.monotonic() < deadline:
            time.sleep(0.02)
        assert "insan" in model.calls, "the person's job waited behind the batch backlog"
    finally:
        model.hold.set()
        jobs.stop()


def test_modules_take_turns_at_the_door_too(gate_engine, model):
    model.delay = 0.1
    jobs = _jobs(gate_engine, model, slots=1, workers=1, interactive_workers=0, start=False)
    for i in range(6):
        jobs.submit([{"role": "user", "content": f"kalabalik-{i}"}], module="kalabalik")
    jobs.submit([{"role": "user", "content": "rapor-0"}], module="rapor")
    last = jobs.submit([{"role": "user", "content": "uyari-0"}], module="uyari")
    jobs.start()
    try:
        assert jobs.wait(last["id"], timeout=20)["status"] == "DONE"
        # one worker: nothing of `kalabalik` is running when the next is picked, so the door is
        # first-come; the turn-taking that matters then happens in the model's line (test_llm_gate).
        assert model.calls.index("uyari-0") <= 7
    finally:
        jobs.stop()


def test_many_modules_submitting_at_once(gate_engine, model):
    """Twelve modules, ten prompts each, all at the same moment: every one accepted immediately,
    every one answered exactly once, the model never over its slots."""
    model.delay = 0.02
    jobs = _jobs(gate_engine, model, slots=4, workers=6, interactive_workers=2)
    accepted: dict[str, float] = {}
    lock = threading.Lock()

    def module(m):
        for i in range(10):
            t0 = time.monotonic()
            job = jobs.submit([{"role": "user", "content": f"m{m}-{i}"}], module=f"modul{m}", priority=m % 3, user_id=f"u{m}")
            with lock:
                accepted[job["id"]] = time.monotonic() - t0

    try:
        threads = [threading.Thread(target=module, args=(m,)) for m in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
        assert len(accepted) == 120
        assert max(accepted.values()) < 5, f"accepting a prompt took {max(accepted.values()):.1f}s"
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and jobs.stats()["queued"] + jobs.stats()["running"]:
            time.sleep(0.2)
        with gate_engine.connect() as conn:
            left = dict(conn.execute(sa.select(J.c.status, sa.func.count()).group_by(J.c.status)).fetchall())
        assert left == {"DONE": 120}, left
        assert sorted(model.calls) == sorted(f"m{m}-{i}" for m in range(12) for i in range(10)), "a prompt ran twice or never"
        assert model.peak <= 4, f"{model.peak} calls at once with 4 slots"
    finally:
        jobs.stop()


def test_two_runners_never_take_the_same_job(gate_engine, model):
    """Two bridge processes on one catalog database (uvicorn --workers 2): SKIP LOCKED on PostgreSQL,
    the status guard in the UPDATE everywhere."""
    model.delay = 0.02
    queue = LlmQueue(gate_engine, slots=4, reserve=0, poll_seconds=0.02)
    llm = QueuedLlm(model, queue)
    feeder = LlmJobs(gate_engine, lambda: llm)
    ids = [feeder.submit([{"role": "user", "content": f"is-{i}"}], module=f"m{i % 4}")["id"] for i in range(60)]
    runners = [LlmJobs(gate_engine, lambda: llm, workers=4, interactive_workers=0, worker=f"surec:{n}") for n in range(2)]
    for r in runners:
        r.IDLE_POLL_SEC = 0.02
        r.start()
    try:
        assert all(feeder.wait(i, timeout=60)["status"] == "DONE" for i in ids)
        assert sorted(model.calls) == sorted(f"is-{i}" for i in range(60)), "two runners ran the same job"
        with gate_engine.connect() as conn:
            workers = {w for (w,) in conn.execute(sa.select(J.c.worker).distinct())}
        assert workers == {"surec:0", "surec:1"}, workers
    finally:
        for r in runners:
            r.stop()


def test_a_job_says_which_wait_it_is_in(gate_engine, model):
    """RUNNING is two waits: in the model's line, and in the model. One slot, two jobs: the second has
    a runner but not the model."""
    model.hold = threading.Event()
    jobs = _jobs(gate_engine, model, slots=1, workers=2, interactive_workers=0)
    try:
        first = jobs.submit([{"role": "user", "content": "ilk"}], module="a")
        second = jobs.submit([{"role": "user", "content": "ikinci"}], module="b")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not (jobs.get(first["id"])["phase"] == "modelde" and jobs.get(second["id"])["status"] == "RUNNING"):
            time.sleep(0.02)
        assert first["phase"] == "kapıda"
        assert jobs.get(first["id"])["phase"] == "modelde" and jobs.get(first["id"])["admittedAt"]
        assert jobs.get(second["id"])["phase"] == "model sırasında" and jobs.get(second["id"])["admittedAt"] is None
        model.hold.set()
        done = jobs.wait(second["id"], timeout=10)
        assert done["status"] == "DONE" and done["phase"] is None and done["admittedAt"]
    finally:
        model.hold.set()
        jobs.stop()
