"""Okur araçları ve sürüm farkı uçları (api.py'ye `include_router` ile takılır; yetki api.py'nin uygulama düzeyi
bağımlılığından gelir: Bearer kart anahtarı; yazanlar X-Editor ister).

    GET  plan/reader                               okur yaşı, resimli mi, son okumalar (çocuk gözü, sayfa çevirme)
    POST plan/reader/child   {passes}              çocuk gözüyle okuma başlat (sayfa başına `passes` bağımsız okuma)
    POST plan/reader/turn                          sayfa çevirme merakı (yalnız resimli kitap)
    GET  plan/reader/runs/{rid}                    okuma sonucu (işaretler, editör kararları)
    POST plan/reader/runs/{rid}/resume             yarıda kalan okumayı sürdür (yalnız eksik sayfalar)
    POST plan/reader/runs/{rid}/decisions {flag, decision}   applied|dismissed|accepted|rejected|open
    GET  plan/versions                             karşılaştırılabilir sürümler (bu işin geçmişi + aynı kitabın işleri)
    GET  plan/versions/compare?a=iş:rev&b=iş:rev    sayfa sayfa fark (metin, yerleşim)
    GET  plan/versions/preview?v=iş:rev&page=pid&w= sürümün sayfa önizlemesi (PNG)
    GET  plan/versions/visual?a=&b=&pa=&pb=         sayfa çiftinin görsel farkı (değişen bölgeler, oranla)
    GET  plan/versions/report?a=&b=                 değişiklik raporu (PDF)

Okuma modeli metin modelidir; stüdyoda GPU işi sürerken (resim modeli açıkken ana model durur) okuma başlatılmaz:
409 BUSY. Okuma bu serviste arka planda yürür; servis yeniden başlarsa kayıt «yarıda kaldı» görünür, sürdürülür.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import plan as plan_mod
from . import reader as reader_mod
from . import studio
from . import versions_diff as vd

router = APIRouter()
P = "/v1/studio/jobs/{job}/plan"
VSPEC = re.compile(r"^[0-9A-Za-z]{1,40}:(?:current|[0-9]{1,6})$")


def _api():
    from . import api
    return api


def _llm(d: Path):
    from .run import FileLlm
    return FileLlm(d / "provenance.jsonl")


async def _no_gpu_job(d: Path) -> None:
    b = await _api()._busy(d)
    if b and not b.get("error"):
        raise _api().Coded(409, "BUSY", "Bu kitapta süren bir üretim var; bitince okumayı başlatın")


def _plan_dir(job: str) -> Path:
    return _api()._plan_dir(job)


# ------------------------------------------------------------------ okur
@router.get(P + "/reader")
def reader_info(job: str) -> dict:
    d = _plan_dir(job)
    plan = plan_mod.load(d)
    age = reader_mod.reader_age(d)
    return {**age, "picture_book": reader_mod.picture_book(d, plan), "rev": plan["rev"],
            "child": reader_mod.latest(d, "child"), "turn": reader_mod.latest(d, "turn"),
            "kinds": reader_mod.KINDS, "techniques": reader_mod.TECHNIQUES}


class ChildBody(BaseModel):
    passes: int = Field(3, ge=1)


def by_editor(x_editor: str = Header("")) -> str:
    if not (x_editor or "").strip():
        raise HTTPException(400, "X-Editor gerekli")
    return x_editor.strip()[:200]


async def _start(d: Path, kind: str, by: str, passes: int | None = None) -> dict:
    cur = reader_mod.running(d, kind)
    if cur and reader_mod.is_running(cur["id"]):
        return {"run": cur, "already": True}
    await _no_gpu_job(d)
    try:
        run = await asyncio.to_thread(reader_mod.new_run, d, kind, by, passes)
    except plan_mod.NoPlan:
        raise _api().Coded(404, "NO_PLAN", "Bu kitabın sayfa planı yok") from None
    except ValueError as e:
        raise _api().Coded(400, "NOT_AVAILABLE", str(e)) from None
    reader_mod.start(d, run["id"], _llm(d))
    return {"run": reader_mod.summary(run), "already": False}


@router.post(P + "/reader/child")
async def reader_child(job: str, body: ChildBody, by: str = Depends(by_editor)) -> dict:
    return await _start(_plan_dir(job), "child", by, body.passes)


@router.post(P + "/reader/turn")
async def reader_turn(job: str, by: str = Depends(by_editor)) -> dict:
    return await _start(_plan_dir(job), "turn", by)


def _run(d: Path, rid: str) -> dict:
    run = reader_mod.load_run(d, rid)
    if run is None:
        raise HTTPException(404, "okuma yok")
    return run


@router.get(P + "/reader/runs/{rid}")
def reader_run(job: str, rid: str) -> JSONResponse:
    d = _plan_dir(job)
    return JSONResponse(reader_mod.flat(_run(d, rid)), headers={"Cache-Control": "no-store"})


@router.post(P + "/reader/runs/{rid}/resume")
async def reader_resume(job: str, rid: str, by: str = Depends(by_editor)) -> dict:
    d = _plan_dir(job)
    run = _run(d, rid)
    if reader_mod.is_running(rid):
        return {"run": reader_mod.summary(run), "already": True}
    if run["status"] == "done":
        return {"run": reader_mod.summary(run), "already": True}
    await _no_gpu_job(d)
    reader_mod.start(d, rid, _llm(d))
    return {"run": {**reader_mod.summary(run), "status": "running"}, "already": False}


class Decision(BaseModel):
    flag: str = Field(min_length=1, max_length=40)
    decision: str


@router.post(P + "/reader/runs/{rid}/decisions")
def reader_decide(job: str, rid: str, body: Decision, by: str = Depends(by_editor)) -> dict:
    d = _plan_dir(job)
    try:
        return {"decisions": reader_mod.decide(d, rid, body.flag, body.decision, by)}
    except KeyError as e:
        raise HTTPException(404, str(e.args[0])) from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


# ------------------------------------------------------------------ sürüm farkı
def _v(d: Path, spec: str):
    if not VSPEC.match(spec or ""):
        raise HTTPException(400, "sürüm biçimi iş:rev olmalı")
    try:
        return vd.resolve(d, spec)
    except (KeyError, FileNotFoundError, ValueError) as e:
        raise HTTPException(404, str(e.args[0]) if e.args else "sürüm yok") from None


@router.get(P + "/versions")
def versions(job: str) -> dict:
    return vd.versions(_plan_dir(job))


@router.get(P + "/versions/compare")
def versions_compare(job: str, a: str = Query(...), b: str = Query(...)) -> JSONResponse:
    d = _plan_dir(job)
    return JSONResponse(vd.compare(_v(d, a), _v(d, b), d), headers={"Cache-Control": "no-store"})


@router.get(P + "/versions/preview")
def versions_preview(job: str, v: str = Query(...), page: str = Query(..., min_length=1, max_length=64),
                     w: int = Query(480, ge=120, le=1600)):
    d = _plan_dir(job)
    ver = _v(d, v)
    try:
        path = vd.page_png(ver, page, w)
    except (KeyError, FileNotFoundError):
        raise HTTPException(404, "sayfa yok") from None
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.get(P + "/versions/visual")
def versions_visual(job: str, a: str = Query(...), b: str = Query(...), pa: str | None = None,
                    pb: str | None = None) -> dict:
    d = _plan_dir(job)
    va, vb = _v(d, a), _v(d, b)
    try:
        return vd.visual(va, vb, pa or None, pb or None)
    except (KeyError, FileNotFoundError):
        raise HTTPException(404, "sayfa yok") from None


@router.get(P + "/versions/report")
def versions_report(job: str, a: str = Query(...), b: str = Query(...), by: str = Depends(by_editor)):
    d = _plan_dir(job)
    va, vb = _v(d, a), _v(d, b)
    pdf = vd.report(d, va, vb, by)
    title = re.sub(r"[^\w\-]+", "-", (studio.read(d, "state.json", {}).get("title") or job)).strip("-")
    return FileResponse(pdf, media_type="application/pdf", filename=f"{title}-degisiklik-raporu-{va.rev}-{vb.rev}.pdf")
