from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from forecasting.contracts.builder import future_periods, seasonality
from forecasting.contracts.models import ForecastPoint, SeriesBundle

Z_80 = 1.2815515655446004  # two-sided 80% interval → p10/p90


def month_index(ym: str) -> int:
    """'YYYY-MM' → ay sırası (yıl*12 + ay − 1)."""
    return int(ym[:4]) * 12 + int(ym[5:7]) - 1


def month_str(i: int) -> str:
    return f"{i // 12}-{i % 12 + 1:02d}"


def calendar_covariates(start: int, n: int, peak_months: list[int]):
    """(3, n): ayın sinüs/kosinüsü ve zirve ayı işareti. Takvim gelecekte de bilinir."""
    import numpy as np

    m = (np.arange(start, start + n) % 12) + 1
    peak = np.isin(m, peak_months).astype(np.float32) if peak_months else np.zeros(n, np.float32)
    return np.stack([np.sin(2 * np.pi * m / 12), np.cos(2 * np.pi * m / 12), peak]).astype(np.float32)


def shared_past_slice(shared_start: int, shared_values: list[float], start: int, n: int):
    """(1, n): ortak serinin bu serinin aylarına denk gelen kısmı, log1p + seri içinde standartlaştırma.
    Ortak serinin kapsamadığı aylar NaN (motor ara değerle doldurur)."""
    import numpy as np

    out = np.full(n, np.nan, np.float64)
    for j in range(n):
        k = start + j - shared_start
        if 0 <= k < len(shared_values):
            out[j] = np.log1p(max(float(shared_values[k]), 0.0))
    ok = ~np.isnan(out)
    if ok.sum() >= 2:
        out[ok] = (out[ok] - out[ok].mean()) / (out[ok].std() + 1e-6)
    return out.astype(np.float32)[None, :]


@dataclass
class EngineForecast:
    points: list[ForecastPoint]
    warnings: list[str] = field(default_factory=list)


class ForecastEngine(ABC):
    name: str = "base"
    version: str = "0"
    checkpoint_sha: str | None = None

    def load(self) -> None:  # noqa: B027 — optional warm-up hook
        """Load weights; called once at service start for the default engine."""

    @property
    def ready(self) -> bool:
        return True

    @abstractmethod
    def forecast(self, bundle: SeriesBundle) -> EngineForecast: ...

    def forecast_batch(self, contexts: list, starts: list[int], horizon: int, *, calendar: bool = False,
                       peak_months: list[int] | None = None, shared: tuple[int, list[float]] | None = None) -> list:
        """Aylık seriler topluca → her seri için (horizon, 9) kantil dizisi (0.1 … 0.9).
        contexts: float dizileri (NaN = eksik ay), starts: her dizinin ilk ay sırası."""
        raise NotImplementedError(f"{self.name} toplu tahmin desteklemiyor")

    # --- shared helpers -------------------------------------------------------

    @staticmethod
    def _timestamps(bundle: SeriesBundle) -> list:
        return future_periods(bundle.history[-1].timestamp, bundle.frequency, bundle.horizon)

    @staticmethod
    def _season(bundle: SeriesBundle) -> int:
        return seasonality(bundle.frequency)

    @staticmethod
    def _clip_floor(values: list[float], bundle: SeriesBundle) -> list[float]:
        """Metrics whose history is entirely non-negative never forecast below 0."""
        if all(p.value >= 0 for p in bundle.history):
            return [max(0.0, v) for v in values]
        return values

    @staticmethod
    def _residual_sigma(residuals: list[float]) -> float:
        res = [r for r in residuals if not math.isnan(r)]
        if len(res) < 2:
            return 0.0
        mean = sum(res) / len(res)
        var = sum((r - mean) ** 2 for r in res) / (len(res) - 1)
        return math.sqrt(var)

    def _interval_points(
        self, bundle: SeriesBundle, point: list[float], sigma: float, *, widen: bool = True
    ) -> list[ForecastPoint]:
        ts = self._timestamps(bundle)
        lo, hi = [], []
        for h, v in enumerate(point, start=1):
            spread = Z_80 * sigma * (math.sqrt(h) if widen else 1.0)
            lo.append(v - spread)
            hi.append(v + spread)
        point = self._clip_floor(point, bundle)
        lo = self._clip_floor(lo, bundle)
        hi = self._clip_floor(hi, bundle)
        return [ForecastPoint(timestamp=t, p10=l, p50=p, p90=u) for t, l, p, u in zip(ts, lo, point, hi)]
