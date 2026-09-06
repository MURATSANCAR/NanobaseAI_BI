"""Forecast engines — adapter pattern (plan Faz 3.2).

The orchestrator never talks to a model library directly; it sends a
SeriesBundle to the service, which picks an engine by name. Baselines
(naive, seasonal_naive) are always available and are the benchmark floor
every learned engine must beat before becoming the default.
"""

from __future__ import annotations

from forecasting.app.engines.base import ForecastEngine
from forecasting.app.engines.naive import NaiveEngine, SeasonalNaiveEngine

ENGINE_FACTORIES = {
    "naive": NaiveEngine,
    "seasonal_naive": SeasonalNaiveEngine,
}


def create_engine(name: str) -> ForecastEngine:
    key = (name or "").strip().lower()
    if key in ENGINE_FACTORIES:
        return ENGINE_FACTORIES[key]()
    if key in ("timesfm25", "timesfm-2.5", "timesfm_2_5"):
        from forecasting.app.engines.timesfm25 import TimesFM25Engine

        return TimesFM25Engine()
    if key in ("timesfm3", "timesfm-3.0", "timesfm_3"):
        from forecasting.app.engines.timesfm3 import TimesFM3Engine

        return TimesFM3Engine()
    raise ValueError(f"unknown forecast engine: {name}")


__all__ = ["ForecastEngine", "NaiveEngine", "SeasonalNaiveEngine", "create_engine", "ENGINE_FACTORIES"]
