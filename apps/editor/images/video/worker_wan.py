"""Wan 2.2 işçisi (ana Python, /opt/Wan2.2 sabit commit). Kod 2026-10-04 server.py'deki üretim yolunun aynısıdır;
yalnız ayrı sürece taşındı. Ağırlıklar: <model_dir>/i2v (Wan2.2-I2V-A14B), <model_dir>/s2v (Wan2.2-S2V-14B).

i2v ve s2v aynı kartta birlikte tutulmaz: istenen kip yüklü değilse öbürü boşaltılır. T5 CPU'da, ağırlıklar dağıtım
sırasında CPU'ya iner (offload_model): tek H100'de 720p.
"""

from __future__ import annotations

import gc
import math
import sys
from pathlib import Path

import torch
from PIL import Image

sys.path.insert(0, "/opt/Wan2.2")
sys.path.insert(0, str(Path(__file__).parent))
import wan  # noqa: E402
from wan.configs import WAN_CONFIGS  # noqa: E402
from wan.utils.utils import save_video  # noqa: E402

import plan  # noqa: E402
from worker_common import Refused, serve  # noqa: E402

ROOT = Path(sys.argv[1])
S2V_CLIP = 80                 # s2v parça boyu (infer_frames)
ENGINE = {"i2v": "wan2.2-i2v-a14b", "s2v": "wan2.2-s2v-14b"}
_loaded: dict[str, object] = {}


def _engine(mode: str):
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


def _i2v(r: dict, img: Image.Image) -> torch.Tensor:
    eng = _engine("i2v")
    parts, cur = [], img
    for k, n in enumerate(plan.frames_for(r["seconds"])):
        v = eng.generate(r["prompt"], cur, max_area=r["width"] * r["height"], frame_num=n, shift=5.0,
                         sample_solver="unipc", sampling_steps=r["steps"], guide_scale=(3.5, 3.5),
                         n_prompt=r["negative_prompt"], seed=r["seed"] + k, offload_model=True)  # [C, T, H, W]
        parts.append(v if k == 0 else v[:, 1:])
        last = ((v[:, -1].clamp(-1, 1) + 1) * 127.5).to(torch.uint8).permute(1, 2, 0).cpu().numpy()
        cur = Image.fromarray(last)
    return torch.cat(parts, dim=1)


def _s2v(r: dict) -> torch.Tensor:
    if not r.get("audio"):
        raise Refused("s2v için ses gerekli")
    eng = _engine("s2v")
    repeat = max(1, math.ceil(r["seconds"] * plan.WAN_FPS / S2V_CLIP))
    v = eng.generate(input_prompt=r["prompt"], ref_image_path=r["image"], audio_path=r["audio"], enable_tts=False,
                     tts_prompt_audio=None, tts_prompt_text=None, tts_text=None, num_repeat=repeat,
                     max_area=r["width"] * r["height"], infer_frames=S2V_CLIP, shift=3.0, sample_solver="unipc",
                     sampling_steps=r["steps"], guide_scale=4.5, n_prompt=r["negative_prompt"], seed=r["seed"],
                     offload_model=True, init_first_frame=True)
    return v[:, : round(r["seconds"] * plan.WAN_FPS)]


def handle(r: dict, td: Path) -> dict:
    img = Image.open(r["image"]).convert("RGB")
    video = _i2v(r, img) if r["mode"] == "i2v" else _s2v(r)
    out = td / "v.mp4"
    save_video(video[None], save_file=str(out), fps=plan.WAN_FPS, nrow=1, normalize=True, value_range=(-1, 1))
    frames = int(video.shape[1])
    return {"file": str(out), "fps": plan.WAN_FPS, "frames": frames, "engine": ENGINE[r["mode"]]}


if __name__ == "__main__":
    serve(handle)
