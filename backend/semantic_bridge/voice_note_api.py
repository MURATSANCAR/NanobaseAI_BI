"""Zeki AI sesli not uçları: /api/v1/voice-note.

* `GET  /api/v1/voice-note/meta` — açık mı, süre/boyut sınırı, düzeltme açık mı (düğme buna göre görünür).
* `POST /api/v1/voice-note` — gövde ham ses (tarayıcı 16 kHz tek kanal WAV gönderir). Sorgu: `baglam` (saha|okul),
  `ad` (müşteri/okul adı — düzeltmede ve isteğe bağlı ipucunda özel ad), `duzelt` (1/0).

Sayfa kapısı `access.RULES` (`sayfa:saha` ya da `sayfa:okul-tanitim`); uç ayrıca not yazma yetkisini ister
(`ozellik:saha.not` ya da `ozellik:okul.ziyaret`). Ses ve metin saklanmaz, günlüğe yazılmaz (yalnız süre/boyut).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

import httpx
from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool

from semantic_bridge import voice_note as V

log = logging.getLogger("semantic.voice_note")
P = "/api/v1/voice-note"
WRITE_KEYS = ("ozellik:saha.not", "ozellik:okul.ziyaret")


def _err(status: int, code: str, message: str, retryable: bool = False) -> HTTPException:
    d: dict[str, Any] = {"code": code, "message": message}
    if retryable:
        d["retryable"] = True
    return HTTPException(status_code=status, detail=d)


def call_service(st: dict[str, Any], data: bytes, *, max_seconds: int, context: str,
                 post: Optional[Callable[..., Any]] = None) -> dict[str, Any]:
    """GPU servisine tek istek. Hata, kişiye söylenecek Türkçe cümleyle HTTPException olur (model adı yok)."""
    headers = {"X-Voice-Token": st["token"], "Content-Type": "application/octet-stream"}
    if ":" in st["extraHeader"]:
        name, _, value = st["extraHeader"].partition(":")
        headers[name.strip()] = value.strip()
    params = {"max_seconds": str(max_seconds)}
    if context:
        params["context"] = context
    try:
        if post is None:
            with httpx.Client(timeout=st["timeoutSec"], verify=st["caFile"] or True, follow_redirects=False) as c:
                r = c.post(f"{st['url']}/v1/transcribe", content=data, headers=headers, params=params)
        else:
            r = post(f"{st['url']}/v1/transcribe", content=data, headers=headers, params=params)
    except httpx.TimeoutException as e:
        raise _err(504, "VOICE_TIMEOUT", "Zeki AI sesli not zamanında cevap vermedi; yeniden deneyin.", True) from e
    except httpx.HTTPError as e:
        raise _err(503, "VOICE_UNAVAILABLE", "Zeki AI sesli not şu an kullanılamıyor; notu yazarak girebilirsiniz.", True) from e
    ctype = r.headers.get("content-type", "")
    try:
        body: Any = r.json() if "json" in ctype else None
    except ValueError:
        body = None
    if r.status_code == 200 and isinstance(body, dict) and "text" in body:
        return body
    msg = (body or {}).get("detail", {}).get("message") if isinstance(body, dict) and isinstance(body.get("detail"), dict) else None
    if r.status_code == 413:
        raise _err(413, "VOICE_TOO_LONG", msg or "Kayıt sınırı aşıyor.")
    if r.status_code == 400:
        raise _err(400, "VOICE_AUDIO", msg or "Ses okunamadı; yeniden kaydedin.")
    if r.status_code in (503, 504):
        raise _err(503, "VOICE_BUSY", msg or "Zeki AI sesli not şu an yoğun; birazdan yeniden deneyin.", True)
    log.warning("voice-note: servis beklenmeyen cevap %s (%s)", r.status_code, ctype[:40])
    raise _err(502, "VOICE_UNAVAILABLE", "Zeki AI sesli not şu an kullanılamıyor; notu yazarak girebilirsiniz.", True)


def register(app: Any, deps: dict[str, Any]) -> V.Gate:
    """`deps`: auth(request) → (engine, tenant, user, display) · can(user, key) · is_admin(user) · conf(key, default) ·
    llm() → LLM kapısı istemcisi ya da None · post (isteğe bağlı; testte servis yerine)."""
    auth, can, is_admin, conf = (deps[k] for k in ("auth", "can", "is_admin", "conf"))
    gate = V.Gate()

    def settings() -> dict[str, Any]:
        return V.settings_from(conf)

    def may_write(user: str) -> bool:
        return is_admin(user) or any(can(user, k) for k in WRITE_KEYS)

    @app.get(f"{P}/meta")
    def voice_meta(request: Request) -> dict[str, Any]:
        _, _, user, _ = auth(request)
        st = settings()
        return {"acik": V.ready(st) and may_write(user), "maxSaniye": st["maxSeconds"], "maxMb": st["maxMb"],
                "duzeltme": st["aiFix"], "sira": gate.view()}

    @app.post(P)
    async def voice_note(request: Request, baglam: str = "", ad: str = "", duzelt: int = 1) -> dict[str, Any]:
        _, _, user, _ = await run_in_threadpool(auth, request)
        st = settings()
        if not may_write(user):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Ziyaret notu yazma rolünüzde yok."})
        if not V.ready(st):
            raise _err(409, "VOICE_OFF", "Zeki AI sesli not bu ortamda açık değil.")
        max_bytes = st["maxMb"] * 1024 * 1024
        if int(request.headers.get("content-length") or 0) > max_bytes:
            raise _err(413, "VOICE_TOO_LARGE", f"Ses {st['maxMb']} MB sınırını aşıyor.")
        buf = bytearray()
        async for part in request.stream():
            buf.extend(part)
            if len(buf) > max_bytes:
                raise _err(413, "VOICE_TOO_LARGE", f"Ses {st['maxMb']} MB sınırını aşıyor.")
        data = bytes(buf)
        del buf
        if len(data) < 1000:
            raise _err(400, "VOICE_AUDIO", "Kayıt boş geldi; yeniden deneyin.")
        secs = V.wav_seconds(data)
        if secs is not None and secs > st["maxSeconds"] + 0.5:
            raise _err(413, "VOICE_TOO_LONG", f"Kayıt {st['maxSeconds']} saniye sınırını aşıyor.")
        names = [ad[:200]] if ad.strip() else []
        t0 = time.monotonic()
        try:
            wait_ms, ahead = await run_in_threadpool(gate.enter, st["slots"], float(st["waitSec"]))
        except V.GateTimeout:
            raise _err(503, "VOICE_BUSY", "Zeki AI sesli not şu an yoğun; birazdan yeniden deneyin.", True) from None
        try:
            out = await run_in_threadpool(call_service, st, data, max_seconds=st["maxSeconds"],
                                          context=V.context_hint(st, names), post=deps.get("post"))
        finally:
            gate.leave()
            del data
        raw = str(out.get("text") or "").strip()
        fix: dict[str, Any] = {"metin": raw, "durum": "kapali", "neden": None}
        if duzelt and st["aiFix"] and raw:
            fix = await run_in_threadpool(V.correct, deps["llm"](), raw, names)
        log.info("voice-note: %s, %.1f sn ses, düzeltme %s, toplam %d ms", baglam or "-", float(out.get("durationSec") or 0),
                 fix["durum"], int((time.monotonic() - t0) * 1000))
        return {
            "metin": fix["metin"], "ham": raw,
            "segmentler": [{"bas": s.get("start"), "son": s.get("end"), "metin": s.get("text")} for s in out.get("segments") or []],
            "sureSn": out.get("durationSec"), "beklemeMs": int(wait_ms) + int(out.get("waitMs") or 0),
            "islemMs": int(out.get("processingMs") or 0), "onundekiler": ahead,
            "duzeltme": {"durum": fix["durum"], "neden": fix["neden"]},
        }

    return gate
