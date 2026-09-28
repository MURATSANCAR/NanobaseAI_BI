"""M45 Finansal raporlama uçları: /api/v1/finance/*.

Sayfa kapısı `access.RULES` (`sayfa:finansal-raporlar`). Nakit sekmesi ve uçları `ozellik:finans.nakit`, vergi
takvimi yazma `ozellik:finans.vergi-takvimi`, sapma notu `ozellik:finans.sapma-notu`, dışa aktarma
`ozellik:veri.disa-aktar` (`FEATURE_RULES`). Açıkça verilen yetkiler ucun içinde denetlenir: hesap eşlemesi kararı
`ozellik:finans.esleme`, ay kapanışı `ozellik:finans.kapanis`. Zamanlayıcı (`timas-finance.timer`) yalnız
`POST /api/v1/finance/run-due`'yu çağırır.

Sözleşme uçları (M47 ve DYK okur): `GET /api/v1/finance/summary`, `GET /api/v1/finance/pnl`.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import Any, Callable

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import finance as F
from semantic_bridge import finance_sources as src

log = logging.getLogger("semantic.finance.api")

ENTRY_PAGE = 100


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None], can: Callable[[str, str], bool]):
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod
    from semantic_bridge.budget_api import _send_mail

    def snapshot() -> Any:
        store = getattr(app.state, "pricing", None)
        try:
            return store.get() if store is not None else None
        except Exception as e:  # noqa: BLE001 — M9 görüntüsü yoksa tahmini maliyet ve telif boş kalır
            log.warning("finance: M9 görüntüsü okunamadı: %s", e)
            return None

    def unit_costs(codes: list[str]) -> dict[str, dict[str, Any]]:
        """M9 birim maliyeti: sağlayıcı (`app.state.pricing_costs`) varsa o; yoksa M9 Logo görüntüsünden aynı tanım."""
        prov = getattr(app.state, "pricing_costs", None)
        if prov is not None and hasattr(prov, "unit_costs"):
            try:
                return {k: {"maliyet": float(v["maliyet"]), "kaynak": v.get("kaynak"), "tarih": v.get("tarih")}
                        for k, v in prov.unit_costs(codes).items() if v.get("maliyet") is not None}
            except Exception as e:  # noqa: BLE001
                log.warning("finance: M9 maliyet sağlayıcısı cevap vermedi: %s", e)
        return F.snapshot_unit_costs(snapshot(), codes)

    logo_file = lambda: rt().settings.connection_file  # noqa: E731
    crm_file = lambda: os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")  # noqa: E731
    refresher = F.Refresher(lambda: rt().store.engine, lambda: rt().settings.tenant_id, logo_file, crm_file, unit_costs)
    suggest_state: dict[str, Any] = {"thread": None}

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        require_caller(request)
        try:
            user, display = board_mod.session_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        r = rt()
        F.ensure(r.store.engine)
        admin_mod.ensure(r.store.engine)
        return r.store.engine, r.settings.tenant_id, user, display

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except F.FinanceError as e:
            raise HTTPException(status_code=e.status, detail={"code": "FINANCE", "message": str(e)}) from e
        except src.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "FINANCE_SOURCE", "message": str(e)}) from e

    def need(user: str, key: str, what: str) -> None:
        if not can(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def audit(engine, user, action, kind, oid, title, detail=None) -> None:
        admin_mod.audit(engine, user, action, kind, oid, title, detail)

    def year_or_default(engine, year: int | None) -> int:
        if year:
            return int(year)
        end = F.data_end(engine)
        return end.year if end else date.today().year

    def recipients(key: str) -> list[str]:
        return [x.strip() for x in (admin_mod.conf(key) or "").replace(";", ",").split(",") if "@" in x]

    def link(tab: str = "") -> str:
        base = (admin_mod.conf("ALERT_LINK") or "").split("/uyarilar")[0]
        return f"{base}/finansal-raporlar{('?sekme=' + tab) if tab else ''}" if base else ""

    # ------------------------------------------------------------------ genel

    @app.get("/api/v1/finance/meta")
    def finance_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        end = F.data_end(engine)
        years = sorted(F._loaded_years(engine) | ({end.year} if end else set()))
        return {"months": F.AY, "grains": F.GRAINS, "profitBy": F.PROFIT_BY, "taxStatuses": F.TAX_STATUSES,
                "lines": F.lines(engine, tenant), "years": years, "defaultYear": end.year if end else None,
                "defaultMonth": _last_closed_month(end), "data": refresher.status(),
                "me": {"username": user, "display": display, "canCash": can(user, "ozellik:finans.nakit"),
                       "canMap": can(user, "ozellik:finans.esleme"), "canClose": can(user, "ozellik:finans.kapanis"),
                       "canTax": can(user, "ozellik:finans.vergi-takvimi"), "canNote": can(user, "ozellik:finans.sapma-notu"),
                       "canExport": can(user, "ozellik:veri.disa-aktar")}}

    @app.get("/api/v1/finance/status")
    def finance_status(request: Request) -> dict[str, Any]:
        ctx(request)
        return refresher.status()

    @app.post("/api/v1/finance/refresh")
    def finance_refresh(request: Request) -> dict[str, Any]:
        engine, _, user, _ = ctx(request)
        started = refresher.start(None, cash=can(user, "ozellik:finans.nakit"), user=user)
        audit(engine, user, "run", "finance_actuals", None, "Finansal raporların Logo okuması", {"started": started})
        return {"started": started, **refresher.status()}

    @app.post("/api/v1/finance/run-due")
    def finance_run_due(request: Request) -> dict[str, Any]:
        """Zamanlayıcı: bayat yılları okur, pazartesi 07:00'den sonra nakit tablosunu kurar, vergi hatırlatması ve iş
        günü 08:30 özet e-postası gönderir. Bir adım düşerse diğerleri sürer; sonuç cevapta."""
        require_caller(request)
        r = rt()
        engine, tenant = r.store.engine, r.settings.tenant_id
        F.ensure(engine)
        out: dict[str, Any] = {}
        years = refresher.due(engine)
        cash_needed = F.cash_due(engine, tenant)
        if refresher.running():
            out["read"] = {"skipped": "başka bir okuma sürüyor"}
        elif years or cash_needed:
            out["read"] = refresher.run(years, cash_too=cash_needed, user="Zamanlayıcı")
        out["years"], out["cash"] = years, cash_needed
        due = F.tax_due_reminders(engine, tenant)
        if due:
            to = recipients("FINANCE_TAX_RECIPIENTS")
            if to:
                text = "\n".join([f"Vergi takvimi hatırlatması ({len(due)} beyan):", ""] +
                                 [f"- {d['beyan']}{' (' + d['donem'] + ')' if d['donem'] else ''}: son gün {d['sonGun']}, "
                                  f"{d['kalanGun']} gün kaldı; durum {d['durum']}{'; sorumlu ' + d['sorumlu'] if d['sorumlu'] else ''}"
                                  for d in due] + ["", f"Takvim: {link('vergi')}" if link() else "Takvim Finansal raporlar ekranında."])
                status = _send_mail("ZEKİ vergi takvimi hatırlatması", text, to)
                if status == "sent":
                    F.mark_reminded(engine, due)
                out["tax"] = {"due": len(due), "status": status}
            else:
                out["tax"] = {"due": len(due), "status": "no_recipient"}
        if F.summary_due(engine):
            to = recipients("FINANCE_SUMMARY_RECIPIENTS")
            if to:
                data = F.summary(engine, tenant, with_cash=True)
                if data.get("hazir"):
                    status = _send_mail(f"ZEKİ finansal özet — veri {data.get('veriSonu')}", F.summary_text(data, link()), to)
                    if status == "sent":
                        F.meta_set(engine, "summary_mail", {"day": datetime.now(F.TZ).date().isoformat(), "to": len(to)})
                    out["summary"] = status
            else:
                out["summary"] = "no_recipient"
        return out

    # ------------------------------------------------------------------ özet ve gelir tablosu

    @app.get("/api/v1/finance/summary")
    def finance_summary(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return call(F.summary, engine, tenant, with_cash=can(user, "ozellik:finans.nakit"))

    @app.get("/api/v1/finance/pnl")
    def finance_pnl(request: Request, year: int | None = None, month: int | None = None, grain: str = "ay",
                    compare: str = "onceki,gecen-yil,butce") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        y = year_or_default(engine, year)
        m = month or _last_closed_month(F.data_end(engine)) or 12
        return call(F.pnl, engine, tenant, y, m, grain, [c for c in compare.split(",") if c])

    @app.get("/api/v1/finance/pnl/lines/{kod}/accounts")
    def finance_pnl_line(kod: str, request: Request, year: int, month: int, grain: str = "ay") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(F.line_accounts, engine, tenant, kod, year, month, grain)

    @app.get("/api/v1/finance/pnl/accounts/{hesap}/entries")
    async def finance_entries(hesap: str, request: Request, year: int, month: int, grain: str = "ay", page: int = 0) -> dict[str, Any]:
        """Hesabın Logo fiş satırları (canlı okuma, sayfalı; her satırın rapordaki kuralı yazılır)."""
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        months = call(F.period_months, int(year), int(month), grain)
        start = date(months[0][0], months[0][1], 1)
        ly, lm = months[-1]
        end = date(ly + (lm == 12), lm % 12 + 1, 1)

        def go():
            run = src.runner(logo_file())
            firms = src.firms_by_year(run)
            firm = firms.get(int(year))
            if not firm:
                raise src.SourceError(f"Logo'da {year} yılının dönemi yok.")
            sql = src.entries_sql(firm, hesap, start, end, max(0, int(page)), ENTRY_PAGE)
            return run(sql), sql

        rows, sql = await run_in_threadpool(call, go)
        total = int(src.f(rows[0].get("toplam"))) if rows else 0
        items = [{"tarih": src.to_day(r.get("tarih")), "fisNo": r.get("fis_no"), "fisTuru": r.get("fis_turu"), "hesap": r.get("hesap"),
                  "hesapAdi": src.clean(r.get("hesap_adi")), "aciklama": src.clean(r.get("aciklama")), "borc": src.f(r.get("borc")),
                  "alacak": src.f(r.get("alacak")), "merkez": src.clean(r.get("merkez")), "kural": r.get("kural")} for r in rows]
        return {"hesap": hesap, "donem": F.period_label(months), "items": items, "total": total, "page": max(0, int(page)),
                "pageSize": ENTRY_PAGE, "sql": sql, **F.freshness(engine)}

    @app.get("/api/v1/finance/pnl/export.xlsx")
    def finance_pnl_export(request: Request, year: int, month: int, grain: str = "ay") -> Response:
        engine, tenant, user, _ = ctx(request)
        data = call(F.pnl, engine, tenant, int(year), int(month), grain)
        audit(engine, user, "run", "finance_export", f"{year}-{month}", "Gelir tablosu Excel", {"donem": grain})
        return Response(F.pnl_xlsx(data), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="gelir-tablosu-{year}-{int(month):02d}-{grain}.xlsx"'})

    @app.get("/api/v1/finance/reconciliation")
    def finance_reconciliation(request: Request, year: int, month: int, grain: str = "ay") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(F.reconciliation, engine, tenant, year, month, grain)

    # ------------------------------------------------------------------ hesap eşlemesi

    @app.get("/api/v1/finance/account-map")
    def finance_map(request: Request, year: int | None = None) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(F.account_map, engine, tenant, year)

    @app.patch("/api/v1/finance/account-map/{hesap}")
    def finance_map_set(hesap: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, "ozellik:finans.esleme", "Hesap eşlemesi kararı")
        out = call(F.set_mapping, engine, tenant, user, hesap, body)
        audit(engine, user, "approve", "finance_account_map", hesap, f"{hesap} → {out['satir']}", {"onceki": out["onceki"], "not": body.get("not")})
        return out

    @app.delete("/api/v1/finance/account-map/{hesap}")
    def finance_map_reset(hesap: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, "ozellik:finans.esleme", "Hesap eşlemesi kararı")
        out = call(F.reset_mapping, engine, tenant, hesap)
        audit(engine, user, "delete", "finance_account_map", hesap, f"{hesap} eşleme kararı geri alındı", out["onceki"])
        return out

    @app.post("/api/v1/finance/account-map/approve")
    def finance_map_approve(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, "ozellik:finans.esleme", "Hesap eşlemesi kararı")
        codes = [str(c) for c in (body.get("codes") or [])]
        if not codes:
            raise HTTPException(status_code=400, detail={"code": "FINANCE", "message": "Onaylanacak hesap seçilmedi."})
        out = call(F.approve_suggestions, engine, tenant, user, codes)
        if out["approved"]:
            audit(engine, user, "approve", "finance_account_map", None, f"{len(out['approved'])} hesap önerisi onaylandı",
                  {"hesaplar": out["approved"]})
        return out

    @app.post("/api/v1/finance/account-map/suggest", status_code=202)
    def finance_map_suggest(body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Zeki AI: kuralı ve kararı olmayan hareketli hesaplara (ya da seçilenlere) kapalı kümeden satır önerisi."""
        engine, tenant, user, _ = ctx(request)
        need(user, "ozellik:finans.esleme", "Hesap eşlemesi")
        from semantic_layer.runtime.llm_queue import BATCH

        llm = rt().llm_for("finance", BATCH)
        if llm is None or not hasattr(llm, "choose"):
            raise HTTPException(status_code=503, detail={"code": "FINANCE", "message": "Zeki AI bu kurulumda tanımlı değil."})
        t = suggest_state.get("thread")
        if t is not None and t.is_alive():
            raise HTTPException(status_code=409, detail={"code": "FINANCE", "message": "Öneri işi sürüyor; bitince yeniden deneyin."})
        items = call(F.suggestion_targets, engine, tenant, body.get("codes"))
        if not items:
            return {"started": False, "count": 0, "message": "Öneri bekleyen hesap yok."}
        min_p = float(F.conf("FINANCE_MAP_MIN_PROB", "0.70"))
        min_m = float(F.conf("FINANCE_MAP_MIN_MARGIN", "0.30"))
        key = f"suggest:{tenant}"
        F.meta_set(engine, key, {"running": True, "count": len(items), "by": user})

        def go():
            try:
                res = F.suggest_with_model(engine, tenant, llm, items, min_p, min_m)
                F.meta_set(engine, key, {"running": False, "by": user, **res})
                audit(engine, user, "run", "finance_account_map", None, "Zeki AI eşleme önerisi", res)
            except Exception as e:  # noqa: BLE001
                log.warning("finance suggest failed: %s", e)
                F.meta_set(engine, key, {"running": False, "by": user, "error": str(e)[:300]})

        import threading
        th = threading.Thread(target=go, daemon=True, name="finance-suggest")
        suggest_state["thread"] = th
        th.start()
        return {"started": True, "count": len(items)}

    # ------------------------------------------------------------------ kapanış

    @app.post("/api/v1/finance/closes/{year}/{month}")
    def finance_close(year: int, month: int, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, "ozellik:finans.kapanis", "Ay kapanışı")
        out = call(F.close_month, engine, tenant, user, year, month, body.get("not"))
        audit(engine, user, "approve", "finance_close", f"{year}-{int(month):02d}", f"{F.AY[int(month) - 1]} {year} kapandı",
              {"not": body.get("not"), "ozet": out.get("ozetHash")})
        return out

    @app.delete("/api/v1/finance/closes/{year}/{month}")
    def finance_reopen(year: int, month: int, request: Request, reason: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, "ozellik:finans.kapanis", "Ay kapanışı")
        out = call(F.reopen_month, engine, tenant, user, year, month, reason)
        audit(engine, user, "update", "finance_close", f"{year}-{int(month):02d}", f"{F.AY[int(month) - 1]} {year} yeniden açıldı",
              {"gerekce": reason})
        return out

    # ------------------------------------------------------------------ kârlılık

    @app.get("/api/v1/finance/profitability")
    def finance_profit(request: Request, by: str = "kitap", year: int | None = None, frm: int = 1, to: int = 12,
                       q: str = "", sort: str = "net", page: int = 0) -> dict[str, Any]:
        engine, _, _, _ = ctx(request)
        return call(F.profitability, engine, by=by, year=year_or_default(engine, year), frm=frm, to=to, q=q, sort=sort,
                    page=page, unit_costs=unit_costs, snapshot=snapshot())

    @app.get("/api/v1/finance/profitability/export.csv")
    def finance_profit_export(request: Request, by: str = "kitap", year: int | None = None, frm: int = 1, to: int = 12,
                              q: str = "", sort: str = "net") -> Response:
        engine, _, user, _ = ctx(request)
        y = year_or_default(engine, year)
        data = call(F.profitability, engine, by=by, year=y, frm=frm, to=to, q=q, sort=sort, unit_costs=unit_costs,
                    snapshot=snapshot(), all_rows=True)
        audit(engine, user, "run", "finance_export", f"{by}-{y}", "Kârlılık CSV", {"satir": data["total"]})
        return Response(F.profitability_csv(data).encode("utf-8"), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="karlilik-{by}-{y}-{frm:02d}-{to:02d}.csv"'})

    # ------------------------------------------------------------------ nakit (ozellik:finans.nakit)

    @app.get("/api/v1/finance/cash")
    def finance_cash(request: Request, budget: bool = False) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {**call(F.cash, engine, tenant, bool(budget)), "status": refresher.status()}

    @app.post("/api/v1/finance/cash/rebuild")
    def finance_cash_rebuild(request: Request) -> dict[str, Any]:
        engine, _, user, _ = ctx(request)
        started = refresher.rebuild_cash(user)
        audit(engine, user, "run", "finance_cash", None, "13 haftalık nakit tablosu", {"started": started})
        return {"started": started, **refresher.status()}

    @app.get("/api/v1/finance/cash/history")
    def finance_cash_history(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(F.cash_history, engine, tenant)

    # ------------------------------------------------------------------ bütçe–gerçekleşme (M46)

    @app.get("/api/v1/finance/budget")
    def finance_budget(request: Request, year: int | None = None) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(F.budget_view, engine, tenant, year_or_default(engine, year))

    @app.get("/api/v1/finance/notes")
    def finance_notes(request: Request, year: int | None = None) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {"items": F.notes(engine, tenant, year_or_default(engine, year))}

    @app.post("/api/v1/finance/notes")
    def finance_note_save(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(F.save_note, engine, tenant, user, body)
        audit(engine, user, "update", "finance_note", out["id"], out["anahtar"], {"metin": out["metin"][:200]})
        return out

    # ------------------------------------------------------------------ vergi takvimi

    @app.get("/api/v1/finance/tax-calendar")
    def finance_tax(request: Request, year: int | None = None) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return F.tax_list(engine, tenant, year)

    @app.post("/api/v1/finance/tax-calendar", status_code=201)
    def finance_tax_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(F.tax_create, engine, tenant, user, body)
        audit(engine, user, "create", "finance_tax", out["id"], f"{out['beyan']} · {out['sonGun']}", {"tutar": out["tutar"]})
        return out

    @app.post("/api/v1/finance/tax-calendar/copy")
    def finance_tax_copy(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        try:
            a, b = int(body.get("from")), int(body.get("to"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail={"code": "FINANCE", "message": "Kaynak ve hedef yıl zorunlu."}) from None
        out = call(F.tax_copy_year, engine, tenant, user, a, b)
        audit(engine, user, "create", "finance_tax", None, f"Vergi takvimi {a} → {b}", out)
        return out

    @app.patch("/api/v1/finance/tax-calendar/{tid}")
    def finance_tax_update(tid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out, diff = call(F.tax_update, engine, tenant, user, tid, body)
        if diff:
            audit(engine, user, "update", "finance_tax", tid, f"{out['beyan']} · {out['sonGun']}", diff)
        return out

    @app.delete("/api/v1/finance/tax-calendar/{tid}")
    def finance_tax_delete(tid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(F.tax_delete, engine, tenant, tid)
        audit(engine, user, "delete", "finance_tax", tid, f"{out['beyan']} · {out['sonGun']}", None)
        return {"ok": True}

    return refresher


def _last_closed_month(end: date | None) -> int | None:
    """Açılışta seçili ay: verinin son günü ay sonuysa o ay, değilse bir önceki ay (yılın içinde)."""
    if not end:
        return None
    nxt = date(end.year + (end.month == 12), end.month % 12 + 1, 1)
    if (nxt - end).days == 1:
        return end.month
    return max(1, end.month - 1)
