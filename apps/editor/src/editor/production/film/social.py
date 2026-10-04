"""Paylaşım paketi: bitmiş filmden platform kesitleri, kapak karesi, açıklama ve etiket taslağı.

Otomatik paylaşım YOKTUR (dış gönderim kapalı): editör paketi onaylar, dosyaları indirir, kendisi paylaşır. Onaysız
paket indirilemez; onaydan sonra yapılan düzeltme onayı düşürür (pazarlama kitiyle aynı kural).

Kesit: filmin en-boy oranı platformunkiyle aynıysa yalnız süre kırpılır; farklıysa görüntü ortalanır, boşluk aynı
görüntünün bulanık büyütülmüşüyle doldurulur (siyah bant yok). Platformun süre sınırını aşan film baştan kesilir ve son
saniyede kararır. Açıklama ve etiketler ana modelin taslağıdır (`production_film_social`); kitabın adı birebir geçer.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .. import marketing as mk
from .. import studio
from . import script as script_mod
from . import spec, store

PROMPT = "production_film_social"
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["caption", "hashtags", "hook"],
          "properties": {"caption": {"type": "string"}, "hashtags": {"type": "array", "items": {"type": "string"}},
                         "hook": {"type": "string"}}}
END_FADE = 0.8


def _ratio(aspect: str) -> float:
    a, b = aspect.split(":")
    return int(a) / int(b)


def cut_command(src: Path, src_aspect: str, platform: str, seconds: float, out: Path) -> list[str]:
    p = spec.PLATFORMS[platform]
    W, H = p["size"]
    T = min(seconds, p["max_sec"]) if p["max_sec"] else seconds
    if _ratio(src_aspect) == _ratio(p["aspect"]):
        vf = f"scale={W}:{H}:flags=lanczos,setsar=1"
    else:
        vf = (f"split=2[bg][fg];[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=40,"
              f"eq=brightness=-0.08[bgb];[fg]scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos[fgs];"
              f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1")
    fade = ""
    if T < seconds:
        fade = f",fade=t=out:st={T - END_FADE}:d={END_FADE}"
    afade = f"afade=t=out:st={T - END_FADE}:d={END_FADE}" if T < seconds else "anull"
    return ["ffmpeg", "-v", "error", "-y", "-i", str(src), "-filter_complex", f"[0:v]{vf}{fade}[v];[0:a]{afade}[a]",
            "-map", "[v]", "-map", "[a]", "-t", str(T), "-c:v", "libx264", "-preset", "slow", "-crf", "19",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)]


def cover(f: Path, title: str, size: tuple[int, int], out: Path) -> None:
    """Kapak karesi: ilk çekimin seçili ilk karesi + kitabın adı (Lato Bold, alt bant)."""
    from PIL import Image, ImageDraw, ImageFont

    from . import frames
    sc = script_mod.load(f)
    first = spec.shots(sc)[0]["id"]
    im = Image.open(frames.selected(f, first)).convert("RGB")
    W, H = size
    s = max(W / im.width, H / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    im = im.crop(((im.width - W) // 2, (im.height - H) // 2, (im.width - W) // 2 + W, (im.height - H) // 2 + H))
    dr = ImageDraw.Draw(im, "RGBA")
    font = ImageFont.truetype(str(studio.fonts() / "Lato-Bold.ttf"), size=max(36, W // 16))
    box = dr.textbbox((0, 0), title, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    pad = W // 24
    y = H - th - pad * 3
    dr.rectangle((0, y - pad, W, H), fill=(0, 0, 0, 140))
    dr.text(((W - tw) // 2, y), title, font=font, fill=(255, 255, 255, 255))
    im.save(out, "JPEG", quality=92)


async def write_text(d: Path, f: Path, llm=None) -> dict:
    sc = script_mod.load(f)
    llm = llm or mk.make_llm(d)
    dg = await mk.digest(d, llm)
    title = studio._manuscript(d).title
    out = await mk._ask(llm, PROMPT, SCHEMA, max_tokens=1500, temperature=0.6, title=title, kind=mk._kind_text(d),
                        logline=sc.get("logline", ""), summary=mk._summary_text(dg)[:6000])
    tags = []
    for t in out["hashtags"]:
        t = "".join(t.replace("#", "").split())
        if t and t.casefold() not in {x.casefold() for x in tags}:
            tags.append(t)
    return {"caption": out["caption"].strip()[:2200], "hashtags": tags[:10], "hook": out["hook"].strip()[:80]}


async def build(d: Path, f: Path, by: str, platforms: list[str], progress=lambda n, t, w="": None) -> dict:
    store.require(f, "kurgu")
    m = store.meta(f)
    unknown = [p for p in platforms if p not in spec.PLATFORMS]
    if unknown or not platforms:
        raise store.FilmError("Bilinmeyen ya da boş platform listesi.")
    store.set_stage(f, "paylasim", status="calisiyor")
    od = f / "cikti" / "paylasim"
    od.mkdir(parents=True, exist_ok=True)
    src = f / "cikti" / "film.mp4"
    seconds = (store.read(f, "kurgu.json") or {}).get("seconds", 0)
    title = studio._manuscript(d).title
    files = []
    for n, p in enumerate(platforms, 1):
        progress(n, len(platforms) + 1, "Kesitler hazırlanıyor")
        out = od / f"{p}.mp4"
        subprocess.run(cut_command(src, spec.FORMATS[m["format"]]["aspect"], p, seconds, out), check=True,
                       timeout=1800)
        cv = od / f"{p}-kapak.jpg"
        cover(f, title, spec.PLATFORMS[p]["size"], cv)
        files.append({"platform": p, "label": spec.PLATFORMS[p]["label"], "video": out.relative_to(f).as_posix(),
                      "cover": cv.relative_to(f).as_posix()})
    progress(len(platforms) + 1, len(platforms) + 1, "Paylaşım metni yazılıyor")
    text = await write_text(d, f)
    rec = {"files": files, "text": text, "by": by, "at": store.now()}
    store.write(f, "paylasim.json", rec)
    store.set_stage(f, "paylasim", status="hazir", platforms=platforms)
    store.log(f, by, "paylaşım paketi hazırlandı", platforms=platforms)
    return rec


def edit_text(f: Path, caption: str, hashtags: list[str], hook: str, by: str) -> dict:
    rec = store.read(f, "paylasim.json")
    if not rec:
        raise store.FilmError("Paylaşım paketi yok.")
    rec["text"] = {"caption": caption.strip()[:2200], "hook": hook.strip()[:80],
                   "hashtags": ["".join(t.replace("#", "").split()) for t in hashtags if t.strip()][:10]}
    rec.update(by=by, at=store.now())
    store.write(f, "paylasim.json", rec)
    store.set_stage(f, "paylasim", status="hazir")
    store.log(f, by, "paylaşım metni düzeltildi")
    return rec
