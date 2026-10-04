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
