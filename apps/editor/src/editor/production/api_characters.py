"""Seri karakter kartı uçları (characters.py). api.py'nin sonunda `app.include_router(router)` ile bağlanır; yetki
(Bearer) uygulamanın kendi bağımlılığıdır, yazanlar `X-Editor` ister. Kart dizi düzeyinde saklanır; uçlar iş
üzerinden adreslenir (dizi işin dizisidir), böylece köprü ve giriş kapısı yalnız iş kimliğini tanır.

    GET    /v1/studio/jobs/{job}/character-cards                        dizi, kartlar, bu kitabın karakterleri,
                                                                        uymayan resimler, yeniden deneme sayısı
    PUT    /v1/studio/jobs/{job}/character-cards/series        {name}   bu işin dizi adı (boş: kurala dön)
    POST   /v1/studio/jobs/{job}/character-cards/suggest       {names}  taslak kartlar (iş akışı; ana model)
    POST   /v1/studio/jobs/{job}/character-cards/check                  seçili resimleri kartlara karşı denetle
    POST   /v1/studio/jobs/{job}/character-cards/cards         {rev, card}
    PUT    /v1/studio/jobs/{job}/character-cards/cards/{cid}   {rev, card}
    DELETE /v1/studio/jobs/{job}/character-cards/cards/{cid}?rev=
    POST   /v1/studio/jobs/{job}/character-cards/cards/{cid}/approve   {ok}
    POST   /v1/studio/jobs/{job}/character-cards/cards/{cid}/translate      modele giden tarif (iş akışı)
    POST   /v1/studio/jobs/{job}/character-cards/cards/{cid}/palette        kartın rengini kitap paletine yaz
    PUT    /v1/studio/jobs/{job}/character-cards/cards/{cid}/refs?filename=  ham gövde: referans görsel yükle
    POST   /v1/studio/jobs/{job}/character-cards/cards/{cid}/refs  {from: sheet|art, name|key, v}  işten al
    POST   /v1/studio/jobs/{job}/character-cards/cards/{cid}/refs/{rid}/primary
    DELETE /v1/studio/jobs/{job}/character-cards/cards/{cid}/refs/{rid}
    GET    /v1/studio/jobs/{job}/character-cards/cards/{cid}/refs/{rid}?w=
    GET    /v1/studio/jobs/{job}/character-cards/history
    GET|PUT /v1/studio/character-settings                     {max_retries}  (köprü yönetim ayarını yazar)

Hatalar: STALE (409, `rev`), NO_SERIES (409), BUSY (409), 404 kart/referans yok, 400 doğrulama, 413 büyük dosya.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from . import characters as ch
from . import plan as plan_mod
from . import studio
from .api import Coded, _busy, _dir, _image, _start_plain, editor, upload_mb

router = APIRouter()
P = "/v1/studio/jobs/{job}/character-cards"


def _series(d: Path) -> dict:
    s = ch.job_series(d)
    if not s:
        raise Coded(409, "NO_SERIES", "Bu kitabın dizisi belirlenemedi; dizi adını yazın")
    return s


def _cid(cid: str) -> str:
    if not ch.CARD_ID.match(cid or ""):
        raise HTTPException(404, "kart yok")
    return cid


def _rid(rid: str) -> str:
    if not ch.REF_ID.match(rid or ""):
        raise HTTPException(404, "referans yok")
    return rid


async def _do(fn, *a, **kw):
    try:
        return await asyncio.to_thread(fn, *a, **kw)
    except ch.Stale as e:
        raise Coded(409, "STALE", "Kartlar başka bir yerde değişti; güncel hâli alınıp yeniden uygulanmalı",
                    rev=e.rev) from None
    except ch.NoSeries:
        raise Coded(409, "NO_SERIES", "Bu kitabın dizisi belirlenemedi; dizi adını yazın") from None
    except plan_mod.Stale as e:
        raise Coded(409, "STALE", "Sayfa planı değişti; yeniden deneyin", rev=e.rev) from None
    except plan_mod.NoPlan:
        raise Coded(404, "NO_PLAN", "Bu kitabın sayfa planı yok") from None
    except KeyError as e:
        raise HTTPException(404, str(e.args[0] if e.args else e)) from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


def _out(data: dict, **extra) -> dict:
    return {"rev": data["rev"], **extra}


@router.get(P)
async def cards_view(job: str) -> Response:
    d = _dir(job)
    out = await _do(ch.view, d)
    out["busy"] = await _busy(d)
    return JSONResponse(out, headers={"Cache-Control": "no-store"})


class SeriesBody(BaseModel):
    name: str = Field("", max_length=120)


@router.put(P + "/series")
async def set_series(job: str, body: SeriesBody, by: str = Depends(editor)) -> dict:
    d = _dir(job)
    return {"series": await _do(ch.set_job_series, d, body.name, by)}


class SuggestBody(BaseModel):
    names: list[str] = Field(default_factory=list)


@router.post(P + "/suggest")
async def suggest(job: str, body: SuggestBody, by: str = Depends(editor)) -> dict:
    d = _dir(job)
    _series(d)
    if not studio.read(d, "artplan.json"):
        raise HTTPException(409, "Kitabın karakterleri henüz çıkarılmadı")
    wf = f"studio-{job}-kartoner-{int(time.time())}"
    await _start_plain("CharacterCards", [job, "suggest", list(body.names), "", by], wf)
    await asyncio.to_thread(ch._task, d, suggest={"status": "queued", "workflow": wf})
    return {"workflow": wf}


@router.post(P + "/check")
async def check(job: str, by: str = Depends(editor)) -> dict:
    d = _dir(job)
    b = await _busy(d)
    if b and not b.get("error"):
        raise Coded(409, "BUSY", "Bu kitapta süren bir üretim var; bitince tekrar deneyin")
    n = await _do(ch.mark_selected, d)
    wf = None
    if n or any(it["status"] == "pending" for it in ch._checks(d)["items"].values()):
        wf = await ch.kick(job)
        if wf is None:
            raise HTTPException(503, "İş kuyruğuna ulaşılamadı; denetim bekliyor, sonra yeniden deneyin")
        await asyncio.to_thread(ch._task, d, check={"status": "queued", "workflow": wf})
    return {"pending": n, "workflow": wf}


class CardBody(BaseModel):
    rev: int
    card: dict


@router.post(P + "/cards")
async def create(job: str, body: CardBody, by: str = Depends(editor)) -> dict:
    d = _dir(job)
    s = _series(d)
    title = (studio.read(d, "manuscript.json") or {}).get("title")
    data, card = await _do(ch.create_card, s, body.rev, body.card, by, {"job": job, "title": title, "from": "editör"})
    return _out(data, card=card, series=s)


@router.put(P + "/cards/{cid}")
async def update(job: str, cid: str, body: CardBody, by: str = Depends(editor)) -> dict:
    s = _series(_dir(job))
    data, card = await _do(ch.update_card, s, body.rev, _cid(cid), body.card, by)
    return _out(data, card=card)


@router.delete(P + "/cards/{cid}")
async def delete(job: str, cid: str, rev: int = Query(...), by: str = Depends(editor)) -> dict:
    s = _series(_dir(job))
    data, _ = await _do(ch.delete_card, s, rev, _cid(cid), by)
    return _out(data, ok=True)


class ApproveBody(BaseModel):
    ok: bool = True


@router.post(P + "/cards/{cid}/approve")
async def approve(job: str, cid: str, body: ApproveBody, by: str = Depends(editor)) -> dict:
    s = _series(_dir(job))
    data, card = await _do(ch.approve, s, _cid(cid), body.ok, by)
    return _out(data, card=card)


@router.post(P + "/cards/{cid}/translate")
async def translate(job: str, cid: str, by: str = Depends(editor)) -> dict:
    d = _dir(job)
    s = _series(d)
    await _do(ch._card, await _do(ch.load, s["id"]), _cid(cid))
    wf = f"studio-{job}-karttr-{cid}-{int(time.time())}"
    await _start_plain("CharacterCards", [job, "translate", [], cid, by], wf)
    await asyncio.to_thread(ch._task, d, translate={"status": "queued", "workflow": wf, "card": cid})
    return {"workflow": wf}


@router.post(P + "/cards/{cid}/palette")
async def palette(job: str, cid: str, by: str = Depends(editor)) -> dict:
    return await _do(ch.apply_palette, _dir(job), _cid(cid), by)


def _upload_limit() -> int:
    """Stüdyonun yükleme sınırı (yönetim ayarı STUDIO_UPLOAD_MB; fotoğraf yüklemesiyle aynı)."""
    return upload_mb() * 1024 * 1024


@router.put(P + "/cards/{cid}/refs")
async def upload_ref(job: str, cid: str, request: Request, filename: str = "", by: str = Depends(editor)) -> dict:
    s = _series(_dir(job))
    declared = request.headers.get("content-length") or ""
    if declared.isdigit() and int(declared) > _upload_limit():
        raise Coded(413, "TOO_LARGE", f"Görsel en çok {upload_mb()} MB olabilir", limit_mb=upload_mb())
    data = await request.body()
    if not data:
        raise HTTPException(400, "Dosya boş")
    if len(data) > _upload_limit():
        raise Coded(413, "TOO_LARGE", f"Görsel en çok {upload_mb()} MB olabilir", limit_mb=upload_mb())
    src = {"kind": "upload", "name": Path(filename or "gorsel").name[:120], "job": job}
    data_, ref = await _do(ch.add_ref, s, _cid(cid), data, src, by)
    return _out(data_, ref=ref)


class RefFrom(BaseModel):
    source: Literal["sheet", "art"] = Field(alias="from")
    name: str = ""
    key: str = ""
    v: int = 0


@router.post(P + "/cards/{cid}/refs")
async def ref_from_job(job: str, cid: str, body: RefFrom, by: str = Depends(editor)) -> dict:
    """İşin karakter referans çizimi (`sheet`, name) ya da onaylı bir sayfa resmi (`art`, key + v) karta referans olur."""
    d = _dir(job)
    s = _series(d)
    st = studio.studio_state(d)
    if body.source == "sheet":
        path = st.get("characters", {}).get(body.name)
        src = {"kind": "sheet", "job": job, "name": body.name}
    else:
        pg = st["pages"].get(body.key)
        if not pg or not 1 <= body.v <= len(pg["versions"]):
            raise HTTPException(404, "resim yok")
        path = pg["versions"][body.v - 1]["path"]
        src = {"kind": "art", "job": job, "key": body.key, "v": body.v}
    if not path or not Path(path).exists():
        raise HTTPException(404, "görsel yok")
    data, ref = await _do(ch.add_ref, s, _cid(cid), Path(path).read_bytes(), src, by)
    return _out(data, ref=ref)


@router.post(P + "/cards/{cid}/refs/{rid}/primary")
async def ref_primary(job: str, cid: str, rid: str, by: str = Depends(editor)) -> dict:
    s = _series(_dir(job))
    data, card = await _do(ch.ref_action, s, _cid(cid), _rid(rid), "primary", by)
    return _out(data, card=card)


@router.delete(P + "/cards/{cid}/refs/{rid}")
async def ref_remove(job: str, cid: str, rid: str, by: str = Depends(editor)) -> dict:
    s = _series(_dir(job))
    data, card = await _do(ch.ref_action, s, _cid(cid), _rid(rid), "remove", by)
    return _out(data, card=card)


@router.get(P + "/cards/{cid}/refs/{rid}")
async def ref_image(job: str, cid: str, rid: str, w: int = Query(320, ge=0, le=2048)) -> Response:
    s = _series(_dir(job))
    if not s["exists"]:
        raise HTTPException(404, "referans yok")
    path = await _do(ch.ref_path, s["id"], _cid(cid), _rid(rid))
    return await asyncio.to_thread(_image, path, w)


@router.get(P + "/history")
async def history(job: str) -> list:
    s = _series(_dir(job))
    return await _do(ch.history, s["id"]) if s["exists"] else []


class Settings(BaseModel):
    max_retries: int = Field(ge=0)


@router.get("/v1/studio/character-settings")
def get_settings() -> dict:
    return {"max_retries": ch.max_retries()}


@router.put("/v1/studio/character-settings")
async def put_settings(body: Settings, by: str = Depends(editor)) -> dict:
    return await asyncio.to_thread(ch.set_max_retries, body.max_retries, by)

