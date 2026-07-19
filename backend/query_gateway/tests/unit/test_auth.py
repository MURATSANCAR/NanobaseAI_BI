from __future__ import annotations

import time

import pytest

from query_gateway.config.settings import Settings, reset_settings
from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.auth.request_signature import sign_request, verify_request_signature
from query_gateway.infrastructure.auth.service_token import mint_service_token, validate_service_token
from query_gateway.infrastructure.redis.replay_guard import InMemoryReplayStore, check_and_store_replay


@pytest.fixture
def settings() -> Settings:
    reset_settings()
    return Settings(
        service_jwt_secret="test-secret",
        hmac_secret="test-secret",
        auth_required=True,
        replay_required=True,
    )


def test_jwt_audience_and_scope(settings: Settings):
    tok = mint_service_token(settings, scopes=["query.validate"], jti="1")
    validate_service_token(tok, settings, required_scope="query.validate")
    with pytest.raises(GatewayError):
        validate_service_token(tok, settings, required_scope="query.execute")


def test_signature_and_tamper(settings: Settings):
    body = b'{"sql":"SELECT 1"}'
    ts = str(int(time.time()))
    rid = "r1"
    sig = sign_request(
        settings, method="POST", path="/internal/v1/queries/validate", timestamp=ts, request_id=rid, body=body
    )
    from query_gateway.infrastructure.auth.request_signature import body_sha256

    verify_request_signature(
        settings,
        method="POST",
        path="/internal/v1/queries/validate",
        timestamp=ts,
        request_id=rid,
        body_hash_header=body_sha256(body),
        signature=sig,
        body=body,
    )
    with pytest.raises(GatewayError):
        verify_request_signature(
            settings,
            method="POST",
            path="/internal/v1/queries/validate",
            timestamp=ts,
            request_id=rid,
            body_hash_header=body_sha256(body),
            signature=sig,
            body=b'{"sql":"SELECT 2"}',
        )


def test_replay(settings: Settings):
    store = InMemoryReplayStore()
    check_and_store_replay(store, settings, "abc")
    with pytest.raises(GatewayError):
        check_and_store_replay(store, settings, "abc")
