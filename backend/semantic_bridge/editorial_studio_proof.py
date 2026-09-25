"""Kitap Tasarım Stüdyosu — 3B kitap ve baskı provası için köprü uçları.

Stüdyo servisindeki (`/v1/studio/jobs/{job}/proof…`, `apps/editor/src/editor/production/api_proof.py`) beş okuyan
ucun birebir vekili; yazan uç yok. Oturum zorunlu (stüdyonun öteki uçlarıyla aynı `_books` denetimi). Kâğıt adı,
katman ve genişlik burada da biçimle/aralıkla sınırlanır; servise serbest yol ya da sorgu gitmez. Görseller PNG
olarak aynen geçer, bugünkü önizlemeler gibi kısa süre tarayıcı önbelleğinde tutulur.

app.py'de `_books` tanımından sonra (stüdyo bloğunun yanında) bağlanır:
    from semantic_bridge import editorial_studio_proof
    editorial_studio_proof.register(app, {"auth": _books})
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

# Kâğıt anahtarları motorun tablosundan gelir (kuse, mat_kuse, hamur, samua); yeni kâğıt eklenince köprü
# değişmesin diye biçimle sınırlanır, listeyle değil.
PAPER = re.compile(r"^[a-z_]{1,24}$")
LAYERS = {"paper", "plain", "gamut", "tac"}
IMAGE_MIME = {"image/png"}
CACHE = {"Cache-Control": "private, max-age=300"}


def _paper(v: str) -> str:
    if not PAPER.match(v or ""):
        raise editorial_studio.StudioError(404, "Kâğıt bulunamadı.")
    return v


def _layer(v: str) -> str:
    if v not in LAYERS:
        raise editorial_studio.StudioError(400, "Katman geçersiz.")
    return v


def _page(n: int) -> int:
    if not 1 <= int(n) <= 9999:
        raise editorial_studio.StudioError(404, "Sayfa yok.")
    return int(n)


def _base(job: str) -> str:
    return f"/v1/studio/jobs/{editorial_studio._job(job)}/proof"


def book(job: str) -> dict:
    return editorial_studio.get_json(_base(job))


def page_image(job: str, n: int, paper: str, width: int, layer: str) -> tuple[bytes, str]:
    q = urlencode({"paper": _paper(paper), "w": max(120, min(int(width), 2400)), "layer": _layer(layer)})
    return editorial_studio.get_bytes(f"{_base(job)}/pages/{_page(n)}?{q}", IMAGE_MIME)


def cover_image(job: str, paper: str, width: int, layer: str) -> tuple[bytes, str]:
    q = urlencode({"paper": _paper(paper), "w": max(200, min(int(width), 3000)), "layer": _layer(layer)})
    return editorial_studio.get_bytes(f"{_base(job)}/cover?{q}", IMAGE_MIME)


def page_report(job: str, n: int, paper: str, width: int) -> dict:
    q = urlencode({"paper": _paper(paper), "w": max(120, min(int(width), 2400))})
    return editorial_studio.get_json(f"{_base(job)}/pages/{_page(n)}/report?{q}")


def cover_report(job: str, paper: str, width: int) -> dict:
    q = urlencode({"paper": _paper(paper), "w": max(200, min(int(width), 3000))})
    return editorial_studio.get_json(f"{_base(job)}/cover/report?{q}")


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
            log.exception("studio proof call failed")
            raise HTTPException(502, "Baskı provası şu an hazırlanamıyor.") from None

    def image(result) -> Response:
        data, mime = result
        return Response(content=data, media_type=mime, headers=CACHE)

    @app.get("/api/v1/editorial/studio/jobs/{job}/proof")
    def editorial_studio_proof_book(job: str, request: Request):
        auth(request)
        return JSONResponse(call(book, job), headers={"Cache-Control": "private, no-cache"})

    @app.get("/api/v1/editorial/studio/jobs/{job}/proof/pages/{n}")
    def editorial_studio_proof_page(job: str, n: int, request: Request, paper: str = "kuse", w: int = 900,
                                    layer: str = "paper"):
        auth(request)
        return image(call(page_image, job, n, paper, w, layer))

    @app.get("/api/v1/editorial/studio/jobs/{job}/proof/cover")
    def editorial_studio_proof_cover(job: str, request: Request, paper: str = "kuse", w: int = 1400,
                                     layer: str = "paper"):
        auth(request)
        return image(call(cover_image, job, paper, w, layer))

    @app.get("/api/v1/editorial/studio/jobs/{job}/proof/pages/{n}/report")
    def editorial_studio_proof_page_report(job: str, n: int, request: Request, paper: str = "kuse", w: int = 900):
        auth(request)
        return JSONResponse(call(page_report, job, n, paper, w), headers=CACHE)

    @app.get("/api/v1/editorial/studio/jobs/{job}/proof/cover/report")
    def editorial_studio_proof_cover_report(job: str, request: Request, paper: str = "kuse", w: int = 1400):
        auth(request)
        return JSONResponse(call(cover_report, job, paper, w), headers=CACHE)
