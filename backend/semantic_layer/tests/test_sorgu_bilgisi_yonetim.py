"""Sorgu bilgisi — yönetim ekranı (genel durum, kişiler, soru izleme, yetkiler, veri alanları, sesli bülten) ve
veri sözlüğü / onaylar / eş anlamlılar; ortak yakalayıcı `sorgu_izi` (koşan SELECT ifadesinin kendisi kaydedilir).
"""
from __future__ import annotations

import json

import pytest
import sqlalchemy as sa

from semantic_bridge import access as AC
from semantic_bridge import admin as AD
from semantic_bridge import admin_kaynak as ADK
from semantic_bridge import alerts as A
from semantic_bridge import board as B
from semantic_bridge import bulletins as BU
from semantic_bridge import provenance as P
from semantic_bridge import reports as R
from semantic_bridge import sorgu_izi as IZ
from semantic_bridge import sozluk_kaynak as SZK
from semantic_layer.store.catalog_store import open_store

T, D = "t1", "logo"


@pytest.fixture
def store():
    st = open_store("sqlite://")
    e = st.engine
    for mod in (A, B, R, AD, BU):
        getattr(mod, "_ready", set()).discard(id(e))
    A.ensure(e)
    B.ensure(e)
    R.ensure(e)
    AD.ensure(e)
    return st


def _ok(out, ignore=()):
    k = out["kaynaklar"]
    assert not k.get("error"), k
    assert P.uncovered_numbers(out, ignore) == []
    assert P.problems(out) == []
    json.dumps(out, default=str)
    return k


def test_capture_records_the_executed_select_only(store):
    e = store.engine
    with IZ.izle(e) as ran:
        with e.connect() as c:
            c.execute(sa.select(A.RULES.c.id).where(A.RULES.c.tenant_id == "t1")).all()
        with e.begin() as c:
            c.execute(A.RULES.delete().where(A.RULES.c.tenant_id == "yok"))
    assert len(ran) == 1
    k = P.Kaynaklar()
    ids = IZ.kaydet(k, ran + ran, e, "x", "Deneme")
    assert ids == ["x.1"] and "'t1'" in k.sources["x.1"]["sql"]
    with e.connect() as c:  # izlemenin dışında kayıt yok
        c.execute(sa.select(A.RULES.c.id)).all()
    assert len(ran) == 1


def test_overview_counts_have_sources(store, monkeypatch):
    e = store.engine
    monkeypatch.setattr(AD, "admins", lambda: ["murat"])
    reports, alerts, cards, people = (AD.all_reports(e, T, D), A.list_rules(e, T, D), AD.all_cards(e, T, D),
                                      AD.users(e, T, D))
    out = {"counts": {"reports": len(reports), "reportsActive": 0, "reportsFailed": 0, "alerts": len(alerts),
                      "alertsActive": 0, "alertsTriggered": 0, "cards": len(cards), "cardsFailed": 0,
                      "users": len(people), "admins": 1},
           "engine": {"model": "x", "llm": True, "db": True, "catalog": store.status_counts(T, D), "profiles": 3},
           "services": [], "timers": [], "recent": [{"id": 5, "detail": {"rows": 3}}]}
    k = _ok(P.ekle(out, ADK.for_overview(e, store, T, D, out)), ADK.OVERVIEW_NOT_RAKAM)
    assert "semantic_reports" in k["sources"]["portal.yonetim.raporlar"]["sql"]
    assert k["formulas"]["yoneticiler"].get("external")


def test_users_and_prompt_screens(store):
    e = store.engine
    out = {"items": AD.users(e, T, D)}
    _ok(P.ekle(out, ADK.for_users(e, T, D)))
    store.log_query(T, D, "bu ay ciro", sql="SELECT 1", compiler="c", catalog_version=3, resolved={}, executed=True,
                    row_count=1, latency_ms=900,
                    result_json={"columns": [{"name": "n"}], "records": [{"n": 1}], "totalRows": 1,
                                 "physicalSql": "SELECT 1 AS n FROM [dbo].[LG_411_01_INVOICE]", "dbMs": 40})
    stmts = store.query_log_overview_stmts(T, D, since_days=30)
    ov = store.query_log_overview(T, D, since_days=30, stmts=stmts)
    k = _ok(P.ekle(dict(ov), ADK.for_prompt_overview(e, stmts, ov)), ("sinceDays", "byType", "byCompiler", "topFailing",
                                                                        "unresolvedTerms"))
    assert "sl_query_log" in k["sources"]["portal.soru.toplam"]["sql"]
    ran: list = []
    lst = store.list_query_log(T, D, stmt_out=ran)
    _ok(P.ekle(lst, ADK.for_prompt_list(e, ran[0], lst)), ADK.PROMPT_NOT_RAKAM)
    qid = lst["items"][0]["id"]
    ran = []
    row = store.get_query_log(T, D, qid, stmt_out=ran)
    k = _ok(P.ekle(row, ADK.for_prompt(e, ran[0], row, "TIGERDB", None)), ADK.PROMPT_NOT_RAKAM)
    assert k["sources"]["soru.kosu"]["sql"].startswith("USE [TIGERDB];")


def test_roles_entities_and_bulletins(store):
    e = store.engine
    AC.ensure(e, T)
    out = {"items": AC.list_roles(e, T)}
    k = _ok(P.ekle(out, ADK.for_roles(e, T, None, None)))
    assert "semantic_access" in json.dumps(k["sources"])
    ent = {"items": [{"entity": "FATURA", "rows": 10, "tables": 2}], "counts": {"satis": 1}, "domains": []}
    _ok(P.ekle(ent, ADK.for_entities(e, T, D, ent)))
    BU.ensure(e)
    bl = {"items": BU.listing(e, T, published_only=False), "maxMb": 50}
    _ok(P.ekle(bl, ADK.for_bulletins(e, T, bl)))
    jobs = {"items": [{"id": "j1", "chars": 1200}]}
    _ok(P.ekle(jobs, ADK.for_jobs(e, T, jobs)))


def test_dictionary_screen_uses_captured_reads(store):
    e = store.engine
    with IZ.izle(e) as ran:
        concepts = store.find_concepts(T, D, status="CERTIFIED", limit=10)
    out = {"items": [{"concept": {"id": c.id, "confidence": c.confidence}} for c in concepts], "n": len(concepts)}
    k = _ok(P.ekle(out, SZK.for_catalog(e, D, ran, out, title="Katalog terimleri", text=SZK.F_TERIM)))
    assert "sl_concept" in json.dumps(k["sources"])
    with pytest.raises(P.ProvenanceError):
        SZK.for_catalog(e, D, [], {"n": 1}, title="x", text="x")
