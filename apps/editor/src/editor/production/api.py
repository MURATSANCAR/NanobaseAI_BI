"""Kitap Tasarım Stüdyosu servisi (editor-studio, :8000 → host 127.0.0.1:19142).

Yetki: kart servisiyle aynı anahtar (Authorization: Bearer EDITOR_CARDS_KEY); yazan her uç X-Editor
başlığı ister (köprü oturumdaki AD hesabını koyar). GPU işleri (hat, yeniden üretim) bu serviste koşmaz:
Temporal'da `editor-production` kuyruğuna iş akışı olarak verilir (flow.py), stüdyo işçisi tek sırada yürütür;
sıra bekleyen iş ekranda «sırada» görünür. Servisin yeniden başlaması süren işi kesmez.

    GET  /v1/studio/jobs                              işler
    POST /v1/studio/jobs            {book_id}         okunmuş kitaptan yeni iş
    POST /v1/studio/jobs/docx       multipart file    Word dosyasından yeni iş
    GET  /v1/studio/jobs/{job}                        bütün görünüm (adımlar, kararlar, sayfalar, ön kontrol)
    GET  /v1/studio/jobs/{job}/pages/{n}/preview?w=   dizilmiş sayfa (PNG)
    GET  /v1/studio/jobs/{job}/cover/preview?w=       kapak açılımı (PNG)
    GET  /v1/studio/jobs/{job}/art/{key}/{v}?w=       resim sürümü (key: sayfa no | kapak)
    GET  /v1/studio/jobs/{job}/characters/{i}?w=      karakter referansı
    POST /v1/studio/jobs/{job}/art/{key}/regenerate   {mode: fix|new, prompt, variants}
    POST /v1/studio/jobs/{job}/art/{key}/select       {v}
    POST /v1/studio/jobs/{job}/art/{key}/approve      {ok}
    POST /v1/studio/jobs/{job}/kunye   {fields}       künyenin eksik/düzeltilecek alanları
    POST /v1/studio/jobs/{job}/resume                 yarıda kalan işi sürdür
    POST /v1/studio/jobs/{job}/restart                aynı kaynakla yeni iş
    GET  /v1/studio/jobs/{job}/pdf/{kind}             ic | kapak | baski-ic | baski-kapak
"""

from __future__ import annotations

import asyncio
import hmac
import io
import os
import re
import time
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from . import studio
from .flow import QUEUE
from .run import State

KEY = os.environ.get("EDITOR_CARDS_KEY", "")
DOCX_MAX = 20 * 1024 * 1024


def authorize(authorization: str = Header("")) -> None:
    tok = authorization.removeprefix("Bearer ").strip()
    if not KEY or not hmac.compare_digest(tok, KEY):
        raise HTTPException(401, "invalid key")


def editor(x_editor: str = Header("")) -> str:
    if not x_editor.strip():
        raise HTTPException(400, "X-Editor gerekli")
    return x_editor.strip()[:200]


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, dependencies=[Depends(authorize)])


def _dir(job: str) -> Path:
    try:
        return studio.job_dir(job)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404, "iş yok") from None


def _key(key: str) -> str:
    if key != "kapak" and not re.fullmatch(r"[0-9]{1,4}", key):
        raise HTTPException(404, "resim yok")
    return key


async def _temporal():
    from ..jobs import temporal
    return await temporal()


async def _busy(d: Path) -> dict | None:
    """busy.json; iş akışı artık koşmuyorsa (iptal, zaman aşımı, elle sonlandırma) kayıt bayattır, silinir."""
    b = studio.busy(d)
    if not b or b.get("error") or not b.get("workflow_id"):
        return b
    try:
        desc = await (await _temporal()).get_workflow_handle(b["workflow_id"]).describe()
        running = desc.status is not None and desc.status.name == "RUNNING"
    except Exception:  # noqa: BLE001 - Temporal'a ulaşılamıyorsa kayda güvenilir
        return b
    if running:
        return b
    studio.set_busy(d, None)
    return None


async def _start(d: Path, workflow: str, args: list, wf_id: str, info: dict) -> None:
    """GPU işini kuyruğa verir. busy.json önce yazılır ki ekran «sırada»yı hemen görsün."""
    from temporalio.exceptions import WorkflowAlreadyStartedError
    studio.set_busy(d, {**info, "since": time.time(), "queued": True, "workflow_id": wf_id})
    try:
        await (await _temporal()).start_workflow(workflow, args=args, id=wf_id, task_queue=QUEUE)
    except WorkflowAlreadyStartedError:
        raise HTTPException(409, "Bu kitapta süren bir iş var") from None
    except Exception as e:
        studio.set_busy(d, None)
        raise HTTPException(503, f"İş kuyruğuna ulaşılamadı: {type(e).__name__}") from None


async def _pipeline(d: Path, resume: bool = False) -> None:
    if not resume and not studio.read(d, "state.json"):
        State(d)                        # adımlar «bekliyor» görünsün; iş sırada olabilir
    try:
        await _start(d, "BookProduction", [d.name, resume], f"studio-{d.name}-{int(time.time())}",
                     {"key": "hat", "mode": "resume" if resume else "run"})
    except HTTPException as e:
        st = studio.read(d, "state.json")
        if st and e.status_code == 503:                 # kuyruğa verilemedi: iş «başladı» görünmesin
            st.update(status="fail", error=e.detail, finished=time.time())
            studio.write(d, "state.json", st)
        raise


# ------------------------------------------------------------------ işler
@app.get("/v1/studio/jobs")
async def jobs() -> dict:
    out = []
    for j in await asyncio.to_thread(studio.list_jobs):
        out.append({**j, "busy": await _busy(studio.root() / j["id"])})
    return {"jobs": out}


class NewJob(BaseModel):
    book_id: UUID


@app.post("/v1/studio/jobs")
async def new_job(body: NewJob, by: str = Depends(editor)) -> dict:
    from .. import db
    g = await asyncio.to_thread(db.one,
        "SELECT g.id FROM ed.generation g JOIN ed.book_version bv ON bv.id=g.book_version_id "
        "WHERE bv.book_id=%s AND EXISTS (SELECT 1 FROM ed.paragraph p WHERE p.generation_id=g.id) "
        "ORDER BY g.created_at DESC LIMIT 1", str(body.book_id))
    if g is None:
        raise HTTPException(404, "Bu kitabın okunmuş metni yok")
    d = studio.new_job({"generation_id": str(g["id"]), "book_id": str(body.book_id)}, by)
    await _pipeline(d)
    return {"id": d.name}


@app.post("/v1/studio/jobs/docx")
async def new_job_docx(file: UploadFile = File(...), by: str = Depends(editor)) -> dict:
    name = Path(file.filename or "kitap.docx").name
    if not name.lower().endswith(".docx"):
        raise HTTPException(400, "Yalnız Word (.docx) dosyası")
    data = await file.read(DOCX_MAX + 1)
    if len(data) > DOCX_MAX or not data.startswith(b"PK"):
        raise HTTPException(400, "Dosya Word (.docx) değil ya da 20 MB'tan büyük")
    d = studio.new_job({}, by)
    (d / "girdi").mkdir()
    path = d / "girdi" / re.sub(r"[^\w.\-]", "_", name)
    path.write_bytes(data)
    job = studio.read(d, "job.json")
    job["source"] = {"docx": str(path), "file_name": name}
    studio.write(d, "job.json", job)
    await _pipeline(d)
    return {"id": d.name}


def _excerpt(t: str, n: int = 160) -> str:
    t = re.sub(r"\s+", " ", t or "").strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


@app.get("/v1/studio/jobs/{job}")
async def job_view(job: str) -> dict:
    d = _dir(job)
    busy = await _busy(d)
    return await asyncio.to_thread(_job_view, d, job, busy)


def _job_view(d: Path, job: str, busy: dict | None) -> dict:
    j, st = studio.read(d, "job.json"), studio.read(d, "state.json", {})
    ms, prof, spec = studio.read(d, "manuscript.json"), studio.read(d, "profile.json"), studio.read(d, "spec.json")
    pm, plan = studio.read(d, "pagemap.json"), studio.read(d, "artplan.json")
    sd, pre = studio.studio_state(d), studio.read(d, "preflight.json")
    scenes = {s["page"]: s for s in (plan or {}).get("scenes", [])}

    def art(key):
        pg = sd["pages"].get(key)
        if not pg:
            return None
        return {"selected": pg["selected"], "approved": pg.get("approved", False), "approved_by": pg.get("approved_by"),
                "versions": [{k: v[k] for k in ("v", "mode", "prompt", "by", "at", "dpi", "base")} for v in pg["versions"]]}

    printed = studio._pagemap(d).art_pages() if pm else set()   # resmi basılan sayfalar
    pages = []
    for p in (pm or {}).get("pages", []):
        sc = scenes.get(p["no"]) if p["no"] in printed else None
        pages.append({"no": p["no"], "kind": p["kind"], "key": p["key"], "chapter": p["chapter"],
                      "excerpt": _excerpt(p["text"]), "art": art(str(p["no"])) if p["no"] in printed else None,
                      "scene": {k: sc[k] for k in ("moment", "quote", "characters", "grounded")} if sc else None})
    chars = [{"i": i, "name": c["name"], "species": c["species"], "look": c["look"], "from_text": c["from_text"],
              "role": c["role"], "has_ref": c["name"] in sd.get("characters", {})}
             for i, c in enumerate((plan or {}).get("characters", []))]
    return {
        "job": j, "state": st, "busy": busy,
        "book": ms and {"title": ms["title"], "author": ms["author"], "meta": ms["meta"],
                        "chapters": [c["title"] for c in ms["chapters"]],
                        "words": sum(len(b["text"].split()) for c in ms["chapters"] for b in c["blocks"])},
        "profile": prof and {k: prof[k] for k in ("age_min", "age_max", "age_source", "genre", "illustration", "tone",
                                                   "reading", "disagreement", "reasons")},
        "spec": spec, "layout": pm and pm["layout"], "style": plan and plan["style"], "characters": chars,
        "pages": pages, "cover": {"art": art("kapak"), "info": studio.read(d, "cover.json")},
        "preflight": pre,
        "front": _front(d),
        "files": {k: (d / rel).exists() for k, (rel, _) in PDF_FILES.items()},
    }


def _front(d: Path) -> dict | None:
    from .front import EDITABLE, MISSING
    fr = studio.read(d, "front.json")
    if not fr:
        return None
    src = {"DIZI": "Dizi", "YAYIN_YONETMENI": "Yayın Yönetmeni", "PROJE_EDITORU": "Proje Editörü", "EDITOR": "Editör",
           "YAYINEVI": "Yayınevi", "ADRES": "Adres", "TELEFON": "Telefon", "EPOSTA": "E-posta",
           "SERTIFIKA": "Sertifika No", "MATBAA": "Baskı ve Cilt", "MATBAA_SERTIFIKA": "Matbaa Sertifika No",
           "MATBAA_ADRES": "Matbaa Adresi", "TELIF": "Telif"}
    sources = {src[k]: v.get("source") for k, v in (fr.get("kunye_fields") or {}).items() if k in src}
    manual = fr.get("manual") or {}
    return {"rows": [{"label": lab, "value": val, "missing": val == MISSING, "editable": lab in EDITABLE,
                      "source": "elle girildi" if lab in manual else sources.get(lab)}
                     for lab, val in fr["kunye"] if lab],
            "bios": fr.get("bios", [])}


# ------------------------------------------------------------------ görseller
def _image(path: Path, w: int) -> Response:
    """İstenen genişlikte WebP (disk önbelleği); w=0 özgün PNG."""
    if not path.exists():
        raise HTTPException(404, "görsel yok")
    if w <= 0:
        return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})
    w = max(64, min(w, 2400))
    cache = path.parent / ".kucuk" / f"{path.stem}-{w}.webp"
    if not cache.exists() or cache.stat().st_mtime < path.stat().st_mtime:
        from PIL import Image
        cache.parent.mkdir(exist_ok=True)
        im = Image.open(path).convert("RGB")
        im.thumbnail((w, w * 4))
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=86)
        cache.write_bytes(buf.getvalue())
    return FileResponse(cache, media_type="image/webp", headers={"Cache-Control": "private, max-age=3600"})


@app.get("/v1/studio/jobs/{job}/pages/{n}/preview")
def page_preview(job: str, n: int, w: int = Query(900, ge=120, le=2400)) -> Response:
    d = _dir(job)
    try:
        return _image(studio.page_preview(d, n, w), 0)
    except FileNotFoundError:
        raise HTTPException(404, "sayfa yok") from None


@app.get("/v1/studio/jobs/{job}/cover/preview")
def cover_preview(job: str, w: int = Query(1400, ge=200, le=3000)) -> Response:
    d = _dir(job)
    if not (d / "kapak" / "kapak.pdf").exists():
        raise HTTPException(404, "kapak yok")
    return _image(studio.cover_preview(d, w), 0)


@app.get("/v1/studio/jobs/{job}/art/{key}/{v}")
def art_image(job: str, key: str, v: int, w: int = Query(800, ge=0, le=2400)) -> Response:
    d = _dir(job)
    pg = studio.studio_state(d)["pages"].get(_key(key))
    if not pg or not 1 <= v <= len(pg["versions"]):
        raise HTTPException(404, "sürüm yok")
    return _image(Path(pg["versions"][v - 1]["path"]), w)


@app.get("/v1/studio/jobs/{job}/characters/{i}")
def character_image(job: str, i: int, w: int = Query(256, ge=0, le=1024)) -> Response:
    d = _dir(job)
    plan = studio.read(d, "artplan.json") or {}
    chars = plan.get("characters", [])
    if not 0 <= i < len(chars):
        raise HTTPException(404, "karakter yok")
    path = studio.studio_state(d).get("characters", {}).get(chars[i]["name"])
    if not path:
        raise HTTPException(404, "referans yok")
    return _image(Path(path), w)


PDF_FILES = {"ic": ("dizgi/ic-sayfalar.pdf", "ic-sayfalar"), "kapak": ("kapak/kapak.pdf", "kapak"),
             "baski-ic": ("baski/ic-sayfalar-baski.pdf", "ic-sayfalar-BASKI-CMYK"),
             "baski-kapak": ("baski/kapak-baski.pdf", "kapak-BASKI-CMYK")}


@app.get("/v1/studio/jobs/{job}/pdf/{kind}")
def pdf(job: str, kind: Literal["ic", "kapak", "baski-ic", "baski-kapak"]) -> Response:
    """Ekran PDF'leri (ic, kapak; RGB) ve baskı PDF'leri (baski-*; CMYK, PDF/X, kesim işaretli)."""
    d = _dir(job)
    rel, label = PDF_FILES[kind]
    path = d / rel
    if not path.exists():
        raise HTTPException(404, "Baskı PDF'i bütün denetimler geçince üretilir" if kind.startswith("baski") else "PDF yok")
    title = re.sub(r"[^\w\-]+", "-", (studio.read(d, "state.json", {}).get("title") or job)).strip("-")
    return FileResponse(path, media_type="application/pdf", filename=f"{title}-{label}.pdf")


# ------------------------------------------------------------------ düzenleme
class Regenerate(BaseModel):
    mode: Literal["fix", "new"]
    prompt: str = Field("", max_length=1200)
    variants: int = Field(1, ge=1, le=3)


@app.post("/v1/studio/jobs/{job}/art/{key}/regenerate")
async def regenerate(job: str, key: str, body: Regenerate, by: str = Depends(editor)) -> dict:
    d = _dir(job)
    key = _key(key)
    b = await _busy(d)
    if b and not b.get("error"):
        raise HTTPException(409, "Bu kitapta süren bir üretim var; bitince tekrar deneyin")
    if body.mode == "fix" and not body.prompt.strip():
        raise HTTPException(400, "Düzeltme için neyin değişeceğini yazın")
    if not studio.read(d, "artplan.json"):
        raise HTTPException(409, "Sayfa planı henüz hazır değil")
    await _start(d, "ArtRegenerate", [job, key, body.mode, body.prompt, by, body.variants],
                 f"studio-{job}-art-{key}-{int(time.time())}", {"key": key, "mode": body.mode})
    return {"accepted": True}


class Select(BaseModel):
    v: int = Field(ge=1)


@app.post("/v1/studio/jobs/{job}/art/{key}/select")
async def select(job: str, key: str, body: Select, by: str = Depends(editor)) -> dict:
    d = _dir(job)
    try:
        await asyncio.to_thread(studio.select, d, _key(key), body.v, by)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e)) from None
    return {"ok": True}


class Approve(BaseModel):
    ok: bool = True


@app.post("/v1/studio/jobs/{job}/art/{key}/approve")
async def approve(job: str, key: str, body: Approve, by: str = Depends(editor)) -> dict:
    d = _dir(job)
    try:
        await asyncio.to_thread(studio.approve, d, _key(key), body.ok, by)
    except KeyError:
        raise HTTPException(404, "resim yok") from None
    return {"ok": True}


@app.post("/v1/studio/jobs/{job}/resume")
async def resume(job: str, by: str = Depends(editor)) -> dict:
    """Yarıda kalan işi kaldığı yerden sürdürür (çizilmiş resimler korunur)."""
    d = _dir(job)
    b = await _busy(d)
    if b and not b.get("error"):
        raise HTTPException(409, "Bu kitapta süren bir iş var")
    if not studio.read(d, "artplan.json"):
        raise HTTPException(409, "Sayfa planı yok; «Yeniden başlat» kullanın")
    await _pipeline(d, resume=True)
    return {"id": job}


class Kunye(BaseModel):
    fields: dict[str, str] = Field(default_factory=dict)


@app.post("/v1/studio/jobs/{job}/kunye")
async def kunye(job: str, body: Kunye, by: str = Depends(editor)) -> dict:
    """Künyenin eksik ya da düzeltilecek alanları; kaynağı olmayan alanı editör girer."""
    d = _dir(job)
    if not studio.read(d, "front.json"):
        raise HTTPException(409, "Künye henüz hazır değil")
    try:
        fr = await asyncio.to_thread(studio.set_kunye, d, body.fields, by)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return {"kunye": fr["kunye"]}


@app.post("/v1/studio/jobs/{job}/restart")
async def restart(job: str, by: str = Depends(editor)) -> dict:
    """Kesilen ya da hatayla biten hattı aynı kaynakla yeni iş olarak yeniden başlatır."""
    d = _dir(job)
    src = studio.read(d, "job.json")["source"]
    nd = studio.new_job(src, by)
    await _pipeline(nd)
    return {"id": nd.name}
