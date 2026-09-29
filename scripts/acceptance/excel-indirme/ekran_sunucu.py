"""Ekran kabulü için tek süreçlik portal: derlenmiş arayüz + köprü, kişi yalnız bu süreçte sabit (giriş servisine dokunmaz).

`yerinde.py` ile aynı yamalar (kişi, denetim/erişim yazıcıları sayaca) yapılır; üstüne:
  /timas/auth/session         → çerez varsa {"username": TEST_USER}
  /timas/__giris              → çerezi koyar, /timas/'a yönlendirir (yalnız 127.0.0.1'de dinler)
  /timas/api/…                → köprü (önek atılarak; sayfa kapısı ve yetki aynen işler)
  /timas/…                    → DIST klasöründen dosya, yoksa index.html (tek sayfa uygulaması)
Ortam: köprünün ortam dosyası, PYTHONPATH=<köprü ağacı>, DIST (ör. /data/nanobaseai/bi/cockpit/dist), PORT (8794).
Durdurunca kayıt çağrı sayıları basılır.
"""
from __future__ import annotations

import json
import mimetypes
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yerinde as Y  # noqa: E402  — yamalar ve köprü burada kurulur

DIST = Path(os.environ.get("DIST", "/data/nanobaseai/bi/cockpit/dist")).resolve()
BRIDGE = Y.app_mod.app


async def _send(send, status: int, body: bytes, ctype: str, extra: list | None = None) -> None:
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", ctype.encode()), (b"content-length", str(len(body)).encode()), *(extra or [])]})
    await send({"type": "http.response.body", "body": body})


async def app(scope, receive, send):  # noqa: ANN001
    if scope["type"] == "lifespan":
        while True:
            m = await receive()
            if m["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif m["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    path = scope.get("path", "")
    cookie = dict(scope.get("headers") or []).get(b"cookie", b"").decode("latin-1")
    if path.startswith("/timas/api/"):
        sub = dict(scope, path=path[len("/timas"):], raw_path=path[len("/timas"):].encode(), root_path="")
        return await BRIDGE(sub, receive, send)
    if path == "/timas/auth/session":
        if Y.COOKIE in cookie:
            return await _send(send, 200, json.dumps({"username": Y.USER, "displayName": "Kabul testi"}).encode(), "application/json")
        return await _send(send, 401, b'{"detail":"oturum yok"}', "application/json")
    if path == "/timas/__giris":
        name, val = Y.COOKIE.split("=", 1)
        return await _send(send, 302, b"", "text/plain", [(b"location", b"/timas/"),
                                                          (b"set-cookie", f"{name}={val}; Path=/; HttpOnly; SameSite=Lax".encode())])
    if path.startswith("/timas/auth/"):
        return await _send(send, 204, b"", "text/plain")
    if path == "/" or not path.startswith("/timas"):
        return await _send(send, 302, b"", "text/plain", [(b"location", b"/timas/")])
    rel = path[len("/timas"):].lstrip("/")
    f = (DIST / rel).resolve()
    if not rel or not f.is_file() or DIST not in f.parents:
        f = DIST / "index.html"
    body = f.read_bytes()
    ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
    cache = [(b"cache-control", b"no-store")] if f.name == "index.html" else []
    return await _send(send, 200, body, ctype, cache)


if __name__ == "__main__":
    import atexit

    import uvicorn

    atexit.register(lambda: print("== kayıt çağrıları (yazılmadı): " + ", ".join(f"{k}={v}" for k, v in sorted(Y.calls.items())), flush=True))
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8794")), log_level="warning")
