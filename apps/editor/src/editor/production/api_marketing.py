"""Pazarlama kiti uçları (marketing.py), hepsi /v1/studio/jobs/{job}/marketing altında. api.py'de tek satırla
bağlanır (`app.include_router`); yetki api.py'nin uygulama düzeyindeki Bearer denetimidir, yazanlar `X-Editor` ister.

    GET    marketing                          bütün görünüm (işler, arka kapak, ürün, sosyal, kılavuz, kayıt)
    POST   marketing/{kind}/generate          kind: back-cover | product | guide; ürün için {limits} (SEO eşikleri)
    PUT    marketing/back-cover               {text}      taslak (onay düşer)
    POST   marketing/back-cover/approve       {text}      onay (kim, ne zaman)
    POST   marketing/back-cover/apply                     onaylı yazıyı kapağa uygula (kapak yeniden dizilir)
    POST   marketing/back-cover/revert                    kayıtlı tanıtım metnine dön
    PUT    marketing/product                  {page}      düzeltme (onay düşer)
    POST   marketing/product/approve          {page}
    POST   marketing/product/seo              {product_id, proposal_id}  köprü SEO önerisini kaydedince bağ
    GET    marketing/product/export?format=html|txt|json   (onaylıysa)
    POST   marketing/social                   {template, visual, source, headline, effect, color, quote}
    GET    marketing/social/zip                            onaylı görseller (zip)
    GET    marketing/social/sources/{key}?w=               seçilebilir görselin küçüğü
    GET    marketing/social/{sid}?w=&download=1            görsel (indirme onaylıysa)
    DELETE marketing/social/{sid}
    POST   marketing/social/{sid}/approve     {ok}
    PUT    marketing/guide                    {guide}
    POST   marketing/guide/approve            {guide}     onay + PDF
    GET    marketing/guide/pdf                             (onaylıysa)

Metin üretimi arka planda (bu süreçte) koşar; ekran `tasks`'tan izler. T-soft'a buradan hiçbir şey gitmez.
"""

from __future__ import annotations

import asyncio
import io
import re
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from . import marketing as mk
from . import studio

router = APIRouter(prefix="/v1/studio/jobs/{job}/marketing")
KEY = re.compile(r"^(?:kapak|[0-9]{1,4}|a_[0-9a-f]{8}|[A-Za-z0-9][A-Za-z0-9_-]{0,63})$")


def _editor(x_editor: str = Header("")) -> str:
    if not x_editor.strip():
        raise HTTPException(400, "X-Editor gerekli")
    return x_editor.strip()[:200]


def _dir(job: str) -> Path:
    try:
        d = studio.job_dir(job)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404, "iş yok") from None
    if not (d / "manuscript.json").exists():
        raise HTTPException(409, "Kitabın içeriği henüz okunmadı; hat ilerleyince pazarlama kiti açılır.")
    return d


async def _call(fn, *a, **kw):
    try:
        return await asyncio.to_thread(fn, *a, **kw)
    except mk.NotReady as e:
        raise HTTPException(409, str(e)) from None
    except KeyError as e:
        raise HTTPException(404, str(e).strip("'\"") or "bulunamadı") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


@router.get("")
async def view(job: str) -> Response:
    return JSONResponse(await _call(mk.view, _dir(job)), headers={"Cache-Control": "no-store"})


class Generate(BaseModel):
    limits: dict[str, int] | None = None


@router.post("/{kind}/generate")
async def generate(job: str, kind: Literal["back-cover", "product", "guide"], body: Generate | None = None,
                   by: str = Depends(_editor)) -> dict:
    d = _dir(job)
    llm = mk.make_llm(d)
    if kind == "back-cover":
        work = lambda progress: mk.gen_back(d, llm, by, progress)  # noqa: E731
    elif kind == "product":
        lim = mk.limits((body.limits if body else None) or {})
        work = lambda progress: mk.gen_product(d, llm, by, lim, progress)  # noqa: E731
    else:
        work = lambda progress: mk.gen_guide(d, llm, by, progress)  # noqa: E731
    try:
        return {"task": mk.start(d, kind, by, work)}
    except mk.NotReady as e:
        raise HTTPException(409, str(e)) from None


class Text(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


@router.put("/back-cover")
async def back_save(job: str, body: Text, by: str = Depends(_editor)) -> dict:
    return await _call(mk.save_back, _dir(job), body.text, by)


@router.post("/back-cover/approve")
async def back_approve(job: str, body: Text, by: str = Depends(_editor)) -> dict:
    return await _call(mk.approve_back, _dir(job), body.text, by)


@router.post("/back-cover/apply")
async def back_apply(job: str, by: str = Depends(_editor)) -> dict:
    return await _call(mk.apply_back, _dir(job), by)


@router.post("/back-cover/revert")
async def back_revert(job: str, by: str = Depends(_editor)) -> dict:
    return await _call(mk.revert_back, _dir(job), by)


class Page(BaseModel):
    page: dict


@router.put("/product")
async def product_save(job: str, body: Page, by: str = Depends(_editor)) -> dict:
    return await _call(mk.save_product, _dir(job), body.page, by)


@router.post("/product/approve")
async def product_approve(job: str, body: Page, by: str = Depends(_editor)) -> dict:
    return await _call(mk.save_product, _dir(job), body.page, by, True)


class SeoLink(BaseModel):
    product_id: str = Field(min_length=1, max_length=40)
    proposal_id: str = Field(min_length=1, max_length=40)


@router.post("/product/seo")
async def product_seo(job: str, body: SeoLink, by: str = Depends(_editor)) -> dict:
    return await _call(mk.link_seo, _dir(job), body.product_id, body.proposal_id, by)


@router.get("/product/export")
async def product_export(job: str, format: Literal["html", "txt", "json"] = Query("html")) -> Response:
    data, mime, name = await _call(mk.product_export, _dir(job), format)
    return Response(data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"',
                                                    "Cache-Control": "no-store"})


class Social(BaseModel):
    template: Literal["kare", "dikey", "yatay"]
    visual: Literal["cover", "page", "quote"]
    source: str | None = Field(default=None, max_length=64)
    headline: str = Field(default="", max_length=300)
    effect: Literal["plain", "shadow", "outline", "burst", "rainbow"] = "plain"
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    quote: str | None = Field(default=None, max_length=2000)


@router.post("/social")
async def social_add(job: str, body: Social, by: str = Depends(_editor)) -> dict:
    return await _call(mk.add_social, _dir(job), body.model_dump(), by)


@router.get("/social/zip")
async def social_zip(job: str) -> Response:
    data = await _call(mk.social_zip, _dir(job))
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="sosyal-medya.zip"', "Cache-Control": "no-store"})


def _png(im, w: int) -> Response:
    if w > 0 and im.width > w:
        im = im.resize((w, max(1, round(im.height * w / im.width))))
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=w > 0)
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


@router.get("/social/sources/{key}")
async def social_source(job: str, key: str, w: int = Query(320, ge=64, le=1600)) -> Response:
    if not KEY.match(key):
        raise HTTPException(404, "Görsel bulunamadı.")
    im = await _call(mk.source_image, _dir(job), key, max(w * 2, 400))
    return _png(im, w)


@router.get("/social/{sid}")
async def social_image(job: str, sid: str, w: int = Query(0, ge=0, le=2400), download: bool = False) -> Response:
    d = _dir(job)
    if download:
        path, name = await _call(mk.social_download, d, sid)
        return FileResponse(path, media_type="image/png", filename=name, headers={"Cache-Control": "no-store"})
    path = await _call(mk.social_path, d, sid)
    if w <= 0:
        return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})
    from PIL import Image
    return _png(await asyncio.to_thread(lambda: Image.open(path).convert("RGB")), w)


@router.delete("/social/{sid}")
async def social_delete(job: str, sid: str, by: str = Depends(_editor)) -> dict:
    await _call(mk.delete_social, _dir(job), sid, by)
    return {"ok": True}


class Approve(BaseModel):
    ok: bool = True


@router.post("/social/{sid}/approve")
async def social_approve(job: str, sid: str, body: Approve, by: str = Depends(_editor)) -> dict:
    return await _call(mk.approve_social, _dir(job), sid, body.ok, by)


class Guide(BaseModel):
    guide: dict


@router.put("/guide")
async def guide_save(job: str, body: Guide, by: str = Depends(_editor)) -> dict:
    return await _call(mk.save_guide, _dir(job), body.guide, by)


@router.post("/guide/approve")
async def guide_approve(job: str, body: Guide, by: str = Depends(_editor)) -> dict:
    return await _call(mk.save_guide, _dir(job), body.guide, by, True)


@router.get("/guide/pdf")
async def guide_pdf(job: str) -> Response:
    d = _dir(job)
    path = await _call(mk.guide_pdf, d)
    title = re.sub(r"[^\w\-]+", "-", studio._manuscript(d).title).strip("-") or job
    return FileResponse(path, media_type="application/pdf", filename=f"{title}-ogretmen-kilavuzu.pdf",
                        headers={"Cache-Control": "no-store"})
