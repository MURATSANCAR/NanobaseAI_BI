"""TimesFM 3.0 (google-research/timesfm, PyTorch) — production engine.

Adapter for the `timesfm3` package installed from the upstream repository
(https://github.com/google-research/timesfm). API verified against timesfm
3.0.1 on the BI server (2026-09-06):

    from timesfm3 import ModelConfig, TimesFM3Evaluator
    cfg = ModelConfig(checkpoint_path=<hf id or local dir>, per_core_batch_size=1, device="cpu")
    outs = TimesFM3Evaluator(cfg).predict_batch([np.ndarray], horizon=h, return_quantiles=True, ...)
    outs[0].forecast   -> (>= h,)       point forecast
    outs[0].quantiles  -> (>= h, 9)     quantile levels 0.1 .. 0.9  (index 0 = p10, 4 = p50, 8 = p90)

The engine only ever receives a SeriesBundle — never raw rows, never LLM
output — and returns p10/p50/p90 per horizon step.

Licence: upstream 3.0 weights are published under a non-commercial licence.
Loading is gated behind FORECAST_ALLOW_NONCOMMERCIAL=1 so that the decision to
run them is explicit in the deployment env (set by deploy-forecast.sh).
"""

from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path

from forecasting.app.engines.base import EngineForecast, ForecastEngine
from forecasting.contracts.models import ForecastPoint, SeriesBundle

DEFAULT_MODEL_ID = "google/timesfm-3.0-pytorch"
QUANTILE_LEVELS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


def _env_flag(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


class TimesFM3Engine(ForecastEngine):
    name = "timesfm-3.0"
    version = "3.0"

    def __init__(self) -> None:
        self.model_id = os.environ.get("FORECAST_MODEL3_ID", DEFAULT_MODEL_ID)
        self._device = os.environ.get("FORECAST_DEVICE", "cpu")
        self._threads = int(os.environ.get("FORECAST_THREADS", "4"))
        self._batch = int(os.environ.get("FORECAST_BATCH", "1"))
        # Symmetric (flip-invariant) averaging doubles inference cost; off by default on the shared CPU host.
        self._symmetric = _env_flag("FORECAST_SYMMETRIC_AVERAGING", "0")
        # Context cap: TimesFM 3.0 accepts long contexts, but a monthly BI series never needs more than this.
        self._max_context = int(os.environ.get("FORECAST_MAX_CONTEXT", "4096"))
        self._model = None
        self._lock = threading.Lock()  # torch model is not re-entrant; FastAPI runs sync handlers in a threadpool

    @property
    def ready(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        if not _env_flag("FORECAST_ALLOW_NONCOMMERCIAL", "0"):
            raise RuntimeError(
                "TimesFM 3.0 weights are published under a non-commercial licence; "
                "set FORECAST_ALLOW_NONCOMMERCIAL=1 to load them."
            )
        if self._model is not None:
            return
        import torch
        from timesfm3 import ModelConfig, TimesFM3Evaluator

        torch.set_num_threads(self._threads)
        cfg = ModelConfig(checkpoint_path=self.model_id, per_core_batch_size=self._batch, device=self._device)
        self._model = TimesFM3Evaluator(cfg)
        self.checkpoint_sha = _checkpoint_sha(self.model_id)

    def forecast(self, bundle: SeriesBundle) -> EngineForecast:
        if self._model is None:
            self.load()
        import numpy as np

        warnings: list[str] = []
        values = [p.value for p in bundle.history]
        if len(values) > self._max_context:
            warnings.append(f"context_truncated:{len(values)}>{self._max_context}")
            values = values[-self._max_context :]
        y = np.asarray(values, dtype=np.float32)
        h = bundle.horizon
        with self._lock:
            outs = list(
                self._model.predict_batch(
                    [y],
                    horizon=h,
                    return_quantiles=True,
                    use_symmetric_averaging=self._symmetric,
                    make_positive=True,
                    sort_quantiles=True,
                )
            )
        out = outs[0]
        q = np.asarray(out.quantiles, dtype=np.float64)
        if q.ndim == 3:  # (1, horizon, n_q) → (horizon, n_q)
            q = q[0]
        if q.ndim != 2 or q.shape[0] < h:
            raise RuntimeError(f"unexpected TimesFM3 quantile shape {q.shape} for horizon {h}")
        n_q = q.shape[1]
        i10, i50, i90 = (0, 4, 8) if n_q == len(QUANTILE_LEVELS) else (0, n_q // 2, n_q - 1)
        p10 = self._clip_floor([float(v) for v in q[:h, i10]], bundle)
        p50 = self._clip_floor([float(v) for v in q[:h, i50]], bundle)
        p90 = self._clip_floor([float(v) for v in q[:h, i90]], bundle)
        ts = self._timestamps(bundle)
        pts = [ForecastPoint(timestamp=t, p10=a, p50=b, p90=c) for t, a, b, c in zip(ts, p10, p50, p90)]
        return EngineForecast(points=pts, warnings=warnings)


def _checkpoint_sha(model_id: str) -> str | None:
    """Provenance: sha256 prefix of the checkpoint safetensors (local dir or HF cache)."""
    try:
        path: Path | None = None
        local = Path(model_id)
        if local.is_dir():
            cands = sorted(local.glob("*.safetensors")) or sorted(local.rglob("*.safetensors"))
            path = cands[0] if cands else None
        else:
            from huggingface_hub import try_to_load_from_cache

            p = try_to_load_from_cache(model_id, "model.safetensors")
            if isinstance(p, str) and Path(p).is_file():
                path = Path(p)
        if path is None:
            return None
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    except Exception:  # noqa: BLE001 — provenance is best-effort
        return None
