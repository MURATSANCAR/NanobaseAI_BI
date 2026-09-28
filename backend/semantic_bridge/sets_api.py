"""M53 Set, hediye ve promosyon uçları: /api/v1/marketing/sets*, /gift-offers*, /promo-items.

Sayfa kapısı `access.RULES` (`sayfa:pazarlama-set-hediye`); set/öneri/teklif yazma `ozellik:set.yaz`, kart listesi indirme
`ozellik:veri.disa-aktar` (`FEATURE_RULES`). Set onayı (fiyat dahil) açıkça verilen `ozellik:set.onay`, kurumsal teklif onayı
açıkça verilen `ozellik:set.teklif-onay` ile burada denetlenir (gönderen onaylayamaz → 409). Maliyet ve marj alanları
`ozellik:set.maliyet-gor` yoksa sunucu tarafında yanıttan çıkarılır. Zamanlayıcı (`timas-marketing-sets.timer`) yalnız
`POST /api/v1/marketing/sets/run-due`'yu çağırır.

Dış gönderim yok: teklif belgesi indirilir, kuruma satış gönderir. E-posta yalnız iç uyarı özetidir (`SETS_ALERT_RECIPIENTS`).
CRM'e, Logo'ya ve T-soft'a hiçbir şey yazılmaz.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
import time
from email.message import EmailMessage
from typing import Any, Optional

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import sets as S
from semantic_bridge import sets_docs as D
from semantic_bridge import sets_sources as src

log = logging.getLogger("semantic.sets.api")
P = "/api/v1/marketing"


def send_mail(subject: str, text: str, to: list[str]) -> str:
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
        log.warning("set/hediye uyarı e-postası gönderilemedi: %s", e)
        return "failed"


def register(app: Any, deps: dict[str, Any]) -> S.Refresher:
    """app.py'de bağlanır. `deps`: auth(request) → (engine, tenant, user, display) · require_caller(request) · can(user, key) ·
    is_admin(user) · audit(engine, user, action, kind, id, title, detail) · conf(key, default) · engine() · tenant() ·
    logo_file() · crm_file() · llm(priority) → LLM kapısı istemcisi ya da None."""
    auth, require_caller, can, is_admin, audit, conf = (deps[k] for k in ("auth", "require_caller", "can", "is_admin", "audit", "conf"))
    settings = lambda: S.settings_from(conf)  # noqa: E731
    schema = lambda: conf("CRM_SCHEMA", "Timas_MSCRM.dbo")  # noqa: E731
    refresher = S.Refresher(deps["engine"], deps["tenant"], deps["logo_file"], deps["crm_file"], schema, settings)
    firms_cache: dict[str, Any] = {"at": 0.0, "firms": None}

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        engine, tenant, user, display = auth(request)
        S.ensure(engine)
        return engine, tenant, user, display

    def has(user: str, key: str) -> bool:
        return is_admin(user) or can(user, key)

    def costs_ok(user: str) -> bool:
        return has(user, "ozellik:set.maliyet-gor")

    def shape(user: str, obj: Any) -> Any:
        return obj if costs_ok(user) else S.strip_costs(obj)

    def need(user: str, key: str, what: str) -> None:
        if not has(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except S.SetsError as e:
            raise HTTPException(status_code=e.status, detail={"code": "FORBIDDEN" if e.status == 403 else "SETS",
                                                              "message": str(e)}) from e
        except src.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "SETS_SOURCE", "retryable": True, "message": str(e)}) from e

    def crm():
        return src.runner(deps["crm_file"]())

    def logo():
        run = src.runner(deps["logo_file"]())
        if not firms_cache["firms"] or time.time() - firms_cache["at"] > 600:
            firms_cache.update(firms=src.firms_by_year(run), at=time.time())
        return run, firms_cache["firms"]

    def llm(priority_name: str) -> Any:
        from semantic_layer.runtime import llm_queue

        try:
            return deps["llm"](getattr(llm_queue, priority_name))
        except Exception as e:  # noqa: BLE001
            log.info("sets: model yok: %s", e)
            return None

    def set_audit(engine, user, action, s: dict[str, Any], detail: Any = None) -> None:
        audit(engine, user, action, "mkt_set", s.get("id"), s.get("ad"), detail)

    def offer_audit(engine, user, action, o: dict[str, Any], detail: Any = None) -> None:
        audit(engine, user, action, "mkt_gift_offer", o.get("id"), o.get("firmaAdi"), detail)

    # ------------------------------------------------------------------ genel

    @app.get(f"{P}/sets/meta")
    def sets_meta(request: Request) -> dict[str, Any]:
        engine, _, user, display = ctx(request)
        st = settings()
        admin = is_admin(user)
        return shape(user, {
            "types": S.TYPES, "sources": S.SOURCES, "statuses": S.STATUSES, "itemSources": S.ITEM_SOURCES,
            "suggestionTypes": S.SUGG_TYPES, "suggestionStatuses": S.SUGG_STATUS, "offerStatuses": S.OFFER_STATUS,
            "promoTypes": S.PROMO_TYPES, "costSource": st["costSource"], "costSourceLabel": src.COST_SOURCES.get(st["costSource"], st["costSource"]),
            "settings": {k: st[k] for k in ("componentSource", "listPriceSource", "salesLinetypes", "promoPrefix", "marginMinPct",
                                            "basketMonths", "basketMinOrders", "suggestSize", "suggestMaxSize", "giftOptions",
                                            "offerValidDays", "seasonLeadWeeks")},
            "giftTiers": [{"adet": a, "indirim": p} for a, p in st["giftTiers"]],
            **S.summary(engine, st), "status": refresher.status(),
            "me": {"username": user, "display": display, "admin": admin, "canWrite": has(user, "ozellik:set.yaz"),
                   "canApprove": has(user, "ozellik:set.onay"), "canApproveOffer": has(user, "ozellik:set.teklif-onay"),
                   "canSeeCost": costs_ok(user), "canExport": has(user, "ozellik:veri.disa-aktar")}})

    @app.get(f"{P}/sets/status")
    def sets_status(request: Request) -> dict[str, Any]:
        ctx(request)
        return refresher.status()

    @app.post(f"{P}/sets/refresh")
    def sets_refresh(request: Request, basket: bool = False) -> dict[str, Any]:
        engine, _, user, _ = ctx(request)
        started = refresher.start(basket=basket)
        audit(engine, user, "run", "mkt_set_refresh", None, "Set ve promosyon verileri yenilendi", {"started": started, "sepet": basket})
        return {"started": started, **refresher.status()}

    @app.post(f"{P}/sets/run-due")
    async def sets_run_due(request: Request, basket: Optional[bool] = None, history: Optional[bool] = None,
                           model: bool = True) -> dict[str, Any]:
        """Zamanlayıcı: CRM/Logo okuması, öneriler, uyarılar; ZEKİ AI öneri adları (gece, süre bütçeli); iç uyarı özeti."""
        require_caller(request)
        engine, tenant, st = deps["engine"](), deps["tenant"](), settings()
        S.ensure(engine)
        out: dict[str, Any] = {}
        if refresher.running():
            out["read"] = {"skipped": "başka bir okuma sürüyor"}
        else:
            out["read"] = await run_in_threadpool(lambda: refresher.run(basket=basket, history=history))
        if model:
            out["model"] = await run_in_threadpool(S.run_model_tasks, engine, st, llm("BATCH"), st["llmBudgetSec"])
        alerts = S.meta_get(engine, "alerts").get("items") or []
        if alerts and st["alertRecipients"]:
            link = (conf("ALERT_LINK", "") or "").split("/uyarilar")[0]
            text = "Set, hediye ve promosyon uyarıları:\n\n" + "\n".join(f"- {a['mesaj']}" for a in alerts)
            if link:
                text += f"\n\nEkran: {link}/pazarlama/set-hediye\n"
            out["mail"] = send_mail("Set ve hediye: uyarılar", text, st["alertRecipients"])
        return out

    # ------------------------------------------------------------------ yardımcı listeler (sabit yollar {id}'den önce)

    @app.get(f"{P}/sets/books")
    def sets_books(request: Request, q: str = "", page: int = 0) -> dict[str, Any]:
        engine, _, _, _ = ctx(request)
        return S.find_books(engine, settings(), q, page)

    @app.get(f"{P}/sets/basket-pairs")
    def sets_basket(request: Request, q: str = "", page: int = 0) -> dict[str, Any]:
        engine, _, _, _ = ctx(request)
        return S.basket_pairs(engine, q=q, page=page)

    @app.get(f"{P}/sets/suggestions")
    def sets_suggestions(request: Request, yas: Optional[int] = None, tema: str = "", butce_min: Optional[float] = None,
                         butce_max: Optional[float] = None, tur: str = "", durum: str = "yeni", page: int = 0) -> dict[str, Any]:
        engine, _, user, _ = ctx(request)
        return shape(user, call(S.list_suggestions, engine, settings(), yas=yas, tema=tema, butce_min=butce_min, butce_max=butce_max,
                                tur=tur, durum=durum, page=page))

    @app.post(f"{P}/sets/suggestions/{{sid}}/adopt", status_code=201)
    def sets_suggestion_adopt(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(S.adopt_suggestion, engine, settings(), tenant, user, sid)
        set_audit(engine, user, "create", out, {"oneri": sid, "kaynak": "ZEKİ AI önerisi"})
        return shape(user, out)

    @app.post(f"{P}/sets/suggestions/{{sid}}/dismiss")
    def sets_suggestion_dismiss(sid: str, request: Request) -> dict[str, Any]:
        engine, _, user, _ = ctx(request)
        out = call(S.dismiss_suggestion, engine, user, sid)
        audit(engine, user, "reject", "mkt_suggestion", sid, out["ad"], None)
        return out

    # ------------------------------------------------------------------ setler

    @app.get(f"{P}/sets")
    def sets_list(request: Request, durum: str = "", tur: str = "", sezon: str = "", kanal: str = "", q: str = "",
                  sort: str = "ciro", page: int = 0) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return shape(user, S.list_sets(engine, tenant, durum=durum, tur=tur, sezon=sezon, kanal=kanal, q=q, sort=sort, page=page))

    @app.post(f"{P}/sets", status_code=201)
    def sets_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(S.create_set, engine, settings(), tenant, user, body)
        set_audit(engine, user, "create", out, {"bilesen": out["bilesenSayisi"], "fiyat": out["setFiyati"]})
        return shape(user, out)

    @app.get(f"{P}/sets/{{set_id}}")
    def sets_get(set_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return shape(user, call(S.get_set, engine, tenant, set_id))

    @app.patch(f"{P}/sets/{{set_id}}")
    def sets_update(set_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out, diff = call(S.update_set, engine, settings(), tenant, user, set_id, body, S.seasons(engine))
        if diff:
            set_audit(engine, user, "update", out, diff)
        return shape(user, out)

    @app.delete(f"{P}/sets/{{set_id}}")
    def sets_delete(set_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(S.delete_set, engine, tenant, set_id)
        set_audit(engine, user, "delete", out)
        return {"ok": True}

    @app.put(f"{P}/sets/{{set_id}}/items")
    def sets_items(set_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(S.put_items, engine, settings(), tenant, set_id, body.get("bilesenler"))
        set_audit(engine, user, "update", out, {"bilesenler": [(i["stok"], i["adet"]) for i in out["bilesenler"] or []]})
        return shape(user, out)

    @app.post(f"{P}/sets/{{set_id}}/price")
    def sets_price(set_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Hesap (kaydetmeden): set fiyatı ya da indirim, ambalaj, bileşenler → liste toplamı, KDV ayrışması, marj."""
        engine, tenant, user, _ = ctx(request)
        return shape(user, call(S.price_preview, engine, settings(), tenant, set_id, body))

    @app.post(f"{P}/sets/{{set_id}}/submit")
    def sets_submit(set_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(S.submit_set, engine, settings(), tenant, user, set_id)
        set_audit(engine, user, "update", out, {"durum": "onayda", "marjOrani": out.get("marjOrani")})
        return shape(user, out)

    @app.post(f"{P}/sets/{{set_id}}/withdraw")
    def sets_withdraw(set_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(S.withdraw_set, engine, tenant, user, set_id)
        set_audit(engine, user, "update", out, {"durum": "taslak", "neden": "onaydan çekildi"})
        return shape(user, out)

    @app.post(f"{P}/sets/{{set_id}}/approve")
    def sets_approve(set_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, "ozellik:set.onay", "Set onayı")
        out = call(S.decide_set, engine, tenant, user, set_id, True, body.get("note"))
        set_audit(engine, user, "approve", out, {"fiyat": out.get("setFiyati"), "not": body.get("note")})
        return shape(user, out)

    @app.post(f"{P}/sets/{{set_id}}/reject")
    def sets_reject(set_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, "ozellik:set.onay", "Set onayı")
        out = call(S.decide_set, engine, tenant, user, set_id, False, body.get("note"))
        set_audit(engine, user, "reject", out, {"not": body.get("note")})
        return shape(user, out)

    @app.post(f"{P}/sets/{{set_id}}/text")
    async def sets_text(set_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        """ZEKİ AI taslağı: `kind` = tanitim (e-ticaret açıklaması, SEO önerisi olarak) | brief (ambalaj ve sunum)."""
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        kind = str(body.get("kind") or "tanitim")
        text, dropped = await run_in_threadpool(call, S.draft_text, engine, llm("NORMAL"), tenant, set_id, kind)
        audit(engine, user, "update", "mkt_set", set_id, None, {"zekiTaslak": kind, "dusenCumle": dropped})
        return {"kind": kind, "text": text, "dusenSayisi": dropped}

    @app.get(f"{P}/sets/{{set_id}}/card-todo")
    def sets_card_todo(set_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(S.card_todo, engine, settings(), tenant, set_id)

    @app.get(f"{P}/sets/{{set_id}}/card-todo.csv")
    def sets_card_todo_csv(set_id: str, request: Request) -> Response:
        engine, tenant, user, _ = ctx(request)
        todo = call(S.card_todo, engine, settings(), tenant, set_id)
        audit(engine, user, "run", "mkt_set_export", set_id, todo["ad"], {"bicim": "csv"})
        return Response(S.card_todo_csv(todo).encode("utf-8"), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="acilacak-kart-{set_id}.csv"'})

    @app.get(f"{P}/sets/{{set_id}}/card-todo.pdf")
    def sets_card_todo_pdf(set_id: str, request: Request) -> Response:
        engine, tenant, user, _ = ctx(request)
        todo = call(S.card_todo, engine, settings(), tenant, set_id)
        data = D.card_pdf(todo, settings()["company"])
        audit(engine, user, "run", "mkt_set_export", set_id, todo["ad"], {"bicim": "pdf"})
        return Response(data, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="acilacak-kart-{set_id}.pdf"'})

    @app.post(f"{P}/sets/{{set_id}}/link")
    def sets_link(set_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        """CRM'de açılan kartla eşleme: stok kodu CRM'de (etkin, «Set» türünde) doğrulanır. CRM'e yazılmaz."""
        engine, tenant, user, _ = ctx(request)
        code = str(body.get("stokKodu") or "").strip()
        if not src.code_ok(code):
            raise HTTPException(status_code=400, detail={"code": "SETS", "message": "Stok kodu gerekli."})
        card = call(src.read_card, crm(), schema(), code)
        out = call(S.link_set, engine, tenant, set_id, code, card)
        set_audit(engine, user, "update", out, {"crmKart": code})
        return shape(user, out)

    @app.get(f"{P}/sets/{{set_id}}/effect")
    def sets_effect(set_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(S.effect, engine, tenant, set_id)

    # ------------------------------------------------------------------ kurumsal hediye teklifi

    @app.get(f"{P}/gift-offers")
    def offers_list(request: Request, durum: str = "", q: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return shape(user, S.list_offers(engine, tenant, durum=durum, q=q, page=page))

    @app.get(f"{P}/gift-offers/accounts")
    def offers_accounts(request: Request, q: str = "", page: int = 0) -> dict[str, Any]:
        """CRM firma araması (canlı okuma, sayfalı)."""
        ctx(request)
        if len(q.strip()) < 2:
            return {"items": [], "total": 0, "page": 0, "pageSize": 50}
        return call(src.search_accounts, crm(), schema(), q.strip(), max(0, page), 50)

    @app.get(f"{P}/gift-offers/accounts/{{account_id}}/history")
    def offers_account_history(account_id: str, request: Request) -> dict[str, Any]:
        """Firmaya geçmiş hediye talepleri (CRM; kişi bilgisi seçilmez)."""
        ctx(request)
        return {"items": call(src.read_gift_history, crm(), schema(), account_id)}

    @app.post(f"{P}/gift-offers", status_code=201)
    def offers_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        account = call(src.read_account, crm(), schema(), str(body.get("firmaId") or "").strip())
        out = call(S.create_offer, engine, settings(), tenant, user, body, account)
        offer_audit(engine, user, "create", out, {"adet": out["adet"], "butce": out["kisiBasiButce"], "secenek": len(out["secenekler"])})
        return shape(user, out)

    @app.get(f"{P}/gift-offers/{{oid}}")
    def offers_get(oid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return shape(user, call(S.get_offer, engine, tenant, oid))

    @app.patch(f"{P}/gift-offers/{{oid}}")
    def offers_update(oid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(S.update_offer, engine, settings(), tenant, user, oid, body)
        offer_audit(engine, user, "update", out, {k: body[k] for k in body if k != "mektup"} | ({"mektup": "düzenlendi"} if "mektup" in body else {}))
        return shape(user, out)

    @app.post(f"{P}/gift-offers/{{oid}}/letter")
    async def offers_letter(oid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        text, dropped = await run_in_threadpool(call, S.draft_letter, engine, llm("NORMAL"), settings(), tenant, oid)
        audit(engine, user, "update", "mkt_gift_offer", oid, None, {"zekiTaslak": "mektup", "dusenCumle": dropped})
        return {"text": text, "dusenSayisi": dropped}

    @app.post(f"{P}/gift-offers/{{oid}}/submit")
    def offers_submit(oid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(S.submit_offer, engine, tenant, user, oid)
        offer_audit(engine, user, "update", out, {"durum": "onayda"})
        return shape(user, out)

    @app.post(f"{P}/gift-offers/{{oid}}/withdraw")
    def offers_withdraw(oid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(S.submit_offer, engine, tenant, user, oid, withdraw=True)
        offer_audit(engine, user, "update", out, {"durum": "taslak"})
        return shape(user, out)

    @app.post(f"{P}/gift-offers/{{oid}}/approve")
    def offers_approve(oid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, "ozellik:set.teklif-onay", "Kurumsal teklif onayı")
        out = call(S.decide_offer, engine, tenant, user, oid, True, body.get("note"))
        offer_audit(engine, user, "approve", out, {"not": body.get("note")})
        return shape(user, out)

    @app.post(f"{P}/gift-offers/{{oid}}/reject")
    def offers_reject(oid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, "ozellik:set.teklif-onay", "Kurumsal teklif onayı")
        out = call(S.decide_offer, engine, tenant, user, oid, False, body.get("note"))
        offer_audit(engine, user, "reject", out, {"not": body.get("note")})
        return shape(user, out)

    @app.get(f"{P}/gift-offers/{{oid}}/document.pdf")
    def offers_pdf(oid: str, request: Request) -> Response:
        engine, tenant, user, _ = ctx(request)
        o = call(S.get_offer, engine, tenant, oid)
        data = D.offer_pdf(o, settings()["company"])
        audit(engine, user, "run", "mkt_gift_offer_doc", oid, o["firmaAdi"], {"taslak": o["durum"] not in D.FINAL})
        return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="teklif-{oid}.pdf"'})

    @app.get(f"{P}/gift-offers/{{oid}}/handoff")
    def offers_handoff(oid: str, request: Request) -> dict[str, Any]:
        """M32 kurumsal teklif akışına bağlantı noktası (seçili seçeneklerin satırları)."""
        engine, tenant, _, _ = ctx(request)
        return call(S.handoff, engine, tenant, oid)

    # ------------------------------------------------------------------ promosyon ürünleri

    @app.get(f"{P}/promo-items")
    def promo_items(request: Request, stok: str = "", tur: str = "", q: str = "", page: int = 0) -> dict[str, Any]:
        engine, _, _, _ = ctx(request)
        return S.list_promo(engine, stok=stok, tur=tur, q=q, page=page)

    return refresher
