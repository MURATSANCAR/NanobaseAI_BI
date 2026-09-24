"""Engine registry + forecast execution with provenance and a bundle-hash cache."""

from __future__ import annotations

import os
import time
from collections import OrderedDict

from forecasting.app.engines import create_engine
from forecasting.app.engines.base import ForecastEngine
from forecasting.app.engines.base import month_index, month_str
from forecasting.contracts.models import (
    BatchForecastRequest,
    BatchForecastResponse,
    BatchSeriesForecast,
    ForecastRequest,
    ForecastResponse,
    SeriesBundle,
)

DEFAULT_ENGINE = os.environ.get("FORECAST_ENGINE", "seasonal_naive")
_CACHE_MAX = int(os.environ.get("FORECAST_CACHE_MAX", "512"))


class ForecastService:
    def __init__(self, default_engine: str = DEFAULT_ENGINE) -> None:
        self.default_engine_name = default_engine
        self._engines: dict[str, ForecastEngine] = {}
        self._cache: OrderedDict[tuple[str, str], ForecastResponse] = OrderedDict()

    # --- engines --------------------------------------------------------------

    def engine(self, name: str | None = None) -> ForecastEngine:
        key = (name or self.default_engine_name).strip().lower()
        if key not in self._engines:
            self._engines[key] = create_engine(key)
        return self._engines[key]

    def warm(self) -> None:
        """Load the default engine at startup (health reports ready=false until done)."""
        self.engine().load()

    def status(self) -> dict:
        eng = self._engines.get(self.default_engine_name.lower())
        return {
            "default_engine": self.default_engine_name,
            "ready": bool(eng and eng.ready),
            "engines_loaded": {k: {"name": e.name, "version": e.version, "ready": e.ready} for k, e in self._engines.items()},
            "cache_entries": len(self._cache),
        }

    # --- forecast -------------------------------------------------------------

    def forecast(self, req: ForecastRequest) -> ForecastResponse:
        bundle: SeriesBundle = req.bundle
        eng = self.engine(req.engine)
        cache_key = (eng.name + "@" + eng.version, bundle.bundle_hash)
        if bundle.bundle_hash and cache_key in self._cache:
            hit = self._cache[cache_key]
            self._cache.move_to_end(cache_key)
            return hit.model_copy(update={"warnings": [*hit.warnings, "cache_hit"], "latency_ms": 0})
        t0 = time.perf_counter()
        out = eng.forecast(bundle)
        resp = ForecastResponse(
            series_id=bundle.series_id,
            engine=eng.name,
            engine_version=eng.version,
            checkpoint_sha=eng.checkpoint_sha,
            bundle_hash=bundle.bundle_hash,
            frequency=bundle.frequency,
            horizon=bundle.horizon,
            forecast=out.points,
            warnings=[*bundle.warnings, *out.warnings],
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )
        if bundle.bundle_hash:
            self._cache[cache_key] = resp
            while len(self._cache) > _CACHE_MAX:
                self._cache.popitem(last=False)
        return resp

    def forecast_batch(self, req: BatchForecastRequest) -> BatchForecastResponse:
        """Aylık seriler topluca. Önbellek yok: yönetim raporu günde bir çağırır."""
        eng = self.engine(req.engine)
        t0 = time.perf_counter()
        starts = [month_index(s.start) for s in req.series]
        contexts = [[float("nan") if v is None else float(v) for v in s.values] for s in req.series]
        shared = (month_index(req.shared_past.start), list(req.shared_past.values)) if req.shared_past else None
        try:
            outs = eng.forecast_batch(contexts, starts, req.horizon, calendar=req.calendar,
                                      peak_months=list(req.calendar_peak_months), shared=shared)
        except NotImplementedError as e:
            raise ValueError(str(e)) from e
        results = [
            BatchSeriesForecast(id=s.id, start=month_str(st + len(s.values)),
                                quantiles=[[round(float(x), 4) for x in row] for row in q])
            for s, st, q in zip(req.series, starts, outs)
        ]
        return BatchForecastResponse(engine=eng.name, engine_version=eng.version, checkpoint_sha=eng.checkpoint_sha,
                                     horizon=req.horizon, results=results,
                                     latency_ms=int((time.perf_counter() - t0) * 1000))
