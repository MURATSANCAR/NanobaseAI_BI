"""Köprünün bütün 403'leri FORBIDDEN koduyla çıkar (`semantic_bridge/http_forbidden.py`).

Ön yüz (`src/canvas/engine.ts`) FORBIDDEN kodsuz 403'ü «oturum düştü» sayar. Kabulde (2026-09-28) M30'un `FieldError(403)`
cevabı `FIELD` koduyla gidiyordu; aynı kalıp (modül kodu + e.status) köprüde ~40 modülde vardı. Kural tek yerde.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from semantic_bridge import http_forbidden as H


def test_forbidden_detail_shapes():
    assert H.forbidden_detail({"code": "HR", "message": "Yalnız yönetici."}) == {
        "code": "FORBIDDEN", "module": "HR", "message": "Yalnız yönetici."}
    assert H.forbidden_detail({"code": "FORBIDDEN", "message": "x"}) == {"code": "FORBIDDEN", "message": "x"}
    assert H.forbidden_detail("Sesi yalnız yönetici kaldırır.") == {"code": "FORBIDDEN", "message": "Sesi yalnız yönetici kaldırır."}
    assert H.forbidden_detail(None)["message"] == H.DEFAULT_MESSAGE
    extra = H.forbidden_detail({"code": "EDITOR_ASSIGN", "message": "m", "kitap": 3})
    assert extra["kitap"] == 3 and extra["module"] == "EDITOR_ASSIGN"


def _app() -> FastAPI:
    app = FastAPI()
    H.install(app)

    @app.get("/m403")
    def m403():
        raise HTTPException(status_code=403, detail={"code": "FIELD", "message": "Bu cari size atanmış değil."})

    @app.get("/s403")
    def s403():
        raise HTTPException(403, "Sesi kütüphaneden yalnız yönetici kaldırabilir.")

    @app.get("/m404")
    def m404():
        raise HTTPException(status_code=404, detail={"code": "FIELD", "message": "yok"})

    @app.get("/h401")
    def h401():
        raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."},
                            headers={"WWW-Authenticate": "Cookie"})

    return app


def test_handler_rewrites_only_403():
    c = TestClient(_app())
    r = c.get("/m403")
    assert r.status_code == 403 and r.json()["detail"] == {"code": "FORBIDDEN", "module": "FIELD",
                                                           "message": "Bu cari size atanmış değil."}
    r = c.get("/s403")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "FORBIDDEN"
    r = c.get("/m404")
    assert r.status_code == 404 and r.json()["detail"] == {"code": "FIELD", "message": "yok"}
    r = c.get("/h401")
    assert r.status_code == 401 and r.json()["detail"]["code"] == "UNAUTHORIZED" and r.headers["www-authenticate"] == "Cookie"
    assert c.get("/yok").status_code == 404                                        # çatının kendi 404'ü bozulmaz


def test_bridge_app_installs_the_handler(monkeypatch, store, settings):
    from semantic_bridge.app import Runtime, create_app
    from semantic_layer.candidates.llm_client import FakeLlm

    monkeypatch.delenv("SEMANTIC_CALLER_TOKEN", raising=False)
    app = create_app(Runtime(settings, store=store, llm=FakeLlm([""])))

    @app.get("/__test/forbidden")
    def _probe():
        raise HTTPException(status_code=403, detail={"code": "HR", "message": "Bu anketin birim sonuçları paylaşılmadı."})

    r = TestClient(app).get("/__test/forbidden")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "FORBIDDEN" and r.json()["detail"]["module"] == "HR"
