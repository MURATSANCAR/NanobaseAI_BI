"""Portal belge okuma (ortak yapı taşı 4): metin katmanlı / taranmış sayfa ayrımı, güven hesabı, OCR temizliği,
yalnız istenen sayfaların okunması, defter kaydı olmaması. Model ve veritabanı yok (OCR çağrısı sahte). Editör
imajında çalıştır:

    python /app/tests/test_portal_read.py
"""

from __future__ import annotations

import asyncio
import math
import sys
import types
from pathlib import Path

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

from editor import portal_read as PR  # noqa: E402

BODY = ("Teknik şartname: yüklenici teslim süresi içinde kırk beş gün boyunca numune verecek ve yerli malı belgesi "
        "sunacaktır. Gecikme halinde günlük binde üç ceza uygulanır.")


def _pdf(texts: list[str], image_page: bool = False) -> bytes:
    import pymupdf
    doc = pymupdf.open()
    for t in texts:
        pg = doc.new_page()
        if t:
            pg.insert_textbox(pymupdf.Rect(40, 40, 560, 800), t, fontsize=11)
    if image_page:
        pg = doc.new_page()
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 40), 0)
        pix.clear_with(200)
        pg.insert_image(pymupdf.Rect(50, 50, 400, 300), pixmap=pix)
    return doc.tobytes()


def test_plan_separates_text_and_scanned_pages():
    kind, pages = PR.plan(_pdf([BODY, ""], image_page=True), "sartname.pdf")
    assert kind == "pdf" and [p["page"] for p in pages] == [1, 2, 3]
    assert pages[0]["reasons"] == []
    assert pages[1]["reasons"] == ["NO_TEXT_LAYER"] and pages[2]["reasons"] == ["NO_TEXT_LAYER"]


def test_unsupported_and_empty():
    for name, data in (("a.docx", b"x"), ("a.pdf", b"")):
        try:
            PR.plan(data, name)
        except PR.ReadError:
            continue
        raise AssertionError(name)


def test_confidence_is_geometric_mean():
    assert PR.confidence([]) is None
    assert PR.confidence([0.0, 0.0]) == 1.0
    assert PR.confidence([math.log(0.5), math.log(0.5)]) == 0.5


def test_clean_ocr_strips_tags_and_loops():
    text, cut = PR.clean_ocr("<table><tr><td>Teslim 45 gün</td></tr></table>\n\n" + "tekrar eden cümle " * 12)
    assert "<" not in text and "Teslim 45 gün" in text
    assert cut > 0 and text.count("tekrar eden cümle") == 1


def test_read_ocr_only_needed_and_requested_pages(monkeypatch=None):
    calls = []

    async def fake_ocr(png: bytes, page_no: int) -> dict:
        calls.append(page_no)
        assert png[:4] == b"\x89PNG"
        return {"page": page_no, "text": "Taranmış sayfa metni 12.05.2026", "confidence": 0.93, "loopCharsRemoved": 0,
                "truncated": False}

    PR.ocr_png = fake_ocr
    data = _pdf([BODY, ""], image_page=True)
    out = asyncio.run(PR.read(data, "s.pdf"))
    assert calls == [2, 3] and out["ocrPages"] == [2, 3]
    assert [p["source"] for p in out["pages"]] == ["text", "ocr", "ocr"]
    assert out["pages"][0]["confidence"] is None and out["pages"][1]["confidence"] == 0.93
    calls.clear()
    out = asyncio.run(PR.read(data, "s.pdf", only_pages=[3]))
    assert calls == [3] and [p["source"] for p in out["pages"]] == ["text", "none", "ocr"]
    calls.clear()
    out = asyncio.run(PR.read(data, "s.pdf", ocr=False))
    assert calls == [] and [p["source"] for p in out["pages"]] == ["text", "none", "none"]


def test_image_file_is_one_ocr_page():
    import pymupdf

    async def fake_ocr(png: bytes, page_no: int) -> dict:
        return {"page": page_no, "text": "Sertifika", "confidence": None, "loopCharsRemoved": 0, "truncated": False}

    PR.ocr_png = fake_ocr
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 3000, 2000), 0)
    pix.clear_with(255)
    out = asyncio.run(PR.read(pix.tobytes("png"), "belge.png"))
    assert out["kind"] == "image" and out["pages"][0]["source"] == "ocr" and out["pages"][0]["confidence"] is None
    png = PR.page_png(pix.tobytes("png"), "image", 1)
    small = pymupdf.Pixmap(png)
    assert max(small.width, small.height) <= 1600


def test_no_ledger_write():
    src = (Path(__file__).resolve().parents[1] / "src" / "editor" / "portal_read.py").read_text(encoding="utf-8")
    assert "model_call" not in src.split('"""', 2)[2]          # yalnız belge metninde anılır, kodda defter yazımı yok
    assert "_record(" not in src


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
