"""HMAC request signature."""

from __future__ import annotations

import hashlib
import hmac
import time

from query_gateway.config.settings import Settings
from query_gateway.domain.errors import REQUEST_SIGNATURE_INVALID, GatewayError


def body_sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def build_signing_string(
    method: str,
    path: str,
    timestamp: str,
    request_id: str,
    body_hash: str,
) -> str:
    return "\n".join([method.upper(), path, timestamp, request_id, body_hash])


def sign_request(
    settings: Settings,
    *,
    method: str,
    path: str,
    timestamp: str,
    request_id: str,
    body: bytes,
) -> str:
    if not settings.hmac_secret:
        raise GatewayError(REQUEST_SIGNATURE_INVALID, "HMAC secret yok.", status=503)
    digest = body_sha256(body)
    msg = build_signing_string(method, path, timestamp, request_id, digest)
    return hmac.new(
        settings.hmac_secret.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_request_signature(
    settings: Settings,
    *,
    method: str,
    path: str,
    timestamp: str,
    request_id: str,
    body_hash_header: str,
    signature: str,
    body: bytes,
) -> None:
    if not settings.hmac_secret:
        raise GatewayError(REQUEST_SIGNATURE_INVALID, "HMAC secret yok.", status=503)
    try:
        ts = int(timestamp)
    except ValueError as e:
        raise GatewayError(REQUEST_SIGNATURE_INVALID, "Geçersiz timestamp.", status=401) from e
    now = int(time.time())
    if abs(now - ts) > settings.timestamp_skew_s:
        raise GatewayError(REQUEST_SIGNATURE_INVALID, "Timestamp skew.", status=401)

    expected_hash = body_sha256(body)
    if not hmac.compare_digest(expected_hash, (body_hash_header or "").lower()):
        raise GatewayError(REQUEST_SIGNATURE_INVALID, "Body hash uyuşmuyor.", status=401)

    expected_sig = sign_request(
        settings,
        method=method,
        path=path,
        timestamp=timestamp,
        request_id=request_id,
        body=body,
    )
    if not hmac.compare_digest(expected_sig, (signature or "").lower()):
        raise GatewayError(REQUEST_SIGNATURE_INVALID, "İmza geçersiz.", status=401)
