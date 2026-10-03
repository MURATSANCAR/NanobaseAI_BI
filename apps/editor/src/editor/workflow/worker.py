"""Temporal worker for the editor task queue. Applies DB migrations and makes
sure the `editor` namespace exists before polling."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import timedelta

from google.protobuf.duration_pb2 import Duration
from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest, RegisterNamespaceRequest
from temporalio import activity
from temporalio.client import Client
from temporalio.exceptions import ApplicationError
from temporalio.worker import ActivityInboundInterceptor, ExecuteActivityInput, Interceptor, Worker

from .. import db, foundation
from ..config import settings
from ..llm import ContextOverflow
from . import liveness
from .activities import ALL
from .workflows import BookFullAnalysis

log = logging.getLogger("editor.worker")

#: Liveness heartbeat period and the worker's heartbeat throttle (seconds).
PULSE_SECONDS = 5.0


class HeartbeatActivityInterceptor(ActivityInboundInterceptor):
    """Report worker liveness; retries still resume through durable DB checkpoints.

    This is not analytical progress. Start-to-close remains the execution limit.
    Older workflow activities without a heartbeat timeout remain unchanged.
    """

    async def execute_activity(self, input: ExecuteActivityInput):
        info = activity.info()
        if not info.heartbeat_timeout:
            return await self.next.execute_activity(input)
        # Short pulse (with the worker's 5 s throttle below): a stall of the shared loop costs the
        # heartbeat only the stall itself plus ~5 s, not stall + 20 s pulse + 20 s throttle
        # (2026-10-03: stalls of ~30 s were enough to pass the 60 s timeout).
        interval = min(PULSE_SECONDS, info.heartbeat_timeout.total_seconds() / 6)
        details = {"kind": "worker_liveness", "activity": info.activity_type, "attempt": info.attempt}
        token = liveness.DETAILS.set(details)       # the activity may add its progress (liveness.report)
        activity.heartbeat(dict(details))

        async def pulse() -> None:
            while True:
                await asyncio.sleep(interval)
                activity.heartbeat(dict(details))

        task = asyncio.create_task(pulse())
        try:
            return await self.next.execute_activity(input)
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            liveness.DETAILS.reset(token)


class LoopWatchdog:
    """Notices, from its own thread, when the worker's event loop stops turning.

    Every activity of this worker and every liveness heartbeat share one asyncio loop. The
    Temporal SDK sends heartbeats through that loop (payload conversion is async), so no
    thread can heartbeat on behalf of a blocked loop: the cure is keeping blocking work off
    it (asyncio.to_thread). This guard makes a regression visible instead of silent — when
    the loop has not turned for `threshold` seconds it logs the loop thread's current stack
    (the code that blocks), and when the loop resumes it logs how long the stall lasted.
    Measured 2026-10-02: stalls of 56-145 s made Temporal cancel healthy activities as
    "activity task timed out" (heartbeat timeout 60 s)."""

    def __init__(self, threshold: float | None = None, tick: float = 1.0) -> None:
        import os
        self.threshold = threshold if threshold is not None else \
            float(os.environ.get("EDITOR_LOOP_STALL_SECONDS", "") or 10)
        self.tick = tick
        self.last = 0.0
        self.stalls: list[float] = []
        self._loop_thread: int | None = None
        self._stop = None
        self._task: asyncio.Task | None = None

    async def _pulse(self) -> None:
        import time
        while True:
            self.last = time.monotonic()
            await asyncio.sleep(self.tick)

    def _watch(self) -> None:
        import sys
        import time
        import traceback
        reported = None
        while not self._stop.wait(self.tick / 2):
            gap = time.monotonic() - self.last
            if gap >= self.threshold and reported != self.last:
                reported = self.last
                frame = sys._current_frames().get(self._loop_thread)
                stack = "".join(traceback.format_stack(frame)) if frame else "(stack unavailable)"
                log.warning("event loop blocked for %.1f s; heartbeats are not being sent. "
                            "Blocking code:\n%s", gap, stack)
            elif reported is not None and reported != self.last:
                self.stalls.append(self.last - reported)
                log.warning("event loop resumed after a %.1f s stall", self.last - reported)
                reported = None

    def start(self) -> None:
        import threading
        import time
        self._loop_thread = threading.get_ident()
        self.last = time.monotonic()
        self._stop = threading.Event()
        self._task = asyncio.get_running_loop().create_task(self._pulse())
        threading.Thread(target=self._watch, name="loop-watchdog", daemon=True).start()

    def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()
        if self._task is not None:
            self._task.cancel()


class DeterministicFailureInterceptor(ActivityInboundInterceptor):
    """A request that cannot fit the model's context fails identically on every attempt:
    it ends the activity at once instead of spending the retry policy (4 attempts x 3 calls,
    measured 2026-09-23). Lives here, not in the workflow's RetryPolicy, so running
    workflows replay unchanged."""

    async def execute_activity(self, input: ExecuteActivityInput):
        try:
            return await self.next.execute_activity(input)
        except Exception as e:
            cause: BaseException | None = e
            seen: set[int] = set()
            while cause is not None and not isinstance(cause, ContextOverflow) and id(cause) not in seen:
                seen.add(id(cause))
                cause = cause.__cause__ or cause.__context__
            if cause is not None and not isinstance(cause, ContextOverflow):
                cause = None
            if cause is None:
                raise
            raise ApplicationError(str(cause)[:2000], type="ContextOverflow", non_retryable=True) from e


class HeartbeatInterceptor(Interceptor):
    def intercept_activity(self, next: ActivityInboundInterceptor) -> ActivityInboundInterceptor:
        return HeartbeatActivityInterceptor(DeterministicFailureInterceptor(next))


async def ensure_namespace(address: str, namespace: str) -> None:
    c = await Client.connect(address, namespace="default")
    try:
        await c.workflow_service.describe_namespace(DescribeNamespaceRequest(namespace=namespace))
    except Exception:  # noqa: BLE001 - NotFound
        await c.workflow_service.register_namespace(RegisterNamespaceRequest(
            namespace=namespace, workflow_execution_retention_period=Duration(seconds=90 * 86400)))
        log.info("registered namespace %s", namespace)
        await asyncio.sleep(12)  # namespace cache refresh


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    s = settings()
    log.info("migrations: %s", await asyncio.to_thread(db.migrate) or "up to date")
    # A restart must not resume the old workflow while foundation work is paused.
    await asyncio.to_thread(foundation.assert_enabled)
    await ensure_namespace(s.temporal_address, s.temporal_namespace)
    client = await Client.connect(s.temporal_address, namespace=s.temporal_namespace)
    worker = Worker(client, task_queue=s.task_queue, workflows=[BookFullAnalysis], activities=ALL,
                    max_concurrent_activities=48, interceptors=[HeartbeatInterceptor()],
                    max_heartbeat_throttle_interval=timedelta(seconds=PULSE_SECONDS),
                    default_heartbeat_throttle_interval=timedelta(seconds=PULSE_SECONDS))
    log.info("worker polling %s/%s", s.temporal_namespace, s.task_queue)
    watchdog = LoopWatchdog()
    watchdog.start()
    try:
        await worker.run()
    finally:
        watchdog.stop()


if __name__ == "__main__":
    asyncio.run(main())
