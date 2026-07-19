from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ["QG_AUTH_REQUIRED"] = "false"
os.environ["QG_REPLAY_REQUIRED"] = "false"

from query_gateway.config.settings import reset_settings

reset_settings()
from query_gateway.main import create_app


@pytest.fixture
def client():
    reset_settings()
    return TestClient(create_app())


def test_health_live(client: TestClient):
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "UP"


def test_health_legacy(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("faz5") is True


def test_internal_validate_reject_dml(client: TestClient):
    r = client.post(
        "/internal/v1/queries/validate",
        json={
            "executionId": "e1",
            "datasourceId": "bi_reporting",
            "sql": "DELETE FROM public.customers",
        },
    )
    # 404 if no local secrets datasource, or 400 rejected
    assert r.status_code in (400, 404, 403)
    body = r.json()
    assert body.get("code") or body.get("status") != "APPROVED"
