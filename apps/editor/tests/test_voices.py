"""Ses kütüphanesi (editor.production.voices): hak beyanlı yükleme, kaydın denetimi ve normalleştirilmesi, kaldırma,
seslendirmede referans kullanımı, uçlar. Kayıt olarak YALNIZ yapay sinyal kullanılır (tonlardan hece benzeri
dizi); gerçek kişi kaydı yoktur. Model yok (seslendirme servisi sahte).

    pytest apps/editor/tests/test_voices.py
"""

from __future__ import annotations

import asyncio
import base64
import io
import re
import wave

import numpy as np
import pytest

from test_narration import PAGE, _fake_service  # noqa: F401

from editor.production import narration as N  # noqa: E402
from editor.production import studio  # noqa: E402
from editor.production import voices as V  # noqa: E402

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def speechlike(sec: float, sr: int = 24000, noise: float = 0.001, amp: float = 0.3, lead: float = 1.0,
               seed: int = 1) -> bytes:
    """Hece benzeri yapay sinyal: 180–260 ms'lik harmonik tonlar, aralarında kısa sessizlik; başta/sonda sessizlik."""
    rng = np.random.default_rng(seed)
    parts = [np.zeros(int(sr * lead))]
    t_total = 0.0
    while t_total < sec:
        d = rng.uniform(0.18, 0.26)
        t = np.arange(int(sr * d)) / sr
        f0 = rng.uniform(100, 140)
        syl = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, 6)) * np.hanning(len(t)) * amp / 1.5
        gap = np.zeros(int(sr * rng.uniform(0.04, 0.12)))
        parts += [syl, gap]
        t_total += d + len(gap) / sr
    parts.append(np.zeros(int(sr * lead)))
    x = np.concatenate(parts) + rng.normal(0, noise, sum(len(p) for p in parts))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


@pytest.fixture()
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "root", lambda: tmp_path)
    d = tmp_path / "20260927000000abcdef"
    d.mkdir()
    studio.write(d, "plan.json", {"version": 1, "rev": 1, "pages": [PAGE], "assets": {}})
    return tmp_path


def _add(**kw):
    args = dict(label="Deneme sesi", group="anlatici", note="", owner="Ayşe Yılmaz", confirm=True, by="editör",
                document=(PDF, "izin.pdf"), reference="")
    args.update(kw)
    audio = args.pop("audio", None) or speechlike(40)
    return V.add(audio, **args)


def test_prepare_trims_normalizes_and_cuts_reference():
    full, ref, st = V.prepare(speechlike(40, lead=2.0))
    x, sr = V.read_wav(full)
    assert sr == 24000 and 38 < st["trimmed"] < 44 and abs(len(x) / sr - st["trimmed"]) < 0.1
    r, _ = V.read_wav(ref)
    assert V.REF_MIN <= len(r) / sr <= V.REF_MAX + 0.05
    assert st["snr_db"] >= V.SNR_MIN_DB and st["clip_share"] == 0
    rms = np.sqrt(np.mean(x[np.abs(x) > 0.01] ** 2))
    assert 0.03 < rms < 0.2                                             # seviye eşitlendi


@pytest.mark.parametrize("data,msg", [
    (lambda: speechlike(12), "çok kısa"),
    (lambda: speechlike(80), "çok uzun"),
    (lambda: speechlike(40, noise=0.06), "gürültülü"),
    (lambda: speechlike(40, amp=3.0), "patlıyor"),
    (lambda: speechlike(40, sr=8000), "örnekleme hızı"),
    (lambda: b"RIFF0000WAVEbozuk", "okunamadı"),
])
def test_prepare_rejects_with_reason(data, msg):
    with pytest.raises(V.VoiceError, match=msg):
        V.prepare(data())


def test_add_requires_rights_statement_owner_and_document(root):
    with pytest.raises(V.VoiceError, match="Hak beyanı"):
        _add(confirm=False)
    with pytest.raises(V.VoiceError, match="sahibinin"):
        _add(owner=" ")
    with pytest.raises(V.VoiceError, match="İzin belgesini"):
        _add(document=None, reference="")
    with pytest.raises(V.VoiceError, match="PDF, PNG ya da JPEG"):
        _add(document=(b"GIF89a....", "izin.gif"))
    with pytest.raises(V.VoiceError, match="grubu"):
        _add(group="yok")
    assert V.entries() == []                                           # reddedilen yükleme iz bırakmaz
    rec = _add(document=None, reference="Sözleşme 2026/114, madde 3", original=(b"ID3...", "kayit.mp3"))
    assert rec["rights"]["statement"] == V.RIGHTS_TEXT and rec["rights"]["reference"].startswith("Sözleşme")
    d = V.lib_dir() / rec["id"]
    assert (d / "ses.wav").exists() and (d / "ref.wav").exists() and (d / "kaynak.mp3").exists()
    rec2 = _add(label="Belgeli")
    path, mime, name = V.document(rec2["id"])
    assert path.read_bytes() == PDF and mime == "application/pdf" and name == "izin.pdf"
    with pytest.raises(FileNotFoundError):
        V.document(rec["id"])


def test_uploaded_voice_is_used_as_reference_and_removal_stops_new_use(root, monkeypatch):
    rec = _add()
    vid = rec["id"]
    assert N.is_voice(vid) and any(v["id"] == vid and v["uploaded"] for v in N.all_voices())
    ref = asyncio.run(N.voice_ref(vid))
    assert ref["ref_text"] is None and base64.b64decode(ref["ref_audio"]) == (V.lib_dir() / vid / "ref.wav").read_bytes()
    job = next(p for p in root.iterdir() if p.name.startswith("2026"))
    calls = []
    monkeypatch.setattr(N, "_call", _fake_service(calls))
    N.set_settings(job, vid, {}, "editör")
    assert asyncio.run(N.narrate_page(job, "p_1", "editör"))["status"] == "done"
    assert all(s["voice"]["ref_audio"] == ref["ref_audio"] for s in calls[-1]["segments"])
    assert N.media_overlay(job)["narrators"] == ["Deneme sesi"]
    # kaldırılınca: seçilemez, yeni üretim reddedilir, eski ses ve kayıt durur
    V.remove(vid, "yönetici")
    assert not N.is_voice(vid) and vid not in {v["id"] for v in N.all_voices()}
    assert N.voice(vid)["removed"]["by"] == "yönetici"
    with pytest.raises(ValueError):
        N.set_settings(job, vid, {}, "editör")
    with pytest.raises(ValueError, match="kaldırıldı"):
        asyncio.run(N.narrate_page(job, "p_1", "editör"))
    assert N.audio_path(job, "p_1").exists() and (V.lib_dir() / vid / "ses.wav").exists()


def test_sample_is_cached_per_voice_and_text(root, monkeypatch):
    calls = []
    monkeypatch.setattr(N, "_call", _fake_service(calls))
    lex = N.Lexicon()
    a = asyncio.run(N.sample("Merhaba, bu kitabı ben okuyacağım.", "masal-baba", lex))
    n = len(calls)
    b = asyncio.run(N.sample("Merhaba, bu kitabı ben okuyacağım.", "masal-baba", lex))
    assert a == b and len(calls) == n                                  # ikinci dinleme modele gitmez
    asyncio.run(N.sample("Başka bir cümle.", "masal-baba", lex))
    assert len(calls) == n + 1


def test_voice_library_groups_and_designs():
    groups = {v["group"] for v in N.VOICES}
    assert groups == set(N.GROUPS)
    for g in ("yetiskin", "genc", "cocuk"):                         # her okuyucu grubunda kadın ve erkek
        ws = [v for v in N.VOICES if v["group"] == g]
        assert any("Kadın" in v["label"] or "kadın" in v["label"] for v in ws), g
        assert any("Erkek" in v["label"] or "erkek" in v["label"] or "adam" in v["label"] for v in ws), g
    assert not any(re.search(r"\b(child|girl|boy)\b", v["design"]) for v in N.VOICES)   # küçük çocuk sesi yok
    assert N.DEFAULT_NARRATOR == "roman-kadin"


def test_voice_endpoints(root, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from editor.production import api
    monkeypatch.setattr(api, "KEY", "k")
    c = TestClient(api.app)
    h = {"Authorization": "Bearer k", "X-Editor": "editor"}
    lib = c.get("/v1/studio/voices", headers=h).json()
    assert lib["rights_text"] == V.RIGHTS_TEXT and set(lib["groups"]) == set(N.GROUPS)
    body = {"label": "Yüklenen", "group": "yetiskin", "owner": "Mehmet Kaya", "confirm": True, "reference": "",
            "audio": base64.b64encode(speechlike(40)).decode(),
            "document": {"name": "izin.pdf", "data": base64.b64encode(PDF).decode()}}
    r = c.post("/v1/studio/voices", headers=h, json={**body, "confirm": False})
    assert r.status_code == 400 and r.json()["code"] == "VOICE_REJECTED" and "Hak beyanı" in r.json()["detail"]
    r = c.post("/v1/studio/voices", headers=h, json={**body, "audio": base64.b64encode(speechlike(10)).decode()})
    assert r.status_code == 400 and "çok kısa" in r.json()["detail"]
    r = c.post("/v1/studio/voices", headers=h, json=body)
    assert r.status_code == 200 and r.json()["voice"]["uploaded"] and r.json()["voice"]["document"]
    vid = r.json()["voice"]["id"]
    doc = c.get(f"/v1/studio/voices/{vid}/document", headers=h)
    assert doc.status_code == 200 and doc.content == PDF
    assert c.delete(f"/v1/studio/voices/{vid}", headers=h).status_code == 403          # yönetici değil
    r = c.delete(f"/v1/studio/voices/{vid}", headers={**h, "X-Editor-Admin": "1"})
    assert r.status_code == 200 and r.json()["voice"]["removed"]
    lib = c.get("/v1/studio/voices", headers=h).json()
    assert vid not in {v["id"] for v in lib["voices"]} and vid in {v["id"] for v in lib["removed"]}


def test_catalog_voices_use_packaged_reference(root, monkeypatch, tmp_path_factory):
    """Katalogdaki her ses (voices_zeki.py) tariften yeniden üretilmez: kullanıcının dinleyip seçtiği kayıt pakette
    sabit (sha256 kodda), kaydın kendi metniyle klonlanır. Eski kimlik aynı kayda gider; kayıt yoksa ya da değişmişse
    ses üretilmez (başka ses sessizce gelmez)."""
    import hashlib
    from editor.production import voices_zeki as Z
    assert set(Z.PINNED) == N.VOICE_IDS                               # bütün katalog sabit kayıtlı
    calls = []
    monkeypatch.setattr(N, "_call", _fake_service(calls))
    for vid, meta in Z.PINNED.items():
        data = (N.PINNED_DIR / meta["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == meta["sha256"]
        w = wave.open(io.BytesIO(data))
        assert w.getnchannels() == 1 and 5.0 < w.getnframes() / w.getframerate() < 16.0
        ref = asyncio.run(N.voice_ref(vid))
        assert base64.b64decode(ref["ref_audio"]) == data and ref["ref_text"] == meta["text"]
        assert meta["text"] in (Z.READER_TEXT, Z.FILM_TEXT)
    vid = N.DEFAULT_MALE_NARRATOR
    data = (N.PINNED_DIR / N.PINNED[vid]["file"]).read_bytes()
    assert base64.b64decode(asyncio.run(N.voice_ref("anlatici-erkek"))["ref_audio"]) == data
    assert calls == [] and not (N._root() / "sesler").exists()        # model çağrılmadı, klasöre yazılmadı
    # sayfa bu referansla okunur
    job = root / "20260927000000abcdef"
    N.set_settings(job, "anlatici-erkek", {}, "editör")
    asyncio.run(N.narrate_page(job, "p_1", "editör"))
    assert calls and all(s["voice"]["ref_audio"] == base64.b64encode(data).decode()
                         for s in calls[-1]["segments"])
    # kayıt bozuk / eksik: üretim durur
    bad = tmp_path_factory.mktemp("sesler")
    (bad / "zeki").mkdir()
    (bad / N.PINNED[vid]["file"]).write_bytes(data[:-10] + b"0123456789")
    monkeypatch.setattr(N, "PINNED_DIR", bad)
    N._pinned_ok.clear()
    with pytest.raises(N.PinnedVoiceMissing, match="«Erkek · roman» sesinin kaydı beklenen kayıt değil"):
        asyncio.run(N.voice_ref(vid))
    (bad / N.PINNED[vid]["file"]).unlink()
    with pytest.raises(N.PinnedVoiceMissing, match="yok"):
        asyncio.run(N.voice_ref(vid))
    N._pinned_ok.clear()

