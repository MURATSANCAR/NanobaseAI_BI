"""Kitaptan film ve reels (editor.production.film): senaryo şeması ve denetimi, çekim süresinin replikle uzaması,
adım/onay geçişleri, ses seçimi, zaman çizelgesi, altyazı, kurgu ve kesit komutları, sahne müziği (plan, çapraz geçiş,
konuşmada kısma, servis yokken müziksiz kurgu). Model yok. Kurgu komutunun gerçek
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
from editor.production.film import mix, music, shoot, social, spec, store  # noqa: E402
from editor.production.film import script as script_mod  # noqa: E402

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


def test_transformed_child_voice_line_has_own_key_and_transform():
    """Dönüşümlü erkek çocuk sesi (voices_zeki.TRANSFORMS): replik kaynak sesin (masal-anne) referansıyla ve dönüşümle
    servise gider; önbellek anahtarı kaynak sesin aynı replikteki anahtarından ayrıdır, dönüşümsüz seslerin anahtarı
    değişmez (eski replikler yeniden okunmaz)."""
    import asyncio
    import hashlib

    from editor.production import narration as N
    from editor.production.film import dialogue
    boy, src = asyncio.run(N.voice_ref("cocuk-erkek")), asyncio.run(N.voice_ref("masal-anne"))
    assert boy["ref_audio"] == src["ref_audio"] and boy["transform"]["path"] == "world"
    assert dialogue._key(boy, "kardan adam", "notr") != dialogue._key(src, "kardan adam", "notr")
    old = hashlib.sha256(json.dumps({"v": dialogue.VERSION, "ref": hashlib.sha256(src["ref_audio"].encode()).hexdigest(),
                                     "t": "kardan adam", "e": "notr"}, sort_keys=True).encode()).hexdigest()[:20]
    assert dialogue._key(src, "kardan adam", "notr") == old
    seg, piece = dialogue.segment("kardan adam", boy, "cocuk-erkek", "neseli")
    assert seg["voice"]["transform"] == boy["transform"] and piece.voice == "cocuk-erkek"
    assert cast_mod.pick_voice({"age": "cocuk", "gender": "erkek", "role": "kahraman"}, set()) == "cocuk-erkek"


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
    for fast in ("fast-h3", "fast-h3-fp8"):                            # V2 yalnız t2va damıtıldı
        assert video_plan.h3_task(fast, "i2v", 2) == "t2va"
        assert video_plan.h3_task(fast, "s2v", 2) == "unsupported"
        assert video_plan.worker_of(fast) == "fasth3"
    assert video_plan.worker_of("wan2.2") == "wan" and set(video_plan.FAST) < set(video_plan.ENGINES)
    with pytest.raises(ValueError):
        video_plan.h3_task("wan2.2", "i2v", 0)
    p = video_plan.h3_prompt("ref2va", "close-up, a girl at the door.", 2)
    assert "<Picture 1> is the first frame" in p and "<Picture 3>" in p and "fully_copy" in p
    q = video_plan.h3_prompt("fl2va", "x", 0)
    assert q.startswith("For the target video") and "nobody speaks" in q
    t = video_plan.h3_prompt("t2va", "x", 0)
    assert t.startswith("integrated_multimodal_description") and "<Picture" not in t


def test_default_engine_and_license_gate(monkeypatch):
    monkeypatch.delenv("VIDEO_ENGINE", raising=False)
    monkeypatch.delenv("VIDEO_LICENSED_ENGINES", raising=False)
    assert video_plan.default_engine() == "h3"                       # kullanıcı kararı 2026-10-07
    assert all(video_plan.license_error(e) is None for e in video_plan.ENGINES)   # varsayılan hepsi açık
    monkeypatch.setenv("VIDEO_LICENSED_ENGINES", "wan2.2")
    assert "lisans ayarıyla kapalı" in video_plan.license_error("h3") and video_plan.license_error("fast-h3-fp8")
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

    async def ok(http, mp4, target, alias=None):
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

    async def down(http, mp4, target, alias=None):
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


# ------------------------------------------------------------------ müzik
def _three_scenes():
    sc = _script([_shot(3, [{"speaker": "Elif", "text": "Merhaba.", "emotion": "neseli"}]), _shot(4)])
    sc["scenes"].append({"setting": "Ev", "setting_en": "a house", "time": "aksam", "shots": [_shot(5), _shot(2)]})
    sc["scenes"].append({"setting": "Göl", "setting_en": "a lake", "time": "gece", "shots": [_shot(6)]})
    return sc


def test_music_scene_plan_matches_timeline_scene_spans():
    sc = _three_scenes()
    v = _voice(sc)
    plan = music.scene_plan(sc, v)
    tl = mix.timeline(sc, v, {s["id"]: "a.mp4" for s in spec.shots(sc)}, {})
    assert [p["scene"] for p in plan] == [1, 2, 3]
    assert plan[1]["start"] == tl["shots"][2]["start"] and plan[2]["start"] == tl["shots"][4]["start"]
    assert round(sum(p["seconds"] for p in plan), 3) == tl["total"]
    assert plan[0]["emotions"] == ["neseli"] and plan[1]["setting"] == "Ev"
    assert tl["music"] == []                                     # müzik verilmedi: iz boş


def test_music_track_crossfades_only_between_scored_neighbours():
    sc = _three_scenes()
    v = _voice(sc)
    plan = music.scene_plan(sc, v)
    tl = mix.timeline(sc, v, {s["id"]: "a.mp4" for s in spec.shots(sc)}, {}, {"1": "/m/1.wav", "2": "/m/2.wav"})
    a, b = tl["music"]
    half = music.XFADE / 2
    end1 = plan[0]["start"] + plan[0]["seconds"]
    end2 = plan[1]["start"] + plan[1]["seconds"]
    assert a["start"] == 0 and a["fade_in"] == mix.MUSIC_EDGE              # film başı: yumuşak açılış
    assert round(a["start"] + a["seconds"], 3) == round(end1 + half, 3)     # sınırı yarım geçiş taşar
    assert b["start"] == round(end1 - half, 3)                              # öbürü yarım geçiş önce başlar
    assert a["fade_out"] == music.XFADE and b["fade_in"] == music.XFADE     # üst üste binen kısım = çapraz geçiş
    assert round(b["start"] + b["seconds"], 3) == round(end2, 3)            # 3. sahne müziksiz: taşma yok
    assert b["fade_out"] == half


def test_music_bus_is_ducked_under_dialogue():
    sc = _three_scenes()
    tl = mix.timeline(sc, _voice(sc), {s["id"]: "a.mp4" for s in spec.shots(sc)}, {}, {"1": "/m/1.wav"})
    args = mix.command(tl, "cizgi-film", Path("/v"), Path("/o.mp4"), None)
    g = args[args.index("-filter_complex") + 1]
    assert f"volume={mix.MUSIC_DB}dB" in g and f"sidechaincompress={mix.MUSIC_DUCK}[mud]" in g
    assert "[dlg]asplit=3[dlg1][dlg2][dlg3]" in g and "[dlg1][fxd][mud]amix=inputs=3" in g
    assert args.count("/m/1.wav") == 1 and args[args.index("/m/1.wav") - 3] == "-stream_loop"


def test_command_without_music_is_unchanged():
    sc = _script([_shot(3, [{"speaker": "Elif", "text": "Merhaba.", "emotion": "notr"}])])
    picks = {"sfx": {"s01c01": ["/x/k.wav"]}, "amb": {"1": "/x/o.wav"}}
    tl = mix.timeline(sc, _voice(sc), {"s01c01": "a.mp4"}, picks)
    old = {k: v for k, v in tl.items() if k != "music"}                    # müzik alanı öncesi zaman çizelgesi
    base = mix.command(old, "reels", Path("/v"), Path("/o.mp4"), Path("/f.srt"))
    assert mix.command(tl, "reels", Path("/v"), Path("/o.mp4"), Path("/f.srt")) == base
    tl2 = mix.timeline(sc, _voice(sc), {"s01c01": "a.mp4"}, picks, {})
    assert mix.command(tl2, "reels", Path("/v"), Path("/o.mp4"), Path("/f.srt")) == base
    T = tl["total"]
    g = base[base.index("-filter_complex") + 1]
    assert g.endswith(f"[dlg]asplit=2[dlg1][dlg2];[fxb][dlg2]sidechaincompress={mix.DUCK}[fxd];"
                      f"[dlg1][fxd]amix=inputs=2:normalize=0:duration=longest,atrim=0:{T},"
                      f"loudnorm=I=-14.0:TP=-1.5:LRA=11[aout]")
    assert "[m" not in g and "sil2" not in g


def test_music_cues_fit_the_scene_plan():
    plan = [{"scene": 1, "start": 0.0, "seconds": 7.0}, {"scene": 2, "start": 7.0, "seconds": 9.0},
            {"scene": 3, "start": 16.0, "seconds": 6.0}]
    raw = [{"scene": 2, "music": True, "prompt_en": "soft strings", "mood": "hüzün", "bpm": 300, "key": "D minor"},
           {"scene": 9, "music": True, "prompt_en": "x", "mood": "", "bpm": 90, "key": ""},
           {"scene": 1, "music": True, "prompt_en": "  ", "mood": "", "bpm": 90, "key": ""},
           {"scene": 2, "music": False, "prompt_en": "ikinci kayıt yok sayılır", "mood": "", "bpm": 90, "key": ""}]
    cues = music.clean_cues(raw, plan)
    assert [c["scene"] for c in cues] == [1, 2, 3]
    assert cues[0]["music"] is False and cues[2]["music"] is False        # boş tarif, eksik sahne
    assert cues[1]["music"] and cues[1]["bpm"] == music.MAX_BPM and cues[1]["key"] == "D minor"
    assert music.piece_seconds(cues[1]) == 9.0 + music.XFADE


def _ready_film(film):
    d, f = film
    sc = _three_scenes()
    script_mod.save(f, sc, "test", [])
    store.write(f, "ses.json", _voice(sc))
    store.set_stage(f, "cekim", status="hazir")
    return d, f


def test_music_skipped_silently_without_service(film, monkeypatch):
    import asyncio
    d, f = _ready_film(film)

    async def no():
        return False
    monkeypatch.setattr(music, "available", no)
    res = asyncio.run(music.build(d, f, "test"))
    assert res["music"] == "yok" and not (f / "muzik.json").exists()
    assert music.scene_files(f, res) == {}


def test_music_build_saves_and_reuses_pieces(film, monkeypatch, tmp_path):
    import asyncio
    import base64
    d, f = _ready_film(film)
    calls, asks = [], []

    async def yes():
        return True

    async def cues(d_, f_, plan, theme, llm=None):
        asks.append(theme)
        return {"cues": music.clean_cues([{"scene": p["scene"], "music": p["scene"] != 3, "prompt_en": "calm piano",
                                           "mood": "sakin", "bpm": 80, "key": "C major"} for p in plan], plan),
                "theme": {"title": "Elif", "lyrics": "[Chorus]\nElif, Elif", "style": "children's pop"}
                if theme else None}

    async def call(http, body):
        calls.append(body)
        return {"audio": base64.b64encode(b"RIFFfake").decode(), "seconds": body["seconds"], "engine": "e"}

    async def rel(http):
        return None
    monkeypatch.setattr(music, "available", yes)
    monkeypatch.setattr(music, "write_cues", cues)
    monkeypatch.setattr(music, "_call", call)
    monkeypatch.setattr(music, "release", rel)
    res = asyncio.run(music.build(d, f, "test", theme=True))
    assert res["music"] == "var" and len(calls) == 3                      # iki sahne + tema şarkısı
    assert [c["kind"] for c in calls] == ["score", "score", "song"] and calls[0]["bpm"] == 80
    assert set(music.scene_files(f, res)) == {"1", "2"} and (f / "muzik" / "tema.wav").is_file()
    again = asyncio.run(music.build(d, f, "test", theme=True))             # girdi aynı: model ve üretim yok
    assert len(calls) == 3 and asks == [True] and again["music"] == "var"


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg yok")
def test_command_with_music_runs_end_to_end(tmp_path):
    def run(*a):
        subprocess.run(["ffmpeg", "-v", "error", "-y", *a], check=True)
    run("-f", "lavfi", "-i", "testsrc=size=320x180:rate=16", "-t", "2", str(tmp_path / "a.mp4"))
    run("-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(tmp_path / "s01c01-0.wav"))
    run("-f", "lavfi", "-i", "sine=frequency=220:duration=2", str(tmp_path / "m1.wav"))
    run("-f", "lavfi", "-i", "sine=frequency=330:duration=9", str(tmp_path / "m2.wav"))
    sc = _script([_shot(3, [{"speaker": "Elif", "text": "Merhaba.", "emotion": "notr"}])])
    sc["scenes"].append({"setting": "Ev", "setting_en": "a house", "time": "gece", "shots": [_shot(4)]})
    v = _voice(sc)
    v["lines"]["s01c01"][0]["file"] = "s01c01-0.wav"
    videos = {s["id"]: str(tmp_path / "a.mp4") for s in spec.shots(sc)}
    tl = mix.timeline(sc, v, videos, {}, {"1": str(tmp_path / "m1.wav"), "2": str(tmp_path / "m2.wav")})
    out = tmp_path / "o.mp4"
    subprocess.run(mix.command(tl, "cizgi-film", tmp_path, out, None), check=True)   # m1 kısa: döngüyle dolar
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json",
                                       str(out)], capture_output=True, text=True).stdout)
    assert abs(float(probe["format"]["duration"]) - tl["total"]) < 0.2

# ------------------------------------------------------------------ tam metin, süre hedefi, kitaba bağlılık
def test_target_seconds_scales_with_book_for_cartoon_only():
    assert spec.target_seconds("cizgi-film", 520) > 300          # 16 sayfalık resimli kitap ~5–7 dk
    assert spec.target_seconds("cizgi-film", 10) == spec.FORMATS["cizgi-film"]["min_sec"]
    assert spec.target_seconds("cizgi-film", 10**6) == spec.FORMATS["cizgi-film"]["max_sec"]
    assert spec.target_seconds("reels", 520) == (15 + 90) // 2


def test_short_film_and_ungrounded_shots_are_fatal_with_target():
    sc = _script([_shot(5) for _ in range(12)])                    # 60 sn
    probs = spec.check(sc, "cizgi-film", {"Elif"}, in_book=lambda q: False, target=360, grounded_min=0.75)
    texts = [p.text for p in spec.fatal(probs)]
    assert any("hedef yaklaşık 360" in t for t in texts)
    assert any("0/12" in t for t in texts)
    ok = spec.check(sc, "cizgi-film", {"Elif"}, in_book=lambda q: True, target=70, grounded_min=0.75)
    assert not spec.fatal(ok)


def test_silent_script_and_monotone_camera_are_fatal_when_asked():
    sc = _script([_shot(5, framing="genel") for _ in range(6)])
    probs = spec.check(sc, "cizgi-film", {"Elif"}, voiced_min=0.7)
    texts = " ".join(p.text for p in spec.fatal(probs))
    assert "0/6 tanesinde ses" in texts and "üst üste 4 kez" in texts
    assert not any("ses var" in p.text for p in spec.check(sc, "cizgi-film", {"Elif"}))   # varsayılan kapalı


def test_first_person_narration_is_added_from_book_sentences():
    from editor.production.film import script as sm
    text = "Annem bana kalem aldı. Ben resim yaptım. Kardeşim de yaptı. - Ben de resim, dedi Mert."
    sc = _script([_shot(3, quote="Ben resim yaptım."), _shot(3, quote="- Ben de resim, dedi Mert."),
                  _shot(3, [{"speaker": "Elif", "text": "Merhaba.", "emotion": "notr"}], quote="Annem bana kalem aldı.")])
    sc["cast"][0]["role"] = "kahraman"
    assert sm.first_person(text) and sm.narrator_of(sc, text) == "Elif"
    assert sm.add_narration(sc, "Elif") == 1                      # konuşma cümlesi ve replikli çekim atlanır
    first = spec.shots(sc)[0]
    assert first["lines"][0] == {"speaker": "Elif", "text": "Ben resim yaptım.", "emotion": "notr"}
    assert not sm.first_person("Ayşe parka gitti. Kedi ağaca çıktı. Rüzgâr esiyordu.")
    assert sm.narrator_of(sc, "Ayşe parka gitti. Kedi ağaca çıktı.") == spec.NARRATOR


def test_book_cast_consolidate_drops_misnamed_detections():
    from editor.production.film import book_cast as bc
    found = [{"name": "Levent", "sure": True, "hair": "orange messy", "top": "yellow sweater", "area": 0.2, "page": 3},
             {"name": "Levent", "sure": True, "hair": "orange spiky", "top": "yellow sweater", "area": 0.3, "page": 5},
             {"name": "Levent", "sure": False, "hair": "blond curly", "top": "green sweater", "area": 0.4, "page": 7},
             {"name": "Mert", "sure": True, "hair": "blond curly", "top": "green sweater", "area": 0.1, "page": 3}]
    g = bc.consolidate(found)
    assert [p["page"] for p in g["Levent"]] == [5, 3]           # yanlış adlandırılan (sarı saç, yeşil kazak) elendi
    assert [p["page"] for p in g["Mert"]] == [3]


def test_qc_decision_is_made_in_code_from_yes_no_answers():
    from editor.production.film import frames as fr
    clean = {"has_text": False, "deformed": False, "extra_copy": False, "action_shown": True,
             "characters": [{"name": "Levent", "present": True, "matches": True}]}
    assert fr.qc_result(clean, ["Levent"]) == {"ok": True, "problems": []}
    bad = {**clean, "extra_copy": True, "characters": [{"name": "levent", "present": True, "matches": False}]}
    r = fr.qc_result(bad, ["Levent", "Mert"])
    assert r["ok"] is False and len(r["problems"]) == 3     # kopya, Levent uymuyor, Mert yok


def test_ref_note_names_references_in_order_and_counts_people():
    from editor.production.film import frames as fr
    n = fr.ref_note(["Levent", "Mert"], ["Levent", "Mert", "Anne"])
    assert "reference image 1 shows Levent; reference image 2 shows Mert" in n
    assert "exactly 3 people (Levent, Mert, Anne)" in n and "no duplicates" in n


def test_best_picks_first_pass_else_fewest_problems():
    from editor.production.film import frames as fr
    assert fr.best([{"ok": False, "problems": ["a"]}, {"ok": True, "problems": []}, {"ok": None}]) == 1
    assert fr.best([{"ok": False, "problems": ["a", "b"]}, {"ok": False, "problems": ["c"]}]) == 1
    assert fr.best([{"ok": None, "problems": []}, {"ok": True, "problems": []}]) == 0


def test_on_screen_adds_mentioned_cast_but_not_possessives():
    cast = [{"name": "Levent", "role": "kahraman"}, {"name": "Mert", "role": "kardeş"}, {"name": "Anne", "role": "anne"}]
    sh = {"characters": ["Anne"], "action_en": "Mother hangs Levent's drawings. Mert looks at his drawing."}
    assert spec.on_screen(sh, cast) == ["Anne", "Mert"]
    sh = {"characters": ["Mert"], "action_en": "Mert comes out. His mother runs to him."}
    assert spec.on_screen(sh, cast) == ["Mert", "Anne"]
    sh = {"characters": ["Anne"], "action_en": "Mother looks at Levent and speaks."}
    assert spec.on_screen(sh, cast) == ["Anne", "Levent"]


def test_pick_best_prefers_first_pass_for_current_frame(tmp_path):
    def v(n, ff, ok, probs=()):
        return {"v": n, "file": f"x.v{n}.mp4", "first_frame": ff, "qc": {"ok": ok, "problems": list(probs)}}
    store.write(tmp_path, "cekimler.json", {"shots": {"s01c01": {"selected": 4, "versions": [
        v(1, "old.png", True), v(2, "new.png", False, ["a", "b"]), v(3, "new.png", False, ["a"]),
        v(4, "new.png", False, ["a", "b", "c"])]}}})
    assert shoot._pick_best(tmp_path, "s01c01") is False
    assert store.read(tmp_path, "cekimler.json")["shots"]["s01c01"]["selected"] == 3
    rec = store.read(tmp_path, "cekimler.json")
    rec["shots"]["s01c01"]["versions"].append(v(5, "new.png", True))
    store.write(tmp_path, "cekimler.json", rec)
    assert shoot._pick_best(tmp_path, "s01c01") is True
    assert store.read(tmp_path, "cekimler.json")["shots"]["s01c01"]["selected"] == 5


def test_pick_sounds_resolves_files_from_catalog_rows(monkeypatch):
    from editor.production import sfx_library as L
    rows = {"a1": {"id": "a1", "path": "x/kalem.wav"}, "o1": {"id": "o1", "path": "y/oda.wav"}}
    monkeypatch.setattr(L, "available", lambda: True)
    monkeypatch.setattr(L, "search", lambda q, kind=None, k=1: [{"id": "a1" if kind == "anlik" else "o1", "score": 0.5}])
    monkeypatch.setattr(L, "get", lambda sid: rows[sid])
    monkeypatch.setattr(L, "file_of", lambda row: Path("/havuz") / row["path"])
    sc = {"scenes": [{"shots": [{"sfx": ["kalem sesi"], "ambience": "oda"}]}]}
    p = mix.pick_sounds(sc)
    assert p["sfx"]["s01c01"] == ["/havuz/x/kalem.wav"]
    assert p["amb"]["1"] == "/havuz/y/oda.wav"


def test_pick_sounds_skips_silence_music_and_weak_matches(monkeypatch):
    from editor.production import sfx_library as L
    asked = []
    monkeypatch.setattr(L, "available", lambda: True)
    monkeypatch.setattr(L, "search", lambda q, kind=None, k=1: asked.append(q) or [{"id": "z", "score": 0.2}])
    sc = {"scenes": [{"shots": [{"sfx": ["neşeli müzik başlangıcı", "bağırma sesi"], "ambience": "sessiz"}]}]}
    p = mix.pick_sounds(sc)
    assert p["sfx"]["s01c01"] == [None, None] and p["amb"] == {} and p["ids"] == []
    assert asked == ["bağırma sesi"]


def test_is_speech_tells_dialogue_from_first_person_narration(monkeypatch):
    monkeypatch.setattr(shoot, "LIPSYNC_AFTER", False)
    book = ("Hediyemi hemen açtım. Paketin içinden boya kalemleri çıktı.\nAnnem:\n- Ressam olacak benim oğlum, "
            "diyordu.\n«Sen kendin yap.» desem de fayda etmiyordu.\nMert, bu yüzünün hâli ne, diye sordu.")
    assert shoot.is_speech("Hediyemi hemen açtım.", book) is False
    assert shoot.is_speech("Ressam olacak benim oğlum.", book) is True
    assert shoot.is_speech("Sen kendin yap.", book) is True
    assert shoot.is_speech("Teşekkür ederim.", book) is True          # kitapta yok: senaryonun repliği
    assert shoot.is_speech("Mert, bu yüzünün hâli ne?", book) is True   # tire düşmüş, «diye sordu» kalmış
    shot = {"framing": "yakin", "characters": ["Levent"]}
    narr = [{"speaker": "Levent", "text": "Hediyemi hemen açtım."}]
    assert shoot.mode_of(shot, narr, book) == "s2v-sessiz"                  # yakın plan
    assert shoot.mode_of({**shot, "framing": "genel"}, narr, book) == "i2v"   # geniş plan
    assert shoot.mode_of(shot, [{"speaker": "Levent", "text": "Sen kendin yap."}], book) == "s2v"
    wide = {"framing": "genel", "characters": ["Anne", "Mert"]}
    assert shoot.mode_of(wide, [{"speaker": "Anne", "text": "Mert, bu yüzünün hâli ne?"}], book) == "s2v"


def test_kiss_is_on_the_cheek():
    shot = {"framing": "genel", "move": "sabit", "action_en": "Levent kisses his mother.", "setting_en": "room"}
    assert spec.KISS_RULE in spec.shot_prompt(shot, next(iter(spec.STYLES)), {})
    shot["action_en"] = "Levent draws."
    assert spec.KISS_RULE not in spec.shot_prompt(shot, next(iter(spec.STYLES)), {})


def test_mouth_hint_by_speech(monkeypatch):
    monkeypatch.setattr(shoot, "LIPSYNC_AFTER", False)
    assert shoot._mouths("i2v", [{"speaker": "Levent"}], False) == shoot.QUIET_MOUTHS
    assert shoot._mouths("i2v", [{"speaker": "Anne"}, {"speaker": "Mert"}], True) == shoot.TALKING
    assert shoot._mouths("s2v", [{"speaker": "Anne"}], True) == ""
    assert shoot._mouths("i2v", [], False) == ""


def test_pick_best_only_among_versions_taken_this_run(tmp_path):
    def v(n, ok):
        return {"v": n, "file": f"x.v{n}.mp4", "first_frame": "k.png", "qc": {"ok": ok, "problems": []}}
    store.write(tmp_path, "cekimler.json", {"shots": {"s01c01": {"selected": 2, "versions": [v(1, None), v(2, False)]}}})
    assert shoot._pick_best(tmp_path, "s01c01", [2]) is False          # eski kuralla çekilmiş v1 aday değil
    assert store.read(tmp_path, "cekimler.json")["shots"]["s01c01"]["selected"] == 2
    assert shoot._pick_best(tmp_path, "s01c01", []) is False           # bu koşuda alınamadı: yeniden çekilir
    assert shoot._pick_best(tmp_path, "s02c01", []) is False


def test_voiced_shot_does_not_wait_after_the_line():
    need = 3.16 + spec.SHOT_TAIL
    assert spec.fit_seconds(8, [3.16]) == round(need + spec.ACTION_PAD, 2)     # 8 sn değil
    assert spec.fit_seconds(4, [3.16]) == 4                                    # senaryo payı küçükse o
    assert spec.fit_seconds(8, [0.6]) == spec.MIN_VOICED or spec.fit_seconds(8, [0.6]) == round(0.6 + spec.SHOT_TAIL + spec.ACTION_PAD, 2)
    assert spec.fit_seconds(8, []) == 8                                        # sessiz çekim senaryonun süresi


def test_set_reference_comes_first(tmp_path):
    from editor.production.film import frames as fr
    (tmp_path / "kare").mkdir()
    (tmp_path / "kare" / "set-oda.png").write_bytes(b"x")
    store.write(tmp_path, "setler.json", {"levent'in odası": "set-oda.png"})
    assert fr.set_of(tmp_path, {"setting": "Levent'in odası "}) == str(tmp_path / "kare" / "set-oda.png")
    assert fr.set_of(tmp_path, {"setting": "Mutfak"}) is None
    n = fr.ref_note(["Levent"], ["Levent"], with_set=True)
    assert "reference image 1 shows the location" in n and "reference image 2 shows Levent" in n


def test_card_lines_drop_book_drawing_style_for_3d():
    rec = {"members": [{"name": "Levent", "look_en": "A boy with orange hair. Drawing style: thick black ink outlines, "
                                                     "watercolour fills. He wears a yellow sweater."}]}
    assert "ink outlines" in cast_mod.card_lines(rec)["Levent"]
    assert "ink outlines" in cast_mod.card_lines(rec, "2b")["Levent"]
    three = cast_mod.card_lines(rec, "3b")["Levent"]
    assert "ink outlines" not in three and "yellow sweater" in three and "orange hair" in three


def test_lipsync_after_shoots_everything_fast(monkeypatch):
    monkeypatch.setattr(shoot, "LIPSYNC_AFTER", True)
    shot = {"framing": "yakin", "characters": ["Levent"]}
    assert shoot.mode_of(shot, [{"speaker": "Levent", "text": "Sen kendin yap."}], "«Sen kendin yap.»") == "i2v"
    assert shoot._mouths("i2v", [{"speaker": "Levent"}], False) == ""


def test_foley_replaces_library_sfx_and_scene_ambience(tmp_path):
    sc = {"scenes": [{"shots": [{"seconds": 3, "sfx": ["kapı"], "ambience": "oda"}]},
                     {"shots": [{"seconds": 2, "sfx": ["kalem"], "ambience": "oda"}]}]}
    voice = {"seconds": {"s01c01": 3, "s02c01": 2}, "lines": {}}
    picks = {"sfx": {"s01c01": ["/a/kapi.wav"], "s02c01": ["/a/kalem.wav"]}, "amb": {"1": "/a/oda.wav", "2": "/a/oda.wav"},
             "foley": {"s01c01": "/f/s01c01.wav"}}
    tl = mix.timeline(sc, voice, {"s01c01": "a.mp4", "s02c01": "b.mp4"}, picks)
    a, b = tl["shots"]
    assert a["sfx"] == [] and a["foley"] == {"file": "/f/s01c01.wav", "start": 0.0, "seconds": 3.0}
    assert b["sfx"] and "foley" not in b
    assert [x["start"] for x in tl["ambience"]] == [3.0]                    # yalnız foley'siz sahnede ortam
    cmd = " ".join(mix.command(tl, next(iter(spec.FORMATS)), tmp_path, tmp_path / "o.mp4", None))
    assert "/f/s01c01.wav" in cmd and f"volume={mix.FOLEY_DB}dB" in cmd
    (tmp_path / "foley").mkdir()
    (tmp_path / "foley" / "s01c01.wav").write_bytes(b"x")
    assert mix.foley_files(tmp_path, ["s01c01", "s02c01"]) == {"s01c01": str(tmp_path / "foley" / "s01c01.wav")}


# ------------------------------------------------------------------ uyarlama (adapt)
_BOOK = ("Hediyemi hemen açtım. İçinden boya kalemleri çıktı.\nAnnem gelip resimlerime baktı.\n"
         "Ressam olacak benim oğlum, diyordu.\nMert de istedi.\n- Ben de resim, ben de resim, diye tutturdu.")


def test_adapt_sentences_and_book_dialogue():
    from editor.production.film import adapt
    s = adapt.sentences(_BOOK)
    assert s[0] == "Hediyemi hemen açtım." and "Mert de istedi." in s
    sp = adapt.speech_lines(_BOOK)
    assert "Ressam olacak benim oğlum" in sp and "Ben de resim, ben de resim" in sp
    assert not any("Hediyemi" in x for x in sp)


def test_adapt_outline_must_cover_book_in_order():
    from editor.production.film import adapt
    s = adapt.sentences(_BOOK)
    good = {"beats": [{"purpose": "kanca", "sentences": [], "seconds": 5}, {"purpose": "isim", "sentences": [], "seconds": 5},
                      {"purpose": "olay", "sentences": [1, 2], "seconds": 30}, {"purpose": "olay", "sentences": [3, 4], "seconds": 30},
                      {"purpose": "kapanis", "sentences": list(range(5, len(s) + 1)), "seconds": 30}]}
    assert adapt.check_outline(good, s, 100) == []
    skipped = {"beats": [{"sentences": [1], "seconds": 100}]}
    assert any("bağlı değil" in p for p in adapt.check_outline(skipped, s, 100))
    unordered = {"beats": [{"sentences": [3], "seconds": 50}, {"sentences": [1, 2, 4, 5, 6], "seconds": 50}]}
    assert any("sırayla" in p for p in adapt.check_outline(unordered, s, 100))


def test_adapt_episode_requires_every_book_line_verbatim():
    from editor.production.film import adapt

    def shot(lines, secs=3):
        return {"seconds": secs, "framing": "yakin", "move": "sabit", "characters": [], "action": "a", "action_en": "a",
                "quote": "", "lines": lines, "sfx": [], "ambience": ""}
    ok = {"cast": [], "scenes": [{"setting": "oda", "shots": [
        shot([{"speaker": "Anne", "text": "Ressam olacak benim oğlum!", "emotion": "neseli", "added": False}]),
        shot([{"speaker": "Mert", "text": "Ben de resim, ben de resim.", "emotion": "heyecanli", "added": False}]),
        shot([{"speaker": "Levent", "text": "Vaaay!", "emotion": "heyecanli", "added": True}])]}]}
    assert not [p for p in adapt.check_episode(ok, _BOOK, 9) if p.fatal]
    bad = {"cast": [], "scenes": [{"setting": "oda", "shots": [
        shot([{"speaker": "Anne", "text": "Sen ressam olacaksın!", "emotion": "neseli", "added": False}]),
        shot([{"speaker": "Levent", "text": "Bu çok güzel bir hediye oldu bence.", "emotion": "neseli", "added": True}])]}]}
    probs = [p.text for p in adapt.check_episode(bad, _BOOK, 6) if p.fatal]
    assert any("Ressam olacak" in p for p in probs) and any("en çok" in p for p in probs)


def test_adapt_write_two_passes(monkeypatch, tmp_path):
    import asyncio
    from editor.production import marketing as mk2
    from editor.production.film import adapt
    from editor.production.film import script as sm
    monkeypatch.setattr(sm, "book_text", lambda d: _BOOK)
    monkeypatch.setattr(sm, "known_characters", lambda d: ["Levent", "Mert", "Anne"])
    monkeypatch.setattr(sm, "book_checker", lambda d: (lambda q: True))
    monkeypatch.setattr(adapt.studio, "_manuscript", lambda d: types.SimpleNamespace(title="Levent"))
    monkeypatch.setattr(mk2, "_kind_text", lambda d: "çocuk kitabı")
    cast = [{"name": n, "role": r, "look_en": "x", "age": a, "gender": g} for n, r, a, g in
            (("Levent", "kahraman", "cocuk", "erkek"), ("Mert", "kardeş", "cocuk", "erkek"), ("Anne", "anne", "yetiskin", "kadin"))]
    n = len(adapt.sentences(_BOOK))
    calls = []

    async def fake(llm, name, schema, **kw):
        calls.append(name)
        if name == adapt.OUTLINE_PROMPT:
            return {"title": "t", "logline": "l", "cast": cast, "beats": [
                {"scene": 1, "setting": "oda", "setting_en": "room", "time": "gunduz", "purpose": "kanca", "summary": "s",
                 "sentences": [], "seconds": 1}, {"scene": 1, "setting": "oda", "setting_en": "room", "time": "gunduz",
                 "purpose": "isim", "summary": "s", "sentences": [], "seconds": 1},
                {"scene": 1, "setting": "oda", "setting_en": "room", "time": "gunduz", "purpose": "kapanis", "summary": "s",
                 "sentences": list(range(1, n + 1)), "seconds": 13}]}
        L = lambda who, t, add=False: {"speaker": who, "text": t, "emotion": "neseli", "added": add}  # noqa: E731
        fr = iter(["genel", "yakin", "omuz-ustu", "yakin", "genel"])
        S = lambda lines: {"seconds": 3, "framing": next(fr), "move": "sabit", "characters": ["Levent"], "action": "a",  # noqa: E731
                           "action_en": "a", "quote": "Hediyemi hemen açtım.", "lines": lines, "sfx": [], "ambience": "",
                           "beat": 1}
        return {"shots": [S([L("Levent", "Hediyemi hemen açtım.")]), S([L("Anne", "Ressam olacak benim oğlum.")]),
                          S([L("Mert", "Ben de resim, ben de resim!")]), S([L("Levent", "Vaaay!", True)]),
                          S([L("Levent", "Mert de istedi.")])]}
    monkeypatch.setattr(mk2, "_ask", fake)
    d = tmp_path / "job"
    d.mkdir()
    f = store.create(d, "cizgi-film", "3b", "Levent", "t")
    rec = asyncio.run(adapt.write(d, f, "t", 15, llm=object()))
    assert calls == [adapt.OUTLINE_PROMPT, adapt.SCENE_PROMPT]
    sc = rec["script"]
    assert sc["adapted"] and len(spec.shots(sc)) == 5 and not [p for p in rec["problems"] if p["fatal"]]


def test_adapt_speech_does_not_swallow_neighbour_sentence():
    from editor.production.film import adapt
    b = "Odama gittim. İçeri girmek istedim. Ama Mert sinirle: - Appi diiiiit, diye bağırdı. Annem:\nMeeert!"
    sp = adapt.speech_lines(b)
    assert "Appi diiiiit" in sp and "Meeert!" in sp or "Meeert" in sp
    assert not any("İçeri girmek" in x or "Odama" in x for x in sp)


def test_adapt_scene_problems_duration_and_added():
    from editor.production.film import adapt
    sh = [{"seconds": 2, "lines": [{"text": "Vay!", "added": True}, {"text": "Hı?", "added": True}]}]
    probs = adapt.scene_problems(sh, ["Hediyemi açtım."], 10)
    assert any("Eklenen satır 2/2" in p for p in probs) and any("Sahne 2 sn" in p for p in probs)


def test_adapt_outline_needs_hook_title_and_ending():
    from editor.production.film import adapt
    s = adapt.sentences(_BOOK)
    o = {"beats": [{"purpose": "olay", "sentences": list(range(1, len(s) + 1)), "seconds": 100}]}
    assert any("kanca" in p for p in adapt.check_outline(o, s, 100))
    o = {"beats": [{"purpose": "kanca", "sentences": [], "seconds": 6}, {"purpose": "isim", "sentences": [], "seconds": 4},
                   {"purpose": "kapanis", "sentences": list(range(1, len(s) + 1)), "seconds": 90}]}
    assert adapt.check_outline(o, s, 100) == []


def test_adapt_scene_keeps_inner_voice_and_last_line():
    from editor.production.film import adapt
    q = ["Hediyemi hemen açtım.", "İçinden boya kalemleri çıktı.", "Annem gelip resimlerime baktı."]
    silent = [{"seconds": 12, "lines": []}]
    probs = adapt.scene_problems(silent, q, 10, last="Annem gelip resimlerime baktı.")
    assert any("iç seste" in p for p in probs) and any("son cümlesi" in p for p in probs)
    voiced = [{"seconds": 5, "lines": []}, {"seconds": 6, "lines": [{"speaker": "Levent",
                                                                       "text": "Annem gelip resimlerime baktı.", "added": False}]}]
    assert adapt.scene_problems(voiced, q, 10, last="Annem gelip resimlerime baktı.") == []


def test_adapt_normalize_names_to_cast_spelling():
    from editor.production.film import adapt
    sc = {"cast": [{"name": "Boyacı"}, {"name": "Levent"}], "scenes": [{"shots": [
        {"characters": ["Boyaci", "levent"], "lines": [{"speaker": "Levent (Anlatıcı)", "text": "x"}]}]}]}
    assert adapt.normalize_names(sc, "Levent") == 3
    sh = sc["scenes"][0]["shots"][0]
    assert sh["characters"] == ["Boyacı", "Levent"] and sh["lines"][0]["speaker"] == "Levent"


def test_adapt_backmatter_spelling_and_narrator_alias():
    from editor.production.film import adapt
    book = "Hediyemi hemen açtım.\nAnnem öyle söyledi.\n* * *\nAşağıdaki soruları hikâyeye göre cevaplayınız.\n1. Ne oldu?"
    assert adapt.sentences(book)[-1] == "Annem öyle söyledi."
    sc = {"cast": [{"name": "Levent"}], "scenes": [{"shots": [{"characters": [], "lines": [
        {"speaker": "Anlatıcı", "text": "Hediyemi hemen actim."}]}]}]}
    adapt.normalize_names(sc, "Levent")
    assert adapt.restore_book_spelling(sc, book) == 1
    ln = sc["scenes"][0]["shots"][0]["lines"][0]
    assert ln == {"speaker": "Levent", "text": "Hediyemi hemen açtım."}


def test_adapt_ending_and_framing_run():
    from editor.production.film import adapt
    assert adapt.ending(["Mert çok tehlikeliymiş.", "Annem öyle söyledi."]) == ["Mert çok tehlikeliymiş.", "Annem öyle söyledi."]
    assert adapt.ending(["A b c.", "Sonunda herkes çok mutlu oldu."]) == ["Sonunda herkes çok mutlu oldu."]
    sh = [{"seconds": 3, "framing": "omuz-ustu", "lines": []} for _ in range(3)]
    assert any("üst üste 3" in p for p in adapt.scene_problems(sh, [], 9))


def test_lipsync_plan_speaker_silent_and_skip():
    from editor.production.film import lipsync
    boxes = {"Levent": [100, 100, 300, 600], "Anne": [400, 50, 700, 700], "Mert": [800, 300, 900, 600]}
    shot = {"framing": "genel"}
    p = lipsync.plan(shot, [{"speaker": "anlatıcı", "text": "x"}], boxes, "Levent")
    assert p["speak"] == [("Levent", boxes["Levent"])] and p["silent"] == [boxes["Anne"]]   # büyük olan sessiz tutulur
    assert lipsync.plan(shot, [], boxes, "Levent") is None                                   # geniş, konuşma yok
    p = lipsync.plan({"framing": "yakin"}, [{"speaker": "Baba", "text": "x"}], {"Mert": [1, 1, 5, 5]}, "Levent")
    assert p == {"speak": [], "silent": [], "all_silent": True}                              # konuşan karede yok
    assert lipsync.dub_name("s01c02.v3.mp4") == "s01c02.v3.dub.mp4"


def test_for_mix_prefers_dub_then_hd(tmp_path):
    (tmp_path / "cekim").mkdir()
    for n in ("s01c01.v1.mp4", "s01c01.v1.dub.mp4"):
        (tmp_path / "cekim" / n).write_bytes(b"x")
    store.write(tmp_path, "cekimler.json", {"shots": {"s01c01": {"selected": 1, "versions": [{"v": 1, "file": "s01c01.v1.mp4"}]}}})
    assert shoot.for_mix(tmp_path, "s01c01") == (tmp_path / "cekim" / "s01c01.v1.dub.mp4", False)


def test_over_shoulder_framing_forbids_duplicate():
    assert "NOT drawn a second time" in spec.FRAMINGS["omuz-ustu"]


def test_take_retries_transient_error(monkeypatch, tmp_path):
    import asyncio
    import httpx as hx
    monkeypatch.setattr(shoot, "TAKE_BACKOFF", 0.0)
    calls = []

    async def flaky(f, s, by, seed, http, alias=shoot.ALIAS):
        calls.append(s["id"])
        if len(calls) == 1:
            raise hx.ConnectError("servis açılıyor")
        return {"v": 1, "file": f"{s['id']}.v1.mp4", "qc": {"ok": None, "problems": []}, "first_frame": "k.png"}

    async def no_check(*a, **k):
        return {"ok": None, "problems": []}

    async def one(): return [shoot.ALIAS]
    monkeypatch.setattr(shoot, "take", flaky)
    monkeypatch.setattr(shoot, "check", no_check)
    monkeypatch.setattr(shoot, "workers", one)
    monkeypatch.setattr(shoot, "enhance_selected", lambda f, http, progress=None: asyncio.sleep(0, {"done": 0, "total": 0, "error": None}))
    monkeypatch.setattr(shoot, "_pick_best", lambda f, sid, taken=None: True)
    monkeypatch.setattr(shoot.store, "require", lambda f, st: None)
    monkeypatch.setattr(shoot.script_mod, "load", lambda f: {"scenes": [{"shots": [{"seconds": 3}]}]})
    f = tmp_path / "film"; f.mkdir()
    store.write(f, "film.json", {"id": "f_x", "format": "cizgi-film", "style": "3b", "stages": {"cekim": {}}})
    asyncio.run(shoot.shoot(tmp_path, f, "t", only=["s01c01"]))
    assert calls == ["s01c01", "s01c01"]


def test_black_spans_detects_fade_to_black(tmp_path):
    p = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=white:s=64x64:d=1", "-f", "lavfi",
                    "-i", "color=c=black:s=64x64:d=0.6", "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]",
                    str(p)], check=True)
    spans = shoot.black_spans(p)
    assert spans and spans[0][0] >= 0.9


def test_foley_prompt_and_jobs(tmp_path):
    from editor.production.film import foley
    shot = {"action_en": "Levent tears the gift paper.", "sfx": ["paper tearing", ""], "ambience": "quiet room"}
    p = foley.prompt_of(shot)
    assert "tears the gift paper" in p and "paper tearing" in p and "quiet room" in p
    f = tmp_path
    (f / "cekim").mkdir(); (f / "foley").mkdir()
    (f / "cekim" / "s01c01.v1.mp4").write_bytes(b"x")
    (f / "cekim" / "s01c01.v1.dub.mp4").write_bytes(b"x")
    store.write(f, "senaryo.json", {"rev": 1, "script": {"scenes": [{"shots": [{**shot, "seconds": 3}]}]}})
    store.write(f, "cekimler.json", {"shots": {"s01c01": {"selected": 1, "versions": [{"v": 1, "file": "s01c01.v1.mp4"}]}}})
    js = foley.jobs(f)
    assert len(js) == 1 and js[0]["video"].endswith("s01c01.v1.dub.mp4") and js[0]["out"].endswith("foley/s01c01.wav")
    (f / "foley" / "s01c01.wav").write_bytes(b"x")
    foley.mark_done(f, js)
    assert foley.jobs(f) == []


def test_gateway_passes_video_enhance():
    from editor import gateway
    assert "video/enhance" in gateway.PASSTHROUGH and "video/generations" in gateway.PASSTHROUGH
