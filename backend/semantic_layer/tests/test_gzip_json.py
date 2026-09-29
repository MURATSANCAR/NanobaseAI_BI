"""JSON cevapları gzip'li (2026-09-29 hız işi): yazar giriş panosu ve editoryal masam hazır cevaptan dönerken bile
büyük gövdenin aktarımıyla 5,9 sn sürüyordu. Yalnız JSON, yalnız istemci isterse, içerik aynen korunur."""
from __future__ import annotations

import gzip
import json

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient

from semantic_bridge import gzip_json

BIG = {"items": [{"id": i, "name": f"Proje {i}", "line": "Editör raporu bekleniyor", "progress": [True] * 9}
                 for i in range(2000)]}


def make_app() -> FastAPI:
    app = FastAPI()

    @app.get("/big")
    def big():
        return BIG

    @app.get("/small")
    def small():
        return {"ok": True}

    @app.get("/image")
    def image():
        return Response(content=b"\x89PNG" + b"0" * 5000, media_type="image/png")

    @app.get("/stream")
    def stream():
        return StreamingResponse(iter([b"data: 1\n\n"] * 500), media_type="text/event-stream")

    @app.get("/pre")
    def pre():
        body = gzip.compress(json.dumps(BIG).encode())
        return Response(content=body, media_type="application/json", headers={"Content-Encoding": "gzip"})

    # Köprüdeki gibi içeride BaseHTTPMiddleware: gövde parça parça gelir.
    @app.middleware("http")
    async def inner(request: Request, call_next):
        return await call_next(request)

    gzip_json.install(app)
    return app


def test_buyuk_json_sikistirilir_icerik_ayni():
    c = TestClient(make_app())
    r = c.get("/big", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers["content-encoding"] == "gzip"
    assert "accept-encoding" in r.headers["vary"].lower()
    assert r.json() == BIG                                   # httpx açar; içerik değişmedi
    assert int(r.headers["content-length"]) < len(json.dumps(BIG)) / 5


def test_istemci_istemezse_duz():
    c = TestClient(make_app())
    r = c.get("/big", headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in r.headers and r.json() == BIG


def test_kucuk_gorsel_akis_ve_kodlanmis_dokunulmaz():
    c = TestClient(make_app())
    assert "content-encoding" not in c.get("/small", headers={"Accept-Encoding": "gzip"}).headers
    img = c.get("/image", headers={"Accept-Encoding": "gzip"})
    assert "content-encoding" not in img.headers and img.content.startswith(b"\x89PNG")
    st = c.get("/stream", headers={"Accept-Encoding": "gzip"})
    assert "content-encoding" not in st.headers and st.text.count("data: 1") == 500
    pre = c.get("/pre", headers={"Accept-Encoding": "gzip"})
    assert pre.headers["content-encoding"] == "gzip" and pre.json() == BIG      # iki kez sıkıştırılmadı


def test_json_hata_cevabi_da_calisir():
    app = make_app()

    @app.get("/err")
    def err():
        return JSONResponse(status_code=403, content={"detail": {"code": "FORBIDDEN", "message": "x" * 3000}})

    r = TestClient(app).get("/err", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 403 and r.headers["content-encoding"] == "gzip" and r.json()["detail"]["code"] == "FORBIDDEN"
