"""Taşma yarışı (2026-10-02): `peer_load` beklenirken aynı anda gelen okuma istekleri hepsi «yer var» gördü ve sınır
8 iken 121 istek GPU 0'a taştı. Denetim ve yer ayırma artık tek adım; eşzamanlı N istekte taşan hiçbir an CAP'i aşmaz,
biten istek yerini geri verir, BI önceliği açıksa taşan istek düşük öncelik taşır."""
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
    monkeypatch.setenv("EDITOR_OVERFLOW_URL", "http://peer:8001")
    monkeypatch.setenv("EDITOR_OVERFLOW_MODEL", "nanobaseAI")
    monkeypatch.setenv("EDITOR_OVERFLOW_CLIENTS", "editor-hermes")
    monkeypatch.setenv("EDITOR_GATEWAY_KEY", "k")
    monkeypatch.setenv("EDITOR_OVERFLOW_PRIORITY", "10")
    monkeypatch.delenv("EDITOR_OVERFLOW_ANALYSIS_CAP", raising=False)
    monkeypatch.delenv("EDITOR_OVERFLOW_ANALYSIS_BI_MAX", raising=False)
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
    def __init__(self, text="", content=b"{}"):
        self.status_code, self.text, self.content, self.headers = 200, text, content, {}


class _Peer:
    """GPU 0'ın sahtesi: /metrics BI yükünü + bize ait taşanları sayar; tamamlama isteği biraz sürer."""

    def __init__(self, G, bi: int):
        self.G, self.bi, self.ours, self.peak, self.bodies, self.local = G, bi, 0, 0, [], 0

    async def get(self, url, timeout=None):
        await asyncio.sleep(0.01)                   # ağ: bu sırada başka istekler de denetime girer
        return _Resp(text=f'vllm:num_requests_running{{engine="0"}} {self.bi + self.ours}\n'
                          'vllm:num_requests_waiting{engine="0"} 0\n')

    async def post(self, url, content=None, headers=None):
        if url.startswith("http://peer:8001"):
            self.ours += 1
            self.peak = max(self.peak, self.G.overflow_inflight)
            self.bodies.append(json.loads(content))
            await asyncio.sleep(0.05)
            self.ours -= 1
        else:
            self.local += 1
            await asyncio.sleep(0.05)
        return _Resp()


class _Req:
    def __init__(self, body: dict):
        self.headers = {"authorization": "Bearer k"}
        self.client = None                          # analiz işçisi (etkileşimli istemci değil)
        self._body = json.dumps(body).encode()

    async def body(self):
        return self._body


def _wire(G, monkeypatch, bi: int, local_up: bool = False) -> _Peer:
    peer = _Peer(G, bi)
    monkeypatch.setattr(G, "http", peer)
    monkeypatch.setattr(G, "_is_running", lambda a: local_up)

    async def healthy(_a):
        await asyncio.sleep(0.005)
        return local_up

    async def started(_a):
        return None

    monkeypatch.setattr(G, "_healthy", healthy)
    monkeypatch.setattr(G, "ensure_running", started)
    return peer


def _flood(G, n: int):
    async def run():
        reqs = [G.proxy("chat/completions", _Req({"model": "book-director", "messages": []})) for _ in range(n)]
        return await asyncio.gather(*reqs)
    return asyncio.run(run())


def test_concurrent_spill_never_exceeds_cap(G, monkeypatch):
    peer = _wire(G, monkeypatch, bi=0)
    _flood(G, 120)
    assert len(peer.bodies) >= G.ANALYSIS_CAP       # yer varken taşıyor
    assert peer.peak <= G.ANALYSIS_CAP              # eskiden 121/8
    assert G.overflow_inflight == 0                 # biten istek yerini geri verdi
    assert G.ALIASES["book-director"].inflight == 0


def test_spill_carries_low_priority(G, monkeypatch):
    peer = _wire(G, monkeypatch, bi=0)
    _flood(G, 4)
    assert peer.bodies and all(b["priority"] == 10 and b["model"] == "nanobaseAI" for b in peer.bodies)


def test_no_priority_field_when_policy_off(G, monkeypatch):
    peer = _wire(G, monkeypatch, bi=0)
    monkeypatch.setattr(G, "OVERFLOW_PRIORITY", 0)
    _flood(G, 4)
    assert peer.bodies and all("priority" not in b for b in peer.bodies)   # vLLM fcfs'te sıfır dışını reddeder


def test_busy_bi_gets_no_spill_even_under_flood(G, monkeypatch):
    peer = _wire(G, monkeypatch, bi=G.ANALYSIS_BI_MAX + 1)
    _flood(G, 60)
    assert peer.bodies == [] and peer.local == 60
    assert G.overflow_inflight == 0


def test_reserved_but_not_yet_arrived_does_not_hide_bi(G, monkeypatch):
    """Ölçüm: BI 3 istek, bizim 0. Ardından 5 yer ayrıldı (eşe henüz varmadı). Eski hesap 3-5=-2 ≤ 2 diye taşırdı."""
    G._peer_load, G._peer_ours = (G.time.time(), 3), 0
    G.overflow_inflight = 5
    assert G._bi_load(3) == 3
    assert not G._reserve_overflow(3)
    assert G.overflow_inflight == 5
