"""Kapak tarzı ve kolaj kapak uçları (collage.py). api.py'de tek satırla bağlanır; yetki uygulamanın genel
bağımlılığından (Bearer), yazanlarda X-Editor. Hepsi /v1/studio/jobs/{job}/collage altında:

    GET  collage                          görünüm: tarz, adaylar, seçili, düzen, etiketler, iş durumu, taslak uyarısı
    PUT  collage/style      {style}       illustrated | collage | typographic → kapak yeniden kurulur
    POST collage/photos     {count, direction}  model adayları (GPU işi, Temporal CollagePhotos) → {workflow}
    PUT  collage/upload?filename=         ham gövde: editörün fotoğrafı (STUDIO_UPLOAD_MB; aşan 413 TOO_LARGE)
    POST collage/select     {photo}       aday seçimi
    POST collage/layout     {layout?}     «başka düzen» (verilmezse bir sonraki; sayı verilirse o düzen)
    PUT  collage/labels     {labels|null} etiket şeritleri (null: başlıktan otomatik); sığmayan şerit 400
    GET  collage/photos/{pid}?w=          aday görseli (w=0 özgün)
    GET  collage/preview?w=               ön kapak önizlemesi (taşma paylı ön panel)

GPU işi sürüyorsa aday üretimi 409 BUSY döner; öteki yazımlar süren işi beklemez.
"""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from . import collage
from .api import Coded, _busy, _dir, _image, _start, editor, upload_mb

router = APIRouter()
C = "/v1/studio/jobs/{job}/collage"


def _ready(job: str):
    d = _dir(job)
    if not (d / "spec.json").exists() or not (d / "manuscript.json").exists():
        raise HTTPException(409, "Kapak için önce kitabın yerleşimi bitmeli")
    return d


async def _call(fn, *a):
    try:
        return await asyncio.to_thread(fn, *a)
    except KeyError as e:
        raise HTTPException(404, str(e.args[0] if e.args else e)) from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


async def _view(d) -> dict:
    return {**await asyncio.to_thread(collage.view, d), "busy": await _busy(d)}


@router.get(C)
async def collage_get(job: str) -> dict:
    return await _view(_ready(job))


class StyleBody(BaseModel):
    style: str


@router.put(C + "/style")
async def collage_style(job: str, body: StyleBody, by: str = Depends(editor)) -> dict:
    d = _ready(job)
    await _call(collage.set_style, d, body.style, by)
    return await _view(d)


class PhotosBody(BaseModel):
    count: int = Field(3, ge=1, le=6)
    direction: str = Field("", max_length=1200)


@router.post(C + "/photos")
async def collage_photos(job: str, body: PhotosBody, by: str = Depends(editor)) -> dict:
    """Model adayları (GPU işi). Bitince adaylar görünüme düşer; seçili fotoğraf yoksa ilki seçilir."""
    d = _ready(job)
    b = await _busy(d)
    if b and not b.get("error"):
        raise Coded(409, "BUSY", "Bu kitapta süren bir üretim var; bitince tekrar deneyin")
    wf = f"studio-{job}-kolaj-{int(time.time())}"
    await asyncio.to_thread(collage.set_job, d, status="queued", done=0, total=body.count, error=None, workflow=wf,
                            by=by, since=time.time(), made=None)
    await _start(d, "CollagePhotos", [job, body.count, body.direction, by], wf,
                 {"key": "kolaj", "mode": "collage", "count": body.count})
    return {"workflow": wf}


@router.put(C + "/upload")
async def collage_upload(job: str, request: Request, filename: str = Query(..., min_length=1, max_length=300),
                         by: str = Depends(editor)) -> dict:
    d = _ready(job)
    mb = upload_mb()
    buf = bytearray()
    async for chunk in request.stream():
        buf += chunk
        if len(buf) > mb * 1024 * 1024:
            raise Coded(413, "TOO_LARGE", f"Dosya {mb} MB sınırını aşıyor", limit_mb=mb)
    if not buf:
        raise HTTPException(400, "Boş dosya")
    rec = await _call(collage.add_upload, d, bytes(buf), filename, by)
    return {**await _view(d), "photo": rec["id"]}


class SelectBody(BaseModel):
    photo: str = Field(pattern=r"^k_[0-9a-f]{8}$")


@router.post(C + "/select")
async def collage_select(job: str, body: SelectBody, by: str = Depends(editor)) -> dict:
    d = _ready(job)
    await _call(collage.select, d, body.photo, by)
    return await _view(d)


class LayoutBody(BaseModel):
    layout: int | None = Field(None, ge=0)


@router.post(C + "/layout")
async def collage_layout(job: str, body: LayoutBody, by: str = Depends(editor)) -> dict:
    d = _ready(job)
    await _call(collage.set_layout, d, body.layout, by)
    return await _view(d)


class LabelsBody(BaseModel):
    labels: list[str] | None = None


@router.put(C + "/labels")
async def collage_labels(job: str, body: LabelsBody, by: str = Depends(editor)) -> dict:
    d = _ready(job)
    await _call(collage.set_labels, d, body.labels, by)
    return await _view(d)


@router.get(C + "/photos/{pid}")
def collage_photo(job: str, pid: str, w: int = Query(480, ge=0, le=2400)) -> Response:
    d = _ready(job)
    if not collage.PHOTO_ID.match(pid):
        raise HTTPException(404, "fotoğraf yok")
    ph = next((p for p in collage.load(d)["photos"] if p["id"] == pid), None)
    if ph is None:
        raise HTTPException(404, "fotoğraf yok")
    path = d / ph["path"]
    if w <= 0:
        return FileResponse(path, media_type="image/png" if path.suffix == ".png" else "image/jpeg",
                            headers={"Cache-Control": "private, max-age=3600"})
    return _image(path, w)


@router.get(C + "/preview")
def collage_preview(job: str, w: int = Query(900, ge=120, le=2400)) -> Response:
    d = _ready(job)
    try:
        return _image(collage.front_preview(d, w), 0)
    except FileNotFoundError:
        raise HTTPException(404, "kapak henüz kurulmadı") from None
