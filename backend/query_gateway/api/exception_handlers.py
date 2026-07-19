from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from query_gateway.domain.errors import GatewayError


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(GatewayError)
    async def gateway_error_handler(_request: Request, exc: GatewayError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content=exc.to_dict())
