"""Kitap Tasarım Stüdyosu — boyama / etkinlik kitabı uçlarının köprüsü (servis: apps/editor/.../api_coloring.py).

Servisteki `/v1/studio/jobs/{job}/coloring…` uçlarının birebir vekili. Oturum zorunlu (stüdyonun öteki uçlarıyla aynı
`_books` denetimi); yazanlarda `X-Editor` oturumdaki AD hesabıdır ve `admin_mod.audit` kaydı düşer. Servisin 4xx
gövdesi ({"code": "BUSY"} vb.) olduğu gibi döner.

app.py'de `_books` tanımından sonra iki satırla bağlanır:
    from semantic_bridge import editorial_studio_coloring
    editorial_studio_coloring.register(app, {"auth": _books, "audit": admin_mod.audit})
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response

from semantic_bridge import editorial_studio

log = logging.getLogger(__name__)

ART_ID = re.compile(r"^a_[0-9a-f]{8}$")
KINDS = {"paint_by_number", "dot_to_dot", "spot_difference", "maze", "word_search", "matching"}
MODES = {"coloring", "coloring_activities"}


def _path(job: str, sub: str = "") -> str:
    return f"/v1/studio/jobs/{editorial_studio._job(job)}/coloring{sub}"


def _request(method: str, job: str, sub: str = "", body: dict | None = None, editor: str | None = None,
             timeout: float = 120) -> object:
    base, headers, ca = editorial_studio._base()
    if editor is not None:
        headers["X-Editor"] = editor[:200]
    with editorial_studio._client(ca, timeout=timeout) as c:
        r = c.request(method, base + _path(job, sub), headers=headers, json=body)
    editorial_studio._plan_raise(r)
    return r.json()


def clean_new(body: dict) -> dict:
    mode = str(body.get("mode") or "")
    if mode not in MODES:
        raise editorial_studio.StudioError(400, "Seçim: yalnız boyama ya da boyama + etkinlik.")
    acts = []
    for a in body.get("activities") or []:
        if not isinstance(a, dict) or a.get("kind") not in KINDS:
            raise editorial_studio.StudioError(400, "Etkinlik türü geçersiz.")
        o: dict[str, Any] = {"kind": a["kind"]}
        if a.get("count") is not None:
            o["count"] = max(1, min(int(a["count"]), 99))
        if a.get("source"):
            o["source"] = editorial_studio.plan_id(str(a["source"]))
        acts.append(o)
    return {"mode": mode, "activities": acts, "captions": "rule" if body.get("captions") == "rule" else "model"}


def clean_sentences(body: dict) -> dict:
    items = []
    for it in body.get("items") or []:
        if not isinstance(it, dict) or not ART_ID.match(str(it.get("aid") or "")):
            raise editorial_studio.StudioError(400, "Cümle bulunamadı.")
        o: dict[str, Any] = {"aid": it["aid"]}
        if it.get("text") is not None:
            o["text"] = str(it["text"])[:400]
        if it.get("approved") is not None:
            o["approved"] = bool(it["approved"])
        items.append(o)
    return {"items": items}


def register(app, deps: dict[str, Any]) -> None:
    """`deps["auth"]`: app.py'deki `_books(request)` → (engine, tenant, user, is_admin); `deps["audit"]`:
    `admin_mod.audit(engine, user, action, kind, obj, what, detail)`."""
    auth: Callable[[Request], Any] = deps["auth"]
    audit: Callable[..., Any] = deps["audit"]

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except editorial_studio.PlanError as e:
            return JSONResponse(status_code=e.status, content=e.body)
        except editorial_studio.StudioError as e:
            raise HTTPException(e.status if e.status in (400, 404, 409, 413) else 400, str(e)) from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        except Exception:  # noqa: BLE001 — ayrıntı günlükte; editöre teknik hata metni gösterilmez
            log.exception("studio coloring call failed")
            raise HTTPException(502, "Stüdyo şu an yanıt vermiyor.") from None

    def write(request: Request, job: str, sub: str, body: dict, what: str):
        engine, _tenant, user, _ = auth(request)
        out = call(_request, "POST", job, sub, body, user, 600)
        if not isinstance(out, Response):
            audit(engine, user, "create" if sub in ("", "/retry") or sub.endswith("/redraw") else "update",
                  "studio_coloring", f"{job}{sub}"[:120], what, None)
        return out

    @app.get("/api/v1/editorial/studio/jobs/{job}/coloring")
    def editorial_studio_coloring_get(job: str, request: Request):
        auth(request)
        return call(_request, "GET", job)

    @app.post("/api/v1/editorial/studio/jobs/{job}/coloring")
    def editorial_studio_coloring_new(job: str, request: Request, body: dict[str, Any] | None = None):
        clean = call(clean_new, body or {})
        return write(request, job, "", clean, f"boyama kitabı ({clean['mode']})")

    @app.post("/api/v1/editorial/studio/jobs/{job}/coloring/retry")
    def editorial_studio_coloring_retry(job: str, request: Request):
        return write(request, job, "/retry", {}, "boyama kitabı yeniden")

    @app.post("/api/v1/editorial/studio/jobs/{job}/coloring/sentences")
    def editorial_studio_coloring_sentences(job: str, request: Request, body: dict[str, Any] | None = None):
        return write(request, job, "/sentences", call(clean_sentences, body or {}), "kısa cümle")

    @app.post("/api/v1/editorial/studio/jobs/{job}/coloring/art/{aid}/redraw")
    def editorial_studio_coloring_redraw(job: str, aid: str, request: Request):
        if not ART_ID.match(aid or ""):
            raise HTTPException(404, "Çizgi bulunamadı.")
        return write(request, job, f"/art/{aid}/redraw", {}, "çizgiyi yeniden çiz")
