"""Sesli okumada ifade katmanı (editor.production.expression): cümleler, editör işareti, üretime yansıma (narration
kancası), metin değişince işaretin düşmesi, ZEKİ AI önerisinin karar kuralı ve vurgu oylaması. Model yok (sahte
servis ve sahte model). Çalıştır:

    pytest apps/editor/tests/test_expression.py
"""

from __future__ import annotations

import asyncio
import json
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

from editor.production import expression as X  # noqa: E402
from editor.production import narration as N  # noqa: E402

PAGE = {
    "id": "p_1", "layout": "art-top",
    "text": {"box": {"x": 14, "y": 126, "w": 141, "h": 88}, "blocks": [
        {"id": "c1", "kind": "para", "runs": [{"text": "Aslan topu ona uzattı. “Buyur! Birlikte oynayalım mı?”"}]},
        {"id": "c2", "kind": "para", "runs": [{"text": "Güneş batarken annesi, “Eve dönme zamanı,” dedi."}]},
        {"id": "c3", "kind": "para", "runs": [{"text": "Hep birlikte koşarak büyük parka gittiler!"}]}]},
    "bubbles": [], "texts": [],
}


@pytest.fixture()
def job(tmp_path, monkeypatch):
    from editor.production import studio
    monkeypatch.setattr(studio, "root", lambda: tmp_path)
    d = tmp_path / "20260927000000abcdef"
    d.mkdir()
    studio.write(d, "plan.json", {"version": 1, "rev": 1, "pages": [PAGE], "assets": {}})
    N.set_settings(d, "anlatici-kadin", {}, "editör")
    return d


def _wav(sec: float, sr: int = 8000) -> bytes:
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"\x01\x00" * int(sec * sr))
    return buf.getvalue()


# ifade örneği adaylarının ölçüsü (tohum → ölçü); taban 200 Hz
MEASURE = {None: {"f0": 200.0, "energy_db": -21.0, "voiced_ratio": 0.85, "cer": 0.0},
           11: {"f0": 262.0, "energy_db": -19.0, "voiced_ratio": 0.8, "cer": 0.02},     # +%31: kimlik sınırı dışı
           22: {"f0": 228.0, "energy_db": -20.0, "voiced_ratio": 0.82, "cer": 0.01},    # +%14: seçilir
           33: {"f0": 232.0, "energy_db": -20.5, "voiced_ratio": 0.8, "cer": 0.2}}      # anlaşılmıyor


def _fake_service(calls):
    async def call(body, timeout=1800.0):
        import base64
        calls.append(body)
        segs, pos = [], 0.0
        for s in body["segments"]:
            n = max(1, len(s.get("words") or []))
            seg = {"start": pos, "end": pos + n * 0.4, "aligned": True,
                   "words": [{"start": round(pos + i * 0.4, 3), "end": round(pos + i * 0.4 + 0.3, 3), "score": 0.9}
                             for i in range(len(s.get("words") or []))]}
            if body.get("measure"):
                seg["measure"] = MEASURE[s.get("seed") if s.get("style") else None]
            segs.append(seg)
            pos = seg["end"] + s["pause_ms"] / 1000
        audio = _wav(pos) if body["format"] == "wav" else b"ID3fake"
        return {"audio": base64.b64encode(audio).decode(), "format": body["format"], "sample_rate": 8000,
                "duration": round(pos, 3), "seconds": 0.1, "segments": segs}
    return call


def test_sentences_follow_piece_boundaries(job):
    rows = X.sentences(job, PAGE)
    assert [r["key"] for r in rows] == ["c1:0", "c1:1", "c1:2", "c2:0", "c3:0"]
    assert [r["text"] for r in rows][:4] == ["Aslan topu ona uzattı.", "“Buyur!", "Birlikte oynayalım mı?”",
                                             "Güneş batarken annesi, “Eve dönme zamanı,” dedi."]
    assert rows[2]["words"] == ["Birlikte", "oynayalım", "mı"]
    # her parça tam olarak bir cümlenin içinde
    units = N.page_units(PAGE, N.settings_of(job), N.lexicon(job))
    for p in N.pieces(units):
        sents = X.unit_sentences(units[p.unit])
        assert any(set(p.words) <= set(s) for s in sents)


def test_set_marks_validation(job):
    with pytest.raises(ValueError):
        X.set_marks(job, "p_1", [{"key": "c1:1", "label": "bagiris"}], "editör")
    with pytest.raises(ValueError):
        X.set_marks(job, "p_1", [{"key": "c1:2", "label": "heyecan", "emphasis": ["Yok"]}], "editör")
    with pytest.raises(KeyError):
        X.set_marks(job, "p_1", [{"key": "c9:0", "label": "notr"}], "editör")
    v = X.set_marks(job, "p_1", [{"key": "c1:2", "label": "heyecan", "emphasis": ["Birlikte"]}], "editör")
    row = next(s for s in v["sentences"] if s["key"] == "c1:2")
    assert row["label"] == "heyecan" and row["emphasis"] == ["Birlikte"] and row["source"] == "editor"
    assert [lab["id"] for lab in v["labels"]] == list(X.LABELS)


def test_marks_reach_the_voice_service_and_make_page_stale(job, monkeypatch):
    calls = []
    monkeypatch.setattr(N, "_call", _fake_service(calls))
    _u, plain, h0 = N.page_input(job, PAGE)
    asyncio.run(N.narrate_page(job, "p_1", "editör"))
    assert {r["id"]: r["status"] for r in N.status(job)}["p_1"] == "done"
    first = calls[-1]["segments"]
    assert not any(k in s for s in first for k in ("style", "clone", "rate", "pause_before_ms"))   # işaretsiz: eski gövde
    assert not any(s["voice"].get("prompt_audio") for s in first)

    X.set_marks(job, "p_1", [{"key": "c1:2", "label": "heyecan", "emphasis": ["oynayalım"]},
                             {"key": "c2:0", "label": "fisilti"}, {"key": "c3:0", "label": "uzuntu"}], "editör")
    assert {r["id"]: r["status"] for r in N.status(job)}["p_1"] == "stale"
    _u, plist, h1 = N.page_input(job, PAGE)
    assert h1 != h0
    asyncio.run(N.narrate_page(job, "p_1", "editör"))
    segs = calls[-1]["segments"]
    by_text = {s["text"]: s for s in segs}
    # heyecan: ton yok (yükselen tonlar ölçümde aştı), hız ve duraklama; vurgu kelimeden önce kısa durak,
    # hizalanan kelimeler değişmez
    short = by_text["Birlikte, oynayalım mı?"]
    assert "rate" not in short and "style" not in short                  # kısa ünlem hızlandırılmaz
    assert not short["voice"].get("prompt_audio") and short["words"] == ["Birlikte", "oynayalım", "mı"]
    # uzun üzüntü cümlesi: ifade örneğinin devamı (tam klon, talimat metne girmez), önce durak
    long = by_text["Hep birlikte koşarak büyük parka gittiler!"]
    assert long["voice"].get("prompt_audio") and long["voice"].get("ref_text") and "style" not in long
    assert long["pause_before_ms"] == X.TABLE["uzuntu"]["before_ms"]
    # örnek bir kez üretildi: taban + üç aday ölçüldü, kimlik sınırında olan (+%14) seçildi
    ex_calls = [c for c in calls if c.get("measure")]
    assert len(ex_calls) == 1 and len(ex_calls[0]["segments"]) == 4
    meta = json.loads((N._root() / "ifade" / "anlatici-kadin" / "uzuntu.json").read_text())
    assert meta["chosen"]["seed"] == 22 and meta["chosen"]["shift"] == 14.0
    # fısıltı: talimat yolu (referans-yalnız), önce durak, sonu uzar
    fis = by_text["Güneş batarken annesi, Eve dönme zamanı, dedi."]
    assert fis["style"] == X.TABLE["fisilti"]["style"] and fis["clone"] == "ref"
    assert fis["pause_before_ms"] == X.TABLE["fisilti"]["before_ms"]
    plain_fis = [p for p in plain if p.text.startswith("Güneş")][0]
    assert fis["pause_ms"] == int(round(plain_fis.pause_ms * X.TABLE["fisilti"]["after"]))
    neutral = by_text["Aslan topu ona uzattı."]
    assert "style" not in neutral and "clone" not in neutral and not neutral["voice"].get("prompt_audio")
    assert {r["id"]: r["status"] for r in N.status(job)}["p_1"] == "done"
    # ikinci seslendirme örneği yeniden üretmez
    asyncio.run(N.narrate_page(job, "p_1", "editör"))
    assert len([c for c in calls if c.get("measure")]) == 1


def test_pick_example_rules():
    base = MEASURE[None]
    cands = [{"seed": s, "measure": MEASURE[s]} for s in (11, 22, 33)]
    assert X.pick_example("uzuntu", base, cands)["seed"] == 22
    assert X.pick_example("uzuntu", base, [cands[0], cands[2]]) is None
    # tonu yükselten ifadelerin yolu yok (hız/duraklama); tabloda örnek hedefi yalnız ton verilenlerde
    assert {k for k, r in X.TABLE.items() if r["method"]} == {"fisilti", "uzuntu"}      # biri kimlik, biri anlaşılırlık dışı


def test_text_change_drops_only_that_mark(job):
    from editor.production import studio
    X.set_marks(job, "p_1", [{"key": "c1:0", "label": "merak"}, {"key": "c2:0", "label": "uzuntu"}], "editör")
    pl = studio.read(job, "plan.json")
    pl["pages"][0]["text"]["blocks"][0]["runs"][0]["text"] = "Aslan topu ona verdi. “Buyur! Birlikte oynayalım mı?”"
    studio.write(job, "plan.json", pl)
    pg = pl["pages"][0]
    v = X.view(job, "p_1")
    rows = {s["key"]: s for s in v["sentences"]}
    assert rows["c1:0"]["label"] == "notr" and rows["c1:0"]["dropped"] is True
    assert rows["c2:0"]["label"] == "uzuntu" and rows["c2:0"]["dropped"] is False
    _u, plist, _h = N.page_input(job, pg)
    changed = [p for p in plist if p.text.startswith("Aslan")][0]
    assert not getattr(changed, "extra", None)


def test_decide_threshold_and_margin():
    assert X.decide({"notr": 0.2, "heyecan": 0.7}) == "heyecan"
    assert X.decide({"notr": 0.45, "heyecan": 0.55}) == "notr"          # nötrün önünde farkı az
    assert X.decide({"notr": 0.1, "heyecan": 0.45, "nese": 0.45}) == "notr"   # en olası eşiğin altında
    assert X.decide({"notr": 0.9, "heyecan": 0.1}) == "notr"


class FakeLlm:
    """choose: cümle metnine göre sabit dağılım (seçenek sırası iki okumada ters); chat: üç vurgu okuması."""

    def __init__(self, emph_reads):
        self.emph_reads = list(emph_reads)
        self.choose_calls = 0

    async def choose(self, alias, messages, choices, **kw):
        self.choose_calls += 1
        text = messages[0]["content"]
        want = "heyecan" if "Cümle [3]" in text else "fisilti" if "Cümle [4]" in text else "notr"
        # prompt'taki seçenek sırasını oku: "A) Nötr — …"
        order = []
        for line in text.splitlines():
            if len(line) > 3 and line[1] == ")" and line[0] in "ABCDEFGHI":
                name = line[3:].split(" — ")[0]
                order.append(next(k for k, v in X.LABEL_TR.items() if v == name))
        return {c: (0.8 if order[i] == want else 0.2 / (len(choices) - 1)) for i, c in enumerate(choices)}, 1

    async def chat(self, alias, messages, **kw):
        return {"items": self.emph_reads.pop(0)}, 1


def test_suggest_votes_and_keeps_editor_marks(job):
    X.set_marks(job, "p_1", [{"key": "c1:0", "label": "korku"}], "editör")
    reads = [[{"n": 3, "words": ["Birlikte", "hiç"]}], [{"n": 3, "words": ["Birlikte"]}, {"n": 1, "words": ["topu"]}],
             [{"n": 3, "words": ["oynayalım"]}]]
    llm = FakeLlm(reads)
    v = asyncio.run(X.suggest(job, "p_1", llm, "editör"))
    rows = {s["key"]: s for s in v["sentences"]}
    assert llm.choose_calls == 10                                   # 5 cümle × 2 okuma (seçenek sırası düz/ters)
    assert rows["c1:0"]["label"] == "korku" and rows["c1:0"]["source"] == "editor"   # editörünkine dokunulmaz
    assert rows["c1:2"]["label"] == "heyecan" and rows["c1:2"]["source"] == "ai"
    assert rows["c1:2"]["emphasis"] == ["Birlikte"]                  # 2/3 okuma; «hiç» cümlede yok, «oynayalım» 1/3
    assert rows["c1:2"]["probs"]["heyecan"] == pytest.approx(0.8)
    assert rows["c2:0"]["label"] == "fisilti"
    assert rows["c1:1"]["label"] == "notr"
    assert v["suggested"]["by"] == "editör"


def test_sample_sentence_only_that_sentence(job, monkeypatch):
    calls = []
    monkeypatch.setattr(N, "_call", _fake_service(calls))
    data = asyncio.run(X.sample_sentence(job, "p_1", "c2:0", "fisilti", ["zamanı"]))
    assert data == b"ID3fake"
    body = calls[-1]
    assert [s["text"] for s in body["segments"]] == ["Güneş batarken annesi, Eve dönme, zamanı, dedi."]
    assert body["segments"][0]["style"] == X.TABLE["fisilti"]["style"] and body["align"] is False
    assert body["segments"][0]["pause_ms"] == 0
    n = len(calls)
    asyncio.run(X.sample_sentence(job, "p_1", "c2:0", "fisilti", ["zamanı"]))
    assert len(calls) == n                                          # aynı örnek önbellekten


# ------------------------------------------------------------------ 2026-09-28 tam kitap dinlemesi
def test_emphasis_is_short_and_skips_aux_verbs_and_caps():
    assert X._emphasize("Kimse yardım etmedi ona", ["etmedi"]) == "Kimse yardım etmedi ona"
    assert X._emphasize("BİLİM VOMBATI AŞKINA", ["AŞKINA"]) == "BİLİM VOMBATI AŞKINA"
    assert X._emphasize("Aslan birden kükredi", ["kükredi"]) == "Aslan birden, kükredi"
    # öbek bölünmez: niteleyici, tamlayan, ilgeç
    assert X._emphasize("Bu çok eğlenceli bir oyun", ["eğlenceli"]) == "Bu çok eğlenceli bir oyun"
    assert X._emphasize("aslanın kükremesiydi", ["kükremesiydi"]) == "aslanın kükremesiydi"
    assert X._emphasize("dönmüştü bile", ["bile"]) == "dönmüştü bile"


def test_narrator_lead_in_is_neutral_when_sentence_has_speech(job):
    from editor.production import studio
    page = json.loads(json.dumps(PAGE))
    page["text"]["blocks"][2]["runs"] = [
        {"text": "İçinden bir ses durmadan fısıldıyordu: “Hemen eve dön, hava kararıyor!”"}]
    studio.write(job, "plan.json", {"version": 1, "rev": 2, "pages": [page], "assets": {}})
    X.set_marks(job, "p_1", [{"key": "c3:0", "label": "fisilti"}], "editör")
    _units, plist, _h = N.page_input(job, page)
    by = {p.text: getattr(p, "extra", {}) for p in plist}
    assert by["İçinden bir ses durmadan fısıldıyordu:"] == {}
    assert by["Hemen eve dön, hava kararıyor!"]["label"] == "fisilti"
    # fısıltı üretimden sonra kısılır: tonlu (5+ kelime) parçada kalan fark −5 dB
    assert by["Hemen eve dön, hava kararıyor!"]["tone"] is True
    assert by["Hemen eve dön, hava kararıyor!"]["gain_db"] == X.TABLE["fisilti"]["gain_tone_db"]


def test_short_whisper_has_no_tone_but_is_quiet(job):
    from editor.production import studio
    page = json.loads(json.dumps(PAGE))
    page["text"]["blocks"][2]["runs"] = [{"text": "“Şşş, uyuyor.”"}]
    studio.write(job, "plan.json", {"version": 1, "rev": 3, "pages": [page], "assets": {}})
    X.set_marks(job, "p_1", [{"key": "c3:0", "label": "fisilti"}], "editör")
    _units, plist, _h = N.page_input(job, page)
    ex = next(p.extra for p in plist if "uyuyor" in p.text)
    assert ex["tone"] is False and ex["gain_db"] == X.TABLE["fisilti"]["gain_db"]
