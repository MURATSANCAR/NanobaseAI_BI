"""Çağıran gidince modele giden istek iptal edilir (2026-10-06): 182 derin sayfa taraması istemci zaman aşımına kadar
model sırasında bekledi; çağıran sayfayı yeniden gönderirken gateway eski isteği tutuyor, model aynı sayfayı kimse
için okuyordu. Çağıran yerindeyse cevap aynen döner."""
from __future__ import annotations

import asyncio
import importlib
import json
import sys
import types
from pathlib import Path

import pytest


@pytest.fixture()
def G(monkeypatch):
    monkeypatch.setitem(sys.modules, "pynvml", types.SimpleNamespace(nvmlInit=lambda: None))
    dmod = types.ModuleType("docker")
    dmod.from_env = lambda: None
    dtypes = types.ModuleType("docker.types")
    dtypes.DeviceRequest = dtypes.Ulimit = object
    dmod.types = dtypes
    monkeypatch.setitem(sys.modules, "docker", dmod)
    monkeypatch.setitem(sys.modules, "docker.types", dtypes)
    monkeypatch.setenv("EDITOR_MODELS_YAML", str(Path(__file__).resolve().parents[1] / "deploy" / "models.yaml"))
    monkeypatch.setenv("EDITOR_GATEWAY_KEY", "k")
    monkeypatch.setenv("EDITOR_DISCONNECT_POLL_SEC", "0.01")
    monkeypatch.delenv("EDITOR_OVERFLOW_URL", raising=False)
    sys.modules.pop("editor.gateway", None)
    g = importlib.import_module("editor.gateway")
    from editor import foundation
    monkeypatch.setattr(foundation, "assert_enabled", lambda: None)
    g.WAITING.clear()
    for a in g.ALIASES.values():
        a.inflight, a.last_used = 0, 0.0
    yield g
    g.WAITING.clear()
    sys.modules.pop("editor.gateway", None)


class _Resp:
    status_code, content, headers, text = 200, b'{"ok": 1}', {}, ""


class _Upstream:
    def __init__(self, delay: float):
        self.delay, self.cancelled, self.done = delay, 0, 0

    async def post(self, url, content=None, headers=None):
        try:
            await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        self.done += 1
        return _Resp()


class _Req:
    def __init__(self, gone_after: float | None):
        self.headers = {"authorization": "Bearer k"}
        self.client = None
        self._body = json.dumps({"model": "book-vision-deep", "messages": []}).encode()
        self._gone_after = gone_after
        self._t0 = None

    async def body(self):
        return self._body

    async def is_disconnected(self):
        loop = asyncio.get_running_loop()
        self._t0 = self._t0 or loop.time()
        return self._gone_after is not None and loop.time() - self._t0 >= self._gone_after


def _wire(G, monkeypatch, delay: float) -> _Upstream:
    up = _Upstream(delay)
    monkeypatch.setattr(G, "http", up)
    monkeypatch.setattr(G, "_is_running", lambda a: True)

    async def ok(*_a, **_k):
        return None

    async def no_route(*_a, **_k):
        return False

    async def same_twin(a, payload):
        return a

    monkeypatch.setattr(G, "ensure_running", ok)
    monkeypatch.setattr(G, "_route", no_route)
    monkeypatch.setattr(G, "_cpu_twin", same_twin)
    return up


def test_upstream_cancelled_when_client_gone(G, monkeypatch):
    up = _wire(G, monkeypatch, delay=5.0)
    r = asyncio.run(G.proxy("chat/completions", _Req(gone_after=0.05)))
    assert r.status_code == 499 and up.cancelled == 1 and up.done == 0
    assert G.ALIASES["book-vision-deep"].inflight == 0          # yer geri verildi


def test_answer_passes_when_client_stays(G, monkeypatch):
    up = _wire(G, monkeypatch, delay=0.05)
    r = asyncio.run(G.proxy("chat/completions", _Req(gone_after=None)))
    assert r.status_code == 200 and r.body == b'{"ok": 1}' and up.done == 1 and up.cancelled == 0
    assert G.ALIASES["book-vision-deep"].inflight == 0
