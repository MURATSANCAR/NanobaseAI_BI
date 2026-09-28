"""Sorgu bilgisi — sistem durumu (veri sonu SQL'i denetim kaydında), veri güvenliği ve Zeki kalite uçlarının ortak
yakalayıcıyla bağlanması (`sorgu_izi.izli`: koşan SELECT'in kendisi + hesap; genel anahtar `_hepsi`).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa

from semantic_bridge import data_security as D
from semantic_bridge import it_ops as I
from semantic_bridge import it_ops_kaynak as IK
from semantic_bridge import it_ops_sources as S
from semantic_bridge import provenance as P
from semantic_bridge import sorgu_izi as IZ
from semantic_layer.store.catalog_store import open_store

T = "t1"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    I._ready.discard(id(e))
    I.ensure(e)
    return e


def _ok(out, ignore=()):
    k = out["kaynaklar"]
    assert not k.get("error"), k
    assert P.uncovered_numbers(out, ignore) == []
    assert P.problems(out) == []
    json.dumps(out, default=str)
    return k


def test_check_stores_the_data_end_sql_and_status_shows_it(engine):
    sql = S.logo_data_end_sql("411")
    I.record_check(engine, T, "logo", True, latency_ms=120, data_end=datetime(2026, 8, 17, tzinfo=timezone.utc),
                   detail="Bağlandı.", sql_text=sql)
    I.record_check(engine, T, "crm", True, latency_ms=80, detail="Bağlandı.")
    st = I.settings(lambda k, d="": d)
    with IZ.izle(engine) as ran:
        out = I.status(engine, T, st)
    k = _ok(P.ekle(out, IK.for_status(engine, T, ran, out, "TIGERDB", "CRMDB")))
    logo = k["sources"]["logo.itops.verisonu"]
    assert logo["sql"].startswith("USE [TIGERDB];") and "LG_411_01_INVOICE" in logo["sql"]
    assert "logo.itops.verisonu" in k["formulas"]["verisonu.logo"]["inputs"]
    assert "bir sonraki denetim" in k["formulas"]["verisonu.crm"]["text"]
    assert k["fields"]["rings[]:logo"] == "hesap:verisonu.logo"


def test_check_result_carries_sql():
    r = S._res(True, "ok", ms=5, sql="SELECT 1")
    assert r["sql"] == "SELECT 1"


def test_izli_maps_every_numeric_key_and_general_key(engine):
    out = IZ.izli(engine, lambda: I.list_releases(engine, T, size=5), prefix="portal.itops.surumler", title="Kurulumlar",
                  text=IK.F_SURUM, skip=("size",))
    k = _ok(out, ("size",))
    assert k["fields"]["_hepsi"] == "hesap:portal.itops.surumler"
    assert all(s["connection"] == "portal" for s in k["sources"].values())


def test_izli_without_any_read_says_so(engine):
    out = IZ.izli(engine, lambda: {"n": 3}, prefix="x", title="x", text="x")
    assert out["kaynaklar"]["error"] and out["n"] == 3


def test_crm_users_sql_has_no_secret_columns():
    sql = D.crm_users_sql("Timas_MSCRM.dbo.")
    assert P.clean_sql(sql) and "SystemUserBase" in sql
