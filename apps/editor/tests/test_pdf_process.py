"""PDF işi ayrı süreçte (2026-10-05, gece toplu düşmeler): işçinin döngüsü 81–93 sn durdu, o an süren bütün
etkinlikler sinyal sınırıyla düştü. Neden GIL: sayfa çizimi (PyMuPDF bütün çizim boyunca GIL'i tutar) ve saf Python
piksel döngüsü aynı süreçteki iş parçacıklarında koşuyordu.

- `nontext_ink_ratio` / `region_ink_ratio` numpy ile: sonuç eski döngüyle BİREBİR aynı,
- süreç havuzu (editor.pdfproc): iş başka süreçte koşar, sayfa sırası korunur, havuzdaki sonuç süreç içindekiyle aynı,
- iptal edilen çağrının başlamamış parçaları hiç koşmaz, asılı görev havuzu değiştirir (sonraki çağrı çalışır).
PDF'ler burada pymupdf ile çizilir; veritabanı yok."""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402
import types  # noqa: E402


class _Stub(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        sub = _Stub(f"{self.__name__}.{name}")
        sys.modules[sub.__name__] = sub
        return sub


# öteki test dosyaları gibi gerçek veritabanı sürücüsü yüklenmez (DB'siz ortamda havuz beklemesin)
for _mod in ("psycopg", "psycopg.rows", "psycopg.types", "psycopg.types.json", "psycopg_pool"):
    sys.modules.setdefault(_mod, _Stub(_mod))

pymupdf = pytest.importorskip("pymupdf")
pytest.importorskip("numpy")

from editor import archive, document as D, pdfproc  # noqa: E402

LINE = "Bir varmış bir yokmuş, evvel zaman içinde, kalbur saman içinde."


def _old_nontext_ink_ratio(page) -> float:
    """2026-10-05 öncesi gövde, birebir (karşılaştırma için)."""
    z = 100 / 72
    pm = page.get_pixmap(matrix=pymupdf.Matrix(z, z), colorspace=pymupdf.csGRAY, alpha=False)
    w, h, buf = pm.width, pm.height, bytearray(pm.samples)
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            if not any(sp["text"].strip() and sp.get("alpha", 255) != 0 for sp in ln["spans"]):
                continue
            x0, y0, x1, y1 = (int(v * z) for v in ln["bbox"])
            xa, xb = max(0, x0 - 2), min(w, x1 + 2)
            for y in range(max(0, y0 - 2), min(h, y1 + 2)):
                buf[y * w + xa: y * w + xb] = b"\xff" * (xb - xa)
    mx, my = int(w * .08), int(h * .08)
    ink = sum(1 for y in range(my, h - my) for v in buf[y * w + mx: y * w + w - mx] if v < 235)
    return ink / max(1, (w - 2 * mx) * (h - 2 * my))


def _old_region_ink_ratio(png_path: str, bbox: list[int]) -> float:
    if not bbox or len(bbox) != 4 or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        return 0.0
    pm = pymupdf.Pixmap(pymupdf.csGRAY, pymupdf.Pixmap(png_path))
    w, h, buf = pm.width, pm.height, pm.samples
    x0, x1 = int(bbox[0] / 1000 * w), max(int(bbox[2] / 1000 * w), int(bbox[0] / 1000 * w) + 1)
    y0, y1 = int(bbox[1] / 1000 * h), max(int(bbox[3] / 1000 * h), int(bbox[1] / 1000 * h) + 1)
    ink = sum(1 for y in range(y0, min(h, y1)) for v in buf[y * w + x0: y * w + min(w, x1)] if v < 235)
    return ink / max(1, (min(w, x1) - x0) * (min(h, y1) - y0))


def _book(path: pathlib.Path) -> pathlib.Path:
    """Sayfa türleri: düz metin, boş, çizim + metin, kenara taşan satırlar, resim + metin, yalnız çizim, ince sayfa."""
    doc = pymupdf.open()
    p = doc.new_page(width=400, height=600)                       # 1 düz metin
    for i in range(25):
        p.insert_text((40, 60 + i * 18), LINE, fontsize=10)
    doc.new_page(width=400, height=600)                           # 2 boş
    p = doc.new_page(width=400, height=600)                       # 3 çizim + metin
    p.draw_circle((200, 300), 120, color=(0, 0, 0), fill=(.3, .3, .3))
    p.draw_rect(pymupdf.Rect(30, 30, 370, 80), color=(0, 0, 0), fill=(.1, .1, .1))
    p.insert_text((40, 520), LINE, fontsize=11)
    p = doc.new_page(width=400, height=600)                       # 4 sayfadan taşan satırlar (negatif / taşan bbox)
    p.insert_text((-80, 8), LINE + " " + LINE, fontsize=14)
    p.insert_text((300, 598), LINE, fontsize=14)
    p.draw_line((0, 0), (400, 600), color=(0, 0, 0), width=3)
    p = doc.new_page(width=400, height=600)                       # 5 raster resim + metin
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 64, 64), 0)
    pix.set_rect(pix.irect, (40, 90, 160))
    p.insert_image(pymupdf.Rect(60, 100, 340, 380), pixmap=pix)
    p.insert_text((40, 450), LINE, fontsize=10)
    p = doc.new_page(width=400, height=600)                       # 6 yalnız çizim (yazısı yola çevrilmiş gibi)
    for row in range(18):
        sh = p.new_shape()
        for col in range(30):
            x, y = 40 + col * 10.5, 70 + row * 25
            sh.draw_rect(pymupdf.Rect(x, y, x + 6, y + 9))
        sh.finish(color=(0, 0, 0), fill=(0, 0, 0))
        sh.commit()
    p = doc.new_page(width=13, height=900)                        # 7 çok ince sayfa (kenar payı ≥ yarı genişlik)
    p.insert_text((1, 100), "x", fontsize=8)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    return path


@pytest.fixture
def pool_off():
    pdfproc.configure(0)
    yield
    pdfproc.configure(0)


# ------------------------------------------------------------------ numpy = eski döngü
def test_nontext_ink_ratio_is_exactly_the_old_loop(tmp_path):
    doc = pymupdf.open(_book(tmp_path / "k.pdf"))
    got = [D.nontext_ink_ratio(p) for p in doc]
    want = [_old_nontext_ink_ratio(p) for p in doc]
    assert got == want                                    # kayan nokta dahil birebir
    assert want[1] == 0.0 and want[2] > 0.05 and want[5] > D.LAYERLESS_INK_MIN


def test_region_ink_ratio_is_exactly_the_old_loop(tmp_path):
    doc = pymupdf.open(_book(tmp_path / "k.pdf"))
    png = tmp_path / "p3.png"
    doc[2].get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False).save(png)
    boxes = [[0, 0, 1000, 1000], [100, 200, 900, 800], [500, 500, 501, 501], [990, 990, 1000, 1000],
             [-50, -20, 300, 400], [0, 0, 1200, 1100], [300, 300, 300, 600], [], [1, 2, 3]]
    assert [D.region_ink_ratio(str(png), b) for b in boxes] == [_old_region_ink_ratio(str(png), b) for b in boxes]


# ------------------------------------------------------------------ süreç havuzu
def test_pool_runs_in_other_processes_and_keeps_page_order(tmp_path, pool_off):
    pdf = _book(tmp_path / "k.pdf")
    assert pdfproc.configure(2) == 2

    async def main():
        pids = {await pdfproc.run(pdfproc.pid_task) for _ in range(4)}
        facts = await pdfproc.map_pages(D.manifest_chunk, str(pdf), range(1, 8))
        n = await pdfproc.run(pdfproc.page_count, str(pdf))
        return pids, facts, n
    pids, facts, n = asyncio.run(main())
    assert os.getpid() not in pids and n == 7
    assert [f["page_no"] for f in facts] == list(range(1, 8))
    doc = pymupdf.open(pdf)
    for f, page in zip(facts, doc):                       # havuzdaki ölçü süreç içindekiyle aynı
        assert f["ink"] == _old_nontext_ink_ratio(page)
        assert f["text"] == (page.get_text("text") or "")
        assert pathlib.Path(f["path"]).is_file() and f["path"].endswith(f"p{f['page_no']:04d}.png")
    # eşzamanlı (eski) render_page yolu da havuzdan geçer ve aynı dosyayı verir
    assert pdfproc.run_sync(D.render_file, str(pdf), 3)["path"] == facts[2]["path"]


def test_async_manifest_text_layer_and_visual_pages_match_the_in_process_ones(tmp_path, monkeypatch, pool_off):
    """Etkinliklerin kullandığı süreçli yollar (_async) eski süreç içi işlevlerle aynı satırları yazar."""
    import contextlib
    pdf = _book(tmp_path / "k.pdf")
    written = {"async": [], "sync": []}
    mode = {"now": "sync"}

    class Conn:
        def execute(self, sql, args=()):
            written[mode["now"]].append((sql.split()[2], tuple(str(a) if not isinstance(a, (int, float, bool))
                                                              else a for a in args)))

    class J:
        def __init__(self, obj):
            self.obj = obj

        def __str__(self):
            import json
            return json.dumps(self.obj, sort_keys=True)

    monkeypatch.setattr(D.db, "J", J, raising=False)
    monkeypatch.setattr(D.db, "tx", lambda: contextlib.nullcontext(Conn()), raising=False)
    monkeypatch.setattr(D.db, "one", lambda sql, *a: {"id": "bv", "file_path": str(pdf), "page_count": 7},
                        raising=False)
    monkeypatch.setattr(D, "_open_version", lambda bv, repair=True: (pdfproc.open_doc(str(pdf), repair),
                                                                     {"id": "bv", "file_path": str(pdf)}))
    sync_man = D.create_page_manifest("bv")
    sync_text = D.extract_text_layer("g", "bv")
    sync_vis = archive.visual_pages("bv")
    mode["now"] = "async"
    pdfproc.configure(2)

    async def main():
        return (await D.create_page_manifest_async("bv"), await D.extract_text_layer_async("g", "bv"),
                await archive.visual_pages_async("bv"))
    man, text, vis = asyncio.run(main())
    assert man == sync_man and text == sync_text and vis == sync_vis
    assert written["async"] == written["sync"] and len(written["sync"]) > 7


def test_cancelled_call_never_runs_its_pending_chunks(tmp_path, monkeypatch, pool_off):
    monkeypatch.setenv("EDITOR_PDF_CHUNK", "1")
    pdfproc.configure(1)
    log = tmp_path / "pages.txt"

    async def main():
        await pdfproc.run(pdfproc.pid_task)              # havuz ayakta (başlatma süresi ölçüme girmesin)
        t = asyncio.ensure_future(pdfproc.map_pages(pdfproc.touch_pages, str(log), range(1, 21), 0.3))
        await asyncio.sleep(0.5)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t
        await asyncio.sleep(1.5)                         # başlamış parça kendiliğinden biter
        return await pdfproc.run(pdfproc.pid_task)       # havuz tıkanmadı
    asyncio.run(main())
    done = log.read_text().split()
    assert 1 <= len(done) <= 3, done                     # 20 sayfanın yalnız başlamış olanları


def test_hung_task_replaces_the_pool(monkeypatch, pool_off):
    pdfproc.configure(1)

    async def main():
        first = await pdfproc.run(pdfproc.pid_task)      # havuz ayakta; sınır bundan sonra 1 sn
        monkeypatch.setenv("EDITOR_PDF_TASK_SECONDS", "1")
        t0 = time.monotonic()
        with pytest.raises(TimeoutError):
            await pdfproc.run(pdfproc.sleep_task, 30)
        waited = time.monotonic() - t0
        monkeypatch.delenv("EDITOR_PDF_TASK_SECONDS")
        second = await pdfproc.run(pdfproc.pid_task)
        return first, second, waited
    first, second, waited = asyncio.run(main())
    assert waited < 5 and first != second               # asılı süreç öldürüldü, yeni havuz çalışıyor


def test_pool_off_runs_in_process(tmp_path, pool_off):
    pdf = _book(tmp_path / "k.pdf")
    assert not pdfproc.active()
    assert asyncio.run(pdfproc.run(pdfproc.pid_task)) == os.getpid()
    assert [f["page_no"] for f in asyncio.run(pdfproc.map_pages(D.manifest_chunk, str(pdf), [2, 1]))] == [2, 1]
