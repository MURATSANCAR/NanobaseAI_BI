"""SEO & GEO ana modülü: karar uçlarının gövde modeli FastAPI'de çözülüyor mu.

`seo_geo/__init__.py` `from __future__ import annotations` kullanır; FastAPI uç imzasındaki adı modülün
globallerinde arar. `RedirectDecision` `register()` içinde tanımlıyken ForwardRef kalıyordu: `/openapi.json` ve
`POST /api/v1/seo-geo/redirects/{rid}/decide` "TypeAdapter ... is not fully defined" ile 500 veriyordu
(2026-09-28 01:53, test sunucusu köprü günlüğü). Testler veritabanına gitmez: gövde doğrulaması uçtan önce koşar,
geçerli gövde de yetki kapısında (401) durur.
"""
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from semantic_bridge import seo_geo


def _deny(request):
    raise HTTPException(401, "oturum yok")


def _app() -> FastAPI:
    app = FastAPI()
    seo_geo.register(app, runtime=None, authorize=_deny, session_user=lambda r: "t")
    return app


def _route(app: FastAPI, method: str, path: str):
    match = [r for r in app.routes if getattr(r, "path", None) == path and method in getattr(r, "methods", ())]
    assert match, (method, path)
    return match[0]


def test_decision_models_are_module_level():
    assert seo_geo.RedirectDecision(action="approve", target="yeni-adres").target == "yeni-adres"
    assert seo_geo.PageDecision(action="reject").fields == {}


def test_redirect_decide_body_resolves_to_model():
    route = _route(_app(), "POST", "/api/v1/seo-geo/redirects/{rid}/decide")
    body = route.dependant.body_params
    assert [f.name for f in body] == ["body"]
    assert body[0].field_info.annotation is seo_geo.RedirectDecision
    assert not route.dependant.query_params


def test_page_decide_body_resolves_to_model():
    route = _route(_app(), "POST", "/api/v1/seo-geo/pages/proposals/{proposal_id}/decide")
    assert route.dependant.body_params[0].field_info.annotation is seo_geo.PageDecision


def test_no_seo_route_takes_body_model_as_query():
    bad = []
    for route in _app().routes:
        dep = getattr(route, "dependant", None)
        if dep is None:
            continue
        for q in dep.query_params:
            if q.name in ("request", "body") or q.name[:1].isupper():
                bad.append(f"{sorted(route.methods)} {route.path}: {q.name}")
    assert not bad, bad


def test_openapi_schema_builds():
    schemas = _app().openapi()["components"]["schemas"]
    assert "RedirectDecision" in schemas and "PageDecision" in schemas


def test_redirect_decide_validates_body_then_hits_gate():
    client = TestClient(_app(), raise_server_exceptions=False)
    url = "/api/v1/seo-geo/redirects/r1/decide"
    assert client.post(url, json={"action": "sil"}).status_code == 422
    assert client.post(url, json={"action": "approve", "target": "x" * 601}).status_code == 422
    assert client.post(url, json={"action": "approve", "target": "yeni-adres"}).status_code == 401
