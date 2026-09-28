"""LLM kapısının OpenAI uyumlu girişi.

OpenAI istemcisiyle konuşan ayrı servisler (NanobaseAI Destek'in yapay zekâ paneli gibi) modele
doğrudan değil buradan gider: her çağrı `sl_llm_queue` sırasından kiralık alır, sonra köprünün
bağlı olduğu modele aynen iletilir (araç çağrısı, akış dahil). Böylece BI'ın soruları, gece işleri
ve bu servisler aynı slotları paylaşır; biri ötekini zaman aşımına düşürmez.

Uçlar (köprü içi yol; dışarıya nginx `…/destek-llm/v1/` ile açılır):
    GET  /api/v1/llm/openai/v1/models
    POST /api/v1/llm/openai/v1/chat/completions

Başlıklar: `X-LLM-Module` (sırada görünen modül adı, vars. `openai`), `X-LLM-Priority`
(0 etkileşimli · 1 normal · 2 arka plan; vars. 0). İstekteki `model` yok sayılır, köprünün
modeli kullanılır; köprünün `LLM_EXTRA_BODY_JSON` değerleri istekte yoksa eklenir.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.concurrency import run_in_threadpool

from semantic_layer.runtime.llm_queue import BATCH, INTERACTIVE, clean_module

log = logging.getLogger(__name__)

PREFIX = "/api/v1/llm/openai/v1"


def _question(messages: Any) -> Optional[str]:
    """Sırada gösterilecek soru: son kullanıcı mesajının metni."""
    if not isinstance(messages, list):
        return None
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "user":
            content = m.get("content")
            if isinstance(content, list):
                content = " ".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
            return str(content or "")[:500] or None
    return None


def _priority(raw: Optional[str]) -> int:
    try:
        return max(INTERACTIVE, min(BATCH, int(raw))) if raw not in (None, "") else INTERACTIVE
    except ValueError:
        return INTERACTIVE


def register(app: Any, rt: Callable[[], Any], require_caller: Callable[[Any], None]) -> None:
    @app.get(f"{PREFIX}/models")
    def openai_models(request: Request) -> dict[str, Any]:
        require_caller(request)
        s = rt().settings
        return {"object": "list", "data": [{"id": s.llm_model, "object": "model", "owned_by": "nanobase"}]}

    @app.post(f"{PREFIX}/chat/completions")
    async def openai_chat(request: Request):
        require_caller(request)
        r = rt()
        s = r.settings
        if r.llm is None or not s.llm_base:
            raise HTTPException(status_code=503, detail={"code": "NO_MODEL", "message": "Model bağlı değil."})
        try:
            body = await request.json()
        except (ValueError, json.JSONDecodeError):
            raise HTTPException(status_code=422, detail={"code": "INVALID", "message": "Gövde JSON değil."}) from None
        if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
            raise HTTPException(status_code=422, detail={"code": "INVALID", "message": "messages dizisi gerekli."})

        module = clean_module(request.headers.get("x-llm-module") or "openai")
        priority = _priority(request.headers.get("x-llm-priority"))
        body["model"] = s.llm_model
        for key, value in (s.llm_extra or {}).items():
            body.setdefault(key, value)
        stream = bool(body.get("stream"))
        url = s.llm_base.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if s.llm_key:
            headers["Authorization"] = f"Bearer {s.llm_key}"
        timeout = httpx.Timeout(float(s.llm_timeout or 900), connect=30.0)

        # Kiralık, sıra gelene kadar bekleyen eşzamanlı bir bağlam; olay döngüsünü tutmasın diye iş
        # parçacığında alınır ve bırakılır. Akışta kiralık, son parça gönderilene (ya da istemci
        # bağlantıyı kesene) kadar tutulur.
        lease = r.queue.lease(purpose=f"openai:{module}", tenant_id=s.tenant_id, datasource_id=s.datasource_id,
                              question=_question(body.get("messages")), module=module, priority=priority)
        ticket = await run_in_threadpool(lease.__enter__)

        async def release(exc: Optional[BaseException] = None) -> None:
            args = (type(exc), exc, exc.__traceback__) if exc else (None, None, None)
            try:
                await run_in_threadpool(lease.__exit__, *args)
            except Exception as e:  # noqa: BLE001
                log.warning("openai gate release failed: %s", e)

        wait_headers = {"X-LLM-Wait-Ms": str(ticket.waited_ms), "X-LLM-Ahead": str(ticket.ahead)}

        if not stream:
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(url, json=body, headers=headers)
            except Exception as exc:
                await release(exc)
                raise HTTPException(status_code=502, detail={"code": "UPSTREAM", "message": "Modele ulaşılamadı."}) from exc
            await release()
            return Response(content=resp.content, status_code=resp.status_code,
                            media_type=resp.headers.get("content-type", "application/json"), headers=wait_headers)

        client = httpx.AsyncClient(timeout=timeout)
        try:
            upstream = await client.send(client.build_request("POST", url, json=body, headers=headers), stream=True)
        except Exception as exc:
            await client.aclose()
            await release(exc)
            raise HTTPException(status_code=502, detail={"code": "UPSTREAM", "message": "Modele ulaşılamadı."}) from exc

        if upstream.status_code >= 400:
            content = await upstream.aread()
            await upstream.aclose()
            await client.aclose()
            await release()
            return JSONResponse(status_code=upstream.status_code, content=_json_or_text(content), headers=wait_headers)

        async def relay():
            failure: Optional[BaseException] = None
            try:
                async for chunk in upstream.aiter_raw():
                    yield chunk
            except BaseException as exc:  # istemci koptu ya da model yarıda kesti
                failure = exc
                raise
            finally:
                await upstream.aclose()
                await client.aclose()
                await release(failure if isinstance(failure, Exception) else None)

        return StreamingResponse(relay(), media_type=upstream.headers.get("content-type", "text/event-stream"),
                                 headers={**wait_headers, "X-Accel-Buffering": "no", "Cache-Control": "no-store"})


def _json_or_text(content: bytes) -> Any:
    try:
        return json.loads(content)
    except (ValueError, json.JSONDecodeError):
        return {"error": {"message": content.decode("utf-8", "replace")[:2000]}}
