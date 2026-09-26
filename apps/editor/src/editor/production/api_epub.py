"""E-kitap uçları (stüdyo servisi; api.py'ye `include_router` ile bağlanır). Yetki servisin genel kuralı: Bearer
anahtar (uygulama düzeyinde), yazanlarda X-Editor. Üretim stüdyo işçisinde (Temporal `EpubBuild`, GPU'suz; aynı sıra).

    GET  /v1/studio/jobs/{job}/epub                         durum: biçim, ilerleme, denetim, sayfalar, alt metin sayıları
    POST /v1/studio/jobs/{job}/epub          {layout}       üret (auto | fixed | reflow)
    GET  /v1/studio/jobs/{job}/epub/file                    indir (application/epub+zip)
    PUT  /v1/studio/jobs/{job}/epub/meta     {eisbn}        e-ISBN (basılı ISBN'den ayrı)
    GET  /v1/studio/jobs/{job}/epub/alt                     alt metin listesi
    PUT  /v1/studio/jobs/{job}/epub/alt/{key}  {text}       editörün alt metni (boş → otomatiğe döner)
    POST /v1/studio/jobs/{job}/epub/alt/{key}/suggest       model önerisi (yazar; editörün metni varsa üzerine yazar)
    GET  /v1/studio/jobs/{job}/epub/alt/{key}/image?w=      görselin küçüğü
    GET  /v1/studio/jobs/{job}/epub/content/{build}/{path}  önizleme: e-kitabın içinden dosya

`key`: kapak | a_<8 hane> (sayfa resmi) | g_<8 hane> (figür/fotoğraf). Hata gövdesi `{"code","detail"}` (NO_PLAN, BUSY).
"""

from __future__ import annotations

import asyncio
import time
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from . import epub
from . import plan as plan_mod
from . import studio

router = APIRouter(prefix="/v1/studio/jobs/{job}/epub")
STUCK = 3 * 3600                     # sürüyor görünen ama bu kadar süredir güncellenmeyen üretim yeniden başlatılabilir


def editor(x_editor: str = Header("")) -> str:
    if not x_editor.strip():
        raise HTTPException(400, "X-Editor gerekli")
    return x_editor.strip()[:200]


def _dir(job: str):
    try:
        return studio.job_dir(job)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404, "iş yok") from None


def _key(key: str) -> str:
    if not epub.KEY.match(key or ""):
        raise HTTPException(404, "görsel yok")
    return key


def _coded(status: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse({"code": code, "detail": detail}, status_code=status)


@router.get("")
def epub_view(job: str) -> dict:
    return epub.view(_dir(job))


class Build(BaseModel):
    layout: Literal["auto", "fixed", "reflow"] = "auto"


@router.post("")
async def epub_build(job: str, body: Build, by: str = Depends(editor)):
    d = _dir(job)
    st = epub.read_state(d)
    if st.get("status") in ("queued", "running") and time.time() - float(st.get("updated") or 0) < STUCK:
        return _coded(409, "BUSY", "E-kitap zaten üretiliyor.")
    plan = plan_mod.load(d)
    if plan is None and not (d / "manuscript.json").exists():
        return _coded(409, "NO_PLAN", "Kitabın metni henüz hazır değil.")
    try:
        epub.decide(d, plan, body.layout)
    except ValueError as e:
        return _coded(409, "NO_PLAN", str(e))
    from .api import _start_plain
    wf = f"studio-{job}-ekitap-{int(time.time())}"
    epub.set_state(d, status="queued", step=None, progress=None, error=None, by=by, layout_want=body.layout,
                   workflow=wf, queued_at=time.time())
    try:
        await _start_plain("EpubBuild", [job, body.layout, by], wf)
    except HTTPException:
        epub.set_state(d, status="fail", error="İş kuyruğuna ulaşılamadı.")
        raise
    return epub.view(d)


@router.get("/file")
def epub_file(job: str) -> Response:
    d = _dir(job)
    p = d / epub.DIR / epub.FILE
    if not p.exists():                  # yeni üretim sıradayken bir önceki dosya indirilebilir
        raise HTTPException(404, "e-kitap henüz üretilmedi")
    return FileResponse(p, media_type="application/epub+zip", filename=f"{job}.epub",
                        headers={"Cache-Control": "private, no-store"})


class Meta(BaseModel):
    eisbn: str | None = Field(default=None, max_length=40)


@router.put("/meta")
def epub_meta(job: str, body: Meta, by: str = Depends(editor)) -> dict:
    d = _dir(job)
    try:
        m = epub.set_meta(d, body.eisbn, by)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return {"eisbn": m.get("eisbn"), "print_isbn": epub.print_isbn(d)}


@router.get("/alt")
def epub_alt(job: str) -> dict:
    d = _dir(job)
    plan = plan_mod.load(d)
    return {"items": epub.alt_list(d, plan) if plan else []}


class Alt(BaseModel):
    text: str = Field(default="", max_length=2000)


@router.put("/alt/{key}")
def epub_alt_set(job: str, key: str, body: Alt, by: str = Depends(editor)) -> dict:
    d = _dir(job)
    try:
        rec = epub.set_alt(d, _key(key), body.text, by)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return _item(d, key, rec)


def _item(d, key: str, rec: dict) -> dict:
    plan = plan_mod.load(d)
    it = next((x for x in epub.alt_list(d, plan) if x["key"] == key), None) if plan else None
    return it or {"key": key, **rec}


@router.post("/alt/{key}/suggest")
async def epub_alt_suggest(job: str, key: str, by: str = Depends(editor)) -> dict:
    from .run import FileLlm
    d = _dir(job)
    try:
        await epub.suggest_one(d, _key(key), FileLlm(d / "provenance.jsonl"))
    except KeyError:
        raise HTTPException(404, "görsel e-kitapta yok") from None
    return _item(d, key, {})


@router.get("/alt/{key}/image")
def epub_alt_image(job: str, key: str, w: int = Query(320, ge=64, le=1200)) -> Response:
    from .api import _asset_image
    d = _dir(job)
    plan = plan_mod.load(d)
    it = next((x for x in epub.images(d, plan) if x["key"] == _key(key)), None) if plan else None
    from pathlib import Path
    if it is None or not it.get("path") or not Path(it["path"]).exists():
        raise HTTPException(404, "görsel yok")
    return _asset_image(Path(it["path"]), w)


@router.get("/content/{build}/{path:path}")
async def epub_content(job: str, build: str, path: str) -> Response:
    d = _dir(job)
    try:
        data, mime = await asyncio.to_thread(epub.content, d, build, path)
    except FileNotFoundError:
        raise HTTPException(404, "yok") from None
    return Response(data, media_type=mime, headers={"Cache-Control": "private, max-age=3600",
                                                    "Content-Security-Policy": "script-src 'none'; object-src 'none'"})
