#!/usr/bin/env python3
"""Havuzda karşılığı olmayan efekti yerelde üretir ve havuza ekler (kaynak: «Zeki AI üretimi»).

Model: MOSS-SoundEffect v2.0 (OpenMOSS, Apache-2.0; ağırlıklar /data/editor/models/sfx-uretim/, sabit revizyon,
MANIFEST'te sha256). Metinden 48 kHz ses; anlık efekt URET_ANLIK sn, ortam URET_ORTAM sn. GPU'da GEÇİCİ kapta,
küçük bellek payıyla çalışır; çalışan kaplara dokunmaz. Model kendi Python ortamını ister (torch 2.9, transformers
4.57): ortam /data/editor/sfx/_ops/moss-venv altında bir kez kurulur (uret.sh).

Girdi: kapsama ölçümünün karşılanmayan ipuçları (_olcum/esleme.jsonl + eşik) ya da --liste ile JSON dosyası
[{query, query_en, kind, category}]. Çıktı: /data/editor/sfx/uretim/<ad>.wav + uretim/katalog-taslak.jsonl (havuz.py
`katalog uretim` ölçer, etiketler ve lisans notu buradan gelir).

    python uret.py --esik 0.2            # karşılanmayan bütün benzersiz ipuçları
    python uret.py --liste liste.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path

ROOT = Path("/data/editor/sfx")
OUT = ROOT / "uretim"
MODEL = Path(os.environ.get("SFX_URETIM_MODEL", "/model/MOSS-SoundEffect-v2.0"))
URET_ANLIK = 4.0
URET_ORTAM = 12.0                 # ortam sesi karışımda döngüyle sayfa boyunca uzar; kısa üretim bellek ister daha az
STEPS = 100
CFG = 4.0


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "ses"


ROOM_GB = float(os.environ.get("SFX_URETIM_BOS_GB", "12"))
MODEL_GB = 12.0                    # modelin yüklü hâldeki payı (ölçüldü: ~11 GB)


def _room(torch, loaded: bool) -> bool:
    """Başka iş öncelikli: stüdyoda süren iş (busy.json) yoksa ve model yüklüyken kartta başkaları için en az
    ROOM_GB boş bellek kalıyorsa üretilir (model yüklü değilse yükleneceği pay düşülerek hesaplanır)."""
    busy = Path("/busy")
    free = torch.cuda.mem_get_info()[0] / 2**30 - (0.0 if loaded else MODEL_GB)
    running = any(busy.glob("*/busy.json")) if busy.exists() else False
    if free >= ROOM_GB and not running:
        return True
    log(f"yer yok: boş {free:.0f} GB, stüdyo işi {'var' if running else 'yok'} → model boşaltıldı, bekleniyor")
    return False


def _save(audio, path: Path, sr: int = 48000) -> None:
    """(B, C, T) dalga biçimi → 16 bit WAV (paketin save_audio'su torchcodec/ffmpeg sürüm uyuşmazlığında düşüyor)."""
    import wave

    import numpy as np
    x = audio[0].float().clamp(-1, 1).cpu().numpy()          # (C, T)
    pcm = (x.T * 32767).astype(np.int16)
    tmp = path.with_suffix(".part")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(pcm.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    tmp.replace(path)


def wanted(esik: float) -> list[dict]:
    rows = [json.loads(x) for x in (ROOT / "_olcum" / "esleme.jsonl").read_text().splitlines() if x.strip()]
    return [r for r in rows if not (r.get("top") and r["top"][0]["score"] >= esik)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--esik", type=float, default=None)
    ap.add_argument("--liste", default=None)
    ap.add_argument("--en-az", type=int, default=1, dest="en_az")   # listede `count` en az bu kadar olanlar
    a = ap.parse_args()
    items = json.loads(Path(a.liste).read_text()) if a.liste else wanted(a.esik)
    items = [it for it in items if int(it.get("count") or 1) >= a.en_az]
    OUT.mkdir(parents=True, exist_ok=True)
    draft = OUT / "katalog-taslak.jsonl"
    done = set()
    if draft.exists():
        done = {json.loads(x)["key"] for x in draft.read_text().splitlines() if x.strip()}
    todo = []
    for it in items:
        en = (it.get("query_en") or "").strip()
        if not en:
            continue
        key = hashlib.sha256(f"{it.get('kind')}|{en.lower()}".encode()).hexdigest()[:12]
        if key not in done:
            todo.append((key, it, en))
    log("üretilecek", len(todo), "önceden", len(done))
    if not todo:
        return
    import torch
    from moss_soundeffect_v2 import MossSoundEffectPipeline
    dev = os.environ.get("SFX_URETIM_CIHAZ", "cuda")
    if dev == "cuda":
        torch.cuda.set_per_process_memory_fraction(float(os.environ.get("SFX_GPU_FRACTION", "0.12")))
    else:
        torch.set_num_threads(int(os.environ.get("SFX_THREADS", "32")))
    pipe = None
    t0 = time.time()
    for n, (key, it, en) in enumerate(todo, 1):
        # her seste yer denetimi: yer yoksa model bellekten tamamen çıkar (başka iş kartı alabilsin), yer açılınca döner
        while dev == "cuda" and not _room(torch, pipe is not None):
            if pipe is not None:
                del pipe
                pipe = None
                import gc
                gc.collect()
                torch.cuda.empty_cache()
            time.sleep(60)
        if pipe is None:
            pipe = MossSoundEffectPipeline.from_pretrained(
                str(MODEL), torch_dtype=torch.bfloat16 if dev == "cuda" else torch.float32, device=dev)
        sec = URET_ORTAM if it.get("kind") == "ortam" else URET_ANLIK
        seed = int(key[:8], 16) % (2**31)
        torch.manual_seed(seed)
        audio = pipe(prompt=en, seconds=sec, num_inference_steps=STEPS, cfg_scale=CFG)
        name = f"{slug(en)}-{key}.wav"
        _save(audio, OUT / name)
        rec = {"key": key, "file": name, "prompt": en, "query": it.get("query"), "kind": it.get("kind"),
               "category": it.get("category"), "seconds": sec, "steps": STEPS, "cfg": CFG, "seed": seed,
               "model": "OpenMOSS-Team/MOSS-SoundEffect-v2.0", "revision": "e35df4d82fbe87fcd5d14e5d100e349c0c3c076d",
               "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        with draft.open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if n % 10 == 0:
            log(n, "/", len(todo), f"{(time.time() - t0) / n:.1f} sn/ses")
    log("üretim bitti", len(todo))


if __name__ == "__main__":
    main()
