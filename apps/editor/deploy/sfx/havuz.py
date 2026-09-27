#!/usr/bin/env python3
"""Efekt havuzunu kurar: indirilen arşivleri açar, her dosyayı kataloğa yazar, ses gömmesini ve arama dizinini çıkarır.

GPU'da GEÇİCİ kapta çalışır (çalışan kaplara dokunmaz); ses çözme/ölçme/gömme için torch + transformers + librosa +
soundfile + ffmpeg gerekir (editor-voice imajında hazır). Kalıcı çıktı yalnız /data/editor/sfx altındadır:

    docker run --rm -v /data/editor/sfx:/data/editor/sfx -v /data/editor/models/sfx-clap:/model:ro \
        -v <repo>/apps/editor:/src:ro --entrypoint python3 editor-voice:1 /src/deploy/sfx/havuz.py <adım>

Adımlar (sırayla; her biri kaldığı yerden sürer):
    ac        _indir/<kaynak> arşivlerini /data/editor/sfx/<kaynak>/ altına açar. Mac artığı (__MACOSX, ._*) açılmaz.
              FSD50K'dan yalnız CC0 ve CC BY klipler çıkarılır (lisans dosyası klip başına).
    katalog   her ses dosyası: süre, örnekleme hızı, kanal, tümleşik yükseklik (LUFS, BS.1770), tepe, kırpılma
              oranı, sha256, etiketler (ad/klasör/kaynak üst verisi), kategoriler, lisans, atıf → <kaynak>/katalog.jsonl
    gomme     ses-metin eşleme modelinin ses kolu → _dizin/gomme.npy (katalogla aynı sırada) + _dizin/katalog.jsonl
    metin     aynı modelin metin kolunu ONNX'e çevirir (stüdyo sorguyu torch'suz gömer) + eşdeğerlik denetimi
    rapor     kategori kapsaması, kaynak dağılımı, işaretli dosyalar (JSON, stdout)

Ölçüm ayrıntıları (tavan değil, ölçümün tanımı): yükseklik dosyanın ilk LUFS_SEC saniyesinden ölçülür (uzun ortam
kayıtlarında ilk beş dakika sayfaya giren kısımdır); gömme, dosyaya eşit aralıkla yayılmış en çok WINDOWS adet 10 sn'lik
pencerenin ortalamasıdır (modelin girdisi 10 sn; uzun dosyada baştan sona temsil).
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import struct
import sys
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(os.environ.get("EDITOR_SFX_ROOT", "/data/editor/sfx"))
IN = ROOT / "_indir"
IDX = ROOT / "_dizin"
MODEL = Path(os.environ.get("SFX_MODEL", "/model/larger_clap_general"))
AUDIO_EXT = {".wav", ".flac", ".ogg", ".oga", ".mp3", ".aif", ".aiff", ".opus"}
LUFS_SEC = 300
WINDOWS = 6
SR = 48000

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from editor.production import sfx_library as L  # noqa: E402  (yalnız kategori ağacı ve yardımcılar; ağır bağımlılık yok)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def mac_junk(name: str) -> bool:
    parts = name.replace("\\", "/").split("/")
    return any(p == "__MACOSX" or p.startswith("._") or p == ".DS_Store" for p in parts)


def safe_rel(name: str) -> str | None:
    n = name.replace("\\", "/").lstrip("/")
    if ".." in n.split("/"):
        return None
    return n


# ------------------------------------------------------------------ açma
def extract(z: zipfile.ZipFile, dest: Path, want=None) -> int:
    n = 0
    for zi in z.infolist():
        if zi.is_dir() or mac_junk(zi.filename):
            continue
        rel = safe_rel(zi.filename)
        if not rel or Path(rel).suffix.lower() not in AUDIO_EXT | {".pdf", ".txt", ".csv", ".md"}:
            continue
        if want is not None and not want(rel):
            continue
        out = dest / rel
        if out.exists() and out.stat().st_size == zi.file_size:
            n += 1
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.name + ".part")
        with z.open(zi) as src, tmp.open("wb") as dst:
            while True:
                b = src.read(1 << 22)
                if not b:
                    break
                dst.write(b)
        tmp.replace(out)
        n += 1
    return n


def step_ac():
    # Sonniss: yıl klasörleri, her zip (ya da yılın tek zip'i) açılır
    for ydir in sorted((IN / "sonniss").glob("20*")):
        for zp in sorted(ydir.glob("*.zip")):
            if not (zp.with_name(zp.name + ".ok")).exists():
                log("atlandı (inmemiş)", zp)
                continue
            done = ydir / (zp.name + ".acildi")
            if done.exists():
                continue
            log("açılıyor", zp)
            with zipfile.ZipFile(zp) as z:
                n = extract(z, ROOT / "sonniss" / ydir.name)
            done.write_text(str(n))
            log("açıldı", zp.name, n)
        for pdf in ydir.glob("*.pdf"):
            (ROOT / "sonniss" / ydir.name).mkdir(parents=True, exist_ok=True)
            (ROOT / "sonniss" / ydir.name / f"LISANS-{pdf.name}").write_bytes(pdf.read_bytes())
    # Kenney, OpenGameArt: paket zip'leri + tek dosyalar
    for src in ("kenney", "opengameart"):
        for f in sorted((IN / src).glob("*")):
            if f.suffix == ".ok" or f.name.endswith(".acildi"):
                continue
            pack = f.stem
            if f.suffix == ".zip":
                if (f.with_name(f.name + ".acildi")).exists():
                    continue
                with zipfile.ZipFile(f) as z:
                    n = extract(z, ROOT / src / pack)
                ok = f.with_name(f.name + ".ok")
                (ROOT / src / pack / "KAYNAK.txt").write_text(ok.read_text() if ok.exists() else "")
                f.with_name(f.name + ".acildi").write_text(str(n))
                log(src, pack, n)
            elif f.suffix.lower() in AUDIO_EXT:
                d = ROOT / src / pack
                d.mkdir(parents=True, exist_ok=True)
                (d / f.name).write_bytes(f.read_bytes())
                ok = f.with_name(f.name + ".ok")
                (d / "KAYNAK.txt").write_text(ok.read_text() if ok.exists() else "")
    # FSD50K: yalnız CC0 / CC BY
    fd = IN / "fsd50k"
    meta = {}
    for s in ("dev", "eval"):
        p = fd / "FSD50K.metadata" / f"{s}_clips_info_FSD50K.json"
        if p.exists():
            meta.update(json.loads(p.read_text()))
    ok_lic = {k for k, v in meta.items() if "/zero/" in v["license"] or re.search(r"/licenses/by/\d", v["license"])}
    for s, parts in (("dev", ["z01", "z02", "z03", "z04", "z05", "zip"]), ("eval", ["z01", "zip"])):
        files = [fd / f"FSD50K.{s}_audio.{x}" for x in parts]
        if not all((f.with_name(f.name + ".ok")).exists() for f in files):
            log("FSD50K", s, "tam inmemiş, atlandı")
            continue
        done = fd / f"{s}.acildi"
        if done.exists():
            continue
        # Python'un zipfile'ı çok diskli zip64'ü açmaz: parçalar `zip -s 0` ile geçici tek dosyada birleştirilir.
        import subprocess
        whole = fd / f"{s}.tek.zip"
        if not whole.exists():
            subprocess.run(["zip", "-q", "-s", "0", str(files[-1]), "--out", str(whole)], check=True)
        with zipfile.ZipFile(whole) as z:
            n = extract(z, ROOT / "fsd50k", want=lambda rel: Path(rel).stem in ok_lic)
        whole.unlink()
        done.write_text(str(n))
        log("FSD50K", s, n)
    # Commons: indirilen dosyalar yerinde (tek klasör)
    cd = IN / "commons"
    if (cd / "commons.jsonl").exists():
        dst = ROOT / "commons"
        dst.mkdir(parents=True, exist_ok=True)
        for line in (cd / "commons.jsonl").read_text().splitlines():
            r = json.loads(line)
            f = cd / r["file"]
            if f.exists() and not (dst / f.name).exists():
                os.link(f, dst / f.name)
    log("açma bitti")


# ------------------------------------------------------------------ etiketler
STOP = set("""a an the and or of in on at to for with from by into over under off up down out as is are was were be
been this that these those it its no not very some more most less few one two three four five six seven eight nine ten
wav mp3 ogg flac aif aiff stereo mono ms ss xy ortf mid side take tk v1 v2 v3 var variation version sfx fx sound
sounds audio file edit mix master final loop loops short long hi lo high low med medium soft hard close far distant
near big small large light heavy fast slow single multiple various misc general bundle gdc sonniss com part pack
kenney opengameart cc0 cc by recording recorded recordings rec sample samples library lib""".split())
CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
UCS = {"AMB": "ambience", "ANML": "animal", "BELL": "bell", "BIRD": "bird", "BOAT": "boat", "CART": "cartoon",
       "CRWD": "crowd", "DOOR": "door", "DSGN": "designed", "EXPL": "explosion", "FIRE": "fire", "FOLY": "foley",
       "FOOT": "footsteps", "GLAS": "glass", "HORN": "horn", "HMN": "human", "IMPT": "impact", "INSC": "insect",
       "KIDS": "children", "MAGC": "magic", "MECH": "mechanical", "METL": "metal", "RAIN": "rain", "ROCK": "rock",
       "SCFI": "scifi", "SWSH": "whoosh", "TOON": "cartoon", "TRAN": "train", "VEH": "vehicle", "VHCL": "vehicle",
       "WATR": "water", "WTHR": "weather", "WIND": "wind", "WOOD": "wood", "WEAP": "weapon", "GUNS": "gun",
       "AIR": "air", "ALRM": "alarm", "CLOCK": "clock", "COMP": "computer", "ELEC": "electric", "FARM": "farm",
       "FOOD": "food", "LIQ": "liquid", "MOTR": "motor", "NATR": "nature", "OBJ": "object", "PAPR": "paper",
       "ROBO": "robot", "SPRT": "sports", "TOOL": "tool", "TOYS": "toy", "USER": "interface", "UI": "interface",
       "VOX": "voice", "WHSH": "whoosh", "ZAP": "zap", "BOOM": "boom", "CERM": "ceramic", "CLOTH": "cloth",
       "DSTR": "destruction", "LAUGH": "laugh", "MOVE": "movement", "PLAS": "plastic", "SPLSH": "splash"}


def tokens(*texts: str) -> list[str]:
    out = []
    for t in texts:
        if not t:
            continue
        for part in re.split(r"[^A-Za-z0-9]+", t):
            if not part:
                continue
            up = part.upper()
            for code, word in UCS.items():
                if up.startswith(code) and (len(part) == len(code) or part[len(code):len(code) + 1].isupper()):
                    out.append(word)
                    part = part[len(code):]
                    break
            for w in CAMEL.split(part):
                w = w.lower()
                if len(w) < 2 or w.isdigit() or re.fullmatch(r"\d+[a-z]{0,2}|[a-z]\d+", w) or w in STOP:
                    continue
                out.append(w)
    return list(dict.fromkeys(out))


def riff_text(p: Path) -> str:
    """WAV içindeki açıklama alanları (bext description, LIST/INFO INAM/ICMT/IKEY): dosyanın ilk 8 MB'ı."""
    try:
        with p.open("rb") as f:
            head = f.read(12)
            if head[:4] != b"RIFF" or head[8:12] != b"WAVE":
                return ""
            out, read = [], 12
            while read < 8 << 20:
                h = f.read(8)
                if len(h) < 8:
                    break
                cid, size = h[:4], struct.unpack("<I", h[4:])[0]
                read += 8
                if cid == b"data":
                    f.seek(size + (size & 1), 1)
                    read += size
                    continue
                if cid in (b"bext", b"LIST", b"iXML") and size < 1 << 20:
                    body = f.read(size + (size & 1))
                    if cid == b"bext":
                        out.append(body[:256].split(b"\0")[0].decode("latin-1", "ignore"))
                    elif cid == b"LIST" and body[:4] == b"INFO":
                        k = 4
                        while k + 8 <= len(body):
                            sid, sz = body[k:k + 4], struct.unpack("<I", body[k + 4:k + 8])[0]
                            if sid in (b"INAM", b"ICMT", b"IKEY", b"ISBJ", b"IGNR"):
                                out.append(body[k + 8:k + 8 + sz].split(b"\0")[0].decode("latin-1", "ignore"))
                            k += 8 + sz + (sz & 1)
                    else:
                        m = re.findall(rb"<(?:DESCRIPTION|NOTE|CATEGORY|SUBCATEGORY|FXNAME|KEYWORDS)>([^<]{1,400})<", body)
                        out += [x.decode("utf-8", "ignore") for x in m]
                else:
                    f.seek(size + (size & 1), 1)
                read += size
            return " ".join(x.strip() for x in out if x.strip())[:1200]
    except OSError:
        return ""


# ------------------------------------------------------------------ ölçüm
def decode(p: Path, seconds: float | None = None):
    """(örnekler [kanal, n] float32, örnekleme hızı). soundfile okuyamazsa ffmpeg."""
    import numpy as np
    import soundfile as sf
    try:
        with sf.SoundFile(str(p)) as f:
            sr = f.samplerate
            n = f.frames if seconds is None else min(f.frames, int(seconds * sr))
            x = f.read(n, dtype="float32", always_2d=True).T
            return x, sr
    except Exception:  # noqa: BLE001
        import subprocess
        args = ["ffmpeg", "-nostdin", "-v", "error", "-i", str(p)] + (["-t", str(seconds)] if seconds else []) + \
               ["-f", "f32le", "-ac", "2", "-ar", "48000", "-"]
        raw = subprocess.run(args, capture_output=True, timeout=600).stdout
        x = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).T.copy()
        return x, 48000


def info(p: Path) -> tuple[float, int, int]:
    import soundfile as sf
    try:
        i = sf.info(str(p))
        return float(i.duration), int(i.samplerate), int(i.channels)
    except Exception:  # noqa: BLE001
        import subprocess
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                            "stream=sample_rate,channels:format=duration", "-of", "json", str(p)],
                           capture_output=True, text=True, timeout=120)
        j = json.loads(r.stdout or "{}")
        st = (j.get("streams") or [{}])[0]
        return float(j.get("format", {}).get("duration") or 0), int(st.get("sample_rate") or 0), int(st.get("channels") or 0)


def measure(p: Path) -> dict:
    import numpy as np
    import pyloudnorm as pyln
    dur, sr, ch = info(p)
    x, fs = decode(p, LUFS_SEC)
    if x.size == 0:
        return {"dur": round(dur, 3), "sr": sr, "ch": ch, "lufs": None, "peak": None, "clip": 0.0}
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    clip = float(np.mean(np.abs(x) >= 0.999)) if x.size else 0.0
    lufs = None
    try:
        data = x.T if x.shape[0] <= 5 else x[:2].T
        if data.shape[0] >= int(0.4 * fs):
            v = pyln.Meter(fs).integrated_loudness(data.astype(np.float64))
            lufs = round(float(v), 2) if math.isfinite(v) else -70.0
    except Exception:  # noqa: BLE001
        lufs = None
    return {"dur": round(dur, 3), "sr": sr or fs, "ch": ch or x.shape[0], "lufs": lufs,
            "peak": round(20 * math.log10(peak), 2) if peak > 0 else -120.0, "clip": round(clip, 6)}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def flags(m: dict) -> list[str]:
    out = []
    if m.get("lufs") is not None and m["lufs"] > -10:
        out.append("yuksek")
    if (m.get("clip") or 0) > 0.001:
        out.append("kirpik")
    if (m.get("dur") or 0) > 120:
        out.append("uzun")
    if (m.get("dur") or 0) < 0.15:
        out.append("kisa")
    if (m.get("lufs") is not None and m["lufs"] < -60) or (m.get("peak") is not None and m["peak"] < -50):
        out.append("sessiz")
    return out


# ------------------------------------------------------------------ kaynak başına kayıt
def _fsd():
    fd = IN / "fsd50k"
    meta, labels = {}, {}
    for s in ("dev", "eval"):
        p = fd / "FSD50K.metadata" / f"{s}_clips_info_FSD50K.json"
        if p.exists():
            meta.update(json.loads(p.read_text()))
        g = fd / "FSD50K.ground_truth" / f"{s}.csv"
        if g.exists():
            for line in g.read_text().splitlines()[1:]:
                parts = line.split(",")
                labels[parts[0]] = [x.replace("_", " ") for x in re.findall(r"[A-Za-z_()\-']+", line.split('"')[1] if '"' in line else parts[1])]
    return meta, labels


_FSD: tuple | None = None
_COMMONS: dict | None = None
_URETIM: dict | None = None


def describe(src: str, p: Path) -> dict:
    """Kaynağa göre etiket metni, lisans, atıf, sayfa."""
    global _FSD, _COMMONS
    rel = p.relative_to(ROOT / src)
    S = L.SOURCES[src]
    base = {"license": S["license"], "license_url": S["license_url"], "page": S["page"], "credit": None}
    if src == "sonniss":
        year = rel.parts[0]
        lib = rel.parts[1] if len(rel.parts) > 2 else ""
        return {**base, "title": p.stem, "text": [lib, *rel.parts[2:-1], p.stem, riff_text(p)], "group": f"GDC {year} · {lib}"}
    if src in ("kenney", "opengameart"):
        pack = rel.parts[0]
        page = ""
        k = ROOT / src / pack / "KAYNAK.txt"
        if k.exists():
            lines = k.read_text().splitlines()
            page = lines[1] if len(lines) > 1 else ""
        return {**base, "page": page or S["page"], "title": p.stem, "text": [pack, *rel.parts[1:-1], p.stem], "group": pack}
    if src == "fsd50k":
        if _FSD is None:
            _FSD = _fsd()
        meta, labels = _FSD
        m = meta.get(p.stem, {})
        lic = m.get("license", "")
        is0 = "/zero/" in lic
        url = f"https://freesound.org/s/{p.stem}/"
        credit = None if is0 else f"«{m.get('title', p.stem)}» — {m.get('uploader', '?')}, Freesound ({url}), CC BY 3.0"
        return {**base, "license": "CC0 1.0" if is0 else "CC BY 3.0", "license_url": lic, "page": url, "credit": credit,
                "title": m.get("title") or p.stem, "group": "Freesound",
                "text": [m.get("title", ""), " ".join(m.get("tags") or []), (m.get("description") or "")[:400],
                         " ".join(labels.get(p.stem, []))]}
    if src == "commons":
        if _COMMONS is None:
            _COMMONS = {}
            j = IN / "commons" / "commons.jsonl"
            if j.exists():
                for line in j.read_text().splitlines():
                    r = json.loads(line)
                    _COMMONS[Path(r["file"]).name] = r
        r = _COMMONS.get(p.name, {})
        lic = r.get("license", "")
        attrib = not re.match(r"(?i)(public domain|pd|cc0|cc zero)", lic)
        title = (r.get("title") or p.name).split(":", 1)[-1]
        credit = f"«{title}» — {r.get('artist') or 'bilinmiyor'}, Wikimedia Commons ({r.get('page')}), {lic}" if attrib else None
        return {**base, "license": lic, "license_url": r.get("license_url") or "", "page": r.get("page") or "",
                "credit": credit, "title": title, "group": "Wikimedia Commons",
                "text": [title, r.get("description", "")[:400], " ".join(r.get("categories") or [])]}
    if src == "uretim":
        global _URETIM
        if _URETIM is None:
            j = ROOT / "uretim" / "katalog-taslak.jsonl"
            _URETIM = {json.loads(x)["file"]: json.loads(x) for x in j.read_text().splitlines() if x.strip()} if j.exists() else {}
        r = _URETIM.get(p.name, {})
        return {**base, "license": "Yayınevinin üretimi (model: MOSS-SoundEffect v2.0, Apache-2.0)",
                "license_url": "https://huggingface.co/OpenMOSS-Team/MOSS-SoundEffect-v2.0", "page": "",
                "title": r.get("query") or r.get("prompt") or p.stem, "group": "Zeki AI üretimi",
                "text": [r.get("prompt") or p.stem]}
    return {**base, "title": p.stem, "text": [p.stem], "group": src}


def record(args) -> dict | None:
    src, path = args
    p = Path(path)
    try:
        d = describe(src, p)
        m = measure(p)
        tags = tokens(*d.pop("text"))
        cats = L.categorize(tags)
        rel = str(p.relative_to(ROOT))
        tr = []
        for k in cats:
            tr.append(L.CATEGORIES[k]["label"])
        return {"id": hashlib.sha256(rel.encode()).hexdigest()[:16], "src": src, "path": rel, "name": p.name,
                "title": d["title"], "group": d.get("group"), "tags_en": tags[:40], "tags_tr": list(dict.fromkeys(tr)),
                "cats": cats, **m, "flags": flags(m), "license": d["license"], "license_url": d["license_url"],
                "credit": d["credit"], "page": d["page"], "sha256": sha256(p)}
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}", "src": src, "path": str(p)}


def step_katalog(sources: list[str]):
    for src in sources:
        d = ROOT / src
        if not d.exists():
            continue
        out = d / "katalog.jsonl"
        done = set()
        if out.exists():
            for line in out.read_text().splitlines():
                if line.strip():
                    done.add(json.loads(line)["path"])
        # paket tanıtım derlemeleri (Preview.ogg: paketteki seslerin arka arkaya çalındığı kayıt) efekt değildir
        files = [f for f in d.rglob("*") if f.is_file() and f.suffix.lower() in AUDIO_EXT and not mac_junk(str(f))
                 and not f.name.startswith(".") and not re.match(r"(?i)^(preview|prev)[\W_]", f.name + " ")
                 and str(f.relative_to(ROOT)) not in done]
        log(src, "işlenecek", len(files), "(önceden", len(done), ")")
        errs = d / "hatalar.jsonl"
        n = 0
        with ProcessPoolExecutor(max_workers=int(os.environ.get("SFX_WORKERS", "48"))) as ex, out.open("a") as fo:
            for r in ex.map(record, [(src, str(f)) for f in files], chunksize=8):
                if r is None:
                    continue
                if "error" in r:
                    with errs.open("a") as fe:
                        fe.write(json.dumps(r, ensure_ascii=False) + "\n")
                    continue
                fo.write(json.dumps(r, ensure_ascii=False) + "\n")
                n += 1
                if n % 2000 == 0:
                    fo.flush()
                    log(src, n, "/", len(files))
        log(src, "katalog bitti", n)


# ------------------------------------------------------------------ gömme
def _windows(path: str):
    """Dosyadan en çok WINDOWS adet 10 sn'lik 48 kHz tek kanal pencere."""
    import numpy as np
    import soundfile as sf
    import librosa
    p = Path(path)
    try:
        dur, sr, _ = info(p)
        win = 10.0
        count = 1 if dur <= win else min(WINDOWS, math.ceil(dur / win))
        starts = [0.0] if count == 1 else [i * (dur - win) / (count - 1) for i in range(count)]
        out = []
        try:
            with sf.SoundFile(str(p)) as f:
                for s in starts:
                    f.seek(int(s * f.samplerate))
                    x = f.read(int(win * f.samplerate), dtype="float32", always_2d=True).mean(axis=1)
                    if f.samplerate != SR:
                        x = librosa.resample(x, orig_sr=f.samplerate, target_sr=SR, res_type="soxr_hq")
                    out.append(x)
        except Exception:  # noqa: BLE001
            x, fs = decode(p)
            x = x.mean(axis=0)
            if fs != SR:
                x = librosa.resample(x, orig_sr=fs, target_sr=SR, res_type="soxr_hq")
            for s in starts:
                out.append(x[int(s * SR): int((s + win) * SR)])
        res = []
        for x in out:
            x = np.asarray(x, dtype=np.float32)
            if len(x) < SR * win:
                x = np.pad(x, (0, int(SR * win) - len(x)))
            res.append(x[: int(SR * win)])
        return res
    except Exception:  # noqa: BLE001
        return []


def step_gomme():
    import numpy as np
    import torch
    from transformers import ClapModel, ClapProcessor
    rows = []
    for src in L.SOURCES:
        k = ROOT / src / "katalog.jsonl"
        if k.exists():
            rows += [json.loads(x) for x in k.read_text().splitlines() if x.strip()]
    log("katalog satırı", len(rows))
    IDX.mkdir(parents=True, exist_ok=True)
    part = IDX / "gomme.part.npy"
    # artımlı: önceki dizinde ya da yarıda kalmış koşuda gömmesi olan dosya yeniden gömülmez (aynı kimlik = aynı yol)
    known: dict[str, np.ndarray] = {}
    if (IDX / "gomme.npy").exists() and (IDX / "katalog.jsonl").exists():
        old_ids = [json.loads(x)["id"] for x in (IDX / "katalog.jsonl").read_text().splitlines() if x.strip()]
        old = np.load(IDX / "gomme.npy")
        if len(old) == len(old_ids):
            known.update(zip(old_ids, old))
    if part.exists() and (IDX / "gomme.part.ids").exists():
        known.update(zip((IDX / "gomme.part.ids").read_text().split(), np.load(part)))
    dev = os.environ.get("SFX_DEVICE", "cpu")
    if dev.startswith("cuda"):
        torch.cuda.set_per_process_memory_fraction(float(os.environ.get("SFX_GPU_FRACTION", "0.05")))
    torch.set_num_threads(int(os.environ.get("SFX_THREADS", "64")))
    model = ClapModel.from_pretrained(str(MODEL)).to(dev).eval()
    proc = ClapProcessor.from_pretrained(str(MODEL))
    dim = model.config.projection_dim
    emb = np.zeros((len(rows), dim), dtype=np.float16)
    todo = []
    for i, r in enumerate(rows):
        v = known.get(r["id"])
        if v is not None and len(v) == dim:
            emb[i] = v
        else:
            todo.append(i)
    log("gömülecek", len(todo), "hazır", len(rows) - len(todo))
    B = int(os.environ.get("SFX_BATCH", "32"))
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=int(os.environ.get("SFX_WORKERS", "48"))) as ex:
        it = ex.map(_windows, [str(ROOT / rows[i]["path"]) for i in todo], chunksize=4)
        buf, owner = [], []
        n = 0

        def flush():
            if not buf:
                return
            with torch.no_grad():
                feats = proc(audio=buf, sampling_rate=SR, return_tensors="pt")
                feats = {k: v.to(dev) for k, v in feats.items()}
                a = model.get_audio_features(**feats)
                a = a.pooler_output if hasattr(a, "pooler_output") else a
                a = torch.nn.functional.normalize(a.float(), dim=-1).cpu().numpy()
            acc: dict[int, list] = {}
            for v, o in zip(a, owner):
                acc.setdefault(o, []).append(v)
            for o, vs in acc.items():
                m = np.mean(vs, axis=0)
                emb[o] = (m / (np.linalg.norm(m) or 1)).astype(np.float16)
            buf.clear()
            owner.clear()

        for i, wins in zip(todo, it):
            for w in wins:
                buf.append(w)
                owner.append(i)
            if len(buf) >= B:
                flush()
            n += 1
            if n % 5000 == 0:
                flush()
                got = todo[:n]
                np.save(part, emb[got])
                (IDX / "gomme.part.ids").write_text("\n".join(rows[j]["id"] for j in got))
                el = time.time() - t0
                log("gömme", n, "/", len(todo), f"{n / el:.1f} dosya/sn")
        flush()
    np.save(IDX / "gomme.npy", emb)
    with (IDX / "katalog.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    total_b = sum((ROOT / r["path"]).stat().st_size for r in rows if (ROOT / r["path"]).exists())
    meta = {"version": L.VERSION, "built": L.now(), "files": len(rows), "bytes": total_b,
            "hours": round(sum(float(r.get("dur") or 0) for r in rows) / 3600, 1),
            "model": "laion/larger_clap_general", "revision": "ada0c23a36c4e8582805bb38fec3905903f18b41",
            "dim": dim, "windows": WINDOWS, "lufs_sec": LUFS_SEC}
    (IDX / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    for f in (part, IDX / "gomme.part.ids"):
        f.unlink(missing_ok=True)
    log("gömme bitti", meta)
    step_gobek()


# ------------------------------------------------------------------ metin kolu → ONNX
def step_metin():
    import numpy as np
    import torch
    from transformers import ClapModel, ClapProcessor
    model = ClapModel.from_pretrained(str(MODEL)).eval()
    proc = ClapProcessor.from_pretrained(str(MODEL))

    class T(torch.nn.Module):
        """Sabit şekil: tek metin, 77 belirtece dolgulu + maske (LAION CLAP'in metin girdisi)."""

        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, input_ids, attention_mask):
            out = self.m.get_text_features(input_ids=input_ids, attention_mask=attention_mask)
            return out.pooler_output if hasattr(out, "pooler_output") else out

    def tok(t):
        return proc.tokenizer([t], padding="max_length", max_length=77, truncation=True, return_tensors="pt")

    d = IDX / "metin"
    d.mkdir(parents=True, exist_ok=True)
    enc = tok("fire crackling in a fireplace")
    torch.onnx.export(T(model), (enc["input_ids"], enc["attention_mask"]), str(d / "metin.onnx"),
                      input_names=["input_ids", "attention_mask"], output_names=["text_embeds"], opset_version=17,
                      dynamo=False)
    model.eval()          # dışa aktarım modeli eğitim kipinde bırakabiliyor (dropout açık kalır); denetimden önce
    proc.tokenizer.backend_tokenizer.save(str(d / "tokenizer.json"))
    (d / "metin.json").write_text(json.dumps({"max_len": 77, "pad_id": proc.tokenizer.pad_token_id, "fixed": True,
                                               "model": "laion/larger_clap_general"}))
    # eşdeğerlik: torch ile ONNX aynı gömmeyi vermeli (farklı uzunlukta metinler)
    import onnxruntime as ort
    s = ort.InferenceSession(str(d / "metin.onnx"), providers=["CPUExecutionProvider"])
    worst = 1.0
    for t in ["dog", "dog barking", "a strong explosion far away", "wind howling through the trees at night in a storm",
              "ördek vaklıyor", "a duck quacking loudly near a pond while children laugh and play in the park"]:
        e = tok(t)
        with torch.no_grad():
            ref = T(model)(e["input_ids"], e["attention_mask"]).numpy()[0]
            unpadded = proc.tokenizer([t], return_tensors="pt")
            ref2 = T(model)(unpadded["input_ids"], unpadded["attention_mask"]).numpy()[0]
        got = s.run(None, {"input_ids": e["input_ids"].numpy(), "attention_mask": e["attention_mask"].numpy()})[0][0]
        for r in (ref, ref2):
            worst = min(worst, float(r @ got / (np.linalg.norm(r) * np.linalg.norm(got))))
    log("ONNX eşdeğerlik (en küçük kosinüs):", worst)
    if worst < 0.999:
        raise SystemExit("ONNX metin kolu torch ile eşdeğer değil")
    # uçtan uca: stüdyonun kullandığı kodlayıcı (sfx_library._TextEncoder: tokenizer.json + ONNX) torch'la aynı mı
    enc = L._TextEncoder(d)
    worst = 1.0
    for t in ["dog", "a strong explosion far away", "ördek vaklıyor"]:
        e = proc.tokenizer([t], return_tensors="pt")
        with torch.no_grad():
            ref = T(model)(e["input_ids"], e["attention_mask"]).numpy()[0]
        got = enc([t])[0]
        worst = min(worst, float(ref @ got / np.linalg.norm(ref)))
    log("stüdyo kodlayıcısı eşdeğerlik:", worst)
    if worst < 0.999:
        raise SystemExit("stüdyonun metin kodlayıcısı torch ile eşdeğer değil")


def step_gobek():
    """Göbek düzeltmesi (CSLS): her dosyanın, kategori ağacından üretilen genel sorgulara en yüksek GOBEK_K
    benzerliğinin ortalaması → _dizin/gobek.npy. Aramada bu değerin yarısı düşülür: çok sesli/uzun «her şeye
    benzeyen» dosyalar her sorguda öne çıkmaz."""
    import numpy as np
    import torch
    from transformers import ClapModel, ClapProcessor
    model = ClapModel.from_pretrained(str(MODEL)).eval()
    proc = ClapProcessor.from_pretrained(str(MODEL))
    bank = []
    for c in L.CATEGORIES.values():
        for w in c["en"][:4]:
            bank.append(f"the sound of {w}")
    vecs = []
    with torch.no_grad():
        for k in range(0, len(bank), 64):
            e = proc.tokenizer(bank[k:k + 64], padding="max_length", max_length=77, truncation=True, return_tensors="pt")
            o = model.get_text_features(input_ids=e["input_ids"], attention_mask=e["attention_mask"])
            o = o.pooler_output if hasattr(o, "pooler_output") else o
            vecs.append(torch.nn.functional.normalize(o, dim=-1).numpy())
    Q = np.concatenate(vecs).astype(np.float32)
    E = np.load(IDX / "gomme.npy", mmap_mode="r")
    K = 10
    hub = np.zeros(len(E), dtype=np.float32)
    for k in range(0, len(E), 20000):
        S = np.asarray(E[k:k + 20000], dtype=np.float32) @ Q.T
        hub[k:k + 20000] = np.sort(S, axis=1)[:, -K:].mean(axis=1)
    np.save(IDX / "gobek.npy", hub.astype(np.float16))
    log("göbek düzeltmesi", len(bank), "sorgu,", len(E), "dosya; ortalama", float(hub.mean()))


def step_rapor():
    rows = [json.loads(x) for x in (IDX / "katalog.jsonl").read_text().splitlines() if x.strip()]
    cats: dict[str, int] = {}
    srcs: dict[str, dict] = {}
    fl: dict[str, int] = {}
    for r in rows:
        for k in r.get("cats") or []:
            cats[k] = cats.get(k, 0) + 1
        s = srcs.setdefault(r["src"], {"files": 0, "bytes": 0, "sec": 0.0})
        s["files"] += 1
        s["sec"] += float(r.get("dur") or 0)
        try:
            s["bytes"] += (ROOT / r["path"]).stat().st_size
        except OSError:
            pass
        for f in r.get("flags") or []:
            fl[f] = fl.get(f, 0) + 1
    groups = {}
    for g, keys in L.COVERAGE_GROUPS.items():
        groups[g] = {L.CATEGORIES[k]["label"]: cats.get(k, 0) for k in L.CATEGORIES if L.CATEGORIES[k]["group"] in keys}
    print(json.dumps({"files": len(rows), "sources": srcs, "flags": fl, "uncategorized": sum(1 for r in rows if not r.get("cats")),
                      "groups": groups}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else ""
    if step == "ac":
        step_ac()
    elif step == "katalog":
        step_katalog(sys.argv[2:] or list(L.SOURCES))
    elif step == "gomme":
        step_gomme()
    elif step == "gobek":
        step_gobek()
    elif step == "metin":
        step_metin()
    elif step == "rapor":
        step_rapor()
    else:
        print(__doc__)
        sys.exit(2)
