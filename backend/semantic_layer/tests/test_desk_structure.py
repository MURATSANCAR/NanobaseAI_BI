"""Redaksiyon: metnin kitabın kendi bölümlerine ayrılması (ZEKI-44), yüklemenin diske akması (ZEKI-26) ve yanlış
yüklenen sürümün kaldırılması (ZEKI-45).

ZEKI-44 eski kusuru: PDF'in her satırı paragraf, tek başına sayfa numarası («12») bölüm başlığı sayılıyordu; metin
sayfa sayfa «bölüm»e bölünüyordu. Burada PDF'ler testin içinde elle kurulur (yazı tipi gömülmez, Helvetica); kitaba
özel hiçbir şey yoktur, yalnız yapı: yer imi, başlık puntosu, içindekiler sayfası, yapısızlık.
"""

from __future__ import annotations

import asyncio
import io
import os
import zipfile

import pytest
import sqlalchemy as sa

from semantic_bridge import editorial_desk as desk
from semantic_bridge import editorial_desk_structure as st
from semantic_layer.store.catalog_store import open_store

TENANT = "timas"
WORDS = ["elma", "armut", "kiraz", "erik", "incir", "dut", "ayva", "nar", "limon", "portakal", "mandalina", "kavun",
         "karpuz", "uzum", "visne", "ceviz"]


def body(p: int, k: int) -> str:
    return f"{WORDS[p % 16]} {WORDS[k % 16]} {WORDS[(p * 3 + k) % 16]} bahcede duruyordu ve herkes ona bakti."


def make_pdf(pages: list[list[tuple[float, str]]], outline: list[tuple[str, int]] | None = None) -> bytes:
    """Her satır kendi puntosuyla (Tf) ve konumuyla (Tm); isteğe bağlı düz yer imi listesi."""
    objs: list[bytes | None] = []

    def add(b: bytes | None) -> int:
        objs.append(b)
        return len(objs)

    cat, pages_id = add(None), add(None)
    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    page_ids: list[int] = []
    for lines in pages:
        ops, y = ["BT"], 800.0
        for size, text in lines:
            ops += [f"/F1 {size} Tf", f"1 0 0 1 72 {y} Tm", f"({text}) Tj"]
            y -= size + 8
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        page = add(None)
        objs[page - 1] = (f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 595 842] "
                          f"/Resources << /Font << /F1 {font} 0 R >> >> /Contents {content} 0 R >>").encode()
        page_ids.append(page)
    objs[pages_id - 1] = f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count {len(page_ids)} >>".encode()
    root = f"<< /Type /Catalog /Pages {pages_id} 0 R"
    if outline:
        head = add(None)
        items = [add(None) for _ in outline]
        for k, (title, pi) in enumerate(outline):
            parts = [f"/Title ({title})", f"/Parent {head} 0 R", f"/Dest [{page_ids[pi]} 0 R /XYZ 0 842 0]"]
            if k:
                parts.append(f"/Prev {items[k - 1]} 0 R")
            if k + 1 < len(items):
                parts.append(f"/Next {items[k + 1]} 0 R")
            objs[items[k] - 1] = ("<< " + " ".join(parts) + " >>").encode()
        objs[head - 1] = f"<< /Type /Outlines /First {items[0]} 0 R /Last {items[-1]} 0 R /Count {len(items)} >>".encode()
        root += f" /Outlines {head} 0 R"
    objs[cat - 1] = (root + " >>").encode()
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for n, b in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + (b or b"null") + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for o in offsets:
        out += f"{o:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root {cat} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def pdf_structure(data: bytes) -> st.Structure:
    return desk.structure_of("kitap.pdf", data)


def test_pdf_typography_chapters_not_page_numbers():
    pages = [[(28, "Kitap Adi")]]
    pages.append([(9, "Kitap Adi")] + [(11, body(1, k)) for k in range(6)] + [(9, "2")])
    pages.append([(9, "Kitap Adi"), (20, "Cocukluk")] + [(11, body(2, k)) for k in range(6)] + [(9, "3")])
    pages.append([(9, "Kitap Adi")] + [(11, body(3, k)) for k in range(8)] + [(9, "4")])
    pages.append([(9, "Kitap Adi"), (20, "Genclik")] + [(11, body(4, k)) for k in range(6)] + [(9, "5")])
    pages.append([(9, "Kitap Adi"), (20, "Yaslilik")] + [(11, body(5, k)) for k in range(6)] + [(9, "6")])
    s = pdf_structure(make_pdf(pages))
    assert s.source == "typography" and s.unit == "bolum"
    titles = [t for t, _ in s.chapters]
    assert titles == [st.LEAD, "Cocukluk", "Genclik", "Yaslilik"]
    for _, text in s.chapters[1:]:
        lines = text.split("\n")
        assert not any(ln.strip() in {"2", "3", "4", "5", "6", "Kitap Adi"} for ln in lines)   # sayfa no / üst bilgi yok
    assert body(3, 0) in s.chapters[1][1]              # bölüm sayfa aşar


def test_pdf_outline_wins():
    pages = [[(11, name)] + [(11, body(p, k)) for k in range(5)] for p, name in enumerate(["Deniz", "Orman", "Dag"])]
    s = pdf_structure(make_pdf(pages, outline=[("Deniz", 0), ("Orman", 1), ("Dag", 2)]))
    assert s.source == "outline"
    assert [t for t, _ in s.chapters] == ["Deniz", "Orman", "Dag"]
    assert not s.chapters[1][1].startswith("Orman")    # başlık satırı gövdeye tekrar girmez


def test_pdf_table_of_contents_page():
    toc = [(11, "Icindekiler"), (11, "Deniz ........ 2"), (11, "Orman ........ 3"), (11, "Dag ........ 4")]
    pages = [toc] + [[(11, name)] + [(11, body(p, k)) for k in range(5)] for p, name in enumerate(["Deniz", "Orman", "Dag"], 1)]
    s = pdf_structure(make_pdf(pages))
    assert s.source == "toc"
    assert [t for t, _ in s.chapters][-3:] == ["Deniz", "Orman", "Dag"]


def test_pdf_without_structure_is_named_piece():
    pages = [[(11, body(p, k)) for k in range(6)] for p in range(2)]
    s = pdf_structure(make_pdf(pages))
    assert s.source == "pieces" and s.unit == "parca"
    assert [t for t, _ in s.chapters] == ["Metnin tamamı"]


def test_pdf_lines_are_joined_into_paragraphs():
    assert st.reflow(["Uzun bir cümlenin ilk yarısı burada", "ve ikinci yarısı da burada bitiyor."]) == \
        "Uzun bir cümlenin ilk yarısı burada ve ikinci yarısı da burada bitiyor."
    assert st.reflow(["Satır sonunda tirelenen bir keli-", "me burada birleşir ve cümle biter."]).startswith(
        "Satır sonunda tirelenen bir kelime burada")


def _docx(paras: list[tuple[str, str | None]]) -> bytes:
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    styles = (f'<w:styles {w}><w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
              '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/></w:style>'
              '<w:style w:type="paragraph" w:styleId="Balk1"><w:name w:val="heading 1"/><w:pPr><w:outlineLvl w:val="0"/></w:pPr></w:style>'
              '<w:style w:type="paragraph" w:styleId="Balk2"><w:name w:val="heading 2"/><w:pPr><w:outlineLvl w:val="1"/></w:pPr></w:style>'
              '</w:styles>')
    ps = "".join((f'<w:p><w:pPr><w:pStyle w:val="{sty}"/></w:pPr>' if sty else "<w:p>") + f"<w:r><w:t>{t}</w:t></w:r></w:p>"
                 for t, sty in paras)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", f"<w:document {w}><w:body>{ps}</w:body></w:document>")
        z.writestr("word/styles.xml", styles)
    return buf.getvalue()


def test_docx_chapter_level_subsections_stay_in_body():
    data = _docx([("Kitap", "Title"), ("Bir", "Balk1"), ("Metin bir.", None), ("Alt başlık", "Balk2"), ("Metin iki.", None),
                  ("İki", "Balk1"), ("Metin üç.", None)])
    s = desk.structure_of("kitap.docx", data)
    assert s.source == "styles"
    assert [t for t, _ in s.chapters] == [st.LEAD, "Bir", "İki"]
    assert "Alt başlık" in s.chapters[1][1]


def test_txt_old_rule_kept():
    s = desk.structure_of("a.txt", "BÖLÜM 1\n\nKış geldi.\n\nBÖLÜM 2\n\nBahar.".encode())
    assert s.source == "pattern" and [t for t, _ in s.chapters] == ["BÖLÜM 1", "BÖLÜM 2"]


# ---------------------------------------------------------------------------------------------- ZEKI-26 / ZEKI-45

@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_DIR", str(tmp_path))
    monkeypatch.setenv("EDITORIAL_DISK_RESERVE_MB", "0")
    e = open_store("sqlite://").engine
    desk._ready.clear()
    desk.ensure(e)
    return e


async def _chunks(data: bytes, size: int = 7):
    for i in range(0, len(data), size):
        yield data[i:i + size]


def test_streamed_upload_moves_file_and_leaves_no_temp(engine, tmp_path):
    text = "BÖLÜM 1\n\nKış geldi.\n\nBÖLÜM 2\n\nBahar.".encode()
    inc = asyncio.run(desk.receive(_chunks(text), len(text)))
    assert inc.size == len(text) and not inc.stored
    try:
        out = desk.create_from_file(engine, TENANT, "editor", False, "manuscript", "Kış.txt", inc)
    finally:
        inc.discard()
    assert out["chapters"] == 2 and out["unit"] == "bolum"
    works = desk.list_works(engine, TENANT, "editor", False)
    stored = works[0]["manuscript"]
    assert stored["bytes"] == len(text)
    assert os.listdir(os.path.join(tmp_path, ".incoming")) == []
    path, _ = desk.file_path(engine, TENANT, "editor", False, stored["id"])
    assert open(path, "rb").read() == text


def test_rejected_streamed_upload_is_discarded(engine, tmp_path):
    inc = asyncio.run(desk.receive(_chunks(b"   \n  "), 6))
    try:
        with pytest.raises(desk.DeskError):
            desk.create_from_file(engine, TENANT, "editor", False, "manuscript", "bos.txt", inc)
    finally:
        inc.discard()
    assert os.listdir(os.path.join(tmp_path, ".incoming")) == []


def test_remove_version_falls_back_and_keeps_trace(engine):
    v1 = "BÖLÜM 1\n\nBir.\n\nBÖLÜM 2\n\nİki.".encode()
    v2 = "BÖLÜM 1\n\nYanlış dosya.".encode()
    out = desk.create_from_file(engine, TENANT, "editor", False, "manuscript", "a.txt", v1)
    wid = out["workId"]
    second = desk.upload_manuscript(engine, TENANT, "editor", False, wid, "b.txt", v2)
    assert second["version"] == 2
    got = desk.remove_file(engine, TENANT, "editor", False, second["fileId"])
    assert got["activeVersion"] == 1
    ch = desk.chapters(engine, TENANT, "editor", False, wid)
    assert len(ch["chapters"]) == 2 and ch["activeFileId"] == out["fileId"]
    removed = [v for v in ch["versions"] if v["version"] == 2][0]
    assert removed["removedAt"] and removed["removedBy"] == "editor"          # iz kalır
    with pytest.raises(desk.DeskError):
        desk.remove_file(engine, TENANT, "editor", False, second["fileId"])   # iki kez kaldırılmaz
    # Aynı yanlış dosya yeniden yüklenebilir (etkin sürümle aynı değil); sürüm numarası kaldırılanın üstünden artar.
    third = desk.upload_manuscript(engine, TENANT, "editor", False, wid, "b.txt", v2)
    assert third["version"] == 3
    # Başkası kaldıramaz.
    with pytest.raises(desk.DeskError):
        desk.remove_file(engine, TENANT, "baska", False, third["fileId"])
    desk.remove_file(engine, TENANT, "editor", False, third["fileId"])
    desk.remove_file(engine, TENANT, "editor", False, out["fileId"])
    w = desk.list_works(engine, TENANT, "editor", False)[0]
    assert w["manuscript"] is None and w["chapters"]["total"] == 0
    desk.delete_empty_work(engine, TENANT, wid)                                # kaldırılmış dosyası olan eser silinmez
    with engine.connect() as c:
        assert c.execute(sa.select(sa.func.count()).select_from(desk.FILES)).scalar_one() == 3


def test_title_and_author_editable_after_create(engine):
    w = desk.create_work(engine, TENANT, "editor", {"title": "Taslak", "author": "A"})
    desk.update_work(engine, TENANT, "editor", False, w["id"], {"title": "Doğru Ad", "author": "Doğru Yazar"})
    got = desk.list_works(engine, TENANT, "editor", False)[0]
    assert got["title"] == "Doğru Ad" and got["author"] == "Doğru Yazar"
    desk.update_work(engine, TENANT, "editor", False, w["id"], {"title": "Doğru Ad", "author": ""})
    assert desk.list_works(engine, TENANT, "editor", False)[0]["author"] is None


def test_translation_source_streams_without_cap(engine, tmp_path):
    """Çeviri kaynağı da aynı yoldan: diske akar, kopyalanmadan işin klasörüne taşınır, geçici dosya kalmaz."""
    from semantic_bridge import editorial_translation as T
    T._ready.clear()
    T.ensure(engine)
    src = b"CHAPTER ONE\n\nIt was cold. We waited.\n\nCHAPTER TWO\n\nNobody came."
    inc = asyncio.run(desk.receive(_chunks(src), len(src)))
    try:
        out = T.create_from_file(engine, TENANT, "editor", False, "Road.txt", inc, "en", "tr")
    finally:
        inc.discard()
    assert out["version"] == 1 and out["segments"] >= 3 and inc.stored
    assert os.listdir(os.path.join(tmp_path, ".incoming")) == []
    path, _ = T.source_path(engine, TENANT, "editor", False, out["jobId"])
    assert open(path, "rb").read() == src


def test_upload_over_the_configured_limit_is_refused_early_and_in_plain_words(monkeypatch, tmp_path):
    """ZEKI-26, kullanıcı kararı 2026-09-30: tek dosyanın üst sınırı Yönetim ayarı (varsayılan 300 MB). Bildirilen boy
    sınırı aşıyorsa hiç yazılmaz; bildirilmemişse akış sırasında durur ve yarım dosya kalmaz."""
    import asyncio
    import pytest
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import editorial_desk as desk

    monkeypatch.setenv("EDITORIAL_DIR", str(tmp_path))
    monkeypatch.setattr(admin_mod, "conf", lambda key, default="": "1" if key == "EDITORIAL_UPLOAD_MAX_MB" else default)

    async def body(n):
        for _ in range(n):
            yield b"x" * (512 * 1024)

    with pytest.raises(desk.DeskError) as e:
        asyncio.run(desk.receive(body(1), expected=3 * 1024 * 1024))
    assert e.value.status == 413 and "üst sınır 1 MB" in str(e.value)
    with pytest.raises(desk.DeskError):
        asyncio.run(desk.receive(body(4), expected=0))          # bildirilmemiş: 2 MB akarken durur
    assert not [p for p in (tmp_path / ".incoming").iterdir() if p.suffix == ".part"]
    ok = asyncio.run(desk.receive(body(1), expected=512 * 1024))
    assert ok.size == 512 * 1024
