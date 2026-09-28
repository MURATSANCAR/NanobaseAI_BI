"""M18 uçları: /api/v1/marketing/months/* (aylık plan), /api/v1/marketing/foy* (satış föyü), sözleşme
/api/v1/marketing/contract/month/{YYYY-MM}. `api.register` içinden çağrılır; app.py değişmez.

Sayfa kapısı `access.RULES`: ay planı `sayfa:pazarlama-aylik`; föy `sayfa:pazarlama-foy` ya da `sayfa:pazarlama-aylik`
(saha temsilcisinin rolünde yalnız föy sayfası olur). Yazma `ozellik:pazarlama.plan-yaz` / `ozellik:pazarlama.foy-yaz`
(`FEATURE_RULES`); açıkça verilen yetkiler ucun içinde: ay planı onayı `plan-onay`, üst onay `butce-ust-onay`, föy onayı
`foy-onay`, föy paketini e-postayla gönderme `foy-gonder`. Föy PDF'i `veri.disa-aktar` istemez (saha temsilcisinin asıl
işi; istisna yetki kataloğunda yazılı). Bütçe tutarları `butce-gor` olmayana gitmez.

Zamanlayıcı ayrı birim değildir: mevcut `timas-marketing.timer` (her gün) `POST /api/v1/marketing/run-due`'yu çağırır,
o da `run_due` kancasıyla bu modülün günlük işini koşturur (15'inde taslak, föy CRM denetimi, 20'sinde föy hatırlatması,
ay başı + N iş günü özeti, pazartesi sapma özeti). `POST /api/v1/marketing/months/run-due` aynı işi elle tetikler (SYSTEM).
"""
from __future__ import annotations

import io
import logging
import zipfile
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge.marketing import core as C
from semantic_bridge.marketing import foy as F
from semantic_bridge.marketing import foy_pdf as FP
from semantic_bridge.marketing import monthly as M
from semantic_bridge.marketing import monthly_gaps as MG
from semantic_bridge.marketing import plans as P
from semantic_bridge.marketing.sources import SourceError
from semantic_layer.runtime.llm_queue import BATCH, NORMAL

log = logging.getLogger("semantic.marketing.monthly_api")

R = "/api/v1/marketing"
PAGE_MONTH = "sayfa:pazarlama-aylik"
PAGE_FOY = "sayfa:pazarlama-foy"
F_WRITE = "ozellik:pazarlama.plan-yaz"
F_BUDGET = "ozellik:pazarlama.butce-gor"
F_APPROVE = "ozellik:pazarlama.plan-onay"
F_UPPER = "ozellik:pazarlama.butce-ust-onay"
F_FOY_WRITE = "ozellik:pazarlama.foy-yaz"
F_FOY_APPROVE = "ozellik:pazarlama.foy-onay"
F_FOY_SEND = "ozellik:pazarlama.foy-gonder"
F_EXPORT = "ozellik:veri.disa-aktar"


def register(app, rt, H: Any) -> None:
    """`H`: api.register'ın yardımcıları (ctx, call, need, db, st, crm, pool, audit, link, can, conf, send_mail, hooks)."""
    from semantic_bridge import budget_sources as bsrc

    crm = H.crm
    can = H.can
    logo = F.LogoPrices(lambda: bsrc.runner(rt().settings.connection_file))

    def st() -> dict[str, Any]:
        return M.settings(H.conf)

    def fst() -> dict[str, Any]:
        return F.settings(H.conf)

    def ctx(request: Request):
        engine, tenant, user, display = H.ctx(request)
        M.ensure(engine)
        F.ensure(engine)
        return engine, tenant, user, display

    def donem_of(v: str) -> str:
        return H.call(M.parse_donem, v)

    def plan_or_404(engine, tenant: str, donem: str) -> dict[str, Any]:
        h = M.find_plan(engine, tenant, donem)
        if not h:
            raise HTTPException(status_code=404, detail={"code": "MARKETING", "message": f"{M.label(donem)} için ay planı yok; "
                                                                                       "önce taslağı kurun."})
        return h

    def audit(engine, user: str, action: str, plan: dict[str, Any], detail: Any = None) -> None:
        H.audit(engine, user, action, plan, detail)

    # ------------------------------------------------------------------ föy eşitleme

    def foy_sync(engine, tenant: str, donem: str, fresh: bool) -> dict[str, Any]:
        s, fs = st(), fst()
        first, last = M.bounds(donem)
        pubs = M._pub_rows(engine, tenant, crm, s, first, last, fresh)
        codes = [b["stokKodu"] for b in pubs]
        raw = crm.foy_books(codes, fresh=fresh)
        prices, note = logo.read(codes, fs["logoPrice"], fresh=fresh)
        notes: list[str] = []
        done: dict[str, int] = {}
        for b in pubs:
            r = raw.get(b["stokKodu"])
            if r is None:
                notes.append(f"{b['stokKodu']}: CRM kitap kartı etkin değil; föy açılmadı.")
                continue
            what = F.upsert_from_crm(engine, tenant, b["stokKodu"], donem, r, b["yayinTarihi"], b["yayinKaynagi"],
                                     prices.get(b["stokKodu"]), note, fs)
            done[what] = done.get(what, 0) + 1
        F.mark_out_of_month(engine, tenant, donem, set(codes))
        return {"pubs": {b["stokKodu"]: b for b in pubs}, "notlar": notes, "logoNotu": note, "islem": done}

    def foy_list(engine, tenant: str, donem: str, durum: str, fresh: bool) -> dict[str, Any]:
        fs = fst()
        notes: list[str] = []
        sync = None
        try:
            sync = foy_sync(engine, tenant, donem, fresh)
            notes += sync["notlar"]
        except SourceError as e:
            notes.append(f"CRM okunamadı; föyler son okunan hâlleriyle: {e}")
        rows = F.list_month(engine, tenant, donem, fs["required"])
        pubs = (sync or {}).get("pubs") or {}
        for r in rows:
            b = pubs.get(r["stokKodu"]) or {}
            r["kitap"] = {"yazar": b.get("yazar"), "yayinevi": b.get("yayinevi"), "kitaplik": b.get("kitaplik"),
                          "yayinTarihi": b.get("yayinTarihi"), "sorumlu": b.get("sorumlu")}
        kpi = {"toplam": sum(1 for r in rows if not r["ayDisi"]),
               "onayli": sum(1 for r in rows if r["durum"] == "onayli" and not r["ayDisi"]),
               "onayda": sum(1 for r in rows if r["durum"] == "onayda" and not r["ayDisi"]),
               "eksik": sum(1 for r in rows if r["eksikler"] and not r["ayDisi"]),
               "uyumsuz": sum(1 for r in rows if r["engelleyen"] and not r["ayDisi"]),
               "eski": sum(1 for r in rows if r["eski"] and not r["ayDisi"])}
        kpi["hazir"] = sum(1 for r in rows if not r["eksikler"] and not r["engelleyen"] and not r["ayDisi"])
        shown = [r for r in rows if not durum or r["durum"] == durum or (durum == "eksik" and r["eksikler"])
                 or (durum == "uyumsuz" and r["engelleyen"]) or (durum == "eski" and r["eski"])]
        return {"donem": donem, "donemAdi": M.label(donem), "items": shown, "kpi": kpi, "notlar": notes,
                "logoNotu": (sync or {}).get("logoNotu"), "gonderimler": F.sends_of(engine, tenant, donem),
                "zorunlu": fs["required"], "logoKaynak": fs["logoPrice"]}

    def foy_one(engine, tenant: str, stok: str, donem: str | None, fresh: bool = False, force: bool = False) -> dict[str, Any]:
        """Tek föy; yoksa (ya da `fresh`) CRM'den açar/tazeler. Dönem verilmezse yayın gününün ayı."""
        fs, s = fst(), st()
        rows = crm.foy_books([stok], fresh=fresh)
        raw = rows.get(stok)
        if raw is None:
            raise C.MarketingError("Bu stok kodunda etkin CRM kitap kartı yok.", 404)
        detail = crm.book(stok, fresh=fresh)
        pub, src = P.resolve_pub(detail["tarihler"], s["dateOrder"]) if detail else (None, None)
        d = donem or (M.of_day(C.today()) if not pub else pub[:7])
        with engine.connect() as c:
            exists = F.get_row(c, tenant, stok, d)
        if exists is None or fresh or force:
            prices, note = logo.read([stok], fs["logoPrice"], fresh=fresh)
            F.upsert_from_crm(engine, tenant, stok, d, raw, pub, src, prices.get(stok), note, fs, force=force)
        out = F.get(engine, tenant, stok, fs["required"], d)
        out["crmTodo"] = F.crm_todo(out) if out["durum"] == "onayli" else []
        out["logo"] = next((x for x in out["uyumsuzluk"] if x["tur"] == "fiyat-logo"), None)
        out["kitap"] = {"yayinKaynagi": src, "sorumlu": (detail or {}).get("sorumlu")}
        return out

    # ------------------------------------------------------------------ ay planı

    @app.get(R + "/months/{donem}")
    async def mkt_month(donem: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        d = donem_of(donem)
        v = await run_in_threadpool(H.call, M.view, engine, tenant, d, st())
        fs = fst()
        rows = F.list_month(engine, tenant, d, fs["required"])
        v["foy"] = {"toplam": sum(1 for r in rows if not r["ayDisi"]), "onayli": sum(1 for r in rows if r["durum"] == "onayli"),
                    "eksik": sum(1 for r in rows if r["eksikler"]), "uyumsuz": sum(1 for r in rows if r["engelleyen"]),
                    "eski": sum(1 for r in rows if r["eski"])}
        v["varsayilanDonem"] = M.default_donem(C.today(), st()["draftDay"])
        if v.get("plan"):
            v["plan"]["ustOnayGerekli"] = C.needs_upper(v["plan"]["butceToplam"], st()["threshold"])
        return v if can(user, F_BUDGET) else M.redact(v)

    @app.post(R + "/months/{donem}/build")
    async def mkt_month_build(donem: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        d = donem_of(donem)
        res = await run_in_threadpool(H.call, M.build, engine, tenant, user, crm, st(), d)
        plan = C.plan_full(engine, tenant, res["planId"])
        audit(engine, user, "run", plan, {"ayPlani": d, **res["stats"], "notlar": len(res["notlar"])})
        return await mkt_month(d, request)

    @app.get(R + "/months/{donem}/conflicts")
    def mkt_month_conflicts(donem: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        d = donem_of(donem)
        h = plan_or_404(engine, tenant, d)
        items = [x for x in M.items_of(engine, h["id"]) if x["cakisma"]]
        return {"donem": d, "items": [{"id": x["id"], "baslik": x["baslik"], "tur": x["tur"], "hafta": x["hafta"],
                                       "baslangic": x["baslangic"], "cakisma": x["cakisma"]} for x in items], "total": len(items)}

    @app.post(R + "/months/{donem}/items", status_code=201)
    def mkt_month_item_new(donem: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        d = donem_of(donem)
        h = plan_or_404(engine, tenant, d)
        if "butce" in body and not can(user, F_BUDGET):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Bütçe görme yetkiniz yok."})
        it = H.call(M.add_item, engine, tenant, user, h["id"], d, body, st())
        audit(engine, user, "update", h, {"kalemEkle": it["baslik"], "tur": it["tur"]})
        return {"item": it}

    @app.patch(R + "/months/{donem}/items/{item_id}")
    def mkt_month_item(donem: str, item_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        d = donem_of(donem)
        h = plan_or_404(engine, tenant, d)
        if "butce" in body and not can(user, F_BUDGET):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Bütçe görme yetkiniz yok."})
        it = H.call(M.update_item, engine, tenant, user, h["id"], d, item_id, body, st())
        audit(engine, user, "update", h, {"kalem": item_id, **{k: body[k] for k in body if k != "butce"}})
        return {"item": it}

    @app.delete(R + "/months/{donem}/items/{item_id}")
    def mkt_month_item_delete(donem: str, item_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        d = donem_of(donem)
        h = plan_or_404(engine, tenant, d)
        out = H.call(M.delete_item, engine, tenant, user, h["id"], item_id, st())
        audit(engine, user, "update", h, {"kalemSil": out["baslik"]})
        return {"ok": True}

    @app.put(R + "/months/{donem}/budget")
    async def mkt_month_budget(donem: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        H.need(user, F_BUDGET, "Bütçe görme")
        d = donem_of(donem)
        h = plan_or_404(engine, tenant, d)
        total = H.call(M.put_budget, engine, tenant, user, h["id"], d, body)
        audit(engine, user, "update", h, {"butce": total, "not": body.get("not")})
        return await mkt_month(d, request)

    @app.post(R + "/months/{donem}/suggest")
    async def mkt_month_suggest(donem: str, request: Request) -> dict[str, Any]:
        """Bütçe önerisi (kod) taslakta yeniden kurulur; Zeki AI gerekçe ve genel müdür özeti yazar (onaylı planda yalnız
        metin)."""
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        d = donem_of(donem)
        h = plan_or_404(engine, tenant, d)
        s = st()
        if h["durum"] in C.EDITABLE:
            def rebuild() -> None:
                prev = M.shift(d, -1)
                ratios = M.segment_ratios(M.month_targets(engine, tenant, prev), M.month_actuals(engine, prev))
                sug = M.suggest_budget(engine, crm, C.plan_full(engine, tenant, h["id"]), M.month_targets(engine, tenant, d),
                                       ratios, s)
                M.put_suggestion(engine, tenant, user, h["id"], d, sug)
            await run_in_threadpool(H.call, rebuild)
        llm = rt().llm_for("marketing", NORMAL)
        warn = None
        if llm is None:
            warn = "Zeki AI modeli bu kurulumda bağlı değil: dağılım kural ile kuruldu, gerekçe yazılamadı."
        else:
            v = await run_in_threadpool(M.view, engine, tenant, d, s)
            try:
                ex = await run_in_threadpool(M.explain, llm, v, s)
            except Exception as e:  # noqa: BLE001 — model hatası ekranda
                log.warning("marketing monthly explain failed: %s", e)
                raise HTTPException(status_code=503, detail={"code": "MARKETING", "message": "Zeki AI şu an cevap vermedi; "
                                                                                           "biraz sonra yeniden deneyin."}) from e
            full = C.plan_full(engine, tenant, h["id"])
            z = dict(full.get("zeki") or {})
            z.update(ex, zaman=C.iso(C.now()), kim=user)
            C.set_fields(engine, h["id"], zeki_json=C.dump(z))
            with engine.begin() as c:
                C.event(c, h["id"], user, "zeki-oneri", None, {"dusen": (ex.get("butceGerekceDusen") or 0) + (ex.get("ozetDusen") or 0)})
        audit(engine, user, "run", h, {"oneri": True, "model": llm is not None})
        out = await mkt_month(d, request)
        out["uyari"] = warn
        return out

    # ---- hedef açığı ↔ ay planı boşluğu (öneri 17): liste kural, paragraf Zeki AI (istenince), karar insanda

    def _gaps(engine, tenant: str, d: str) -> dict[str, Any]:
        return MG.with_paragraph(engine, tenant, MG.gaps(engine, tenant, d))

    @app.get(R + "/months/{donem}/target-gaps")
    async def mkt_month_gaps(donem: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        d = donem_of(donem)
        g = await run_in_threadpool(H.call, _gaps, engine, tenant, d)
        g["modelVar"] = rt().llm_for("marketing", NORMAL) is not None
        return g if can(user, F_BUDGET) else MG.redact(g)

    @app.post(R + "/months/{donem}/target-gaps/explain")
    async def mkt_month_gaps_explain(donem: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        d = donem_of(donem)
        llm = rt().llm_for("marketing", NORMAL)
        if llm is None:
            raise HTTPException(status_code=503, detail={"code": "MARKETING", "message": "Zeki AI bu kurulumda bağlı değil; "
                                                                                       "kural paragrafı gösteriliyor."})
        g = await run_in_threadpool(H.call, MG.gaps, engine, tenant, d)
        try:
            res = await run_in_threadpool(MG.write_paragraph, engine, tenant, g, llm, st().get("claims") or [])
        except Exception as e:  # noqa: BLE001 — model hatası ekranda
            log.warning("marketing monthly gaps explain failed: %s", e)
            raise HTTPException(status_code=503, detail={"code": "MARKETING", "message": "Zeki AI şu an cevap vermedi; "
                                                                                       "biraz sonra yeniden deneyin."}) from e
        h = M.find_plan(engine, tenant, d)
        if h:
            audit(engine, user, "run", h, {"hedefAcigiParagrafi": True, "dusen": res["dusen"]})
        out = MG.with_paragraph(engine, tenant, g)
        out["modelVar"] = True
        return out if can(user, F_BUDGET) else MG.redact(out)

    @app.get(R + "/months/{donem}/events")
    def mkt_month_events(donem: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        h = plan_or_404(engine, tenant, donem_of(donem))
        items = C.events(engine, h["id"])
        if not can(user, F_BUDGET):
            for e in items:
                for side in ("eski", "yeni"):
                    if isinstance(e.get(side), dict):
                        e[side] = {k: v for k, v in e[side].items() if k not in ("toplam", "butce")}
        return {"items": items}

    def _flow(donem: str, request: Request, kind: str, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        d = donem_of(donem)
        h = plan_or_404(engine, tenant, d)
        s = st()
        if kind == "submit":
            out = H.call(C.submit, engine, tenant, user, h["id"])
            upper = C.needs_upper(out["butceToplam"], s["threshold"])
            H.notify(engine, tenant, out, f"Onay bekleyen aylık pazarlama planı: {M.label(d)}",
                     f"{user} {M.label(d)} pazarlama planını onaya gönderdi.\n"
                     + ("Bütçe eşiğin üstünde: pazarlama onayına ek olarak üst onay gerekir.\n" if upper else "")
                     + (f"\nPlan: {H.link('aylik-plan/' + d)}" if H.link() else ""), False)
        elif kind == "withdraw":
            out = H.call(C.withdraw, engine, tenant, user, h["id"])
        elif kind in ("approve", "upper"):
            level = "ust" if kind == "upper" else "pazarlama"
            H.need(user, F_UPPER if level == "ust" else F_APPROVE, "Bütçe üst onayı" if level == "ust" else "Pazarlama planı onayı")
            out = H.call(C.decide, engine, tenant, user, h["id"], True, body.get("note"), level=level, threshold=s["threshold"])
            if out["durum"] == "onayli":
                H.notify(engine, tenant, out, f"Aylık pazarlama planı onaylandı: {M.label(d)}",
                         f"Plan onaylandı ({user})." + (f"\nPlan: {H.link('aylik-plan/' + d)}" if H.link() else ""), True)
        elif kind == "reject":
            level = "ust" if (can(user, F_UPPER) and not can(user, F_APPROVE)) else "pazarlama"
            H.need(user, F_UPPER if level == "ust" else F_APPROVE, "Plan onayı")
            out = H.call(C.decide, engine, tenant, user, h["id"], False, body.get("note"), level=level, threshold=s["threshold"])
            H.notify(engine, tenant, out, f"Aylık pazarlama planı geri gönderildi: {M.label(d)}",
                     f"Plan geri gönderildi ({user}).\nGerekçe: {body.get('note')}", True)
        else:
            out = H.call(C.revise, engine, tenant, user, h["id"], body.get("reason"))
        audit(engine, user, {"submit": "update", "withdraw": "update", "approve": "approve", "upper": "approve", "reject": "reject",
                             "revise": "create"}[kind], out, {"ayPlani": d, "islem": kind, "not": body.get("note") or body.get("reason"),
                                                              "durum": out["durum"]})
        return {"planId": out["id"], "durum": out["durum"], "durumAdi": out["durumAdi"]}

    @app.post(R + "/months/{donem}/submit")
    def mkt_month_submit(donem: str, request: Request) -> dict[str, Any]:
        return _flow(donem, request, "submit", {})

    @app.post(R + "/months/{donem}/withdraw")
    def mkt_month_withdraw(donem: str, request: Request) -> dict[str, Any]:
        return _flow(donem, request, "withdraw", {})

    @app.post(R + "/months/{donem}/approve")
    def mkt_month_approve(donem: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        return _flow(donem, request, "approve", body)

    @app.post(R + "/months/{donem}/upper-approve")
    def mkt_month_upper(donem: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        return _flow(donem, request, "upper", body)

    @app.post(R + "/months/{donem}/reject")
    def mkt_month_reject(donem: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        return _flow(donem, request, "reject", body)

    @app.post(R + "/months/{donem}/revise", status_code=201)
    def mkt_month_revise(donem: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        return _flow(donem, request, "revise", body)

    @app.get(R + "/months/{donem}/summary.pdf")
    async def mkt_month_pdf(donem: str, request: Request) -> Response:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        d = donem_of(donem)
        v = await run_in_threadpool(H.call, M.view, engine, tenant, d, st())
        ozet = ((v.get("plan") or {}).get("zeki") or {}).get("ozet")
        body = await run_in_threadpool(H.call, FP.summary_pdf, v, can(user, F_BUDGET), user, ozet)
        if v.get("plan"):
            audit(engine, user, "run", v["plan"], {"disaAktar": "ay-ozeti-pdf"})
        return Response(body, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="aylik-pazarlama-plani-{d}.pdf"'})

    @app.get(R + "/contract/month/{donem}")
    def mkt_contract_month(donem: str, request: Request) -> dict[str, Any]:
        """M22/M24/M30/M32 okur: onaylı ay takvimi, bütçe payları ve onaylı föylerin bağlantıları."""
        engine, tenant, user, _ = ctx(request)
        d = donem_of(donem)
        out = M.contract(engine, tenant, d)
        rows = [r for r in F.list_month(engine, tenant, d, fst()["required"]) if r["durum"] == "onayli" and not r["ayDisi"]]
        out["foy"] = [{"stokKodu": r["stokKodu"], "surum": r["surum"], "eski": r["eski"],
                       "pdf": f"{R}/foy/{r['stokKodu']}.pdf?donem={d}"} for r in rows]
        out["foyPaket"] = f"{R}/foy/paket/{d}.pdf"
        if not can(user, F_BUDGET):
            out["budget"] = [{**b, "oneri": None, "onayli": None, "tutar": None} for b in out.get("budget") or []]
            out["items"] = [{**x, "butce": None} for x in out.get("items") or []]
            if out.get("plan"):
                out["plan"] = {**out["plan"], "butceToplam": None}
        return out

    # ------------------------------------------------------------------ föy

    @app.get(R + "/foy")
    async def mkt_foy_list(request: Request, donem: str = "", durum: str = "", yenile: bool = False) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        d = donem_of(donem) if donem else M.default_donem(C.today(), st()["draftDay"])
        return await run_in_threadpool(H.call, foy_list, engine, tenant, d, durum, yenile)

    # Dosya uçları `{stok}` uçlarından önce kaydedilir (yol eşleşmesi sırayla).
    def _covers(items: list[dict[str, Any]]) -> dict[str, Any]:
        base = fst()["coverBase"]
        out = {}
        for f in items:
            rel = next((a.get("deger") for a in f["alanlar"] if a["key"] == "kapak"), None)
            out[f["stokKodu"]] = F.cover_bytes(base, rel)
        return out

    def _package(engine, tenant: str, d: str) -> list[dict[str, Any]]:
        return [r for r in F.list_month(engine, tenant, d, fst()["required"]) if r["durum"] == "onayli" and not r["ayDisi"]]

    @app.get(R + "/foy/paket/{donem}.pdf")
    async def mkt_foy_pack_pdf(donem: str, request: Request) -> Response:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        d = donem_of(donem)
        items = _package(engine, tenant, d)
        covers = await run_in_threadpool(_covers, items)
        body = await run_in_threadpool(H.call, FP.foy_pdf, items, M.label(d), covers)
        H.admin.audit(engine, user, "run", "marketing_foy", d, f"Föy paketi {M.label(d)}", {"pdf": len(items)})
        return Response(body, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="satis-foyleri-{d}.pdf"'})

    @app.get(R + "/foy/paket/{donem}.zip")
    async def mkt_foy_pack_zip(donem: str, request: Request) -> Response:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        d = donem_of(donem)
        items = _package(engine, tenant, d)
        covers = await run_in_threadpool(_covers, items)

        def make() -> bytes:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for f in items:
                    name = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in f["stokKodu"])
                    z.writestr(f"foy-{name}.pdf", FP.foy_pdf([f], M.label(d), covers))
                z.writestr("OKUBENI.txt", f"{M.label(d)} onaylı satış föyleri ({len(items)}). Her föy ayrı PDF. Portal hiçbir "
                                          "dış kanala kendiliğinden göndermez.\n")
            return buf.getvalue()

        body = await run_in_threadpool(H.call, make)
        H.admin.audit(engine, user, "run", "marketing_foy", d, f"Föy paketi {M.label(d)}", {"zip": len(items)})
        return Response(body, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="satis-foyleri-{d}.zip"'})

    @app.post(R + "/foy/paket/{donem}/send")
    async def mkt_foy_pack_send(donem: str, request: Request) -> dict[str, Any]:
        """Onaylı föy paketi iç dağıtım listesine (Yönetim → Pazarlama planları → Föy dağıtım listesi). Yalnız
        `foy-gonder` yetkisi olan kişinin tıklamasıyla; alıcı ekrandan girilmez (dışarıya gitmesin)."""
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        H.need(user, F_FOY_SEND, "Föy paketini gönderme")
        d = donem_of(donem)
        items = _package(engine, tenant, d)
        if not items:
            raise HTTPException(status_code=409, detail={"code": "MARKETING", "message": "Gönderilecek onaylı föy yok."})
        to = fst()["recipients"]
        covers = await run_in_threadpool(_covers, items)
        body = await run_in_threadpool(H.call, FP.foy_pdf, items, M.label(d), covers)
        name = f"satis-foyleri-{d}.pdf"
        text = (f"{M.label(d)} satış föyleri ({len(items)} kitap) ekte.\n\n"
                + "\n".join(f"- {next((a['deger'] for a in f['alanlar'] if a['key'] == 'ad'), f['stokKodu'])} ({f['stokKodu']})"
                            for f in items)
                + (f"\n\nPortal: {H.link('foy?donem=' + d)}" if H.link() else "") + f"\n\nGönderen: {user}")
        status = await run_in_threadpool(F.send_mail, f"Satış föyleri · {M.label(d)}", text, to, [(name, body, "application/pdf")])
        rec = F.record_send(engine, tenant, d, to, user, name, len(items), status)
        H.admin.audit(engine, user, "run", "marketing_foy", d, f"Föy paketi gönderimi {M.label(d)}",
                      {"alici": len(to), "adet": len(items), "sonuc": status})
        return rec

    @app.get(R + "/foy/{stok}.pdf")
    async def mkt_foy_pdf(stok: str, request: Request, donem: str = "") -> Response:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        f = await run_in_threadpool(H.call, F.get, engine, tenant, stok, fst()["required"], donem_of(donem) if donem else None)
        covers = await run_in_threadpool(_covers, [f])
        body = await run_in_threadpool(H.call, FP.foy_pdf, [f], M.label(f["donem"]), covers)
        H.admin.audit(engine, user, "run", "marketing_foy", stok, f"Föy PDF {stok}", {"surum": f["surum"], "durum": f["durum"]})
        safe = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in stok)
        return Response(body, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="foy-{safe}.pdf"'})

    @app.get(R + "/foy/{stok}")
    async def mkt_foy(stok: str, request: Request, donem: str = "", yenile: bool = False) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        return await run_in_threadpool(H.call, foy_one, engine, tenant, stok, donem_of(donem) if donem else None, yenile)

    def _foy_audit(engine, user: str, action: str, f: dict[str, Any], detail: Any) -> None:
        name = next((a.get("deger") for a in f["alanlar"] if a["key"] == "ad"), None) or f["stokKodu"]
        H.admin.audit(engine, user, action, "marketing_foy", f["id"], f"Föy · {name}", detail)

    @app.put(R + "/foy/{stok}")
    async def mkt_foy_update(stok: str, body: dict[str, Any], request: Request, donem: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        cur = await run_in_threadpool(H.call, F.get, engine, tenant, stok, fst()["required"], donem_of(donem) if donem else None)
        raw = (await run_in_threadpool(H.call, crm.foy_books, [stok])).get(stok)
        out = await run_in_threadpool(H.call, F.update, engine, tenant, user, stok, cur["donem"], body, fst(), raw)
        _foy_audit(engine, user, "update", out, {"alanlar": list((body.get("alanlar") or {}).keys()), "surum": out["surum"]})
        return out

    @app.post(R + "/foy/{stok}/refresh")
    async def mkt_foy_refresh(stok: str, request: Request, donem: str = "") -> dict[str, Any]:
        """CRM'den yenile: onaylı ya da onaydaki föy yeni sürümle taslağa döner (elle alanlar korunur)."""
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        cur = await run_in_threadpool(H.call, F.get, engine, tenant, stok, fst()["required"], donem_of(donem) if donem else None)
        out = await run_in_threadpool(H.call, foy_one, engine, tenant, stok, cur["donem"], True, True)
        _foy_audit(engine, user, "update", out, {"crmYenile": True, "surum": out["surum"]})
        return out

    @app.post(R + "/foy/{stok}/submit")
    def mkt_foy_submit(stok: str, request: Request, donem: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        cur = H.call(F.get, engine, tenant, stok, fst()["required"], donem_of(donem) if donem else None)
        out = H.call(F.submit, engine, tenant, user, stok, cur["donem"], fst())
        _foy_audit(engine, user, "update", out, {"durum": "onayda"})
        return out

    def _decide(stok: str, body: dict[str, Any], request: Request, donem: str, approve: bool) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        H.need(user, F_FOY_APPROVE, "Föy onayı")
        cur = H.call(F.get, engine, tenant, stok, fst()["required"], donem_of(donem) if donem else None)
        out = H.call(F.decide, engine, tenant, user, stok, cur["donem"], approve, body, fst())
        _foy_audit(engine, user, "approve" if approve else "reject", out,
                   {"surum": out["surum"], "not": body.get("not") or body.get("note"), "kabul": bool(body.get("kabul"))})
        return out

    @app.post(R + "/foy/{stok}/approve")
    def mkt_foy_approve(stok: str, body: dict[str, Any], request: Request, donem: str = "") -> dict[str, Any]:
        return _decide(stok, body, request, donem, True)

    @app.post(R + "/foy/{stok}/reject")
    def mkt_foy_reject(stok: str, body: dict[str, Any], request: Request, donem: str = "") -> dict[str, Any]:
        return _decide(stok, body, request, donem, False)

    @app.post(R + "/foy/{stok}/draft-args")
    async def mkt_foy_args(stok: str, request: Request, donem: str = "") -> dict[str, Any]:
        """Zeki AI satış argümanı taslağı — yalnız CRM'de «Bu kitap neden önemli?» boşsa."""
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        cur = await run_in_threadpool(H.call, F.get, engine, tenant, stok, fst()["required"], donem_of(donem) if donem else None)
        raw = (await run_in_threadpool(H.call, crm.foy_books, [stok], True)).get(stok)
        if raw is None:
            raise HTTPException(status_code=404, detail={"code": "MARKETING", "message": "CRM kitap kartı bulunamadı."})
        if F.split_args(F._long(raw.get("new_kitabinonecikanyanlari"))):
            raise HTTPException(status_code=409, detail={"code": "MARKETING", "message": "CRM'de «Bu kitap neden önemli?» dolu; "
                                                                                       "argümanlar oradan geliyor."})
        llm = rt().llm_for("marketing", NORMAL)
        if llm is None:
            raise HTTPException(status_code=503, detail={"code": "MARKETING", "message": "Zeki AI modeli bu kurulumda bağlı değil."})
        try:
            args, meta = await run_in_threadpool(F.draft_args, llm, cur, raw, st())
        except Exception as e:  # noqa: BLE001
            log.warning("foy draft-args failed: %s", e)
            raise HTTPException(status_code=503, detail={"code": "MARKETING", "message": "Zeki AI şu an cevap vermedi; biraz "
                                                                                       "sonra yeniden deneyin."}) from e
        if not args:
            raise HTTPException(status_code=422, detail={"code": "MARKETING", "message": "Denetimden geçen argüman kalmadı "
                                                                                       "(kaynaksız rakam ya da iddia); elle yazın."})
        out = H.call(F.set_args, engine, tenant, stok, cur["donem"], args, fst(), {**meta, "kim": user})
        _foy_audit(engine, user, "run", out, {"zekiArguman": len(args), "dusen": meta["dusenSayisi"]})
        return out

    # ------------------------------------------------------------------ zamanlayıcı

    def run_due(engine, tenant: str, force: bool = False) -> dict[str, Any]:
        M.ensure(engine)
        F.ensure(engine)
        s, fs = st(), fst()
        today = C.today()
        cur, nxt = M.of_day(today), M.shift(M.of_day(today), 1)
        out: dict[str, Any] = {}
        recipients = list(s["recipients"])

        # 1) Ayın 15'i (ya da sonrası, kaçırılmışsa): gelecek ayın taslağı, dönem başına bir kez.
        if today.day >= s["draftDay"]:
            key = f"month-draft:{nxt}"
            if force or not C.meta_get(engine, tenant, key).get("tarih"):
                h = M.find_plan(engine, tenant, nxt)
                if h is not None and h["durum"] not in C.EDITABLE:
                    out["taslak"] = f"{M.label(nxt)} planı zaten {h['durumAdi'].lower()}"
                    C.meta_set(engine, tenant, key, {"tarih": today.isoformat(), "sonuc": "var"})
                else:
                    try:
                        res = M.build(engine, tenant, "sistem", crm, s, nxt)
                        v = M.view(engine, tenant, nxt, s)
                        n = v["sayilar"]
                        text = (f"{M.label(nxt)} pazarlama planının taslağı kendiliğinden kuruldu.\n\n"
                                f"- Yeni kitap kalemi: {n.get('yeni', 0)}\n- Backlist kalemi: {n.get('backlist', 0)}\n"
                                f"- Özel gün: {n.get('ozel-gun', 0)}\n- B2B kampanyası: {n.get('b2b-kampanya', 0)}\n"
                                f"- Çakışma: {v['cakismaSayisi']}\n"
                                + ("".join(f"\nNot: {x}" for x in res["notlar"]))
                                + (f"\n\nPlan: {H.link('aylik-plan/' + nxt)}" if H.link() else "\n\nPazarlama › Planlama › Aylık plan"))
                        status = H.send_mail(f"ZEKİ pazarlama: {M.label(nxt)} taslak planı hazır", text, recipients) \
                            if recipients else "no_recipient"
                        out["taslak"] = {"planId": res["planId"], **res["stats"], "eposta": status}
                        C.meta_set(engine, tenant, key, {"tarih": today.isoformat(), "sonuc": status, "planId": res["planId"]})
                        llm = rt().llm_for("marketing", BATCH)
                        if llm is not None:
                            H.pool.submit(_explain_bg, engine, tenant, nxt, res["planId"], llm)
                    except (SourceError, C.MarketingError) as e:
                        out["taslakHata"] = str(e)

        # 2) Föyler: bu ay ve gelecek ay CRM'den tazelenir; onaylı föyün CRM alanı değiştiyse «eski».
        out["foy"] = {}
        for d in (cur, nxt):
            try:
                out["foy"][d] = foy_sync(engine, tenant, d, True)["islem"]
            except SourceError as e:
                out["foy"][d] = {"hata": str(e)}

        # 3) Ayın 20'si: gelecek ayın eksik / onaysız föyleri (bir kez).
        if today.day >= s["foyRemindDay"]:
            key = f"foy-remind:{nxt}"
            if force or not C.meta_get(engine, tenant, key).get("tarih"):
                rows = [r for r in F.list_month(engine, tenant, nxt, fs["required"]) if not r["ayDisi"] and r["durum"] != "onayli"]
                if rows:
                    lines = []
                    for r in rows:
                        name = next((a.get("deger") for a in r["alanlar"] if a["key"] == "ad"), None) or r["stokKodu"]
                        why = ", ".join(F.LABELS.get(k, k) for k in r["eksikler"]) if r["eksikler"] else r["durumAdi"].lower()
                        lines.append(f"- {name} ({r['stokKodu']}): {why}")
                    to = sorted(set(recipients) | set(fs["recipients"]))
                    status = H.send_mail(f"ZEKİ pazarlama: {M.label(nxt)} föyleri eksik ya da onaysız ({len(rows)})",
                                         "Yayın ayından önce onaylı föyü olmayan yeni kitaplar:\n\n" + "\n".join(lines)
                                         + (f"\n\nFöyler: {H.link('foy?donem=' + nxt)}" if H.link() else ""), to) if to else "no_recipient"
                else:
                    status = "yok"
                out["foyHatirlatma"] = status
                C.meta_set(engine, tenant, key, {"tarih": today.isoformat(), "sonuc": status})

        # 4) Ay başı + N iş günü: önceki ayın özeti (bir kez).
        prev = M.shift(cur, -1)
        if today >= M.nth_workday(today.year, today.month, s["summaryWorkday"]):
            key = f"month-summary:{prev}"
            if force or not C.meta_get(engine, tenant, key).get("tarih"):
                v = M.view(engine, tenant, prev, s)  # yalnız planın kimliği ve durumu için
                t, a = M.month_targets(engine, tenant, prev), M.month_actuals(engine, prev)
                ratios = M.segment_ratios(t, a)
                hed = sum(x["hedef"] for x in ratios.values()) if ratios else None
                ger = sum(x["gercek"] for x in ratios.values()) if ratios else None
                isler = M.task_stats(engine, tenant, prev)
                pct = lambda x: "—" if x is None else f"%{x * 100:.1f}".replace(".", ",")  # noqa: E731
                text = (f"{M.label(prev)} pazarlama ayı özeti\n\n"
                        f"- Hedefli kitaplarda hedefe oran: {pct(ger / hed if hed else None)}\n"
                        + "".join(f"- {M.SEGMENTS[k]}: {pct(x['oran'])}\n" for k, x in ratios.items())
                        + f"- Plan işleri: {isler['yapildi']} / {isler['toplam']} yapıldı ({isler['atlandi']} atlandı)\n"
                        + (f"- {a['not']}\n" if a.get("not") else "")
                        + (f"- Plan: {v['plan']['id']} ({v['plan']['durumAdi']})\n" if v.get("plan") else "- Bu ay için ay planı yoktu.\n")
                        + (f"\nAyrıntı: {H.link('aylik-plan/' + prev)}" if H.link() else ""))
                status = H.send_mail(f"ZEKİ pazarlama: {M.label(prev)} özeti", text, recipients) if recipients else "no_recipient"
                out["ayOzeti"] = status
                C.meta_set(engine, tenant, key, {"tarih": today.isoformat(), "sonuc": status})

        # 5) Pazartesi: bu ayın planındaki kitaplardan M46'da %80 altına düşenler → plan sahibine haftalık özet.
        if today.weekday() == 0:
            week = M.iso_week(today)
            key = f"month-deviation:{week}"
            h = M.find_plan(engine, tenant, cur)
            if h and (force or not C.meta_get(engine, tenant, key).get("tarih")):
                dev = M.open_deviations(engine, tenant, today.year)
                hit = [x for x in M.items_of(engine, h["id"]) if x.get("stokKodu") and x["stokKodu"] in dev]
                if hit:
                    mail = crm.email_of(h.get("sahip") or "") if h.get("sahip") and h["sahip"] != "sistem" else None
                    to = [mail] if mail else recipients
                    text = ("Bu ayın planında satış hedefinin eşiğinin altında kalan kitaplar:\n\n"
                            + "\n".join(f"- {x['baslik']} ({x['stokKodu']}): hedefe oran "
                                        f"{'—' if dev[x['stokKodu']]['oran'] is None else '%' + format(dev[x['stokKodu']]['oran'] * 100, '.0f')}"
                                        for x in hit)
                            + (f"\n\nPlan: {H.link('aylik-plan/' + cur)}" if H.link() else ""))
                    status = H.send_mail(f"ZEKİ pazarlama: {M.label(cur)} planında hedefin altındaki kitaplar ({len(hit)})",
                                         text, to) if to else "no_recipient"
                else:
                    status = "yok"
                out["sapma"] = status
                C.meta_set(engine, tenant, key, {"tarih": today.isoformat(), "sonuc": status})
        C.meta_set(engine, tenant, "month-run-due", {**{k: v for k, v in out.items() if k != "foy"}, "tarih": today.isoformat()})
        return out

    def _explain_bg(engine, tenant: str, donem: str, plan_id: str, llm: Any) -> None:
        try:
            s = st()
            ex = M.explain(llm, M.view(engine, tenant, donem, s), s)
            full = C.plan_full(engine, tenant, plan_id)
            z = dict(full.get("zeki") or {})
            z.update(ex, zaman=C.iso(C.now()), kim="sistem")
            C.set_fields(engine, plan_id, zeki_json=C.dump(z))
        except Exception as e:  # noqa: BLE001
            log.warning("marketing monthly background explain failed: %s", e)

    H.hooks["run_due"].append(lambda engine, tenant, force=False: {"aylik": run_due(engine, tenant, force)})

    @app.post(R + "/months/run-due")
    def mkt_month_run_due(request: Request, force: bool = False) -> dict[str, Any]:
        H.require_caller(request)
        engine, tenant = H.db()
        return run_due(engine, tenant, force)

    def meta_extra(user: str) -> dict[str, Any]:
        s = st()
        return {"monthly": {"draftDay": s["draftDay"], "foyRemindDay": s["foyRemindDay"],
                            "varsayilanDonem": M.default_donem(C.today(), s["draftDay"]), "types": M.TYPES,
                            "itemSources": M.ITEM_SOURCES, "segments": M.SEGMENTS, "foyStatuses": F.STATUSES,
                            "foyFields": dict(F.FIELDS), "foyRecipients": len(fst()["recipients"])},
                "meExtra": {"canMonth": can(user, PAGE_MONTH), "canFoy": can(user, PAGE_FOY) or can(user, PAGE_MONTH),
                            "canFoyWrite": can(user, F_FOY_WRITE), "canFoyApprove": can(user, F_FOY_APPROVE),
                            "canFoySend": can(user, F_FOY_SEND), "canNewBooks": can(user, "sayfa:pazarlama-yeni-kitap")}}

    H.hooks["meta"].append(meta_extra)
