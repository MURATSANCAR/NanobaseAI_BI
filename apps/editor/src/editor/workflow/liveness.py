"""What an activity's liveness heartbeat carries.

The worker's interceptor (workflow.worker.HeartbeatActivityInterceptor) heartbeats every few
seconds for every activity with a heartbeat timeout. A long activity can put its progress into
those details (`report(check="layout", done=7, of=19)`): Temporal's UI and `describe` then show
where a step is, and the next heartbeat carries it without the activity having to time its own.
Outside an activity (a CLI run, a test) `report` does nothing."""

from __future__ import annotations

import contextvars
from typing import Any

DETAILS: contextvars.ContextVar[dict | None] = contextvars.ContextVar("editor_liveness", default=None)


def report(**progress: Any) -> None:
    details = DETAILS.get()
    if details is None:
        return
    details["progress"] = progress
    try:
        from temporalio import activity
        activity.heartbeat(dict(details))
    except Exception:  # noqa: BLE001 - not in an activity, or the SDK refused: the pulse still runs
        pass
