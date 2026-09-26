"""Kitap Tasarım Stüdyosu — sesli okuma köprü uçları.

Stüdyo servisindeki `/v1/studio/jobs/{job}/narration…` uçlarının birebir vekili (apps/editor/src/editor/production/
api_narration.py). Oturum zorunlu (stüdyonun öteki uçlarıyla aynı `_books` denetimi); yazanlarda X-Editor oturumdaki
AD hesabıdır ve denetim kaydı düşer. Servisin kodlu 4xx/503 gövdesi ({"code": "NO_PLAN" | "NO_VOICE" | "BUSY" |
"NOTHING", "detail"}) olduğu gibi ekrana gider.

Ses dosyası: servis bütün dosyayı verir, köprü tarayıcının `Range` isteğini kendisi karşılar (206 Partial Content);
iOS Safari sesi yalnız aralık desteği olan adresten çalar, ileri/geri sarma da buna bağlı.

app.py'de `_books` tanımından sonra (stüdyo bloğunun yanında) iki satırla bağlanır:
    from semantic_bridge import editorial_studio_narration
    editorial_studio_narration.register(app, {"auth": _books, "audit": admin_mod.audit})
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response

from semantic_bridge import editorial_studio

log = logging.getLogger(__name__)

AUDIO_MAX = 200 * 1024 * 1024
SAMPLE_TEXT_MAX = 300
READ_TEXT_MAX = 2000
RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


def _url(job_id: str, sub: str) -> tuple[str, dict, str]:
    base, headers, ca = editorial_studio._base()
    return f"{base}/v1/studio/jobs/{editorial_studio._job(job_id)}/narration{sub}", headers, ca


def request(method: str, job_id: str, sub: str, *, body: dict | None = None, editor: str | None = None,
            timeout: float = 120) -> object:
    url, headers, ca = _url(job_id, sub)
    if editor is not None:
        headers["X-Editor"] = editor[:200]
    with editorial_studio._client(ca, timeout=timeout) as c:
        r = c.request(method, url, headers=headers, json=body)
    if 400 <= r.status_code < 500 or r.status_code == 503:
        try:
            payload = r.json()
        except ValueError:
            payload = {"detail": "İstek kabul edilmedi."}
        raise editorial_studio.PlanError(r.status_code, payload)
    r.raise_for_status()
    return r.json()


def audio_bytes(job_id: str, sub: str, *, method: str = "GET", body: dict | None = None, editor: str | None = None,
                timeout: float = 120) -> bytes:
    url, headers, ca = _url(job_id, sub)
    if editor is not None:
        headers["X-Editor"] = editor[:200]
    with editorial_studio._client(ca, timeout=timeout) as c:
        r = c.request(method, url, headers=headers, json=body)
    if 400 <= r.status_code < 500 or r.status_code == 503:
        try:
            payload = r.json()
        except ValueError:
            payload = {"detail": "Ses bulunamadı."}
        raise editorial_studio.PlanError(r.status_code, payload)
    r.raise_for_status()
    if r.headers.get("content-type", "").split(";")[0] != "audio/mpeg":
        raise editorial_studio.StudioError(404, "Ses bulunamadı.")
    if len(r.content) > AUDIO_MAX:
        raise editorial_studio.StudioError(413, "Ses dosyası çok büyük.")
    return r.content


def ranged(data: bytes, range_header: str | None, headers: dict) -> Response:
    """Tek aralıklı `Range` isteği → 206; aralık yoksa ya da çözülemezse 200 bütün dosya."""
    base = {"Accept-Ranges": "bytes", **headers}
    m = RANGE.match((range_header or "").strip())
    size = len(data)
    if not m or (not m[1] and not m[2]) or size == 0:
        return Response(data, media_type="audio/mpeg", headers=base)
    if m[1]:
        start = int(m[1])
        end = min(int(m[2]), size - 1) if m[2] else size - 1
    else:                                   # son N bayt
        start, end = max(0, size - int(m[2])), size - 1
    if start >= size or start > end:
        return Response(status_code=416, headers={**base, "Content-Range": f"bytes */{size}"})
    return Response(data[start:end + 1], status_code=206, media_type="audio/mpeg",
                    headers={**base, "Content-Range": f"bytes {start}-{end}/{size}"})


def register(app, deps: dict[str, Any] | Any) -> None:
    """`deps["auth"]`: app.py'deki `_books(request)` → (engine, tenant, user, is_admin); `deps["audit"]`:
    `admin_mod.audit(engine, user, action, kind, id, what, detail)`."""
    auth: Callable[[Request], Any] = deps["auth"] if isinstance(deps, dict) else deps.auth
    audit: Callable[..., Any] | None = deps.get("audit") if isinstance(deps, dict) else getattr(deps, "audit", None)
    request_fn = request            # uç işlevlerinde `request` adı FastAPI isteğidir

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except editorial_studio.PlanError as e:
            return JSONResponse(status_code=e.status, content=e.body)
        except editorial_studio.StudioError as e:
            raise HTTPException(e.status if e.status in (400, 404, 409, 413) else 400, str(e)) from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        except httpx.TimeoutException:
            raise HTTPException(504, "Stüdyo zamanında yanıt vermedi.") from None
        except Exception:  # noqa: BLE001 — ayrıntı günlükte; editöre teknik hata metni gösterilmez
            log.exception("studio narration call failed")
            raise HTTPException(502, "Stüdyo şu an yanıt vermiyor.") from None

    def write(request: Request, method: str, job: str, sub: str, what: str, body: dict, timeout: float = 120):
        engine, _tenant, user, _ = auth(request)
        out = call(request_fn, method, job, sub, body=body, editor=user, timeout=timeout)
        if audit is not None and not isinstance(out, Response):
            try:
                audit(engine, user, "create" if method == "POST" else "update", "studio_narration",
                      f"{job}{sub}"[:120], what, body if len(str(body)) < 4000 else None)
            except Exception:  # noqa: BLE001 — denetim kaydı düşmezse işlem geri alınmaz, günlüğe yazılır
                log.exception("studio narration audit failed")
        return out

    def obj(body: Any) -> dict:
        if not isinstance(body, dict):
            raise HTTPException(400, "Gövde bir nesne olmalı.")
        return body

    def pid(v: str) -> str:
        if not editorial_studio.PLAN_ID.match(v or ""):
            raise HTTPException(404, "Sayfa bulunamadı.")
        return v

    @app.get("/api/v1/editorial/studio/jobs/{job}/narration")
    def editorial_narration(job: str, request: Request):
        auth(request)
        return call(request_fn, "GET", job, "", timeout=60)

    @app.put("/api/v1/editorial/studio/jobs/{job}/narration/settings")
    def editorial_narration_settings(job: str, request: Request, body: dict[str, Any] | None = None):
        b = obj(body)
        clean = {"narrator": str(b.get("narrator") or "")[:40],
                 "characters": {str(k)[:120]: str(v)[:40] for k, v in (b.get("characters") or {}).items()}}
        return write(request, "PUT", job, "/settings", "sesli okuma sesleri", clean)

    @app.put("/api/v1/editorial/studio/jobs/{job}/narration/lexicon")
    def editorial_narration_lexicon(job: str, request: Request, body: dict[str, Any] | None = None):
        b = obj(body)
        scope = b.get("scope") if b.get("scope") in ("job", "publisher") else "job"
        entries = [{"word": str(e.get("word", ""))[:120], "say": str(e.get("say", ""))[:240]}
                   for e in (b.get("entries") or []) if isinstance(e, dict)]
        return write(request, "PUT", job, "/lexicon",
                     "telaffuz sözlüğü (" + ("yayınevi" if scope == "publisher" else "bu kitap") + ")",
                     {"scope": scope, "entries": entries})

    @app.post("/api/v1/editorial/studio/jobs/{job}/narration/run")
    def editorial_narration_run(job: str, request: Request, body: dict[str, Any] | None = None):
        b = obj(body or {})
        pages = b.get("pages")
        clean = {"pages": [pid(str(p)) for p in pages] if isinstance(pages, list) else None,
                 "force": bool(b.get("force"))}
        return write(request, "POST", job, "/run", "seslendirme başlatıldı", clean)

    @app.get("/api/v1/editorial/studio/jobs/{job}/narration/pages/{page}")
    def editorial_narration_page(job: str, page: str, request: Request):
        auth(request)
        return call(request_fn, "GET", job, f"/pages/{pid(page)}", timeout=60)

    @app.get("/api/v1/editorial/studio/jobs/{job}/narration/pages/{page}/audio")
    def editorial_narration_audio(job: str, page: str, request: Request):
        auth(request)
        out = call(audio_bytes, job, f"/pages/{pid(page)}/audio")
        if isinstance(out, Response):
            return out
        return ranged(out, request.headers.get("range"), {"Cache-Control": "private, max-age=60"})

    @app.post("/api/v1/editorial/studio/jobs/{job}/narration/read")
    def editorial_narration_read(job: str, request: Request, body: dict[str, Any] | None = None):
        auth(request)
        text = str(obj(body).get("text") or "")
        if not text.strip() or len(text) > READ_TEXT_MAX:
            raise HTTPException(400, f"Metin 1–{READ_TEXT_MAX} harf olmalı.")
        return call(request_fn, "POST", job, "/read", body={"text": text}, timeout=30)

    @app.post("/api/v1/editorial/studio/jobs/{job}/narration/sample")
    def editorial_narration_sample(job: str, request: Request, body: dict[str, Any] | None = None):
        _engine, _tenant, user, _ = auth(request)
        b = obj(body)
        text = str(b.get("text") or "")
        if not text.strip() or len(text) > SAMPLE_TEXT_MAX:
            raise HTTPException(400, f"Deneme metni 1–{SAMPLE_TEXT_MAX} harf olmalı.")
        out = call(audio_bytes, job, "/sample", method="POST", body={"text": text, "voice": str(b.get("voice") or "")[:40]},
                   editor=user, timeout=600)
        if isinstance(out, Response):
            return out
        return ranged(out, request.headers.get("range"), {"Cache-Control": "no-store"})

    @app.get("/api/v1/editorial/studio/jobs/{job}/narration/overlay")
    def editorial_narration_overlay(job: str, request: Request):
        auth(request)
        return call(request_fn, "GET", job, "/overlay", timeout=120)
