"""FastAPI contract tests for scenario engine routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nanobase_api.scenario_engine.api.routes import router
from nanobase_api.scenario_engine.infrastructure.store import reset_scenario_store


def _client() -> TestClient:
    reset_scenario_store()
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_bootstrap_and_match():
    c = _client()
    r = c.post(
        "/api/v1/semantic/bootstrap/invoice-scenario-slice",
        json={"tenantId": "default", "datasourceId": "bi_reporting", "autoPublish": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "COMPLETED"

    sug = c.get("/api/v1/datasources/bi_reporting/suggested-questions?tenant_id=default")
    assert sug.status_code == 200
    assert len(sug.json().get("questions") or []) >= 1

    # Match using suggested question
    q = sug.json()["questions"][0]["question"]
    m = c.post(
        "/api/v1/query-scenarios/match",
        json={"datasourceId": "bi_reporting", "question": q, "tenantId": "default"},
    )
    assert m.status_code == 200
    assert m.json()["matched"] is True
    assert m.json()["route"] == "PRECOMPILED_SCENARIO"


def test_build_status_endpoint():
    c = _client()
    r = c.post(
        "/api/v1/datasources/bi_reporting/scenario-builds",
        json={"tenantId": "default", "async": False, "autoPublish": True},
    )
    assert r.status_code == 200
    build_id = r.json()["buildId"]
    st = c.get(f"/api/v1/datasources/bi_reporting/scenario-builds/{build_id}")
    assert st.status_code == 200
    assert st.json()["status"] in ("COMPLETED", "FAILED", "RUNNING")
