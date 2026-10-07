"""FastH3 8-Step V2 işçisi: ComfyUI'nin MiniMax-H3 düğümleri grafiksiz (kütüphane olarak) çağrılır.

Neden ComfyUI: indirilen ağırlık FastVideo/FastVideo-FastH3-Comfy'dir (diffusion_models + vae). Bu dosya «pruned»
biçimdedir (`adaln_t_table` [1025, 8] + blok başına rank-8 adaLN izdüşümü); diffusers bunu açıkça reddeder
(single_file_utils.py:4250 «This is a pruned MiniMax-H3 checkpoint ... does not support»), FastVideo kendi HF
biçimini yükler (registry.py:1272-1296, dosyada `adaln_t_table` geçmez). Yükleyen tek kod ComfyUI'dir
(comfy/model_detection.py:403, comfy/ldm/minimax/model.py:501/744).

ÇALIŞTIRILMADI (kullanıcı kararı). Düğüm sırası Comfy-Org/workflow_templates video_fastvideo_fasth3_i2v.json alt
grafiğinin aynısıdır (düğüm kimlikleri parantezde); her çağrının imzası ComfyUI b00c6e95 kaynağından:
  UNETLoader(6) → comfy.sd.load_diffusion_model                      sd.py:2426
  VAELoader(11, 24) → comfy.sd.VAE(sd, metadata)                        nodes.py:844-864
  CLIPLoader(13, type minimax) → comfy.sd.load_text_encoder_state_dicts  sd.py:1777, QWEN3VL_32B dalı 1995
  MiniMaxH3SigmaShift(143) shift 10 / 3                                 nodes_minimax_h3.py:392
  MiniMaxH3ImageToVideo(104)                                            nodes_minimax_h3.py:139
  [yalnız s2v] MiniMaxH3AddGuide(audio, frame_idx=0)                    nodes_minimax_h3.py:191
  BasicScheduler(9) simple / 8 / 1.0, KSamplerSelect(17) res_multistep  nodes_custom_sampler.py:33, 390
  BasicGuider(16), RandomNoise(15), SamplerCustomAdvanced(14)           nodes_custom_sampler.py:816, 1014, 1040
  VAEDecode(10)                                                         nodes.py:338
Şablondaki iki hız düğümü kullanılmaz: BlockSparseAttention(127, VSA %10 tutma, adımların %20'sinden sonra) ve
ModelAttentionBackend(128). İkisi de yoğun dikkatin yaklaşığıdır; yoğun dikkat doğruluk açısından güvenli yoldur, hız
ölçüsü ilk kurulumda alınır.

Metin kodlayıcı: FastH3-Comfy'nin text_encoders/ klasörü indirilmedi. Aynı ağırlık (Qwen3-VL-32B, H3 tokenizer'ı)
MiniMax-H3/text_encoder altında HF parçaları olarak var; ComfyUI'nin kendi Qwen3-VL dallarında yaptığı önek çevirisi
(sd.py:1957 `{"model.language_model.": "model.", "model.visual.": "visual.", "lm_head.": "model.lm_head."}`)
uygulanır ve 50. katmandan sonrası, son norm ve lm_head atılır (ComfyUI'nin dönüştürülmüş dosyası da 50 katmanda
kesik, son normsuz: text_encoders/llama.py:366-374 Qwen3VL_32BConfig). Algılama anahtarları
(sd.py:1731 `visual.deepstack_merger_list.0.norm.weight` + `model.layers.49.self_attn.q_proj.weight`) bu çeviriden
sonra oluşur. DOĞRULANMADI: bu yol ComfyUI'nin kendi dosyasıyla bayt bayt aynı değil; ilk kurulumda iki yolun
koşullama çıktısı karşılaştırılmalı ya da qwen3vl_32b_minimax_h3_bf16.safetensors indirilmeli (FAST_H3_TE ile verilir).

Ses: s2v'de replik izimiz 0. kareye ses çıpası olarak verilir (koşul satırı, her adımda sabit; PackedLayout
model.py:387-394). Üretilen ses atılır, film bizim izimizle kurgulanır. Karakter kartları (refs) FastH3'te
kullanılmaz: damıtılan öğrenci yalnız transformer/ (t2va/fl2va) bölümüdür, ref2va yoktur.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from PIL import Image

sys.path.insert(0, "/opt/ComfyUI")
sys.path.insert(0, str(Path(__file__).parent))
import comfy.options  # noqa: E402,F401 — args_parsing False: ComfyUI argv okumaz, varsayılan ayarlar
import comfy.sd  # noqa: E402
import comfy.utils  # noqa: E402
import nodes  # noqa: E402
from comfy_extras.nodes_custom_sampler import (  # noqa: E402
    BasicGuider, BasicScheduler, KSamplerSelect, RandomNoise, SamplerCustomAdvanced)
from comfy_extras.nodes_minimax_h3 import (  # noqa: E402
    MiniMaxH3AddGuide, MiniMaxH3ImageToVideo, MiniMaxH3SigmaShift)
from safetensors.torch import load_file  # noqa: E402

import plan  # noqa: E402
from worker_common import Refused, pad_wav, serve, write_mp4  # noqa: E402

MODELS = Path(sys.argv[1])
ROOT = MODELS / "fast-h3"
DIT = os.environ.get("FAST_H3_DIT", "fastvideo_fasth3_8step_v2_pruned_bf16.safetensors")
VIDEO_VAE = "minimax_h3_video_vae_fp16.safetensors"
AUDIO_VAE = "minimax_h3_audio_vae_fp32.safetensors"
TE = os.environ.get("FAST_H3_TE", "")                  # boşsa h3/text_encoder HF parçaları
SHORT_EDGE = int(os.environ.get("FAST_H3_SHORT_EDGE", str(plan.FAST_H3_SHORT_EDGE)))
STEPS, SHIFT_VIDEO, SHIFT_AUDIO, SAMPLER = 8, 10.0, 3.0, "res_multistep"
TE_LAYERS = 50
_m: dict = {}


def _vae(path: Path):
    sd, metadata = comfy.utils.load_torch_file(str(path), return_metadata=True)
    vae = comfy.sd.VAE(sd=sd, metadata=metadata)
    vae.throw_exception_if_invalid()
    return vae


def _hf_text_encoder() -> dict:
    """MiniMax-H3/text_encoder HF parçaları → ComfyUI'nin MiniMax Qwen3-VL-32B anahtar düzeni (50 katman)."""
    d = MODELS / "h3" / "text_encoder"
    index = json.loads((d / "model.safetensors.index.json").read_text())["weight_map"]
    sd: dict = {}
    for shard in sorted(set(index.values())):
        sd.update(load_file(str(d / shard)))
    sd = comfy.utils.state_dict_prefix_replace(sd, {"model.language_model.": "model.", "model.visual.": "visual.",
                                                     "lm_head.": "model.lm_head."})
    drop = [k for k in sd if k.startswith("model.lm_head.") or k == "model.norm.weight" or
            (k.startswith("model.layers.") and int(k.split(".")[2]) >= TE_LAYERS)]
    for k in drop:
        del sd[k]
    return sd


def _load():
    if _m:
        return _m
    _m["model"] = MiniMaxH3SigmaShift.execute(comfy.sd.load_diffusion_model(str(ROOT / "diffusion_models" / DIT)),
                                              SHIFT_VIDEO, SHIFT_AUDIO).args[0]
    _m["vae"] = _vae(ROOT / "vae" / VIDEO_VAE)
    _m["audio_vae"] = _vae(ROOT / "vae" / AUDIO_VAE)
    if TE:
        _m["clip"] = comfy.sd.load_clip(ckpt_paths=[TE], clip_type=comfy.sd.CLIPType.MINIMAX)
    else:
        _m["clip"] = comfy.sd.load_text_encoder_state_dicts([_hf_text_encoder()], clip_type=comfy.sd.CLIPType.MINIMAX)
    return _m


def handle(r: dict, td: Path) -> dict:
    task = plan.h3_task("fast-h3", r["mode"], 0)
    if task == "fl2va+audio" and not r.get("audio"):
        raise Refused("s2v için ses gerekli")
    m = _load()
    W, H = plan.h3_canvas(r["width"], r["height"], short_edge=SHORT_EDGE)
    n = plan.h3_frames(r["seconds"])
    img = torch.from_numpy(np.asarray(Image.open(r["image"]).convert("RGB"), dtype=np.float32) / 255.0)[None]
    cond, latent = MiniMaxH3ImageToVideo.execute(m["clip"], m["vae"], plan.h3_prompt(task, r["prompt"], 0), W, H, n,
                                                 first_frame=img).args
    if task == "fl2va+audio":
        wav = td / "a32k.wav"
        pad_wav(Path(r["audio"]), n / plan.H3_FPS, wav, 32000)
        data, sr = sf.read(str(wav), dtype="float32", always_2d=True)          # (N, 1)
        stereo = torch.from_numpy(np.repeat(data.T, 2, axis=0).copy())[None]     # [1, 2, N]: H3 stereo
        cond = MiniMaxH3AddGuide.execute(cond, latent, 0, audio_vae=m["audio_vae"],
                                         audio={"waveform": stereo, "sample_rate": sr}).args[0]
    sigmas = BasicScheduler.execute(m["model"], "simple", STEPS, 1.0).args[0]
    sampler = KSamplerSelect.execute(SAMPLER).args[0]
    guider = BasicGuider.execute(m["model"], cond).args[0]
    noise = RandomNoise.execute(r["seed"]).args[0]
    out = SamplerCustomAdvanced.execute(noise, guider, sampler, sigmas, latent).args[0]
    images = nodes.VAEDecode().decode(m["vae"], out)[0]                         # [T, H, W, C], 0..1
    keep = min(images.shape[0], max(1, round(r["seconds"] * plan.H3_FPS)))
    u8 = (images[:keep].clamp(0, 1) * 255).round().to(torch.uint8).cpu().numpy()
    path = td / "v.mp4"
    write_mp4(u8, plan.H3_FPS, path)
    return {"file": str(path), "fps": plan.H3_FPS, "frames": int(keep), "engine": f"fasth3-8step-v2-{task}",
            "canvas": [W, H], "steps": STEPS, "refs_used": 0}


if __name__ == "__main__":
    serve(handle)
