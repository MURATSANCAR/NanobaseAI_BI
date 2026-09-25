"""Sürüm farkı (editor.production.versions_diff): model ve veritabanı yok. Dizgili testler editor-py imajında.

    pytest apps/editor/tests/test_versions_diff.py
"""

from __future__ import annotations

import copy
import io
import json

import pytest

from test_plan import QUIET, _job, _mini, typeset_only  # noqa: F401
from editor.production import plan as P, studio, versions_diff as V  # noqa: E402


def _edit(d, i, fn):
    pl = P.load(d)
    pg = copy.deepcopy(pl["pages"][i])
    fn(pg)
    return P.update_page(d, pg["id"], pl["rev"], pg, "editör", **QUIET)


def test_word_diff_marks_inserted_and_deleted_words():
    segs = V.word_diff("Elif bahçeye koştu.", "Elif hızla bahçeye gitti.")
    assert [(s["op"], s["text"]) for s in segs] == [("eq", "Elif "), ("ins", "hızla "), ("eq", "bahçeye "),
                                                    ("del", "koştu."), ("ins", "gitti.")]
    assert "".join(s["text"] for s in segs if s["op"] != "ins") == "Elif bahçeye koştu."
    assert "".join(s["text"] for s in segs if s["op"] != "del") == "Elif hızla bahçeye gitti."


def test_match_by_id_then_content_and_places_removed_pages():
    mk = lambda pid, t: {"id": pid, "layout": "text-only", "art": None, "bubbles": [], "texts": [],  # noqa: E731
                         "text": {"blocks": [{"id": "b", "runs": [{"text": t}]}]}}
    a = [mk("p1", "bir iki üç dört"), mk("p2", "kedi köpek kuş balık"), mk("p3", "deniz dalga kum güneş")]
    b = [mk("p1", "bir iki üç dört"), mk("x9", "kedi köpek kuş balık at"), mk("p4", "tamamen başka sözler burada")]
    assert V.match(a, b) == [(0, 0), (1, 1), (2, None), (None, 2)]
    # Kimlikler bambaşka (yeniden açılmış iş): içerikle eşleşir.
    c = [mk("q1", "deniz dalga kum güneş"), mk("q2", "bir iki üç dört")]
    assert V.match(a, c) == [(2, 0), (0, 1), (1, None)]


def test_compare_history_revs(tmp_path):
    d = tmp_path / "job"
    _mini(d)                                                                     # rev 1
    _edit(d, 0, lambda pg: pg["text"]["blocks"][0]["runs"].__setitem__(0, {"text": "Elif hızla bahçeye koştu 0. "}))
    def move(pg):
        pg["text"]["box"]["x"] += 5
        pg["text"]["box"]["h"] -= 20
        pg["layout"] = "custom"
        pg["bubbles"] = [{"id": "b_1", "speaker": "Elif", "text": "Bak!", "shape": "oval",
                          "box": {"x": 20, "y": 20, "w": 40, "h": 20}, "tail": None, "color": None, "source": "editor"}]
    _edit(d, 2, move)                                                            # rev 3
    P.delete_page(d, P.load(d)["pages"][4]["id"], P.load(d)["rev"], "editör", **QUIET)   # rev 4
    diff = V.compare(V.resolve(d, f"{d.name}:1"), V.resolve(d, f"{d.name}:current"), d)
    st = [p["status"] for p in diff["pages"]]
    assert st == ["changed", "same", "changed", "same", "removed"]
    assert diff["counts"] == {"changed": 2, "added": 0, "removed": 1, "same": 2}
    assert diff["words"] == {"ins": 2, "del": 6}                  # «hızla» + balon «Bak!»; silinen sayfanın 6 kelimesi
    p0 = diff["pages"][0]
    assert p0["match"] == "id" and p0["text"][0]["label"] == "Sayfa metni"
    assert {"op": "ins", "text": "hızla "} in p0["text"][0]["segments"]
    lay = [c["text"] for c in diff["pages"][2]["layout"]]
    assert any("Yazı kutusu: taşındı (5,0 mm sağa)" == t for t in lay)
    assert any(t.startswith("Yazı kutusu: boyutu değişti") for t in lay)
    assert any(t.startswith("Balon «Bak!» eklendi") for t in lay) and any(t.startswith("Yerleşim:") for t in lay)
    assert diff["pages"][2]["text"][0]["label"] == "Balon (Elif)"
    assert "İç sayfa sayısı: 5 → 4" in diff["global"]
    assert V.unchanged_ranges(diff["pages"]) == [(5, 5), (7, 7)]


def test_order_change_is_reported(tmp_path):
    d = tmp_path / "job"
    pl = _mini(d)
    ids = [p["id"] for p in pl["pages"]]
    P.order(d, pl["rev"], [ids[1], ids[0]] + ids[2:], "e", **QUIET)
    diff = V.compare(V.resolve(d, f"{d.name}:1"), V.resolve(d, f"{d.name}:current"), d)
    moved = [p for p in diff["pages"] if any(c["kind"] == "order" for c in p["layout"])]
    assert len(moved) == 1 and moved[0]["a"]["no"] == 4 and moved[0]["b"]["no"] == 5


def test_versions_across_jobs_of_same_book(tmp_path, monkeypatch):
    root = tmp_path / "production"
    monkeypatch.setattr(studio, "root", lambda: root)
    for j, book in (("20260925000000aaaaaa", "k1"), ("20260925000001bbbbbb", "k1"), ("20260925000002cccccc", "k2")):
        _mini(root / j)
        studio.write(root / j, "job.json", {"id": j, "source": {"book_id": book}, "created_by": "e", "created_at": 1})
    a, b, c = (root / j for j in sorted(p.name for p in root.iterdir()))
    got = V.versions(a)
    assert {j["id"] for j in got["jobs"]} == {a.name, b.name} and [j["self"] for j in got["jobs"] if j["id"] == a.name] == [True]
    assert got["jobs"][0]["revs"][0]["rev"] == 1
    v = V.resolve(a, f"{b.name}:current")
    assert v.d == b and v.current
    with pytest.raises(KeyError):
        V.resolve(a, f"{c.name}:current")                                         # başka kitap
    with pytest.raises(KeyError):
        V.resolve(a, f"{a.name}:99")
    # Yeniden açılmış işte kimlikler başka: içerikle eşleşir, metin aynıysa değişmedi sayılır.
    pl = P.load(b)
    for i, pg in enumerate(pl["pages"]):
        pg["id"] = f"p_new{i:04d}"
    studio.write(b, P.PLAN, pl)
    diff = V.compare(V.resolve(a, f"{a.name}:current"), V.resolve(a, f"{b.name}:current"), a)
    assert all(p["match"] == "content" and p["status"] == "same" for p in diff["pages"])


def test_condense_keeps_context_around_changes():
    long = " ".join(f"k{i}" for i in range(40))
    segs = V.word_diff(long + " son.", long + " yeni son.")
    c = V.condense(segs, keep=5)
    assert c[0]["text"].startswith("… ") and len(c[0]["text"].split()) == 6
    assert c[1] == {"op": "ins", "text": "yeni "} and c[2] == {"op": "eq", "text": "son."}


def test_changed_regions_find_the_changed_box(tmp_path):
    from PIL import Image, ImageDraw
    a = Image.new("RGB", (400, 560), "white")
    b = a.copy()
    ImageDraw.Draw(b).rectangle((100, 200, 199, 259), fill="black")
    a.save(tmp_path / "a.png")
    b.save(tmp_path / "b.png")
    out = V.changed_regions(tmp_path / "a.png", tmp_path / "b.png")
    assert len(out["regions"]) == 1
    r = out["regions"][0]
    assert abs(r["x"] - 0.25) < 0.03 and abs(r["y"] - 200 / 560) < 0.03 and abs(r["w"] - 0.25) < 0.04
    assert V.changed_regions(tmp_path / "a.png", tmp_path / "a.png")["regions"] == []


@typeset_only
def test_old_revision_renders_and_report_pdf(tmp_path):
    import pymupdf
    d, _ms = _job(tmp_path, child=True)
    pl = P.freeze(d, "sınama")
    pid = next(p["id"] for p in pl["pages"] if p["text"] and p["text"]["blocks"])
    def edit(pg):
        pg["text"]["blocks"][0]["runs"] = [{"text": "Tamamen yeni bir cümle geldi."}] + pg["text"]["blocks"][0]["runs"][1:]
        pg["text"]["box"]["y"] += 12
    pl2 = P.load(d)
    pg = copy.deepcopy(next(p for p in pl2["pages"] if p["id"] == pid))
    edit(pg)
    P.update_page(d, pid, pl2["rev"], pg, "editör", post="none")
    va, vb = V.resolve(d, f"{d.name}:1"), V.resolve(d, f"{d.name}:current")
    old = V.version_pdf(va)
    assert old.parent.name == "r1" and pymupdf.open(old).page_count == P.FRONT + len(pl["pages"])
    vis = V.visual(va, vb, pid, pid)
    assert vis["regions"] and 0 < vis["share"] < 0.6
    same = next(p["id"] for p in pl["pages"] if p["id"] != pid and p["text"] and p["text"]["blocks"])
    assert V.visual(va, vb, same, same)["regions"] == []
    pdf = V.report(d, va, vb, "editör")
    doc = pymupdf.open(pdf)
    flat = " ".join(" ".join(p.get_text() for p in doc).split())
    assert "DEĞİŞİKLİK RAPORU" in flat and "Tamamen yeni bir cümle geldi." in flat
    assert "Değişmeyen sayfalar" in flat and len(doc[0].get_images()) + sum(len(p.get_images()) for p in doc[1:]) >= 2
    assert V.report(d, va, vb, "editör") == pdf                                     # aynı iki sürüm: bir kez
