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
    for d in (g.WAITING_SINCE, g.WAITING_INTERACTIVE, g.YIELDING, g.TURN_START):
        d.clear()
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


# --- Adil sıra (2026-10-02): dört kitap paralel okunurken derin görsel model hiç boşalmadı; OCR ve embedding
# 25+ dk aç kaldı (90 dk'da 5 OCR çağrısı). Bekleyen model HOLD_MAX sonra sırasını alır; iş kesilmez.
class _Clock:
    def __init__(self, t=10_000.0):
        self.t = t

    def time(self):
        return self.t


def test_busy_holder_cannot_starve_a_waiting_model(G, monkeypatch):
    """Açlık: görsel model her an yeni iş alıyor (hiç boş değil). OCR beklemeye başladıktan en geç HOLD_MAX (+1 adım)
    sonra yoluna devam eder; o andan itibaren görsel modele yeni iş verilmez (drain)."""
    clock = _Clock()
    monkeypatch.setattr(G, "time", clock)
    vision, ocr = G.ALIASES["book-vision-deep"], G.ALIASES["book-ocr-dots"]
    _running(G, monkeypatch, {"book-vision-deep"})
    G.TURN_START[vision.name] = clock.t
    vision.inflight = 9
    begun = clock.t
    G._wait_begin(ocr, interactive=False)
    proceeded = None
    for _ in range(1000):
        clock.t += 5
        vision.last_used = clock.t                 # sürekli yeni iş
        if not G._must_yield(ocr):
            proceeded = clock.t
            break
    assert proceeded is not None and proceeded - begun <= G.HOLD_MAX + 5
    G._wait_end(ocr, proceeding=True)
    assert ocr.name in G.WAITING_SINCE            # yer açılana kadar sıra kaydı durur
    G.WAITING.add(ocr.name)                       # ensure_running: yer bekliyor
    assert G._must_yield(vision)                  # görsel modele yeni iş yok, elindekiler biter
    vision.inflight = 0
    assert not G._held(vision, ocr, clock.t)      # boşalınca kartı bırakır (EVICT_GRACE beklenmez)


def test_new_holder_keeps_the_card_at_least_one_hold_no_thrash(G, monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(G, "time", clock)
    vision, ocr = G.ALIASES["book-vision-deep"], G.ALIASES["book-ocr-dots"]
    _running(G, monkeypatch, {"book-ocr-dots"})
    G.TURN_START[ocr.name] = clock.t - 30          # OCR sırasını 30 sn önce aldı
    ocr.last_used = clock.t
    G.WAITING_SINCE[vision.name] = clock.t - G.HOLD_MAX - 100   # görsel model çoktandır bekliyor
    assert G._held(ocr, vision, clock.t) and G._must_yield(vision)
    G.TURN_START[ocr.name] = clock.t - G.HOLD_MAX  # bir HOLD süresi doldu: sıra geri döner
    assert not G._held(ocr, vision, clock.t) and not G._must_yield(vision)


def test_interactive_wait_has_a_shorter_hold(G, monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(G, "time", clock)
    vision, rer = G.ALIASES["book-vision-deep"], G.ALIASES["book-reranker"]
    _running(G, monkeypatch, {"book-vision-deep"})
    vision.last_used = clock.t
    G.WAITING_SINCE[rer.name] = clock.t - G.INTERACTIVE_HOLD_MAX - 1
    assert G._must_yield(rer)                      # toplu bekleyiş: HOLD_MAX dolmadı
    G.WAITING_INTERACTIVE[rer.name] = clock.t - G.INTERACTIVE_HOLD_MAX - 1
    assert not G._must_yield(rer)                  # etkileşimli: kısa süre yeter
    assert G.INTERACTIVE_HOLD_MAX < G.HOLD_MAX


def test_route_records_wait_and_forgets_it_when_request_leaves(G, monkeypatch):
    vision, ocr = G.ALIASES["book-vision-deep"], G.ALIASES["book-ocr-dots"]
    state = {"n": 0}

    def must_yield(a):
        state["n"] += 1
        assert a.name not in G.WAITING_SINCE or G.YIELDING[a.name] == 1
        return state["n"] < 2

    async def no(*_a):
        return False

    monkeypatch.setattr(G, "_must_yield", must_yield)
    monkeypatch.setattr(G, "_should_overflow", no)
    monkeypatch.setattr(G, "_drain_overflow", no)

    async def fast(_s):
        return None

    monkeypatch.setattr(G.asyncio, "sleep", fast)
    assert asyncio.run(G._route(ocr, object())) is False       # bekledi, sonra modeli açmaya gidiyor
    assert ocr.name in G.WAITING_SINCE and G.YIELDING[ocr.name] == 0
    G._wait_forget(ocr, served=True)
    assert ocr.name not in G.WAITING_SINCE


# --- CPU eşi ve beklemeyen istek (Kitaba sor) ---------------------------------------------------------------------
def test_small_embedding_goes_to_cpu_twin_while_gpu_copy_is_down(G, monkeypatch):
    emb, cpu = G.ALIASES["book-embedding"], G.ALIASES["book-embedding-cpu"]
    assert emb.cpu_twin == cpu.name and cpu.gpu < 0 and cpu.always_on
    up = _running(G, monkeypatch, set())

    async def healthy(_a):
        return True

    monkeypatch.setattr(G, "_healthy", healthy)
    payload = {"model": emb.name, "input": ["soru"]}
    assert asyncio.run(G._cpu_twin(emb, payload)) is cpu and payload["model"] == cpu.name
    batch = {"model": emb.name, "input": ["p"] * 64}
    assert asyncio.run(G._cpu_twin(emb, batch)) is emb and batch["model"] == emb.name   # toplu dizinleme GPU'da
    up.add(emb.name)
    assert asyncio.run(G._cpu_twin(emb, {"model": emb.name, "input": "soru"})) is emb   # GPU kopyası açık
    G.WAITING.add("book-vision-deep")             # kart boşaltılıyor: GPU kopyası açık ama yeni iş almaz
    assert asyncio.run(G._cpu_twin(emb, {"model": emb.name, "input": "soru"})) is cpu


def test_cpu_model_is_created_without_a_gpu(G, monkeypatch):
    seen = {}

    class _Dk:
        class containers:
            @staticmethod
            def create(image, cmd, **kw):
                seen.update(kw, image=image)

    monkeypatch.setattr(G, "dk", _Dk)
    monkeypatch.setattr(G, "Ulimit", lambda **kw: kw)
    monkeypatch.setattr(G, "DeviceRequest", lambda **kw: kw)
    G._create(G.ALIASES["book-embedding-cpu"])
    assert "device_requests" not in seen and seen["nano_cpus"] == 32 * 10**9
    G._create(G.ALIASES["book-embedding"])
    assert "device_requests" in seen


def test_no_wait_request_is_refused_when_model_is_not_up(G, monkeypatch):
    rer, vision = G.ALIASES["book-reranker"], G.ALIASES["book-vision-deep"]
    _running(G, monkeypatch, {"book-vision-deep"})
    vision.last_used = time.time()
    monkeypatch.setattr(G, "gpu_mem", lambda i: (5 * G.GIB, 95 * G.GIB))
    started = []
    monkeypatch.setattr(G, "_background_start", lambda a: started.append(a.name) or asyncio.sleep(0))
    req = types.SimpleNamespace(headers={}, client=None)
    assert asyncio.run(G._ready_now(rer, req)) is False and started == []   # kart dolu: kimse atılmaz
