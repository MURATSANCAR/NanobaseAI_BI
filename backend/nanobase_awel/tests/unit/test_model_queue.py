"""Model queue concurrency / tenant fairness / backpressure."""

from __future__ import annotations

import asyncio

import pytest

from nanobase_awel.operators.model_queue import (
    ModelQueueFullError,
    ModelQueueTimeoutError,
    reset_model_queue_for_tests,
)


def test_max_concurrency_queues_second_caller():
    async def _run():
        q = reset_model_queue_for_tests(
            max_concurrency=1, queue_limit=10, tenant_limit=10, queue_timeout_s=5
        )
        events: list[str] = []

        async def holder():
            async for kind, payload in q.acquire_with_progress(tenant_id="t1", request_id="a"):
                if kind == "acquired":
                    events.append("a-acquired")
                    await asyncio.sleep(0.15)
                    await payload.release()
                    events.append("a-released")
                    return

        async def waiter():
            saw_wait = False
            async for kind, payload in q.acquire_with_progress(tenant_id="t1", request_id="b"):
                if kind == "waiting":
                    saw_wait = True
                    events.append(f"b-wait-{payload['position']}")
                else:
                    events.append("b-acquired")
                    assert saw_wait
                    await payload.release()
                    events.append("b-released")
                    return

        await asyncio.gather(holder(), waiter())
        assert "a-acquired" in events
        assert any(e.startswith("b-wait-") for e in events)
        assert "b-acquired" in events

    asyncio.run(_run())


def test_tenant_queue_limit():
    async def _run():
        q = reset_model_queue_for_tests(
            max_concurrency=1, queue_limit=50, tenant_limit=2, queue_timeout_s=2
        )
        slot = None
        async for kind, payload in q.acquire_with_progress(tenant_id="acme", request_id="1"):
            if kind == "acquired":
                slot = payload
                break

        started = asyncio.Event()

        async def enqueue_second():
            async for kind, payload in q.acquire_with_progress(tenant_id="acme", request_id="2"):
                if kind == "waiting":
                    started.set()
                    # stay waiting until released by main
                    continue
                await payload.release()
                return

        t = asyncio.create_task(enqueue_second())
        await asyncio.wait_for(started.wait(), timeout=2)
        with pytest.raises(ModelQueueFullError) as ei:
            async for _ in q.acquire_with_progress(tenant_id="acme", request_id="3"):
                pass
        assert ei.value.code == "TENANT_QUEUE_FULL"
        assert slot is not None
        await slot.release()
        await asyncio.wait_for(t, timeout=2)

    asyncio.run(_run())


def test_queue_timeout():
    async def _run():
        q = reset_model_queue_for_tests(
            max_concurrency=1, queue_limit=10, tenant_limit=10, queue_timeout_s=0.25
        )
        slot = None
        async for kind, payload in q.acquire_with_progress(tenant_id="t", request_id="hold"):
            if kind == "acquired":
                slot = payload
                break
        assert slot is not None
        with pytest.raises(ModelQueueTimeoutError):
            async for _ in q.acquire_with_progress(tenant_id="t", request_id="late"):
                pass
        await slot.release()

    asyncio.run(_run())
