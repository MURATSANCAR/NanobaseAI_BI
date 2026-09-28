"""The OpenAI-compatible door of the LLM gate: every call takes a lease, the bridge's model wins,
streams pass through untouched, and the lease is always given back."""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from semantic_bridge import llm_openai
from semantic_layer.runtime.llm_queue import LlmQueue

SSE = [b'data: {"choices":[{"delta":{"content":"Mer"}}]}\n\n', b'data: {"choices":[{"delta":{"content":"haba"}}]}\n\n',
       b"data: [DONE]\n\n"]


class Recorder:
    def __init__(self, status: int = 200):
        self.status = status
        self.bodies: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        if self.status >= 400:
            return httpx.Response(self.status, json={"error": {"message": "boom"}})
        if body.get("stream"):
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=httpx.ByteStream(b"".join(SSE)))
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "tamam"}}]})


class CountingQueue:
    def __init__(self):
        self.inner = LlmQueue(None, slots=1)
        self.leases: list[dict] = []
        self.open = 0

    def lease(self, **kw):
        self.leases.append(kw)
        cm = self.inner.lease(**kw)
        outer = self

        class _Wrap:
            def __enter__(self):
                outer.open += 1
                return cm.__enter__()

            def __exit__(self, *exc):
                outer.open -= 1
                return cm.__exit__(*exc)

        return _Wrap()


@pytest.fixture
def setup(monkeypatch):
    recorder = Recorder()
    real = httpx.AsyncClient
    monkeypatch.setattr(llm_openai.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(recorder), **kw))
    queue = CountingQueue()
    settings = SimpleNamespace(llm_base="http://model.test/v1", llm_model="nanobaseAI", llm_key="k", llm_timeout=30,
                               llm_extra={"chat_template_kwargs": {"enable_thinking": False}}, tenant_id="t", datasource_id="d")
    runtime = SimpleNamespace(settings=settings, llm=object(), queue=queue)
    app = FastAPI()
    llm_openai.register(app, lambda: runtime, lambda request: None)
    return TestClient(app), recorder, queue, runtime


URL = "/api/v1/llm/openai/v1/chat/completions"
MSG = {"messages": [{"role": "user", "content": "selam"}], "model": "baska-model"}


def test_non_stream_takes_a_lease_and_uses_the_bridge_model(setup):
    client, recorder, queue, _ = setup
    r = client.post(URL, json=MSG, headers={"X-LLM-Module": "destek"})
    assert r.status_code == 200
    assert r.json()["choices"][0]["message"]["content"] == "tamam"
    sent = recorder.bodies[0]
    assert sent["model"] == "nanobaseAI"
    assert sent["chat_template_kwargs"] == {"enable_thinking": False}
    assert queue.leases[0]["module"] == "destek" and queue.leases[0]["priority"] == 0
    assert queue.leases[0]["question"] == "selam"
    assert queue.open == 0
    assert "X-LLM-Wait-Ms" in r.headers


def test_request_value_wins_over_bridge_default(setup):
    client, recorder, _, _ = setup
    client.post(URL, json={**MSG, "chat_template_kwargs": {"enable_thinking": True}})
    assert recorder.bodies[0]["chat_template_kwargs"] == {"enable_thinking": True}


def test_stream_passes_through_and_releases(setup):
    client, _, queue, _ = setup
    with client.stream("POST", URL, json={**MSG, "stream": True}, headers={"X-LLM-Priority": "2"}) as r:
        body = b"".join(r.iter_raw())
    assert body == b"".join(SSE)
    assert queue.leases[0]["priority"] == 2
    assert queue.open == 0


def test_upstream_error_is_forwarded_and_lease_released(setup):
    client, recorder, queue, _ = setup
    recorder.status = 500
    r = client.post(URL, json={**MSG, "stream": True})
    assert r.status_code == 500 and r.json()["error"]["message"] == "boom"
    assert queue.open == 0


def test_bad_body_and_no_model(setup):
    client, _, queue, runtime = setup
    assert client.post(URL, json={"messages": "x"}).status_code == 422
    runtime.llm = None
    assert client.post(URL, json=MSG).status_code == 503
    assert queue.leases == []


def test_models_lists_the_bridge_model(setup):
    client, *_ = setup
    assert client.get("/api/v1/llm/openai/v1/models").json()["data"][0]["id"] == "nanobaseAI"


def test_embeddings_pass_through_without_a_lease(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"object": "list", "data": [{"embedding": [0.1, 0.2], "index": 0}]})

    real = httpx.AsyncClient
    monkeypatch.setattr(llm_openai.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setenv("BI_EMBED_URL", "http://embed.test/v1/embeddings")
    monkeypatch.setenv("BI_EMBED_API_KEY", '"k2"')
    app = FastAPI()
    llm_openai.register_embeddings(app, lambda request: None)
    client = TestClient(app)
    r = client.post("/api/v1/llm/openai/v1/embeddings", json={"model": "x", "input": ["merhaba"], "encoding_format": None, "user": None})
    assert r.status_code == 200 and r.json()["data"][0]["embedding"] == [0.1, 0.2]
    assert seen == {"url": "http://embed.test/v1/embeddings", "auth": "Bearer k2",
                    "body": {"model": "x", "input": ["merhaba"], "encoding_format": "float"}}
    assert client.post("/api/v1/llm/openai/v1/embeddings", json={"model": "x"}).status_code == 422
    monkeypatch.delenv("BI_EMBED_URL")
    assert client.post("/api/v1/llm/openai/v1/embeddings", json={"input": ["a"]}).status_code == 503
