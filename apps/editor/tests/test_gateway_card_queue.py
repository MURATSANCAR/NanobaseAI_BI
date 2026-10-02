"""Kart sırası (2026-10-01): aynı kartta modeller sırayla açılır, yer bekleyen modele yol açılır, iş başındaki model
atılmaz. Ölçülen olaylar: okuma sürerken resim modeli 40 dk yer bulamadı; iki model (%90 + %62) aynı anda açılıp
biri bellek aşımıyla düştü; resim ile ana model her resimde yer değiştirdi."""
from __future__ import annotations

import asyncio
import importlib
import sys
import time
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
    monkeypatch.setenv("EDITOR_YIELD_MAX_SEC", "1")
    sys.modules.pop("editor.gateway", None)
    g = importlib.import_module("editor.gateway")
    g.WAITING.clear()
    for a in g.ALIASES.values():
        a.inflight, a.last_used = 0, 0.0
    yield g
    g.WAITING.clear()
    sys.modules.pop("editor.gateway", None)


def _running(G, monkeypatch, names):
    up = set(names)
    monkeypatch.setattr(G, "_is_running", lambda a: a.name in up)
    return up


def test_waiting_model_stops_feeding_the_card(G, monkeypatch):
    director, image = G.ALIASES["book-director"], G.ALIASES["book-image"]
    _running(G, monkeypatch, {"book-director"})
    assert not G._must_yield(director)
    G.WAITING.add(image.name)                       # resim modeli kartta yer bekliyor
    assert G._must_yield(director)                  # ana modele yeni iş verilmez, kart boşalır


def test_main_model_does_not_evict_a_working_image_model(G, monkeypatch):
    director, image = G.ALIASES["book-director"], G.ALIASES["book-image"]
    _running(G, monkeypatch, {"book-image"})
    image.last_used = time.time()                   # resimler arasında: az önce kullanıldı
    assert G._held(image, director, time.time())
    assert G._must_yield(director)                  # ana model kapalı, kartı iş başındaki resim modeli tutuyor
    image.last_used = time.time() - G.EVICT_GRACE - 1
    assert not G._held(image, director, time.time())
    assert not G._must_yield(director)              # resim işi bitti: ana model kartı geri alır


def test_main_model_is_never_held(G):
    director, image = G.ALIASES["book-director"], G.ALIASES["book-image"]
    director.last_used = time.time()
    assert not G._held(director, image, time.time())  # sürekli açık model yer verir, bekçi geri kaldırır


def test_yielding_request_spills_to_peer_when_bi_idle(G, monkeypatch):
    director, image = G.ALIASES["book-director"], G.ALIASES["book-image"]
    _running(G, monkeypatch, {"book-director"})
    G.WAITING.add(image.name)

    async def no(*_a):
        return False

    async def load():
        return 0

    monkeypatch.setattr(G, "_should_overflow", no)
    monkeypatch.setattr(G, "peer_load", load)
    assert asyncio.run(G._route(director, object())) is True


def test_yielding_request_waits_when_peer_busy_then_bounded(G, monkeypatch):
    director, image = G.ALIASES["book-director"], G.ALIASES["book-image"]
    _running(G, monkeypatch, {"book-director"})
    G.WAITING.add(image.name)

    async def no(*_a):
        return False

    async def load():
        return 9                                    # BI meşgul: taşma yok

    monkeypatch.setattr(G, "_should_overflow", no)
    monkeypatch.setattr(G, "peer_load", load)
    t0 = time.time()
    assert asyncio.run(G._route(director, object())) is False   # YIELD_MAX (1 sn) sonra kendi yoluna
    assert time.time() - t0 >= 1


def test_same_card_starts_one_at_a_time(G, monkeypatch):
    """İki model aynı anda açılmak isterse ikincisi, ilki sağlıklı olana kadar başlamaz."""
    events = []

    async def start(a):
        events.append(("start", a.name))
        await asyncio.sleep(0.05)
        events.append(("ready", a.name))

    monkeypatch.setattr(G, "_start_locked", start)
    monkeypatch.setattr(G, "_is_running", lambda a: False)

    async def unhealthy(_a):
        return False

    monkeypatch.setattr(G, "_healthy", unhealthy)
    # Gerçek modülün tek fonksiyonu: sahte modül sys.modules'tan geri alınsa da `editor.foundation` paket
    # özniteliği sahte kalır ve sonraki testleri bozar (test_portal_read bununla düşüyordu).
    from editor import foundation
    monkeypatch.setattr(foundation, "assert_enabled", lambda: None)

    async def both():
        await asyncio.gather(G.ensure_running(G.ALIASES["book-image"]),
                             G.ensure_running(G.ALIASES["book-vision-deep"]))

    asyncio.run(both())
    assert [e[0] for e in events] == ["start", "ready", "start", "ready"]
    assert not G.WAITING
