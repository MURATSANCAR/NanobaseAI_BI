"""Model calls through the gateway, each one recorded in ed.model_call.

"Model, prompt, sürüm ve kullanılan kaynaklar kaydedilir": every call stores
alias, real model, revision, prompt name/version, the pages it looked at, a
digest of the request (images replaced by their sha256) and the response.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from . import db
from .config import settings

MAX_RETRY_TOKENS = 32768     # fits every chat model's context next to its prompt
_client: httpx.AsyncClient | None = None
_aliases: dict[str, dict] | None = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        s = settings()
        _client = httpx.AsyncClient(
            base_url=s.gateway_url,
            headers={"authorization": f"Bearer {s.gateway_key}"},
            timeout=httpx.Timeout(3600.0, connect=15.0),
            limits=httpx.Limits(max_connections=128, max_keepalive_connections=64),
        )
    return _client


async def aliases() -> dict[str, dict]:
    """alias -> {real_model, revision, ...} (internal endpoint, workers only)."""
    global _aliases
    if _aliases is None:
        s = settings()
        r = await client().get("/internal/aliases",
                               headers={"authorization": f"Bearer {s.gateway_internal_key}"})
        r.raise_for_status()
        _aliases = r.json()
    return _aliases


@dataclass(frozen=True)
class PromptRef:
    name: str
    version: str


def image_part(png: bytes) -> dict:
    return {"type": "image_url",
            "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}}


def _redact(obj: Any) -> Any:
    """Replace inline images with their digest so the ledger stays small."""
    if isinstance(obj, dict):
        if obj.get("type") == "image_url":
            url = obj["image_url"]["url"]
            return {"type": "image_url", "sha256": hashlib.sha256(url.encode()).hexdigest()}
        return {k: _redact(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


class ModelError(RuntimeError):
    pass


class Llm:
    def __init__(self, generation_id: str | None = None):
        self.generation_id = generation_id

    async def _record(self, alias: str, prompt: PromptRef | None, pages: list[int],
                      request: dict, response: Any, usage: dict | None, t0: float,
                      ok: bool, error: str | None) -> int:
        meta = (await aliases()).get(alias, {})
        red = _redact(request)
        digest = hashlib.sha256(json.dumps(red, sort_keys=True).encode()).hexdigest()
        row = await asyncio.to_thread(
            db.one,
            "INSERT INTO model_call(generation_id, alias, real_model, revision, prompt_name,"
            " prompt_version, pages, request_digest, request, response, prompt_tokens,"
            " completion_tokens, latency_ms, ok, error)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            self.generation_id, alias, meta.get("real_model", "?"), meta.get("revision", "?"),
            prompt.name if prompt else None, prompt.version if prompt else None, pages,
            digest, db.J(red), db.J(response) if response is not None else None,
            (usage or {}).get("prompt_tokens"), (usage or {}).get("completion_tokens"),
            int((time.time() - t0) * 1000), ok, error)
        return row["id"]

    async def chat(self, alias: str, messages: list[dict], *, prompt: PromptRef | None = None,
                   schema: dict | None = None, pages: list[int] | None = None,
                   max_tokens: int = 4096, temperature: float = 0.2,
                   thinking: bool | None = None, retries: int = 2) -> tuple[Any, int]:
        """Returns (parsed JSON if schema else text, model_call id)."""
        req: dict[str, Any] = {"model": alias, "messages": messages,
                               "max_tokens": max_tokens, "temperature": temperature}
        if schema is not None:
            req["response_format"] = {"type": "json_schema", "json_schema": {
                "name": (prompt.name if prompt else "out").replace(".", "_"),
                "schema": schema, "strict": True}}
        if thinking is not None:
            req["chat_template_kwargs"] = {"enable_thinking": thinking}
        last_err = None
        for attempt in range(retries + 1):
            t0 = time.time()
            resp = None
            try:
                r = await client().post("/v1/chat/completions", json=req)
                if r.status_code >= 400:
                    raise ModelError(f"{r.status_code} {r.text[:1500]}")
                data = r.json()
                msg = data["choices"][0]["message"]
                text = msg.get("content") or ""
                finish = data["choices"][0].get("finish_reason")
                resp = {"content": text[:200000], "finish_reason": finish,
                        "reasoning": (msg.get("reasoning_content") or msg.get("reasoning") or "")[:20000]}
                if finish == "length":
                    # ran into max_tokens: a runaway string or thinking that never ended
                    raise ModelError(f"finish_reason=length after {len(text)} chars; tail: {text[-200:]!r}")
                out: Any = json.loads(text) if schema is not None else text
                cid = await self._record(alias, prompt, pages or [], req, resp,
                                         data.get("usage"), t0, True, None)
                return out, cid
            except (ModelError, json.JSONDecodeError, httpx.HTTPError, KeyError) as e:
                last_err = e
                await self._record(alias, prompt, pages or [], req, resp, None, t0, False,
                                   str(e)[:2000])
                if isinstance(e, ModelError) and "gpu_busy" in str(e):
                    raise
                # A deterministic retry repeats a degenerate loop token for token:
                # move away from it instead (measured 2026-09-19, page 8 x3 identical).
                if "finish_reason=length" in str(e):
                    # The first budget is sized for speed; it must never be the reason a page
                    # is lost. A retry gets twice the room (bounded by the model's context).
                    req["max_tokens"] = min(req["max_tokens"] * 2, MAX_RETRY_TOKENS)
                if "finish_reason=length" in str(e) and (req.get("chat_template_kwargs") or {}).get("enable_thinking"):
                    # thinking used the whole budget and left no answer: answer directly
                    req["chat_template_kwargs"] = {"enable_thinking": False}
                req["temperature"] = min(0.7, temperature + 0.3 * (attempt + 1))
                req["repetition_penalty"] = 1.1
                await asyncio.sleep(2 * (attempt + 1))
        raise ModelError(f"{alias} failed after {retries + 1} attempts: {last_err}")

    async def embed(self, texts: list[str], *, instruction: str | None = None) -> list[list[float]]:
        """Qwen3-Embedding: queries carry an instruction, documents do not."""
        inputs = [f"Instruct: {instruction}\nQuery:{t}" if instruction else t for t in texts]
        t0 = time.time()
        req = {"model": "book-embedding", "input": inputs}
        r = await client().post("/v1/embeddings", json=req)
        if r.status_code >= 400:
            await self._record("book-embedding", None, [], {"n": len(texts)}, None, None, t0,
                               False, r.text[:2000])
            raise ModelError(r.text[:1500])
        data = r.json()
        await self._record("book-embedding", None, [], {"n": len(texts), "instruction": instruction},
                           {"dims": len(data["data"][0]["embedding"])}, data.get("usage"), t0,
                           True, None)
        return [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])]

    RERANK_PREFIX = ("<|im_start|>system\nJudge whether the Document meets the requirements "
                     "based on the Query and the Instruct provided. Note that the answer can "
                     "only be \"yes\" or \"no\".<|im_end|>\n<|im_start|>user\n")
    RERANK_SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"

    async def rerank(self, query: str, docs: list[str], *, instruction: str) -> list[float]:
        """Qwen3-Reranker yes/no probability per document (vLLM score API)."""
        if not docs:
            return []
        q = f"{self.RERANK_PREFIX}<Instruct>: {instruction}\n<Query>: {query}\n"
        d = [f"<Document>: {x}{self.RERANK_SUFFIX}" for x in docs]
        t0 = time.time()
        r = await client().post("/v1/score", json={"model": "book-reranker",
                                                   "text_1": q, "text_2": d})
        if r.status_code >= 400:
            await self._record("book-reranker", None, [], {"n": len(docs)}, None, None, t0,
                               False, r.text[:2000])
            raise ModelError(r.text[:1500])
        data = r.json()
        scores = [0.0] * len(docs)
        for item in data["data"]:
            scores[item["index"]] = float(item["score"])
        await self._record("book-reranker", None, [], {"query": query, "n": len(docs),
                                                       "instruction": instruction},
                           {"scores": scores}, data.get("usage"), t0, True, None)
        return scores
