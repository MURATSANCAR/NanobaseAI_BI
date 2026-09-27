"""Yetki Aşama C: ZEKİ AI'ın okuyabileceği veri, role bağlı veri alanlarıyla sınırlı.

Sözleşme: kataloğun her varlığı bir alana düşer (kural, ya da yöneticinin ataması); kişi yalnız rolündeki
alanların varlıklarını okuyan SQL'i çalıştırabilir; kapsam dışı soru net bir ret alır; ortak başvuru tabloları
herkese açık; yönetici ve sistem işi sınırsız; zamanlı iş sahibinin kapsamıyla koşar.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from semantic_bridge import access as A
from semantic_layer.candidates.llm_client import FakeLlm
from semantic_layer.runtime.guardrails import entities_read
from semantic_layer.tests.conftest import TENANT

CTX = {"n0": "411", "n1": "01"}


def test_rules_put_known_families_in_their_domain():
    d = A.rule_domain
    assert d("INVOICE", "logo") == "satis" and d("STLINE", "logo") == "satis" and d("LG_ORFLINE", "logo") == "satis"
    assert d("CLCARD", "logo") == "cari" and d("LG_CLFLINE", "logo") == "cari" and d("PAYTRANS", "logo") == "cari"
    assert d("EMFLINE", "logo") == "muhasebe" and d("ITEMS", "logo") == "stok" and d("LG_KSLINES", "logo") == "banka-kasa"
    assert d("L_CAPIUSER", "logo") == "sistem" and d("LG_EXCHANGE", "logo") == "ortak"
    assert d("NEW_SOZLESMEBASE", "crm") == "telif-sozlesme" and d("NEW_KITAPBASE", "crm") == "yayin-crm"
    assert d("NEW_SIPARISBASE", "crm") == "satis" and d("ACCOUNTBASE", "crm") == "cari"
    assert d("BILINMEYEN_TABLO", "logo") == "atanmamis"


def test_data_keys_join_the_catalog_but_the_common_domain_is_always_open():
    keys = A.all_keys()
    assert "veri:satis" in keys and "veri:atanmamis" in keys and "veri:ortak" not in keys
    assert "ortak" in A.always_domains()


def test_entities_read_matches_the_table_check(profiles):
    sql = ('SELECT c."CITY", SUM(i."NETTOTAL") FROM dbo_LG_411_01_INVOICE i '
           'JOIN dbo_LG_411_CLCARD c ON c."LOGICALREF" = i."CLIENTREF" GROUP BY c."CITY"')
    assert entities_read(sql, profiles, CTX, "tsql") == {"INVOICE", "CLCARD"}
    assert entities_read("SELEC nonsense (", profiles, CTX, "tsql") is None


@pytest.fixture
def runtime(store, profiles, logo_connector, settings):
    from semantic_bridge.app import Runtime

    for p in profiles:
        store.upsert_profile(p)
    A._ready.clear()
    A.invalidate()
    A._ent_cache["key"] = None
    return Runtime(settings, store=store, connector=logo_connector, llm=FakeLlm([""]))


def test_sql_gate_refuses_out_of_scope_entities(runtime):
    sql = 'SELECT SUM("NETTOTAL") AS t FROM dbo_LG_411_01_INVOICE WHERE "CANCELLED" = 0'
    assert runtime.run_sql(sql, 10)["records"]                       # bağlam yok: sınır yok
    token = A.DATA_ALLOWED.set(frozenset({"cari", "ortak"}))
    try:
        with pytest.raises(A.DataScopeError) as e:
            runtime.run_sql(sql, 10)
        assert "Satış ve sipariş" in str(e.value)
        runtime.run_sql('SELECT COUNT(*) AS n FROM dbo_LG_411_CLCARD', 10)   # cari rolde: çalışır
        # yöneticinin ataması kuralın önüne geçer
        A.set_entity_domain(runtime.store.engine, TENANT, "zekiai", "INVOICE", "cari")
        assert runtime.run_sql(sql, 10)["records"]
        A.set_entity_domain(runtime.store.engine, TENANT, "zekiai", "INVOICE", None)
        with pytest.raises(A.DataScopeError):
            runtime.run_complete(sql)
    finally:
        A.DATA_ALLOWED.reset(token)


def test_listing_shows_where_each_domain_came_from(runtime):
    A.set_entity_domain(runtime.store.engine, TENANT, "zekiai", "ITEMS", "satis")
    rows = {r["entity"].upper(): r for r in A.domain_listing(runtime.store.engine, TENANT, runtime.profiles)}
    assert rows["ITEMS"]["domain"] == "satis" and rows["ITEMS"]["manual"] is True
    assert rows["INVOICE"]["domain"] == "satis" and rows["INVOICE"]["manual"] is False
    with pytest.raises(A.AccessError):
        A.set_entity_domain(runtime.store.engine, TENANT, "zekiai", "ITEMS", "yok-boyle")


def _client(monkeypatch, runtime):
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod
    from semantic_bridge.app import create_app

    users = {"timas_session=a": "ayse", "timas_session=z": "zekiai"}
    monkeypatch.setattr(board_mod, "_fetch_user", lambda cookie: users.get(cookie))
    monkeypatch.setattr(board_mod, "_fetch_session", lambda cookie: {"username": users.get(cookie), "displayName": "x"})
    monkeypatch.setattr(admin_mod, "admins", lambda: ["zekiai"])
    monkeypatch.delenv("SEMANTIC_CALLER_TOKEN", raising=False)
    monkeypatch.delenv("SEMANTIC_ADMIN_TOKEN", raising=False)
    return TestClient(create_app(runtime))


def test_bridge_scopes_each_person(monkeypatch, runtime):
    client = _client(monkeypatch, runtime)
    engine = runtime.store.engine
    A.ensure(engine, TENANT)
    sql = {"sql": 'SELECT SUM("NETTOTAL") AS t FROM dbo_LG_411_01_INVOICE WHERE "CANCELLED" = 0'}
    a, z = {"cookie": "timas_session=a"}, {"cookie": "timas_session=z"}
    # Kurulumda Herkes bütün alanları taşır: davranış değişmez.
    assert client.post("/api/v1/run_sql", json=sql, headers=a).status_code == 200
    everyone = next(r for r in A.list_roles(engine, TENANT) if r["system"])
    A.save_role(engine, TENANT, "zekiai", {"name": "x", "allPerms": False,
                                           "perms": ["sayfa:genel-bakis", "ozellik:zeki.soru", "veri:cari"]}, everyone["id"])
    A.invalidate()
    denied = client.post("/api/v1/run_sql", json=sql, headers=a)
    assert denied.status_code == 403 and "Satış ve sipariş" in denied.json()["detail"]["message"]
    assert client.post("/api/v1/run_sql", json={"sql": 'SELECT COUNT(*) AS n FROM dbo_LG_411_CLCARD'}, headers=a).status_code == 200
    assert client.post("/api/v1/run_sql", json=sql, headers=z).status_code == 200      # yönetici sınırsız
    assert client.post("/api/v1/run_sql", json=sql).status_code == 200                 # çerezsiz sistem işi
    ex = client.get("/api/v1/access/explain?user=ayse", headers=z).json()
    by = {d["id"]: d["allowed"] for d in ex["data"]}
    assert by["cari"] and by["ortak"] and not by["satis"]


def test_scheduled_work_runs_with_the_owners_scope(runtime):
    engine = runtime.store.engine
    A.ensure(engine, TENANT)
    A.bind(lambda: engine, lambda: TENANT, lambda u: u == "zekiai")
    try:
        everyone = next(r for r in A.list_roles(engine, TENANT) if r["system"])
        A.save_role(engine, TENANT, "zekiai", {"name": "x", "allPerms": False, "perms": ["veri:cari"]}, everyone["id"])
        A.invalidate()
        sql = 'SELECT SUM("NETTOTAL") AS t FROM dbo_LG_411_01_INVOICE WHERE "CANCELLED" = 0'
        with A.acting_as("ayse"):
            with pytest.raises(A.DataScopeError):
                runtime.run_sql(sql, 10)
        with A.acting_as("zekiai"):
            assert runtime.run_sql(sql, 10)["records"]
        assert A.DATA_ALLOWED.get() is None                        # bağlam geri döndü
    finally:
        A._bound.clear()
