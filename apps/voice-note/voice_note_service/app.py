"""Sesli not servisi (TT GPU, yalnız 127.0.0.1). Uçlar:

* `GET  /health` — hazır mı, sıra (koşan/bekleyen), bellek. Anahtar istemez, içerik vermez.
* `POST /v1/transcribe` — gövde: ham ses (WAV önerilir; başka biçim ffmpeg ile çözülür). Başlık `X-Voice-Token`.
  Sorgu: `max_seconds` (çağıranın süre sınırı, servisinkinden büyük olamaz), `context` (isteğe bağlı sözlük/ad ipucu,
  URL kodlu, en çok 600 karakter). Cevap: metin + parça zaman damgaları.

Sıra: GPU işi tek kuyruktan geçer (`VOICE_CONCURRENCY`, varsayılan 1; geliş sırası korunur). Bekleyen reddedilmez;
beklemesi `VOICE_QUEUE_WAIT_SEC`'i aşarsa 503 + `retryable` döner. Test sunucusu ve müşteri VM'i aynı servise
geldiğinden GPU'yu koruyan sınır buradadır; köprünün kendi sırası yalnız kendi iş parçacıklarını korur.

Gizlilik: gövde bellekte okunur (çok parçalı form değil — Starlette büyük formu geçici dosyaya yazar), çözülen ses ve
metin günlüğe yazılmaz; günlükte yalnız süre/boyut/bekleme vardır. Cevap dönünce ses referansları bırakılır.
"""
from __future__ import annotations

import asyncio
import hmac
import logging
import os
import time
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from voice_note_service import audio as A
from voice_note_service import text as T

log = logging.getLogger("voice_note")


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default


class Queue:
    """Geliş sırasını koruyan GPU kapısı; kaç kişinin beklediğini söyler."""

    def __init__(self, slots: int):
        self.slots = max(1, slots)
        self._sem = asyncio.Semaphore(self.slots)
        self.running = 0
        self.waiting = 0
        self.served = 0

    async def enter(self, timeout: float) -> float:
        t0 = time.perf_counter()
        self.waiting += 1
        try:
            await asyncio.wait_for(self._sem.acquire(), timeout=timeout if timeout > 0 else None)
        finally:
            self.waiting -= 1
        self.running += 1
        return (time.perf_counter() - t0) * 1000

    def leave(self) -> None:
        self.running -= 1
        self.served += 1
        self._sem.release()

    def view(self) -> dict[str, int]:
        return {"slots": self.slots, "running": self.running, "waiting": self.waiting, "served": self.served}


def create_app(engine: Any = None, *, load: bool = True) -> FastAPI:
    token = os.environ.get("VOICE_TOKEN", "")
    max_bytes = _env_int("VOICE_MAX_BYTES", 64 * 1024 * 1024)
    max_seconds = _env_int("VOICE_MAX_SECONDS", 1800)
    wait_sec = _env_int("VOICE_QUEUE_WAIT_SEC", 300)
    chunk_s = float(os.environ.get("VOICE_CHUNK_SEC", "28"))
    label = os.environ.get("VOICE_MODEL_LABEL", "zeki-ses")

    state: dict[str, Any] = {"engine": engine, "error": None}
    pool = ThreadPoolExecutor(max_workers=max(1, _env_int("VOICE_CONCURRENCY", 1)), thread_name_prefix="asr")
    queue: Optional[Queue] = None

    def q() -> Queue:
        nonlocal queue
        if queue is None:  # olay döngüsü içinde kurulmalı
            queue = Queue(_env_int("VOICE_CONCURRENCY", 1))
        return queue

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await _startup()
        yield

    async def _startup() -> None:
        if state["engine"] is None and load:
            from voice_note_service.engine import Engine
            eng = Engine(os.environ.get("VOICE_MODEL_DIR", "/models/asr"), device=os.environ.get("VOICE_DEVICE", "cuda"),
                         batch=_env_int("VOICE_BATCH", 8), beams=_env_int("VOICE_BEAMS", 1),
                         mem_fraction=float(os.environ.get("VOICE_MEM_FRACTION", "0") or 0))
            try:
                await asyncio.get_running_loop().run_in_executor(pool, eng.load)
                state["engine"] = eng
            except Exception as e:  # noqa: BLE001 — sağlık ucu nedeni söyler
                log.exception("model yüklenemedi")
                state["error"] = str(e)[:300]

    app = FastAPI(title="voice-note", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        eng = state["engine"]
        return {"ready": eng is not None, "model": label, "queue": q().view(),
                "memory": eng.memory() if eng is not None and hasattr(eng, "memory") else {},
                "error": state["error"], "maxSeconds": max_seconds, "maxBytes": max_bytes}

    @app.post("/v1/transcribe")
    async def transcribe(request: Request) -> JSONResponse:
        if not token or not hmac.compare_digest(request.headers.get("x-voice-token", ""), token):
            raise HTTPException(status_code=401, detail={"code": "VOICE_AUTH", "message": "Yetkisiz istek."})
        eng = state["engine"]
        if eng is None:
            raise HTTPException(status_code=503, detail={"code": "VOICE_NOT_READY", "retryable": True,
                                                         "message": "Sesli not servisi hazırlanıyor; birazdan yeniden deneyin."})
        try:
            limit_s = min(max_seconds, int(request.query_params.get("max_seconds") or max_seconds))
        except ValueError:
            limit_s = max_seconds
        ctx = (request.query_params.get("context") or "")[:600]
        if int(request.headers.get("content-length") or 0) > max_bytes:
            raise HTTPException(status_code=413, detail={"code": "VOICE_TOO_LARGE", "message": "Ses dosyası çok büyük."})
        buf = bytearray()
        async for part in request.stream():
            buf.extend(part)
            if len(buf) > max_bytes:
                raise HTTPException(status_code=413, detail={"code": "VOICE_TOO_LARGE", "message": "Ses dosyası çok büyük."})
        data = bytes(buf)
        del buf
        secs = A.wav_seconds(data)
        if secs is not None and secs > limit_s + 0.5:
            raise HTTPException(status_code=413, detail={"code": "VOICE_TOO_LONG", "message": f"Kayıt {limit_s} saniyeyi aşıyor."})

        t0 = time.perf_counter()
        try:
            wait_ms = await q().enter(wait_sec)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=503, detail={"code": "VOICE_BUSY", "retryable": True,
                                                         "message": "Sesli not sırası uzun; birazdan yeniden deneyin."}) from None
        loop = asyncio.get_running_loop()
        try:
            out = await loop.run_in_executor(pool, _work, eng, data, limit_s, ctx, chunk_s)
        except A.AudioError as e:
            raise HTTPException(status_code=e.status, detail={"code": "VOICE_AUDIO", "message": str(e)}) from None
        finally:
            q().leave()
            del data
        out.update({"model": label, "waitMs": int(wait_ms), "processingMs": int((time.perf_counter() - t0) * 1000 - wait_ms)})
        log.info("yazıya döküldü: %.1f sn ses, %d parça, bekleme %d ms, işlem %d ms",
                 out["durationSec"], len(out["segments"]), out["waitMs"], out["processingMs"])
        return JSONResponse(out)

    return app


def _work(eng: Any, data: bytes, limit_s: int, ctx: str, chunk_s: float) -> dict[str, Any]:
    a = A.decode(data)
    dur = a.size / A.SR
    if dur > limit_s + 0.5:
        raise A.AudioError(f"Kayıt {limit_s} saniyeyi aşıyor.", 413)
    chunks = A.split(a, max_s=chunk_s)
    del a
    spoken = [c for c in chunks if not c.silent]
    texts = eng.transcribe([c.audio for c in spoken], ctx) if spoken else []
    segs = []
    for c, t in zip(spoken, texts):
        t = T.clean(t)
        if t:
            segs.append({"start": c.start, "end": c.end, "text": t})
    for c in chunks:
        c.audio = None  # type: ignore[assignment]
    return {"text": T.join([s["text"] for s in segs]), "segments": segs, "durationSec": round(dur, 2),
            "chunks": len(chunks), "silentChunks": len(chunks) - len(spoken)}


def main() -> None:  # pragma: no cover
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    uvicorn.run(create_app(), host=os.environ.get("VOICE_HOST", "0.0.0.0"), port=_env_int("VOICE_PORT", 8797),
                workers=1, timeout_keep_alive=30, access_log=False)


if __name__ == "__main__":  # pragma: no cover
    main()
