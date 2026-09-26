"""Sesli okuma (editor.production.narration) saf parçaları: Türkçe okunuş, sayfa → okuma birimleri, parçalama,
kelime zamanlarının bağlanması, medya kaplaması ve SMIL biçimi. Model yok (servis sahte). Çalıştır:

    pytest apps/editor/tests/test_narration.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
import types
import xml.etree.ElementTree as ET
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

from editor.production import narration as N  # noqa: E402


def say(text: str, lex: N.Lexicon | None = None) -> str:
    return N.spoken_text(N.read(text, lex))


# ------------------------------------------------------------------ sayılar
@pytest.mark.parametrize("n,want", [
    (0, "sıfır"), (1, "bir"), (10, "on"), (11, "on bir"), (100, "yüz"), (101, "yüz bir"), (200, "iki yüz"),
    (1000, "bin"), (1001, "bin bir"), (1923, "bin dokuz yüz yirmi üç"), (2026, "iki bin yirmi altı"),
    (10_000, "on bin"), (100_000, "yüz bin"), (1_000_000, "bir milyon"), (2_500_000, "iki milyon beş yüz bin"),
    (1_000_000_000, "bir milyar"), (-5, "eksi beş"),
])
def test_number(n, want):
    assert N.number(n) == want


@pytest.mark.parametrize("n,want", [
    (1, "birinci"), (2, "ikinci"), (3, "üçüncü"), (4, "dördüncü"), (5, "beşinci"), (6, "altıncı"), (7, "yedinci"),
    (8, "sekizinci"), (9, "dokuzuncu"), (10, "onuncu"), (20, "yirminci"), (30, "otuzuncu"), (40, "kırkıncı"),
    (60, "altmışıncı"), (90, "doksanıncı"), (100, "yüzüncü"), (1000, "bininci"), (24, "yirmi dördüncü"),
])
def test_ordinal(n, want):
    assert N.ordinal(n) == want


@pytest.mark.parametrize("text,want", [
    ("1923'te", "bin dokuz yüz yirmi üçte"),
    ("4'ü", "dördü"),                                   # dört + ünlü → dörd
    ("4'te", "dörtte"),
    ("2'nci", "ikinci"),
    ("3,5", "üç virgül beş"),
    ("0,05", "sıfır virgül sıfır beş"),
    ("2.500", "iki bin beş yüz"),
    ("1.000.000'dan", "bir milyondan"),
    ("25.09.2026", "yirmi beş eylül iki bin yirmi altı"),
    ("14:30'da", "on dört otuzda"),
    ("09:05", "dokuz sıfır beş"),
    ("%80", "yüzde seksen"),
    ("%42,7'si", "yüzde kırk iki virgül yedisi"),
    ("7-9", "yedi ila dokuz"),
    ("₺150", "yüz elli lira"),
    ("5km", "beş kilometre"),
])
def test_number_forms(text, want):
    assert say(text) == want


def test_ordinal_dot_and_sentence_end():
    assert say("3. sınıf") == "üçüncü sınıf"
    assert say("1. Dünya Savaşı") == "birinci Dünya Savaşı"
    assert say("Sayısı tam 3.") == "Sayısı tam üç."           # bloğun sonu: sayı + cümle sonu


def test_roman():
    assert say("XX. yüzyıl") == "yirminci yüzyıl"
    assert say("II. Abdülhamit") == "ikinci Abdülhamit"
    assert say("Ahmet C. Yılmaz") == "Ahmet C. Yılmaz"         # baş harf Roma rakamı sayılmaz
    assert N.roman("IIII") is None and N.roman("XIV") == 14


def test_units_and_currency_need_a_number():
    assert say("150 TL") == "yüz elli lira"
    assert say("150 TL'lik saat") == "yüz elli liralık saat"
    assert say("3 km yürüdü") == "üç kilometre yürüdü"
    assert say("TL") == "te le"                               # sayısız: kısaltma gibi


# ------------------------------------------------------------------ kısaltmalar
def test_abbreviations():
    assert say("Dr. Ahmet") == "doktor Ahmet"
    assert say("elma, armut vb. Sonra") == "elma, armut ve benzeri. Sonra"
    assert say("elma, armut vb. meyveler") == "elma, armut ve benzeri meyveler"
    assert say("M.Ö. 500") == "milattan önce beş yüz"


def test_acronyms():
    assert say("TBMM'nin") == "te be me menin"
    assert say("ABD'de") == "a be dede"
    assert say("NATO") == "nato"
    assert say("ODTÜ'de") == "odtüde"
    assert say("AH!") == "ah!"                               # iki harfli ünlem
    assert say("SİHİRLİ ORMAN") == "sihirli orman"             # tamamı büyük harfli başlık


def test_lexicon_job_over_publisher_and_suffix():
    lex = N.Lexicon([{"word": "Timaş", "say": "tımaş"}], [{"word": "Timaş", "say": "timaş"}, {"word": "AB", "say": "a be"}])
    assert say("Timaş'ın kitabı", lex) == "tımaşın kitabı"
    assert say("timaş,", lex) == "tımaş,"
    assert say("AB üyesi", lex) == "a be üyesi"


def test_word_offsets_and_punctuation():
    text = "– Bak, bir yıldız!"
    ws = N.read(text)
    assert [w.text for w in ws] == ["–", "Bak,", "bir", "yıldız!"]
    assert [text[w.start:w.end] for w in ws] == [w.text for w in ws]
    assert ws[0].say == [] and ws[0].spoken == ""              # tire okunmaz
    assert ws[1].spoken == "Bak," and ws[1].say == ["Bak"]
    assert say("“Gel,” dedi.") == "Gel, dedi."                 # tırnak okunmaz
    assert say("Ve sonra...") == "Ve sonra…"


def test_tr_lower_upper():
    assert N.tr_lower("IŞIK İzmir") == "ışık izmir"
    assert N.tr_upper("ışık izmir") == "IŞIK İZMİR"


# ------------------------------------------------------------------ sayfa → birimler → parçalar
PAGE = {
    "id": "p_1", "layout": "art-top",
    "text": {"box": {"x": 14, "y": 126, "w": 141, "h": 88}, "blocks": [
        {"id": "c1", "kind": "para", "runs": [{"text": "Elif pencereden baktı. "}, {"text": "Ayşe", "color": "#B0341C"},
                                              {"text": " çok heyecanlıydı."}]},
        {"id": "c2", "kind": "sound", "runs": [{"text": "Güm!"}]}]},
    "bubbles": [{"id": "b1", "speaker": "Elif", "text": "Bak, bir yıldız!", "box": {"x": 12, "y": 14, "w": 52, "h": 22}},
                {"id": "b2", "speaker": "Kim", "text": "Nerede?", "box": {"x": 90, "y": 14, "w": 40, "h": 20}}],
    "texts": [{"id": "t1", "box": {"x": 20, "y": 200, "w": 60, "h": 18}, "runs": [{"text": "SON"}], "z": 4}],
    "shapes": [{"id": "s1", "kind": "sign", "runs": [{"text": "Sihirli Orman"}]}],
}
CFG = {"narrator": "anlatici-kadin", "characters": {"Elif": "cocuk-kiz"}}


def test_page_units_reading_order_and_voices():
    us = N.page_units(PAGE, CFG, N.Lexicon())
    assert [u.id for u in us] == ["b1", "b2", "c1", "c2", "t1"]     # üstteki balonlar önce, şekil yazısı yok
    assert [u.voice for u in us] == ["cocuk-kiz", "anlatici-kadin", "anlatici-kadin", "anlatici-kadin", "anlatici-kadin"]
    assert us[2].text == "Elif pencereden baktı. Ayşe çok heyecanlıydı."   # run'lar birleşir
    assert us[0].speaker == "Elif" and us[0].kind == "bubble"


def test_pieces_split_sentences_and_pauses():
    us = N.page_units(PAGE, CFG, N.Lexicon())
    ps = N.pieces(us)
    assert [p.text for p in ps] == ["Bak, bir yıldız!", "Nerede?", "Elif pencereden baktı.", "Ayşe çok heyecanlıydı.",
                                    "Güm!", "son"]
    assert ps[0].pause_ms == N.PAUSE["bubble"]
    assert ps[-1].pause_ms == N.PAUSE["page"]
    # her parça birimin kelimelerini sırayla kapsar, kelime kaybolmaz
    covered = {(p.unit, k) for p in ps for k in p.words}
    assert covered == {(ui, w.i) for ui, u in enumerate(us) for w in u.words}


def test_long_sentence_is_split_without_losing_words():
    long = ", ".join(["uzun bir cümlenin parçası"] * 40) + "."
    us = [N.Unit("x", "para", None, "anlatici-kadin", long, N.read(long))]
    ps = N.pieces(us)
    assert len(ps) > 1
    assert all(len(p.text) <= N.SEG_CHARS * 1.7 for p in ps)
    assert [k for p in ps for k in p.words] == list(range(len(us[0].words)))


# ------------------------------------------------------------------ zamanlar
def test_fill_times_interpolates_by_letters():
    t, est = N.fill_times([(0.0, 0.5), None, None, (2.0, 2.4)], [4, 2, 6, 3], 0.0, 3.0)
    assert est == [False, True, True, False]
    assert t[1][0] == 0.5 and t[2][1] == 2.0
    assert abs((t[1][1] - t[1][0]) * 3 - (t[2][1] - t[2][0])) < 1e-6     # 2 harf : 6 harf
    t2, est2 = N.fill_times([None, None], [1, 1], 1.0, 3.0)
    assert t2 == [(1.0, 2.0), (2.0, 3.0)] and est2 == [True, True]


def test_word_times_merge_expanded_words():
    # "1923'te geldi." → okunuş 5 + 1 kelime; ekranda iki kelime
    u = N.Unit("c1", "para", None, "anlatici-kadin", "1923'te geldi.", N.read("1923'te geldi."))
    ps = N.pieces([u])
    assert ps[0].text == "bin dokuz yüz yirmi üçte geldi."
    seg = {"start": 0.0, "end": 3.0, "words": [
        {"start": 0.1, "end": 0.3}, {"start": 0.3, "end": 0.6}, {"start": 0.6, "end": 0.8}, None,
        {"start": 1.2, "end": 1.6}, {"start": 1.8, "end": 2.4}]}
    blocks = N.word_times([u], ps, [seg])
    w = blocks[0]["words"]
    # kısa boşluk (0,2 sn) önceki kelimeye katılır; parçanın son kelimesi 0,3 sn uzar (parça sonunu aşmadan)
    assert (w[0]["start"], w[0]["end"]) == (0.1, 1.8) and w[0]["estimated"] is True   # bir parçası tahmin
    assert (w[1]["start"], w[1]["end"]) == (1.8, 2.7) and "estimated" not in w[1]
    assert w[0]["char"] == [0, 7] and w[1]["char"] == [8, 14]
    assert blocks[0]["start"] == 0.1 and blocks[0]["end"] == 2.7


def test_contiguous_keeps_long_pauses():
    t = N.contiguous([(0.0, 0.4), (0.5, 0.9), (2.0, 2.3)], 2.4)
    assert t == [(0.0, 0.5), (0.5, 0.9), (2.0, 2.4)]          # 1,1 sn duraklama korunur


# ------------------------------------------------------------------ iş klasörüyle uçtan uca (sahte servis)
@pytest.fixture()
def job(tmp_path, monkeypatch):
    from editor.production import studio
    monkeypatch.setattr(studio, "root", lambda: tmp_path)
    d = tmp_path / "20260925000000abcdef"
    d.mkdir()
    page2 = {"id": "p_2", "layout": "blank", "text": None, "bubbles": [], "texts": []}
    studio.write(d, "plan.json", {"version": 1, "rev": 1, "pages": [PAGE, page2], "assets": {}})
    return d


def _fake_service(calls):
    async def call(body, timeout=1800.0):
        calls.append(body)
        segs, pos = [], 0.0
        for s in body["segments"]:
            n = max(1, len(s.get("words") or []))
            seg = {"start": pos, "end": pos + n * 0.4, "aligned": True,
                   "words": [{"start": round(pos + i * 0.4, 3), "end": round(pos + i * 0.4 + 0.3, 3), "score": 0.9}
                             for i in range(len(s.get("words") or []))]}
            segs.append(seg)
            pos = seg["end"] + s["pause_ms"] / 1000
        return {"audio": base64.b64encode(b"ID3fake").decode(), "format": body["format"], "sample_rate": 48000,
                "duration": round(pos, 3), "seconds": 0.1, "segments": segs}
    return call


def test_narrate_page_status_overlay_and_smil(job, monkeypatch):
    calls = []
    monkeypatch.setattr(N, "_call", _fake_service(calls))
    N.set_settings(job, "anlatici-kadin", {"Elif": "cocuk-kiz"}, "editör")
    st = {r["id"]: r["status"] for r in N.status(job)}
    assert st == {"p_1": "missing", "p_2": "empty"}

    res = asyncio.run(N.narrate_page(job, "p_1", "editör"))
    assert res["status"] == "done"
    # iki ses referansı bir kez tarifle üretildi (yayınevi düzeyinde), sayfa referansla klonlandı
    designs = [c for c in calls if c["segments"][0]["voice"].get("design")]
    assert {c["segments"][0]["voice"]["design"] for c in designs} == {N.voice("anlatici-kadin")["design"],
                                                                        N.voice("cocuk-kiz")["design"]}
    page_call = calls[-1]
    assert all(s["voice"].get("ref_audio") and s["voice"].get("ref_text") for s in page_call["segments"])
    assert page_call["format"] == "mp3" and page_call["align"] is True
    assert (N._root() / "sesler" / "cocuk-kiz.wav").exists()

    assert {r["id"]: r["status"] for r in N.status(job)}["p_1"] == "done"
    mo = N.media_overlay(job)
    assert mo["complete"] is True and mo["missing"] == [] and mo["format"] == "mp3"
    pg = mo["pages"][0]
    assert pg["page"] == "p_1" and pg["no"] == 4 and pg["href"] == "ses/sayfa/p_1.mp3" and Path(pg["audio"]).exists()
    ids = [b["id"] for b in pg["blocks"]]
    assert ids == ["b1", "b2", "c1", "c2", "t1"]
    w0 = pg["blocks"][0]["words"][0]
    assert w0["id"] == "w-b1-0" and w0["text"] == "Bak," and w0["char"] == [0, 4] and w0["start"] is not None
    for b in pg["blocks"]:
        ends = [w["end"] for w in b["words"] if w["start"] is not None]
        assert ends == sorted(ends)                             # kelimeler zamanda sıralı
        for w in b["words"]:
            assert b["text"][w["char"][0]:w["char"][1]] == w["text"]

    doc = N.smil(pg, "sayfa-4.xhtml", "ses/sayfa/p_1.mp3")
    root = ET.fromstring(doc.encode())
    ns = {"s": "http://www.w3.org/ns/SMIL"}
    pars = root.findall(".//s:par", ns)
    assert len(pars) == sum(1 for b in pg["blocks"] for w in b["words"] if w["start"] is not None)
    a = pars[0].find("s:audio", ns)
    assert pars[0].find("s:text", ns).get("src") == "sayfa-4.xhtml#w-b1-0"
    assert a.get("clipBegin") == N.clock(w0["start"]) and a.get("clipEnd") == N.clock(w0["end"])

    # metin değişince sayfa «güncel değil» olur ve kaplamaya girmez
    from editor.production import studio
    pl = studio.read(job, "plan.json")
    pl["pages"][0]["bubbles"][0]["text"] = "Bak, iki yıldız!"
    studio.write(job, "plan.json", pl)
    assert {r["id"]: r["status"] for r in N.status(job)}["p_1"] == "stale"
    mo = N.media_overlay(job)
    assert mo["complete"] is False and mo["stale"] == ["p_1"] and mo["pages"] == []
    # sözlük değişince de
    pl["pages"][0]["bubbles"][0]["text"] = "Bak, bir yıldız!"
    studio.write(job, "plan.json", pl)
    assert {r["id"]: r["status"] for r in N.status(job)}["p_1"] == "done"
    N.set_lexicon(job, "job", [{"word": "yıldız", "say": "yıl-dız"}], "editör")
    assert {r["id"]: r["status"] for r in N.status(job)}["p_1"] == "stale"


def test_settings_and_lexicon_validation(job):
    with pytest.raises(ValueError):
        N.set_settings(job, "yok-boyle-ses", {}, "e")
    with pytest.raises(ValueError):
        N.set_settings(job, "anlatici-kadin", {"Elif": "yok"}, "e")
    out = N.set_lexicon(job, "publisher", [{"word": "Timaş", "say": "tımaş"}, {"word": "timaş", "say": "tımmaş"},
                                           {"word": "", "say": "x"}], "e")
    assert out == [{"word": "timaş", "say": "tımmaş", "by": "e", "at": out[0]["at"]}]
    assert json.loads((N._root() / "sozluk.json").read_text())[0]["say"] == "tımmaş"


def test_default_voices_from_character_descriptions(job):
    from editor.production import studio
    studio.write(job, "artplan.json", {"characters": [
        {"name": "Elif", "species": "a 7-year-old girl", "base_look": ""},
        {"name": "Dede", "species": "human", "base_look": "an old man with a white beard"},
        {"name": "Tilki", "species": "a small fox", "base_look": ""}]})
    cfg = N.settings_of(job)
    assert cfg["source"] == "auto" and cfg["characters"] == {"Elif": "cocuk-kiz", "Dede": "yasli-erkek"}


def test_clock():
    assert N.clock(0) == "0:00:00.000"
    assert N.clock(83.4567) == "0:01:23.457"
    assert N.clock(3723.5) == "1:02:03.500"
