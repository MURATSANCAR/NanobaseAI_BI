"""Kurgu ve ses miksi: çekimler art arda, replikler yerinde, efekt, ortam sesi ve sahne müziği altta; konuşma olunca
efekt, ortam ve müzik kısılır; son ses düzeyi biçimin hedefine (spec.FORMATS lufs) getirilir. Altyazı her zaman ayrı dosyadır (.srt);
reels'te görüntüye de basılır (sosyal medyada çoğu kişi sessiz izler).

Efekt ve ortam sesi, Sesli Okuma'nın efekt havuzundan (sfx_library, GPU'daki telifsiz arşiv) senaryonun Türkçe
tarifiyle aranır; seçim `kurgu.json`'a yazılır (editör değiştirebilir), kaynakça dosyası çıktının yanındadır.

Sahne müziği (music.py, kurgu etkinliği bu adımdan önce üretir) ayrı bir izdir: her sahnenin parçası sahne sınırının
iki yanında XFADE/2 taşar, komşu parçalar XFADE boyunca biri kısılırken öbürü açılarak geçer (çapraz geçiş); filmin
başında ve sonunda yumuşak açılış/kapanış. Müzik izi replik izine göre ayrıca kısılır (MUSIC_DUCK, efektten yavaş
geri açılır). Müzik yoksa (servis kapalı, sahne müziksiz) komut müziksiz kurguyla birebir aynıdır.

Zaman çizelgesi (`timeline`) ve ffmpeg komutu (`command`) modelsiz ve deterministiktir; testler ikisini doğrudan
çağırır. Video büyütme ve ara kare (SeedVR2 + RIFE, `book-video` /v1/video/enhance) çekim adımının sonunda her seçili
çekime bir kez uygulanır (shoot.enhance_selected, `cekim/<id>.vK.hd.mp4`); kurgu varsa iyileştirilmiş kopyayı alır,
yoksa ham çekimi lanczos ile ölçekler. Kaç çekimin iyileştirildiği film.json kurgu adımına `enhanced: n/toplam`
olarak yazılır.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .. import studio
from . import dialogue
from . import script as script_mod
from . import shoot as shoot_mod
from . import spec, store

FPS = 24
FX_DB = -8.0                 # anlık efekt, replikten alçak
AMB_DB = -20.0               # ortam sesi
FX_MAX = 4.0                 # anlık efektin en uzun kısmı (sn)
FADE = 0.25
AMB_FADE = 1.2
DUCK = "threshold=0.03:ratio=8:attack=15:release=350"
MUSIC_DB = -17.0             # sahne müziği, konuşma yokken; konuşmada MUSIC_DUCK ile ayrıca kısılır
MUSIC_DUCK = "threshold=0.02:ratio=6:attack=25:release=700"
MUSIC_EDGE = 1.5             # filmin başında açılış, sonunda kapanış (sn)
SUB_FONT = "Lato"
SUB_CHARS = {"16:9": 42, "9:16": 30, "1:1": 34}


def line_starts(durations: list[float]) -> list[float]:
    """Çekim içinde replik başlangıçları: sırayla, aralarında spec.LINE_GAP (shoot.talk_track ile aynı düzen)."""
    out, t = [], 0.0
    for d in durations:
        out.append(round(t, 3))
        t += d + spec.LINE_GAP
    return out


def timeline(sc: dict, voice: dict, videos: dict[str, str], picks: dict, music: dict | None = None) -> dict:
    """{"shots": [{id, start, seconds, video, lines:[{file,start,duration,text,speaker}], sfx:[{file,start}]}],
    "ambience": [{file, start, seconds}], "music": [{file, start, seconds, fade_in, fade_out}], "total"}.
    `picks`: {"sfx": {<çekim>: [dosya|None]}, "amb": {<sahne>: dosya}}. `music`: {<sahne>: dosya} (music.scene_files)."""
    shots, t = [], 0.0
    scene_span: dict[int, list[float]] = {}
    for s in spec.shots(sc):
        secs = float(voice["seconds"].get(s["id"], s["seconds"]))
        ls = voice["lines"].get(s["id"], [])
        starts = line_starts([x["duration"] for x in ls])
        fx = [{"file": p, "start": round(t + 0.2 + 0.6 * k, 3)}
              for k, p in enumerate(picks.get("sfx", {}).get(s["id"], [])) if p]
        shots.append({"id": s["id"], "start": round(t, 3), "seconds": secs, "video": videos[s["id"]],
                      "lines": [{"file": x["file"], "start": round(t + st, 3), "duration": x["duration"],
                                 "text": x["text"], "speaker": x["speaker"]} for x, st in zip(ls, starts)],
                      "sfx": fx})
        span = scene_span.setdefault(s["scene"], [t, t])
        span[1] = t + secs
        t += secs
    amb = [{"file": picks["amb"][str(sc_no)], "start": round(a, 3), "seconds": round(b - a, 3)}
           for sc_no, (a, b) in scene_span.items() if picks.get("amb", {}).get(str(sc_no))]
    return {"shots": shots, "ambience": amb, "music": music_track(scene_span, music or {}, t), "total": round(t, 3)}


def music_track(scene_span: dict[int, list[float]], music: dict, total: float) -> list[dict]:
    """Sahne müzikleri: sahne sınırında yarım XFADE taşar, komşuyla XFADE boyunca çapraz geçer. Komşu sahnede müzik
    yoksa o yanda taşma olmaz, parça sahne sınırında XFADE/2 içinde kapanır (açılır)."""
    from .music import XFADE
    half = XFADE / 2
    out = []
    for sc_no, (a, b) in scene_span.items():
        f = music.get(str(sc_no))
        if not f:
            continue
        prev_on, next_on = bool(music.get(str(sc_no - 1))), bool(music.get(str(sc_no + 1)))
        s = max(0.0, a - half) if prev_on else a
        e = min(total, b + half) if next_on else b
        fi = XFADE if prev_on and a > 0 else (MUSIC_EDGE if a <= 0 else half)
        fo = XFADE if next_on and b < total else (MUSIC_EDGE if b >= total else half)
        secs = round(e - s, 3)
        out.append({"file": f, "start": round(s, 3), "seconds": secs, "fade_in": round(min(fi, secs / 2), 3),
                    "fade_out": round(min(fo, secs / 2), 3)})
    return out


def _clock(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def _wrap(text: str, width: int) -> str:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    if len(lines) > 2:                       # en çok iki satır: kalan ikinci satıra
        lines = [lines[0], " ".join(lines[1:])]
    return "\n".join(lines)


def srt(tl: dict, aspect: str) -> str:
    width = SUB_CHARS.get(aspect, 40)
    out, n = [], 0
    for s in tl["shots"]:
        for ln in s["lines"]:
            n += 1
            out.append(f"{n}\n{_clock(ln['start'])} --> {_clock(ln['start'] + ln['duration'])}\n"
                       f"{_wrap(ln['text'], width)}\n")
    return "\n".join(out)


def command(tl: dict, fmt: str, voice_dir: Path, out: Path, srt_path: Path | None) -> list[str]:
    f = spec.FORMATS[fmt]
    W, H = f["out"]
    args = ["ffmpeg", "-v", "error", "-y"]
    vf, af, n = [], [], 0
    for s in tl["shots"]:
        args += ["-i", s["video"]]
        S = s["seconds"]
        vf.append(f"[{n}:v]fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},"
                  f"setsar=1,tpad=stop_mode=clone:stop_duration={S},trim=0:{S},setpts=PTS-STARTPTS[v{n}]")
        n += 1
    nv = n
    vf.append("".join(f"[v{i}]" for i in range(nv)) + f"concat=n={nv}:v=1:a=0[vcat]")
    norm = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
    dl, fx = [], []
    for s in tl["shots"]:
        for ln in s["lines"]:
            args += ["-i", str(voice_dir / ln["file"])]
            ms = int(ln["start"] * 1000)
            af.append(f"[{n}:a]{norm},adelay={ms}|{ms}[d{n}]")
            dl.append(f"[d{n}]")
            n += 1
        for x in s["sfx"]:
            args += ["-i", x["file"]]
            ms = int(x["start"] * 1000)
            af.append(f"[{n}:a]{norm},atrim=0:{FX_MAX},afade=t=out:st={FX_MAX - FADE}:d={FADE},volume={FX_DB}dB,"
                      f"adelay={ms}|{ms}[x{n}]")
            fx.append(f"[x{n}]")
            n += 1
    for a in tl["ambience"]:
        args += ["-stream_loop", "-1", "-i", a["file"]]
        ms, S = int(a["start"] * 1000), a["seconds"]
        af.append(f"[{n}:a]{norm},atrim=0:{S},afade=t=in:d={AMB_FADE},afade=t=out:st={max(S - AMB_FADE, 0)}:"
                  f"d={AMB_FADE},volume={AMB_DB}dB,adelay={ms}|{ms}[x{n}]")
        fx.append(f"[x{n}]")
        n += 1
    mus = []
    for m in tl.get("music", []):
        args += ["-stream_loop", "-1", "-i", m["file"]]
        ms, S = int(m["start"] * 1000), m["seconds"]
        af.append(f"[{n}:a]{norm},atrim=0:{S},afade=t=in:d={m['fade_in']},afade=t=out:st={max(S - m['fade_out'], 0)}:"
                  f"d={m['fade_out']},volume={MUSIC_DB}dB,adelay={ms}|{ms}[m{n}]")
        mus.append(f"[m{n}]")
        n += 1
    T = tl["total"]
    silent = f"anullsrc=r=48000:cl=stereo,atrim=0:{T}"
    af.append(f"{silent}[sil0]")
    af.append(f"{silent}[sil1]")
    af.append("".join(dl) + f"[sil0]amix=inputs={len(dl) + 1}:normalize=0:duration=longest[dlg]")
    af.append("".join(fx) + f"[sil1]amix=inputs={len(fx) + 1}:normalize=0:duration=longest[fxb]")
    if not mus:
        af.append("[dlg]asplit=2[dlg1][dlg2]")
        af.append(f"[fxb][dlg2]sidechaincompress={DUCK}[fxd]")
        af.append(f"[dlg1][fxd]amix=inputs=2:normalize=0:duration=longest,atrim=0:{T},"
                  f"loudnorm=I={f['lufs']}:TP=-1.5:LRA=11[aout]")
    else:
        af.append(f"{silent}[sil2]")
        af.append("".join(mus) + f"[sil2]amix=inputs={len(mus) + 1}:normalize=0:duration=longest[mub]")
        af.append("[dlg]asplit=3[dlg1][dlg2][dlg3]")
        af.append(f"[fxb][dlg2]sidechaincompress={DUCK}[fxd]")
        af.append(f"[mub][dlg3]sidechaincompress={MUSIC_DUCK}[mud]")
        af.append(f"[dlg1][fxd][mud]amix=inputs=3:normalize=0:duration=longest,atrim=0:{T},"
                  f"loudnorm=I={f['lufs']}:TP=-1.5:LRA=11[aout]")
    vout = "vcat"
    if srt_path is not None and f["burn_subtitles"]:
        size = 14 if f["aspect"] == "16:9" else 18
        style = f"FontName={SUB_FONT},Bold=1,Fontsize={size},Outline=2,Shadow=0,Alignment=2,MarginV={40 if f['aspect'] == '16:9' else 110}"
        vf.append(f"[vcat]subtitles={srt_path}:fontsdir={studio.fonts()}:force_style='{style}'[vsub]")
        vout = "vsub"
    args += ["-filter_complex", ";".join(vf + af), "-map", f"[{vout}]", "-map", "[aout]",
             "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS),
             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", str(T), str(out)]
    return args


def pick_sounds(sc: dict, old: dict | None = None) -> dict:
    """Senaryonun efekt ve ortam tarifleri → havuzdan dosya. Editörün seçtiği (`source: editor`) korunur."""
    from .. import sfx_library as L
    old = old or {}
    picks = {"sfx": {}, "amb": {}, "ids": []}
    if not L.available():
        return picks
    for s in spec.shots(sc):
        keep = old.get("sfx", {}).get(s["id"])
        if keep is not None and old.get("editor", {}).get(s["id"]):
            picks["sfx"][s["id"]] = keep
            continue
        files = []
        for q in s.get("sfx", [])[:3]:
            res = L.search(q, kind="anlik", k=1)
            files.append(str(L.file_of(res[0])) if res else None)
            if res:
                picks["ids"].append(res[0]["id"])
        picks["sfx"][s["id"]] = files
    for si, scene in enumerate(sc.get("scenes", []), 1):
        q = next((sh.get("ambience") for sh in scene.get("shots", []) if (sh.get("ambience") or "").strip()), "")
        if q:
            res = L.search(q, kind="ortam", k=1)
            if res:
                picks["amb"][str(si)] = str(L.file_of(res[0]))
                picks["ids"].append(res[0]["id"])
    return picks


def pick_videos(f: Path, shot_ids: list[str]) -> tuple[dict[str, str], int]:
    """Çekim → kurguya girecek dosya (iyileştirilmiş kopya varsa o) ve iyileştirilmiş çekim sayısı."""
    videos, hd = {}, 0
    for sid in shot_ids:
        p, is_hd = shoot_mod.for_mix(f, sid)
        videos[sid] = str(p)
        hd += is_hd
    return videos, hd


def build(d: Path, f: Path, by: str, progress=lambda n, t, w="": None, music: dict | None = None) -> dict:
    """Kurgu. `music`: {sahne: wav yolu} (music.scene_files); boş ya da None ise müziksiz kurgu (eski davranış)."""
    store.require(f, "cekim")
    m = store.meta(f)
    sc = script_mod.load(f)
    voice = dialogue.load(f)
    store.set_stage(f, "kurgu", status="calisiyor")
    progress(1, 3, "Sesler seçiliyor")
    old = store.read(f, "kurgu.json") or {}
    picks = pick_sounds(sc, old.get("picks"))
    videos, hd = pick_videos(f, [s["id"] for s in spec.shots(sc)])
    tl = timeline(sc, voice, videos, picks, music)
    od = f / "cikti"
    od.mkdir(exist_ok=True)
    aspect = spec.FORMATS[m["format"]]["aspect"]
    (od / "film.srt").write_text(srt(tl, aspect))
    progress(2, 3, "Kurgu yapılıyor")
    tmp = od / "film.tmp.mp4"
    subprocess.run(command(tl, m["format"], f / "ses", tmp, od / "film.srt"), check=True, timeout=3600)
    tmp.replace(od / "film.mp4")
    credits = []
    if picks["ids"]:
        from .. import sfx_library as L
        credits = L.credits(sorted(set(picks["ids"])))
    enhanced = f"{hd}/{len(videos)}"
    has_music = "var" if tl["music"] else "yok"
    rec = {"picks": picks, "timeline": tl, "credits": credits, "by": by, "at": store.now(),
           "file": "cikti/film.mp4", "subtitles": "cikti/film.srt", "seconds": tl["total"], "enhanced": enhanced,
           "music": has_music}
    store.write(f, "kurgu.json", rec)
    store.set_stage(f, "kurgu", status="hazir", seconds=tl["total"], enhanced=enhanced, music=has_music)
    store.log(f, by, "kurgu yapıldı", seconds=tl["total"], enhanced=enhanced)
    progress(3, 3, "Bitti")
    return rec
