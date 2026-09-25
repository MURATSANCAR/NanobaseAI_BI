"""Stüdyo otomatikleri (editor.production.palette / colorize / bubbles): model ve veritabanı yok; resimler numpy ile
çizilir, görsel okuma sahte `locate` ile. Çalıştır (editor-py imajında):

    pytest apps/editor/tests/test_autos.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from editor.production import bubbles as B, colorize as C, palette as P  # noqa: E402

RED, GREEN = "#B0341C", "#1F6F5B"


def _png(path: Path, arr: np.ndarray) -> Path:
    Image.fromarray(np.asarray(arr, dtype=np.uint8)).save(path)
    return path


def _fill(h: int, w: int, hx: str) -> np.ndarray:
    return np.tile(P._hex_rgb(hx), (h, w, 1))


def _de(a: str, b: str) -> float:
    return float(P.delta_e(P.hex_lab(a), P.hex_lab(b)))


# ------------------------------------------------------------------ palet
@pytest.mark.parametrize("lab1,lab2,want", [
    ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
    ((50.0, 0.0, 0.0), (50.0, -1.0, 2.0), 2.3669),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
])
def test_ciede2000_reference(lab1, lab2, want):
    assert float(P.delta_e(lab1, lab2)) == pytest.approx(want, abs=1e-3)


def test_contrast_and_lab_roundtrip():
    assert P.contrast("#000000") == pytest.approx(21.0)
    assert P.contrast("#FFFFFF") == pytest.approx(1.0)
    for hx in ("#1F3B73", "#B0341C", "#8A6500"):
        assert P._rgb_hex(P.lab_to_rgb(P.hex_lab(hx))) == hx


def test_timas_kids_obey_rules():
    hexes = [t["hex"] for t in P.TIMAS_KIDS]
    assert len(hexes) == 8 and len({t["name"] for t in P.TIMAS_KIDS}) == 8
    for hx in hexes:
        L, c, h = P._lch(P.hex_lab(hx))
        assert P.contrast(hx) >= P.MIN_CONTRAST, hx
        assert P.C_MIN <= c <= P.c_max(h) + 0.5, (hx, c, h)
        assert L >= P.L_MIN
        assert _de(P.print_safe(P.hex_lab(hx)), hx) < 1.0          # zaten basılabilir: değişmez
    for i, a in enumerate(hexes):
        for b in hexes[i + 1:]:
            assert _de(a, b) >= P.MIN_DE, (a, b, _de(a, b))


def test_extract_from_book_art(tmp_path):
    img = _fill(240, 320, "#FFFFFF")
    img[:, :80] = P._hex_rgb("#A83A22")          # kiremit
    img[:, 80:150] = P._hex_rgb("#203C78")       # gece mavisi
    img[:120, 150:260] = P._hex_rgb("#F5E08A")   # açık pastel sarı: okunmaz, koyulaştırmak rengi değiştirir → elenir
    img[120:, 150:230] = P._hex_rgb("#2A7A3A")   # yeşil
    p = _png(tmp_path / "s1.png", img)
    pal = P.extract([p], n=6)
    assert pal == P.extract([p], n=6)             # deterministik
    assert len(pal) == 6
    resim = [c for c in pal if c["source"] == "resim"]
    assert len(resim) == 3
    for want in ("#A83A22", "#203C78", "#2A7A3A"):
        assert min(_de(c["hex"], want) for c in resim) < 3, want
    assert all(_de(c["hex"], "#F5E08A") > 20 for c in pal)
    assert {c["source"] for c in pal} == {"resim", "timas"}
    assert all(P.contrast(c["hex"]) >= P.MIN_CONTRAST for c in pal)
    assert len({c["name"] for c in pal}) == 6
    for i, a in enumerate(pal):
        for b in pal[i + 1:]:
            assert _de(a["hex"], b["hex"]) >= P.MIN_DE


def test_extract_clamps_screen_blue_and_darkens_light_colour(tmp_path):
    img = _fill(100, 200, "#0000FF")
    img[:, 100:] = P._hex_rgb("#3F8FCF")          # orta mavi: kontrast < 4,5, biraz koyulaşınca geçer
    pal = P.extract([_png(tmp_path / "b.png", img)], n=2)
    assert [c["source"] for c in pal] == ["resim", "resim"]
    for c in pal:
        L, ch, h = P._lch(P.hex_lab(c["hex"]))
        assert ch <= P.C_MAX_BLUE + 0.5 and P.contrast(c["hex"]) >= P.MIN_CONTRAST


def test_extract_grey_or_missing_art_falls_back_to_timas(tmp_path):
    grey = _png(tmp_path / "g.png", _fill(50, 50, "#808080"))
    for paths in ([grey], [tmp_path / "yok.png"], []):
        pal = P.extract(paths, n=5)
        assert [c["hex"] for c in pal] == [t["hex"] for t in P.TIMAS_KIDS[:5]]
        assert [c["name"] for c in pal] == [t["name"] for t in P.TIMAS_KIDS[:5]]
        assert {c["source"] for c in pal} == {"timas"}


def test_names_are_turkish_and_unique():
    assert P.name_for("#1F3B73") == "Gece mavisi"
    assert P.name_for("#B0341C") == "Kiremit"
    assert P.name_for("#B0341C", {"Kiremit"}) != "Kiremit"


def test_assign_characters_distinct_and_stable():
    colors = [{"hex": "#1F3B73"}, {"hex": "#243F78"}, {"hex": RED}]
    chars = [{"name": "Ayşe", "role": "YAN"}, {"name": "Elif", "role": "ANA"}]
    got = P.assign_characters(chars, colors)
    assert got == {"Elif": "#1F3B73", "Ayşe": RED}               # ana karakter önce; ikinci en uzak renk
    assert got == P.assign_characters(chars, colors)
    many = [{"name": n} for n in ("A", "B", "C", "D", "E")]
    got = P.assign_characters(many, [t["hex"] for t in P.TIMAS_KIDS[:2]])
    assert len(got) == 5
    counts = [list(got.values()).count(h) for h in {*got.values()}]
    assert max(counts) - min(counts) <= 1
    assert P.assign_characters(many, []) == {}


# ------------------------------------------------------------------ renkli yazı
CHARS = {"Elif": RED, "Ayşe": GREEN}


def _styled(blocks) -> list[tuple[str, str | None]]:
    return [(r["text"], r.get("color")) for b in blocks for r in b["runs"] if r.get("source") == "auto"]


def test_names_with_turkish_suffixes():
    out = C.apply([{"id": "c0b0", "kind": "para",
                    "text": "Elif'in kedisi Ayşe’ye koştu. ELİF'İN sesi duyuldu. Elifin değil."}], CHARS, [])
    assert _styled(out) == [("Elif'in", RED), ("Ayşe’ye", GREEN), ("ELİF'İN", RED)]
    assert "".join(r["text"] for r in out[0]["runs"]) == \
        "Elif'in kedisi Ayşe’ye koştu. ELİF'İN sesi duyuldu. Elifin değil."
    assert all(r.get("weight") == 700 for r in out[0]["runs"] if r.get("source") == "auto")
    assert "text" not in out[0] and out[0]["id"] == "c0b0"


def test_turkish_dotted_i_and_common_words():
    chars = {"Işık": RED, "İpek": GREEN, "Can": "#1F3B73"}
    out = C.apply([{"id": "x", "kind": "para",
                    "text": "Işık'la İpek bahçede. Bir ışık yandı. IŞIK geldi. Can, canım dedi; Canan Can'a baktı."}],
                  chars, [])
    assert [t for t, _ in _styled(out)] == ["Işık'la", "İpek", "IŞIK", "Can", "Can'a"]


def test_sound_block_and_inline_sound():
    pal = {"colors": [{"hex": RED}, {"hex": "#8A6500"}]}
    out = C.apply([{"id": "a", "kind": "para", "text": "Güüüümmm!"},
                   {"id": "b", "kind": "para", "text": "Kapı gıcııırrr diye açıldı."}], {"Elif": RED}, pal,
                  body_size=16)
    assert out[0]["kind"] == "sound"
    assert out[0]["runs"] == [{"text": "Güüüümmm!", "color": "#8A6500", "weight": 800, "font": "heading",
                               "size": 21.6, "source": "auto"}]         # vurgu: karaktere verilmemiş ilk renk
    assert out[1]["kind"] == "para"
    assert [r["text"] for r in out[1]["runs"]] == ["Kapı ", "gıcııırrr", " diye açıldı."]
    assert out[1]["runs"][1]["font"] == "heading"
    assert C.apply([{"id": "c", "kind": "para", "text": "Yıl 2000 idi."}], {}, pal)[0]["runs"] == \
        [{"text": "Yıl 2000 idi."}]                                   # rakam tekrarı ses değil


def test_editor_runs_are_never_touched():
    ed = {"text": "Elif ", "color": "#000000", "source": "editor"}
    bare = {"text": "Ayşe", "color": "#123456"}                       # kaynağı yazılmamış biçimli run: korunur
    blocks = [{"id": "a", "kind": "para", "runs": [ed, {"text": "ve Ayşe geldi. "}, bare, {"text": " gitti."}]}]
    out = C.apply(blocks, CHARS, [])
    assert out[0]["runs"][0] == ed and bare in out[0]["runs"]
    assert ("Ayşe", GREEN) in _styled(out)
    assert blocks[0]["runs"][1] == {"text": "ve Ayşe geldi. "}         # girdi değişmez


def test_dialogue_in_speaker_colour():
    out = C.apply([{"id": "a", "kind": "para", "text": "Elif pencereye koşup seslendi:"},
                   {"id": "b", "kind": "dialogue", "text": "Bak Ayşe, bir yıldız!"}], CHARS, [])
    runs = out[1]["runs"]
    assert [(r["text"], r.get("color")) for r in runs] == [("Bak ", RED), ("Ayşe", GREEN), (", bir yıldız!", RED)]


def test_colorize_is_idempotent():
    blocks = [{"id": "a", "kind": "para", "text": "Elif pencereye koşup seslendi:"},
              {"id": "b", "kind": "dialogue", "text": "Bak, bir yıldız! dedi Elif."},
              {"id": "c", "kind": "para", "runs": [{"text": "Ayşe", "color": "#000000", "source": "editor"},
                                                   {"text": " ile Elif'in gözleri parladı. Vıııınnn!"}]},
              {"id": "d", "kind": "para", "text": "Vıııınnn!"}]
    once = C.apply(blocks, CHARS, [RED, "#8A6500"], body_size=14)
    assert C.apply(once, CHARS, [RED, "#8A6500"], body_size=14) == once


# ------------------------------------------------------------------ balon: konuşan
NAMES = ["Elif", "Ayşe"]


@pytest.mark.parametrize("line,speech,who", [
    ("- Bak, bir yıldız! dedi Elif.", "Bak, bir yıldız!", "Elif"),
    ("Gel, diye seslendi Ayşe, hemen gel!", "Gel, hemen gel!", "Ayşe"),
    ("Buraya gel, dedi Elif. Hemen!", "Buraya gel. Hemen!", "Elif"),
    ("Ne oldu? Elif heyecanla sordu.", "Ne oldu?", "Elif"),
    ("“Neredesin?” diye bağırdı AYŞE.", "Neredesin?", "Ayşe"),
    ("Ne oldu? Elif'in annesi sordu.", "Ne oldu? Elif'in annesi sordu.", None),
    ("Olmaz, dedi.", "Olmaz.", None),
    ("Bu çok güzel bir gün.", "Bu çok güzel bir gün.", None),
])
def test_parse_tags(line, speech, who):
    got = B.parse(line, NAMES)
    assert got[:2] == (speech, who)


def test_from_dialogue_attribution_from_neighbours():
    blocks = [{"id": "p0", "kind": "para", "text": "Elif pencereye koşup seslendi:"},
              {"id": "d0", "kind": "dialogue", "text": "Bak, bir yıldız!"},
              {"id": "d1", "kind": "dialogue", "text": "Neden bu kadar parlak?"},
              {"id": "p1", "kind": "para", "text": "diye sordu Ayşe."},
              {"id": "d2", "kind": "dialogue", "text": "Bilmiyorum."},
              {"id": "p2", "kind": "para", "text": "Ayşe gülümseyerek ekledi ve kapıyı açtı."},
              {"id": "p3", "kind": "para", "text": "Annesi Elif'e seslendi:"},
              {"id": "d3", "kind": "dialogue", "text": "Yemek hazır!"}]
    rest, bubbles = B.from_dialogue(blocks, NAMES)
    assert [b["id"] for b in rest] == ["p0", "p2", "p3"]             # yalnız etiketten ibaret p1 de çıktı
    assert [(b["speaker"], b["text"]) for b in bubbles] == [
        ("Elif", "Bak, bir yıldız!"), ("Ayşe", "Neden bu kadar parlak?"), ("Ayşe", "Bilmiyorum."),
        (None, "Yemek hazır!")]
    assert all(b["box"] is None and b["tail"] is None and b["source"] == "auto" for b in bubbles)
    assert (rest, bubbles) == B.from_dialogue(blocks, NAMES)


def test_long_dialogue_splits_into_two_bubbles_in_order():
    speech = ("Bugün ormanın en yaşlı ağacına gideceğiz. Yolda nehri geçmemiz gerekecek. "
              "Sakın korkma, ben hep yanında olacağım.")
    rest, bubbles = B.from_dialogue([{"id": "d", "kind": "dialogue", "text": f"{speech} dedi Elif."}], NAMES)
    assert rest == [] and len(bubbles) == 2
    assert " ".join(b["text"] for b in bubbles) == speech
    assert {b["speaker"] for b in bubbles} == {"Elif"} and bubbles[0]["id"] != bubbles[1]["id"]
    assert B.split_long("Kısa bir cümle.") == ["Kısa bir cümle."]
    one = "Bu tek bir cümle ama çok çok uzun bir cümle ve hiç bitmiyor gibi görünüyor çünkü noktası sonda duruyor"
    assert B.split_long(one) == [one]


def test_bubble_shapes():
    _, bs = B.from_dialogue([{"id": "a", "kind": "dialogue", "text": "İMDAT!"},
                             {"id": "b", "kind": "dialogue", "text": "Acaba nerede? diye düşündü Elif."},
                             {"id": "c", "kind": "dialogue", "text": "Merhaba."}], NAMES)
    assert [b["shape"] for b in bs] == ["shout", "thought", "oval"]


def test_wanted_rule(tmp_path):
    assert B.wanted({"age_max": 10, "illustration": "HER_SAYFA"})
    assert not B.wanted({"age_max": 14, "illustration": "HER_SAYFA"})
    assert not B.wanted({"age_max": 10, "illustration": "BOLUM_BASI"})
    (tmp_path / "profile.json").write_text(json.dumps({"age_max": 8, "illustration": "HER_SAYFA"}))
    assert B.wanted(tmp_path / "profile.json")
    assert not B.wanted(tmp_path / "yok.json")


# ------------------------------------------------------------------ balon: yerleşim
PAGE = {"w": 169, "h": 231, "bleed": 2, "safe": 8}
ART = {"x": 0, "y": 0, "w": 169, "h": 113}
TEXT = {"x": 14, "y": 126, "w": 141, "h": 88}
FACE = {"x": 0.6, "y": 0.55, "w": 0.1, "h": 0.15}


@pytest.fixture
def scene(tmp_path) -> Path:
    """Üst %40 düz gökyüzü, altı ayrıntılı (gürültü) — balonun yeri gökyüzü olmalı."""
    rng = np.random.default_rng(7)
    img = rng.integers(0, 255, (400, 600, 3))
    img[:160] = P._hex_rgb("#9CC8E8")
    return _png(tmp_path / "sahne.png", img)


def _overlap(a, b, gap=0.0) -> bool:
    return a["x"] < b["x"] + b["w"] + gap and b["x"] < a["x"] + a["w"] + gap and \
        a["y"] < b["y"] + b["h"] + gap and b["y"] < a["y"] + a["h"] + gap


def _face_mm():
    s, ox, oy = B._mapping(ART, 600, 400)
    x0, y0, x1, y1 = B._grow(B._head_box(FACE, 600, 400, s, ox, oy), B.FACE_PAD)
    return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}


def _locate(calls):
    def locate(path, name):
        calls.append(name)
        return FACE if name == "Elif" else None
    return locate


def test_place_in_calm_area_with_tail_to_speaker(scene):
    bubbles = [{"id": "b1", "speaker": "Elif", "text": "Bak, bir yıldız!", "shape": "oval", "source": "auto"},
               {"id": "b2", "speaker": None, "text": "Neden bu kadar parlak?", "shape": "oval", "source": "auto"},
               {"id": "b3", "speaker": "Elif", "text": "Bilmiyorum.", "shape": "oval", "source": "auto"}]
    calls: list[str] = []
    out = B.place(bubbles, ART, TEXT, scene, _locate(calls), page=PAGE, size=16)
    assert calls == ["Elif"]                                          # konuşan başına bir kez sorulur
    assert out == B.place(bubbles, ART, TEXT, scene, _locate([]), page=PAGE, size=16)
    m = PAGE["bleed"] + PAGE["safe"]
    face = _face_mm()
    for b in out:
        box = b["box"]
        assert box["x"] >= m and box["y"] >= m and box["x"] + box["w"] <= ART["w"] and box["y"] + box["h"] <= ART["h"]
        assert box["y"] + box["h"] <= 0.4 * ART["h"] + 0.5, box       # gökyüzünde
        assert not _overlap(box, TEXT) and not _overlap(box, face)
        assert "warning" not in b
    for i, a in enumerate(out):
        for c in out[i + 1:]:
            assert not _overlap(a["box"], c["box"], B.GAP - 0.01)
    assert out[1]["tail"] is None
    for b in (out[0], out[2]):
        t = b["tail"]
        assert face["x"] - 2 <= t["x"] <= face["x"] + face["w"] + 2 and face["y"] - 2 <= t["y"] <= face["y"] + face["h"] + 2
    assert bubbles[0].get("box") is None                              # girdi değişmez


def test_place_keeps_editor_bubble_and_avoids_it(scene):
    ed = {"id": "e", "speaker": "Elif", "text": "Merhaba!", "shape": "oval", "source": "editor",
          "box": {"x": 12, "y": 12, "w": 60, "h": 30}, "tail": {"x": 1, "y": 1}}
    auto = {"id": "a", "speaker": "Ayşe", "text": "Merhaba Elif, nasılsın?", "shape": "oval", "source": "auto"}
    out = B.place([ed, auto], ART, TEXT, scene, _locate([]), page=PAGE)
    assert out[0] == ed
    assert not _overlap(out[1]["box"], ed["box"], B.GAP - 0.01)
    assert out[1]["tail"] is None                                     # Ayşe resimde bulunamadı


def test_place_survives_failing_locate_and_text_over_art(scene):
    def broken(path, name):
        raise RuntimeError("görsel okuma kapalı")
    over = {"x": 14, "y": 60, "w": 141, "h": 45}                     # yazı resmin üstünde
    out = B.place([{"id": "a", "speaker": "Elif", "text": "Hadi!", "shape": "oval", "source": "auto"}],
                  {"box": ART, "fit": "cover", "focus": {"x": 0.5, "y": 0.5}}, over, scene, broken, page=PAGE)
    assert out[0]["tail"] is None and not _overlap(out[0]["box"], over)


def test_bubble_size_grows_with_text_and_font():
    w1, h1 = B.bubble_size("Merhaba!", 14, 150)
    w2, h2 = B.bubble_size("Merhaba! Bugün ormana gidiyoruz, sen de gelir misin?", 14, 150)
    w3, h3 = B.bubble_size("Merhaba!", 20, 150)
    assert w2 * h2 > w1 * h1 and w3 * h3 > w1 * h1
    assert B.bubble_size("x" * 400, 14, 60)[0] <= 60
