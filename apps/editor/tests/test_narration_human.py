"""Sesli okumada insan kaydı (editor.production.narration_human, 2026-09-28): seslendirmenin okuduğu kayıt sayfanın
sesi olur; kelime zamanları hizalayıcıdan (servis sahte), birden çok sayfalı dosya sayfalara bölünür, hak beyanı
zorunlu, metin değişince «güncel değil» ama yapay ses insan kaydını ezmez (yalnız açık onayla). Model yok. Ses dosyası
kesme ffmpeg ister (stüdyo imajında var; yoksa o testler atlanır).

    pytest apps/editor/tests/test_narration_human.py
"""

from __future__ import annotations

import asyncio
import base64
import io
import shutil
import wave

import numpy as np
import pytest

from test_narration import PAGE, _fake_service

from editor.production import narration as N  # noqa: E402
from editor.production import narration_human as H  # noqa: E402

ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg yok")
PAGE2 = {"id": "p_3", "layout": "text", "text": {"box": {"x": 14, "y": 20, "w": 141, "h": 180}, "blocks": [
    {"id": "d1", "kind": "para", "runs": [{"text": "Ertesi sabah güneş doğdu. Elif bahçeye koştu."}]}]},
    "bubbles": [], "texts": []}


@pytest.fixture()
def job(tmp_path, monkeypatch):
    from editor.production import studio
    monkeypatch.setattr(studio, "root", lambda: tmp_path)
    d = tmp_path / "20260928000000abcdef"
    d.mkdir()
    blank = {"id": "p_2", "layout": "blank", "text": None, "bubbles": [], "texts": []}
    studio.write(d, "plan.json", {"version": 1, "rev": 1, "pages": [PAGE, blank, PAGE2], "assets": {}})
    return d


def _wav(seconds: float, sr: int = 16000) -> bytes:
    t = np.arange(int(seconds * sr)) / sr
    x = (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((x * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def _fake_aligner(calls, duration: float, missing: set[int] = frozenset()):
    """Yalnız hizalama kipi (`recording`): kelimeler kayda eşit aralıkla yayılır; `missing` sıraları bulunamaz."""
    synth = _fake_service(calls)

    async def call(body, timeout=1800.0):
        if "recording" not in body:
            return await synth(body, timeout)
        calls.append(body)
        assert base64.b64decode(body["recording"])[:4] == b"fLaC"          # 16 kHz kayıpsız gövde
        n = len(body["words"])
        step = duration / max(1, n)
        words = [None if i in missing else {"start": round(i * step + 0.02, 3), "end": round((i + 0.8) * step, 3),
                                             "score": 0.9} for i in range(n)]
        return {"audio": "", "format": "none", "sample_rate": 16000, "duration": duration, "seconds": 0.1,
                "aligned": True, "segments": [], "words": words}
    return call


def _stage(job, pages, **kw):
    args = {"owner": "Ayşe Okur", "confirm": True, "by": "editör", "reference": "Sözleşme 2026/7"}
    args.update(kw)
    return H.stage(job, pages, _wav(kw.pop("seconds", 6.0)), kw.pop("name", "kayit.wav"),
                   **{k: v for k, v in args.items() if k not in ("seconds", "name")})


# ------------------------------------------------------------------ saf
def test_cuts_split_in_the_middle_of_the_gap():
    filled = [(0.2, 0.6), (0.7, 1.0), (2.0, 2.4), (2.5, 3.0)]
    assert H.cuts(filled, [0, 2], [1, 3], 3.5) == [0.0, 1.5, 3.5]
    # tek sayfa: kaydın tamamı
    assert H.cuts(filled, [0], [3], 3.5) == [0.0, 3.5]


def test_page_segments_are_relative_to_page_start():
    got = [{"start": 2.1, "end": 2.4}, None, {"start": 3.0, "end": 3.3}]
    filled = [(2.1, 2.4), (2.5, 2.8), (3.0, 3.3)]
    segs = H.page_segments([[0, 1], [2]], got, filled, 2.0, 4.0)
    assert segs[0]["start"] == 0.0 and segs[0]["end"] == 1.0            # sonraki parçanın ilk kelimesine kadar
    assert segs[0]["words"] == [{"start": 0.1, "end": 0.4}, None]        # bulunamayan kelime tahmine kalır
    assert segs[1]["start"] == 0.8 and segs[1]["end"] == 2.0


# ------------------------------------------------------------------ yükleme denetimi
@ffmpeg
def test_rights_and_pages_are_required(job):
    with pytest.raises(H.RecordingError, match="Hak beyanı"):
        _stage(job, ["p_1"], confirm=False)
    with pytest.raises(H.RecordingError, match="okuyan kişinin"):
        _stage(job, ["p_1"], owner=" ")
    with pytest.raises(H.RecordingError, match="İzin belgesini"):
        _stage(job, ["p_1"], reference="")
    with pytest.raises(H.RecordingError, match="wav, mp3"):
        _stage(job, ["p_1"], name="kayit.exe")
    with pytest.raises(H.RecordingError, match="okunacak metin yok"):
        _stage(job, ["p_2"])
    with pytest.raises(KeyError):
        _stage(job, ["p_9"])
    with pytest.raises(H.RecordingError, match="PDF, PNG ya da JPEG"):
        _stage(job, ["p_1"], document=(b"hello", "izin.txt"))
    with pytest.raises(H.RecordingError, match="okunamadı"):
        H.stage(job, ["p_1"], b"not audio", "kayit.mp3", owner="A", confirm=True, by="e", reference="x")
    assert H.uploads(job) == []                                           # reddedilen yükleme iz bırakmaz
    # boş sayfa atlanır: p_1 ve p_3 okuma sırasıyla ardışık; ters verilse de sıraya dizilir
    rec = _stage(job, ["p_3", "p_1"], document=(b"%PDF-1.4 x", "izin.pdf"))
    assert rec["pages"] == ["p_1", "p_3"] and rec["status"] == "queued"
    assert rec["rights"]["confirmed"] is True and rec["rights"]["document"]["name"] == "izin.pdf"
    assert rec["source"]["seconds"] == pytest.approx(6.0, abs=0.1)
    assert (H.up_dir(job) / rec["id"] / "kaynak.wav").exists() and (H.up_dir(job) / rec["id"] / "izin.pdf").exists()
    assert H.public(rec)["owner"] == "Ayşe Okur" and "file" in H.public(rec)


# ------------------------------------------------------------------ uçtan uca (sahte hizalayıcı)
@ffmpeg
def test_human_recording_becomes_page_audio_and_is_not_overwritten(job, monkeypatch):
    calls = []
    monkeypatch.setattr(N, "_call", _fake_aligner(calls, 6.0, missing={3}))
    rec = _stage(job, ["p_1", "p_3"])
    prog = []
    res = asyncio.run(H.apply(job, rec["id"], "editör", lambda i, n: prog.append((i, n))))
    assert prog == [(1, 2), (2, 2)] and len(calls) == 1
    body = calls[0]
    assert body["format"] == "none" and body["align"] is True and "segments" not in body
    # okunuş kelimeleri: iki sayfanın bütün parçaları sırasıyla
    u1, p1, _ = N.page_input(job, PAGE)
    u3, p3, _ = N.page_input(job, PAGE2)
    want = [s for us, ps in ((u1, p1), (u3, p3)) for p in ps for k in p.words for s in us[p.unit].words[k].say]
    assert body["words"] == want

    a, b = res["pages"][0], res["pages"][1]
    assert a["start"] == 0.0 and b["end"] == 6.0 and a["end"] == b["start"] and 0 < a["end"] < 6.0
    st = {r["id"]: r for r in N.status(job)}
    assert st["p_1"]["status"] == "done" and st["p_1"]["human"] is True and st["p_1"]["owner"] == "Ayşe Okur"
    assert st["p_3"]["status"] == "done" and st["p_2"]["status"] == "empty" and not st["p_2"]["human"]
    r1 = N.page_record(job, "p_1")
    assert r1["source"] == "human" and r1["human"]["upload"] == rec["id"] and r1["estimated"] is True   # kelime 3 yok
    assert r1["duration"] == pytest.approx(a["end"], abs=0.1)
    for bl in r1["blocks"]:
        assert bl["voice"] == ""
        ends = [w["end"] for w in bl["words"] if w["start"] is not None]
        assert ends == sorted(ends) and all(0 <= e <= r1["duration"] + 0.05 for e in ends)
    assert N.audio_path(job, "p_1").read_bytes()[:3] in (b"ID3", b"\xff\xfb", b"\xff\xf3")
    assert H.load(job, rec["id"])["status"] == "done"

    # e-kitap: kaplama tamam, anlatıcı kaydı okuyan kişi
    mo = N.media_overlay(job)
    assert mo["complete"] and mo["narrators"] == ["Ayşe Okur"] and [p["page"] for p in mo["pages"]] == ["p_1", "p_3"]

    # ses/sözlük değişikliği insan kaydını eskitmez; metin değişikliği eskitir
    N.set_settings(job, "cocuk-kiz", {}, "editör")
    N.set_lexicon(job, "job", [{"word": "yıldız", "say": "yıl-dız"}], "editör")
    assert {r["id"]: r["status"] for r in N.status(job)}["p_1"] == "done"
    from editor.production import studio
    pl = studio.read(job, "plan.json")
    pl["pages"][2]["text"]["blocks"][0]["runs"][0]["text"] = "Ertesi sabah güneş doğdu. Elif bahçeye yürüdü."
    studio.write(job, "plan.json", pl)
    st = {r["id"]: r for r in N.status(job)}
    assert st["p_3"]["status"] == "stale" and st["p_3"]["human"] is True
    view = N.page_view(job, "p_3")
    assert view["status"] == "stale" and view["source"] == "human"

    # «Seslendir» (keep_human) insan kaydına dokunmaz; açık onayla yapay ses yazılır
    before = N.audio_path(job, "p_3").read_bytes()
    assert asyncio.run(N.narrate_page(job, "p_3", "editör", keep_human=True))["status"] == "human"
    assert N.audio_path(job, "p_3").read_bytes() == before and N.is_human(N.page_record(job, "p_3"))
    assert asyncio.run(N.narrate_page(job, "p_3", "editör", keep_human=False))["status"] == "done"
    assert not N.is_human(N.page_record(job, "p_3"))
    mo = N.media_overlay(job)
    assert mo["narrators"][0] == "Ayşe Okur" and len(mo["narrators"]) == 2          # insan + yapay anlatıcı


@ffmpeg
def test_recording_that_matches_nothing_fails_clearly(job, monkeypatch):
    calls = []
    monkeypatch.setattr(N, "_call", _fake_aligner(calls, 4.0, missing=set(range(100))))
    rec = _stage(job, ["p_1"])
    with pytest.raises(H.RecordingError, match="eşleşmedi"):
        asyncio.run(H.apply(job, rec["id"], "editör"))
    assert N.page_record(job, "p_1") is None


# ------------------------------------------------------------------ servis uçları
def _client(job, monkeypatch):
    from fastapi.testclient import TestClient

    from editor.production import api, studio
    monkeypatch.setattr(api, "KEY", "k")

    async def no_busy(d):
        return studio.busy(d)
    monkeypatch.setattr(api, "_busy", no_busy)
    monkeypatch.setattr(N, "available", lambda: asyncio.sleep(0, True))
    started = []

    class T:
        async def start_workflow(self, name, args, id, task_queue):
            started.append((name, args))

    async def temporal():
        return T()
    monkeypatch.setattr(api, "_temporal", temporal)
    return TestClient(api.app), {"Authorization": "Bearer k", "X-Editor": "sinama"}, started


@ffmpeg
def test_endpoints_upload_and_run_skip_human_pages(job, monkeypatch):
    pytest.importorskip("fastapi")
    from editor.production import plan as P
    c, h, started = _client(job, monkeypatch)
    url = f"/v1/studio/jobs/{job.name}/narration"
    audio = {"name": "kayit.wav", "data": base64.b64encode(_wav(5.0)).decode()}
    r = c.post(url + "/recordings", headers=h, json={"pages": ["p_1"], "owner": "Ayşe Okur", "confirm": False,
                                                       "reference": "x", "audio": audio})
    assert r.status_code == 400 and r.json()["code"] == "RECORDING_REJECTED" and "Hak beyanı" in r.json()["detail"]
    r = c.post(url + "/recordings", headers=h, json={"pages": ["p_1"], "owner": "Ayşe Okur", "confirm": True,
                                                       "reference": "Sözleşme 7", "audio": audio})
    assert r.status_code == 200, r.text
    name, args = started[-1]
    assert name == "HumanRecording" and args[2] == r.json()["recording"]["id"]
    rec_job = next(j for j in P.jobs(job) if j["id"] == args[1])
    assert rec_job["kind"] == "narration" and rec_job["mode"] == "human" and rec_job["status"] == "queued"
    # iş sürerken ikinci yükleme ve seslendirme reddedilir
    assert c.post(url + "/recordings", headers=h, json={"pages": ["p_1"], "owner": "A", "confirm": True,
                                                         "reference": "x", "audio": audio}).json()["code"] == "BUSY"
    monkeypatch.setattr(N, "_call", _fake_aligner([], 5.0))
    asyncio.run(H.apply(job, args[2], "sinama"))
    P.job_record(job, args[1], status="done")

    ov = c.get(url, headers=h).json()
    assert ov["summary"]["human"] == 1 and ov["recordings"]["items"][0]["status"] == "done"
    assert ov["recordings"]["rights_text"] == H.RIGHTS_TEXT and ov["recordings"]["upload_mb"] >= 1
    # listesiz «Seslendir» insan kayıtlı sayfayı atlar; açıkça verilen sayfa onaysız 409
    r = c.post(url + "/run", headers=h, json={"pages": None})
    assert r.status_code == 200 and started[-1][0] == "BookNarration" and started[-1][1][2] == ["p_3"]
    assert started[-1][1][4] is False
    P.job_record(job, started[-1][1][1], status="done")
    r = c.post(url + "/run", headers=h, json={"pages": None, "force": True})
    assert r.status_code == 200 and started[-1][1][2] == ["p_3"]
    P.job_record(job, started[-1][1][1], status="done")
    r = c.post(url + "/run", headers=h, json={"pages": ["p_1"]})
    assert r.status_code == 409 and r.json()["code"] == "HUMAN_RECORDING"
    r = c.post(url + "/run", headers=h, json={"pages": ["p_1"], "replace_human": True})
    assert r.status_code == 200 and started[-1][1][2] == ["p_1"] and started[-1][1][4] is True


def test_workflow_and_activity_are_registered():
    from editor.production.flow import ACTIVITIES, WORKFLOWS
    wfs = {getattr(w, "__temporal_workflow_definition").name for w in WORKFLOWS}
    acts = {getattr(a, "__temporal_activity_definition").name for a in ACTIVITIES}
    assert {"HumanRecording", "HumanRealign"} <= wfs
    assert {"production_human_recording", "production_human_realign"} <= acts


# ------------------------------------------------------------------ kelimeleri kayda yeniden yerleştirme (09-29)
def test_mostly_missing_is_the_majority_of_words():
    assert H.mostly_missing(0, 1) and H.mostly_missing(4, 9)            # 5/9 bulunamadı
    assert not H.mostly_missing(5, 10) and not H.mostly_missing(9, 9)  # yarısı bulundu: yerleştirilir
    assert not H.mostly_missing(0, 0)


def _edit_p3(job, text: str) -> None:
    from editor.production import studio
    pl = studio.read(job, "plan.json")
    pl["pages"][2]["text"]["blocks"][0]["runs"][0]["text"] = text
    studio.write(job, "plan.json", pl)


def _human_pages(job, monkeypatch):
    monkeypatch.setattr(N, "_call", _fake_aligner([], 6.0))
    rec = _stage(job, ["p_1", "p_3"], document=(b"%PDF-1.4 izin", "izin.pdf"))
    asyncio.run(H.apply(job, rec["id"], "editör"))
    return rec


@ffmpeg
def test_realign_keeps_the_recording_and_updates_word_times(job, monkeypatch):
    rec = _human_pages(job, monkeypatch)
    before = N.page_record(job, "p_3")
    audio = N.audio_path(job, "p_3").read_bytes()
    _edit_p3(job, "Ertesi sabah güneş doğdu. Elif bahçeye yürüdü.")
    assert {r["id"]: r["status"] for r in N.status(job)}["p_3"] == "stale"

    calls = []
    monkeypatch.setattr(N, "_call", _fake_aligner(calls, before["duration"]))
    res = asyncio.run(H.realign(job, "p_3", "düzelten"))
    assert len(calls) == 1 and calls[0]["format"] == "none" and "segments" not in calls[0]
    u3, p3, _ = N.page_input(job, studio_page(job, "p_3"))
    assert calls[0]["words"] == [s for p in p3 for k in p.words for s in u3[p.unit].words[k].say]
    assert any("yürüdü" in s for s in calls[0]["words"])
    assert res["aligned"] == [len(calls[0]["words"])] * 2

    after = N.page_record(job, "p_3")
    st = {r["id"]: r for r in N.status(job)}
    assert st["p_3"]["status"] == "done" and st["p_3"]["human"] and st["p_3"]["owner"] == "Ayşe Okur"
    assert after["source"] == "human" and after["human"] == before["human"] and after["human"]["upload"] == rec["id"]
    assert after["duration"] == before["duration"] and after["audio"] == before["audio"]     # kayıt ve süre aynı
    assert N.audio_path(job, "p_3").read_bytes() == audio
    assert after["text_hash"] != before["text_hash"] and after["realigned"]["by"] == "düzelten"
    words = [w["text"] for bl in after["blocks"] for w in bl["words"]]
    assert any("yürüdü" in t for t in words)
    assert all(bl["voice"] == "" for bl in after["blocks"])
    ends = [w["end"] for bl in after["blocks"] for w in bl["words"] if w["start"] is not None]
    assert ends == sorted(ends) and all(0 <= e <= after["duration"] + 0.05 for e in ends)
    assert N.page_view(job, "p_3")["status"] == "done"


def studio_page(job, pid):
    from editor.production import plan as plan_mod
    return plan_mod._page(plan_mod.load(job), pid)


@ffmpeg
def test_realign_refuses_when_most_words_are_not_in_the_recording(job, monkeypatch):
    _human_pages(job, monkeypatch)
    _edit_p3(job, "Bambaşka bir metin yazıldı buraya, hiç okunmamış kelimelerle dolu.")
    before = N.page_record(job, "p_3")
    # ilk kelime bulunur, gerisi bulunamaz: çoğunluk kayıtta yok
    monkeypatch.setattr(N, "_call", _fake_aligner([], before["duration"], missing=set(range(1, 100))))
    with pytest.raises(H.RecordingError, match="metin kayıttan çok farklı.*kaydı yeniden yükleyin"):
        asyncio.run(H.realign(job, "p_3", "düzelten"))
    assert N.page_record(job, "p_3") == before                          # sayfa kaydına dokunulmadı
    assert {r["id"]: r["status"] for r in N.status(job)}["p_3"] == "stale"
    # yalnız insan kaydına: sesi insan kaydı olmayan sayfa reddedilir
    for p in (N.audio_path(job, "p_1"), N.ses_dir(job) / "sayfa" / "p_1.json"):
        p.unlink()
    with pytest.raises(H.RecordingError, match="insan kaydı değil"):
        asyncio.run(H.realign(job, "p_1", "düzelten"))


@ffmpeg
def test_realign_pages_reports_rejected_pages_and_continues(job, monkeypatch):
    _human_pages(job, monkeypatch)
    _edit_p3(job, "Ertesi sabah güneş doğdu. Elif bahçeye yürüdü.")
    monkeypatch.setattr(N, "_call", _fake_aligner([], 3.0))
    prog = []
    res = asyncio.run(H.realign_pages(job, ["p_1", "p_3"], "düzelten", lambda i, n: prog.append((i, n))))
    assert prog == [(1, 2), (2, 2)] and [p["page"] for p in res["pages"]] == ["p_1", "p_3"] and res["rejected"] == []
    monkeypatch.setattr(N, "_call", _fake_aligner([], 3.0, missing=set(range(100))))
    res = asyncio.run(H.realign_pages(job, ["p_3"], "düzelten"))
    assert res["pages"] == [] and res["rejected"][0]["page"] == "p_3" and "çok farklı" in res["rejected"][0]["error"]


@ffmpeg
def test_endpoints_realign_and_document(job, monkeypatch):
    pytest.importorskip("fastapi")
    from editor.production import plan as P
    rec = _human_pages(job, monkeypatch)
    c, h, started = _client(job, monkeypatch)
    url = f"/v1/studio/jobs/{job.name}/narration"

    # izin belgesi: tarayıcıda açılır (inline), doğru tür
    r = c.get(f"{url}/recordings/{rec['id']}/document", headers=h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/pdf")
    assert r.headers["content-disposition"].startswith("inline") and r.content == b"%PDF-1.4 izin"
    assert c.get(f"{url}/recordings/r0000000000/document", headers=h).status_code == 404
    assert c.get(f"{url}/recordings/../document", headers=h).status_code == 404
    ref_only = _stage(job, ["p_1"])                                      # yalnız belge numarası
    assert c.get(f"{url}/recordings/{ref_only['id']}/document", headers=h).status_code == 404
    items = {i["id"]: i for i in c.get(url, headers=h).json()["recordings"]["items"]}
    assert items[rec["id"]]["document"] is True and items[ref_only["id"]]["reference"] == "Sözleşme 2026/7"

    # güncel sayfada yapılacak iş yok; insan kaydı olmayan sayfa reddedilir
    r = c.post(url + "/realign", headers=h, json={"pages": ["p_3"]})
    assert r.status_code == 400 and r.json()["code"] == "NOTHING"
    _edit_p3(job, "Ertesi sabah güneş doğdu. Elif bahçeye yürüdü.")
    for p in (N.audio_path(job, "p_1"), N.ses_dir(job) / "sayfa" / "p_1.json"):
        p.unlink()
    r = c.post(url + "/realign", headers=h, json={"pages": ["p_1", "p_3"]})
    assert r.status_code == 400 and r.json()["code"] == "RECORDING_REJECTED"
    assert c.post(url + "/realign", headers=h, json={"pages": ["p_9"]}).status_code == 404
    assert c.post(url + "/realign", headers=h, json={"pages": []}).status_code == 422
    assert c.post(url + "/realign", json={"pages": ["p_3"]},
                  headers={"Authorization": "Bearer k"}).status_code == 400          # X-Editor şart

    r = c.post(url + "/realign", headers=h, json={"pages": ["p_3"]})
    assert r.status_code == 200, r.text
    name, args = started[-1]
    assert name == "HumanRealign" and args[2] == ["p_3"] and args[3] == "sinama"
    jr = next(j for j in P.jobs(job) if j["id"] == args[1])
    assert jr["kind"] == "narration" and jr["mode"] == "realign" and jr["status"] == "queued"
    assert c.get(url, headers=h).json()["job"]["mode"] == "realign"
    # iş sürerken ikinci istek ve seslendirme reddedilir
    assert c.post(url + "/realign", headers=h, json={"pages": ["p_3"]}).json()["code"] == "BUSY"
    assert c.post(url + "/run", headers=h, json={"pages": None}).json()["code"] == "BUSY"
