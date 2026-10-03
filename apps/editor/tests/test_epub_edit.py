"""E-kitap düzenleme katmanı (editor.production.epub_edit): paragraf stili, bölüm adı/bölme/katma, ön sayfalar,
basılıdan eklenen metin; e-kitaba uygulanması. Dizgili test Typst ve fontlar ister (editor-py imajında koşar)."""

from __future__ import annotations

import zipfile

import pytest

from test_plan import FONTS, _job, typeset_only  # noqa: F401 - ortak iş kurulumu

from editor.production import epub as E  # noqa: E402
from editor.production import epub_edit as X  # noqa: E402
from editor.production import plan as P  # noqa: E402


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("EDITOR_FONT_DIR", str(FONTS))
    monkeypatch.setenv("EPUB_HOUSE_DIR", str(tmp_path / "sablon"))
    monkeypatch.delenv("EPUB_HOUSE", raising=False)


def _p(bid, text, kind="para"):
    return ("p", kind, [("runs", [{"text": text}], bid)])


DOCS = [{"title": "BİR", "nodes": [("h", "BİR", "h0", [{"text": "BİR"}]), _p("a", "Hayat bir yolculuktur."),
                                   _p("b", "İlk paragraf."), _p("c", "İkinci paragraf."), _p("d", "Üçüncü paragraf.")]},
        {"title": "İKİ", "nodes": [("h", "İKİ", "h1", [{"text": "İKİ"}]), _p("e", "Dördüncü paragraf.")]}]


def test_apply_styles_splits_merges_titles_and_extras():
    e = X.empty()
    e["styles"] = {"a": {"style": "e-epi", "h": X.digest("Hayat bir yolculuktur.")},
                   "b": {"style": "gizle", "h": X.digest("İlk paragraf.")},
                   "e": {"style": "e-siir", "h": X.digest("eski metin")}}            # metin değişmiş: uygulanmaz
    e["splits"] = {"c": {"title": "Ara Bölüm", "h": X.digest("İkinci paragraf.")}}
    e["titles"] = {"h0": "Birinci Bölüm"}
    e["merges"] = ["h1"]
    e["extras"] = [{"id": "ek-206-208", "title": "Yazarın Notu", "pages": [206, 208], "paras": ["Not bir.", "Not iki."]}]
    warn: list[str] = []
    docs, styles = X.apply(DOCS, e, warn)
    assert [d["title"] for d in docs] == ["Birinci Bölüm", "Ara Bölüm", "Yazarın Notu"]
    assert styles["a"] == "e-epi" and styles["b"] == "gizle" and "e" not in styles
    assert styles["h1"] == "e-2-baslik"                                            # katılan bölümün başlığı ara başlık
    assert [X.node_id(n) for n in docs[1]["nodes"]] == ["c-baslik", "c", "d", "h1", "e"]
    assert docs[0]["nodes"][0][1] == "Birinci Bölüm"
    assert any("değişen 1 paragraf" in w for w in warn)
    html, _ = E.flow_html(docs[0], 1, {}, {}, {"body": "serif", "heading": "sans-serif"},
                          notebook=E.NoteBook("notlar.xhtml"), href="bolum-001.xhtml", styles=styles)
    assert '<p class="e-epi">Hayat bir yolculuktur.</p>' in html and "İlk paragraf" not in html
    assert "Birinci Bölüm" in html


def test_added_text_drops_repeated_title_and_publisher_promo():
    paras = ["YAZARIN NOTU", "Bu hikâye bir öyküydü.", "Teşekkürler.", "Aynı karekod ile her hafta başka bir kitap",
             "Kitap önerimiz"]
    assert X._clean(paras, "Yazarın Notu") == ["Bu hikâye bir öyküydü.", "Teşekkürler."]


def test_added_text_skips_paragraphs_already_in_epub(tmp_path, monkeypatch):
    """Aynı basılı sayfada e-kitaba girmiş metin (yazar tanıtımı) ve onun ad satırı yeniden eklenmez; çevirmenin adı
    başlığın içinde geçtiği için düşer."""
    from editor.production import epub_compare
    d = tmp_path / "j"
    (d / "epub").mkdir(parents=True)
    (d / "epub" / "kitap.epub").write_bytes(b"x")
    author = "Minyoung Kang sinema dergisi CAST'ın genel yayın yönetmeni ve yazardır, Güney Kore'de yaşamaktadır."
    monkeypatch.setattr(epub_compare, "epub_text", lambda p: "Yazar hakkında " + author)
    page = ["MİNYOUNG KANG", author, "SELEN DEMİRTAŞ",
            "2000 yılında İstanbul'da doğdu ve Ankara Üniversitesi Kore Dili ve Edebiyatı Bölümü'nden mezun oldu."]
    got = X._clean(X._not_in_epub(d, page), "Çeviren: Selen Demirtaş")
    assert got == [page[3]]


def test_split_on_changed_text_is_not_applied():
    e = X.empty()
    e["splits"] = {"c": {"title": "Ara", "h": "0000000000"}}
    warn: list[str] = []
    chs = X.chapters(DOCS, e, warn)
    assert len(chs) == 2 and warn


@typeset_only
def test_change_then_build_applies_edits(tmp_path):
    d, ms = _job(tmp_path, child=False)
    P.freeze(d, "sınama")
    st = X.structure(d)
    assert st["house"] and st["rev"] == 0 and st["chapters"]
    ch = st["chapters"][0]
    blk = ch["blocks"][1]
    st = X.change(d, 0, [{"op": "style", "block": blk["id"], "style": "e-epi"},
                         {"op": "title", "chapter": ch["key"], "title": "Yeni Ad"},
                         {"op": "front", "key": "imza", "on": False},
                         {"op": "add_missing", "pages": [9, 9], "title": "Yazarın Notu"},
                         {"op": "add_missing", "pages": [3, 3], "title": "Çeviren", "place": "front"}],
                  "editör", source=lambda d_, a, b: ["Basılı kitaptan gelen not."])
    assert st["rev"] == 1 and st["chapters"][0]["title"] == "Yeni Ad" and st["extras"][0]["title"] == "Yazarın Notu"
    assert next(f for f in st["fronts"] if f["key"] == "imza")["on"] is False
    with pytest.raises(X.Conflict):
        X.change(d, 0, [{"op": "reset"}], "editör")
    out = E.build(d, "reflow", "e")
    z = zipfile.ZipFile(d / "epub" / "kitap.epub")
    names = z.namelist()
    assert "e-iyikikitaplarvar" not in z.read("OEBPS/text/kunye.xhtml").decode()
    assert "Çeviren" in z.read("OEBPS/text/yazar.xhtml").decode()                       # ön sayfaya eklenen tanıtım
    body = "".join(z.read("OEBPS/" + p["href"]).decode() for p in out["pages"] if p["href"].startswith("text/bolum-"))
    assert 'class="e-epi"' in body and "Yeni Ad" in body and "Basılı kitaptan gelen not." in body
    assert [p["title"] for p in out["pages"]][-1] == "Yazarın Notu"
    E.set_state(d, status="done", result=out, inputs=E.inputs_hash(d))
    X.change(d, 1, [{"op": "front", "key": "imza", "on": True}], "editör")
    assert E.view(d)["stale"]                                                      # düzen değişince e-kitap «eski»
