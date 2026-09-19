"""LlmClient against a real HTTP server that misbehaves on purpose: refuses with 429, answers late,
streams, goes silent. Loopback only — the provider cannot be asked to fail on demand."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from semantic_layer.candidates.llm_client import LlmCancelled, LlmClient


class Provider:
    def __init__(self):
        self.script: list[dict] = []          # one entry per request, consumed in order; last one repeats
        self.requests: list[dict] = []
        self.lock = threading.Lock()
        provider = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("content-length", "0"))) or b"{}")
                with provider.lock:
                    provider.requests.append({"body": body, "auth": self.headers.get("authorization"), "at": time.monotonic()})
                    step = provider.script.pop(0) if len(provider.script) > 1 else provider.script[0]
                time.sleep(step.get("delay", 0))
                status = step.get("status", 200)
                if status != 200:
                    payload = json.dumps({"status": status, "detail": "dolu"}).encode()
                    self.send_response(status)
                    for k, v in step.get("headers", {}).items():
                        self.send_header(k, v)
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                text = step.get("text", "TAMAM")
                if body.get("stream"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    try:
                        self.wfile.write(b": keep-alive\n\n")
                        for piece in [text[i:i + 3] for i in range(0, len(text), 3)]:
                            chunk = {"choices": [{"delta": {"content": piece}, "finish_reason": None}]}
                            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                            self.wfile.flush()
                            time.sleep(step.get("gap", 0))
                        self.wfile.write(b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    return
                payload = json.dumps({"choices": [{"message": {"content": text}, "finish_reason": "stop"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


class Observer:
    def __init__(self):
        self.events: list[tuple] = []

    def pressure(self, status, retry_after):
        self.events.append(("pressure", status, retry_after))

    def success(self):
        self.events.append(("success",))


@pytest.fixture
def provider():
    p = Provider()
    yield p
    p.close()


@pytest.mark.parametrize("stream", [False, True])
def test_a_plain_answer(provider, stream):
    provider.script = [{"text": "Merhaba dünya, çğıöşü"}]
    client = LlmClient(provider.base, "m", key="anahtar", timeout=10, extra={"chat_template_kwargs": {"thinking": False}}, stream=stream)
    assert client.chat([{"role": "user", "content": "selam"}], max_tokens=16) == "Merhaba dünya, çğıöşü"
    sent = provider.requests[0]
    assert sent["auth"] == "Bearer anahtar" and sent["body"]["stream"] is stream
    assert sent["body"]["chat_template_kwargs"] == {"thinking": False} and sent["body"]["max_tokens"] == 16


@pytest.mark.parametrize("stream", [False, True])
def test_a_refusal_is_waited_out_and_reported(provider, stream):
    provider.script = [{"status": 429, "headers": {"Retry-After": "1"}}, {"status": 504}, {"text": "sonunda"}]
    client = LlmClient(provider.base, "m", timeout=60, stream=stream)
    client.observer = Observer()
    t0 = time.monotonic()
    assert client.chat([{"role": "user", "content": "x"}]) == "sonunda"
    assert len(provider.requests) == 3 and time.monotonic() - t0 >= 3.5
    assert client.observer.events == [("pressure", 429, 1.0), ("pressure", 504, None), ("success",)]


def test_refused_calls_do_not_all_come_back_in_the_same_instant(provider):
    provider.script = [{"status": 429}] * 6 + [{"text": "ok"}]
    clients = [LlmClient(provider.base, "m", timeout=60) for _ in range(6)]
    threads = [threading.Thread(target=c.chat, args=([{"role": "user", "content": "x"}],)) for c in clients]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    retries = sorted(r["at"] for r in provider.requests[6:12])
    assert len(retries) == 6 and retries[-1] - retries[0] > 0.3, "every retry landed together"


def test_a_request_that_is_wrong_is_not_retried(provider):
    provider.script = [{"status": 404}]
    client = LlmClient(provider.base, "m", timeout=30)
    client.observer = Observer()
    with pytest.raises(RuntimeError, match="LLM HTTP 404"):
        client.chat([{"role": "user", "content": "x"}])
    assert len(provider.requests) == 1 and client.observer.events == []


def test_refusals_stop_at_the_clients_own_deadline(provider):
    provider.script = [{"status": 529}]
    client = LlmClient(provider.base, "m", timeout=4)
    t0 = time.monotonic()
    with pytest.raises(RuntimeError, match="LLM HTTP 529"):
        client.chat([{"role": "user", "content": "x"}])
    assert time.monotonic() - t0 < 8


@pytest.mark.parametrize("stream", [False, True])
def test_the_whole_answer_has_a_deadline(provider, stream):
    provider.script = [{"delay": 5, "text": "geç"}]
    client = LlmClient(provider.base, "m", timeout=1.5, stream=stream)
    t0 = time.monotonic()
    with pytest.raises(httpx.TimeoutException):
        client.chat([{"role": "user", "content": "x"}])
    assert time.monotonic() - t0 < 4


@pytest.mark.parametrize("stream", [False, True])
def test_a_call_in_flight_can_be_withdrawn(provider, stream):
    provider.script = [{"delay": 8, "text": "geç"}]
    client = LlmClient(provider.base, "m", timeout=60, stream=stream)
    cancel = threading.Event()
    threading.Timer(0.5, cancel.set).start()
    t0 = time.monotonic()
    with pytest.raises(LlmCancelled):
        client.chat([{"role": "user", "content": "x"}], cancel=cancel)
    assert time.monotonic() - t0 < 3


def test_a_stream_that_goes_silent_is_noticed(provider, monkeypatch):
    monkeypatch.setenv("LLM_STREAM_IDLE_SEC", "1")
    provider.script = [{"text": "abcdefghi", "gap": 3}]
    client = LlmClient(provider.base, "m", timeout=60, stream=True)
    t0 = time.monotonic()
    with pytest.raises(httpx.TimeoutException):
        client.chat([{"role": "user", "content": "x"}])
    assert time.monotonic() - t0 < 10, "waited the whole timeout on a stream that had stopped"


def test_streaming_is_off_unless_asked_for(provider, monkeypatch):
    monkeypatch.delenv("LLM_STREAM", raising=False)
    assert LlmClient(provider.base, "m").stream is False
    monkeypatch.setenv("LLM_STREAM", "1")
    assert LlmClient(provider.base, "m").stream is True


def test_an_unreachable_provider_is_said_so():
    client = LlmClient("http://127.0.0.1:9", "m", timeout=5)
    with pytest.raises(RuntimeError, match="unreachable after 3 attempts"):
        client.chat([{"role": "user", "content": "x"}])
