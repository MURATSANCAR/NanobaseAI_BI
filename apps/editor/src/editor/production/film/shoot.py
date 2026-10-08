"""Çekim: ilk kare video modelinde hareketlenir (gateway `book-video`, images/video/server.py). GPU'nun en ağır işi;
gece kuyruğunda, Temporal'da çekim çekim yürür (flow: FilmShoot), yarıda kalan kaldığı yerden sürer.

Uç sözleşmesi (POST /v1/video/generations, gövde JSON):
    {"model": "book-video", "mode": "i2v" | "s2v", "image": <png b64>, "prompt", "negative_prompt",
     "seconds", "width", "height", "seed", "audio": <wav b64, yalnız s2v>,
     "engine"?: "wan2.2" | "h3" | "fast-h3", "refs"?: [<png b64>]}
    → {"video": <mp4 b64>, "seconds", "fps", "frames", "engine"}
`engine` yalnız EDITOR_VIDEO_ENGINE verilmişse gönderilir (yoksa servisin VIDEO_ENGINE'i). `refs` yalnız s2v'de:
çekimdeki karakterlerin kart görselleri (H3 ref2va'da karakter kimliği; Wan ve FastH3 yok sayar). Lisansı olmayan
motor 409 döner → editöre Türkçe hata.

İyileştirme (POST /v1/video/enhance {model, video, target, fps} → {video, width, height, fps, engine}): çekimler
bittikten sonra her seçili çekim bir kez SeedVR2 + RIFE'tan geçer, `cekim/<id>.vK.hd.mp4` olarak saklanır; kurgu
varsa onu kullanır. Servis yoksa ya da hata verirse çekimin `hd_error`'una yazılır, kurgu lanczos yoluna düşer ve
film.json'daki kurgu adımına `enhanced: n/toplam` yazılır (sessiz düşüş yok). Bir sonraki çekim koşusu eksik
iyileştirmeleri yeniden dener.
`i2v`: kareden hareket. `s2v`: konuşan çekim — karakterin ağzı verilen replik sesine uyar (yalnız tek konuşanlı,
yakın/bel planda; çok kişili sahne ve geniş plan i2v + kurguda ses).

Her çekimden üç kare görsel denetçiye gider (frames.review): bozulma, yazı, karakter kayması. Geçmeyen çekim bir kez
yeni tohumla yeniden çekilir; yine geçmezse editörün önüne «denetimden geçmedi» notuyla gelir.
"""

from __future__ import annotations

import asyncio
import base64
import os
import re
import subprocess
import tempfile
from pathlib import Path

import httpx

from . import cast as cast_mod
from . import dialogue
from . import frames as F
from . import script as script_mod
from . import spec, store

ALIAS = "book-video"
RETRIES = 1
ENHANCE_FPS = 24             # kurgu kare hızı (mix.FPS)
MAX_REFS = 8
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


def engine_override() -> str | None:
    return os.environ.get("EDITOR_VIDEO_ENGINE", "").strip() or None


def enhance_target() -> str | None:
    """Kurgu öncesi iyileştirme hedefi (1080p | 4k); EDITOR_FILM_ENHANCE=0 kapatır."""
    if os.environ.get("EDITOR_FILM_ENHANCE", "1").strip() == "0":
        return None
    return os.environ.get("EDITOR_FILM_ENHANCE_TARGET", "1080p").strip() or "1080p"


def char_refs(f: Path, shot: dict, first: str | None = None) -> list[Path]:
    """Çekimdeki karakterlerin referans görselleri, oyuncu listesi sırasıyla: onaylı kartın görseli, yoksa kareler
    adımının çizdiği `kare/oyuncu-<n>.png` (frames._char_refs ile aynı ad). Görseli olmayan karakter atlanır."""
    try:
        cast = cast_mod.load(f)
    except store.FilmError:
        return []
    out = []
    members = sorted(enumerate(cast["members"]), key=lambda im: im[1]["name"] != first)   # konuşan önce (<Subject 1>)
    for i, m in members:
        if m["name"] not in shot.get("characters", []):
            continue
        p = Path(m["ref"]) if m.get("ref") else f / "kare" / f"oyuncu-{i:02d}.png"
        if p.is_file():
            out.append(p)
    return out[:MAX_REFS]


def body_for(f: Path, shot: dict, first: Path, mode: str, seconds: float, W: int, H: int, style: str,
             lines: list[dict], talking: bool | None = None) -> dict:
    """`talking`: çekimde gerçek konuşma var mı (is_speech). Yoksa i2v'de ağızlar kapalı (dış ses); birden çok konuşan
    varsa (i2v) konuşanlar doğal konuşur. None: eski davranış (satır varsa ağızlar kapalı değil, ek yok)."""
    body = {"mode": mode, "image": base64.b64encode(first.read_bytes()).decode(),
            "prompt": spec.shot_prompt(shot, style, {}) + _mouths(mode, lines, talking),
            "negative_prompt": F.NEGATIVE,
            "seconds": seconds, "width": W, "height": H}
    eng = engine_override()
    if eng:
        body["engine"] = eng
    if mode == "s2v":
        body["audio"] = base64.b64encode(talk_track(f, lines, seconds)).decode()
        refs = char_refs(f, shot, next((x["speaker"] for x in lines if x["speaker"].casefold() != spec.NARRATOR), None))
        if refs:
            body["refs"] = [base64.b64encode(p.read_bytes()).decode() for p in refs]
    return body


def cast_lines_of(f: Path) -> dict[str, str]:
    from . import cast as cast_mod
    try:
        return cast_mod.card_lines(cast_mod.load(f))
    except store.FilmError:
        return {}


_SPEECH_MARKS = ("-", "–", "—", "«", '"', "“", ":")
# Konuşma etiketi: «…, diye sordu», «…, dedi», «…, diyordu». Okuma tireyi/tırnağı düşürebiliyor (2026-10-08: Levent
# kitabında hiçbir replikte tire kalmamıştı); etiket metinde kalır. Dil kuralı, kitaba özel değil.
_SAID = re.compile(r"^[^\n]{0,160}?[,!?…]\s*(?:diye\b|de(?:d|r)i\b|dedi[mk]?\b|diyordu[mk]?\b|diyor\w*|sordu\b|"
                   r"bağırdı\b|seslendi\b)", re.I)
QUIET_MOUTHS = " The characters do not talk: mouths stay closed (the words are a voice-over narration)."


TALKING = " The characters who speak move their mouths naturally while talking; the others listen."


def _mouths(mode: str, lines: list[dict], talking: bool | None) -> str:
    if mode != "i2v" or not lines or talking is None:
        return ""
    return TALKING if talking else QUIET_MOUTHS


def is_speech(text: str, book: str) -> bool:
    """Satır kitapta konuşma mı (tire, tırnak ya da iki nokta ardından)? Birinci tekil anlatımda dış ses satırının
    konuşanı da kahramandır; anlatımı ağızdan konuşturmak dudak uyumsuzluğu yapıyordu (2026-10-08). Kitapta
    bulunamayan satır (senaryonun yazdığı replik) konuşma sayılır."""
    probe = " ".join(text.split()[:4]).strip(" .,!?…")
    i = book.find(probe) if probe else -1
    if i < 0:
        return True
    j = i - 1
    while j >= 0 and book[j] in " \t\n":
        j -= 1
    return (j >= 0 and book[j] in _SPEECH_MARKS) or bool(_SAID.match(book[i:]))


def mode_of(shot: dict, lines: list[dict], book: str | None = None) -> str:
    spoken = [x for x in lines if x["speaker"].casefold() != spec.NARRATOR
              and (book is None or is_speech(x["text"], book))]
    speakers = {x["speaker"] for x in spoken}
    if len(speakers) != 1:
        return "i2v"
    if book is not None:            # kitaba bakılabiliyorsa: tek konuşan her çekimde ağız sesle eşlenir (kartı ilk referans)
        return "s2v"
    return "s2v" if shot["framing"] in TALK_FRAMINGS and len(shot.get("characters", [])) == 1 else "i2v"


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


async def workers() -> list[str]:
    """Çekim alabilecek takma adlar: `book-video` + gateway'de tanımlıysa `book-video-2`, `book-video-3`… (her biri
    ayrı kartta ayrı video modeli). Çekimler aralarında paylaştırılır."""
    if os.environ.get("EDITOR_VIDEO_URL"):
        return [ALIAS]
    url, hd = _endpoint()
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{url}/v1/models", headers=hd)
        ids = [m.get("id", "") for m in r.json().get("data", [])] if r.status_code == 200 else []
    except (httpx.HTTPError, ValueError):
        ids = []
    extra = sorted(i for i in ids if re.fullmatch(re.escape(ALIAS) + r"-\d+", i))
    return [ALIAS] + extra


async def _call(http, body: dict, alias: str = ALIAS) -> dict:
    url, hd = _endpoint()
    try:
        r = await http.post(f"{url}/v1/video/generations", json={"model": alias, **body}, headers=hd)
    except httpx.HTTPError as e:
        raise VideoUnavailable(f"video servisine ulaşılamadı: {type(e).__name__}") from None
    if r.status_code == 404:
        raise VideoUnavailable("video servisi bu kurulumda açık değil")
    if r.status_code in (409, 422):           # motor kapalı / bu motor bu kipi desteklemiyor (örn. fast-h3 s2v)
        raise store.FilmError(_detail(r))
    r.raise_for_status()
    return r.json()


def _detail(r) -> str:
    try:
        return str(r.json().get("detail") or r.text)[:300]
    except ValueError:
        return r.text[:300]


async def _enhance_call(http, mp4: bytes, target: str) -> dict:
    url, hd = _endpoint()
    try:
        r = await http.post(f"{url}/v1/video/enhance", headers=hd,
                            json={"model": ALIAS, "video": base64.b64encode(mp4).decode(), "target": target,
                                  "fps": ENHANCE_FPS})
    except httpx.HTTPError as e:
        raise VideoUnavailable(f"iyileştirme servisine ulaşılamadı: {type(e).__name__}") from None
    if r.status_code == 404:
        raise VideoUnavailable("iyileştirme servisi bu kurulumda açık değil")
    if r.status_code >= 400:
        raise RuntimeError(f"iyileştirme hatası {r.status_code}: {_detail(r)}")
    return r.json()


def _pick_best(f: Path, sid: str, taken: list[int] | None = None) -> bool:
    """Çekimin seçili sürümü: `taken` (bu koşuda alınan sürümler; verilmezse seçili sürümün karesiyle çekilmiş bütün
    sürümler) içinden ilk geçen, yoksa en az sorunlu. Dönen: geçen var mı. Hiç sürüm yoksa False (yeniden çekilir)."""
    rec = store.read(f, "cekimler.json") or {"shots": {}}
    cur = rec["shots"].get(sid)
    if not cur or not cur.get("versions"):
        return False
    if taken is None:
        first = cur["versions"][cur["selected"] - 1]["first_frame"]
        cands = [v for v in cur["versions"] if v["first_frame"] == first]
    else:
        cands = [v for v in cur["versions"] if v["v"] in taken]
    if not cands:
        return False
    ok = [v for v in cands if v["qc"].get("ok") is not False]
    best = ok[0] if ok else min(cands, key=lambda v: len(v["qc"].get("problems", [])))
    cur["selected"] = best["v"]
    store.write(f, "cekimler.json", rec)
    return bool(ok)


def hd_name(file: str) -> str:
    """`s01c02.v3.mp4` → `s01c02.v3.hd.mp4`."""
    return file[:-4] + ".hd.mp4"


def _mark(f: Path, sid: str, v: int, **fields) -> None:
    rec = store.read(f, "cekimler.json") or {"shots": {}}
    ver = rec["shots"][sid]["versions"][v - 1]
    for k, val in fields.items():
        if val is None:
            ver.pop(k, None)
        else:
            ver[k] = val
    store.write(f, "cekimler.json", rec)


async def enhance_selected(f: Path, http, progress=lambda n, t, w="": None) -> dict:
    """Her seçili çekimi bir kez iyileştirir (iyileştirilmiş kopyası yoksa). Dönüş {done, total, error}.
    Hata çekim adımını durdurmaz: nedeni sürümün `hd_error`'una yazılır, kurgu ham çekimle sürer. Servise hiç
    ulaşılamıyorsa kalan çekimler denenmez."""
    target = enhance_target()
    rec = store.read(f, "cekimler.json") or {"shots": {}}
    sel = [(sid, x["versions"][x["selected"] - 1]) for sid, x in sorted(rec["shots"].items()) if x.get("selected")]
    res = {"done": 0, "total": len(sel), "error": None}
    if target is None:
        res["error"] = "iyileştirme kapalı (EDITOR_FILM_ENHANCE=0)"
    todo = [] if target is None else [(sid, v) for sid, v in sel
                                      if not ((v.get("hd") or {}).get("file") and (f / "cekim" / v["hd"]["file"]).is_file())]
    for n, (sid, v) in enumerate(todo, 1):
        progress(n, len(todo), "Çekimler iyileştiriliyor")
        try:
            out = await _enhance_call(http, (f / "cekim" / v["file"]).read_bytes(), target)
        except (VideoUnavailable, RuntimeError, httpx.HTTPError, ValueError) as e:
            res["error"] = str(e)[:300]
            _mark(f, sid, v["v"], hd_error=res["error"])
            if isinstance(e, VideoUnavailable):
                break
            continue
        name = hd_name(v["file"])
        (f / "cekim" / name).write_bytes(base64.b64decode(out["video"]))
        _mark(f, sid, v["v"], hd={"file": name, "width": out.get("width"), "height": out.get("height"),
                                   "fps": out.get("fps"), "engine": out.get("engine"), "target": target,
                                   "at": store.now()}, hd_error=None)
    res["done"] = sum(1 for sid, _ in sel if for_mix(f, sid)[1])
    return res


async def take(f: Path, shot: dict, by: str, seed: int, http, alias: str = ALIAS) -> dict:
    """Bir çekim alır ve sürüm olarak kaydeder (denetimsiz, qc «bekliyor»). Seçili sürüm, çekimin ilk sürümüyse bu olur."""
    m = store.meta(f)
    W, H = spec.FORMATS[m["format"]]["gen"]
    voice = dialogue.load(f)
    lines = voice["lines"].get(shot["id"], [])
    seconds = voice["seconds"].get(shot["id"], float(shot["seconds"]))
    first = F.selected(f, shot["id"])
    book = script_mod.book_text(f.parent.parent)
    mode = mode_of(shot, lines, book)
    talking = any(x["speaker"].casefold() != spec.NARRATOR and is_speech(x["text"], book) for x in lines)
    res = await _call(http, {**body_for(f, shot, first, mode, seconds, W, H, m["style"], lines, talking),
                             "seed": seed}, alias)
    rec = store.read(f, "cekimler.json") or {"shots": {}}
    cur = rec["shots"].setdefault(shot["id"], {"versions": [], "selected": None})
    v = len(cur["versions"]) + 1
    cd = f / "cekim"
    cd.mkdir(exist_ok=True)
    name = f"{shot['id']}.v{v}.mp4"
    (cd / name).write_bytes(base64.b64decode(res["video"]))
    cur["versions"].append({"v": v, "file": name, "mode": mode, "seconds": res.get("seconds", seconds),
                            "engine": res.get("engine"), "first_frame": first.name,
                            "qc": {"ok": None, "problems": [], "pending": True}, "by": by, "at": store.now()})
    cur["selected"] = v
    store.write(f, "cekimler.json", rec)
    return cur["versions"][-1]


async def check(f: Path, shot: dict, ver: dict, http) -> dict:
    """Çekimden üç kare görsel denetçiye; sonuç sürümün `qc`'sine yazılır."""
    lines_of = cast_lines_of(f)
    mp4 = (f / "cekim" / ver["file"]).read_bytes()
    checks = [await F.review(http, fr, shot, lines_of) for fr in sample_frames(mp4)]
    bad = [p for c in checks if c["ok"] is False for p in c["problems"]]
    qc = {"ok": None if all(c["ok"] is None for c in checks) else not bad, "problems": sorted(set(bad))}
    _mark(f, shot["id"], ver["v"], qc=qc)
    return qc


async def shoot_one(f: Path, shot: dict, by: str, seed: int, http) -> dict:
    """Tek çekim: al, denetle, geçmezse yeni tohumla yeniden (en çok RETRIES)."""
    ver = None
    for k in range(RETRIES + 1):
        ver = await take(f, shot, by, seed + k, http)
        ver["qc"] = await check(f, shot, ver, http)
        if ver["qc"]["ok"] is not False:
            break
    return ver


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
        # Video modeli bir kartta, görsel denetçi öbüründe: çekimler sırayla alınırken önceki çekimin denetimi aynı
        # anda koşar (aynı karttaysa gateway sıraya koyar). Birden çok video modeli varsa (`workers`) çekimler
        # aralarında paylaşılır ve denetim tur sonunda yapılır (denetçinin kartı da çekimde). Geçmeyenler turun
        # sonunda yeniden çekilir; en iyi sürüm seçilir (2026-10-08: tek kartta çekim başı 25 dk).
        aliases = await workers()
        seeds = {s["id"]: 5000 + 53 * n for n, s in enumerate(todo, 1)}
        round_ = todo
        taken: dict[str, list[int]] = {}
        for k in range(RETRIES + 1):
            queue = list(round_)
            done: list[tuple[dict, dict]] = []
            failed: dict[str, str] = {}
            qcs = []
            label = "Çekimler yapılıyor" if k == 0 else "Geçmeyen çekimler yeniden çekiliyor"

            async def run(alias: str) -> None:
                while queue:
                    s = queue.pop(0)
                    progress(len(done) + 1, len(round_), label)
                    try:
                        ver = await take(f, s, by, seeds[s["id"]] + k, http, alias)
                    except (httpx.HTTPError, store.FilmError) as e:
                        # tek çekimin hatası çekim adımını durdurmaz (2026-10-08: bir OOM 35 çekimi kesti); çekim
                        # sonraki turda yeniden denenir
                        failed[s["id"]] = str(e)[:300]
                        continue
                    done.append((s, ver))
                    taken.setdefault(s["id"], []).append(ver["v"])
                    if len(aliases) == 1:
                        qcs.append(asyncio.create_task(check(f, s, ver, http)))

            await asyncio.gather(*(run(a) for a in aliases))
            if len(aliases) > 1:
                for n, (s, ver) in enumerate(done, 1):
                    progress(n, len(done), "Çekimler denetleniyor")
                    await check(f, s, ver, http)
            await asyncio.gather(*qcs)
            round_ = [s for s in round_ if not _pick_best(f, s["id"], taken.get(s["id"], []))]
            if failed:
                store.log(f, by, "çekim hatası", shots=failed)
            if not round_:
                break
        hd = await enhance_selected(f, http, progress)
    rec = store.read(f, "cekimler.json") or {"shots": {}}
    failed = sum(1 for x in rec["shots"].values() if x["versions"][x["selected"] - 1]["qc"].get("ok") is False)
    store.set_stage(f, "cekim", status="hazir", shot=len(todo), failed_qc=failed,
                    enhanced=f"{hd['done']}/{hd['total']}", enhance_error=hd["error"])
    store.log(f, by, "çekimler yapıldı", count=len(todo), failed_qc=failed, enhanced=hd["done"],
              enhance_error=hd["error"])
    return rec


def for_mix(f: Path, shot_id: str) -> tuple[Path, bool]:
    """Kurguya girecek dosya: seçili sürümün iyileştirilmiş kopyası varsa o (True), yoksa ham çekim (False)."""
    rec = store.read(f, "cekimler.json") or {"shots": {}}
    cur = rec["shots"].get(shot_id)
    if not cur or not cur.get("selected"):
        raise store.FilmError(f"{shot_id} çekimi yok.")
    v = cur["versions"][cur["selected"] - 1]
    hd = (v.get("hd") or {}).get("file")
    if hd and (f / "cekim" / hd).is_file():
        return f / "cekim" / hd, True
    return f / "cekim" / v["file"], False


def selected(f: Path, shot_id: str) -> Path:
    rec = store.read(f, "cekimler.json") or {"shots": {}}
    cur = rec["shots"].get(shot_id)
    if not cur or not cur.get("selected"):
        raise store.FilmError(f"{shot_id} çekimi yok.")
    return f / "cekim" / cur["versions"][cur["selected"] - 1]["file"]

