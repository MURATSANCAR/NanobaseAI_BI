"""NanobaseAI BI Forecast API (:8793).

POST /forecast   SeriesBundle → p10/p50/p90 per horizon step (+ provenance)
GET  /health     ready gate (default engine loaded)
GET  /engines    engines available in this build
"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from forecasting.app.engines import ENGINE_FACTORIES
from forecasting.app.service import ForecastService
from forecasting.contracts.models import ForecastRequest, ForecastResponse

log = logging.getLogger("nanobaseai.forecast")
service = ForecastService()
_warm_error: dict[str, str] = {}


def _warm() -> None:
    try:
        service.warm()
        log.info("forecast engine ready: %s", service.default_engine_name)
    except Exception as e:  # noqa: BLE001 — surfaced via /health
        _warm_error["error"] = f"{type(e).__name__}: {e}"
        log.exception("forecast engine warm-up failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if os.environ.get("FORECAST_WARM", "1") == "1":
        threading.Thread(target=_warm, name="forecast-warm", daemon=True).start()
    yield


app = FastAPI(title="NanobaseAI BI Forecast API", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> JSONResponse:
    st = service.status()
    st["service"] = "nanobaseai-bi-forecast"
    if _warm_error:
        st["error"] = _warm_error["error"]
    return JSONResponse(st, status_code=200 if st["ready"] else 503)


@app.get("/engines")
def engines() -> dict:
    return {
        "default": service.default_engine_name,
        "available": [*ENGINE_FACTORIES.keys(), "timesfm25", "timesfm3"],
        "loaded": service.status()["engines_loaded"],
    }


@app.post("/forecast", response_model=ForecastResponse)
def forecast(req: ForecastRequest) -> ForecastResponse:
    if not req.bundle.history:
        raise HTTPException(status_code=422, detail={"code": "INSUFFICIENT_HISTORY", "message": "history boş"})
    try:
        return service.forecast(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": "UNKNOWN_ENGINE", "message": str(e)}) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail={"code": "ENGINE_UNAVAILABLE", "message": str(e)}) from e
