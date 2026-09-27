"""Ses kütüphanesi: yayınevinin yüklediği, kullanım hakkı belgeli referans sesler (2026-09-27).

Tarifle tasarlanan sesler (`narration.VOICES`) hiçbir gerçek kişinin kaydına dayanmaz. Yayınevi kendi seslendirmeninin
sesiyle okutmak isterse kaydı buradan yükler; yükleme **hak beyanı olmadan kabul edilmez**: «Bu sesin ticari kullanım
hakkı yayınevimize aittir» onayı, sesin sahibinin adı ve izin belgesi (PDF/görüntü dosyası ya da belge numarası /
açıklaması). Kim, ne zaman, hangi belge — ses kaydının yanında saklanır (köprü ayrıca denetim kaydı düşer).

Kayıt: 30–60 sn konuşma (sessizlikler kırpıldıktan sonra). Tarayıcı dosyayı (wav/mp3/m4a/ogg) çözüp tek kanal
16 bit WAV'a çevirir; burada okunur, ölçülür ve normalleştirilir: tek kanal, en az 16 kHz, baş/son sessizlik kırpılır,
konuşma seviyesi eşitlenir. Çok kısa/uzun, gürültülü (konuşma ile arka plan farkı < 18 dB), patlayan (kırpılmış örnek
payı > %0,2) ya da konuşması az kayıt açık Türkçe hatayla reddedilir. Üretimde referans olarak kaydın 8–15 sn'lik ilk
parçası (bir duraklamada biter) kullanılır: seslendirme modeli referanslı üretim yoluyla (yalnız ses, metinsiz) o
sesle okur.

Klasör (yayınevi düzeyinde, `<storage>/production/_ses/kutuphane/<ses>/`):
    kayit.json   {id, label, group, note, owner, rights{statement, confirmed, document, reference}, by, at, stats,
                  removed{by, at} | null}
    ses.wav      normalleştirilmiş kaydın tamamı       ref.wav   üretimde kullanılan parça
    kaynak.<uz>  yüklenen özgün dosya (varsa)         izin.<uz> izin belgesi (varsa)
Kaldırılan ses yeni üretimde kullanılmaz (seçilemez, seslendirme reddedilir); dosyaları ve eski sayfa sesleri durur.
"""

from __future__ import annotations

import base64
import io
import json
import re
import secrets
import time
import wave
from pathlib import Path

import numpy as np

LIB = "kutuphane"
STAMP = ".surum"
RIGHTS_TEXT = "Bu sesin ticari kullanım hakkı yayınevimize aittir."
MIN_SEC, MAX_SEC = 30.0, 60.0            # kullanıcı isteği: 30–60 sn'lik kayıt
REF_MIN, REF_MAX = 8.0, 15.0             # üretimde referans parçası
MIN_SR = 16000
SNR_MIN_DB = 18.0
CLIP_MAX = 0.002
SPEECH_MIN = 0.45                        # kırpılmış kaydın en az bu payı konuşma olmalı
TARGET_RMS = 0.08                        # konuşma karelerinin hedef seviyesi (~ -22 dBFS)
DOC_KINDS = ((b"%PDF", "application/pdf", ".pdf"), (b"\x89PNG", "image/png", ".png"), (b"\xff\xd8\xff", "image/jpeg", ".jpg"))
AUDIO_EXT = (".wav", ".mp3", ".m4a", ".ogg")
_cache: dict = {"stamp": None, "rows": []}


class VoiceError(ValueError):
    """Ekrana giden Türkçe cümleyle reddedilen yükleme."""


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def lib_dir() -> Path:
    from . import narration
    return narration._root() / LIB


def _touch() -> None:
    d = lib_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / STAMP).write_text(str(time.time_ns()))


def entries(include_removed: bool = False) -> list[dict]:
    """Kütüphanedeki yüklenmiş sesler (eklenme sırasıyla). Liste diske her yazımda tazelenir (damga dosyası)."""
    d = lib_dir()
    st = d / STAMP
    stamp = st.read_text() if st.exists() else None
    if stamp is None or stamp != _cache["stamp"] or _cache.get("dir") != str(d):
        rows = []
        for p in sorted(d.glob("*/kayit.json")) if d.exists() else []:
            try:
                rows.append(json.loads(p.read_text()))
            except ValueError:
                continue
        rows.sort(key=lambda r: r.get("at") or "")
        _cache.update(stamp=stamp, rows=rows, dir=str(d))
    return [r for r in _cache["rows"] if include_removed or not r.get("removed")]


def get(vid: str) -> dict | None:
    return next((r for r in entries(True) if r["id"] == vid), None)


def active_ids() -> set[str]:
    return {r["id"] for r in entries()}


def as_voice(r: dict) -> dict:
    """Ekrandaki ses listesine giden biçim (tarifli seslerle aynı alanlar + yükleme bilgisi)."""
    rights = r.get("rights") or {}
    return {"id": r["id"], "label": r["label"], "note": r.get("note") or "", "group": r["group"], "uploaded": True,
            "owner": r.get("owner"), "by": r.get("by"), "at": r.get("at"), "document": bool(rights.get("document")),
            "reference": rights.get("reference"), "duration": (r.get("stats") or {}).get("duration"),
            "removed": r.get("removed")}


# ------------------------------------------------------------------ ses: oku, ölç, normalleştir
def read_wav(data: bytes) -> tuple[np.ndarray, int]:
    try:
        w = wave.open(io.BytesIO(data))
        sr, ch, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
    except (wave.Error, EOFError):
        raise VoiceError("Ses dosyası okunamadı; wav, mp3, m4a ya da ogg yükleyin.") from None
    if width == 1:
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128) / 128
    elif width == 2:
        x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768
    elif width == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        x = (np.where(v >= 1 << 23, v - (1 << 24), v)).astype(np.float32) / (1 << 23)
    elif width == 4:
        x = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2**31
    else:
        raise VoiceError("Ses dosyasının örnek biçimi desteklenmiyor.")
    if ch > 1:
        x = x[: len(x) // ch * ch].reshape(-1, ch).mean(axis=1)
    return x, sr


def _frames(x: np.ndarray, sr: int, ms: int = 30) -> np.ndarray:
    n = max(1, int(sr * ms / 1000))
    k = len(x) // n
    return np.sqrt((x[: k * n].reshape(k, n) ** 2).mean(axis=1) + 1e-12) if k else np.zeros(0)


def analyze(x: np.ndarray, sr: int) -> dict:
    """Kare (30 ms) enerjileri: arka plan (%10), konuşma (%90), konuşma karesi eşiği, baş/son kırpma sınırları."""
    rms = _frames(x, sr)
    if len(rms) < 10:
        return {"duration": len(x) / sr, "trimmed": 0.0, "snr_db": 0.0, "speech_share": 0.0, "clip_share": 0.0,
                "start": 0, "end": len(x)}
    noise, speech = float(np.percentile(rms, 10)), float(np.percentile(rms, 90))
    thr = max(noise * 2.5, speech * 0.08, 0.002)
    voiced = rms > thr
    idx = np.where(voiced)[0]
    n = int(sr * 0.03)
    pad = int(sr * 0.15)
    start = max(0, int(idx[0]) * n - pad) if len(idx) else 0
    end = min(len(x), (int(idx[-1]) + 1) * n + pad) if len(idx) else len(x)
    inner = voiced[start // n:end // n] if end > start else voiced
    return {"duration": round(len(x) / sr, 2), "trimmed": round((end - start) / sr, 2),
            "snr_db": round(20 * np.log10(speech / max(noise, 1e-5)), 1),
            "speech_share": round(float(inner.mean()) if len(inner) else 0.0, 3),
            "clip_share": round(float((np.abs(x) >= 0.999).mean()), 5), "start": start, "end": end,
            "speech_rms": round(float(np.sqrt((rms[voiced] ** 2).mean())) if voiced.any() else 0.0, 4)}


def _pcm(x: np.ndarray, sr: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def prepare(data: bytes) -> tuple[bytes, bytes, dict]:
    """Kaydı denetler ve normalleştirir. Dönen: (bütün kayıt WAV, referans parçası WAV, ölçüler)."""
    x, sr = read_wav(data)
    if sr < MIN_SR:
        raise VoiceError(f"Kaydın örnekleme hızı düşük ({sr} Hz; en az {MIN_SR} Hz). Telefon görüşmesi kaydı "
                         "kullanılamaz; stüdyo ya da telefon ses kaydedicisiyle yeniden kaydedin.")
    a = analyze(x, sr)
    if a["clip_share"] > CLIP_MAX:
        raise VoiceError("Kayıt patlıyor (ses seviyesi çok yüksek, dalga kırpılmış). Mikrofona biraz daha uzaktan ya "
                         "da daha düşük kazançla yeniden kaydedin.")
    if a["snr_db"] < SNR_MIN_DB:
        raise VoiceError(f"Kayıt gürültülü: konuşma ile arka plan arasındaki fark {a['snr_db']:.0f} dB (en az "
                         f"{SNR_MIN_DB:.0f} dB). Sessiz bir odada, mikrofona yakın yeniden kaydedin.")
    if a["trimmed"] < MIN_SEC:
        raise VoiceError(f"Kayıt çok kısa: sessizlikler çıkınca {a['trimmed']:.0f} sn konuşma kaldı (en az "
                         f"{MIN_SEC:.0f} sn). 30–60 sn'lik bir kayıt yükleyin.")
    if a["trimmed"] > MAX_SEC:
        raise VoiceError(f"Kayıt çok uzun: {a['trimmed']:.0f} sn (en çok {MAX_SEC:.0f} sn). 30–60 sn'lik bir "
                         "bölüm yükleyin.")
    if a["speech_share"] < SPEECH_MIN:
        raise VoiceError(f"Kayıtta konuşma az (sürenin %{a['speech_share'] * 100:.0f}'i). Uzun sessizlik ya da müzik "
                         "olmadan, düz okuma kaydı yükleyin.")
    y = x[a["start"]:a["end"]]
    peak = float(np.abs(y).max()) or 1.0
    gain = min(TARGET_RMS / max(a["speech_rms"], 1e-4), 0.89 / peak)
    y = (y * gain).astype(np.float32)
    # Referans parçası: baştan REF_MIN–REF_MAX arası, bir duraklamada (en sessiz karede) biter.
    rms = _frames(y, sr)
    n = int(sr * 0.03)
    lo, hi = int(REF_MIN / 0.03), min(len(rms), int(REF_MAX / 0.03))
    cut = (lo + int(np.argmin(rms[lo:hi]))) * n if hi > lo else len(y)
    ref = y[:cut]
    stats = {k: a[k] for k in ("duration", "trimmed", "snr_db", "speech_share", "clip_share")}
    stats.update(sample_rate=sr, gain_db=round(20 * np.log10(gain), 1), ref_seconds=round(len(ref) / sr, 2))
    return _pcm(y, sr), _pcm(ref, sr), stats


# ------------------------------------------------------------------ kütüphane
def _doc_kind(data: bytes) -> tuple[str, str]:
    for magic, mime, ext in DOC_KINDS:
        if data.startswith(magic):
            return mime, ext
    raise VoiceError("İzin belgesi PDF, PNG ya da JPEG olmalı.")


def add(audio: bytes, *, label: str, group: str, note: str, owner: str, confirm: bool, by: str,
        document: tuple[bytes, str] | None = None, reference: str = "", original: tuple[bytes, str] | None = None
        ) -> dict:
    """Yeni ses. `audio`: tarayıcının çevirdiği WAV; `document`: (bayt, dosya adı); `original`: yüklenen özgün dosya."""
    from .narration import GROUPS
    label, owner, note, reference = (str(v or "").strip() for v in (label, owner, note, reference))
    if not confirm:
        raise VoiceError(f"Hak beyanı onaylanmadan ses yüklenemez: «{RIGHTS_TEXT}»")
    if not owner:
        raise VoiceError("Sesin sahibinin adını yazın.")
    if not document and not reference:
        raise VoiceError("İzin belgesini yükleyin ya da belge numarasını / açıklamasını yazın.")
    if not label:
        raise VoiceError("Sese bir ad verin.")
    if group not in GROUPS:
        raise VoiceError("Ses grubu geçersiz.")
    doc_kind = _doc_kind(document[0]) if document else None
    if original and Path(original[1]).suffix.lower() not in AUDIO_EXT:
        raise VoiceError("Yalnız wav, mp3, m4a ya da ogg ses dosyası yüklenebilir.")
    full, ref, stats = prepare(audio)
    vid = f"yuklenen-{secrets.token_hex(4)}"
    d = lib_dir() / vid
    d.mkdir(parents=True)
    (d / "ses.wav").write_bytes(full)
    (d / "ref.wav").write_bytes(ref)
    doc = None
    if document:
        (d / f"izin{doc_kind[1]}").write_bytes(document[0])
        doc = {"file": f"izin{doc_kind[1]}", "name": Path(document[1] or "izin").name[:200], "mime": doc_kind[0],
               "bytes": len(document[0])}
    src = None
    if original:
        ext = Path(original[1]).suffix.lower()
        (d / f"kaynak{ext}").write_bytes(original[0])
        src = {"file": f"kaynak{ext}", "name": Path(original[1]).name[:200], "bytes": len(original[0])}
    rec = {"id": vid, "label": label[:80], "group": group, "note": note[:120], "owner": owner[:120],
           "rights": {"statement": RIGHTS_TEXT, "confirmed": True, "document": doc, "reference": reference[:300] or None},
           "source": src, "by": by, "at": _now(), "stats": stats, "removed": None}
    (d / "kayit.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    _touch()
    return rec


def remove(vid: str, by: str) -> dict:
    rec = get(vid)
    if rec is None:
        raise KeyError(vid)
    if not rec.get("removed"):
        rec["removed"] = {"by": by, "at": _now()}
        (lib_dir() / vid / "kayit.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1))
        _touch()
    return rec


def document(vid: str) -> tuple[Path, str, str]:
    rec = get(vid)
    doc = ((rec or {}).get("rights") or {}).get("document")
    if not doc:
        raise FileNotFoundError(vid)
    return lib_dir() / vid / doc["file"], doc["mime"], doc["name"]


def ref_audio(vid: str) -> str:
    return base64.b64encode((lib_dir() / vid / "ref.wav").read_bytes()).decode()


VID = re.compile(r"^yuklenen-[0-9a-f]{8}$")
