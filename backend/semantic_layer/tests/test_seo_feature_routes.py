"""SEO & GEO özellik modülleri: uç imzaları FastAPI'de doğru çözülüyor mu.

`from __future__ import annotations` ile tipler modülün globallerinde aranır; `Request` ya da gövde modeli
fonksiyon içinde tanımlıysa FastAPI onu sorgu parametresi sanar ve uç her istekte 422 döner (2026-09-27,
rehber konuları ucu canlıda böyle bozuk çıktı; birim testleri yakalamadı).
"""
from fastapi import FastAPI

from semantic_bridge.seo_geo import features


class _Seo:
    def __init__(self):
        self.nightly = []

    def conf(self, key):
        return ""


def _app() -> FastAPI:
    app = FastAPI()
    features.register(app, features.Ctx(seo=_Seo(), gate=lambda r: "t", approver=lambda r: "t", authorize=lambda r: None))
    return app


def test_no_route_takes_request_or_body_model_as_query():
    bad = []
    for route in _app().routes:
        dep = getattr(route, "dependant", None)
        if dep is None:
            continue
        for q in dep.query_params:
            if q.name in ("request", "body") or q.name[:1].isupper():
                bad.append(f"{sorted(route.methods)} {route.path}: {q.name}")
    assert not bad, bad


def test_post_bodies_are_json_models():
    routes = {(tuple(sorted(r.methods)), r.path): r for r in _app().routes if hasattr(r, "dependant")}
    for key in ((("POST",), "/api/v1/seo-geo/guides"), (("POST",), "/api/v1/seo-geo/guides/{gid}/decide")):
        match = [r for (m, p), r in routes.items() if m == key[0] and p.split("{")[0] == key[1].split("{")[0]]
        assert match, key
        assert all(r.dependant.body_params for r in match), key
