"""OpenAI-compatible chat client (llama-server / vLLM). Retries transport errors; no streaming."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import httpx

log = logging.getLogger(__name__)


class LlmClient:
    def __init__(self, base: str, model: str, key: str = "", timeout: float = 240.0,
                 extra: Optional[dict[str, Any]] = None):
        self.base = base.rstrip("/")
        self.model = model
        self.key = key
        self.timeout = timeout
        # Server-side options this deployment wants on every call from this client — llama.cpp takes
        # chat_template_kwargs here, which is how a reasoning model is asked not to reason. Measured
        # on the A40: a call that returns a table name goes from 1.5s to 0.6s when the thinking block
        # is turned off, and returns the same name.
        self.extra = dict(extra or {})

    def chat(self, messages: list[dict[str, str]], *, max_tokens: int = 1024, temperature: float = 0.0) -> str:
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature, "stream": False}
        payload.update(self.extra)
        last: Optional[Exception] = None
        for attempt, wait_s in enumerate((0.0, 1.0, 3.0)):
            if wait_s:
                time.sleep(wait_s)
            try:
                with httpx.Client(timeout=self.timeout) as c:
                    r = c.post(f"{self.base}/chat/completions", json=payload, headers=headers)
                break
            except httpx.TimeoutException:
                raise
            except httpx.TransportError as e:
                last = e
                log.warning("LLM transport error (attempt %d/3): %s", attempt + 1, e)
        else:
            raise RuntimeError(f"LLM unreachable after 3 attempts: {last}") from last
        if r.status_code >= 400:
            raise RuntimeError(f"LLM HTTP {r.status_code}: {r.text[:300]}")
        return str(r.json()["choices"][0]["message"]["content"] or "")


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
