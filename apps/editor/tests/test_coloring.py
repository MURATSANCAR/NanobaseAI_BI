"""Boyama / etkinlik kitabı (editor.production.coloring, lineart, activities, raster): model ve veritabanı yok.
Görseller sentetik (şekiller), kitap hattının dizgisi gerçek (Typst ve fontlar editor-py imajında; yoksa o testler
atlanır). Çalıştır:

    pytest apps/editor/tests/test_coloring.py
"""

from __future__ import annotations

import asyncio
import hashlib
import sys
import types
from dataclasses import asdict
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

from PIL import Image, ImageDraw  # noqa: E402

from editor.production import activities as A  # noqa: E402
from editor.production import coloring as C  # noqa: E402
from editor.production import front, lineart, plan as P, raster, spec as S, studio  # noqa: E402
from editor.production import manuscript as M  # noqa: E402
from editor.production.profile import Profile  # noqa: E402

FONTS = Path("/app/data/fonts")
HAS_TYPST = FONTS.joinpath("Andika-Regular.ttf").exists()
try:
    import typst  # noqa: F401
except ImportError:
    HAS_TYPST = False
typeset_only = pytest.mark.skipif(not HAS_TYPST, reason="typst/fontlar yok (editor-py imajında koşar)")


def _scene_img(w=1200, h=800, seed=0) -> Image.Image:
    """Yumuşak degrade zemin üzerinde renkli şekiller (resimli kitap sayfası yerine)."""
    rng = np.random.default_rng(seed)
    y = np.linspace(0, 1, h)[:, None, None]
    bg = (np.array([250, 230, 190]) * (1 - y) + np.array([200, 220, 250]) * y).repeat(w, 1)
    im = Image.fromarray(bg.astype(np.uint8), "RGB")
    d = ImageDraw.Draw(im)
    d.ellipse((w * 0.1, h * 0.2, w * 0.4, h * 0.8), fill=(230, 160, 40))      # gövde
    d.ellipse((w * 0.18, h * 0.35, w * 0.22, h * 0.41), fill=(40, 30, 20))   # göz
    d.rectangle((w * 0.55, h * 0.3, w * 0.9, h * 0.75), fill=(60, 130, 200))
    d.polygon([(w * 0.55, h * 0.3), (w * 0.725, h * 0.1), (w * 0.9, h * 0.3)], fill=(200, 50, 60))
    d.rectangle((w * 0.66, h * 0.5, w * 0.76, h * 0.75), fill=(120, 80, 40))
    noise = rng.normal(0, 3, (h, w, 3))
    return Image.fromarray(np.clip(np.asarray(im, float) + noise, 0, 255).astype(np.uint8))


def _char_img(color=(230, 150, 60), w=600, h=800) -> Image.Image:
    im = Image.new("RGB", (w, h), (253, 254, 255))
    d = ImageDraw.Draw(im)
    d.ellipse((w * 0.25, h * 0.08, w * 0.75, h * 0.45), fill=color)                   # baş
    d.rounded_rectangle((w * 0.3, h * 0.42, w * 0.7, h * 0.85), radius=40, fill=(250, 240, 150))
    d.ellipse((w * 0.38, h * 0.2, w * 0.44, h * 0.26), fill=(30, 20, 10))
    d.ellipse((w * 0.56, h * 0.2, w * 0.62, h * 0.26), fill=(30, 20, 10))
    return im


# ------------------------------------------------------------------ raster
def test_label_matches_flood_fill():
    rng = np.random.default_rng(3)
    m = rng.random((60, 80)) > 0.55
    lab, n = raster.label(m, conn8=False)
    # her bileşen 4-komşulukla kapalı: komşu iki mürekkep pikseli aynı etiketi taşır
    assert (lab[:, :-1][m[:, :-1] & m[:, 1:]] == lab[:, 1:][m[:, :-1] & m[:, 1:]]).all()
    assert (lab[:-1][m[:-1] & m[1:]] == lab[1:][m[:-1] & m[1:]]).all()
    assert set(np.unique(lab[m])) == set(range(1, n + 1)) and (lab[~m] == 0).all()
    lab8, n8 = raster.label(m, conn8=True)
    assert n8 <= n


def test_small_parts_holes_distance_and_contour():
    m = np.zeros((50, 50), bool)
    m[5:25, 5:25] = True
    m[40, 40] = True                                     # kırıntı
    out, removed = raster.remove_small(m, 5)
    assert removed == 1 and not out[40, 40] and out[10, 10]
    ring = np.zeros((40, 40), bool)
    ring[5:15, 5:15] = True
    ring[8:12, 8:12] = False                             # 16 px'lik delik
    filled, n = raster.fill_small_holes(ring, 20)
    assert n == 1 and filled[9, 9]
    dist = raster.distance(np.ones((21, 21), bool))
    assert dist[10, 10] == 11 and dist[0, 0] == 1
    c = raster.trace_outer(m[:30, :30])
    assert len(c) >= 4 * 19 and c[0] == (5, 5)
    assert len(raster.rdp([(0, 0), (5, 0.1), (10, 0)], 0.5)) == 2


def test_merge_regions_merges_weak_boundaries_only():
    lab = np.zeros((20, 30), np.int32)
    lab[:, :10], lab[:, 10:20], lab[:, 20:] = 1, 2, 3
    w = np.zeros((20, 30), np.float32)
    w[:, 19:21] = 50.0                                   # 2|3 güçlü, 1|2 zayıf
    color = np.zeros((20, 30, 3), np.float32)
    seg = raster.merge_regions(lab, 3, w, color, weak=10.0, min_area=1)
    assert seg[0, 0] == seg[0, 15] and seg[0, 15] != seg[0, 25]


# ------------------------------------------------------------------ çizgi
def test_lineart_is_two_tone_closed_and_framed():
    im = _scene_img()
    res = lineart.extract(im, src_dpi=150, stroke=1.0, detail="orta")
    out = res.image
    assert out.size == (im.width * lineart.OUT_SCALE, im.height * lineart.OUT_SCALE)
    assert lineart.is_two_tone(out)
    a = np.asarray(out) < 128
    assert a[0].all() and a[-1].all() and a[:, 0].all()                      # çerçeve
    assert res.info["regions"] >= 4 and 0.02 < res.info["ink_share"] < 0.5
    png = lineart.png_bytes(out)
    assert Image.open(__import__("io").BytesIO(png)).mode == "1"


def test_clean_drawn_binarizes_model_output():
    g = Image.new("L", (400, 300), 235)
    d = ImageDraw.Draw(g)
    d.ellipse((50, 50, 250, 250), outline=60, width=4)
    d.point([(300, 20)], fill=0)                                              # kırıntı
    res = lineart.clean_drawn(g.convert("RGB"), src_dpi=100, stroke=1.0)
    assert lineart.is_two_tone(res.image) and res.info["method"] == "model"
    a = np.asarray(res.image) < 128
    assert a.mean() < 0.3


# ------------------------------------------------------------------ etkinlikler
def test_word_search_turkish_upper_and_placement():
    words = A.book_words("Bir sabah ile Elif ve kedi ıhlamur ağacının altında oynadı. Kedi ile Elif çok sevindi.",
                         ["Elif’in", "Kedi"], 8)
    assert words[:2] == ["ELİF", "KEDİ"] and "IHLAMUR" in words and "İLE" not in words and "BİR" not in words
    a = A.word_search(words, (120, 150), 6, 5, FONTS)
    assert set(a.words) <= set(words) and a.words and lineart.is_two_tone(a.image)
    assert set(a.info["placed"]) | set(a.info["not_placed"]) == set(words)
    assert A.tr_upper("ığdır şişe") == "IĞDIR ŞİŞE"


def test_maze_single_solution_and_age():
    small = A.maze((140, 180), 6, 1)
    big = A.maze((140, 180), 12, 1)
    assert big.info["cols"] * big.info["rows"] > small.info["cols"] * small.info["rows"]
    assert small.info["path"] >= small.info["cols"] and small.answer is not None
    assert A.maze((140, 180), 6, 1).image.tobytes() == small.image.tobytes()          # deterministik


def test_spot_difference_changes_only_bottom():
    line = lineart.extract(_scene_img(), src_dpi=150, stroke=1.0).image
    a = A.spot_difference(line, (140, 190), 8, 3, count=4)
    assert 1 <= a.info["made"] <= 4 and str(a.info["made"]) in a.instruction
    im = np.asarray(a.image) < 128
    h = im.shape[0]
    top, bottom = im[: (h - A.px(6)) // 2], im[(h - A.px(6)) // 2 + A.px(6):][: (h - A.px(6)) // 2]
    assert (top != bottom[: top.shape[0]]).any()


def test_paint_by_number_and_colors():
    src = _scene_img()
    line = lineart.extract(src, src_dpi=150, stroke=1.0).image
    a = A.paint_by_number(src, line, (140, 190), 6, FONTS)
    assert a.info["numbered"] >= 3 and a.image.mode == "RGB"
    assert all(c["hex"] for c in a.info["colors"])
    assert A.kid_color_name((250, 220, 40)) == "sarı" and A.kid_color_name((40, 90, 200)) == "mavi"
    assert A.kid_color_name((10, 10, 10)) == "siyah"


def test_dot_to_dot_and_matching():
    a = A.dot_to_dot(_char_img(), (140, 190), 6, FONTS)
    assert 8 <= a.info["dots"] <= 80 and lineart.is_two_tone(a.image)
    pages = A.matching([("Elif", _char_img()), ("Kedi", _char_img((90, 90, 90))), ("Ayı", _char_img((120, 60, 30)))],
                       (140, 190), 6, 2, FONTS)
    assert len(pages) >= 1 and sum(len(p.info["characters"]) for p in pages) >= 3
    assert A.matching([("Elif", _char_img())], (140, 190), 6, 2, FONTS) == []


def test_rule_caption_and_cover():
    t = "“Haydi parka gidelim!” dedi annesi. Aslan çok sevindi ve kapıya doğru koştu, ayakkabılarını giydi, bekledi."
    s = C.rule_caption(t, 6)
    assert "“" not in s and s.startswith("Aslan") and len(s.split()) <= C.max_words(6) + 1
    col = _scene_img(300, 200)
    ln = lineart.extract(col, src_dpi=100).image
    comp = C.cover_art(col, ln)
    a = np.asarray(comp)
    assert comp.size == col.size and a[5, 5].tolist() == np.asarray(col)[5, 5].tolist()
    assert set(np.unique(a[-5:, -5:])) <= {0, 255}


# ------------------------------------------------------------------ kitap işinden boyama işi (dizgiyle)
def _prof() -> Profile:
    return Profile(4, 7, "beyan", "RESIMLI_OYKU", "HER_SAYFA", [], {}, {}, {})


def _source(root: Path, with_plan: bool) -> Path:
    from editor.production.art import Scene
    from editor.production.typeset import Typesetter
    d = root / "20260925000000aaaaaa"
    d.mkdir(parents=True)
    ms = M.Manuscript(title="Deneme Kitabı", author="Yazar", meta={"PUBLISHER": "YAYINEVİ", "ISBN": "9786050000000"})
    bl = [M.Block("para", f"Elif bahçede koştu {i}. Kedi Pamuk ağacın altında uyuyordu, rüzgâr esiyordu.")
          for i in range(6)] + [M.Block("dialogue", "– Bak, bir yıldız! dedi Elif.")]
    ms.chapters.append(M.Chapter("BİR", bl))
    prof = _prof()
    sp = S.build(prof)
    fr = {"kunye": front.kunye(ms, {}), "kunye_fields": {}, "manual": {"ISBN": "9786050000000"}, "bios": []}
    pm = Typesetter(d / "dizgi", FONTS).fit(ms, sp, fr, "#264653")
    for name, obj in (("manuscript.json", ms.to_json()), ("profile.json", prof.to_json()), ("spec.json", sp.to_json()),
                      ("front.json", fr), ("pagemap.json", pm.to_json()),
                      ("job.json", {"id": d.name, "source": {"docx": "x.docx"}, "created_by": "t"})):
        studio.write(d, name, obj)
    style = {"medium": "m", "line": "l", "lighting": "l", "mood": "m", "accent": "#264653", "style_prompt": "s",
             "palette": ["#264653", "#2A9D8F", "#E9C46A"], "avoid": "text", "why": "w"}
    chars = [{"name": n, "species": "x", "look": "y", "from_text": [], "role": r, "outfits": [], "default_outfit": ""}
             for n, r in (("Elif", "ANA"), ("Pamuk", "YAN"))]
    kinds = {p.no: p.kind for p in pm.pages}
    art = sorted(pm.art_pages())
    scenes = [asdict(Scene(no, kinds[no], "Elif koşuyor", f"Elif bahçede koştu {i}.", ["Elif"], "s", "bahçe", True))
              for i, no in enumerate(art)]
    studio.write(d, "artplan.json", {"style": style, "characters": chars, "scenes": scenes})
    (d / "resim").mkdir()
    pages = {}
    for i, no in enumerate(art):
        p = d / "resim" / f"sayfa-{no:02d}.v1.png"
        _scene_img(900, 620, seed=i).save(p)
        pages[str(no)] = {"versions": [{"v": 1, "path": str(p), "mode": "generate", "prompt": "", "seed": 1, "by": "t",
                                        "at": 0, "dpi": 300, "base": None}], "selected": 1, "approved": True}
    cov = d / "resim" / "kapak.v1.png"
    _scene_img(700, 960, seed=9).save(cov)
    pages["kapak"] = {"versions": [{"v": 1, "path": str(cov), "mode": "new", "prompt": "", "seed": 1, "by": "t", "at": 0,
                                    "dpi": 300, "base": None}], "selected": 1, "approved": True}
    refs = {}
    for i, c in enumerate(chars):
        p = d / "resim" / f"karakter-{i:02d}.png"
        _char_img(((230, 150, 60), (120, 120, 120))[i]).save(p)
        refs[c["name"]] = str(p)
    studio.write(d, "studio.json", {"pages": pages, "characters": refs})
    if with_plan:
        P.freeze(d, "t")
    return d


def _digest(d: Path) -> dict[str, str]:
    return {str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(d.rglob("*"))
            if p.is_file() and "dizgi" not in p.parts and "onizleme" not in p.name}


@typeset_only
@pytest.mark.parametrize("with_plan", [False, True])
def test_derived_coloring_book(tmp_path, monkeypatch, with_plan):
    root = tmp_path / "production"
    monkeypatch.setattr(studio, "root", lambda: root)
    monkeypatch.setenv("EDITOR_FONT_DIR", str(FONTS))
    src = _source(root, with_plan)
    before = _digest(src)
    assert [a["ok"] for a in C.available(src)] == [True] * 6
    acts = [{"kind": k} for k in A.KINDS]
    d = C.new_job(src, "sinama", "coloring_activities", acts, captions="rule")
    job = studio.read(d, "job.json")
    assert job["kind"] == "coloring" and job["derived_from"] == src.name
    st = asyncio.run(C.build(d))
    assert st["status"] == "done" and not st["error"], st
    assert _digest(src) == before                                         # kaynak iş değişmedi
    pl = P.load(d)
    cz = studio.read(d, C.FILE)
    n_art = len(C.source_arts(src))
    roles = [cz["pages"][pg["id"]]["role"] for pg in pl["pages"]]
    assert roles[: 2 * n_art] == ["caption", "coloring"] * n_art
    for i, pg in enumerate(pl["pages"]):
        if roles[i] == "coloring":
            assert (P.FRONT + i + 1) % 2 == 1                           # boyama sağ sayfada
    assert "activity" in roles and roles[-1] == "answers"
    assert (P.FRONT + len(pl["pages"])) % studio._spec(d).signature == 0
    sel = studio.selected_art(d)
    for a in cz["arts"]:
        with Image.open(sel[a["aid"]]) as im:
            assert lineart.is_two_tone(im)
    ms = studio.read(d, "manuscript.json")
    assert "Boyama" in ms["title"] and "ISBN" not in ms["meta"]
    assert dict(studio.read(d, "front.json")["kunye"])["ISBN"] == front.MISSING
    assert (d / "dizgi" / "ic-sayfalar.pdf").exists() and (d / "kapak" / "kapak.pdf").exists()
    rep = studio.read(d, "preflight.json")
    got = {c["name"]: c["status"] for c in rep["checks"]}
    assert got["Metin eksiksiz"] == "OK" and got["Sayfa resimleri"] == "OK" and got["Sayfa sayısı"] == "OK"
    assert got["Editör onayı"] == "FAIL"                                  # çizgiler editör onayı bekler
    # görünüm, kısa cümle düzeltme ve onay
    v = C.view(d)
    assert len(v["sentences"]) == n_art and v["drafts"] == [] and v["derived_from"] == src.name
    s0 = v["sentences"][0]
    v2 = C.set_sentences(d, [{"aid": s0["aid"], "text": "Elif koşuyor.", "approved": True}], "editor")
    assert v2["sentences"][0]["text"] == "Elif koşuyor." and v2["sentences"][0]["approved"]
    assert C.derived(src)[0]["id"] == d.name
    # görsel modelin (renkli) sürümü kancayla baskı kuralına gelir; taslak işaretlenir
    aid = cz["arts"][0]["aid"]
    colored = d / "resim" / f"cizgi-{aid}.v2.png"
    _scene_img(900, 620).save(colored)
    studio.add_version(d, aid, str(colored), mode="new", prompt="", seed=1, by="t", dpi=300)
    with Image.open(colored) as im:
        assert lineart.is_two_tone(im)
    assert C.view(d)["arts"][0]["draft"] is True
    # yeniden koşmak planı bozmaz
    rev = P.load(d)["rev"]
    assert asyncio.run(C.build(d))["status"] == "done" and P.load(d)["rev"] == rev


def test_validate_rejects(tmp_path, monkeypatch):
    root = tmp_path / "production"
    monkeypatch.setattr(studio, "root", lambda: root)
    d = root / "20260925000000bbbbbb"
    d.mkdir(parents=True)
    studio.write(d, "studio.json", {"pages": {}, "characters": {}})
    studio.write(d, "artplan.json", {"style": {}, "characters": [], "scenes": []})
    studio.write(d, "pagemap.json", {"pages": [], "layout": {}})
    with pytest.raises(ValueError):
        C.validate(d, "coloring", [])
    with pytest.raises(ValueError):
        C.validate(d, "x", [])


def test_workflows_registered():
    from editor.production import flow
    assert {"ColoringBook", "ColoringRedraw"} <= {getattr(w, "__temporal_workflow_definition").name
                                                  for w in flow.WORKFLOWS}
    assert flow.coloring_activity in flow.ACTIVITIES and flow.coloring_redraw_activity in flow.ACTIVITIES


def test_api_routes(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from editor.production import api
    root = tmp_path / "production"
    d = root / "20260925000000cccccc"
    d.mkdir(parents=True)
    studio.write(d, "job.json", {"id": d.name, "source": {}, "created_by": "t"})
    studio.write(d, "studio.json", {"pages": {}, "characters": {}})
    studio.write(d, "artplan.json", {"style": {}, "characters": [], "scenes": []})
    studio.write(d, "pagemap.json", {"pages": [], "layout": {}})
    monkeypatch.setattr(studio, "root", lambda: root)
    monkeypatch.setattr(api, "KEY", "k")
    c = TestClient(api.app)
    h = {"Authorization": "Bearer k", "X-Editor": "sinama"}
    r = c.get(f"/v1/studio/jobs/{d.name}/coloring", headers=h)
    assert r.status_code == 200 and r.json()["kind"] == "source" and r.json()["arts"] == 0
    r = c.post(f"/v1/studio/jobs/{d.name}/coloring", headers=h, json={"mode": "coloring"})
    assert r.status_code == 400 and "resim yok" in r.json()["detail"]
    assert c.get(f"/v1/studio/jobs/{d.name}/coloring").status_code == 401
    r = c.post(f"/v1/studio/jobs/{d.name}/coloring/retry", headers=h)
    assert r.status_code == 400
