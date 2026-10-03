"""Sesli e-kitap ve planın kendiliğinden kurulumu (2026-09-27):

- Planı olmayan işte sesli okuma (ve okur, sürüm farkı) açılınca sayfa düzeni kendiliğinden kurulur (plan.ensure):
  ekran 409 PREPARING görür, kurulum bitince bölüm açılır; yarış yok (tek kurulum), üretim hattı sürerken beklenir,
  dizgi (iç sayfa PDF'i) sayfa sayısı ve metniyle korunur.
- Sesli e-kitap (EPUB 3 medya kaplaması): sesi olan sayfalarda kelimeler kimlikli, SMIL + MP3 pakette, OPF'te süreler,
  anlatıcı ve vurgu sınıfı; sabit sayfa ve akışkan düzenin ikisinde. Sesi eksik sayfa varsa sesli üretim reddedilir.

Model yok (seslendirme servisi sahte). Dizgili testler Typst ve fontlar ister (editor-py imajında koşar). Tam e-kitap
denetimi kuruluysa (EDITOR_EPUBCHECK_JAR + java) sesli EPUB'da da hatasız olmalı; EPUB_OUT verilirse dosyalar oraya
kopyalanır.

    pytest apps/editor/tests/test_audio_epub.py
"""

from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET
import zipfile

import pytest

from test_epub import FakeLlm, _keep, _no_errors, _opf, NS  # noqa: F401 - ortak yardımcılar
from test_narration import _fake_service
from test_plan import FONTS, _job, typeset_only  # noqa: F401

from editor.production import epub as E  # noqa: E402
from editor.production import narration as N  # noqa: E402
from editor.production import plan as P  # noqa: E402
from editor.production import studio  # noqa: E402

SMIL = "{http://www.w3.org/ns/SMIL}"


@pytest.fixture(autouse=True)
def _fonts(monkeypatch):
    monkeypatch.setenv("EDITOR_FONT_DIR", str(FONTS))


# ------------------------------------------------------------------ saf
def test_wrap_runs_keeps_styles_and_wraps_every_word():
    runs = [{"text": "Elif pencereden baktı. "}, {"text": "Ay", "color": "#B0341C"}, {"text": "şe çok sevindi."}]
    words = [w.__dict__ for w in N.read(E.runs_text(runs))]
    ws = [{"i": w["i"], "text": w["text"], "char": [w["start"], w["end"]]} for w in words]
    placed: dict = {}
    html = E.wrap_runs(runs, ws, "c1", {}, None, placed, "text/s004.xhtml")
    assert len(placed) == len(ws) == 6 and set(placed.values()) == {"text/s004.xhtml"}
    # renkli parça kelimenin ortasından geçiyor: kelime tek kimlikte, biçim içeride
    assert '<span id="w-c1-3"><span style="color:#B0341C">Ay</span>şe</span>' in html
    assert re.sub(r"<[^>]+>", "", html) == E.runs_text(runs)
    # metin tutmazsa (fazladan boşluk) kelime sıradaki yerinde bulunur; hiç yoksa sarılmaz
    placed2: dict = {}
    html2 = E.wrap_runs([{"text": "Elif  pencereden"}], [{"i": 0, "text": "Elif", "char": [0, 4]},
                                                          {"i": 1, "text": "pencereden", "char": [5, 15]},
                                                          {"i": 2, "text": "yok", "char": [16, 19]}],
                        "b", {}, None, placed2, "x")
    assert set(placed2) == {"w-b-0", "w-b-1"} and '<span id="w-b-1">pencereden</span>' in html2


def test_smil_doc_is_continuous_and_sums_duration():
    clips = [("w-a-0", "../audio/p1.mp3", 0.10, 0.50), ("w-a-1", "../audio/p1.mp3", 0.50, 0.90),
             ("w-a-2", "../audio/p1.mp3", 1.60, 2.00), ("w-b-0", "../audio/p2.mp3", 0.20, 0.60)]
    xml, secs = N.smil_doc(clips, "../text/bolum-001.xhtml", "seq-bolum-001")
    root = ET.fromstring(xml.encode())
    pars = root.findall(f".//{SMIL}par")
    assert [p.find(f"{SMIL}text").get("src") for p in pars][0] == "../text/bolum-001.xhtml#w-a-0"
    a = [p.find(f"{SMIL}audio") for p in pars]
    assert a[1].get("clipEnd") == N.clock(1.60)             # cümle arası duraklama öndeki kelimeye katıldı
    assert a[2].get("clipEnd") == N.clock(2.00)             # başka sese geçerken uzatılmaz
    assert secs == pytest.approx(0.4 + 1.1 + 0.4 + 0.4)
    # tek sayfalık eski biçim değişmedi: zamanlar olduğu gibi
    page = {"page": "p1", "blocks": [{"id": "a", "words": [{"i": 0, "start": 0.1, "end": 0.5},
                                                           {"i": 1, "start": 1.6, "end": 2.0},
                                                           {"i": 2, "start": None, "end": None}]}]}
    root = ET.fromstring(N.smil(page, "s.xhtml", "a.mp3").encode())
    assert [p.find(f"{SMIL}audio").get("clipEnd") for p in root.findall(f".//{SMIL}par")] == [N.clock(0.5), N.clock(2.0)]


def test_catalog_voices_are_designs_not_people():
    ids = [v["id"] for v in N.VOICES]
    assert len(ids) == len(set(ids)) and len({v["design"] for v in N.VOICES}) == len(N.VOICES)
    for v in N.VOICES:
        assert not re.search(r"\b(clone|voice of|sounds like|imitat)", v["design"], re.I)   # tarif, kişi değil


def test_old_voice_ids_follow_the_new_catalog(tmp_path, monkeypatch):
    """Kullanıcı kararı 2026-10-03: eski sesler kaldırıldı, yerine voices_zeki.py. Eski kimlik en yakın yeni sese
    yönlenir, listede ayrı satır yoktur; anlatıcı varsayılanları roman okuyucuları, ikisi «önerilen»."""
    assert (N.DEFAULT_NARRATOR, N.DEFAULT_MALE_NARRATOR) == ("roman-kadin", "roman-erkek")
    assert N.canonical("anlatici-erkek") == N.DEFAULT_MALE_NARRATOR and N.canonical("anlatici-kadin") == "roman-kadin"
    assert N.is_voice("anlatici-erkek") and N.voice("anlatici-erkek")["id"] == N.DEFAULT_MALE_NARRATOR
    assert all(N.is_voice(old) and new in N.VOICE_IDS for old, new in N.ALIASES.items())
    listed = N.all_voices()
    assert not set(N.ALIASES) & {v["id"] for v in listed}
    assert {v["id"] for v in listed if v.get("recommended")} == {N.DEFAULT_NARRATOR, N.DEFAULT_MALE_NARRATOR}
    # kayıtlı ayar ve API isteği: eski kimlik güncel sese çevrilir
    monkeypatch.setattr(studio, "root", lambda: tmp_path)
    d = tmp_path / "20260927000000abcdef"
    d.mkdir()
    assert N.set_settings(d, "anlatici-erkek", {"Ali": "anlatici-erkek"}, "e")["narrator"] == N.DEFAULT_MALE_NARRATOR
    N._write(d / "ses" / "ayar.json", {"narrator": "anlatici-erkek", "characters": {"Ali": "anlatici-erkek"}})
    cfg = N.settings_of(d)
    assert cfg["narrator"] == N.DEFAULT_MALE_NARRATOR and cfg["characters"] == {"Ali": N.DEFAULT_MALE_NARRATOR}
    us = N.page_units({"text": {"blocks": [{"id": "b", "kind": "para", "text": "Bir varmış."}]}},
                      {"narrator": "anlatici-erkek"}, N.Lexicon())
    assert us[0].voice == N.DEFAULT_MALE_NARRATOR


# ------------------------------------------------------------------ planın kendiliğinden kurulumu
def _client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from editor.production import api
    monkeypatch.setattr(studio, "root", lambda: tmp_path)
    monkeypatch.setattr(api, "KEY", "k")

    async def no_busy(d):
        return studio.busy(d)
    monkeypatch.setattr(api, "_busy", no_busy)
    return TestClient(api.app), {"Authorization": "Bearer k", "X-Editor": "sinama"}


@typeset_only
def test_narration_builds_missing_plan_itself(tmp_path, monkeypatch):
    import pymupdf

    from editor.production import api, preflight
    pytest.importorskip("fastapi")
    d, ms = _job(tmp_path, child=False)          # roman: planın metni el yazmasıyla kelime kelime aynı kalmalı
    pdf = d / "dizgi" / "ic-sayfalar.pdf"
    before = pymupdf.open(pdf).page_count if pdf.exists() else None
    c, h = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(N, "available", lambda: asyncio.sleep(0, True))
    assert not P.exists(d)

    # üretim hattı sürerken plan kurulmaz (hat sonunda kendisi kurar), ekran bekler
    studio.set_busy(d, {"key": "hat", "mode": "run", "workflow_id": "w"})
    r = c.get(f"/v1/studio/jobs/{d.name}/narration", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "PREPARING" and r.json()["state"] == "waiting"
    assert not P.exists(d) and P.auto_state(d) is None
    studio.set_busy(d, None)

    # ilk açılış kurulumu başlatır; ikinci istek aynı kurulumu bekler (yarış yok)
    r1 = c.get(f"/v1/studio/jobs/{d.name}/narration", headers=h)
    r2 = c.get(f"/v1/studio/jobs/{d.name}/narration", headers=h)
    assert r1.status_code == 409 and r1.json()["code"] == "PREPARING" and r1.json()["state"] == "preparing"
    assert r2.status_code in (200, 409)
    assert P.wait_auto(d, 300)
    rec = P.auto_state(d)
    assert rec["status"] == "done" and rec["by"] == "sinama" and rec["reason"] == "sesli okuma"
    assert [h_["rev"] for h_ in P.history(d)] == [1]                  # tek kurulum
    pl = P.load(d)
    assert preflight._words(P.PlanText(pl).text()) == preflight._words(ms.text().replace("## ", ""))
    if before is not None:                                            # dizgi korunur: aynı sayfa sayısı
        assert pymupdf.open(pdf).page_count == before
    ov = c.get(f"/v1/studio/jobs/{d.name}/narration", headers=h).json()
    assert ov["plan_auto"]["status"] == "done" and ov["summary"]["missing"] > 0

    # «Seslendir»: iş kuyruğa verilir, sesler üretilir (sahte ses)
    started = []

    class T:
        async def start_workflow(self, name, args, id, task_queue):
            started.append((name, args))

    async def temporal():
        return T()
    monkeypatch.setattr(api, "_temporal", temporal)
    r = c.post(f"/v1/studio/jobs/{d.name}/narration/run", headers=h, json={"pages": None})
    assert r.status_code == 200 and started[0][0] == "BookNarration"
    pids = started[0][1][2]
    monkeypatch.setattr(N, "_call", _fake_service([]))
    for pid in pids:
        assert asyncio.run(N.narrate_page(d, pid, "sinama"))["status"] == "done"
    assert N.media_overlay(d)["complete"]

    # okur ve sürüm farkı giriş uçları da plan ister; plan artık var
    assert c.get(f"/v1/studio/jobs/{d.name}/plan/versions", headers=h).status_code == 200


@typeset_only
def test_auto_plan_failure_is_reported_and_retried(tmp_path, monkeypatch):
    d, _ = _job(tmp_path, child=True)
    c, h = _client(tmp_path, monkeypatch)
    real = P.freeze

    def boom(*a, **k):
        raise ValueError("dizgi okunamadı")
    monkeypatch.setattr(P, "freeze", boom)
    assert c.get(f"/v1/studio/jobs/{d.name}/plan/reader", headers=h).json()["code"] == "PREPARING"
    assert not P.wait_auto(d, 60)
    r = c.get(f"/v1/studio/jobs/{d.name}/plan/reader", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "PLAN_FAILED" and "dizgi okunamadı" in r.json()["detail"]
    monkeypatch.setattr(P, "freeze", real)
    assert c.get(f"/v1/studio/jobs/{d.name}/plan/reader?retry=1", headers=h).json()["code"] == "PREPARING"
    assert P.wait_auto(d, 300)
    # yerleşmemiş kitapta kurulum denenmez
    (tmp_path / "bos").mkdir()
    studio.write(tmp_path / "bos", "job.json", {"id": "bos", "source": {}})
    r = c.get("/v1/studio/jobs/bos/narration", headers=h)
    assert r.status_code == 404 and r.json()["code"] == "NO_PLAN"


@typeset_only
def test_plan_screen_prepares_missing_plan(tmp_path, monkeypatch):
    """Sayfa düzeni ekranının akışı: `GET plan` «plan yok» der (otomatik kayıt bu cevaba dayanır, tetiklemez), ekran
    `POST plan/prepare` çağırır → 409 PREPARING, kurulum bitince 200 ready ve `GET plan` planı verir. Üretim hattı
    sürerken bekler; düşen kurulum PLAN_FAILED, `?retry=1` yeniler; yerleşmemiş kitapta NO_PLAN."""
    d, ms = _job(tmp_path, child=True)
    c, h = _client(tmp_path, monkeypatch)
    base = f"/v1/studio/jobs/{d.name}/plan"
    r = c.get(base, headers=h)
    assert r.status_code == 404 and r.json()["code"] == "NO_PLAN" and P.auto_state(d) is None   # GET tetiklemez
    assert c.post(base + "/prepare", headers={"Authorization": "Bearer k"}).status_code == 400    # X-Editor şart

    studio.set_busy(d, {"key": "hat", "mode": "run", "workflow_id": "w"})
    r = c.post(base + "/prepare", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "PREPARING" and r.json()["state"] == "waiting"
    assert not P.exists(d)
    studio.set_busy(d, None)

    real = P.freeze

    def boom(*a, **k):
        raise ValueError("dizgi okunamadı")
    monkeypatch.setattr(P, "freeze", boom)
    r = c.post(base + "/prepare", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "PREPARING" and r.json()["state"] == "preparing"
    assert not P.wait_auto(d, 60)
    r = c.post(base + "/prepare", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "PLAN_FAILED" and "dizgi okunamadı" in r.json()["detail"]
    monkeypatch.setattr(P, "freeze", real)

    r = c.post(base + "/prepare?retry=1", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "PREPARING"
    assert P.wait_auto(d, 300)
    r = c.post(base + "/prepare", headers=h)
    assert r.status_code == 200 and r.json() == {"status": "ready"}
    rec = P.auto_state(d)
    assert rec["status"] == "done" and rec["by"] == "sinama" and rec["reason"] == "sayfa düzeni"
    pl = c.get(base, headers=h).json()
    assert pl["rev"] == 1 and pl["pages"] and [x["rev"] for x in P.history(d)] == [1]   # tek kurulum
    # plan hazırken yeniden çağrı planı bozmaz (yeni sürüm yazılmaz)
    assert c.post(base + "/prepare", headers=h).status_code == 200 and P.load(d)["rev"] == 1

    (tmp_path / "bos").mkdir()
    studio.write(tmp_path / "bos", "job.json", {"id": "bos", "source": {}})
    r = c.post("/v1/studio/jobs/bos/plan/prepare", headers=h)
    assert r.status_code == 404 and r.json()["code"] == "NO_PLAN"


# ------------------------------------------------------------------ sesli e-kitap
def _narrated(tmp_path, monkeypatch, child: bool):
    d, ms = _job(tmp_path, child=child)
    monkeypatch.setattr(studio, "root", lambda: tmp_path)
    P.freeze(d, "sınama")
    monkeypatch.setattr(N, "_call", _fake_service([]))
    for r in N.status(d):
        if r["status"] != "empty":
            asyncio.run(N.narrate_page(d, r["id"], "sınama"))
    return d, ms


def _check_audio(z: zipfile.ZipFile, out: dict) -> None:
    opf = _opf(z)
    items = {i.get("id"): i for i in opf.findall(".//o:item", NS)}
    smils = [i for i in items.values() if i.get("media-type") == "application/smil+xml"]
    mp3 = [i for i in items.values() if i.get("media-type") == "audio/mpeg"]
    assert smils and mp3
    with_mo = [i for i in items.values() if i.get("media-overlay")]
    assert {i.get("media-overlay") for i in with_mo} == {s.get("id") for s in smils}
    metas = opf.findall(".//o:meta", NS)
    durs = {m.get("refines"): m.text for m in metas if m.get("property") == "media:duration"}
    assert None in durs and all(f"#{s.get('id')}" in durs for s in smils)
    total = sum(E._secs(v) for k, v in durs.items() if k)
    assert abs(E._secs(durs[None]) - total) < 0.01
    assert any(m.get("property") == "media:narrator" and m.text for m in metas)
    assert any(m.get("property") == "media:active-class" and m.text == E.ACTIVE_CLASS for m in metas)
    feats = [m.text for m in metas if m.get("property") == "schema:accessibilityFeature"]
    assert "synchronizedAudioText" in feats
    assert "auditory" in [m.text for m in metas if m.get("property") == "schema:accessMode"]
    # her par: XHTML'deki bir kelimeye ve paketteki bir sese; kelimenin metni sayfada aynen
    for s in smils:
        sname = "OEBPS/" + s.get("href")
        root = ET.fromstring(z.read(sname))
        for par in root.iter(f"{SMIL}par"):
            src = par.find(f"{SMIL}text").get("src")
            f, _, frag = src.partition("#")
            xname = "OEBPS/" + f.removeprefix("../")
            assert f'id="{frag}"' in z.read(xname).decode()
            a = par.find(f"{SMIL}audio")
            assert "OEBPS/" + a.get("src").removeprefix("../") in z.namelist()
            assert E._secs(a.get("clipEnd")) > E._secs(a.get("clipBegin"))
    css = "".join(z.read(n).decode() for n in z.namelist() if n.endswith(".css"))
    assert f".{E.ACTIVE_CLASS}" in css
    assert out["audio"]["on"] and out["audio"]["words"] > 0 and out["audio"]["duration"] > 0


@typeset_only
def test_fixed_layout_audio_epub(tmp_path, monkeypatch):
    d, ms = _narrated(tmp_path, monkeypatch, child=True)
    ov = N.media_overlay(d)
    assert ov["complete"]
    out = E.build(d, "fixed", "e", audio=True)
    path = d / "epub" / "kitap.epub"
    _keep(path, "sesli-sabit-sayfa.epub")
    z = zipfile.ZipFile(path)
    _check_audio(z, out)
    timed = sum(1 for pg in ov["pages"] for b in pg["blocks"] for w in b["words"] if w["start"] is not None)
    assert out["audio"]["words"] == timed and not [w for w in out["warnings"] if "eşlenemedi" in w]
    # sabit sayfada sayfa başına bir SMIL, sayfa önizlemesi SMIL yolunu bilir
    smil_pages = [p for p in out["pages"] if p.get("smil")]
    assert len(smil_pages) == len(ov["pages"])
    _no_errors(E.check(path))
    # önizleme: SMIL ve ses de içerikten döner
    E.set_state(d, status="done", result=out)
    data, mime = E.content(d, out["build"], smil_pages[0]["smil"])
    assert mime == "application/smil+xml" and b"<par" in data
    data, mime = E.content(d, out["build"], f"audio/{ov['pages'][0]['page']}.mp3")
    assert mime == "audio/mpeg" and data
    # sessiz e-kitap: kaplama yok
    out2 = E.build(d, "fixed", "e")
    z2 = zipfile.ZipFile(path)
    assert out2["audio"] is None and not [n for n in z2.namelist() if n.endswith((".smil", ".mp3"))]
    assert "w-" not in "".join(z2.read(n).decode() for n in z2.namelist() if n.endswith(".xhtml"))


@typeset_only
def test_reflow_audio_epub(tmp_path, monkeypatch):
    d, ms = _narrated(tmp_path, monkeypatch, child=False)
    out = E.build(d, "reflow", "e", audio=True)
    path = d / "epub" / "kitap.epub"
    _keep(path, "sesli-akiskan.epub")
    z = zipfile.ZipFile(path)
    _check_audio(z, out)
    # bölüm birden çok sayfanın sesini taşır; sayfa sınırından bölünen blok tek paragrafta iki kimlik takımıyla
    chapters = [p for p in out["pages"] if p["href"].startswith("text/bolum-")]
    assert all(p["smil"] for p in chapters)
    root = ET.fromstring(z.read("OEBPS/" + chapters[0]["smil"]))
    assert len({a.get("src") for a in root.iter(f"{SMIL}audio")}) > 1
    ov = N.media_overlay(d)
    timed = sum(1 for pg in ov["pages"] for b in pg["blocks"] for w in b["words"] if w["start"] is not None)
    assert out["audio"]["words"] == timed
    _no_errors(E.check(path))


@typeset_only
def test_audio_epub_needs_every_page(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    d, ms = _narrated(tmp_path, monkeypatch, child=True)
    pl = P.load(d)
    pg = next(p for p in pl["pages"] if p["text"])
    pg["text"]["blocks"][0]["runs"] = [{"text": "Bambaşka bir cümle."}]
    P.update_page(d, pg["id"], pl["rev"], pg, "e", post="none")
    with pytest.raises(ValueError, match="güncel değil"):
        E.build(d, "fixed", "e", audio=True)
    v = E.view(d)
    assert v["audio"]["ready"] is False and v["audio"]["stale"] == 1
    c, h = _client(tmp_path, monkeypatch)
    r = c.post(f"/v1/studio/jobs/{d.name}/epub", headers=h, json={"layout": "auto", "audio": True})
    assert r.status_code == 409 and r.json()["code"] == "AUDIO_INCOMPLETE"
    # yeniden seslendirilince sesli e-kitap üretilir; ses değişince e-kitap «eski» görünür
    asyncio.run(N.narrate_page(d, pg["id"], "e"))
    assert E.view(d)["audio"]["ready"]
    st = asyncio.run(E.build_job(d, "auto", "e", llm=FakeLlm(), audio=True))
    assert st["status"] == "done" and st["result"]["audio"]["on"] and not E.view(d)["stale"]
    N.set_settings(d, "anlatici-erkek", {}, "e")                        # anlatıcı değişti: sesler eskidi
    assert E.view(d)["stale"]
    assert "sesli" in E.preflight_checks(d)[0]["detail"]
