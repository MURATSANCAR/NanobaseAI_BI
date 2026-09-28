"""Zeki AI sesli not: köprü (`voice_note`, `voice_note_api`) ve GPU servisi (`apps/voice-note`).

Sözleşme: ses saklanmaz ve boyut/süre sınırı servise gitmeden denetlenir; not yazma yetkisi olmayan kaydedemez; kapalı
ortamda uç 409 der; Zeki AI düzeltmesi sayıyı ya da metni fazla değiştirirse kullanılmaz (ham metin + neden); sıra
geliş sırasını korur ve bekleyeni sessizce düşürmez; servis sessiz parçayı modele vermez, uydurma altyazı kalıbını ve
takılıp tekrar eden öbeği atar; servis anahtarsız isteği reddeder. Model/teknoloji adı kişiye giden metinde yok.
"""
from __future__ import annotations

import io
import sys
import threading
import time
import wave
from pathlib import Path

import math
import struct
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from semantic_bridge import access as A
from semantic_bridge import voice_note as V
from semantic_bridge import voice_note_api as VA



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


# ------------------------------------------------------------------ sayı ve düzeltme denetimi


@pytest.mark.parametrize("spoken,written", [
    ("yirmi bin beş yüz lira", "20.500 TL"),
    ("yüzde on beş iskonto", "%15 iskonto"),
    ("iki bin yirmi altı", "2026"),
    ("iki buçuk milyon", "2,5 milyon"),
    ("on beşinde çek verecek", "15'inde çek verecek"),
    ("yüz elli adet", "150 adet"),
    ("yirmi bin", "20 bin"),
    ("on beş ekim", "15 Ekim"),
])
def test_spoken_and_written_numbers_are_the_same_value(spoken, written):
    assert V.numbers(spoken) == V.numbers(written) != {}


def test_lone_bir_is_an_article_not_a_number():
    assert V.numbers("bir kitap sipariş verecek") == {}
    assert V.numbers("bir milyon") == V.numbers("1.000.000")


def test_date_is_three_values():
    assert V.numbers("15.10.2026") == {"15": 1, "10": 1, "2026": 1}
    assert V.numbers("saat 14:30'da") == {"14": 1, "30": 1}


RAW = "kalanı on beş ekimde çekle ödeyecek yüzde on iskonto istedi moda kitap evi yeni sipariş verecek"


def test_fix_that_only_formats_is_accepted():
    fixed = "Kalanı 15 Ekim'de çekle ödeyecek, %10 iskonto istedi. Moda Kitabevi yeni sipariş verecek."
    assert V.check_fix(RAW, fixed) is None


@pytest.mark.parametrize("bad", [
    "Kalanı 16 Ekim'de çekle ödeyecek, %10 iskonto istedi. Moda Kitabevi yeni sipariş verecek.",  # tarih değişti
    "Kalanı 15 Ekim'de çekle ödeyecek, %20 iskonto istedi. Moda Kitabevi yeni sipariş verecek.",  # oran değişti
    "Kalanı 15 Ekim'de ödeyecek, %10 iskonto.",  # cümle kısaldı
    "Müşteri memnun, yeni kitaplar için 15 Ekim'de ödeme yapıp %10 iskontoyla büyük bir sipariş geçmeyi planlıyor ve katalog istedi.",
    "",
])
def test_fix_that_changes_numbers_or_meaning_is_refused(bad):
    assert V.check_fix(RAW, bad)


class _Llm:
    def __init__(self, reply=None, boom=False):
        self.reply, self.boom, self.calls = reply, boom, []

    def chat(self, messages, **kw):
        self.calls.append((messages, kw))
        if self.boom:
            raise RuntimeError("model yok")
        return self.reply


def test_correct_applies_checked_fix_and_passes_names():
    llm = _Llm("«Kalanı 15 Ekim'de çekle ödeyecek, %10 iskonto istedi. Moda Kitabevi yeni sipariş verecek.»")
    out = V.correct(llm, RAW, ["Moda Kitabevi"])
    assert out["durum"] == "uygulandi" and out["metin"].startswith("Kalanı 15 Ekim")
    msgs, kw = llm.calls[0]
    assert "Moda Kitabevi" in msgs[1]["content"] and kw["temperature"] == 0


def test_correct_falls_back_to_raw_with_reason():
    assert V.correct(_Llm("Kalanı 20 Ekim'de ödeyecek."), RAW, [])["metin"] == RAW
    assert V.correct(_Llm("x"), RAW, [])["durum"] == "atildi"
    for llm in (None, _Llm(boom=True)):
        out = V.correct(llm, RAW, [])
        assert out["durum"] == "yok" and out["metin"] == RAW and out["neden"]


# ------------------------------------------------------------------ ayar, WAV, sıra


def test_settings_default_off_and_secrets_only_from_env():
    st = V.settings_from(lambda key, default="": default)
    assert st["enabled"] is False and st["maxSeconds"] == 300 and st["maxMb"] == 20 and st["aiFix"] is True
    assert not V.ready(st)
    conf = {"VOICE_NOTE_ENABLED": "1", "VOICE_NOTE_URL": "http://gpu:8797/", "VOICE_NOTE_TOKEN": "t"}
    st = V.settings_from(lambda key, default="": conf.get(key, default))
    assert V.ready(st) and st["url"] == "http://gpu:8797"


def test_wav_seconds_reads_header_only():
    assert V.wav_seconds(_wav(3.0)) == pytest.approx(3.0)
    assert V.wav_seconds(b"OggS" + b"\0" * 100) is None


def test_gate_keeps_arrival_order_and_times_out():
    g = V.Gate()
    order: list[int] = []
    g.enter(1, 1.0)  # ilk kişi içeride

    def worker(i):
        g.enter(1, 5.0)
        order.append(i)
        g.leave()

    ts = []
    for i in range(3):
        t = threading.Thread(target=worker, args=(i,))
        t.start()
        ts.append(t)
        time.sleep(0.05)
    assert g.view() == {"running": 1, "waiting": 3}
    g.leave()
    for t in ts:
        t.join(5)
    assert order == [0, 1, 2]
    g.enter(1, 1.0)
    with pytest.raises(V.GateTimeout):
        g.enter(1, 0.1)
    assert g.view()["waiting"] == 0  # süresi dolan sıradan çıkar
    g.leave()


# ------------------------------------------------------------------ köprü ucu


def _bridge(conf=None, can=lambda u, k: u == "yazar", llm=None, post=None):
    base = {"VOICE_NOTE_ENABLED": "1", "VOICE_NOTE_URL": "http://gpu", "VOICE_NOTE_TOKEN": "sir", "VOICE_NOTE_MAX_SECONDS": "10"}
    base.update(conf or {})
    app = FastAPI()
    user = {"name": "yazar"}
    VA.register(app, {"auth": lambda r: (None, "t", user["name"], "Yazar"), "can": can, "is_admin": lambda u: False,
                      "conf": lambda key, default="": base.get(key, default), "llm": lambda: llm, "post": post})
    return TestClient(app), user


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._body


def test_endpoint_rule_is_saha_or_okul_page():
    assert A.rule_for("/api/v1/voice-note") == frozenset({A.page("saha"), A.page("okul-tanitim")})
    assert A.rule_for("/api/v1/voice-note/meta") == A.rule_for("/api/v1/voice-note")


def test_meta_tells_the_button_whether_to_show():
    c, user = _bridge()
    assert c.get("/api/v1/voice-note/meta").json()["acik"] is True
    user["name"] = "okuyucu"
    assert c.get("/api/v1/voice-note/meta").json()["acik"] is False
    c2, _ = _bridge({"VOICE_NOTE_ENABLED": "0"})
    assert c2.get("/api/v1/voice-note/meta").json()["acik"] is False


def test_transcribe_forwards_audio_and_applies_fix():
    seen = {}

    def post(url, content, headers, params):
        seen.update(url=url, size=len(content), token=headers["X-Voice-Token"], params=params)
        return _Resp(200, {"text": "kalanı on beş ekimde ödeyecek", "segments": [{"start": 0, "end": 3.1, "text": "kalanı on beş ekimde ödeyecek"}],
                           "durationSec": 3.1, "waitMs": 5, "processingMs": 400, "model": "zeki-ses"})

    c, _ = _bridge(llm=_Llm("Kalanı 15 Ekim'de ödeyecek."), post=post)
    r = c.post("/api/v1/voice-note?baglam=saha&ad=Moda%20Kitabevi", content=_wav(3.1, tone=0.2), headers={"content-type": "audio/wav"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["metin"] == "Kalanı 15 Ekim'de ödeyecek." and j["ham"] == "kalanı on beş ekimde ödeyecek"
    assert j["duzeltme"]["durum"] == "uygulandi" and j["segmentler"][0]["son"] == 3.1
    assert seen["url"] == "http://gpu/v1/transcribe" and seen["token"] == "sir" and seen["params"]["max_seconds"] == "10"
    assert "context" not in seen["params"]  # ad ipucu varsayılan kapalı
    assert "model" not in j  # kişiye model adı gitmez


def test_transcribe_without_fix_returns_raw():
    post = lambda *a, **k: _Resp(200, {"text": "merhaba", "segments": [], "durationSec": 1.2})  # noqa: E731
    c, _ = _bridge(llm=_Llm("Merhaba."), post=post)
    j = c.post("/api/v1/voice-note?duzelt=0", content=_wav(1.2)).json()
    assert j["metin"] == "merhaba" and j["duzeltme"]["durum"] == "kapali"


def test_transcribe_refuses_before_calling_the_service():
    called = []
    post = lambda *a, **k: called.append(1)  # noqa: E731
    c, user = _bridge(post=post)
    assert c.post("/api/v1/voice-note", content=_wav(11.0)).status_code == 413  # süre
    assert c.post("/api/v1/voice-note", content=b"x" * 10).status_code == 400  # boş
    c2, _ = _bridge({"VOICE_NOTE_MAX_MB": "1"}, post=post)
    assert c2.post("/api/v1/voice-note", content=b"\0" * (1024 * 1024 + 10)).status_code == 413  # boyut
    c3, _ = _bridge({"VOICE_NOTE_ENABLED": "0"}, post=post)
    assert c3.post("/api/v1/voice-note", content=_wav(2)).status_code == 409
    user["name"] = "okuyucu"
    assert c.post("/api/v1/voice-note", content=_wav(2)).status_code == 403
    assert called == []


@pytest.mark.parametrize("status,expect", [(503, 503), (413, 413), (400, 400), (500, 502)])
def test_service_errors_become_plain_turkish(status, expect):
    post = lambda *a, **k: _Resp(status, {"detail": {"message": "Kayıt 10 saniyeyi aşıyor."} if status == 413 else {}})  # noqa: E731
    c, _ = _bridge(post=post)
    r = c.post("/api/v1/voice-note", content=_wav(2))
    assert r.status_code == expect
    msg = r.json()["detail"]["message"]
    assert msg and not any(x in msg.lower() for x in ("whisper", "qwen", "vllm", "cuda", "gpu"))


def test_service_unreachable_is_retryable():
    import httpx

    def post(*a, **k):
        raise httpx.ConnectError("yok")

    c, _ = _bridge(post=post)
    r = c.post("/api/v1/voice-note", content=_wav(2))
    assert r.status_code == 503 and r.json()["detail"]["retryable"] is True


def test_screen_code_has_no_technology_names():
    root = Path(__file__).resolve().parents[3] / "src" / "canvas" / "voice"
    text = "".join(p.read_text(encoding="utf-8") for p in root.glob("*.ts*") if not p.name.endswith(".test.ts")).lower()
    for name in ("whisper", "qwen", "vllm", "openai", "cuda", "h100"):
        assert name not in text
