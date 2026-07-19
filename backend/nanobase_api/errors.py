"""Standard API error envelope (Faz 3)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: list[Any] | None = None,
        trace_id: str | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or []
        self.trace_id = trace_id or str(uuid.uuid4())
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "traceId": self.trace_id,
            "details": self.details,
        }


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(exc.to_dict(), status_code=exc.status_code)


async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    tid = str(uuid.uuid4())
    return JSONResponse(
        {
            "code": "INTERNAL_ERROR",
            "message": "Beklenmeyen bir hata oluştu.",
            "traceId": tid,
            "details": [],
        },
        status_code=500,
    )
