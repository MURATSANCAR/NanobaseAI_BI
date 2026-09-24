"""SeriesBundle / Forecast contracts (pydantic v2).

The LLM never sees or produces these. `nanobase_api` builds a SeriesBundle from
governed metric rows (SeriesBundleBuilder), the forecast service consumes it.
Every response carries `bundle_hash` + `engine@version` so a forecast can be
traced back to exactly the data and model that produced it.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Frequency = Literal["D", "W", "M", "Q", "Y"]
FREQUENCIES: tuple[str, ...] = ("D", "W", "M", "Q", "Y")
MissingPolicy = Literal["zero", "interpolate", "reject"]


class SeriesBundleError(Exception):
    """Fail-visible normalization error. `code` is stable for FE/i18n."""

    def __init__(self, code: str, message: str, **details: object) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "message": self.message, **self.details}


class SeriesPoint(BaseModel):
    timestamp: date
    value: float


class SeriesBundle(BaseModel):
    series_id: str
    metric: str
    dimension: dict[str, str] = Field(default_factory=dict)
    frequency: Frequency
    timezone: str = "Europe/Istanbul"
    history: list[SeriesPoint]
    horizon: int = Field(ge=1)
    target_unit: str | None = None
    missing_policy: MissingPolicy = "zero"
    return_quantiles: bool = True
    # Provenance / diagnostics filled by the builder
    filled_periods: list[date] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metric_version: int | None = None
    bundle_hash: str = ""


class ForecastPoint(BaseModel):
    timestamp: date
    p10: float
    p50: float
    p90: float


class ForecastRequest(BaseModel):
    bundle: SeriesBundle
    engine: str | None = None  # None → service default (benchmark-selected)


class ForecastResponse(BaseModel):
    series_id: str
    engine: str
    engine_version: str
    checkpoint_sha: str | None = None
    bundle_hash: str
    frequency: Frequency
    horizon: int
    forecast: list[ForecastPoint]
    warnings: list[str] = Field(default_factory=list)
    latency_ms: int = 0


# --- toplu aylık tahmin (POST /forecast/batch) ------------------------------------
# Yönetim raporları binlerce seriyi tek çağrıda ister; tek seri sözleşmesi (SeriesBundle) buna uygun değil.
# Yalnız aylık seriler. Eksik ay None gönderilir, motor ara değerle doldurur.

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"
QUANTILE_LEVELS: tuple[float, ...] = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


class BatchSeries(BaseModel):
    id: str = Field(min_length=1)
    start: str = Field(pattern=MONTH_PATTERN, description="values[0] ayı, YYYY-MM")
    values: list[float | None] = Field(min_length=1)


class SharedCovariate(BaseModel):
    """Bütün serilere ortak, yalnız geçmişte bilinen aylık seri (ör. portföy toplam satışı)."""

    start: str = Field(pattern=MONTH_PATTERN)
    values: list[float] = Field(min_length=1)


class BatchForecastRequest(BaseModel):
    horizon: int = Field(ge=1, le=36)
    series: list[BatchSeries] = Field(min_length=1)
    calendar: bool = Field(False, description="Ay sin/cos + zirve ayı işareti ek değişkeni (geçmiş ve gelecek)")
    calendar_peak_months: list[int] = Field(default_factory=list)
    shared_past: SharedCovariate | None = None
    engine: str | None = None


class BatchSeriesForecast(BaseModel):
    id: str
    start: str  # ilk tahmin ayı
    quantiles: list[list[float]]  # horizon × len(QUANTILE_LEVELS)


class BatchForecastResponse(BaseModel):
    engine: str
    engine_version: str
    checkpoint_sha: str | None = None
    horizon: int
    quantile_levels: list[float] = Field(default_factory=lambda: list(QUANTILE_LEVELS))
    results: list[BatchSeriesForecast]
    warnings: list[str] = Field(default_factory=list)
    latency_ms: int = 0
