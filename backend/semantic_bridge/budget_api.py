"""M46 Bütçe uçları: /api/v1/budget/*.

Sayfa kapısı `access.RULES` (`sayfa:butce`); taslak yazma `ozellik:butce.duzenle` (`FEATURE_RULES`), onay/geri gönderme
açıkça verilen `ozellik:butce.onay` ile burada denetlenir (gönderen onaylayamaz, `budget.decide`). Zamanlayıcı
(`timas-budget.timer`) yalnız `POST /api/v1/budget/run-due`'yu çağırır.

Sözleşme uçları (diğer modüller okur): `GET /api/v1/budget/targets`, `GET /api/v1/budget/deviations`.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any, Callable

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import budget as B
from semantic_bridge import budget_sources as src

log = logging.getLogger("semantic.budget.api")


def _send_mail(subject: str, text: str, to: list[str]) -> str:
    from semantic_bridge.alerts import smtp_settings

    cfg = smtp_settings()
    if not cfg:
        return "no_smtp"
    try:
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, cfg["sender"], ", ".join(to)
        msg.set_content(text)
        ctx = ssl.create_default_context()
        server = (smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=20, context=ctx) if cfg["ssl"]
                  else smtplib.SMTP(cfg["host"], cfg["port"], timeout=20))
        with server as s:
            if not cfg["ssl"] and cfg["starttls"]:
                s.starttls(context=ctx)
            if cfg["user"]:
                s.login(cfg["user"], cfg["password"])
            s.send_message(msg)
        return "sent"
    except Exception as e:  # noqa: BLE001
        log.warning("bütçe uyarısı e-postası gönderilemedi: %s", e)
        return "failed"


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None], can: Callable[[str, str], bool]):
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod

    refresher = B.Refresher(
        lambda: rt().store.engine,
        lambda: rt().settings.connection_file,
        lambda: os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"),
    )

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        require_caller(request)
        try:
            user, display = board_mod.session_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        r = rt()
        B.ensure(r.store.engine)
        admin_mod.ensure(r.store.engine)
        return r.store.engine, r.settings.tenant_id, user, display

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except B.BudgetError as e:
            raise HTTPException(status_code=e.status, detail={"code": "BUDGET", "message": str(e)}) from e
        except src.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "BUDGET_SOURCE", "message": str(e)}) from e

    def need(user: str, key: str, what: str) -> None:
        if not can(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def audit(engine, user, action, plan: dict[str, Any], detail: Any = None) -> None:
        admin_mod.audit(engine, user, action, "budget_plan", plan.get("id"), plan.get("title"), detail)

    # ------------------------------------------------------------------ genel

    @app.get("/api/v1/budget/meta")
    def budget_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        st = refresher.status()
        end = B.data_end(engine)
        years = sorted(set(B.list_plans(engine, tenant)["years"]) | ({end.year, end.year + 1} if end else set()))
        return {"scenarios": B.SCENARIOS, "statuses": B.STATUSES, "segments": B.SEGMENTS, "months": B.AY,
                "threshold": B.DEFAULT_THRESHOLD, "earlyWarning": B.EARLY_WARNING, "years": years,
                "defaultYear": (end.year if end else None), "data": st,
                "me": {"username": user, "display": display, "canEdit": can(user, "ozellik:butce.duzenle"),
                       "canApprove": can(user, "ozellik:butce.onay")}}

    @app.get("/api/v1/budget/status")
    def budget_status(request: Request) -> dict[str, Any]:
        ctx(request)
        return refresher.status()

    @app.post("/api/v1/budget/refresh")
    def budget_refresh(request: Request) -> dict[str, Any]:
        engine, _, user, _ = ctx(request)
        started = refresher.start(refresher.needed_years(engine))
        admin_mod.audit(engine, user, "run", "budget_actuals", None, "Bütçe gerçekleşmesi yenilendi", {"started": started})
        return {"started": started, **refresher.status()}

    @app.post("/api/v1/budget/run-due")
    def budget_run_due(request: Request) -> dict[str, Any]:
        """Zamanlayıcı: bayat gerçekleşmeyi okur, yürürlükteki planlarda sapmayı değerlendirir, yeni uyarıyı e-postalar."""
        require_caller(request)
        r = rt()
        engine, tenant = r.store.engine, r.settings.tenant_id
        B.ensure(engine)
        years = refresher.due(engine)
        read = {"skipped": "başka bir okuma sürüyor"} if refresher.running() else refresher.run(years)
        end = B.data_end(engine)
        out: dict[str, Any] = {"read": read, "years": years, "alerts": []}
        if end:
            recipients = [x.strip() for x in (admin_mod.conf("BUDGET_ALERT_RECIPIENTS") or "").replace(";", ",").split(",") if "@" in x]
            link = (admin_mod.conf("ALERT_LINK") or "").split("/uyarilar")[0]
            link = f"{link}/butce?sekme=izleme" if link else ""
            for y in sorted({end.year, end.year - 1}):
                ev = B.evaluate_alerts(engine, tenant, y)
                if ev.get("planId"):
                    ev["notify"] = B.notify(engine, tenant, y, recipients, link, _send_mail)
                out["alerts"].append(ev)
        return out

    # ------------------------------------------------------------------ planlar

    @app.get("/api/v1/budget/plans")
    def budget_plans(request: Request, year: int | None = None) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return B.list_plans(engine, tenant, year)

    @app.get("/api/v1/budget/defaults")
    def budget_defaults(request: Request, year: int) -> dict[str, Any]:
        engine, _, _, _ = ctx(request)
        fc = src.read_forecast()
        out = call(B.default_params, engine, year)
        return {**out, "tahminVar": bool(fc), "tahminBaslangic": fc.get("start")}

    @app.post("/api/v1/budget/plans/generate", status_code=201)
    async def budget_generate(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        items = await run_in_threadpool(call, B.generate, engine, tenant, user, body, src.read_forecast())
        for p in items:
            audit(engine, user, "create", p, {"senaryo": p["scenario"], "kitap": p["totals"]["kitap"],
                                              "ciro": round(p["totals"]["ciro"], 2), "kaynak": "ZEKİ AI önerisi"})
        return {"items": items}

    @app.get("/api/v1/budget/plans/{plan_id}")
    def budget_plan(plan_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(B.plan_summary, engine, tenant, plan_id)

    @app.patch("/api/v1/budget/plans/{plan_id}")
    def budget_plan_update(plan_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(B.update_plan, engine, tenant, user, plan_id, body)
        audit(engine, user, "update", out, {k: body[k] for k in ("title", "note") if k in body})
        return out

    @app.delete("/api/v1/budget/plans/{plan_id}")
    def budget_plan_delete(plan_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(B.delete_plan, engine, tenant, plan_id)
        audit(engine, user, "delete", out)
        return {"ok": True}

    @app.post("/api/v1/budget/plans/{plan_id}/recompute")
    async def budget_recompute(plan_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        out = await run_in_threadpool(call, B.recompute, engine, tenant, user, plan_id, body, src.read_forecast())
        audit(engine, user, "update", out, {"yenidenHesap": body.get("params")})
        return out

    @app.post("/api/v1/budget/plans/{plan_id}/submit")
    def budget_submit(plan_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(B.submit, engine, tenant, user, plan_id)
        audit(engine, user, "update", out, {"durum": "onayda"})
        return out

    @app.post("/api/v1/budget/plans/{plan_id}/withdraw")
    def budget_withdraw(plan_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(B.withdraw, engine, tenant, user, plan_id)
        audit(engine, user, "update", out, {"durum": "taslak", "neden": "onaydan geri çekildi"})
        return out

    @app.post("/api/v1/budget/plans/{plan_id}/approve")
    def budget_approve(plan_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, "ozellik:butce.onay", "Bütçe onayı")
        out = call(B.decide, engine, tenant, user, plan_id, True, body.get("note"))
        audit(engine, user, "approve", out, {"arsivlenen": out.get("archived"), "not": body.get("note")})
        return out

    @app.post("/api/v1/budget/plans/{plan_id}/reject")
    def budget_reject(plan_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, "ozellik:butce.onay", "Bütçe onayı")
        out = call(B.decide, engine, tenant, user, plan_id, False, body.get("note"))
        audit(engine, user, "reject", out, {"not": body.get("note")})
        return out

    @app.post("/api/v1/budget/plans/{plan_id}/revise", status_code=201)
    def budget_revise(plan_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(B.revise, engine, tenant, user, plan_id, body.get("reason"))
        audit(engine, user, "create", out, {"revizyon": plan_id, "gerekce": body.get("reason")})
        return out

    # ------------------------------------------------------------------ satırlar

    @app.get("/api/v1/budget/plans/{plan_id}/books")
    def budget_books(plan_id: str, request: Request, segment: str = "", q: str = "", yayinevi: str = "",
                     sort: str = "ciro", page: int = 0, durum: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(B.books, engine, tenant, plan_id, segment=segment, q=q, yayinevi=yayinevi, sort=sort, page=page, durum=durum)

    @app.post("/api/v1/budget/plans/{plan_id}/books", status_code=201)
    def budget_book_add(plan_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(B.add_book, engine, tenant, user, plan_id, body)
        admin_mod.audit(engine, user, "create", "budget_target", f"{plan_id}:{out['stokKodu']}", out["ad"] or out["stokKodu"],
                        {"adet": out["adet"], "ciro": out["ciro"], "marj": out["marj"]})
        return out

    @app.patch("/api/v1/budget/plans/{plan_id}/books/{code}")
    def budget_book_update(plan_id: str, code: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out, diff = call(B.update_book, engine, tenant, user, plan_id, code, body)
        if diff:
            admin_mod.audit(engine, user, "update", "budget_target", f"{plan_id}:{code}", out["ad"] or code, diff)
        return out

    @app.delete("/api/v1/budget/plans/{plan_id}/books/{code}")
    def budget_book_delete(plan_id: str, code: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(B.delete_book, engine, tenant, user, plan_id, code)
        admin_mod.audit(engine, user, "delete", "budget_target", f"{plan_id}:{code}", out["ad"] or code, None)
        return {"ok": True}

    @app.get("/api/v1/budget/plans/{plan_id}/program")
    def budget_program(plan_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(B.program, engine, tenant, plan_id)

    @app.patch("/api/v1/budget/plans/{plan_id}/program/{yayinevi}")
    def budget_program_update(plan_id: str, yayinevi: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(B.update_program, engine, tenant, user, plan_id, yayinevi, body)
        admin_mod.audit(engine, user, "update", "budget_program", f"{plan_id}:{yayinevi}", yayinevi,
                        {k: body[k] for k in ("ekBaslik", "baslikAdet", "baslikCiro", "marj") if k in body})
        return out

    @app.get("/api/v1/budget/plans/{plan_id}/departments")
    def budget_departments(plan_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(B.departments, engine, tenant, plan_id)

    @app.patch("/api/v1/budget/plans/{plan_id}/departments/{center}/{hesap}")
    def budget_department_update(plan_id: str, center: str, hesap: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(B.update_dept, engine, tenant, user, plan_id, center, hesap, body)
        admin_mod.audit(engine, user, "update", "budget_dept", f"{plan_id}:{center}:{hesap}",
                        f"{out['merkezAdi']} · {out['hesapAdi']}", {"yillik": out["yillik"]})
        return out

    @app.get("/api/v1/budget/plans/{plan_id}/export.csv")
    def budget_export(plan_id: str, request: Request) -> Response:
        engine, tenant, user, _ = ctx(request)
        text = call(B.books_csv, engine, tenant, plan_id)
        admin_mod.audit(engine, user, "run", "budget_export", plan_id, "Kitap hedefleri CSV", None)
        return Response(text.encode("utf-8"), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="butce-hedefleri-{plan_id[:8]}.csv"'})

    # ------------------------------------------------------------------ izleme ve karşılaştırma

    @app.get("/api/v1/budget/compare")
    def budget_compare(request: Request, year: int) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(B.compare, engine, tenant, year)

    @app.get("/api/v1/budget/tracking")
    def budget_tracking(request: Request, year: int, plan: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(B.tracking, engine, tenant, year, plan or None)

    # ------------------------------------------------------------------ sözleşme (diğer modüller)

    @app.get("/api/v1/budget/targets")
    def budget_targets(request: Request, year: int, segment: str = "", stok: str = "", yayinevi: str = "",
                       actuals: bool = True) -> dict[str, Any]:
        """Yürürlükteki planın kitap hedefleri. `stok` virgülle birden çok stok kodu alır."""
        engine, tenant, _, _ = ctx(request)
        codes = [c for c in stok.split(",") if c.strip()] if stok else None
        return call(B.approved_targets, engine, tenant, year, codes=codes, segment=segment, yayinevi=yayinevi,
                    with_actuals=actuals)

    @app.get("/api/v1/budget/deviations")
    def budget_deviations(request: Request, year: int, status: str = "acik", kind: str = "", scope: str = "",
                          module: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(B.deviations, engine, tenant, year, status=status, kind=kind, scope=scope, module=module, page=page)

    return refresher
