"""Authenticated, read-only Editor control API; never starts a model or worker."""
from __future__ import annotations

import hmac
import os
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query

from . import foundation
from .config import settings


def authorize(authorization: str = Header(default="")) -> None:
    expected = settings().gateway_internal_key
    given = authorization.removeprefix("Bearer ").strip()
    if not expected or not hmac.compare_digest(given, expected):
        raise HTTPException(401, "unauthorized")


app = FastAPI(title="Editor control", docs_url=None, redoc_url=None,
    openapi_url=None, dependencies=[Depends(authorize)])


@app.get("/health")
def health():
    result = foundation.runtime_status()
    return {"ok": True, "maintenance": result["control"]["maintenance"],
        "code_version": os.environ.get("EDITOR_CODE_VERSION", "unknown"),
        "mode": "foundation_only"}


@app.get("/v1/runtime")
def runtime():
    return foundation.runtime_status()


@app.get("/v1/generations")
def generations(limit: int = Query(default=100, ge=1, le=100)):
    return foundation.generations(limit)


@app.get("/v1/generations/{generation_id}/readiness")
def readiness(generation_id: UUID):
    try:
        return foundation.readiness(str(generation_id))
    except KeyError:
        raise HTTPException(404, "generation not found") from None


@app.get("/v1/generations/{generation_id}/records/{kind}")
def records(generation_id: UUID, kind: Literal["claims", "events", "emotions"],
            limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)):
    try:
        return foundation.read_records(str(generation_id),kind,limit,offset)
    except KeyError:
        raise HTTPException(404, "generation not found") from None
