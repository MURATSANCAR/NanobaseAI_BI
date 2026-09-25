"""Kitap Tasarım Stüdyosu — yaş uygunluğu raporu için köprü uçları.

Stüdyo servisindeki `/v1/studio/jobs/{job}/age…` uçlarının birebir vekili (apps/editor/src/editor/production/api_age.py).
Oturum zorunlu (stüdyonun öteki uçlarıyla aynı `_books` denetimi); yazanlarda X-Editor = oturumdaki AD hesabı ve
denetim kaydı (`admin.audit`). Servisin 4xx gövdesi ({"code": "BUSY"}, {"code": "NO_PLAN"}, {"detail": …}) olduğu gibi
geçer; ekran kodu okur.

app.py'de `_books` tanımından sonra iki satırla bağlanır:
    from semantic_bridge import editorial_studio_age
    editorial_studio_age.register(app, {"auth": _books, "audit": admin_mod.audit})
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response

from semantic_bridge import editorial_studio

log = logging.getLogger(__name__)

KINDS = {"finding", "word", "check"}
ITEM = re.compile(r"^[\w'’ -]{1,80}$")
STATES = {None, "dismissed", "fix", "approved", "rejected", "ok", "not_ok"}


def _call(method: str, job: str, sub: str, *, body: dict | None = None, editor: str | None = None,
          timeout: float = 120) -> Any:
    """`/v1/studio/jobs/{iş}/age{sub}`; 4xx gövdesi PlanError ile olduğu gibi döner."""
    base, headers, ca = editorial_studio._base()
    if editor is not None:
        headers["X-Editor"] = editor[:200]
    url = f"{base}/v1/studio/jobs/{editorial_studio._job(job)}/age{sub}"
    with editorial_studio._client(ca, timeout=timeout) as c:
        r = c.request(method, url, headers=headers, json=body)
    editorial_studio._plan_raise(r)
    return r.json()


def view(job: str) -> Any:
    return _call("GET", job, "", timeout=60)


def run(job: str, editor: str) -> Any:
    return _call("POST", job, "/run", body={}, editor=editor, timeout=60)


def decide(job: str, body: dict, editor: str) -> Any:
    kind, item, state = body.get("kind"), str(body.get("id") or ""), body.get("state")
    if kind not in KINDS or not ITEM.match(item) or state not in STATES:
        raise editorial_studio.StudioError(400, "Karar geçersiz.")
    choice = body.get("choice")
    clean = {"kind": kind, "id": item, "state": state, "note": str(body.get("note") or "")[:500]}
    if isinstance(choice, dict):
        clean["choice"] = {str(k)[:80]: str(v)[:80] for k, v in list(choice.items())}
    return _call("POST", job, "/decisions", body=clean, editor=editor, timeout=60)


def apply(job: str, body: dict, editor: str) -> Any:
    clean = {k: str(body.get(k) or "").strip()[:80] for k in ("lemma", "form", "to")}
    if not all(clean.values()):
        raise editorial_studio.StudioError(400, "Kök, biçim ve karşılık gerekli.")
    # metin değişir, bütün kitap yeniden dizilir: süre uzun
    return _call("POST", job, "/words/apply", body=clean, editor=editor, timeout=300)


def pdf(job: str) -> tuple[bytes, str]:
    return editorial_studio.get_bytes(f"/v1/studio/jobs/{editorial_studio._job(job)}/age/pdf", {"application/pdf"},
                                      limit=100 * 1024 * 1024)


def register(app, deps: dict[str, Any] | Any) -> None:
    """`deps["auth"]`: app.py'deki `_books(request)` → (engine, tenant, user, is_admin); `deps["audit"]`: admin.audit."""
    auth: Callable[[Request], Any] = deps["auth"] if isinstance(deps, dict) else deps.auth
    audit: Callable[..., None] = (deps.get("audit") if isinstance(deps, dict) else getattr(deps, "audit", None)) \
        or (lambda *a, **k: None)

    def call(fn, *a):
        try:
            return fn(*a)
        except editorial_studio.PlanError as e:
            return JSONResponse(status_code=e.status, content=e.body)
        except editorial_studio.StudioError as e:
            raise HTTPException(e.status if e.status in (400, 404, 409, 413) else 400, str(e)) from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        except Exception:  # noqa: BLE001 — ayrıntı günlükte; editöre teknik hata metni gösterilmez
            log.exception("studio age call failed")
            raise HTTPException(502, "Stüdyo şu an yanıt vermiyor.") from None

    def write(request: Request, job: str, what: str, fn, *a, detail: Any = None):
        engine, _tenant, user, _ = auth(request)
        out = call(fn, job, *a, user)
        if not isinstance(out, Response):
            audit(engine, user, "update", "studio_age", f"{job}"[:120], what, detail)
        return out

    @app.get("/api/v1/editorial/studio/jobs/{job}/age")
    def editorial_studio_age_view(job: str, request: Request):
        auth(request)
        return call(view, job)

    @app.post("/api/v1/editorial/studio/jobs/{job}/age/run")
    def editorial_studio_age_run(job: str, request: Request):
        return write(request, job, "yaş uygunluğu raporu çıkarıldı", run)

    @app.post("/api/v1/editorial/studio/jobs/{job}/age/decisions")
    def editorial_studio_age_decide(job: str, request: Request, body: dict[str, Any] | None = None):
        b = body if isinstance(body, dict) else {}
        return write(request, job, f"yaş raporu kararı: {b.get('kind')} {b.get('id')} → {b.get('state')}", decide, b,
                     detail={k: b.get(k) for k in ("kind", "id", "state", "note", "choice")})

    @app.post("/api/v1/editorial/studio/jobs/{job}/age/words/apply")
    def editorial_studio_age_apply(job: str, request: Request, body: dict[str, Any] | None = None):
        b = body if isinstance(body, dict) else {}
        return write(request, job, f"yaş raporu: «{b.get('form')}» → «{b.get('to')}»", apply, b,
                     detail={k: b.get(k) for k in ("lemma", "form", "to")})

    @app.get("/api/v1/editorial/studio/jobs/{job}/age/pdf")
    def editorial_studio_age_pdf(job: str, request: Request):
        engine, _tenant, user, _ = auth(request)
        data, _mime = call(pdf, job)
        audit(engine, user, "export", "studio_age_pdf", job, "yaş uygunluğu raporu", None)
        return Response(content=data, media_type="application/pdf", headers={
            "Content-Disposition": f'attachment; filename="{job}-yas-uygunlugu.pdf"', "Cache-Control": "private, no-store"})
