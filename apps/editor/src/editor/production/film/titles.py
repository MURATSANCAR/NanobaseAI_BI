"""Açılış ve kapanış jeneriği (2026-10-08, kullanıcı: «çizgi filmlerdeki girişler gibi, şarkımızla»).

Bölüm düzeni: kanca (uyarlamanın 1. beat'i) → açılış jeneriği (tema şarkısı üstünde bölümden kısa kesitler + dizi
logosu ve bölüm adı) → hikâye → kapanış jeneriği (şarkının sonu, kayan isimler). İsim kartı beat'inin çekimi açılışın
yerini alır. Yazılar ffmpeg ile basılır (görsel model yazı çizmez); jeneriğe model ya da teknoloji adı girmez.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .. import studio
from . import spec, store

FONT = "Baloo2[wght].ttf"          # yuvarlak, çocuk dostu
OPEN_SEC = 20.0                    # açılış jeneriği
LOGO_SEC = 4.5                     # sonundaki logo kartı
CLIP_SEC = 1.9                     # açılıştaki kesit uzunluğu
CREDITS_SEC = 18.0
FPS = 24
W, H = 1920, 1080


def _esc(t: str) -> str:
    return t.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")


def pick_clips(shots: list[dict], videos: dict[str, str], n: int) -> list[tuple[str, float]]:
    """Açılış için bölümden kesitler: yakın planlar, eşit aralıklı (bölümün başından sonuna), kanca ve isim hariç.
    Dönen: [(video, başlangıç sn)]."""
    pool = [s for s in shots if s.get("framing") in ("yakin", "cok-yakin", "omuz-ustu") and s["id"] in videos
            and float(s.get("seconds") or 0) >= CLIP_SEC]
    if not pool:
        pool = [s for s in shots if s["id"] in videos]
    step = max(1, len(pool) // max(n, 1))
    return [(videos[s["id"]], 0.3) for s in pool[::step][:n]]


def opening(clips: list[tuple[str, float]], logo_bg: str, series: str, episode: str, theme: str, out: Path) -> None:
    """Açılış jeneriği: kesitler (her biri CLIP_SEC, çapraz kesme) + logo kartı (arka plan yavaşça yakınlaşır),
    altında tema şarkısının başı (sonda kısılır)."""
    font = str(Path(studio.fonts()) / FONT)
    args = ["ffmpeg", "-v", "error", "-y"]
    vf = []
    for i, (v, st) in enumerate(clips):
        args += ["-ss", f"{st:.2f}", "-t", f"{CLIP_SEC:.2f}", "-i", v]
        vf.append(f"[{i}:v]fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,"
                  f"tpad=stop_mode=clone:stop_duration={CLIP_SEC},trim=0:{CLIP_SEC},setpts=PTS-STARTPTS[c{i}]")
    n = len(clips)
    args += ["-loop", "1", "-t", f"{LOGO_SEC:.2f}", "-i", logo_bg]
    frames = int(LOGO_SEC * FPS)
    vf.append(f"[{n}:v]scale={W * 2}:{H * 2},zoompan=z='min(1.0+0.0012*on,1.12)':d={frames}:s={W}x{H}:fps={FPS},"
              f"eq=brightness=-0.06,"
              f"drawtext=fontfile='{font}':text='{_esc(series)}':fontsize=230:fontcolor=white:borderw=14:"
              f"bordercolor=0xE8552B:shadowx=8:shadowy=10:shadowcolor=0x00000088:x=(w-text_w)/2:"
              f"y=(h-text_h)/2-80:alpha='min(1,t/0.6)',"
              f"drawtext=fontfile='{font}':text='{_esc(episode)}':fontsize=92:fontcolor=0xFFF3C4:borderw=7:"
              f"bordercolor=0x2B5BA8:x=(w-text_w)/2:y=(h/2)+110:alpha='min(1,max(0,(t-0.7)/0.6))',"
              f"setsar=1,format=yuv420p[lg]")
    vf.append("".join(f"[c{i}]" for i in range(n)) + f"[lg]concat=n={n + 1}:v=1:a=0[v]")
    total = n * CLIP_SEC + LOGO_SEC
    args += ["-i", theme]
    af = (f"[{n + 1}:a]aresample=48000,atrim=0:{total:.2f},afade=t=in:d=0.3,"
          f"afade=t=out:st={total - 1.5:.2f}:d=1.5,volume=-4dB[a]")
    args += ["-filter_complex", ";".join(vf + [af]), "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18",
             "-preset", "medium", "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k",
             "-t", f"{total:.2f}", str(out)]
    subprocess.run(args, check=True, timeout=900)


def credits_lines(d: Path, f: Path) -> list[str]:
    """Kapanış yazıları: bölüm, kitap künyesi (yazar/çizer varsa), yapım. Model/teknoloji adı yok."""
    man = studio._manuscript(d)
    m = store.meta(f)
    out = [m.get("title") or man.title, "", f"Kitap: {man.title}"]
    if getattr(man, "author", None):
        out.append(f"Yazan: {man.author}")
    ill = (getattr(man, "illustrator", None) or "").strip()
    if ill:
        out.append(f"Resimleyen: {ill}")
    out += ["", "Yapım: Zeki AI · Timaş Yayınları"]
    return out


def credits(bg_video: str, lines: list[str], theme: str, out: Path) -> None:
    """Kapanış jeneriği: son çekim kararır ve bulanıklaşır, yazılar aşağıdan yukarı kayar; tema şarkısının sonu."""
    font = str(Path(studio.fonts()) / FONT)
    T = CREDITS_SEC
    step = 96
    speed = (H + step * len(lines)) / T
    draws = "".join(f",drawtext=fontfile='{font}':text='{_esc(t)}':fontsize={84 if i == 0 else 60}:fontcolor="
                    f"{'0xFFF3C4' if i == 0 else 'white'}:x=(w-text_w)/2:y=h+{i * step}-{speed:.2f}*t"
                    for i, t in enumerate(lines) if t.strip())
    vf = (f"[0:v]fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,"
          f"tpad=stop_mode=clone:stop_duration={T},trim=0:{T},setpts=PTS-STARTPTS,boxblur=12:2,eq=brightness=-0.35"
          f"{draws},fade=t=in:d=0.8,fade=t=out:st={T - 1.2}:d=1.2,format=yuv420p[v]")
    af = (f"[1:a]aresample=48000,areverse,atrim=0:{T},areverse,afade=t=in:d=1,"
          f"afade=t=out:st={T - 2}:d=2,volume=-4dB[a]")
    args = ["ffmpeg", "-v", "error", "-y", "-i", bg_video, "-i", theme, "-filter_complex", f"{vf};{af}",
            "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "192k", "-t", str(T), str(out)]
    subprocess.run(args, check=True, timeout=900)


def assemble(body: str, hook_sec: float, title_sec: float, opening_mp4: str, credits_mp4: str, out: Path,
             lufs: float) -> None:
    """Bölüm: gövdeden kanca [0, hook) + açılış + gövdenin isim kartından sonrası + kapanış; ses ölçümü bütün
    bölümde bir kez."""
    cut = hook_sec + title_sec
    fc = (f"[0:v]trim=0:{hook_sec},setpts=PTS-STARTPTS[v0];[0:a]atrim=0:{hook_sec},asetpts=PTS-STARTPTS[a0];"
          f"[0:v]trim={cut},setpts=PTS-STARTPTS[v2];[0:a]atrim={cut},asetpts=PTS-STARTPTS[a2];"
          f"[1:v]scale={W}:{H},setsar=1[v1];[2:v]scale={W}:{H},setsar=1[v3];"
          f"[v0][a0][v1][1:a][v2][a2][v3][2:a]concat=n=4:v=1:a=1[v][a0n];"
          f"[a0n]loudnorm=I={lufs}:TP=-1.5:LRA=11[a]")
    args = ["ffmpeg", "-v", "error", "-y", "-i", body, "-i", opening_mp4, "-i", credits_mp4, "-filter_complex", fc,
            "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p",
            "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)]
    subprocess.run(args, check=True, timeout=3600)


def hook_and_title(script: dict, voice: dict) -> tuple[float, float]:
    """Kanca ve isim kartı beat'lerinin gövdedeki süresi (uyarlamanın `outline`'ından; çekimin `beat` alanı)."""
    outline = script.get("outline") or []
    purpose = {i: b.get("purpose") for i, b in enumerate(outline, 1)}
    hook = title = 0.0
    for s in spec.shots(script):
        secs = float(voice["seconds"].get(s["id"], s["seconds"]))
        p = purpose.get(int(s.get("beat") or 0))
        if p == "kanca":
            hook += secs
        elif p == "isim":
            title += secs
    return round(hook, 3), round(title, 3)
