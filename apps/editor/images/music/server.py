"""book-music: kitaptan çizgi filmin müziği — sözsüz sahne müziği (score) ve sözlü tema şarkısı (song); gateway takma adı
olarak istekte açılır (images/video/server.py ile aynı biçim).

Motorlar (ağırlıklar /data/editor/models/book-music/<klasör>, gateway salt okunur /model olarak bağlar). Kullanıcı
kararı 2026-10-07: kurumun hepsi için lisansı var; hepsi varsayılan açık, MUSIC_DISABLED_ENGINES (virgüllü) ile
kapatılır. Seçim sırası (istekte `engine` yoksa, kurulu ve açık ilk motor):
    score: stable-audio-3 > acestep15 > yue2
    song:  yue2 > minimax-music3 > heartmula          (acestep15 şarkıyı yalnız açıkça istenirse yapar)
    stable-audio-3   Stable Audio 3.0 Medium — tempo/ton/süre tutar (HF kapılı: anahtar gelince indirilir)
    acestep15        ACE-Step 1.5 XL-SFT + LM 4B (MIT) — tempo/ton istenmez, parça kurguda sahneye uydurulur
    yue2             YuE2-3B + YuE2-Vae — şarkı; sözsüz kipi resmî instrumental yolu
    minimax-music3   MiniMax Music 3 — şarkı (söz hatası en düşük açık model)
    heartmula        HeartMuLa-oss-3B + HeartCodec (Apache-2.0) — şarkı
Türkçe söz hiçbir motorda belgelenmemiştir; şarkı motorları ilk kurulumda karşılaştırılır (istekte `engine`).

Kütüphane sürümleri birbiriyle çakışır: her motor kendi sanal ortamında ayrı bir süreçte (worker.py) çalışır. Tek kilit,
tek motor: istenen motor yüklü değilse öbürünün süreci kapatılır (kart belleği tamamen boşalır), sonra yenisi açılır.
Motor tembel yüklenir: servis açılınca hiçbir motor yüklü değildir.

    GET  /health
    POST /v1/audio/music  {model, kind: score|song, prompt (İngilizce tarz/duygu), seconds, bpm?, key?, lyrics? (song),
                           engine?: stable-audio-3|acestep15|yue2|minimax-music3|heartmula, seed}
                          → {audio: wav b64 (48 kHz stereo 16 bit), seconds, engine, sample_rate, truncated?, took}
"""

import argparse
import asyncio
import base64
import json
import os
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

ap = argparse.ArgumentParser()
ap.add_argument("model_dir")
ap.add_argument("--served-model-name", nargs="*")
ap.add_argument("--gpu-memory-utilization")
ap.add_argument("--port", type=int, default=8000)
args, _ = ap.parse_known_args()

ROOT = Path(args.model_dir)
SR = 48000
ENGINES = {  # anahtar → (sanal ortam, klasör, desteklenen türler)
    "stable-audio-3": ("/opt/venv/sa3", "stable-audio-3", {"score"}),
    "acestep15": ("/opt/venv/acestep", "acestep15", {"score", "song"}),
    "yue2": ("/opt/venv/yue2", "yue2", {"score", "song"}),
    "minimax-music3": ("/opt/venv/mm3", "minimax-music3", {"song"}),
    "heartmula": ("/opt/venv/heartmula", "heartmula", {"song"}),
}
PREFER = {"score": ("stable-audio-3", "acestep15", "yue2"), "song": ("yue2", "minimax-music3", "heartmula")}
DISABLED = {x.strip() for x in os.environ.get("MUSIC_DISABLED_ENGINES", "").split(",") if x.strip()}
WORKER = "/srv/worker.py"
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
_lock = threading.Lock()
_proc: dict[str, subprocess.Popen] = {}


def allowed(engine: str) -> bool:
    return engine not in DISABLED


def present(engine: str) -> bool:
    return allowed(engine) and (ROOT / ENGINES[engine][1]).is_dir() and Path(ENGINES[engine][0]).is_dir()


def pick(kind: str, engine: str | None) -> str:
    if engine:
        if engine not in ENGINES or kind not in ENGINES[engine][2]:
            raise HTTPException(422, f"{engine} motoru {kind} üretmez")
        if not allowed(engine):
            raise HTTPException(403, f"{engine} motoru bu kurulumda kapalı (MUSIC_DISABLED_ENGINES)")
        if not present(engine):
            raise HTTPException(503, f"{engine} motoru bu kurulumda yok (ağırlık ya da ortam)")
        return engine
    for e in PREFER[kind]:
        if present(e):
            return e
    raise HTTPException(503, f"{kind} için kurulu motor yok")


def _stop(engine: str) -> None:
    p = _proc.pop(engine, None)
    if p is None:
        return
    try:
        p.stdin.close()
        p.wait(timeout=30)
    except Exception:  # noqa: BLE001 - kapanmayan süreç zorla
        p.kill()
        p.wait()


def _worker(engine: str) -> subprocess.Popen:
    """İstenen motorun süreci; öbürü açıksa önce kapatılır (tek kart)."""
    p = _proc.get(engine)
    if p is not None and p.poll() is None:
        return p
    for k in list(_proc):
        _stop(k)
    venv, sub, _ = ENGINES[engine]
    _proc[engine] = subprocess.Popen([f"{venv}/bin/python", WORKER, engine, str(ROOT / sub)], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, text=True, bufsize=1)
    return _proc[engine]


def _ask(engine: str, job: dict) -> dict:
    p = _worker(engine)
    p.stdin.write(json.dumps(job) + "\n")
    p.stdin.flush()
    line = p.stdout.readline()
    if not line:
        _proc.pop(engine, None)
        raise HTTPException(500, f"{engine} süreci kapandı (çıkış {p.wait()})")
    res = json.loads(line)
    if not res.get("ok"):
        raise HTTPException(500, f"{engine}: {res.get('error', 'bilinmeyen hata')}")
    return res


@app.get("/health")
def health() -> dict:
    return {"ok": True, "loaded": [k for k, p in _proc.items() if p.poll() is None],
            "engines": {k: present(k) for k in ENGINES}, "disabled": sorted(DISABLED)}


class Req(BaseModel):
    model: str = "book-music"
    kind: str = Field("score", pattern="^(score|song)$")
    prompt: str = Field(..., min_length=1, max_length=4000)
    seconds: float = Field(..., gt=1, le=380)
    bpm: int | None = Field(None, ge=40, le=220)
    key: str | None = Field(None, max_length=40)
    lyrics: str | None = Field(None, max_length=6000)
    engine: str | None = None
    seed: int = Field(0, ge=0, lt=2**31)


def _run(r: Req) -> dict:
    if r.kind == "song" and not (r.lyrics or "").strip():
        raise HTTPException(422, "şarkı için söz gerekli")
    engine = pick(r.kind, r.engine)
    t0 = time.time()
    with _lock, tempfile.TemporaryDirectory() as td:
        raw, wav = Path(td) / "raw.wav", Path(td) / "out.wav"
        res = _ask(engine, {"kind": r.kind, "prompt": r.prompt, "seconds": r.seconds, "bpm": r.bpm, "key": r.key,
                            "lyrics": r.lyrics or "", "seed": r.seed, "out": str(raw), "tmp": td})
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-ar", str(SR), "-ac", "2", "-c:a", "pcm_s16le",
                        str(wav)], check=True, timeout=300)
        with wave.open(str(wav)) as w:
            secs = w.getnframes() / w.getframerate()
        data = wav.read_bytes()
    return {"audio": base64.b64encode(data).decode(), "seconds": round(secs, 3), "engine": engine,
            "sample_rate": SR, "truncated": bool(res.get("truncated")), "took": round(time.time() - t0, 1)}


@app.post("/v1/audio/music")
async def generate(r: Req) -> dict:
    return await asyncio.to_thread(_run, r)


if __name__ == "__main__":
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")
