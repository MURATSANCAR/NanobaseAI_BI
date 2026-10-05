"""PDF CPU work of the reading worker in a small pool of separate processes.

Measured 2026-10-05 02:23–02:33 on the GPU worker: the worker's event loop stood still for 81–93 s and every
activity running at that moment lost its heartbeat (60 s) at once — five readings used up their four attempts in
~9 minutes. The cause was the GIL, not the loop's own code: `asyncio.to_thread` and `editor.offloop` are threads of
the same process, and PyMuPDF holds the GIL for the whole of a page render (a C call the 5 ms switch interval cannot
interrupt), while `nontext_ink_ratio` counted pixels in a pure Python loop. The page manifest rendered every page of
a book that way, cancelled attempts left their threads running underneath the retry, and the worker had 399 threads
(3.967 s CPU in to_thread threads against ~350 s for the loop).

Here that work runs in other processes, so it never competes for the worker's GIL:

- `configure()` (the worker calls it at start) turns the pool on: EDITOR_PDF_PROCS processes (default 4), fixed
  size, started on demand. Without it (CLI, card service, tests) every call runs in-process as before.
- Inputs and outputs are plain data: a file path and page numbers in, bytes / numbers / text out.
- `run(fn, *args)` awaits one task, `map_pages(fn, path, pages, *args)` splits pages into chunks of
  EDITOR_PDF_CHUNK pages and keeps at most `procs` chunks of one caller in the pool at a time, so several books
  share it in turn. Cancelling the caller (a cancelled Temporal attempt) cancels its chunks that have not started;
  a started chunk is a few pages and ends on its own — no pile-up of abandoned work under the retry.
- A task that does not finish in EDITOR_PDF_TASK_SECONDS (default 600) is a hung process: the pool is replaced,
  its processes are killed, and the calls that lost their task to the replacement are submitted once more.
- `run_sync(fn, *args)` is the same for synchronous code running in a thread (render_page from vision, proofing).

Inside a pool process documents are kept open per path (`open_doc`), so a chunk does not parse the PDF again.
"""

from __future__ import annotations

import asyncio
import concurrent.futures as cf
import multiprocessing as mp
import os
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Iterable

_lock = threading.Lock()
_procs = 0                                # 0: in-process (not configured, or inside a pool process)
_pool: cf.ProcessPoolExecutor | None = None
_IN_CHILD = False

#: Open documents kept by one pool process (path, repair, mtime, size) → document.
_DOCS: OrderedDict = OrderedDict()
_DOCS_KEPT = 3


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def chunk_pages() -> int:
    return max(1, _env_int("EDITOR_PDF_CHUNK", 4))


def task_seconds() -> float:
    return float(max(1, _env_int("EDITOR_PDF_TASK_SECONDS", 600)))


def configure(procs: int | None = None) -> int:
    """Turn the process pool on (`procs` > 0) or off (0). Returns the pool size."""
    global _procs
    n = _env_int("EDITOR_PDF_PROCS", 4) if procs is None else int(procs)
    with _lock:
        old = _pool if n != _procs else None
        _procs = max(0, n)
    if old is not None:
        _replace(old, kill=False)
    return _procs


def active() -> bool:
    return _procs > 0 and not _IN_CHILD


def _child_init() -> None:
    global _IN_CHILD, _procs
    _IN_CHILD = True
    _procs = 0
    os.environ["EDITOR_PDF_CHILD"] = "1"
    import signal
    signal.signal(signal.SIGINT, signal.SIG_IGN)   # the worker's Ctrl-C / stop is the parent's to handle


def _context():
    methods = mp.get_all_start_methods()
    if "forkserver" in methods:
        ctx = mp.get_context("forkserver")
        # the server imports these once; every pool process is forked from it with them loaded
        ctx.set_forkserver_preload(["editor.pdfproc", "pymupdf", "numpy"])
        return ctx
    return mp.get_context("spawn")


def pool() -> cf.ProcessPoolExecutor:
    global _pool
    with _lock:
        if _pool is None:
            _pool = cf.ProcessPoolExecutor(max_workers=_procs, mp_context=_context(), initializer=_child_init,
                                           max_tasks_per_child=500)
        return _pool


def _replace(old: cf.ProcessPoolExecutor | None, kill: bool = True) -> None:
    """Drop `old` (if it is still the current pool); with `kill` its processes are ended at once."""
    global _pool
    with _lock:
        if old is None or _pool is not old:
            return
        _pool = None
    procs = list(getattr(old, "_processes", {}).values()) if kill else []
    for p in procs:
        try:
            p.kill()
        except Exception:  # noqa: BLE001 - already gone
            pass
    old.shutdown(wait=False, cancel_futures=True)


def shutdown() -> None:
    _replace(_pool, kill=False)


# ------------------------------------------------------------------ calling
async def run(fn: Callable[..., Any], *args: Any) -> Any:
    """Await `fn(*args)` in a pool process (in a thread of this process when the pool is off)."""
    if not active():
        return await asyncio.to_thread(fn, *args)
    for attempt in (1, 2):
        p = pool()
        fut = p.submit(fn, *args)
        try:
            return await asyncio.wait_for(asyncio.wrap_future(fut), task_seconds())
        except asyncio.TimeoutError:
            _replace(p)
            raise TimeoutError(f"{getattr(fn, '__name__', 'pdf task')}: no result in {task_seconds():.0f} s; "
                               "the PDF process was stopped") from None
        except cf.process.BrokenProcessPool:
            _replace(p, kill=False)
            if attempt == 2:
                raise
        except asyncio.CancelledError:
            fut.cancel()                       # not started yet: it never runs
            raise
    raise AssertionError("unreachable")


def run_sync(fn: Callable[..., Any], *args: Any) -> Any:
    """`run` for synchronous code (a thread, an own loop): blocks only its caller."""
    if not active():
        return fn(*args)
    for attempt in (1, 2):
        p = pool()
        fut = p.submit(fn, *args)
        try:
            return fut.result(timeout=task_seconds())
        except cf.TimeoutError:
            fut.cancel()
            _replace(p)
            raise TimeoutError(f"{getattr(fn, '__name__', 'pdf task')}: no result in {task_seconds():.0f} s; "
                               "the PDF process was stopped") from None
        except cf.process.BrokenProcessPool:
            _replace(p, kill=False)
            if attempt == 2:
                raise
    raise AssertionError("unreachable")


def chunks(pages: Iterable[int], size: int | None = None) -> list[list[int]]:
    pages = list(pages)
    size = size or chunk_pages()
    return [pages[i:i + size] for i in range(0, len(pages), size)]


async def map_pages(fn: Callable[..., list], path: str, pages: Iterable[int], *args: Any) -> list:
    """`fn(path, chunk, *args)` over chunks of `pages`, results concatenated in page order. At most `procs`
    chunks of this call are in the pool at once (other callers' chunks take turns between them)."""
    parts = chunks(pages)
    if not active():
        return await asyncio.to_thread(lambda: [x for c in parts for x in fn(path, c, *args)])
    window = max(1, _procs)
    out: list = [None] * len(parts)
    running: dict[asyncio.Task, int] = {}
    nxt = 0
    try:
        while nxt < len(parts) or running:
            while nxt < len(parts) and len(running) < window:
                running[asyncio.ensure_future(run(fn, path, parts[nxt], *args))] = nxt
                nxt += 1
            done, _ = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                out[running.pop(t)] = t.result()
    finally:
        for t in running:
            t.cancel()
        if running:
            await asyncio.gather(*running, return_exceptions=True)
    return [x for part in out for x in part]


# ------------------------------------------------------------------ inside a pool process
def open_doc(path: str, repair: bool):
    """The document at `path` (repaired font mappings with `repair`, editor.pdf_repair). In a pool process it is
    kept open for the next chunk; elsewhere a fresh document every time (PyMuPDF documents are not thread-safe,
    and the worker's threads must not share one)."""
    import pymupdf
    if not _IN_CHILD:
        doc = pymupdf.open(path)
        if repair:
            from . import pdf_repair
            pdf_repair.repair_document(doc)
        return doc
    st = os.stat(path)
    key = (path, bool(repair), st.st_mtime_ns, st.st_size)
    doc = _DOCS.get(key)
    if doc is not None:
        _DOCS.move_to_end(key)
        return doc
    doc = pymupdf.open(path)
    if repair:
        from . import pdf_repair
        pdf_repair.repair_document(doc)
    _DOCS[key] = doc
    while len(_DOCS) > _DOCS_KEPT:
        _, old = _DOCS.popitem(last=False)
        try:
            old.close()
        except Exception:  # noqa: BLE001
            pass
    return doc


def page_count(path: str) -> int:
    return open_doc(path, False).page_count


def sleep_task(seconds: float) -> float:
    """Test helper: a task that only waits."""
    time.sleep(seconds)
    return seconds


def pid_task(_: Any = None) -> int:
    """Test helper: the process that ran the task."""
    return os.getpid()


def touch_pages(path: str, pages: list[int], seconds: float) -> list[int]:
    """Test helper with the `map_pages` signature: per page, wait and append its number to the file `path`."""
    for p in pages:
        time.sleep(seconds)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{p}\n")
    return list(pages)
