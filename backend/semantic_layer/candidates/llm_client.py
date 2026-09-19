"""OpenAI-compatible chat client (llama-server / vLLM / hosted). Retries transport errors and load
refusals; streams when asked to (LLM_STREAM=1) so a dead connection shows as one."""

from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

log = logging.getLogger(__name__)

#: answers that are about the provider's load, not about this request
RETRY_STATUSES = (429, 500, 502, 503, 504, 529)
PRESSURE_STATUSES = (429, 503, 504, 529)


class LlmCancelled(Exception):
    """The caller withdrew the request while it was in flight."""


@dataclass
class _Reply:
    status_code: int
    text: str = ""
    body: dict[str, Any] = field(default_factory=dict)
    retry_after: Optional[float] = None


def _retry_after(headers: Any) -> Optional[float]:
    try:
        value = float(headers.get("retry-after", ""))
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None                   # an HTTP date, or nothing: the backoff decides


class LlmClient:
    supports_cancel = True

    def __init__(self, base: str, model: str, key: str = "", timeout: float = 240.0,
                 extra: Optional[dict[str, Any]] = None, stream: Optional[bool] = None):
        self.base = base.rstrip("/")
        self.model = model
        self.key = key
        self.timeout = timeout
        # Server-side options this deployment wants on every call from this client — llama.cpp takes
        # chat_template_kwargs here, which is how a reasoning model is asked not to reason. Measured
        # earlier: a call that returns a table name goes from 1.5s to 0.6s when the thinking block
        # is turned off, and returns the same name.
        self.extra = dict(extra or {})
        self.stream = os.environ.get("LLM_STREAM", "").strip().lower() in ("1", "true", "on", "yes") if stream is None else bool(stream)
        # Longest silence tolerated between two pieces of a streamed answer. 0 = the whole timeout:
        # a hosted queue may hold a request for minutes before its first byte.
        self.stream_idle = float(os.environ.get("LLM_STREAM_IDLE_SEC", "0") or 0)
        #: told about load refusals and successes (the shared queue); set by QueuedLlm
        self.observer: Any = None

    # ------------------------------------------------------------------ one request
    def _request(self, payload: dict[str, Any], headers: dict[str, str], cancel: Optional[threading.Event]) -> _Reply:
        if not payload.get("stream"):
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(f"{self.base}/chat/completions", json=payload, headers=headers)
            if r.status_code >= 400:
                return _Reply(r.status_code, r.text, retry_after=_retry_after(r.headers))
            return _Reply(r.status_code, r.text, r.json())
        idle = self.stream_idle or self.timeout
        parts: list[str] = []
        finish: Optional[str] = None
        with httpx.Client(timeout=httpx.Timeout(idle, connect=min(30.0, self.timeout))) as c:
            with c.stream("POST", f"{self.base}/chat/completions", json=payload, headers=headers) as r:
                if r.status_code >= 400:
                    return _Reply(r.status_code, r.read().decode("utf-8", "replace"), retry_after=_retry_after(r.headers))
                for line in r.iter_lines():
                    if cancel is not None and cancel.is_set():
                        raise LlmCancelled()
                    if not line.startswith("data:"):
                        continue                          # SSE comments and keep-alives
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        choice = (json.loads(data).get("choices") or [{}])[0]
                    except ValueError:
                        continue
                    parts.append(str((choice.get("delta") or {}).get("content") or ""))
                    finish = choice.get("finish_reason") or finish
        return _Reply(200, body={"choices": [{"message": {"content": "".join(parts)}, "finish_reason": finish}]})

    def _post(self, payload: dict[str, Any], headers: dict[str, str], cancel: Optional[threading.Event] = None) -> _Reply:
        """One request, bounded by `timeout` as a whole. httpx's timeout is per socket operation: a
        gateway that trickles bytes while the model works never trips it, and a 30-second table
        selector ran for four minutes. The request is made on a worker thread and abandoned at the
        deadline; the abandoned response, if it ever comes, is dropped."""
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = pool.submit(self._request, payload, headers, cancel)
            deadline = time.monotonic() + self.timeout
            while True:
                left = deadline - time.monotonic()
                try:
                    return future.result(timeout=max(0.0, min(left, 0.5 if cancel is not None else left)))
                except concurrent.futures.TimeoutError as e:
                    if cancel is not None and cancel.is_set():
                        raise LlmCancelled() from e
                    if time.monotonic() >= deadline:
                        raise httpx.ReadTimeout(f"LLM answer not complete within {self.timeout:.0f}s") from e
        finally:
            pool.shutdown(wait=False)

    def _pause(self, seconds: float, cancel: Optional[threading.Event]) -> None:
        if cancel is None:
            time.sleep(seconds)
        elif cancel.wait(seconds):
            raise LlmCancelled()

    def _tell(self, what: str, *args: Any) -> None:
        if self.observer is not None:
            try:
                getattr(self.observer, what)(*args)
            except Exception as e:  # noqa: BLE001
                log.warning("LLM observer failed on %s: %s", what, e)

    # ------------------------------------------------------------------ public
    def chat(self, messages: list[dict[str, str]], *, max_tokens: int = 4096, temperature: float = 0.0,
             cancel: Optional[threading.Event] = None) -> str:
        # 4096, not 1024: a statement with its reading lines, two derived tables and a CASE per
        # measure ran past 1024 tokens; cut mid-fence it read as "no SQL" and the question was
        # refused after a correct answer had been written.
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature, "stream": False}
        payload.update(self.extra)
        if self.stream:
            payload["stream"] = True
        last: Optional[Exception] = None
        for attempt, wait_s in enumerate((0.0, 1.0, 3.0)):
            if wait_s:
                self._pause(wait_s, cancel)
            try:
                r = self._post(payload, headers, cancel)
                break
            except httpx.TimeoutException:
                raise
            except httpx.TransportError as e:
                last = e
                log.warning("LLM transport error (attempt %d/3): %s", attempt + 1, e)
        else:
            raise RuntimeError(f"LLM unreachable after 3 attempts: {last}") from last
        # An endpoint answers 429/529 when its queue is full. That is load, not an answer. Wait and ask again
        # for as long as this client's timeout allows.
        deadline = time.monotonic() + self.timeout
        wait_s = 5.0
        while r.status_code in RETRY_STATUSES:
            if r.status_code in PRESSURE_STATUSES:
                self._tell("pressure", r.status_code, r.retry_after)
            # Jitter: eight calls refused in the same second must not all come back in the same second.
            pause = max(wait_s * random.uniform(0.75, 1.25), min(r.retry_after or 0.0, 120.0))
            if time.monotonic() + pause >= deadline:
                break
            log.warning("LLM HTTP %d, retrying in %.0fs", r.status_code, pause)
            self._pause(pause, cancel)
            wait_s = min(60.0, wait_s * 2)
            try:
                r = self._post(payload, headers, cancel)
            except httpx.TimeoutException:
                raise
            except httpx.TransportError as e:
                log.warning("LLM transport error while retrying: %s", e)
        if r.status_code >= 400:
            raise RuntimeError(f"LLM HTTP {r.status_code}: {r.text[:300]}")
        self._tell("success")
        choice = r.body["choices"][0]
        if choice.get("finish_reason") == "length":
            # Said out loud: a cut answer looks like a bad answer downstream, and the fix is a budget.
            log.warning("LLM answer cut at max_tokens=%d (model %s); raise the budget if this repeats", max_tokens, self.model)
        return str(choice["message"]["content"] or "")


class FakeLlm:
    """Deterministic stand-in for tests: returns canned replies in order or by keyword."""

    def __init__(self, replies: Optional[list[str]] = None, by_keyword: Optional[dict[str, str]] = None):
        self.replies = list(replies or [])
        self.by_keyword = dict(by_keyword or {})
        self.calls: list[list[dict[str, str]]] = []
        self.model = "fake"

    def chat(self, messages: list[dict[str, str]], **_: Any) -> str:
        self.calls.append(messages)
        text = "\n".join(m.get("content", "") for m in messages)
        for k, v in self.by_keyword.items():
            if k in text:
                return v
        if self.replies:
            return self.replies.pop(0)
        return "NO_SQL: fake"
