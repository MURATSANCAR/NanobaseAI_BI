"""Baseline engines: last-value naive and seasonal naive.

These are the floor. Plan Faz 4.3: a learned engine becomes the production
default only if it beats SeasonalNaive on WAPE in the rolling-origin benchmark.
"""

from __future__ import annotations

from forecasting.app.engines.base import EngineForecast, ForecastEngine
from forecasting.contracts.models import SeriesBundle


class NaiveEngine(ForecastEngine):
    name = "naive"
    version = "1.0"

    def forecast(self, bundle: SeriesBundle) -> EngineForecast:
        y = [p.value for p in bundle.history]
        last = y[-1]
        point = [last] * bundle.horizon
        sigma = self._residual_sigma([y[i] - y[i - 1] for i in range(1, len(y))])
        return EngineForecast(points=self._interval_points(bundle, point, sigma, widen=True))


class SeasonalNaiveEngine(ForecastEngine):
    name = "seasonal_naive"
    version = "1.0"

    def forecast(self, bundle: SeriesBundle) -> EngineForecast:
        y = [p.value for p in bundle.history]
        m = self._season(bundle)
        warnings: list[str] = []
        if m <= 1 or len(y) < 2 * m:
            # Not enough seasons to be seasonal — fall back to naive, say so.
            warnings.append(f"seasonal_fallback_naive:m={m},n={len(y)}")
            last = y[-1]
            point = [last] * bundle.horizon
            sigma = self._residual_sigma([y[i] - y[i - 1] for i in range(1, len(y))])
            return EngineForecast(points=self._interval_points(bundle, point, sigma, widen=True), warnings=warnings)
        point = [y[len(y) - m + (h % m)] for h in range(bundle.horizon)]
        sigma = self._residual_sigma([y[i] - y[i - m] for i in range(m, len(y))])
        # Seasonal-naive error does not compound within the first season.
        return EngineForecast(points=self._interval_points(bundle, point, sigma, widen=False), warnings=warnings)
