"""Sesli not GPU servisi (modelsiz): bölme, çözme, metin süzgeci, anahtar. Servisin imajında koşar (numpy, ffmpeg)."""
from __future__ import annotations

import io
import sys
import wave
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from voice_note_service import app as SA  # noqa: E402
from voice_note_service import audio as SAu  # noqa: E402
from voice_note_service import text as ST  # noqa: E402


def _wav(seconds: float, rate: int = 16000, tone: float = 0.0) -> bytes:
    n = int(seconds * rate)
    frames = struct.pack(f"<{n}h", *(int(tone * math.sin(2 * math.pi * 220 * i / rate) * 32767) for i in range(n)))
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)
    return b.getvalue()


# ------------------------------------------------------------------ GPU servisi (modelsiz)


def test_service_splits_long_audio_at_quiet_points_and_marks_silence():
    sr = SAu.SR
    speech = 0.3 * np.sin(2 * np.pi * 200 * np.arange(sr * 20) / sr).astype(np.float32)
    quiet = np.zeros(sr, dtype=np.float32)
    a = np.concatenate([speech, quiet, speech, quiet, np.zeros(sr * 30, dtype=np.float32)])
    chunks = SAu.split(a, max_s=28, min_s=8)
    assert all(c.end - c.start <= 28.01 for c in chunks)
    assert chunks[0].end == pytest.approx(20.5, abs=0.6)  # sessiz aradan kesildi
    assert chunks[-1].silent and not chunks[0].silent
    assert sum(c.audio.size for c in chunks) == a.size  # ses kaybolmaz


def test_service_keeps_quiet_speech_and_pauseless_speech():
    """Kısık okunan cümle (−50 dBFS) ve hiç duraksamayan kayıt sessiz sayılıp atılmaz; yalnız taban gürültüsü atılır."""
    sr = SAu.SR
    rng = np.random.default_rng(1)
    speech = (0.004 * np.sin(2 * np.pi * 180 * np.arange(sr * 5) / sr) * (1 + np.sin(np.arange(sr * 5) / 400))).astype(np.float32)
    gaps = np.zeros(sr * 12, dtype=np.float32)
    quiet = SAu.split(np.concatenate([gaps, speech, gaps]), max_s=28, min_s=8)
    assert any(not c.silent for c in quiet)
    loud_only = SAu.split((0.2 * np.sin(2 * np.pi * 200 * np.arange(sr * 3) / sr)).astype(np.float32))
    assert [c.silent for c in loud_only] == [False]
    room = (0.004 * rng.standard_normal(sr * 6)).astype(np.float32)  # telefonun yükselttiği oda gürültüsü, konuşma yok
    assert all(c.silent for c in SAu.split(room))


def test_service_reads_wav_without_ffmpeg():
    a = SAu.decode(_wav(1.0, rate=48000, tone=0.5))
    assert a.size == pytest.approx(16000, abs=2) and a.dtype == np.float32
    with pytest.raises(SAu.AudioError):
        SAu.decode(b"")


def test_service_drops_phantom_subtitles_and_loops():
    assert ST.clean("Altyazı M.K.") == ""
    assert ST.clean("İzlediğiniz için teşekkür ederim.") == ""
    assert ST.clean("Altyazı hazırlığı için kitapları istedi") == "Altyazı hazırlığı için kitapları istedi"
    looped = "kitapları gönderecek " * 12
    assert ST.clean(looped) == "kitapları gönderecek"
    assert ST.clean("evet evet evet tamam") == "evet evet evet tamam"
    assert ST.clean("sipariş verecek " + "tamam " * 9 + "dedi") == "sipariş verecek tamam dedi"


class _FakeEngine:
    def __init__(self):
        self.calls = []

    def transcribe(self, arrs, ctx=""):
        self.calls.append((len(arrs), ctx))
        return ["kalanı on beş ekimde ödeyecek"] * len(arrs)

    def memory(self):
        return {}


def test_service_requires_token_and_transcribes(monkeypatch):
    monkeypatch.setenv("VOICE_TOKEN", "sir")
    monkeypatch.setenv("VOICE_MAX_SECONDS", "60")
    eng = _FakeEngine()
    with TestClient(SA.create_app(eng, load=False)) as c:
        assert c.get("/health").json()["ready"] is True
        assert c.post("/v1/transcribe", content=_wav(2, tone=0.3)).status_code == 401
        assert c.post("/v1/transcribe", content=_wav(2, tone=0.3), headers={"X-Voice-Token": "yanlis"}).status_code == 401
        r = c.post("/v1/transcribe?context=Moda%20Kitabevi", content=_wav(2, tone=0.3), headers={"X-Voice-Token": "sir"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["text"] == "kalanı on beş ekimde ödeyecek" and j["segments"][0]["start"] == 0
        assert eng.calls[-1] == (1, "Moda Kitabevi")
        # sessiz kayıt modele gitmez
        n = len(eng.calls)
        assert c.post("/v1/transcribe", content=_wav(3), headers={"X-Voice-Token": "sir"}).json()["text"] == ""
        assert len(eng.calls) == n
        # çağıranın süre sınırı
        assert c.post("/v1/transcribe?max_seconds=1", content=_wav(2, tone=0.3), headers={"X-Voice-Token": "sir"}).status_code == 413
        assert c.get("/health").json()["queue"]["served"] == 2


def test_service_without_token_env_refuses_everyone(monkeypatch):
    monkeypatch.delenv("VOICE_TOKEN", raising=False)
    with TestClient(SA.create_app(_FakeEngine(), load=False)) as c:
        assert c.post("/v1/transcribe", content=_wav(2, tone=0.3), headers={"X-Voice-Token": ""}).status_code == 401


