"""OpenAI-compatible LLM call (llama.cpp :8010). No tools, no DB.

All calls go through the production ModelQueue so concurrent users wait
instead of overloading the local model.
"""

from __future__ import annotations

import os

import httpx

from nanobase_awel.contracts.errors import TEXT_TO_SQL_MODEL_UNAVAILABLE, WorkflowError
from nanobase_awel.operators.model_queue import (
    ModelQueueFullError,
    ModelQueueTimeoutError,
    get_model_queue,
    progress_sink,
    request_ctx,
    tenant_ctx,
    user_ctx,
)

LLM_BASE = os.environ.get("OPENAI_API_BASE", "http://127.0.0.1:8010/v1").rstrip("/")
LLM_KEY = os.environ.get("OPENAI_API_KEY", "nanobase-local")
LLM_MODEL = os.environ.get("LLM_MODEL_NAME", "nanobase-qwen36-35b-a3b-mtp")


async def _raw_chat_completion(
    system: str,
    user: str,
    *,
    temperature: float,
    max_tokens: int,
    timeout_s: float,
) -> str:
    body = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {LLM_KEY}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.post(f"{LLM_BASE}/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        raise WorkflowError(
            TEXT_TO_SQL_MODEL_UNAVAILABLE,
            "Text-to-SQL modeline erişilemiyor.",
            retryable=True,
        ) from e
    return str((((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or "")


async def chat_completion(
    system: str,
    user: str,
    *,
    temperature: float = 0.0,
    max_tokens: int = 2048,
    timeout_s: float = 180.0,
) -> str:
    queue = get_model_queue()
    sink = progress_sink.get()
    slot = None
    try:
        async for kind, payload in queue.acquire_with_progress(
            tenant_id=tenant_ctx.get() or "default",
            user_id=user_ctx.get(),
            request_id=request_ctx.get(),
        ):
            if kind == "waiting":
                if sink is not None:
                    await sink.put(dict(payload))
            else:
                slot = payload
        return await _raw_chat_completion(
            system,
            user,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_s=timeout_s,
        )
    except ModelQueueFullError as e:
        raise WorkflowError(e.code, e.message, retryable=True) from e
    except ModelQueueTimeoutError as e:
        raise WorkflowError("MODEL_QUEUE_TIMEOUT", e.message, retryable=True) from e
    finally:
        if slot is not None:
            await slot.release()
