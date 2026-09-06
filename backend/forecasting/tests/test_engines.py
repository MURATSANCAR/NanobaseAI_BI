"""Baseline engines + service + HTTP surface (no model download in CI)."""

from __future__ import annotations

import math
import random
from datetime import date

import pytest
from fastapi.testclient import TestClient

from forecasting.app.engines import NaiveEngine, SeasonalNaiveEngine, create_engine
from forecasting.app.service import ForecastService
from forecasting.contracts import ForecastRequest, build_series_bundle
from forecasting.contracts.builder import next_period


def _seasonal_bundle(n: int = 48, horizon: int = 6, seed: int = 7):
    rnd = random.Random(seed)
    rows = []
    for i in range(n):
        d = next_period(date(2022, 9, 1), "M", i)
        season = 1 + 0.2 * math.sin(2 * math.pi * (d.month - 1) / 12)
        rows.append((d, 1000 * (1 + 0.01 * i) * season + rnd.random() * 20))
    return build_series_bundle(rows, metric="total_revenue", frequency="M", horizon=horizon)


def test_naive_repeats_last_value_with_widening_interval():
    b = _seasonal_bundle()
    out = NaiveEngine().forecast(b)
    assert len(out.points) == 6
    assert all(p.p50 == b.history[-1].value for p in out.points)
    widths = [p.p90 - p.p10 for p in out.points]
    assert widths == sorted(widths)  # random-walk widening
    assert out.points[0].timestamp == date(2026, 9, 1)


def test_seasonal_naive_uses_same_month_last_year():
    b = _seasonal_bundle()
    out = SeasonalNaiveEngine().forecast(b)
    y = [p.value for p in b.history]
    assert [p.p50 for p in out.points] == [y[len(y) - 12 + h] for h in range(6)]
    assert all(p.p10 <= p.p50 <= p.p90 for p in out.points)
    assert out.warnings == []


def test_seasonal_naive_falls_back_when_short():
    b = _seasonal_bundle(n=18, horizon=3)
    out = SeasonalNaiveEngine().forecast(b)
    assert any(w.startswith("seasonal_fallback_naive") for w in out.warnings)
    assert all(p.p50 == b.history[-1].value for p in out.points)


def test_non_negative_history_never_forecasts_below_zero():
    rows = [(next_period(date(2024, 1, 1), "M", i), 5.0 if i % 2 else 0.0) for i in range(24)]
    b = build_series_bundle(rows, metric="m", frequency="M", horizon=4)
    out = NaiveEngine().forecast(b)
    assert all(p.p10 >= 0 for p in out.points)


def test_create_engine_unknown():
    with pytest.raises(ValueError):
        create_engine("oracle_of_delphi")


def test_service_provenance_and_cache():
    svc = ForecastService(default_engine="seasonal_naive")
    b = _seasonal_bundle()
    r1 = svc.forecast(ForecastRequest(bundle=b))
    assert r1.engine == "seasonal_naive"
    assert r1.bundle_hash == b.bundle_hash
    assert r1.horizon == 6 and len(r1.forecast) == 6
    r2 = svc.forecast(ForecastRequest(bundle=b))
    assert "cache_hit" in r2.warnings
    assert [p.p50 for p in r2.forecast] == [p.p50 for p in r1.forecast]
    r3 = svc.forecast(ForecastRequest(bundle=b, engine="naive"))
    assert r3.engine == "naive" and "cache_hit" not in r3.warnings


def test_http_surface(monkeypatch):
    monkeypatch.setenv("FORECAST_WARM", "0")
    from forecasting.app import main as m

    client = TestClient(m.app)
    # default engine not warmed → 503 until first use loads it
    m.service.engine().load()
    assert client.get("/health").status_code == 200
    assert "seasonal_naive" in client.get("/engines").json()["available"]
    b = _seasonal_bundle()
    r = client.post("/forecast", json={"bundle": b.model_dump(mode="json")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["bundle_hash"] == b.bundle_hash
    assert len(body["forecast"]) == 6
    assert body["forecast"][0]["timestamp"] == "2026-09-01"
    bad = client.post("/forecast", json={"bundle": b.model_dump(mode="json"), "engine": "nope"})
    assert bad.status_code == 400


# --- TimesFM 3.0 (opt-in: needs the upstream package + checkpoint) --------------


@pytest.mark.skipif(
    __import__("os").environ.get("FORECAST_TEST_MODEL") != "1",
    reason="set FORECAST_TEST_MODEL=1 (and FORECAST_MODEL3_ID / FORECAST_ALLOW_NONCOMMERCIAL=1) to run TimesFM 3.0",
)
def test_timesfm3_real_model_quantiles():
    from forecasting.app.engines.timesfm3 import TimesFM3Engine

    eng = TimesFM3Engine()
    eng.load()
    assert eng.ready
    b = _seasonal_bundle(n=48, horizon=6)
    out = eng.forecast(b)
    assert len(out.points) == 6
    assert all(p.p10 <= p.p50 <= p.p90 for p in out.points)
    assert all(p.p10 >= 0 for p in out.points)  # non-negative history → floor at 0
    assert out.points[0].timestamp == date(2026, 9, 1)
    # A trended seasonal series must not collapse to a constant.
    assert len({round(p.p50, 3) for p in out.points}) > 1
    # Determinism: same bundle → same numbers.
    again = eng.forecast(b)
    assert [p.p50 for p in again.points] == [p.p50 for p in out.points]


def test_timesfm3_refuses_without_licence_flag(monkeypatch):
    monkeypatch.delenv("FORECAST_ALLOW_NONCOMMERCIAL", raising=False)
    from forecasting.app.engines.timesfm3 import TimesFM3Engine

    eng = TimesFM3Engine()
    assert not eng.ready
    with pytest.raises(RuntimeError, match="FORECAST_ALLOW_NONCOMMERCIAL"):
        eng.load()
