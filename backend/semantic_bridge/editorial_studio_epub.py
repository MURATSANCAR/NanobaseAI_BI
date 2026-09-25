"""Kitap Tasarım Stüdyosu — e-kitap (EPUB) köprü uçları.

Stüdyo servisindeki `/v1/studio/jobs/{job}/epub…` uçlarının birebir vekili (servis: apps/editor/src/editor/production/
api_epub.py). Oturum zorunlu (stüdyonun öteki uçlarıyla aynı `_books` denetimi); yazanlarda `X-Editor` oturumdaki AD
hesabıdır ve denetim kaydına geçer. Kimlikler biçimle sınırlanır; servise serbest yol gitmez. Önizleme dosyaları
(e-kitabın içinden XHTML, stil, görsel, font) yalnız izinli türlerle ve betik çalıştırmayan güvenlik başlığıyla döner.

app.py'de `_books` tanımından sonra (stüdyo bloğunun yanında) bağlanır:
    from semantic_bridge import editorial_studio_epub
    editorial_studio_epub.register(app, {"auth": _books, "audit": admin_mod.audit})
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable

from fastapi import HTTPException, Request
from fastapi.responses import Response

from semantic_bridge import editorial_studio

log = logging.getLogger(__name__)

KEY = re.compile(r"^(kapak|a_[0-9a-f]{8}|g_[0-9a-f]{8})$")          # kapak, sayfa resmi, figür/fotoğraf
BUILD = re.compile(r"^[0-9a-f]{12}$")
# E-kitabın içindeki yol: harf/rakam/_/- klasörler, tek noktalı dosya adı; «..» ve mutlak yol olamaz.
PATH = re.compile(r"^(?:[A-Za-z0-9_-]+/){0,4}[A-Za-z0-9_-]+\.(xhtml|css|jpg|png|svg|ttf|otf)$")
CONTENT_MIME = {"application/xhtml+xml", "text/css", "image/jpeg", "image/png", "image/svg+xml", "font/ttf", "font/otf"}
IMAGE_MIME = {"image/png", "image/jpeg"}
LAYOUTS = {"auto", "fixed", "reflow"}
EPUB_MAX = 800 * 1024 * 1024
PREVIEW_HEADERS = {"Cache-Control": "private, max-age=3600",
                   "Content-Security-Policy": "script-src 'none'; object-src 'none'; frame-ancestors 'self'",
                   "X-Content-Type-Options": "nosniff"}


def _base(job_id: str) -> str:
    return f"/v1/studio/jobs/{editorial_studio._job(job_id)}/epub"


def _key(key: str) -> str:
    if not KEY.match(key or ""):
        raise editorial_studio.StudioError(404, "Görsel bulunamadı.")
    return key


def view(job_id: str) -> dict:
    return editorial_studio.get_json(_base(job_id))


def build(job_id: str, layout: str, editor: str) -> dict:
    if layout not in LAYOUTS:
        raise editorial_studio.StudioError(400, "E-kitap biçimi geçersiz.")
    return editorial_studio.post_json(_base(job_id), {"layout": layout}, editor)


def _put(path: str, body: dict, editor: str) -> dict:
    base, headers, ca = editorial_studio._base()
    headers["X-Editor"] = editor[:200]
    with editorial_studio._client(ca, timeout=60) as c:
        r = c.put(base + path, headers=headers, json=body)
    editorial_studio._raise(r)
    return r.json()


def set_eisbn(job_id: str, eisbn: str, editor: str) -> dict:
    return _put(f"{_base(job_id)}/meta", {"eisbn": str(eisbn or "")[:40]}, editor)


def alts(job_id: str) -> dict:
    return editorial_studio.get_json(f"{_base(job_id)}/alt")


def set_alt(job_id: str, key: str, text: str, editor: str) -> dict:
    return _put(f"{_base(job_id)}/alt/{_key(key)}", {"text": str(text or "")[:2000]}, editor)


def suggest_alt(job_id: str, key: str, editor: str) -> dict:
    base, headers, ca = editorial_studio._base()
    headers["X-Editor"] = editor[:200]
    with editorial_studio._client(ca, timeout=240) as c:            # model önerisi birkaç saniye sürer
        r = c.post(f"{base}{_base(job_id)}/alt/{_key(key)}/suggest", headers=headers, json={})
    editorial_studio._raise(r)
    return r.json()


def alt_image(job_id: str, key: str, width: int) -> tuple[bytes, str]:
    return editorial_studio.get_bytes(f"{_base(job_id)}/alt/{_key(key)}/image?w={int(width)}", IMAGE_MIME)


def epub_file(job_id: str) -> tuple[bytes, str]:
    return editorial_studio.get_bytes(f"{_base(job_id)}/file", {"application/epub+zip"}, limit=EPUB_MAX)


def content(job_id: str, build_id: str, path: str) -> tuple[bytes, str]:
    if not BUILD.match(build_id or "") or not PATH.match(path or ""):
        raise editorial_studio.StudioError(404, "Dosya bulunamadı.")
    return editorial_studio.get_bytes(f"{_base(job_id)}/content/{build_id}/{path}", CONTENT_MIME)


def register(app, deps: dict[str, Any] | Any) -> None:
    """`deps["auth"]`: app.py'deki `_books(request)` → (engine, tenant, user, is_admin); `deps["audit"]`:
    `admin_mod.audit(engine, user, action, kind, obj, what, detail)`."""
    auth: Callable[[Request], Any] = deps["auth"] if isinstance(deps, dict) else deps.auth
    audit: Callable[..., Any] | None = deps.get("audit") if isinstance(deps, dict) else getattr(deps, "audit", None)

    def call(fn, *a, what: str = "Stüdyo şu an yanıt vermiyor."):
        try:
            return fn(*a)
        except editorial_studio.StudioError as e:
            raise HTTPException(e.status if e.status in (400, 404, 409, 413) else 400, str(e)) from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        except Exception:  # noqa: BLE001 — ayrıntı günlükte; editöre teknik hata metni gösterilmez
            log.exception("studio epub call failed")
            raise HTTPException(502, what) from None

    def write(request: Request, fn, *a, action: str, obj: str, what: str, detail: Any = None):
        engine, _tenant, user, _ = auth(request)
        out = call(fn, *a, user)
        if audit is not None:
            try:
                audit(engine, user, action, "studio_epub", obj[:120], what, detail)
            except Exception:  # noqa: BLE001 — denetim kaydı düşmezse işlem geri alınmaz, günlüğe yazılır
                log.exception("studio epub audit failed")
        return out

    async def body(request: Request) -> dict:
        try:
            b = await request.json()
        except Exception:  # noqa: BLE001
            b = None
        if not isinstance(b, dict):
            raise HTTPException(400, "Gövde bir nesne olmalı.")
        return b

    P = "/api/v1/editorial/studio/jobs/{job}/epub"

    @app.get(P)
    def editorial_studio_epub_view(job: str, request: Request):
        auth(request)
        return call(view, job)

    @app.post(P)
    async def editorial_studio_epub_build(job: str, request: Request):
        b = await body(request)
        layout = str(b.get("layout") or "auto")
        return write(request, build, job, layout, action="create", obj=job, what=f"e-kitap üretimi ({layout})",
                     detail={"layout": layout})

    @app.get(P + "/file")
    def editorial_studio_epub_file(job: str, request: Request):
        engine, _tenant, user, _ = auth(request)
        data, _mime = call(epub_file, job, what="E-kitap şu an alınamıyor.")
        if audit is not None:
            try:
                audit(engine, user, "export", "studio_epub", job, "e-kitap indirildi", None)
            except Exception:  # noqa: BLE001
                log.exception("studio epub audit failed")
        return Response(content=data, media_type="application/epub+zip",
                        headers={"Content-Disposition": f'attachment; filename="{job}.epub"',
                                 "Cache-Control": "private, no-store"})

    @app.put(P + "/meta")
    async def editorial_studio_epub_meta(job: str, request: Request):
        b = await body(request)
        return write(request, set_eisbn, job, str(b.get("eisbn") or ""), action="update", obj=job, what="e-ISBN",
                     detail={"eisbn": b.get("eisbn")})

    @app.get(P + "/alt")
    def editorial_studio_epub_alts(job: str, request: Request):
        auth(request)
        return call(alts, job)

    @app.put(P + "/alt/{key}")
    async def editorial_studio_epub_alt(job: str, key: str, request: Request):
        b = await body(request)
        return write(request, set_alt, job, key, str(b.get("text") or ""), action="update", obj=f"{job}/{key}",
                     what="alt metin")

    @app.post(P + "/alt/{key}/suggest")
    def editorial_studio_epub_alt_suggest(job: str, key: str, request: Request):
        return write(request, suggest_alt, job, key, action="update", obj=f"{job}/{key}", what="alt metin önerisi")

    @app.get(P + "/alt/{key}/image")
    def editorial_studio_epub_alt_image(job: str, key: str, request: Request, w: int = 240):
        auth(request)
        data, mime = call(alt_image, job, key, max(64, min(int(w), 1200)))
        return Response(content=data, media_type=mime, headers={"Cache-Control": "private, max-age=300"})

    @app.get(P + "/content/{build_id}/{path:path}")
    def editorial_studio_epub_content(job: str, build_id: str, path: str, request: Request):
        auth(request)
        data, mime = call(content, job, build_id, path)
        return Response(content=data, media_type=mime, headers=PREVIEW_HEADERS)
