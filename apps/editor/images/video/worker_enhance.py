"""Görüntü iyileştirme işçisi (/opt/h3 sanal ortamı): SeedVR2 7B sharp ile büyütme, sonra Practical-RIFE ile ara kare.

ÇALIŞTIRILMADI (kullanıcı kararı). Kaynakla eşleme:
- SeedVR2: ağırlıklar numz/SeedVR2_comfyUI (fp16 safetensors). Bu dosyaları yükleyen kod numz/ComfyUI-SeedVR2_
  VideoUpscaler'dır (src/utils/model_registry.py:49 `seedvr2_ema_7b_sharp_fp16.safetensors` sha256 20a93e01…,
  :52 `ema_vae_fp16.safetensors`); ByteDance-Seed/SeedVR'ın resmî betikleri `.pth` yükler
  (projects/inference_seedvr2_7b.py:76 `./ckpts/seedvr2_ema_7b.pth`) — bu dosyalarla çalışmaz. Model kodu numz
  paketinin içinde (src/) ByteDance kodundan türetilmiş halde gelir. Paketin kendi CLI'ı (inference_cli.py)
  komut satırı olarak çağrılır; bayraklar oradaki argparse'tan (plan.seedvr2_args).
- CLI ağırlığın sha256'sını doğrular ve sonucu model klasöründeki .validation_cache.json'a yazar
  (src/utils/downloads.py validate_file); model klasörü salt okunur bağlandığı için geçici klasörde sembolik bağlı bir
  kopya kurulur, doğrulama süreç başına bir kez yapılır. Dosya yoksa CLI HF'den indirmeye kalkar — klasör denetlenir.
- RIFE: Practical-RIFE (kod imajda sabit commit) + 4.26 ağırlığı (README sürüm listesi, Google Drive; HF'de yok):
  <model_dir>/enhance/rife/train_log/{flownet.pkl, IFNet_HDv3.py, RIFE_HDv3.py}. Döngü inference_video.py:155-260
  ile aynı: kenar 128/scale katına doldurulur, `model.inference(I0, I1, (i+1)/m, scale)` (sürüm ≥3.9 yolu), sahne
  kesmesinde (ssim < 0,2) ara kare yerine I0 tekrarlanır. Durağan kare atlama (ssim > 0,996) kullanılmaz.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).parent))
import plan  # noqa: E402
from worker_common import Refused, probe, serve  # noqa: E402

MODELS = Path(sys.argv[1]) / "enhance"
SEEDVR2_DIR = MODELS / "seedvr2"
RIFE_DIR = MODELS / "rife"
SEEDVR2_CLI = "/opt/SeedVR2/inference_cli.py"
_rife = None
_seed_dir: Path | None = None


def _seedvr2_models() -> Path:
    """Salt okunur ağırlıkların yazılabilir sembolik bağ klasörü (doğrulama önbelleği buraya yazılır)."""
    global _seed_dir
    if _seed_dir is None:
        d = Path(tempfile.mkdtemp(prefix="seedvr2-"))
        for name in (plan.SEEDVR2_DIT, plan.SEEDVR2_VAE):
            src = SEEDVR2_DIR / name
            if not src.is_file():
                raise RuntimeError(f"SeedVR2 ağırlığı yok: {src}")
            (d / name).symlink_to(src)
        _seed_dir = d
    return _seed_dir


def _upscale(src: Path, out: Path, target: str, frames: int) -> None:
    args = [sys.executable, SEEDVR2_CLI, *plan.seedvr2_args(str(src), str(out), str(_seedvr2_models()), target, frames)]
    r = subprocess.run(args, cwd=str(out.parent), stdout=sys.stderr, stderr=sys.stderr, timeout=3 * 3600,
                       env={**os.environ, "PYTHONUNBUFFERED": "1"})
    if r.returncode != 0 or not out.is_file():
        raise RuntimeError(f"SeedVR2 başarısız (çıkış {r.returncode})")


def _load_rife():
    global _rife
    if _rife is None:
        sys.path.insert(0, "/opt/Practical-RIFE")      # model.warplayer, model.loss, model.pytorch_msssim
        sys.path.insert(0, str(RIFE_DIR))              # train_log.RIFE_HDv3
        from train_log.RIFE_HDv3 import Model
        torch.set_grad_enabled(False)
        m = Model()
        if not hasattr(m, "version"):
            m.version = 0
        m.load_model(str(RIFE_DIR / "train_log"), -1)
        m.eval()
        m.device()
        _rife = m
    return _rife


def _interpolate(src: Path, out: Path, fps: int) -> float:
    """src'yi `fps` kare/sn'ye getirir; gerekiyorsa RIFE ile ara kare. Dönüş: RIFE katı (1 = ara kare yok)."""
    info = probe(src)
    w, h, src_fps = info["width"], info["height"], info["fps"]
    m = plan.rife_multi(src_fps, fps)
    enc = ["ffmpeg", "-v", "error", "-y"]
    tail = ["-vf", f"fps={fps}", "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p", "-an",
            str(out)]
    if m == 1:
        subprocess.run(enc + ["-i", str(src)] + tail, check=True, timeout=3600)
        return 1
    from model.pytorch_msssim import ssim_matlab  # noqa: E402 — _load_rife yolu ekler
    model = _load_rife()
    dev = torch.device("cuda")
    scale = plan.rife_scale(h, w)
    tmp = max(128, int(128 / scale))
    ph, pw = ((h - 1) // tmp + 1) * tmp, ((w - 1) // tmp + 1) * tmp
    pad = (0, pw - w, 0, ph - h)
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(src), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)
    wr = subprocess.Popen(enc + ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(src_fps * m),
                                 "-i", "-"] + tail, stdin=subprocess.PIPE)
    size = w * h * 3

    def read():
        b = dec.stdout.read(size)
        return np.frombuffer(b, np.uint8).reshape(h, w, 3) if len(b) == size else None

    def tensor(fr):
        return F.pad(torch.from_numpy(fr.copy()).permute(2, 0, 1)[None].to(dev).float() / 255.0, pad)

    def emit(t):
        wr.stdin.write((t[0] * 255.0).clamp(0, 255).byte().permute(1, 2, 0)[:h, :w].contiguous().cpu().numpy()
                       .tobytes())

    last = read()
    if last is None:
        raise Refused("videoda kare yok")
    I1 = tensor(last)
    while True:
        frame = read()
        if frame is None:
            break
        I0, I1 = I1, tensor(frame)
        s0 = F.interpolate(I0, (32, 32), mode="bilinear", align_corners=False)
        s1 = F.interpolate(I1, (32, 32), mode="bilinear", align_corners=False)
        cut = ssim_matlab(s0[:, :3], s1[:, :3]) < 0.2
        wr.stdin.write(last.tobytes())
        for i in range(m - 1):
            emit(I0 if cut else model.inference(I0, I1, (i + 1) * 1.0 / m, scale))
        last = frame
    wr.stdin.write(last.tobytes())
    wr.stdin.close()
    if wr.wait() != 0 or dec.wait() != 0:
        raise RuntimeError("ffmpeg ara kare yazımı başarısız")
    return m


def handle(r: dict, td: Path) -> dict:
    src = Path(r["video"])
    info = probe(src)
    up = td / "up.mp4"
    _upscale(src, up, r["target"], max(info["frames"], 1))
    out = td / "hd.mp4"
    m = _interpolate(up, out, r["fps"])
    fin = probe(out)
    eng = "seedvr2-7b-sharp" + (f"+rife-4.26x{m}" if m > 1 else "")
    return {"file": str(out), "width": fin["width"], "height": fin["height"], "fps": r["fps"], "engine": eng}


if __name__ == "__main__":
    serve(handle)
