"""Run a coroutine on its own event loop, in its own thread.

Every activity of the editor worker and every liveness heartbeat share one asyncio loop, and the
Temporal SDK can only send a heartbeat when that loop turns. Synchronous work inside an async step
(a database transaction, a page render, a regex pass over the whole book, a numpy contrast
measurement) stops the loop: measured 2026-10-03 on the GPU worker, stalls of 14-34 s in
proofreading (layout._pix, series_canon._latest_generation), visual identity (embed_figures),
book metadata (source.load) and page scans (source.read). Two such stalls back to back exceed the
60 s heartbeat timeout and Temporal kills a healthy activity — of this book or of any other book
read at the same time. Final-read checks failed that way on 13 of the full readings of 01-03.10.

`run(fn, *args)` gives such a step its own loop on its own thread: whatever it blocks, it blocks
only itself. Context variables (Temporal's activity context, db.validation_token) are copied in.
Cancelling the awaiting task cancels the inner task and waits for it to unwind (a cancelled
activity must not keep writing behind the retry's back).

The model client is per loop (editor.llm.client); it is closed when the inner loop ends.
"""

from __future__ import annotations

import asyncio
import collections
import contextvars
import threading
from typing import Any, Awaitable, Callable

#: How long a cancelled call waits for the inner coroutine to unwind before giving up on it.
CANCEL_GRACE_SECONDS = 30.0


def _deliver(fut: asyncio.Future, value: Any, exc: BaseException | None) -> None:
    if fut.done():
        return
    if exc is None:
        fut.set_result(value)
    elif isinstance(exc, asyncio.CancelledError):
        fut.cancel()
    elif isinstance(exc, Exception):
        fut.set_exception(exc)
    else:                       # KeyboardInterrupt / SystemExit inside the thread
        fut.set_exception(RuntimeError(f"{type(exc).__name__}: {exc}"))


async def _close_loop_resources() -> None:
    from . import llm
    try:
        await llm.close_client()
    except Exception:  # noqa: BLE001 - closing must never mask the step's own result
        pass
    import sys
    retrieval = sys.modules.get(f"{__package__}.retrieval")   # only if the step used it
    if retrieval is not None:
        try:
            await retrieval.close_qdrant()
        except Exception:  # noqa: BLE001
            pass


class SharedSemaphore:
    """An asyncio semaphore every event loop of the process can share (asyncio.Semaphore belongs to one loop).

    Steps run on their own loops (`run`), yet some limits are the process's, not a loop's: the director model
    serves N requests at once for every book this worker reads (knowledge.director_slots). Waiters are served
    in arrival order; a slot handed to a waiter that was cancelled meanwhile is passed on, never lost."""

    def __init__(self, value: int) -> None:
        self._lock = threading.Lock()
        self._value = value
        self._waiters: collections.deque = collections.deque()

    @property
    def value(self) -> int:
        return self._value

    def locked(self) -> bool:
        return self._value <= 0

    async def acquire(self) -> bool:
        loop = asyncio.get_running_loop()
        with self._lock:
            if self._value > 0 and not self._waiters:
                self._value -= 1
                return True
            fut = loop.create_future()
            entry = (loop, fut)
            self._waiters.append(entry)
        try:
            await fut
        except asyncio.CancelledError:
            with self._lock:
                try:
                    self._waiters.remove(entry)
                    handed = False
                except ValueError:
                    handed = True                # a release already gave this waiter the slot
            if handed:
                self.release()
            raise
        return True

    def release(self) -> None:
        with self._lock:
            while self._waiters:
                loop, fut = self._waiters.popleft()
                try:
                    loop.call_soon_threadsafe(_wake, fut)
                    return
                except RuntimeError:             # that loop is closed: its waiter is gone
                    continue
            self._value += 1

    async def __aenter__(self) -> None:
        await self.acquire()

    async def __aexit__(self, *exc: Any) -> None:
        self.release()


def _wake(fut: asyncio.Future) -> None:
    if not fut.done():
        fut.set_result(True)
    # a cancelled waiter returns the slot itself (SharedSemaphore.acquire)


async def run(fn: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any) -> Any:
    """Await `fn(*args, **kwargs)` executed on a fresh event loop in a dedicated thread."""
    outer = asyncio.get_running_loop()
    result: asyncio.Future = outer.create_future()
    inner: dict[str, Any] = {"cancel": False}

    async def body():
        inner["loop"] = asyncio.get_running_loop()
        inner["task"] = asyncio.current_task()
        if inner["cancel"]:
            raise asyncio.CancelledError()
        try:
            return await fn(*args, **kwargs)
        finally:
            await _close_loop_resources()

    def thread_main() -> None:
        try:
            value = asyncio.run(body())
        except BaseException as e:  # noqa: BLE001 - handed to the awaiting loop
            try:
                outer.call_soon_threadsafe(_deliver, result, None, e)
            except RuntimeError:     # the outer loop is gone (process shutting down)
                pass
        else:
            try:
                outer.call_soon_threadsafe(_deliver, result, value, None)
            except RuntimeError:
                pass

    ctx = contextvars.copy_context()
    name = f"offloop-{getattr(fn, '__name__', 'step')}"
    threading.Thread(target=ctx.run, args=(thread_main,), name=name, daemon=True).start()
    try:
        return await asyncio.shield(result)
    except asyncio.CancelledError:
        inner["cancel"] = True
        loop, task = inner.get("loop"), inner.get("task")
        if loop is not None and task is not None:
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:     # inner loop already closed: nothing left to cancel
                pass
        try:
            await asyncio.wait_for(asyncio.shield(result), CANCEL_GRACE_SECONDS)
        except BaseException:  # noqa: BLE001 - the cancellation below is what the caller sees
            pass
        raise
