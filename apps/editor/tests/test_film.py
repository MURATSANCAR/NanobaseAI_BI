"""Kitaptan film ve reels (editor.production.film): senaryo şeması ve denetimi, çekim süresinin replikle uzaması,
adım/onay geçişleri, ses seçimi, zaman çizelgesi, altyazı, kurgu ve kesit komutları. Model yok. Kurgu komutunun gerçek
çalıştırılması ffmpeg ister; yoksa atlanır. Çalıştır:

    pytest apps/editor/tests/test_film.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class _Stub(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        sub = _Stub(f"{self.__name__}.{name}")
        sys.modules[sub.__name__] = sub
        return sub


for _mod in ("psycopg", "psycopg.rows", "psycopg.types", "psycopg.types.json", "psycopg_pool"):
    sys.modules.setdefault(_mod, _Stub(_mod))

from editor.production.film import cast as cast_mod  # noqa: E402
from editor.production.film import mix, shoot, social, spec, store  # noqa: E402

import importlib.util  # noqa: E402

# images/video/plan.py: video servisinin modelsiz hesapları (torch içe aktarmaz)
_spec = importlib.util.spec_from_file_location(
    "book_video_plan", Path(__file__).resolve().parents[1] / "images" / "video" / "plan.py")
video_plan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(video_plan)

FFMPEG = shutil.which("ffmpeg") is not None


def _shot(seconds=4, lines=None, chars=("Elif",), framing="bel", move="sabit", quote="Elif kapıyı açtı."):
    return {"seconds": seconds, "framing": framing, "move": move, "characters": list(chars),
            "action": "Elif kapıyı açar.", "action_en": "Elif opens the wooden door.", "quote": quote,
            "lines": lines or [], "sfx": ["kapı gıcırtısı"], "ambience": "orman"}


def _script(shots=None, total=None):
    shots = shots or [_shot(3, [{"speaker": "Elif", "text": "Kim var orada?", "emotion": "merakli"}])] + \
        [_shot(5) for _ in range(4)]
    return {"title": "Deneme", "logline": "Elif ormanda.",
            "cast": [{"name": "Elif", "role": "kahraman", "look_en": "a girl", "age": "cocuk", "gender": "kadin"}],
            "scenes": [{"setting": "Orman", "setting_en": "a forest", "time": "gunduz", "shots": shots}]}


# ------------------------------------------------------------------ şema ve denetim
def test_schema_shape_ok_and_errors():
    assert spec.shape_errors(_script()) == []
    bad = _script()
    bad["scenes"][0]["shots"][0]["framing"] = "uzay"
    bad["scenes"][0]["shots"][0]["extra"] = 1
    del bad["cast"]
    errs = spec.shape_errors(bad)
    assert any("cast: eksik" in e for e in errs)
    assert any("framing" in e for e in errs)
    assert any("extra: tanımsız" in e for e in errs)


def test_shot_ids_are_stable_and_scene_aware():
    sc = _script()
    sc["scenes"].append({"setting": "Ev", "setting_en": "a house", "time": "gece", "shots": [_shot(4)]})
    ids = [s["id"] for s in spec.shots(sc)]
    assert ids[:2] == ["s01c01", "s01c02"] and ids[-1] == "s02c01"
    assert spec.shots(sc)[-1]["time"] == "gece"


def test_check_flags_duration_cast_and_quote():
    sc = _script([_shot(1), _shot(12, chars=["Ali"])])
    probs = spec.check(sc, "fragman", {"Elif"}, in_book=lambda q: False)
    text = " ".join(p.text for p in probs)
    assert "Toplam süre" in text                      # 13 sn < 45*0.8
    assert "1.0 sn" in text and "12.0 sn" in text       # çekim sınırları
    assert "«Ali» oyuncu listesinde yok" in text
    assert any(not p.fatal and "kanıtsız" in p.text for p in probs)


def test_long_line_does_not_fit_shot():
    long = " ".join(["kelime"] * 30)
    probs = spec.check(_script([_shot(4, [{"speaker": "Elif", "text": long, "emotion": "notr"}])] * 5),
                       "reels", {"Elif"})
    assert any("sığmıyor" in p.text for p in spec.fatal(probs))


def test_hook_rule_only_for_social_formats():
    sc = _script([_shot(6)] * 4)
    assert any("İlk çekim" in p.text for p in spec.check(sc, "reels", {"Elif"}))
    assert not any("İlk çekim" in p.text for p in spec.check(sc, "cizgi-film", {"Elif"}))


def test_fit_seconds_grows_with_speech():
    assert spec.fit_seconds(3, []) == 3
    assert spec.fit_seconds(1, []) == spec.MIN_SHOT
    need = 2.0 + 1.5 + spec.LINE_GAP + spec.SHOT_TAIL
    assert spec.fit_seconds(3, [2.0, 1.5]) == round(need, 2)


def test_prompt_has_style_light_and_no_text_rule():
    s = {**_shot(), "time": "gece", "setting_en": "a forest"}
    p = spec.shot_prompt(s, "2b", {"Elif": "Elif: a girl with red hair."})
    assert "medium shot" in p and "moonlight" in p and "red hair" in p and "No text" in p


# ------------------------------------------------------------------ adımlar ve onay
@pytest.fixture
def film(tmp_path):
    d = tmp_path / "job"
    d.mkdir()
    return d, store.create(d, "reels", "2b", "Deneme", "test")


def test_stage_approval_and_staleness(film):
    d, f = film
    with pytest.raises(store.FilmError):
        store.require(f, "senaryo")
    store.set_stage(f, "senaryo", status="hazir")
    with pytest.raises(store.FilmError):
        store.require(f, "senaryo")                    # onay istiyor
    store.approve(f, "senaryo", True, "editör")
    store.require(f, "senaryo")
    store.set_stage(f, "oyuncular", status="hazir")
    store.approve(f, "oyuncular", True, "editör")
    store.set_stage(f, "senaryo", status="hazir")      # senaryo yeniden yazıldı
    m = store.meta(f)
    assert m["stages"]["senaryo"]["status"] == "hazir" and "approved_by" not in m["stages"]["senaryo"]
    assert m["stages"]["oyuncular"]["status"] == "eski"
    assert store.films(d)[0]["id"] == f.name
    with pytest.raises(store.FilmError):
        store.approve(f, "ses", True, "editör")         # ses onay istemez


def test_film_id_is_validated(film):
    d, _ = film
    for bad in ("../x", "f_../../", "abc", "f_" + "a" * 20):
        with pytest.raises((store.FilmError, FileNotFoundError)):
            store.fdir(d, bad)


# ------------------------------------------------------------------ oyuncular
def test_voice_pick_spreads_and_respects_roles(monkeypatch):
    monkeypatch.setattr(cast_mod, "_ok", lambda v: True)
    used: set[str] = set()
    a = cast_mod.pick_voice({"age": "yetiskin", "gender": "erkek", "role": "baba"}, used)
    used.add(a)
    b = cast_mod.pick_voice({"age": "yetiskin", "gender": "erkek", "role": "komşu"}, used)
    assert a != b
    assert cast_mod.pick_voice({"age": "yasli", "gender": "erkek", "role": "kötü büyücü"}, set()) == "karanlik-lord"
    assert cast_mod.pick_voice({"age": "yasli", "gender": "kadin", "role": "kötü cadı"}, set()) != "karanlik-lord"


def test_child_cast_uses_child_voices_with_young_fallback(monkeypatch):
    """Çocuk karakter önce çocuk sesini alır; ses onay bekliyorsa (katalogda yok) eski genç ses yedeği kalır."""
    from editor.production import narration as N
    from editor.production import voices_zeki as Z
    boy, girl = {"age": "cocuk", "gender": "erkek", "role": "kahraman"}, {"age": "cocuk", "gender": "kadin", "role": ""}
    if Z.PENDING:                                   # bugünkü durum: seçilmemiş ses genç sese gider, iki kez sayılmaz
        pend = {v["id"] for v in Z.PENDING}
        assert {"cocuk-erkek", "kucuk-erkek"} <= pend
        assert cast_mod.pick_voice(boy, set()) == "genc-erkek"
        assert cast_mod.pick_voice(boy, {"genc-erkek"}) == "masal-baba"
    # onaylanmış durum (kayıt dosyası olmadan): kimlikler katalogda, yönlendirme yok
    ids = {v["id"] for v in Z.CHILD_VOICES}
    monkeypatch.setattr(N, "ALIASES", {k: v for k, v in N.ALIASES.items() if k not in ids})
    monkeypatch.setattr(N, "VOICE_IDS", N.VOICE_IDS | ids)
    used: set[str] = set()
    a = cast_mod.pick_voice(boy, used)
    used.add(a)
    b = cast_mod.pick_voice({**boy, "role": "kardeş"}, used)
    assert (a, b) == ("cocuk-erkek", "kucuk-erkek")
    assert cast_mod.pick_voice(girl, set()) == "cocuk-kiz"
    assert cast_mod.pick_voice({**girl, "look_en": "a five-year-old girl with pigtails"}, set()) == "kucuk-kiz"
    assert cast_mod.pick_voice({**boy, "look_en": "a little boy in a school uniform"}, set()) == "cocuk-erkek"
    assert cast_mod.pick_voice({"age": "genc", "gender": "erkek"}, set()) == "genc-erkek"


def test_voice_of_falls_back_to_narrator():
    rec = {"narrator": "roman-kadin", "members": [{"name": "Elif", "voice": "genc-kadin"}]}
    assert cast_mod.voice_of(rec, "elif") == "genc-kadin"
    assert cast_mod.voice_of(rec, "anlatıcı") == "roman-kadin"
    assert cast_mod.voice_of(rec, "Bilinmeyen") == "roman-kadin"


# ------------------------------------------------------------------ çekim kipi
def test_talking_mode_only_for_single_speaker_close_shot():
    one = [{"speaker": "Elif"}]
    assert shoot.mode_of(_shot(framing="yakin"), one) == "s2v"
    assert shoot.mode_of(_shot(framing="genel"), one) == "i2v"
    assert shoot.mode_of(_shot(framing="yakin", chars=["Elif", "Ali"]), one) == "i2v"
    assert shoot.mode_of(_shot(framing="yakin"), [{"speaker": "anlatıcı"}]) == "i2v"


# ------------------------------------------------------------------ kurgu
def _voice(sc):
    lines, secs = {}, {}
    for s in spec.shots(sc):
        ls = [{"file": f"{s['id']}-{i}.wav", "duration": 1.2, "text": x["text"], "speaker": x["speaker"]}
              for i, x in enumerate(s["lines"])]
        lines[s["id"]] = ls
        secs[s["id"]] = spec.fit_seconds(s["seconds"], [x["duration"] for x in ls])
    return {"lines": lines, "seconds": secs}


def test_timeline_places_lines_and_ambience():
    sc = _script([_shot(3, [{"speaker": "Elif", "text": "Merhaba.", "emotion": "notr"},
                            {"speaker": "Elif", "text": "Kim var?", "emotion": "merakli"}]), _shot(4)])
    v = _voice(sc)
    tl = mix.timeline(sc, v, {s["id"]: f"{s['id']}.mp4" for s in spec.shots(sc)},
                      {"sfx": {"s01c02": ["/x/kapi.wav"]}, "amb": {"1": "/x/orman.wav"}})
    a, b = tl["shots"]
    assert a["lines"][1]["start"] == round(1.2 + spec.LINE_GAP, 3)
    assert b["start"] == a["seconds"] and b["sfx"][0]["start"] == round(b["start"] + 0.2, 3)
    assert tl["ambience"] == [{"file": "/x/orman.wav", "start": 0.0, "seconds": tl["total"]}]


def test_srt_wraps_two_lines_and_times():
    sc = _script([_shot(6, [{"speaker": "Elif", "text": "Bu çok uzun bir cümle; ekranda iki satıra bölünmeli ki "
                                                         "telefonda rahat okunsun.", "emotion": "notr"}])])
    tl = mix.timeline(sc, _voice(sc), {"s01c01": "a.mp4"}, {})
    out = mix.srt(tl, "9:16")
    assert out.startswith("1\n00:00:00,000 --> 00:00:01,200\n")
    assert len(out.split("\n")[2]) <= mix.SUB_CHARS["9:16"] and out.count("\n") >= 4


def test_command_has_ducking_loudness_and_burned_subs(tmp_path):
    sc = _script([_shot(3, [{"speaker": "Elif", "text": "Merhaba.", "emotion": "notr"}])])
    tl = mix.timeline(sc, _voice(sc), {"s01c01": "a.mp4"}, {"sfx": {"s01c01": ["/x/k.wav"]}, "amb": {"1": "/x/o.wav"}})
    args = mix.command(tl, "reels", tmp_path, tmp_path / "o.mp4", tmp_path / "f.srt")
    g = args[args.index("-filter_complex") + 1]
    assert "sidechaincompress" in g and "loudnorm=I=-14.0" in g and "subtitles=" in g
    assert "-stream_loop" in args and "scale=1080:1920" in g
    g2 = mix.command(tl, "cizgi-film", tmp_path, tmp_path / "o.mp4", tmp_path / "f.srt")
    assert "subtitles=" not in g2[g2.index("-filter_complex") + 1]


def test_social_cut_letterboxes_with_blur_only_when_aspect_differs(tmp_path):
    same = social.cut_command(tmp_path / "f.mp4", "9:16", "tiktok", 40, tmp_path / "o.mp4")
    other = social.cut_command(tmp_path / "f.mp4", "16:9", "instagram-reels", 120, tmp_path / "o.mp4")
    assert "gblur" not in " ".join(same) and "gblur" in " ".join(other)
    assert other[other.index("-t") + 1] == "90" and "fade=t=out" in " ".join(other)


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg yok")
def test_command_runs_end_to_end(tmp_path):
    def run(*a):
        subprocess.run(["ffmpeg", "-v", "error", "-y", *a], check=True)
    run("-f", "lavfi", "-i", "testsrc=size=320x180:rate=16", "-t", "2", str(tmp_path / "a.mp4"))
    run("-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(tmp_path / "s01c01-0.wav"))
    run("-f", "lavfi", "-i", "anoisesrc=d=1:a=0.05", str(tmp_path / "amb.wav"))
    sc = _script([_shot(3, [{"speaker": "Elif", "text": "Merhaba.", "emotion": "notr"}])])
    v = _voice(sc)
    v["lines"]["s01c01"][0]["file"] = "s01c01-0.wav"
    tl = mix.timeline(sc, v, {"s01c01": str(tmp_path / "a.mp4")}, {"amb": {"1": str(tmp_path / "amb.wav")}})
    (tmp_path / "f.srt").write_text(mix.srt(tl, "16:9"))
    out = tmp_path / "o.mp4"
    subprocess.run(mix.command(tl, "cizgi-film", tmp_path, out, tmp_path / "f.srt"), check=True)
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height",
                                       "-of", "json", str(out)], capture_output=True, text=True).stdout)
    assert abs(float(probe["format"]["duration"]) - tl["total"]) < 0.2
    assert {"width": 1920, "height": 1080} in [{k: s[k] for k in ("width", "height")}
                                                for s in probe["streams"] if "width" in s]


# ------------------------------------------------------------------ video servisi: motor, kare, tuval, lisans
def test_wan_frames_for_chunks_overlap_and_are_4n_plus_1():
    assert video_plan.frames_for(2) == [33]
    parts = video_plan.frames_for(10)                 # 161 kare → 81 + 81 (bir kare örtüşür)
    assert parts == [81, 81] and all((n - 1) % 4 == 0 and n <= 81 for n in parts)
    assert sum(parts) - (len(parts) - 1) >= round(10 * video_plan.WAN_FPS) + 1


def test_h3_frames_snap_to_17n_plus_5_within_5_to_15_seconds():
    assert video_plan.h3_frames(2.0) == 124            # 5 sn altı: en az 124, sunucu keser
    assert video_plan.h3_frames(5.0) == 124
    assert video_plan.h3_frames(10.0) == 243           # 240 → 17·14+5
    assert video_plan.h3_frames(15.0) == 345           # 362 = 15,08 sn reddedilir
    for s in (2, 4.4, 6.1, 9.9, 12, 15):
        n = video_plan.h3_frames(s)
        assert n % 17 == 5 and 120 <= n <= 360


def test_h3_canvas_matches_diffusers_rule():
    assert video_plan.h3_canvas(1280, 720) == (1344, 768)          # 16:9, alan tavanı 768×1344
    assert video_plan.h3_canvas(720, 1280) == (768, 1344)
    assert video_plan.h3_canvas(1280, 720, short_edge=544) == (960, 544)   # FastH3 H100 ölçü tuvali
    w, h = video_plan.h3_canvas(1080, 1080)
    assert w == h == 768
    with pytest.raises(ValueError):
        video_plan.h3_canvas(1920, 256)


def test_engine_task_choice_and_prompt():
    assert video_plan.h3_task("h3", "i2v", 3) == "fl2va"
    assert video_plan.h3_task("h3", "s2v", 2) == "ref2va"
    assert video_plan.h3_task("fast-h3", "s2v", 2) == "fl2va+audio"     # FastH3'te ref2va yok
    assert video_plan.worker_of("fast-h3") == "fasth3" and video_plan.worker_of("wan2.2") == "wan"
    p = video_plan.h3_prompt("ref2va", "close-up, a girl at the door.", 2)
    assert "<Picture 1> is the first frame" in p and "<Picture 3>" in p and "fully_copy" in p
    q = video_plan.h3_prompt("fl2va", "x", 0)
    assert q.startswith("For the target video") and "nobody speaks" in q


def test_default_engine_and_license_gate(monkeypatch):
    monkeypatch.delenv("VIDEO_ENGINE", raising=False)
    monkeypatch.delenv("VIDEO_LICENSED_ENGINES", raising=False)
    assert video_plan.default_engine() == "h3"                       # kullanıcı kararı 2026-10-07
    assert all(video_plan.license_error(e) is None for e in video_plan.ENGINES)   # varsayılan hepsi açık
    monkeypatch.setenv("VIDEO_LICENSED_ENGINES", "wan2.2")
    assert "lisans ayarıyla kapalı" in video_plan.license_error("h3") and video_plan.license_error("fast-h3")
    monkeypatch.setenv("VIDEO_LICENSED_ENGINES", "h3, bilinmeyen")
    assert video_plan.license_error("h3") is None and video_plan.license_error("fast-h3")
    assert video_plan.licensed_engines() == {"wan2.2", "h3"}          # wan2.2 Apache-2.0: her zaman açık
    monkeypatch.setenv("VIDEO_ENGINE", "sora")
    with pytest.raises(ValueError):
        video_plan.default_engine()


def test_enhance_params():
    assert video_plan.target_size(1280, 720, "1080p") == (1920, 1080)
    assert video_plan.target_size(720, 1280, "4k") == (2160, 3840)
    assert video_plan.rife_multi(24, 24) == 1 and video_plan.rife_multi(16, 24) == 3
    assert video_plan.rife_multi(24, 30) == 2 and video_plan.rife_multi(16, 30) == 2
    assert video_plan.rife_scale(2160, 3840) == 0.5 and video_plan.rife_scale(1080, 1920) == 1.0
    a = video_plan.seedvr2_args("i.mp4", "o.mp4", "/m", "4k", 120)
    assert a[a.index("--resolution") + 1] == "2160" and "--vae_decode_tiled" in a
    assert a[a.index("--dit_model") + 1] == "seedvr2_ema_7b_sharp_fp16.safetensors"
    assert (int(a[a.index("--batch_size") + 1]) - 1) % 4 == 0
    b = video_plan.seedvr2_args("i.mp4", "o.mp4", "/m", "1080p", 17)
    assert int(b[b.index("--batch_size") + 1]) == 17 and "--vae_decode_tiled" not in b
    assert shoot.ENHANCE_FPS == mix.FPS


# ------------------------------------------------------------------ istemci: gövde, iyileştirme, kurgu seçimi
def _shot_film(f, ids=("s01c01", "s01c02")):
    (f / "cekim").mkdir(exist_ok=True)
    rec = {"shots": {}}
    for sid in ids:
        (f / "cekim" / f"{sid}.v1.mp4").write_bytes(b"raw")
        rec["shots"][sid] = {"versions": [{"v": 1, "file": f"{sid}.v1.mp4", "mode": "i2v", "qc": {"ok": True}}],
                             "selected": 1}
    store.write(f, "cekimler.json", rec)


def test_body_engine_override_and_refs_only_for_talking_shots(film, monkeypatch):
    _, f = film
    (f / "kare").mkdir()
    (f / "kare" / "oyuncu-00.png").write_bytes(b"png-elif")
    store.write(f, "oyuncular.json", {"rev": 1, "narrator": "x", "members": [
        {"name": "Elif", "look_en": "a girl", "ref": None}, {"name": "Ali", "look_en": "a boy", "ref": None}]})
    first = f / "kare" / "first.png"
    first.write_bytes(b"first")
    monkeypatch.setattr(shoot, "talk_track", lambda *a: b"wav")
    monkeypatch.delenv("EDITOR_VIDEO_ENGINE", raising=False)
    b = shoot.body_for(f, {**_shot(framing="yakin"), "id": "s01c01"}, first, "i2v", 3.0, 1280, 720, "2b", [])
    assert "engine" not in b and "refs" not in b and "audio" not in b
    monkeypatch.setenv("EDITOR_VIDEO_ENGINE", "h3")
    b = shoot.body_for(f, {**_shot(framing="yakin", chars=("Elif", "Ali")), "id": "s01c01"}, first, "s2v", 3.0,
                       1280, 720, "2b", [{"speaker": "Elif"}])
    assert b["engine"] == "h3" and b["audio"] and len(b["refs"]) == 1     # Ali'nin görseli yok: atlanır


def test_enhance_saves_hd_once_and_mix_prefers_it(film, monkeypatch):
    import asyncio
    import base64
    _, f = film
    _shot_film(f)
    calls = []

    async def ok(http, mp4, target):
        calls.append(target)
        return {"video": base64.b64encode(b"hd").decode(), "width": 1920, "height": 1080, "fps": 24,
                "engine": "seedvr2-7b-sharp"}
    monkeypatch.setattr(shoot, "_enhance_call", ok)
    monkeypatch.delenv("EDITOR_FILM_ENHANCE", raising=False)
    monkeypatch.delenv("EDITOR_FILM_ENHANCE_TARGET", raising=False)
    res = asyncio.run(shoot.enhance_selected(f, None))
    assert res == {"done": 2, "total": 2, "error": None} and calls == ["1080p", "1080p"]
    assert (f / "cekim" / "s01c01.v1.hd.mp4").read_bytes() == b"hd"
    assert asyncio.run(shoot.enhance_selected(f, None))["done"] == 2 and len(calls) == 2   # bir kez
    videos, hd = mix.pick_videos(f, ["s01c01", "s01c02"])
    assert hd == 2 and videos["s01c02"].endswith("s01c02.v1.hd.mp4")


def test_enhance_failure_falls_back_to_raw_and_is_reported(film, monkeypatch):
    import asyncio
    _, f = film
    _shot_film(f)

    async def down(http, mp4, target):
        raise shoot.VideoUnavailable("iyileştirme servisi bu kurulumda açık değil")
    monkeypatch.setattr(shoot, "_enhance_call", down)
    monkeypatch.delenv("EDITOR_FILM_ENHANCE", raising=False)
    res = asyncio.run(shoot.enhance_selected(f, None))
    assert res["done"] == 0 and res["total"] == 2 and "açık değil" in res["error"]
    rec = store.read(f, "cekimler.json")
    assert "açık değil" in rec["shots"]["s01c01"]["versions"][0]["hd_error"]
    assert "hd_error" not in rec["shots"]["s01c02"]["versions"][0]               # servis yok: kalan denenmedi
    videos, hd = mix.pick_videos(f, ["s01c01", "s01c02"])
    assert hd == 0 and videos["s01c01"].endswith("s01c01.v1.mp4")
    monkeypatch.setenv("EDITOR_FILM_ENHANCE", "0")
    assert asyncio.run(shoot.enhance_selected(f, None))["error"].startswith("iyileştirme kapalı")
