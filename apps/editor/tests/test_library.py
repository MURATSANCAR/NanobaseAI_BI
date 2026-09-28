"""Kapak arşivi (editor.production.library): besleme kaydının doğrulanması, kategori ağacı, süzme ve sayfalama.
Veritabanı yok: `_rows` yerine bellekteki kayıtlar. Çalıştır:

    pytest apps/editor/tests/test_library.py
"""

from __future__ import annotations

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

from editor.production import library as L  # noqa: E402


def _row(cid, title, cat, *, audience=None, sales=0, status="ok", authors=(), genres=()):
    r = {"id": cid, "title": title, "authors": list(authors), "illustrators": [], "isbn": None, "brand": "Timaş",
         "category": list(cat), "audience": audience, "age_from": None, "age_to": None, "genres": list(genres),
         "on_sale": True, "sales": sales, "page_url": None, "image_file": f"{cid}.jpg", "image_w": 400,
         "image_h": 600, "status": status}
    r["_q"] = L.fold(" ".join([title, *authors, *genres]))
    r["_cat"] = L.SEP.join(cat)
    return r


ROWS = [
    _row("tsoft-1", "Kaybolan Balinaların Şarkısı", ["Çocuk Kitapları", "Hikâye"], audience="CHILD", sales=50,
         authors=["Ayşe Şükrü"]),
    _row("tsoft-2", "Dilek Ağacı", ["Çocuk Kitapları", "Masal"], audience="CHILD", sales=90),
    _row("tsoft-3", "Masal Kuşu", ["Çocuk Kitapları", "Masal"], audience="CHILD", sales=10),
    _row("tsoft-4", "Sultan Abdülhamid", ["Tarih", "Osmanlı"], audience="ADULT", sales=500),
    _row("tsoft-5", "Görseli yok", ["Tarih"], status="pending"),
    _row("tsoft-6", "Kategorisiz", []),
]


def _use(monkeypatch, rows=ROWS):
    monkeypatch.setattr(L, "_rows", lambda: rows)


def test_clean_rejects_items_without_id_or_title():
    assert L.clean({"id": "tsoft-1"}) is None
    assert L.clean({"id": "kötü kimlik", "title": "A"}) is None
    assert L.clean({"id": "tsoft-1", "title": "  "}) is None


def test_clean_normalizes_paths_names_and_urls():
    r = L.clean({"id": "tsoft-42", "title": " Dilek  Ağacı ", "authors": "A, B; A", "audience": "KID",
                 "category": "Çocuk > Çocuk > Masal >  ", "image_url": "ftp://x/y.jpg", "sales": "12,0",
                 "categories": [["Çok Satanlar"], "Çocuk > Masal"]})
    assert r["title"] == "Dilek Ağacı" and r["source"] == "tsoft" and r["source_id"] == "42"
    assert r["authors"] == ["A", "B"]
    assert r["category"] == ["Çocuk", "Masal"]              # art arda tekrar ve boş parça düşer
    assert r["categories"] == [["Çok Satanlar"], ["Çocuk", "Masal"]]
    assert r["audience"] is None                              # bilinmeyen kitle alınmaz
    assert r["image_url"] is None                             # yalnız http(s)
    assert r["sales"] == 12


def test_tree_counts_only_downloaded_covers_and_orders_by_size(monkeypatch):
    _use(monkeypatch)
    t = L.tree()
    names = [c["name"] for c in t["categories"]]
    assert names == ["Çocuk Kitapları", "Tarih"]              # 3 kapak > 1 kapak (bekleyen sayılmaz)
    kids = t["categories"][0]
    assert kids["count"] == 3
    assert [(c["name"], c["count"]) for c in kids["children"]] == [("Masal", 2), ("Hikâye", 1)]
    assert kids["children"][0]["path"] == "Çocuk Kitapları > Masal"
    assert t["uncategorized"] == 1 and t["total"] == 5
    assert t["audiences"] == {"CHILD": 3, "YOUNG": 0, "ADULT": 1}


def test_tree_by_audience(monkeypatch):
    _use(monkeypatch)
    assert [c["name"] for c in L.tree("ADULT")["categories"]] == ["Tarih"]


def test_covers_filter_by_category_prefix_not_substring(monkeypatch):
    rows = ROWS + [_row("tsoft-7", "Başka", ["Çocuk Kitapları Özel"])]
    _use(monkeypatch, rows)
    got = L.covers(cat="Çocuk Kitapları")
    assert {i["id"] for i in got["items"]} == {"tsoft-1", "tsoft-2", "tsoft-3"}   # «Çocuk Kitapları Özel» değil
    assert [i["id"] for i in L.covers(cat="Çocuk Kitapları > Masal")["items"]] == ["tsoft-2", "tsoft-3"]
    assert [i["id"] for i in L.covers(cat="")["items"]] == ["tsoft-6"]           # kategorisiz


def test_covers_search_is_turkish_insensitive(monkeypatch):
    _use(monkeypatch)
    assert [i["id"] for i in L.covers(q="sukru")["items"]] == ["tsoft-1"]
    assert [i["id"] for i in L.covers(q="DILEK agac")["items"]] == ["tsoft-2"]


def test_covers_sort_and_pagination(monkeypatch):
    _use(monkeypatch)
    first = L.covers(size=2)
    assert [i["id"] for i in first["items"]] == ["tsoft-4", "tsoft-2"] and first["pages"] == 3
    last = L.covers(size=2, page=99)                        # sayfa sınırın dışındaysa son sayfa
    assert last["page"] == 3 and [i["id"] for i in last["items"]] == ["tsoft-6"]
    assert [i["id"] for i in L.covers(sort="title", size=1)["items"]] == ["tsoft-2"]


def test_image_path_rejects_bad_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "root", lambda: tmp_path)
    (tmp_path / "tsoft-1.jpg").write_bytes(b"x")
    (tmp_path / "tsoft-1.jpg.tmp").write_bytes(b"x")
    assert L.image_path("tsoft-1") == tmp_path / "tsoft-1.jpg"
    assert L.image_path("../etc") is None
    assert L.image_path("tsoft-2") is None
