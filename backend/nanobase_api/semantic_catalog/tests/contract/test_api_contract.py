"""Contract-ish API tests using FastAPI TestClient (in-memory catalog)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nanobase_api.auth.principal import mint_dev_token
from nanobase_api.errors import ApiError, api_error_handler
from nanobase_api.semantic_catalog.api.routes import router
from nanobase_api.semantic_catalog.infrastructure.catalog_store import reset_catalog_store


@pytest.fixture()
def client(monkeypatch):
    reset_catalog_store()
    monkeypatch.setenv("AUTH_MODE", "jwt")
    # Clear settings cache
    from nanobase_api.config import get_settings

    get_settings.cache_clear()
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(router)
    return TestClient(app)


def _headers(roles: list[str], user: str = "u1") -> dict[str, str]:
    token = mint_dev_token(user_id=user, tenant_id="default", roles=roles)
    return {
        "Authorization": f"Bearer {token}",
        "X-Nanobase-Semantic-Contract-Version": "1",
    }


def test_contract_header_and_bootstrap(client):
    r = client.get("/api/v1/semantic/status")
    assert r.status_code == 200
    assert r.headers.get("X-Nanobase-Semantic-Contract-Version") == "1"

    r = client.post(
        "/api/v1/semantic/bootstrap/unpaid-invoice-slice",
        json={"datasourceId": "default"},
        headers=_headers(["ADMIN", "DATA_ANALYST"]),
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_unauthorized_publish(client):
    client.post(
        "/api/v1/semantic/bootstrap/unpaid-invoice-slice",
        json={},
        headers=_headers(["ADMIN"]),
    )
    # create fake ready promotion
    from nanobase_api.semantic_catalog.domain.promotion import PromotionPhase, PromotionRequest
    from nanobase_api.semantic_catalog.infrastructure.catalog_store import get_catalog_store

    store = get_catalog_store()
    store.promotions["promo-x"] = PromotionRequest(
        id="promo-x",
        tenant_id="default",
        datasource_id="default",
        asset_type="METRIC",
        asset_id="x",
        phase=PromotionPhase.READY_TO_PUBLISH,
        requires_dual_approval=False,
    )
    r = client.post(
        "/api/v1/semantic/promotion-requests/promo-x/publish",
        json={},
        headers=_headers(["DATA_ANALYST"], user="analyst"),
    )
    assert r.status_code in (403, 400)
    body = r.json()
    assert body.get("ok") is False or r.status_code == 403


def test_candidate_from_feedback_endpoint(client):
    r = client.post(
        "/api/v1/semantic/verified-query-candidates",
        json={"question": "test", "logicalPlan": {"metric": "unpaid_invoice_amount"}},
        headers=_headers(["DATA_ANALYST"]),
    )
    assert r.status_code == 200
    assert r.json()["candidate"]["status"] == "DRAFT"
