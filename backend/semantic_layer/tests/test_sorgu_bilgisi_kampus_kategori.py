"""Sorgu bilgisi — Kampüs (rehber CRM okuması + AD) ve Kategori ağacı (portal okumaları + gece eşitlemesinin CRM/Logo
sorguları köken olarak, kaydedilen şema / firma / pencereyle yeniden kurulur).
"""
from __future__ import annotations

from datetime import date

import pytest

from semantic_bridge import categories as C
from semantic_bridge import categories_kaynak as CK
from semantic_bridge import categories_sources as CS
from semantic_bridge import kampus_kaynak as KK
from semantic_bridge import people as PE
from semantic_bridge import provenance as P
from semantic_bridge import sorgu_izi as IZ
from semantic_layer.store.catalog_store import open_store

T = "t1"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    C._ready.discard(id(e))
    C.ensure(e)
    return e


def test_people_sources_prefer_the_executed_text():
    k = P.Kaynaklar()
    ids = KK.people_sources(k, "Timas_MSCRM.dbo", "CRMDB", {}, 130, 1790000000.0)
    s = k.sources["crm.rehber"]
    assert s["sql"].startswith("USE [CRMDB];") and PE.directory_sql("Timas_MSCRM.dbo").split("\n")[0] in s["sql"]
    assert "hesap:ad" in ids and k.formulas["ad"]["external"]
    k2 = P.Kaynaklar()
    KK.people_sources(k2, "Timas_MSCRM.dbo", None, {"sql": "SELECT 1 AS x FROM Timas_MSCRM.dbo.SystemUserBase", "rows": 7},
                      130, None)
    assert "SELECT 1 AS x" in k2.sources["crm.rehber"]["sql"] and k2.sources["crm.rehber"]["stats"]["rows"] == 7


def test_category_origin_rebuilds_crm_and_logo_sql(engine):
    C.meta_set(engine, T, "sync", {
        "at": "2026-09-28T03:10:00+00:00",
        "crm": {"books": 5200, "ms": 9000, "schema": "Timas_MSCRM.dbo"},
        "logo": {"start": "2025-09-17", "end": "2026-08-17", "months": 24, "years": [2025, 2026],
                 "firms": {"2025": "211", "2026": "411"}}})
    k = P.Kaynaklar()
    ids = CK.origin(k, engine, T, "TIGERDB", "CRMDB")
    assert "crm.kategori.kitaplar" in ids and "logo.kategori.oncelik.2025" in ids
    s25 = k.sources["logo.kategori.oncelik.2025"]["sql"]
    assert "LG_211_01_STLINE" in s25 and "'2025-09-17'" in s25 and "'2026-01-01'" in s25
    s26 = k.sources["logo.kategori.oncelik.2026"]["sql"]
    assert "LG_411_01_STLINE" in s26 and "'2026-08-18'" in s26
    assert CS.priority_sql("411", date(2026, 1, 1), date(2026, 8, 18)).split("\n")[-1] in s26


def test_category_overview_bound_or_waits_for_next_sync(engine):
    with IZ.izle(engine) as ran:
        out = C.overview(engine, T, None)
    kk = IZ.kaynak(engine, ran, out, prefix="portal.kategori.ozet", title="Özet", text=CK.F_OZET,
                   origin=lambda k: CK.origin(k, engine, T, None, None))
    out = P.ekle(out, kk)
    assert P.uncovered_numbers(out) == [] and P.problems(out) == []
    assert "esitleme-bekliyor" in out["kaynaklar"]["formulas"]
