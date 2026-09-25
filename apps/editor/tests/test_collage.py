"""Kolaj kapak (editor.production.collage, cover.typ kolaj kolu, api_collage): model ve veritabanı yok. Typst ve
fontlar editor-py imajında; yoksa dizgi testleri atlanır. Çalıştır:

    pytest apps/editor/tests/test_collage.py
"""

from __future__ import annotations

import asyncio
import hashlib
import io
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

from editor.production import collage as K, front, manuscript as M, spec as S, studio  # noqa: E402
from editor.production.profile import Profile  # noqa: E402

FONTS = Path("/app/data/fonts")
HAS_TYPST = FONTS.joinpath("Andika-Regular.ttf").exists()
try:
    import typst  # noqa: F401
except ImportError:
    HAS_TYPST = False
typeset_only = pytest.mark.skipif(not HAS_TYPST, reason="typst/fontlar yok (editor-py imajında koşar)")
TITLE = "Işığın Peşindeki Küçük Güğüm Öyküsü"
AUTHOR = "Ayşe Gül Öztürk"


def _scene_photo(arm: bool = True, noisy: bool = False, w: int = 800, h: int = 1000) -> Image:
    """Yapay fotoğraf: üstte açık düz gök, altta koyu zemin (ufuk %70), ortada ayakta koyu figür (gövde + baş),
    isteğe bağlı başın üstüne uzanan ince kol."""
    from PIL import Image, ImageDraw
    rng = np.random.default_rng(3)
    a = np.full((h, w), 205.0) + rng.normal(0, 60 if noisy else 2.0, (h, w))
    a[int(h * 0.70):] = 70 + rng.normal(0, 6, (h - int(h * 0.70), w))
    im = Image.fromarray(a.clip(0, 255).astype(np.uint8)).convert("RGB")
    dr = ImageDraw.Draw(im)
    dr.rectangle([w * 0.40, h * 0.42, w * 0.60, h * 0.75], fill=(40, 40, 40))       # gövde
    dr.ellipse([w * 0.44, h * 0.33, w * 0.56, h * 0.43], fill=(35, 35, 35))           # baş
    if arm:
        dr.rectangle([w * 0.57, h * 0.12, w * 0.595, h * 0.45], fill=(45, 45, 45))    # yukarı uzanan kol
    return im


def _png(im) -> bytes:
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


# ------------------------------------------------------------------ etiket ölçümü
def test_labels_measured_from_title_split_in_order_and_fit():
    short = K.label_lines("Kar", 135)
    assert short["lines"] == ["Kar"] and short["size_pt"] == pytest.approx(135 * K.LABEL_PT_PER_MM, abs=0.01)
    long = K.label_lines("Babamın Sevdiği Ekinler Gibi Uzun Bir Yaz Günü Masalı", 135)
    assert len(long["lines"]) >= 2
    assert " ".join(long["lines"]) == "Babamın Sevdiği Ekinler Gibi Uzun Bir Yaz Günü Masalı"        # sıra bozulmaz
    for ln in long["lines"]:
        assert K.text_mm(ln, long["size_pt"], long["file"]) <= long["max_mm"] + 0.01
    assert long["size_pt"] >= 135 * K.LABEL_PT_PER_MM * K.LABEL_TARGET - 0.01
    # dar kitapta aynı başlık daha çok şeride bölünür
    assert len(K.label_lines("Babamın Sevdiği Ekinler Gibi Uzun Bir Yaz Günü Masalı", 100)["lines"]) >= len(long["lines"])
    assert K.label_font([TITLE])[0] == "Special Elite"                                      # Türkçe harfler fontta


def test_editor_labels_common_size_and_clear_error():
    lb = K.label_lines(TITLE, 135, ["Işığın Peşindeki", "Küçük Güğüm Öyküsü"])
    assert lb["lines"] == ["Işığın Peşindeki", "Küçük Güğüm Öyküsü"]
    widest = max(K.text_mm(x, lb["size_pt"], lb["file"]) for x in lb["lines"])
    assert widest <= lb["max_mm"] + 0.01
    with pytest.raises(ValueError, match="sığmıyor"):
        K.label_lines(TITLE, 135, [TITLE * 3])
    with pytest.raises(ValueError):
        K.label_lines(TITLE, 135, ["", "x"])


# ------------------------------------------------------------------ figür ve taşma
def test_figure_cut_from_mask_arm_overflows_head_inside():
    c = K.figure_cut(_scene_photo(arm=True))
    assert c["flat"] and c["overflow"]
    assert c["top"] == pytest.approx(0.12, abs=0.02)                  # kolun ucu
    assert c["top"] < c["cut"] < 0.33                                  # kesim başın üstünde: kol dışarıda
    assert c["horizon"] == pytest.approx(0.70, abs=0.02)
    c2 = K.figure_cut(_scene_photo(arm=False))
    assert c2["overflow"] and c2["top"] == pytest.approx(0.33, abs=0.02)
    assert c2["cut"] > c2["top"]                                       # ince parça yok: baş taşar


def test_figure_cut_on_plain_backdrop_without_ground():
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (600, 800), (250, 250, 250))
    dr = ImageDraw.Draw(im)
    dr.rectangle([250, 300, 350, 650], fill=(60, 60, 60))
    dr.ellipse([265, 220, 335, 300], fill=(50, 50, 50))
    c = K.figure_cut(im)
    assert c["overflow"] and c["top"] == pytest.approx(220 / 800, abs=0.02) and c["cut"] > c["top"]


def test_figure_cut_skips_busy_background():
    c = K.figure_cut(_scene_photo(noisy=True))
    assert not c["flat"] and not c["overflow"] and c["note"]


# ------------------------------------------------------------------ belirlenimcilik ve 300 dpi
def test_layout_deterministic_per_book_and_layout_number():
    cut = {"overflow": True, "top": 0.12, "cut": 0.28}
    lb = K.label_lines(TITLE, 135)
    a = K.layout(K.seed_for(TITLE, 0), 135, 210, 3, 10, 0.8, cut, lb, AUTHOR)
    b = K.layout(K.seed_for(TITLE, 0), 135, 210, 3, 10, 0.8, cut, lb, AUTHOR)
    c = K.layout(K.seed_for(TITLE, 1), 135, 210, 3, 10, 0.8, cut, lb, AUTHOR)
    assert a == b and a != c
    assert K.seed_for(TITLE, 0) != K.seed_for("Başka Kitap", 0)
    for x in (a, c):
        assert x["author"]["y"] + x["author"]["size_pt"] * K.PT_MM <= 3 + 210 - 10 + 0.01    # güvenli alanda
        for lab in x["labels"]:
            assert lab["cx"] - lab["w"] / 2 >= 10 - 0.01 and lab["cx"] + lab["w"] / 2 <= 135 - 10 + 0.01
        assert any(bl["kind"] == "strip" for bl in x["blobs"])
        assert all(bl["cx"] - max(bl["rx"], bl["ry"]) * 0.9 >= 2.0 - 0.01 for bl in x["blobs"])   # sırt kıvrımı boş
    # yazar adı yoksa yeri ayrılmaz: yığın dikeyde ortalanır (alt boşluk üst boşluktan büyük değil)
    e = K.layout(K.seed_for(TITLE, 0), 135, 210, 3, 10, 0.8, cut, lb, "")
    last = e["labels"][-1]
    bottom_gap = (3 + 210 - 10) - (last["cy"] + last["h"] / 2)
    top_gap = e["photo"]["y"] + cut["top"] * e["photo"]["h"] - (3 + 10)
    assert e["author"] is None and 0 <= bottom_gap <= top_gap + 0.01


def test_compose_same_book_same_bytes_at_300_dpi(tmp_path):
    from PIL import Image
    src = tmp_path / "foto.png"
    _scene_photo().save(src)
    md5 = []
    for name in ("a", "b"):
        data, info = K.compose(tmp_path / name, src, TITLE, AUTHOR, 135, 210, 3, 10)
        md5.append(hashlib.md5((tmp_path / name / "kolaj-on.png").read_bytes()).hexdigest())
        im = Image.open(tmp_path / name / "kolaj-on.png")
        assert im.mode == "L"                                                  # gri: baskıda yalnız siyah
        assert im.size == (K.px(135 + 3), K.px(210 + 6))
        assert round(im.info["dpi"][0]) == 300
    assert md5[0] == md5[1]
    assert info["cut"]["overflow"] and "mask" not in info["cut"]
    data2, _ = K.compose(tmp_path / "c", src, TITLE, AUTHOR, 135, 210, 3, 10, layout_n=1)
    assert hashlib.md5((tmp_path / "c" / "kolaj-on.png").read_bytes()).hexdigest() != md5[0]
    assert [x["text"] for x in data["labels"]] == info["labels"]["lines"]


# ------------------------------------------------------------------ iş klasörüyle: kapak, PDF, uçlar
def _prof() -> Profile:
    return Profile(13, 16, "beyan", "GENCLIK_ROMANI", "BOLUM_BASI", ["sakin"], {}, {}, {})


def _job(root: Path) -> Path:
    from editor.production.typeset import Typesetter
    d = root / "job1"
    d.mkdir(parents=True)
    ms = M.Manuscript(title=TITLE, author=AUTHOR, meta={"PUBLISHER": "YAYINEVİ", "ISBN": "9786050000009",
                                                        "CRM_SUMMARY": "Kısa tanıtım."})
    ms.chapters.append(M.Chapter("BÖLÜM 1", [M.Block("para", "Metin " + " ".join(["kelime"] * 60)) for _ in range(6)]))
    prof = _prof()
    sp = S.build(prof)
    fr = {"kunye": front.kunye(ms, {}), "kunye_fields": {}, "manual": {}, "bios": []}
    pm = Typesetter(d / "dizgi", FONTS).fit(ms, sp, fr, "#264653")
    style = {"medium": "m", "line": "l", "lighting": "l", "mood": "m", "accent": "#264653", "style_prompt": "s",
             "palette": ["#264653", "#2A9D8F", "#E9C46A", "#F4A261", "#FBF7EF"], "avoid": "text", "why": "w"}
    for name, obj in (("manuscript.json", ms.to_json()), ("profile.json", prof.to_json()), ("spec.json", sp.to_json()),
                      ("front.json", fr), ("pagemap.json", pm.to_json()),
                      ("artplan.json", {"style": style, "characters": [], "scenes": []}),
                      ("job.json", {"id": "job1", "source": {}, "created_by": "t", "art_mode": "chapter"})):
        studio.write(d, name, obj)
    studio.write(d, "studio.json", {"pages": {}, "characters": {}})
    return d


@typeset_only
def test_collage_cover_pdf_turkish_text_vector_gray_300dpi(tmp_path, monkeypatch):
    import pymupdf
    monkeypatch.setenv("EDITOR_FONT_DIR", str(FONTS))
    d = _job(tmp_path)
    K.add_upload(d, _png(_scene_photo()), "foto.png", "sınama")
    assert not (d / "kapak" / "kapak.pdf").exists()                   # tarz seçilmedi: kapak kurulmaz
    K.set_style(d, "collage", "sınama")
    pdf = d / "kapak" / "kapak.pdf"
    assert pdf.exists() and studio.read(d, "cover.json")["style"] == "collage"
    doc = pymupdf.open(pdf)
    text = " ".join(doc[0].get_text().split())
    view = K.view(d)
    for ln in view["label_lines"]:
        assert ln in text                                              # Türkçe harfler PDF'ten geri okunur
    assert AUTHOR.replace(" ", "") in text.replace(" ", "")             # geniş harf aralığı boşluk sayılabilir
    fonts = " ".join(f[3] for f in doc[0].get_fonts(full=True))
    assert "SpecialElite" in fonts and "Poppins-Light" in fonts
    spec = studio._spec(d)
    pt = 72 / 25.4
    front_x = doc[0].rect.width - (spec.trim_w + spec.bleed) * pt
    art = [im for im in doc[0].get_images(full=True) if im[2] == K.px(spec.trim_w + spec.bleed)]
    assert art and pymupdf.Pixmap(doc, art[0][0]).n == 1                      # tek kanal (gri)
    rect = doc[0].get_image_rects(art[0][0])[0]
    assert rect.x0 == pytest.approx(front_x, abs=0.5)
    assert art[0][2] / (rect.width / 72) == pytest.approx(300, abs=1)          # etkin çözünürlük 300 dpi
    assert view["draft"] is False and view["photos"][0]["overflow"]
    # başka düzen: kapak değişir; aynı düzene dönünce aynı ön kapak
    first = hashlib.md5((d / "kapak" / "kolaj-on.png").read_bytes()).hexdigest()
    K.set_layout(d, None, "sınama")
    assert hashlib.md5((d / "kapak" / "kolaj-on.png").read_bytes()).hexdigest() != first
    K.set_layout(d, 0, "sınama")
    assert hashlib.md5((d / "kapak" / "kolaj-on.png").read_bytes()).hexdigest() == first
    # elle etiket
    K.set_labels(d, ["Işığın", "Peşindeki Küçük", "Güğüm Öyküsü"], "sınama")
    t2 = " ".join(pymupdf.open(pdf)[0].get_text().split())
    assert "Peşindeki Küçük" in t2 and K.view(d)["label_lines"] == ["Işığın", "Peşindeki Küçük", "Güğüm Öyküsü"]
    # ön panel önizlemesi
    assert K.front_preview(d, 300).exists()
    # tipografik seçilince resim olmasa da tipografik; resimli seçilince bugünkü yol (kapak resmi yok → kurulmaz)
    K.set_style(d, "typographic", "sınama")
    assert studio.read(d, "cover.json")["style"] == "typographic"


@typeset_only
def test_collage_cover_goes_through_prepress(tmp_path, monkeypatch):
    import shutil
    if not shutil.which("gs"):
        pytest.skip("ghostscript yok")
    from editor.production import prepress
    d = _job(tmp_path)
    K.add_upload(d, _png(_scene_photo()), "foto.png", "sınama")
    K.set_style(d, "collage", "sınama")
    out = tmp_path / "baski.pdf"
    prepress.make(d / "kapak" / "kapak.pdf", out, studio._spec(d).bleed, TITLE)
    c = prepress.check(out)
    assert c["output_intent"] and c["non_cmyk_images"] == 0 and not c["unembedded_fonts"] and c["boxes"]


@typeset_only
def test_preflight_ignores_unprinted_cover_art(tmp_path):
    """Kolaj seçilince basılmayan (onaysız) kapak resmi ön kontrolde onay beklemez."""
    from PIL import Image
    d = _job(tmp_path)
    p = d / "resim" / "kapak.v1.png"
    p.parent.mkdir()
    Image.new("RGB", (300, 400), "#888888").save(p)
    studio.write(d, "studio.json", {"pages": {"kapak": {"versions": [{"v": 1, "path": str(p), "mode": "generate",
                                                                       "prompt": "", "seed": 1, "by": "t", "at": 0,
                                                                       "dpi": 300, "base": None}],
                                                         "selected": 1, "approved": False}}, "characters": {}})
    studio.rebuild(d)

    def approval():
        return {c["name"]: c for c in studio.read(d, "preflight.json")["checks"]}["Editör onayı"]["status"]
    assert approval() == "FAIL"
    K.add_upload(d, _png(_scene_photo()), "foto.png", "sınama")
    K.set_style(d, "collage", "sınama")
    assert approval() == "OK"


def test_generate_uses_collage_negative_and_book_seed(tmp_path, monkeypatch):
    """Model yok: sahte dil modeli ve sahte ressam. Negatif istem analog görünümle çelişmez, tohum kitaptan."""
    from PIL import Image
    d = tmp_path / "job1"
    d.mkdir()
    ms = M.Manuscript(title=TITLE, author=AUTHOR, meta={"CRM_SUMMARY": "Tanıtım."})
    ms.chapters.append(M.Chapter("B", [M.Block("para", "Metin.")]))
    for name, obj in (("manuscript.json", ms.to_json()), ("profile.json", _prof().to_json()),
                      ("spec.json", S.build(_prof()).to_json())):
        studio.write(d, name, obj)
    seen = {}

    class Llm:
        async def chat(self, alias, messages, **kw):
            seen["prompt"] = messages[0]["content"]
            return {"subject": "A child seen from behind.", "gesture": "She raises a paper kite high.",
                    "setting": "On a flat shore.", "era": "1960s", "why": "Deniz kıyısı."}, None

    class Painter:
        negative = K.NEGATIVE

        async def _generate(self, prompt, W, H, seed):
            seen.setdefault("seeds", []).append(seed)
            seen["gen"] = prompt
            return _png(_scene_photo(w=W // 4, h=H // 4))

        async def enlarge(self, png, W, H):
            return _png(Image.open(io.BytesIO(png)).resize((W, H))), ""

    made = asyncio.run(K.generate(d, 2, "kıyıda uçurtma", "sınama", painter=Painter(), llm=Llm()))
    st = K.load(d)
    assert len(made) == 2 and st["selected"] == made[0] and all(p["source"] == "model" for p in st["photos"])
    assert "kıyıda uçurtma" in seen["prompt"] and TITLE in seen["prompt"]
    assert seen["gen"].startswith("Black and white analog film photograph, 1960s documentary snapshot.")
    assert "blurry" not in K.NEGATIVE and "low quality" not in K.NEGATIVE and "grain" not in K.NEGATIVE
    assert st["scene"]["negative"] == K.NEGATIVE
    again = asyncio.run(K.generate(d, 1, "", "sınama", painter=Painter(), llm=Llm()))
    assert len(set(seen["seeds"])) == 3 and len(again) == 1                 # yeni adaylar yeni tohum
    assert K.view(d)["draft"] is True                                     # model fotoğrafı: taslak uyarısı


def test_workflow_registered():
    from editor.production.flow import ACTIVITIES, WORKFLOWS
    assert "CollagePhotos" in {getattr(w, "__temporal_workflow_definition").name for w in WORKFLOWS}
    assert "production_collage_photos" in {getattr(a, "__temporal_activity_definition").name for a in ACTIVITIES}


@typeset_only
def test_api_collage(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from editor.production import api
    root = tmp_path / "production"
    d = _job(root)
    monkeypatch.setattr(studio, "root", lambda: root)
    monkeypatch.setattr(api, "KEY", "k")
    monkeypatch.setenv("STUDIO_UPLOAD_MB", "1")
    c = TestClient(api.app)
    h = {"Authorization": "Bearer k", "X-Editor": "sinama"}
    base = "/v1/studio/jobs/job1/collage"
    v = c.get(base, headers=h).json()
    assert v["style"] is None and v["photos"] == [] and v["auto_labels"]
    assert c.put(base + "/style", headers=h, json={"style": "kolaj"}).status_code == 400
    r = c.put(base + "/upload?filename=b.jpg", headers=h, content=b"x" * (1024 * 1024 + 10))
    assert r.status_code == 413 and r.json()["code"] == "TOO_LARGE"
    r = c.put(base + "/upload?filename=f.png", headers=h, content=_png(_scene_photo(w=400, h=500)))
    assert r.status_code == 200 and r.json()["selected"] == r.json()["photo"]
    pid = r.json()["photo"]
    r = c.put(base + "/style", headers=h, json={"style": "collage"})
    assert r.status_code == 200 and r.json()["effective_style"] == "collage"
    assert c.get(f"{base}/photos/{pid}?w=120", headers=h).headers["content-type"] == "image/webp"
    assert c.get(base + "/preview?w=200", headers=h).status_code == 200
    assert c.post(base + "/layout", headers=h, json={}).json()["layout"] == 1
    assert c.put(base + "/labels", headers=h, json={"labels": [TITLE * 3]}).status_code == 400
    assert c.put(base + "/labels", headers=h, json={"labels": None}).json()["labels"] is None
    assert c.post(base + "/select", headers=h, json={"photo": "k_00000000"}).status_code == 404
    assert c.put(base + "/style", headers={"Authorization": "Bearer k"}, json={"style": "collage"}).status_code == 400
    studio.set_busy(d, {"key": "kapak", "since": 0})
    r = c.post(base + "/photos", headers=h, json={"count": 2})
    assert r.status_code == 409 and r.json()["code"] == "BUSY"
