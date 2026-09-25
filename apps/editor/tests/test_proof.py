"""Baskı provası ve 3B kitap ölçüleri (editor.production.proof, api_proof): model ve veritabanı yok. Renk
dönüşümü ve PDF çizimi editor-py imajında (Pillow ImageCms, pymupdf). Çalıştır:

    pytest apps/editor/tests/test_proof.py
"""

from __future__ import annotations

import io
import json
import math
import os
import sys
import time
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

np = pytest.importorskip("numpy")
Image = pytest.importorskip("PIL.Image")
pytest.importorskip("PIL.ImageCms")

from editor.production import proof, spec as S, studio  # noqa: E402

MM = 72 / 25.4
TRIM, BLEED = (165.0, 225.0), 3.0


def _rgb(*colors, size=8):
    """Yan yana düz renk şeritleri (her renk size×size)."""
    im = Image.new("RGB", (size * len(colors), size))
    for i, c in enumerate(colors):
        im.paste(c, (i * size, 0, (i + 1) * size, size))
    return im


def _cell(arr, i, size=8):
    return arr[:, i * size:(i + 1) * size]


# ------------------------------------------------------------------ kâğıtlar ve profiller
def test_every_paper_has_a_readable_profile_and_license_note():
    assert (proof.ICC / "LISANS.md").exists()
    for p in proof.PAPERS.values():
        assert (proof.ICC / p.profile).exists(), p.profile
        prof = proof._profile(p.profile)
        from PIL import ImageCms
        assert "copyright" in ImageCms.getProfileCopyright(prof).lower()   # «free of known copyright restrictions»
        assert 280 <= p.tac_limit <= 350
        assert p.finish in ("gloss", "matte", "uncoated")


def test_caliper_matches_spec_for_the_books_own_papers():
    assert proof.PAPERS["kuse"].caliper == pytest.approx(S.CALIPER["kuse_130"], abs=0.005)
    assert proof.PAPERS["hamur"].caliper == pytest.approx(S.CALIPER["hamur_70"], abs=0.005)
    assert proof.PAPERS["mat_kuse"].caliper > proof.PAPERS["kuse"].caliper      # mat daha kabarık
    assert proof.PAPERS["samua"].caliper > proof.PAPERS["hamur"].caliper        # şamua kitap kâğıdı kabarık


def test_samua_white_is_warmer_than_coated_white():
    def rgb(h):
        return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
    r, g, b = rgb(proof.paper_white("samua"))
    assert r > b and g > b                     # sarımsı
    kr, kg, kb = rgb(proof.paper_white("kuse"))
    assert kb >= kr                            # kuşe nötr/soğuk beyaz
    assert all(v < 255 for v in (r, g, b))     # kâğıt beyazı ekran beyazından koyu (mutlak kolorimetrik)


# ------------------------------------------------------------------ dönüşüm
def test_saturated_blue_is_out_of_gamut_on_uncoated_but_neutrals_are_not():
    im = _rgb((0, 60, 255), (128, 128, 128), (0, 0, 0), (255, 255, 255), (200, 170, 140))
    for key in proof.PAPERS:
        r = proof.convert(im, key)
        g = r["gamut"]
        for i in (1, 2, 3, 4):                 # gri, siyah (siyah nokta dengeli), beyaz, ten rengi: kayıp yok
            assert not _cell(g, i).any(), (key, i, float(_cell(r["de"], i).max()))
        assert r["paper"].size == im.size and r["plain"].mode == "RGB"
    assert _cell(proof.convert(im, "hamur")["gamut"], 0).all()
    assert _cell(proof.convert(im, "samua")["gamut"], 0).all()
    # kaplamalıda aynı mavi daha az kaybeder
    assert _cell(proof.convert(im, "kuse")["de"], 0).mean() < _cell(proof.convert(im, "hamur")["de"], 0).mean()


def test_lab_decoding_handles_negative_a_b():
    # yeşil (a<0) ve mavi (b<0): işaretli bayt yanlış okunursa fark 200'ün üstüne çıkar
    im = _rgb((40, 160, 60), (30, 60, 200), (90, 140, 200))
    r = proof.convert(im, "kuse")
    assert float(r["de"].max()) < 40


def test_plain_view_keeps_white_white_paper_view_shows_paper():
    im = _rgb((255, 255, 255))
    r = proof.convert(im, "samua")
    assert r["plain"].getpixel((1, 1)) == (255, 255, 255)
    assert r["paper"].getpixel((1, 1)) != (255, 255, 255)


def test_tac_sum():
    cm = Image.new("CMYK", (2, 1))
    cm.putpixel((0, 0), (255, 255, 255, 255))
    cm.putpixel((1, 0), (128, 0, 0, 255))
    t = proof.tac(cm)
    assert t[0, 0] == pytest.approx(400, abs=0.1)
    assert t[0, 1] == pytest.approx(150.2, abs=0.5)


def test_rich_black_separation_stays_within_paper_limit():
    im = _rgb((0, 0, 0), (20, 10, 40))
    for key, p in proof.PAPERS.items():
        assert proof.tac(proof.convert(im, key)["cmyk"]).max() <= p.tac_limit + 0.5, key


def test_hatch_marks_only_near_mask():
    mask = np.zeros((40, 40), bool)
    mask[20, 20] = True
    im = proof.hatch(mask, (255, 0, 0, 255), (255, 255, 255, 200))
    a = np.asarray(im)[..., 3]
    assert im.mode == "RGBA" and im.size == (40, 40)
    assert a[20, 20] > 0 and a[0, 0] == 0
    assert (a > 0).sum() == proof.MARK_GROW ** 2      # tek piksel büyütülerek görünür olur
    assert len({tuple(p) for p in np.asarray(im)[a > 0][:, :3]}) == 2   # iki renk dönüşümlü tarama


# ------------------------------------------------------------------ iş klasörü
def _pdf(path: Path, pages: list[list[tuple]], w_mm: float, h_mm: float, cmyk: bool = False) -> None:
    """Düz dikdörtgenlerle PDF. Her sayfa: [(x0,y0,x1,y1 oran), renk (RGB ya da CMYK 0–1)]."""
    import pymupdf
    doc = pymupdf.open()
    for rects in pages:
        pg = doc.new_page(width=w_mm * MM, height=h_mm * MM)
        for (x0, y0, x1, y1), color in rects:
            r = pymupdf.Rect(x0 * pg.rect.width, y0 * pg.rect.height, x1 * pg.rect.width, y1 * pg.rect.height)
            pg.draw_rect(r, color=None, fill=color)
    doc.save(path)


def _job(tmp_path: Path, cover: bool = True) -> Path:
    pytest.importorskip("pymupdf")
    d = tmp_path / "production" / "20260925000000abcdef"
    (d / "dizgi").mkdir(parents=True)
    W, H = TRIM[0] + 2 * BLEED, TRIM[1] + 2 * BLEED
    blue = ((0.1, 0.1, 0.9, 0.5), (0.0, 0.24, 1.0))
    gray = ((0.1, 0.6, 0.9, 0.9), (0.5, 0.5, 0.5))
    _pdf(d / "dizgi" / "ic-sayfalar.pdf", [[gray], [blue, gray], [gray], [blue]], W, H)
    studio.write(d, "spec.json", {"trim_w": TRIM[0], "trim_h": TRIM[1], "bleed": BLEED, "paper": "kuse_130"})
    if cover:
        (d / "kapak").mkdir()
        spine = 6.4
        _pdf(d / "kapak" / "kapak.pdf", [[blue]], 2 * TRIM[0] + spine + 2 * BLEED, H)
        studio.write(d, "cover.json", {"spine_mm": spine, "binding": "amerikan_cilt",
                                       "size_mm": [2 * TRIM[0] + spine + 2 * BLEED, H]})
    return d


def test_render_writes_layers_and_report_and_caches(tmp_path):
    d = _job(tmp_path)
    files = proof.render(d, "page", 2, "hamur", 300)
    assert set(files) == {"paper", "plain", "gamut", "tac", "report"}
    rep = json.loads(files["report"].read_text())
    assert rep["paper"] == "hamur" and rep["tac_source"] == "prova" and rep["tac_limit"] == 300
    assert rep["gamut_share"] > 10                         # sayfanın yarısı doygun mavi
    assert rep["tac_max"] <= 300
    size = Image.open(studio.page_preview(d, 2, 300)).size
    for k in ("paper", "plain", "gamut", "tac"):
        assert Image.open(files[k]).size == size
    assert Image.open(files["gamut"]).mode == "RGBA"
    stamp = files["paper"].stat().st_mtime_ns
    time.sleep(0.02)
    assert proof.render(d, "page", 2, "hamur", 300)["paper"].stat().st_mtime_ns == stamp   # önbellek
    # gri sayfada renk kaybı yok
    assert proof.report(d, "page", 1, "hamur", 300)["gamut_share"] == 0


def test_tac_is_read_from_print_pdf_when_present(tmp_path):
    d = _job(tmp_path)
    W, H = TRIM[0] + 2 * BLEED, TRIM[1] + 2 * BLEED
    (d / "baski").mkdir()
    # baskı PDF'i: doğrudan CMYK %400 dolgu (kesim işaretli PDF'te kutular; burada sayfa = taşma kutusu)
    _pdf(studio.print_paths(d)["ic"], [[((0, 0, 1, 0.5), (1, 1, 1, 1))]] * 4, W, H)
    future = time.time() + 5
    os.utime(studio.print_paths(d)["ic"], (future, future))
    rep = proof.report(d, "page", 1, "kuse", 300)
    assert rep["tac_source"] == "baski"
    assert rep["tac_max"] >= 390 and rep["tac_share"] > 40
    tac = np.asarray(Image.open(proof.render(d, "page", 1, "kuse", 300)["tac"]))[..., 3]
    assert tac[: tac.shape[0] // 3].any() and not tac[-tac.shape[0] // 4:].any()   # işaret yalnız üst yarıda


def test_book_dimensions(tmp_path, monkeypatch):
    d = _job(tmp_path)
    monkeypatch.setattr(studio, "page_count", lambda _d: 48)
    b = proof.book(d)
    assert b["trim_w"] == TRIM[0] and b["pages"] == 48 and b["leaves"] == 24
    assert b["default_paper"] == "kuse"
    assert b["thickness_mm"]["kuse"] == pytest.approx(24 * proof.PAPERS["kuse"].caliper + 2 * S.COVER_BOARD, abs=0.01)
    assert b["thickness_mm"]["mat_kuse"] > b["thickness_mm"]["kuse"]
    assert b["cover"]["spine_mm"] == 6.4 and b["cover"]["binding"] == "amerikan_cilt"
    assert {p["key"] for p in b["papers"]} == set(proof.PAPERS)
    monkeypatch.setattr(studio, "page_count", lambda _d: 47)
    assert proof.book(d)["leaves"] == math.ceil(47 / 2)


def test_book_without_cover(tmp_path, monkeypatch):
    d = _job(tmp_path, cover=False)
    monkeypatch.setattr(studio, "page_count", lambda _d: 4)
    assert proof.book(d)["cover"] is None


# ------------------------------------------------------------------ uçlar
@pytest.fixture
def client(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from editor.production import api
    d = _job(tmp_path)
    monkeypatch.setattr(studio, "root", lambda: d.parent)
    monkeypatch.setattr(studio, "page_count", lambda _d: 4)
    monkeypatch.setattr(api, "KEY", "k")
    return TestClient(api.app), d.name


def test_api_proof_endpoints(client):
    c, job = client
    h = {"Authorization": "Bearer k"}
    assert c.get(f"/v1/studio/jobs/{job}/proof").status_code == 401          # uygulamanın yetkisi geçerli
    r = c.get(f"/v1/studio/jobs/{job}/proof", headers=h)
    assert r.status_code == 200 and r.json()["leaves"] == 2
    r = c.get(f"/v1/studio/jobs/{job}/proof/pages/2", params={"paper": "samua", "w": 240}, headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(r.content)).mode == "RGB"
    r = c.get(f"/v1/studio/jobs/{job}/proof/pages/2", params={"paper": "samua", "w": 240, "layer": "gamut"}, headers=h)
    assert Image.open(io.BytesIO(r.content)).mode == "RGBA"
    r = c.get(f"/v1/studio/jobs/{job}/proof/pages/2/report", params={"paper": "samua", "w": 240}, headers=h)
    assert r.json()["gamut_share"] > 0
    r = c.get(f"/v1/studio/jobs/{job}/proof/cover", params={"paper": "kuse", "w": 400}, headers=h)
    assert r.status_code == 200
    assert c.get(f"/v1/studio/jobs/{job}/proof/cover/report", params={"paper": "kuse", "w": 400},
                 headers=h).json()["tac_source"] == "prova"
    assert c.get(f"/v1/studio/jobs/{job}/proof/pages/2", params={"paper": "yok"}, headers=h).status_code == 404
    assert c.get(f"/v1/studio/jobs/{job}/proof/pages/99", params={"paper": "kuse"}, headers=h).status_code == 404
    assert c.get(f"/v1/studio/jobs/{job}/proof/pages/2", params={"paper": "kuse", "layer": "x"},
                 headers=h).status_code == 422
    assert c.get("/v1/studio/jobs/yok/proof", headers=h).status_code == 404
