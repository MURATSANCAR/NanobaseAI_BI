"""Film uçları (production/film/), hepsi /v1/studio/jobs/{job}/films altında. api.py'de tek satırla bağlanır; yetki
uygulama düzeyindeki Bearer denetimidir, yazanlar `X-Editor` ister.

    GET    films                               işin filmleri
    POST   films                               {format, style, title} → yeni film
    GET    films/{fid}                         bütün görünüm (adımlar, senaryo, oyuncular, ses, kareler, çekimler, kurgu,
                                               paylaşım, kayıt)
    POST   films/{fid}/stages/{stage}          {only?, direction?, platforms?} adımı başlat (GPU adımları kuyruğa)
    PUT    films/{fid}/script                  {script, rev}     editör düzeltmesi (denetim yeniden koşar, onay düşer)
    PUT    films/{fid}/cast/voice              {name, voice, rev}
    POST   films/{fid}/frames/{shot}/select    {v}
    POST   films/{fid}/approve/{stage}         {ok}
    PUT    films/{fid}/share/text              {caption, hashtags, hook}
    GET    films/{fid}/media/{path}            kare, çekim, replik sesi, kurgu; paylaşım dosyası yalnız onaylıysa indirilir

Oyuncular adımı modelsizdir, istekte biter. Öbür adımlar Temporal'da (film/flow.py) yürür; ekran film.json'u izler.
Hiçbir uç dışarıya gönderim yapmaz.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import studio
from .film import cast as cast_mod
from .film import frames as frames_mod
from .film import script as script_mod
from .film import social as social_mod
from .film import spec, store

router = APIRouter(prefix="/v1/studio/jobs/{job}/films")
Stage = Literal["senaryo", "oyuncular", "ses", "kareler", "cekim", "kurgu", "paylasim"]
# adım → başlamadan önce hazır/onaylı olması gerekenler (store.require)
NEEDS = {"senaryo": [], "oyuncular": ["senaryo"], "ses": ["oyuncular"], "kareler": ["oyuncular"],
         "cekim": ["ses", "kareler"], "kurgu": ["cekim"], "paylasim": ["kurgu"]}
MEDIA_DIRS = ("kare", "cekim", "ses", "cikti")
MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".mp4": "video/mp4", ".wav": "audio/wav",
               ".srt": "application/x-subrip"}


def _editor(x_editor: str = Header("")) -> str:
    if not x_editor.strip():
        raise HTTPException(400, "X-Editor gerekli")
    return x_editor.strip()[:200]


def _job(job: str) -> Path:
    try:
        return studio.job_dir(job)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404, "iş yok") from None


def _film(job: str, fid: str) -> tuple[Path, Path]:
    d = _job(job)
    try:
        return d, store.fdir(d, fid)
    except (store.FilmError, FileNotFoundError):
        raise HTTPException(404, "film yok") from None


def _err(e: Exception) -> HTTPException:
    return HTTPException(409, str(e))


@router.get("")
def films(job: str) -> dict:
    d = _job(job)
    return {"films": store.films(d), "formats": spec.FORMATS, "styles": {k: v["label"] for k, v in spec.STYLES.items()},
            "platforms": {k: v["label"] for k, v in spec.PLATFORMS.items()}}


class NewFilm(BaseModel):
    format: Literal["cizgi-film", "fragman", "reels"]
    style: Literal["2b", "3b", "suluboya", "gercekci"] = "2b"
    title: str = Field("", max_length=120)


@router.post("")
def new_film(job: str, body: NewFilm, by: str = Depends(_editor)) -> dict:
    d = _job(job)
    f = store.create(d, body.format, body.style, body.title or studio._manuscript(d).title, by)
    return store.meta(f)


@router.get("/{fid}")
def view(job: str, fid: str) -> dict:
    _, f = _film(job, fid)
    return {"film": store.meta(f), "script": store.read(f, "senaryo.json"), "cast": store.read(f, "oyuncular.json"),
            "voice": store.read(f, "ses.json"), "frames": store.read(f, "kareler.json"),
            "shots": store.read(f, "cekimler.json"), "cut": store.read(f, "kurgu.json"),
            "share": store.read(f, "paylasim.json"), "events": store.events(f)[:100]}


class StageOpts(BaseModel):
    only: list[str] | None = None
    direction: str = Field("", max_length=600)
    platforms: list[str] | None = None


@router.post("/{fid}/stages/{stage}")
async def start(job: str, fid: str, stage: Stage, body: StageOpts, by: str = Depends(_editor)) -> dict:
    d, f = _film(job, fid)
    try:
        for need in NEEDS[stage]:
            store.require(f, need)
        if stage == "oyuncular":
            return cast_mod.build(d, f, script_mod.load(f), by)
        if stage == "paylasim" and not body.platforms:
            raise store.FilmError("En az bir platform seçin.")
    except store.FilmError as e:
        raise _err(e) from None
    from temporalio.exceptions import WorkflowAlreadyStartedError

    from ..jobs import temporal
    from .flow import QUEUE
    wf = f"studio-{job}-{fid}-{stage}"
    opts = body.model_dump(exclude_none=True)
    try:
        await (await temporal()).start_workflow("FilmStage", args=[job, fid, stage, by, opts], id=wf,
                                                task_queue=QUEUE)
    except WorkflowAlreadyStartedError:
        raise HTTPException(409, "Bu adım zaten sürüyor.") from None
    store.set_stage(f, stage, status="sirada", by=by)
    store.log(f, by, "adım başlatıldı", stage=stage)
    return store.meta(f)


class ScriptBody(BaseModel):
    script: dict
    rev: int


@router.put("/{fid}/script")
def put_script(job: str, fid: str, body: ScriptBody, by: str = Depends(_editor)) -> dict:
    d, f = _film(job, fid)
    bad = spec.shape_errors(body.script)
    if bad:
        raise HTTPException(422, "Senaryo biçimi geçersiz: " + "; ".join(bad[:5]))
    try:
        return script_mod.edit(d, f, body.script, body.rev, by)
    except store.FilmError as e:
        raise _err(e) from None


class VoiceBody(BaseModel):
    name: str
    voice: str
    rev: int


@router.put("/{fid}/cast/voice")
def put_voice(job: str, fid: str, body: VoiceBody, by: str = Depends(_editor)) -> dict:
    _, f = _film(job, fid)
    try:
        return cast_mod.set_voice(f, body.name, body.voice, body.rev, by)
    except store.FilmError as e:
        raise _err(e) from None


class SelectBody(BaseModel):
    v: int


@router.post("/{fid}/frames/{shot}/select")
def select_frame(job: str, fid: str, shot: str, body: SelectBody, by: str = Depends(_editor)) -> dict:
    _, f = _film(job, fid)
    try:
        return frames_mod.select(f, shot, body.v, by)
    except store.FilmError as e:
        raise _err(e) from None


class ApproveBody(BaseModel):
    ok: bool = True


@router.post("/{fid}/approve/{stage}")
def approve(job: str, fid: str, stage: Stage, body: ApproveBody, by: str = Depends(_editor)) -> dict:
    _, f = _film(job, fid)
    try:
        return store.approve(f, stage, body.ok, by)
    except store.FilmError as e:
        raise _err(e) from None


class ShareText(BaseModel):
    caption: str = Field(..., max_length=2200)
    hashtags: list[str] = Field(default_factory=list, max_length=10)
    hook: str = Field("", max_length=80)


@router.put("/{fid}/share/text")
def share_text(job: str, fid: str, body: ShareText, by: str = Depends(_editor)) -> dict:
    _, f = _film(job, fid)
    try:
        return social_mod.edit_text(f, body.caption, body.hashtags, body.hook, by)
    except store.FilmError as e:
        raise _err(e) from None


@router.get("/{fid}/media/{path:path}")
def media(job: str, fid: str, path: str, download: bool = False) -> FileResponse:
    _, f = _film(job, fid)
    p = (f / path).resolve()
    if f.resolve() not in p.parents or p.parts[len(f.resolve().parts)] not in MEDIA_DIRS or not p.is_file():
        raise HTTPException(404, "dosya yok")
    if p.suffix not in MEDIA_TYPES:
        raise HTTPException(404, "dosya yok")
    share = (f / "cikti" / "paylasim").resolve()
    if download and share in p.parents and store.meta(f)["stages"]["paylasim"].get("status") != "onayli":
        raise HTTPException(409, "Paylaşım paketi onaylanmadan indirilemez.")
    return FileResponse(p, media_type=MEDIA_TYPES[p.suffix], filename=p.name if download else None)
