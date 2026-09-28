"""Efekt sesleri (editor.production.sfx, sfx_library): alıntının metinde bulunması, oylama, sayfa kaydı doğrulaması,
havuz araması (sahte küçük dizin), karışımın zamanlaması ve anlatımın korunması, sesli okuma kancası, e-kitabın ses
seçimi. Model yok (Zeki AI sahte). Karışım testleri ffmpeg ister; yoksa atlanır. Çalıştır:

    pytest apps/editor/tests/test_sfx.py
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import types
from pathlib import Path

import numpy as np
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

from editor.production import narration as N  # noqa: E402
from editor.production import sfx  # noqa: E402
from editor.production import sfx_library as L  # noqa: E402

FFMPEG = shutil.which("ffmpeg") is not None

TEXT = ("Göl kıyısında ördekler vak vak diye bağırıyordu. Birden kapı gıcırdadı ve rüzgâr uğuldamaya başladı. "
        "Ormanda herkes sustu.")
PAGE = {"id": "p_1", "layout": "text", "chapter": 0,
        "text": {"box": {"x": 0, "y": 0}, "blocks": [{"id": "b1", "kind": "para", "runs": [{"text": TEXT}]}]},
        "bubbles": [], "texts": []}


# ------------------------------------------------------------------ sahte havuz
def _index(root: Path) -> dict[str, str]:
    """Dört dosyalık küçük dizin: gömmeler elle (sorgu kolu sahte), etiketler gerçek biçimde."""
    d = root / "_dizin"
    d.mkdir(parents=True)
    rows = []
    vecs = []
    names = [("ordek", "duck quack", ["ordek"], 1.2), ("kapi", "door creak", ["kapi"], 2.0),
             ("ruzgar", "wind howling", ["ruzgar"], 40.0), ("orman", "forest ambience birds", ["orman"], 60.0)]
    for k, (nm, tags, cats, dur) in enumerate(names):
        f = root / "kenney" / f"{nm}.wav"
        f.parent.mkdir(parents=True, exist_ok=True)
        _tone(f, min(dur, 3.0), 300 + 150 * k)
        rows.append({"id": f"{k:016x}", "src": "kenney", "path": f"kenney/{nm}.wav", "name": f"{nm}.wav", "title": nm,
                     "tags_en": tags.split(), "tags_tr": [L.CATEGORIES[cats[0]]["label"]], "cats": cats, "dur": dur,
                     "sr": 48000, "ch": 1, "lufs": -20.0, "peak": -3.0, "clip": 0.0, "flags": [],
                     "license": "CC0 1.0", "license_url": "", "credit": None if k else "«ordek» — biri, CC BY 3.0",
                     "page": "", "sha256": f"{k:064x}"})
        v = np.zeros(8, dtype=np.float16)
        v[k] = 1
        vecs.append(v)
    (d / "katalog.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    np.save(d / "gomme.npy", np.stack(vecs))
    return {n[0]: r["id"] for n, r in zip(names, rows)}


def _tone(path: Path, sec: float, hz: float, sr: int = 48000) -> None:
    import wave
    t = np.arange(int(sec * sr)) / sr
    x = (0.3 * np.sin(2 * np.pi * hz * t) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(x.tobytes())


class _Enc:
    """Sahte metin kolu: sorgudaki anahtar sözcüğün eksenine bakan birim vektör."""
    AX = {"duck": 0, "door": 1, "wind": 2, "forest": 3}

    def __call__(self, texts):
        out = np.zeros((len(texts), 8), dtype=np.float32)
        for i, t in enumerate(texts):
            for w, ax in self.AX.items():
                if w in t.lower():
                    out[i, ax] = 1
        n = np.linalg.norm(out, axis=1, keepdims=True)
        n[n == 0] = 1
        return out / n


@pytest.fixture()
def pool(tmp_path, monkeypatch):
    root = tmp_path / "sfx"
    ids = _index(root)
    monkeypatch.setenv("EDITOR_SFX_ROOT", str(root))
    monkeypatch.setattr(L, "_IDX", None)
    monkeypatch.setattr(L, "text_encoder", lambda: _Enc())
    return ids


@pytest.fixture()
def job(tmp_path, monkeypatch):
    from editor.production import studio
    store = tmp_path / "store"
    store.mkdir()
    monkeypatch.setattr(studio, "root", lambda: store)
    d = store / "20260927000000abcdef"
    d.mkdir()
    studio.write(d, "plan.json", {"version": 1, "rev": 1, "pages": [PAGE], "assets": {}})
    studio.write(d, "profile.json", {"age_min": 5, "age_max": 8})
    return d


def _units(job):
    from editor.production import plan as plan_mod
    return sfx._units(job, plan_mod.load(job)["pages"][0])


# ------------------------------------------------------------------ metin
def test_locate_exact_quote_only(job):
    u = _units(job)
    assert sfx.locate(u, "vak vak") == ("b1", 3, 4)
    assert sfx.locate(u, "Kapı gıcırdadı") == ("b1", 8, 9)           # büyük/küçük harf, noktalama önemsiz
    assert sfx.locate(u, "kapı gıcırdayarak") is None                  # metinde birebir yok → atılır
    assert sfx.locate(u, "") is None


def test_vote_keeps_majority_and_drops_invented(job):
    u = _units(job)
    a = {"blok": "b1", "alinti": "vak vak", "tur": "yansima", "kategori": "ordek", "tarif": "ördek vaklıyor",
         "tarif_en": "duck quacking", "yer": "birlikte"}
    b = {"blok": "b1", "alinti": "kapı gıcırdadı", "tur": "olay", "kategori": "kapi", "tarif": "gıcırdayan kapı",
         "tarif_en": "door creaking", "yer": "ardindan"}
    fake = {**b, "alinti": "kapı hızla çarptı"}
    amb = {"blok": "b1", "alinti": "Ormanda", "tur": "ortam", "kategori": "orman", "tarif": "orman", "tarif_en": "forest",
           "yer": "birlikte"}
    cues, st = sfx._vote([[a, b, fake, amb], [a, {**b, "alinti": "gıcırdadı"}, amb], [a]], u)
    by = {c["quote"]: c for c in cues}
    assert set(by) == {"vak vak", "kapı gıcırdadı", "Ormanda"}
    assert by["vak vak"]["confidence"] == 1.0 and by["kapı gıcırdadı"]["confidence"] == pytest.approx(0.67)
    assert by["Ormanda"]["kind"] == "ortam"
    assert st["not_in_text"] == 1 and st["kept"] == 3
    only_once = [[b], [], []]
    assert sfx._vote(only_once, u)[0] == []                            # tek okumada çıkan ipucu kalmaz


def test_sound_hints_and_rule_support(job):
    u = _units(job)
    h = sfx.sound_hints(u)
    assert "vak vak" in h and "gıcırdadı" in h and "uğuldamaya" in h and "Göl" not in h
    b = {"blok": "b1", "alinti": "kapı gıcırdadı", "tur": "olay", "kategori": "kapi", "tarif": "gıcırdayan kapı",
         "tarif_en": "door creaking", "yer": "ardindan"}
    fake = {**b, "alinti": "herkes sustu", "kategori": "diger"}
    cues, _ = sfx._vote([[b, fake], [], []], u, hints=h)
    assert [c["quote"] for c in cues] == ["kapı gıcırdadı"] and cues[0]["ruled"] is True   # kural + tek okuma
    assert sfx._vote([[b], [], []], u)[0] == []                                              # kuralsız tek okuma


# ------------------------------------------------------------------ havuz
def test_search_semantic_lexical_and_filters(pool):
    top = L.search("ördek vaklıyor", en="duck quacking", k=2)
    assert top[0]["id"] == pool["ordek"] and top[0]["why"] == "anlam"
    assert L.search("rüzgâr", category="ruzgar", k=5)[0]["id"] == pool["ruzgar"]
    assert L.search("x", category="ordek", k=5, exclude={pool["ordek"]}) == []
    amb = L.search("forest", en="forest", kind="ortam", k=1)
    assert amb[0]["id"] == pool["orman"]
    assert L.credits([pool["ordek"], pool["kapi"]]) == [{"id": pool["ordek"], "text": "«ordek» — biri, CC BY 3.0",
                                                         "license": "CC0 1.0", "url": ""}]


def test_search_without_text_encoder_uses_tags(pool, monkeypatch):
    monkeypatch.setattr(L, "text_encoder", lambda: None)
    top = L.search("door", k=1)
    assert top[0]["id"] == pool["kapi"] and top[0]["why"] == "etiket"


def test_categorize():
    assert L.categorize(["duck", "quack"])[0] == "ordek"
    assert "ates" in L.categorize(["crackling", "fire"])
    assert L.categorize_tr("çıtırdayan ateş")[0] == "ates"


# ------------------------------------------------------------------ sayfa kaydı
def test_set_page_validates_quote_and_sound(job, pool):
    ok = {"quote": "vak vak", "chosen": pool["ordek"], "candidates": [pool["ordek"]], "gain_db": 40}
    v = sfx.set_page(job, "p_1", {"cues": [ok], "ambience": None}, "editör")
    c = v["cues"][0]
    assert c["block"] == "b1" and c["words"] == [3, 4] and c["gain_db"] == sfx.GAIN_RANGE[1] and c["id"].startswith("e_")
    with pytest.raises(ValueError):
        sfx.set_page(job, "p_1", {"cues": [{**ok, "quote": "hav hav"}]}, "editör")
    with pytest.raises(ValueError):
        sfx.set_page(job, "p_1", {"cues": [{**ok, "chosen": "ffffffffffffffff"}]}, "editör")


def test_quote_moves_or_is_lost_when_text_changes(job, pool):
    from editor.production import studio
    sfx.set_page(job, "p_1", {"cues": [{"quote": "kapı gıcırdadı", "chosen": pool["kapi"]}]}, "e")
    pl = studio.read(job, "plan.json")
    pl["pages"][0]["text"]["blocks"][0]["runs"][0]["text"] = "Sonra kapı gıcırdadı."
    studio.write(job, "plan.json", pl)
    c = sfx.page_effects(job, "p_1")["cues"][0]
    assert c["words"] == [1, 2] and not c.get("lost")
    pl["pages"][0]["text"]["blocks"][0]["runs"][0]["text"] = "Sonra sessizlik oldu."
    studio.write(job, "plan.json", pl)
    assert sfx.page_effects(job, "p_1")["cues"][0]["lost"] is True


def test_default_on_for_children_off_for_adults(job):
    from editor.production import studio
    assert sfx.settings(job)["enabled"] is True
    studio.write(job, "profile.json", {"age_min": 18, "age_max": 99})
    assert sfx.settings(job)["enabled"] is False
    sfx.set_enabled(job, True, "editör")
    s = sfx.settings(job)
    assert s["enabled"] is True and s["source"] == "editor" and s["by"] == "editör"


def test_suggest_page_with_fake_model(job, pool, monkeypatch):
    async def fake_read(llm, units, pid, t):
        return [{"blok": "b1", "alinti": "vak vak", "tur": "yansima", "kategori": "ordek", "tarif": "ördek vaklıyor",
                 "tarif_en": "duck quacking", "yer": "birlikte"},
                {"blok": "b1", "alinti": "Ormanda", "tur": "ortam", "kategori": "orman", "tarif": "orman sesi",
                 "tarif_en": "forest ambience", "yer": "birlikte"}]
    sfx.set_page(job, "p_1", {"cues": [{"quote": "rüzgâr uğuldamaya", "chosen": pool["ruzgar"]}]}, "editör")
    monkeypatch.setattr(sfx, "_read_page", fake_read)
    rec = asyncio.run(sfx.suggest_page(job, "p_1", "editör", llm=object()))
    quotes = {c["quote"]: c for c in rec["cues"]}
    assert set(quotes) == {"rüzgâr uğuldamaya", "vak vak"}               # editörün eklediği korunur
    assert quotes["vak vak"]["chosen"] == pool["ordek"] and len(quotes["vak vak"]["candidates"]) == sfx.CANDIDATES
    assert rec["ambience"]["chosen"] == pool["orman"]


# ------------------------------------------------------------------ karışım
def _narrated(job, dur=6.0):
    """Sahte anlatım: kayıt + mp3 (ffmpeg ile gerçek dosya), kelime zamanları 0,4 sn aralıklı."""
    from editor.production import plan as plan_mod
    pg = plan_mod.load(job)["pages"][0]
    units, plist, h = N.page_input(job, pg)
    blocks = N.word_times(units, [], [])
    t = 0.0
    for b in blocks:
        for w in b["words"]:
            w["start"], w["end"] = round(t, 3), round(t + 0.3, 3)
            t += 0.4
    sd = N.ses_dir(job) / "sayfa"
    wav = sd / "p_1.wav"
    _tone(wav, dur, 200)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-c:a", "libmp3lame", str(sd / "p_1.mp3")], check=True)
    wav.unlink()
    rec = {"version": 1, "page": "p_1", "no": 1, "hash": h, "audio": "ses/sayfa/p_1.mp3", "format": "mp3",
           "duration": dur, "blocks": blocks}
    (sd / "p_1.json").write_text(json.dumps(rec))
    return rec


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg yok")
def test_mix_page_places_effects_at_word_times_and_keeps_narration(job, pool):
    rec = _narrated(job)
    sfx.set_page(job, "p_1", {"cues": [{"quote": "vak vak", "chosen": pool["ordek"], "place": "birlikte"},
                                       {"quote": "kapı gıcırdadı", "chosen": pool["kapi"], "place": "ardindan"}],
                              "ambience": {"chosen": pool["orman"], "query": "orman"}}, "e")
    assert sfx.mix_state(job, "p_1") == "stale"
    out = sfx.mix_page(job, "p_1")
    assert out["status"] == "done" and sfx.mix_path(job, "p_1").exists()
    w = {x["i"]: x for x in rec["blocks"][0]["words"]}
    pl = {p["quote"]: p for p in out["placements"]}
    assert pl["vak vak"]["start"] == w[3]["start"]                      # kelimeyle birlikte
    assert pl["kapı gıcırdadı"]["start"] == w[9]["end"]                 # alıntının bitiminde
    assert abs(out["lufs"] - sfx.TARGET_LUFS) < 1.5 and out["true_peak"] <= sfx.TRUE_PEAK + 0.6
    assert out["duration"] >= rec["duration"]                           # anlatım kesilmez
    # anlatımın kaydı ve dosyası olduğu gibi
    assert json.loads((job / "ses/sayfa/p_1.json").read_text())["blocks"] == rec["blocks"]
    assert sfx.mix_state(job, "p_1") == "done"
    assert sfx.page_audio(job, "p_1", Path("x")) == sfx.mix_path(job, "p_1")
    # ses düzeyi değişince yalnız karışım eskir; kapalıyken anlatım çalar
    v = sfx.page_view(job, "p_1")
    v["cues"][0]["gain_db"] = -6
    sfx.set_page(job, "p_1", {"cues": v["cues"], "ambience": v["ambience"]}, "e")
    assert sfx.mix_state(job, "p_1") == "stale"
    assert sfx.page_audio(job, "p_1", Path("x")) == Path("x")
    sfx.mix_page(job, "p_1")
    sfx.set_enabled(job, False, "e")
    assert sfx.page_audio(job, "p_1", Path("x")) == Path("x")


def test_mix_requires_current_narration(job, pool):
    sfx.set_page(job, "p_1", {"cues": [{"quote": "vak vak", "chosen": pool["ordek"]}]}, "e")
    with pytest.raises(sfx.NoNarration):
        sfx.mix_page(job, "p_1")
    assert sfx.mix_state(job, "p_1") == "no_audio"


def test_narration_hook_never_breaks_narration(job, monkeypatch):
    async def boom(d, pid, by="x"):
        raise RuntimeError("havuz yok")
    monkeypatch.setattr(sfx, "after_narration", boom)
    asyncio.run(N._efekt_kancasi(job, "p_1", "e"))                      # hata yutulur, günlüğe yazılır


def test_overview_and_kunye(job, pool):
    sfx.set_page(job, "p_1", {"cues": [{"quote": "vak vak", "chosen": pool["ordek"]}]}, "e")
    ov = sfx.overview(job)
    assert ov["settings"]["enabled"] is True and ov["pages"][0]["active"] == 1
    assert ov["pages"][0]["mix"] == "no_audio"
    rows = sfx.kunye_rows(job)
    assert rows[0][0] == "Ses efektleri" and "Kenney" in rows[0][1]
    assert ("Ses efekti kaynağı", "«ordek» — biri, CC BY 3.0") in rows


# ------------------------------------------------------------------ 2026-09-28 tam kitap dinlemesi
def test_sound_hints_quote_diye_and_stretched_words():
    t = "Top “Pat!” diye yere düştü. Güüüümmmm! Kedi “miyav” dedi."
    u = [N.Unit("b1", "para", None, "anlatici-kadin", t, N.read(t))]
    h = sfx.sound_hints(u)
    assert "Pat" in h and "Güüüümmmm" in h and "miyav" in h


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg yok")
def test_render_keeps_effect_tail_after_narration_ends(tmp_path):
    nar, fx = tmp_path / "n.wav", tmp_path / "f.wav"
    _tone(nar, 2.0, 200)
    _tone(fx, 3.0, 600)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(nar), "-c:a", "libmp3lame", str(tmp_path / "n.mp3")],
                   check=True)
    out = tmp_path / "o.mp3"
    r = sfx.render(tmp_path / "n.mp3", 2.0, [{"file": str(fx), "start": 1.5, "length": 3.0, "gain_db": 0.0}], None, out)
    got = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                               capture_output=True, text=True, check=True).stdout)
    assert r["duration"] == 4.5 and got >= 4.4                         # efekt anlatımdan sonra 2,5 sn daha çalar
