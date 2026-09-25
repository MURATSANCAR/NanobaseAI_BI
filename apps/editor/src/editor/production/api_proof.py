"""3B kitap ve baskı provası uçları (stüdyo servisine `app.include_router` ile bağlanır; yetki uygulamanın kendi
bağımlılığıyla — Bearer EDITOR_CARDS_KEY). Hepsi okuyan uç; yazan uç yok (prova önbelleği iş klasöründe `prova/`).

    GET /v1/studio/jobs/{job}/proof                         kitabın ölçüleri (mm), kâğıtlar, varsayılan kâğıt
    GET /v1/studio/jobs/{job}/proof/pages/{n}?paper=&w=&layer=   sayfanın provası (PNG)
    GET /v1/studio/jobs/{job}/proof/cover?paper=&w=&layer=       kapak açılımının provası (PNG)
    GET /v1/studio/jobs/{job}/proof/pages/{n}/report?paper=&w=   renk kaybı ve mürekkep yükü özeti
    GET /v1/studio/jobs/{job}/proof/cover/report?paper=&w=

layer: paper (kâğıt tonuyla, varsayılan) | plain (kâğıt tonu olmadan) | gamut (renk kaybı işareti, saydam) |
tac (mürekkep yükü aşımı işareti, saydam). İşaret katmanları prova görüntüsüyle aynı boydadır, üstüne konur.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from . import proof, studio

router = APIRouter(prefix="/v1/studio/jobs/{job}/proof")
Layer = Literal["paper", "plain", "gamut", "tac"]
CACHE = {"Cache-Control": "private, max-age=300"}
PAPER = re.compile(r"^[a-z_]{1,24}$")


def _dir(job: str):
    try:
        return studio.job_dir(job)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404, "iş yok") from None


def _paper(key: str) -> str:
    if not PAPER.match(key or "") or key not in proof.PAPERS:
        raise HTTPException(404, "kâğıt yok")
    return key


def _files(job: str, what: str, n: int, paper: str, w: int) -> dict:
    d = _dir(job)
    paper = _paper(paper)
    if what == "cover" and not (d / "kapak" / "kapak.pdf").exists():
        raise HTTPException(404, "kapak yok")
    try:
        return proof.render(d, what, n, paper, w)
    except FileNotFoundError:
        raise HTTPException(404, "sayfa yok" if what == "page" else "kapak yok") from None


@router.get("")
async def proof_book(job: str) -> dict:
    d = _dir(job)
    try:
        return await asyncio.to_thread(proof.book, d)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e) or "kitap henüz hazır değil") from None


@router.get("/pages/{n}")
async def proof_page(job: str, n: int, paper: str = Query(...), w: int = Query(900, ge=120, le=2400),
                     layer: Layer = "paper") -> FileResponse:
    files = await asyncio.to_thread(_files, job, "page", n, paper, w)
    return FileResponse(files[layer], media_type="image/png", headers=CACHE)


@router.get("/cover")
async def proof_cover(job: str, paper: str = Query(...), w: int = Query(1400, ge=200, le=3000),
                      layer: Layer = "paper") -> FileResponse:
    files = await asyncio.to_thread(_files, job, "cover", 0, paper, w)
    return FileResponse(files[layer], media_type="image/png", headers=CACHE)


@router.get("/pages/{n}/report")
async def proof_page_report(job: str, n: int, paper: str = Query(...), w: int = Query(900, ge=120, le=2400)) -> dict:
    files = await asyncio.to_thread(_files, job, "page", n, paper, w)
    return json.loads(files["report"].read_text())


@router.get("/cover/report")
async def proof_cover_report(job: str, paper: str = Query(...), w: int = Query(1400, ge=200, le=3000)) -> dict:
    files = await asyncio.to_thread(_files, job, "cover", 0, paper, w)
    return json.loads(files["report"].read_text())
