"""M40 Trendyol uçları: /api/v1/channels/trendyol/* (M42 kanal paketinin altında; `channels.register` bağlar).

Sayfa kapısı `access.RULES`: ürün/stok/fiyat `sayfa:trendyol-urunler`, sipariş/iade `sayfa:trendyol-siparisler`,
soru/yorum `sayfa:trendyol-sorular`, açılış, vitrin, haftalık rapor ve yükleme `sayfa:trendyol`. İşlem kapısı
`FEATURE_RULES`: dosya yükleme/silme `ozellik:trendyol.yukle`, Zeki AI taslağı/sınıflama/vitrin önerisi
`ozellik:trendyol.taslak`, cariyi eşleme listesine ekleme `ozellik:kanal.eslesme`, Excel `ozellik:veri.disa-aktar`.
Açıkça verilen, ucun içinde: `ozellik:trendyol.oneri-karar` (öneri onayı; hazırlayan onaylayamaz) ve M42'nin
`ozellik:kanal.marj`'ı (birim maliyet ve «maliyet altı» işareti).

Hiçbir uç Trendyol'a, T-soft'a, CRM'e ya da Logo'ya yazmaz; platform API'sine istek gönderilmez (kullanıcı kararı
2026-09-28). Zamanlayıcı yalnız `POST run-due`'yu çağırır.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import provenance as PV
from semantic_bridge import sorgu_yakala as Y
from semantic_bridge.channels import kaynak_pazaryeri as KP
from semantic_bridge.channels import mapping as M
from semantic_bridge.channels import platform_common as PC
from semantic_bridge.channels import report as RP
from semantic_bridge.channels import scorecard as SC
from semantic_bridge.channels import sources as src
from semantic_bridge.channels import store as S
from semantic_bridge.channels import trendyol as T
from semantic_bridge.channels import trendyol_import as TI
from semantic_bridge.channels.trendyol_client import TrendyolClient

log = logging.getLogger("semantic.channels.trendyol.api")

R = "/api/v1/channels/trendyol"
PAGES = {"trendyol": "sayfa:trendyol", "urunler": "sayfa:trendyol-urunler", "siparisler": "sayfa:trendyol-siparisler",
         "sorular": "sayfa:trendyol-sorular", "mutabakat": "sayfa:trendyol-mutabakat"}
F_IMPORT = "ozellik:trendyol.yukle"
F_DRAFT = "ozellik:trendyol.taslak"
F_DECIDE = "ozellik:trendyol.oneri-karar"
F_MAP = "ozellik:kanal.eslesme"
F_MARGIN = "ozellik:kanal.marj"
F_EXPORT = "ozellik:veri.disa-aktar"
EXPORTS = {"stok-farki": "urunler", "fiyat-farki": "urunler", "urunler": "urunler", "siparisler": "siparisler",
           "iadeler": "siparisler", "sorular": "sorular", "yorumlar": "sorular", "vitrin": "trendyol"}


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None], can: Callable[[str, str], bool]) -> dict[str, Any]:
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod
    from semantic_layer.runtime.llm_queue import BATCH

    job = PC.Job("trendyol-refresh")

    def conf(key: str) -> str:
        return admin_mod.conf(key) or ""

    def st() -> dict[str, Any]:
        return T.settings(conf)

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        require_caller(request)
        try:
            user, display = board_mod.session_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        r = rt()
        T.ensure(r.store.engine)
        admin_mod.ensure(r.store.engine)
        return r.store.engine, r.settings.tenant_id, user, display

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except SC.ChannelError as e:
            raise HTTPException(status_code=e.status, detail={"code": "TRENDYOL", "message": str(e)}) from e
        except (M.MappingError, TI.ImportError_, T.DraftError, ValueError) as e:
            raise HTTPException(status_code=400, detail={"code": "TRENDYOL", "message": str(e)}) from e
        except src.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "TRENDYOL_SOURCE", "message": str(e)}) from e

    def need(user: str, key: str, what: str) -> None:
        if not can(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def llm(batch: bool = False) -> Any:
        try:
            return rt().llm_for("trendyol", BATCH if batch else None)
        except Exception:  # noqa: BLE001
            return None

    def unit_costs() -> Optional[Callable[[list[str]], dict[str, dict[str, Any]]]]:
        prov = getattr(app.state, "pricing_costs", None)
        return prov.unit_costs if prov is not None and hasattr(prov, "unit_costs") else None

    def refresh_fn(engine, tenant) -> Callable[[Callable[[str], None]], Any]:
        return lambda step: T.refresh_logo(engine, tenant, rt().settings.connection_file, conf, step)

    def wholesale(engine, tenant) -> dict[str, Any]:
        """M42 karnesindeki Trendyol satırı (toptan senaryo). Eşleme yoksa ya da Logo okunmadıysa nedeni."""
        codes = PC.approved_codes(engine, tenant, T.PLATFORM)
        if not codes and not any(v == T.PLATFORM for v in M.kanal_map(engine, tenant).values()):
            return {"eslendi": False, "neden": "Logo'da Trendyol'a bağlanmış cari yok (Cari eşleme). Boş sonuç «Trendyol'a satış yok» demek değildir."}
        try:
            d = SC.channel(engine, tenant, T.PLATFORM)
        except SC.ChannelError as e:
            return {"eslendi": True, "cariler": codes, "neden": str(e)}
        return {"eslendi": True, "cariler": codes, "period": d["period"], "netCiro": d["donem"]["netCiro"],
                "netAdet": d["donem"]["netAdet"], "iadeOrani": d["donem"]["iadeOrani"], "degisim": d["degisim"],
                "cariSayisi": len(d["cariler"])}

    # ------------------------------------------------------------------ genel

    @app.get(R + "/meta")
    def ty_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        s = st()
        with Y.yakala(engine) as q:
            logo, imports = S.meta_get(engine, tenant, "trendyol:logo"), T.last_imports(engine, tenant)
        out = {
            "types": T.TYPE_LABELS, "stockDiffs": T.STOCK_DIFFS, "priceFlags": T.PRICE_FLAGS, "claimClasses": T.CLAIM_CLASSES,
            "settings": {k: s[k] for k in ("minDepo", "maxIndirim", "listeKdv", "vitrinMinStok", "vitrinGun", "soruSaat")},
            "api": TrendyolClient(conf).status(), "job": job.status(), "logo": logo,
            "imports": imports, "modelReady": getattr(rt(), "llm", None) is not None,
            "me": {"username": user, "display": display, "canImport": can(user, F_IMPORT), "canDraft": can(user, F_DRAFT),
                   "canDecide": can(user, F_DECIDE), "canMap": can(user, F_MAP), "canMargin": can(user, F_MARGIN),
                   "canExport": can(user, F_EXPORT), "pages": {k: can(user, v) for k, v in PAGES.items()}},
        }
        return PV.bagla(out, lambda: KP.ty_list("dosya")(engine, tenant, out, q))

    @app.get(R + "/status")
    def ty_status(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {"job": job.status(), "logo": S.meta_get(engine, tenant, "trendyol:logo")}

    @app.post(R + "/refresh")
    def ty_refresh(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        started = job.start(refresh_fn(engine, tenant))
        admin_mod.audit(engine, user, "run", "trendyol_read", None, "Trendyol: Logo stok ve fiyatı yenilendi", {"started": started})
        return {"started": started, "job": job.status()}

    @app.post(R + "/run-due")
    def ty_run_due(request: Request) -> dict[str, Any]:
        """Zamanlayıcı: Logo stok/fiyat/barkod okuması (dosya varsa) ve sınıfsız iadelerin sınıflanması. Ağa çıkmaz."""
        require_caller(request)
        r = rt()
        engine, tenant = r.store.engine, r.settings.tenant_id
        T.ensure(engine)
        admin_mod.ensure(engine)
        out: dict[str, Any] = {"api": "bağlı değil (panel dosyası)"}
        if not T.all_barcodes(engine, tenant):
            out["logo"] = {"skipped": "yüklenmiş Trendyol dosyası yok"}
        elif job.running():
            out["logo"] = {"skipped": "başka bir okuma sürüyor"}
        else:
            out["logo"] = job.run(refresh_fn(engine, tenant))
        out["iade"] = T.classify_claims(engine, tenant, llm(batch=True), st())
        return out

    @app.get(R + "/overview")
    async def ty_overview(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        with Y.yakala(engine) as q:
            out = await run_in_threadpool(lambda: T.overview(engine, tenant, st(), wholesale(engine, tenant)))
        return PV.bagla(out, lambda: KP.ty_overview(engine, tenant, out, q))

    @app.get(R + "/accounts")
    def ty_accounts(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        with Y.yakala(engine) as q:
            m = S.meta_get(engine, tenant, "trendyol:cariler")
            out = {"adayCariler": PC.candidates_view(engine, tenant, T.PLATFORM, m.get("items") or []), "desenler": m.get("desenler"),
                   "okundu": m.get("_at"), "onayli": PC.approved_codes(engine, tenant, T.PLATFORM), "toptan": wholesale(engine, tenant)}
        return PV.bagla(out, lambda: KP.ty_accounts(engine, tenant, out, q))

    @app.post(R + "/cariler/ekle")
    def ty_add_account(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        code = str(body.get("kod") or "").strip()
        card = next((c for c in (S.meta_get(engine, tenant, "trendyol:cariler").get("items") or []) if c["cari_kodu"] == code), None)
        if card is None:
            raise HTTPException(status_code=404, detail={"code": "TRENDYOL", "message": "Cari, adla bulunan Trendyol carileri arasında yok."})
        out = call(PC.add_to_mapping, engine, tenant, T.PLATFORM, card, "M40")
        admin_mod.audit(engine, user, "update", "channel_account", code, card.get("unvan") or code,
                        {"platform": T.PLATFORM, "durum": out.get("durum"), "modul": "M40"})
        return out

    # ------------------------------------------------------------------ ürün, stok, fiyat

    @app.get(R + "/products")
    async def ty_products(request: Request, durum: str = "", q: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        with Y.yakala(engine) as yq:
            out = await run_in_threadpool(call, T.products, engine, tenant, st(), durum, q, page)
        return PV.bagla(out, lambda: KP.ty_list("urun")(engine, tenant, out, yq))

    @app.get(R + "/stock-diff")
    async def ty_stock_diff(request: Request, fark: str = "", q: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        with Y.yakala(engine) as yq:
            out = await run_in_threadpool(call, T.stock_diff, engine, tenant, st(), fark, q, page)
        return PV.bagla(out, lambda: KP.ty_list("stok")(engine, tenant, out, yq))

    @app.get(R + "/price-diff")
    async def ty_price_diff(request: Request, isaret: str = "", q: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        uc = unit_costs() if can(user, F_MARGIN) else None
        if isaret == "maliyet-alti" and uc is None:
            isaret = ""
        with Y.yakala(engine) as yq:
            out = await run_in_threadpool(call, T.price_diff, engine, tenant, st(), isaret, q, page, uc)
        return PV.bagla(out, lambda: KP.ty_list("fiyat")(engine, tenant, out, yq))

    # ------------------------------------------------------------------ sipariş ve iade

    @app.get(R + "/orders")
    async def ty_orders(request: Request, durum: str = "", bas: str = "", bit: str = "", q: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        with Y.yakala(engine) as yq:
            out = await run_in_threadpool(call, T.orders, engine, tenant, durum, bas, bit, q, page)
        return PV.bagla(out, lambda: KP.ty_list("siparis")(engine, tenant, out, yq))

    @app.get(R + "/claims")
    async def ty_claims(request: Request, bas: str = "", bit: str = "", sinif: str = "", q: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        with Y.yakala(engine) as yq:
            out = await run_in_threadpool(call, T.claims, engine, tenant, bas, bit, sinif, q, page)
        return PV.bagla(out, lambda: KP.ty_list("iade")(engine, tenant, out, yq))

    @app.post(R + "/claims/classify")
    async def ty_classify(request: Request, yeniden: bool = False) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        out = await run_in_threadpool(T.classify_claims, engine, tenant, llm(), st(), budget_sec=120, force=yeniden)
        admin_mod.audit(engine, user, "run", "trendyol_claim_class", None, "Trendyol iade nedenleri sınıflandı", out)
        return out

    # ------------------------------------------------------------------ soru ve yorum

    @app.get(R + "/questions")
    async def ty_questions(request: Request, cevapsiz: bool = False, q: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        with Y.yakala(engine) as yq:
            out = await run_in_threadpool(call, T.questions, engine, tenant, st(), cevapsiz, q, page)
        return PV.bagla(out, lambda: KP.ty_list("soru")(engine, tenant, out, yq))

    @app.get(R + "/reviews")
    async def ty_reviews(request: Request, maxPuan: Optional[float] = None, q: str = "", page: int = 0) -> dict[str, Any]:  # noqa: N803
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        with Y.yakala(engine) as yq:
            out = await run_in_threadpool(call, T.reviews, engine, tenant, maxPuan, q, page)
        return PV.bagla(out, lambda: KP.ty_list("yorum")(engine, tenant, out, yq))

    async def _draft(kind: str, rid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        out = await run_in_threadpool(call, T.draft_reply, engine, tenant, user, llm(), kind, rid)
        admin_mod.audit(engine, user, "create", "trendyol_reply_draft", rid, f"Trendyol {kind} yanıt taslağı", {"dusen": out["dusen"]})
        return out

    @app.post(R + "/questions/{rid}/draft")
    async def ty_question_draft(rid: str, request: Request) -> dict[str, Any]:
        return await _draft("soru", rid, request)

    @app.post(R + "/reviews/{rid}/draft")
    async def ty_review_draft(rid: str, request: Request) -> dict[str, Any]:
        return await _draft("yorum", rid, request)

    # ------------------------------------------------------------------ vitrin ve öneri

    @app.get(R + "/showcase")
    async def ty_showcase(request: Request, q: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        with Y.yakala(engine) as yq:
            out = await run_in_threadpool(call, T.showcase, engine, tenant, st(), q, page)
        return PV.bagla(out, lambda: KP.ty_list("vitrin")(engine, tenant, out, yq))

    @app.post(R + "/showcase/suggest", status_code=201)
    async def ty_showcase_suggest(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        codes = [str(x) for x in (body.get("kitaplar") or []) if str(x).strip()]
        note = str(body.get("not") or "").strip()[:1000] or None
        out = await run_in_threadpool(call, T.showcase_suggest, engine, tenant, user, st(), codes, llm(), note)
        admin_mod.audit(engine, user, "create", "channel_suggestion", out["id"], out["baslik"], {"tur": "vitrin", "kitap": len(codes)})
        return out

    @app.get(R + "/suggestions")
    def ty_suggestions(request: Request, durum: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        with Y.yakala(engine) as q:
            out = {"items": S.suggestions(engine, tenant, platform=T.PLATFORM, durum=durum)}
        return PV.bagla(out, lambda: KP.ty_list("oneri")(engine, tenant, out, q))

    @app.post(R + "/suggestions/{sid}/decision")
    def ty_suggestion_decide(sid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_DECIDE, "Trendyol önerisi kararı")
        cur = S.suggestion_get(engine, tenant, sid)
        if cur is None or cur["platform"] != T.PLATFORM:
            raise HTTPException(status_code=404, detail={"code": "TRENDYOL", "message": "Öneri bulunamadı."})
        karar = str(body.get("karar") or "")
        if karar not in ("onayli", "red"):
            raise HTTPException(status_code=400, detail={"code": "TRENDYOL", "message": "Karar «onayli» ya da «red» olmalı."})
        if cur["durum"] != "taslak":
            raise HTTPException(status_code=409, detail={"code": "TRENDYOL", "message": "Öneri zaten karara bağlandı."})
        if cur["olusturan"].lower() == user.lower():
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Öneriyi hazırlayan kişi onaylayamaz."})
        note = str(body.get("not") or "").strip()[:1000] or None
        if karar == "red" and not note:
            raise HTTPException(status_code=400, detail={"code": "TRENDYOL", "message": "Ret gerekçesi yazılmalı."})
        S.suggestion_decide(engine, tenant, sid, user, karar, note)
        admin_mod.audit(engine, user, "approve" if karar == "onayli" else "reject", "channel_suggestion", sid, cur["baslik"], {"not": note})
        return S.suggestion_get(engine, tenant, sid) or {}

    # ------------------------------------------------------------------ panel dosyası

    @app.get(R + "/imports")
    def ty_imports(request: Request, tur: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        with Y.yakala(engine) as q:
            out = {"items": TI.list_imports(engine, tenant, tur), "types": T.TYPE_LABELS}
        return PV.bagla(out, lambda: KP.ty_list("dosya")(engine, tenant, out, q))

    @app.get(R + "/imports/{iid}")
    def ty_import_get(iid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        with Y.yakala(engine) as q:
            out = call(TI.get, engine, tenant, iid)
        return PV.bagla(out, lambda: KP.ty_list("dosya")(engine, tenant, out, q))

    @app.post(R + "/imports", status_code=201)
    async def ty_import(request: Request, tur: str = "", filename: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        if int(request.headers.get("content-length") or 0) > TI.MAX_MB * 1024 * 1024:
            raise HTTPException(413, detail={"code": "TRENDYOL", "message": f"Dosya {TI.MAX_MB} MB sınırını aşıyor."})
        data = await request.body()
        out = await run_in_threadpool(call, TI.store, engine, tenant, user, tur, filename, data)
        admin_mod.audit(engine, user, "upload", "trendyol_import", out["id"], out["dosya"] or "panel dosyası",
                        {"tur": tur, "satir": out["satir"], "eslesen": out["eslesen"],
                         "kisiselOlabilir": out["kolonlar"].get("kisiselOlabilir")})
        return out

    @app.delete(R + "/imports/{iid}")
    def ty_import_delete(iid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(TI.delete, engine, tenant, iid)
        admin_mod.audit(engine, user, "delete", "trendyol_import", iid, out["dosya"] or "panel dosyası", {"tur": out["tur"], "satir": out["satir"]})
        return {"ok": True}

    # ------------------------------------------------------------------ haftalık ve dışa aktarım

    @app.get(R + "/weekly")
    async def ty_weekly(request: Request, bitis: str = "", ozet: bool = False) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        with Y.yakala(engine) as q:
            out = await run_in_threadpool(call, T.weekly, engine, tenant, st(), bitis, llm() if ozet else None)
        return PV.bagla(out, lambda: KP.ty_list("hafta")(engine, tenant, out, q))

    @app.get(R + "/export/{liste}.xlsx")
    async def ty_export(liste: str, request: Request, fark: str = "", isaret: str = "", durum: str = "", bas: str = "",
                        bit: str = "", sinif: str = "", cevapsiz: bool = False, maxPuan: Optional[float] = None,  # noqa: N803
                        q: str = "") -> Response:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        page = EXPORTS.get(liste)
        if not page:
            raise HTTPException(status_code=404, detail={"code": "TRENDYOL", "message": "Bilinmeyen liste."})
        need(user, PAGES[page], "Bu liste")
        s = st()

        def everything(fn, *a) -> dict[str, Any]:
            first = call(fn, *a, 0)
            items = list(first["items"])
            for k in range(1, (first["total"] + first["pageSize"] - 1) // first["pageSize"]):
                items += call(fn, *a, k)["items"]
            return {**first, "items": items}

        if liste == "stok-farki":
            d = await run_in_threadpool(everything, T.stock_diff, engine, tenant, s, fark, q)
            rows = [{**r, "farkAd": T.STOCK_DIFFS.get(r["fark"] or "", "")} for r in d["items"]]
            cols = [("barkod", "Barkod"), ("stokKodu", "Stok kodu"), ("ad", "Kitap"), ("farkAd", "Fark"), ("trendyolStok", "Trendyol stoğu"),
                    ("depoStok", "Depo stoğu"), ("durum", "Trendyol durumu")]
            note = f"Trendyol ürün listesi × Logo depo stoğu · Logo {(d.get('logo') or {}).get('veriSonu') or '—'}"
        elif liste == "fiyat-farki":
            uc = unit_costs() if can(user, F_MARGIN) else None
            allp = await run_in_threadpool(call, T.price_rows, engine, tenant, s, uc)
            d = {"items": PC.search([r for r in allp if (isaret in r["isaret"] if isaret else r["isaret"])], q, ("ad", "barkod", "stokKodu"))}
            rows = [{**r, "isaretAd": ", ".join(T.PRICE_FLAGS[x] for x in r["isaret"])} for r in d["items"]]
            cols = [("barkod", "Barkod"), ("stokKodu", "Stok kodu"), ("ad", "Kitap"), ("trendyolFiyat", "Trendyol fiyatı"),
                    ("listeFiyat", "Liste fiyatı"), ("siteFiyat", "Site fiyatı"), ("indirim", "Listeye göre indirim"), ("isaretAd", "İşaret")]
            if uc is not None:
                cols.append(("birimMaliyet", "Birim maliyet"))
            note = "Trendyol satış fiyatı ↔ Logo liste fiyatı ↔ site fiyatı (KDV dahil)"
        elif liste == "urunler":
            d = await run_in_threadpool(everything, T.products, engine, tenant, s, durum, q)
            rows = d["items"]
            cols = [("barkod", "Barkod"), ("stokKodu", "Stok kodu"), ("ad", "Kitap"), ("durum", "Trendyol durumu"),
                    ("trendyolStok", "Trendyol stoğu"), ("depoStok", "Depo stoğu")]
            note = "Trendyol ürün listesi (son yüklenen dosya)"
        elif liste == "siparisler":
            d = await run_in_threadpool(everything, T.orders, engine, tenant, durum, bas, bit, q)
            rows = d["items"]
            cols = [("paketId", "Paket"), ("tarih", "Sipariş tarihi"), ("durum", "Durum"), ("kargoFirma", "Kargo"), ("termin", "Termin"),
                    ("gecikti", "Gecikti"), ("barkod", "Barkod"), ("ad", "Kitap"), ("adet", "Adet"), ("tutar", "Tutar")]
            note = "Trendyol siparişleri (panel dosyası; alıcı bilgisi içeri alınmaz)"
        elif liste == "iadeler":
            d = await run_in_threadpool(everything, T.claims, engine, tenant, bas, bit, sinif, q)
            rows = d["items"]
            cols = [("talepId", "Talep"), ("tarih", "Tarih"), ("barkod", "Barkod"), ("ad", "Kitap"), ("adet", "Adet"), ("neden", "Platformdaki neden"),
                    ("sinif", "Sınıf"), ("yontem", "Sınıflama"), ("durum", "Durum")]
            note = "Trendyol iadeleri; sınıf kural ya da Zeki AI kapalı küme seçimi"
        elif liste == "sorular":
            d = await run_in_threadpool(everything, T.questions, engine, tenant, s, cevapsiz, q)
            rows = d["items"]
            cols = [("tarih", "Tarih"), ("ad", "Kitap"), ("metin", "Soru (maskeli)"), ("cevaplandi", "Cevaplandı"), ("saat", "Bekleme (saat)"),
                    ("taslak", "Yanıt taslağı")]
            note = "Trendyol müşteri soruları; kişisel bilgi maskeli, yanıtı kişi panelden verir"
        elif liste == "yorumlar":
            d = await run_in_threadpool(everything, T.reviews, engine, tenant, maxPuan, q)
            rows = d["items"]
            cols = [("tarih", "Tarih"), ("ad", "Kitap"), ("puan", "Puan"), ("metin", "Yorum (maskeli)"), ("taslak", "Yanıt taslağı")]
            note = "Trendyol yorumları (panel dosyası)"
        else:
            d = await run_in_threadpool(everything, T.showcase, engine, tenant, s, q)
            rows = d["items"]
            cols = [("stokKodu", "Stok kodu"), ("ad", "Kitap"), ("satis", f"Son {s['vitrinGun']} gün satış"), ("haftalik", "Haftalık hız"),
                    ("depoStok", "Depo stoğu"), ("karsilamaHafta", "Stok kaç hafta"), ("trendyolAcik", "Trendyol'da açık")]
            note = "Vitrin adayları (kural: stok derinliği × satış hızı)"
        data = RP.xlsx(liste, cols, rows, note)
        admin_mod.audit(engine, user, "run", "trendyol_export", liste, f"Trendyol listesi: {liste}", {"satir": len(rows)})
        return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="trendyol-{liste}.xlsx"'})

    return {"job": job}
