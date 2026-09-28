"""Sorgu bilgisi — pazar ve rakip araştırması: portal okumaları (koşan ifade) + anlık görüntüyü dolduran asıl CRM ve
Logo sorguları (origin), gerçek şema / firma kopyası / kesim günüyle yeniden kurulur; şablon metin yok.
"""
from __future__ import annotations

import json

import pytest

from semantic_bridge import pazar as PZ
from semantic_bridge import pazar_kaynak as PK
from semantic_bridge import pazar_sources as src
from semantic_bridge import provenance as P
from semantic_bridge import sorgu_izi as IZ
from semantic_layer.store.catalog_store import open_store
from semantic_layer.tests.test_pazar import _comp, _own

T = "t1"


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("PAZAR_DIR", str(tmp_path / "raporlar"))
    monkeypatch.setenv("PAZAR_CATEGORY_SOURCE", "kitaplik")
    e = open_store("sqlite://").engine
    PZ._ready.discard(id(e))
    PZ.ensure(e)
    return e


def _snapshot(engine, okuma=True):
    own_sales = {"rows": [{"yil": 2026, "boyut": "stok", "anahtar": "S1", "yayinevi": "Timaş", "ytd_adet": 10.0,
                           "ytd_ciro": 100.0, "adet": 10.0, "ciro": 100.0}],
                 "dataEnd": "2026-08-17", "missingYears": [], "years": [2025, 2026],
                 "firms": {"2025": "211", "2026": "411"}}
    PZ.apply_snapshot(engine, T, competitors=[_comp("r1", "Rakip", "Yayınevi A", 120.0, 240, "Roman")],
                      own_books=[_own("b1", "Kitap", "S1", 150.0, 300, "K-ROMAN")], links=[("b1", "r1")],
                      kitaplik=[{"id": "K-ROMAN", "ad": "Roman"}], own_sales=own_sales, actor="test",
                      okuma={"crmSchema": "Timas_MSCRM.dbo", "blurbChars": 200,
                             "crmRows": {"competitors": 1, "ownBooks": 1, "links": 1, "kitaplik": 1}} if okuma else None)


def _ok(out, ignore=()):
    k = out["kaynaklar"]
    assert not k.get("error"), k
    assert P.uncovered_numbers(out, ignore) == []
    assert P.problems(out) == []
    json.dumps(out, default=str)
    return k


def test_origin_rebuilds_the_real_crm_and_logo_sql(engine):
    _snapshot(engine)
    k = P.Kaynaklar()
    ids = PK.origin(k, engine, T, "TIGERDB", "TIMAS_MSCRM")
    assert "crm.pazar.competitors" in ids and "logo.pazar.stok.2026" in ids and "logo.pazar.kanal.2025" in ids
    s = k.sources["logo.pazar.stok.2026"]
    assert s["sql"].startswith("USE [TIGERDB];") and "LG_411_01_STLINE" in s["sql"]
    assert "'2026-08-18'" in s["sql"]  # kesim günü = veri sonunun ertesi günü
    assert "LG_211_01_STLINE" in k.sources["logo.pazar.stok.2025"]["sql"]
    assert src.competitors_sql("Timas_MSCRM.dbo", 200).strip() in k.sources["crm.pazar.competitors"]["sql"]
    assert P.placeholders_left(s["sql"]) == []


def test_overview_is_bound_with_origin(engine):
    _snapshot(engine)
    with IZ.izle(engine) as ran:
        out = PZ.overview(engine, T)
    kk = IZ.kaynak(engine, ran, out, prefix="portal.pazar.ozet", title="Pazar özeti", text=PK.F_OZET,
                   origin=lambda k: PK.origin(k, engine, T, "TIGERDB", "CRMDB"))
    k = _ok(P.ekle(out, kk))
    portal = [s for s in k["sources"].values() if s["connection"] == "portal"]
    assert portal and all(s["origin"] for s in portal)


def test_snapshot_before_this_version_says_so(engine):
    _snapshot(engine, okuma=False)
    k = P.Kaynaklar()
    ids = PK.origin(k, engine, T, None, None, logo=False)
    assert ids == ["hesap:okuma-bekliyor"] and k.formulas["okuma-bekliyor"]["external"]
