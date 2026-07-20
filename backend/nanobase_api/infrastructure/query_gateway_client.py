"""Authenticated Query Gateway client (JWT + HMAC + replay-safe request ids)."""

from __future__ import annotations

import hashlib
import hmac
import os
import time
import uuid
from typing import Any

import httpx
import jwt


class QueryGatewayClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        jwt_secret: str | None = None,
        hmac_secret: str | None = None,
        timeout_s: float = 60.0,
        use_internal: bool | None = None,
    ) -> None:
        self.base = (base_url or os.environ.get("QUERY_GATEWAY_BASE", "http://127.0.0.1:8792")).rstrip(
            "/"
        )
        self.jwt_secret = jwt_secret or os.environ.get("QG_SERVICE_JWT_SECRET") or os.environ.get(
            "QG_HMAC_SECRET", ""
        )
        self.hmac_secret = hmac_secret or os.environ.get("QG_HMAC_SECRET") or self.jwt_secret
        self.timeout_s = timeout_s
        self.use_internal = (
            use_internal
            if use_internal is not None
            else os.environ.get("QG_USE_INTERNAL_API", "true").lower() in ("1", "true", "yes")
        )
        self.issuer = os.environ.get("QG_JWT_ISSUER", "nanobase-backend")
        self.audience = os.environ.get("QG_JWT_AUDIENCE", "nanobase-query-gateway")

    def _mint(self, scopes: list[str], jti: str) -> str:
        now = int(time.time())
        payload = {
            "iss": self.issuer,
            "aud": self.audience,
            "sub": "nanobase-backend",
            "jti": jti,
            "iat": now,
            "exp": now + 60,
            "scope": scopes,
        }
        return jwt.encode(payload, self.jwt_secret, algorithm="HS256")

    def _headers(self, method: str, path: str, body: bytes, scope: str) -> dict[str, str]:
        request_id = str(uuid.uuid4())
        ts = str(int(time.time()))
        body_hash = hashlib.sha256(body).hexdigest()
        msg = "\n".join([method.upper(), path, ts, request_id, body_hash])
        sig = hmac.new(self.hmac_secret.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()
        token = self._mint([scope], request_id)
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Request-Id": request_id,
            "X-Trace-Id": request_id,
            "X-Timestamp": ts,
            "X-Body-SHA256": body_hash,
            "X-Signature": sig,
            "X-Nanobase-Contract-Version": "1",
        }

    async def validate(
        self,
        *,
        sql: str,
        datasource_id: str,
        execution_id: str | None = None,
        tenant_id: str | None = None,
        client: httpx.AsyncClient | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.use_internal or not self.jwt_secret:
            # Legacy unauthenticated path
            async with httpx.AsyncClient(timeout=self.timeout_s) as c:
                payload_legacy: dict[str, Any] = {"datasource_id": datasource_id, "sql": sql}
                if parameters:
                    payload_legacy["parameters"] = parameters
                r = await (client or c).post(
                    f"{self.base}/api/v1/query/validate",
                    json=payload_legacy,
                )
                r.raise_for_status()
                return r.json()

        path = "/internal/v1/queries/validate"
        payload: dict[str, Any] = {
            "executionId": execution_id or str(uuid.uuid4()),
            "datasourceId": datasource_id,
            "tenantId": tenant_id,
            "sql": sql,
            "purpose": "INTERACTIVE_ANALYSIS",
        }
        if parameters:
            payload["parameters"] = parameters
        import json

        body = json.dumps(payload).encode("utf-8")
        headers = self._headers("POST", path, body, "query.validate")
        own = client is None
        c = client or httpx.AsyncClient(timeout=self.timeout_s)
        try:
            r = await c.post(f"{self.base}{path}", content=body, headers=headers)
            if r.status_code >= 400:
                return {"ok": False, "status": "REJECTED", **_safe_json(r)}
            data = r.json()
            data["ok"] = data.get("status") == "APPROVED"
            data["sql"] = data.get("normalizedSql") or sql
            return data
        finally:
            if own:
                await c.aclose()

    async def execute(
        self,
        *,
        sql: str,
        datasource_id: str,
        execution_id: str | None = None,
        tenant_id: str | None = None,
        explain: bool = False,
        client: httpx.AsyncClient | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.use_internal or not self.jwt_secret:
            async with httpx.AsyncClient(timeout=self.timeout_s) as c:
                payload_legacy: dict[str, Any] = {
                    "datasource_id": datasource_id,
                    "sql": sql,
                    "explain": explain,
                }
                if parameters:
                    payload_legacy["parameters"] = parameters
                r = await (client or c).post(
                    f"{self.base}/api/v1/query/execute",
                    json=payload_legacy,
                )
                r.raise_for_status()
                return r.json()

        if explain:
            # EXPLAIN still via legacy for display plans
            async with httpx.AsyncClient(timeout=self.timeout_s) as c:
                payload_ex: dict[str, Any] = {
                    "datasource_id": datasource_id,
                    "sql": sql,
                    "explain": True,
                }
                if parameters:
                    payload_ex["parameters"] = parameters
                r = await (client or c).post(
                    f"{self.base}/api/v1/query/execute",
                    json=payload_ex,
                )
                r.raise_for_status()
                return r.json()

        path = "/internal/v1/queries/execute"
        payload = {
            "executionId": execution_id or str(uuid.uuid4()),
            "datasourceId": datasource_id,
            "tenantId": tenant_id,
            "sql": sql,
            "purpose": "INTERACTIVE_ANALYSIS",
        }
        if parameters:
            payload["parameters"] = parameters
        import json

        body = json.dumps(payload).encode("utf-8")
        headers = self._headers("POST", path, body, "query.execute")
        own = client is None
        c = client or httpx.AsyncClient(timeout=self.timeout_s)
        try:
            r = await c.post(f"{self.base}{path}", content=body, headers=headers)
            if r.status_code >= 400:
                err = _safe_json(r)
                return {
                    "ok": False,
                    "status": "FAILED",
                    "code": err.get("code") or f"HTTP_{r.status_code}",
                    "message": err.get("message") or err.get("detail") or err.get("error") or r.text[:400],
                    "detail": err.get("detail") or err.get("message"),
                    "error": err.get("message") or err.get("detail") or err.get("error"),
                    "raw": err,
                    "http_status": r.status_code,
                }
            data = r.json()
            # Adapt to legacy shape used by chat_gateway
            cols = data.get("columns") or []
            if cols and isinstance(cols[0], dict):
                col_names = [c.get("name") for c in cols]
            else:
                col_names = cols
            return {
                "ok": data.get("status") == "SUCCESS",
                "sql": data.get("normalizedSql") or sql,
                "columns": col_names,
                "rows": data.get("rows") or [],
                "row_count": data.get("rowCount") or 0,
                "truncated": data.get("truncated") or False,
                "elapsed_ms": data.get("executionTimeMs") or data.get("gatewayTimeMs"),
                "executionId": data.get("executionId"),
                "policyVersion": data.get("policyVersion"),
                "raw": data,
            }
        finally:
            if own:
                await c.aclose()


def _safe_json(r: httpx.Response) -> dict[str, Any]:
    try:
        data = r.json()
        return data if isinstance(data, dict) else {"message": str(data)}
    except Exception:
        return {"message": r.text[:500], "code": "INTERNAL_ERROR"}
