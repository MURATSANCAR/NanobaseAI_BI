"""Kapak arşivi uçları (stüdyo servisi; api.py'ye tek `include_router` ile bağlanır). Ayrıntı: library.py.

Yetki api.py'deki uygulama düzeyindeki bağımlılıktan gelir (Bearer kart anahtarı); yazan uçlar X-Editor ister.
Hepsi /v1/studio/library altında:

    GET  library                          sayılar (toplam, indirilen, bekleyen, hatalı) + indirme durumu
    GET  library/categories?audience=     kategori ağacı (her düğümde kapak sayısı) + okur kitlesi sayıları
    GET  library/covers?cat=&q=&audience=&sort=&page=&size=   süzülmüş, sayfalanmış kapak listesi
         cat: «Kök > Alt» yolu (altındakiler dahil); boş değer = kategorisiz. sort: sales | title
    GET  library/covers/{id}              tek kapak
    GET  library/covers/{id}/image?w=     görsel (WebP, genişlik 64–2400)
    POST library/items    {items: [...]}  köprünün beslemesi (T-soft + CRM); bekleyen görseller indirilir
    POST library/fetch    {retry_failed}  bekleyen (istenirse hatalı) görselleri yeniden indir
"""

from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from . import library

router = APIRouter(prefix="/v1/studio/library")
_tasks: set[asyncio.Task] = set()
Audience = Literal["CHILD", "YOUNG", "ADULT"]


def _editor(x_editor: str = Header("")) -> str:
    if not x_editor.strip():
        raise HTTPException(400, "X-Editor gerekli")
    return x_editor.strip()[:200]


def _start(retry_failed: bool = False) -> bool:
    if not library.claim_fetch():
        return False
    t = asyncio.create_task(library.fetch_pending(retry_failed))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)
    return True


@router.get("")
async def library_stats() -> dict:
    return await asyncio.to_thread(library.stats)


@router.get("/categories")
async def library_categories(audience: Audience | None = None) -> dict:
    return await asyncio.to_thread(library.tree, audience)


@router.get("/covers")
async def library_covers(cat: str | None = Query(None, max_length=600), q: str | None = Query(None, max_length=200),
                         audience: Audience | None = None, sort: Literal["sales", "title"] = "sales",
                         page: int = Query(1, ge=1), size: int = Query(60, ge=1, le=120)) -> dict:
    return await asyncio.to_thread(library.covers, cat, q, audience, sort, page, size)


@router.get("/covers/{cid}")
async def library_cover(cid: str) -> dict:
    out = await asyncio.to_thread(library.get, cid)
    if out is None:
        raise HTTPException(404, "kapak yok")
    return out


@router.get("/covers/{cid}/image")
async def library_image(cid: str, w: int = Query(360, ge=64, le=2400)):
    from .api import _image  # noqa: PLC0415 — api.py bu modülü sonda bağlar; döngüsel içe aktarma olmasın
    p = await asyncio.to_thread(library.image_path, cid)
    if p is None:
        raise HTTPException(404, "görsel yok")
    return await asyncio.to_thread(_image, p, w)


class Items(BaseModel):
    items: list[dict] = Field(default_factory=list, max_length=2000)


@router.post("/items")
async def library_items(body: Items, by: str = Depends(_editor)) -> dict:
    out = await asyncio.to_thread(library.upsert, body.items)
    return {**out, "fetching": _start() or library.fetch_state()["running"]}


class Fetch(BaseModel):
    retry_failed: bool = False


@router.post("/fetch")
async def library_fetch(body: Fetch, by: str = Depends(_editor)) -> dict:
    return {"started": _start(body.retry_failed), "fetch": library.fetch_state()}
