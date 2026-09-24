"""Toplu aylık tahmin (POST /forecast/batch): sözleşme, ek değişken hizalama, servis ve HTTP."""

from __future__ import annotations

import math
import os

import numpy as np
import pytest
from fastapi.testclient import TestClient

from forecasting.app.engines.base import calendar_covariates, month_index, month_str, shared_past_slice
from forecasting.app.service import ForecastService
from forecasting.contracts import BatchForecastRequest


def test_month_index_round_trip():
    assert month_index("2026-07") == 2026 * 12 + 6
    assert month_str(month_index("2025-12") + 1) == "2026-01"


def test_calendar_covariates_mark_peak_months():
    c = calendar_covariates(month_index("2025-08"), 4, [9, 10])  # Ağu, Eyl, Eki, Kas
    assert c.shape == (3, 4)
    assert c[2].tolist() == [0.0, 1.0, 1.0, 0.0]
    assert abs(c[0][0] - math.sin(2 * math.pi * 8 / 12)) < 1e-6


def test_shared_past_is_aligned_and_standardised():
    shared_start = month_index("2025-01")
    vals = [100.0 * (i + 1) for i in range(12)]  # 2025-01 … 2025-12
    s = shared_past_slice(shared_start, vals, month_index("2024-11"), 6)  # 2024-11 … 2025-04
    assert s.shape == (1, 6)
    assert np.isnan(s[0, :2]).all()  # ortak serinin kapsamadığı aylar
    ok = s[0, 2:]
    assert abs(ok.mean()) < 1e-5 and list(ok) == sorted(ok)


def _req(**kw):
    series = [
        {"id": "A", "start": "2024-01", "values": [float(m % 12 + 1) for m in range(24)]},
        {"id": "B", "start": "2025-06", "values": [5.0, None, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0]},
    ]
    return BatchForecastRequest(horizon=6, series=series, **kw)


def test_service_batch_seasonal_naive_shapes_and_months():
    out = ForecastService("seasonal_naive").forecast_batch(_req(engine="seasonal_naive"))
    assert out.engine == "seasonal_naive" and out.horizon == 6 and len(out.quantile_levels) == 9
    a, b = out.results
    assert (a.id, a.start) == ("A", "2026-01") and (b.id, b.start) == ("B", "2026-07")
    assert all(len(row) == 9 for row in a.quantiles) and len(a.quantiles) == 6
    assert [row[4] for row in a.quantiles] == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]  # geçen yılın aynı ayı
    # Temmuz 2026'nın geçen yılki karşılığı eksik ay (None → 0), Ağustos'unki 7
    assert (b.quantiles[0][4], b.quantiles[1][4]) == (0.0, 7.0)


def test_service_batch_rejects_engine_without_batch():
    with pytest.raises(ValueError):
        ForecastService("naive").forecast_batch(_req(engine="naive"))


def test_http_batch(monkeypatch):
    monkeypatch.setenv("FORECAST_WARM", "0")
    from forecasting.app import main as m

    client = TestClient(m.app)
    body = _req(engine="seasonal_naive", calendar=True, calendar_peak_months=[9, 10],
                shared_past={"start": "2024-01", "values": [1.0] * 30}).model_dump(mode="json")
    r = client.post("/forecast/batch", json=body)
    assert r.status_code == 200, r.text
    assert [x["id"] for x in r.json()["results"]] == ["A", "B"]
    body["engine"] = "naive"
    assert client.post("/forecast/batch", json=body).status_code == 400
    bad = dict(body, series=[{"id": "X", "start": "2026-13", "values": [1.0]}])
    assert client.post("/forecast/batch", json=bad).status_code == 422


@pytest.mark.skipif(os.environ.get("FORECAST_TEST_MODEL") != "1", reason="FORECAST_TEST_MODEL=1 ile TimesFM 3.0")
def test_timesfm3_batch_with_covariates():
    from forecasting.app.engines.timesfm3 import TimesFM3Engine

    eng = TimesFM3Engine()
    ctx = [np.array([10 + 5 * math.sin(2 * math.pi * m / 12) for m in range(60)], np.float32),
           np.array([1.0, np.nan, 3.0] + [4.0] * 30, np.float32)]
    outs = eng.forecast_batch(ctx, [month_index("2021-01"), month_index("2023-06")], 12, calendar=True,
                              peak_months=[9, 10], shared=(month_index("2020-01"), [100.0] * 90))
    assert [o.shape for o in outs] == [(12, 9), (12, 9)]
    assert all((np.diff(o, axis=1) >= -1e-6).all() for o in outs)  # kantiller sıralı
    assert (outs[0] >= 0).all()
