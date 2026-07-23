"""Analytics (Superset) API contract tests — offline / disabled + guest JWT mint."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure settings cache is fresh per test
os.environ.pop("BI_SUPERSET_ENABLED", None)


@pytest.fixture(autouse=True)
def _reset_settings_and_client():
    from nanobase_api.config import get_settings
    from nanobase_api.infrastructure.superset_client import reset_superset_client_for_tests

    get_settings.cache_clear()
    reset_superset_client_for_tests()
    yield
    get_settings.cache_clear()
    reset_superset_client_for_tests()


def _app_client() -> TestClient:
    from nanobase_api.analytics_api import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_status_disabled_by_default():
    c = _app_client()
    r = c.get("/api/v1/bi/analytics/status")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["health"]["ok"] is False


def test_lists_shaped_when_disabled():
    c = _app_client()
    assert c.get("/api/v1/bi/analytics/dashboards").json() == {"dashboards": []}
    assert c.get("/api/v1/bi/analytics/charts").json() == {"charts": []}
    assert c.get("/api/v1/bi/analytics/datasets").json() == {"datasets": []}


def test_guest_token_503_when_disabled():
    c = _app_client()
    r = c.post("/api/v1/bi/analytics/guest-token/1")
    assert r.status_code == 503


def test_local_guest_jwt_mint():
    secret = "unit_test_guest_jwt_secret_32chars!!"
    os.environ["BI_SUPERSET_ENABLED"] = "1"
    os.environ["BI_SUPERSET_URL"] = "http://superset.test"
    os.environ["BI_SUPERSET_PUBLIC_URL"] = "https://portal.test:8443"
    os.environ["BI_SUPERSET_USERNAME"] = "svc"
    os.environ["BI_SUPERSET_PASSWORD"] = "pw"
    os.environ["BI_SUPERSET_GUEST_SECRET"] = secret
    os.environ["BI_SUPERSET_GUEST_AUDIENCE"] = "http://0.0.0.0:8080/"
    from nanobase_api.config import get_settings
    from nanobase_api.infrastructure.superset_client import reset_superset_client_for_tests

    get_settings.cache_clear()
    reset_superset_client_for_tests()

    with patch(
        "nanobase_api.infrastructure.superset_client.SupersetClient._ensure_auth",
        new_callable=AsyncMock,
    ), patch(
        "nanobase_api.infrastructure.superset_client.SupersetClient.ensure_embedded",
        new_callable=AsyncMock,
        return_value="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    ), patch(
        "nanobase_api.infrastructure.superset_client.SupersetClient._post",
        new_callable=AsyncMock,
        side_effect=Exception("no guest api"),
    ):
        # Force local JWT path: make guest_token API raise SupersetError
        from nanobase_api.infrastructure.superset_client import SupersetError

        async def _post_fail(*_a, **_k):
            raise SupersetError("SUPERSET_API_ERROR", "nope")

        with patch(
            "nanobase_api.infrastructure.superset_client.SupersetClient._post",
            new=_post_fail,
        ):
            c = _app_client()
            r = c.post("/api/v1/bi/analytics/guest-token/42")
    assert r.status_code == 200
    data = r.json()
    assert data["dashboard_id"] == 42
    assert data["embed_uuid"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert data["analytics_url"] == "https://portal.test:8443"
    claims = jwt.decode(
        data["token"],
        secret,
        algorithms=["HS256"],
        audience="http://0.0.0.0:8080/",
    )
    assert claims["type"] == "guest"
    assert claims["resources"][0]["id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_pin_writes_canvas_when_superset_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv("BI_SUPERSET_ENABLED", raising=False)
    monkeypatch.setenv("SECRETS_ROOT", str(tmp_path))
    from nanobase_api.config import get_settings
    from nanobase_api.infrastructure.superset_client import reset_superset_client_for_tests

    get_settings.cache_clear()
    reset_superset_client_for_tests()

    import importlib

    import nanobase_api.source_widgets as sw

    importlib.reload(sw)
    import nanobase_api.analytics_api as analytics_api

    importlib.reload(analytics_api)

    app = FastAPI()
    app.include_router(analytics_api.router)
    c = TestClient(app)
    r = c.post(
        "/api/v1/bi/analytics/dashboards/0/pin",
        json={
            "sql": "SELECT city, n FROM t",
            "title": "Cities",
            "viz_type": "bar",
            "widgets": [
                {
                    "id": "chat_test1",
                    "type": "bar",
                    "title": "Cities",
                    "sql": "SELECT city, n FROM t",
                    "x_key": "city",
                    "y_key": "n",
                }
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["action"] == "pin_canvas"
    assert body["widget"]["id"] == "chat_test1"
    assert (tmp_path / "source-widgets-pinned.json").is_file()
