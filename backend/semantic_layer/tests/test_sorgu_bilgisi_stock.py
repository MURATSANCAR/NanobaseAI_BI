"""Sorgu bilgisi · M43 Depo ve stok: her ucun cevabındaki her rakam bir kaynağa bağlı, SQL çalışmış metin.

Okuma yapaydır (FakeRun): `stock_sources.Logo`/`Crm` gerçek dosyaları gerçek yer tutucu doldurmayla çalıştırır ve
`runs` kaydını tutar; uçlar bu kayıtla cevap verir. Denetlenen: kaynaksız rakam yok (`uncovered_numbers`), kayıt
tutarlı, SQL'de yer tutucu yok, okunmamış kaynağın kaydı yok. Gerçek Logo/CRM kabulü: `scripts/acceptance/sorgu-bilgisi/g3_stock.py`.
"""
from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from semantic_bridge import access as A
from semantic_bridge import provenance as P
from semantic_bridge import stock_api
from semantic_bridge import stock_kaynak as K
from semantic_bridge import stock_sources as src
from semantic_bridge import stock_store as store
from semantic_layer.store.catalog_store import open_store
from semantic_layer.tests.test_stock import SETTINGS, FakeCosts, raw_fixture

T = "t1"
H = {"x-user": "a"}


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    store._ready.discard(id(e))
    store.ensure(e)
    return e


def _runs() -> dict:
    """Okumanın çalıştırma kaydı: gerçek SQL dosyaları, gerçek doldurma (firma, şema, pencere)."""
    lg, cr = src.Logo(lambda sql: []), src.Crm(lambda sql: [], "Timas_MSCRM.dbo")
    lg._firms = {2025: "211", 2026: "411"}
    lg.balances()
    lg.data_end()
    lg.warehouses()
    lg.eos_stock()
    lg.turnover()
    lg.movement(date(2025, 8, 17), date(2026, 8, 18))
    lg.open_orders()
    cr.pending_orders()
    cr.shelves()
    cr.depots()
    cr.transfers()
    cr.transfer_items()
    cr.waiting_products()
    cr.pick_line(date(2026, 8, 1))
    runs = {**lg.runs, **cr.runs}
    # satış hızı: Baskı Öneri dosyası yıllık görünüm açılımıyla (açılım `management.expand_sales`, burada 2025–2026)
    from semantic_bridge import management

    text, _ = management.expand_sales(src.sql_text("baski-oneri:logo_satis_hizi"), date(2026, 8, 17), {2025, 2026})
    runs["baski-oneri:logo_satis_hizi"] = {"sql": text, "rows": 6, "ms": 900, "at": 1_000_000.0}
    return runs


def _raw() -> dict:
    raw = raw_fixture()
    raw["runs"] = _runs()
    raw["pick"] = [{"id": "s1", "no": "SP-1", "durum": 100000012, "tip": 1, "oncelik": 1, "siparis": date(2026, 9, 1),
                    "depoda": "2026-09-20T08:00:00", "pusula": "2026-09-20T09:00:00", "kutulandi": None, "sevk": None,
                    "depo": "Merkez", "toplayan": "Ali", "koli": 2},
                   {"id": "s2", "no": "SP-2", "durum": 3, "tip": 1, "oncelik": 3, "siparis": date(2026, 9, 1),
                    "depoda": "2026-09-19T08:00:00", "pusula": "2026-09-19T09:00:00", "kutulandi": "2026-09-19T12:00:00",
                    "sevk": "2026-09-19T15:00:00", "depo": "Merkez", "toplayan": "Ali", "koli": 1}]
    return raw


class FakeSource:
    def peek(self):
        return {"since": "2025-01-01", "cards": [{"id": "c1"}], "at": 1_000_000.0, "crmMs": 40}

    def _schema(self):
        return "Timas_MSCRM.dbo"


class FakeM12:
    source = FakeSource()

    def cards(self, engine, tenant):
        return [{"id": "c1", "stockCode": "B-BIT", "stage": "matbaada", "qty": 2000, "printNo": 3, "name": "Bitecek",
                 "stageLabel": "Matbaada", "plan": {"baski": "2026-10-01", "depo": "2026-10-15"}, "created": "2026-09-01"}], {}


def _client(engine, monkeypatch, perms: set[str]):
    app = FastAPI()

    def auth(request):
        if request.headers.get("x-user") != "a":
            from fastapi import HTTPException
            raise HTTPException(status_code=401)
        return engine, T, "ayse", "Ayşe"

    deps = {"auth": auth, "require_caller": lambda r: None, "can": lambda u, k: k in perms, "is_admin": lambda u: False,
            "audit": lambda *a: None, "conf": lambda k, d="": d, "fresh": lambda: False, "engine": lambda: engine,
            "tenant": lambda: T, "logo_file": lambda: "", "crm_file": lambda: "", "llm": lambda p: None,
            "m12": lambda: FakeM12(), "costs": lambda: FakeCosts()}
    svc = stock_api.register(app, deps)
    raw = _raw()
    monkeypatch.setattr(svc, "raw", lambda fresh=False: raw)
    monkeypatch.setattr(svc, "settings", lambda: SETTINGS)
    return TestClient(app)


def _check(out: dict) -> dict:
    k = out.get("kaynaklar")
    assert k and not k.get("error"), k
    assert P.uncovered_numbers(out, K.NOT_RAKAM) == []
    assert P.problems(out) == []
    for s in k["sources"].values():
        assert s["sql"].strip() and P.placeholders_left(s["sql"]) == [], (s["id"], P.placeholders_left(s["sql"]))
        assert s["connection"] in ("logo", "crm", "portal")
    json.dumps(out, default=str)
    return k


def test_runs_keep_the_executed_text_per_year_copy():
    runs = _runs()
    assert "logo_hareket:2025" in runs and "logo_hareket:2026" in runs
    assert "LG_211_01_STLINE" in runs["logo_hareket:2025"]["sql"] and "LG_411_01_STLINE" in runs["logo_hareket:2026"]["sql"]
    for rid, r in runs.items():
        assert P.placeholders_left(r["sql"]) == [], rid
        assert r["rows"] >= 0 and r["ms"] >= 0 and r["at"]


@pytest.mark.parametrize("perms", [set(), {A.page("stok"), stock_api.FEATURE_COST, stock_api.FEATURE_PICK}])
def test_every_stock_endpoint_has_no_unsourced_number(engine, monkeypatch, perms):
    c = _client(engine, monkeypatch, perms)
    store.save_threshold(engine, T, "ayse", {"stokKodu": "B-YET", "guvenlikGun": 20, "yenidenSiparisAdet": 500})
    store.add_suggestion(engine, T, "bitecek", "B-BIT", {"gun": 20.0, "bakiye": 100.0, "satisHizi": 150.0}, "kural", "M12")
    for path in ("/overview", "/items", "/items?durum=bitecek", "/items/B-BIT", "/running-out?gun=30", "/excess",
                 "/diff", "/transfer-errors", "/transfer-errors?tur=bekliyor", "/pick-line", "/thresholds?durum=oneri",
                 "/thresholds?durum=taslak", "/suggestions?tur=bitecek"):
        r = c.get("/api/v1/stock" + path, headers=H)
        assert r.status_code == 200, (path, r.text)
        k = _check(r.json())
        assert k["sources"], path


def test_overview_numbers_point_to_their_own_queries(engine, monkeypatch):
    c = _client(engine, monkeypatch, {stock_api.FEATURE_COST})
    ov = c.get("/api/v1/stock/overview", headers=H).json()
    k = ov["kaynaklar"]
    assert k["fields"]["toplamStok"] == "hesap:toplam"
    assert "stok.logo_bakiye" in k["formulas"]["bakiye"]["inputs"]
    assert "stok.crm_aktarim_hatasi" in k["formulas"]["aktarim"]["inputs"]
    assert "LG_411_01_STLINE" in k["sources"]["stok.logo_bakiye"]["sql"]
    assert "Timas_MSCRM.dbo." in k["sources"]["stok.crm_raf_stok"]["sql"]
    assert k["sources"]["stok.logo_bakiye"]["stats"]["rows"] == 0
    assert "deger" in k["fields"]
    # yılbaşı penceresi iki yıl kopyasından: iki ayrı kayıt, ikisi de 12 ay satış hesabının girdisi
    assert {"stok.logo_hareket.2025", "stok.logo_hareket.2026"} <= set(k["formulas"]["hareket"]["inputs"])


def test_unread_source_is_not_shown(engine, monkeypatch):
    raw = _raw()
    for rid in [r for r in raw["runs"] if r.startswith("crm_")]:
        raw["runs"].pop(rid)
    import semantic_bridge.stock as S

    svc = S.Service(lambda: None, lambda: None, lambda: "", lambda: SETTINGS)
    monkeypatch.setattr(svc, "raw", lambda fresh=False: raw)
    m = svc.model(engine, T)
    k = K.for_overview(engine, T, m, {"aktarimHatasi": 1}, {"m12": FakeM12()})
    assert not any(sid.startswith("stok.crm_") for sid in k.sources)
    assert "aktarimHatasi" not in k.fields               # kaynağı okunmadıysa «i» çıkmaz, uydurma sorgu yok


def test_sources_panel_never_returns_a_template(engine, monkeypatch):
    c = _client(engine, monkeypatch, set())
    out = c.get("/api/v1/stock/sources", headers=H).json()
    for s in out["sources"]:
        assert s["sql"] is None or P.placeholders_left(s["sql"]) == []
