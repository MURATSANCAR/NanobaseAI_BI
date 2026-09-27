"""M32 Kurumsal satış ve B2B uçları: /api/v1/corporate/*.

Sayfa kapısı `access.RULES` (`sayfa:kurumsal-satis`); fırsat/paket/teklif yazma `ozellik:kurumsal.teklif`, bayi paneli
`ozellik:kurumsal.b2b`, tema onayı `ozellik:kurumsal.tema-onay`, belge ve CSV `ozellik:veri.disa-aktar` (`FEATURE_RULES`).
Teklif onayı açıkça verilen `ozellik:kurumsal.teklif-onay` ile burada denetlenir (gönderen onaylayamaz). Başkasının fırsatını
görmek `ozellik:kurumsal.herkesinki` ister. Zamanlayıcı (`timas-corporate.timer`) yalnız `POST /api/v1/corporate/run-due`'yu çağırır.

Dış gönderim yok (kullanıcı kararı 2026-09-28): teklif belgesi indirilir, kuruma temsilci gönderir. E-posta yalnız iç
bildirimdir (onay bekleyen teklif, haftalık bayi özeti) ve alıcıları yönetim ekranındaki ayardır; boşsa gönderilmez.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
import time
from email.message import EmailMessage
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import corporate_sales as C
from semantic_bridge import corporate_sales_docs as D
from semantic_bridge import corporate_sales_sources as src

log = logging.getLogger("semantic.corporate.api")
P = "/api/v1/corporate"


def send_mail(subject: str, text: str, to: list[str], attachments: Optional[list[tuple[str, bytes, str]]] = None) -> str:
    from semantic_bridge.alerts import smtp_settings

    if not to:
        return "no_recipient"
    cfg = smtp_settings()
    if not cfg:
        return "no_smtp"
    try:
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, cfg["sender"], ", ".join(to)
        msg.set_content(text)
        for name, data, mime in attachments or []:
            main, _, sub = mime.partition("/")
            msg.add_attachment(data, maintype=main, subtype=sub or "octet-stream", filename=name)
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
        log.warning("kurumsal satış e-postası gönderilemedi: %s", e)
        return "failed"


def register(app: Any, deps: dict[str, Any]) -> C.Refresher:
    """app.py'de bağlanır. `deps`: auth(request) → (engine, tenant, user, display) · require_caller(request) · can(user, key) ·
    is_admin(user) · audit(engine, user, action, kind, id, title, detail) · conf(key, default) · engine() · tenant() ·
    logo_file() · crm_file() · llm(priority) → LLM kapısı istemcisi ya da None."""
    auth, require_caller, can, is_admin, audit, conf = (deps[k] for k in ("auth", "require_caller", "can", "is_admin", "audit", "conf"))
    settings = lambda: C.settings_from(conf)  # noqa: E731
    schema = lambda: conf("CRM_SCHEMA", "Timas_MSCRM.dbo")  # noqa: E731
    refresher = C.Refresher(deps["engine"], deps["tenant"], deps["logo_file"], deps["crm_file"], schema, settings)
    firms_cache: dict[str, Any] = {"at": 0.0, "firms": None}

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        engine, tenant, user, display = auth(request)
        C.ensure(engine)
        return engine, tenant, user, display

    def rights(user: str) -> tuple[bool, bool]:
        admin = is_admin(user)
        return admin or can(user, "ozellik:kurumsal.herkesinki"), admin or can(user, "ozellik:kurumsal.teklif-onay")

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except C.CorporateError as e:
            raise HTTPException(status_code=e.status, detail={"code": "FORBIDDEN" if e.status == 403 else "CORPORATE",
                                                              "message": str(e)}) from e
        except src.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "CORPORATE_SOURCE", "retryable": True, "message": str(e)}) from e

    def logo():
        """Anlık okuma (bayi ayrıntısı) için Logo bağlantısı ve yıl → firma eşlemesi (10 dk bellekte)."""
        run = src.runner(deps["logo_file"]())
        if not firms_cache["firms"] or time.time() - firms_cache["at"] > 600:
            firms_cache.update(firms=src.firms_by_year(run), at=time.time())
        return run, firms_cache["firms"]

    def quote_audit(engine, user, action, q: dict[str, Any], detail: Any = None) -> None:
        audit(engine, user, action, "corp_quote", q["id"], f"{(q.get('firsat') or {}).get('kurum') or ''} · sürüm {q['surum']}", detail)

    def opp_audit(engine, user, action, o: dict[str, Any], detail: Any = None) -> None:
        audit(engine, user, action, "corp_opportunity", o["id"], f"{o['kurum']} · {o['ad']}", detail)

    def csv_response(text: str, name: str) -> Response:
        return Response(text.encode("utf-8"), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    # ------------------------------------------------------------------ genel

    @app.get(f"{P}/meta")
    def corporate_meta(request: Request) -> dict[str, Any]:
        engine, _, user, display = ctx(request)
        st = settings()
        see_all, approver = rights(user)
        admin = is_admin(user)
        return {"stages": C.STAGES, "openStages": list(C.OPEN_STAGES), "segments": C.SEGMENTS, "segmentSources": C.SEGMENT_SOURCES,
                "loss": C.LOSS, "quoteStatus": C.QUOTE_STATUS, "themeStatus": C.THEME_STATUS, "reminderStatus": C.REMINDER_STATUS,
                "vocabulary": C.vocabulary(engine, st), "costSource": st["costSource"],
                "costSourceLabel": src.COST_SOURCES.get(st["costSource"], st["costSource"]),
                "settings": {k: st[k] for k in ("channel", "dealerChannels", "discountApprovalPct", "marginMinPct", "reminderLeadDays",
                                                "silentDays", "b2bDays", "highlightDays", "alternatives", "quoteValidDays", "historyYears")},
                "volume": C.meta_get(engine, "volume"), "volumeTiers": st["volumeTiers"], "status": refresher.status(),
                "me": {"username": user, "display": display, "admin": admin, "seeAll": see_all, "canApprove": approver,
                       "canQuote": admin or can(user, "ozellik:kurumsal.teklif"), "canB2b": admin or can(user, "ozellik:kurumsal.b2b"),
                       "canTheme": admin or can(user, "ozellik:kurumsal.tema-onay"),
                       "canExport": admin or can(user, "ozellik:veri.disa-aktar")}}

    @app.get(f"{P}/summary")
    def corporate_summary(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        see_all, _ = rights(user)
        return call(C.summary, engine, tenant, user, see_all, settings())

    @app.get(f"{P}/status")
    def corporate_status(request: Request) -> dict[str, Any]:
        ctx(request)
        return refresher.status()

    @app.post(f"{P}/refresh")
    def corporate_refresh(request: Request) -> dict[str, Any]:
        engine, _, user, _ = ctx(request)
        started = refresher.start()
        audit(engine, user, "run", "corp_refresh", None, "Kurumsal satış verileri yenilendi", {"started": started})
        return {"started": started, **refresher.status()}

    @app.post(f"{P}/run-due")
    async def corporate_run_due(request: Request, weekly: bool = False, model: bool = True) -> dict[str, Any]:
        """Zamanlayıcı: Logo/CRM okuması, dönemsel hatırlatma, sessiz bayi listesi, ZEKİ AI önerileri; `weekly=1` ise
        haftalık bayi özeti iç alıcılara."""
        require_caller(request)
        engine, tenant, st = deps["engine"](), deps["tenant"](), settings()
        C.ensure(engine)
        out: dict[str, Any] = {}
        if refresher.running():
            out["read"] = {"skipped": "başka bir okuma sürüyor"}
        else:
            out["read"] = await run_in_threadpool(refresher.run)
        if model:
            from semantic_layer.runtime.llm_queue import BATCH

            llm = None
            try:
                llm = deps["llm"](BATCH)
            except Exception as e:  # noqa: BLE001
                log.info("corporate: model yok: %s", e)
            out["model"] = await run_in_threadpool(C.run_model_tasks, engine, tenant, st, llm, st["llmBudgetSec"])
        if weekly:
            data = C.dealer_rows(engine, gun=st["silentDays"], durum="sessiz")
            by = {k: sum(1 for i in data["items"] if i["sinif"] == k) for k in ("A", "B", "C")}
            link = (conf("ALERT_LINK", "") or "").split("/uyarilar")[0]
            text = (f"Bayi kanalında ({', '.join(st['dealerChannels'])}) {st['silentDays']} gündür satış faturası olmayan ve önceki "
                    f"12 ayda alımı olan {data['total']} bayi var (A: {by['A']}, B: {by['B']}, C: {by['C']}).\n"
                    f"Logo verisi {data['dataEnd'] or '—'} tarihine kadar okunmuştur. Listenin tamamı ektedir.\n"
                    + (f"\nEkran: {link}/kurumsal-satis?sekme=bayi\n" if link else ""))
            out["weekly"] = send_mail("Haftalık bayi özeti: sipariş vermeyen bayiler", text, st["b2bReportTo"],
                                      [("sessiz-bayiler.csv", C.dealers_csv(data).encode("utf-8"), "text/csv")])
        return out

    # ------------------------------------------------------------------ kurumlar

    @app.get(f"{P}/accounts")
    def corporate_accounts(request: Request, q: str = "", segment: str = "", temsilci: str = "", sort: str = "ciro",
                           page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(C.list_accounts, engine, tenant, q=q, segment=segment, temsilci=temsilci, sort=sort, page=max(0, page))

    @app.get(f"{P}/accounts/{{ref}}")
    def corporate_account(ref: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(C.account_detail, engine, tenant, ref)

    @app.patch(f"{P}/accounts/{{ref}}")
    def corporate_account_update(ref: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(C.set_segment, engine, tenant, user, ref, body)
        audit(engine, user, "update", "corp_account", ref, ref, {"segment": {"once": out["onceki"], "sonra": out["segment"]}})
        return call(C.account_detail, engine, tenant, ref)

    # ------------------------------------------------------------------ kitaplar, temalar, paket

    @app.get(f"{P}/books")
    def corporate_books(request: Request, q: str = "", page: int = 0) -> dict[str, Any]:
        engine, _, _, _ = ctx(request)
        return call(C.find_books, engine, q, limit_page=max(0, page))

    @app.get(f"{P}/themes")
    def corporate_themes(request: Request, durum: str = "onerildi", q: str = "", tema: str = "", page: int = 0) -> dict[str, Any]:
        engine, _, _, _ = ctx(request)
        return call(C.list_themes, engine, settings(), durum=durum, q=q, tema=tema, page=max(0, page))

    @app.post(f"{P}/themes/{{stok}}/approve")
    def corporate_theme_decide(stok: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, _, user, _ = ctx(request)
        out = call(C.set_theme, engine, settings(), user, stok, body.get("tema"), str(body.get("karar") or "onayla"))
        audit(engine, user, "approve" if out["karar"] == "onayla" else ("reject" if out["karar"] == "reddet" else "update"),
              "corp_theme", f"{stok}:{out['tema']}", out["tema"], {"karar": out["karar"]})
        return out

    @app.post(f"{P}/packages/suggest")
    async def corporate_packages(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, _, _, _ = await run_in_threadpool(ctx, request)
        return await run_in_threadpool(call, C.suggest_packages, engine, settings(), body)

    # ------------------------------------------------------------------ fırsatlar

    @app.get(f"{P}/opportunities")
    def corporate_opps(request: Request, asama: str = "", sahip: str = "", q: str = "", acik: bool = False) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        see_all, approver = rights(user)
        return call(C.list_opportunities, engine, tenant, user, see_all, approver, asama=asama, sahip=sahip, q=q, acik=acik)

    @app.get(f"{P}/pipeline/summary")
    def corporate_pipeline_summary(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        see_all, _ = rights(user)
        return call(C.pipeline_summary, engine, tenant, user, see_all)

    @app.post(f"{P}/opportunities", status_code=201)
    def corporate_opp_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(C.create_opportunity, engine, tenant, user, body)
        opp_audit(engine, user, "create", out, {"asama": out["asama"], "deger": out["deger"]})
        return out

    @app.get(f"{P}/opportunities/{{opp_id}}")
    def corporate_opp(opp_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        see_all, approver = rights(user)
        return call(C.opportunity, engine, tenant, user, see_all, approver, opp_id)

    @app.patch(f"{P}/opportunities/{{opp_id}}")
    def corporate_opp_update(opp_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        see_all, _ = rights(user)
        out, diff = call(C.update_opportunity, engine, tenant, user, see_all, opp_id, body)
        if diff:
            opp_audit(engine, user, "update", out, diff)
        return out

    # ------------------------------------------------------------------ teklifler

    @app.post(f"{P}/opportunities/{{opp_id}}/quotes", status_code=201)
    def corporate_quote_create(opp_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        see_all, _ = rights(user)
        out = call(C.create_quote, engine, settings(), tenant, user, see_all, opp_id, body)
        quote_audit(engine, user, "create", out, {"kalem": len(out["kalemler"]), "tutar": out["toplamNet"], "kopya": body.get("kopya")})
        return out

    @app.get(f"{P}/approvals")
    def corporate_approvals(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        _, approver = rights(user)
        if not approver:
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Teklif onayı rolünüzde yok."})
        return {"items": C.approval_queue(engine, tenant)}

    @app.get(f"{P}/quotes/{{qid}}")
    def corporate_quote(qid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        see_all, approver = rights(user)
        return call(C.quote, engine, tenant, user, see_all, approver, qid)

    @app.patch(f"{P}/quotes/{{qid}}")
    def corporate_quote_update(qid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        see_all, _ = rights(user)
        out = call(C.update_quote, engine, settings(), tenant, user, see_all, qid, body)
        quote_audit(engine, user, "update", out, {k: ("…" if k in ("mektup", "notlar") else body[k]) for k in body
                                                  if k in ("kalemler", "mektup", "notlar", "paketAdet", "gecerlilikGun")})
        return out

    @app.delete(f"{P}/quotes/{{qid}}")
    def corporate_quote_delete(qid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        see_all, _ = rights(user)
        out = call(C.delete_quote, engine, tenant, user, see_all, qid)
        audit(engine, user, "delete", "corp_quote", qid, f"sürüm {out['surum']}", None)
        return {"ok": True}

    @app.post(f"{P}/quotes/{{qid}}/submit")
    def corporate_quote_submit(qid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        see_all, _ = rights(user)
        st = settings()
        out = call(C.submit_quote, engine, st, tenant, user, see_all, qid)
        quote_audit(engine, user, "update", out, {"durum": out["durum"], "onayNedenleri": out["onayNedenleri"]})
        if out["durum"] == "onayda" and st["approvalRecipients"]:
            link = (conf("ALERT_LINK", "") or "").split("/uyarilar")[0]
            reasons = "\n".join(f"- {r['metin']}" for r in out["onayNedenleri"])
            f = out["firsat"]
            out["bildirim"] = send_mail(
                f"Onay bekleyen kurumsal teklif: {f['kurum']}",
                f"{f['kurum']} · {f['ad']} teklifi (sürüm {out['surum']}, {D.money(out['toplamNet'])}) onayınızı bekliyor.\n"
                f"Gönderen: {user}\nNeden:\n{reasons}\n" + (f"\nEkran: {link}/kurumsal-satis/firsat/{f['id']}\n" if link else ""),
                st["approvalRecipients"])
        return out

    @app.post(f"{P}/quotes/{{qid}}/withdraw")
    def corporate_quote_withdraw(qid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        see_all, _ = rights(user)
        out = call(C.withdraw_quote, engine, tenant, user, see_all, qid)
        quote_audit(engine, user, "update", out, {"durum": "taslak", "neden": "geri çekildi"})
        return out

    def decide(qid: str, body: dict[str, Any], request: Request, approve: bool) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        _, approver = rights(user)
        if not approver:
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Teklif onayı rolünüzde yok."})
        out = call(C.decide_quote, engine, tenant, user, qid, approve, body.get("note"))
        quote_audit(engine, user, "approve" if approve else "reject", out, {"not": body.get("note")})
        return out

    @app.post(f"{P}/quotes/{{qid}}/approve")
    def corporate_quote_approve(qid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        return decide(qid, body, request, True)

    @app.post(f"{P}/quotes/{{qid}}/reject")
    def corporate_quote_reject(qid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        return decide(qid, body, request, False)

    @app.post(f"{P}/quotes/{{qid}}/sent")
    def corporate_quote_sent(qid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        see_all, _ = rights(user)
        out = call(C.mark_sent, engine, tenant, user, see_all, qid)
        quote_audit(engine, user, "update", out, {"durum": "gonderildi"})
        return out

    @app.post(f"{P}/quotes/{{qid}}/result")
    def corporate_quote_result(qid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        see_all, _ = rights(user)
        out = call(C.record_result, engine, tenant, user, see_all, qid, body)
        quote_audit(engine, user, "update", out, {"durum": out["durum"], "neden": body.get("neden")})
        return out

    @app.post(f"{P}/quotes/{{qid}}/letter")
    async def corporate_quote_letter(qid: str, request: Request) -> dict[str, Any]:
        """ZEKİ AI mektup taslağı. Kaydedilmez; temsilci düzenleyip kaydeder. Rakam modelden gelmez."""
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        see_all, approver = rights(user)
        q = await run_in_threadpool(call, C.quote, engine, tenant, user, see_all, approver, qid)
        try:
            llm = deps["llm"](None)
        except Exception:  # noqa: BLE001
            llm = None
        if llm is None:
            raise HTTPException(status_code=503, detail={"code": "CORPORATE", "message": "ZEKİ AI bu kurulumda bağlı değil."})
        try:
            text = await run_in_threadpool(C.draft_letter, llm, settings(), q["firsat"], q["kalemler"])
        except Exception as e:  # noqa: BLE001
            log.warning("corporate: mektup taslağı alınamadı: %s", e)
            raise HTTPException(status_code=503, detail={"code": "CORPORATE", "retryable": True,
                                                         "message": "ZEKİ AI şu anda cevap vermiyor; birazdan tekrar deneyin."}) from e
        return {"mektup": text}

    @app.get(f"{P}/quotes/{{qid}}/document.pdf")
    def corporate_quote_pdf(qid: str, request: Request) -> Response:
        engine, tenant, user, _ = ctx(request)
        see_all, approver = rights(user)
        q = call(C.quote, engine, tenant, user, see_all, approver, qid)
        data = D.pdf(q, settings()["company"])
        audit(engine, user, "run", "corp_quote_export", qid, f"Teklif PDF · {D.quote_no(q)}", None)
        return Response(data, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="teklif-{D.quote_no(q)}.pdf"'})

    @app.get(f"{P}/quotes/{{qid}}/document.xlsx")
    def corporate_quote_xlsx(qid: str, request: Request) -> Response:
        engine, tenant, user, _ = ctx(request)
        see_all, approver = rights(user)
        q = call(C.quote, engine, tenant, user, see_all, approver, qid)
        data = D.xlsx(q, settings()["company"])
        audit(engine, user, "run", "corp_quote_export", qid, f"Teklif Excel · {D.quote_no(q)}", None)
        return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="teklif-{D.quote_no(q)}.xlsx"'})

    # ------------------------------------------------------------------ hatırlatmalar

    @app.get(f"{P}/reminders")
    def corporate_reminders(request: Request, ay: str = "", durum: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(C.list_reminders, engine, tenant, settings(), ay=ay, durum=durum)

    @app.patch(f"{P}/reminders/{{rid}}")
    def corporate_reminder_update(rid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(C.update_reminder, engine, tenant, user, rid, body)
        audit(engine, user, "update", "corp_reminder", rid, f"{out['unvan']} · {out['donemAyi']}", {"durum": out["durum"]})
        return out

    @app.post(f"{P}/reminders/{{rid}}/opportunity", status_code=201)
    def corporate_reminder_opp(rid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(C.opportunity_from_reminder, engine, tenant, user, rid, body)
        opp_audit(engine, user, "create", out, {"kaynak": "hatırlatma", "hatirlatma": rid})
        return out

    # ------------------------------------------------------------------ bayi paneli

    @app.get(f"{P}/b2b/dealers")
    def corporate_dealers(request: Request, durum: str = "sessiz", gun: int = 0, sinif: str = "", kanal: str = "",
                          q: str = "") -> dict[str, Any]:
        engine, _, _, _ = ctx(request)
        st = settings()
        return call(C.dealer_rows, engine, gun=gun if gun > 0 else st["silentDays"], durum=durum, sinif=sinif, kanal=kanal, q=q)

    @app.get(f"{P}/b2b/dealers.csv")
    def corporate_dealers_csv(request: Request, durum: str = "sessiz", gun: int = 0, sinif: str = "", kanal: str = "",
                              q: str = "") -> Response:
        engine, _, user, _ = ctx(request)
        st = settings()
        data = call(C.dealer_rows, engine, gun=gun if gun > 0 else st["silentDays"], durum=durum, sinif=sinif, kanal=kanal, q=q)
        audit(engine, user, "run", "corp_dealers_export", None, "Bayi listesi CSV", {"durum": durum, "satir": data["total"]})
        return csv_response(C.dealers_csv(data), f"bayiler-{durum or 'hepsi'}.csv")

    @app.get(f"{P}/b2b/dealers/{{kod}}")
    async def corporate_dealer(kod: str, request: Request) -> dict[str, Any]:
        engine, _, _, _ = await run_in_threadpool(ctx, request)

        def work():
            run, firms = logo()
            return C.dealer_detail(engine, run, firms, kod)

        return await run_in_threadpool(call, work)

    @app.get(f"{P}/b2b/highlights")
    def corporate_highlights(request: Request) -> dict[str, Any]:
        engine, _, _, _ = ctx(request)
        return call(C.highlights, engine, settings())

    @app.get(f"{P}/b2b/highlights.csv")
    def corporate_highlights_csv(request: Request) -> Response:
        engine, _, user, _ = ctx(request)
        data = call(C.highlights, engine, settings())
        audit(engine, user, "run", "corp_highlights_export", None, "Öne çıkarılacak kitaplar CSV", {"satir": data["total"]})
        return csv_response(C.highlights_csv(data), "one-cikarilacak-kitaplar.csv")

    return refresher
