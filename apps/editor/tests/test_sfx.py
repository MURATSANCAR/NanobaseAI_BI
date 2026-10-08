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

    async def no_translate(text):
        return None
    monkeypatch.setattr(sfx, "translate", no_translate)
    rec = asyncio.run(sfx.suggest_page(job, "p_1", "editör", llm=object()))
    quotes = {c["quote"]: c for c in rec["cues"]}
    # editörün eklediği korunur; modelin atladığı güçlü ses fiili («gıcırdadı») kural ipucu olur
    assert set(quotes) == {"rüzgâr uğuldamaya", "vak vak", "gıcırdadı"}
    assert quotes["gıcırdadı"]["rule_only"] is True and rec["suggested"]["stats"]["rule_only"] == 1
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


def test_rule_cue_when_model_misses_strong_sound(job):
    t = "Aslan kahkahalarla güldü. Sonra herkes eve döndü."
    u = [N.Unit("b1", "para", None, "anlatici-kadin", t, N.read(t))]
    hints = sfx.strong_hints(u)
    assert hints == ["kahkahalarla"]
    rc = sfx._rule_cues(u, [], hints, 3)
    assert [(c["quote"], c["rule_only"], c["confidence"]) for c in rc] == [("kahkahalarla", True, 0.33)]
    model = [{"block": "b1", "words": [1, 2]}]
    assert sfx._rule_cues(u, model, hints, 3) == []                   # model aynı yeri bulduysa kural açmaz
    other = [{"block": "b1", "words": [5, 6], "quote": "kahkaha attı"}]
    assert sfx._rule_cues(u, other, hints, 3) == []                   # aynı ses fiili sayfada zaten ipucu
    assert sfx.strong_hints([N.Unit("b2", "para", None, "anlatici-kadin", "Top yere düştü.",
                                    N.read("Top yere düştü."))]) == []


# ------------------------------------------------------------------ 2026-09-29: sesi çıkaran ve üst üste binme
def test_voice_person_from_voice_identity():
    """Kişi sesin kimliğinden (ad, not, tarif) — kitaptan bağımsız; bilinmeyen ses bilgi vermez.
    Çocuk sesleri 2026-10-08'den beri sabit kayıtlı (voices_zeki.PINNED): artık genç sese yönlenmez, kişisi çocuktur."""
    got = {v: sfx.voice_person(v) for v in ("anlatici-kadin", "canli-erkek-radyo", "anlatici-erkek", "cocuk-kiz",
                                             "cocuk-erkek", "kucuk-kiz", "kucuk-erkek", "yasli-kadin",
                                             "masal-erkek-dede", "masal-kadin-anne")}
    assert got == {"anlatici-kadin": "kadın", "canli-erkek-radyo": "erkek", "anlatici-erkek": "erkek",
                   "cocuk-kiz": "kız çocuğu", "cocuk-erkek": "erkek çocuğu", "kucuk-kiz": "kız çocuğu",
                   "kucuk-erkek": "erkek çocuğu", "yasli-kadin": "yaşlı kadın",
                   "masal-erkek-dede": "yaşlı erkek", "masal-kadin-anne": "kadın"}
    assert sfx.voice_person("yok-boyle-ses") is None and sfx.voice_person(None) is None


def test_pick_prompt_carries_who_makes_the_human_sound(pool):
    """Kadın anlatıcının okuduğu yerde iç çekiş, nine karakterin balonundaki «Tüh!»: seçim istemi sesi çıkaranın
    cinsiyetini/yaşını taşır, insan sesinde tutması gerektiğini söyler; istem sürümü artar."""
    t, b = "Kız derin bir iç çekti.", "Tüh!"
    units = [N.Unit("b1", "para", None, "anlatici-kadin", t, N.read(t)),
             N.Unit("k1", "bubble", "Nine", "masal-nine", b, N.read(b)),
             N.Unit("k2", "bubble", "Can", "canli-erkek-radyo", b, N.read(b))]
    cands = [{"id": "x1", "title": "male sigh", "source": "kenney", "dur": 1.0},
             {"id": "x2", "title": "female sigh", "source": "kenney", "dur": 1.0}]
    # anlatımda okuyan anlatıcı sesi çıkaran değildir: kişi satırı yok (kişiyi metin söyler)
    assert sfx.block_speaker(units, "b1") is None
    nar = sfx.pick_prompt({"quote": "iç çekti", "query": "iç çekiş"}, cands, sfx.block_speaker(units, "b1"))
    assert "Sesi çıkaran" not in nar
    assert "adayın cinsiyeti ve yaşı sesi çıkaranla tutmalı" in nar and "A) male sigh" in nar
    bub = sfx.pick_prompt({"quote": "Tüh", "query": "hayal kırıklığı iç çekişi"}, cands, sfx.block_speaker(units, "k1"))
    assert "Sesi çıkaran: yaşlı kadın («Nine» konuşuyor)." in bub
    assert "Sesi çıkaran: erkek («Can» konuşuyor)." in sfx.pick_prompt({"quote": "Tüh"}, cands,
                                                                        sfx.block_speaker(units, "k2"))
    assert "Sesi çıkaran" not in sfx.pick_prompt({"quote": "Tüh"}, cands, None)   # bilinmiyorsa satır yok
    # ipucu okumasında da her bloğun okuyan sesi görünür (tarif cinsiyet/yaşla yazılsın)
    prompt, _ = sfx._page_prompt(units)
    assert "[b1] Kız derin" in prompt and "[k1] (Nine · konuşan ses: yaşlı kadın) Tüh!" in prompt

    class Llm:
        def __init__(self):
            self.msgs, self.refs = [], []

        async def choose(self, alias, messages, choices, *, prompt=None, **kw):
            self.msgs.append(messages[0]["content"])
            self.refs.append((prompt.name, prompt.version) if prompt else None)
            return {"B": 0.9, "A": 0.05, "X": 0.05}, 0

    llm = Llm()
    ranked, fit = asyncio.run(sfx.rerank(llm, {"quote": "Tüh"}, cands, sfx.block_speaker(units, "k1")))
    assert [r["id"] for r in ranked] == ["x2", "x1"] and fit == 0.95
    assert "Sesi çıkaran: yaşlı kadın" in llm.msgs[0] and llm.refs[0] == ("sfx.pick", "5")


def test_suggest_page_gives_no_person_for_narration_text(job, pool, monkeypatch):
    """Anlatım metnindeki ipucunda okuyan anlatıcı sesi çıkaran sayılmaz (kişiyi metin söyler): seçime kişi gitmez."""
    async def fake_read(llm, units, pid, t):
        return [{"blok": "b1", "alinti": "vak vak", "tur": "yansima", "kategori": "ordek", "tarif": "ördek vaklıyor",
                 "tarif_en": "duck quacking", "yer": "birlikte"}]
    monkeypatch.setattr(sfx, "_read_page", fake_read)

    async def no_translate(text):
        return None
    monkeypatch.setattr(sfx, "translate", no_translate)
    seen = []

    async def fake_rerank(llm, cue, cands, who=None):
        seen.append(who)
        return cands, 0.9
    monkeypatch.setattr(sfx, "rerank", fake_rerank)
    asyncio.run(sfx.suggest_page(job, "p_1", "editör", llm=object()))
    assert seen and all(w is None for w in seen)


def test_back_to_back_effects_do_not_overlap(pool):
    """«pat» için uzun düşme sesi 3 sn sonraki «güm»ün başında biter; aynı anda sayılacak kadar yakın iki efektte
    öncekinin en kısa hali FX_MIN_SEC (sesin kendisi daha kısaysa kendi süresi); sonuncusu kısalmaz."""
    words = [{"i": i, "start": s, "end": s + 0.3} for i, s in enumerate((0.0, 3.0, 3.2, 8.0))]
    nrec = {"blocks": [{"id": "b1", "words": words}]}

    def cue(cid, sid, w, place="birlikte"):
        return {"id": cid, "chosen": pool[sid], "block": "b1", "words": [w, w], "place": place, "gain_db": 0.0,
                "quote": cid}
    # sıra karışık verilir: yerleşim başlangıca göre sıralanır
    pl = sfx.plan_placements(nrec, [cue("ordek2", "ordek", 3), cue("gum", "kapi", 1), cue("ordek1", "ordek", 2),
                                    cue("pat", "ruzgar", 0)])
    got = [(p["quote"], p["start"], p["length"], bool(p.get("trimmed"))) for p in pl]
    assert got == [("pat", 0.0, 3.0, True),                             # 4 sn (FX_MAX_SEC) → 3 sn
                   ("gum", 3.0, sfx.FX_MIN_SEC, True),                  # 0,2 sn sonra yenisi: en az FX_MIN_SEC
                   ("ordek1", 3.2, 1.2, False),                         # sonraki 4,8 sn uzakta: kendi süresi
                   ("ordek2", 8.0, 1.2, False)]
    for a, b in zip(pl, pl[1:]):
        assert a["start"] + a["length"] <= b["start"] or a["length"] == sfx.FX_MIN_SEC
    assert sfx.MIX_VERSION >= 3                                         # eski karışımlar yeniden yapılır


def test_stretched_word_is_a_sound_only_as_a_standalone_exclamation():
    t = "Aslan çoook korkmuştu. Güüüümmmm! O günleriiii hatırladı."
    u = [N.Unit("b1", "para", None, "anlatici-kadin", t, N.read(t))]
    assert sfx.strong_hints(u) == ["Güüüümmmm"]
    assert "çoook" not in sfx.sound_hints(u) and "günleriiii" not in sfx.sound_hints(u)
    assert "Güüüümmmm" in sfx.sound_hints(u)
