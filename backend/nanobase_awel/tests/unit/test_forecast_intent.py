from __future__ import annotations

import pytest

from nanobase_awel.retrieval.forecast_intent import resolve_forecast_intent


@pytest.mark.parametrize(
    "q,metric,city,horizon,grain",
    [
        ("İstanbul satışları önümüzdeki 6 ay nasıl?", "total_revenue", "İstanbul", 6, "month"),
        ("istanbul satislari onumuzdeki alti ay nasil olur", "total_revenue", "İstanbul", 6, "month"),
        ("Ankara cirosu için gelecek 3 çeyrek tahmini", "total_revenue", "Ankara", 3, "quarter"),
        ("Önümüzdeki 12 ay toplam ciro ne olacak?", "total_revenue", None, 12, "month"),
        ("Satılan adet önümüzdeki 4 hafta tahmin", "total_quantity_sold", None, 4, "week"),
        ("6 aylık satış tahmini yap", "total_revenue", None, 6, "month"),
        ("Berlin sales forecast for the next 6 months", "total_revenue", "Berlin", 6, "month"),
        ("Gelecek ay ciro tahmini?", "total_revenue", None, 1, "month"),
    ],
)
def test_resolves(q, metric, city, horizon, grain):
    r = resolve_forecast_intent(q)
    assert r and "declined" not in r, r
    assert r["metricCode"] == metric
    assert r["dimensionFilters"] == ({"branch_city": city} if city else {})
    assert r["horizon"] == horizon
    assert r["grain"] == grain
    assert r["historyMonths"] == 36


@pytest.mark.parametrize(
    "q",
    [
        "Toplam ciro nedir?",
        "Bu sorgunun tahmini maliyeti nedir?",
        "Tahmin ediyorum ki İstanbul en iyisidir",
        "Geçen ay satışlar nasıldı?",
        "Cirosu 20000 TL üzerinde olan müşteriler",
    ],
)
def test_not_forecast(q):
    assert resolve_forecast_intent(q) is None


def test_declines_visibly_instead_of_guessing():
    assert resolve_forecast_intent("Önümüzdeki 6 ay nasıl olur?")["declined"] == "METRIC_UNRESOLVED"
    assert resolve_forecast_intent("Önümüzdeki 30 gün satış tahmini")["declined"] == "UNSUPPORTED_GRAIN"
    assert resolve_forecast_intent("Segment bazında önümüzdeki 6 ay satış tahmini")["declined"] == "UNSUPPORTED_SHAPE"
    assert resolve_forecast_intent("Cirosu 20000 üzerinde olanlar için önümüzdeki 6 ay satış tahmini")["declined"] == "UNSUPPORTED_SHAPE"
    assert resolve_forecast_intent("Şehir bazında önümüzdeki 6 ay satış tahmini")["declined"] == "UNSUPPORTED_SHAPE"


def test_dimension_values_from_env(monkeypatch):
    monkeypatch.setenv("FORECAST_DIMENSION_VALUES", '{"branch_city": ["İzmir"]}')
    r = resolve_forecast_intent("İzmir satışları önümüzdeki 6 ay nasıl?")
    assert r["dimensionFilters"] == {"branch_city": "İzmir"}
    assert resolve_forecast_intent("İstanbul satışları önümüzdeki 6 ay nasıl?")["dimensionFilters"] == {}
