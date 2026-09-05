"""HTTP client for the NanobaseAI BI Forecast API (plan Faz 3.5).

No retry: a forecast is deterministic and expensive; a failure is surfaced,
not silently recomputed.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from forecasting.contracts.models import ForecastResponse, SeriesBundle

FORECAST_API_BASE = os.environ.get("FORECAST_API_BASE", "http://127.0.0.1:8793").rstrip("/")


class ForecastError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ForecastClient:
    def __init__(self, base: str | None = None, timeout_s: float = 30.0) -> None:
        self.base = (base or FORECAST_API_BASE).rstrip("/")
        self.timeout_s = timeout_s

    async def health(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get(f"{self.base}/health")
                data = r.json() if r.content else {}
                data.setdefault("ready", r.status_code == 200)
                return data
        except Exception as e:  # noqa: BLE001
            return {"ready": False, "error": f"{type(e).__name__}: {e}"}

    async def forecast(self, bundle: SeriesBundle, *, engine: str | None = None) -> ForecastResponse:
        payload: dict[str, Any] = {"bundle": bundle.model_dump(mode="json")}
        if engine:
            payload["engine"] = engine
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as c:
                r = await c.post(f"{self.base}/forecast", json=payload)
        except httpx.HTTPError as e:
            raise ForecastError("FORECAST_UNAVAILABLE", f"Tahmin servisine ulaşılamadı: {e}") from e
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail")
            except Exception:  # noqa: BLE001
                detail = None
            if isinstance(detail, dict):
                raise ForecastError(str(detail.get("code") or f"HTTP_{r.status_code}"), str(detail.get("message") or r.text[:300]))
            raise ForecastError(f"HTTP_{r.status_code}", str(detail or r.text[:300]))
        return ForecastResponse.model_validate(r.json())
