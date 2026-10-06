"""CRM seçenek adları: StringMap'ten gelen ad yazılı sözlüğü ezer, yeni kod eklenir, okunamazsa sözlük kalır."""
from __future__ import annotations

import pytest

from semantic_bridge import crm_labels as L


@pytest.fixture
def crm(monkeypatch):
    rows = [
        {"ENT": "new_siparis", "ATTR": "statuscode", "CODE": 100000001, "LABEL": "İptal Edildi"},
        {"ENT": "new_siparis", "ATTR": "statuscode", "CODE": 862440000, "LABEL": "Dağılım"},
        {"ENT": "new_etkinlik", "ATTR": "new_ziyarettipi", "CODE": 3, "LABEL": "Üniversiteler"},
        {"ENT": "new_etkinlik", "ATTR": "new_ziyarettipi", "CODE": 4, "LABEL": "Cari Ziyareti"},
        {"ENT": "new_etkinlik", "ATTR": "new_ziyarettipi", "CODE": 5, "LABEL": "  "},
    ]
    calls = []

    def read():
        calls.append(1)
        return L.parse(rows)

    monkeypatch.setenv("CRM_LABELS", "1")
    monkeypatch.setattr(L, "_read", read)
    L.reset()
    yield calls
    L.reset()


def test_crm_name_wins_and_new_codes_join(crm):
    s = L.Labels("new_siparis", "statuscode", {1: "Taslak", 100000001: "İptal"})
    assert s[100000001] == "İptal Edildi"
    assert s.get(1) == "Taslak"                       # CRM'de yok: yazılı ad
    assert s.get(862440000) == "Dağılım"              # CRM'e eklenen kod
    assert list(s) == [1, 100000001, 862440000]       # yazılı sıra, yeni kod sonda
    assert s.get("100000001") == "İptal Edildi" and s.get(None) is None and 7 not in s


def test_fixed_keeps_the_written_subset(crm):
    t = L.Labels("new_etkinlik", "new_ziyarettipi", {1: "MEB okulları", 3: "Üniversite"}, fixed=True)
    assert dict(t) == {1: "MEB okulları", 3: "Üniversiteler"}
    assert 4 not in t


def test_read_once_per_process(crm):
    s = L.Labels("new_siparis", "statuscode", {})
    for _ in range(5):
        s.get(1)
    L.Labels("new_etkinlik", "new_ziyarettipi", {}).get(3)
    assert len(crm) == 1


def test_warm_does_not_wait(monkeypatch):
    import threading
    gate = threading.Event()

    def slow():
        gate.wait(5)
        return L.parse([{"ent": "new_siparis", "attr": "statuscode", "code": 1, "label": "Taslak"}])

    monkeypatch.setenv("CRM_LABELS", "1")
    monkeypatch.setattr(L, "_read", slow)
    L.reset()
    try:
        L.warm()                                       # beklemeden döner
        gate.set()
        assert L.Labels("new_siparis", "statuscode", {})[1] == "Taslak"
    finally:
        L.reset()


def test_unreadable_crm_keeps_the_written_dictionary(monkeypatch):
    def broken():
        raise RuntimeError("VPN yok")

    monkeypatch.setenv("CRM_LABELS", "1")
    monkeypatch.setattr(L, "_read", broken)
    L.reset()
    try:
        s = L.Labels("new_siparis", "statuscode", {100000001: "İptal"})
        assert s[100000001] == "İptal" and len(s) == 1
    finally:
        L.reset()


def test_disabled_never_reads(monkeypatch):
    monkeypatch.setattr(L, "_read", lambda: pytest.fail("okunmamalı"))
    L.reset()
    assert L.Labels("new_siparis", "statuscode", {1: "Taslak"})[1] == "Taslak"


def test_sql_reads_turkish_names_with_entity():
    q = L.sql("Timas_MSCRM")
    assert "[Timas_MSCRM].dbo.StringMapBase" in q and "LangId = 1055" in q and "EntityView" in q
