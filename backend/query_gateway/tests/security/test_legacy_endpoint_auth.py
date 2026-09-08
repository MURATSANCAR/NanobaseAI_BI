"""Eski Gateway uçları da servis kimliğinden geçmeli."""
import os

os.environ["QG_AUTH_REQUIRED"] = "true"

import pytest
from fastapi.testclient import TestClient

from query_gateway.config.settings import get_settings
from query_gateway.main import create_app


@pytest.fixture
def client():
    get_settings.cache_clear()
    return TestClient(create_app(), raise_server_exceptions=False)


def test_legacy_execute_requires_service_authentication(client):
    """`/internal/v1/queries/execute` servis kimliği isterken aynı uygulamadaki eski yol hiçbir
    bağımlılık taşımıyordu: gateway ağına ulaşan bir istemci, yalnız kaynak kimliği vererek
    yürütücüye erişebiliyordu."""
    r = client.post("/api/v1/query/execute", json={"datasource_id": "x", "sql": "SELECT 1"})
    assert r.status_code in (401, 403), r.text


def test_legacy_validate_and_datasources_require_it_too(client):
    assert client.post("/api/v1/query/validate", json={"datasource_id": "x", "sql": "SELECT 1"}).status_code in (401, 403)
    assert client.get("/api/v1/query/datasources").status_code in (401, 403)
