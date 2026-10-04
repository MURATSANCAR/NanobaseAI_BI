"""book-video: kareden video (i2v) ve sesten konuşan çekim (s2v) servisi; gateway takma adı olarak istekte açılır.

Motor Wan 2.2'dir (Apache-2.0; kod imajda sabit sürüm, ağırlıklar /data/editor/models/book-video altında):
    <model_dir>/i2v   Wan2.2-I2V-A14B   (iki uzman: yüksek/düşük gürültü)
    <model_dir>/s2v   Wan2.2-S2V-14B    (ses kodlayıcı wav2vec2 klasörün içinde)
Motorların karşılaştırması (MiniMax-H3, HunyuanVideo 1.5) bitince kazanan bu sözleşmenin arkasına girer; istemci
(production/film/shoot.py) değişmez. Yanıtta `engine` hangi motorun ürettiğini söyler (kayda girer).

Bellek: iki motor aynı kartta birlikte tutulmaz; istenen kip yüklü değilse öbürü boşaltılır. Ağırlıklar dağıtım
sırasında CPU'ya indirilir (offload_model), T5 CPU'da: tek H100'de (94 GB) 720p çalışır. Gateway payı 0.95: ana model
açılıştan önce durur, servis boşta kalınca kapanır, ana model geri kalkar.

Süre: Wan 16 kare/sn üretir; bir parça en çok 81 kare (≈5 sn) — daha uzun çekim, bir önceki parçanın son karesinden
devam eden parçalarla üretilir (i2v), s2v kendi parçalarını (`num_repeat`) sesle sürdürür.

    GET  /health
    POST /v1/video/generations  {model, mode: i2v|s2v, image: png b64, prompt, negative_prompt, seconds, width, height,
                                 seed, audio?: wav b64 (s2v), steps?}  → {video: mp4 b64, seconds, fps, frames, engine}
"""

import argparse
import asyncio
import base64
import gc
import io
import math
import sys
import tempfile
import threading
import time
from pathlib import Path

import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from PIL import Image
from pydantic import BaseModel, Field

sys.path.insert(0, "/opt/Wan2.2")
import wan  # noqa: E402
from wan.configs import WAN_CONFIGS  # noqa: E402
from wan.utils.utils import save_video  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("model_dir")
ap.add_argument("--served-model-name", nargs="*")
ap.add_argument("--gpu-memory-utilization")
ap.add_argument("--port", type=int, default=8000)
args, _ = ap.parse_known_args()

ROOT = Path(args.model_dir)
FPS = 16
CLIP = 81                     # bir parçanın en çok karesi (4n+1)
S2V_CLIP = 80                 # s2v parça boyu (infer_frames)
STEPS = 40
ENGINE = {"i2v": "wan2.2-i2v-a14b", "s2v": "wan2.2-s2v-14b"}
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
_lock = threading.Lock()
_loaded: dict[str, object] = {}


def _engine(mode: str):
    """İstenen kipin motoru; öbürü yüklüyse önce boşaltılır (tek kart)."""
    if mode in _loaded:
        return _loaded[mode]
    for k in list(_loaded):
        del _loaded[k]
    gc.collect()
    torch.cuda.empty_cache()
    common = dict(device_id=0, rank=0, t5_fsdp=False, dit_fsdp=False, use_sp=False, t5_cpu=True,
                  convert_model_dtype=True)
    if mode == "i2v":
        _loaded[mode] = wan.WanI2V(config=WAN_CONFIGS["i2v-A14B"], checkpoint_dir=str(ROOT / "i2v"), **common)
    else:
        _loaded[mode] = wan.WanS2V(config=WAN_CONFIGS["s2v-14B"], checkpoint_dir=str(ROOT / "s2v"), **common)
    return _loaded[mode]


def frames_for(seconds: float, cap: int = CLIP) -> list[int]:
    """Çekim süresini parçalara böler: her parça 4n+1 kare, en çok `cap`; ilk parçadan sonrakiler bir kare örtüşür."""
    total = max(17, round(seconds * FPS) + 1)
    out, left = [], total
    while left > 0:
        n = min(left + (1 if out else 0), cap)
        n = max(17, (n - 1) // 4 * 4 + 1)
        out.append(n)
        left -= n - (1 if len(out) > 1 else 0)
    return out


@app.get("/health")
def health() -> dict:
    return {"ok": True, "loaded": list(_loaded), "engines": ENGINE}


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
    steps: int = Field(STEPS, ge=8, le=60)


def _i2v(r: Req, img: Image.Image) -> torch.Tensor:
    eng = _engine("i2v")
    parts, cur = [], img
    for k, n in enumerate(frames_for(r.seconds)):
        v = eng.generate(r.prompt, cur, max_area=r.width * r.height, frame_num=n, shift=5.0, sample_solver="unipc",
                         sampling_steps=r.steps, guide_scale=(3.5, 3.5), n_prompt=r.negative_prompt,
                         seed=r.seed + k, offload_model=True)            # [C, T, H, W], -1..1
        parts.append(v if k == 0 else v[:, 1:])
        last = ((v[:, -1].clamp(-1, 1) + 1) * 127.5).to(torch.uint8).permute(1, 2, 0).cpu().numpy()
        cur = Image.fromarray(last)
    return torch.cat(parts, dim=1)


def _s2v(r: Req, img: Image.Image, td: Path) -> torch.Tensor:
    if not r.audio:
        raise HTTPException(422, "s2v için ses gerekli")
    eng = _engine("s2v")
    ref, wav = td / "ref.png", td / "a.wav"
    img.save(ref)
    wav.write_bytes(base64.b64decode(r.audio))
    repeat = max(1, math.ceil(r.seconds * FPS / S2V_CLIP))
    v = eng.generate(input_prompt=r.prompt, ref_image_path=str(ref), audio_path=str(wav), enable_tts=False,
                     tts_prompt_audio=None, tts_prompt_text=None, tts_text=None, num_repeat=repeat,
                     max_area=r.width * r.height, infer_frames=S2V_CLIP, shift=3.0, sample_solver="unipc",
                     sampling_steps=r.steps, guide_scale=4.5, n_prompt=r.negative_prompt, seed=r.seed,
                     offload_model=True, init_first_frame=True)
    return v[:, : round(r.seconds * FPS)]


def _run(r: Req) -> dict:
    img = Image.open(io.BytesIO(base64.b64decode(r.image))).convert("RGB")
    t0 = time.time()
    with _lock, tempfile.TemporaryDirectory() as td:
        td = Path(td)
        video = _i2v(r, img) if r.mode == "i2v" else _s2v(r, img, td)
        out = td / "v.mp4"
        save_video(video[None], save_file=str(out), fps=FPS, nrow=1, normalize=True, value_range=(-1, 1))
        data = out.read_bytes()
    frames = int(video.shape[1])
    return {"video": base64.b64encode(data).decode(), "seconds": round(frames / FPS, 3), "fps": FPS,
            "frames": frames, "engine": ENGINE[r.mode], "took": round(time.time() - t0, 1)}


@app.post("/v1/video/generations")
async def generate(r: Req) -> dict:
    return await asyncio.to_thread(_run, r)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")
