"""Kitap Tasarım Stüdyosu — okur araçları (çocuk gözüyle okuma, sayfa çevirme merakı) ve sürüm farkı köprü uçları.

Stüdyo servisindeki `/v1/studio/jobs/{iş}/plan/reader…` ve `/plan/versions…` uçlarının vekili (servis:
apps/editor/src/editor/production/api_reader.py). Oturum zorunlu; yazanlarda X-Editor oturumdaki AD hesabıdır ve
denetim kaydı düşer. Servisin 4xx gövdesi ({"code": "BUSY"} …) olduğu gibi döner.

Okuma sayısı yönetim ayarıdır (`STUDIO_READER_PASSES`, grup «studio»): istemcinin gönderdiği değer değil, ayar
servise gider; ekrana da `GET …/plan/reader` ile yazılır.

app.py'de `_books` tanımından sonra (stüdyo bloğunun yanında) iki satırla bağlanır:
    from semantic_bridge import editorial_studio_reader
    editorial_studio_reader.register(app, {"auth": _books, "audit": admin_mod.audit, "conf": admin_mod.conf})
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response

from semantic_bridge import editorial_studio as es

log = logging.getLogger(__name__)

RUN = re.compile(r"^r_[0-9a-f]{8}$")
FLAG = re.compile(r"^[kt]_[0-9a-f]{10}$")
VSPEC = re.compile(r"^[0-9]{14}[0-9a-f]{6}:(?:current|[0-9]{1,6})$")
DECISIONS = {"applied", "dismissed", "accepted", "rejected", "open"}
DEFAULT_PASSES = 3


def passes(conf: Callable[[str], str] | None) -> int:
    """Sayfa başına bağımsız okuma sayısı (yönetim ayarı). Geçersizse varsayılan."""
    try:
        return max(1, int((conf("STUDIO_READER_PASSES") if conf else "") or DEFAULT_PASSES))
    except (TypeError, ValueError):
        return DEFAULT_PASSES


def _run(v: str) -> str:
    if not RUN.match(v or ""):
        raise es.StudioError(404, "Okuma bulunamadı.")
    return v


def _vspec(v: str) -> str:
    if not VSPEC.match(v or ""):
        raise es.StudioError(400, "Sürüm geçersiz.")
    return v


def _get(job: str, sub: str, params: dict, allowed: set[str], editor: str | None = None,
         limit: int = 60 * 1024 * 1024, timeout: float = 600) -> tuple[bytes, str]:
    base, headers, ca = es._base()
    if editor is not None:
        headers["X-Editor"] = editor[:200]
    with es._client(ca, timeout=timeout) as c:
        r = c.get(f"{base}/v1/studio/jobs/{es._job(job)}/plan{sub}", headers=headers, params=params)
    es._raise(r)
    mime = r.headers.get("content-type", "").split(";")[0]
    if mime not in allowed:
        raise es.StudioError(404, "Dosya bulunamadı.")
    if len(r.content) > limit:
        raise es.StudioError(413, "Dosya çok büyük.")
    return r.content, mime


def register(app, deps: dict[str, Any]) -> None:
    auth: Callable[[Request], Any] = deps["auth"]
    audit = deps.get("audit")
    conf = deps.get("conf")

    def plan(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except es.PlanError as e:
            return JSONResponse(status_code=e.status, content=e.body)
        except es.StudioError as e:
            raise HTTPException(e.status if e.status in (400, 404, 409, 413) else 400, str(e)) from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        except Exception:  # noqa: BLE001 — ayrıntı günlükte; editöre teknik hata metni gösterilmez
            log.exception("studio reader call failed")
            raise HTTPException(502, "Stüdyo şu an yanıt vermiyor.") from None

    def note(engine, user, action, obj, what, detail=None):
        if audit:
            audit(engine, user, action, "studio_reader", obj[:120], what, detail)

    # ---------------------------------------------------------------- okur
    @app.get("/api/v1/editorial/studio/jobs/{job}/plan/reader")
    def editorial_reader_info(job: str, request: Request):
        auth(request)
        out = plan(es.plan_request, "GET", job, "/reader", timeout=60)
        if isinstance(out, dict):
            out["passes"] = passes(conf)
        return out

    @app.post("/api/v1/editorial/studio/jobs/{job}/plan/reader/child")
    def editorial_reader_child(job: str, request: Request):
        engine, _t, user, _ = auth(request)
        n = passes(conf)
        out = plan(es.plan_request, "POST", job, "/reader/child", body={"passes": n}, editor=user, timeout=60)
        if not isinstance(out, Response):
            note(engine, user, "run", f"{job}/child", "çocuk gözüyle okuma başlatıldı", {"passes": n})
        return out

    @app.post("/api/v1/editorial/studio/jobs/{job}/plan/reader/turn")
    def editorial_reader_turn(job: str, request: Request):
        engine, _t, user, _ = auth(request)
        n = passes(conf)
        out = plan(es.plan_request, "POST", job, "/reader/turn", body={"passes": n}, editor=user, timeout=60)
        if not isinstance(out, Response):
            note(engine, user, "run", f"{job}/turn", "sayfa çevirme merakı ölçümü başlatıldı", {"passes": n})
        return out

    @app.get("/api/v1/editorial/studio/jobs/{job}/plan/reader/runs/{rid}")
    def editorial_reader_run(job: str, rid: str, request: Request):
        auth(request)
        out = plan(lambda: es.plan_request("GET", job, f"/reader/runs/{_run(rid)}", timeout=60))
        return out if isinstance(out, Response) else JSONResponse(out, headers={"Cache-Control": "no-store"})

    @app.post("/api/v1/editorial/studio/jobs/{job}/plan/reader/runs/{rid}/resume")
    def editorial_reader_resume(job: str, rid: str, request: Request):
        engine, _t, user, _ = auth(request)
        out = plan(lambda: es.plan_request("POST", job, f"/reader/runs/{_run(rid)}/resume", body={}, editor=user,
                                           timeout=60))
        if not isinstance(out, Response):
            note(engine, user, "run", f"{job}/{rid}", "okuma sürdürüldü")
        return out

    @app.post("/api/v1/editorial/studio/jobs/{job}/plan/reader/runs/{rid}/decisions")
    def editorial_reader_decide(job: str, rid: str, request: Request, body: dict[str, Any] | None = None):
        engine, _t, user, _ = auth(request)
        b = body if isinstance(body, dict) else {}
        flag, decision = str(b.get("flag") or ""), str(b.get("decision") or "")
        if not FLAG.match(flag) or decision not in DECISIONS:
            raise HTTPException(400, "Karar geçersiz.")
        out = plan(lambda: es.plan_request("POST", job, f"/reader/runs/{_run(rid)}/decisions",
                                           body={"flag": flag, "decision": decision}, editor=user, timeout=60))
        if not isinstance(out, Response):
            note(engine, user, "update", f"{job}/{rid}/{flag}", f"okur işareti: {decision}")
        return out

    # ---------------------------------------------------------------- sürüm farkı
    @app.get("/api/v1/editorial/studio/jobs/{job}/plan/versions")
    def editorial_versions(job: str, request: Request):
        auth(request)
        return plan(es.plan_request, "GET", job, "/versions", timeout=60)

    @app.get("/api/v1/editorial/studio/jobs/{job}/plan/versions/compare")
    def editorial_versions_compare(job: str, request: Request, a: str = "", b: str = ""):
        auth(request)
        out = plan(lambda: es.plan_request("GET", job, "/versions/compare", params={"a": _vspec(a), "b": _vspec(b)},
                                           timeout=120))
        return out if isinstance(out, Response) else JSONResponse(out, headers={"Cache-Control": "no-store"})

    @app.get("/api/v1/editorial/studio/jobs/{job}/plan/versions/visual")
    def editorial_versions_visual(job: str, request: Request, a: str = "", b: str = "", pa: str = "", pb: str = ""):
        auth(request)
        params = {"a": _vspec(a), "b": _vspec(b)}
        if pa:
            params["pa"] = es.plan_id(pa)
        if pb:
            params["pb"] = es.plan_id(pb)
        return plan(lambda: es.plan_request("GET", job, "/versions/visual", params=params, timeout=600))

    @app.get("/api/v1/editorial/studio/jobs/{job}/plan/versions/preview")
    def editorial_versions_preview(job: str, request: Request, v: str = "", page: str = "", w: int = 480):
        auth(request)
        params = {"v": _vspec(v), "page": es.plan_id(page), "w": max(120, min(int(w), 1600))}
        data, mime = plan(_get, job, "/versions/preview", params, {"image/png"})
        return Response(content=data, media_type=mime, headers={"Cache-Control": "private, max-age=3600"})

    @app.get("/api/v1/editorial/studio/jobs/{job}/plan/versions/report")
    def editorial_versions_report(job: str, request: Request, a: str = "", b: str = ""):
        engine, _t, user, _ = auth(request)
        params = {"a": _vspec(a), "b": _vspec(b)}
        data, _mime = plan(_get, job, "/versions/report", params, {"application/pdf"}, user,
                           limit=200 * 1024 * 1024)
        note(engine, user, "export", f"{job}/{a}/{b}", "değişiklik raporu indirildi", params)
        name = f"{job}-degisiklik-raporu.pdf"
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "private, no-store"})
