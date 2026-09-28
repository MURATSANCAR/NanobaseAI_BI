"""Kitap Tasarım Stüdyosu — sesli okumaya efekt sesleri, köprü uçları.

Stüdyo servisindeki `/v1/studio/jobs/{job}/sfx…` ve `/v1/studio/sfx/library…` uçlarının birebir vekili
(apps/editor/src/editor/production/api_sfx.py). Oturum zorunlu (stüdyonun öteki uçlarıyla aynı `_books` denetimi);
yazanlarda X-Editor oturumdaki AD hesabıdır ve denetim kaydı düşer. Servisin kodlu gövdesi ({"code": "NO_PLAN" |
"PREPARING" | "NO_LIBRARY" | "BUSY" | "NO_AUDIO" | "NOTHING", "detail"}) olduğu gibi ekrana gider.

Ses dosyaları (efektli sayfa sesi, kütüphane önizlemesi) köprüde `Range` ile verilir (iOS Safari ve ileri/geri sarma).
Kaynaklar ve lisanslar: docs/analiz/efekt-sesleri-kaynaklar.md.

app.py'de `_books` tanımından sonra (sesli okuma bloğunun yanında) iki satırla bağlanır:
    from semantic_bridge import editorial_studio_sfx
    editorial_studio_sfx.register(app, {"auth": _books, "audit": admin_mod.audit})
"""
from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Any, Callable

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response

from semantic_bridge import editorial_studio
from semantic_bridge.editorial_studio_narration import AUDIO_MAX, ranged

log = logging.getLogger(__name__)

SID = re.compile(r"^[0-9a-f]{16}$")
CAT = re.compile(r"^[a-z_]{1,40}$")
TEXT_MAX = 200


def _call(method: str, path: str, *, body: dict | None = None, editor: str | None = None, timeout: float = 120,
          raw: bool = False):
    base, headers, ca = editorial_studio._base()
    if editor is not None:
        headers["X-Editor"] = editor[:200]
    with editorial_studio._client(ca, timeout=timeout) as c:
        r = c.request(method, base + path, headers=headers, json=body)
    if 400 <= r.status_code < 500 or r.status_code == 503:
        try:
            payload = r.json()
        except ValueError:
            payload = {"detail": "İstek kabul edilmedi."}
        raise editorial_studio.PlanError(r.status_code, payload)
    r.raise_for_status()
    if raw:
        if r.headers.get("content-type", "").split(";")[0] != "audio/mpeg":
            raise editorial_studio.StudioError(404, "Ses bulunamadı.")
        if len(r.content) > AUDIO_MAX:
            raise editorial_studio.StudioError(413, "Ses dosyası çok büyük.")
        return r.content
    return r.json()


def _jobp(job: str, sub: str = "") -> str:
    return f"/v1/studio/jobs/{editorial_studio._job(job)}/sfx{sub}"


def register(app, deps: dict[str, Any] | Any) -> None:
    """`deps["auth"]`: app.py'deki `_books(request)` → (engine, tenant, user, is_admin); `deps["audit"]`:
    `admin_mod.audit(engine, user, action, kind, id, what, detail)`."""
    auth: Callable[[Request], Any] = deps["auth"] if isinstance(deps, dict) else deps.auth
    audit: Callable[..., Any] | None = deps.get("audit") if isinstance(deps, dict) else getattr(deps, "audit", None)

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except editorial_studio.PlanError as e:
            return JSONResponse(status_code=e.status, content=e.body)
        except editorial_studio.StudioError as e:
            raise HTTPException(e.status if e.status in (400, 404, 409, 413) else 400, str(e)) from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        except httpx.TimeoutException:
            raise HTTPException(504, "Stüdyo zamanında yanıt vermedi.") from None
        except Exception:  # noqa: BLE001 — ayrıntı günlükte; editöre teknik hata metni gösterilmez
            log.exception("studio sfx call failed")
            raise HTTPException(502, "Stüdyo şu an yanıt vermiyor.") from None

    def write(request: Request, method: str, path: str, what: str, body: dict, timeout: float = 120):
        engine, _tenant, user, _ = auth(request)
        out = call(_call, method, path, body=body, editor=user, timeout=timeout)
        if audit is not None and not isinstance(out, Response):
            try:
                audit(engine, user, "create" if method == "POST" else "update", "studio_sfx", path[-120:], what,
                      body if len(str(body)) < 4000 else None)
            except Exception:  # noqa: BLE001 — denetim kaydı düşmezse işlem geri alınmaz, günlüğe yazılır
                log.exception("studio sfx audit failed")
        return out

    def obj(body: Any) -> dict:
        if not isinstance(body, dict):
            raise HTTPException(400, "Gövde bir nesne olmalı.")
        return body

    def pid(v: str) -> str:
        if not editorial_studio.PLAN_ID.match(v or ""):
            raise HTTPException(404, "Sayfa bulunamadı.")
        return v

    def pages(v: Any) -> list[str] | None:
        return [pid(str(p)) for p in v] if isinstance(v, list) else None

    def sid(v: Any) -> str | None:
        if v in (None, ""):
            return None
        if not SID.match(str(v)):
            raise HTTPException(400, "Geçersiz efekt.")
        return str(v)

    def text(v: Any, n: int = TEXT_MAX) -> str:
        return str(v or "")[:n]

    def gain(v: Any) -> float:
        try:
            return max(-18.0, min(12.0, float(v or 0)))
        except (TypeError, ValueError):
            raise HTTPException(400, "Ses düzeyi sayı olmalı.") from None

    def cue(c: Any) -> dict:
        if not isinstance(c, dict):
            raise HTTPException(400, "Efekt kaydı nesne olmalı.")
        words = c.get("words")
        if words is not None and not (isinstance(words, list) and len(words) == 2 and all(isinstance(x, int) for x in words)):
            raise HTTPException(400, "Kelime aralığı [ilk, son] olmalı.")
        return {"id": text(c.get("id"), 16) or None, "kind": "ortam" if c.get("kind") == "ortam" else "anlik",
                "type": text(c.get("type"), 12) or None, "block": text(c.get("block"), 64) or None, "words": words,
                "quote": text(c.get("quote")), "query": text(c.get("query")), "query_en": text(c.get("query_en")),
                "category": text(c.get("category"), 40) or None,
                "candidates": [x for x in (sid(v) for v in (c.get("candidates") or [])[:20]) if x],
                "chosen": sid(c.get("chosen")), "gain_db": gain(c.get("gain_db")),
                "place": "ardindan" if c.get("place") == "ardindan" else "birlikte",
                "source": "zeki" if c.get("source") == "zeki" else "editor",
                "confidence": c.get("confidence") if isinstance(c.get("confidence"), (int, float)) else None}

    def ambience(a: Any) -> dict | None:
        if not isinstance(a, dict):
            return None
        return {"query": text(a.get("query")), "query_en": text(a.get("query_en")),
                "category": text(a.get("category"), 40) or None,
                "candidates": [x for x in (sid(v) for v in (a.get("candidates") or [])[:20]) if x],
                "chosen": sid(a.get("chosen")), "gain_db": gain(a.get("gain_db")),
                "quote": text(a.get("quote")) or None, "block": text(a.get("block"), 64) or None,
                "source": "zeki" if a.get("source") == "zeki" else "editor",
                "scope": "bolum" if a.get("scope") == "bolum" else "sayfa"}

    # ---------------------------------------------------------------- kitap
    @app.get("/api/v1/editorial/studio/jobs/{job}/sfx")
    def editorial_sfx(job: str, request: Request):
        auth(request)
        return call(_call, "GET", _jobp(job), timeout=60)

    @app.put("/api/v1/editorial/studio/jobs/{job}/sfx/settings")
    def editorial_sfx_settings(job: str, request: Request, body: dict[str, Any] | None = None):
        on = obj(body).get("enabled")
        if not isinstance(on, bool):
            raise HTTPException(400, "enabled true/false olmalı.")
        return write(request, "PUT", _jobp(job, "/settings"), "efekt sesleri " + ("açıldı" if on else "kapatıldı"),
                     {"enabled": on})

    @app.post("/api/v1/editorial/studio/jobs/{job}/sfx/suggest")
    def editorial_sfx_suggest(job: str, request: Request, body: dict[str, Any] | None = None):
        b = obj(body or {})
        return write(request, "POST", _jobp(job, "/suggest"), "efekt önerisi başlatıldı",
                     {"pages": pages(b.get("pages")), "force": bool(b.get("force"))})

    @app.post("/api/v1/editorial/studio/jobs/{job}/sfx/mix")
    def editorial_sfx_mix(job: str, request: Request, body: dict[str, Any] | None = None):
        b = obj(body or {})
        return write(request, "POST", _jobp(job, "/mix"), "efektli sesler yeniden karıştırılıyor",
                     {"pages": pages(b.get("pages"))})

    @app.get("/api/v1/editorial/studio/jobs/{job}/sfx/pages/{page}")
    def editorial_sfx_page(job: str, page: str, request: Request):
        auth(request)
        return call(_call, "GET", _jobp(job, f"/pages/{pid(page)}"), timeout=60)

    @app.put("/api/v1/editorial/studio/jobs/{job}/sfx/pages/{page}")
    def editorial_sfx_page_save(job: str, page: str, request: Request, body: dict[str, Any] | None = None):
        b = obj(body)
        clean = {"cues": [cue(c) for c in (b.get("cues") or [])], "ambience": ambience(b.get("ambience"))}
        return write(request, "PUT", _jobp(job, f"/pages/{pid(page)}"), "sayfa efektleri", clean)

    @app.post("/api/v1/editorial/studio/jobs/{job}/sfx/pages/{page}/mix")
    def editorial_sfx_page_mix(job: str, page: str, request: Request):
        return write(request, "POST", _jobp(job, f"/pages/{pid(page)}/mix"), "sayfa efektli sesi karıştırıldı", {},
                     timeout=300)

    @app.get("/api/v1/editorial/studio/jobs/{job}/sfx/pages/{page}/audio")
    def editorial_sfx_page_audio(job: str, page: str, request: Request):
        auth(request)
        out = call(_call, "GET", _jobp(job, f"/pages/{pid(page)}/audio"), raw=True)
        if isinstance(out, Response):
            return out
        return ranged(out, request.headers.get("range"), {"Cache-Control": "private, max-age=60"})

    @app.get("/api/v1/editorial/studio/jobs/{job}/sfx/credits")
    def editorial_sfx_credits(job: str, request: Request):
        auth(request)
        return call(_call, "GET", _jobp(job, "/credits"), timeout=60)

    # ---------------------------------------------------------------- havuz
    LIB = "/v1/studio/sfx/library"

    @app.get("/api/v1/editorial/studio/sfx/library")
    def editorial_sfx_library(request: Request, q: str = "", en: str = "", category: str = "", kind: str = "",
                              k: int = 24):
        auth(request)
        if category and not CAT.match(category):
            raise HTTPException(400, "Bilinmeyen kategori.")
        qs = urllib.parse.urlencode({"q": text(q), "en": text(en), "category": category,
                                     "kind": kind if kind in ("anlik", "ortam") else "", "k": max(1, min(200, int(k)))})
        return call(_call, "GET", f"{LIB}?{qs}", timeout=90)

    @app.get("/api/v1/editorial/studio/sfx/library/categories")
    def editorial_sfx_categories(request: Request):
        auth(request)
        return call(_call, "GET", f"{LIB}/categories", timeout=60)

    @app.get("/api/v1/editorial/studio/sfx/library/browse")
    def editorial_sfx_browse(request: Request, category: str, offset: int = 0, k: int = 30):
        auth(request)
        if not CAT.match(category or ""):
            raise HTTPException(400, "Bilinmeyen kategori.")
        qs = urllib.parse.urlencode({"category": category, "offset": max(0, int(offset)), "k": max(1, min(200, int(k)))})
        return call(_call, "GET", f"{LIB}/browse?{qs}", timeout=60)

    @app.get("/api/v1/editorial/studio/sfx/library/{sid_}/preview")
    def editorial_sfx_preview(sid_: str, request: Request):
        auth(request)
        if not SID.match(sid_ or ""):
            raise HTTPException(404, "Efekt bulunamadı.")
        out = call(_call, "GET", f"{LIB}/{sid_}/preview", raw=True, timeout=120)
        if isinstance(out, Response):
            return out
        return ranged(out, request.headers.get("range"), {"Cache-Control": "private, max-age=86400"})

    @app.get("/api/v1/editorial/studio/sfx/library/{sid_}")
    def editorial_sfx_item(sid_: str, request: Request):
        auth(request)
        if not SID.match(sid_ or ""):
            raise HTTPException(404, "Efekt bulunamadı.")
        return call(_call, "GET", f"{LIB}/{sid_}", timeout=30)
