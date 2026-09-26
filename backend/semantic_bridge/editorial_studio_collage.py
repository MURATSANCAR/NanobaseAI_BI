"""Kitap Tasarım Stüdyosu — kapak tarzı ve kolaj kapak için köprü uçları.

Stüdyo servisindeki `/v1/studio/jobs/{job}/collage…` uçlarının birebir vekili (apps/editor/src/editor/production/
api_collage.py). Oturum zorunlu; yazanlarda `X-Editor` = oturumdaki AD hesabı ve denetim kaydı. Servisin 4xx gövdesi
({"code": "BUSY"}, {"code": "TOO_LARGE"}, {"detail": "…"}) olduğu gibi döner; ekran kodu okur. Fotoğraf yükleme ham
gövdeli PUT (plan fotoğraflarıyla aynı kalıp ve sınır: yönetim ayarı STUDIO_UPLOAD_MB).

app.py'de `_books` ve `_upload_mb` tanımlarından sonra iki satırla bağlanır:
    from semantic_bridge import editorial_studio_collage
    editorial_studio_collage.register(app, {"auth": _books, "audit": admin_mod.audit, "upload_mb": _upload_mb})
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Callable

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import editorial_studio

log = logging.getLogger(__name__)

PHOTO = re.compile(r"^k_[0-9a-f]{8}$")
STYLES = {"illustrated", "collage", "typographic"}
PHOTO_MIME = editorial_studio.PHOTO_MIME
IMAGE_MIME = editorial_studio.IMAGE_MIME
CACHE = {"Cache-Control": "private, max-age=300"}
DIRECTION_MAX = 1200
LABEL_MAX = 300


class Passthrough(Exception):
    def __init__(self, status: int, body: object):
        super().__init__(f"collage {status}")
        self.status, self.body = status, body


def request(method: str, job_id: str, sub: str, *, body: dict | None = None, editor: str | None = None,
            params: dict | None = None, content: bytes | None = None, mime: str | None = None,
            timeout: float = 300) -> object:
    """`/v1/studio/jobs/{iş}/collage{sub}` çağrısı. Kapak yeniden kurulduğu için yazanlarda süre uzun."""
    base, headers, ca = editorial_studio._base()
    if editor is not None:
        headers["X-Editor"] = editor[:200]
    if mime:
        headers["Content-Type"] = mime
    url = f"{base}/v1/studio/jobs/{editorial_studio._job(job_id)}/collage{sub}"
    with editorial_studio._client(ca, timeout=timeout) as c:
        r = c.request(method, url, headers=headers, json=body if content is None else None, params=params,
                      content=content)
    if 400 <= r.status_code < 500:
        try:
            payload = r.json()
        except ValueError:
            payload = {"detail": "İstek kabul edilmedi."}
        raise Passthrough(r.status_code, payload)
    r.raise_for_status()
    return r.json()


def image(job_id: str, sub: str, width: int) -> tuple[bytes, str]:
    base, headers, ca = editorial_studio._base()
    with editorial_studio._client(ca, timeout=120) as c:
        r = c.get(f"{base}/v1/studio/jobs/{editorial_studio._job(job_id)}/collage{sub}", headers=headers,
                  params={"w": width})
    editorial_studio._raise(r)
    mime = r.headers.get("content-type", "").split(";")[0]
    if mime not in IMAGE_MIME:
        raise editorial_studio.StudioError(404, "Görsel bulunamadı.")
    if len(r.content) > 40 * 1024 * 1024:
        raise editorial_studio.StudioError(413, "Görsel çok büyük.")
    return r.content, mime


def register(app, deps: dict[str, Any]) -> None:
    """`deps`: auth = app.py `_books(request)` (oturum; (engine, tenant, user, _) döner), audit = admin_mod.audit,
    upload_mb = yönetim ayarındaki fotoğraf sınırı (MB)."""
    auth: Callable[[Request], Any] = deps["auth"]
    audit: Callable[..., Any] = deps["audit"]
    upload_mb: Callable[[], int] = deps["upload_mb"]

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except Passthrough as e:
            return JSONResponse(status_code=e.status, content=e.body)
        except editorial_studio.StudioError as e:
            raise HTTPException(e.status if e.status in (400, 404, 409, 413) else 400, str(e)) from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        except Exception:  # noqa: BLE001 — ayrıntı günlükte; editöre teknik hata metni gösterilmez
            log.exception("studio collage call failed")
            raise HTTPException(502, "Stüdyo şu an yanıt vermiyor.") from None

    def write(req: Request, method: str, job: str, sub: str, what: str, body: dict | None = None,
              detail: Any = None):
        engine, _tenant, user, _ = auth(req)
        out = call(request, method, job, sub, body=body, editor=user)
        if not isinstance(out, Response):
            audit(engine, user, "update", "studio_cover", f"{job}/kapak"[:120], what, detail)
        return out

    def img(result) -> Response:
        if isinstance(result, Response):
            return result
        data, mime = result
        return Response(content=data, media_type=mime, headers=CACHE)

    P = "/api/v1/editorial/studio/jobs/{job}/collage"

    @app.get(P)
    def editorial_collage_get(job: str, req: Request):
        auth(req)
        return call(request, "GET", job, "", timeout=60)

    @app.put(P + "/style")
    def editorial_collage_style(job: str, req: Request, body: dict[str, Any] | None = None):
        style = str((body or {}).get("style") or "")
        if style not in STYLES:
            raise HTTPException(400, "Kapak tarzı geçersiz.")
        return write(req, "PUT", job, "/style", f"kapak tarzı: {style}", {"style": style}, {"style": style})

    @app.post(P + "/photos")
    def editorial_collage_photos(job: str, req: Request, body: dict[str, Any] | None = None):
        b = body or {}
        try:
            count = int(b.get("count") or 3)
        except (TypeError, ValueError):
            raise HTTPException(400, "Aday sayısı geçersiz.") from None
        direction = str(b.get("direction") or "").strip()
        if len(direction) > DIRECTION_MAX:
            raise HTTPException(400, f"Yönlendirme en çok {DIRECTION_MAX} harf olabilir.")
        clean = {"count": count, "direction": direction}
        return write(req, "POST", job, "/photos", "kolaj fotoğraf adayları istendi", clean, clean)

    @app.put(P + "/upload")
    async def editorial_collage_upload(job: str, req: Request, filename: str = ""):
        engine, _tenant, user, _ = await run_in_threadpool(auth, req)
        mb = upload_mb()
        limit = mb * 1024 * 1024
        declared = req.headers.get("content-length") or ""
        if declared.isdigit() and int(declared) > limit:
            raise HTTPException(413, f"Fotoğraf en çok {mb} MB olabilir.")
        data = await req.body()
        if not data:
            raise HTTPException(400, "Dosya boş.")
        if len(data) > limit:
            raise HTTPException(413, f"Fotoğraf en çok {mb} MB olabilir.")
        mime = (req.headers.get("content-type") or "application/octet-stream").split(";")[0].strip().lower()
        if mime not in PHOTO_MIME:
            raise HTTPException(400, "Yalnız JPEG, PNG, WebP ya da HEIC fotoğraf yüklenebilir.")
        name = os.path.basename((filename or "").replace("\\", "/")).strip()[:200] or "fotograf"
        out = await run_in_threadpool(call, request, "PUT", job, "/upload", editor=user, params={"filename": name},
                                      content=data, mime=mime, timeout=600)
        if not isinstance(out, Response):
            audit(engine, user, "create", "studio_cover", f"{job}/kapak-foto"[:120], "kolaj fotoğrafı yüklendi",
                  {"name": name, "bytes": len(data)})
        return out

    @app.post(P + "/select")
    def editorial_collage_select(job: str, req: Request, body: dict[str, Any] | None = None):
        pid = str((body or {}).get("photo") or "")
        if not PHOTO.match(pid):
            raise HTTPException(404, "Fotoğraf bulunamadı.")
        return write(req, "POST", job, "/select", "kolaj fotoğrafı seçildi", {"photo": pid}, {"photo": pid})

    @app.post(P + "/layout")
    def editorial_collage_layout(job: str, req: Request, body: dict[str, Any] | None = None):
        n = (body or {}).get("layout")
        if n is not None:
            try:
                n = max(0, int(n))
            except (TypeError, ValueError):
                raise HTTPException(400, "Düzen numarası geçersiz.") from None
        return write(req, "POST", job, "/layout", "kolaj düzeni değişti", {"layout": n}, {"layout": n})

    @app.put(P + "/labels")
    def editorial_collage_labels(job: str, req: Request, body: dict[str, Any] | None = None):
        raw = (body or {}).get("labels")
        if raw is not None:
            if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
                raise HTTPException(400, "Etiketler yazı listesi olmalı.")
            if any(len(x) > LABEL_MAX for x in raw):
                raise HTTPException(400, f"Bir etiket en çok {LABEL_MAX} harf olabilir.")
        return write(req, "PUT", job, "/labels", "kolaj etiketleri değişti", {"labels": raw}, {"labels": raw})

    @app.get(P + "/photos/{pid}")
    def editorial_collage_photo(job: str, pid: str, req: Request, w: int = 480):
        auth(req)
        if not PHOTO.match(pid or ""):
            raise HTTPException(404, "Fotoğraf bulunamadı.")
        return img(call(image, job, f"/photos/{pid}", max(0, min(int(w), 2400))))

    @app.get(P + "/preview")
    def editorial_collage_preview(job: str, req: Request, w: int = 900):
        auth(req)
        return img(call(image, job, "/preview", max(120, min(int(w), 2400))))
