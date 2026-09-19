"""Prompts left at the door.

A module that needs the model has two ways in. Code that lives in the same process wraps its calls in
`QueuedLlm` and blocks until the answer is there. Everything else — another service, a browser, a
module that must not hold a connection open for the fifteen minutes a hosted queue can take — leaves
the prompt here, gets an id back at once, and asks for the answer later.

* the job is a row in the catalog database before the caller hears "accepted": a restart loses nothing;
* a runner inside the bridge takes jobs in priority order, fairly between modules, and runs each one
  through the same `LlmQueue` as every other call — there is still exactly one line for the model;
* some runner threads only ever take priority-0 jobs, so a backlog of unattended work cannot occupy
  every thread while a person waits;
* a job whose runner died (no heartbeat) goes back in line; three deaths and it is failed out loud;
* the same prompt from the same user and module, while the first is still in flight, is the same job.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_layer.models import new_id
from semantic_layer.runtime.llm_queue import BATCH, INTERACTIVE, NORMAL, LeaseCancelled, clean_module
from semantic_layer.store import schema as S

log = logging.getLogger(__name__)

J = S.sl_llm_job
OPEN = ("QUEUED", "RUNNING")
CLOSED = ("DONE", "FAILED", "CANCELLED")
PRIORITY_NAMES = {"interactive": INTERACTIVE, "normal": NORMAL, "batch": BATCH}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return None


def _iso(value: Any) -> Optional[str]:
    value = _aware(value)
    return value.isoformat() if value else None


def parse_priority(value: Any) -> int:
    if value is None or value == "":
        return NORMAL
    if isinstance(value, str) and value.strip().lower() in PRIORITY_NAMES:
        return PRIORITY_NAMES[value.strip().lower()]
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError("priority: interactive | normal | batch (ya da 0 | 1 | 2)") from None
    if number not in (INTERACTIVE, NORMAL, BATCH):
        raise ValueError("priority: interactive | normal | batch (ya da 0 | 1 | 2)")
    return number


def validate_messages(messages: Any) -> list[dict[str, str]]:
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages: en az bir mesaj gerekli")
    out = []
    for m in messages:
        if not isinstance(m, dict) or m.get("role") not in ("system", "user", "assistant") or not isinstance(m.get("content"), str):
            raise ValueError("messages: her öğe {role: system|user|assistant, content: metin} olmalı")
        out.append({"role": m["role"], "content": m["content"]})
    return out


class LlmJobs:
    """Submit, read, cancel — and the runner that works the line."""

    HEARTBEAT_SEC = 5
    STALE_AFTER_SEC = 60
    MAX_ATTEMPTS = 3
    IDLE_POLL_SEC = 1.0

    def __init__(self, engine: sa.Engine, get_llm: Callable[[], Any], *, tenant_id: str = "default", datasource_id: str = "default",
                 workers: int = 4, interactive_workers: int = 1, keep_days: int = 0, worker: Optional[str] = None):
        self.engine = engine
        self.get_llm = get_llm                      # the bridge swaps its client when settings change
        self.tenant_id = tenant_id
        self.datasource_id = datasource_id
        self.workers = max(1, workers)
        self.interactive_workers = max(0, interactive_workers)
        #: closed jobs older than this are removed; 0 keeps everything (nothing is deleted unasked)
        self.keep_days = max(0, keep_days)
        self.worker = worker or f"{socket.gethostname()}:{os.getpid()}"
        self._pg = engine.dialect.name == "postgresql"
        self._lock = threading.Lock()
        self._free_any = self.workers
        self._free_interactive = self.interactive_workers
        self._active: dict[str, threading.Event] = {}        # job id → cancel flag, for jobs running here
        self._done: dict[str, threading.Event] = {}          # job id → set when it closes, for waiters here
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._pool: Optional[ThreadPoolExecutor] = None

    @classmethod
    def from_env(cls, engine: sa.Engine, get_llm: Callable[[], Any], *, slots: int, tenant_id: str, datasource_id: str) -> "LlmJobs":
        # More threads than slots on purpose: the extra ones stand in the model's line, where the
        # queue's own fairness decides — a job held back here is invisible to it.
        workers = int(os.environ.get("SEMANTIC_LLM_JOB_WORKERS", "") or slots + 2)
        interactive = int(os.environ.get("SEMANTIC_LLM_JOB_INTERACTIVE_WORKERS", "") or max(1, slots // 4))
        return cls(engine, get_llm, tenant_id=tenant_id, datasource_id=datasource_id, workers=workers,
                   interactive_workers=interactive, keep_days=int(os.environ.get("SEMANTIC_LLM_JOB_KEEP_DAYS", "0")))

    # ------------------------------------------------------------------ submit / read / cancel
    def submit(self, messages: list[dict[str, str]], *, module: str, priority: Any = NORMAL, user_id: Optional[str] = None,
               max_tokens: int = 4096, temperature: float = 0.0, dedup: bool = True, cache_ttl_sec: int = 0) -> dict[str, Any]:
        messages = validate_messages(messages)
        module = clean_module(module)
        priority = parse_priority(priority)
        params = {"max_tokens": int(max_tokens), "temperature": float(temperature)}
        model = str(getattr(self.get_llm(), "model", "") or "")
        # The user and the module are part of the key: two people asking the same thing are two
        # jobs, because only the one who asked may read the answer.
        key = hashlib.sha256(json.dumps([self.tenant_id, user_id or "", module, model, messages, params],
                                        ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        with self.engine.begin() as conn:
            if self._pg:                                  # two identical submits at once must see each other
                conn.execute(sa.text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": "sl_llm_job:" + key})
            if dedup:
                same = conn.execute(sa.select(J).where(J.c.dedup_key == key, J.c.status.in_(OPEN)).order_by(J.c.created_at).limit(1)).first()
                if same is None and cache_ttl_sec > 0:
                    same = conn.execute(sa.select(J).where(J.c.dedup_key == key, J.c.status == "DONE",
                                                           J.c.finished_at >= _now() - timedelta(seconds=int(cache_ttl_sec)))
                                        .order_by(J.c.finished_at.desc()).limit(1)).first()
                if same is not None:
                    return self._view(dict(same._mapping), conn) | {"deduplicated": True}
            job_id = new_id("llmjob")
            conn.execute(J.insert().values(
                id=job_id, tenant_id=self.tenant_id, datasource_id=self.datasource_id, module=module, priority=priority,
                user_id=user_id, status="QUEUED", messages_json=json.dumps(messages, ensure_ascii=False),
                params_json=json.dumps(params), dedup_key=key, attempts=0, created_at=_now()))
            row = conn.execute(sa.select(J).where(J.c.id == job_id)).first()
            view = self._view(dict(row._mapping), conn) | {"deduplicated": False}
        self._wake.set()
        return view

    def get(self, job_id: str) -> Optional[dict[str, Any]]:
        with self.engine.connect() as conn:
            row = conn.execute(sa.select(J).where(J.c.id == job_id, J.c.tenant_id == self.tenant_id)).first()
            return self._view(dict(row._mapping), conn) if row is not None else None

    def owner(self, job_id: str) -> tuple[bool, Optional[str]]:
        with self.engine.connect() as conn:
            row = conn.execute(sa.select(J.c.user_id).where(J.c.id == job_id, J.c.tenant_id == self.tenant_id)).first()
        return (row is not None, row[0] if row is not None else None)

    def cancel(self, job_id: str) -> Optional[dict[str, Any]]:
        with self.engine.begin() as conn:
            conn.execute(J.update().where(J.c.id == job_id, J.c.tenant_id == self.tenant_id, J.c.status.in_(OPEN))
                         .values(status="CANCELLED", finished_at=_now(), error="İptal edildi."))
        flag = self._active.get(job_id)
        if flag is not None:
            flag.set()                                     # running here: stop waiting / drop the call now
        self._closed(job_id)
        return self.get(job_id)

    def wait(self, job_id: str, timeout: Optional[float] = None) -> Optional[dict[str, Any]]:
        """Block until the job closes (or `timeout` seconds pass) and return it as it then stands."""
        deadline = None if timeout is None else time.monotonic() + timeout
        done = self._done.setdefault(job_id, threading.Event())
        poll = 0.25
        try:
            while True:
                view = self.get(job_id)
                if view is None or view["status"] in CLOSED:
                    return view
                left = None if deadline is None else deadline - time.monotonic()
                if left is not None and left <= 0:
                    return view
                done.wait(poll if left is None else min(poll, left))
                poll = min(poll * 1.5, 2.0)
        finally:
            self._done.pop(job_id, None)

    def stats(self) -> dict[str, Any]:
        with self.engine.connect() as conn:
            rows = conn.execute(sa.select(J.c.module, J.c.status, sa.func.count()).where(J.c.tenant_id == self.tenant_id, J.c.status.in_(OPEN))
                                .group_by(J.c.module, J.c.status)).fetchall()
        modules: dict[str, dict[str, int]] = {}
        for module, status, n in rows:
            modules.setdefault(module, {"queued": 0, "running": 0})["queued" if status == "QUEUED" else "running"] += int(n)
        return {"workers": self.workers, "interactiveOnlyWorkers": self.interactive_workers,
                "queued": sum(m["queued"] for m in modules.values()), "running": sum(m["running"] for m in modules.values()),
                "modules": modules, "runnerAlive": any(t.is_alive() for t in self._threads)}

    def _view(self, r: dict[str, Any], conn: sa.Connection) -> dict[str, Any]:
        position = None
        if r["status"] == "QUEUED":
            position = 1 + int(conn.execute(sa.select(sa.func.count()).select_from(J).where(
                J.c.tenant_id == r["tenant_id"], J.c.status == "QUEUED",
                sa.or_(J.c.priority < r["priority"], sa.and_(J.c.priority == r["priority"], J.c.created_at < r["created_at"])))).scalar() or 0)
        # RUNNING covers two different waits; the caller is told which one it is in.
        phase = {"QUEUED": "kapıda"}.get(r["status"]) or ("modelde" if r.get("admitted_at") else "model sırasında") if r["status"] in OPEN else None
        return {
            "id": r["id"], "status": r["status"], "phase": phase, "module": r["module"], "priority": r["priority"], "position": position,
            "attempts": r["attempts"], "result": r["result"] if r["status"] == "DONE" else None,
            "error": r["error"] if r["status"] in ("FAILED", "CANCELLED") else None,
            "createdAt": _iso(r["created_at"]), "startedAt": _iso(r["started_at"]), "admittedAt": _iso(r.get("admitted_at")), "finishedAt": _iso(r["finished_at"]),
            "queueWaitMs": r["queue_wait_ms"], "llmMs": r["llm_ms"],
        }

    # ------------------------------------------------------------------ runner
    def start(self) -> None:
        if self._threads:
            return
        self._stop.clear()
        self._pool = ThreadPoolExecutor(max_workers=self.workers + self.interactive_workers, thread_name_prefix="llm-job")
        for target, name in ((self._dispatch_loop, "llm-jobs-dispatch"), (self._heartbeat_loop, "llm-jobs-heartbeat")):
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self._threads.append(t)
        log.info("llm jobs: runner started (%d workers + %d interactive-only)", self.workers, self.interactive_workers)

    def stop(self) -> None:
        """Jobs running here go back in line untouched; the next runner picks them up."""
        self._stop.set()
        self._wake.set()
        for flag in list(self._active.values()):
            flag.set()
        for t in self._threads:
            t.join(timeout=5)
        self._threads = []
        if self._pool is not None:
            self._pool.shutdown(wait=False)

    def _dispatch_loop(self) -> None:
        last_sweep = 0.0
        while not self._stop.is_set():
            try:
                if time.monotonic() - last_sweep > 15:
                    last_sweep = time.monotonic()
                    self._sweep()
                with self._lock:
                    lane = "any" if self._free_any > 0 else "interactive" if self._free_interactive > 0 else None
                job = self._claim(interactive_only=(lane == "interactive")) if lane else None
                if job is None:
                    self._wake.wait(self.IDLE_POLL_SEC)
                    self._wake.clear()
                    continue
                with self._lock:
                    if lane == "any":
                        self._free_any -= 1
                    else:
                        self._free_interactive -= 1
                self._active[job["id"]] = threading.Event()
                self._pool.submit(self._run, job, lane)
            except Exception:  # noqa: BLE001
                log.exception("llm jobs: dispatch failed; retrying")
                self._stop.wait(2)

    def _claim(self, *, interactive_only: bool) -> Optional[dict[str, Any]]:
        """Highest priority first; within it the module with the fewest running jobs, then the oldest."""
        busy = sa.select(J.c.module.label("m"), sa.func.count().label("n")).where(J.c.status == "RUNNING").group_by(J.c.module).subquery()
        pick = (sa.select(J.c.id).select_from(J.outerjoin(busy, busy.c.m == J.c.module))
                .where(J.c.status == "QUEUED", J.c.tenant_id == self.tenant_id)
                .order_by(J.c.priority, sa.func.coalesce(busy.c.n, 0), J.c.created_at, J.c.id).limit(1))
        if interactive_only:
            pick = pick.where(J.c.priority == INTERACTIVE)
        if self._pg:
            pick = pick.with_for_update(skip_locked=True, of=J)
        with self.engine.begin() as conn:
            job_id = conn.execute(pick).scalar()
            if job_id is None:
                return None
            taken = conn.execute(J.update().where(J.c.id == job_id, J.c.status == "QUEUED").values(
                status="RUNNING", started_at=_now(), heartbeat_at=_now(), worker=self.worker, attempts=J.c.attempts + 1))
            if not taken.rowcount:
                return None
            return dict(conn.execute(sa.select(J).where(J.c.id == job_id)).first()._mapping)

    def _run(self, job: dict[str, Any], lane: str) -> None:
        job_id = job["id"]
        cancel = self._active[job_id]
        started = time.perf_counter()
        try:
            llm = self.get_llm()
            if llm is None:
                raise RuntimeError("Model tanımlı değil (LLM kapalı).")
            client = llm.for_module(job["module"], priority=int(job["priority"])) if hasattr(llm, "for_module") else llm
            params = json.loads(job["params_json"] or "{}")
            kwargs: dict[str, Any] = {"max_tokens": int(params.get("max_tokens", 4096)), "temperature": float(params.get("temperature", 0.0)), "cancel": cancel}
            if hasattr(llm, "for_module"):
                kwargs["on_admitted"] = lambda _ticket: self._admitted(job_id)
            if job.get("user_id") and hasattr(llm, "for_module"):
                kwargs["user_id"] = job["user_id"]            # the queue shows who is waiting
            if not hasattr(llm, "for_module") and not getattr(llm, "supports_cancel", False):
                kwargs.pop("cancel")
            text = client.chat(json.loads(job["messages_json"]), **kwargs)
            waited = int(getattr(client, "last_wait_ms", 0) or 0)
            total = int((time.perf_counter() - started) * 1000)
            self._close(job_id, status="DONE", result=text, queue_wait_ms=waited, llm_ms=max(0, total - waited))
        except TimeoutError:
            # Unattended work that gave its place up after the queue's wait limit: not its fault.
            self._requeue(job_id, forgive=True)
        except Exception as e:  # noqa: BLE001
            if cancel.is_set() or isinstance(e, LeaseCancelled) or type(e).__name__ == "LlmCancelled":
                if self._stop.is_set():
                    self._requeue(job_id, forgive=True)   # the runner is going down, the job is not cancelled
            else:
                log.warning("llm job %s (%s) failed: %s", job_id, job["module"], e)
                self._close(job_id, status="FAILED", error=f"{type(e).__name__}: {e}"[:2000])
        finally:
            self._active.pop(job_id, None)
            with self._lock:
                if lane == "any":
                    self._free_any += 1
                else:
                    self._free_interactive += 1
            self._closed(job_id)
            self._wake.set()

    def _admitted(self, job_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(J.update().where(J.c.id == job_id, J.c.status == "RUNNING").values(admitted_at=_now()))

    def _close(self, job_id: str, **values: Any) -> None:
        with self.engine.begin() as conn:                  # never over a cancellation that got there first
            conn.execute(J.update().where(J.c.id == job_id, J.c.status == "RUNNING").values(finished_at=_now(), **values))

    def _requeue(self, job_id: str, *, forgive: bool = False) -> None:
        values: dict[str, Any] = {"status": "QUEUED", "started_at": None, "admitted_at": None, "heartbeat_at": None, "worker": None}
        if forgive:
            values["attempts"] = sa.case((J.c.attempts > 0, J.c.attempts - 1), else_=0)
        with self.engine.begin() as conn:
            conn.execute(J.update().where(J.c.id == job_id, J.c.status == "RUNNING").values(**values))

    def _closed(self, job_id: str) -> None:
        done = self._done.get(job_id)
        if done is not None:
            done.set()

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(self.HEARTBEAT_SEC):
            ids = list(self._active)
            if not ids:
                continue
            try:
                with self.engine.begin() as conn:
                    conn.execute(J.update().where(J.c.id.in_(ids), J.c.status == "RUNNING").values(heartbeat_at=_now()))
                    # cancelled through another process (or straight in the table): stop the call here
                    gone = [r[0] for r in conn.execute(sa.select(J.c.id).where(J.c.id.in_(ids), J.c.status != "RUNNING"))]
                for job_id in gone:
                    flag = self._active.get(job_id)
                    if flag is not None:
                        flag.set()
            except Exception as e:  # noqa: BLE001
                log.warning("llm jobs: heartbeat failed: %s", e)

    def _sweep(self) -> None:
        """Jobs whose runner stopped beating go back in line; after MAX_ATTEMPTS they fail out loud."""
        cutoff = _now() - timedelta(seconds=self.STALE_AFTER_SEC)
        stale = sa.and_(J.c.status == "RUNNING", sa.or_(J.c.heartbeat_at.is_(None), J.c.heartbeat_at < cutoff))
        mine = list(self._active)
        if mine:
            stale = sa.and_(stale, J.c.id.notin_(mine))
        with self.engine.begin() as conn:
            failed = conn.execute(J.update().where(stale, J.c.attempts >= self.MAX_ATTEMPTS).values(
                status="FAILED", finished_at=_now(), error=f"İşleyici {self.MAX_ATTEMPTS} kez yanıt vermeden kayboldu.")).rowcount
            back = conn.execute(J.update().where(stale).values(status="QUEUED", started_at=None, admitted_at=None, heartbeat_at=None, worker=None)).rowcount
            purged = 0
            if self.keep_days:
                purged = conn.execute(J.delete().where(J.c.status.in_(CLOSED), J.c.finished_at < _now() - timedelta(days=self.keep_days))).rowcount
        if failed or back or purged:
            log.info("llm jobs: sweep — %d back in line, %d failed after %d attempts, %d old rows removed", back, failed, self.MAX_ATTEMPTS, purged)
