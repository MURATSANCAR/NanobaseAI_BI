"""Ses çözme ve parçalara bölme. Hepsi bellekte; hiçbir ara dosya yazılmaz.

* WAV (PCM 16 bit) doğrudan okunur — portal tarayıcıda kaydı 16 kHz tek kanal WAV'a çevirip gönderir.
* Başka biçim (m4a, ogg, webm, mp3…) ffmpeg'e stdin'den verilir, stdout'tan 16 kHz float okunur.
* Uzun kayıt sessiz anlardan ≤ `max_s` saniyelik parçalara bölünür; yalnız sessizlikten oluşan parça modele
  gitmez (model sessizlikte uydurma altyazı cümlesi yazabiliyor).
"""
from __future__ import annotations

import io
import subprocess
import wave
from dataclasses import dataclass

import numpy as np

SR = 16000


class AudioError(ValueError):
    """Okunamayan ya da boş ses: çağırana 400/413 olarak döner."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _resample(a: np.ndarray, sr: int) -> np.ndarray:
    if sr == SR or a.size == 0:
        return a.astype(np.float32, copy=False)
    n = int(round(a.size * SR / sr))
    x_old = np.linspace(0.0, 1.0, num=a.size, endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n, endpoint=False)
    return np.interp(x_new, x_old, a).astype(np.float32)


def read_wav(data: bytes) -> np.ndarray | None:
    """PCM 16 bit WAV ise 16 kHz tek kanal float döner; değilse None (ffmpeg yoluna gidilir)."""
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return None
    try:
        with wave.open(io.BytesIO(data)) as w:
            if w.getsampwidth() != 2:
                return None
            ch, sr = w.getnchannels(), w.getframerate()
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
    except (wave.Error, EOFError):
        return None
    if ch > 1:
        pcm = pcm[: pcm.size - pcm.size % ch].reshape(-1, ch).mean(axis=1)
    return _resample(pcm, sr)


def wav_seconds(data: bytes) -> float | None:
    """WAV başlığından süre (sn); WAV değilse None. Köprü de aynı hesabı yapar (sınır ses çözülmeden denetlenir)."""
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return None
    try:
        with wave.open(io.BytesIO(data)) as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except (wave.Error, EOFError):
        return None


def decode(data: bytes, *, ffmpeg: str = "ffmpeg", timeout: float = 120.0) -> np.ndarray:
    if not data:
        raise AudioError("Ses boş geldi.")
    a = read_wav(data)
    if a is None:
        try:
            p = subprocess.run(
                [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
                 "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "pipe:1"],
                input=data, capture_output=True, timeout=timeout, check=False)
        except FileNotFoundError as e:  # pragma: no cover — imajda ffmpeg var
            raise AudioError("Ses çözücü bulunamadı.", 500) from e
        except subprocess.TimeoutExpired as e:
            raise AudioError("Ses çözülemedi (süre aşıldı).") from e
        if p.returncode != 0 or not p.stdout:
            raise AudioError("Ses dosyası okunamadı; desteklenen bir kayıt biçimi gönderin.")
        a = np.frombuffer(p.stdout, dtype="<f4").astype(np.float32)
    if a.size < SR // 4:
        raise AudioError("Kayıt çok kısa.")
    return a


@dataclass
class Chunk:
    start: float
    end: float
    audio: np.ndarray
    silent: bool


def _frame_rms(a: np.ndarray, hop: int) -> np.ndarray:
    n = a.size // hop
    if n == 0:
        return np.array([float(np.sqrt(np.mean(a**2)))]) if a.size else np.zeros(1)
    f = a[: n * hop].reshape(n, hop)
    return np.sqrt(np.mean(f * f, axis=1) + 1e-12)


def split(a: np.ndarray, *, max_s: float = 28.0, min_s: float = 8.0, frame_ms: int = 20,
          silence_abs: float = 0.0015, silence_rel: float = 2.0, always_speech: float = 0.01) -> list[Chunk]:
    """Kaydı konuşma aralarından böler. Her parça ≤ max_s; kesim, [min_s, max_s] penceresindeki en sessiz
    300 ms'lik noktadır.

    `silent`: parçanın yüksek sesli karelerinin (95. yüzdelik) seviyesi ya mutlak sessizlikte (−56 dBFS altı) ya da
    kaydın kendi gürültü tabanının (20. yüzdelik) `silence_rel` katının altında. Sabit bir «konuşma eşiği» kullanılmaz:
    FLEURS'ta −50 dBFS civarı kısık okunmuş gerçek cümleler (RMS ≈ 0,003) sabit 0,008 eşiğiyle atılıyordu (2026-09-28).
    `always_speech` (−40 dBFS) üstündeki parça her zaman modele gider: duraksamasız kayıtta ya da düşük SNR'li
    kalabalıkta taban konuşmanın kendisi olabilir, göreli kural onu atmasın."""
    hop = SR * frame_ms // 1000
    rms = _frame_rms(a, hop)
    k = max(1, 300 // frame_ms)
    smooth = np.convolve(rms, np.ones(k) / k, mode="same")
    floor = float(np.percentile(rms, 20)) if rms.size else 0.0
    quiet = min(always_speech, max(silence_abs, floor * silence_rel))
    fps = 1000 // frame_ms
    total = rms.size
    chunks: list[Chunk] = []
    s = 0
    max_f, min_f = int(max_s * fps), int(min_s * fps)
    while s < total:
        if total - s <= max_f:
            e = total
        else:
            lo, hi = s + min_f, min(total, s + max_f)
            e = lo + int(np.argmin(smooth[lo:hi]))
            e = max(e, s + 1)
        seg = a[s * hop: (e * hop if e < total else a.size)]
        loud = float(np.percentile(rms[s:e], 95)) if e > s else 0.0
        chunks.append(Chunk(round(s / fps, 2), round(min(e, total) / fps if e < total else a.size / SR, 2), seg, loud < quiet))
        s = e
    return chunks
