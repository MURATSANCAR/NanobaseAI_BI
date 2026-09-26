"""Künyede kitap adı ve yazar düzeltmesi (studio.set_kunye `book`, manuscript.field_source/fill_from_crm, api
POST /kunye): el yazması tek doğruluk kaynağı; kapak, iç kapak, künye, dizgi yeni değerle; boş kitap adı reddi;
CRM eşleşmesi yalnız boş alanı doldurur, editörün değerini ezmez. Model yok; veritabanı sahte satırlarla. Typst ve
fontlar editor-py imajında; yoksa dizgi testleri atlanır. Çalıştır:

    pytest apps/editor/tests/test_kunye_book.py
"""

from __future__ import annotations

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

from editor.production import front, manuscript as M, spec as S, studio  # noqa: E402
from editor.production.profile import Profile  # noqa: E402

FONTS = Path("/app/data/fonts")
HAS_TYPST = FONTS.joinpath("Andika-Regular.ttf").exists()
try:
    import typst  # noqa: F401
except ImportError:
    HAS_TYPST = False
typeset_only = pytest.mark.skipif(not HAS_TYPST, reason="typst/fontlar yok (editor-py imajında koşar)")

OLD_TITLE = "Etimesgutlu_Bebek_Aslan.docx"          # eski Word işi: kitap adı dosya adından kalmış
NEW_TITLE = "Işıklı Ormanın Küçük Aslanı"
NEW_AUTHOR = "Gülşen Öztürk"


def _crm_row(title=NEW_TITLE, rid="11111111-1111-1111-1111-111111111111", **kw):
    return {"crm_title": title, "authors": kw.get("authors", ["Ayşe Kayıt"]), "illustrators": kw.get("illustrators", []),
            "summary": kw.get("summary", "Kayıttaki tanıtım yazısı."), "isbn": kw.get("isbn", "9786050000009"),
            "stock_code": kw.get("stock_code", "STK-1"), "crm_book_id": rid}


def _fake_db(monkeypatch, rows):
    """ed.book_crm_record yerine sahte satırlar (crm_lookup yalnız bu sorguyu yapar)."""
    from editor import db
    monkeypatch.setattr(db, "all_rows", lambda sql, *a: [dict(r) for r in rows], raising=False)


def _no_rebuild(monkeypatch):
    calls = []
    monkeypatch.setattr(studio, "rebuild", lambda d: calls.append(d.name))
    return calls


def _mini(tmp_path: Path, title=OLD_TITLE, author=None, source=None, meta=None) -> Path:
    """Dizgisiz iş klasörü: el yazması, künye, durum (CRM/kayıt testleri için)."""
    d = tmp_path / "job1"
    d.mkdir(parents=True)
    ms = M.Manuscript(title=title, author=author, meta=dict(meta or {}),
                      source=source if source is not None else {"kind": "docx", "path": "/x/k.docx", "crm_match": "yok",
                                                                "origin": {"title": "docx", "author": None}})
    ms.chapters = [M.Chapter(None, [M.Block("para", "Bir varmış bir yokmuş.")])]
    studio.write(d, "manuscript.json", ms.to_json())
    studio.write(d, "front.json", {"kunye": front.kunye(ms, {}), "kunye_fields": {}, "manual": {},
                                   "bios": [{"name": author or front.MISSING, "text": front.MISSING}]})
    studio.write(d, "state.json", {"title": title, "status": "done", "steps": [
        {"key": "crm", "label": "CRM proje verisi", "status": "warn", "summary": "CRM kaydı bulunamadı"}]})
    studio.write(d, "job.json", {"id": "job1", "source": {"docx": "/x/k.docx"}, "created_by": "t", "art_mode": "auto"})
    return d


def _rows(fr):
    return {r[0]: r[1] for r in fr["kunye"] if r[0]}


# ------------------------------------------------------------------ kayıt, kaynak, CRM (dizgisiz)
def test_edit_keeps_original_and_logs_who_when_was(tmp_path, monkeypatch):
    d = _mini(tmp_path)
    _fake_db(monkeypatch, [])
    calls = _no_rebuild(monkeypatch)
    out = studio.set_kunye(d, {}, "editör1", {"title": f"  {NEW_TITLE} ", "author": NEW_AUTHOR})
    assert calls == ["job1"] and out["changed"] == ["title", "author"]
    assert out["was"] == {"title": OLD_TITLE, "author": None} and out["crm"]["match"] == "yok"
    m = studio.read(d, "manuscript.json")
    assert (m["title"], m["author"]) == (NEW_TITLE, NEW_AUTHOR)                     # boşluk düzeltildi
    assert m["source"]["read"] == {"title": OLD_TITLE, "author": None}              # okunan özgün değer kalır
    e = m["source"]["edits"]["title"]
    assert e["by"] == "editör1" and e["was"] == OLD_TITLE and e["value"] == NEW_TITLE and e["at"] > 0
    assert [x["field"] for x in m["source"]["edit_log"]] == ["title", "author"]
    assert _rows(studio.read(d, "front.json"))["Kitap"] == NEW_TITLE
    assert _rows(studio.read(d, "front.json"))["Yazar"] == NEW_AUTHOR
    assert studio.read(d, "front.json")["bios"] == [{"name": NEW_AUTHOR, "text": front.MISSING}]
    assert studio.read(d, "state.json")["title"] == NEW_TITLE and studio.title_of(d) == NEW_TITLE
    # ikinci düzeltme: özgün değer yine ilk okunan, geçmiş büyür, aynı değer kayda girmez
    studio.set_kunye(d, {}, "editör2", {"title": "Başka Ad", "author": NEW_AUTHOR})
    m = studio.read(d, "manuscript.json")
    assert m["source"]["read"]["title"] == OLD_TITLE and m["source"]["edits"]["title"]["was"] == NEW_TITLE
    assert [x["field"] for x in m["source"]["edit_log"]] == ["title", "author", "title"]
    assert m["source"]["edits"]["author"]["by"] == "editör1"


def test_empty_title_rejected_nothing_written(tmp_path, monkeypatch):
    d = _mini(tmp_path, author="Yazar")
    calls = _no_rebuild(monkeypatch)
    before = {n: (d / n).read_bytes() for n in ("manuscript.json", "front.json", "state.json")}
    for bad in ("", "   ", "\n\t"):
        with pytest.raises(ValueError, match="Kitap adı boş olamaz"):
            studio.set_kunye(d, {"Baskı": "1. Baskı"}, "e", {"title": bad})
    with pytest.raises(ValueError, match="düzenlenemeyen alan"):
        studio.set_kunye(d, {}, "e", {"isbn": "1"})
    assert not calls and before == {n: (d / n).read_bytes() for n in before}


def test_crm_match_fills_only_empty_fields(tmp_path, monkeypatch):
    """Kitap adı düzeltilince CRM'de birebir (harf büyüklüğü/boşluk farkı gözetmeden) eşleşme: boş yazar, ISBN,
    stok kodu, tanıtım dolar; dolu alan (yayınevi, elle girilen künye ISBN'i) değişmez."""
    d = _mini(tmp_path, meta={"PUBLISHER": "Kendi Yayınevi"})
    _fake_db(monkeypatch, [_crm_row(title="ışıklı  ormanın küçük ASLANI", illustrators=["Çizer Kişi"]),
                           _crm_row(title="Başka Kitap", rid="2")])
    _no_rebuild(monkeypatch)
    out = studio.set_kunye(d, {}, "editör1", {"title": NEW_TITLE})
    assert out["crm"]["match"] == "kitap adı" and out["crm"]["linked"]
    assert set(out["crm"]["filled"]) == {"author", "illustrator", "ISBN", "STOCK_CODE", "CRM_SUMMARY"}
    m = studio.read(d, "manuscript.json")
    assert m["title"] == NEW_TITLE                                   # editörün yazımı kalır, CRM yazımı değil
    assert m["author"] == "Ayşe Kayıt" and m["meta"]["ISBN"] == "9786050000009"
    assert m["meta"]["PUBLISHER"] == "Kendi Yayınevi" and m["source"]["crm_book_id"].startswith("1111")
    assert M.field_source(m["source"], "author") == {"label": "yayınevi kaydı"}
    assert M.field_source(m["source"], "title")["label"] == "editör: editör1"
    rows = _rows(studio.read(d, "front.json"))
    assert rows["Yazar"] == "Ayşe Kayıt" and rows["ISBN"] == "9786050000009"
    st = studio.read(d, "state.json")
    assert st["steps"][0]["status"] == "done" and "düzeltilince eşleşti" in st["steps"][0]["summary"]
    # künyede elle girilmiş ISBN varsa CRM'inki yazılmaz
    d2 = _mini(tmp_path / "b")
    fr = studio.read(d2, "front.json")
    studio.write(d2, "front.json", {**fr, "manual": {"ISBN": "978-0-00-000000-2"}})
    out2 = studio.set_kunye(d2, {}, "e", {"title": NEW_TITLE})
    assert "ISBN" not in out2["crm"]["filled"] and "ISBN" not in studio.read(d2, "manuscript.json")["meta"]


def test_editor_value_not_overwritten_by_crm(tmp_path, monkeypatch):
    _fake_db(monkeypatch, [_crm_row()])
    _no_rebuild(monkeypatch)
    # aynı kayıtta yazar da girildi: CRM yazarı ezmez
    d = _mini(tmp_path)
    out = studio.set_kunye(d, {}, "e", {"title": NEW_TITLE, "author": NEW_AUTHOR})
    assert "author" not in out["crm"]["filled"] and studio.read(d, "manuscript.json")["author"] == NEW_AUTHOR
    # yazar bilerek boş bırakıldı (yazarsız kitap), sonra kitap adı düzeltildi: CRM yazarı doldurmaz
    d2 = _mini(tmp_path / "b")
    out = studio.set_kunye(d2, {}, "e", {"author": ""})
    assert out["changed"] == ["author"]
    fr = studio.read(d2, "front.json")
    assert "Yazar" not in _rows(fr) and "Yazar" not in front.missing(fr["kunye"])
    studio.set_kunye(d2, {}, "e", {"title": NEW_TITLE})
    m = studio.read(d2, "manuscript.json")
    assert m["author"] is None and m["meta"]["ISBN"] == "9786050000009"            # öteki boş alan dolar
    from editor.production import api
    view = api._front(d2, m)
    yazar = next(r for r in view["rows"] if r["label"] == "Yazar")
    assert yazar["field"] == "author" and yazar["editable"] and yazar.get("none") and yazar["edited"]["by"] == "e"
    # yazar hiç bilinmiyorsa (kimse karar vermedi) künyede eksik görünür, ön kontrol durur
    d3 = _mini(tmp_path / "c")
    assert "Yazar" in front.missing(studio.read(d3, "front.json")["kunye"])


def test_other_crm_record_not_mixed(tmp_path, monkeypatch):
    """İş zaten bir CRM kaydına bağlıysa yeni ad başka kayda denk gelse de iki kayıt karışmaz."""
    d = _mini(tmp_path, author=None, source={"kind": "generation", "crm_book_id": "9", "origin": {"title": "crm"}})
    _fake_db(monkeypatch, [_crm_row(rid="10")])
    _no_rebuild(monkeypatch)
    out = studio.set_kunye(d, {}, "e", {"title": NEW_TITLE})
    m = studio.read(d, "manuscript.json")
    assert out["crm"]["filled"] == [] and not out["crm"]["linked"] and m["author"] is None
    assert m["source"]["crm_book_id"] == "9" and "ISBN" not in m["meta"]


def test_crm_unreachable_does_not_block_edit(tmp_path, monkeypatch):
    from editor import db
    d = _mini(tmp_path)

    def boom(*a):
        raise ConnectionError("yok")
    monkeypatch.setattr(db, "all_rows", boom, raising=False)
    _no_rebuild(monkeypatch)
    out = studio.set_kunye(d, {}, "e", {"title": NEW_TITLE})
    assert out["crm"]["match"] == "denenemedi" and studio.read(d, "manuscript.json")["title"] == NEW_TITLE


def test_source_labels_for_old_and_new_jobs():
    assert M.field_source({"kind": "docx"}, "title") == {"label": "Word dosyası"}
    assert M.field_source({"kind": "docx", "crm_book_id": "1"}, "author") == {"label": "yayınevi kaydı"}
    assert M.field_source({"kind": "generation", "crm_book_id": "1"}, "title") == {"label": "yayınevi kaydı"}
    assert M.field_source({"kind": "generation"}, "title") == {"label": "okunmuş kitap"}
    assert M.field_source({"kind": "docx", "origin": {"author": None}}, "author") == {}
    e = M.field_source({"edits": {"title": {"value": "A", "by": "ali", "at": 5, "was": "B"}}}, "title")
    assert e == {"label": "editör: ali", "by": "ali", "at": 5, "was": "B"}


def test_reread_keeps_editor_edits():
    ms = M.Manuscript(title=OLD_TITLE, author=None, source={"kind": "docx"})
    old = {"edits": {"title": {"value": NEW_TITLE, "by": "e", "at": 1, "was": OLD_TITLE}},
           "edit_log": [{"field": "title", "value": NEW_TITLE}]}
    M.reapply_edits(ms, old)
    assert ms.title == NEW_TITLE and ms.source["read"]["title"] == OLD_TITLE and ms.source["edit_log"]


def test_collage_labels_of_old_title_reset(tmp_path, monkeypatch):
    from editor.production import collage as K
    d = _mini(tmp_path)
    _fake_db(monkeypatch, [])
    _no_rebuild(monkeypatch)
    with K.locked(d):
        K.save(d, {**K.load(d), "labels": ["Etimesgutlu", "Bebek Aslan"]})
    studio.set_kunye(d, {}, "e", {"title": "Etimesgutlu Bebek Aslan"})           # aynı kelimeler: kalır
    assert K.load(d)["labels"] == ["Etimesgutlu", "Bebek Aslan"]
    studio.set_kunye(d, {}, "e", {"title": NEW_TITLE})                          # yeni ad: yeni addan bölünür
    assert K.load(d)["labels"] is None


def test_api_kunye_book(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from editor.production import api
    root = tmp_path / "production"
    d = _mini(root)
    monkeypatch.setattr(studio, "root", lambda: root)
    monkeypatch.setattr(api, "KEY", "k")
    _fake_db(monkeypatch, [])
    _no_rebuild(monkeypatch)
    c = TestClient(api.app)
    h = {"Authorization": "Bearer k", "X-Editor": "ayse.yilmaz"}          # başlık ASCII (AD hesabı)
    r = c.post("/v1/studio/jobs/job1/kunye", headers=h, json={"fields": {}, "book": {"title": " "}})
    assert r.status_code == 400 and "boş olamaz" in r.json()["detail"]
    r = c.post("/v1/studio/jobs/job1/kunye", headers=h,
               json={"fields": {"Baskı": "1. Baskı"}, "book": {"title": NEW_TITLE, "author": None}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["book"] == {"title": NEW_TITLE, "author": None} and body["changed"] == ["title"]
    assert body["was"] == {"title": OLD_TITLE}
    view = api._job_view(d, "job1", None)
    assert view["state"]["title"] == NEW_TITLE and view["book"]["title"] == NEW_TITLE
    kitap = next(r for r in view["front"]["rows"] if r["label"] == "Kitap")
    assert kitap["editable"] and kitap["field"] == "title" and kitap["source"] == "editör: ayse.yilmaz"
    assert kitap["edited"]["was"] == OLD_TITLE
    baski = next(r for r in view["front"]["rows"] if r["label"] == "Baskı")
    assert baski["value"] == "1. Baskı" and baski["source"] == "elle girildi" and "field" not in baski
    # eski istemci (yalnız fields) aynen çalışır
    assert c.post("/v1/studio/jobs/job1/kunye", headers=h, json={"fields": {"Telif": "© 2026"}}).status_code == 200


# ------------------------------------------------------------------ dizgiyle (editor-py imajında)
def _prof(illustrated: bool) -> Profile:
    return Profile(4, 8, "beyan", "RESIMLI_OYKU", "HER_SAYFA" if illustrated else "YOK", [], {}, {}, {})


def _job(tmp_path: Path, cover: str) -> Path:
    """Gerçek dizgiyle kurulmuş iş: kapak resimli (kapak sürümü var) ya da tipografik (resimsiz kitap)."""
    from PIL import Image

    from editor.production.art import Scene
    from editor.production.typeset import Typesetter
    d = tmp_path / "job"
    d.mkdir()
    ms = M.Manuscript(title=OLD_TITLE, author=None, meta={"PUBLISHER": "YAYINEVİ"},
                      source={"kind": "docx", "path": "/x/k.docx", "origin": {"title": "docx", "author": None}})
    ms.chapters = [M.Chapter("BÖLÜM 1", [M.Block("para", "Elif " + " ".join(["kelime"] * 30) + f" ağaç{b}.")
                                         for b in range(8)])]
    prof = _prof(cover != "typographic")
    sp = S.build(prof)
    fr = {"kunye": front.kunye(ms, {}), "kunye_fields": {}, "manual": {}, "bios": [{"name": front.MISSING,
                                                                                    "text": front.MISSING}]}
    pm = Typesetter(d / "dizgi", FONTS).fit(ms, sp, fr, "#264653")
    for name, obj in (("manuscript.json", ms.to_json()), ("profile.json", prof.to_json()), ("spec.json", sp.to_json()),
                      ("front.json", fr), ("pagemap.json", pm.to_json()),
                      ("state.json", {"title": OLD_TITLE, "status": "done", "steps": []}),
                      ("job.json", {"id": "job", "source": {}, "created_by": "t",
                                    "art_mode": "none" if cover == "typographic" else "auto"})):
        studio.write(d, name, obj)
    style = {"medium": "m", "line": "l", "lighting": "l", "mood": "m", "accent": "#264653", "style_prompt": "s",
             "palette": ["#264653", "#2A9D8F", "#E9C46A", "#F4A261", "#E76F51"], "avoid": "text", "why": "w"}
    kinds = {p.no: p.kind for p in pm.pages}
    art = sorted(pm.art_pages()) if cover != "typographic" else []
    scenes = [asdict(Scene(no, kinds[no], "m", "q", [], "s", "set", True)) for no in art]
    studio.write(d, "artplan.json", {"style": style, "characters": [], "scenes": scenes})
    (d / "resim").mkdir()
    pages = {}
    for key in [str(n) for n in art] + (["kapak"] if cover == "illustrated" else []):
        p = d / "resim" / f"{key}.v1.png"
        Image.new("RGB", (900, 1300) if key == "kapak" else (600, 400), "#88aacc").save(p)
        pages[key] = {"versions": [{"v": 1, "path": str(p), "mode": "generate", "prompt": "", "seed": 1, "by": "t",
                                    "at": 0, "dpi": 300, "base": None}], "selected": 1, "approved": True}
    studio.write(d, "studio.json", {"pages": pages, "characters": {}})
    return d


def _flat(page) -> str:
    return " ".join(page.get_text().split())


@typeset_only
@pytest.mark.parametrize("cover,planned", [("illustrated", False), ("typographic", True)])
def test_title_author_edit_rebuilds_cover_front_pages_and_typesetting(tmp_path, monkeypatch, cover, planned):
    import pymupdf

    from editor import cover_text as ct
    from editor.production import plan as P
    monkeypatch.setenv("EDITOR_FONT_DIR", str(FONTS))
    _fake_db(monkeypatch, [])
    d = _job(tmp_path, cover)
    if planned:
        P.freeze(d, "sınama")
    studio.rebuild(d)
    cover_pdf, inner = d / "kapak" / "kapak.pdf", d / "dizgi" / "ic-sayfalar.pdf"
    assert cover_pdf.exists() and inner.exists()
    assert "Yazar" in front.missing(studio.read(d, "front.json")["kunye"])        # yazar bilinmiyor: eksik
    t0 = (cover_pdf.stat().st_mtime_ns, inner.stat().st_mtime_ns, (d / "preflight.json").stat().st_mtime_ns)

    studio.set_kunye(d, {}, "editör1", {"title": NEW_TITLE, "author": NEW_AUTHOR})
    t1 = (cover_pdf.stat().st_mtime_ns, inner.stat().st_mtime_ns, (d / "preflight.json").stat().st_mtime_ns)
    assert all(b > a for a, b in zip(t0, t1))                                    # kapak, dizgi, ön kontrol yenilendi
    doc = pymupdf.open(inner)
    assert doc.metadata["title"] == NEW_TITLE and doc.metadata["author"] == NEW_AUTHOR
    ic_kapak, kunye_page = _flat(doc[0]), _flat(doc[1])
    assert NEW_TITLE in ic_kapak and NEW_AUTHOR in ic_kapak and "Etimesgutlu" not in ic_kapak
    assert NEW_TITLE in kunye_page and NEW_AUTHOR in kunye_page
    assert NEW_AUTHOR in _flat(doc[2])                                           # yazar tanıtım sayfasının adı
    text = _flat(pymupdf.open(cover_pdf)[0])
    assert (ct.tr_upper(NEW_TITLE) in text or NEW_TITLE in text) and "Etimesgutlu" not in text
    assert NEW_AUTHOR in text or ct.tr_upper(NEW_AUTHOR) in text
    rep = studio.read(d, "preflight.json")
    kunye_check = next(c for c in rep["checks"] if c["name"] == "Künye")
    assert "Yazar" not in kunye_check["detail"]                                  # yazar artık eksik değil
    assert "Yazar adı" not in {c["name"] for c in rep["checks"]}                 # sayfa planında da (kitap bilgisi)
    assert next(c for c in rep["checks"] if c["name"] == "Metin eksiksiz")["status"] == "OK"
    # yazar bilerek boş: kapakta yazar yok, künyede «Yazar» satırı yok ve eksik sayılmıyor
    studio.set_kunye(d, {}, "editör1", {"author": ""})
    text = _flat(pymupdf.open(cover_pdf)[0])
    assert NEW_AUTHOR not in text and ct.tr_upper(NEW_AUTHOR) not in text
    kp = _flat(pymupdf.open(inner)[1])
    assert NEW_AUTHOR not in kp and "Yazar" not in kp.split("Resimler")[0]
    checks = {c["name"]: c for c in studio.read(d, "preflight.json")["checks"]}
    assert "Yazar" not in checks["Künye"]["detail"]
    assert checks["Yazar adı"]["status"] == "OK" and "editörün kararı" in checks["Yazar adı"]["detail"]


@typeset_only
def test_title_that_cannot_be_typeset_is_rolled_back(tmp_path, monkeypatch):
    """Yeni ad kapağa sığmıyorsa hiçbir şey kaydedilmez, eski hâl yeniden dizilir, sebep açık hatayla döner."""
    import pymupdf
    monkeypatch.setenv("EDITOR_FONT_DIR", str(FONTS))
    _fake_db(monkeypatch, [])
    d = _job(tmp_path, "illustrated")
    studio.rebuild(d)
    before = studio.read(d, "manuscript.json")
    with pytest.raises(ValueError, match="Kaydedilmedi"):
        studio.set_kunye(d, {}, "e", {"title": "Ş" * 400})
    assert studio.read(d, "manuscript.json") == before
    assert _rows(studio.read(d, "front.json"))["Kitap"] == OLD_TITLE
    assert OLD_TITLE.split("_")[0] in _flat(pymupdf.open(d / "dizgi" / "ic-sayfalar.pdf")[0])


@typeset_only
def test_collage_cover_labels_follow_new_title(tmp_path, monkeypatch):
    import numpy as np
    import pymupdf
    from PIL import Image

    from editor.production import collage as K
    monkeypatch.setenv("EDITOR_FONT_DIR", str(FONTS))
    _fake_db(monkeypatch, [])
    d = _job(tmp_path, "illustrated")
    studio.rebuild(d)
    a = np.full((1000, 800), 205, np.uint8)
    a[700:] = 70
    buf = io.BytesIO()
    Image.fromarray(a).convert("RGB").save(buf, "PNG")
    K.add_upload(d, buf.getvalue(), "foto.png", "e")
    K.set_style(d, "collage", "e")
    studio.set_kunye(d, {}, "e", {"title": NEW_TITLE, "author": NEW_AUTHOR})
    text = _flat(pymupdf.open(d / "kapak" / "kapak.pdf")[0])
    assert all(ln in text for ln in K.view(d)["label_lines"]) and "Etimesgutlu" not in text
    assert " ".join(K.view(d)["label_lines"]).split() == NEW_TITLE.split()
    assert json.loads((d / "cover.json").read_text())["style"] == "collage"
