"""Sayfa planı (editor.production.plan, photo, plan.typ): model ve veritabanı yok. Typst ve fontlar editor-py
imajında; yoksa dizgi testleri atlanır. Çalıştır:

    pytest apps/editor/tests/test_plan.py
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
import types
from dataclasses import asdict
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

from editor.production import front, manuscript as M, photo, plan as P, spec as S, studio  # noqa: E402
from editor.production.profile import Profile  # noqa: E402

FONTS = Path("/app/data/fonts")
HAS_TYPST = FONTS.joinpath("Andika-Regular.ttf").exists()
try:
    import typst  # noqa: F401
except ImportError:
    HAS_TYPST = False
typeset_only = pytest.mark.skipif(not HAS_TYPST, reason="typst/fontlar yok (editor-py imajında koşar)")
QUIET = {"build": False, "post": "none"}                 # dizgisiz, ön kontrolsüz yazım (saf testler)


def _png(w, h, color="#3366aa", mode="RGB") -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new(mode, (w, h), color).save(buf, "PNG")
    return buf.getvalue()


def _prof(child: bool) -> Profile:
    return (Profile(4, 8, "beyan", "RESIMLI_OYKU", "HER_SAYFA", [], {}, {}, {}) if child
            else Profile(13, 16, "beyan", "GENCLIK_ROMANI", "BOLUM_BASI", [], {}, {}, {}))


# ------------------------------------------------------------------ elle kurulan küçük plan (dizgisiz)
def _mini(d: Path, n: int = 5) -> dict:
    """spec.json + plan.json (n yazı sayfası, sayfa 2'de resim a_00000001) + artplan; rev 1."""
    d.mkdir(parents=True, exist_ok=True)
    sp = S.build(_prof(True))
    studio.write(d, "spec.json", sp.to_json())
    studio.write(d, "profile.json", _prof(True).to_json())
    studio.write(d, "artplan.json", {"style": {"palette": ["#264653"], "accent": "#264653", "avoid": "text",
                                               "style_prompt": "s", "medium": "", "line": "", "lighting": "",
                                               "mood": "", "why": ""},
                                     "characters": [{"name": "Elif", "species": "girl", "look": "", "from_text": [],
                                                     "role": "ANA", "outfits": [], "default_outfit": ""}],
                                     "scenes": []})
    page = P.geometry(sp)
    pages = []
    for i in range(n):
        pr = P.preset("art-top" if i == 1 else "text-only", page)
        pg = {"id": f"p_{i:08x}", "chapter": 0, "layout": "art-top" if i == 1 else "text-only", "art": None,
              "text": {"box": pr["text"], "align": "left", "size": None, "background": None,
                       "blocks": [{"id": f"c0b{i}", "kind": "para",
                                   "runs": [{"text": f"Elif bahçeye koştu {i}. "},
                                            {"text": "Elif", "color": "#B0341C", "weight": 700, "source": "auto"},
                                            {"text": " güldü."}]}]},
              "bubbles": [], "figures": [], "texts": [], "overflow": False}
        if i == 1:
            pg["art"] = {"id": "a_00000001", "box": pr["art"], "fit": "cover", "focus": {"x": 0.5, "y": 0.5}}
        pages.append(pg)
    plan = {"version": 1, "rev": 0, "page": page, "pages": pages, "assets": {}, "warnings": [],
            "palette": {"colors": [{"name": "Kiremit", "hex": "#B0341C", "source": "resim"}], "text": "#2C2C2A",
                        "characters": {"Elif": "#B0341C"}}}
    P._commit(d, plan, "sınama", "kuruldu")
    return plan


def test_presets_inside_page_and_safe_area():
    page = P.geometry(S.build(_prof(True)))
    for lay in P.LAYOUTS:
        pr = P.preset(lay, page)
        if lay == "custom":
            assert pr is None
            continue
        for k in ("art", "text"):
            bx = pr[k]
            if bx:
                assert bx["x"] >= 0 and bx["y"] >= 0 and bx["w"] > 0 and bx["h"] > 0
                assert bx["x"] + bx["w"] <= page["w"] + 1e-6 and bx["y"] + bx["h"] <= page["h"] + 1e-6
        if pr["text"]:
            assert P.inside_safe(pr["text"], page), lay
    assert P.preset("art-top", page)["art"]["w"] == page["w"]
    assert P.preset("text-over-art", page)["background"] == P.OVER_ART_BG
    with pytest.raises(ValueError):
        P.preset("yok-boyle", page)


def test_bubble_shapes():
    bb = {"box": {"x": 20, "y": 20, "w": 50, "h": 24}, "tail": {"x": 60, "y": 80}, "shape": "oval"}
    sh = P.bubble_shapes(bb)
    assert len(sh["outline"]) == 72 and sh["tail"][1] == [60, 80] and sh["tail_fill"] and not sh["dots"]
    inner = sh["inner"]
    assert 20 < inner["x"] and inner["x"] + inner["w"] < 70 and 20 < inner["y"] and inner["y"] + inner["h"] < 44
    th = P.bubble_shapes({**bb, "shape": "thought"})
    assert th["tail"] is None and len(th["dots"]) == 3
    assert len(P.bubble_shapes({**bb, "shape": "shout"})["outline"]) == 32
    assert P.bubble_shapes({**bb, "shape": "box"})["tail"]
    assert P.bubble_shapes({**bb, "tail": {"x": 45, "y": 32}})["tail"] is None     # uç balonun içinde: kuyruk yok


def test_update_page_rev_history_and_stale(tmp_path):
    d = tmp_path / "j"
    plan = _mini(d)
    pg = json.loads(json.dumps(plan["pages"][0]))
    pg["text"]["box"]["x"] += 5
    pg["texts"] = [{"box": {"x": 30, "y": 40, "w": 60, "h": 20}, "align": "center", "size": 22,
                    "runs": [{"text": "Sihirli orman", "color": "#1F3B73", "weight": 800, "font": "heading"}]}]
    new, page = P.update_page(d, pg["id"], 1, pg, "editör", **QUIET)
    assert new["rev"] == 2 and page["texts"][0]["id"].startswith("t_") and page["texts"][0]["z"] == P.Z_FREE
    with pytest.raises(P.Stale) as e:
        P.update_page(d, pg["id"], 1, pg, "editör", **QUIET)
    assert e.value.rev == 2
    assert [h["rev"] for h in P.history(d)] == [2, 1]
    assert P.history(d)[0]["by"] == "editör"
    prov = [json.loads(x) for x in (d / "provenance.jsonl").read_text().splitlines()]
    assert [p["rev"] for p in prov if p["kind"] == "plan"] == [1, 2]
    with pytest.raises(ValueError):                   # bilinmeyen renk biçimi
        P.update_page(d, pg["id"], 2, {**pg, "texts": [{**pg["texts"][0], "runs": [{"text": "x", "color": "kırmızı"}]}]},
                      "editör", **QUIET)


def test_boxes_clamped_into_page_and_safe_warning(tmp_path):
    d = tmp_path / "j"
    plan = _mini(d)
    pg = json.loads(json.dumps(plan["pages"][0]))
    pg["text"]["box"] = {"x": -20, "y": 5, "w": 500, "h": 50}
    new, page = P.update_page(d, pg["id"], 1, pg, "e", **QUIET)
    bx = page["text"]["box"]
    assert bx["x"] == 0 and bx["w"] == plan["page"]["w"]
    assert any("4. sayfa: yazı kutusu güvenli alanın dışına" in w for w in new["warnings"])


def test_layout_change_applies_preset_and_keeps_text(tmp_path):
    d = tmp_path / "j"
    plan = _mini(d)
    pg = json.loads(json.dumps(plan["pages"][0]))
    new, page = P.update_page(d, pg["id"], 1, {**pg, "layout": "text-over-art"}, "e", **QUIET)
    assert page["art"]["id"].startswith("a_") and page["text"]["background"] == P.OVER_ART_BG
    assert page["text"]["blocks"] == pg["text"]["blocks"]
    with pytest.raises(ValueError):                   # metni olan sayfa «tam sayfa resim» olamaz (metin kaybolmaz)
        P.update_page(d, pg["id"], 2, {**page, "layout": "art-full"}, "e", **QUIET)


def test_insert_delete_order_and_unused_art(tmp_path):
    d = tmp_path / "j"
    plan = _mini(d)
    studio.write(d, "studio.json", {"pages": {"a_00000001": {"versions": [], "selected": None}}, "characters": {}})
    new, pg = P.insert_page(d, 1, plan["pages"][0]["id"], "art-top", "e", **QUIET)
    assert new["pages"][1]["id"] == pg["id"] and pg["art"]["id"].startswith("a_") and pg["text"]["blocks"] == []
    new, _ = P.delete_page(d, plan["pages"][1]["id"], new["rev"], "e", **QUIET)
    assert all(p["id"] != plan["pages"][1]["id"] for p in new["pages"])
    assert [a["id"] for a in P.unused_art(d, new)] == ["a_00000001"]         # resim silinmedi, boşta
    ids = [p["id"] for p in new["pages"]][::-1]
    new, _ = P.order(d, new["rev"], ids, "e", **QUIET)
    assert [p["id"] for p in new["pages"]] == ids
    with pytest.raises(ValueError):
        P.order(d, new["rev"], ids[:-1], "e", **QUIET)


def test_eight_multiple_warning_never_adds_pages(tmp_path):
    d = tmp_path / "j"
    _mini(d, n=5)                                     # 3 ön sayfa + 5 = 8
    pl = P.load(d)
    assert not [w for w in P.warnings(d, pl) if "katı değil" in w]
    new, _ = P.insert_page(d, 1, None, "blank", "e", **QUIET)
    assert "Sayfa sayısı 8'in katı değil: 7 sayfa eksik." in new["warnings"] and len(new["pages"]) == 6


def test_split_moves_rest_to_new_page(tmp_path):
    d = tmp_path / "j"
    plan = _mini(d)
    pg = plan["pages"][0]
    at = len("Elif bahçeye koştu 0. Elif")
    new, (a, b) = P.split_page(d, pg["id"], 1, "c0b0", at, "e", **QUIET)
    assert "".join(r["text"] for r in a["text"]["blocks"][0]["runs"]) == "Elif bahçeye koştu 0. Elif"
    assert "".join(r["text"] for r in b["text"]["blocks"][0]["runs"]) == "güldü."
    assert new["pages"][1]["id"] == b["id"] and b["layout"] == "text-only"


def test_palette_recolors_auto_runs_only(tmp_path):
    d = tmp_path / "j"
    plan = _mini(d)
    pg = json.loads(json.dumps(plan["pages"][0]))
    pg["text"]["blocks"][0]["runs"].append({"text": " Elif!", "color": "#B0341C", "source": "editor"})
    new, _ = P.update_page(d, pg["id"], 1, pg, "e", **QUIET)
    pal = {**new["palette"], "characters": {"Elif": "#1F6F5B"}}
    new, _ = P.set_palette(d, new["rev"], pal, "e", **QUIET)
    runs = new["pages"][0]["text"]["blocks"][0]["runs"]
    assert runs[1]["color"] == "#1F6F5B" and runs[-1]["color"] == "#B0341C"


def test_restore_keeps_later_assets(tmp_path):
    d = tmp_path / "j"
    plan = _mini(d)
    pg = json.loads(json.dumps(plan["pages"][0]))
    pg["text"]["blocks"][0]["runs"] = [{"text": "değişti"}]
    P.update_page(d, pg["id"], 1, pg, "e", **QUIET)
    P.add_asset(d, "g_00000001", {"kind": "figure", "path": "figur/g_00000001.png", "w_px": 10, "h_px": 10},
                None, "e", **QUIET)
    new, _ = P.restore(d, 1, "e", **QUIET)
    assert new["rev"] == 4 and new["restored_from"] == 1
    assert new["pages"][0]["text"]["blocks"][0]["runs"][0]["text"].startswith("Elif bahçeye")
    assert "g_00000001" in new["assets"]
    with pytest.raises(KeyError):
        P.restore(d, 99, "e", **QUIET)


def test_assets_in_use_and_low_dpi_photo(tmp_path):
    from PIL import Image
    d = tmp_path / "j"
    plan = _mini(d)
    buf = io.BytesIO()
    Image.new("RGB", (300, 200), "#aa3322").save(buf, "JPEG")
    gid, meta, res = P.add_photo(d, buf.getvalue(), "kedi.jpg", plan["pages"][0]["id"], "e", **QUIET)
    assert meta["kind"] == "photo" and (d / meta["path"]).exists() and res["figure"]["asset"] == gid
    assert any("fotoğraf baskıda bulanık çıkabilir" in w for w in res["plan"]["warnings"])
    with pytest.raises(P.InUse) as e:
        P.delete_asset(d, gid, res["plan"]["rev"], "e", **QUIET)
    assert e.value.pages == [4]
    pg = json.loads(json.dumps(res["plan"]["pages"][0]))
    pg["figures"] = []
    new, _ = P.update_page(d, pg["id"], res["plan"]["rev"], pg, "e", **QUIET)
    new, _ = P.delete_asset(d, gid, new["rev"], "e", **QUIET)
    assert gid not in new["assets"] and (d / meta["path"]).exists()        # dosya diskte kalır


def test_photo_ingest_orientation_and_metadata():
    from PIL import Image
    ex = Image.Exif()
    ex[0x0112] = 6                                    # 90° döndür
    ex[0x010F] = "Kamera"
    buf = io.BytesIO()
    Image.new("RGB", (40, 20), "#123456").save(buf, "JPEG", exif=ex)
    out = photo.ingest(buf.getvalue(), "foto.jpg")
    im = Image.open(io.BytesIO(out["bytes"]))
    assert (out["ext"], im.size, out["alpha"]) == ("jpg", (20, 40), False) and len(im.getexif()) == 0
    png = photo.ingest(_png(30, 30, (255, 0, 0, 128), "RGBA"), "saydam.png")
    assert png["ext"] == "png" and png["alpha"]
    with pytest.raises(ValueError):
        photo.ingest(b"bu bir resim degil", "x.jpg")


def test_dpi_and_upscale_factor():
    assert round(photo.dpi(3000, 2000, {"w": 254, "h": 169.3})) == 300
    assert round(photo.dpi(1000, 1000, {"w": 254, "h": 127}, "cover")) == 100
    assert photo.upscale_factor(250) == 2 and photo.upscale_factor(90) == 4 and photo.upscale_factor(120) == 3
    assert photo.upscale_factor(40) == 4                                     # 4× de yetmez: en çok 4


def test_cutout_keyed_and_connected():
    import numpy as np
    from PIL import Image, ImageDraw
    rng = np.random.default_rng(1)
    a = np.clip(np.array([255, 0, 255]) + rng.normal(0, 4, (200, 200, 3)), 0, 255).astype("uint8")
    im = Image.fromarray(a, "RGB")
    dr = ImageDraw.Draw(im)
    dr.ellipse((20, 20, 80, 80), fill="#cc2222")                             # dolu figür
    dr.ellipse((110, 110, 190, 190), outline="#2244cc", width=14)            # içi zemin olan halka
    buf = io.BytesIO()
    im.save(buf, "PNG")
    png, info = photo.cutout(buf.getvalue(), keyed=True)
    out = Image.open(io.BytesIO(png))
    assert out.mode == "RGBA" and info["flat"] and info["removed"] > 0.3
    x0, y0 = info["crop"][:2]
    A = np.asarray(out.getchannel("A"))
    assert A[50 - y0, 50 - x0] == 255                  # figürün içi opak
    assert A[150 - y0, 150 - x0] < 10                  # halkanın içi (kapalı zemin) saydam: anahtar renk
    assert out.width < 200 and out.height < 200        # figüre kırpıldı
    png2, _ = photo.cutout(buf.getvalue(), keyed=False)
    B = np.asarray(Image.open(io.BytesIO(png2)).getchannel("A"))
    assert B[150 - y0, 150 - x0] == 255                # fotoğrafta kenara bağlı olmayan zemin korunur
    assert photo.key_color(["#FF10F0", "#E020E0"])[1] != "#FF00FF"          # kitabın rengine yakın anahtar seçilmez


def test_regenerate_new_art_needs_direction(tmp_path):
    d = tmp_path / "j"
    _mini(d)
    studio.write(d, "pagemap.json", {"layout": {"art_ratio": 0.5, "body_size": 16, "accent": "#264653"}, "pages": []})
    with pytest.raises(ValueError, match="ne çizileceğini"):
        asyncio.run(studio.regenerate(d, "a_00000001", "new", "  ", "e"))


def test_upscale_asset_marks_lanczos(tmp_path, monkeypatch):
    from editor.production import images
    d = tmp_path / "j"
    plan = _mini(d)
    gid, meta, res = P.add_photo(d, _png(100, 80), "k.png", plan["pages"][0]["id"], "e", **QUIET)

    async def lanczos(self, png, W, H):
        return images.upscale(png, W, H), "servis açılamadı"
    monkeypatch.setattr(images.Painter, "enlarge", lanczos)
    monkeypatch.setattr(P, "after_write", lambda *a, **k: None)
    monkeypatch.setattr(P, "_typeset", lambda d, plan, build: plan.__setitem__("warnings", P.warnings(d, plan)))
    out = asyncio.run(studio.upscale_asset(d, gid, "g_00000002", plan["pages"][0]["id"], res["figure"]["id"], "e"))
    a = P.load(d)["assets"]["g_00000002"]
    assert out["factor"] == 4 and not out["enough"] and out["note"].startswith("Yalnız büyütüldü")
    assert a["derived_from"] == gid and a["upscale"] == 4 and a["w_px"] == 400 and gid in P.load(d)["assets"]


def _magenta_figure() -> bytes:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (300, 400), "#FF00FF")
    ImageDraw.Draw(im).ellipse((80, 80, 220, 320), fill="#d04010")
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def test_make_figure_registers_transparent_asset_on_page(tmp_path, monkeypatch):
    """Figür işi (model sahte): anahtar renkli zemin ayıklanır, saydam PNG kütüphaneye ve sayfaya girer."""
    from editor.production import art as art_mod, images
    d = tmp_path / "j"
    plan = _mini(d)
    seen = {}

    async def en(text, chars, llm):
        return "a small fox with a red balloon"

    async def fig(self, what, chars, key_name, key_hex, seed):
        seen.update(what=what, chars=[c.name for c in chars], key=key_hex)
        return _magenta_figure(), "generate"
    monkeypatch.setattr(art_mod, "direction_en", en)
    monkeypatch.setattr(images.Painter, "figure", fig)
    monkeypatch.setattr(P, "after_write", lambda *a, **k: None)
    monkeypatch.setattr(P, "_typeset", lambda d, plan, build: plan.__setitem__("warnings", P.warnings(d, plan)))
    pid = plan["pages"][0]["id"]
    out = asyncio.run(studio.make_figure(d, "g_000000aa", "kırmızı balonlu küçük tilki", ["Elif"], pid, "e"))
    pl = P.load(d)
    a = pl["assets"]["g_000000aa"]
    assert out["flat"] and a["kind"] == "figure" and a["alpha"] and a["characters"] == ["Elif"]
    assert a["prompt"] == "kırmızı balonlu küçük tilki" and seen["key"] != "#FFFFFF" and seen["chars"] == ["Elif"]
    assert (d / "figur" / "g_000000aa.png").exists() and (d / "figur" / "g_000000aa.ham.png").exists()
    assert pl["pages"][0]["figures"][0]["asset"] == "g_000000aa"
    from PIL import Image
    im = Image.open(d / a["path"])
    assert im.mode == "RGBA" and im.getpixel((2, 2))[3] == 0 and im.width < 300           # zemin gitti, kırpıldı


def test_cutout_asset_makes_new_unplaced_asset(tmp_path, monkeypatch):
    d = tmp_path / "j"
    _mini(d)
    monkeypatch.setattr(P, "after_write", lambda *a, **k: None)
    gid, _, _ = P.add_photo(d, _magenta_figure(), "tilki.png", None, "e", **QUIET)
    monkeypatch.setattr(P, "_typeset", lambda d, plan, build: plan.__setitem__("warnings", P.warnings(d, plan)))
    out = studio.cutout_asset(d, gid, "g_000000bb", "e")
    pl = P.load(d)
    assert out["asset"] == "g_000000bb" and pl["assets"]["g_000000bb"]["derived_from"] == gid
    assert pl["assets"]["g_000000bb"]["alpha"] and gid in pl["assets"]
    assert not any(f["asset"] == "g_000000bb" for p in pl["pages"] for f in p["figures"])   # onaysız sayfaya konmaz


def test_new_workflows_registered():
    from editor.production.flow import ACTIVITIES, WORKFLOWS
    names = {getattr(w, "__temporal_workflow_definition").name for w in WORKFLOWS}
    assert {"FigureGenerate", "AssetCutout", "AssetUpscale"} <= names
    acts = {getattr(a, "__temporal_activity_definition").name for a in ACTIVITIES}
    assert {"production_figure", "production_cutout", "production_upscale"} <= acts


def test_figure_workflow_runs_activity_with_args():
    testing = pytest.importorskip("temporalio.testing")
    from temporalio import activity
    from temporalio.worker import Worker
    from editor.production.flow import WORKFLOWS
    calls = []

    @activity.defn(name="production_figure")
    async def fig(job, jid, gid, prompt, characters, page, by):
        calls.append((job, gid, prompt, characters, page))

    @activity.defn(name="production_upscale")
    async def up(job, jid, gid, new_gid, page, item, by):
        calls.append((job, gid, new_gid, page, item))

    async def main():
        try:
            env = await testing.WorkflowEnvironment.start_time_skipping()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"Temporal test sunucusu yok: {e}")
        async with env, Worker(env.client, task_queue="t", workflows=WORKFLOWS, activities=[fig, up]):
            await env.client.execute_workflow("FigureGenerate", args=["a", "j", "g_1", "tilki", ["Elif"], None, "e"],
                                              id="wf", task_queue="t")
            await env.client.execute_workflow("AssetUpscale", args=["a", "j", "g_1", "g_2", "p_1", "art", "e"],
                                              id="wu", task_queue="t")
    asyncio.run(main())
    assert calls == [("a", "g_1", "tilki", ["Elif"], None), ("a", "g_1", "g_2", "p_1", "art")]


def test_api_codes(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from editor.production import api
    root = tmp_path / "production"
    _mini(root / "job1")
    (root / "job2").mkdir(parents=True)
    monkeypatch.setattr(studio, "root", lambda: root)
    monkeypatch.setattr(api, "KEY", "k")
    monkeypatch.setattr(P, "after_write", lambda *a, **k: None)
    monkeypatch.setattr(P, "_typeset", lambda d, plan, build: plan.__setitem__("warnings", P.warnings(d, plan)))
    monkeypatch.setenv("STUDIO_UPLOAD_MB", "1")
    c = TestClient(api.app)
    h = {"Authorization": "Bearer k", "X-Editor": "sinama"}
    r = c.get("/v1/studio/jobs/job2/plan", headers=h)
    assert r.status_code == 404 and r.json()["code"] == "NO_PLAN"
    pl = c.get("/v1/studio/jobs/job1/plan", headers=h).json()
    pg = pl["pages"][0]
    r = c.put(f"/v1/studio/jobs/job1/plan/pages/{pg['id']}", headers=h, json={"rev": 1, "page": pg})
    assert r.status_code == 200 and r.json()["rev"] == 2
    r = c.put(f"/v1/studio/jobs/job1/plan/pages/{pg['id']}", headers=h, json={"rev": 1, "page": pg})
    assert r.status_code == 409 and r.json()["code"] == "STALE" and r.json()["rev"] == 2
    r = c.put("/v1/studio/jobs/job1/plan/photos?filename=b.jpg", headers=h, content=b"x" * (1024 * 1024 + 10))
    assert r.status_code == 413 and r.json()["code"] == "TOO_LARGE"
    r = c.put("/v1/studio/jobs/job1/plan/photos?filename=b.png", headers=h, content=_png(64, 48))
    assert r.status_code == 200 and r.json()["w_px"] == 64
    gid = r.json()["asset"]
    r = c.get(f"/v1/studio/jobs/job1/plan/assets/{gid}?w=64", headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert [x["rev"] for x in c.get("/v1/studio/jobs/job1/plan/history", headers=h).json()] == [3, 2, 1]
    assert c.post("/v1/studio/jobs/job1/plan/restore", headers=h, json={"rev": 1}).json()["rev"] == 4
    assert c.put(f"/v1/studio/jobs/job1/plan/pages/{pg['id']}", json={"rev": 4, "page": pg},
                 headers={"Authorization": "Bearer k"}).status_code == 400          # X-Editor yok
    view = c.get("/v1/studio/jobs/job1", headers=h).json()
    assert view["plan"]["rev"] == 4 and [p["id"] for p in view["pages"]] == [p["id"] for p in P.load(root / "job1")["pages"]]
    assert view["pages"][1]["art_id"] == "a_00000001" and view["pages"][1]["no"] == P.FRONT + 2
    assert api._key("5", root / "job1") == "a_00000001" and api._key("kapak", root / "job1") == "kapak"
    assert c.get("/v1/studio/jobs/job1/plan/jobs", headers=h).json() == {"busy": None, "jobs": []}
    assert c.get("/v1/studio/jobs/job1/plan/unused-art", headers=h).json() == {"art": []}


# ------------------------------------------------------------------ dizgiyle (editor-py imajında)
def _job(tmp_path: Path, child: bool) -> tuple[Path, M.Manuscript]:
    """Gerçek dizgiyle kurulmuş iş klasörü: el yazması, profil, spec, künye, sayfa haritası, sahneler, resimler."""
    from PIL import Image

    from editor.production.art import Scene
    from editor.production.typeset import Typesetter
    d = tmp_path / "job"
    d.mkdir()
    ms = M.Manuscript(title="Deneme Kitabı", author="Yazar", meta={"PUBLISHER": "YAYINEVİ"})
    for c in range(2):
        bl = []
        for b in range(10):
            if b % 4 == 1:
                bl.append(M.Block("dialogue", f"Bak, bir yıldız {c}{b}! dedi Elif."))
            else:
                bl.append(M.Block("para", "Elif " + " ".join(["kelime"] * 40) + f" ağaç{c}{b} şişe ığdır."))
        ms.chapters.append(M.Chapter(f"BÖLÜM {c + 1}", bl))
    prof = _prof(child)
    sp = S.build(prof)
    fr = {"kunye": front.kunye(ms, {}), "kunye_fields": {}, "manual": {}, "bios": [{"name": "Yazar", "text": "Tanıtım."}]}
    pm = Typesetter(d / "dizgi", FONTS).fit(ms, sp, fr, "#264653")
    for name, obj in (("manuscript.json", ms.to_json()), ("profile.json", prof.to_json()), ("spec.json", sp.to_json()),
                      ("front.json", fr), ("pagemap.json", pm.to_json()),
                      ("job.json", {"id": "job", "source": {}, "created_by": "t"})):
        studio.write(d, name, obj)
    style = {"medium": "m", "line": "l", "lighting": "l", "mood": "m", "accent": "#264653", "style_prompt": "s",
             "palette": ["#264653", "#2A9D8F", "#E9C46A", "#F4A261", "#E76F51"], "avoid": "text", "why": "w"}
    chars = [{"name": "Elif", "species": "girl", "look": "red coat", "from_text": [], "role": "ANA", "outfits": [],
              "default_outfit": ""}]
    kinds = {p.no: p.kind for p in pm.pages}
    art = sorted(pm.art_pages())
    scenes = [asdict(Scene(no, kinds[no], "m", "q", ["Elif"], "s", "set", True)) for no in art]
    studio.write(d, "artplan.json", {"style": style, "characters": chars, "scenes": scenes})
    (d / "resim").mkdir()
    pages = {}
    for i, no in enumerate(art):
        p = d / "resim" / f"sayfa-{no:02d}.v1.png"
        Image.new("RGB", (600, 400), ("#88aacc", "#ccaa88", "#aaccaa")[i % 3]).save(p)
        pages[str(no)] = {"versions": [{"v": 1, "path": str(p), "mode": "generate", "prompt": "", "seed": 1, "by": "t",
                                        "at": 0, "dpi": 300, "base": None}], "selected": 1, "approved": True}
    studio.write(d, "studio.json", {"pages": pages, "characters": {}})
    return d, ms


@typeset_only
def test_freeze_keeps_every_word_and_migrates_art(tmp_path):
    """Yetişkin/genç kitabı: dondurma sonrası planın metni el yazmasıyla kelime kelime aynı (sayfa sınırından
    bölünen bloklar dahil), hiçbir sayfa taşmıyor, resimler kimliğe taşındı, iç sayfa plan.typ'den dizildi."""
    from editor.production import preflight
    d, ms = _job(tmp_path, child=False)
    pm = studio._pagemap(d)
    before = studio.selected_art(d)
    pl = P.freeze(d, "sınama")
    assert pl["rev"] == 1 and len(pl["pages"]) == len(pm.pages) - P.FRONT
    assert preflight._words(P.PlanText(pl).text()) == preflight._words(ms.text().replace("## ", ""))
    assert any(k["id"].endswith("-2") for p in pl["pages"] if p["text"] for k in p["text"]["blocks"])  # bölünen blok
    assert not any(p["overflow"] for p in pl["pages"])
    assert not [w for w in pl["warnings"] if "güvenli alan" in w or "sığmıyor" in w]
    sel = studio.selected_art(d)
    assert set(sel) == {a for _, a in P.printed_art(pl)} and sorted(sel.values()) == sorted(before.values())
    assert all(s["art_id"] for s in studio.read(d, "artplan.json")["scenes"])
    assert P.freeze(d, "başka")["rev"] == 1                                # varsa bozmaz
    import pymupdf
    assert pymupdf.open(d / "dizgi" / "ic-sayfalar.pdf").page_count == P.FRONT + len(pl["pages"])
    studio.rebuild(d)
    rep = studio.read(d, "preflight.json")
    got = {c["name"]: c["status"] for c in rep["checks"]}
    assert got["Metin eksiksiz"] == "OK" and got["Sayfa resimleri"] == "OK" and got["Sayfa sayısı"] == "OK"


@typeset_only
def test_freeze_child_bubbles_colors_and_overflow(tmp_path):
    d, ms = _job(tmp_path, child=True)
    pl = P.freeze(d, "sınama")
    bubbles = [b for p in pl["pages"] for b in p["bubbles"]]
    assert bubbles and all(b["box"] for b in bubbles) and any(b["speaker"] == "Elif" for b in bubbles)
    assert not any(k["kind"] == "dialogue" for p in pl["pages"] if p["text"] for k in p["text"]["blocks"])
    elif_ = pl["palette"]["characters"]["Elif"]
    assert pl["palette"]["colors"] and any(r.get("color") == elif_ for p in pl["pages"] if p["text"]
                                           for k in p["text"]["blocks"] for r in k["runs"])
    # Küçük yazı kutusu: metin kesilmez, taşma işaretlenir; büyütünce kalkar.
    pg = json.loads(json.dumps(next(p for p in pl["pages"] if p["text"] and p["text"]["blocks"])))
    no = P.page_no(pl, pg["id"])
    pg["text"]["box"]["h"] = 8
    new, page = P.update_page(d, pg["id"], pl["rev"], pg, "e", post="none")
    assert page["overflow"] and f"{no}. sayfa: metin kutusuna sığmıyor" in " ".join(new["warnings"])
    pg["text"]["box"]["h"] = 140
    pg["text"]["size"] = 9
    new, page = P.update_page(d, pg["id"], new["rev"], pg, "e", post="none")
    assert not page["overflow"]


@typeset_only
def test_plan_typ_draws_bubbles_figures_photos_and_runs(tmp_path):
    import pymupdf
    from PIL import Image
    d, ms = _job(tmp_path, child=True)
    pl = P.freeze(d, "sınama", build=False)
    pid = pl["pages"][2]["id"]
    fig = Image.new("RGBA", (200, 300), (0, 0, 0, 0))
    fig.paste((200, 30, 30, 255), (50, 50, 150, 250))
    buf = io.BytesIO()
    fig.save(buf, "PNG")
    (d / "figur").mkdir()
    (d / "figur" / "g_0000000f.png").write_bytes(buf.getvalue())
    P.add_asset(d, "g_0000000f", {"kind": "figure", "path": "figur/g_0000000f.png", "w_px": 200, "h_px": 300,
                                  "alpha": True}, pid, "e", build=False, post="none")
    gid, _, res = P.add_photo(d, _png(1200, 900, "#446688"), "manzara.png", None, "e", build=False, post="none")
    pl = P.load(d)
    pg = json.loads(json.dumps(P._page(pl, pid)))
    pg["layout"] = "custom"
    pg["art"] = {**(pg["art"] or {}), "asset": gid, "box": {"x": 0, "y": 0, "w": 100, "h": 80}, "fit": "cover",
                 "focus": {"x": 0.2, "y": 0.8}}
    pg["bubbles"] = [{"text": f"Balon {s} ğüşıöç", "shape": s, "speaker": "Elif", "tail": {"x": 60, "y": 150},
                      "box": {"x": 20 + 30 * i, "y": 30 + 20 * i, "w": 48, "h": 22}} for i, s in enumerate(P.SHAPES)]
    pg["figures"][0].update(rotate=15, flip=True)
    pg["texts"] = [{"box": {"x": 20, "y": 180, "w": 100, "h": 20}, "align": "center", "size": 20,
                    "background": "#FFFFFFE6",
                    "runs": [{"text": "Sihirli "}, {"text": "orman", "color": "#1F3B73", "weight": 800, "font": "heading"}],
                    "z": 5}]
    new, page = P.update_page(d, pid, pl["rev"], pg, "e", post="none")
    assert "hata-plan.txt" not in {p.name for p in d.iterdir()}
    doc = pymupdf.open(d / "dizgi" / "ic-sayfalar.pdf")
    assert doc.page_count == P.FRONT + len(new["pages"])
    text = doc[P.page_no(new, pid) - 1].get_text()
    flat = " ".join(text.split())
    assert "Sihirli orman" in flat and all(f"Balon {s} ğüşıöç" in flat for s in P.SHAPES)
    assert len(doc[P.page_no(new, pid) - 1].get_images()) >= 2                  # fotoğraf + figür
    assert P.preview(d, pid, 300).exists()


@typeset_only
def test_without_plan_book_typ_path_unchanged(tmp_path):
    """Geri uyum: plan.json yoksa dizgi akıştan (book.typ), resimler sayfa numarasıyla; plan kendiliğinden oluşmaz."""
    import pymupdf
    d, ms = _job(tmp_path, child=True)
    studio.rebuild(d)
    assert not P.exists(d) and all(k.isdigit() for k in studio.studio_state(d)["pages"])
    doc = pymupdf.open(d / "dizgi" / "ic-sayfalar.pdf")
    assert doc.page_count == len(studio._pagemap(d).pages)
    assert {c["name"]: c["status"] for c in studio.read(d, "preflight.json")["checks"]}["Metin eksiksiz"] == "OK"
