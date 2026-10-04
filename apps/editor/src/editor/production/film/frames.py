"""İlk kareler (storyboard): her çekimin ilk karesi görsel modelde (gateway `book-image`) çizilir; video modeli bu
kareden başlar. Karakter tutarlılığı referansla sağlanır: dizinin onaylı kartının görseli, kart yoksa filmin kendi
ürettiği karakter referansı (bir kez, `kare/oyuncu-<n>.png`). Çekimde karakter varsa düzenleme ucu (referanslı), yoksa
metinden üretim — images.Painter ile aynı uç sözleşmesi.

Her kare görsel denetçiden geçer (gateway `book-vision-fast`): yazı/harf, bozuk el-yüz, kişi sayısı, tarife uyum.
Geçmeyen kare yeni tohumla yeniden çizilir (en çok `RETRIES`); yine geçmezse editöre «denetimden geçmedi» notuyla
gösterilir. Editör tek kareyi yönlendirmeyle yeniden çizdirebilir (`redo`), sürümler saklanır.
"""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import httpx

from .. import images as I
from . import cast as cast_mod
from . import script as script_mod
from . import spec, store

VISION = "book-vision-fast"
RETRIES = 2
NEGATIVE = ("text, letters, subtitles, watermark, logo, blurry, low quality, deformed hands, extra fingers, "
            "extra limbs, distorted face, duplicate character")
QC_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["ok", "problems"],
             "properties": {"ok": {"type": "boolean"}, "problems": {"type": "array", "items": {"type": "string"}}}}


def _gateway() -> tuple[str, dict]:
    from ...config import settings
    s = settings()
    return s.gateway_url.rstrip("/"), {"authorization": f"Bearer {s.gateway_key}"}


def _b64(path: str | Path) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode()


async def _generate(http, prompt: str, W: int, H: int, seed: int) -> bytes:
    url, hd = _gateway()
    body = {"model": I.ALIAS, "prompt": prompt, "negative_prompt": NEGATIVE, "size": f"{W}x{H}",
            "num_inference_steps": I.STEPS, "true_cfg_scale": 4.0, "seed": seed, "response_format": "b64_json"}
    r = await http.post(f"{url}/v1/images/generations", json=body, headers=hd)
    r.raise_for_status()
    return base64.b64decode(r.json()["data"][0]["b64_json"])


async def _edit(http, prompt: str, refs: list[str], W: int, H: int, seed: int) -> bytes:
    url, hd = _gateway()
    content = [{"type": "text", "text": prompt}] + [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + _b64(p)}} for p in refs[:I.MAX_REFS]]
    body = {"model": I.ALIAS, "messages": [{"role": "user", "content": content}], "height": H, "width": W,
            "num_inference_steps": I.STEPS, "seed": seed, "true_cfg_scale": 4.0, "negative_prompt": NEGATIVE}
    r = await http.post(f"{url}/v1/chat/completions", json=body, headers=hd)
    r.raise_for_status()
    part = r.json()["choices"][0]["message"]["content"]
    u = part[0]["image_url"]["url"] if isinstance(part, list) else part
    return base64.b64decode(u.split(",", 1)[1])


def _jpeg(png: bytes, side: int = 1280) -> str:
    from PIL import Image
    im = Image.open(io.BytesIO(png)).convert("RGB")
    im.thumbnail((side, side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode()


async def review(http, png: bytes, shot: dict) -> dict:
    """Görsel denetçi. Ulaşılamazsa {"ok": None}: kare kullanılır, ekranda «denetlenemedi»."""
    url, hd = _gateway()
    n = len(shot.get("characters", []))
    ask = ("You check one frame of an animated film before it is animated. Answer ok=false if ANY of these is true: "
           "there is visible text, letters, numbers or a watermark; a hand, face or body is deformed or has extra "
           f"parts; the number of main characters is clearly not {n}; the picture clearly does not show this action: "
           f"\"{shot['action_en']}\". List each problem briefly in Turkish. Otherwise ok=true and no problems.")
    body = {"model": VISION, "max_tokens": 300, "temperature": 0.0, "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_schema", "json_schema": {"name": "qc", "schema": QC_SCHEMA,
                                                                        "strict": True}},
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": ask},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + _jpeg(png)}}]}]}
    try:
        r = await http.post(f"{url}/v1/chat/completions", json=body, headers=hd, timeout=600)
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])
    except Exception:  # noqa: BLE001
        return {"ok": None, "problems": []}


async def _char_refs(http, f: Path, cast: dict, style: str, W: int) -> dict[str, str]:
    """Kartı olmayan oyuncuya bir kez referans çizer (düz zemin, tam boy)."""
    kd = f / "kare"
    out = {}
    for i, m in enumerate(cast["members"]):
        if m.get("ref") and Path(m["ref"]).exists():
            out[m["name"]] = m["ref"]
            continue
        p = kd / f"oyuncu-{i:02d}.png"
        if not p.exists():
            prompt = (f"Character reference sheet of {m['name']}: {m['look_en']} Full body, standing, front "
                      f"three-quarter view, neutral expression, plain white background. Style: "
                      f"{spec.STYLES[style]['en']}. No text.")
            p.write_bytes(await _generate(http, prompt, 1024, 1024, 7000 + i))
        out[m["name"]] = str(p)
    return out


async def draw(f: Path, shot: dict, cast: dict, refs: dict[str, str], style: str, seed: int,
               direction: str = "", http=None) -> tuple[bytes, dict, str]:
    W, H = spec.FORMATS[store.meta(f)["format"]]["gen"]
    prompt = spec.shot_prompt(shot, style, cast_mod.card_lines(cast))
    if direction.strip():
        prompt += f" Editor's direction (follow it): {direction.strip()}."
    chars = [refs[c] for c in shot.get("characters", []) if c in refs]
    qc = {"ok": None, "problems": []}
    png = b""
    for k in range(RETRIES + 1):
        if chars:
            png = await _edit(http, prompt + " Keep each character's face, body, clothes and colours exactly as in the "
                                             "reference images.", chars, W, H, seed + k)
        else:
            png = await _generate(http, prompt, W, H, seed + k)
        qc = await review(http, png, shot)
        if qc["ok"] is not False:
            break
    return png, qc, prompt


async def build(d: Path, f: Path, by: str, progress=lambda n, t, w="": None, only: list[str] | None = None,
                direction: str = "") -> dict:
    store.require(f, "oyuncular")
    m = store.meta(f)
    sc = script_mod.load(f)
    cast = cast_mod.load(f)
    kd = f / "kare"
    kd.mkdir(exist_ok=True)
    rec = store.read(f, "kareler.json") or {"shots": {}}
    store.set_stage(f, "kareler", status="calisiyor")
    shots = [s for s in spec.shots(sc) if not only or s["id"] in only]
    async with httpx.AsyncClient(timeout=httpx.Timeout(1800.0, connect=10.0)) as http:
        refs = await _char_refs(http, f, cast, m["style"], spec.FORMATS[m["format"]]["gen"][0])
        for n, s in enumerate(shots, 1):
            progress(n, len(shots), "İlk kareler çiziliyor")
            cur = rec["shots"].setdefault(s["id"], {"versions": [], "selected": None})
            v = len(cur["versions"]) + 1
            png, qc, prompt = await draw(f, s, cast, refs, m["style"], 1000 + 37 * n + 101 * v, direction, http)
            name = f"{s['id']}.v{v}.png"
            (kd / name).write_bytes(png)
            cur["versions"].append({"v": v, "file": name, "prompt": prompt, "qc": qc, "by": by, "at": store.now(),
                                    **({"direction": direction} if direction else {})})
            cur["selected"] = v
            store.write(f, "kareler.json", rec)
    failed = sum(1 for x in rec["shots"].values() if x["versions"][x["selected"] - 1]["qc"].get("ok") is False)
    store.set_stage(f, "kareler", status="hazir", failed_qc=failed)
    store.log(f, by, "ilk kareler çizildi", count=len(shots), failed_qc=failed)
    return rec


def select(f: Path, shot_id: str, v: int, by: str) -> dict:
    rec = store.read(f, "kareler.json") or {"shots": {}}
    cur = rec["shots"].get(shot_id)
    if not cur or not 1 <= v <= len(cur["versions"]):
        raise store.FilmError("Böyle bir kare sürümü yok.")
    cur["selected"] = v
    store.write(f, "kareler.json", rec)
    store.set_stage(f, "kareler", status="hazir")
    store.log(f, by, "kare seçildi", shot=shot_id, v=v)
    return rec


def selected(f: Path, shot_id: str) -> Path:
    rec = store.read(f, "kareler.json") or {"shots": {}}
    cur = rec["shots"].get(shot_id)
    if not cur or not cur.get("selected"):
        raise store.FilmError(f"{shot_id} çekiminin ilk karesi yok.")
    return f / "kare" / cur["versions"][cur["selected"] - 1]["file"]
