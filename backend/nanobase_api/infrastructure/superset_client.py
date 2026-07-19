"""Apache Superset REST client + guest token minting (production analytics canvas)."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

from nanobase_api.config import get_settings

log = logging.getLogger(__name__)


class SupersetError(Exception):
    def __init__(self, code: str, message: str, status: int = 502) -> None:
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


@dataclass
class _Auth:
    access_token: str
    refresh_token: str | None
    expires_at: float


class SupersetClient:
    def __init__(self) -> None:
        s = get_settings()
        self.enabled = s.superset_enabled
        self.base = (s.superset_url or "").rstrip("/")
        self.public_url = (s.superset_public_url or self.base).rstrip("/")
        self.username = s.superset_username
        self.password = s.superset_password
        self.guest_secret = s.superset_guest_secret
        self.guest_audience = s.superset_guest_audience
        self.guest_ttl_min = s.superset_guest_ttl_min
        self.embed_domains = s.superset_embed_domains
        self._auth: _Auth | None = None

    def configured(self) -> bool:
        return bool(
            self.enabled
            and self.base
            and self.username
            and self.password
            and self.guest_secret
            and len(self.guest_secret) >= 16
        )

    async def health(self) -> dict[str, Any]:
        if not self.configured():
            return {
                "ok": False,
                "message": "analytics_not_configured",
                "dashboard_count": 0,
            }
        try:
            await self._ensure_auth()
            data = await self._get("/api/v1/dashboard/", params={"q": "(page:0,page_size:1)"})
            count = int((data.get("count") if isinstance(data, dict) else 0) or 0)
            return {"ok": True, "message": "up", "dashboard_count": count}
        except Exception as e:
            log.warning("superset health failed: %s", e)
            return {"ok": False, "message": str(e)[:200], "dashboard_count": 0}

    async def list_dashboards(self) -> list[dict[str, Any]]:
        await self._ensure_auth()
        data = await self._get("/api/v1/dashboard/", params={"q": "(page:0,page_size:100,order_column:changed_on,order_direction:desc)"})
        rows = (data.get("result") if isinstance(data, dict) else None) or []
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "id": int(r.get("id")),
                    "title": r.get("dashboard_title") or r.get("slug") or f"Dashboard {r.get('id')}",
                    "chart_count": len(r.get("charts") or []) if isinstance(r.get("charts"), list) else r.get("chart_count"),
                    "changed_on": r.get("changed_on_utc") or r.get("changed_on"),
                    "changed_on_delta": r.get("changed_on_delta_humanized"),
                    "status": r.get("status"),
                    "published": r.get("published"),
                }
            )
        return out

    async def list_charts(self) -> list[dict[str, Any]]:
        await self._ensure_auth()
        data = await self._get("/api/v1/chart/", params={"q": "(page:0,page_size:100)"})
        rows = (data.get("result") if isinstance(data, dict) else None) or []
        return [
            {
                "id": int(r.get("id")),
                "title": r.get("slice_name") or f"Chart {r.get('id')}",
                "viz_type": r.get("viz_type"),
            }
            for r in rows
            if r.get("id") is not None
        ]

    async def list_datasets(self) -> list[dict[str, Any]]:
        await self._ensure_auth()
        data = await self._get("/api/v1/dataset/", params={"q": "(page:0,page_size:100)"})
        rows = (data.get("result") if isinstance(data, dict) else None) or []
        return [
            {
                "id": int(r.get("id")),
                "table_name": r.get("table_name") or r.get("datasource_name"),
            }
            for r in rows
            if r.get("id") is not None
        ]

    async def create_dashboard(self, title: str) -> dict[str, Any]:
        await self._ensure_auth()
        created = await self._post(
            "/api/v1/dashboard/",
            json={"dashboard_title": title or "NanobaseAI Panel", "published": True},
        )
        dash_id = int((created.get("id") if isinstance(created, dict) else None) or (created.get("result") or {}).get("id"))
        embed_uuid = await self.ensure_embedded(dash_id)
        guest = await self.mint_guest_token(dash_id, embed_uuid=embed_uuid)
        return {
            "id": dash_id,
            "title": title or "NanobaseAI Panel",
            "embed_uuid": embed_uuid,
            "guest": guest,
        }

    async def ensure_embedded(self, dashboard_id: int) -> str:
        await self._ensure_auth()
        # Try read existing
        try:
            existing = await self._get(f"/api/v1/dashboard/{dashboard_id}/embedded")
            result = existing.get("result") if isinstance(existing, dict) else None
            if isinstance(result, dict) and result.get("uuid"):
                return str(result["uuid"])
        except SupersetError:
            pass
        # Enable embedding
        body = {"allowed_domains": self.embed_domains}
        data = await self._post(f"/api/v1/dashboard/{dashboard_id}/embedded", json=body)
        result = data.get("result") if isinstance(data, dict) else None
        if isinstance(result, dict) and result.get("uuid"):
            return str(result["uuid"])
        # Some versions return uuid at top level
        if isinstance(data, dict) and data.get("uuid"):
            return str(data["uuid"])
        raise SupersetError("EMBED_ENABLE_FAILED", "Could not enable dashboard embedding")

    async def mint_guest_token(self, dashboard_id: int, *, embed_uuid: str | None = None) -> dict[str, Any]:
        await self._ensure_auth()
        euuid = embed_uuid or await self.ensure_embedded(dashboard_id)

        # Prefer Superset native guest_token API when available
        try:
            payload = {
                "user": {
                    "username": "nanobase_embed",
                    "first_name": "Nanobase",
                    "last_name": "Embed",
                },
                "resources": [{"type": "dashboard", "id": str(euuid)}],
                "rls": [],
            }
            data = await self._post("/api/v1/security/guest_token/", json=payload)
            token = data.get("token") if isinstance(data, dict) else None
            if token:
                return {
                    "token": str(token),
                    "dashboard_id": int(dashboard_id),
                    "embed_uuid": euuid,
                    "analytics_url": self.public_url,
                }
        except SupersetError as e:
            log.info("superset guest_token API unavailable, minting local JWT: %s", e)

        # Local JWT fallback (must match GUEST_TOKEN_JWT_SECRET / AUDIENCE)
        now = int(time.time())
        claims = {
            "user": {
                "username": "nanobase_embed",
                "first_name": "Nanobase",
                "last_name": "Embed",
            },
            "resources": [{"type": "dashboard", "id": str(euuid)}],
            "rls_rules": [],
            "iat": now,
            "exp": now + int(self.guest_ttl_min * 60),
            "aud": self.guest_audience,
            "type": "guest",
        }
        token = jwt.encode(claims, self.guest_secret, algorithm="HS256")
        if isinstance(token, bytes):
            token = token.decode("utf-8")
        return {
            "token": token,
            "dashboard_id": int(dashboard_id),
            "embed_uuid": euuid,
            "analytics_url": self.public_url,
        }

    async def dashboard_charts(self, dashboard_id: int) -> list[dict[str, Any]]:
        await self._ensure_auth()
        data = await self._get(f"/api/v1/dashboard/{dashboard_id}")
        result = (data.get("result") if isinstance(data, dict) else None) or {}
        charts = result.get("charts") or []
        # charts may be list of names or ids depending on version — also try slices
        out: list[dict[str, Any]] = []
        position = result.get("position_json") or result.get("position") or {}
        # Prefer chart endpoint filtered by dashboard
        try:
            listed = await self._get(
                "/api/v1/chart/",
                params={"q": f"(filters:!((col:dashboards,opr:rel_m_m,value:{dashboard_id})),page:0,page_size:100)"},
            )
            for r in (listed.get("result") or []):
                out.append(
                    {
                        "id": int(r["id"]),
                        "title": r.get("slice_name"),
                        "viz_type": r.get("viz_type"),
                    }
                )
            if out:
                return out
        except SupersetError:
            pass
        for i, c in enumerate(charts):
            if isinstance(c, dict) and c.get("id") is not None:
                out.append({"id": int(c["id"]), "title": c.get("slice_name") or c.get("title"), "viz_type": c.get("viz_type")})
            elif isinstance(c, str):
                out.append({"id": i, "title": c})
        _ = position
        return out

    async def pin_sql_chart(
        self,
        dashboard_id: int,
        *,
        sql: str,
        title: str = "NanobaseAI Chart",
        viz_type: str = "table",
    ) -> dict[str, Any]:
        """Best-effort: create a table chart from SQL and attach to dashboard."""
        await self._ensure_auth()
        # Need a database id — pick first
        dbs = await self._get("/api/v1/database/", params={"q": "(page:0,page_size:20)"})
        db_rows = (dbs.get("result") if isinstance(dbs, dict) else None) or []
        if not db_rows:
            raise SupersetError(
                "NO_DATABASE",
                "Superset'te bağlı veritabanı yok. Önce analytics DB bağlantısını ekleyin.",
                status=400,
            )
        database_id = int(db_rows[0]["id"])
        # Create / reuse SQL lab dataset via dataset API (virtual)
        ds_name = f"nanobase_pin_{uuid.uuid4().hex[:10]}"
        try:
            ds = await self._post(
                "/api/v1/dataset/",
                json={
                    "database": database_id,
                    "schema": None,
                    "table_name": ds_name,
                    "sql": sql,
                    "is_managed_externally": False,
                },
            )
            dataset_id = int((ds.get("id") if isinstance(ds, dict) else None) or (ds.get("result") or {}).get("id"))
        except SupersetError as e:
            raise SupersetError(
                "PIN_DATASET_FAILED",
                f"Chart için dataset oluşturulamadı: {e.message}",
                status=400,
            ) from e

        chart = await self._post(
            "/api/v1/chart/",
            json={
                "slice_name": title or "NanobaseAI Chart",
                "viz_type": viz_type or "table",
                "datasource_id": dataset_id,
                "datasource_type": "table",
                "params": "{}",
                "query_context": None,
                "dashboards": [dashboard_id],
            },
        )
        chart_id = int((chart.get("id") if isinstance(chart, dict) else None) or (chart.get("result") or {}).get("id"))
        embed_uuid = await self.ensure_embedded(dashboard_id)
        guest = await self.mint_guest_token(dashboard_id, embed_uuid=embed_uuid)
        return {
            "action": "pin",
            "dashboard_id": dashboard_id,
            "charts": [{"id": chart_id, "title": title}],
            "embed_uuid": embed_uuid,
            "guest": guest,
            "count": 1,
        }

    async def remove_chart(self, dashboard_id: int, chart_id: int) -> dict[str, Any]:
        await self._ensure_auth()
        # Detach: update chart dashboards list / delete chart
        try:
            await self._delete(f"/api/v1/chart/{chart_id}")
        except SupersetError:
            # try update without dashboard
            try:
                await self._put(f"/api/v1/chart/{chart_id}", json={"dashboards": []})
            except SupersetError as e:
                raise SupersetError("REMOVE_CHART_FAILED", e.message, status=400) from e
        embed_uuid = await self.ensure_embedded(dashboard_id)
        charts = await self.dashboard_charts(dashboard_id)
        return {
            "dashboard_id": dashboard_id,
            "chart_ids": [c["id"] for c in charts],
            "embed_uuid": embed_uuid,
        }

    async def reorder_layout(self, dashboard_id: int, chart_ids: list[int]) -> dict[str, Any]:
        await self._ensure_auth()
        # Minimal: accept order and return current embed — full position_json rewrite is version-specific
        embed_uuid = await self.ensure_embedded(dashboard_id)
        return {
            "dashboard_id": dashboard_id,
            "chart_ids": [int(x) for x in chart_ids],
            "embed_uuid": embed_uuid,
        }

    async def _ensure_auth(self) -> None:
        if not self.configured():
            raise SupersetError("analytics_not_configured", "Analytics engine is not configured", status=503)
        if self._auth and self._auth.expires_at > time.time() + 30:
            return
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{self.base}/api/v1/security/login",
                json={
                    "username": self.username,
                    "password": self.password,
                    "provider": "db",
                    "refresh": True,
                },
            )
            if r.status_code >= 400:
                raise SupersetError(
                    "SUPERSET_LOGIN_FAILED",
                    f"Superset login failed ({r.status_code})",
                    status=502,
                )
            data = r.json()
            access = data.get("access_token")
            if not access:
                raise SupersetError("SUPERSET_LOGIN_FAILED", "No access_token from Superset", status=502)
            self._auth = _Auth(
                access_token=str(access),
                refresh_token=data.get("refresh_token"),
                expires_at=time.time() + 50 * 60,
            )

    def _headers(self) -> dict[str, str]:
        assert self._auth
        return {
            "Authorization": f"Bearer {self._auth.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _get(self, path: str, params: dict | None = None) -> Any:
        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.get(f"{self.base}{path}", headers=self._headers(), params=params)
            if r.status_code == 401:
                self._auth = None
                await self._ensure_auth()
                r = await client.get(f"{self.base}{path}", headers=self._headers(), params=params)
            if r.status_code >= 400:
                raise SupersetError("SUPERSET_API_ERROR", r.text[:300], status=502)
            return r.json() if r.content else {}

    async def _post(self, path: str, json: dict | None = None) -> Any:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(f"{self.base}{path}", headers=self._headers(), json=json or {})
            if r.status_code == 401:
                self._auth = None
                await self._ensure_auth()
                r = await client.post(f"{self.base}{path}", headers=self._headers(), json=json or {})
            if r.status_code >= 400:
                raise SupersetError("SUPERSET_API_ERROR", r.text[:300], status=502)
            return r.json() if r.content else {}

    async def _put(self, path: str, json: dict | None = None) -> Any:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.put(f"{self.base}{path}", headers=self._headers(), json=json or {})
            if r.status_code >= 400:
                raise SupersetError("SUPERSET_API_ERROR", r.text[:300], status=502)
            return r.json() if r.content else {}

    async def _delete(self, path: str) -> Any:
        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.delete(f"{self.base}{path}", headers=self._headers())
            if r.status_code >= 400:
                raise SupersetError("SUPERSET_API_ERROR", r.text[:300], status=502)
            return r.json() if r.content else {}


_CLIENT: SupersetClient | None = None


def get_superset_client() -> SupersetClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = SupersetClient()
    return _CLIENT


def reset_superset_client_for_tests() -> None:
    global _CLIENT
    _CLIENT = None
