"""JSON cevaplarını sıkıştırarak gönderen en dış ara katman (2026-09-29 hız işi).

Sorun: köprü de, önündeki nginx de (test sunucusu, VM `web` kabı) hiçbir cevabı sıkıştırmıyordu. Yazar giriş panosu
(`/api/v1/editorial/intake`: bütün projelerin kartı) ve editoryal masam (`/api/v1/editorial/home`) hazır cevaptan
(x-data-cached=1) dönerken bile 5,9 sn sürüyordu: süre hesap değil, VPN/uzak bağlantıdaki büyük gövdenin aktarımıydı.
JSON gövdesi tekrar eden anahtarlarla doludur; gzip onu tipik olarak 8–15 kat küçültür.

Kural:
- Yalnız `application/json`, istemci `Accept-Encoding: gzip` gönderdiyse, gövde `MINIMUM` baytı aşıyorsa ve cevap
  zaten kodlanmamışsa. Görsel, PDF, Excel, CSV, olay akışı (`text/event-stream`), ndjson dokunulmaz.
- Gövde parça parça gelse de (Starlette `@app.middleware` cevapları her zaman parçalı gelir) tamamı toplanıp sıkıştırılır;
  `MAX_BUFFER`'ı aşan gövde sıkıştırılmadan olduğu gibi akıtılır (uzun akış bekletilmez).
- Büyük gövdenin sıkıştırılması olay döngüsünü tutmasın diye iş parçacığında yapılır.
- Uygulamanın en dışında durmalı (`create_app` sonunda kurulur): içerideki ara katmanlar (hazır cevap, sorgu bilgisi,
  Excel çevirisi) sıkıştırılmamış gövdeyle çalışır, hazır cevap diske sıkıştırılmamış yazılır.
"""
from __future__ import annotations

import gzip
from typing import Any

from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers, MutableHeaders

MINIMUM = 1024
MAX_BUFFER = 64 * 1024 * 1024
LEVEL = 5
THREAD_ABOVE = 256 * 1024


def _compress(body: bytes) -> bytes:
    return gzip.compress(body, compresslevel=LEVEL, mtime=0)


class GzipJson:
    def __init__(self, app: Any, minimum_size: int = MINIMUM) -> None:
        self.app = app
        self.minimum_size = minimum_size

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or "gzip" not in Headers(scope=scope).get("accept-encoding", "").lower():
            await self.app(scope, receive, send)
            return
        start: dict | None = None
        chunks: list[bytes] = []
        size = 0
        mode = "wait"        # wait: başlık tutuluyor | pass: olduğu gibi | buffer: JSON toplanıyor

        async def flush_plain(message: dict | None) -> None:
            nonlocal mode
            mode = "pass"
            await send(start)
            if chunks:
                await send({"type": "http.response.body", "body": b"".join(chunks), "more_body": True})
                chunks.clear()
            if message is not None:
                await send(message)

        async def wrapped(message: dict) -> None:
            nonlocal start, mode, size
            if mode == "pass":
                await send(message)
                return
            kind = message.get("type")
            if kind == "http.response.start":
                start = message
                headers = Headers(raw=message.get("headers") or [])
                ctype = headers.get("content-type", "").split(";")[0].strip().lower()
                if ctype != "application/json" or headers.get("content-encoding"):
                    mode = "pass"
                    await send(message)
                else:
                    mode = "buffer"
                return
            if kind != "http.response.body" or start is None:
                await send(message)
                return
            body = message.get("body") or b""
            chunks.append(body)
            size += len(body)
            if message.get("more_body"):
                if size > MAX_BUFFER:
                    await flush_plain(None)
                return
            data = b"".join(chunks)
            chunks.clear()
            if len(data) < self.minimum_size:
                mode = "pass"
                await send(start)
                await send({"type": "http.response.body", "body": data, "more_body": False})
                return
            packed = await run_in_threadpool(_compress, data) if len(data) > THREAD_ABOVE else _compress(data)
            headers = MutableHeaders(raw=list(start.get("headers") or []))
            headers["content-encoding"] = "gzip"
            headers["content-length"] = str(len(packed))
            headers.add_vary_header("Accept-Encoding")
            mode = "pass"
            await send({**start, "headers": headers.raw})
            await send({"type": "http.response.body", "body": packed, "more_body": False})

        await self.app(scope, receive, wrapped)


def install(app: Any) -> None:
    """En dışa kurar (çağrı `create_app` sonunda, bütün öteki ara katmanlardan sonra)."""
    app.add_middleware(GzipJson)
