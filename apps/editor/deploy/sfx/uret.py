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
URET_ORTAM = 20.0
STEPS = 100
CFG = 4.0


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "ses"


def wanted(esik: float) -> list[dict]:
    rows = [json.loads(x) for x in (ROOT / "_olcum" / "esleme.jsonl").read_text().splitlines() if x.strip()]
    return [r for r in rows if not (r.get("top") and r["top"][0]["score"] >= esik)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--esik", type=float, default=None)
    ap.add_argument("--liste", default=None)
    a = ap.parse_args()
    items = json.loads(Path(a.liste).read_text()) if a.liste else wanted(a.esik)
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
    torch.cuda.set_per_process_memory_fraction(float(os.environ.get("SFX_GPU_FRACTION", "0.12")))
    pipe = MossSoundEffectPipeline.from_pretrained(str(MODEL), torch_dtype=torch.bfloat16, device="cuda")
    t0 = time.time()
    for n, (key, it, en) in enumerate(todo, 1):
        sec = URET_ORTAM if it.get("kind") == "ortam" else URET_ANLIK
        seed = int(key[:8], 16) % (2**31)
        torch.manual_seed(seed)
        audio = pipe(prompt=en, seconds=sec, num_inference_steps=STEPS, cfg_scale=CFG)
        name = f"{slug(en)}-{key}.wav"
        pipe.save_audio(audio, str(OUT / name))
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
