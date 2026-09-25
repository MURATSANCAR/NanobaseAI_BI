"""Kitap Tasarım Stüdyosu servisi (editor-studio, :8000 → host 127.0.0.1:19142).

Yetki: kart servisiyle aynı anahtar (Authorization: Bearer EDITOR_CARDS_KEY); yazan her uç X-Editor
başlığı ister (köprü oturumdaki AD hesabını koyar). GPU işleri (hat, yeniden üretim) bu serviste koşmaz:
Temporal'da `editor-production` kuyruğuna iş akışı olarak verilir (flow.py), stüdyo işçisi tek sırada yürütür;
sıra bekleyen iş ekranda «sırada» görünür. Servisin yeniden başlaması süren işi kesmez.

    GET  /v1/studio/jobs                              işler
    POST /v1/studio/jobs            {book_id, art_mode}  okunmuş kitaptan yeni iş
    POST /v1/studio/jobs/docx?art_mode=  multipart file  Word dosyasından yeni iş
    POST /v1/studio/jobs/{job}/art-mode  {art_mode}   resim seçimini değiştir (yerleşim yeniden kurulur)
         art_mode: auto | every_page | chapter | none (profilin resim kararının önüne geçer)
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

Sayfa planı (plan.py; sözleşme docs/analiz/studyo-sayfa-plani-sozlesme.md), hepsi /v1/studio/jobs/{job}/ altında:
    GET plan · POST plan/freeze · PUT|DELETE plan/pages/{pid} · POST plan/pages · POST plan/order
    POST plan/pages/{pid}/split · PUT plan/palette · POST plan/pages/{pid}/bubbles/suggest
    GET plan/pages/{pid}/preview?w= · GET plan/unused-art · POST plan/figures · GET|DELETE plan/assets/{gid}
    PUT plan/photos?filename=&page= (ham gövde) · POST plan/assets/{gid}/cutout · POST plan/assets/{gid}/upscale
    GET plan/history · POST plan/restore · GET plan/jobs
Hatalar gövdede `code` taşır: NO_PLAN (404), STALE (409, güncel `rev`), BUSY (409), IN_USE (409, sayfalar),
TOO_LARGE (413). Plan düzenlemeleri süren GPU işini beklemez; yalnız GPU isteyen yazımlar (resim, figür, kaliteyi
artırma) süren GPU işinde 409 döner. `art/{key}` uçlarında key sayfa no, resim kimliği (a_…) ya da «kapak»;
plan varken sayfa no o sayfanın resim kimliğine çevrilir (eski ekran bozulmaz).
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

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from . import plan as plan_mod
from . import studio
from .flow import QUEUE
from .run import State

KEY = os.environ.get("EDITOR_CARDS_KEY", "")
DOCX_MAX = 20 * 1024 * 1024


def upload_mb() -> int:
    """Fotoğraf yükleme üst sınırı (MB): yönetim ayarı STUDIO_UPLOAD_MB, varsayılan 60. Aşan yükleme açık hata alır."""
    try:
        return max(1, int(os.environ.get("STUDIO_UPLOAD_MB", "60")))
    except ValueError:
        return 60


def authorize(authorization: str = Header("")) -> None:
    tok = authorization.removeprefix("Bearer ").strip()
    if not KEY or not hmac.compare_digest(tok, KEY):
        raise HTTPException(401, "invalid key")


def editor(x_editor: str = Header("")) -> str:
    if not x_editor.strip():
        raise HTTPException(400, "X-Editor gerekli")
    return x_editor.strip()[:200]


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, dependencies=[Depends(authorize)])


class Coded(Exception):
    """Gövdesinde `code` taşıyan hata (sözleşmedeki NO_PLAN, STALE, BUSY, IN_USE, TOO_LARGE)."""

    def __init__(self, status: int, code: str, detail: str, **extra):
        self.status, self.body = status, {"code": code, "detail": detail, **extra}


@app.exception_handler(Coded)
async def _coded(_req, e: Coded):
    return JSONResponse(e.body, status_code=e.status)


def _dir(job: str) -> Path:
    try:
        return studio.job_dir(job)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404, "iş yok") from None


def _key(key: str, d: Path | None = None) -> str:
    """Resim anahtarı: «kapak», resim kimliği (a_…) ya da sayfa no. Plan varken sayfa no o sayfanın resmine çevrilir."""
    if key == "kapak" or plan_mod.ART_ID.match(key):
        return key
    if not re.fullmatch(r"[0-9]{1,4}", key):
        raise HTTPException(404, "resim yok")
    pl = plan_mod.load(d) if d is not None else None
    if pl is not None:
        aid = plan_mod.art_at(pl, int(key))
        if not aid:
            raise HTTPException(404, "bu sayfada resim yok")
        return aid
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


ArtMode = Literal["auto", "every_page", "chapter", "none"]


class NewJob(BaseModel):
    book_id: UUID
    art_mode: ArtMode = "auto"


@app.post("/v1/studio/jobs")
async def new_job(body: NewJob, by: str = Depends(editor)) -> dict:
    from .. import db
    g = await asyncio.to_thread(db.one,
        "SELECT g.id FROM ed.generation g JOIN ed.book_version bv ON bv.id=g.book_version_id "
        "WHERE bv.book_id=%s AND EXISTS (SELECT 1 FROM ed.paragraph p WHERE p.generation_id=g.id) "
        "ORDER BY g.created_at DESC LIMIT 1", str(body.book_id))
    if g is None:
        raise HTTPException(404, "Bu kitabın okunmuş metni yok")
    d = studio.new_job({"generation_id": str(g["id"]), "book_id": str(body.book_id)}, by, body.art_mode)
    await _pipeline(d)
    return {"id": d.name}


@app.post("/v1/studio/jobs/docx")
async def new_job_docx(file: UploadFile = File(...), art_mode: ArtMode = Query("auto"),
                       by: str = Depends(editor)) -> dict:
    name = Path(file.filename or "kitap.docx").name
    if not name.lower().endswith(".docx"):
        raise HTTPException(400, "Yalnız Word (.docx) dosyası")
    data = await file.read(DOCX_MAX + 1)
    if len(data) > DOCX_MAX or not data.startswith(b"PK"):
        raise HTTPException(400, "Dosya Word (.docx) değil ya da 20 MB'tan büyük")
    d = studio.new_job({}, by, art_mode)
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

    pl = plan_mod.load(d)
    pages = []
    if pl is not None:
        # Sayfa planı varsa sayfalar plandan (ön sayfalar akıştan); resim kimlikle, sahne kimlikle bulunur.
        by_art = {s.get("art_id"): s for s in (plan or {}).get("scenes", []) if s.get("art_id")}
        for p in (pm or {}).get("pages", [])[:plan_mod.FRONT]:
            pages.append({"no": p["no"], "kind": p["kind"], "key": p["key"], "chapter": p["chapter"], "excerpt": "",
                          "art": None, "scene": None})
        for i, p in enumerate(pl["pages"]):
            aid = (p["art"] or {}).get("id") if p["art"] and not p["art"].get("asset") else None
            sc = by_art.get(aid)
            pages.append({"no": plan_mod.FRONT + i + 1, "id": p["id"], "layout": p["layout"], "art_id": aid,
                          "kind": "full" if p["layout"] == "art-full" else "flow", "key": None, "chapter": p["chapter"],
                          "excerpt": _excerpt(plan_mod.page_text(p)), "art": art(aid) if aid else None,
                          "scene": {k: sc[k] for k in ("moment", "quote", "characters", "grounded")} if sc else None})
    else:
        printed = studio._pagemap(d).art_pages() if pm else set()   # resmi basılan sayfalar
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
        "profile": prof and {k: prof.get(k) for k in ("age_min", "age_max", "age_source", "genre", "illustration",
                                                       "illustration_source", "art_source", "tone", "reading",
                                                       "disagreement", "reasons")},
        "art_mode": (j or {}).get("art_mode") or "auto",
        "spec": spec, "layout": pm and pm["layout"], "style": plan and plan["style"], "characters": chars,
        "pages": pages, "cover": {"art": art("kapak"), "info": studio.read(d, "cover.json")},
        "plan": pl and {"rev": pl["rev"], "warnings": pl.get("warnings", []), "pages": len(pl["pages"])},
        "preflight": pre,
        "front": _front(d),
        "files": {k: (d / rel).exists() for k, (rel, _) in PDF_FILES.items()},
        # Dizginin son yenilenişi: ekran önizleme adresine katar. Yeni sürüm seçilince dizgi birkaç saniye sonra
        # yenilenir; arada istenen önizleme eski sayfayı döner ve tarayıcı onu yeni adresle önbelleğe alıyordu.
        "built": max(((d / rel).stat().st_mtime for rel, _ in PDF_FILES.values() if (d / rel).exists()), default=0),
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
    pg = studio.studio_state(d)["pages"].get(_key(key, d))
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
    key = _key(key, d)
    b = await _busy(d)
    if b and not b.get("error"):
        raise HTTPException(409, "Bu kitapta süren bir üretim var; bitince tekrar deneyin")
    if body.mode == "fix" and not body.prompt.strip():
        raise HTTPException(400, "Düzeltme için neyin değişeceğini yazın")
    ap = studio.read(d, "artplan.json")
    if not ap:
        raise HTTPException(409, "Sayfa planı henüz hazır değil")
    if (key.startswith("a_") and not body.prompt.strip() and key not in studio.studio_state(d)["pages"]
            and not any(s.get("art_id") == key for s in ap["scenes"])):
        raise HTTPException(400, "Yeni resim için ne çizileceğini yazın")
    await _start(d, "ArtRegenerate", [job, key, body.mode, body.prompt, by, body.variants],
                 f"studio-{job}-art-{key}-{int(time.time())}", {"key": key, "mode": body.mode})
    return {"accepted": True}


class Select(BaseModel):
    v: int = Field(ge=1)


@app.post("/v1/studio/jobs/{job}/art/{key}/select")
async def select(job: str, key: str, body: Select, by: str = Depends(editor)) -> dict:
    d = _dir(job)
    try:
        await asyncio.to_thread(studio.select, d, _key(key, d), body.v, by)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e)) from None
    return {"ok": True}


class Approve(BaseModel):
    ok: bool = True


@app.post("/v1/studio/jobs/{job}/art/{key}/approve")
async def approve(job: str, key: str, body: Approve, by: str = Depends(editor)) -> dict:
    d = _dir(job)
    try:
        await asyncio.to_thread(studio.approve, d, _key(key, d), body.ok, by)
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
    old = studio.read(d, "job.json")
    nd = studio.new_job(old["source"], by, old.get("art_mode") or "auto")
    await _pipeline(nd)
    return {"id": nd.name}


class ArtModeBody(BaseModel):
    art_mode: ArtMode


@app.post("/v1/studio/jobs/{job}/art-mode")
async def art_mode(job: str, body: ArtModeBody, by: str = Depends(editor)) -> dict:
    """Resim seçimini sonradan değiştirir: yerleşim yeniden kurulur (stüdyo işçisinde), metin/üslup/karakterler
    korunur; eski sayfa planı geçmişte kalır, üretilmiş resimler silinmez («kullanılmayan resimler»). GPU işi
    sürüyorsa 409."""
    from . import run as run_mod
    d = _dir(job)
    b = await _busy(d)
    if b and not b.get("error"):
        raise Coded(409, "BUSY", "Bu kitapta süren bir üretim var; bitince tekrar deneyin")
    if not (studio.read(d, "manuscript.json") and studio.read(d, "profile.json") and studio.read(d, "artplan.json")):
        raise HTTPException(409, "Kitap henüz okunup yerleştirilmedi; seçim iş başlarken verilir")
    await asyncio.to_thread(run_mod.prepare_replan, d, body.art_mode, by)
    await _pipeline(d)
    return {"id": job, "art_mode": body.art_mode}


# ------------------------------------------------------------------ sayfa planı
P = "/v1/studio/jobs/{job}/plan"


def _plan_dir(job: str) -> Path:
    d = _dir(job)
    if not plan_mod.exists(d):
        raise Coded(404, "NO_PLAN", "Bu kitabın sayfa planı yok")
    return d


async def _write(fn, *args, **kw):
    """Plan yazımı iş parçacığında; plan hataları sözleşmedeki kodlarla döner."""
    try:
        return await asyncio.to_thread(fn, *args, **kw)
    except plan_mod.Stale as e:
        raise Coded(409, "STALE", "Plan başka bir yerde değişti; güncel hâli alınıp yeniden uygulanmalı",
                    rev=e.rev) from None
    except plan_mod.NoPlan:
        raise Coded(404, "NO_PLAN", "Bu kitabın sayfa planı yok") from None
    except plan_mod.InUse as e:
        raise Coded(409, "IN_USE", f"Bu görsel kullanılıyor: {', '.join(f'{n}. sayfa' for n in e.pages)}",
                    pages=e.pages) from None
    except KeyError as e:
        raise HTTPException(404, str(e.args[0] if e.args else e)) from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


async def _gpu_free(d: Path) -> None:
    b = await _busy(d)
    if b and not b.get("error"):
        raise Coded(409, "BUSY", "Bu kitapta süren bir üretim var; bitince tekrar deneyin")


def _saved(plan: dict, **extra) -> dict:
    return {"rev": plan["rev"], "warnings": plan.get("warnings", []), **extra}


@app.get(P)
def plan_get(job: str) -> Response:
    d = _plan_dir(job)
    return JSONResponse(plan_mod.load(d), headers={"Cache-Control": "no-store"})


@app.post(P + "/freeze")
async def plan_freeze(job: str, by: str = Depends(editor)) -> Response:
    """Sayfa planını kurar (varsa bozmaz, aynısını döner). Balon yerleşimi burada görsel okuyucusuz (kuralla)."""
    d = _dir(job)
    if not plan_mod.exists(d):
        if not (studio.read(d, "pagemap.json") and studio.read(d, "artplan.json")):
            raise HTTPException(409, "Sayfa planı için önce kitabın yerleşimi bitmeli")
        await _write(plan_mod.freeze, d, by)
        plan_mod.after_write(d, cover=True)
    return JSONResponse(plan_mod.load(d), headers={"Cache-Control": "no-store"})


class PageBody(BaseModel):
    rev: int
    page: dict


@app.put(P + "/pages/{pid}")
async def plan_page_put(job: str, pid: str, body: PageBody, by: str = Depends(editor)) -> dict:
    d = _plan_dir(job)
    plan, page = await _write(plan_mod.update_page, d, pid, body.rev, body.page, by)
    return _saved(plan, page=page)


class NewPage(BaseModel):
    rev: int
    after: str | None = None
    layout: str = "text-only"


@app.post(P + "/pages")
async def plan_page_new(job: str, body: NewPage, by: str = Depends(editor)) -> dict:
    d = _plan_dir(job)
    plan, page = await _write(plan_mod.insert_page, d, body.rev, body.after, body.layout, by)
    return _saved(plan, page=page)


@app.delete(P + "/pages/{pid}")
async def plan_page_delete(job: str, pid: str, rev: int = Query(...), by: str = Depends(editor)) -> dict:
    d = _plan_dir(job)
    plan, _ = await _write(plan_mod.delete_page, d, pid, rev, by)
    return _saved(plan, ok=True)


class Order(BaseModel):
    rev: int
    ids: list[str]


@app.post(P + "/order")
async def plan_order(job: str, body: Order, by: str = Depends(editor)) -> dict:
    d = _plan_dir(job)
    plan, _ = await _write(plan_mod.order, d, body.rev, body.ids, by)
    return plan


class Split(BaseModel):
    rev: int
    block: str
    at: int = Field(ge=0)


@app.post(P + "/pages/{pid}/split")
async def plan_split(job: str, pid: str, body: Split, by: str = Depends(editor)) -> dict:
    d = _plan_dir(job)
    plan, pages = await _write(plan_mod.split_page, d, pid, body.rev, body.block, body.at, by)
    return _saved(plan, pages=pages)


class PaletteBody(BaseModel):
    rev: int
    palette: dict


@app.put(P + "/palette")
async def plan_palette(job: str, body: PaletteBody, by: str = Depends(editor)) -> dict:
    d = _plan_dir(job)
    plan, _ = await _write(plan_mod.set_palette, d, body.rev, body.palette, by)
    return plan


@app.post(P + "/pages/{pid}/bubbles/suggest")
async def plan_bubbles_suggest(job: str, pid: str, by: str = Depends(editor)) -> dict:
    """Sayfanın diyaloğundan balon önerisi (kaydetmez). Kuyruk için görsel okuyucu gateway üzerinden."""
    d = _plan_dir(job)
    pl = plan_mod.load(d)
    ap = studio.read(d, "artplan.json") or {"characters": []}

    def run():
        pg = plan_mod._page(pl, pid)
        sel = studio.selected_art(d)
        img = sel.get(pg["art"]["id"]) if pg["art"] and pg["art"].get("id") else None
        if pg["art"] and pg["art"].get("asset") in pl["assets"]:
            img = str(d / pl["assets"][pg["art"]["asset"]]["path"])
        return plan_mod.suggest_bubbles(pl, pg, [c["name"] for c in ap["characters"]], img,
                                        plan_mod.locator(ap["characters"]) if img else None)
    return {"bubbles": await _write(run)}


@app.get(P + "/pages/{pid}/preview")
def plan_preview(job: str, pid: str, w: int = Query(900, ge=120, le=2400)) -> Response:
    d = _plan_dir(job)
    try:
        return _image(plan_mod.preview(d, pid, w), 0)
    except (KeyError, FileNotFoundError):
        raise HTTPException(404, "sayfa yok") from None


@app.get(P + "/unused-art")
def plan_unused(job: str) -> dict:
    d = _plan_dir(job)
    return {"art": plan_mod.unused_art(d, plan_mod.load(d))}


class Figure(BaseModel):
    prompt: str = Field(min_length=1, max_length=1200)
    characters: list[str] = Field(default_factory=list)
    page: str | None = None


@app.post(P + "/figures")
async def plan_figure(job: str, body: Figure, by: str = Depends(editor)) -> dict:
    """Serbest figür (GPU işi). Bitince varlık kütüphaneye, `page` verildiyse o sayfaya eklenir."""
    d = _plan_dir(job)
    await _gpu_free(d)
    pl = plan_mod.load(d)
    if body.page and not any(p["id"] == body.page for p in pl["pages"]):
        raise HTTPException(404, f"sayfa yok: {body.page}")
    names = {c["name"] for c in (studio.read(d, "artplan.json") or {}).get("characters", [])}
    unknown = [c for c in body.characters if c not in names]
    if unknown:
        raise HTTPException(400, f"kitapta böyle karakter yok: {', '.join(unknown)}")
    gid, jid = plan_mod.new_id("g"), plan_mod.new_id("j")
    wf = f"studio-{job}-figur-{gid}"
    plan_mod.job_record(d, jid, kind="figure", status="queued", asset=gid, page=body.page, prompt=body.prompt, by=by,
                        workflow=wf)
    await _start(d, "FigureGenerate", [job, jid, gid, body.prompt, body.characters, body.page, by], wf,
                 {"key": "figur", "mode": "figure", "asset": gid, "job": jid})
    return {"workflow": wf, "job": jid, "asset": gid}


def _asset_image(path: Path, w: int) -> Response:
    """Kütüphane görseli; w>0 saydamlığı koruyan küçük PNG (disk önbelleği), w=0 özgün dosya."""
    if not path.exists():
        raise HTTPException(404, "görsel yok")
    head = {"Cache-Control": "private, max-age=3600"}
    if w <= 0:
        return FileResponse(path, media_type="image/png" if path.suffix == ".png" else "image/jpeg", headers=head)
    w = max(64, min(w, 2400))
    cache = path.parent / ".kucuk" / f"{path.stem}-{w}.png"
    if not cache.exists() or cache.stat().st_mtime < path.stat().st_mtime:
        from PIL import Image
        cache.parent.mkdir(exist_ok=True)
        im = Image.open(path)
        im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB")
        im.thumbnail((w, w * 4))
        im.save(cache, "PNG", compress_level=6)
    return FileResponse(cache, media_type="image/png", headers=head)


@app.get(P + "/assets/{gid}")
def plan_asset(job: str, gid: str, w: int = Query(0, ge=0, le=2400)) -> Response:
    d = _plan_dir(job)
    a = plan_mod.load(d).get("assets", {}).get(gid)
    if not a:
        raise HTTPException(404, "kütüphanede yok")
    return _asset_image(d / a["path"], w)


@app.delete(P + "/assets/{gid}")
async def plan_asset_delete(job: str, gid: str, rev: int = Query(...), by: str = Depends(editor)) -> dict:
    d = _plan_dir(job)
    plan, _ = await _write(plan_mod.delete_asset, d, gid, rev, by)
    return _saved(plan, ok=True)


@app.put(P + "/photos")
async def plan_photo(job: str, request: Request, filename: str = Query(..., min_length=1, max_length=300),
                     page: str | None = None, by: str = Depends(editor)) -> dict:
    """Fotoğraf yükleme: ham gövde (multipart yok). Sınır STUDIO_UPLOAD_MB; aşan yükleme 413 TOO_LARGE."""
    from . import photo
    d = _plan_dir(job)
    if page and not any(p["id"] == page for p in plan_mod.load(d)["pages"]):
        raise HTTPException(404, f"sayfa yok: {page}")
    mb = upload_mb()
    buf = bytearray()
    async for chunk in request.stream():
        buf += chunk
        if len(buf) > mb * 1024 * 1024:
            raise Coded(413, "TOO_LARGE", f"Dosya {mb} MB sınırını aşıyor", limit_mb=mb)
    if not buf:
        raise HTTPException(400, "Boş dosya")
    gid, meta, res = await _write(plan_mod.add_photo, d, bytes(buf), filename, page, by)
    plan, fig = res["plan"], res["figure"]
    hint = photo.dpi(meta["w_px"], meta["h_px"], fig["box"] if fig else {"w": plan["page"]["w"], "h": plan["page"]["h"]})
    return _saved(plan, asset=gid, w_px=meta["w_px"], h_px=meta["h_px"], dpi_hint=int(round(hint)), figure=fig)


async def _start_plain(workflow: str, args: list, wf_id: str) -> None:
    """GPU'suz iş (busy tutmaz): aynı kuyrukta sırayla yürür."""
    try:
        await (await _temporal()).start_workflow(workflow, args=args, id=wf_id, task_queue=QUEUE)
    except Exception as e:
        raise HTTPException(503, f"İş kuyruğuna ulaşılamadı: {type(e).__name__}") from None


@app.post(P + "/assets/{gid}/cutout")
async def plan_cutout(job: str, gid: str, by: str = Depends(editor)) -> dict:
    """Arka planı kaldır: saydam yeni varlık (onaylanınca sayfadaki kutu ona geçirilir)."""
    d = _plan_dir(job)
    if gid not in plan_mod.load(d).get("assets", {}):
        raise HTTPException(404, "kütüphanede yok")
    new, jid = plan_mod.new_id("g"), plan_mod.new_id("j")
    wf = f"studio-{job}-zemin-{new}"
    plan_mod.job_record(d, jid, kind="cutout", status="queued", source=gid, asset=new, by=by, workflow=wf)
    await _start_plain("AssetCutout", [job, jid, gid, new, by], wf)
    return {"workflow": wf, "job": jid, "asset": new}


class Upscale(BaseModel):
    page: str
    item: str


@app.post(P + "/assets/{gid}/upscale")
async def plan_upscale(job: str, gid: str, body: Upscale, by: str = Depends(editor)) -> dict:
    """Kaliteyi artır (GPU işi): kutusunda 300 dpi'ye yetecek katsayıyla (2–4) büyütülmüş yeni varlık."""
    from . import photo
    d = _plan_dir(job)
    await _gpu_free(d)
    pl = plan_mod.load(d)
    try:
        bx, fit, used = plan_mod.placement(pl, body.page, body.item)
    except KeyError as e:
        raise HTTPException(404, str(e.args[0])) from None
    if used != gid:
        raise HTTPException(400, "bu kutudaki görsel başka bir varlık")
    a = pl["assets"][gid]
    now = photo.dpi(a["w_px"], a["h_px"], bx, fit)
    new, jid = plan_mod.new_id("g"), plan_mod.new_id("j")
    wf = f"studio-{job}-buyut-{new}"
    plan_mod.job_record(d, jid, kind="upscale", status="queued", source=gid, asset=new, page=body.page,
                        item=body.item, by=by, workflow=wf, dpi_before=int(round(now)),
                        factor=photo.upscale_factor(now))
    await _start(d, "AssetUpscale", [job, jid, gid, new, body.page, body.item, by], wf,
                 {"key": "buyut", "mode": "upscale", "asset": new, "job": jid})
    return {"workflow": wf, "job": jid, "asset": new, "factor": photo.upscale_factor(now), "dpi_before": int(round(now))}


@app.get(P + "/history")
def plan_history(job: str) -> list:
    return plan_mod.history(_plan_dir(job))


class Restore(BaseModel):
    rev: int = Field(ge=1)


@app.post(P + "/restore")
async def plan_restore(job: str, body: Restore, by: str = Depends(editor)) -> dict:
    d = _plan_dir(job)
    plan, _ = await _write(plan_mod.restore, d, body.rev, by)
    return plan


@app.get(P + "/jobs")
async def plan_jobs(job: str) -> dict:
    """Süren GPU işi (busy) ve figür / zemin ayıklama / kaliteyi artırma işlerinin durumu (ekran bununla bekler)."""
    d = _plan_dir(job)
    return {"busy": await _busy(d), "jobs": await asyncio.to_thread(plan_mod.jobs, d)}


from .api_coloring import router as _coloring_router  # noqa: E402  boyama/etkinlik kitabı (coloring.py)
app.include_router(_coloring_router)
