"""M29 İlk dağılım uçları: /api/v1/distribution/*.

Sayfa kapısı `access.RULES` (`sayfa:ilk-dagilim`); öneri, düzeltme, onaya gönderme, revizyon, liste yenileme
`ozellik:dagilim.plan` (`FEATURE_RULES`); onay/geri gönderme açıkça verilen `ozellik:dagilim.onay` ile burada
denetlenir (gönderen onaylayamaz, `distribution.decide`); sevk listesi `ozellik:veri.disa-aktar`.

Kapsam: `ozellik:dagilim.herkesinki` (açıkça verilir), `dagilim.plan` ya da `dagilim.onay` olan bütün carileri görür;
olmayan (BMT) yalnız CRM'de sahibi kendisi olan carilerin satırlarını görür (`AccountBase.OwnerId` →
`SystemUserBase.DomainName` = portal hesabı).

Zamanlayıcı (`timas-distribution.timer`, 07:30 ve 13:30) yalnız `POST /api/v1/distribution/run-due`'yu çağırır. Uyarı
özeti yalnız iç ekibe (`DIST_ALERT_RECIPIENTS`) gider; müşteriye (cariye) hiçbir gönderim yoktur.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import distribution as D
from semantic_bridge import distribution_sources as src

log = logging.getLogger("semantic.distribution.api")
P = "/api/v1/distribution"
FEATURE_PLAN = "ozellik:dagilim.plan"
FEATURE_APPROVE = "ozellik:dagilim.onay"
FEATURE_ALL = "ozellik:dagilim.herkesinki"
FEATURE_EXPORT = "ozellik:veri.disa-aktar"


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None], can: Callable[[str, str], bool]):
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod

    def crm_path() -> str:
        return os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")

    def m10():
        reports = getattr(app.state, "management_reports", None)
        return getattr(reports, "first_print", None) if reports is not None else None

    def llm():
        try:
            return rt().llm_for("dagilim")
        except Exception:  # noqa: BLE001 — model tanımlı değilse kural metni
            return None

    def sources() -> D.Sources:
        return D.Sources(lambda: src.runner(rt().settings.connection_file), lambda: src.runner(crm_path()),
                         lambda: admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo",
                         m12=lambda: getattr(app.state, "production", None), m10=m10, llm=llm)

    def m12_cards(engine, tenant) -> Callable[[], list]:
        def read() -> list:
            svc = getattr(app.state, "production", None)
            return svc.cards(engine, tenant)[0] if svc is not None else []
        return read

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        require_caller(request)
        try:
            user, display = board_mod.session_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        r = rt()
        D.ensure(r.store.engine)
        admin_mod.ensure(r.store.engine)
        return r.store.engine, r.settings.tenant_id, user, display

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except D.DistError as e:
            raise HTTPException(status_code=e.status, detail={"code": "DISTRIBUTION", "message": str(e)}) from e
        except src.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "DISTRIBUTION_SOURCE", "message": str(e)}) from e

    def need(user: str, key: str, what: str) -> None:
        if not can(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def scope(user: str) -> Optional[str]:
        """None = bütün cariler; aksi hâlde yalnız bu hesabın (BMT) carileri."""
        if can(user, FEATURE_ALL) or can(user, FEATURE_PLAN) or can(user, FEATURE_APPROVE):
            return None
        return user

    def audit(engine, user, action, plan: dict[str, Any], detail: Any = None, kind: str = "dist_plan", oid: str = "") -> None:
        admin_mod.audit(engine, user, action, kind, oid or plan.get("id"),
                        f"{plan.get('ad') or plan.get('stokKodu') or ''} · sürüm {plan.get('surum')}", detail)

    # ------------------------------------------------------------------ genel

    @app.get(f"{P}/meta")
    def dist_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        lm = D.meta_get(engine, tenant, "logo")
        return {"statuses": D.STATUSES, "bookStates": D.BOOK_STATES, "alertKinds": D.ALERT_KINDS, "regions": D.REGION_ORDER,
                "params": D.params(), "veriSonu": lm.get("veriSonu"), "depoSonu": lm.get("depoSonu"), "asof": lm.get("_at"),
                "me": {"username": user, "display": display, "canPlan": can(user, FEATURE_PLAN),
                       "canApprove": can(user, FEATURE_APPROVE), "canAll": scope(user) is None,
                       "canExport": can(user, FEATURE_EXPORT)}}

    @app.get(f"{P}/books")
    def dist_books(request: Request, durum: str = "", q: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(D.list_books, engine, tenant, durum, q)

    @app.post(f"{P}/books/refresh")
    async def dist_books_refresh(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        out = await run_in_threadpool(call, D.refresh_books, engine, tenant, sources(), m12_cards(engine, tenant))
        admin_mod.audit(engine, user, "run", "dist_plan", None, "Dağılım bekleyen kitaplar yenilendi", out)
        return out

    @app.post(f"{P}/run-due")
    def dist_run_due(request: Request) -> dict[str, Any]:
        """Zamanlayıcı: depoya girişleri okur, izlenen planların takibini tazeler, uyarıları açar/kapatır, özeti gönderir."""
        require_caller(request)
        r = rt()
        engine, tenant = r.store.engine, r.settings.tenant_id
        D.ensure(engine)
        S = sources()
        out: dict[str, Any] = {}
        try:
            out["kitaplar"] = D.refresh_books(engine, tenant, S, m12_cards(engine, tenant))
        except src.SourceError as e:
            out["kitaplar"] = {"hata": str(e)}
        tracked = [t["planId"] for t in D.list_books(engine, tenant)["izlenen"]]
        out["takip"] = []
        for pid in tracked:
            try:
                out["takip"].append(D.refresh_tracking(engine, tenant, S, D.get_plan_row(engine, tenant, pid)))
            except src.SourceError as e:
                out["takip"].append({"planId": pid, "hata": str(e)})
        try:
            out["bmtGuncellenen"] = D.refresh_owners(engine, S, tracked)
        except src.SourceError as e:
            out["bmtGuncellenen"] = {"hata": str(e)}
        out["uyarilar"] = D.evaluate_alerts(engine, tenant)
        from semantic_bridge.budget_api import _send_mail

        recipients = [x.strip() for x in (admin_mod.conf("DIST_ALERT_RECIPIENTS") or "").replace(";", ",").split(",") if "@" in x]
        link = (admin_mod.conf("ALERT_LINK") or "").split("/uyarilar")[0]
        out["bildirim"] = D.notify(engine, tenant, recipients, f"{link}/ilk-dagilim?sekme=uyarilar" if link else "", _send_mail)
        return out

    # ------------------------------------------------------------------ planlar

    @app.get(f"{P}/plans")
    def dist_plans(request: Request, stok: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        if not stok:
            raise HTTPException(status_code=400, detail={"code": "DISTRIBUTION", "message": "Stok kodu gerekli."})
        return {"items": D.plans_of(engine, tenant, stok.strip()[:60])}

    @app.post(f"{P}/plans/generate", status_code=201)
    async def dist_generate(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        out = await run_in_threadpool(call, D.generate, engine, tenant, user, body.get("stok_kodu") or body.get("stokKodu"), sources())
        audit(engine, user, "create", out, {"kaynak": "ZEKİ AI önerisi", "toplam": out["toplam"], "rezerv": out["rezerv"],
                                            "musteri": out["musteri"], "benzer": out["basis"].get("benzerSayisi")})
        return out

    @app.get(f"{P}/plans/{{plan_id}}")
    def dist_plan(plan_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return call(D.plan_detail, engine, tenant, plan_id, scope(user))

    @app.get(f"{P}/plans/{{plan_id}}/lines")
    def dist_lines(plan_id: str, request: Request, q: str = "", bolge: str = "", kanal: str = "", yalniz: str = "",
                   page: int = 0) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return call(D.list_lines, engine, tenant, plan_id, q=q, bolge=bolge, kanal=kanal, yalniz=yalniz, page=page, bmt=scope(user))

    @app.patch(f"{P}/plans/{{plan_id}}")
    def dist_plan_update(plan_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out, diff = call(D.update_plan, engine, tenant, user, plan_id, body)
        if diff:
            audit(engine, user, "update", out, diff)
        return out

    @app.patch(f"{P}/plans/{{plan_id}}/lines/{{line}}")
    def dist_line_update(plan_id: str, line: int, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out, diff = call(D.update_line, engine, tenant, user, plan_id, line, body)
        if len(diff) > 1:
            admin_mod.audit(engine, user, "update", "dist_line", f"{plan_id}:{line}", out.get("unvan"), diff)
        return out

    @app.patch(f"{P}/plans/{{plan_id}}/cells")
    def dist_cell_update(plan_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out, diff = call(D.update_cell, engine, tenant, user, plan_id, body)
        admin_mod.audit(engine, user, "update", "dist_line", f"{plan_id}:{diff['bolge']}|{diff['kanal']}",
                        f"{diff['bolge']} · {diff['kanal']}", diff)
        return out

    @app.delete(f"{P}/plans/{{plan_id}}")
    def dist_plan_delete(plan_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(D.delete_plan, engine, tenant, plan_id)
        admin_mod.audit(engine, user, "delete", "dist_plan", out["id"], out["title"], None)
        return {"ok": True}

    @app.post(f"{P}/plans/{{plan_id}}/submit")
    def dist_submit(plan_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(D.submit, engine, tenant, user, plan_id)
        audit(engine, user, "update", out, {"durum": "onayda", "toplam": out["toplam"], "rezerv": out["rezerv"]})
        return out

    @app.post(f"{P}/plans/{{plan_id}}/withdraw")
    def dist_withdraw(plan_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(D.withdraw, engine, tenant, user, plan_id)
        audit(engine, user, "update", out, {"durum": "taslak", "neden": "onaydan geri çekildi"})
        return out

    @app.post(f"{P}/plans/{{plan_id}}/approve")
    def dist_approve(plan_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, FEATURE_APPROVE, "Dağılım onayı")
        out = call(D.decide, engine, tenant, user, plan_id, True, body.get("note"))
        audit(engine, user, "approve", out, {"arsivlenen": out.get("archived"), "not": body.get("note")})
        return out

    @app.post(f"{P}/plans/{{plan_id}}/reject")
    def dist_reject(plan_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, FEATURE_APPROVE, "Dağılım onayı")
        out = call(D.decide, engine, tenant, user, plan_id, False, body.get("note"))
        audit(engine, user, "reject", out, {"not": body.get("note")})
        return out

    @app.post(f"{P}/plans/{{plan_id}}/revise", status_code=201)
    def dist_revise(plan_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(D.revise, engine, tenant, user, plan_id, body.get("reason"))
        audit(engine, user, "create", out, {"revizyon": plan_id, "gerekce": body.get("reason")})
        return out

    @app.post(f"{P}/plans/{{plan_id}}/track")
    async def dist_track(plan_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        row = await run_in_threadpool(call, D.get_plan_row, engine, tenant, plan_id)
        if row.durum != "onayli":
            raise HTTPException(status_code=409, detail={"code": "DISTRIBUTION", "message": "Takip yalnız onaylı planda."})
        out = await run_in_threadpool(call, D.refresh_tracking, engine, tenant, sources(), row)
        admin_mod.audit(engine, user, "run", "dist_plan", plan_id, "Dağılım takibi yenilendi", out)
        return out

    @app.get(f"{P}/plans/{{plan_id}}/export.xlsx")
    def dist_export(plan_id: str, request: Request) -> Response:
        engine, tenant, user, _ = ctx(request)
        if scope(user) is not None:
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Sevk listesi bütün carileri içerir; rolünüzde yok."})
        data, name = call(D.export_xlsx, engine, tenant, plan_id)
        admin_mod.audit(engine, user, "run", "dist_export", plan_id, f"Sevk listesi {name}", None)
        return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    # ------------------------------------------------------------------ takip, bölgem, uyarılar

    @app.get(f"{P}/tracking")
    def dist_tracking(request: Request, stok: str = "", hafta: int = 0) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return call(D.tracking, engine, tenant, stok.strip()[:60], hafta, scope(user))

    @app.get(f"{P}/my-region")
    def dist_my_region(request: Request, herkes: bool = False) -> dict[str, Any]:
        """BMT: kendi carilerine düşen kitaplar. Bütün carileri görebilen kişi `herkes=1` ile hepsini görür."""
        engine, tenant, user, _ = ctx(request)
        mine = scope(user)
        return call(D.my_region, engine, tenant, None if (herkes and mine is None) else user)

    @app.get(f"{P}/alerts")
    def dist_alerts(request: Request, durum: str = "acik", tur: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return call(D.alerts, engine, tenant, durum=durum, tur=tur, page=page, bmt=scope(user))

    return sources
