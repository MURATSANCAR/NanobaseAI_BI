from __future__ import annotations

import asyncio

import pytest

from nanobase_api.infrastructure.chat_session_gate import reset_chat_session_gate_for_tests


@pytest.mark.asyncio
async def test_session_gate_fifo_second_waits_until_release():
    gate = reset_chat_session_gate_for_tests()
    order: list[str] = []

    async def first():
        async for kind, _ in gate.acquire(tenant_id="t", session_id="s", request_id="a"):
            if kind == "acquired":
                order.append("a_acquired")
                await asyncio.sleep(0.05)
                await gate.release(tenant_id="t", session_id="s", request_id="a")
                order.append("a_released")
                return

    async def second():
        saw_wait = False
        async for kind, payload in gate.acquire(tenant_id="t", session_id="s", request_id="b"):
            if kind == "waiting":
                saw_wait = True
                assert payload and payload.get("phase") == "session_queued"
            if kind == "acquired":
                assert saw_wait
                order.append("b_acquired")
                await gate.release(tenant_id="t", session_id="s", request_id="b")
                order.append("b_released")
                return

    await asyncio.gather(first(), second())
    assert order == ["a_acquired", "a_released", "b_acquired", "b_released"]


@pytest.mark.asyncio
async def test_session_gate_different_sessions_parallel():
    gate = reset_chat_session_gate_for_tests()
    got = asyncio.Event()

    async def one(sid: str):
        async for kind, _ in gate.acquire(tenant_id="t", session_id=sid, request_id=sid):
            if kind == "acquired":
                got.set()
                await asyncio.sleep(0.05)
                await gate.release(tenant_id="t", session_id=sid, request_id=sid)
                return

    await asyncio.wait_for(asyncio.gather(one("s1"), one("s2")), timeout=2.0)
    assert got.is_set()


@pytest.mark.asyncio
async def test_session_gate_reclaims_stale_owner():
    gate = reset_chat_session_gate_for_tests()
    gate._stale_owner_s = 0.05  # type: ignore[attr-defined]

    async def hang():
        async for kind, _ in gate.acquire(tenant_id="t", session_id="s", request_id="stuck"):
            if kind == "acquired":
                # Never release — simulate hung stream / lost disconnect
                await asyncio.sleep(10)
                return

    async def next_msg():
        await asyncio.sleep(0.08)  # past stale window
        async for kind, _ in gate.acquire(tenant_id="t", session_id="s", request_id="next"):
            if kind == "acquired":
                await gate.release(tenant_id="t", session_id="s", request_id="next")
                return "ok"
        return "fail"

    task = asyncio.create_task(hang())
    assert await asyncio.wait_for(next_msg(), timeout=5.0) == "ok"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
