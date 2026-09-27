"""Sesli okumada ifade katmanı uçları (stüdyo servisi; api.py'ye tek `include_router` ile bağlanır). Hepsi
/v1/studio/jobs/{job}/narration/pages/{pid}/expression altında; yazanlarda X-Editor. Modül: expression.py.

    GET  …/expression                  cümleler (okuma sırasıyla), her cümlenin ifadesi + vurgusu + kaynağı, etiketler,
                                       sayfanın ses durumu (ifade değişince «stale»)
    PUT  …/expression                  {items: [{key, label, emphasis: [kelime]}]}  editörün işareti (yalnız verilenler)
    POST …/expression/suggest          {replace_editor?: bool} Zeki AI önerisi (editörün işaretine dokunmaz)
    POST …/expression/sample           {key, label, emphasis} bu cümleyi dinle (audio/mpeg; kaydedilmez)

Hatalar gövdede `code`: NO_PLAN (404), PREPARING (409), BUSY (409: bu kitapta GPU işi sürüyor, ana model kapalı),
MODEL_BUSY (503: Zeki AI şu an yanıt veremiyor), NO_VOICE (503), INVALID (400: bilinmeyen ifade / cümlede olmayan kelime).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from . import expression as X
from . import plan as plan_mod
from .api_narration import PID, _dir, _editor, _guard

router = APIRouter()
P = "/v1/studio/jobs/{job}/narration/pages/{pid}/expression"


def _coded(status: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse({"code": code, "detail": detail}, status_code=status)


def _page(job: str, pid: str) -> Path:
    if not PID.match(pid):
        raise HTTPException(404, "sayfa yok")
    d = _dir(job)
    pl = plan_mod.load(d) or {}
    if pid not in {p["id"] for p in pl.get("pages", [])}:
        raise HTTPException(404, "sayfa yok")
    return d


@router.get(P)
@_guard
async def expression_view(job: str, pid: str) -> dict:
    d = _page(job, pid)
    return await asyncio.to_thread(X.view, d, pid)


class Item(BaseModel):
    key: str = Field(max_length=100)
    label: str = Field(max_length=20)
    emphasis: list[str] = []


class Marks(BaseModel):
    items: list[Item]


@router.put(P)
@_guard
async def expression_set(job: str, pid: str, body: Marks, by: str = Depends(_editor)):
    d = _page(job, pid)
    try:
        return await asyncio.to_thread(X.set_marks, d, pid, [i.model_dump() for i in body.items], by)
    except KeyError:
        return _coded(400, "INVALID", "Bu cümle sayfada yok; sayfa değişmiş olabilir, yenileyin.")
    except ValueError as e:
        return _coded(400, "INVALID", str(e))


class Suggest(BaseModel):
    replace_editor: bool = False


@router.post(P + "/suggest")
@_guard
async def expression_suggest(job: str, pid: str, body: Suggest | None = None, by: str = Depends(_editor)):
    from .api import _busy
    from ..llm import ModelError
    from .run import FileLlm
    d = _page(job, pid)
    b = await _busy(d)
    if b and not b.get("error"):
        return _coded(409, "BUSY", "Bu kitapta süren bir üretim var; bitince Zeki AI önerisini isteyin.")
    try:
        return await X.suggest(d, pid, FileLlm(d / "provenance.jsonl"), by, bool(body and body.replace_editor))
    except ModelError:
        return _coded(503, "MODEL_BUSY", "Zeki AI şu an yanıt veremiyor; biraz sonra yeniden deneyin.")


class SampleBody(BaseModel):
    key: str = Field(max_length=100)
    label: str = Field(default="notr", max_length=20)
    emphasis: list[str] = []


@router.post(P + "/sample")
@_guard
async def expression_sample(job: str, pid: str, body: SampleBody, _by: str = Depends(_editor)):
    d = _page(job, pid)
    try:
        data = await X.sample_sentence(d, pid, body.key, body.label, body.emphasis)
    except KeyError:
        return _coded(400, "INVALID", "Bu cümle sayfada yok; sayfa değişmiş olabilir, yenileyin.")
    except ValueError as e:
        return _coded(400, "INVALID", str(e))
    return Response(data, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


