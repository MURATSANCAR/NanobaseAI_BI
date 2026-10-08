"""editor-foley: çekim videosundan senkron efekt / ortam sesi (HunyuanVideo-Foley, video + metin → 48 kHz ses).

Çizgi film hattında arşiv efekti çekimin başına konuyordu, görüntüyle senkron değildi (paket açma sesi ör.). Bu araç
her çekimin kendi görüntüsünden (SigLIP2 8 fps anlam + Synchformer 25 fps zamanlama) sesi üretir.

Konuşma ve müzik ÜRETMEZ: negatif istem (sınıflandırıcısız yönlendirmenin «koşulsuz» kolu) varsayılan olarak konuşma,
ses, şarkı ve müziği iter — konuşma bizim seslendirmemizden, müzik ayrı müzik izinden gelir.

Kullanım (tek çekim):
  python /srv/foley.py --video cekim.mp4 --prompt "paper tearing, crayons rattling, indoor room tone" --out x.wav
Toplu (modeller bir kez yüklenir, çekim başına yeniden yükleme yok):
  python /srv/foley.py --jobs isler.json        # [{"video": ..., "prompt": ..., "out": ...}, ...]

Çıktı: mono, 48 kHz, 16 bit PCM wav; süresi videonun süresine örnek doğruluğunda eşittir (eksikse sessizlikle
tamamlanır, fazlası kesilir), baş/son 10 ms yumuşatılır (tık sesi olmasın).

Metin kodlayıcı (CLAP) İngilizce eğitilmiştir: Türkçe tarif çalışır ama zayıf eşleşir; çağıran taraf (senaryo/LLM)
İngilizce kısa tarif vermelidir. Türkçe harf görülürse uyarı basılır.

Model 15 sn'den uzun videoyu kesiyor (feature_utils.get_frames_av): uzun çekim ≤ 12 sn parçalara bölünür, parçalar
1 sn çapraz geçişle birleşir. 1 sn'den kısa video son karesi dondurularak 1 sn'ye uzatılır, ses sonra kırpılır.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

KOD = os.environ.get("FOLEY_KOD", "/opt/HunyuanVideo-Foley")
MODEL = os.environ.get("FOLEY_MODEL", "/data/editor/models/HunyuanVideo-Foley")
sys.path.insert(0, KOD)

SR = 48000
NEG = ("speech, talking, voice, human voice, dialogue, narration, whispering, singing, vocals, choir, "
       "music, melody, musical instrument, song, noisy, harsh")
PART = 12.0          # parça uzunluğu (model sınırı 15 sn)
XF = 1.0             # parça çapraz geçişi (sn)
MIN_S = 1.0          # modelin en kısa videosu
EDGE = 0.010         # baş/son yumuşatma (sn)
_TR = re.compile(r"[çğıöşüÇĞİÖŞÜ]")


def log(m: str) -> None:
    print(f"[foley] {m}", file=sys.stderr, flush=True)


def duration(video: str) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def cut(video: str, start: float, secs: float, out: str, pad_to: float = 0.0) -> None:
    """[start, start+secs) parçası, 25 fps (Synchformer hızı) yeniden kodlanır; pad_to > secs ise son kare donar."""
    vf = "fps=25"
    if pad_to > secs:
        vf += f",tpad=stop_mode=clone:stop_duration={pad_to - secs:.3f}"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{secs:.3f}", "-i", video, "-an",
                    "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", out],
                   check=True)


def plan(total: float) -> list[tuple[float, float]]:
    """Çekimi ≤ PART parçalara böler; ardışık parçalar XF kadar örtüşür."""
    if total <= 15.0:
        return [(0.0, total)]
    n = math.ceil((total - XF) / (PART - XF))
    step = (total - XF) / n
    return [(round(i * step, 3), round(min(step + XF, total - i * step), 3)) for i in range(n)]


class Foley:
    def __init__(self, size: str, offload: bool, steps: int, guidance: float, neg: str):
        import torch
        from hunyuanvideo_foley.utils.model_utils import load_model
        cfg = f"{KOD}/configs/hunyuanvideo-foley-{size}.yaml"
        self.torch = torch
        self.device = torch.device("cuda:0")
        self.steps, self.guidance, self.neg = steps, guidance, neg
        self.model, self.cfg = load_model(MODEL, cfg, self.device, enable_offload=offload, model_size=size)

    def _one(self, video: str, prompt: str):
        from hunyuanvideo_foley.utils.feature_utils import feature_process
        from hunyuanvideo_foley.utils.model_utils import denoise_process
        vis, txt, secs = feature_process(video, prompt, self.model, self.cfg, neg_prompt=self.neg)
        audio, sr = denoise_process(vis, txt, secs, self.model, self.cfg, guidance_scale=self.guidance,
                                    num_inference_steps=self.steps)
        assert sr == SR, sr
        return audio[0].mean(dim=0).numpy()          # [C, N] → mono

    def run(self, video: str, prompt: str, out: str, seed: int) -> dict:
        import numpy as np
        import soundfile as sf
        if _TR.search(prompt):
            log("uyarı: tarif Türkçe görünüyor; metin kodlayıcı İngilizce eğitildi, İngilizce tarif daha iyi eşleşir")
        random.seed(seed)
        np.random.seed(seed)
        self.torch.manual_seed(seed)
        total = duration(video)
        n = int(round(total * SR))
        mix = np.zeros(n, dtype=np.float32)
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as td:
            parts = plan(total)
            for i, (a, s) in enumerate(parts):
                tmp = f"{td}/p{i}.mp4"
                cut(video, a, s, tmp, pad_to=MIN_S)
                y = self._one(tmp, prompt)[: int(round(s * SR))]
                if len(parts) > 1:                   # örtüşen kenarlarda doğrusal çapraz geçiş
                    k = int(XF * SR)
                    g = np.ones(len(y), dtype=np.float32)
                    if i > 0:
                        g[:k] = np.linspace(0, 1, k, dtype=np.float32)[: len(g)]
                    if i < len(parts) - 1:
                        g[-k:] = np.minimum(g[-k:], np.linspace(1, 0, k, dtype=np.float32))
                    y = y * g
                o = int(round(a * SR))
                m = min(len(y), n - o)
                mix[o:o + m] += y[:m]
                log(f"{Path(video).name}: parça {i + 1}/{len(parts)} {a:.2f}+{s:.2f} sn")
        e = min(int(EDGE * SR), n // 2)
        if e:
            mix[:e] *= np.linspace(0, 1, e, dtype=np.float32)
            mix[-e:] *= np.linspace(1, 0, e, dtype=np.float32)
        peak = float(np.abs(mix).max()) if n else 0.0
        if peak > 0.99:
            mix *= 0.99 / peak
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        sf.write(out, mix, SR, subtype="PCM_16")
        return {"video": video, "out": out, "seconds": round(total, 3), "samples": n, "parts": len(parts),
                "peak": round(min(peak, 0.99), 4)}


def main() -> None:
    ap = argparse.ArgumentParser(description="Çekim videosundan senkron efekt/ortam sesi (48 kHz wav).")
    ap.add_argument("--video")
    ap.add_argument("--prompt", default="")
    ap.add_argument("--out")
    ap.add_argument("--jobs", help='JSON: [{"video","prompt","out"}, ...] — modeller bir kez yüklenir')
    ap.add_argument("--neg", default=NEG, help="negatif istem (varsayılan: konuşma/ses/müzik)")
    ap.add_argument("--size", choices=["xxl", "xl"], default="xxl")
    ap.add_argument("--offload", action="store_true", help="alt modelleri sırayla yükle/boşalt (daha az GPU belleği)")
    ap.add_argument("--steps", type=int, default=50)
    ap.add_argument("--guidance", type=float, default=4.5)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--skip-existing", action="store_true")
    a = ap.parse_args()
    if a.jobs:
        jobs = json.loads(Path(a.jobs).read_text())
    elif a.video and a.out:
        jobs = [{"video": a.video, "prompt": a.prompt, "out": a.out}]
    else:
        ap.error("--video + --out ya da --jobs gerekli")
    if a.skip_existing:
        jobs = [j for j in jobs if not Path(j["out"]).exists()]
    if not jobs:
        print(json.dumps({"ok": True, "results": []}))
        return
    fo = Foley(a.size, a.offload, a.steps, a.guidance, a.neg)
    results = []
    for j in jobs:
        try:
            results.append({"ok": True, **fo.run(j["video"], j.get("prompt", ""), j["out"], int(j.get("seed", a.seed)))})
        except Exception as e:                       # tek çekimin hatası ötekileri durdurmaz
            log(f"HATA {j.get('video')}: {e!r}")
            results.append({"ok": False, "video": j.get("video"), "out": j.get("out"), "error": repr(e)})
    print(json.dumps({"ok": all(r["ok"] for r in results), "results": results}, ensure_ascii=False))
    sys.exit(0 if all(r["ok"] for r in results) else 1)


if __name__ == "__main__":
    main()
