"""M9 birim maliyet sağlayıcısı: öncelik (onaylı analiz → Logo gerçekleşen → yok), «maliyet bilinmiyor» durumu ve
M32 / M33 / M53'ün sağlayıcıyı kendi beklediği biçimde aldığı (sahte kayıt ve sahte görüntüyle; Logo'ya gidilmez)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from semantic_bridge import corporate_sales_sources as CS
from semantic_bridge import tenders_sources as TS
from semantic_bridge.pricing import cost_provider as C
from semantic_bridge.pricing import store as S
from semantic_layer.store.catalog_store import open_store

T = "t1"
ROLES = {"tahmini": ("mali", "satis"), "kesin": ("mali", "satis", "pazarlama", "yonetim")}

#: Görüntüde: B'nin 2026'sı maliyetli (2025 daha eski), D yalnız 2025'te maliyetli, E'nin maliyeti girilmemiş.
SNAP = {
    "dataEnd": "2026-08-17",
    "sales": {
        "A": {"2026": {"cogs": 9000.0, "costedQty": 1000.0, "soldQty": 1000.0}},
        "B": {"2025": {"cogs": 5000.0, "costedQty": 1000.0, "soldQty": 1000.0},
              "2026": {"cogs": 3600.0, "costedQty": 300.0, "soldQty": 400.0}},
        "D": {"2025": {"cogs": 1250.0, "costedQty": 100.0, "soldQty": 100.0},
              "2026": {"cogs": 0.0, "costedQty": 0.0, "soldQty": 50.0}},
        "E": {"2026": {"cogs": 0.0, "costedQty": 0.0, "soldQty": 80.0}},
    },
}


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    S._ready.discard(id(e))
    S.ensure(e)
    return e


@pytest.fixture
def clock(monkeypatch):
    """Onay imzalarına artan saat: «en son onaylanan» sırası belirli olsun."""
    t = [datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)]

    def now():
        t[0] += timedelta(minutes=1)
        return t[0]
    monkeypatch.setattr(S, "_now", now)
    return t


def approved(engine, code, unit_cost, stage="tahmini", tenant=T, status="onaylandi"):
    """Kitaba analiz açar, onaya gönderir, aşamanın bütün imzalarını attırır (status='onayda' ise imzasız bırakır)."""
    a = S.create_analysis(engine, tenant, "hazirlayan", {"title": f"{code} analizi", "stage": stage, "stockCode": code})
    S.update_analysis(engine, tenant, "hazirlayan", a["id"], {"chosenPrice": 240, "chosenQty": 3000})
    a = S.submit(engine, tenant, "hazirlayan", a["id"], {"summary": {"unitCost": unit_cost, "qty": 3000, "price": 240}})
    if status == "onaylandi":
        for role in ROLES[stage]:
            a = S.decide(engine, tenant, f"{role}1", a["id"], role, "onay", "", a["version"], True)
        assert a["status"] == "onaylandi"
    return a


def test_priority_approved_then_actual_then_none(engine, clock):
    approved(engine, "A", 12.5)
    out = C.unit_costs(["A", "B", "Z"], engine=engine, tenant=T, snapshot=SNAP)
    assert set(out) == {"A", "B", "Z"}
    # A: hem onaylı analiz hem gerçekleşen var → onaylı analiz
    assert out["A"]["kaynak"] == "onayli-analiz" and out["A"]["maliyet"] == Decimal("12.5")
    assert out["A"]["tarih"] == "2026-09-01" and out["A"]["asama"] == "tahmini"
    # B: analiz yok → maliyetli en son yıl (2026: 3600 / 300), tarih veri sonu
    assert out["B"] == {"maliyet": Decimal("12.0"), "kaynak": "gerceklesen", "tarih": "2026-08-17", "yil": 2026,
                        "kapsam": 0.75}
    # Z: hiçbir yerde yok → uydurma yok
    assert out["Z"] == {"maliyet": None, "kaynak": "yok", "tarih": None, "not": "maliyet bilinmiyor"}


def test_actual_skips_years_without_cost_and_dates_old_years_at_year_end():
    out = C.unit_costs(["D", "E"], snapshot=SNAP)
    assert out["D"]["kaynak"] == "gerceklesen" and out["D"]["maliyet"] == Decimal("12.5")
    assert out["D"]["yil"] == 2025 and out["D"]["tarih"] == "2025-12-31"
    assert out["E"]["kaynak"] == "yok" and out["E"]["maliyet"] is None      # satış var ama maliyet girilmemiş


def test_final_stage_beats_estimate_and_newest_wins_within_a_stage(engine, clock):
    approved(engine, "A", 10.0, "kesin")
    approved(engine, "A", 11.0, "tahmini")              # daha yeni ama tahmini → kesin kalır
    approved(engine, "B", 20.0, "tahmini")
    approved(engine, "B", 21.0, "tahmini")              # aynı aşamada daha yeni → bu
    out = C.unit_costs(["A", "B"], engine=engine, tenant=T, snapshot=SNAP)
    assert out["A"]["maliyet"] == Decimal("10.0") and out["A"]["asama"] == "kesin"
    assert out["B"]["maliyet"] == Decimal("21.0")


def test_unapproved_other_tenant_and_zero_cost_analyses_are_ignored(engine, clock):
    approved(engine, "A", 30.0, status="onayda")        # imza bekliyor
    approved(engine, "B", 30.0, tenant="baska")         # başka kiracı
    approved(engine, "D", 0.0)                          # onaylı ama maliyeti sıfır → bilinmiyor sayılır
    out = C.unit_costs(["A", "B", "D", "Q"], engine=engine, tenant=T, snapshot=SNAP)
    assert out["A"]["kaynak"] == "gerceklesen" and out["A"]["maliyet"] == Decimal("9.0")
    assert out["B"]["kaynak"] == "gerceklesen"
    assert out["D"]["kaynak"] == "gerceklesen" and out["D"]["yil"] == 2025
    assert out["Q"]["kaynak"] == "yok"


def test_nothing_known_is_unknown_not_invented():
    out = C.unit_costs([" A ", "A", "", None, "Q"])
    assert list(out) == ["A", "Q"]
    assert all(v["maliyet"] is None and v["kaynak"] == "yok" and v["not"] == "maliyet bilinmiyor" for v in out.values())
    assert C.unit_costs([]) == {}


def test_unreadable_records_fall_back_to_actual():
    class Broken:
        def connect(self):
            raise RuntimeError("veritabanı yok")
    out = C.unit_costs(["B"], engine=Broken(), tenant=T, snapshot=SNAP)
    assert out["B"]["kaynak"] == "gerceklesen"


def _provider(engine, snap=SNAP):
    return C.Provider(engine=lambda: engine, tenant=lambda: T, snapshot=lambda: snap)


def test_provider_survives_missing_snapshot_and_context():
    def boom():
        raise OSError("klasör yok")
    p = C.Provider(engine=boom, tenant=lambda: T, snapshot=boom)
    assert p.unit_costs(["A"])["A"]["kaynak"] == "yok"
    assert p.birim(["A"]) == {} and p.labelled().unit_costs(["A"]) == {}


def test_m32_corporate_sales_takes_the_provider(engine, clock):
    approved(engine, "A", 12.5)
    CS.register_cost_provider(_provider(engine).birim)
    try:
        out = CS.unit_costs(["A", "B", "Z"], "m9")
    finally:
        CS.register_cost_provider(None)
    assert out["A"] == {"birim": 12.5, "kaynak": "m9", "tarih": "2026-09-01", "tahmini": False}
    assert out["B"]["birim"] == 12.0 and out["B"]["tarih"] == "2026-08-17"
    assert out["Z"]["birim"] is None and out["Z"]["kaynak"] == "bilinmiyor"


def test_m33_tenders_takes_the_provider_with_a_readable_source(engine, clock):
    approved(engine, "A", 12.5, "kesin")
    out = TS.unit_costs(_provider(engine).labelled(), ["A", "B", "Z"])
    assert out["A"] == {"maliyet": 12.5, "kaynak": "Onaylı fiyat analizi (Aşama 2 · Kesin fiyat, 2026-09-01)"}
    assert out["B"] == {"maliyet": 12.0, "kaynak": "Logo gerçekleşen maliyet (2026)"}
    assert "Z" not in out                               # ekran «maliyet bilinmiyor» yazar


def test_m53_sets_takes_the_same_shape_as_m32(engine, clock):
    sets = pytest.importorskip("semantic_bridge.sets_sources")   # M53 main'e girince koşar
    approved(engine, "A", 12.5)
    sets.register_cost_provider(_provider(engine).birim)
    try:
        out = sets.unit_costs(["A", "Z"], "m9")
    finally:
        sets.register_cost_provider(None)
    assert out["A"]["birim"] == 12.5 and out["Z"]["birim"] is None


def test_app_wires_the_provider_into_m32_and_m33(monkeypatch, tmp_path, store, settings):
    from semantic_bridge.app import Runtime, create_app
    from semantic_layer.candidates.llm_client import FakeLlm

    monkeypatch.setenv("PRICING_DATA_DIR", str(tmp_path))
    (tmp_path / "snapshot.json").write_text(json.dumps(SNAP))
    app = create_app(Runtime(settings, store=store, llm=FakeLlm([""])))
    try:
        assert CS._COST_PROVIDER == app.state.pricing_costs.birim
        assert isinstance(app.state.unit_cost, C.Labelled)
        S._ready.discard(id(store.engine))
        S.ensure(store.engine)
        a = S.create_analysis(store.engine, settings.tenant_id, "h", {"title": "A", "stockCode": "A"})
        S.update_analysis(store.engine, settings.tenant_id, "h", a["id"], {"chosenPrice": 240, "chosenQty": 3000})
        a = S.submit(store.engine, settings.tenant_id, "h", a["id"], {"summary": {"unitCost": 12.5}})
        for role in ROLES["tahmini"]:
            a = S.decide(store.engine, settings.tenant_id, f"{role}1", a["id"], role, "onay", "", a["version"], True)
        corp = CS.unit_costs(["A", "B", "Z"], "m9")
        assert corp["A"]["birim"] == 12.5 and corp["B"]["birim"] == 12.0 and corp["Z"]["birim"] is None
        tender = TS.unit_costs(app.state.unit_cost, ["A", "B", "Z"])
        assert tender["A"]["maliyet"] == 12.5 and tender["A"]["kaynak"].startswith("Onaylı fiyat analizi")
        assert tender["B"]["kaynak"] == "Logo gerçekleşen maliyet (2026)" and "Z" not in tender
    finally:
        CS.register_cost_provider(None)
