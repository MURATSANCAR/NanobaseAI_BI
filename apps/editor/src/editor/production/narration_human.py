"""İnsan kaydı: yayınevinin seslendirmenine okuttuğu kayıt sayfanın sesi olur (2026-09-28).

Kullanıcı: «seslerimiz çok robotik, bize gerçek insan sesi lazım». Editör bir sayfanın kaydını ya da ardışık birden
çok sayfayı okuyan tek dosyayı yükler. Yapay ses üretilmez: kayıt olduğu gibi sayfanın sesi olur. Kelime zamanları
seslendirme servisinin hizalayıcısıyla çıkarılır (`/v1/audio/narrate` gövdesinde `recording`: üretim yok, yalnız
hizalama); okurken kelime vurgusu, sesli e-kitabın medya kaplaması ve efekt karışımı yapay sesle aynı yoldan çalışır.
Bu bir ses klonu değildir: kayıt yalnız kendi sayfasında çalınır, başka metni okutmak için kullanılmaz.

Hak beyanı zorunlu (ses kütüphanesindeki «Ses yükle» ile aynı kural, voices.py): «RIGHTS_TEXT» onayı, kaydı okuyan
kişinin adı ve izin belgesi (PDF/PNG/JPEG) ya da belge numarası / açıklaması. Kim, ne zaman, hangi belge — yüklemenin
kaydında saklanır; köprü ayrıca denetim kaydı düşer.

Birden çok sayfa: sayfalar okuma sırasıyla ardışık olmalı (okunacak metni olmayan sayfa sayılmaz). Bütün sayfaların
okunuş kelimeleri tek hizalamada kayda yerleştirilir; sayfa sınırı, bir sayfanın son kelimesiyle sonrakinin ilk kelimesi
arasındaki boşluğun ortasıdır. İlk sayfa kaydın başından, son sayfa kaydın sonuna kadar sürer. Her sayfanın sesi özgün
dosyadan kendi aralığıyla kesilir (tek kanal MP3). Hizalayıcının bulamadığı kelimenin zamanı komşularının arasından
harf sayısıyla tahmin edilir (`estimated`), yapay seste olduğu gibi.

Güncellik: sayfa kaydı `source: "human"` taşır ve yalnız metne bakar (`narration.text_hash`): ses seçimi, sözlük ya da
ifade işareti insan kaydını eskitmez. Metin değişince sayfa «güncel değil» görünür ama üzerine yapay ses yazılmaz:
«Seslendir» insan kayıtlı sayfaları atlar; yalnız editör o sayfa için açıkça «yapay sesle değiştir» derse yazılır
(`narration/run` `replace_human`).

İş klasöründe (`<iş>/ses/insan/<yükleme>/`):
    kayit.json   {id, pages, owner, rights{statement, confirmed, document, reference}, source{file, name, bytes,
                  seconds}, by, at, status queued|running|done|fail, error, result{pages: [{page, no, start, end,
                  duration, estimated}], aligned, seconds}}
    kaynak.<uz>  yüklenen özgün dosya (değiştirilmez)       izin.<uz>  izin belgesi (varsa)
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import secrets
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

SUB = "insan"
RIGHTS_TEXT = "Bu ses kaydının ticari kullanım hakkı yayınevimize aittir; kaydı okuyan kişi kullanımına izin vermiştir."
AUDIO_EXT = (".wav", ".mp3", ".m4a", ".ogg", ".flac")
KBPS = 96                                # sayfa sesi: tek kanal MP3 (insan sesi yapay sesin 64 kbit/s'inden iyi kalır)
UID = re.compile(r"^r[0-9a-f]{10}$")


class RecordingError(ValueError):
    """Ekrana giden Türkçe cümleyle reddedilen yükleme ya da işlenemeyen kayıt."""


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def up_dir(d: Path) -> Path:
    from . import narration as N
    return d / N.DIR / SUB


def load(d: Path, uid: str) -> dict:
    if not UID.match(uid or ""):
        raise KeyError(uid)
    p = up_dir(d) / uid / "kayit.json"
    if not p.exists():
        raise KeyError(uid)
    return json.loads(p.read_text())


def _save(d: Path, rec: dict) -> dict:
    p = up_dir(d) / rec["id"] / "kayit.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    tmp.replace(p)
    return rec


def mark(d: Path, uid: str, **fields) -> dict:
    return _save(d, {**load(d, uid), **fields})


def uploads(d: Path) -> list[dict]:
    """Bu kitabın insan kaydı yüklemeleri, en yeni önce."""
    root = up_dir(d)
    rows = []
    for p in root.glob("*/kayit.json") if root.exists() else []:
        try:
            rows.append(json.loads(p.read_text()))
        except ValueError:
            continue
    return sorted(rows, key=lambda r: r.get("at") or "", reverse=True)


def public(rec: dict) -> dict:
    """Ekrana giden biçim (dosya yolları yok)."""
    rights = rec.get("rights") or {}
    src = rec.get("source") or {}
    return {"id": rec["id"], "pages": rec.get("pages") or [], "owner": rec.get("owner"), "by": rec.get("by"),
            "at": rec.get("at"), "status": rec.get("status"), "error": rec.get("error"),
            "file": src.get("name"), "seconds": src.get("seconds"), "document": bool(rights.get("document")),
            "reference": rights.get("reference"), "result": rec.get("result")}


# ------------------------------------------------------------------ ses aracı
def _ff(args: list[str], timeout: int = 3600) -> subprocess.CompletedProcess:
    return subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-y", *args], capture_output=True,
                          timeout=timeout)


def seconds_of(path: Path) -> float | None:
    """Ses dosyasının süresi (sn); çözülemiyorsa None."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                            "default=noprint_wrappers=1:nokey=1", str(path)], capture_output=True, text=True, timeout=300)
        v = float(r.stdout.strip().splitlines()[0])
    except (subprocess.SubprocessError, OSError, ValueError, IndexError):
        return None
    return v if v > 0 else None


# ------------------------------------------------------------------ yükleme
def _readable(d: Path) -> tuple[list[dict], list[str]]:
    from . import narration as N
    rows = N.status(d)
    return rows, [r["id"] for r in rows if r["status"] != "empty"]


def stage(d: Path, pages: list[str], audio: bytes, name: str, *, owner: str, confirm: bool, by: str,
          reference: str = "", document: tuple[bytes, str] | None = None) -> dict:
    """Yüklemeyi denetler ve iş klasörüne yazar (kuyruğa `queued`). İşlenmesi `apply` ile (Temporal HumanRecording).
    `pages`: kaydın okuduğu sayfalar (okuma sırasıyla ardışık); `document`: (bayt, dosya adı)."""
    from . import voices
    owner, reference = str(owner or "").strip(), str(reference or "").strip()
    if not confirm:
        raise RecordingError(f"Hak beyanı onaylanmadan kayıt yüklenemez: «{RIGHTS_TEXT}»")
    if not owner:
        raise RecordingError("Kaydı okuyan kişinin adını yazın.")
    if not document and not reference:
        raise RecordingError("İzin belgesini yükleyin ya da belge numarasını / açıklamasını yazın.")
    ext = Path(name or "").suffix.lower()
    if ext not in AUDIO_EXT:
        raise RecordingError("Yalnız wav, mp3, m4a, ogg ya da flac ses dosyası yüklenebilir.")
    if not audio:
        raise RecordingError("Ses dosyası boş.")
    try:
        doc_kind = voices._doc_kind(document[0]) if document else None
    except voices.VoiceError as e:
        raise RecordingError(str(e)) from None
    want = list(dict.fromkeys(str(p) for p in pages or []))
    if not want:
        raise RecordingError("Kaydın hangi sayfaları okuduğunu seçin.")
    rows, readable = _readable(d)
    known = {r["id"]: r for r in rows}
    for p in want:
        if p not in known:
            raise KeyError(p)
        if p not in readable:
            raise RecordingError(f"Sayfa {known[p]['no']}'de okunacak metin yok.")
    idx = sorted(readable.index(p) for p in want)
    if idx != list(range(idx[0], idx[0] + len(idx))):
        raise RecordingError("Tek dosya yalnız ardışık sayfaları kapsayabilir (okuma sırasıyla, arada sayfa atlanmadan).")
    ordered = [readable[i] for i in idx]

    uid = "r" + secrets.token_hex(5)
    ud = up_dir(d) / uid
    ud.mkdir(parents=True)
    src = ud / f"kaynak{ext}"
    src.write_bytes(audio)
    sec = seconds_of(src)
    if not sec:
        shutil.rmtree(ud, ignore_errors=True)
        raise RecordingError("Ses dosyası okunamadı; wav, mp3, m4a, ogg ya da flac yükleyin.")
    doc = None
    if document:
        (ud / f"izin{doc_kind[1]}").write_bytes(document[0])
        doc = {"file": f"izin{doc_kind[1]}", "name": Path(document[1] or "izin").name[:200], "mime": doc_kind[0],
               "bytes": len(document[0])}
    rec = {"id": uid, "pages": ordered, "owner": owner[:120],
           "rights": {"statement": RIGHTS_TEXT, "confirmed": True, "document": doc, "reference": reference[:300] or None},
           "source": {"file": src.name, "name": Path(name).name[:200], "bytes": len(audio), "seconds": round(sec, 2)},
           "by": by, "at": _now(), "status": "queued", "error": None, "result": None}
    return _save(d, rec)


# ------------------------------------------------------------------ hizalama ve sayfalara bölme
def cuts(filled: list[tuple[float, float]], first: list[int], last: list[int], total: float) -> list[float]:
    """Sayfa sınırları (sn): ilk sayfa 0'dan, son sayfa `total`'a; aradakiler önceki sayfanın son kelimesinin sonu ile
    sonrakinin ilk kelimesinin başı arasındaki boşluğun ortası. `first`/`last`: sayfanın ilk/son kelimesinin sırası."""
    out = [0.0]
    for pi in range(1, len(first)):
        e = filled[last[pi - 1]][1]
        s = max(filled[first[pi]][0], e)
        out.append(round((e + s) / 2, 3))
    out.append(round(max(total, out[-1]), 3))
    return out


def page_segments(plist_idx: list[list[int]], got: list[dict | None], filled: list[tuple[float, float]],
                  a: float, b: float) -> list[dict]:
    """Bir sayfanın parçaları için servis biçiminde kayıtlar (`narration.word_times` girdisi), zamanlar sayfa sesinin
    başından. `plist_idx`: parça başına düz kelime listesindeki sıralar. Parçanın sınırı önceki parçanın son kelimesinin
    sonundan sonraki parçanın ilk kelimesinin başına kadardır (bulunamayan kelimeler bu aralıkta tahmin edilir)."""
    segs = []
    for qi, xs in enumerate(plist_idx):
        lo = filled[plist_idx[qi - 1][-1]][1] if qi else a
        hi = filled[plist_idx[qi + 1][0]][0] if qi + 1 < len(plist_idx) else b
        hi = max(hi, lo)
        segs.append({"start": round(lo - a, 3), "end": round(hi - a, 3), "aligned": True,
                     "words": [None if got[x] is None else
                               {"start": round(min(max(float(got[x]["start"]), a), b) - a, 3),
                                "end": round(min(max(float(got[x]["end"]), a), b) - a, 3)} for x in xs]})
    return segs


async def apply(d: Path, uid: str, by: str, progress=None) -> dict:
    """Yüklemeyi işler: kelimeleri hizalar, sayfalara böler, her sayfanın sesini ve kaydını yazar, efekt karışımını
    yeniler. `progress(i, n)`: yazılan sayfa sayısı. Aynı yükleme yeniden işlenebilir (sonuç aynı)."""
    from . import narration as N
    from . import plan as plan_mod
    rec = load(d, uid)
    t0 = time.time()
    pl = plan_mod.load(d)
    if pl is None:
        raise plan_mod.NoPlan(d.name)
    mark(d, uid, status="running", error=None)
    cfg, lex = N.settings_of(d), N.lexicon(d)
    items = []
    for pid in rec["pages"]:
        try:
            pg = plan_mod._page(pl, pid)
        except KeyError:
            raise RecordingError("Kaydın sayfalarından biri sayfa düzeninden silindi; kaydı yeniden yükleyin.") from None
        units, plist, h = N.page_input(d, pg, cfg, lex)
        if not plist:
            raise RecordingError(f"Sayfa {plan_mod.page_no(pl, pid)}'de okunacak metin kalmadı; kaydı yeniden yükleyin.")
        items.append((pid, units, plist, h))

    flat: list[str] = []
    idx: list[list[list[int]]] = []          # sayfa → parça → düz kelime sıraları
    for _pid, units, plist, _h in items:
        per = []
        for p in plist:
            xs = []
            for k in p.words:
                for s in units[p.unit].words[k].say:
                    xs.append(len(flat))
                    flat.append(s)
            per.append(xs)
        idx.append(per)

    ud = up_dir(d) / uid
    src = ud / rec["source"]["file"]
    with tempfile.TemporaryDirectory() as tmp:
        low = Path(tmp) / "hiza.flac"         # hizalayıcı 16 kHz tek kanalla çalışır: kayıpsız, küçük gövde
        r = await asyncio.to_thread(_ff, ["-i", str(src), "-ac", "1", "-ar", "16000", "-c:a", "flac", str(low)])
        if r.returncode != 0 or not low.exists():
            raise RecordingError("Ses dosyası çözülemedi; kaydı wav ya da mp3 olarak yeniden yükleyin.")
        data = low.read_bytes()
    import httpx
    try:
        out = await N._call({"recording": base64.b64encode(data).decode(), "words": flat, "align": True,
                             "format": "none"})
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (400, 422):
            raise RecordingError("Ses servisi bu kaydı hizalayamadı; servis insan kaydını henüz desteklemiyor olabilir "
                                 "ya da dosya bozuk.") from None
        raise
    total = float(out.get("duration") or 0) or float(rec["source"].get("seconds") or 0)
    got = list(out.get("words") or [])[:len(flat)]
    got += [None] * (len(flat) - len(got))
    aligned = sum(1 for w in got if w)
    if flat and not aligned and out.get("aligned", True):
        raise RecordingError("Kayıt sayfaların metniyle eşleşmedi (hiçbir kelime bulunamadı). Doğru dosyayı ve doğru "
                             "sayfaları seçtiğinizi denetleyin.")
    known = [(float(w["start"]), float(w["end"])) if w else None for w in got]
    filled, _ = N.fill_times(known, [len(s) for s in flat], 0.0, total)
    bounds = cuts(filled, [per[0][0] for per in idx], [per[-1][-1] for per in idx], total)

    sd = N.ses_dir(d) / "sayfa"
    result = []
    for pi, (pid, units, plist, h) in enumerate(items):
        a, b = bounds[pi], bounds[pi + 1]
        segs = page_segments(idx[pi], got, filled, a, b)
        blocks = N.word_times(units, plist, segs)
        for bl in blocks:
            bl["voice"] = ""                    # okuyan insan; yapay ses kimliği yok (ekran sesin adını yazmaz)
        est = any(w.get("estimated") for bl in blocks for w in bl["words"])
        tmp_mp3 = sd / f"{pid}.mp3.tmp"
        r = await asyncio.to_thread(_ff, ["-ss", f"{a:.3f}", "-i", str(src), "-t", f"{max(0.05, b - a):.3f}",
                                          "-ac", "1", "-c:a", "libmp3lame", "-b:a", f"{KBPS}k", "-f", "mp3",
                                          str(tmp_mp3)])
        if r.returncode != 0 or not tmp_mp3.exists():
            tmp_mp3.unlink(missing_ok=True)
            raise RecordingError("Sayfanın sesi kayıttan kesilemedi.")
        dur = await asyncio.to_thread(seconds_of, tmp_mp3) or round(b - a, 3)
        page_rec = {"version": N.VERSION, "page": pid, "no": plan_mod.page_no(pl, pid), "hash": h,
                    "text_hash": N.text_hash(units), "source": "human",
                    "human": {"upload": uid, "owner": rec["owner"], "file": rec["source"]["name"],
                              "range": [a, b]},
                    "audio": f"{N.DIR}/sayfa/{pid}.mp3", "format": "mp3", "duration": round(dur, 3),
                    "estimated": est, "blocks": blocks, "by": by, "at": _now(),
                    "seconds": round(time.time() - t0, 1), "voices": []}
        tmp_mp3.replace(sd / f"{pid}.mp3")
        N._write(sd / f"{pid}.json", page_rec)
        await N._efekt_kancasi(d, pid, by)
        result.append({"page": pid, "no": page_rec["no"], "start": a, "end": b, "duration": page_rec["duration"],
                       "estimated": est})
        if progress:
            progress(pi + 1, len(items))
    res = {"pages": result, "aligned": [aligned, len(flat)], "seconds": round(time.time() - t0, 1)}
    mark(d, uid, status="done", error=None, result=res, finished=_now())
    return res
