"""Çekim: ilk kare video modelinde hareketlenir (gateway `book-video`, images/video/server.py). GPU'nun en ağır işi;
gece kuyruğunda, Temporal'da çekim çekim yürür (flow: FilmShoot), yarıda kalan kaldığı yerden sürer.

Uç sözleşmesi (POST /v1/video/generations, gövde JSON):
    {"model": "book-video", "mode": "i2v" | "s2v", "image": <png b64>, "prompt", "negative_prompt",
     "seconds", "width", "height", "seed", "audio": <wav b64, yalnız s2v>}
    → {"video": <mp4 b64>, "seconds", "fps", "frames", "engine"}
`i2v`: kareden hareket. `s2v`: konuşan çekim — karakterin ağzı verilen replik sesine uyar (yalnız tek konuşanlı,
yakın/bel planda; çok kişili sahne ve geniş plan i2v + kurguda ses).

Her çekimden üç kare görsel denetçiye gider (frames.review): bozulma, yazı, karakter kayması. Geçmeyen çekim bir kez
yeni tohumla yeniden çekilir; yine geçmezse editörün önüne «denetimden geçmedi» notuyla gelir.
"""

from __future__ import annotations

import base64
import os
import subprocess
import tempfile
from pathlib import Path

import httpx

from . import dialogue
from . import frames as F
from . import script as script_mod
from . import spec, store

ALIAS = "book-video"
RETRIES = 1
TALK_FRAMINGS = {"yakin", "cok-yakin", "bel", "omuz-ustu"}


class VideoUnavailable(RuntimeError):  # noqa: N818
    """Video servisi bu kurulumda açık değil."""


def _endpoint() -> tuple[str, dict]:
    direct = os.environ.get("EDITOR_VIDEO_URL", "").rstrip("/")
    if direct:
        return direct, {}
    return F._gateway()


async def available() -> bool:
    """Gateway `book-video` takma adını tanıyor mu (ya da doğrudan uç verilmiş mi)? Kapalı kurulumda çekim adımı
    başlamadan editöre söylenir; model yine de ayağa kaldırılmaz (yalnız takma ad listesine bakılır)."""
    if os.environ.get("EDITOR_VIDEO_URL"):
        return True
    url, hd = _endpoint()
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{url}/v1/models", headers=hd)
        return r.status_code == 200 and any(m.get("id") == ALIAS for m in r.json().get("data", []))
    except (httpx.HTTPError, ValueError):
        return False


def mode_of(shot: dict, lines: list[dict]) -> str:
    speakers = {x["speaker"] for x in lines if x["speaker"].casefold() != spec.NARRATOR}
    if len(speakers) == 1 and shot["framing"] in TALK_FRAMINGS and len(shot.get("characters", [])) == 1:
        return "s2v"
    return "i2v"


def talk_track(f: Path, lines: list[dict], seconds: float) -> bytes:
    """Konuşan çekimin ses izi: replikler sırayla, aralarında spec.LINE_GAP; çekim süresine tamamlanır (wav)."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "t.wav"
        args = ["ffmpeg", "-v", "error", "-y"]
        parts = []
        for i, x in enumerate(lines):
            args += ["-i", str(f / "ses" / x["file"])]
            parts.append(f"[{i}:a]aresample=24000,apad=pad_dur={spec.LINE_GAP}[a{i}]")
        chain = ";".join(parts) + ";" + "".join(f"[a{i}]" for i in range(len(lines))) + \
            f"concat=n={len(lines)}:v=0:a=1,apad,atrim=0:{seconds}[o]"
        args += ["-filter_complex", chain, "-map", "[o]", "-ac", "1", str(out)]
        subprocess.run(args, check=True, timeout=120)
        return out.read_bytes()


def sample_frames(mp4: bytes, n: int = 3) -> list[bytes]:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "v.mp4"
        p.write_bytes(mp4)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                    str(p)], capture_output=True, text=True, check=True).stdout.strip() or 0)
        out = []
        for k in range(n):
            t = dur * (k + 1) / (n + 1)
            png = Path(td) / f"{k}.png"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(p), "-frames:v", "1", str(png)],
                           check=True, timeout=60)
            out.append(png.read_bytes())
        return out


async def _call(http, body: dict) -> dict:
    url, hd = _endpoint()
    try:
        r = await http.post(f"{url}/v1/video/generations", json={"model": ALIAS, **body}, headers=hd)
    except httpx.HTTPError as e:
        raise VideoUnavailable(f"video servisine ulaşılamadı: {type(e).__name__}") from None
    if r.status_code == 404:
        raise VideoUnavailable("video servisi bu kurulumda açık değil")
    r.raise_for_status()
    return r.json()


async def shoot_one(f: Path, shot: dict, by: str, seed: int, http) -> dict:
    m = store.meta(f)
    W, H = spec.FORMATS[m["format"]]["gen"]
    voice = dialogue.load(f)
    lines = voice["lines"].get(shot["id"], [])
    seconds = voice["seconds"].get(shot["id"], float(shot["seconds"]))
    first = F.selected(f, shot["id"])
    mode = mode_of(shot, lines)
    body = {"mode": mode, "image": base64.b64encode(first.read_bytes()).decode(),
            "prompt": spec.shot_prompt(shot, m["style"], {}), "negative_prompt": F.NEGATIVE,
            "seconds": seconds, "width": W, "height": H}
    if mode == "s2v":
        body["audio"] = base64.b64encode(talk_track(f, lines, seconds)).decode()
    res, qc = None, {"ok": None, "problems": []}
    for k in range(RETRIES + 1):
        res = await _call(http, {**body, "seed": seed + k})
        mp4 = base64.b64decode(res["video"])
        checks = [await F.review(http, fr, shot) for fr in sample_frames(mp4)]
        bad = [p for c in checks if c["ok"] is False for p in c["problems"]]
        qc = {"ok": None if all(c["ok"] is None for c in checks) else not bad, "problems": sorted(set(bad))}
        if qc["ok"] is not False:
            break
    rec = store.read(f, "cekimler.json") or {"shots": {}}
    cur = rec["shots"].setdefault(shot["id"], {"versions": [], "selected": None})
    v = len(cur["versions"]) + 1
    cd = f / "cekim"
    cd.mkdir(exist_ok=True)
    name = f"{shot['id']}.v{v}.mp4"
    (cd / name).write_bytes(mp4)
    cur["versions"].append({"v": v, "file": name, "mode": mode, "seconds": res.get("seconds", seconds),
                            "engine": res.get("engine"), "first_frame": first.name, "qc": qc, "by": by,
                            "at": store.now()})
    cur["selected"] = v
    store.write(f, "cekimler.json", rec)
    return cur["versions"][-1]


async def shoot(d: Path, f: Path, by: str, progress=lambda n, t, w="": None, only: list[str] | None = None) -> dict:
    """Seçili ilk kareleri çeker. `only` yoksa çekimi olmayan (ya da karesi değişmiş) çekimler çekilir."""
    store.require(f, "ses")
    store.require(f, "kareler")
    sc = script_mod.load(f)
    rec = store.read(f, "cekimler.json") or {"shots": {}}
    todo = []
    for s in spec.shots(sc):
        if only is not None:
            if s["id"] in only:
                todo.append(s)
            continue
        cur = rec["shots"].get(s["id"])
        first = F.selected(f, s["id"]).name
        if not cur or cur["versions"][cur["selected"] - 1]["first_frame"] != first:
            todo.append(s)
    store.set_stage(f, "cekim", status="calisiyor")
    async with httpx.AsyncClient(timeout=httpx.Timeout(3600.0, connect=10.0)) as http:
        for n, s in enumerate(todo, 1):
            progress(n, len(todo), "Çekimler yapılıyor")
            await shoot_one(f, s, by, 5000 + 53 * n, http)
    rec = store.read(f, "cekimler.json") or {"shots": {}}
    failed = sum(1 for x in rec["shots"].values() if x["versions"][x["selected"] - 1]["qc"].get("ok") is False)
    store.set_stage(f, "cekim", status="hazir", shot=len(todo), failed_qc=failed)
    store.log(f, by, "çekimler yapıldı", count=len(todo), failed_qc=failed)
    return rec


def selected(f: Path, shot_id: str) -> Path:
    rec = store.read(f, "cekimler.json") or {"shots": {}}
    cur = rec["shots"].get(shot_id)
    if not cur or not cur.get("selected"):
        raise store.FilmError(f"{shot_id} çekimi yok.")
    return f / "cekim" / cur["versions"][cur["selected"] - 1]["file"]

