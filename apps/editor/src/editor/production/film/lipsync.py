"""Dudak senkronu: çekimden sonra ağızlar sese bağlanır (images/lipsync, InfiniteTalk V2V; 2026-10-08).

Video modeli ağzı sesle kendisi eşleyemiyordu (konuşmayanın ağzı oynuyor, konuşanınki sesle uyumsuz). Bu adım her
çekim için bir iş planlar:

- Çekimde konuşan (kitaptaki replik ya da birinci tekil anlatıcının iç sesi) karedeyse onun ağzı kendi sesine bağlanır;
  karedeki bir başka kişi (en çok bir) sessizliğe bağlanır, ağzı kapalı kalır.
- Konuşan karede değilse ama yüzler yakın planda görünüyorsa (TALK_FRAMINGS) bütün ağızlar kapalı tutulur (dış ses).
- Geniş plan, konuşmasız çekim: dokunulmaz.

Karakterlerin karedeki yeri ilk karede görsel modelle bulunur (`locate`); çıktı `cekim/<çekim>.vK.dub.mp4`,
kurgu onu ham çekime yeğler (shoot.for_mix). Kurallar kitaptan bağımsızdır.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from . import dialogue, spec, store
from . import frames as F
from . import script as script_mod
from .shoot import TALK_FRAMINGS

MAX_PEOPLE = 2                 # InfiniteTalk person1/person2
BOX_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["people"], "properties": {"people": {
    "type": "array", "items": {"type": "object", "additionalProperties": False,
                               "required": ["name", "visible", "box"],
                               "properties": {"name": {"type": "string"}, "visible": {"type": "boolean"},
                                              "box": {"type": "array", "items": {"type": "number"}}}}}}}


def dub_name(file: str) -> str:
    """`s01c02.v3.mp4` → `s01c02.v3.dub.mp4`."""
    return file[:-4] + ".dub.mp4"


def plan(shot: dict, lines: list[dict], boxes: dict[str, list[int]], narrator: str) -> dict | None:
    """Tek çekimin işi: {"speak": [(konuşan, kutu)], "silent": [kutu], "all_silent": bool} ya da None (dokunma).
    `boxes`: karede bulunan kişi → [x1,y1,x2,y2] (piksel). Anlatıcı satırı (konuşan = anlatıcı) anlatıcı karedeyse
    onun ağzından çıkar."""
    who = []
    for ln in lines:
        sp = ln["speaker"]
        sp = narrator if sp.casefold() == spec.NARRATOR else sp
        if sp in boxes and sp not in who:
            who.append(sp)
    speak = [(sp, boxes[sp]) for sp in who[:MAX_PEOPLE]]
    rest = sorted((n for n in boxes if n not in who),
                  key=lambda n: -(boxes[n][2] - boxes[n][0]) * (boxes[n][3] - boxes[n][1]))
    silent = [boxes[n] for n in rest[:MAX_PEOPLE - len(speak)]] if speak else []
    if speak:
        return {"speak": speak, "silent": silent, "all_silent": False}
    if boxes and shot.get("framing") in TALK_FRAMINGS:
        return {"speak": [], "silent": [], "all_silent": True}
    return None


def speaker_track(f: Path, lines: list[dict], speaker: str, narrator: str, seconds: float, out: Path) -> None:
    """Konuşanın ses izi: yalnız onun satırları, çekim içindeki yerinde (mix.line_starts ile aynı düzen), gerisi sessiz."""
    from .mix import line_starts
    starts = line_starts([x["duration"] for x in lines])
    args, parts, n = ["ffmpeg", "-v", "error", "-y"], [], 0
    for x, st in zip(lines, starts):
        sp = narrator if x["speaker"].casefold() == spec.NARRATOR else x["speaker"]
        if sp != speaker:
            continue
        args += ["-i", str(f / "ses" / x["file"])]
        ms = int(st * 1000)
        parts.append(f"[{n}:a]aresample=16000,adelay={ms}|{ms}[a{n}]")
        n += 1
    sil = f"anullsrc=r=16000:cl=mono,atrim=0:{seconds}[s]"
    mix = "".join(f"[a{i}]" for i in range(n)) + f"[s]amix=inputs={n + 1}:normalize=0:duration=longest,atrim=0:{seconds}[o]"
    args += ["-filter_complex", ";".join(parts + [sil, mix]), "-map", "[o]", "-ac", "1", str(out)]
    subprocess.run(args, check=True, timeout=120)


async def locate(http, png: bytes, names: list[str], cast_lines: dict[str, str], W: int, H: int) -> dict[str, list[int]]:
    """İlk karede adı verilen karakterlerin baş-gövde kutusu (piksel). Görünmeyen ya da bulunamayan düşer."""
    url, hd = F._gateway()
    who = "\n".join(f"- {cast_lines.get(n, n)}" for n in names)
    ask = ("For each character below, say whether they are visible in this frame of an animated film and give the "
           "bounding box of their head and upper body as [x1, y1, x2, y2] in a 0–1000 coordinate system "
           f"(0,0 top-left). Characters:\n{who}")
    body = {"model": F.VISION, "max_tokens": 4000, "temperature": 0.0,
            "response_format": {"type": "json_schema", "json_schema": {"name": "boxes", "schema": BOX_SCHEMA,
                                                                        "strict": True}},
            "messages": [{"role": "user", "content": [{"type": "text", "text": ask},
                                                       {"type": "image_url", "image_url": {
                                                           "url": "data:image/jpeg;base64," + F._jpeg(png)}}]}]}
    r = await http.post(f"{url}/v1/chat/completions", json=body, headers=hd, timeout=600)
    r.raise_for_status()
    out = json.loads(r.json()["choices"][0]["message"]["content"])
    res = {}
    for p in out.get("people", []):
        b = p.get("box") or []
        if p.get("visible") and p.get("name") in names and len(b) == 4 and b[2] > b[0] and b[3] > b[1]:
            res[p["name"]] = [int(b[0] * W / 1000), int(b[1] * H / 1000), int(b[2] * W / 1000), int(b[3] * H / 1000)]
    return res


async def jobs(d: Path, f: Path, http, workdir: Path, mount: str = "/is", film_mount: str | None = None) -> list[dict]:
    """Bütün çekimler için dub.py toplu iş listesi. Kutular `lipsync.json`da önbellekte (çekim dosyası değişince
    yeniden bulunur). `workdir`: konuşan ses izlerinin yazıldığı klasör (konteynerde `mount`)."""
    from . import cast as cast_mod
    sc = script_mod.load(f)
    voice = dialogue.load(f)
    cast = cast_mod.load(f)
    narrator = script_mod.narrator_of(sc, script_mod.book_text(d))
    lines_of = cast_mod.card_lines(cast, store.meta(f).get("style"))
    rec = store.read(f, "cekimler.json") or {"shots": {}}
    cache = store.read(f, "lipsync.json") or {}
    W, H = 1344, 768
    out = []
    workdir.mkdir(parents=True, exist_ok=True)
    fm = film_mount or str(f)
    for s in spec.shots(sc):
        x = rec["shots"].get(s["id"])
        if not x or not x.get("selected"):
            continue
        v = x["versions"][x["selected"] - 1]
        lines = voice["lines"].get(s["id"], [])
        if not s.get("characters"):
            continue
        key = v["file"]
        if cache.get(s["id"], {}).get("file") != key:
            first = (f / "cekim" / v["file"])
            with tempfile.TemporaryDirectory() as td:
                png = Path(td) / "k.png"
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(first), "-frames:v", "1", str(png)],
                               check=True, timeout=60)
                try:
                    boxes = await locate(http, png.read_bytes(), s["characters"], lines_of, W, H)
                except Exception:  # noqa: BLE001 - kutu bulunamazsa çekime dokunulmaz
                    boxes = {}
            cache[s["id"]] = {"file": key, "boxes": boxes}
            store.write(f, "lipsync.json", cache)
        p = plan(s, lines, cache[s["id"]]["boxes"], narrator)
        if p is None:
            continue
        secs = float(voice["seconds"].get(s["id"], s["seconds"]))
        job = {"video": f"{fm}/cekim/{v['file']}", "cikti": f"{fm}/cekim/{dub_name(v['file'])}",
               "konusmaci": [], "sessiz_kisi": [], "sessiz": p["all_silent"]}
        for sp, box in p["speak"]:
            wav = workdir / f"{s['id']}-{sp}.wav"
            speaker_track(f, lines, sp, narrator, secs, wav)
            b = ",".join(map(str, box))
            job["konusmaci"].append(f"{mount}/{wav.name}" + (f"@{b}" if len(p["speak"]) + len(p["silent"]) > 1 else ""))
        job["sessiz_kisi"] = [",".join(map(str, b)) for b in p["silent"]]
        out.append(job)
    return out
