"""M24 Katalog ve bülten uçları: /api/v1/catalog-newsletter/*.

Sayfa kapısı `access.RULES` (`sayfa:katalog-bulten`). Katalog yazma `ozellik:katalog.duzenle`, bülten yazma
`ozellik:bulten.duzenle`, dışa aktarım (Excel, tasarımcı paketi, PDF önizleme, bülten HTML'i) `ozellik:veri.disa-aktar`
(`FEATURE_RULES`). Açıkça verilen iki yetki ucun içinde denetlenir: onay/geri gönderme `ozellik:katalog-bulten.onay`
(gönderen onaylayamaz), segment sayacı `ozellik:bulten.segment` (yalnız sayı ve dağılım; kişi listesi hiçbir uçtan dönmez).

Kitap havuzu (CRM kitap kartları + Baskı önerisi tanımıyla stok/satış hızı + özel gün bağı + T-soft fiyatı) ağır bir
okumadır; bir kez okunur, `semantic_catalog_meta`'da saklanır, zamanlayıcı (`timas-catalog.timer`, her gün 07:15
`run-due`) ya da ekrandaki «Kaynaktan yenile» ile tazelenir. İlk açılışta havuz yoksa okuma arka planda başlar, uç
«hazırlanıyor» (503) döner.

Model çağrıları LLM kapısından: `rt.llm_for("katalog", BATCH)` (toplu metin kısaltma ve gerekçe) ve
`rt.llm_for("bulten", NORMAL)` (bülten taslağı). `LlmClient` doğrudan kurulmaz.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import catalogs as C
from semantic_bridge import catalogs_sources as S
from semantic_bridge import newsletters as N

log = logging.getLogger("semantic.catalogs.api")
P = "/api/v1/catalog-newsletter"
FEATURE_CATALOG = "ozellik:katalog.duzenle"
FEATURE_NEWSLETTER = "ozellik:bulten.duzenle"
FEATURE_APPROVE = "ozellik:katalog-bulten.onay"
FEATURE_SEGMENT = "ozellik:bulten.segment"
FEATURE_EXPORT = "ozellik:veri.disa-aktar"
POOL_KEY = "pool"


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None], can: Callable[[str, str], bool]):
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod

    state: dict[str, Any] = {"pools": {}, "running": False, "started": None, "error": None, "lock": threading.Lock()}

    def crm_path() -> str:
        return os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")

    def schema() -> str:
        return admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo"

    def crm():
        return S.runner(crm_path())

    def logo():
        return S.runner(rt().settings.connection_file)

    def llm(module: str, batch: bool):
        try:
            from semantic_layer.runtime.llm_queue import BATCH, NORMAL
            return rt().llm_for(module, BATCH if batch else NORMAL)
        except Exception:  # noqa: BLE001 — model tanımlı değil
            return None

    def chatter(module: str, batch: bool, max_tokens: int) -> Optional[Callable[[list[dict[str, str]]], str]]:
        m = llm(module, batch)
        if m is None:
            return None
        return lambda messages: m.chat(messages, max_tokens=max_tokens, temperature=0.2)

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        require_caller(request)
        try:
            user, display = board_mod.session_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        r = rt()
        C.ensure(r.store.engine)
        N.ensure(r.store.engine)
        admin_mod.ensure(r.store.engine)
        return r.store.engine, r.settings.tenant_id, user, display

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except C.CatalogError as e:
            raise HTTPException(status_code=e.status, detail={"code": "CATALOG", "message": str(e)}) from e
        except S.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "CATALOG_SOURCE", "message": str(e)}) from e

    def need(user: str, key: str, what: str) -> None:
        if not can(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def audit(engine, user, action, kind, oid, title, detail=None) -> None:
        admin_mod.audit(engine, user, action, kind, oid, title, detail)

    # ------------------------------------------------------------------ kitap havuzu

    def build_pool(engine, tenant: str) -> dict[str, Any]:
        cfg = C.settings()
        today = C.today()
        crm_r = crm()
        notes: list[str] = []
        crm_part = S.read_pool_crm(crm_r, schema(), cfg["bookTypes"])
        try:
            logo_r = logo()
        except S.SourceError as e:
            logo_r = None
            notes.append(f"Logo bağlantısı yok ({e}); stok, satış hızı ve Logo fiyatı boş.")
        stock: dict[str, Any] = {"byCode": {}}
        logo_end = None
        if logo_r is not None:
            stock = S.read_stock_speed(logo_r, crm_r, today)
            notes += stock.get("notes") or []
            try:
                logo_end = S.logo_data_end(logo_r)
            except S.SourceError as e:
                notes.append(f"Logo veri sonu okunamadı ({e}).")
        try:
            days = S.read_special_days(crm_r, schema(), today)
        except Exception as e:  # noqa: BLE001 — özel gün bağı yoksa katalog yine kurulur
            days = []
            notes.append(f"Özel günler okunamadı ({str(e)[:160]}).")
        try:
            rights = S.read_rights_notes(crm_r, schema(), today)
        except Exception as e:  # noqa: BLE001
            rights = set()
            notes.append(f"Telif sözleşmesi hak notları okunamadı ({str(e)[:160]}).")
        try:
            interests = S.read_interests(crm_r, schema())
        except Exception as e:  # noqa: BLE001
            interests = []
            notes.append(f"CRM ilgi alanları okunamadı ({str(e)[:160]}).")
        tsoft = S.read_tsoft(engine, tenant, admin_mod.conf("SEO_SITE_URL") or "")
        pool = C.build_pool(crm_part, stock, tsoft, days, rights, logo_end, notes, cfg)
        pool["ilgiAlanlari"] = interests
        pool["tsoftUrun"] = len(tsoft)
        C.meta_set(engine, tenant, POOL_KEY, pool)
        state["pools"][tenant] = pool
        return pool

    def start_refresh(engine, tenant: str) -> bool:
        with state["lock"]:
            if state["running"]:
                return False
            state.update(running=True, started=time.time(), error=None)

        def work() -> None:
            try:
                build_pool(engine, tenant)
            except Exception as e:  # noqa: BLE001 — son başarılı havuz korunur
                log.warning("katalog havuzu okunamadı: %s", e)
                state["error"] = str(e)[:300]
            finally:
                state["running"] = False

        threading.Thread(target=work, name="catalog-pool", daemon=True).start()
        return True

    def pool_of(engine, tenant: str, required: bool = True) -> Optional[dict[str, Any]]:
        p = state["pools"].get(tenant)
        if p is None:
            p, _ = C.meta_get(engine, tenant, POOL_KEY)
            if p is not None:
                state["pools"][tenant] = p
        if p is None and required:
            start_refresh(engine, tenant)
            msg = "Kitap havuzu hazırlanıyor (CRM kitap kartları, stok ve satış hızı okunuyor); birkaç dakika sonra yenileyin."
            if state["error"]:
                msg = f"Kitap havuzu okunamadı: {state['error']}"
            raise HTTPException(503, detail={"code": "CATALOG_POOL", "message": msg})
        return p

    def pool_status(pool: Optional[dict[str, Any]]) -> dict[str, Any]:
        return {"okuma": (pool or {}).get("readAt"), "logoSon": (pool or {}).get("logoSon"), "kitap": len((pool or {}).get("books") or []),
                "notlar": (pool or {}).get("notes") or [], "fiyatFarkli": (pool or {}).get("fiyatFarkli"),
                "tsoftUrun": (pool or {}).get("tsoftUrun"), "yenileniyor": state["running"], "hata": state["error"]}

    def interests_of(pool: dict[str, Any]) -> dict[str, str]:
        return {i["id"]: i["ad"] for i in pool.get("ilgiAlanlari") or []}

    def texts_reader() -> Callable[[list[str]], dict[str, dict[str, Optional[str]]]]:
        return lambda ids: S.read_texts(crm(), schema(), ids)

    # ------------------------------------------------------------------ genel

    @app.get(P + "/meta")
    def cn_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        pool = pool_of(engine, tenant, required=False)
        if pool is None and not state["running"]:
            start_refresh(engine, tenant)
        cfg, ncfg = C.settings(), N.settings()
        last, _ = C.meta_get(engine, tenant, "last_run")
        return {
            "turler": C.KINDS, "durumlar": C.STATUSES, "bultenDurumlari": N.STATUSES, "fiyatKaynaklari": C.PRICE_SOURCES,
            "stokKaynaklari": C.STOCK_SOURCES, "uyariTurleri": {k: {"seviye": v[0], "ad": v[1]} for k, v in C.ALERT_KINDS.items()},
            "ayarlar": {"fiyatKaynagi": cfg["priceSource"], "fiyatGerekce": C.PRICE_SOURCE_WHY, "stokKaynagi": cfg["stockSource"],
                        "kritikAy": cfg["criticalMonths"], "hedefAy": cfg["targetMonths"], "yeniAy": cfg["newMonths"],
                        "agirliklar": cfg["weights"], "kelime": cfg["textWords"], "pdfSayfa": cfg["pdfPerPage"],
                        "kvkkSart": ncfg["requireKvkk"], "konuSayisi": ncfg["subjects"], "izinKurali": N.segment_result({}, ncfg["requireKvkk"])["kural"]},
            "havuz": pool_status(pool),
            "ozelGunler": [d for d in (pool or {}).get("days") or [] if d.get("kitapSayisi")],
            "hedefler": (pool or {}).get("hedefler") or [],
            "markalar": sorted({b["marka"] for b in (pool or {}).get("books") or [] if b.get("marka")}),
            "ilgiBayraklari": N.CONTACT_FLAGS, "ilgiAlanlari": (pool or {}).get("ilgiAlanlari") or [],
            "bekleyen": {**C.pending_counts(engine, tenant), **N.pending_counts(engine, tenant)},
            "sonKosu": last,
            "modelVar": llm("katalog", True) is not None,
            "me": {"username": user, "display": display, "canCatalog": can(user, FEATURE_CATALOG),
                   "canNewsletter": can(user, FEATURE_NEWSLETTER), "canApprove": can(user, FEATURE_APPROVE),
                   "canSegment": can(user, FEATURE_SEGMENT), "canExport": can(user, FEATURE_EXPORT)},
        }

    @app.post(P + "/pool/refresh", status_code=202)
    def cn_pool_refresh(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        started = start_refresh(engine, tenant)
        audit(engine, user, "run", "catalog_pool", None, "Kitap havuzu yenileme", {"basladi": started})
        return {"started": started, "havuz": pool_status(state["pools"].get(tenant))}

    # ------------------------------------------------------------------ katalog

    @app.get(P + "/catalogs")
    def cn_catalogs(request: Request, durum: str = "acik") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return C.list_catalogs(engine, tenant, durum)

    @app.post(P + "/catalogs", status_code=201)
    def cn_catalog_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(C.create, engine, tenant, user, body, C.settings())
        audit(engine, user, "create", "catalog", out["id"], out["baslik"], {"tur": out["tur"], "fiyatKaynagi": out["fiyatKaynagi"]})
        return out

    @app.get(P + "/catalogs/{cid}")
    async def cn_catalog(cid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        pool = pool_of(engine, tenant, required=False)
        return await run_in_threadpool(call, C.detail, engine, tenant, cid, pool, C.settings())

    @app.patch(P + "/catalogs/{cid}")
    def cn_catalog_update(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out, diff = call(C.update, engine, tenant, cid, body)
        if diff:
            audit(engine, user, "update", "catalog", cid, out["baslik"], diff)
        return out

    @app.delete(P + "/catalogs/{cid}")
    def cn_catalog_delete(cid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(C.delete, engine, tenant, cid)
        audit(engine, user, "delete", "catalog", cid, out["baslik"])
        return {"ok": True}

    @app.post(P + "/catalogs/{cid}/suggest")
    async def cn_catalog_suggest(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Süzgece uyan bütün kitaplar puan sırasıyla (katalogdakiler hariç); sayfa sayfa döner, toplam yazar."""
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        pool = await run_in_threadpool(pool_of, engine, tenant)
        cat = await run_in_threadpool(call, C.detail, engine, tenant, cid, None, C.settings())
        filters = body.get("suzgec") if isinstance(body.get("suzgec"), dict) else cat["suzgec"]
        res = await run_in_threadpool(C.candidates, pool, filters, C.settings(), [k["crmKitapId"] for k in cat["kitaplar"]],
                                      None, None, cat["fiyatKaynagi"])
        page, size = max(0, int(body.get("page") or 0)), min(200, max(10, int(body.get("pageSize") or 50)))
        return {**{k: v for k, v in res.items() if k != "items"}, "items": res["items"][page * size:(page + 1) * size],
                "page": page, "pageSize": size, "havuz": pool_status(pool)}

    @app.put(P + "/catalogs/{cid}/items")
    async def cn_catalog_items(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        pool = await run_in_threadpool(pool_of, engine, tenant)
        out, diff = await run_in_threadpool(call, C.set_items, engine, tenant, user, cid, body.get("items"), pool, C.settings())
        if diff["eklenen"] or diff["cikan"]:
            audit(engine, user, "update", "catalog_item", cid, out["baslik"], diff)
        return out

    @app.post(P + "/catalogs/{cid}/items/{bid}/accept")
    def cn_catalog_accept(cid: str, bid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        pool = pool_of(engine, tenant)
        out = call(C.accept, engine, tenant, cid, bid, str(body.get("tur") or ""), pool, C.settings())
        audit(engine, user, "update", "catalog_item", f"{cid}:{bid}", out["ad"], {"uyariKabul": out["tur"], "deger": out["deger"]})
        return call(C.detail, engine, tenant, cid, pool, C.settings())

    @app.post(P + "/catalogs/{cid}/zeki", status_code=202)
    def cn_catalog_zeki(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        pool = pool_of(engine, tenant)
        chat = chatter("katalog", True, 700)
        if chat is None:
            raise HTTPException(503, detail={"code": "CATALOG", "message": "Zeki AI bu kurulumda bağlı değil; metin ve gerekçe yazılamıyor."})
        opts = {"metin": bool(body.get("metin", True)), "gerekce": bool(body.get("gerekce", True)), "yeniden": bool(body.get("yeniden")),
                "kelime": body.get("kelime")}
        cat = call(C.get, engine, tenant, cid)
        if cat["durum"] != "taslak":
            raise HTTPException(409, detail={"code": "CATALOG", "message": "Zeki AI metni yalnız taslak kataloğa yazılır."})
        job = call(C.job_create, engine, tenant, user, "katalog-zeki", cid)
        threading.Thread(target=C.run_zeki, args=(engine, tenant, job["id"], cid, chat, texts_reader(), pool, opts, C.settings()),
                         name="catalog-zeki", daemon=True).start()
        audit(engine, user, "run", "catalog", cid, cat["baslik"], {"is": "Zeki AI metin/gerekçe", **opts})
        return job

    @app.get(P + "/jobs/{jid}")
    def cn_job(jid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(C.job_get, engine, tenant, jid)

    def catalog_flow(action: str, explicit: bool):
        def handler(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
            engine, tenant, user, _ = ctx(request)
            if explicit:
                need(user, FEATURE_APPROVE, "Katalog ve bülten onayı")
            out = call(C.transition, engine, tenant, user, cid, action, body.get("note"))
            audit(engine, user, {"approve": "approve", "reject": "reject"}.get(action, "update"), "catalog", cid, out["baslik"],
                  {"islem": action, "durum": out["durum"], "not": body.get("note")})
            return out
        return handler

    for act, explicit in (("submit", False), ("withdraw", False), ("approve", True), ("reject", True), ("publish", False),
                          ("archive", False), ("reopen", False)):
        app.add_api_route(P + "/catalogs/{cid}/" + act, catalog_flow(act, explicit), methods=["POST"], name=f"cn_catalog_{act}")

    async def _catalog_export(cid: str, request: Request) -> tuple[Any, str, dict[str, Any], dict[str, Any]]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        pool = await run_in_threadpool(pool_of, engine, tenant, False)
        d = await run_in_threadpool(call, C.detail, engine, tenant, cid, pool, C.settings())
        texts = await run_in_threadpool(call, S.read_texts, crm(), schema(), [k["crmKitapId"] for k in d["kitaplar"]])
        return engine, user, d, texts

    def _file_name(d: dict[str, Any], ext: str) -> str:
        base = C.fold(d["baslik"]).replace(" ", "-")
        base = "".join(ch for ch in base if ch.isalnum() or ch == "-")[:60] or "katalog"
        return f"{base}.{ext}"

    @app.get(P + "/catalogs/{cid}/export.xlsx")
    async def cn_catalog_xlsx(cid: str, request: Request) -> Response:
        engine, user, d, texts = await _catalog_export(cid, request)
        data = await run_in_threadpool(C.catalog_xlsx, d, texts)
        audit(engine, user, "run", "catalog_export", cid, d["baslik"], {"bicim": "xlsx", "kitap": len(d["kitaplar"])})
        return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{_file_name(d, "xlsx")}"'})

    @app.get(P + "/catalogs/{cid}/package.zip")
    async def cn_catalog_package(cid: str, request: Request) -> Response:
        engine, user, d, texts = await _catalog_export(cid, request)
        data = await run_in_threadpool(C.package_zip, d, texts)
        audit(engine, user, "run", "catalog_export", cid, d["baslik"], {"bicim": "tasarım paketi", "kitap": len(d["kitaplar"])})
        return Response(data, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{_file_name(d, "zip")}"'})

    @app.get(P + "/catalogs/{cid}/preview.pdf")
    async def cn_catalog_pdf(cid: str, request: Request, perPage: int = 0) -> Response:
        engine, user, d, texts = await _catalog_export(cid, request)
        data = await run_in_threadpool(call, C.preview_pdf, d, texts, perPage or C.settings()["pdfPerPage"])
        audit(engine, user, "run", "catalog_export", cid, d["baslik"], {"bicim": "pdf", "kitap": len(d["kitaplar"])})
        return Response(data, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{_file_name(d, "pdf")}"'})

    # ------------------------------------------------------------------ bülten

    def price_source() -> str:
        return C.settings()["priceSource"]

    @app.get(P + "/newsletters")
    def cn_newsletters(request: Request, durum: str = "acik") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return N.list_newsletters(engine, tenant, durum)

    @app.post(P + "/newsletters", status_code=201)
    def cn_newsletter_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(N.create, engine, tenant, user, body)
        audit(engine, user, "create", "newsletter", out["id"], out["baslik"], {"segment": out["segment"]})
        return out

    @app.get(P + "/newsletters/{nid}")
    async def cn_newsletter(nid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        pool = pool_of(engine, tenant, required=False)
        return await run_in_threadpool(call, N.detail, engine, tenant, nid, pool, price_source())

    @app.patch(P + "/newsletters/{nid}")
    async def cn_newsletter_update(nid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        out, diff = await run_in_threadpool(call, N.update, engine, tenant, nid, body)
        if {"giris", "konu"} & set(body):
            await run_in_threadpool(N.rebuild_html, engine, tenant, nid, pool_of(engine, tenant, required=False), price_source())
        if diff:
            audit(engine, user, "update", "newsletter", nid, out["baslik"], diff)
        return await run_in_threadpool(call, N.detail, engine, tenant, nid, pool_of(engine, tenant, required=False), price_source())

    @app.delete(P + "/newsletters/{nid}")
    def cn_newsletter_delete(nid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(N.delete, engine, tenant, nid)
        audit(engine, user, "delete", "newsletter", nid, out["baslik"])
        return {"ok": True}

    @app.post(P + "/segments/count")
    async def cn_segment_count(body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Segment büyüklüğü ve izin dağılımı — YALNIZ SAYILAR. Kişi listesi, adres ya da kimlik dönmez."""
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        need(user, FEATURE_SEGMENT, "Segment sayacı")
        seg = N.normalize_segment(body.get("segment"))
        ncfg = N.settings()
        sql = N.segment_sql(S.prefix(schema()), seg, ncfg["requireKvkk"], C.today())
        rows = await run_in_threadpool(call, lambda: crm()(sql))
        res = N.segment_result(rows[0] if rows else None, ncfg["requireKvkk"])
        nid = str(body.get("newsletterId") or "")
        if nid:
            await run_in_threadpool(call, N.set_segment_count, engine, tenant, nid, seg, res)
        pool = pool_of(engine, tenant, required=False)
        res["tanim"] = N.describe(seg, interests_of(pool or {}))
        res["zaman"] = C.iso(C.now())
        audit(engine, user, "run", "newsletter_segment", nid or None, res["tanim"][:300], {"izinli": res["izinli"], "segment": seg})
        return res

    @app.post(P + "/newsletters/{nid}/suggest")
    async def cn_newsletter_suggest(nid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        pool = await run_in_threadpool(pool_of, engine, tenant)
        d = await run_in_threadpool(call, N.detail, engine, tenant, nid, None, price_source())
        res = await run_in_threadpool(N.suggest, pool, d["segment"], d.get("ozelGun"), interests_of(pool), C.settings(), N.settings(),
                                      [k["crmKitapId"] for k in d["kitaplar"]], price_source())
        page, size = max(0, int(body.get("page") or 0)), min(200, max(10, int(body.get("pageSize") or 30)))
        return {**{k: v for k, v in res.items() if k != "items"}, "items": res["items"][page * size:(page + 1) * size],
                "page": page, "pageSize": size}

    @app.put(P + "/newsletters/{nid}/items")
    async def cn_newsletter_items(nid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        pool = await run_in_threadpool(pool_of, engine, tenant)
        out = await run_in_threadpool(call, N.set_items, engine, tenant, nid, body.get("items"), pool, price_source())
        audit(engine, user, "update", "newsletter_item", nid, out["baslik"], {"kitap": len(out["kitaplar"])})
        return out

    @app.post(P + "/newsletters/{nid}/draft", status_code=202)
    def cn_newsletter_draft(nid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        pool = pool_of(engine, tenant)
        chat = chatter("bulten", False, 2500)
        if chat is None:
            raise HTTPException(503, detail={"code": "CATALOG", "message": "Zeki AI bu kurulumda bağlı değil; taslak yazılamıyor. "
                                                                          "Giriş ve kitap metinleri elle yazılabilir."})
        d = call(N.get, engine, tenant, nid)
        if d["durum"] != "taslak":
            raise HTTPException(409, detail={"code": "CATALOG", "message": "Taslak yalnız taslak bültene yazılır."})
        job = call(C.job_create, engine, tenant, user, "bulten-taslak", nid)
        threading.Thread(target=N.run_draft, args=(engine, tenant, job["id"], nid, chat, texts_reader(), pool, price_source(),
                                                   interests_of(pool), N.settings()), name="newsletter-draft", daemon=True).start()
        audit(engine, user, "run", "newsletter", nid, d["baslik"], {"is": "Zeki AI taslak"})
        return job

    def newsletter_flow(action: str, explicit: bool):
        def handler(nid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
            engine, tenant, user, _ = ctx(request)
            if explicit:
                need(user, FEATURE_APPROVE, "Katalog ve bülten onayı")
            out = call(N.transition, engine, tenant, user, nid, action, body.get("note"))
            audit(engine, user, {"approve": "approve", "reject": "reject"}.get(action, "update"), "newsletter", nid, out["baslik"],
                  {"islem": action, "durum": out["durum"], "not": body.get("note")})
            return out
        return handler

    for act, explicit in (("submit", False), ("withdraw", False), ("approve", True), ("reject", True), ("mark-sent", False),
                          ("archive", False), ("reopen", False)):
        app.add_api_route(P + "/newsletters/{nid}/" + act, newsletter_flow(act, explicit), methods=["POST"],
                          name=f"cn_newsletter_{act.replace('-', '_')}")

    @app.get(P + "/newsletters/{nid}/html")
    def cn_newsletter_html(nid: str, request: Request) -> Response:
        """Gönderime hazır HTML (yalnız onaylı bülten indirilir; taslak ekranda önizlenir)."""
        engine, tenant, user, _ = ctx(request)
        d = call(N.detail, engine, tenant, nid, None, price_source())
        if d["durum"] not in ("onayli", "gonderildi", "arsiv"):
            raise HTTPException(409, detail={"code": "CATALOG", "message": "Gönderime hazır HTML yalnız onaylı bülten için indirilir."})
        if not d.get("html"):
            raise HTTPException(409, detail={"code": "CATALOG", "message": "Bültenin HTML'i yok."})
        audit(engine, user, "run", "newsletter_export", nid, d["baslik"], {"bicim": "html"})
        name = _file_name(d, "html")
        return HTMLResponse(d["html"], headers={"Content-Disposition": f'attachment; filename="{name}"',
                                                "X-Content-Type-Options": "nosniff"})

    @app.post(P + "/newsletters/{nid}/results", status_code=201)
    async def cn_newsletter_result(nid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Sonuç: `dosya` (e-posta aracının CSV dışa aktarımı; yalnız toplamlar alınır, dosya saklanmaz), elle sayılar ya
        da bağlı CRM kampanyasından okuma (`kaynak: crm`)."""
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        src = str(body.get("kaynak") or ("dosya" if body.get("dosya") else "elle"))
        note = body.get("not")
        if src == "dosya":
            parsed = await run_in_threadpool(call, N.parse_results, str(body.get("dosya") or ""))
            counts, note = parsed, (note or parsed["not"])
        elif src == "crm":
            d = await run_in_threadpool(call, N.get, engine, tenant, nid)
            if not d.get("crmKampanya"):
                raise HTTPException(400, detail={"code": "CATALOG", "message": "Önce bülteni CRM kampanyasına bağlayın."})
            got = await run_in_threadpool(call, S.campaign_counts, crm(), schema(), d["crmKampanya"])
            if got is None:
                raise HTTPException(404, detail={"code": "CATALOG", "message": "CRM'de bu kampanya bulunamadı."})
            counts = {"sent": got.get("toplam"), "opened": got.get("okunan"), "clicked": got.get("tiklanan")}
            note = f"CRM kampanyası: {got.get('ad') or ''}"
        else:
            counts = body.get("sayilar") or {}
            src = "elle"
        out = await run_in_threadpool(call, N.add_result, engine, tenant, user, nid, src, counts, note)
        audit(engine, user, "create", "newsletter_result", nid, None, {k: out[k] for k in ("kaynak", "gonderilen", "acilan", "tiklanan")})
        return out

    @app.delete(P + "/newsletters/{nid}/results/{rid}")
    def cn_newsletter_result_delete(nid: str, rid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(N.delete_result, engine, tenant, nid, rid)
        audit(engine, user, "delete", "newsletter_result", nid, None, {"kaynak": out["kaynak"], "gonderilen": out["gonderilen"]})
        return {"ok": True}

    @app.get(P + "/report")
    async def cn_report(request: Request, crmKampanyalar: bool = True) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        out = await run_in_threadpool(N.report, engine, tenant)
        out["crm"] = None
        if crmKampanyalar:
            try:
                out["crm"] = await run_in_threadpool(S.read_campaigns, crm(), schema())
            except Exception as e:  # noqa: BLE001 — CRM okunamazsa portal sonuçları yine görünür
                out["crmHata"] = str(e)[:200]
        return out

    # ------------------------------------------------------------------ zamanlayıcı

    @app.post(P + "/run-due")
    def cn_run_due(request: Request) -> dict[str, Any]:
        """Zamanlayıcı: havuzu yeniler, açık katalogların uyarılarını yazar, CRM'e bağlı bültenlerin sonucunu okur, kritik
        uyarı ve onay bekleyenleri iç ekibe tek özet e-postayla bildirir (okura/bayiye hiçbir gönderim yok)."""
        require_caller(request)
        from semantic_bridge.budget_api import _send_mail

        r = rt()
        engine, tenant = r.store.engine, r.settings.tenant_id
        C.ensure(engine)
        N.ensure(engine)
        out: dict[str, Any] = {}
        try:
            pool = build_pool(engine, tenant)
            out["havuz"] = {"kitap": len(pool["books"]), "logoSon": pool.get("logoSon"), "notlar": pool.get("notes")}
        except Exception as e:  # noqa: BLE001 — havuz okunamazsa son havuzla uyarılar yine yenilenir
            out["havuzHata"] = str(e)[:300]
            pool = pool_of(engine, tenant, required=False)
        summary = C.refresh_alerts(engine, tenant, pool, C.settings()) if pool else []
        out["katalog"] = len(summary)
        out["kritik"] = sum(s["kritik"] for s in summary)
        n_crm = 0
        for nl in N.crm_linked(engine, tenant):
            try:
                got = S.campaign_counts(crm(), schema(), nl["sent_ref"])
                if got and N.record_crm_result(engine, tenant, nl["id"], got):
                    n_crm += 1
            except Exception as e:  # noqa: BLE001
                out.setdefault("crmHata", str(e)[:200])
        out["crmSonuc"] = n_crm
        pend = {**C.pending_counts(engine, tenant), **N.pending_counts(engine, tenant)}
        cfg = C.settings()
        mail = "bos"
        if out["kritik"] or pend["katalogOnayda"] or pend["bultenOnayda"]:
            if cfg["recipients"]:
                link = (admin_mod.conf("ALERT_LINK") or "").split("/uyarilar")[0]
                lines = [f"Katalog ve bülten — {C.tr_day(C.today().isoformat())}", ""]
                if pool and pool.get("logoSon"):
                    lines.append(f"Stok ve satış verisi {C.tr_day(pool['logoSon'])} tarihine kadardır.")
                for s in summary:
                    if s["kritik"]:
                        lines += ["", f"{s['baslik']} ({C.STATUSES.get(s['durum'])}): {s['kritik']} kritik uyarı"]
                        lines += [f"  - {x}" for x in s["satirlar"]]
                if pend["katalogOnayda"] or pend["bultenOnayda"]:
                    lines += ["", f"Onay bekleyen: {pend['katalogOnayda']} katalog, {pend['bultenOnayda']} bülten."]
                if link:
                    lines += ["", f"{link}/katalog-bulten"]
                mail = _send_mail(f"Katalog ve bülten: {out['kritik']} kritik uyarı", "\n".join(lines), cfg["recipients"])
            else:
                mail = "alici_yok"
        out["eposta"] = mail
        out["bekleyen"] = pend
        C.meta_set(engine, tenant, "last_run", {**out, "zaman": C.iso(C.now())})
        return out

    return state
