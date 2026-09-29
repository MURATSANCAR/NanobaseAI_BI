"""Sosyal medya hızı (2026-09-29): fırsatlar ve marka önerileri CRM'i her açılışta okumaz.

CRM okuması (özel günler + kitap bağları, aralıktaki yeni kitaplar, marka kartları) portal tablosunda saklanır; ikinci
açılış CRM'e gitmez ve aynı cevabı verir (JSON'a yazılıp okunan veri canlı okumayla birebir). Sabah turu (run-due)
beklenerek yeniler. Sorgu bilgisi: saklanan kaydın okuması + kökende CRM SQL'i; kaynaksız rakam yok.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from semantic_bridge import access as A
from semantic_bridge import provenance as PV
from semantic_bridge import social as S
from semantic_bridge import social_kaynak as SOK
from semantic_bridge import social_sources as src
from semantic_layer.candidates.llm_client import FakeLlm

TODAY = date.today()
SOON = TODAY + timedelta(days=10)


def _rows(sql: str) -> list[dict]:
    if "new_ozelgunlerBase o" in sql:
        return [{"id": "D-1", "name": "Kitap Haftası", "w1": None, "w2": None,
                 "dt": f"{SOON.isoformat()} 00:00:00"},
                {"id": "D-2", "name": "kitap haftası", "w1": None, "w2": None, "dt": None}]
    if "new_new_kitap_new_ozelgunlerBase" in sql:
        return [{"day_id": "d-1", "book_id": "B-1", "name": "Kitap Bir", "stok": "S1"},
                {"day_id": "D-2", "book_id": "B-2", "name": "Kitap İki", "stok": "S2"}]
    if "new_markaBase" in sql:
        return [{"id": "M-1", "ad": "Timaş", "instagram": "@timasyayinlari", "url": None},
                {"id": "M-2", "ad": "Genç Timaş", "instagram": None, "url": "https://x"}]
    if "new_ilkyayintarihi >=" in sql:
        return [{"kitap_id": "K-1", "stok_kodu": "S9", "ad": "Yeni Kitap", "yazar": "Yazar", "yayinevi_id": "Y-1",
                 "yayinevi": "Timaş", "kitaplik": "Roman", "kapak": None, "ilk_yayin": TODAY.isoformat()},
                {"kitap_id": "K-2", "stok_kodu": "S9", "ad": "Aynı Stok", "yazar": None, "yayinevi_id": None,
                 "yayinevi": None, "kitaplik": None, "kapak": None, "ilk_yayin": TODAY.isoformat()}]
    raise AssertionError(f"beklenmeyen CRM sorgusu: {sql[:80]}")


@pytest.fixture
def crm_calls(monkeypatch):
    calls: list[str] = []

    def run(self, sql):
        calls.append(sql)
        return _rows(sql)

    monkeypatch.setattr(src.Crm, "_run", run)
    return calls


@pytest.fixture
def client(monkeypatch, store, settings, crm_calls):
    from fastapi.testclient import TestClient

    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod
    from semantic_bridge.app import Runtime, create_app

    users = {"timas_session=a": "ayse"}
    monkeypatch.setattr(board_mod, "_fetch_user", lambda cookie: users.get(cookie))
    monkeypatch.setattr(board_mod, "_fetch_session", lambda cookie: {"username": users.get(cookie), "displayName": "x"})
    monkeypatch.setattr(admin_mod, "admins", lambda: ["zekiai"])
    monkeypatch.delenv("SEMANTIC_CALLER_TOKEN", raising=False)
    monkeypatch.delenv("SEMANTIC_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("SOCIAL_CRM_FRESH_SEC", raising=False)
    A._ready.clear()
    A.invalidate()
    S._ready.discard(id(store.engine))
    return TestClient(create_app(Runtime(settings, store=store, llm=FakeLlm([""]))))


H = {"cookie": "timas_session=a"}


def _body(r):
    return {k: v for k, v in r.json().items() if k != "kaynaklar"}


def _expected_opportunities(days: int) -> dict:
    """Eski hesap: CRM'i doğrudan okuyup aynı saf işlevlerle kurulan kısım."""
    from semantic_bridge.seo_geo import seasons as SS

    crm = src.Crm(lambda: "Timas_MSCRM.dbo", runner=lambda: None)
    sdays, sbooks = crm.special_days()
    st = S.settings(lambda k: "")
    occ = S.occasion_items(sdays, sbooks, TODAY, days, st["leadDays"], {d["key"]: set() for d in sdays}, SS.resolve,
                           SS.next_occurrence)
    start = TODAY.replace(day=1)
    end = max(TODAY + timedelta(days=days), (start + timedelta(days=32)).replace(day=1) - timedelta(days=1))
    nb = [{**b, "takvimde": False} for b in crm.new_books(start, end)]
    return {"ozelGunler": occ, "yeniKitaplar": {"baslangic": start.isoformat(), "bitis": end.isoformat(), "items": nb}}


def test_firsatlar_ikinci_acilista_crm_okunmaz_ve_ayni(client, crm_calls):
    first = client.get("/api/v1/social/opportunities", headers=H)
    assert first.status_code == 200, first.text
    n = len(crm_calls)
    assert n == 3, "ilk açılış: özel günler, kitap bağları, yeni kitaplar"
    crm_calls.clear()
    exp = _expected_opportunities(first.json()["gun"])
    assert crm_calls and first.json()["ozelGunler"] == exp["ozelGunler"]
    assert first.json()["yeniKitaplar"] == exp["yeniKitaplar"]
    assert first.json()["ozelGunler"], "fixture özel günü pencereye düşmeli"
    crm_calls.clear()
    second = client.get("/api/v1/social/opportunities", headers=H)
    assert crm_calls == [], "saklanan okuma: CRM'e gidilmez"
    assert _body(second) == _body(first)
    k = second.json()["kaynaklar"]
    assert not k.get("error")
    saved = [s for s in k["sources"].values() if "semantic_social_meta" in (s.get("sql") or "")]
    assert saved and all(s["origin"] for s in saved), "saklanan kaydın okuması ve kökende CRM sorgusu"
    crm_sql = {s["id"]: s["sql"] for s in k["sources"].values() if s["connection"] == "crm"}
    assert any("new_ozelgunlerBase" in x for x in crm_sql.values()) and any("new_ilkyayintarihi" in x for x in crm_sql.values())
    assert not PV.uncovered_numbers(second.json(), SOK.NOT_RAKAM)


def test_yenile_basligi_beklemez(client, crm_calls):
    import time

    client.get("/api/v1/social/opportunities", headers=H)
    crm_calls.clear()
    r = client.get("/api/v1/social/opportunities", headers={**H, "x-data-refresh": "1"})
    assert r.status_code == 200 and crm_calls == [], "yenile CRM'i beklemez"
    time.sleep(0.2)
    assert crm_calls == [], "1 dakikadan taze kayıt yenile basılsa da arkada yeniden okunmaz"


def test_marka_onerileri_saklanir(client, crm_calls):
    a = client.get("/api/v1/social/accounts/crm-suggestions", headers=H)
    assert a.status_code == 200, a.text
    assert len(crm_calls) == 1
    crm = src.Crm(lambda: "Timas_MSCRM.dbo", runner=lambda: None)
    exp = [{**b, "ekli": False} for b in crm.brands()]
    assert a.json()["items"] == exp and a.json()["marka"] == 2 and a.json()["instagramDolu"] == 1
    crm_calls.clear()
    b = client.get("/api/v1/social/accounts/crm-suggestions", headers=H)
    assert crm_calls == [] and _body(b) == _body(a)
    k = b.json()["kaynaklar"]
    assert not k.get("error") and not PV.uncovered_numbers(b.json(), SOK.NOT_RAKAM)
    assert any("new_markaBase" in (s.get("sql") or "") for s in k["sources"].values())


def test_sabah_turu_beklenerek_yeniler(client, crm_calls, store):
    client.get("/api/v1/social/opportunities", headers=H)
    client.get("/api/v1/social/accounts/crm-suggestions", headers=H)
    crm_calls.clear()
    r = client.post("/api/v1/social/run-due")
    assert r.status_code == 200, r.text
    joined = "\n".join(crm_calls)
    assert "new_ozelgunlerBase" in joined and "new_ilkyayintarihi" in joined and "new_markaBase" in joined
    assert r.json()["crmOkuma"] == {"yeniKitaplar": 1, "markalar": 2}
    keys = [row.key for row in store.engine.connect().execute(S.META.select()).all()]
    assert "crm.ozelgun" in keys and "crm.marka" in keys and sum(1 for x in keys if x.startswith("crm.yeni.")) >= 1
