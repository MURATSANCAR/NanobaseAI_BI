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
import math
import time
from dataclasses import dataclass
from typing import Any

import httpx

from . import db
from .config import settings

MAX_RETRY_TOKENS = 32768     # upper bound; retry_budget also keeps it inside the context
_clients: dict[int, tuple[Any, httpx.AsyncClient]] = {}
_aliases: dict[str, dict] | None = None


def client() -> httpx.AsyncClient:
    """One client per event loop: an httpx connection pool belongs to the loop that opened it, and a
    step may run on its own loop (editor.offloop) beside the worker's."""
    try:
        loop: Any = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    held = _clients.get(id(loop))
    if held is None or held[0] is not loop:
        s = settings()
        held = (loop, httpx.AsyncClient(
            base_url=s.gateway_url,
            headers={"authorization": f"Bearer {s.gateway_key}"},
            timeout=httpx.Timeout(float(s.model_timeout_seconds), connect=15.0),
            limits=httpx.Limits(max_connections=128, max_keepalive_connections=64),
        ))
        _clients[id(loop)] = held
    return held[1]


async def close_client() -> None:
    """Close the current loop's client (editor.offloop calls this when its loop ends)."""
    loop = asyncio.get_running_loop()
    held = _clients.get(id(loop))
    if held is not None and held[0] is loop:
        _clients.pop(id(loop), None)
        await held[1].aclose()


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


def request_digest(req: dict) -> str:
    """The ledger's digest of a request: images replaced by their sha256 (ed.model_call.request_digest)."""
    return hashlib.sha256(json.dumps(_redact(req), sort_keys=True).encode()).hexdigest()


def cacheable(req: dict) -> bool:
    """May this request be answered from an earlier identical call («aynı istek önbelleği»)?
    Only a deterministic request: temperature 0 and one answer. A sampled call (temperature > 0) is never
    answered from the ledger: a single visual reading is noisy (the same model agreed 18/26 times with itself)
    and the votes / rechecks (text_visual_vote, continuity_vote, text_visual_recheck, 0.1-0.6) exist precisely
    to sample it again; a cached answer would turn n votes into one vote counted n times."""
    if not settings().llm_cache:
        return False
    t = req.get("temperature")
    return t is not None and float(t) == 0.0 and int(req.get("n") or 1) == 1


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


def _looping(text: str) -> bool:
    """True when the tail of an answer is one short pattern repeated over and over."""
    tail = text[-600:]
    if len(tail) < 200:
        return False
    for n in range(2, 80):
        unit = tail[-n:]
        if unit.strip() and tail.endswith(unit * 6):
            return True
    return False


#: Etkileşimli istek (Kitaba sor): gateway kart sırasında kısa bekler (EDITOR_INTERACTIVE_HOLD_MAX_SEC).
INTERACTIVE = {"x-editor-interactive": "1"}
#: Hiç beklemeyen istek: model ayakta değilse gateway hemen 503 model_not_ready döner, çağıran adımı atlar.
NO_WAIT = {**INTERACTIVE, "x-editor-no-wait": "1"}


#: The request never reached the gateway (its container is being recreated: the name does not resolve, the port
#: refuses): sending it again is safe. Measured 2026-10-03..05: 13 such windows, each <= 12 s, 1.000+ calls lost
#: («[Errno -3] Temporary failure in name resolution»); two in-call retries 2 + 4 s apart did not span them.
_GATEWAY_DOWN = (httpx.ConnectError, httpx.ConnectTimeout)


async def _post(path: str, req: dict, headers: dict | None = None) -> httpx.Response:
    """POST to the gateway; while it answers gpu_busy, wait for room instead of failing.
    Holders of the GPU that are not the editor's are never stopped, so waiting is the only
    honest move; the window is a setting and ends in the same error it would have raised.
    While the gateway itself cannot be reached, a background request (no INTERACTIVE / NO_WAIT headers)
    waits for it too (EDITOR_GATEWAY_DOWN_WAIT_SECONDS) instead of spending its attempts in seconds."""
    deadline = time.time() + settings().gpu_wait_seconds
    down_deadline = time.time() + settings().gateway_down_wait_seconds
    while True:
        try:
            r = await client().post(path, json=req, headers=headers)
        except _GATEWAY_DOWN:
            if headers or time.time() >= down_deadline:
                raise
            await asyncio.sleep(5)
            continue
        if r.status_code == 503 and "gpu_busy" in r.text and time.time() < deadline:
            await asyncio.sleep(30)
            continue
        return r


class ModelError(RuntimeError):
    pass


def _error_text(e: BaseException | None) -> str:
    """The ledger's error text. A transport error carries its class name: an httpx timeout's own text is empty,
    and 182 page scans were recorded with no error at all (2026-10-04..06). editor.transient reads the name."""
    if e is None:
        return ""
    if isinstance(e, httpx.HTTPError):
        return f"{type(e).__name__}: {e}"[:2000]
    return str(e)[:2000]


def _timed_out(e: BaseException) -> bool:
    """A read/write/pool timeout: the request was sent and waited the whole window. (A connect timeout never
    reached the gateway; _post already waited for it.)"""
    return isinstance(e, httpx.TimeoutException) and not isinstance(e, httpx.ConnectTimeout)


class ContextOverflow(ModelError):
    """The request does not fit the model's context. The same request fails the same way
    every time, so it is not retried here, and the worker turns it into a non-retryable
    activity failure (workflow.worker) instead of four more identical attempts."""


def _is_context_overflow(status: int, text: str) -> bool:
    return status == 400 and "context length" in text.lower()


def context_length(meta: dict) -> int | None:
    """The served context of an alias, from its vLLM arguments (--max-model-len)."""
    for a in meta.get("args") or []:
        if str(a).startswith("--max-model-len="):
            return int(str(a).split("=", 1)[1])
    return None


def retry_budget(max_tokens: int, prompt_tokens: int | None, context: int | None) -> int:
    """Output budget for a retry after finish_reason=length: twice the room, bounded by
    MAX_RETRY_TOKENS and by what the context leaves next to this prompt. Doubling without
    the prompt in view turned a 110k-token prompt that had fit into a context overflow
    (12000 -> 24000 output tokens, measured 2026-09-23). Never below the current budget."""
    room = MAX_RETRY_TOKENS
    if prompt_tokens and context:
        room = min(room, context - prompt_tokens - 64)
    return max(max_tokens, min(max_tokens * 2, room))


class Llm:
    def __init__(self, generation_id: str | None = None):
        self.generation_id = generation_id

    async def _record(self, alias: str, prompt: PromptRef | None, pages: list[int],
                      request: dict, response: Any, usage: dict | None, t0: float,
                      ok: bool, error: str | None) -> int:
        meta = (await aliases()).get(alias, {})
        red = _redact(request)
        digest = request_digest(request)
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

    async def _cached(self, alias: str, req: dict) -> dict | None:
        """The newest successful ed.model_call with this exact request (same digest, alias, model and
        revision) in this book version's readings: a repeated reading or a repair asks the same questions
        again. None when there is no scope (no generation), the revision is unknown, or nothing matches."""
        if not self.generation_id:
            return None
        meta = (await aliases()).get(alias, {})
        real, rev = meta.get("real_model"), meta.get("revision")
        if not real or not rev or rev in ("?", "unknown"):
            return None
        try:
            return await asyncio.to_thread(
                db.one,
                "SELECT m.id, m.response FROM model_call m WHERE m.request_digest=%s AND m.ok AND m.alias=%s"
                " AND m.real_model=%s AND m.revision=%s AND m.response IS NOT NULL AND m.generation_id IN"
                " (SELECT g.id FROM generation g WHERE g.book_version_id=(SELECT book_version_id FROM generation"
                " WHERE id=%s)) ORDER BY m.id DESC LIMIT 1",
                request_digest(req), alias, real, rev, self.generation_id)
        except Exception:  # noqa: BLE001 — a shortcut only: a failed lookup asks the model as before
            return None

    async def chat(self, alias: str, messages: list[dict], *, prompt: PromptRef | None = None,
                   schema: dict | None = None, pages: list[int] | None = None,
                   max_tokens: int = 4096, temperature: float = 0.2,
                   thinking: bool | None = None, think_budget: int | None = None,
                   cache: bool = True, retries: int = 2) -> tuple[Any, int]:
        """Returns (parsed JSON if schema else text, model_call id).

        `think_budget`: vLLM `thinking_token_budget`: after this many reasoning tokens vLLM forces the end of
        thinking and the model writes its answer in the same call (needs --reasoning-parser on the server;
        vLLM 0.29 refuses the field otherwise). `max_tokens` must leave room for the answer after it.
        `cache`: a deterministic request (`cacheable`) is first looked up in the ledger; False never is."""
        req: dict[str, Any] = {"model": alias, "messages": messages,
                               "max_tokens": max_tokens, "temperature": temperature}
        if schema is not None:
            req["response_format"] = {"type": "json_schema", "json_schema": {
                "name": (prompt.name if prompt else "out").replace(".", "_"),
                "schema": schema, "strict": True}}
        if thinking is not None:
            req["chat_template_kwargs"] = {"enable_thinking": thinking}
        if think_budget:
            req["thinking_token_budget"] = int(think_budget)
        if cache and cacheable(req):
            hit = await self._cached(alias, req)
            content = ((hit or {}).get("response") or {}).get("content")
            if hit and isinstance(content, str) and len(content) < 200000:
                try:
                    return (json.loads(content) if schema is not None else content), hit["id"]
                except json.JSONDecodeError:
                    pass
        last_err = None
        for attempt in range(retries + 1):
            t0 = time.time()
            resp = usage = None
            try:
                r = await _post("/v1/chat/completions", req)
                if _is_context_overflow(r.status_code, r.text):
                    raise ContextOverflow(f"{r.status_code} {r.text[:1500]}")
                if r.status_code >= 400:
                    raise ModelError(f"{r.status_code} {r.text[:1500]}")
                data = r.json()
                usage = data.get("usage")
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
                await self._record(alias, prompt, pages or [], req, resp, usage, t0, False, _error_text(e))
                if isinstance(e, ContextOverflow):
                    raise
                if isinstance(e, ModelError) and "gpu_busy" in str(e):
                    raise
                if _timed_out(e):
                    # Waited the whole read timeout (in the gateway's card queue or the model's): a second
                    # attempt would start at the back of the queue and outlive the activity (LONG). It is an
                    # infrastructure failure; the activity's retry policy sends it again.
                    raise ModelError(f"{alias} timed out after {settings().model_timeout_seconds}s: "
                                     f"{_error_text(e)}") from e
                # A deterministic retry repeats a degenerate loop token for token:
                # move away from it instead (measured 2026-09-19, page 8 x3 identical).
                _content = (resp or {}).get("content") or ""
                if "finish_reason=length" in str(e) and not _looping(_content) and len(_content) > 200:
                    # The first budget is sized for speed; it must never be the reason a page
                    # is lost: thinking that did not fit gets twice the room (bounded by the
                    # model's context). A loop gets no extra room, only a push out of the loop.
                    # A near-empty length stop (0 chars) is NOT truncation but a stalled decode:
                    # doubling the budget only makes the next stall run twice as long (measured
                    # 34→76s on modality_referee/merge_events), so it keeps the same budget and
                    # relies on the temperature/repetition push below to break out.
                    req["max_tokens"] = retry_budget(
                        req["max_tokens"], (usage or {}).get("prompt_tokens"),
                        context_length((await aliases()).get(alias, {})))
                if "finish_reason=length" in str(e) and (req.get("chat_template_kwargs") or {}).get("enable_thinking"):
                    # thinking used the whole budget and left no answer: answer directly
                    req["chat_template_kwargs"] = {"enable_thinking": False}
                req["temperature"] = min(0.7, temperature + 0.3 * (attempt + 1))
                req["repetition_penalty"] = 1.1
                await asyncio.sleep(2 * (attempt + 1))
        raise ModelError(f"{alias} failed after {retries + 1} attempts: {_error_text(last_err)}") from last_err

    async def choose(self, alias: str, messages: list[dict], choices: list[str], *,
                     prompt: PromptRef | None = None, pages: list[int] | None = None,
                     seed: int = 17, retries: int = 2) -> tuple[dict[str, float], int]:
        """A closed-set decision read as a distribution: the answer is ONE token out of
        `choices` (vLLM structured_outputs.choice) and the probability of every choice comes
        from that token's logprobs, so one call gives what repeated sampled votes only
        estimate. Every choice must be a single token (single letters are).
        Returns ({choice: probability, summing to 1}, model_call id)."""
        req: dict[str, Any] = {"model": alias, "messages": messages, "max_tokens": 1,
                               "temperature": 0, "seed": seed, "logprobs": True, "top_logprobs": 20,
                               "structured_outputs": {"choice": choices},
                               "chat_template_kwargs": {"enable_thinking": False}}
        if cacheable(req):
            # one token read as a distribution at temperature 0 with a fixed seed: the same request gives the
            # same probabilities (measured 2026-10-06: 31.197 repeated choose calls in 3 days)
            hit = await self._cached(alias, req)
            probs = ((hit or {}).get("response") or {}).get("probs")
            if hit and isinstance(probs, dict) and set(probs) == set(choices):
                return {c: float(probs[c]) for c in choices}, hit["id"]
        last_err = None
        for attempt in range(retries + 1):
            t0 = time.time()
            resp = None
            try:
                r = await _post("/v1/chat/completions", req)
                if _is_context_overflow(r.status_code, r.text):
                    raise ContextOverflow(f"{r.status_code} {r.text[:1500]}")
                if r.status_code >= 400:
                    raise ModelError(f"{r.status_code} {r.text[:1500]}")
                data = r.json()
                top = data["choices"][0]["logprobs"]["content"][0]["top_logprobs"]
                mass = {c: sum(math.exp(t["logprob"]) for t in top if t["token"].strip() == c)
                        for c in choices}
                total = sum(mass.values())
                resp = {"content": data["choices"][0]["message"].get("content"), "mass": mass}
                if total <= 0:
                    # none of the choices is among the reported tokens: there is no reading
                    raise ModelError(f"no choice among top tokens: {[t['token'] for t in top]}")
                probs = {c: m / total for c, m in mass.items()}
                cid = await self._record(alias, prompt, pages or [], req, {**resp, "probs": probs},
                                         data.get("usage"), t0, True, None)
                return probs, cid
            except (ModelError, httpx.HTTPError, KeyError, IndexError, TypeError) as e:
                last_err = e
                await self._record(alias, prompt, pages or [], req, resp, None, t0, False, _error_text(e))
                if isinstance(e, ContextOverflow):
                    raise
                if isinstance(e, ModelError) and "gpu_busy" in str(e):
                    raise
                if _timed_out(e):
                    raise ModelError(f"{alias} choose timed out after {settings().model_timeout_seconds}s: "
                                     f"{_error_text(e)}") from e
                await asyncio.sleep(2 * (attempt + 1))
        raise ModelError(f"{alias} choose failed after {retries + 1} attempts: {_error_text(last_err)}") \
            from last_err

    async def embed(self, texts: list[str], *, instruction: str | None = None,
                    headers: dict | None = None) -> list[list[float]]:
        """Qwen3-Embedding: queries carry an instruction, documents do not. `headers`: INTERACTIVE / NO_WAIT."""
        inputs = [f"Instruct: {instruction}\nQuery:{t}" if instruction else t for t in texts]
        t0 = time.time()
        req = {"model": "book-embedding", "input": inputs}
        r = await _post("/v1/embeddings", req, headers)
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

    async def rerank(self, query: str, docs: list[str], *, instruction: str,
                     headers: dict | None = None) -> list[float]:
        """Qwen3-Reranker yes/no probability per document (vLLM score API)."""
        if not docs:
            return []
        q = f"{self.RERANK_PREFIX}<Instruct>: {instruction}\n<Query>: {query}\n"
        d = [f"<Document>: {x}{self.RERANK_SUFFIX}" for x in docs]
        t0 = time.time()
        r = await client().post("/v1/score", json={"model": "book-reranker",
                                                   "text_1": q, "text_2": d}, headers=headers)
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
