"""Which failures are the infrastructure's, not the book's.

A step that fails because a connection dropped, the database or the model was not there, or the
activity lost its worker (a heartbeat or start-to-close timeout) will most likely pass a little
later; the same step failing because of the book's data or a rule fails the same way every time.
The first kind must never end as a silently dropped step in a SUCCEEDED job: the workflow retries
it, and when it still cannot pass the job fails (editor.workflow.workflows, «infra-step-retry-v1»)
so the existing self-repair / «Yeniden okut» path takes over. The second kind keeps its old
handling (the editor's queue).

Pure standard library: the workflow sandbox imports this module.
"""

from __future__ import annotations

#: ApplicationError type an activity raises when part of its work failed for an infrastructure
#: reason after the rest was recorded (e.g. one final-read check lost the model): retried.
TYPE = "TransientStepFailure"

#: Exception class names (= Temporal ApplicationError.type of a raised Python exception) that are
#: infrastructure: httpx transport errors, psycopg / psycopg_pool connection errors, OS errors.
INFRA_TYPES = frozenset({
    TYPE,
    # httpx
    "TransportError", "NetworkError", "ConnectError", "ReadError", "WriteError", "CloseError",
    "RemoteProtocolError", "TimeoutException", "ConnectTimeout", "ReadTimeout", "WriteTimeout",
    "PoolTimeout",
    # psycopg / psycopg_pool
    "OperationalError", "InterfaceError", "AdminShutdown", "ConnectionTimeout", "TooManyRequests",
    # builtins
    "ConnectionError", "ConnectionRefusedError", "ConnectionResetError", "ConnectionAbortedError",
    "BrokenPipeError", "TimeoutError",
})

#: A model error whose text says the model was busy, not loaded or behind a failing proxy.
_MODEL_BUSY = ("gpu_busy", "model_not_ready", "gpu busy")
_MODEL_STATUS = ("502", "503", "504")
#: ... and never one whose text says the request itself cannot work (same answer every time).
_DETERMINISTIC = ("context length", "finish_reason=length", "maximum context")


#: The gateway could not be reached or never answered in time (editor.llm writes the transport error's class
#: name into the message: «book-vision-deep failed after 3 attempts: ConnectError: [Errno -3] Temporary failure
#: in name resolution», «… timed out after 6600s: ReadTimeout: »). Measured 2026-10-03..06: 48 cluster_name and
#: 700+ other calls lost to the gateway's container being recreated; 182 page scans to a queue timeout.
_UNREACHABLE = ("name resolution", "connection refused", "all connection attempts failed", " timed out after ")


def model_text_transient(text: str) -> bool:
    """A ModelError message from editor.llm: transient when the model was busy / down / unreachable."""
    low = (text or "").lower()
    if any(m in low for m in _DETERMINISTIC):
        return False
    if any(m in low for m in _MODEL_BUSY) or any(m in low for m in _UNREACHABLE):
        return True
    if any(f"{t.lower()}:" in low for t in INFRA_TYPES):
        return True
    return any(low.startswith(s) or f": {s}" in low for s in _MODEL_STATUS)


def failure_type_transient(type_name: str | None, message: str = "") -> bool:
    """For a Temporal ApplicationError (type = the raised exception's class name)."""
    if not type_name:
        return False
    if type_name in INFRA_TYPES:
        return True
    return type_name == "ModelError" and model_text_transient(message)


def is_transient(exc: BaseException | None) -> bool:
    """True when this exception, or one it was raised from, is an infrastructure failure."""
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        name = type(exc).__name__
        if name == "ContextOverflow":
            return False
        if name in INFRA_TYPES or any(c.__name__ in INFRA_TYPES for c in type(exc).__mro__[1:]):
            return True
        if name == "ModelError" and model_text_transient(str(exc)):
            return True
        exc = exc.__cause__ or exc.__context__
    return False
