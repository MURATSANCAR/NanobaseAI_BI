"""FastH3 8-Step V2 işçisi: FastVideo'nun resmî çıkarım yolu (/opt/fastvideo ortamı, FastVideo commit Dockerfile'da
sabit). İki anahtar: `fast-h3` (FastVideo/FastVideo-FastH3-8-Step-V2, bf16) ve `fast-h3-fp8`
(FastVideo/FastVideo-FastH3-8-Step-V2-FP8: transformer FP8 E4M3 kanal başı ölçek, Qwen3-VL NVFP4 → FP4'süz kartta katman
başı açılır, LynnReal hafif video VAE'si).

ÇALIŞTIRILMADI (kullanıcı kararı). Kaynakla eşleme (FastVideo d1416b59):
- Yapılandırma ve istek examples/inference/basic/basic_fasth3.py:283-354 (`build_generator_config`, `build_request`)
  ile aynı alanlar; tek kart: num_gpus=1, FSDP yok, sp_size=1 (kart: «GPU sayısı 56 dikkat başını bölmeli»).
- Ortam değişkenleri aynı dosyanın `profile_environment`'ı (:196-223), «strict» profil + `--vsa-kernel triton
  --no-fa4` (Hopper'da sm100a çekirdeği ve FA4 yok; model kartı: «add --no-replicated-dit --vsa-kernel triton
  --no-fa4»). V2 VSA-H3 dikkat arka ucunu ister (kart); seyreklik 0,8, döşeme 64 (fastvideo_inference.json).
- Adım: 9 sigma noktası = 8 ileri geçiş; başka ızgara reddedilir (basic_fasth3_8step.py). Kayma 10/3 ve DMD
  basamakları checkpoint'teki fastvideo_inference.json'dan otomatik okunur.
- V2 indirmesi yalnız transformer + yapılandırma taşır; ortak parçalar MiniMax-H3 ile birebir (34/34 özet). Klasör,
  basic_fasth3_omniref_pdd.py:145-191 `compose_model_dir` desenindeki gibi sembolik bağlarla birleştirilir.

KAPSAM (model kartı «Scope»): V2 yalnız metinden video+ses (T2VA) damıtıldı; «FL2VA and Ref2VA were not distilled»,
FastVideo yemek kitabı da CUDA'da FL2VA/Ref2VA'yı yalnız tam H3 için listeler. Bu yüzden:
- i2v → t2va: onaylı ilk kare modele GİRMEZ (yanıtta `first_frame_used: false`); karakter tutarlılığı yalnız
  istemle sağlanır.
- s2v → 422: replik izine dudak uyumu bu checkpoint'te yok; konuşan çekim için `h3`.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import plan  # noqa: E402
from worker_common import Refused, serve  # noqa: E402

MODELS = Path(sys.argv[1])
VARIANT = os.environ.get("FAST_H3_VARIANT", "fast-h3")            # server.py işçiyi motor adıyla başlatır
SHORT_EDGE = int(os.environ.get("FAST_H3_SHORT_EDGE", str(plan.FAST_H3_SHORT_EDGE)))
STEPS = 9
SHARED = ("text_encoder", "tokenizer", "processor", "vae", "audio_vae", "model_index.json")
ENV = {                                          # basic_fasth3.profile_environment, strict + triton VSA, FA4 yok
    "FASTVIDEO_ATTENTION_BACKEND": "VIDEO_SPARSE_ATTN_H3", "FASTVIDEO_VSA_SM100A": "0", "FASTVIDEO_VSA_TK": "0",
    "FASTVIDEO_VSA_CUTEDSL": "0", "FASTVIDEO_DISABLE_ATTENTION_COMPILE": "0", "FASTVIDEO_FA4": "0",
    "FASTVIDEO_NVFP4_FA4": "0", "FASTVIDEO_MINIMAX_H3_FA4_PACKED_VARLEN": "0", "FASTVIDEO_MINIMAX_H3_FUSIONS": "0",
    "FASTVIDEO_INFERENCE_TORCH_COMPILE": "0", "FASTVIDEO_VAE_PARALLEL_DECODE": "0", "FASTVIDEO_VAE_PARALLEL_ENCODE": "0",
    "FASTVIDEO_VAE_PARALLEL_DECODE_STRATEGY": "gather", "FASTVIDEO_STAGE_LOGGING": "1"}
_gen = None


def compose(variant_dir: Path, base_dir: Path, out: Path) -> Path:
    """Damıtılmış parçalar (transformer, zamanlayıcılar, fastvideo_inference.json, dizin) variant'tan, eksik ortak
    parçalar MiniMax-H3'ten — sembolik bağlı tek model klasörü. FP8 deposu tam olduğu için ondan hiçbir şey eksik
    kalmaz, yalnız kendi dosyalarına bağlanır."""
    out.mkdir(parents=True, exist_ok=True)
    for p in variant_dir.iterdir():
        if not p.name.startswith("."):
            (out / p.name).symlink_to(p)
    for name in SHARED:
        if not (out / name).exists():
            src = base_dir / name
            if not src.exists():
                raise RuntimeError(f"FastH3 ortak parça yok: {src}")
            (out / name).symlink_to(src)
    return out


def _load():
    global _gen
    if _gen is not None:
        return _gen
    os.environ.update(ENV)
    from fastvideo import VideoGenerator
    from fastvideo.api import (CompileConfig, ComponentConfig, EngineConfig, GeneratorConfig, OffloadConfig,
                               ParallelismConfig, PipelineSelection)
    model = compose(MODELS / VARIANT, MODELS / "h3", Path(tempfile.mkdtemp(prefix="fasth3-")) / "model")
    cfg = GeneratorConfig(
        model_path=str(model),
        pipeline=PipelineSelection(
            components=ComponentConfig(),
            experimental={"attention_backend": "VIDEO_SPARSE_ATTN_H3", "inference_torch_compile": False,
                          "vae_parallel_decode": False, "vae_parallel_decode_strategy": "gather",
                          "VSA_sparsity": 0.8, "VSA_tile_size": 64}),
        engine=EngineConfig(
            num_gpus=1, execution_backend="mp", use_fsdp_inference=False,
            parallelism=ParallelismConfig(tp_size=1, sp_size=1),
            # Tek kart: transformer kartta (bf16 ~70 GB / fp8 daha az), Qwen3-VL ve VAE iş bitince CPU'ya iner.
            offload=OffloadConfig(dit=False, dit_layerwise=os.environ.get("FAST_H3_DIT_LAYERWISE") == "1",
                                  text_encoder=True, vae=True, pin_cpu_memory=True, lazy_module_load=None),
            compile=CompileConfig(enabled=False)))
    _gen = VideoGenerator.from_config(cfg)
    return _gen


def handle(r: dict, td: Path) -> dict:
    task = plan.h3_task("fast-h3", r["mode"], 0)
    if task != "t2va":
        raise Refused("fast-h3 (FastH3 V2) yalnız metinden video üretir; konuşan çekim (s2v) için h3 kullanın")
    from fastvideo.api import GenerationRequest, OutputConfig, SamplingConfig
    gen = _load()
    W, H = plan.h3_canvas(r["width"], r["height"], short_edge=SHORT_EDGE)
    n = plan.h3_frames(r["seconds"])
    raw = td / "fasth3.mp4"
    res = gen.generate(GenerationRequest(
        prompt=plan.h3_prompt(task, r["prompt"], 0), negative_prompt="",
        sampling=SamplingConfig(height=H, width=W, num_frames=n, fps=plan.H3_FPS, num_inference_steps=STEPS,
                                guidance_scale=1.0, batch_cfg=False, seed=r["seed"]),
        output=OutputConfig(output_path=str(raw), save_video=True, return_frames=False)))
    src = Path(getattr(res, "video_path", None) or raw)
    keep = min(n, max(1, round(r["seconds"] * plan.H3_FPS)))
    out = td / "v.mp4"
    # Üretilen ses atılır (-an), istenen süreye kesilir.
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-frames:v", str(keep), "-an", "-c:v", "libx264",
                    "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p", str(out)], check=True, timeout=600)
    return {"file": str(out), "fps": plan.H3_FPS, "frames": int(keep), "engine": f"{VARIANT}-8step-v2-t2va",
            "canvas": [W, H], "steps": STEPS - 1, "refs_used": 0, "first_frame_used": False}


if __name__ == "__main__":
    serve(handle)
