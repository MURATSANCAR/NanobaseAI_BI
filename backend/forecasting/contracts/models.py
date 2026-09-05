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
