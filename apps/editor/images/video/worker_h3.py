"""MiniMax-H3 işçisi (diffusers, /opt/h3 sanal ortamı; diffusers commit Dockerfile'da sabit).

ÇALIŞTIRILMADI (2026-10-07, kullanıcı kararı: modeller kurulum gecesinde kalkar). Her çağrı diffusers kaynağıyla
eşlendi (commit c6df88a5, dosya:satır):
- Yükleme: `ModularPipeline.from_pretrained(<yerel klasör>, components_manager=...)` — modular_pipeline.py:1903;
  yerel kopyada dizin `MiniMaxAI/MiniMax-H3`'ü gösterse de dosyası yerelde olan bileşen yerelden yüklenir
  (modular_pipeline.py:1813-1817 `_is_local_component`). `load_components(dtype=...)` başarısız bileşende yalnız uyarı
  yazar (2551-2576) → yüklendikten sonra burada açıkça denetlenir.
- Tek kart: `ComponentsManager.enable_auto_cpu_offload(device, memory_reserve_margin)` — components_manager.py:699;
  docs/source/en/api/pipelines/minimax_h3.md «On one 80 GB card» tarifi. Transformer 61,7 GB + Qwen3-VL 62,1 GB
  bf16 aynı anda sığmaz; yönetici her bileşeni sırası gelince karta alır, yer gerekince ötekini CPU'ya indirir.
- Çağrı girdileri: modular_blocks_minimax_h3.py:682-735 (`image`, `references`, `height`, `width`, `num_frames`,
  `num_inference_steps`, `generator`, `output_type`); çıktı `videos`/`audio`/`sampling_rate` (736-742).
  Damıtılmış (CFG-distilled) ağırlık: negatif istem ve guidance yok (modular_pipeline.py sınıf belgesi).
- Adım: varsayılan 50 (InputParam şablonu modular_pipeline_utils.py:395-398; SGLang minimax_h3.py:44 da 50).
- ref2va referansları: references.py:82-209 (`MiniMaxH3ImageReference(image)`, `MiniMaxH3AudioReference(audio
  (C, N) tensor, sample_rate)`); ses tek başına referans olamaz, en az bir görselle gelir.

Ses: H3 sesi atılır; filmin sesi bizim Türkçe replik izimizdir. s2v'de ağız hareketi için replik izi <Audio 1>
`fully_copy` olarak verilir (plan.h3_prompt). Türkçe H3'ün «kararlı 11 dil» listesinde değil («diğer diller değişen
ölçüde»); dudak uyumunun ölçüsü ilk kurulumda alınacak.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from diffusers import ComponentsManager, ModularPipeline
from diffusers.modular_pipelines.minimax_h3 import MiniMaxH3AudioReference, MiniMaxH3ImageReference
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import plan  # noqa: E402
from worker_common import Refused, pad_wav, serve, write_mp4  # noqa: E402

ROOT = Path(sys.argv[1]) / "h3"
STEPS = int(os.environ.get("H3_STEPS", "50"))
MARGIN = os.environ.get("H3_MEMORY_MARGIN", "12GB")
ATTENTION = os.environ.get("H3_ATTENTION", "")          # örn. "_flash_3_hub" (Hopper; çekirdek Hub'dan iner)
_pipe = None


def _load():
    global _pipe
    if _pipe is not None:
        return _pipe
    manager = ComponentsManager()
    pipe = ModularPipeline.from_pretrained(str(ROOT), components_manager=manager)
    # workflow= verilmez: iki transformer bölümü (transformer/ fl2va, transformer_ref/ ref2va) CPU belleğine iner,
    # çağrı girdisine göre iş akışı seçilir (minimax_h3.md «A plain load_components() ... pulls both»).
    pipe.load_components(dtype=torch.bfloat16)
    missing = [n for n in ("text_encoder", "tokenizer", "processor", "vae", "audio_vae", "transformer",
                           "transformer_ref", "scheduler", "audio_scheduler") if getattr(pipe, n, None) is None]
    if missing:
        raise RuntimeError(f"H3 bileşenleri yüklenemedi: {missing} ({ROOT})")
    manager.enable_auto_cpu_offload(device="cuda", memory_reserve_margin=MARGIN)
    if ATTENTION:
        for n in ("transformer", "transformer_ref"):
            getattr(pipe, n).set_attention_backend(ATTENTION)
    _pipe = pipe
    return pipe


def handle(r: dict, td: Path) -> dict:
    task = plan.h3_task("h3", r["mode"], len(r.get("refs", [])))
    if task == "ref2va" and not r.get("audio"):
        raise Refused("s2v için ses gerekli")
    pipe = _load()
    W, H = plan.h3_canvas(r["width"], r["height"])
    n = plan.h3_frames(r["seconds"])
    first = Image.open(r["image"]).convert("RGB")
    common = dict(prompt=plan.h3_prompt(task, r["prompt"], len(r.get("refs", []))), height=H, width=W, num_frames=n,
                  num_inference_steps=r.get("steps") or STEPS, generator=torch.Generator().manual_seed(r["seed"]),
                  output_type="np", output="videos")
    if task == "fl2va":
        videos = pipe(image=first, **common)
    else:
        wav = td / "a32k.wav"
        pad_wav(Path(r["audio"]), n / plan.H3_FPS, wav, 32000)
        data, sr = sf.read(str(wav), dtype="float32", always_2d=True)          # (N, C)
        refs = [MiniMaxH3ImageReference(image=first)]
        refs += [MiniMaxH3ImageReference(image=Image.open(p).convert("RGB")) for p in r.get("refs", [])]
        refs.append(MiniMaxH3AudioReference(audio=torch.from_numpy(data.T.copy()), sample_rate=sr))
        videos = pipe(references=refs, **common)
    frames = np.asarray(videos[0])                                              # [T, H, W, C], 0..1
    keep = min(len(frames), max(1, round(r["seconds"] * plan.H3_FPS)))
    u8 = (frames[:keep].clip(0, 1) * 255).round().astype(np.uint8)
    out = td / "v.mp4"
    write_mp4(u8, plan.H3_FPS, out)
    return {"file": str(out), "fps": plan.H3_FPS, "frames": int(keep), "engine": f"minimax-h3-{task}",
            "canvas": [W, H], "steps": common["num_inference_steps"], "refs_used": len(r.get("refs", []))
            if task == "ref2va" else 0}


if __name__ == "__main__":
    serve(handle)
