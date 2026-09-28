"""M9 fiyatlama hesabı: birim maliyet, başabaş, hedef marja göre fiyat, emsal önerisi, baskı eğrisi."""

from __future__ import annotations

import math

import pytest

from semantic_bridge.pricing import model as M


def _inp(**kw):
    base = dict(print_per_copy=40.0, print_setup=20000.0, fixed={"ceviri": 30000.0, "grafik": 10000.0},
                royalty_rate=0.10, royalty_base="kapak", vat=0.10, discount=0.45, variable_rate=0.05)
    base.update(kw)
    return M.CostInputs(**base)


def test_print_unit_and_scale_economy():
    inp = _inp()
    assert M.print_unit(inp, 1000) == pytest.approx(60.0)
    assert M.print_unit(inp, 5000) == pytest.approx(44.0)
    uc = [M.unit_cost(inp, q)["perCopy"] for q in M.DEFAULT_QTYS]
    assert uc == sorted(uc, reverse=True)  # adet arttıkça birim maliyet düşer
    with pytest.raises(ValueError):
        M.print_unit(inp, 0)


def test_scenario_profit_matches_hand_calculation():
    inp = _inp()
    sc = M.scenario(inp, 2000, 220.0)
    n = 220 / 1.1 * 0.55            # 110
    r = 0.10 * 220 / 1.1            # 20
    var = 0.05 * n                  # 5.5
    cost = 2000 * 50 + 40000 + r * 2000 + var * 2000
    assert sc["netUnit"] == pytest.approx(n)
    assert sc["royaltyUnit"] == pytest.approx(r)
    assert sc["profit"] == pytest.approx(n * 2000 - cost, abs=0.01)
    # başabaş: (baskı toplamı + sabit) / (n − var − r)
    assert sc["breakeven"] == math.ceil((100000 + 40000) / (n - var - r))


def test_breakeven_with_advance_two_regimes():
    # Büyük avans: satıştan doğan telif avansı aşmadan başabaş gelir → telif avansın içinde kalır.
    inp = _inp(fixed={"avans": 100000.0})
    sc = M.scenario(inp, 3000, 300.0)
    n = 300 / 1.1 * 0.55
    var = 0.05 * n
    s1 = (3000 * (40 + 20000 / 3000) + 100000) / (n - var)
    assert 0.10 * 300 / 1.1 * s1 <= 100000
    assert sc["breakeven"] == math.ceil(s1)
    # Küçük avans: telif avansı aşar, avans mahsup edilir.
    small = _inp(fixed={"avans": 1000.0})
    sc2 = M.scenario(small, 3000, 300.0)
    r = 0.10 * 300 / 1.1
    s2 = (3000 * (40 + 20000 / 3000) + 1000 - 1000) / (n - var - r)
    assert sc2["breakeven"] == math.ceil(s2)
    # Kârda avans + değişken telif çift sayılmaz: toplam telif = max(avans, oran × satış).
    assert sc2["royaltyTotal"] == pytest.approx(r * 3000, abs=0.01)


def test_no_breakeven_when_contribution_negative():
    inp = _inp(discount=0.95)
    sc = M.scenario(inp, 1000, 100.0)
    assert sc["breakeven"] is None


def test_price_for_margin_hits_target_and_rounds_to_five():
    inp = _inp()
    out = M.price_for_margin(inp, 3000, 0.15)
    assert out["price"] % 5 == 0
    sc = M.scenario(inp, 3000, out["price"])
    assert sc["margin"] >= 0.15
    below = M.scenario(inp, 3000, out["price"] - 5)
    assert below["margin"] < 0.15  # en düşük fiyat


def test_price_for_margin_impossible():
    out = M.price_for_margin(_inp(discount=0.6, variable_rate=0.2, royalty_rate=0.2), 2000, 0.3)
    assert out["price"] is None and "hiçbir fiyatta" in out["reason"]


def test_net_royalty_base():
    inp = _inp(royalty_base="net")
    assert M.royalty_unit(inp, 220.0) == pytest.approx(0.10 * 110)
    out = M.price_for_margin(inp, 2000, 0.10)
    assert M.scenario(inp, 2000, out["price"])["margin"] >= 0.10


def test_sell_through_raises_price():
    full = M.price_for_margin(_inp(sell_through=1.0), 3000, 0.1)["price"]
    part = M.price_for_margin(_inp(sell_through=0.6), 3000, 0.1)["price"]
    assert part > full


def test_recommend_uses_comparables():
    inp = _inp()
    floor = M.price_for_margin(inp, 3000, 0.1)["price"]
    rec = M.recommend(inp, 3000, 0.1, [floor + 40, floor + 50, floor + 60, floor + 70])
    assert rec["floor"] == floor and rec["price"] == M.round_price(rec["median"])
    low = M.recommend(inp, 3000, 0.1, [10, 20, 30])
    assert low["price"] == floor and any("üst çeyreğini" in n for n in low["notes"])
    none = M.recommend(inp, 3000, 0.1, [])
    assert none["price"] == floor and any("Emsal fiyat yok" in n for n in none["notes"])


def test_fit_print_curve():
    pts = [(q, 30 + 15000 / q) for q in (500, 1000, 2000, 3000, 5000)]
    fit = M.fit_print_curve(pts)
    assert fit["shape"] == "a+b/Q" and fit["a"] == pytest.approx(30, abs=0.01) and fit["b"] == pytest.approx(15000, abs=1)
    assert M.fit_print_curve([(1000, 50), (1000, 52)]) is None
    # Adet arttıkça fiyat artıyorsa (b<0) eğri uydurulmaz, ortalama kullanılır.
    flat = M.fit_print_curve([(1000, 40), (2000, 50), (4000, 60)])
    assert flat["shape"] == "ortalama" and flat["b"] == 0.0


def test_quantile():
    assert M.quantile([], 0.5) is None
    assert M.quantile([1, 2, 3, 4], 0.5) == 2.5
    assert M.quantile([5], 0.25) == 5


def test_royalty_on_print_run():
    inp = _inp(royalty_on="baski", sell_through=0.5)
    sc = M.scenario(inp, 2000, 220.0)
    r = 0.10 * 220 / 1.1
    assert sc["royaltyTotal"] == pytest.approx(r * 2000)       # basılan adet üzerinden
    n = 220 / 1.1 * 0.55
    var = 0.05 * n
    assert sc["breakeven"] == math.ceil((100000 + 40000 + r * 2000) / (n - var))
    out = M.price_for_margin(inp, 2000, 0.1)
    assert M.scenario(inp, 2000, out["price"])["margin"] >= 0.1
    assert M.scenario(inp, 2000, out["price"] - 5)["margin"] < 0.1
