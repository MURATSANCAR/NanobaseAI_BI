"""Efekt sesleri uçları (stüdyo servisi; api.py'ye tek `include_router` ile bağlanır). Yetki api.py'nin uygulama
düzeyi anahtarıyla, yazanlarda X-Editor. Ayrıntı: production/sfx.py (kitap), production/sfx_library.py (havuz).

Kitap başına, /v1/studio/jobs/{job}/sfx altında:
    GET  sfx                          açık/kapalı (ve neden), sayfa özetleri, süren koşu, havuz özeti, kaynakça
    PUT  sfx/settings                 {enabled}
    POST sfx/suggest                  {pages: [pid]|null, force} → arka planda Zeki AI önerisi + karışım (409 BUSY)
    POST sfx/mix                      {pages: [pid]|null} → «güncel değil» sayfaları yeniden karıştırır (arka plan)
    GET  sfx/pages/{pid}              sayfanın blokları, ipuçları, adayların katalog bilgisi, karışım durumu
    PUT  sfx/pages/{pid}              {cues: [...], ambience: {...}|null}  (tamamı; alıntı metinde geçmeli → 400)
    POST sfx/pages/{pid}/mix          yalnız bu sayfa yeniden karıştırılır (anlatım önbellekten) → 409 NO_AUDIO
    GET  sfx/pages/{pid}/audio        efektli sayfa sesi (audio/mpeg, Range)
    GET  sfx/credits                  «ses efektleri kaynakçası» (atıf gerekenler + kullanılan kaynaklar)

Havuz (yayınevi düzeyinde), /v1/studio/sfx altında:
    GET  sfx/library?q=&en=&category=&kind=&k=   arama (Türkçe sorgu Zeki AI ile İngilizceye çevrilir, önbellekli)
    GET  sfx/library/categories       kategori ağacı + dosya sayıları + havuz özeti
    GET  sfx/library/browse?category=&offset=&k=
    GET  sfx/library/{sid}            katalog kaydı (lisans, kaynak, atıf)
    GET  sfx/library/{sid}/preview    dinleme önizlemesi (audio/mpeg, en çok 20 sn)

Hatalar gövdede `code`: NO_PLAN (404), PREPARING (409), NO_LIBRARY (503: havuz bu kurulumda bağlı değil),
BUSY (409), NO_AUDIO (409: sayfanın anlatımı yok/güncel değil), NOTHING (400).
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import plan as plan_mod
from . import sfx
from . import sfx_library as L
from . import studio

router = APIRouter()
P = "/v1/studio/jobs/{job}/sfx"
LIB = "/v1/studio/sfx/library"
PID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
SID = re.compile(r"^[0-9a-f]{16}$")
_tasks: set[asyncio.Task] = set()


def _editor(x_editor: str = Header("")) -> str:
    if not x_editor.strip():
        raise HTTPException(400, "X-Editor gerekli")
    return x_editor.strip()[:200]


def _coded(status: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse({"code": code, "detail": detail}, status_code=status)


class _Err(Exception):
    def __init__(self, status: int, code: str, detail: str):
        self.resp = _coded(status, code, detail)


def _guard(fn):
    import functools

    @functools.wraps(fn)
    async def wrap(*a, **kw):
        try:
            return await fn(*a, **kw)
        except _Err as e:
            return e.resp
        except L.Unavailable:
            return _coded(503, "NO_LIBRARY", "Efekt havuzu bu kurulumda henüz bağlı değil.")
        except plan_mod.NoPlan:
            return _coded(404, "NO_PLAN", "Kitap henüz sayfalara yerleşmedi; üretim bitince açılır.")
    return wrap


def _dir(job: str) -> Path:
    try:
        d = studio.job_dir(job)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404, "iş yok") from None
    if not plan_mod.exists(d):
        if (plan_mod.auto_state(d) or {}).get("status") == "running":
            raise _Err(409, "PREPARING", "Sayfa düzeni hazırlanıyor; birkaç saniye sürer.")
        raise _Err(404, "NO_PLAN", "Kitap henüz sayfalara yerleşmedi; üretim bitince açılır.")
    return d


def _pid(pid: str) -> str:
    if not PID.match(pid or ""):
        raise HTTPException(404, "sayfa yok")
    return pid


def _start(coro) -> None:
    t = asyncio.create_task(coro)
    _tasks.add(t)
    t.add_done_callback(lambda x: (_tasks.discard(x), x.exception() if not x.cancelled() else None))


@router.get(P)
@_guard
async def sfx_view(job: str) -> dict:
    return await asyncio.to_thread(sfx.overview, _dir(job))


class Settings(BaseModel):
    enabled: bool


@router.put(P + "/settings")
@_guard
async def sfx_settings(job: str, body: Settings, by: str = Depends(_editor)) -> dict:
    return await asyncio.to_thread(sfx.set_enabled, _dir(job), body.enabled, by)


class Run(BaseModel):
    pages: list[str] | None = None
    force: bool = False


def _pages(d: Path, pages: list[str] | None, pick) -> list[str]:
    from . import narration as N
    rows = N.status(d)
    ids = [r["id"] for r in rows if r["status"] != "empty"]
    if pages is not None:
        unknown = [p for p in pages if p not in ids]
        if unknown:
            raise HTTPException(404, "sayfa yok: " + ", ".join(unknown[:5]))
        return pages
    return [p for p in ids if pick(p)]


@router.post(P + "/suggest")
@_guard
async def sfx_suggest(job: str, body: Run, by: str = Depends(_editor)) -> dict:
    """`pages` verilmezse önerisi olmayan sayfalar; `force` ile bütün sayfalar (editörün elle eklediği korunur)."""
    d = _dir(job)
    if not L.available():
        raise L.Unavailable()

    def pick(pid: str) -> bool:
        rec = sfx._read(sfx.page_file(d, pid)) or {}
        return body.force or not rec.get("suggested")
    pids = await asyncio.to_thread(_pages, d, body.pages, pick)
    if not pids:
        raise _Err(400, "NOTHING", "Önerilecek sayfa yok; bütün sayfalar önerildi.")
    if not sfx.claim(d, by, pids):
        raise _Err(409, "BUSY", "Bu kitapta efekt işi sürüyor.")
    _start(sfx.suggest_run(d, pids, by))
    return {"started": True, "pages": len(pids)}


@router.post(P + "/mix")
@_guard
async def sfx_mix_all(job: str, body: Run, by: str = Depends(_editor)) -> dict:
    d = _dir(job)
    if not L.available():
        raise L.Unavailable()
    pids = await asyncio.to_thread(_pages, d, body.pages, lambda p: sfx.mix_state(d, p) == "stale")
    if not pids:
        raise _Err(400, "NOTHING", "Karıştırılacak sayfa yok; efektli sesler güncel.")
    if not sfx.claim(d, by, pids):
        raise _Err(409, "BUSY", "Bu kitapta efekt işi sürüyor.")
    _start(sfx.suggest_run(d, pids, by, mix=True, suggest=False))
    return {"started": True, "pages": len(pids)}


@router.get(P + "/pages/{pid}")
@_guard
async def sfx_page(job: str, pid: str) -> dict:
    d = _dir(job)
    try:
        return await asyncio.to_thread(sfx.page_view, d, _pid(pid))
    except KeyError:
        raise HTTPException(404, "sayfa yok") from None


class Cue(BaseModel):
    id: str | None = Field(default=None, max_length=16)
    kind: str = "anlik"
    type: str | None = None
    block: str | None = Field(default=None, max_length=64)
    words: list[int] | None = None
    quote: str = Field(max_length=200)
    query: str = Field(default="", max_length=200)
    query_en: str = Field(default="", max_length=200)
    category: str | None = Field(default=None, max_length=40)
    candidates: list[str] = []
    chosen: str | None = Field(default=None, max_length=32)
    gain_db: float = 0.0
    place: str = "birlikte"
    source: str = "editor"
    confidence: float | None = None


class Ambience(BaseModel):
    query: str = Field(default="", max_length=200)
    query_en: str = Field(default="", max_length=200)
    category: str | None = Field(default=None, max_length=40)
    candidates: list[str] = []
    chosen: str | None = Field(default=None, max_length=32)
    gain_db: float = 0.0
    quote: str | None = Field(default=None, max_length=200)
    block: str | None = Field(default=None, max_length=64)
    source: str = "editor"
    scope: str = "sayfa"


class PageBody(BaseModel):
    cues: list[Cue] = []
    ambience: Ambience | None = None


@router.put(P + "/pages/{pid}")
@_guard
async def sfx_page_save(job: str, pid: str, body: PageBody, by: str = Depends(_editor)) -> dict:
    d = _dir(job)
    try:
        return await asyncio.to_thread(sfx.set_page, d, _pid(pid), body.model_dump(), by)
    except KeyError:
        raise HTTPException(404, "sayfa yok") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


@router.post(P + "/pages/{pid}/mix")
@_guard
async def sfx_page_mix(job: str, pid: str, _by: str = Depends(_editor)) -> dict:
    d = _dir(job)
    try:
        return await asyncio.to_thread(sfx.mix_page, d, _pid(pid))
    except sfx.NoNarration:
        raise _Err(409, "NO_AUDIO", "Bu sayfanın sesi yok ya da güncel değil; önce sayfayı seslendirin.") from None


@router.get(P + "/pages/{pid}/audio")
@_guard
async def sfx_page_audio(job: str, pid: str):
    d = _dir(job)
    p = sfx.mix_path(d, _pid(pid))
    if not p.exists():
        raise HTTPException(404, "Bu sayfanın efektli sesi henüz yok")
    return FileResponse(p, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=60"})


@router.get(P + "/credits")
@_guard
async def sfx_credits(job: str) -> dict:
    return await asyncio.to_thread(sfx.credits, _dir(job))


# ------------------------------------------------------------------ havuz
def _lib():
    if not L.available():
        raise L.Unavailable()


@router.get(LIB)
@_guard
async def library_search(q: str = Query("", max_length=200), en: str = Query("", max_length=200),
                         category: str = Query("", max_length=40), kind: str = Query("", max_length=10),
                         k: int = Query(24, ge=1, le=200)) -> dict:
    _lib()
    if category and category not in L.CATEGORIES:
        raise HTTPException(400, "Bilinmeyen kategori")
    if not q.strip() and not en.strip():
        if not category:
            raise HTTPException(400, "Aranacak metin ya da kategori verin")
        out = await asyncio.to_thread(L.browse, category, offset=0, k=k)
        return {"query": None, "en": None, **out}
    en_q = en.strip() or (await sfx.translate(q)) or None
    items = await asyncio.to_thread(L.search, q, en=en_q, category=category or None,
                                    kind=kind if kind in ("anlik", "ortam") else None, k=k)
    return {"query": q, "en": en_q, "total": len(items), "items": items}


@router.get(LIB + "/categories")
@_guard
async def library_categories() -> dict:
    _lib()
    st = await asyncio.to_thread(L.stats)
    tree = L.category_tree()
    for g in tree:
        for c in g["categories"]:
            c["count"] = st["categories"].get(c["key"], 0)
        g["count"] = sum(c["count"] for c in g["categories"])
    return {"groups": tree, "stats": st, "sources": [{"key": k, **v} for k, v in L.SOURCES.items()]}


@router.get(LIB + "/browse")
@_guard
async def library_browse(category: str = Query(..., max_length=40), offset: int = Query(0, ge=0),
                         k: int = Query(30, ge=1, le=200)) -> dict:
    _lib()
    if category not in L.CATEGORIES:
        raise HTTPException(400, "Bilinmeyen kategori")
    return await asyncio.to_thread(L.browse, category, offset=offset, k=k)


@router.get(LIB + "/{sid}")
@_guard
async def library_item(sid: str) -> dict:
    _lib()
    if not SID.match(sid):
        raise HTTPException(404, "efekt yok")
    r = await asyncio.to_thread(L.get, sid)
    if r is None:
        raise HTTPException(404, "efekt yok")
    return L.public(r)


@router.get(LIB + "/{sid}/preview")
@_guard
async def library_preview(sid: str):
    _lib()
    if not SID.match(sid):
        raise HTTPException(404, "efekt yok")
    try:
        p = await asyncio.to_thread(L.preview, sid)
    except KeyError:
        raise HTTPException(404, "efekt yok") from None
    return FileResponse(p, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=86400"})
