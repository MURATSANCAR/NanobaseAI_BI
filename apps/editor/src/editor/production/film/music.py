"""Film müziği: sahne başına sözsüz fon müziği ve isteğe bağlı tema şarkısı (gateway `book-music`,
images/music/server.py). Kurgu adımının parçasıdır (store.STAGES'e ayrı adım eklenmez): kurgu etkinliği (flow.py)
önce bunu, sonra mix.build'i çalıştırır. Servis bu kurulumda yoksa (takma ad listesinde değil ya da 404) müzik
sessizce atlanır; kurgu müziksiz yapılır, film.json'un kurgu adımına `music: "yok"` yazılır.

Akış:
    1. Sahne planı (modelsiz): her sahnenin başlangıcı ve süresi, kurgunun zaman çizelgesiyle aynı hesap (ses adımının
       gerçek çekim süreleri) — `scene_plan`.
    2. Müzik ipucu (ana model `book-director`, istem `production_film_music`): her sahne için İngilizce sözsüz fon
       tarifi (tarz, duygu, çalgılar), tempo, ton ve editörün okuyacağı kısa Türkçe duygu; sahnede müzik gerekmiyorsa
       `music: false`. Tema şarkısı istenirse aynı çağrıda Türkçe söz + İngilizce tarz. Kurallar kitaptan bağımsızdır;
       söz kitabın adından, konusundan ve okur yaşından yazılır, kitaba özel ayar yoktur. Plan, girdinin özetiyle
       anahtarlıdır: senaryo ve süreler değişmediyse model yeniden çağrılmaz.
    3. Üretim: sahne süresi + çapraz geçiş payı kadar parça (`kind: score`); tema şarkısı `kind: song`. Aynı tarif ve
       süreyle üretilmiş parça yeniden üretilmez. Bir sahnenin hatası filmi düşürmez: sahne müziksiz kalır, hata
       muzik.json'a yazılır.

Motoru servis seçer (images/music/server.py: sahne müziği Stable Audio 3 > ACE-Step 1.5 XL > YuE2 sözsüz; şarkı
YuE2 > MiniMax Music 3 > HeartMuLa); yanıttaki `engine` kayda girer, ekranda gösterilmez. Tempo ve ton ipucu her motora
gider; tutmayan motorda parça kurguda sahneye uydurulur (mix.py: kesme, döngü, çapraz geçiş).

Kayıt: `<film>/muzik/<sahne>.wav`, `muzik/tema.wav`, `muzik.json`. Tema şarkısı filmin içine karıştırılmaz (filmin
süresi çekimlerle sabittir, sözlü şarkı replikle çakışır); ayrı dosyadır, editör indirir.

Uç sözleşmesi (POST /v1/audio/music):
    {"model": "book-music", "kind": "score" | "song", "prompt", "seconds", "bpm"?, "key"?, "lyrics"?, "engine"?,
     "seed"} → {"audio": <wav b64>, "seconds", "engine", "sample_rate", "truncated"}
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

import httpx

from .. import marketing as mk
from .. import studio
from . import dialogue
from . import script as script_mod
from . import spec, store

ALIAS = "book-music"
PROMPT = "production_film_music"
DIR = "muzik"
XFADE = 2.0                  # sahne geçişinde iki parçanın üst üste bindiği süre (sn)
THEME_SEC = 120.0            # tema şarkısı için istenen süre (şarkı motoru sözün uzunluğuna göre kısaltabilir)
TIMEOUT = httpx.Timeout(1800.0, connect=10.0)
MIN_BPM, MAX_BPM = 40, 220

_STR = {"type": "string"}
SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["cues", "theme"],
    "properties": {
        "cues": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["scene", "music", "prompt_en", "mood", "bpm", "key"],
            "properties": {"scene": {"type": "number"}, "music": {"type": "boolean"}, "prompt_en": _STR,
                           "mood": _STR, "bpm": {"type": "number"}, "key": _STR}}},
        "theme": {"type": "object", "additionalProperties": False, "required": ["title", "lyrics", "style_en"],
                  "properties": {"title": _STR, "lyrics": _STR, "style_en": _STR}}}}


class MusicUnavailable(RuntimeError):  # noqa: N818
    """Müzik servisi bu kurulumda açık değil."""


def _endpoint() -> tuple[str, dict]:
    direct = os.environ.get("EDITOR_MUSIC_URL", "").rstrip("/")
    if direct:
        return direct, {}
    from . import frames as F
    return F._gateway()


async def available() -> bool:
    """Gateway `book-music` takma adını tanıyor mu (ya da doğrudan uç verilmiş mi)? Model ayağa kaldırılmaz."""
    if os.environ.get("EDITOR_MUSIC_URL"):
        return True
    url, hd = _endpoint()
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{url}/v1/models", headers=hd)
        return r.status_code == 200 and any(m.get("id") == ALIAS for m in r.json().get("data", []))
    except (httpx.HTTPError, ValueError):
        return False


# ------------------------------------------------------------------ modelsiz: sahne planı ve kayıt
def scene_plan(sc: dict, voice: dict) -> list[dict]:
    """Sahneler sırayla: {scene, start, seconds, setting, time, actions, emotions}. Süre, kurgunun zaman çizelgesindeki
    gibi ses adımının gerçek çekim süresidir (mix.timeline ile aynı toplama)."""
    out: dict[int, dict] = {}
    t = 0.0
    for s in spec.shots(sc):
        secs = float(voice["seconds"].get(s["id"], s["seconds"]))
        cur = out.setdefault(s["scene"], {"scene": s["scene"], "start": round(t, 3), "seconds": 0.0,
                                          "setting": s.get("setting", ""), "time": s.get("time", "gunduz"),
                                          "actions": [], "emotions": []})
        cur["seconds"] = round(cur["seconds"] + secs, 3)
        cur["actions"].append(s.get("action", ""))
        cur["emotions"] += [ln.get("emotion", "notr") for ln in s.get("lines", [])]
        t += secs
    return list(out.values())


def plan_key(plan: list[dict], theme: bool, fmt: str, style: str) -> str:
    """Müzik ipucunun girdisi: sahne tarifleri, süreleri, biçim ve üslup. Değişmediyse ipucu yeniden istenmez."""
    raw = json.dumps({"p": [[p["scene"], p["seconds"], p["setting"], p["time"], p["actions"], p["emotions"]]
                            for p in plan], "t": theme, "f": fmt, "s": style}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def clean_cues(raw: list[dict], plan: list[dict]) -> list[dict]:
    """Modelin ipucunu sahne planına oturtur: bilinmeyen sahne atılır, eksik sahne müziksiz kalır, tempo sınırda,
    tarif boşsa müzik yok. Her sahne için tek kayıt, plan sırasıyla."""
    by = {}
    for c in raw:
        try:
            n = int(c.get("scene"))
        except (TypeError, ValueError):
            continue
        if n not in by:
            by[n] = c
    out = []
    for p in plan:
        c = by.get(p["scene"], {})
        prompt = (c.get("prompt_en") or "").strip()
        bpm = c.get("bpm")
        bpm = int(min(MAX_BPM, max(MIN_BPM, round(bpm)))) if isinstance(bpm, (int, float)) and bpm > 0 else None
        out.append({"scene": p["scene"], "start": p["start"], "seconds": p["seconds"],
                    "music": bool(c.get("music")) and bool(prompt), "prompt": prompt[:600],
                    "mood": (c.get("mood") or "").strip()[:60], "bpm": bpm, "key": (c.get("key") or "").strip()[:30]})
    return out


def piece_seconds(cue: dict) -> float:
    """İstenen parça süresi: sahne + iki yanda yarım çapraz geçiş payı (mix.timeline'ın müzik bölümüyle aynı)."""
    return round(cue["seconds"] + XFADE, 3)


def cue_key(cue: dict) -> str:
    raw = json.dumps([cue["prompt"], cue["bpm"], cue["key"], piece_seconds(cue)], ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def scene_files(f: Path, rec: dict | None) -> dict[str, str]:
    """Kurgunun kullanacağı müzik: {sahne no (str): dosya yolu}; yalnız dosyası duran sahneler."""
    out = {}
    for c in (rec or {}).get("cues", []):
        p = f / DIR / c["file"] if c.get("file") else None
        if p is not None and p.is_file():
            out[str(c["scene"])] = str(p)
    return out


# ------------------------------------------------------------------ model
async def _call(http, body: dict) -> dict:
    url, hd = _endpoint()
    try:
        r = await http.post(f"{url}/v1/audio/music", json={"model": ALIAS, **body}, headers=hd)
    except httpx.HTTPError as e:
        raise MusicUnavailable(f"müzik servisine ulaşılamadı: {type(e).__name__}") from None
    if r.status_code == 404:
        raise MusicUnavailable("müzik servisi bu kurulumda açık değil")
    r.raise_for_status()
    return r.json()


async def release(http) -> None:
    """Müzik modelini hemen kapatır (gateway iç ucu); kapanmazsa boşta kalınca kendisi kapanır."""
    if os.environ.get("EDITOR_MUSIC_URL"):
        return
    from ...config import settings
    url, _ = _endpoint()
    try:
        await http.post(f"{url}/internal/stop/{ALIAS}", timeout=90,
                        headers={"authorization": f"Bearer {settings().gateway_internal_key}"})
    except httpx.HTTPError:
        pass


async def write_cues(d: Path, f: Path, plan: list[dict], theme: bool, llm=None) -> dict:
    m = store.meta(f)
    sc = script_mod.load(f)
    llm = llm or mk.make_llm(d)
    scenes = "\n".join(
        f"- Sahne {p['scene']}: {p['seconds']:.0f} sn, {p['setting']}, {p['time']}. Olan: "
        f"{' / '.join(a for a in p['actions'] if a)}. Replik duyguları: {', '.join(sorted(set(p['emotions']))) or 'yok'}."
        for p in plan)
    want = ("İsteniyor: filmin tema şarkısını da yaz (`theme`)." if theme else
            "Tema şarkısı istenmiyor: `theme` alanlarını boş bırak.")
    out = await mk._ask(llm, PROMPT, SCHEMA, max_tokens=4000, temperature=0.4,
                        title=studio._manuscript(d).title, kind=mk._kind_text(d),
                        format=spec.FORMATS[m["format"]]["label"].lower(), style=spec.STYLES[m["style"]]["label"],
                        logline=sc.get("logline", ""), scenes=scenes, theme=want)
    th = out.get("theme") or {}
    return {"cues": clean_cues(out.get("cues", []), plan),
            "theme": {"title": (th.get("title") or "").strip()[:120], "lyrics": (th.get("lyrics") or "").strip()[:4000],
                      "style": (th.get("style_en") or "").strip()[:600]} if theme else None}


async def build(d: Path, f: Path, by: str, progress=lambda n, t, w="": None, theme: bool = False, llm=None) -> dict:
    """Sahne müziklerini (ve istenirse tema şarkısını) üretir. Servis yoksa hiçbir şey yapmaz, `music: "yok"` döner."""
    store.require(f, "cekim")
    old = store.read(f, "muzik.json") or {}
    if not await available():
        return {"music": "yok", "reason": "servis yok"}
    m = store.meta(f)
    sc = script_mod.load(f)
    plan = scene_plan(sc, dialogue.load(f))
    key = plan_key(plan, theme, m["format"], m["style"])
    progress(0, 1, "Müzik planlanıyor")
    if old.get("plan_key") == key:
        cues, theme_rec = old["cues"], old.get("theme")
    else:
        got = await write_cues(d, f, plan, theme, llm)
        cues, theme_rec = got["cues"], got["theme"]
    prev = {c["scene"]: c for c in old.get("cues", [])}
    md = f / DIR
    md.mkdir(exist_ok=True)
    todo = [c for c in cues if c["music"]]
    total = len(todo) + (1 if theme_rec and theme_rec.get("lyrics") else 0)
    made, reason = 0, ""
    async with httpx.AsyncClient(timeout=TIMEOUT) as http:
        try:
            for n, c in enumerate(todo, 1):
                progress(n, total, "Müzik hazırlanıyor")
                p = prev.get(c["scene"], {})
                h = cue_key(c)
                if p.get("hash") == h and p.get("file") and (md / p["file"]).is_file():
                    c.update({x: p[x] for x in ("hash", "file", "engine", "seed", "got_seconds") if x in p})
                    continue
                c["hash"], c["seed"] = h, 7000 + 31 * c["scene"]
                try:
                    res = await _call(http, {"kind": "score", "prompt": c["prompt"], "seconds": piece_seconds(c),
                                             "bpm": c["bpm"], "key": c["key"] or None, "seed": c["seed"]})
                except MusicUnavailable:
                    raise
                except httpx.HTTPError as e:
                    c["error"] = f"{type(e).__name__}: {str(e)[:200]}"
                    continue
                name = f"s{c['scene']:02d}.wav"
                (md / name).write_bytes(base64.b64decode(res["audio"]))
                c.update(file=name, engine=res.get("engine"), got_seconds=res.get("seconds"))
                c.pop("error", None)
                made += 1
            if theme_rec and theme_rec.get("lyrics"):
                progress(total, total, "Tema şarkısı hazırlanıyor")
                got = await _theme(http, md, theme_rec, old.get("theme"))
                made += got is not old.get("theme") and bool(got.get("file"))
                theme_rec = got
        except MusicUnavailable as e:
            reason = str(e)
        finally:
            if made:
                await release(http)
    if reason and not made:
        return {"music": "yok", "reason": reason}
    rec = {"plan_key": key, "cues": cues, "theme": theme_rec, "xfade": XFADE, "by": by, "at": store.now(),
           **({"reason": reason} if reason else {})}
    store.write(f, "muzik.json", rec)
    store.log(f, by, "müzik hazırlandı", scenes=sum(1 for c in cues if c.get("file")), theme=bool(theme_rec))
    return {"music": "var" if scene_files(f, rec) else "yok", **rec}


async def _theme(http, md: Path, th: dict, old: dict | None) -> dict:
    k = hashlib.sha256(json.dumps([th["lyrics"], th["style"]], ensure_ascii=False).encode()).hexdigest()[:16]
    if old and old.get("hash") == k and old.get("file") and (md / old["file"]).is_file():
        return old
    th = {**th, "hash": k, "seed": 9100}
    try:
        res = await _call(http, {"kind": "song", "prompt": th["style"] or "children's song, cheerful", "seconds": THEME_SEC,
                                 "lyrics": th["lyrics"], "seed": th["seed"]})
    except (httpx.HTTPError, MusicUnavailable) as e:
        return {**th, "error": f"{type(e).__name__}: {str(e)[:200]}"}
    (md / "tema.wav").write_bytes(base64.b64decode(res["audio"]))
    return {**th, "file": "tema.wav", "engine": res.get("engine"), "got_seconds": res.get("seconds"),
            "truncated": res.get("truncated")}
