"""Analiz taşması (2026-10-01): okuma isteği GPU 0'daki eşe yalnız BI orada boşken ve sınır içinde gider."""
from __future__ import annotations

import asyncio
import importlib
import sys
import types
from pathlib import Path

import pytest


@pytest.fixture()
def G(monkeypatch):
    # GPU/docker'sız içe aktarma: modül açılışta NVML ve docker istemcisi kuruyor.
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
    monkeypatch.delenv("EDITOR_OVERFLOW_ANALYSIS_CAP", raising=False)
    monkeypatch.delenv("EDITOR_OVERFLOW_ANALYSIS_BI_MAX", raising=False)
    sys.modules.pop("editor.gateway", None)
    g = importlib.import_module("editor.gateway")
    yield g
    sys.modules.pop("editor.gateway", None)


def _setup(G, monkeypatch, *, up=True, local=0, spilled=0, peer=0):
    a = G.ALIASES["book-director"]
    a.inflight = local + 1                      # proxy bu isteği saymış olur
    G.overflow_inflight = spilled
    monkeypatch.setattr(G, "_is_running", lambda _a: up)

    async def healthy(_a):
        return up

    async def load():
        return peer

    monkeypatch.setattr(G, "_healthy", healthy)
    monkeypatch.setattr(G, "peer_load", load)
    monkeypatch.setattr(G, "_client_name", lambda _r: "")
    return a


def _ask(G, a):
    return asyncio.run(G._should_overflow(a, object()))


def test_defaults(G):
    assert G.ANALYSIS_CAP == 8 and G.ANALYSIS_BI_MAX == 2


def test_local_free_stays_local(G, monkeypatch):
    assert not _ask(G, _setup(G, monkeypatch, local=0, spilled=0, peer=0))


def test_local_busy_and_bi_idle_spills(G, monkeypatch):
    assert _ask(G, _setup(G, monkeypatch, local=5, spilled=1, peer=1))


def test_bi_busy_blocks_spill(G, monkeypatch):
    # eşte 6 istek, 1'i bizim → BI'ın kendi yükü 5 > 2
    assert not _ask(G, _setup(G, monkeypatch, local=5, spilled=1, peer=6))


def test_cap_blocks_spill(G, monkeypatch):
    assert not _ask(G, _setup(G, monkeypatch, local=20, spilled=8, peer=8))


def test_local_down_spills_instead_of_cold_start(G, monkeypatch):
    assert _ask(G, _setup(G, monkeypatch, up=False, local=0, spilled=0, peer=0))


def test_peer_unreadable_stays_local(G, monkeypatch):
    assert not _ask(G, _setup(G, monkeypatch, local=5, spilled=0, peer=None))


def test_other_alias_never_spills(G, monkeypatch):
    _setup(G, monkeypatch, local=5, peer=0)
    other = next(x for n, x in G.ALIASES.items() if n != "book-director")
    other.inflight = 9
    assert not _ask(G, other)


def test_interactive_rule_unchanged(G, monkeypatch):
    a = _setup(G, monkeypatch, up=True, local=5, peer=0)
    monkeypatch.setattr(G, "_client_name", lambda _r: "editor-hermes")
    assert not _ask(G, a)                       # yönetici ayaktayken etkileşimli soru yerelde kalır


def test_cap_zero_disables(G, monkeypatch):
    a = _setup(G, monkeypatch, up=False, peer=0)
    monkeypatch.setattr(G, "ANALYSIS_CAP", 0)
    assert not _ask(G, a)
