"""book-video: kareden video (i2v), sesten konuşan çekim (s2v) ve çekim iyileştirme servisi; gateway takma adı olarak
istekte açılır.

Motorlar (gövdede `engine`, yoksa VIDEO_ENGINE ortam değişkeni, o da yoksa h3; sıra: h3, fast-h3 hızlı kip, wan2.2
yedek; VIDEO_LICENSED_ENGINES verilirse yalnız listedekiler açık):
    wan2.2   Wan 2.2 I2V-A14B / S2V-14B (Apache-2.0)                         <model_dir>/i2v, <model_dir>/s2v
    h3       MiniMax-H3 Base, diffusers ModularPipeline (fl2va / ref2va)      <model_dir>/h3
    fast-h3  FastVideo FastH3 8-Step V2, ComfyUI düğümleri (fl2va)            <model_dir>/fast-h3 (+ h3/text_encoder)
İyileştirme: SeedVR2 7B sharp + Practical-RIFE 4.26                          <model_dir>/enhance/{seedvr2,rife}

Her motor ayrı süreçte çalışır (worker_*.py; Wan ana Python'da, diğerleri /opt/h3 ortamında — Wan
transformers ≤4.51.3 ister, H3'ün Qwen3-VL kodlayıcısı daha yenisini). Kartta aynı anda tek işçi vardır: başka motor
istenince yüklü işçi kapatılır, GPU ve CPU belleği süreçle birlikte boşalır. İstekler sırayla işlenir (tek kart).

H3 ve FastH3 görüntüyle birlikte ses de üretir; o ses atılır. Filmin sesi bizim Türkçe replik izimizdir (kurgu,
production/film/mix.py). s2v'de replik izi H3'e ağız hareketi için verilir (plan.h3_task).

    GET  /health
    POST /v1/video/generations  {model, mode: i2v|s2v, image: png b64, prompt, negative_prompt, seconds, width, height,
                                 seed, audio?: wav b64 (s2v), steps?, engine?: wan2.2|h3|fast-h3,
                                 refs?: [png b64] (karakter kartları)}
                                 → {video: mp4 b64, seconds, fps, frames, engine}
                                 409: motor bu kurulumda lisans ayarıyla kapalı (VIDEO_LICENSED_ENGINES)
    POST /v1/video/enhance      {model, video: mp4 b64, target: 1080p|4k, fps: 24|30}
                                 → {video: mp4 b64, width, height, fps, engine}
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import itertools
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).parent))
import plan  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("model_dir")
ap.add_argument("--served-model-name", nargs="*")
ap.add_argument("--gpu-memory-utilization")
ap.add_argument("--port", type=int, default=8000)
args, _ = ap.parse_known_args()

ROOT = Path(args.model_dir)
HERE = Path(__file__).parent
PYTHON = {"wan": sys.executable, "h3": "/opt/h3/bin/python", "fasth3": "/opt/h3/bin/python",
          "enhance": "/opt/h3/bin/python"}
DEFAULT_ENGINE = plan.default_engine()
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
_lock = threading.Lock()
_ids = itertools.count(1)


class Worker:
    """Kartta yüklü tek işçi süreci."""

    def __init__(self):
        self.name: str | None = None
        self.proc: subprocess.Popen | None = None

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.stdin.close()
            try:
                self.proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.proc, self.name = None, None

    def call(self, name: str, req: dict, td: Path) -> dict:
        if self.name != name or self.proc is None or self.proc.poll() is not None:
            self.stop()
            self.proc = subprocess.Popen([PYTHON[name], str(HERE / f"worker_{name}.py"), str(ROOT)],
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr, text=True,
                                         bufsize=1)
            self.name = name
        mid = next(_ids)
        self.proc.stdin.write(json.dumps({"id": mid, "req": req, "td": str(td)}) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            code = self.proc.wait()
            self.proc, self.name = None, None
            raise HTTPException(500, f"{name} işçisi kapandı (çıkış {code})")
        rep = json.loads(line)
        if not rep["ok"]:
            raise HTTPException(rep.get("status", 500), rep["error"])
        return rep["out"]


_worker = Worker()


@app.get("/health")
def health() -> dict:
    return {"ok": True, "loaded": _worker.name, "default_engine": DEFAULT_ENGINE, "engines": list(plan.ENGINES),
            "licensed": sorted(plan.licensed_engines())}


class Req(BaseModel):
    model: str = "book-video"
    mode: str = Field("i2v", pattern="^(i2v|s2v)$")
    image: str
    prompt: str = Field(..., max_length=4000)
    negative_prompt: str = Field("", max_length=2000)
    seconds: float = Field(..., gt=0.5, le=15)
    width: int = Field(1280, ge=256, le=1920)
    height: int = Field(720, ge=256, le=1920)
    seed: int = 0
    audio: str | None = None
    steps: int | None = Field(None, ge=2, le=60)
    engine: str | None = Field(None, pattern=r"^(wan2\.2|h3|fast-h3)$")
    refs: list[str] = Field(default_factory=list, max_length=plan.MAX_REFS)


class EnhanceReq(BaseModel):
    model: str = "book-video"
    video: str
    target: str = Field("1080p", pattern="^(1080p|4k)$")
    fps: int = Field(24)


def _b64file(data: str, path: Path) -> str:
    path.write_bytes(base64.b64decode(data))
    return str(path)


def _generate(r: Req) -> dict:
    engine = r.engine or DEFAULT_ENGINE
    why = plan.license_error(engine)
    if why:
        raise HTTPException(409, why)
    if r.mode == "s2v" and not r.audio:
        raise HTTPException(422, "s2v için ses gerekli")
    t0 = time.time()
    with _lock, tempfile.TemporaryDirectory() as td:
        td = Path(td)
        req = {"mode": r.mode, "prompt": r.prompt, "negative_prompt": r.negative_prompt, "seconds": r.seconds,
               "width": r.width, "height": r.height, "seed": r.seed,
               "steps": r.steps or (40 if engine == "wan2.2" else None),
               "image": _b64file(r.image, td / "first.png"),
               "audio": _b64file(r.audio, td / "talk.wav") if r.audio else None,
               "refs": [_b64file(x, td / f"ref{i}.png") for i, x in enumerate(r.refs, 1)]}
        out = _worker.call(plan.worker_of(engine), req, td)
        data = Path(out["file"]).read_bytes()
    res = {"video": base64.b64encode(data).decode(), "seconds": round(out["frames"] / out["fps"], 3),
           "fps": out["fps"], "frames": out["frames"], "engine": out["engine"], "took": round(time.time() - t0, 1)}
    for k in ("canvas", "steps", "refs_used"):
        if k in out:
            res[k] = out[k]
    return res


def _enhance(r: EnhanceReq) -> dict:
    if r.fps not in (24, 30):
        raise HTTPException(422, "fps 24 ya da 30 olmalı")
    t0 = time.time()
    with _lock, tempfile.TemporaryDirectory() as td:
        td = Path(td)
        out = _worker.call("enhance", {"video": _b64file(r.video, td / "in.mp4"), "target": r.target, "fps": r.fps},
                           td)
        data = Path(out["file"]).read_bytes()
    return {"video": base64.b64encode(data).decode(), "width": out["width"], "height": out["height"],
            "fps": out["fps"], "engine": out["engine"], "took": round(time.time() - t0, 1)}


@app.post("/v1/video/generations")
async def generate(r: Req) -> dict:
    return await asyncio.to_thread(_generate, r)


@app.post("/v1/video/enhance")
async def enhance(r: EnhanceReq) -> dict:
    return await asyncio.to_thread(_enhance, r)


if __name__ == "__main__":
    os.environ.setdefault("HF_HUB_OFFLINE", "1")      # ağırlıklar yerelde; işçiler HF'ye çıkmaz
    try:
        uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")
    finally:
        _worker.stop()
