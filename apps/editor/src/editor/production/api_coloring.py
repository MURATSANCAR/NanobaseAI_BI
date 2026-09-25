"""Boyama / etkinlik kitabı uçları (coloring.py). api.py'de tek satırla bağlanır (`app.include_router`); yetki ve
hata kalıbı stüdyonun öteki uçlarıyla aynı (Bearer; yazanlarda X-Editor; iş kuyruğu Temporal `editor-production`).

    GET  /v1/studio/jobs/{job}/coloring                  kaynak kitapta: yapılabilir etkinlikler, türetilmiş işler;
                                                         boyama işinde: kısa cümleler, etkinlikler, taslak çizgiler
    POST /v1/studio/jobs/{job}/coloring                  {mode, activities:[{kind, source?, count?}], captions}
                                                         → yeni boyama işi {id, workflow}; kaynak iş değişmez
    POST /v1/studio/jobs/{job}/coloring/retry            boyama işini kaldığı yerden yeniden koşar
    POST /v1/studio/jobs/{job}/coloring/sentences        {items:[{aid, text?, approved?}]} kısa cümle düzelt/onayla
    POST /v1/studio/jobs/{job}/coloring/art/{aid}/redraw çizgiyi görsel modelle yeniden çiz (GPU işi, taslak)
"""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import api
from . import coloring
from . import plan as plan_mod
from . import studio

router = APIRouter(dependencies=[Depends(api.authorize)])
C = "/v1/studio/jobs/{job}/coloring"


class Act(BaseModel):
    kind: str = Field(max_length=40)
    source: str | None = Field(default=None, max_length=80)
    count: int | None = Field(default=None, ge=1, le=99)


class NewColoring(BaseModel):
    mode: str = Field(pattern="^(coloring|coloring_activities)$")
    activities: list[Act] = Field(default_factory=list)
    captions: str = Field(default="model", pattern="^(model|rule)$")


class Sentence(BaseModel):
    aid: str = Field(max_length=40)
    text: str | None = Field(default=None, max_length=400)
    approved: bool | None = None


class Sentences(BaseModel):
    items: list[Sentence]


async def _start_build(d, by: str) -> str:
    wf = f"studio-{d.name}-boyama-{int(time.time())}"
    await api._start(d, "ColoringBook", [d.name], wf, {"key": "boyama", "mode": "coloring"})
    return wf


@router.get(C)
async def coloring_get(job: str) -> dict:
    d = api._dir(job)
    if coloring.is_coloring(d):
        out = await asyncio.to_thread(coloring.view, d)
        out["busy"] = await api._busy(d)
        return out
    return await asyncio.to_thread(coloring.source_view, d)


@router.post(C)
async def coloring_new(job: str, body: NewColoring, by: str = Depends(api.editor)) -> dict:
    """Kaynak kitaptan yeni boyama/etkinlik işi. Kaynağın resimleri hazır olmalı (hat sürüyorsa 409)."""
    src = api._dir(job)
    if coloring.is_coloring(src):
        raise HTTPException(400, "Bu iş zaten bir boyama kitabı; kaynak kitabın sayfasından üretin")
    b = await api._busy(src)
    if b and not b.get("error") and b.get("key") == "hat":
        raise api.Coded(409, "BUSY", "Kitabın resimleri hâlâ üretiliyor; bitince tekrar deneyin")
    try:
        d = await asyncio.to_thread(coloring.new_job, src, by, body.mode,
                                    [a.model_dump(exclude_none=True) for a in body.activities], body.captions)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    wf = await _start_build(d, by)
    return {"id": d.name, "workflow": wf}


@router.post(C + "/retry")
async def coloring_retry(job: str, by: str = Depends(api.editor)) -> dict:
    d = api._dir(job)
    if not coloring.is_coloring(d):
        raise HTTPException(400, "Bu iş bir boyama kitabı değil")
    b = await api._busy(d)
    if b and not b.get("error"):
        raise api.Coded(409, "BUSY", "Bu kitapta süren bir iş var; bitince tekrar deneyin")
    return {"id": d.name, "workflow": await _start_build(d, by)}


@router.post(C + "/sentences")
async def coloring_sentences(job: str, body: Sentences, by: str = Depends(api.editor)) -> dict:
    d = api._dir(job)
    if not coloring.is_coloring(d):
        raise HTTPException(400, "Bu iş bir boyama kitabı değil")
    return await api._write(coloring.set_sentences, d, [i.model_dump(exclude_unset=True) for i in body.items], by)


@router.post(C + "/art/{aid}/redraw")
async def coloring_redraw(job: str, aid: str, by: str = Depends(api.editor)) -> dict:
    """Çizgiyi görsel modelle yeniden çizdirir (GPU işi; sırada iş varsa bekler). Sonuç yeni sürümdür ve taslaktır."""
    d = api._dir(job)
    if not coloring.is_coloring(d):
        raise HTTPException(400, "Bu iş bir boyama kitabı değil")
    if not plan_mod.ART_ID.match(aid) or aid not in studio.studio_state(d)["pages"]:
        raise HTTPException(404, "çizgi yok")
    await api._gpu_free(d)
    jid = plan_mod.new_id("j")
    wf = f"studio-{job}-cizgi-{aid}-{int(time.time())}"
    plan_mod.job_record(d, jid, kind="art", status="queued", source=aid, page=None, by=by, workflow=wf,
                        note="Zeki AI ile çizgi")
    await api._start(d, "ColoringRedraw", [job, jid, aid, by], wf,
                     {"key": aid, "mode": "lineart-model", "job": jid})
    return {"workflow": wf, "job": jid}
