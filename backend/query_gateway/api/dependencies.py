"""FastAPI dependencies for internal auth."""

from __future__ import annotations

from typing import Annotated, Callable

from fastapi import Depends, Header, Request

from query_gateway.config.settings import get_settings
from query_gateway.domain.errors import (
    CONTRACT_VERSION_NOT_SUPPORTED,
    SERVICE_AUTHENTICATION_FAILED,
    GatewayError,
)
from query_gateway.infrastructure.auth.request_signature import verify_request_signature
from query_gateway.infrastructure.auth.service_token import validate_service_token
from query_gateway.infrastructure.redis.replay_guard import (
    InMemoryReplayStore,
    check_and_store_replay,
)

_replay_store: object | None = None


def get_replay_store():
    global _replay_store
    settings = get_settings()
    if _replay_store is not None:
        return _replay_store
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, socket_timeout=1, decode_responses=True)
        client.ping()
        _replay_store = client
    except Exception:
        if settings.replay_required and settings.auth_required:
            _replay_store = None
        else:
            _replay_store = InMemoryReplayStore()
    return _replay_store


def reset_replay_store() -> None:
    global _replay_store
    _replay_store = None


def internal_auth(required_scope: str) -> Callable:
    async def _dep(
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
        x_trace_id: Annotated[str | None, Header(alias="X-Trace-Id")] = None,
        x_timestamp: Annotated[str | None, Header(alias="X-Timestamp")] = None,
        x_body_sha256: Annotated[str | None, Header(alias="X-Body-SHA256")] = None,
        x_signature: Annotated[str | None, Header(alias="X-Signature")] = None,
        x_nanobase_contract_version: Annotated[
            str | None, Header(alias="X-Nanobase-Contract-Version")
        ] = None,
    ) -> dict:
        settings = get_settings()
        if (
            x_nanobase_contract_version
            and x_nanobase_contract_version != settings.contract_version
        ):
            raise GatewayError(
                CONTRACT_VERSION_NOT_SUPPORTED,
                "Sözleşme sürümü desteklenmiyor.",
                status=400,
            )

        if not settings.auth_required:
            return {"trace_id": x_trace_id or "", "request_id": x_request_id or "dev"}

        if not authorization or not authorization.lower().startswith("bearer "):
            raise GatewayError(
                SERVICE_AUTHENTICATION_FAILED, "Bearer token gerekli.", status=401
            )
        token = authorization.split(" ", 1)[1].strip()
        validate_service_token(token, settings, required_scope=required_scope)

        body = await request.body()
        if not all([x_request_id, x_timestamp, x_body_sha256, x_signature]):
            raise GatewayError(
                SERVICE_AUTHENTICATION_FAILED, "İmza başlıkları eksik.", status=401
            )

        verify_request_signature(
            settings,
            method=request.method,
            path=request.url.path,
            timestamp=x_timestamp or "",
            request_id=x_request_id or "",
            body_hash_header=x_body_sha256 or "",
            signature=x_signature or "",
            body=body,
        )
        check_and_store_replay(get_replay_store(), settings, x_request_id or "")
        return {"trace_id": x_trace_id or x_request_id or "", "request_id": x_request_id or ""}

    return _dep


AuthValidate = Depends(internal_auth("query.validate"))
AuthExecute = Depends(internal_auth("query.execute"))
