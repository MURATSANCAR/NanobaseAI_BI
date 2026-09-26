"""E-kitap (editor.production.epub): sayfa planından sabit sayfa ve akışkan EPUB 3. Model ve veritabanı yok (alt metin
önerisi sahte modelle). Dizgili testler Typst ve fontlar ister (editor-py imajında koşar). Tam e-kitap denetimi
kuruluysa (EDITOR_EPUBCHECK_JAR + java) üretilen her EPUB'da hatasız olmalı. EPUB_OUT verilirse üretilen dosyalar oraya
kopyalanır (imaj dışında ayrıca denetlemek için).

    pytest apps/editor/tests/test_epub.py
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import zipfile
from pathlib import Path

import pytest

from test_plan import FONTS, _job, _mini, _png, typeset_only  # noqa: F401 - ortak iş kurulumu (stub'lar dahil)

from editor.production import epub as E  # noqa: E402
from editor.production import plan as P  # noqa: E402
from editor.production import preflight, studio  # noqa: E402

NS = {"o": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/",
      "x": "http://www.w3.org/1999/xhtml", "e": "http://www.idpf.org/2007/ops"}


class FakeLlm:
    def __init__(self, fail: bool = False):
        self.calls: list[str] = []
        self.fail = fail

    async def chat(self, alias, messages, **kw):
        self.calls.append(alias)
        if self.fail:
            raise RuntimeError("gpu_busy")
        return {"alt": "Resimde Elif kırmızı paltosuyla bahçede koşuyor."}, len(self.calls)


@pytest.fixture(autouse=True)
def _fonts(monkeypatch):
    monkeypatch.setenv("EDITOR_FONT_DIR", str(FONTS))


def _keep(path: Path, name: str) -> None:
    out = os.environ.get("EPUB_OUT")
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        shutil.copy(path, Path(out) / name)


def _opf(z: zipfile.ZipFile):
    from lxml import etree
    return etree.fromstring(z.read("OEBPS/content.opf"))


def _xhtml_text(z: zipfile.ZipFile, name: str) -> str:
    from lxml import etree
    x = etree.fromstring(z.read(name))
    return " ".join(t for t in x.find(".//x:body", NS).itertext())


def _subseq(small: list[str], big: list[str]) -> bool:
    it = iter(big)
    return all(w in it for w in small)


def _no_errors(rep: dict) -> None:
    assert not rep["errors"], json.dumps(rep["errors"][:10], ensure_ascii=False, indent=1)


# ------------------------------------------------------------------ saf
def test_isbn13_and_meta(tmp_path):
    assert E.isbn13("978-605-08-1234-6") is None                   # denetim hanesi tutmuyor
    assert E.isbn13("9786050812343") == "9786050812343"
    assert E.isbn13("0-306-40615-2") == "9780306406157"             # 10 hane → 978
    assert E.isbn13("12345") is None
    d = tmp_path / "j"
    _mini(d)
    studio.write(d, "manuscript.json", {"title": "K", "author": "Y", "illustrator": None,
                                        "meta": {"ISBN": "9780306406157"}, "source": {}, "chapters": []})
    with pytest.raises(ValueError, match="basılı"):
        E.set_meta(d, "978-0-306-40615-7", "e")
    with pytest.raises(ValueError, match="geçersiz"):
        E.set_meta(d, "9780306406158", "e")
    assert E.set_meta(d, "9786050812343", "e")["eisbn"] == "9786050812343"
    assert "eisbn" not in E.set_meta(d, "", "e")


def test_decide_is_book_independent(tmp_path):
    d = tmp_path / "j"
    plan = _mini(d, n=6)                                           # çocuk profili: HER_SAYFA → sabit
    assert E.decide(d, plan)[0] == "fixed"
    assert E.decide(d, plan, "reflow")[0] == "reflow"
    sp = studio.read(d, "spec.json")
    studio.write(d, "spec.json", {**sp, "illustration": "YOK"})
    assert E.decide(d, plan)[0] == "reflow"                        # 1/6 sayfa görselli
    for pg in plan["pages"][:3]:
        pg["art"] = pg["art"] or {"id": P.new_id("a"), "box": {"x": 0, "y": 0, "w": 10, "h": 10}, "fit": "cover",
                                  "focus": {"x": .5, "y": .5}}
    assert E.decide(d, plan)[0] == "fixed"                         # yarısı görselli
    with pytest.raises(ValueError):
        E.decide(d, None, "fixed")


def test_obfuscation_is_symmetric():
    data = bytes(range(256)) * 10
    uid = "urn:uuid:12345678-1234-5678-1234-567812345678"
    ob = E.obfuscate(data, uid)
    assert ob != data and ob[1040:] == data[1040:] and E.obfuscate(ob, uid) == data


def test_flow_docs_merges_split_block_and_notes():
    import types
    ms = types.SimpleNamespace(title="K", chapters=[types.SimpleNamespace(title="BİR")])

    def pg(blocks, art=None):
        return {"id": P.new_id("p"), "chapter": 0, "layout": "text-only", "art": art,
                "text": {"blocks": [{"id": i, "kind": k, "runs": [{"text": t}]} for i, k, t in blocks]} if blocks else None,
                "bubbles": [], "figures": [], "texts": [], "shapes": []}
    plan = {"pages": [pg([("h0", "heading", "BİR"), ("c0b0", "para", "Uzun paragrafın ilk"), ]),
                      pg([("c0b0-2", "para", "yarısı burada[1] biter."), ("c0b1", "para", "[1] Dipnot açıklaması.")]),
                      pg(None, art={"id": "a_00000001"}),
                      pg([("h1", "heading", "İKİ"), ("c1b0", "dialogue", "Merhaba!")])]}
    docs = E.flow_docs(plan, ms)
    assert [d["title"] for d in docs] == ["BİR", "İKİ"]
    assert ("img", "a_00000001", 6) in docs[1]["nodes"]           # yazısız sayfanın resmi sonraki bölümün başında
    html, pages = E.flow_html(docs[0], 1, {}, {}, {"body": "serif", "heading": "sans-serif"})
    assert pages == [4, 5]
    assert html.split("<section")[0].count("<p") == 1 and 'id="s5"' in html   # bölünen blok tek paragraf, sınır içinde
    assert 'epub:type="noteref"' in html and 'epub:type="footnote"' in html and "Dipnot açıklaması." in html
    assert "[1] Dipnot" not in html


# ------------------------------------------------------------------ dizgiyle
@typeset_only
def test_fixed_layout_epub_from_child_plan(tmp_path):
    d, ms = _job(tmp_path, child=True)
    pl = P.freeze(d, "sınama")
    pid = pl["pages"][2]["id"]
    P.add_photo(d, _png(900, 700, "#446688"), "deniz.png", pid, "e", post="none")
    pl = P.load(d)
    llm = FakeLlm()
    res = asyncio.run(E.fill_alts(d, pl, llm))
    assert res["suggested"] >= 2 and "book-director" in llm.calls and "book-vision-fast" in llm.calls
    items = E.alt_list(d, pl)
    assert items and all(i["text"] for i in items) and not any(i["text"].startswith("Resimde") for i in items)
    E.set_meta(d, "9786050812343", "e")
    out = E.build(d, "auto", "e")
    assert out["layout"] == "fixed" and out["alt_missing"] == 0
    path = d / "epub" / "kitap.epub"
    _keep(path, "sabit-sayfa.epub")
    z = zipfile.ZipFile(path)
    first = z.infolist()[0]
    assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED and not first.extra
    assert z.read("mimetype") == b"application/epub+zip"
    opf = _opf(z)
    assert opf.findtext(".//dc:language", namespaces=NS) == "tr"
    assert opf.findtext(".//dc:identifier", namespaces=NS) == "urn:isbn:9786050812343"
    assert opf.findtext(".//dc:title", namespaces=NS) == ms.title
    assert opf.findtext(".//o:meta[@property='rendition:layout']", namespaces=NS) == "pre-paginated"
    props = {m.get("property") for m in opf.findall(".//o:meta", NS)}
    assert {"schema:accessMode", "schema:accessibilityFeature", "schema:accessibilityHazard",
            "schema:accessibilitySummary", "schema:accessModeSufficient"} <= props
    feats = [m.text for m in opf.findall(".//o:meta[@property='schema:accessibilityFeature']", NS)]
    assert "alternativeText" in feats and "printPageNumbers" in feats
    assert opf.find(".//o:item[@properties='cover-image']", NS) is not None
    fonts = [i.get("href") for i in opf.findall(".//o:item", NS) if i.get("media-type") == "font/ttf"]
    assert fonts and "fonts/andika-400.ttf" in fonts
    # Sayfa yanları basılı kitaptaki gibi: tek sağda, çift solda, kapak ortada.
    spine = opf.findall(".//o:spine/o:itemref", NS)
    assert spine[0].get("properties") == "rendition:page-spread-center"
    for ref, pm in zip(spine[1:], out["pages"][1:]):
        assert ref.get("properties") == f"page-spread-{'right' if pm['no'] % 2 else 'left'}"
    assert len(spine) == 1 + P.FRONT + len(pl["pages"])
    # Her sayfa viewport'lu, metin gerçek metin (planın bütün kelimeleri sırasıyla).
    vw, vh = out["viewport"]
    words = []
    for pm in out["pages"]:
        raw = z.read("OEBPS/" + pm["href"]).decode()
        assert f'content="width={vw}, height={vh}"' in raw
        words += preflight._words(_xhtml_text(z, "OEBPS/" + pm["href"]))
    assert _subseq(preflight._words(P.PlanText(pl).text()), words)
    bubbled = [i for i in opf.findall(".//o:item", NS) if "svg" in (i.get("properties") or "")]
    assert bubbled                                                    # balon çizgisi satır içi SVG
    raw = "".join(z.read("OEBPS/" + i.get("href")).decode() for i in bubbled)
    assert "<polygon" in raw and 'class="sr"' in raw                  # konuşan sesli okumada
    assert all(re.search(r'<img [^>]*alt="[^"]+"', z.read("OEBPS/" + pm["href"]).decode())
               for pm in out["pages"] if "<img" in z.read("OEBPS/" + pm["href"]).decode())
    kun = _xhtml_text(z, "OEBPS/text/kunye.xhtml")
    assert "e-ISBN" in kun and "978-6050812343" in kun and "Matbaa" not in kun
    nav = z.read("OEBPS/nav.xhtml").decode()
    assert 'epub:type="page-list"' in nav and 'epub:type="toc"' in nav
    rep = E.check(path)
    _no_errors(rep)
    assert rep["full"] == (E.full_checker() is not None)
    # Önizleme: yalnız bu üretimin dosyaları; yol dışına çıkılamaz.
    E.set_state(d, status="done", result=out)
    data, mime = E.content(d, out["build"], out["pages"][4]["href"])
    assert mime == "application/xhtml+xml" and b"viewport" in data
    for bad in ("../job.json", "/etc/passwd", "content.opf", "text/../../x.xhtml"):
        with pytest.raises(FileNotFoundError):
            E.content(d, out["build"], bad)


@typeset_only
def test_reflowable_epub_from_novel_plan(tmp_path):
    d, ms = _job(tmp_path, child=False)
    pl = P.freeze(d, "sınama")
    asyncio.run(E.fill_alts(d, pl, FakeLlm(fail=True)))            # model yok: sahnenin «an» cümlesi, gözden geçir
    items = E.alt_list(d, pl)
    assert all(i["source"] in ("an", "kapak") for i in items) and any(i["review"] for i in items)
    out = E.build(d, "auto", "e")
    assert out["layout"] == "reflow"
    path = d / "epub" / "kitap.epub"
    _keep(path, "akiskan.epub")
    z = zipfile.ZipFile(path)
    opf = _opf(z)
    assert opf.find(".//o:meta[@property='rendition:layout']", NS) is None
    assert opf.findtext(".//dc:identifier", namespaces=NS).startswith("urn:uuid:")
    assert any("e-ISBN girilmedi" in w for w in out["warnings"])
    feats = [m.text for m in opf.findall(".//o:meta[@property='schema:accessibilityFeature']", NS)]
    assert "displayTransformability" in feats
    chapters = [p for p in out["pages"] if p["href"].startswith("text/bolum-")]
    assert [c["title"] for c in chapters] == [c.title for c in ms.chapters]
    words = []
    for c in chapters:
        words += preflight._words(_xhtml_text(z, "OEBPS/" + c["href"]))
    assert preflight._words(ms.text().replace("## ", "")) == words
    body = "".join(z.read("OEBPS/" + c["href"]).decode() for c in chapters)
    split = [k["id"] for p in pl["pages"] if p["text"] for k in p["text"]["blocks"] if k["id"].endswith("-2")]
    assert split                                                     # sınırdan bölünen blok tek paragraf olarak
    n_para = sum(1 for c in ms.chapters for _ in c.blocks)
    assert body.count("<p") == n_para
    printed = {P.FRONT + i + 1 for i, p in enumerate(pl["pages"]) if p["text"]}
    assert printed <= {int(n) for n in re.findall(r'id="s(\d+)"', body)}
    rep = E.check(path)
    _no_errors(rep)


@typeset_only
def test_build_job_preflight_line_and_stale(tmp_path):
    d, ms = _job(tmp_path, child=True)
    P.freeze(d, "sınama")
    st = asyncio.run(E.build_job(d, "auto", "e", llm=FakeLlm()))
    assert st["status"] == "done" and st["check"]["status"] in ("OK", "WARN")
    v = E.view(d)
    assert v["status"] == "done" and not v["stale"] and v["result"]["layout"] == "fixed"
    line = [c for c in studio.read(d, "preflight.json")["checks"] if c["name"] == "E-kitap"]
    assert line and "denetimden geçti" in line[0]["detail"] and "e-ISBN yok" in line[0]["detail"]
    E.set_alt(d, next(i["key"] for i in E.alt_list(d, P.load(d)) if i["key"] != "kapak"), "Elif ağacın altında.", "ed")
    assert E.view(d)["stale"]
    assert "yeniden üretin" in E.preflight_checks(d)[0]["detail"]


@typeset_only
def test_vector_layer_svg_when_elements_exist(tmp_path, monkeypatch):
    """Şekil ve efekt yazı dizginin vektör çiziminden SVG; efekt yazının gerçek metni saydam yazı olarak durur."""
    from editor.production import typeset
    tpl = tmp_path / "tpl"
    shutil.copytree(typeset.TEMPLATES, tpl)
    (tpl / "elements.typ").write_text(
        "#let draw-shape(s, palette, fonts) = rect(width: 100%, height: 100%, fill: rgb(\"#FAC775\"))\n"
        "#let effect-text(t, palette, fonts) = text(fill: rgb(\"#B0341C\"), weight: 800, "
        "t.runs.map(r => r.text).join())\n")
    monkeypatch.setattr(typeset, "TEMPLATES", tpl)
    d, ms = _job(tmp_path, child=True)
    pl = P.freeze(d, "sınama", build=False)
    pg = json.loads(json.dumps(pl["pages"][1]))
    pg["texts"] = [{"box": {"x": 20, "y": 30, "w": 90, "h": 20}, "size": 20, "runs": [{"text": "Güüüm çığlık"}],
                    "effect": {"style": "burst", "params": {}}, "z": 4}]
    pg["shapes"] = [{"kind": "star", "box": {"x": 40, "y": 60, "w": 30, "h": 30}, "z": 5, "fill": "#FAC775"}]
    monkeypatch.setattr(P, "_elements", lambda: None)                # doğrulama modülü yok (D işi)
    P.update_page(d, pg["id"], pl["rev"], pg, "e", post="none")
    out = E.build(d, "fixed", "e")
    z = zipfile.ZipFile(d / "epub" / "kitap.epub")
    svgs = [n for n in z.namelist() if n.startswith("OEBPS/images/katman-")]
    assert svgs and all(z.read(n).lstrip().startswith(b"<svg") for n in svgs)
    page = next(p for p in out["pages"] if p["no"] == P.FRONT + 2)
    raw = z.read("OEBPS/" + page["href"]).decode()
    assert "katman-" in raw and "tb ghost" in raw and "Güüüm çığlık" in raw
    _keep(d / "epub" / "kitap.epub", "katmanli.epub")
    _no_errors(E.check(d / "epub" / "kitap.epub"))


@typeset_only
def test_obfuscated_font_is_listed_and_served_clear(tmp_path, monkeypatch):
    d, ms = _job(tmp_path, child=True)
    P.freeze(d, "sınama", build=False)
    real = E.font_faces

    def faces(fams, font_dir=None):
        out = real(fams, font_dir)
        for f in out:
            f.obfuscate = True                                     # açık lisans değilmiş gibi
        return out
    monkeypatch.setattr(E, "font_faces", faces)
    out = E.build(d, "fixed", "e")
    E.set_state(d, status="done", result=out)
    path = d / "epub" / "kitap.epub"
    z = zipfile.ZipFile(path)
    enc = z.read("META-INF/encryption.xml").decode()
    name = next(n for n in z.namelist() if n.endswith(".ttf"))
    assert name in enc and "http://www.idpf.org/2008/embedding" in enc
    sp = studio._spec(d)
    orig = next(f.path for f in real([sp.body_font, sp.heading_font]) if f.name == Path(name).name).read_bytes()
    assert z.read(name) != orig
    data, mime = E.content(d, out["build"], name.removeprefix("OEBPS/"))
    assert data == orig and mime == "font/ttf"
    _keep(path, "karartilmis-font.epub")
    _no_errors(E.check(path))


def test_font_license_report():
    faces = E.font_faces(["Andika", "Baloo 2"], FONTS)
    if not faces:
        pytest.skip("fontlar yok (editor-py imajında koşar)")
    by = {f.path.name: f for f in faces}
    a = by["Andika-Regular.ttf"]
    assert a.license == "SIL OFL 1.1" and a.embed and not a.obfuscate and a.rfn
    b = by["Baloo2[wght].ttf"]
    assert b.weight.count(" ") == 1 and b.license == "SIL OFL 1.1" and b.embed


def test_api_epub_endpoints(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from editor.production import api
    root = tmp_path / "production"
    d = root / "job1"
    _mini(d)
    studio.write(d, "manuscript.json", {"title": "K", "author": "Y", "illustrator": None, "meta": {}, "source": {},
                                        "chapters": []})
    monkeypatch.setattr(studio, "root", lambda: root)
    monkeypatch.setattr(api, "KEY", "k")
    started = []

    async def start(wf, args, wid):
        started.append((wf, args))
    monkeypatch.setattr(api, "_start_plain", start)
    c = TestClient(api.app)
    h = {"Authorization": "Bearer k", "X-Editor": "sinama"}
    assert c.get("/v1/studio/jobs/job1/epub").status_code == 401
    v = c.get("/v1/studio/jobs/job1/epub", headers=h).json()
    assert v["status"] == "none" and v["auto"]["layout"] == "fixed" and v["alt"]["total"] >= 1
    r = c.put("/v1/studio/jobs/job1/epub/meta", headers=h, json={"eisbn": "123"})
    assert r.status_code == 400 and "geçersiz" in r.json()["detail"]
    assert c.put("/v1/studio/jobs/job1/epub/meta", headers=h, json={"eisbn": "9786050812343"}).json()["eisbn"]
    r = c.put("/v1/studio/jobs/job1/epub/alt/a_00000001", headers=h, json={"text": "  Elif   bahçede. "})
    assert r.status_code == 200 and r.json()["text"] == "Elif bahçede." and r.json()["source"] == "editor"
    assert c.put("/v1/studio/jobs/job1/epub/alt/../x", headers=h, json={"text": "x"}).status_code == 404
    r = c.post("/v1/studio/jobs/job1/epub", headers=h, json={"layout": "auto"})
    assert r.status_code == 200 and r.json()["status"] == "queued" and started[0][0] == "EpubBuild"
    r = c.post("/v1/studio/jobs/job1/epub", headers=h, json={"layout": "auto"})
    assert r.status_code == 409 and r.json()["code"] == "BUSY"
    assert c.get("/v1/studio/jobs/job1/epub/content/000000000000/text/kapak.xhtml", headers=h).status_code == 404
    assert c.get("/v1/studio/jobs/job1/epub/file", headers=h).status_code == 404


def test_epub_workflow_registered():
    from editor.production.flow import ACTIVITIES, WORKFLOWS
    assert "EpubBuild" in {getattr(w, "__temporal_workflow_definition").name for w in WORKFLOWS}
    assert "production_epub" in {getattr(a, "__temporal_activity_definition").name for a in ACTIVITIES}
