"""OpenAI-compatible LLM call (llama.cpp).

SQL plan/repair default to the chat model (Qwen) which matches our JSON
plan prompts. Optional Arctic Text2SQL is used as a fallback when configured.
Explain/general always use the chat ModelQueue.
"""

from __future__ import annotations

import os
from typing import Any

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

TEXT2SQL_BASE = (os.environ.get("TEXT2SQL_API_BASE") or "").rstrip("/")
TEXT2SQL_MODEL = os.environ.get("TEXT2SQL_MODEL") or "arctic-text2sql"
TEXT2SQL_KEY = os.environ.get("TEXT2SQL_API_KEY") or LLM_KEY
# Prefer chat (Qwen) for JSON sql-plan; arctic is R1/CoT and often slower/noisier.
TEXT2SQL_PREFER = (os.environ.get("TEXT2SQL_PREFER") or "chat").strip().lower()
TEXT2SQL_FALLBACK = os.environ.get("TEXT2SQL_FALLBACK_TO_CHAT", "1").strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
)

LLM_TIMEOUT_SEC = float(os.environ.get("LLM_TIMEOUT_SEC", "90"))
TEXT2SQL_TIMEOUT_SEC = float(os.environ.get("TEXT2SQL_TIMEOUT_SEC", "90"))
HEALTH_TIMEOUT_SEC = float(os.environ.get("LLM_HEALTH_TIMEOUT_SEC", "3"))


def _compact_user_prompt(user: str, *, ratio: float = 0.5) -> str:
    """Truncate authorized schema context once under model/queue pressure."""
    text = user or ""
    start_tag = "<authorized_schema_context>"
    end_tag = "</authorized_schema_context>"
    s = text.find(start_tag)
    e = text.find(end_tag)
    if s >= 0 and e > s:
        inner = text[s + len(start_tag) : e]
        keep = max(800, int(len(inner) * max(0.25, min(ratio, 0.9))))
        if len(inner) > keep:
            inner = inner[:keep] + "\n…[truncated for retry]…"
            return text[: s + len(start_tag)] + inner + text[e:]
    if len(text) > 6000:
        return text[:3000] + "\n…[truncated for retry]…\n" + text[-2000:]
    return text


async def _probe_models(base: str, key: str) -> bool:
    try:
        headers = {"Authorization": f"Bearer {key}"}
        async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT_SEC) as client:
            r = await client.get(f"{base.rstrip('/')}/models", headers=headers)
            return r.status_code < 500
    except Exception:
        return False


async def _raw_chat_completion(
    system: str,
    user: str,
    *,
    base: str,
    model: str,
    key: str,
    temperature: float,
    max_tokens: int,
    timeout_s: float,
) -> str:
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    # Use a request that respects asyncio cancellation (client disconnect → task.cancel).
    timeout = httpx.Timeout(timeout_s, connect=min(30.0, timeout_s))
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            r = await client.post(f"{base}/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
        except httpx.TimeoutException as e:
            raise TimeoutError(f"llm_timeout:{base}:{timeout_s}s") from e
    return str((((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or "")


async def _call_endpoint(
    system: str,
    user: str,
    *,
    base: str,
    model: str,
    key: str,
    temperature: float,
    max_tokens: int,
    timeout_s: float,
    require_healthy: bool = True,
) -> str:
    if require_healthy and not await _probe_models(base, key):
        raise RuntimeError(f"llm_unhealthy:{base}")
    return await _raw_chat_completion(
        system,
        user,
        base=base,
        model=model,
        key=key,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_s=timeout_s,
    )


async def _via_chat_queue(
    system: str,
    user: str,
    *,
    temperature: float,
    max_tokens: int,
    timeout_s: float,
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
        return await _call_endpoint(
            system,
            user,
            base=LLM_BASE,
            model=LLM_MODEL,
            key=LLM_KEY,
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


async def _via_arctic(
    system: str,
    user: str,
    *,
    temperature: float,
    max_tokens: int,
    timeout_s: float,
) -> str:
    return await _call_endpoint(
        system,
        user,
        base=TEXT2SQL_BASE,
        model=TEXT2SQL_MODEL,
        key=TEXT2SQL_KEY,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_s=timeout_s,
    )


async def chat_completion(
    system: str,
    user: str,
    *,
    temperature: float = 0.0,
    max_tokens: int = 2048,
    timeout_s: float | None = None,
    purpose: str = "general",
) -> str:
    """LLM completion.

    purpose=sql_plan|sql_repair → prefer chat model (JSON plan), Arctic optional fallback.
    purpose=general → ModelQueue + chat model.
    """
    chat_timeout = float(timeout_s) if timeout_s is not None else LLM_TIMEOUT_SEC
    arctic_timeout = float(timeout_s) if timeout_s is not None else TEXT2SQL_TIMEOUT_SEC
    use_sql_path = purpose in ("sql_plan", "sql_repair")
    last_err: Exception | None = None

    if use_sql_path and TEXT2SQL_BASE and TEXT2SQL_PREFER in ("arctic", "text2sql"):
        try:
            return await _via_arctic(
                system,
                user,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout_s=arctic_timeout,
            )
        except Exception as e:  # noqa: BLE001
            last_err = e
            if not TEXT2SQL_FALLBACK:
                raise WorkflowError(
                    TEXT_TO_SQL_MODEL_UNAVAILABLE,
                    "Text-to-SQL modeline erişilemiyor.",
                    retryable=True,
                ) from e

    def _should_compact_retry(exc: BaseException) -> bool:
        if not use_sql_path:
            return False
        if isinstance(exc, WorkflowError):
            return exc.code in {
                TEXT_TO_SQL_MODEL_UNAVAILABLE,
                "MODEL_QUEUE_TIMEOUT",
                "MODEL_QUEUE_FULL",
            }
        return isinstance(exc, (TimeoutError, httpx.TimeoutException, RuntimeError))

    try:
        return await _via_chat_queue(
            system,
            user,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_s=chat_timeout,
        )
    except Exception as e:
        # One compact-context retry for sql_plan/sql_repair under load/queue pressure.
        if _should_compact_retry(e):
            compact = _compact_user_prompt(user, ratio=0.45)
            if compact != user:
                try:
                    return await _via_chat_queue(
                        system,
                        compact,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout_s=chat_timeout,
                    )
                except Exception as e2:  # noqa: BLE001
                    raise WorkflowError(
                        TEXT_TO_SQL_MODEL_UNAVAILABLE,
                        "Text-to-SQL modeline erişilemiyor.",
                        retryable=True,
                    ) from e2
        if isinstance(e, WorkflowError):
            raise
        # Do not chain Arctic after a chat timeout — doubles wait (~270s).
        raise WorkflowError(
            TEXT_TO_SQL_MODEL_UNAVAILABLE,
            "Text-to-SQL modeline erişilemiyor.",
            retryable=True,
        ) from e


def _endpoints_for_purpose(purpose: str) -> list[tuple[str, str, str, float]]:
    """Test helper — ordered (base, model, key, timeout) candidates."""
    chat = (LLM_BASE, LLM_MODEL, LLM_KEY, LLM_TIMEOUT_SEC)
    arctic = (TEXT2SQL_BASE, TEXT2SQL_MODEL, TEXT2SQL_KEY, TEXT2SQL_TIMEOUT_SEC)
    if purpose not in ("sql_plan", "sql_repair") or not TEXT2SQL_BASE:
        return [chat]
    if TEXT2SQL_PREFER in ("arctic", "text2sql"):
        return [arctic, chat] if TEXT2SQL_FALLBACK else [arctic]
    return [chat]
