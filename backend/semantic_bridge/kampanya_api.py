"""M35 E-ticaret kampanya yönetimi uçları: /api/v1/kampanya/*.

Sayfa kapısı `access.RULES` (`sayfa:kampanya`). Kampanya, kitap, indirim, takvim, öğrenim ve veri yenileme `ozellik:kampanya.duzenle`;
Zeki AI metni ve sonuç özeti `ozellik:kampanya.metin-uret`; Excel brifi `ozellik:veri.disa-aktar` (`FEATURE_RULES`). Onay ya da geri
gönderme açıkça verilen `ozellik:kampanya.onay` ile burada denetlenir; hazırlayan ve onaya gönderen onaylayamaz (409). Zamanlayıcı
(`timas-kampanya.timer`, 05:00) yalnız `POST /api/v1/kampanya/run-due`'yu çağırır.

Dış gönderim yok: kampanya hiçbir platforma, T-soft'a ya da CRM'e gönderilmez. E-posta yalnız iç bildirimdir (onay bekleyen,
karar, stok tükenme uyarısı, sonuç hazır).
"""
from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any, Optional

import sqlalchemy as sa
from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import kampanya as K
from semantic_bridge import kampanya_sources as src

log = logging.getLogger("semantic.kampanya.api")
P = "/api/v1/kampanya"


def register(app: Any, deps: dict[str, Any]) -> K.Refresher:
    """app.py'de bağlanır. `deps`: auth(request) → (engine, tenant, user, display) · require_caller(request) · can(user, key) ·
    is_admin(user) · audit(engine, user, action, kind, id, title, detail) · conf(key, default) · engine() · tenant() ·
    logo_file() · crm_file() · llm(priority) → LLM kapısı istemcisi ya da None · send_mail(subject, text, to) → durum ·
    directory() → {kullanıcı: {"email", "name"}}."""
    auth, require_caller, can, is_admin, audit, conf = (deps[k] for k in ("auth", "require_caller", "can", "is_admin", "audit", "conf"))
    settings = lambda: K.settings_from(conf)  # noqa: E731
    schema = lambda: conf("CRM_SCHEMA", "Timas_MSCRM.dbo")  # noqa: E731
    refresher = K.Refresher(deps["engine"], deps["tenant"], deps["logo_file"], deps["crm_file"], schema, settings)

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        engine, tenant, user, display = auth(request)
        K.ensure(engine)
        return engine, tenant, user, display

    def has(user: str, key: str) -> bool:
        return is_admin(user) or can(user, key)

    def need(user: str, key: str, what: str) -> None:
        if not has(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except K.KampanyaError as e:
            raise HTTPException(status_code=e.status, detail={"code": "FORBIDDEN" if e.status == 403 else "KAMPANYA",
                                                              "message": str(e)}) from e
        except src.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "KAMPANYA_SOURCE", "retryable": True, "message": str(e)}) from e

    def llm(priority_name: str) -> Any:
        from semantic_layer.runtime import llm_queue

        try:
            return deps["llm"](getattr(llm_queue, priority_name))
        except Exception as e:  # noqa: BLE001
            log.info("kampanya: model yok: %s", e)
            return None

    def link(cid: str = "") -> str:
        base = (conf("ALERT_LINK", "") or "").split("/uyarilar")[0].rstrip("/")
        return f"{base}/kampanyalar{('/' + cid) if cid else ''}" if base else ""

    def emails(users: list[Optional[str]]) -> list[str]:
        wanted = [u.lower() for u in users if u]
        if not wanted:
            return []
        try:
            d = deps["directory"]()
        except Exception as e:  # noqa: BLE001 — rehber okunamazsa kişiye e-posta gitmez, ekranda durur
            log.warning("kampanya: kişi rehberi okunamadı: %s", e)
            return []
        return [d[u]["email"] for u in dict.fromkeys(wanted) if u in d and d[u].get("email")]

    def mail(subject: str, text: str, to: list[str]) -> str:
        to = [x for x in dict.fromkeys(to) if x]
        if not to:
            return "no_recipient"
        try:
            return deps["send_mail"](subject, text, to)
        except Exception as e:  # noqa: BLE001
            log.warning("kampanya e-postası gönderilemedi: %s", e)
            return "failed"

    def camp_audit(engine, user, action, c: dict[str, Any], detail: Any = None) -> None:
        audit(engine, user, action, "kampanya", c.get("id"), c.get("ad"), detail)

    def me(user: str, display: str) -> dict[str, Any]:
        return {"username": user, "display": display, "admin": is_admin(user), "canEdit": has(user, "ozellik:kampanya.duzenle"),
                "canApprove": has(user, "ozellik:kampanya.onay"), "canCopy": has(user, "ozellik:kampanya.metin-uret"),
                "canExport": has(user, "ozellik:veri.disa-aktar")}

    def shape(user: str, c: dict[str, Any]) -> dict[str, Any]:
        """Kişiye göre ekran bayrakları: hazırlayan/gönderen onaylayamaz."""
        own = user in {c.get("hazirlayan"), c.get("gonderen")}
        return {**c, "yetki": {"duzenle": c["durum"] == "taslak" and has(user, "ozellik:kampanya.duzenle"),
                               "karar": c["durum"] == "onay_bekliyor" and has(user, "ozellik:kampanya.onay") and not own,
                               "kendisi": own}}

    def advance(engine, tenant) -> list[dict[str, str]]:
        changed = K.advance(engine, tenant)
        for ch in changed:
            audit(engine, "sistem", "update", "kampanya", ch["id"], ch["ad"], {"durum": ch["durum"], "neden": "tarih"})
        return changed

    # ------------------------------------------------------------------ genel

    @app.get(f"{P}/overview")
    def kampanya_overview(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        st = settings()
        advance(engine, tenant)
        ref = K.today()
        waiting = K.all_campaigns(engine, tenant, "onay_bekliyor")
        running = K.all_campaigns(engine, tenant, "yurutuluyor,onaylandi")
        return {
            **K.summary(engine, tenant), "status": refresher.status(),
            "takvim": K.calendar(engine, tenant, ref, ref + timedelta(days=st["takvimGun"])),
            "onayBekleyen": [shape(user, c) for c in waiting], "yurutulen": [shape(user, c) for c in running],
            "kanallar": K.KANALLAR, "durumlar": K.DURUMLAR, "kurallar": K.KURALLAR, "varsayilanKurallar": list(K.VARSAYILAN_KURALLAR),
            "takvimTurleri": K.TAKVIM_TURLERI, "metinTurleri": {k: {"ad": v[0], "sinir": v[1]} for k, v in K.METIN_TURLERI.items()},
            "ayarlar": {k: st[k] for k in ("listPriceSource", "costSource", "marginMinPct", "hizAy", "stokAy", "dususPct",
                                           "adayMarjMinPct", "sezonOncesiGun", "sonraGun", "fiyatGun", "takvimGun")},
            "kanalCari": {k: len(v) for k, v in st["kanalCari"].items()},
            "maliyetSaglayici": K.cost_provider_connected(), "platformBagli": src.platform_connected(),
            "window": K.meta_get(engine, "window"), "me": me(user, display)}

    @app.get(f"{P}/status")
    def kampanya_status(request: Request) -> dict[str, Any]:
        ctx(request)
        return refresher.status()

    @app.post(f"{P}/refresh")
    def kampanya_refresh(request: Request) -> dict[str, Any]:
        engine, _, user, _ = ctx(request)
        started = refresher.start()
        audit(engine, user, "run", "kampanya_refresh", None, "Kampanya verileri yenilendi", {"started": started})
        return {"started": started, **refresher.status()}

    @app.post(f"{P}/run-due")
    async def kampanya_run_due(request: Request, read: bool = True, model: bool = True) -> dict[str, Any]:
        """Zamanlayıcı (her gece 05:00): Logo/CRM okuması, site fiyat kaydı, tarih geçişleri, yürüyen kampanyanın stok/tükenme
        uyarısı, sonuç okuması, biten kampanyanın Zeki AI özeti ve «sonuç hazır» bildirimi, CRM bayi kampanyası türü."""
        require_caller(request)
        engine, tenant, st = deps["engine"](), deps["tenant"](), settings()
        K.ensure(engine)
        out: dict[str, Any] = {}
        if read:
            if refresher.running():
                out["read"] = {"skipped": "başka bir okuma sürüyor"}
            else:
                out["read"] = await run_in_threadpool(refresher.run)
        out.update(await run_in_threadpool(_nightly, engine, tenant, st, model))
        return out

    def _nightly(engine, tenant: str, st: dict[str, Any], model: bool) -> dict[str, Any]:
        out: dict[str, Any] = {"gecis": advance(engine, tenant)}
        ref = K.today()
        end = K.data_end(engine)
        # 1) Onaylı / yürüyen kampanyada stok ve tükenme (fiyat ve marj onaylandığı gibi kalır); uyarı günde bir kez.
        alerts = []
        for c in K.all_campaigns(engine, tenant, "onaylandi,yurutuluyor"):
            try:
                fresh = K.simulate(engine, st, tenant, c["id"], stock_only=True)
            except K.KampanyaError as e:
                log.warning("kampanya %s stok tazelenemedi: %s", c["id"], e)
                continue
            risky = [i for i in fresh["kitaplar"] if i.get("tukenme") and i["tukenme"] <= fresh["bitis"]]
            prev = fresh.get("uyarilar") or []
            with engine.begin() as cn:
                cn.execute(K.CAMPAIGNS.update().where(K.CAMPAIGNS.c.id == c["id"]).values(uyari_json=K._dump(
                    {"gun": ref.isoformat(), "items": [{"stok": i["stok"], "ad": i["ad"], "tukenme": i["tukenme"]} for i in risky]})))
            new = {i["stok"] for i in risky} - {p.get("stok") for p in prev}
            if new:
                lines = [f"- {i['ad'] or i['stok']}: tahmini tükenme {K._day_tr(i['tukenme'])} (stok {i['stokAdet']:.0f})"
                         for i in risky if i["stok"] in new]
                text = (f"«{fresh['ad']}» kampanyasında ({K._day_tr(fresh['baslangic'])} – {K._day_tr(fresh['bitis'])}) stok "
                        f"kampanya bitmeden tükenebilir:\n\n" + "\n".join(lines) +
                        f"\n\nTahmin Logo'nun {K._day_tr(end.isoformat() if end else None)} tarihli verisinden.\n" +
                        (f"\nEkran: {link(fresh['id'])}\n" if link() else ""))
                alerts.append({"id": fresh["id"], "kitap": len(new),
                               "mail": mail(f"Kampanya stok uyarısı: {fresh['ad']}", text,
                                            emails([fresh.get("hazirlayan")]) + st["depoAlicilari"])})
        out["stokUyarisi"] = alerts
        # 2) Sonuç okuması: yürüyen kampanyalar ve «sonra» penceresi Logo verisinde henüz kapanmamış (ya da hiç okunmamış)
        #    biten kampanyalar. Kapanmış pencerenin sonucu değişmez, yeniden okunmaz.
        res_out = []
        todo = []
        for c in K.all_campaigns(engine, tenant, "yurutuluyor,bitti"):
            bit = K._d(c["bitis"])
            open_window = bool(end and bit and end <= bit + timedelta(days=st["sonraGun"] + 7))
            if c["durum"] == "yurutuluyor" or open_window or not K.has_results(engine, c["id"]):
                todo.append(c)
        if todo:
            try:
                run, firms = refresher.logo()
                for c in todo:
                    try:
                        res_out.append({"id": c["id"], **K.refresh_results(engine, st, tenant, c["id"], run, firms, end)})
                    except (K.KampanyaError, src.SourceError) as e:
                        res_out.append({"id": c["id"], "hata": str(e)})
            except src.SourceError as e:
                res_out.append({"hata": str(e)})
        out["sonuc"] = res_out
        # 3) Biten kampanyanın Zeki AI özeti ve «sonuç hazır» bildirimi (bir kez).
        budget = st["llmBudgetSec"]
        t_model = llm("BATCH") if model else None
        summaries = []
        t0 = time.monotonic()
        for c in K.all_campaigns(engine, tenant, "bitti"):
            bit = K._d(c["bitis"])
            if not end or not bit or end < bit:
                continue
            if not c.get("sonucOzet") and t_model is not None and time.monotonic() - t0 < budget:
                try:
                    K.draft_summary(engine, st, t_model, tenant, c["id"])
                    audit(engine, "sistem", "update", "kampanya", c["id"], c["ad"], {"zekiOzet": True})
                    summaries.append(c["id"])
                except K.KampanyaError as e:
                    log.info("kampanya %s özeti yazılamadı: %s", c["id"], e)
            with engine.connect() as cn:
                row = cn.execute(sa.select(K.CAMPAIGNS.c.sonuc_bildirildi, K.CAMPAIGNS.c.sonuc_ozet).where(
                    K.CAMPAIGNS.c.id == c["id"])).first()
            complete = end >= bit + timedelta(days=st["sonraGun"])
            if row and row.sonuc_bildirildi is None and K.has_results(engine, c["id"]) and (row.sonuc_ozet or complete):
                text = (f"«{c['ad']}» kampanyasının sonucu hazır (Logo verisi {K._day_tr(end.isoformat())} tarihine kadar).\n" +
                        (f"\n{row.sonuc_ozet}\n" if row.sonuc_ozet else "") + (f"\nEkran: {link(c['id'])}\n" if link() else ""))
                status = mail(f"Kampanya sonucu: {c['ad']}", text, emails([c.get("hazirlayan")]))
                if status in ("sent", "no_recipient"):
                    with engine.begin() as cn:
                        cn.execute(K.CAMPAIGNS.update().where(K.CAMPAIGNS.c.id == c["id"]).values(sonuc_bildirildi=K._now()))
        out["ozet"] = summaries
        # 4) CRM bayi kampanyalarının türü (kural, sonra kapalı küme seçim).
        try:
            camps = src.read_all_crm_campaigns(refresher.crm(), schema())
            left = max(0.0, budget - (time.monotonic() - t0))
            out["crmTur"] = K.classify_crm(engine, st, t_model, camps, int(left))
        except src.SourceError as e:
            out["crmTur"] = {"hata": str(e)}
        return out

    # ------------------------------------------------------------------ takvim

    @app.get(f"{P}/calendar")
    def kampanya_calendar(request: Request, to: Optional[str] = None) -> dict[str, Any]:
        """?from=YYYY-AA-GG&to=YYYY-AA-GG (from Python'da ayrılmış ad; sorgu dizesinden okunur)."""
        engine, tenant, _, _ = ctx(request)
        ref = K.today()
        a = K._d(request.query_params.get("from")) or ref
        b = K._d(to) or (a + timedelta(days=settings()["takvimGun"]))
        if b < a or (b - a).days > 800:
            raise HTTPException(status_code=422, detail={"code": "KAMPANYA", "message": "Tarih aralığı geçersiz (en çok 800 gün)."})
        return K.calendar(engine, tenant, a, b)

    @app.post(f"{P}/calendar", status_code=201)
    def kampanya_calendar_add(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(K.add_calendar, engine, tenant, user, body)
        audit(engine, user, "create", "kampanya_takvim", out["id"], out["ad"], {k: out[k] for k in ("tur", "baslangic", "bitis")})
        return out

    @app.delete(f"{P}/calendar/{{kid}}")
    def kampanya_calendar_delete(kid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(K.delete_calendar, engine, tenant, kid)
        audit(engine, user, "delete", "kampanya_takvim", kid, out["ad"], None)
        return {"ok": True}

    # ------------------------------------------------------------------ yardımcı listeler

    @app.get(f"{P}/candidates")
    def kampanya_candidates(request: Request, campaign_id: str = "", kurallar: str = "", q: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(K.candidates, engine, settings(), tenant, cid=campaign_id or None, rules=kurallar, q=q, page=page)

    @app.get(f"{P}/books")
    def kampanya_books(request: Request, q: str = "", page: int = 0) -> dict[str, Any]:
        """Elle ekleme için kitap araması (ad, stok kodu, yazar, barkod); stoklu olanlar önce."""
        engine, _, _, _ = ctx(request)
        qq = q.strip()
        if len(qq) < 2:
            return {"items": [], "total": 0, "page": 0, "pageSize": K.PAGE_SIZE}
        like = f"%{qq}%"
        cond = [K.BOOKS.c.in_crm.is_(True), sa.or_(K.BOOKS.c.ad.ilike(like), K.BOOKS.c.stok_kodu.ilike(like),
                                                     K.BOOKS.c.yazar.ilike(like), K.BOOKS.c.ean.ilike(like))]
        page = max(0, page)
        with engine.connect() as c:
            total = c.execute(sa.select(sa.func.count()).select_from(K.BOOKS).where(*cond)).scalar() or 0
            rows = c.execute(sa.select(K.BOOKS).where(*cond).order_by(K.BOOKS.c.stok.desc(), K.BOOKS.c.ad)
                             .offset(page * K.PAGE_SIZE).limit(K.PAGE_SIZE)).all()
        st = settings()
        items = []
        for r in rows:
            b = K.book_dict(r)
            items.append({"stok": b["stok"], "ad": b["ad"], "yazar": b["yazar"], "ean": b["ean"], "stokAdet": b["stokAdet"],
                          "liste": K.list_price(b, st)[0], "adet12": b["adet12"]})
        return {"items": items, "total": total, "page": page, "pageSize": K.PAGE_SIZE}

    @app.get(f"{P}/crm-campaigns")
    def kampanya_crm(request: Request, page: int = 0, etkin: bool = True) -> dict[str, Any]:
        """CRM bayi kampanyaları (salt okunur, sayfalı) ve bağlı sipariş satırlarının etkisi; türü gece sınıflanır."""
        engine, _, _, _ = ctx(request)
        crm = call(refresher.crm)
        got = call(src.read_crm_campaigns, crm, schema(), max(0, page), K.PAGE_SIZE, etkin)
        ids = [x["id"] for x in got["items"]]
        eff = call(src.read_campaign_effect, crm, schema(), ids) if ids else {}
        types = K.crm_types(engine, ids)
        for x in got["items"]:
            x["etki"] = eff.get(x["id"])
            x["tur"] = types.get(x["id"])
        return got

    # ------------------------------------------------------------------ kampanyalar

    @app.get(f"{P}/campaigns")
    def kampanya_list(request: Request, durum: str = "", kanal: str = "", q: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = K.list_campaigns(engine, tenant, durum=durum, kanal=kanal, q=q, page=page)
        out["items"] = [shape(user, c) for c in out["items"]]
        return out

    @app.post(f"{P}/campaigns", status_code=201)
    def kampanya_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(K.create_campaign, engine, tenant, user, body)
        camp_audit(engine, user, "create", out, {k: out[k] for k in ("kanal", "baslangic", "bitis")})
        return shape(user, out)

    @app.get(f"{P}/campaigns/{{cid}}")
    def kampanya_get(cid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return shape(user, call(K.get_campaign, engine, tenant, cid))

    @app.patch(f"{P}/campaigns/{{cid}}")
    def kampanya_update(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)

        def crm_check(g: str) -> bool:
            return src.crm_campaign_exists(refresher.crm(), schema(), g)

        out, info = call(K.update_campaign, engine, tenant, user, cid, body, crm_check)
        if info["diff"]:
            camp_audit(engine, user, "update", out, info["diff"])
        if info["resimulate"] and out["durum"] == "taslak":
            out = call(K.simulate, engine, settings(), tenant, cid)
        return shape(user, out)

    @app.delete(f"{P}/campaigns/{{cid}}")
    def kampanya_delete(cid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(K.delete_campaign, engine, tenant, cid)
        camp_audit(engine, user, "delete", out)
        return {"ok": True}

    @app.post(f"{P}/campaigns/{{cid}}/items")
    def kampanya_items_add(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out, missing = call(K.add_items, engine, settings(), tenant, cid, body.get("kitaplar"))
        camp_audit(engine, user, "update", out, {"eklenen": [x.get("stok") for x in body.get("kitaplar") or [] if isinstance(x, dict)],
                                                 "bulunamayan": missing})
        return {**shape(user, out), "bulunamayan": missing}

    @app.patch(f"{P}/campaigns/{{cid}}/items/{{stok:path}}")
    def kampanya_item_update(cid: str, stok: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(K.update_item, engine, settings(), tenant, cid, stok, body)
        camp_audit(engine, user, "update", out, {"kitap": stok, **{k: body[k] for k in ("indirim", "kampanyaFiyati", "liste") if k in body}})
        return shape(user, out)

    @app.delete(f"{P}/campaigns/{{cid}}/items/{{stok:path}}")
    def kampanya_item_delete(cid: str, stok: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(K.remove_item, engine, tenant, cid, stok)
        camp_audit(engine, user, "update", out, {"cikarilan": stok})
        return shape(user, out)

    @app.post(f"{P}/campaigns/{{cid}}/simulate")
    def kampanya_simulate(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Toplu indirim (`indirim`) ve yeniden hesap. `kaydet: false` önizlemedir, hiçbir şey yazılmaz."""
        engine, tenant, user, _ = ctx(request)
        bulk = call(K.ratio, body.get("indirim"), "Toplu indirim") if body.get("indirim") not in (None, "") else None
        save = body.get("kaydet", True) is not False
        out = call(K.simulate, engine, settings(), tenant, cid, bulk=bulk, save=save)
        if save and bulk is not None:
            camp_audit(engine, user, "update", out, {"topluIndirim": bulk})
        return shape(user, out) if save else out

    @app.post(f"{P}/campaigns/{{cid}}/submit")
    def kampanya_submit(cid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        st = settings()
        out = call(K.submit, engine, st, tenant, user, cid)
        o = out["ozet"]
        camp_audit(engine, user, "update", out, {"durum": "onay_bekliyor", "kitap": o["kitap"], "kirmizi": o["kirmizi"],
                                                 "marjOraniSonra": o["marjOraniSonra"]})
        text = (f"{display} «{out['ad']}» kampanyasını onaya gönderdi.\n\nKanal: {out['kanalAdi']}"
                f"{(' · ' + out['platform']) if out.get('platform') else ''}\nTarih: {K._day_tr(out['baslangic'])} – "
                f"{K._day_tr(out['bitis'])}\nKitap: {o['kitap']} · ortalama indirim {K._pct(o['ortalamaIndirim'])} · "
                f"kampanyalı marj {K._pct(o['marjOraniSonra'], 1) if o['marjOraniSonra'] is not None else 'hesaplanamadı'}\n"
                f"Kırmızı kontrol: {o['kirmizi']} · maliyeti eksik kitap: {o['maliyetEksik']}\n" +
                (f"\nEkran: {link(cid)}\n" if link() else ""))
        out["bildirim"] = mail(f"Onay bekleyen kampanya: {out['ad']}", text, st["onayAlicilari"])
        return shape(user, out)

    @app.post(f"{P}/campaigns/{{cid}}/withdraw")
    def kampanya_withdraw(cid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(K.withdraw, engine, tenant, user, cid)
        camp_audit(engine, user, "update", out, {"durum": "taslak", "neden": "onaydan çekildi"})
        return shape(user, out)

    @app.post(f"{P}/campaigns/{{cid}}/decision")
    def kampanya_decision(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        need(user, "ozellik:kampanya.onay", "Kampanya onayı")
        karar = str(body.get("karar") or "")
        if karar not in ("onay", "geri"):
            raise HTTPException(status_code=422, detail={"code": "KAMPANYA", "message": "Karar «onay» ya da «geri» olmalı."})
        out = call(K.decide, engine, tenant, user, cid, karar == "onay", body.get("not"))
        camp_audit(engine, user, "approve" if karar == "onay" else "reject", out, {"not": out.get("onayNotu")})
        verdict = "onaylandı" if karar == "onay" else "geri gönderildi"
        text = (f"«{out['ad']}» kampanyası {display} tarafından {verdict}.\n" +
                (f"\nNot: {out['onayNotu']}\n" if out.get("onayNotu") else "") +
                ("\nKampanyayı platform panelinde / T-soft'ta / CRM'de siz kurarsınız; portal hiçbir yere göndermez. Kurunca "
                 "ekranda «Elle kurdum» diye işaretleyin.\n" if karar == "onay" else "") +
                (f"\nEkran: {link(cid)}\n" if link() else ""))
        out["bildirim"] = mail(f"Kampanya {verdict}: {out['ad']}", text, emails([out.get("hazirlayan"), out.get("gonderen")]))
        return shape(user, out)

    @app.post(f"{P}/campaigns/{{cid}}/cancel")
    def kampanya_cancel(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(K.cancel_campaign, engine, tenant, user, cid, body.get("not"))
        camp_audit(engine, user, "update", out, {"durum": "iptal", "not": body.get("not")})
        return shape(user, out)

    @app.post(f"{P}/campaigns/{{cid}}/copy")
    async def kampanya_copy(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        kind = str(body.get("tur") or "baslik")
        out = await run_in_threadpool(call, K.draft_copy, engine, llm("NORMAL"), tenant, cid, kind)
        audit(engine, user, "update", "kampanya", cid, None, {"zekiMetin": kind, "secenek": len(out["secenekler"]),
                                                             "dusenSayisi": out["dusenSayisi"]})
        return out

    # ------------------------------------------------------------------ sonuç ve öğrenim

    @app.get(f"{P}/campaigns/{{cid}}/results")
    def kampanya_results(cid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = call(K.results, engine, settings(), tenant, cid)
        camp = call(K.get_campaign, engine, tenant, cid)
        if camp["kanal"] == "bayi" and camp.get("crmKampanyaId"):
            try:
                out["crmEtki"] = src.read_campaign_effect(refresher.crm(), schema(), [camp["crmKampanyaId"]]).get(camp["crmKampanyaId"])
            except src.SourceError as e:
                out["crmEtkiHata"] = str(e)
        return out

    @app.post(f"{P}/campaigns/{{cid}}/results/refresh")
    async def kampanya_results_refresh(cid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)

        def work() -> dict[str, Any]:
            run, firms = refresher.logo()
            return K.refresh_results(engine, settings(), tenant, cid, run, firms, K.data_end(engine))

        out = await run_in_threadpool(call, work)
        audit(engine, user, "run", "kampanya_sonuc", cid, None, out)
        return await run_in_threadpool(call, K.results, engine, settings(), tenant, cid)

    @app.post(f"{P}/campaigns/{{cid}}/summary")
    async def kampanya_summary(cid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        out = await run_in_threadpool(call, K.draft_summary, engine, settings(), llm("NORMAL"), tenant, cid)
        audit(engine, user, "update", "kampanya", cid, None, {"zekiOzet": True, "dusenSayisi": out["dusenSayisi"]})
        return out

    @app.get(f"{P}/learnings")
    def kampanya_learnings(request: Request, kanal: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return K.learnings(engine, tenant, kanal=kanal, page=page)

    @app.post(f"{P}/campaigns/{{cid}}/learnings", status_code=201)
    def kampanya_learning_add(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(K.add_learning, engine, settings(), tenant, user, cid, body)
        audit(engine, user, "create", "kampanya_ogrenim", out["id"], None, {"kampanya": cid})
        return out

    @app.delete(f"{P}/learnings/{{lid}}")
    def kampanya_learning_delete(lid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(K.delete_learning, engine, tenant, user, lid, is_admin(user))
        audit(engine, user, "delete", "kampanya_ogrenim", lid, None, {"kampanya": out["kampanyaId"]})
        return {"ok": True}

    @app.get(f"{P}/campaigns/{{cid}}/export.xlsx")
    def kampanya_export(cid: str, request: Request, ic: bool = False) -> Response:
        engine, tenant, user, _ = ctx(request)
        camp = call(K.get_campaign, engine, tenant, cid)
        data = K.export_xlsx(camp, internal=ic)
        audit(engine, user, "run", "kampanya_export", cid, camp["ad"], {"ic": ic, "taslak": camp["durum"] in ("taslak", "onay_bekliyor")})
        name = f"kampanya-{cid}{'-ic' if ic else ''}.xlsx"
        return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    return refresher
