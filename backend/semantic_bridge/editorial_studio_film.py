"""Kitap Tasarım Stüdyosu — kitaptan film, çizgi film ve sosyal medya kısa videosu köprü uçları. Stüdyo servisindeki
`/v1/studio/jobs/{job}/films…` uçlarının vekili (apps/editor/src/editor/production/api_film.py); üretim stüdyo
servisinde ve GPU'da yürür, köprü yalnız aracılık eder. Sözleşme: apps/editor/docs/analiz/film-ve-sosyal-medya-hatti.md.

Oturum zorunlu (`_books`); yazanlarda `X-Editor` oturumdaki AD hesabıdır ve `admin.audit` kaydı düşer. Medya ucu
(kare, çekim, replik sesi, kurgu) akış olarak geçer ve tarayıcının ileri sarma isteğini (Range) servise iletir: film
dosyası köprü belleğine alınmaz. Paylaşım paketinin indirilmesi `veri.disa-aktar` ister (öbür stüdyo indirmeleri gibi);
servis ayrıca onaysız paketi vermez. Hiçbir uç dışarıya (sosyal medya) gönderim yapmaz.

app.py'de iki satırla bağlanır:
    from semantic_bridge import editorial_studio_film
    editorial_studio_film.register(app, {"auth": _books, "audit": admin_mod.audit, "can": _can})
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from semantic_bridge import editorial_studio as es

log = logging.getLogger(__name__)

FILM_ID = re.compile(r"^f_[0-9a-f]{8}$")
SHOT_ID = re.compile(r"^s[0-9]{2}c[0-9]{2}$")
STAGES = {"senaryo", "oyuncular", "ses", "kareler", "cekim", "kurgu", "paylasim"}
MEDIA = re.compile(r"^(?:kare|cekim|ses|cikti(?:/paylasim)?)/[A-Za-z0-9._-]{1,80}\.(?:png|jpg|mp4|wav|srt)$")
MEDIA_MIME = {"image/png", "image/jpeg", "video/mp4", "audio/wav", "audio/x-wav", "application/x-subrip"}
EXPORT_KEY = "ozellik:veri.disa-aktar"
PASS_HEADERS = ("content-type", "content-length", "content-range", "accept-ranges", "content-disposition",
                "last-modified", "etag")


def _fid(fid: str) -> str:
    if not FILM_ID.match(fid or ""):
        raise ValueError("Film bulunamadı.")
    return fid


def _path(job: str, sub: str = "") -> str:
    return f"/v1/studio/jobs/{es._job(job)}/films{sub}"


def request(method: str, job: str, sub: str = "", *, body: dict | None = None, editor: str | None = None,
            timeout: float = 120) -> Any:
    base, headers, ca = es._base()
    if editor is not None:
        headers["X-Editor"] = editor[:200]
    with es._client(ca, timeout=timeout) as c:
        r = c.request(method, base + _path(job, sub), headers=headers, json=body)
    es._raise(r)
    return r.json()


def register(app, deps: dict[str, Any]) -> None:
    auth: Callable[[Request], Any] = deps["auth"]
    audit_fn = deps.get("audit")
    can: Callable[[str, str], bool] = deps.get("can") or (lambda _user, _key: False)

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except es.StudioError as e:
            raise HTTPException(e.status if e.status in (400, 404, 409, 413, 422) else 400, str(e)) from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        except HTTPException:
            raise
        except Exception:  # noqa: BLE001 — ayrıntı günlükte; editöre teknik hata metni gösterilmez
            log.exception("studio film call failed")
            raise HTTPException(502, "Stüdyo şu an yanıt vermiyor.") from None

    def write(req: Request, method: str, job: str, sub: str, what: str, title: str, body: dict | None = None):
        engine, _tenant, user, _ = auth(req)
        out = call(request, method, job, sub, body=body, editor=user)
        if audit_fn is not None:
            audit_fn(engine, user, {"POST": "create", "PUT": "update"}.get(method, "update"), "studio_film",
                     f"{job}/{what}"[:120], title, None)
        return out

    def body_of(v: Any) -> dict:
        if not isinstance(v, dict):
            raise HTTPException(400, "Gövde bir nesne olmalı.")
        return v

    P = "/api/v1/editorial/studio/jobs/{job}/films"
    request_fn = request           # uçların `request` parametresi modül işlevini gölgeler

    @app.get(P)
    def film_list(job: str, request: Request):
        auth(request)
        return JSONResponse(call(request_fn, "GET", job), headers={"Cache-Control": "no-store"})

    @app.post(P)
    def film_new(job: str, request: Request, body: dict[str, Any] | None = None):
        b = body_of(body)
        keep = {k: b.get(k) for k in ("format", "style", "title") if b.get(k) is not None}
        return write(request, "POST", job, "", "film", "film açıldı", keep)

    @app.get(P + "/{fid}")
    def film_view(job: str, fid: str, request: Request):
        auth(request)
        return JSONResponse(call(request_fn, "GET", job, f"/{call(_fid, fid)}"), headers={"Cache-Control": "no-store"})

    @app.post(P + "/{fid}/stages/{stage}")
    def film_stage(job: str, fid: str, stage: str, request: Request, body: dict[str, Any] | None = None):
        if stage not in STAGES:
            raise HTTPException(404, "Adım yok.")
        b = body_of(body or {})
        keep: dict[str, Any] = {}
        if isinstance(b.get("only"), list):
            keep["only"] = [s for s in b["only"] if isinstance(s, str) and SHOT_ID.match(s)][:200]
        if isinstance(b.get("direction"), str):
            keep["direction"] = b["direction"][:600]
        if isinstance(b.get("platforms"), list):
            keep["platforms"] = [p for p in b["platforms"] if isinstance(p, str)][:10]
        return write(request, "POST", job, f"/{call(_fid, fid)}/stages/{stage}", f"{fid}/{stage}",
                     f"film adımı başlatıldı: {stage}", keep)

    @app.put(P + "/{fid}/script")
    def film_script(job: str, fid: str, request: Request, body: dict[str, Any] | None = None):
        b = body_of(body)
        return write(request, "PUT", job, f"/{call(_fid, fid)}/script", f"{fid}/senaryo", "senaryo düzeltildi",
                     {"script": body_of(b.get("script")), "rev": int(b.get("rev") or 0)})

    @app.put(P + "/{fid}/cast/voice")
    def film_voice(job: str, fid: str, request: Request, body: dict[str, Any] | None = None):
        b = body_of(body)
        return write(request, "PUT", job, f"/{call(_fid, fid)}/cast/voice", f"{fid}/oyuncular", "oyuncu sesi değişti",
                     {"name": str(b.get("name") or "")[:120], "voice": str(b.get("voice") or "")[:60],
                      "rev": int(b.get("rev") or 0)})

    @app.post(P + "/{fid}/frames/{shot}/select")
    def film_frame_select(job: str, fid: str, shot: str, request: Request, body: dict[str, Any] | None = None):
        if not SHOT_ID.match(shot or ""):
            raise HTTPException(404, "Çekim yok.")
        v = int(body_of(body).get("v") or 0)
        return write(request, "POST", job, f"/{call(_fid, fid)}/frames/{shot}/select", f"{fid}/{shot}",
                     "ilk kare seçildi", {"v": v})

    @app.post(P + "/{fid}/approve/{stage}")
    def film_approve(job: str, fid: str, stage: str, request: Request, body: dict[str, Any] | None = None):
        if stage not in STAGES:
            raise HTTPException(404, "Adım yok.")
        ok = bool(body_of(body or {"ok": True}).get("ok", True))
        return write(request, "POST", job, f"/{call(_fid, fid)}/approve/{stage}", f"{fid}/{stage}",
                     f"film adımı {'onaylandı' if ok else 'onayı geri alındı'}: {stage}", {"ok": ok})

    @app.put(P + "/{fid}/share/text")
    def film_share_text(job: str, fid: str, request: Request, body: dict[str, Any] | None = None):
        b = body_of(body)
        tags = [str(t)[:60] for t in b.get("hashtags") or [] if isinstance(t, str)][:10]
        return write(request, "PUT", job, f"/{call(_fid, fid)}/share/text", f"{fid}/paylasim",
                     "paylaşım metni düzeltildi",
                     {"caption": str(b.get("caption") or "")[:2200], "hashtags": tags,
                      "hook": str(b.get("hook") or "")[:80]})

    @app.get(P + "/{fid}/media/{path:path}")
    def film_media(job: str, fid: str, path: str, request: Request, download: bool = False):
        _engine, _tenant, user, _ = auth(request)
        if not MEDIA.match(path or ""):
            raise HTTPException(404, "Dosya bulunamadı.")
        if download and not can(user, EXPORT_KEY):
            raise HTTPException(403, {"code": "FORBIDDEN", "message": "Bu işlem rolünüzde yok."})
        base, headers, ca = es._base()
        if request.headers.get("range"):
            headers["Range"] = request.headers["range"][:100]
        url = base + _path(job, f"/{call(_fid, fid)}/media/{path}")
        client = es._fresh(ca)
        try:
            r = client.send(client.build_request("GET", url, headers=headers,
                                                 params={"download": "true"} if download else None), stream=True)
        except Exception:  # noqa: BLE001
            client.close()
            log.exception("studio film media failed")
            raise HTTPException(502, "Stüdyo şu an yanıt vermiyor.") from None
        if r.status_code >= 400:
            r.read()
            r.close()
            client.close()
            call(es._raise, r)
        mime = r.headers.get("content-type", "").split(";")[0]
        if mime not in MEDIA_MIME:
            r.close()
            client.close()
            raise HTTPException(404, "Dosya bulunamadı.")

        def body():
            try:
                yield from r.iter_bytes(1 << 20)
            finally:
                r.close()
                client.close()
        out = {k: r.headers[k] for k in PASS_HEADERS if k in r.headers}
        out["Cache-Control"] = "private, max-age=600" if not download else "private, no-store"
        return StreamingResponse(body(), status_code=r.status_code, headers=out, media_type=mime)
