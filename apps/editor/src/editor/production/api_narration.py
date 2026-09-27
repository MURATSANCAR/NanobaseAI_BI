"""Sesli okuma uçları (stüdyo servisi; api.py'ye tek `include_router` ile bağlanır). Hepsi
/v1/studio/jobs/{job}/narration altında; yetki api.py'nin uygulama düzeyi anahtarıyla, yazanlarda X-Editor.

    GET  narration                       sesler, ayarlar, konuşanlar, sayfa durumları, süren iş, sözlükler
    PUT  narration/settings              {narrator, characters: {konuşan: ses}}
    PUT  narration/lexicon               {scope: job|publisher, entries: [{word, say}]}  (kapsamın tamamı)
    POST narration/run                   {pages: [pid] | null, force: bool} → {workflow, job}  (Temporal işi)
    GET  narration/pages/{pid}           sayfanın blokları, kelimeleri ve (güncelse) zamanları
    GET  narration/pages/{pid}/audio     sayfanın sesi (audio/mpeg, Range destekli)
    POST narration/read                  {text} → okunuş (sözlük ve Türkçe kurallarıyla; model yok)
    POST narration/sample                {text, voice} → kısa deneme sesi (audio/mpeg; ses+okunuş başına bir kez üretilir)
    GET  narration/overlay               media_overlay(job): EPUB medya kaplaması için bütün kitabın zamanları

Ses kütüphanesi (yayınevi düzeyinde; voices.py), /v1/studio/voices altında:
    GET    voices                        gruplar, bütün sesler (tarifli + yüklenmiş), hak beyanı metni, süre sınırları
    POST   voices                        {label, group, note, owner, confirm, reference, audio(b64 WAV),
                                          document?: {name, data(b64)}, original?: {name, data(b64)}}  (X-Editor)
    GET    voices/{ses}/document         izin belgesi (PDF/PNG/JPEG)
    DELETE voices/{ses}                  kütüphaneden kaldır (X-Editor + X-Editor-Admin: 1; yetkiyi köprü verir)
Yükleme reddi 400 `{"code": "VOICE_REJECTED", "detail": <Türkçe neden>}`; dosya sınırı STUDIO_UPLOAD_MB (413 TOO_LARGE).

Hatalar gövdede `code` taşır: NO_PLAN (404: kitap henüz sayfalara yerleşmedi), PREPARING (409: sayfa düzeni
kendiliğinden kuruluyor, `state` preparing | waiting; ekran bekler), PLAN_FAILED (409: kurulum düştü; GET `?retry=1`),
NO_VOICE (503: seslendirme bu kurulumda açık değil), BUSY (409: bu kitapta seslendirme sürüyor), NOTHING (400:
seslendirilecek sayfa yok).

Planı olmayan iş (sayfa düzeni hiç açılmamış eski iş): `GET narration` ve `POST narration/run` planı kendiliğinden
kurar (`plan.ensure`: dondurmanın aynısı, görsel çizilmez, balonlar kuralla). Öteki uçlar ekranın ilk çağrısından
sonra gelir; plan yokken kurulmaz, kurulum sürüyorsa PREPARING döner.
"""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from . import narration as N
from . import plan as plan_mod
from . import studio

router = APIRouter()
P = "/v1/studio/jobs/{job}/narration"
PID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def _editor(x_editor: str = Header("")) -> str:
    if not x_editor.strip():
        raise HTTPException(400, "X-Editor gerekli")
    return x_editor.strip()[:200]


def _coded(status: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse({"code": code, "detail": detail}, status_code=status)


class _Err(Exception):
    def __init__(self, status: int, code: str, detail: str):
        self.resp = _coded(status, code, detail)


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


async def _ready(job: str, by: str | None, retry: bool = False) -> Path:
    """Giriş uçları: plan yoksa kendiliğinden kurulur (api.auto_plan_dir; 409 PREPARING ile ekran bekler)."""
    from .api import auto_plan_dir
    return await auto_plan_dir(job, by, "sesli okuma", retry)


def _guard(fn):
    """_Err'i kodlu JSON yanıta çevirir (router kendi hata işleyicisini kuramaz)."""
    import functools

    @functools.wraps(fn)
    async def wrap(*a, **kw):
        try:
            return await fn(*a, **kw)
        except _Err as e:
            return e.resp
        except N.VoiceUnavailable:
            return _coded(503, "NO_VOICE", "Sesli okuma bu kurulumda henüz açık değil.")
    return wrap


def _running(d: Path) -> dict | None:
    for r in plan_mod.jobs(d):
        if r.get("kind") == "narration":
            return r if r.get("status") in ("queued", "running") else None
    return None


def _latest(d: Path) -> dict | None:
    return next((r for r in plan_mod.jobs(d) if r.get("kind") == "narration"), None)


def _speakers(d: Path) -> list[str]:
    names: list[str] = []
    pl = plan_mod.load(d) or {}
    for pg in pl.get("pages", []):
        for bb in pg.get("bubbles") or []:
            if bb.get("speaker") and bb["speaker"] not in names:
                names.append(bb["speaker"])
    for c in (studio.read(d, "artplan.json") or {}).get("characters", []):
        if c.get("name") and c["name"] not in names:
            names.append(c["name"])
    return names


def _overview(d: Path) -> dict:
    rows = N.status(d)
    count = {k: sum(1 for r in rows if r["status"] == k) for k in ("done", "stale", "missing", "empty")}
    return {
        "voices": N.all_voices(),
        "groups": N.GROUPS,
        "settings": N.settings_of(d),
        "speakers": _speakers(d),
        "pages": rows,
        "summary": {**count, "duration": round(sum(r["duration"] or 0 for r in rows if r["status"] == "done"), 1)},
        "job": _latest(d),
        "lexicon": {"job": N.lexicon_entries(d, "job"), "publisher": N.lexicon_entries(None, "publisher")},
        "plan_auto": plan_mod.auto_state(d),              # sayfa düzeni kendiliğinden kurulduysa kaydı
    }


@router.get(P)
@_guard
async def narration_view(job: str, retry: bool = Query(False), x_editor: str = Header("")) -> dict:
    d = await _ready(job, x_editor, retry)
    view, ok = await asyncio.gather(asyncio.to_thread(_overview, d), N.available())
    return {**view, "available": ok}


class Settings(BaseModel):
    narrator: str
    characters: dict[str, str] = {}


@router.put(P + "/settings")
@_guard
async def narration_settings(job: str, body: Settings, by: str = Depends(_editor)) -> dict:
    d = _dir(job)
    try:
        return await asyncio.to_thread(N.set_settings, d, body.narrator, body.characters, by)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


class Entry(BaseModel):
    word: str = Field(max_length=120)
    say: str = Field(max_length=240)


class LexiconBody(BaseModel):
    scope: str = "job"
    entries: list[Entry]


@router.put(P + "/lexicon")
@_guard
async def narration_lexicon(job: str, body: LexiconBody, by: str = Depends(_editor)) -> dict:
    d = _dir(job)
    try:
        out = await asyncio.to_thread(N.set_lexicon, d, body.scope, [e.model_dump() for e in body.entries], by)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return {"scope": body.scope, "entries": out}


class Run(BaseModel):
    pages: list[str] | None = None
    force: bool = False


@router.post(P + "/run")
@_guard
async def narration_run(job: str, body: Run, by: str = Depends(_editor)) -> dict:
    """Seslendirme işini kuyruğa verir. `pages` verilmezse sesi olmayan ve güncel olmayan sayfalar; `force` ile
    okunacak metni olan bütün sayfalar (verilen sayfalar her durumda yeniden üretilir)."""
    from .api import _temporal
    from .flow import QUEUE
    d = await _ready(job, by)
    if _running(d):
        raise _Err(409, "BUSY", "Bu kitapta seslendirme sürüyor.")
    rows = await asyncio.to_thread(N.status, d)
    by_id = {r["id"]: r for r in rows}
    if body.pages is not None:
        unknown = [p for p in body.pages if p not in by_id]
        if unknown:
            raise HTTPException(404, "sayfa yok: " + ", ".join(unknown))
        pids = [p for p in body.pages if by_id[p]["status"] != "empty"]
    elif body.force:
        pids = [r["id"] for r in rows if r["status"] != "empty"]
    else:
        pids = [r["id"] for r in rows if r["status"] in ("missing", "stale")]
    if not pids:
        raise _Err(400, "NOTHING", "Seslendirilecek sayfa yok; bütün sayfalar güncel.")
    if not await N.available():
        raise N.VoiceUnavailable("kapalı")
    jid = plan_mod.new_id("j")
    wf = f"studio-{job}-ses-{jid}"
    plan_mod.job_record(d, jid, kind="narration", status="queued", pages=pids, progress=[0, len(pids)], by=by,
                        workflow=wf)
    try:
        await (await _temporal()).start_workflow("BookNarration", args=[job, jid, pids, by], id=wf, task_queue=QUEUE)
    except Exception as e:  # noqa: BLE001
        plan_mod.job_record(d, jid, status="fail", error=f"İş kuyruğuna ulaşılamadı: {type(e).__name__}")
        raise HTTPException(503, f"İş kuyruğuna ulaşılamadı: {type(e).__name__}") from None
    return {"workflow": wf, "job": jid, "pages": len(pids)}


@router.get(P + "/pages/{pid}")
@_guard
async def narration_page(job: str, pid: str) -> dict:
    d = _dir(job)
    try:
        return await asyncio.to_thread(N.page_view, d, pid)
    except KeyError:
        raise HTTPException(404, "sayfa yok") from None


@router.get(P + "/pages/{pid}/audio")
@_guard
async def narration_audio(job: str, pid: str) -> Response:
    d = _dir(job)
    if not PID.match(pid):
        raise HTTPException(404, "ses yok")
    p = N.audio_path(d, pid)
    if not p.exists():
        raise HTTPException(404, "Bu sayfanın sesi henüz yok")
    # Starlette FileResponse Range isteklerini karşılar (tarayıcıda ileri/geri sarma).
    return FileResponse(p, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=60"})


class ReadBody(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.post(P + "/read")
@_guard
async def narration_read(job: str, body: ReadBody) -> dict:
    d = _dir(job)
    words = N.read(body.text, N.lexicon(d))
    return {"spoken": N.spoken_text(words), "words": [{"text": w.text, "spoken": w.spoken} for w in words]}


class Sample(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    voice: str = N.DEFAULT_NARRATOR


@router.post(P + "/sample")
@_guard
async def narration_sample(job: str, body: Sample, _by: str = Depends(_editor)) -> Response:
    d = _dir(job)
    if not N.is_voice(body.voice):
        raise HTTPException(400, "Bilinmeyen ses")
    try:
        data = await N.sample(body.text, body.voice, N.lexicon(d))
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return Response(data, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


@router.get(P + "/overlay")
@_guard
async def narration_overlay(job: str) -> dict:
    d = _dir(job)
    t = time.time()
    out = await asyncio.to_thread(N.media_overlay, d)
    return {**out, "built_seconds": round(time.time() - t, 2)}


# ------------------------------------------------------------------ ses kütüphanesi (yayınevi düzeyinde)
V = "/v1/studio/voices"


class FileIn(BaseModel):
    name: str = Field(default="", max_length=300)
    data: str                                        # base64


class VoiceIn(BaseModel):
    label: str = Field(max_length=120)
    group: str = Field(max_length=40)
    note: str = Field(default="", max_length=200)
    owner: str = Field(max_length=200)
    confirm: bool = False
    reference: str = Field(default="", max_length=400)
    audio: str                                       # base64 WAV (tarayıcı tek kanal 16 bit'e çevirir)
    document: FileIn | None = None
    original: FileIn | None = None


def _b64(v: str, what: str) -> bytes:
    import base64
    import binascii
    from .api import upload_mb
    try:
        data = base64.b64decode(v, validate=True)
    except (binascii.Error, ValueError):
        raise _Err(400, "VOICE_REJECTED", f"{what} okunamadı.") from None
    if len(data) > upload_mb() * 1024 * 1024:
        raise _Err(413, "TOO_LARGE", f"{what} {upload_mb()} MB sınırını aşıyor.")
    return data


def _library() -> dict:
    from . import voices
    return {"groups": N.GROUPS, "voices": N.all_voices(), "rights_text": voices.RIGHTS_TEXT,
            "limits": {"min_sec": voices.MIN_SEC, "max_sec": voices.MAX_SEC, "upload_mb": _upload_mb()},
            "removed": [voices.as_voice(r) for r in voices.entries(True) if r.get("removed")]}


def _upload_mb() -> int:
    from .api import upload_mb
    return upload_mb()


@router.get(V)
@_guard
async def voices_list() -> dict:
    return await asyncio.to_thread(_library)


@router.post(V)
@_guard
async def voices_add(body: VoiceIn, by: str = Depends(_editor)) -> dict:
    from . import voices
    audio = _b64(body.audio, "Ses kaydı")
    doc = (_b64(body.document.data, "İzin belgesi"), body.document.name) if body.document else None
    orig = (_b64(body.original.data, "Özgün ses dosyası"), body.original.name) if body.original else None
    try:
        rec = await asyncio.to_thread(voices.add, audio, label=body.label, group=body.group, note=body.note,
                                      owner=body.owner, confirm=body.confirm, by=by, document=doc,
                                      reference=body.reference, original=orig)
    except voices.VoiceError as e:
        raise _Err(400, "VOICE_REJECTED", str(e)) from None
    return {"voice": voices.as_voice(rec), "stats": rec["stats"], "rights": rec["rights"]}


@router.get(V + "/{vid}/document")
@_guard
async def voices_document(vid: str) -> Response:
    from . import voices
    if not voices.VID.match(vid):
        raise HTTPException(404, "ses yok")
    try:
        path, mime, name = voices.document(vid)
    except FileNotFoundError:
        raise HTTPException(404, "Bu sesin izin belgesi dosya olarak yüklenmedi") from None
    return FileResponse(path, media_type=mime, filename=name, headers={"Cache-Control": "private, no-store"})


@router.delete(V + "/{vid}")
@_guard
async def voices_remove(vid: str, by: str = Depends(_editor), x_editor_admin: str = Header("")) -> dict:
    from . import voices
    if x_editor_admin != "1":
        raise HTTPException(403, "Sesi kütüphaneden yalnız yönetici kaldırabilir")
    if not voices.VID.match(vid):
        raise HTTPException(404, "ses yok")
    try:
        rec = await asyncio.to_thread(voices.remove, vid, by)
    except KeyError:
        raise HTTPException(404, "ses yok") from None
    return {"voice": voices.as_voice(rec)}
