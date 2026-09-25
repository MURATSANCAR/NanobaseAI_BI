"""Yaş uygunluğu raporu uçları (stüdyo servisi; api.py'ye tek `include_router` ile bağlanır).

Yetki api.py'deki uygulama düzeyindeki bağımlılıktan gelir (Bearer kart anahtarı); yazan uçlar X-Editor ister.
Hepsi /v1/studio/jobs/{job}/age altında:

    GET  age                    rapor + editör kararları + hüküm + koşu durumu (rapor yoksa report: null)
    POST age/run                raporu çıkarır (arka planda; ekran GET ile bekler). Süren koşu varsa 409 BUSY
    POST age/decisions          {kind: finding|word|check, id, state|null, note?, choice?}
    POST age/words/apply        {lemma, form, to}: onaylanan karşılığı sayfa planının metnine uygular
    GET  age/pdf                indirilebilir rapor (PDF)
"""

from __future__ import annotations

import asyncio
import re
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import age_report, studio

router = APIRouter(prefix="/v1/studio/jobs/{job}/age")
_tasks: set[asyncio.Task] = set()


def _editor(x_editor: str = Header("")) -> str:
    if not x_editor.strip():
        raise HTTPException(400, "X-Editor gerekli")
    return x_editor.strip()[:200]


def _dir(job: str):
    try:
        return studio.job_dir(job)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404, "iş yok") from None


@router.get("")
async def age_view(job: str) -> dict:
    return await asyncio.to_thread(age_report.view, _dir(job))


@router.post("/run")
async def age_run(job: str, by: str = Depends(_editor)):
    d = _dir(job)
    if not (studio.read(d, "manuscript.json")):
        raise HTTPException(409, "Kitabın metni henüz okunmadı.")
    if not age_report.claim(d, by):
        return JSONResponse({"code": "BUSY", "detail": "Rapor zaten çıkarılıyor."}, status_code=409)
    t = asyncio.create_task(age_report.run(d, by))
    _tasks.add(t)
    t.add_done_callback(lambda x: (_tasks.discard(x), x.exception() if not x.cancelled() else None))
    return {"started": True}


class Decision(BaseModel):
    kind: Literal["finding", "word", "check"]
    id: str = Field(min_length=1, max_length=80)
    state: str | None = None
    note: str = Field("", max_length=500)
    choice: dict[str, str] | None = None


@router.post("/decisions")
async def age_decide(job: str, body: Decision, by: str = Depends(_editor)) -> dict:
    d = _dir(job)
    try:
        await asyncio.to_thread(age_report.decide, d, body.kind, body.id, body.state, by, body.note, body.choice)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return await asyncio.to_thread(age_report.view, d)


class Apply(BaseModel):
    lemma: str = Field(min_length=1, max_length=80)
    form: str = Field(min_length=1, max_length=80)
    to: str = Field(min_length=1, max_length=80)


@router.post("/words/apply")
async def age_apply(job: str, body: Apply, by: str = Depends(_editor)) -> dict:
    from . import plan as plan_mod
    d = _dir(job)
    if not re.fullmatch(r"[^\W\d_]+", body.form.strip()):
        raise HTTPException(400, "Biçim tek bir sözcük olmalı.")
    try:
        out = await asyncio.to_thread(age_report.apply_word, d, body.lemma, body.form, body.to, by)
    except plan_mod.NoPlan:
        return JSONResponse({"code": "NO_PLAN", "detail": "Sayfa planı yok; metni sayfa düzeni ekranında değiştirin."},
                            status_code=409)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return {**out, **(await asyncio.to_thread(age_report.view, d))}


@router.get("/pdf")
async def age_pdf(job: str) -> FileResponse:
    d = _dir(job)
    try:
        path = await asyncio.to_thread(age_report.pdf, d)
    except FileNotFoundError:
        raise HTTPException(404, "Önce raporu çıkarın.") from None
    title = re.sub(r"[^\w\-]+", "-", (studio.read(d, "state.json", {}).get("title") or job)).strip("-")
    return FileResponse(path, media_type="application/pdf", filename=f"{title}-yas-uygunlugu.pdf")
