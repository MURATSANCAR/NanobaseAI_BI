"""TimesFM 2.5 (200M, PyTorch, Apache-2.0) — production engine candidate.

Loaded lazily; the service reports `ready=false` until weights are in memory.
Quantiles come from the model's continuous quantile head (q10..q90). The
adapter only ever receives a SeriesBundle — never raw rows, never LLM output.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from forecasting.app.engines.base import EngineForecast, ForecastEngine
from forecasting.contracts.models import ForecastPoint, SeriesBundle

DEFAULT_MODEL_ID = "google/timesfm-2.5-200m-pytorch"


class TimesFM25Engine(ForecastEngine):
    name = "timesfm-2.5-200m"
    version = "2.5"

    def __init__(self) -> None:
        self.model_id = os.environ.get("FORECAST_MODEL_ID", DEFAULT_MODEL_ID)
        self._model = None
        self._threads = int(os.environ.get("FORECAST_THREADS", "4"))

    @property
    def ready(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        if self._model is not None:
            return
        import numpy as np  # noqa: F401
        import timesfm
        import torch

        torch.set_num_threads(self._threads)
        model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(self.model_id)
        model.compile(
            timesfm.ForecastConfig(
                max_context=1024,
                max_horizon=64,
                normalize_inputs=True,
                use_continuous_quantile_head=True,
                force_flip_invariance=True,
                infer_is_positive=True,
                fix_quantile_crossing=True,
            )
        )
        self._model = model
        self.checkpoint_sha = _checkpoint_sha(self.model_id)

    def forecast(self, bundle: SeriesBundle) -> EngineForecast:
        if self._model is None:
            self.load()
        import numpy as np

        y = np.asarray([p.value for p in bundle.history], dtype=np.float32)
        point, quantiles = self._model.forecast(horizon=bundle.horizon, inputs=[y])
        # quantiles: (n_series, horizon, 10) → index 0 = mean, 1..9 = q10..q90
        q = quantiles[0]
        ts = self._timestamps(bundle)
        p10 = self._clip_floor([float(v) for v in q[:, 1]], bundle)
        p50 = self._clip_floor([float(v) for v in q[:, 5]], bundle)
        p90 = self._clip_floor([float(v) for v in q[:, 9]], bundle)
        pts = [ForecastPoint(timestamp=t, p10=a, p50=b, p90=c) for t, a, b, c in zip(ts, p10, p50, p90)]
        return EngineForecast(points=pts)


def _checkpoint_sha(model_id: str) -> str | None:
    """Best-effort: hash the safetensors file in the HF cache for provenance."""
    try:
        from huggingface_hub import try_to_load_from_cache

        p = try_to_load_from_cache(model_id, "model.safetensors")
        if isinstance(p, str) and Path(p).is_file():
            h = hashlib.sha256()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            return h.hexdigest()[:16]
    except Exception:
        return None
    return None
