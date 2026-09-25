"""Kitap Tasarım Stüdyosu — seri karakter kartı için köprü uçları.

Stüdyo servisindeki `/v1/studio/jobs/{job}/character-cards/...` uçlarının birebir vekili (motor:
apps/editor/src/editor/production/characters.py). Oturum zorunlu (`_books`); yazanlarda `X-Editor` = oturumdaki AD
hesabı ve `admin.audit` kaydı. Servisin 4xx gövdesi ({"code": "STALE", "rev"}, {"code": "NO_SERIES"}, BUSY …) olduğu
gibi ekrana gider: ekran çakışmayı ve dizisi belirsiz kitabı koddan tanır.

Yeniden deneme sayısı yönetim ekranındaki `STUDIO_CHARACTER_RETRIES` ayarıdır (grup «studio»). Değer stüdyoya
köprüden iletilir (`PUT /v1/studio/character-settings`): yönetim ekranında kaydedilince, karakter paneli açılınca ve
GPU işi başlatan her stüdyo isteğinden önce. Stüdyo son iletilen değeri saklar; köprüye ulaşamadığı zaman o değerle
çalışır.

app.py'de `_books` tanımından sonra (stüdyo bloğunun yanında) bağlanır:
    from semantic_bridge import editorial_studio_characters
    editorial_studio_characters.register(app, {"auth": _books})
"""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any, Callable

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import admin as admin_mod
from semantic_bridge import editorial_studio

log = logging.getLogger(__name__)

CARD = re.compile(r"^c_[0-9a-f]{8}$")
REF = re.compile(r"^r_[0-9a-f]{8}$")
IMAGE_MIME = {"image/png", "image/jpeg", "image/webp"}
UPLOAD_MIME = {"image/png", "image/jpeg", "image/webp", "image/heic", "image/heif", "application/octet-stream"}
RETRIES_KEY = "STUDIO_CHARACTER_RETRIES"
# GPU işi başlatan stüdyo istekleri: önce yeniden deneme sayısı stüdyoya iletilir (resim üretimi bu işlerde olur).
GPU_START = re.compile(r"^/api/v1/editorial/studio/jobs(?:/[0-9]{14}[0-9a-f]{6}/(?:resume|restart|art-mode|"
                       r"art/[^/]+/regenerate|plan/figures|character-cards/check))?$")


class CardError(Exception):
    def __init__(self, status: int, body: object):
        super().__init__(f"character-cards {status}")
        self.status, self.body = status, body


def _cid(v: str) -> str:
    if not CARD.match(v or ""):
        raise HTTPException(404, "Kart bulunamadı.")
    return v


def _rid(v: str) -> str:
    if not REF.match(v or ""):
        raise HTTPException(404, "Görsel bulunamadı.")
    return v


def _raise(r: httpx.Response) -> None:
    if 400 <= r.status_code < 500:
        try:
            body = r.json()
        except ValueError:
            body = {"detail": "İstek kabul edilmedi."}
        raise CardError(r.status_code, body)
    r.raise_for_status()


def request(method: str, job_id: str, sub: str, *, body: dict | None = None, editor: str | None = None,
            params: dict | None = None, content: bytes | None = None, mime: str | None = None,
            timeout: float = 120) -> object:
    base, headers, ca = editorial_studio._base()
    if editor is not None:
        headers["X-Editor"] = editor[:200]
    if mime:
        headers["Content-Type"] = mime
    url = f"{base}/v1/studio/jobs/{editorial_studio._job(job_id)}/character-cards{sub}"
    with editorial_studio._client(ca, timeout=timeout) as c:
        if content is not None:
            r = c.request(method, url, headers=headers, params=params, content=content)
        else:
            r = c.request(method, url, headers=headers, params=params, json=body)
    _raise(r)
    return r.json()


def ref_image(job_id: str, cid: str, rid: str, width: int) -> tuple[bytes, str]:
    return editorial_studio.get_bytes(
        f"/v1/studio/jobs/{editorial_studio._job(job_id)}/character-cards/cards/{_cid(cid)}/refs/{_rid(rid)}?w={width}",
        IMAGE_MIME)


# ------------------------------------------------------------------ yeniden deneme sayısı (yönetim ayarı)
_pushed: dict[str, Any] = {"value": None, "at": 0.0}
_push_lock = threading.Lock()


def retries() -> int:
    try:
        return max(0, int(admin_mod.conf(RETRIES_KEY) or 3))
    except ValueError:
        return 3


def push_retries(force: bool = False) -> bool:
    """Yönetim ayarını stüdyoya iletir. Aynı değer yakın zamanda iletildiyse tekrar gitmez (force hariç)."""
    n = retries()
    with _push_lock:
        if not force and _pushed["value"] == n and time.time() - _pushed["at"] < 600:
            return True
    base, headers, ca = editorial_studio._base()
    headers["X-Editor"] = "yonetim-ayari"
    try:
        with editorial_studio._client(ca, timeout=8) as c:
            r = c.put(f"{base}/v1/studio/character-settings", headers=headers, json={"max_retries": n})
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001 — stüdyo kapalıysa bir sonraki istekte yeniden denenir
        log.warning("karakter kartı ayarı stüdyoya iletilemedi: %s", e)
        return False
    with _push_lock:
        _pushed.update(value=n, at=time.time())
    return True


# ------------------------------------------------------------------ uçlar
def register(app, deps: dict[str, Any] | Any) -> None:
    """`deps["auth"]`: app.py'deki `_books(request)` — oturumu denetler, (engine, tenant, user, is_admin) döner."""
    auth: Callable[[Request], Any] = deps["auth"] if isinstance(deps, dict) else deps.auth
    P = "/api/v1/editorial/studio/jobs/{job}/character-cards"

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except CardError as e:
            return JSONResponse(status_code=e.status, content=e.body)
        except editorial_studio.StudioError as e:
            raise HTTPException(e.status if e.status in (400, 404, 409, 413) else 400, str(e)) from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        except Exception:  # noqa: BLE001 — ayrıntı günlükte; editöre teknik hata metni gösterilmez
            log.exception("studio character-cards call failed")
            raise HTTPException(502, "Stüdyo şu an yanıt vermiyor.") from None

    def write(request: Request, method: str, job: str, sub: str, what: str, obj: str, body: dict | None = None,
              params: dict | None = None, detail: Any = None, **kw):
        engine, _tenant, user, _ = auth(request)
        out = call(request_fn, method, job, sub, body=body, editor=user, params=params, **kw)
        if not isinstance(out, Response):
            admin_mod.audit(engine, user, {"POST": "create", "PUT": "update", "DELETE": "delete"}.get(method, "update"),
                            "studio_character", f"{job}/{obj}"[:120], what, detail)
        return out

    request_fn = request

    def obj(v: Any) -> dict:
        if not isinstance(v, dict):
            raise HTTPException(400, "Gövde bir nesne olmalı.")
        return v

    def rev(v: Any) -> int:
        try:
            return int(v)
        except (TypeError, ValueError):
            raise HTTPException(400, "Sürüm (rev) eksik.") from None

    @app.middleware("http")
    async def studio_character_settings_sync(request: Request, call_next):
        path, method = request.url.path, request.method
        if method == "POST" and GPU_START.match(path):
            await run_in_threadpool(push_retries)
        response = await call_next(request)
        if method == "PUT" and path == "/api/v1/admin/settings" and response.status_code == 200:
            await run_in_threadpool(push_retries, True)
        return response

    @app.get(P)
    def editorial_character_cards(job: str, request: Request):
        auth(request)
        push_retries()
        return call(request_fn, "GET", job, "")

    @app.put(P + "/series")
    def editorial_character_series(job: str, request: Request, body: dict[str, Any] | None = None):
        name = str(obj(body).get("name") or "").strip()
        return write(request, "PUT", job, "/series", f"dizi adı: {name or '(kurala dön)'}"[:300], "series",
                     body={"name": name}, detail={"name": name})

    @app.post(P + "/suggest")
    def editorial_character_suggest(job: str, request: Request, body: dict[str, Any] | None = None):
        names = [str(n) for n in (body or {}).get("names") or []]
        return write(request, "POST", job, "/suggest", "karakter kartı önerisi istendi", "suggest",
                     body={"names": names}, detail={"names": names})

    @app.post(P + "/check")
    def editorial_character_check(job: str, request: Request):
        return write(request, "POST", job, "/check", "karakter denetimi istendi", "check", body={})

    @app.post(P + "/cards")
    def editorial_character_create(job: str, request: Request, body: dict[str, Any] | None = None):
        b = obj(body)
        card = obj(b.get("card"))
        return write(request, "POST", job, "/cards", f"kart eklendi: {card.get('name')}"[:300], "cards",
                     body={"rev": rev(b.get("rev")), "card": card}, detail={"name": card.get("name")})

    @app.put(P + "/cards/{cid}")
    def editorial_character_update(job: str, cid: str, request: Request, body: dict[str, Any] | None = None):
        b = obj(body)
        card = obj(b.get("card"))
        return write(request, "PUT", job, f"/cards/{_cid(cid)}", f"kart düzenlendi: {card.get('name')}"[:300], cid,
                     body={"rev": rev(b.get("rev")), "card": card}, detail={"name": card.get("name")})

    @app.delete(P + "/cards/{cid}")
    def editorial_character_delete(job: str, cid: str, request: Request):
        r = request.query_params.get("rev")
        return write(request, "DELETE", job, f"/cards/{_cid(cid)}", "kart silindi", cid, params={"rev": rev(r)})

    @app.post(P + "/cards/{cid}/approve")
    def editorial_character_approve(job: str, cid: str, request: Request, body: dict[str, Any] | None = None):
        ok = bool((body or {}).get("ok", True))
        return write(request, "POST", job, f"/cards/{_cid(cid)}/approve",
                     "kart onaylandı" if ok else "kart onayı kaldırıldı", cid, body={"ok": ok}, detail={"ok": ok})

    @app.post(P + "/cards/{cid}/translate")
    def editorial_character_translate(job: str, cid: str, request: Request):
        return write(request, "POST", job, f"/cards/{_cid(cid)}/translate", "modele giden tarif yenilenmesi istendi",
                     cid, body={})

    @app.post(P + "/cards/{cid}/palette")
    def editorial_character_palette(job: str, cid: str, request: Request):
        return write(request, "POST", job, f"/cards/{_cid(cid)}/palette", "kart rengi kitap paletine yazıldı", cid,
                     body={})

    @app.put(P + "/cards/{cid}/refs")
    async def editorial_character_ref_upload(job: str, cid: str, request: Request, filename: str = ""):
        """Referans görsel ham gövdeyle gelir (Content-Type dosyanın türü). Sınır: fotoğraf yüklemesiyle aynı ayar."""
        engine, _tenant, user, _ = await run_in_threadpool(auth, request)
        try:
            mb = max(1, int(admin_mod.conf("STUDIO_UPLOAD_MB") or 60))
        except ValueError:
            mb = 60
        declared = request.headers.get("content-length") or ""
        if declared.isdigit() and int(declared) > mb * 1024 * 1024:
            raise HTTPException(413, f"Görsel en çok {mb} MB olabilir.")
        data = await request.body()
        if not data:
            raise HTTPException(400, "Dosya boş.")
        if len(data) > mb * 1024 * 1024:
            raise HTTPException(413, f"Görsel en çok {mb} MB olabilir.")
        mime = (request.headers.get("content-type") or "application/octet-stream").split(";")[0].strip().lower()
        if mime not in UPLOAD_MIME:
            raise HTTPException(400, "Yalnız JPEG, PNG, WebP ya da HEIC görsel yüklenebilir.")
        name = (filename or "gorsel").replace("\\", "/").rsplit("/", 1)[-1][:120]
        out = await run_in_threadpool(call, request_fn, "PUT", job, f"/cards/{_cid(cid)}/refs", editor=user,
                                      params={"filename": name}, content=data, mime=mime, timeout=300)
        if not isinstance(out, Response):
            admin_mod.audit(engine, user, "create", "studio_character", f"{job}/{cid}", "referans görsel yüklendi",
                            {"name": name, "bytes": len(data)})
        return out

    @app.post(P + "/cards/{cid}/refs")
    def editorial_character_ref_from(job: str, cid: str, request: Request, body: dict[str, Any] | None = None):
        b = obj(body)
        src = str(b.get("from") or "")
        if src not in ("sheet", "art"):
            raise HTTPException(400, "Kaynak geçersiz.")
        clean = {"from": src, "name": str(b.get("name") or "")[:80]}
        if src == "art":
            key = str(b.get("key") or "")
            if not editorial_studio.KEY.match(key):
                raise HTTPException(404, "Resim bulunamadı.")
            clean.update(key=key, v=rev(b.get("v")))
        return write(request, "POST", job, f"/cards/{_cid(cid)}/refs", "işten referans görsel alındı", cid,
                     body=clean, detail=clean)

    @app.post(P + "/cards/{cid}/refs/{rid}/primary")
    def editorial_character_ref_primary(job: str, cid: str, rid: str, request: Request):
        return write(request, "POST", job, f"/cards/{_cid(cid)}/refs/{_rid(rid)}/primary", "birincil referans seçildi",
                     cid, body={})

    @app.delete(P + "/cards/{cid}/refs/{rid}")
    def editorial_character_ref_remove(job: str, cid: str, rid: str, request: Request):
        return write(request, "DELETE", job, f"/cards/{_cid(cid)}/refs/{_rid(rid)}", "referans görsel kaldırıldı", cid)

    @app.get(P + "/cards/{cid}/refs/{rid}")
    def editorial_character_ref_image(job: str, cid: str, rid: str, request: Request, w: int = 320):
        auth(request)
        out = call(ref_image, job, cid, rid, max(0, min(int(w), 2048)))
        if isinstance(out, Response):
            return out
        data, mime = out
        return Response(content=data, media_type=mime, headers={"Cache-Control": "private, max-age=300"})

    @app.get(P + "/history")
    def editorial_character_history(job: str, request: Request):
        auth(request)
        return call(request_fn, "GET", job, "/history")
