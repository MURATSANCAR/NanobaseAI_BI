"""Local Model Gateway (NIHAI-KARAR.md §2, §6).

OpenAI-compatible front for the editor's models. Callers name an alias
(book-director, book-vision-fast, ...); the real model never leaves this
process except through the internal provenance endpoint the workers use.

Each alias is one vLLM container. The gateway creates it from models.yaml,
starts it on the first request, and stops it after `idle_stop_sec` without
traffic, so the editor holds no GPU memory while idle. When a card is short
of memory it stops idle *editor* models on that card first; containers that
are not labelled `editor.model` are never touched.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import socket
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import docker
import httpx
import pynvml
import yaml
from docker.types import DeviceRequest, Ulimit
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .chat_params import without_thinking

log = logging.getLogger("editor.gateway")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

MODELS_YAML = Path(os.environ.get("EDITOR_MODELS_YAML", "/app/deploy/models.yaml"))
MANIFEST = Path(os.environ.get("EDITOR_ROOT", "/data/editor")) / "models" / "MANIFEST.json"
HOST_ROOT = os.environ.get("EDITOR_HOST_ROOT", "/data/editor")
PUBLIC_KEY = os.environ.get("EDITOR_GATEWAY_KEY", "")
INTERNAL_KEY = os.environ.get("EDITOR_GATEWAY_INTERNAL_KEY", "")
NETWORK = os.environ.get("EDITOR_NETWORK", "editor-net")
GIB = 1024**3
MEM_MARGIN = int(float(os.environ.get("EDITOR_GPU_MARGIN_GIB", "1.5")) * GIB)
FIT_TOGETHER = 0.92          # models.yaml: aynı karttaki modellerin payları toplamı bunu aşmıyorsa birlikte sığar
# Kart sırası (2026-10-01): okuma sürerken resim modeli 40 dk yer bulamadı (ana model hiç boşalmadı), iki model aynı
# anda açılıp bellek aşımıyla düştü, resim ile ana model her resimde yer değiştirdi. Kurallar:
#  - aynı kartta modeller sırayla açılır (kart kilidi; bir model sağlıklı olana kadar ikincisi başlamaz);
#  - kartta yer bekleyen model varsa kartı tutan modele yeni iş beslenmez: istek eşe taşar ya da bekler;
#  - son EVICT_GRACE saniyede iş görmüş (ya da açılmakta olan) model kartından atılmaz; resim üretiminin adımları
#    arasında yer değiştirme olmaz. Ana model o sırada isteklerini eşe taşır ya da bekler.
#  - sürekli açık ana model de bu korumadan yararlanır (2026-10-05). Eskiden muaftı: 2026-10-04 23:24–23:32 kart
#    1'de derin görsel → gömme → ana model → derin görsel takası oldu; ana model 23:32:14'te 120 sn'lik soğuk açılışı
#    bitirdi, 5 sn sonra (23:32:19) bekleyen derin görsel model için yine durduruldu. O 5 sn'de ana modelin
#    istekleri kartta yer bekleyen model yüzünden `_route`'ta bekliyordu (`_must_yield`), `_serving` 0 göründü ve
#    muafiyet onu «boşta» saydı. Artık ana model de iş başındayken (son EVICT_GRACE sn) sırası bitene kadar
#    (`_turn_over`: bekleyen HOLD_MAX bekledi, ana model sırasını HOLD_MAX kullandı) kartta kalır; boştaysa hemen
#    yer verir. Yeni açılan model en az bir sıra süresi kartta kalır, bekleyen modelin bekleyişi HOLD_MAX'la sınırlı.
EVICT_GRACE = int(os.environ.get("EDITOR_EVICT_GRACE_SEC", "120"))
YIELD_MAX = int(os.environ.get("EDITOR_YIELD_MAX_SEC", "1500"))     # bekleme bundan uzarsa eski davranış;
#   istemci zaman aşımlarının altında (stüdyo 1800 sn, okuma 3600 sn)
GPU_LOCKS: dict[int, asyncio.Lock] = {}
# Bakım anahtarı sorgusu (2026-10-03): her vekil istek kendi iş parçacığından `assert_enabled` ile veritabanına
# gidiyordu; aynı anda gelen onlarca istek (okumanın paralel parçaları, gömme, eleştirmen) havuzu açabildiği kadar
# açtı ve psycopg_pool fazlasını 10 dakikada bir kapattığı için gateway Postgres'te ~21 bağlantıyı boşta tuttu.
# Cevap MAINTENANCE_CHECK_SEC saniye paylaşılır; aynı anda soran iş parçacıkları tek sorguyu bekler.
MAINTENANCE_CHECK_SEC = float(os.environ.get("EDITOR_MAINTENANCE_CHECK_SEC", "5") or 5)
_ENABLED_GUARD = threading.Lock()
_ENABLED: dict[str, Any] = {"at": None, "fn": None, "error": None}


def _enabled_cached() -> None:
    """foundation.assert_enabled, cevabı MAINTENANCE_CHECK_SEC saniye paylaşılarak (iş parçacığında çağrılır).
    Bakım hatası (RuntimeError) da paylaşılır; bağlantı hatası paylaşılmaz, yükselir."""
    from . import foundation
    fn = foundation.assert_enabled
    with _ENABLED_GUARD:
        now = time.monotonic()
        if MAINTENANCE_CHECK_SEC <= 0 or _ENABLED["fn"] is not fn or _ENABLED["at"] is None \
                or now - _ENABLED["at"] >= MAINTENANCE_CHECK_SEC:
            try:
                fn()
                _ENABLED["error"] = None
            except RuntimeError as exc:
                _ENABLED["error"] = str(exc)
            _ENABLED.update(at=time.monotonic(), fn=fn)
        err = _ENABLED["error"]
    if err:
        raise RuntimeError(err)


async def check_enabled() -> None:
    await asyncio.to_thread(_enabled_cached)
# Adil sıra (2026-10-02): dört kitap paralel okunurken derin görsel model sürekli yeni iş aldığı için hiç «boş» olmadı;
# _held kartı ona bıraktı, OCR ve embedding istekleri 25+ dk (YIELD_MAX'a kadar) aç kaldı — ölçüldü: 90 dk'da 5 OCR
# çağrısı, iki kitap 1,5 saat OCR adımında. Kural: kartı bekleyen model, beklemeye başladığı andan HOLD_MAX saniye
# sonra (etkileşimli istekte INTERACTIVE_HOLD_MAX) sırasını alır: kartı tutan model yeni iş almaz (drain), elindeki
# işler biter, bekleyen açılır. Kartı tutan model sırasını en az HOLD_MAX saniye kullanmış olmalı (yer değiştirme
# döngüsü olmasın); yeni açılan model de aynı korumayla en az bir HOLD süresi kartta kalır. İş kesilmez.
HOLD_MAX = int(os.environ.get("EDITOR_HOLD_MAX_SEC", "600"))
INTERACTIVE_HOLD_MAX = int(os.environ.get("EDITOR_INTERACTIVE_HOLD_MAX_SEC", "120"))
WAITING_SINCE: dict[str, float] = {}        # alias -> kartı beklemeye başladığı an (ilk bekleyen istek)
WAITING_INTERACTIVE: dict[str, float] = {}  # alias -> etkileşimli bir isteğin beklemeye başladığı an
YIELDING: dict[str, int] = {}               # alias -> şu an _route'ta sıra bekleyen istek sayısı
TURN_START: dict[str, float] = {}           # alias -> kartta sırasının başladığı an (sağlıklı açıldığı an)
# Etkileşimli istek (Kitaba sor, kart ekranı) bu başlıkla gelir: kartı daha kısa süre bekler.
INTERACTIVE_HEADER = "x-editor-interactive"
# Bu başlıkla gelen istek hiç beklemez: model şimdi ayakta değilse (ve CPU eşi yoksa) hemen 503 model_not_ready
# döner; çağıran o adımı atlar (Kitaba sor: yeniden sıralama yoksa metin parçaları benzerlik sırasıyla verilir).
NO_WAIT_HEADER = "x-editor-no-wait"
# CPU eşi (models.yaml `cpu_twin`): GPU kopyası kapalıyken küçük istekler (en çok bu kadar girdi; sorgu embedding'i
# 1 girdi) CPU'daki aynı ağırlıklara gider. Toplu dizinleme (64'lük paketler) GPU'yu bekler/açar.
CPU_TWIN_MAX_INPUTS = int(os.environ.get("EDITOR_CPU_TWIN_MAX_INPUTS", "4"))


def _serving(o: "Alias") -> int:
    """Modelin şu an gerçekten sunduğu istek sayısı. `inflight` _route'ta sırasını bekleyen istekleri de sayar; onlar
    kartı kullanmıyor. Ölçüldü 2026-10-02: derin görsel model işi bitmiş, kartı tutarken yeni istekleri bekleyen modele
    yol vermek için bekliyordu (yield); bekleyen istekler `inflight`'ı sıfırın üstünde tuttuğundan bekleyen model onu
    «iş başında» sayıp hiç atamadı — iki taraf 30 dk birbirini bekledi (gpu_busy), okumalar zaman aşımına düştü."""
    return max(0, o.inflight - YIELDING.get(o.name, 0))


def _gpu_lock(gpu: int) -> asyncio.Lock:
    return GPU_LOCKS.setdefault(gpu, asyncio.Lock())
PASSTHROUGH = {"chat/completions", "completions", "embeddings", "rerank", "score",
               "pooling", "classify", "tokenize", "detokenize",
               "images/generations",      # book-image (vLLM-Omni); edits go as JSON chat/completions
               "images/upscale",          # book-upscale (Real-ESRGAN, images/upscale/server.py)
               "audio/narrate",           # book-voice (seslendirme + kelime zamanı, images/voice/server.py)
               "video/generations"}       # book-video (kareden video / konuşan çekim, images/video/server.py)
HOP = {"content-length", "transfer-encoding", "connection", "keep-alive", "content-encoding"}
# vLLM serves these at its root, not under /v1 (/tokenize, /detokenize). The editor counts a long
# request with the model's own tokenizer before sending it (editor.budget).
ROOT_PATHS = {"tokenize", "detokenize"}


def _upstream_path(path: str) -> str:
    return f"/{path}" if path in ROOT_PATHS else f"/v1/{path}"

# Taşma (kullanıcı kararı 2026-09-21): aynı model (Qwen3.8-27B-FP8) GPU 0'da BI için de açık. Etkileşimli
# soru, yönetici model GPU 1'de kapalıyken ve kart analizle doluyken beklemek yerine o eşe gider; iki kopya
# aynı ağırlık ve aynı sunum ayarıyla çalışır (bağlam 131072, qwen3 akıl yürütme ayrıştırıcısı, MTP).
# Yalnız EDITOR_OVERFLOW_CLIENTS'taki konteynerlerden gelen istekler bu kuralla taşar; analiz işçisi aşağıdaki
# «analiz taşması» kuralıyla (yalnız GPU 0'da BI boşken) taşar.
# Boş bırakılırsa taşma kapalıdır.
OVERFLOW_ALIAS = os.environ.get("EDITOR_OVERFLOW_ALIAS", "book-director")
OVERFLOW_URL = os.environ.get("EDITOR_OVERFLOW_URL", "").rstrip("/")
OVERFLOW_MODEL = os.environ.get("EDITOR_OVERFLOW_MODEL", "")
OVERFLOW_CLIENTS = {c.strip() for c in os.environ.get("EDITOR_OVERFLOW_CLIENTS", "").split(",") if c.strip()}

# Analiz taşması (kullanıcı kararı 2026-10-01): kitap okuma yalnız GPU 1'deki tek kopyayı kullanıyordu ve
# kitap başına ~1 M çıktı tokenıyla 80+ dk sürüyordu; GPU 0'daki eş aynı saatlerde boş duruyordu. Analiz
# işçisinin isteği, yönetici model kapalıyken ya da eşteki kendi taşan isteklerimizden fazla iş taşırken
# GPU 0'a gider — yalnız orada BI'ın kendi yükü (eşin çalışan + bekleyen istekleri eksi bizim taşanlar)
# EDITOR_OVERFLOW_ANALYSIS_BI_MAX'ı aşmıyorsa ve aynı anda en çok EDITOR_OVERFLOW_ANALYSIS_CAP istek taşıyorsa.
# BI modeli hiç kapatılmaz; BI isteği gelince yeni taşma durur, taşmış olanlar biter. CAP=0 kapalı.
ANALYSIS_CAP = int(os.environ.get("EDITOR_OVERFLOW_ANALYSIS_CAP", "8") or 0)
ANALYSIS_BI_MAX = int(os.environ.get("EDITOR_OVERFLOW_ANALYSIS_BI_MAX", "2") or 0)
# BI önceliği (2026-10-02): GPU 0'daki vLLM `--scheduling-policy priority` ile açıldığında taşan analiz isteği bu
# değeri `priority` alanında taşır (vLLM: küçük sayı önce; BI isteği alan göndermez = 0). Bekleme sırasında BI önce
# alınır, bellek darlığında önce taşan analiz geri çekilir. 0 = alan gönderilmez: politika açık değilken vLLM sıfırdan
# farklı önceliği reddeder; önce BI kabı priority ile açılır, sonra bu değer verilir (deploy/tt-gpu/compose.qwen27b.yaml).
OVERFLOW_PRIORITY = int(os.environ.get("EDITOR_OVERFLOW_PRIORITY", "0") or 0)
PRIORITY_PATHS = {"chat/completions", "completions"}
# Etkileşimli öncelik (2026-10-03): «Gölge Tilki'de ana karakter kim?» kitap okumaları yoğunken 8+ dk bekledi, yük
# yokken 7 sn. GPU 1'deki yönetici model 32 koltuğu analizle doluyken (ölçüldü: bekleyen 82'ye kadar, bir saatte
# 10.461 event_actor + 3.949 adsız çağrı) vLLM FCFS sırasında soru analiz isteklerinin arkasına giriyordu.
# Yönetici `--scheduling-policy priority` ile açıldığında (models.yaml) gateway her sohbet isteğine `priority` koyar:
# etkileşimli (Kitaba sor, kart ekranı) INTERACTIVE_PRIORITY, analiz ANALYSIS_PRIORITY. vLLM: küçük sayı önce; KV
# darlığında önce büyük sayılı istek geri çekilir. BI'ın dağıtıcıdan (llm-dispatch backup) gelen isteği alan
# göndermez = 0, yani etkileşimliyle aynı, analizden önce. Politika kapalı kapta sıfırdan farklı öncelik reddedilir;
# bu yüzden karar models.yaml'a değil çalışan kabın kendi argümanlarına bakar (`_priority_on`): yeni argüman, kap
# bir sonraki soğuk açılışında yeniden yaratılana kadar geçerli değildir.
INTERACTIVE_PRIORITY = int(os.environ.get("EDITOR_INTERACTIVE_PRIORITY", "0") or 0)
ANALYSIS_PRIORITY = int(os.environ.get("EDITOR_ANALYSIS_PRIORITY", "10") or 0)
PRIORITY_TTL = 10.0
_priority_seen: dict[str, tuple[float, bool]] = {}   # alias -> (okunduğu an, çalışan kapta politika açık mı)
PEER_LOAD_TTL = 1.0
_peer_load: tuple[float, int | None] = (0.0, None)
_peer_ours: int | None = None  # eşin yükü okunduğu an bizim taşan isteklerimiz (BI payı = yük - bu)
_peer_lock = asyncio.Lock()    # önbellek süresi dolunca /metrics'i tek istek okur, ötekiler onu bekler
overflow_inflight = 0          # GPU 0'a taşmış (ya da yeri ayrılmış), henüz bitmemiş analiz istekleri
overflow_total = 0

# Etkileşimli sohbet (EDITOR_OVERFLOW_CLIENTS) düşünme kapalı çalışır (editor.chat_params). Analiz işçisinin
# istekleri değişmez; istemci kendisi açıkça isterse ona uyulur. EDITOR_CHAT_THINKING=1 eski davranışa döner.
CHAT_THINKING = os.environ.get("EDITOR_CHAT_THINKING", "0").strip() == "1"


@dataclass
class Alias:
    name: str
    container: str
    model_dir: str
    real_model: str
    kind: str
    gpu: int
    mem_fraction: float
    args: list[str]
    image: str
    idle_stop_sec: int
    start_timeout_sec: int
    role: str = ""
    always_on: bool = False
    # Further names the same server answers to. The main model on GPU 1 also answers as BI's
    # `nanobaseAI`, so the dispatcher in front of both cards (deploy/tt-gpu/llm-dispatch) can
    # send BI prompts to it while no book is being read.
    also_serves: list[str] = field(default_factory=list)
    # Image without an entrypoint (vLLM-Omni): the command the container runs before the
    # model path. vllm/vllm-openai images already start with `vllm serve`.
    entrypoint: list[str] = field(default_factory=list)
    # Extra container environment for this alias only (e.g. PyTorch allocator settings).
    env: dict[str, str] = field(default_factory=dict)
    # gpu < 0: CPU'da çalışan model (kart, bellek payı ve kart kilidi yok). `cpus`: kaba ayrılan çekirdek sayısı.
    cpus: int = 0
    # Aynı ağırlıkları CPU'da sunan alias; GPU kopyası kapalıyken küçük istekler ona gider (CPU_TWIN_MAX_INPUTS).
    cpu_twin: str = ""
    inflight: int = 0
    last_used: float = field(default_factory=time.time)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def upstream(self) -> str:
        return f"http://{self.container}:8000"

    def spec_hash(self) -> str:
        spec = [self.image, self.model_dir, self.gpu, self.mem_fraction, self.args]
        if self.also_serves:              # only then: the other models' containers keep their hash
            spec.append(self.also_serves)
        if self.entrypoint:
            spec.append(self.entrypoint)
        if self.env:
            spec.append(sorted(self.env.items()))
        if self.cpus:
            spec.append(self.cpus)
        blob = json.dumps(spec)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


def load_aliases() -> dict[str, Alias]:
    cfg = yaml.safe_load(MODELS_YAML.read_text())
    d = cfg.get("defaults", {})
    out = {}
    for name, a in cfg["aliases"].items():
        out[name] = Alias(
            name=name, container=a["container"], model_dir=a["model_dir"],
            real_model=a["real_model"], kind=a["kind"], gpu=int(a["gpu"]),
            mem_fraction=float(a["mem_fraction"]), args=list(a.get("args", [])),
            image=a.get("image", d["image"]),
            idle_stop_sec=int(a.get("idle_stop_sec", d.get("idle_stop_sec", 600))),
            start_timeout_sec=int(a.get("start_timeout_sec", d.get("start_timeout_sec", 1800))),
            role=a.get("role", ""),
            always_on=bool(a.get("always_on", False)),
            also_serves=[str(x) for x in a.get("also_serves", [])],
            entrypoint=[str(x) for x in a.get("entrypoint", [])],
            env={str(k): str(v) for k, v in (a.get("env") or {}).items()},
            cpus=int(a.get("cpus", 0)),
            cpu_twin=str(a.get("cpu_twin", "")),
        )
    return out


ALIASES = load_aliases()
@asynccontextmanager
async def lifespan(_app: FastAPI):
    for a in ALIASES.values():
        a.last_used = time.time()
    task = asyncio.create_task(reaper())
    yield
    task.cancel()


app = FastAPI(title="editor-model-gateway", docs_url=None, redoc_url=None, lifespan=lifespan)
dk = docker.from_env()
http = httpx.AsyncClient(timeout=httpx.Timeout(None, connect=10.0))
pynvml.nvmlInit()


# ----------------------------------------------------------------- GPU info
def gpu_mem(idx: int) -> tuple[int, int]:
    h = pynvml.nvmlDeviceGetHandleByIndex(idx)
    m = pynvml.nvmlDeviceGetMemoryInfo(h)
    return m.free, m.total


def gpu_holders(idx: int) -> list[dict]:
    """Who holds memory on a card: pid -> container name when we can map it."""
    h = pynvml.nvmlDeviceGetHandleByIndex(idx)
    procs = pynvml.nvmlDeviceGetComputeRunningProcesses(h)
    pid_to_ctr: dict[int, str] = {}
    try:
        for c in dk.containers.list():
            try:
                for row in c.top().get("Processes") or []:
                    pid_to_ctr[int(row[1])] = c.name
            except Exception:  # noqa: BLE001 - best effort mapping
                continue
    except Exception:  # noqa: BLE001
        pass
    return [{"pid": p.pid, "used_gib": round((p.usedGpuMemory or 0) / GIB, 1),
             "container": pid_to_ctr.get(p.pid, "?")} for p in procs]


# ------------------------------------------------------- container control
def _container(a: Alias):
    try:
        return dk.containers.get(a.container)
    except docker.errors.NotFound:
        return None


def _create(a: Alias):
    labels = {"editor.model": a.name, "editor.spec": a.spec_hash()}
    cache = f"{HOST_ROOT}/vllm-cache/{a.name}"
    cmd = ["/model", "--served-model-name", a.name, *a.also_serves,
           "--gpu-memory-utilization", f"{a.mem_fraction:.2f}", *a.args]
    log.info("create %s (%s) gpu=%s frac=%.2f", a.container, a.real_model, a.gpu, a.mem_fraction)
    extra: dict[str, Any] = {}
    if a.gpu >= 0:
        extra["device_requests"] = [DeviceRequest(device_ids=[str(a.gpu)], capabilities=[["gpu"]])]
    if a.cpus:
        extra["nano_cpus"] = a.cpus * 10**9
    return dk.containers.create(
        a.image, cmd, entrypoint=a.entrypoint or None, name=a.container, labels=labels, detach=True,
        network=NETWORK, ipc_mode="host", shm_size="16g",
        ulimits=[Ulimit(name="memlock", soft=-1, hard=-1)], **extra,
        volumes={f"{HOST_ROOT}/models/{a.model_dir}": {"bind": "/model", "mode": "ro"},
                 cache: {"bind": "/root/.cache/vllm", "mode": "rw"}},
        environment={**a.env, "HF_HUB_OFFLINE": "1", "VLLM_NO_USAGE_STATS": "1",
                     "DO_NOT_TRACK": "1"},
        restart_policy={"Name": "no"},
    )


def _ensure_created(a: Alias):
    c = _container(a)
    if c is not None and c.labels.get("editor.model") != a.name:
        raise HTTPException(500, f"{a.container} exists but is not an editor model")
    if c is not None and c.labels.get("editor.spec") != a.spec_hash():
        if c.status == "running":
            return c  # spec changed; recreate at next cold start
        c.remove()
        c = None
    return c or _create(a)


def _is_running(a: Alias) -> bool:
    c = _container(a)
    return c is not None and c.status == "running"


async def _healthy(a: Alias) -> bool:
    try:
        r = await http.get(f"{a.upstream}/health", timeout=3.0)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


async def _stop(a: Alias, why: str) -> None:
    c = _container(a)
    if c is None or c.status != "running":
        return
    if c.labels.get("editor.model") != a.name:
        return  # never touch foreign containers
    log.info("stop %s (%s)", a.name, why)
    await asyncio.to_thread(c.stop, timeout=30)


WAITING: set[str] = set()      # aliases waiting for room right now


def _orphans() -> list:
    """Running containers the gateway itself labelled as editor models whose alias no longer
    exists (removed from models.yaml). Nobody else would ever stop them. Measured: a removed
    benchmark model held 28 GB of GPU 1 for an hour and stalled an analysis."""
    return [c for c in dk.containers.list(filters={"label": "editor.model"})
            if c.labels.get("editor.model") not in ALIASES]


async def _make_room(a: Alias) -> None:
    """Free enough memory on a's card by stopping idle editor models there."""
    need = int(a.mem_fraction * gpu_mem(a.gpu)[1]) + MEM_MARGIN
    deadline = time.time() + a.start_timeout_sec
    await _make_room_inner(a, need, deadline)      # WAITING'i ensure_running tutar (kart kilidi boyunca)


async def _make_room_inner(a: Alias, need: int, deadline: float) -> None:
    while True:
        free, total = gpu_mem(a.gpu)
        if free >= need:
            return
        orphans = await asyncio.to_thread(_orphans)
        if orphans:
            for c in orphans:
                log.info("stop %s (orphan: alias removed; make room for %s)", c.name, a.name)
                await asyncio.to_thread(c.stop, timeout=30)
            await asyncio.sleep(3)
            continue
        others = sorted(
            (o for o in ALIASES.values()
             if o.name != a.name and o.gpu == a.gpu and _is_running(o)),
            key=lambda o: o.last_used)
        # An always-on model gives way only when nothing else can: it is stopped last and the
        # keeper brings it back as soon as the card has room again.
        now = time.time()
        idle = sorted((o for o in others if _serving(o) == 0 and not _held(o, a, now)), key=lambda o: o.always_on)
        if idle:
            await _stop(idle[0], f"make room for {a.name}")
            await asyncio.sleep(3)
            continue
        if not others or time.time() > deadline:
            # Remaining memory is held by something that is not an editor
            # model (or editor models that stay busy): report, do not kill.
            raise HTTPException(503, {
                "error": "gpu_busy", "alias": a.name, "gpu": a.gpu,
                "need_gib": round(need / GIB, 1), "free_gib": round(free / GIB, 1),
                "total_gib": round(total / GIB, 1), "holders": gpu_holders(a.gpu),
            })
        await asyncio.sleep(5)  # busy editor models on this card: wait


def _held(o: Alias, a: Alias, now: float) -> bool:
    """`o` kartını `a`ya bırakmamalı mı? İş başındaki model (son EVICT_GRACE saniyede kullanılmış ya da açılıyor)
    tutulur; sürekli açık ana model de (bkz. EVICT_GRACE notu, 2026-10-04 takası). `a`nın sırası geldiyse
    (`_turn_over`) `o` artık tutulmaz: yeni iş almaz, elindeki işler bitince kartı bırakır."""
    if o.lock.locked():
        return True
    return now - o.last_used < EVICT_GRACE and not _turn_over(o, a, now)


def _turn_over(o: Alias, a: Alias, now: float) -> bool:
    """`a` kartı yeterince bekledi ve `o` sırasını en az bir HOLD süresi kullandı mı? Etkileşimli bekleyişte iki süre
    de INTERACTIVE_HOLD_MAX'tır."""
    since, inter = WAITING_SINCE.get(a.name), WAITING_INTERACTIVE.get(a.name)
    if inter is not None and now - inter >= INTERACTIVE_HOLD_MAX \
            and now - TURN_START.get(o.name, 0.0) >= INTERACTIVE_HOLD_MAX:
        return True
    return since is not None and now - since >= HOLD_MAX and now - TURN_START.get(o.name, 0.0) >= HOLD_MAX


def _wait_begin(a: Alias, interactive: bool) -> None:
    now = time.time()
    YIELDING[a.name] = YIELDING.get(a.name, 0) + 1
    WAITING_SINCE.setdefault(a.name, now)
    if interactive:
        WAITING_INTERACTIVE.setdefault(a.name, now)


def _wait_end(a: Alias, proceeding: bool) -> None:
    """`proceeding`: istek modeli açmaya gidiyor (ensure_running); bekleyiş kaydı orada, model açılınca silinir —
    burada silinirse yer açma sırasında kartı tutan modelin sırası yeniden «bitmemiş» görünür."""
    YIELDING[a.name] = max(0, YIELDING.get(a.name, 0) - 1)
    if not proceeding:
        _wait_forget(a)


def _wait_forget(a: Alias, served: bool = False) -> None:
    """Bekleyiş kaydı, model açıldığında ya da artık bekleyen isteği kalmadığında silinir."""
    if served or (not YIELDING.get(a.name) and a.name not in WAITING):
        WAITING_SINCE.pop(a.name, None)
        WAITING_INTERACTIVE.pop(a.name, None)


def _must_yield(a: Alias) -> bool:
    """`a`ya gelen yeni istek kartı beslememeli mi? (1) Aynı kartta yer bekleyen başka model var: kartı boşaltmak
    için `a`ya iş verilmez. (2) `a` sürekli açık model ve kapalı; kartını iş başındaki başka model tutuyor: onu
    atmak yerine beklenir. İkisinde de istek eşe taşar ya da sırasını bekler (`_route`)."""
    now = time.time()
    for o in ALIASES.values():
        if o is a or o.gpu != a.gpu:
            continue
        if o.name in WAITING:
            return True
        if (not _is_running(a) and _held(o, a, now) and (o.lock.locked() or _is_running(o))
                and o.mem_fraction + a.mem_fraction > FIT_TOGETHER):
            return True
    return False


async def _drain_overflow(a: Alias, client: str = "") -> bool:
    """Kart boşaltılırken ana modelin isteği eşe gidebilir mi? Yalnız eş ayaktaysa, taşma sınırı doluysa değil ve
    eşte BI'ın kendi yükü sınırı aşmıyorsa (BI hiç yavaşlatılmaz). Analiz isteğinin yeri burada ayrılır
    (`_reserve_overflow`); etkileşimli istek eskisi gibi sayılmaz, yalnız denetlenir."""
    if not (OVERFLOW_URL and OVERFLOW_MODEL and a.name == OVERFLOW_ALIAS):
        return False
    if ANALYSIS_CAP <= 0 or overflow_inflight >= ANALYSIS_CAP:
        return False
    load = await peer_load()
    if client:
        return _overflow_room(load)
    return _reserve_overflow(load)


def _interactive(req: Request) -> bool:
    headers = getattr(req, "headers", None) or {}
    return bool(_client_name(req)) or headers.get(INTERACTIVE_HEADER, "") == "1"


async def _route(a: Alias, req: Request) -> bool:
    """True: istek eşe gider. Kart boşaltılıyor ya da başka modelde iken istek kartı beslemez; eşe taşar ya da
    sırasını bekler (YIELD_MAX'tan sonra eski davranış: kendi modelini açar). Beklemeye başladığı an kaydedilir:
    HOLD_MAX (etkileşimlide INTERACTIVE_HOLD_MAX) dolunca kartı tutan modelin sırası biter (`_turn_over`)."""
    deadline = time.time() + YIELD_MAX
    waiting = proceeding = False
    client = _client_name(req)
    try:
        while True:
            if await _should_overflow(a, req):
                return True
            if not _must_yield(a) or time.time() > deadline:
                proceeding = True
                return False
            if await _drain_overflow(a, client):
                return True
            if not waiting:
                log.info("yield %s: card %s busy with another model, request waits", a.name, a.gpu)
                _wait_begin(a, _interactive(req))
                waiting = True
            await asyncio.sleep(2)
    finally:
        if waiting:
            _wait_end(a, proceeding)


def _would_wait(a: Alias) -> bool:
    """`a`yı şimdi başlatmak kartta meşgul bir modelin bitmesini beklemeyi gerektirir mi?
    Boş bellek + boşta duran editör modellerinin bırakacağı bellek yetiyorsa beklemez."""
    free, total = gpu_mem(a.gpu)
    need = int(a.mem_fraction * total) + MEM_MARGIN
    if free >= need:
        return False
    others = [o for o in ALIASES.values() if o.name != a.name and o.gpu == a.gpu and _is_running(o)]
    reclaimable = sum(int(o.mem_fraction * total) for o in others if _serving(o) == 0)
    return free + reclaimable < need


def _client_name(req: Request) -> str:
    """İsteği atan konteynerin adı (editor-net üzerinde ters DNS); çözülemezse boş. İstek başına bir kez çözülür:
    taşma yeri «analiz isteği» kararıyla ayrılıp (`_route`) aynı kararla geri verildiği (`proxy.release`) için iki
    çağrı aynı cevabı vermeli, yoksa ayrılan yer hiç geri verilmez."""
    cached = getattr(req, "_editor_client", None)
    if cached is not None:
        return cached
    c = getattr(req, "client", None)
    host = c.host if c else ""
    name = ""
    for n in OVERFLOW_CLIENTS if host else ():
        try:
            if host in {ai[4][0] for ai in socket.getaddrinfo(n, None)}:
                name = n
                break
        except OSError:
            continue
    try:
        req._editor_client = name            # type: ignore[attr-defined]
    except AttributeError:
        pass
    return name


async def _overflow_ok() -> bool:
    try:
        r = await http.get(f"{OVERFLOW_URL}/v1/models", timeout=5.0)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


async def peer_load() -> int | None:
    """Eşin (GPU 0) çalışan + bekleyen istek sayısı, vLLM /metrics'ten; okunamazsa None. 1 sn önbellek.
    Okunduğu an bizim taşan isteklerimizin sayısı da saklanır (`_peer_ours`); BI'ın kendi yükü ondan hesaplanır."""
    global _peer_load, _peer_ours
    if time.time() - _peer_load[0] < PEER_LOAD_TTL:
        return _peer_load[1]
    async with _peer_lock:
        if time.time() - _peer_load[0] < PEER_LOAD_TTL:     # beklerken başkası okudu
            return _peer_load[1]
        n: int | None = None
        try:
            r = await http.get(f"{OVERFLOW_URL}/metrics", timeout=3.0)
            if r.status_code == 200:
                n = 0
                for line in r.text.splitlines():
                    if line.startswith(("vllm:num_requests_running{", "vllm:num_requests_waiting{")):
                        n += int(float(line.rsplit(" ", 1)[1]))
        except (httpx.HTTPError, ValueError):
            n = None
        _peer_load, _peer_ours = (time.time(), n), overflow_inflight
        return n


def _bi_load(load: int) -> int:
    """Eşteki yükün BI'a ait kısmı: ölçüm anındaki taşan sayımız çıkarılır. Ölçümden sonra yeri ayrılan (eşin
    sayacına henüz girmemiş) istekler çıkarılırsa BI yükü eksi görünür ve sınır yine aşılır."""
    ours = overflow_inflight if _peer_ours is None else _peer_ours
    return max(0, load - ours)


def _overflow_room(load: int | None) -> bool:
    """Taşma için yer var mı (yalnız denetim)? Sınır dolmamış ve eşte BI'ın kendi yükü sınırı aşmıyor."""
    if ANALYSIS_CAP <= 0 or overflow_inflight >= ANALYSIS_CAP or load is None:
        return False
    return _bi_load(load) <= ANALYSIS_BI_MAX


def _reserve_overflow(load: int | None) -> bool:
    """Denetim + yer ayırma tek adımda; arada `await` yok, olay döngüsünde başka istek araya giremez.
    Ölçüldü 2026-10-02: denetim (`peer_load` beklenirken) ile `overflow_inflight += 1` (proxy'de) ayrıyken aynı anda
    gelen okumaların hepsi «yer var» gördü; sınır 8 iken 121 istek taştı, BI GPU 0 kuyruğunda bekledi.
    True: yer ayrıldı; istek bitince `proxy.release` geri verir."""
    global overflow_inflight
    if not _overflow_room(load):
        return False
    overflow_inflight += 1
    return True


async def _analysis_overflow(a: Alias) -> bool:
    """Analiz isteği GPU 0'daki eşe gitsin mi? Yerelde yer varsa hayır; eşte BI meşgulse ya da sınır doluysa hayır.
    True dönerse taşma yeri ayrılmıştır."""
    if ANALYSIS_CAP <= 0 or overflow_inflight >= ANALYSIS_CAP:
        return False                                 # hızlı ret; asıl denetim beklemelerden sonra
    local_up = _is_running(a) and await _healthy(a)
    load = await peer_load()
    # Buradan sonra await yok: denetim ve yer ayırma aynı anda gelen isteklerle yarışmaz.
    # Yerel kopya ayaktaysa yük dengelenir: yereldeki iş (bu istek hariç) eşe taşanlardan fazla değilse yerelde kalır.
    if local_up and a.inflight - 1 <= overflow_inflight:
        return False
    return _reserve_overflow(load)


def _seats(a: Alias) -> int:
    """Modelin aynı anda sunduğu istek sayısı (`--max-num-seqs`); bilinmiyorsa 0."""
    args = [str(x).strip() for x in a.args]
    for i, arg in enumerate(args):
        if arg.startswith("--max-num-seqs="):
            return int(arg.split("=", 1)[1])
        if arg == "--max-num-seqs" and i + 1 < len(args):
            return int(args[i + 1])
    return 0


def _policy_priority(args: list) -> bool:
    args = [str(x).strip() for x in args or []]
    return "--scheduling-policy=priority" in args or any(
        x == "--scheduling-policy" and i + 1 < len(args) and args[i + 1] == "priority" for i, x in enumerate(args))


def _priority_on(a: Alias) -> bool:
    """Çalışan kap `--scheduling-policy priority` ile mi açıldı? models.yaml'a bakılmaz: argüman değişince kap bir
    sonraki soğuk açılışa kadar eski argümanla çalışır (`_ensure_created`) ve politika kapalıyken vLLM sıfırdan farklı
    önceliği 400 ile reddeder. 10 sn önbellek (istek başına docker sorgusu olmasın)."""
    now = time.time()
    seen = _priority_seen.get(a.name)
    if seen and now - seen[0] < PRIORITY_TTL:
        return seen[1]
    on = False
    try:
        c = _container(a)
        if c is not None and c.status == "running":
            on = _policy_priority((getattr(c, "attrs", None) or {}).get("Args") or [])
    except Exception:  # noqa: BLE001 — okunamazsa alan gönderilmez (eski davranış)
        on = False
    _priority_seen[a.name] = (now, on)
    return on


def _with_priority(a: Alias, path: str, payload: dict, interactive: bool) -> bool:
    """Yerel kaba gidecek sohbet isteğine öncelik koyar (politika açıksa). True: gövde değişti."""
    if path not in PRIORITY_PATHS or "priority" in payload or not _priority_on(a):
        return False
    payload["priority"] = INTERACTIVE_PRIORITY if interactive else ANALYSIS_PRIORITY
    return True


async def _interactive_spill(a: Alias) -> bool:
    """Yönetici ayaktayken etkileşimli soru eşe gitsin mi? Yalnız yerelde koltuklar doluysa (bu istek hariç sunulan
    istek ≥ `--max-num-seqs`: soru vLLM sırasına girecek) ve eşte BI'ın kendi yükü EDITOR_OVERFLOW_ANALYSIS_BI_MAX'ı
    aşmıyorsa (BI hiç yavaşlatılmaz). Analiz taşma sınırı (ANALYSIS_CAP) burada sayılmaz: o sınır okumanın eşe
    taşıdığı yük içindir; soru tek istektir ve analiz 8/8 doluyken (ölçüldü 2026-10-03) hiç geçemezdi."""
    seats = _seats(a)
    if seats <= 0 or _serving(a) - 1 < seats:
        return False
    load = await peer_load()
    return load is not None and _bi_load(load) <= ANALYSIS_BI_MAX


async def _should_overflow(a: Alias, req: Request) -> bool:
    if not (OVERFLOW_URL and OVERFLOW_MODEL and a.name == OVERFLOW_ALIAS):
        return False
    if not _client_name(req):
        return await _analysis_overflow(a)  # analiz işçisi: yalnız GPU 0'da BI boşken
    if _is_running(a) and await _healthy(a):
        return await _interactive_spill(a)  # yönetici GPU 1'de açık: koltuklar dolu değilse orada cevaplanır
    # Kapalı model de "meşgul"dür: soğuk açılış ~100 sn sürüyor (ölçüldü: "ana karakter kim"
    # 111 sn'de cevaplandı, kullanıcı ekranda boş bekledi). Aynı model GPU 0'da zaten ayakta;
    # etkileşimli soru oradan anında cevaplanır. GPU 1 bir sonraki analiz ihtiyacında açılır.
    return await _overflow_ok()


async def ensure_running(a: Alias) -> None:
    try:
        await check_enabled()
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from None
    if _is_running(a) and await _healthy(a):
        _wait_forget(a, served=True)
        return
    if a.gpu < 0:                       # CPU modeli: kart, kart kilidi ve yer açma yok
        async with a.lock:
            await _start_locked(a)
        return
    async with a.lock:
        if _is_running(a) and await _healthy(a):
            return
        # Kart kilidi: yer açma, başlatma ve sağlıklı olana kadar bekleme tek parça. Yeni açılan model belleğini
        # yüklenirken ayırır; o arada kart boş görünür ve ikinci model de açılırsa ikisi birden düşer (ölçüldü
        # 2026-10-01: %90 + %62 aynı anda başladı, resim modeli bellek aşımıyla düştü).
        WAITING.add(a.name)            # sırada beklerken de kartı besleyen istekler durur
        try:
            async with _gpu_lock(a.gpu):
                await _start_locked(a)
        finally:
            WAITING.discard(a.name)
            _wait_forget(a)


async def _start_locked(a: Alias) -> None:
    if _is_running(a) and await _healthy(a):
        return
    c = await asyncio.to_thread(_ensure_created, a)
    if c.status != "running":
        if a.gpu >= 0:
            await _make_room(a)
        log.info("start %s on gpu %s", a.name, a.gpu)
        await asyncio.to_thread(c.start)
    t0 = time.time()
    while time.time() - t0 < a.start_timeout_sec:
        if await _healthy(a):
            log.info("ready %s in %.0fs", a.name, time.time() - t0)
            a.last_used = TURN_START[a.name] = time.time()
            _wait_forget(a, served=True)
            return
        c.reload()
        if c.status != "running":
            tail = c.logs(tail=40).decode(errors="replace")
            raise HTTPException(503, {"error": "model_failed_to_start",
                                      "alias": a.name, "log_tail": tail[-4000:]})
        await asyncio.sleep(3)
    raise HTTPException(504, {"error": "model_start_timeout", "alias": a.name})


async def reaper() -> None:
    while True:
        await asyncio.sleep(15)
        now = time.time()
        for a in ALIASES.values():
            try:
                if a.always_on:
                    await _keep(a)
                elif (a.inflight == 0 and not a.lock.locked() and _is_running(a)
                        and now - a.last_used > a.idle_stop_sec):
                    await _stop(a, f"idle {int(now - a.last_used)}s")
            except Exception as e:  # noqa: BLE001
                log.warning("reaper %s: %s", a.name, e)


async def _keep(a: Alias) -> None:
    """The main model is never stopped for being idle (user decision 2026-09-22: "bu bizim
    ana modelimiz, hiç kapanmasın"). If a job needing the whole card pushed it out, it comes
    back as soon as there is room — never by pushing a working model out in turn — and while
    it is away interactive questions are answered by its copy on GPU 0 (overflow)."""
    if _is_running(a) or a.lock.locked():
        return
    if a.gpu < 0:                             # CPU modeli: kart hesabı yok, hemen geri kalkar
        log.info("keep %s up (always on, cpu)", a.name)
        await ensure_running(a)
        return
    # Another model is waiting for room on this card: coming back now would only be pushed
    # out again (measured: a start/stop loop every 50 s that stalled an analysis for an hour).
    if any(ALIASES[w].gpu == a.gpu for w in WAITING if w in ALIASES):
        return
    try:
        await check_enabled()
    except RuntimeError:
        return                                # maintenance: nothing is started
    # Boş bellek tek başına ölçü değil: yeni açılan model (ör. book-image) belleğini ancak yüklenirken
    # ayırır, o arada kart boş görünür. Ölçüldü 2026-09-24: ana model 7 sn sonra geri kaldırıldı, iki
    # model aynı karta bindi, resim üretimi bellek aşımıyla düştü. Kartta açık ya da açılmakta olan
    # modellerin payları + bu modelin payı sığmıyorsa geri gelmez; o model kapanınca gelir.
    busy = [o for o in ALIASES.values()
            if o.name != a.name and o.gpu == a.gpu and (o.lock.locked() or _is_running(o))]
    if sum(o.mem_fraction for o in busy) + a.mem_fraction > FIT_TOGETHER:
        return
    need = int(a.mem_fraction * gpu_mem(a.gpu)[1]) + MEM_MARGIN
    if gpu_mem(a.gpu)[0] < need:
        return
    log.info("keep %s up (always on)", a.name)
    await ensure_running(a)


# ---------------------------------------------------------------- auth/API
def _auth(req: Request, internal: bool = False) -> None:
    tok = req.headers.get("authorization", "").removeprefix("Bearer ").strip()
    ok = tok and (tok == INTERNAL_KEY or (not internal and tok == PUBLIC_KEY))
    if not ok:
        raise HTTPException(401, "invalid key")


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


@app.get("/v1/models")
async def models(req: Request) -> dict:
    _auth(req)
    return {"object": "list", "data": [
        {"id": a.name, "object": "model", "owned_by": "editor", "kind": a.kind}
        for a in ALIASES.values()]}


@app.api_route("/v1/{path:path}", methods=["POST"])
async def proxy(path: str, req: Request):
    global overflow_total
    _auth(req)
    try:
        await check_enabled()
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from None
    if path not in PASSTHROUGH:
        raise HTTPException(404, f"unsupported endpoint /v1/{path}")
    body = await req.body()
    try:
        payload: dict[str, Any] = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(400, "body must be JSON")
    a = ALIASES.get(payload.get("model", ""))
    if a is None:
        raise HTTPException(404, {"error": "unknown model", "models": sorted(ALIASES)})
    twin = await _cpu_twin(a, payload)
    if twin is not a:
        # Eşin sunduğu ad gövdeye yazılır. 2026-10-05 ölçümü: gövde eski baytlarla gidiyordu, CPU eşi «unknown model
        # book-embedding» (404) diyordu; GPU kopyası kapalıyken Kitaba sor'un bütün metin aramaları sessizce boştu.
        body = json.dumps(payload).encode()
        a = twin
    if req.headers.get(NO_WAIT_HEADER, "") == "1" and not await _ready_now(a, req):
        raise HTTPException(503, {"error": "model_not_ready", "alias": a.name})
    a.inflight += 1
    released = False
    spilled = False

    def release() -> None:
        global overflow_inflight
        nonlocal released
        if not released:
            released = True
            if spilled:
                overflow_inflight -= 1      # GPU 1'deki modeli meşgul saymaz (boşta durdurma kararı)
            else:
                a.inflight -= 1
            a.last_used = time.time()

    try:
        if (path == "chat/completions" and not CHAT_THINKING and _client_name(req)
                and without_thinking(payload)):
            body = json.dumps(payload).encode()
        if await _route(a, req):
            # Aynı modelin GPU 0'daki eşi; yalnız sunulan ad farklı, gövdedeki model adı ona çevrilir.
            client = _client_name(req)
            if not client:
                spilled = True                   # yeri _route içinde ayrıldı (_reserve_overflow), burada sayılmaz
                a.inflight -= 1
                overflow_total += 1
                if OVERFLOW_PRIORITY and path in PRIORITY_PATHS:
                    payload.setdefault("priority", OVERFLOW_PRIORITY)   # BI (0) önce sıraya girer
            if client or overflow_total % 100 == 1:
                log.info("overflow %s → %s (gpu %s busy, client %s, analiz taşan %d/%d, toplam %d)", a.name,
                         OVERFLOW_URL, a.gpu, client or "analiz", overflow_inflight, ANALYSIS_CAP, overflow_total)
            payload["model"] = OVERFLOW_MODEL
            body = json.dumps(payload).encode()
            url = f"{OVERFLOW_URL}{_upstream_path(path)}"
        else:
            await ensure_running(a)
            if _with_priority(a, path, payload, _interactive(req)):
                body = json.dumps(payload).encode()
            url = f"{a.upstream}{_upstream_path(path)}"
        headers = {"content-type": "application/json"}
        if payload.get("stream"):
            upstream = await http.send(http.build_request("POST", url, content=body,
                                                          headers=headers), stream=True)

            async def gen():
                try:
                    async for chunk in upstream.aiter_raw():
                        yield chunk
                finally:
                    await upstream.aclose()
                    release()

            return StreamingResponse(gen(), status_code=upstream.status_code,
                                     media_type=upstream.headers.get("content-type"))
        try:
            r = await _unless_client_gone(req, http.post(url, content=body, headers=headers))
        except ClientGone:
            release()
            log.info("client gone, upstream %s request cancelled (%s)", a.name, path)
            return Response(status_code=499)
        release()
        return Response(r.content, status_code=r.status_code,
                        headers={k: v for k, v in r.headers.items() if k.lower() not in HOP})
    except BaseException:
        release()
        raise


class ClientGone(Exception):
    """The caller hung up (its read timeout) while the model request was still queued or running."""


#: How often a waiting non-streaming request checks that its caller is still there.
DISCONNECT_POLL_SEC = float(os.environ.get("EDITOR_DISCONNECT_POLL_SEC", "5"))


async def _unless_client_gone(req: Request, call):
    """Await the upstream call, but cancel it when the caller has gone. Measured 2026-10-04..06: 182 deep page scans
    waited the client's whole read timeout in the model's queue; the caller sent the page again while this
    handler kept its upstream request, so the model later read the same page for nobody. Cancelling closes the
    upstream connection and vLLM aborts the request (its chat endpoint is `with_cancellation`)."""
    task = asyncio.ensure_future(call)
    check = getattr(req, "is_disconnected", None)
    if check is None:
        return await task
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=DISCONNECT_POLL_SEC)
            if done:
                return task.result()
            if await check():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise ClientGone()
    except BaseException:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        raise


async def _up_now(a: Alias) -> bool:
    """Model şu an, kart sırası beklemeden cevap verebilir mi (ayakta, sağlıklı ve kartı boşaltılmıyor)?
    Ölçüldü 2026-10-02: embedding kabı ayaktayken bile kartta başka model yer beklediği için (`_must_yield`)
    soru embedding'i dakikalarca «card 1 busy» diye bekledi."""
    return _is_running(a) and not _must_yield(a) and await _healthy(a)


async def _cpu_twin(a: Alias, payload: dict) -> Alias:
    """GPU kopyası şu an cevap veremiyorsa (`_up_now`) küçük isteği CPU eşine verir. Ölçüldü 2026-10-02: derin görsel model kartın
    %90'ını tutarken Kitaba sor'un sorgu embedding'i kartta yer bulamadı (YIELD_MAX'a kadar bekledi); aynı
    Qwen3-Embedding-8B CPU'da (32 çekirdek, AMX bf16) bir soruyu 0,15 sn'de gömüyor, dizindeki GPU vektörleriyle
    kosinüs 0,9999."""
    twin = ALIASES.get(a.cpu_twin) if a.cpu_twin else None
    if twin is None:
        return a
    inputs = payload.get("input")
    n = len(inputs) if isinstance(inputs, list) else 1
    if n > CPU_TWIN_MAX_INPUTS or await _up_now(a):
        return a
    payload["model"] = twin.name
    return twin


async def _ready_now(a: Alias, req: Request) -> bool:
    """NO_WAIT isteği şimdi cevaplanabilir mi: model ayakta ya da eşe taşacak. Değilse ve kartta kimseyi atmadan
    yer varsa model arka planda açılır (bir sonraki soru kullanır); kimse durdurulmaz, kimse beklemez."""
    if await _up_now(a):
        return True
    if a.gpu < 0:
        return False
    if OVERFLOW_URL and OVERFLOW_MODEL and a.name == OVERFLOW_ALIAS and _client_name(req):
        return await _overflow_ok()
    free, total = gpu_mem(a.gpu)
    if not a.lock.locked() and not _must_yield(a) and free >= int(a.mem_fraction * total) + MEM_MARGIN:
        log.info("no-wait %s: card %s has room, starting in background", a.name, a.gpu)
        asyncio.create_task(_background_start(a))
    return False


async def _background_start(a: Alias) -> None:
    try:
        await ensure_running(a)
        a.last_used = time.time()
    except Exception as e:  # noqa: BLE001 — arka plan açılışı; istek zaten cevaplandı
        log.info("background start %s failed: %s", a.name, str(e)[:200])


# ------------------------------------------------------ internal endpoints
def _revision(a: Alias) -> str:
    try:
        return json.loads(MANIFEST.read_text())[a.real_model]["revision"]
    except Exception:  # noqa: BLE001
        return "unknown"


@app.get("/internal/aliases")
async def internal_aliases(req: Request) -> dict:
    _auth(req, internal=True)
    return {a.name: {"real_model": a.real_model, "revision": _revision(a), "gpu": a.gpu,
                     "mem_fraction": a.mem_fraction, "kind": a.kind, "role": a.role,
                     "image": a.image, "args": a.args} for a in ALIASES.values()}


@app.get("/internal/status")
async def internal_status(req: Request) -> dict:
    _auth(req, internal=True)
    gpus = []
    for i in range(pynvml.nvmlDeviceGetCount()):
        free, total = gpu_mem(i)
        gpus.append({"gpu": i, "free_gib": round(free / GIB, 1),
                     "total_gib": round(total / GIB, 1), "holders": gpu_holders(i)})
    now = time.time()
    return {"gpus": gpus, "models": {a.name: {
        "running": _is_running(a), "inflight": a.inflight,
        "idle_sec": int(now - a.last_used), "gpu": a.gpu} for a in ALIASES.values()},
        "analysis_overflow": {"inflight": overflow_inflight, "total": overflow_total, "cap": ANALYSIS_CAP,
                              "bi_max": ANALYSIS_BI_MAX, "priority": OVERFLOW_PRIORITY,
                              "local_priority": {n: v[1] for n, v in _priority_seen.items()},
                              "peer_load": _peer_load[1], "peer_ours": _peer_ours}}


@app.post("/internal/start/{alias}")
async def internal_start(alias: str, req: Request) -> dict:
    _auth(req, internal=True)
    a = ALIASES.get(alias) or _404(alias)
    a.inflight += 1
    try:
        await ensure_running(a)
    finally:
        a.inflight -= 1
        a.last_used = time.time()
    return {"alias": alias, "running": True}


@app.post("/internal/stop/{alias}")
async def internal_stop(alias: str, req: Request) -> dict:
    _auth(req, internal=True)
    a = ALIASES.get(alias) or _404(alias)
    # Bir kitabın işi bitti diye model, başka kitapların istekleri sürerken durdurulmaz. Ölçüldü 2026-10-03:
    # release_models derin görsel modeli öbür kitapların sayfaları işlenirken durduruyordu; derin çağrıların %29'u
    # 500 ile öldü (her biri ~7 dk iş). Model iş başındaysa yalnız «boşta durdurulabilir» işaretlenir: reaper
    # idle_stop_sec sonra kapatır, kartı bekleyen model zaten kart sırasıyla yer alır.
    if _serving(a) > 0 or YIELDING.get(a.name, 0) > 0 or a.lock.locked():
        log.info("stop %s deferred (requested; %d serving, %d waiting)", a.name, _serving(a), YIELDING.get(a.name, 0))
        return {"alias": alias, "running": _is_running(a), "deferred": True}
    await _stop(a, "requested")
    return {"alias": alias, "running": False}


@app.post("/internal/stop-all")
async def internal_stop_all(req: Request) -> dict:
    _auth(req, internal=True)
    for a in ALIASES.values():
        await _stop(a, "stop-all")
    return {"stopped": list(ALIASES)}


def _404(alias: str):
    raise HTTPException(404, {"error": "unknown model", "models": sorted(ALIASES)})


@app.exception_handler(HTTPException)
async def _http_exc(_req: Request, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
