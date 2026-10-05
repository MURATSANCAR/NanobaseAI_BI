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
    monkeypatch.setenv("EDITOR_OVERFLOW_CLIENTS", "editor-cards")
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


def test_main_model_just_ready_is_held_for_its_turn(G, monkeypatch):
    """2026-10-04 23:32: ana model 120 sn'lik soğuk açılışı bitirdi (23:32:14), 5 sn sonra bekleyen derin görsel
    model için yine durduruldu. Sürekli açık model de iş başındayken sırasını kullanır."""
    director, deep = G.ALIASES["book-director"], G.ALIASES["book-vision-deep"]
    _running(G, monkeypatch, {"book-director"})
    now = time.time()
    director.last_used = G.TURN_START[director.name] = now - 5           # 5 sn önce hazır oldu
    G.WAITING_SINCE[deep.name] = now - 160                                # derin model 23:29:40'tan beri bekliyor
    assert G._held(director, deep, now)
    assert G._must_yield(deep)               # derin model kartı istemez, sırasını bekler; ana model beslenir
    assert not G._must_yield(director)


def test_main_model_gives_way_when_the_turn_is_over(G, monkeypatch):
    director, deep = G.ALIASES["book-director"], G.ALIASES["book-vision-deep"]
    _running(G, monkeypatch, {"book-director"})
    now = time.time()
    director.last_used = now                                              # sürekli iş alıyor
    G.TURN_START[director.name] = now - G.HOLD_MAX - 1                    # sırasını kullandı
    G.WAITING_SINCE[deep.name] = now - G.HOLD_MAX + 30                    # bekleyen henüz HOLD_MAX beklemedi
    assert G._held(director, deep, now)
    G.WAITING_SINCE[deep.name] = now - G.HOLD_MAX - 1                     # bekleyiş sınırı doldu
    assert not G._held(director, deep, now)
    assert not G._must_yield(deep)


def test_idle_main_model_gives_way_at_once(G, monkeypatch):
    director, image = G.ALIASES["book-director"], G.ALIASES["book-image"]
    now = time.time()
    director.last_used = now - G.EVICT_GRACE - 1                          # iş yok: kartı hemen bırakır
    G.TURN_START[director.name] = now - 10
    assert not G._held(director, image, now)


def test_make_room_does_not_evict_main_model_whose_requests_wait(G, monkeypatch):
    """Ana modelin istekleri kartta yer bekleyen model yüzünden `_route`'ta beklerken `_serving` 0 görünür; yer
    açma onu yine de atmaz, sırası bitmeden kart ona aittir."""
    director, deep = G.ALIASES["book-director"], G.ALIASES["book-vision-deep"]
    _running(G, monkeypatch, {"book-director"})
    now = time.time()
    director.last_used = G.TURN_START[director.name] = now - 5
    director.inflight = G.YIELDING[director.name] = 12                    # hepsi sırada bekliyor
    assert G._serving(director) == 0
    G.WAITING_SINCE[deep.name] = now - 160
    stopped = []

    async def stop(o, why):
        stopped.append(o.name)

    monkeypatch.setattr(G, "_stop", stop)
    monkeypatch.setattr(G, "_orphans", lambda: [])
    monkeypatch.setattr(G, "gpu_mem", lambda i: (10 * G.GIB, 94 * G.GIB))
    monkeypatch.setattr(G, "gpu_holders", lambda i: [])
    with pytest.raises(G.HTTPException) as e:
        asyncio.run(G._make_room_inner(deep, 80 * G.GIB, time.time() - 1))
    assert e.value.status_code == 503 and stopped == []


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


def test_cpu_twin_request_carries_the_twins_model_name_upstream(G, monkeypatch):
    """2026-10-05: gövde eski baytlarla gidiyordu; CPU eşi «unknown model book-embedding» (404) dedi."""
    import json
    emb, cpu = G.ALIASES["book-embedding"], G.ALIASES["book-embedding-cpu"]
    _running(G, monkeypatch, {cpu.name})

    async def ok(*_a, **_k):
        return True

    async def none(*_a, **_k):
        return None

    async def no(*_a, **_k):
        return False

    sent = {}

    class Http:
        async def post(self, url, content=None, headers=None):
            sent["url"], sent["body"] = url, json.loads(content)
            return types.SimpleNamespace(content=b"{}", status_code=200, headers={})

    monkeypatch.setattr(G, "_healthy", ok)
    monkeypatch.setattr(G, "check_enabled", none)
    monkeypatch.setattr(G, "ensure_running", none)
    monkeypatch.setattr(G, "_route", no)
    monkeypatch.setattr(G, "_auth", lambda req, internal=False: None)
    monkeypatch.setattr(G, "http", Http())

    class Req:
        headers = {}

        async def body(self):
            return json.dumps({"model": emb.name, "input": ["soru"]}).encode()

    asyncio.run(G.proxy("embeddings", Req()))
    assert sent["body"]["model"] == cpu.name and sent["url"].startswith(cpu.upstream)


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


def test_requests_waiting_their_turn_do_not_keep_the_holder_busy(G, monkeypatch):
    """Ölçüldü 2026-10-02: derin görsel modelin işi bitti, ona gelen yeni istekler sırasını bekliyor (yield), embedding
    kartta yer bekliyor. Bekleyen istekler kartı kullanmaz: görsel model boşta sayılır ve yer açılır."""
    vision, emb = G.ALIASES["book-vision-deep"], G.ALIASES["book-embedding"]
    _running(G, monkeypatch, {"book-vision-deep"})
    vision.last_used = time.time() - G.EVICT_GRACE - 1
    vision.inflight = 3                              # _route'ta bekleyen üç istek
    G.YIELDING[vision.name] = 3
    assert G._serving(vision) == 0 and not G._held(vision, emb, time.time())
    vision.inflight = 4                              # biri gerçekten sunuluyor
    assert G._serving(vision) == 1


def test_requested_stop_waits_while_other_books_use_the_model(G, monkeypatch):
    """Ölçüldü 2026-10-03: bir kitabın release_models'i derin görsel modeli öbür kitapların istekleri sürerken
    durduruyordu (%29 «500»). İş başındaki model durdurulmaz; boşta ise durur."""
    vision = G.ALIASES["book-vision-deep"]
    _running(G, monkeypatch, {"book-vision-deep"})
    stopped = []

    async def fake_stop(a, why):
        stopped.append((a.name, why))
    monkeypatch.setattr(G, "_stop", fake_stop)
    monkeypatch.setattr(G, "_auth", lambda req, internal=False: None)
    vision.inflight = 2
    out = asyncio.run(G.internal_stop("book-vision-deep", object()))
    assert out["deferred"] and stopped == []
    vision.inflight = 0
    out = asyncio.run(G.internal_stop("book-vision-deep", object()))
    assert stopped == [("book-vision-deep", "requested")] and out["running"] is False
