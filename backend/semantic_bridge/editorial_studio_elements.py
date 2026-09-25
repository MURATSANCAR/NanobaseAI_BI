"""Kitap Tasarım Stüdyosu — öğeler (süs/şekil) kataloğu ve efekt yazı önizlemeleri için köprü uçları.

Sözleşme: docs/analiz/studyo-sayfa-plani-sozlesme.md → «Efekt yazılar ve süs/şekiller». Stüdyo servisindeki
(`/v1/studio/jobs/{job}/plan/...`) üç okuyan ucun birebir vekili; yazan uç yok (şekil ve efekt sayfa PUT'uyla
kaydedilir). Oturum zorunlu (stüdyonun öteki uçlarıyla aynı `_books` denetimi); görseller PNG olarak aynen
geçer, bugünkü önizlemeler gibi kısa süre tarayıcı önbelleğinde tutulur. Genişlik ve önizleme yazısı olduğu gibi
geçer: sınır motorundadır ve açık hatadır (genişlik 16–4000 px); köprü sessizce kırpmaz, yazıya tavan koymaz (uzun
yazı önizlemede kutuya sığacak kadar küçülür).

app.py'de `_books` tanımından sonra (stüdyo bloğunun yanında) tek satırla bağlanır:
    editorial_studio_elements.register(app, {"auth": _books})
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable
from urllib.parse import urlencode

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response

from semantic_bridge import editorial_studio

log = logging.getLogger(__name__)

# Tür ve stil adları motorun kataloğundan gelir (frame, corner, … / burst, wave, …); yeni tür eklenince köprü
# değişmesin diye biçimle sınırlanır, listeyle değil. Serbest yol parçası servise geçmez.
NAME = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
STYLE = re.compile(r"^[a-z0-9_-]{0,32}$")
IMAGE_MIME = {"image/png"}
CACHE = {"Cache-Control": "private, max-age=300"}


def _name(v: str, what: str) -> str:
    if not NAME.match(v or ""):
        raise editorial_studio.StudioError(404, f"{what} bulunamadı.")
    return v


def _width(w: int) -> int:
    return int(w)


def catalog(job_id: str) -> dict:
    return editorial_studio.get_json(f"/v1/studio/jobs/{editorial_studio._job(job_id)}/plan/elements/catalog")


def element_preview(job_id: str, kind: str, width: int, style: str) -> tuple[bytes, str]:
    if not STYLE.match(style or ""):
        raise editorial_studio.StudioError(400, "Biçim adı geçersiz.")
    q = {"w": width, **({"style": style} if style else {})}
    return editorial_studio.get_bytes(
        f"/v1/studio/jobs/{editorial_studio._job(job_id)}/plan/elements/{_name(kind, 'Öğe')}/preview?{urlencode(q)}",
        IMAGE_MIME)


def effect_preview(job_id: str, style: str, width: int, text: str) -> tuple[bytes, str]:
    text = (text or "").strip()
    q = {"w": width, **({"text": text} if text else {})}
    return editorial_studio.get_bytes(
        f"/v1/studio/jobs/{editorial_studio._job(job_id)}/plan/effects/{_name(style, 'Efekt')}/preview?{urlencode(q)}",
        IMAGE_MIME)


def register(app, deps: dict[str, Any] | Any) -> None:
    """`deps["auth"]`: app.py'deki `_books(request)` — oturumu denetler (yoksa 401)."""
    auth: Callable[[Request], Any] = deps["auth"] if isinstance(deps, dict) else deps.auth

    def call(fn, *a):
        try:
            return fn(*a)
        except editorial_studio.StudioError as e:
            raise HTTPException(e.status if e.status in (400, 404, 409, 413) else 400, str(e)) from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        except Exception:  # noqa: BLE001 — ayrıntı günlükte; editöre teknik hata metni gösterilmez
            log.exception("studio elements call failed")
            raise HTTPException(502, "Stüdyo şu an yanıt vermiyor.") from None

    def image(result) -> Response:
        data, mime = result
        return Response(content=data, media_type=mime, headers=CACHE)

    @app.get("/api/v1/editorial/studio/jobs/{job}/plan/elements/catalog")
    def editorial_studio_elements_catalog(job: str, request: Request):
        auth(request)
        return JSONResponse(call(catalog, job), headers=CACHE)

    @app.get("/api/v1/editorial/studio/jobs/{job}/plan/elements/{kind}/preview")
    def editorial_studio_elements_preview(job: str, kind: str, request: Request, w: int = 192, style: str = ""):
        auth(request)
        return image(call(element_preview, job, kind, _width(w), style))

    @app.get("/api/v1/editorial/studio/jobs/{job}/plan/effects/{style}/preview")
    def editorial_studio_effects_preview(job: str, style: str, request: Request, w: int = 240, text: str = ""):
        auth(request)
        return image(call(effect_preview, job, style, _width(w), text))
