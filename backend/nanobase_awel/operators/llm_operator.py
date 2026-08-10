"""OpenAI-compatible LLM call (llama.cpp).

SQL plan/repair default to the chat model (Qwen) which matches our JSON
plan prompts. Optional Arctic Text2SQL is used as a fallback when configured.
Explain/general always use the chat ModelQueue.
"""

from __future__ import annotations

import inspect
import json
import os
import time
from typing import Any, Callable

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
# Health probe result is cached; a per-completion GET /models round trip adds
# latency (and a spurious 3s failure mode) while the exclusive model slot is held.
HEALTH_CACHE_SEC = float(os.environ.get("LLM_HEALTH_CACHE_SEC", "30"))
# llama.cpp defaults repeat_penalty to 1.1 which corrupts long SQL with repeated
# column tokens even at temperature 0. Pin greedy-friendly sampling.
SAMPLER_PIN = os.environ.get("LLM_SAMPLER_PIN", "1").strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
)
LLM_REPEAT_PENALTY = float(os.environ.get("LLM_REPEAT_PENALTY", "1.0"))

_shared_client: httpx.AsyncClient | None = None
_probe_cache: dict[str, tuple[float, bool]] = {}

# Delta callback: called with each streamed content chunk (may be sync or async).
DeltaCallback = Callable[[str], Any]


def _client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            timeout=httpx.Timeout(LLM_TIMEOUT_SEC, connect=10.0),
        )
    return _shared_client


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
            # Cut at a line boundary — a mid-line cut leaves a half column list
            # that reads as authoritative and invites invented identifiers.
            cut = inner.rfind("\n", 0, keep)
            if cut > 400:
                keep = cut
            inner = inner[:keep] + "\n…[truncated for retry]…"
            return text[: s + len(start_tag)] + inner + text[e:]
    if len(text) > 6000:
        return text[:3000] + "\n…[truncated for retry]…\n" + text[-2000:]
    return text


async def _probe_models(base: str, key: str) -> bool:
    now = time.monotonic()
    cached = _probe_cache.get(base)
    if cached and (now - cached[0]) < HEALTH_CACHE_SEC:
        return cached[1]
    try:
        headers = {"Authorization": f"Bearer {key}"}
        r = await _client().get(
            f"{base.rstrip('/')}/models", headers=headers, timeout=HEALTH_TIMEOUT_SEC
        )
        ok = r.status_code < 500
    except Exception:
        ok = False
    _probe_cache[base] = (now, ok)
    return ok


async def _emit_delta(on_delta: DeltaCallback | None, chunk: str) -> None:
    if on_delta is None or not chunk:
        return
    try:
        res = on_delta(chunk)
        if inspect.isawaitable(res):
            await res
    except Exception:
        # Delivery to the UI must never fail the completion itself.
        pass


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
    meta: dict[str, Any] | None = None,
    on_delta: DeltaCallback | None = None,
) -> str:
    stream = on_delta is not None
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if SAMPLER_PIN:
        body["top_p"] = 1.0
        body["repeat_penalty"] = LLM_REPEAT_PENALTY
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    # Use a request that respects asyncio cancellation (client disconnect → task.cancel).
    timeout = httpx.Timeout(timeout_s, connect=min(30.0, timeout_s))
    client = _client()
    finish_reason: str | None = None
    try:
        if stream:
            parts: list[str] = []
            async with client.stream(
                "POST",
                f"{base}/chat/completions",
                headers=headers,
                json=body,
                timeout=timeout,
            ) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    line = (line or "").strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except Exception:
                        continue
                    choice = (chunk.get("choices") or [{}])[0]
                    finish_reason = choice.get("finish_reason") or finish_reason
                    delta = str(((choice.get("delta") or {}).get("content")) or "")
                    if delta:
                        parts.append(delta)
                        await _emit_delta(on_delta, delta)
            content = "".join(parts)
        else:
            r = await client.post(
                f"{base}/chat/completions", headers=headers, json=body, timeout=timeout
            )
            r.raise_for_status()
            data = r.json()
            choice = (data.get("choices") or [{}])[0]
            finish_reason = choice.get("finish_reason")
            content = str(((choice.get("message") or {}).get("content")) or "")
    except httpx.TimeoutException as e:
        raise TimeoutError(f"llm_timeout:{base}:{timeout_s}s") from e
    if meta is not None:
        meta["finish_reason"] = finish_reason
    return content


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
    meta: dict[str, Any] | None = None,
    on_delta: DeltaCallback | None = None,
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
        meta=meta,
        on_delta=on_delta,
    )


async def _via_chat_queue(
    system: str,
    user: str,
    *,
    temperature: float,
    max_tokens: int,
    timeout_s: float,
    meta: dict[str, Any] | None = None,
    on_delta: DeltaCallback | None = None,
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
            meta=meta,
            on_delta=on_delta,
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
    meta: dict[str, Any] | None = None,
    on_delta: DeltaCallback | None = None,
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
        meta=meta,
        on_delta=on_delta,
    )


async def chat_completion(
    system: str,
    user: str,
    *,
    temperature: float = 0.0,
    max_tokens: int = 2048,
    timeout_s: float | None = None,
    purpose: str = "general",
    meta: dict[str, Any] | None = None,
    on_delta: DeltaCallback | None = None,
) -> str:
    """LLM completion.

    purpose=sql_plan|sql_repair → prefer chat model (JSON plan), Arctic optional fallback.
    purpose=general → ModelQueue + chat model.
    meta (optional dict) receives finish_reason; on_delta streams content chunks.
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
                meta=meta,
                on_delta=on_delta,
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
            meta=meta,
            on_delta=on_delta,
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
                        meta=meta,
                        on_delta=on_delta,
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
