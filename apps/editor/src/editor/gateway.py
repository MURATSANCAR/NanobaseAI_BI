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
PASSTHROUGH = {"chat/completions", "completions", "embeddings", "rerank", "score",
               "pooling", "classify", "tokenize", "detokenize",
               "images/generations"}      # book-image (vLLM-Omni); edits go as JSON chat/completions
HOP = {"content-length", "transfer-encoding", "connection", "keep-alive", "content-encoding"}

# Taşma (kullanıcı kararı 2026-09-21): aynı model (Qwen3.8-27B-FP8) GPU 0'da BI için de açık. Etkileşimli
# soru, yönetici model GPU 1'de kapalıyken ve kart analizle doluyken beklemek yerine o eşe gider; iki kopya
# aynı ağırlık ve aynı sunum ayarıyla çalışır (bağlam 131072, qwen3 akıl yürütme ayrıştırıcısı, MTP).
# Yalnız EDITOR_OVERFLOW_CLIENTS'taki konteynerlerden gelen istekler taşar; analiz işçisi taşmaz.
# Boş bırakılırsa taşma kapalıdır.
OVERFLOW_ALIAS = os.environ.get("EDITOR_OVERFLOW_ALIAS", "book-director")
OVERFLOW_URL = os.environ.get("EDITOR_OVERFLOW_URL", "").rstrip("/")
OVERFLOW_MODEL = os.environ.get("EDITOR_OVERFLOW_MODEL", "")
OVERFLOW_CLIENTS = {c.strip() for c in os.environ.get("EDITOR_OVERFLOW_CLIENTS", "").split(",") if c.strip()}


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
    return dk.containers.create(
        a.image, cmd, entrypoint=a.entrypoint or None, name=a.container, labels=labels, detach=True,
        network=NETWORK, ipc_mode="host", shm_size="16g",
        ulimits=[Ulimit(name="memlock", soft=-1, hard=-1)],
        device_requests=[DeviceRequest(device_ids=[str(a.gpu)], capabilities=[["gpu"]])],
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
    WAITING.add(a.name)
    try:
        await _make_room_inner(a, need, deadline)
    finally:
        WAITING.discard(a.name)


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
        idle = sorted((o for o in others if o.inflight == 0), key=lambda o: o.always_on)
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


def _would_wait(a: Alias) -> bool:
    """`a`yı şimdi başlatmak kartta meşgul bir modelin bitmesini beklemeyi gerektirir mi?
    Boş bellek + boşta duran editör modellerinin bırakacağı bellek yetiyorsa beklemez."""
    free, total = gpu_mem(a.gpu)
    need = int(a.mem_fraction * total) + MEM_MARGIN
    if free >= need:
        return False
    others = [o for o in ALIASES.values() if o.name != a.name and o.gpu == a.gpu and _is_running(o)]
    reclaimable = sum(int(o.mem_fraction * total) for o in others if o.inflight == 0)
    return free + reclaimable < need


def _client_name(req: Request) -> str:
    """İsteği atan konteynerin adı (editor-net üzerinde ters DNS); çözülemezse boş."""
    host = req.client.host if req.client else ""
    if not host:
        return ""
    for name in OVERFLOW_CLIENTS:
        try:
            if host in {ai[4][0] for ai in socket.getaddrinfo(name, None)}:
                return name
        except OSError:
            continue
    return ""


async def _overflow_ok() -> bool:
    try:
        r = await http.get(f"{OVERFLOW_URL}/v1/models", timeout=5.0)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


async def _should_overflow(a: Alias, req: Request) -> bool:
    if not (OVERFLOW_URL and OVERFLOW_MODEL and a.name == OVERFLOW_ALIAS):
        return False
    if not _client_name(req):
        return False                      # analiz işçisi ve diğerleri: hiçbir koşulda taşmaz
    if _is_running(a) and await _healthy(a):
        return False                      # yönetici model GPU 1'de açık: orada cevaplanır
    # Kapalı model de "meşgul"dür: soğuk açılış ~100 sn sürüyor (ölçüldü: "ana karakter kim"
    # 111 sn'de cevaplandı, kullanıcı ekranda boş bekledi). Aynı model GPU 0'da zaten ayakta;
    # etkileşimli soru oradan anında cevaplanır. GPU 1 bir sonraki analiz ihtiyacında açılır.
    return await _overflow_ok()


async def ensure_running(a: Alias) -> None:
    from .foundation import assert_enabled
    try:
        await asyncio.to_thread(assert_enabled)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from None
    if _is_running(a) and await _healthy(a):
        return
    async with a.lock:
        if _is_running(a) and await _healthy(a):
            return
        c = await asyncio.to_thread(_ensure_created, a)
        if c.status != "running":
            await _make_room(a)
            log.info("start %s on gpu %s", a.name, a.gpu)
            await asyncio.to_thread(c.start)
        t0 = time.time()
        while time.time() - t0 < a.start_timeout_sec:
            if await _healthy(a):
                log.info("ready %s in %.0fs", a.name, time.time() - t0)
                a.last_used = time.time()
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
    # Another model is waiting for room on this card: coming back now would only be pushed
    # out again (measured: a start/stop loop every 50 s that stalled an analysis for an hour).
    if any(ALIASES[w].gpu == a.gpu for w in WAITING if w in ALIASES):
        return
    from .foundation import assert_enabled
    try:
        await asyncio.to_thread(assert_enabled)
    except RuntimeError:
        return                                # maintenance: nothing is started
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
    _auth(req)
    from .foundation import assert_enabled
    try:
        await asyncio.to_thread(assert_enabled)
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
    a.inflight += 1
    released = False

    def release() -> None:
        nonlocal released
        if not released:
            released = True
            a.inflight -= 1
            a.last_used = time.time()

    try:
        if await _should_overflow(a, req):
            # Aynı modelin GPU 0'daki eşi; yalnız sunulan ad farklı, gövdedeki model adı ona çevrilir.
            log.info("overflow %s → %s (gpu %s busy, client %s)", a.name, OVERFLOW_URL, a.gpu, _client_name(req))
            payload["model"] = OVERFLOW_MODEL
            body = json.dumps(payload).encode()
            url = f"{OVERFLOW_URL}/v1/{path}"
        else:
            await ensure_running(a)
            url = f"{a.upstream}/v1/{path}"
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
        r = await http.post(url, content=body, headers=headers)
        release()
        return Response(r.content, status_code=r.status_code,
                        headers={k: v for k, v in r.headers.items() if k.lower() not in HOP})
    except BaseException:
        release()
        raise


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
        "idle_sec": int(now - a.last_used), "gpu": a.gpu} for a in ALIASES.values()}}


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
