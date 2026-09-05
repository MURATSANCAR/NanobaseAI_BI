"""TimesFM 3.0 — benchmark-only (upstream weights are non-commercial /
non-production). Refuses to load unless FORECAST_ALLOW_NONCOMMERCIAL=1.
"""

from __future__ import annotations

import os

from forecasting.app.engines.base import EngineForecast, ForecastEngine
from forecasting.contracts.models import ForecastPoint, SeriesBundle

DEFAULT_MODEL_ID = "google/timesfm-3.0-pytorch"


class TimesFM3Engine(ForecastEngine):
    name = "timesfm-3.0"
    version = "3.0"

    def __init__(self) -> None:
        self.model_id = os.environ.get("FORECAST_MODEL3_ID", DEFAULT_MODEL_ID)
        self._model = None

    @property
    def ready(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        if os.environ.get("FORECAST_ALLOW_NONCOMMERCIAL") != "1":
            raise RuntimeError(
                "TimesFM 3.0 weights are non-commercial/non-production; set FORECAST_ALLOW_NONCOMMERCIAL=1 "
                "for offline benchmarking only."
            )
        if self._model is not None:
            return
        from timesfm import ModelConfig, TimesFM3Evaluator

        device = os.environ.get("FORECAST_DEVICE", "cpu")
        self._model = TimesFM3Evaluator(ModelConfig(checkpoint_path=self.model_id, per_core_batch_size=16, device=device))

    def forecast(self, bundle: SeriesBundle) -> EngineForecast:
        if self._model is None:
            self.load()
        import numpy as np

        y = np.asarray([p.value for p in bundle.history], dtype=np.float32)
        out = self._model.forecast(inputs=[y], horizon=bundle.horizon, return_quantiles=True)
        # Evaluator API shape is version-dependent; accept (point, quantiles) or dict.
        if isinstance(out, tuple):
            _, quantiles = out
            q = quantiles[0]
            p10, p50, p90 = q[:, 1], q[:, 5], q[:, 9]
        else:
            q = out["quantiles"][0]
            p10, p50, p90 = q[:, 1], q[:, 5], q[:, 9]
        ts = self._timestamps(bundle)
        pts = [
            ForecastPoint(timestamp=t, p10=float(a), p50=float(b), p90=float(c))
            for t, a, b, c in zip(ts, self._clip_floor(list(map(float, p10)), bundle), self._clip_floor(list(map(float, p50)), bundle), self._clip_floor(list(map(float, p90)), bundle))
        ]
        return EngineForecast(points=pts, warnings=["noncommercial_engine"])
