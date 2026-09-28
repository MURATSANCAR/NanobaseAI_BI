"""M33 İhale takibi uçları: /api/v1/tenders/*.

Sayfa kapısı `access.RULES` (`sayfa:ihale`). Yazma (ihale kaydı, dosya, kalem, eşleştirme, kontrol listesi, karar önerisi,
sonuç) `ozellik:ihale.duzenle`; şirket belge arşivine yazma `ozellik:ihale.belge`; teklif tablosu Excel'i
`ozellik:veri.disa-aktar` (`FEATURE_RULES`). Karar onayı/geri gönderme açıkça verilen `ozellik:ihale.karar` ile burada
denetlenir (öneren onaylayamaz, `tenders.decide`). İlan kaynağı uçları `ozellik:ihale.kaynak-yonet` ister ve
`TENDER_WATCH_ENABLED=0` iken «bu ortamda kapalı» döner.

Zamanlayıcı (`timas-tenders.timer`, her gün 07:30) yalnız `POST /api/v1/tenders/run-due`'yu çağırır: son teklif ve
belge geçerliliği hatırlatmaları (`TENDER_ALERT_RECIPIENTS`'e tek özet e-posta; kuruma hiçbir gönderim yok) ve kamu
satış özetinin tazelenmesi.

Model çağrıları LLM kapısından: `rt.llm_for("ihale", NORMAL)` (`choose` ile kalem eşleştirme ve ilan sınıflaması,
`chat` ile şartname özeti ve karar özeti metni). `LlmClient` doğrudan kurulmaz.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import date
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import tenders as T
from semantic_bridge import tenders_sources as src

log = logging.getLogger("semantic.tenders.api")
P = "/api/v1/tenders"
FEATURE_EDIT = "ozellik:ihale.duzenle"
FEATURE_DECIDE = "ozellik:ihale.karar"
FEATURE_DOCS = "ozellik:ihale.belge"
FEATURE_SOURCE = "ozellik:ihale.kaynak-yonet"
FEATURE_EXPORT = "ozellik:veri.disa-aktar"
CATALOG_TTL = 30 * 60
SALES_TTL = 10 * 60


class _Cache:
    """Katalog ve kamu satış özeti için süreli bellek. Aynı anahtarı iki iş parçacığı birlikte okumaz."""

    def __init__(self) -> None:
        self._data: dict[Any, tuple[float, Any]] = {}
        self._locks: dict[Any, threading.Lock] = {}
        self._guard = threading.Lock()

    def get(self, key: Any, ttl: float, load: Callable[[], Any], fresh: bool = False) -> Any:
        with self._guard:
            lock = self._locks.setdefault(key, threading.Lock())
        with lock:
            hit = self._data.get(key)
            if hit and not fresh and time.monotonic() - hit[0] < ttl:
                return hit[1]
            val = load()
            self._data[key] = (time.monotonic(), val)
            return val


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None], can: Callable[[str, str], bool]):
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod

    cache = _Cache()

    def crm_path() -> str:
        return os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")

    def schema() -> str:
        return admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo"

    def logo():
        return src.runner(rt().settings.connection_file)

    def crm():
        return src.runner(crm_path())

    def llm():
        try:
            from semantic_layer.runtime.llm_queue import NORMAL
            return rt().llm_for("ihale", NORMAL)
        except Exception:  # noqa: BLE001 — model tanımlı değil
            return None

    def chooser() -> Optional[Callable[[str, list[str]], Any]]:
        m = llm()
        if m is None or not hasattr(m, "choose"):
            return None
        return lambda prompt, choices: m.choose(prompt, choices)

    def chatter(max_tokens: int, temperature: float = 0.0) -> Optional[Callable[[list[dict[str, str]]], str]]:
        m = llm()
        if m is None:
            return None
        return lambda messages: m.chat(messages, max_tokens=max_tokens, temperature=temperature)

    def catalog(fresh: bool = False) -> T.Catalog:
        def load() -> T.Catalog:
            data = src.read_catalog(crm(), logo(), schema())
            return T.Catalog(data["books"], data["notes"])
        return cache.get("catalog", CATALOG_TTL, load, fresh)

    def enricher(cat: T.Catalog) -> Callable[[list[str]], dict[str, dict[str, Any]]]:
        def enrich(codes: list[str]) -> dict[str, dict[str, Any]]:
            codes = [c for c in codes if c in cat.by_code]
            stock: dict[str, float] = {}
            prices: dict[str, dict[str, Any]] = {}
            try:
                run = logo()
                stock = src.read_stock(run, codes)
                prices = src.read_prices(run, codes)
            except src.SourceError as e:
                note = f"Logo okunamadı ({e}); stok ve Logo fiyatı boş."
                if note not in cat.notes:
                    cat.notes.append(note)
            costs = src.unit_costs(getattr(app.state, "unit_cost", None), codes)
            return T.enrich_codes(cat, codes, stock, prices, costs, T.settings())
        return enrich

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
        except T.TenderError as e:
            raise HTTPException(status_code=e.status, detail={"code": "TENDER", "message": str(e)}) from e
        except src.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "TENDER_SOURCE", "message": str(e)}) from e

    def need(user: str, key: str, what: str) -> None:
        if not can(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def audit(engine, user, action, kind, oid, title, detail=None) -> None:
        admin_mod.audit(engine, user, action, kind, oid, title, detail)

    async def body_bytes(request: Request, max_mb: int) -> bytes:
        if int(request.headers.get("content-length") or 0) > max_mb * 1024 * 1024:
            raise HTTPException(413, detail={"code": "TENDER", "message": f"Dosya {max_mb} MB sınırını aşıyor."})
        return await request.body()

    # ------------------------------------------------------------------ genel

    @app.get(P + "/meta")
    def tenders_meta(request: Request) -> dict[str, Any]:
        _, _, user, display = ctx(request)
        out = T.meta()
        out["me"] = {"username": user, "display": display, "canEdit": can(user, FEATURE_EDIT),
                     "canDecide": can(user, FEATURE_DECIDE), "canDocs": can(user, FEATURE_DOCS),
                     "canExport": can(user, FEATURE_EXPORT), "canSource": can(user, FEATURE_SOURCE)}
        out["modelVar"] = llm() is not None
        return out

    @app.get(P)
    def tenders_list(request: Request, durum: str = "acik", il: str = "", kurumTuru: str = "", q: str = "",
                     son: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(T.list_tenders, engine, tenant, durum=durum, il=il, kurum_turu=kurumTuru, q=q, son=son)

    @app.post(P, status_code=201)
    def tenders_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(T.create, engine, tenant, user, body)
        audit(engine, user, "create", "tender", out["id"], f"{out['kurum']} — {out['konu'][:120]}",
              {"kurumTuru": out["kurumTuru"], "sonTeklif": out["sonTeklifTarihi"]})
        # İlan konusu kitap alımı mı: model varsa arka planda sorulur, kaydı bekletmez.
        choose = chooser()
        if choose is not None:
            def classify() -> None:
                try:
                    res = T.classify_notice(out["konu"], choose)
                    if res is not None:
                        with engine.begin() as c:
                            c.execute(T.TENDERS.update().where(T.TENDERS.c.id == out["id"]).values(kitap_ilani_json=T._dump(res)))
                except Exception as e:  # noqa: BLE001
                    log.warning("ihale ilan sınıflaması yazılamadı: %s", e)
            threading.Thread(target=classify, name="tender-classify", daemon=True).start()
        return out

    @app.get(P + "/calendar")
    def tenders_calendar(request: Request, gun: int = 90) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return T.calendar(engine, tenant, max(0, gun))

    @app.get(P + "/results")
    def tenders_results(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return T.results(engine, tenant)

    @app.get(P + "/public-sales")
    async def tenders_public_sales(request: Request, yil: int = 0, yenile: bool = False) -> dict[str, Any]:
        await run_in_threadpool(ctx, request)
        year = yil or date.today().year
        if not 2000 <= year <= 2100:
            raise HTTPException(400, detail={"code": "TENDER", "message": "Yıl geçersiz."})
        channel = T.settings()["publicChannel"]
        out = await run_in_threadpool(call, cache.get, ("sales", year), SALES_TTL,
                                      lambda: src.read_public_sales(logo(), crm(), schema(), year, channel), yenile)
        return _sales_view(out)

    def _sales_view(d: dict[str, Any]) -> dict[str, Any]:
        rows = d["rows"]
        by_city: dict[str, dict[str, Any]] = {}
        for r in rows:
            c = by_city.setdefault(r["il"] or "(boş)", {"il": r["il"] or "(boş)", "ciro": 0.0, "adet": 0.0, "cari": 0})
            c["ciro"] += r["ciro"]
            c["adet"] += r["adet"]
            c["cari"] += 1
        by_src = {k: round(sum(r["ciro"] for r in rows if r["kaynak"] == k), 2) for k in ("crm", "kanal", "ikisi")}
        return {**d, "toplamCiro": round(sum(r["ciro"] for r in rows), 2), "toplamAdet": sum(r["adet"] for r in rows),
                "cariSayisi": len(rows), "kaynakCiro": by_src,
                "iller": sorted(by_city.values(), key=lambda x: -x["ciro"])}

    # ------------------------------------------------------------------ şirket belge arşivi

    @app.get(P + "/documents")
    def tenders_documents(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return T.documents(engine, tenant)

    @app.post(P + "/documents", status_code=201)
    async def tenders_document_add(request: Request, ad: str = "", tur: str = "", gecerlilik: str = "", filename: str = "",
                                   note: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        data = await body_bytes(request, T.settings()["fileMaxMb"])
        out = await run_in_threadpool(call, T.add_document, engine, tenant, user,
                                      {"ad": ad, "tur": tur, "gecerlilik": gecerlilik, "not": note}, filename, data)
        audit(engine, user, "create", "tender_document", out["id"], out["ad"], {"tur": out["tur"], "gecerlilik": out["gecerlilik"],
                                                                                 "bytes": len(data)})
        return out

    @app.patch(P + "/documents/{did}")
    def tenders_document_update(did: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out, diff = call(T.update_document, engine, tenant, did, body)
        if diff:
            audit(engine, user, "update", "tender_document", did, out["ad"], diff)
        return out

    @app.delete(P + "/documents/{did}")
    def tenders_document_delete(did: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(T.delete_document, engine, tenant, did)
        audit(engine, user, "delete", "tender_document", did, out["ad"])
        return {"ok": True}

    @app.get(P + "/documents/{did}/file")
    def tenders_document_file(did: str, request: Request):
        engine, tenant, _, _ = ctx(request)
        path, name, mime = call(T.document_file, engine, tenant, did)
        return FileResponse(path, media_type=mime, filename=name, headers={"X-Content-Type-Options": "nosniff",
                                                                          "Cache-Control": "private, no-store"})

    # ------------------------------------------------------------------ zamanlayıcı ve ilan kaynağı

    @app.post(P + "/run-due")
    def tenders_run_due(request: Request) -> dict[str, Any]:
        """Zamanlayıcı: hatırlatmaları tek özet e-postayla gönderir (bir kez), kamu satış özetini tazeler."""
        require_caller(request)
        from semantic_bridge.budget_api import _send_mail

        r = rt()
        engine, tenant = r.store.engine, r.settings.tenant_id
        T.ensure(engine)
        cfg = T.settings()
        items = T.due_reminders(engine, tenant, cfg)
        recipients = [x.strip() for x in (admin_mod.conf("TENDER_ALERT_RECIPIENTS") or "").replace(";", ",").split(",") if "@" in x]
        link = (admin_mod.conf("ALERT_LINK") or "").split("/uyarilar")[0]
        link = f"{link}/ihale" if link else ""
        mail = "bos"
        if items:
            if recipients:
                mail = _send_mail(f"İhale takibi: {len(items)} hatırlatma", T.reminder_text(items, link), recipients)
                if mail == "sent":
                    T.mark_sent(engine, tenant, [i["key"] for i in items])
            else:
                mail = "alici_yok"
        sales: dict[str, Any] = {}
        try:
            year = date.today().year
            d = cache.get(("sales", year), SALES_TTL, lambda: src.read_public_sales(logo(), crm(), schema(), year, cfg["publicChannel"]), True)
            sales = {"year": year, "cari": len(d["rows"])}
        except src.SourceError as e:
            sales = {"error": str(e)}
        return {"hatirlatma": len(items), "eposta": mail, "alici": len(recipients), "kamuSatis": sales,
                "ilanIceAlma": "kapalı" if not cfg["watchEnabled"] else "ikinci sürümde"}

    @app.get(P + "/watch/status")
    def tenders_watch_status(request: Request) -> dict[str, Any]:
        ctx(request)
        on = T.settings()["watchEnabled"]
        return {"enabled": on, "message": ("Resmî kaynaktan ilan içe alma bu ortamda kapalı; ilanlar elle ya da dosyayla girilir."
                                           if not on else "Resmî kaynaktan ilan içe alma ikinci sürümde gelecek; izinli kaynak tanımlanmadı.")}

    @app.post(P + "/watch/import")
    def tenders_watch_import(request: Request) -> dict[str, Any]:
        _, _, user, _ = ctx(request)
        need(user, FEATURE_SOURCE, "İlan kaynağı yönetimi")
        if not T.settings()["watchEnabled"]:
            raise HTTPException(409, detail={"code": "TENDER_WATCH_OFF", "message": "İlan içe alma bu ortamda kapalı."})
        raise HTTPException(501, detail={"code": "TENDER_WATCH", "message": "Resmî kaynaktan ilan içe alma ikinci sürümde; izinli kaynak tanımlı değil."})

    # ------------------------------------------------------------------ tek ihale

    @app.get(P + "/{tid}")
    def tenders_detail(tid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(T.detail, engine, tenant, tid)

    @app.patch(P + "/{tid}")
    def tenders_update(tid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out, diff = call(T.update, engine, tenant, user, tid, body)
        if diff:
            audit(engine, user, "update", "tender", tid, out["kurum"], diff)
        return out

    @app.delete(P + "/{tid}")
    def tenders_delete(tid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(T.delete, engine, tenant, tid)
        audit(engine, user, "delete", "tender", tid, out["kurum"])
        return {"ok": True}

    @app.post(P + "/{tid}/files", status_code=201)
    async def tenders_file_add(tid: str, request: Request, filename: str = "", tur: str = "sartname") -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        data = await body_bytes(request, T.settings()["fileMaxMb"])
        out = await run_in_threadpool(call, T.add_file, engine, tenant, user, tid, filename, data, tur)
        audit(engine, user, "upload", "tender_file", tid, out["ad"], {"tur": out["tur"], "bytes": out["boyut"]})
        return out

    @app.get(P + "/{tid}/files/{fid}")
    def tenders_file(tid: str, fid: str, request: Request):
        engine, tenant, _, _ = ctx(request)
        path, name, mime = call(T.file_of, engine, tenant, tid, fid)
        return FileResponse(path, media_type=mime, filename=name, headers={"X-Content-Type-Options": "nosniff",
                                                                          "Cache-Control": "private, no-store"})

    @app.delete(P + "/{tid}/files/{fid}")
    def tenders_file_delete(tid: str, fid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(T.delete_file, engine, tenant, tid, fid)
        audit(engine, user, "delete", "tender_file", tid, out["ad"])
        return {"ok": True}

    def _file_bytes(engine, tenant, tid, fid) -> tuple[str, bytes]:
        path, name, _ = T.file_of(engine, tenant, tid, fid)
        with open(path, "rb") as fh:
            return name, fh.read()

    @app.post(P + "/{tid}/summarize", status_code=202)
    def tenders_summarize(tid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        chat = chatter(2000)
        if chat is None:
            raise HTTPException(503, detail={"code": "TENDER", "message": "Zeki AI bu kurulumda tanımlı değil; özet çıkarılamıyor."})
        d = call(T.detail, engine, tenant, tid)
        fid = body.get("fileId") or next((f["id"] for f in reversed(d["dosyalar"]) if f["tur"] == "sartname"), None)
        if not fid:
            raise HTTPException(400, detail={"code": "TENDER", "message": "Önce şartname dosyasını yükleyin."})
        name, data = call(_file_bytes, engine, tenant, tid, fid)
        if T._ext(name) not in ("pdf", "png", "jpg", "jpeg", "tif", "tiff", "webp"):
            call(T.document_text, name, data)       # desteklenmeyen tür hemen söylenir; PDF/görüntü okuması işin içinde
        choose = chooser()
        cfg = T.settings()

        def work(progress):
            # Ortak belge okuma hattı: taranmış sayfalar OCR'la okunur (dakikalar sürebilir, bu yüzden işin içinde).
            text, reading = T.document_reading(name, data)
            summary = T.summarize_text(text, chat, cfg, progress, reading=reading)
            summary["dosya"] = name
            classify = T.classify_notice((summary.get("konu") or {}).get("deger") or d["konu"], choose)
            applied = T.apply_summary(engine, tenant, user, tid, summary, classify, choose)
            return {**applied, "atilan": summary["atilan"], "parca": summary["parca"], "okuma": summary.get("okuma")}

        out = call(T.start_job, engine, tenant, user, tid, "ozet", work)
        audit(engine, user, "run", "tender", tid, d["kurum"], {"is": "şartname özeti", "dosya": name})
        return out

    @app.post(P + "/{tid}/items/import")
    async def tenders_items_import(tid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        mode = str(body.get("mode") or "replace")
        if body.get("text"):
            parsed = T.parse_text(str(body["text"]))
            origin = "yapıştırılan metin"
        elif body.get("fileId"):
            name, data = await run_in_threadpool(call, _file_bytes, engine, tenant, tid, str(body["fileId"]))
            rows = await run_in_threadpool(call, T.extract_rows, name, data)
            parsed = T.parse_rows(rows)
            origin = name
        else:
            raise HTTPException(400, detail={"code": "TENDER", "message": "Metin ya da yüklenmiş dosya verin."})
        out = await run_in_threadpool(call, T.import_items, engine, tenant, user, tid, parsed, mode)
        audit(engine, user, "update", "tender_item", tid, None, {"iceAktarma": origin, "eklenen": out["eklenen"],
                                                                  "okunamayan": len(out["okunamayan"]), "bicim": mode})
        return out

    @app.post(P + "/{tid}/items/match", status_code=202)
    def tenders_items_match(tid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        choose = chooser()
        only = bool(body.get("onlyPending"))
        fresh = bool(body.get("refreshCatalog"))

        def work(progress):
            cat = catalog(fresh)
            return T.run_match(engine, tenant, tid, cat, choose, enricher(cat), progress, only_pending=only)

        out = call(T.start_job, engine, tenant, user, tid, "eslestirme", work)
        audit(engine, user, "run", "tender_item", tid, None, {"is": "kalem eşleştirme", "yalnizBekleyen": only,
                                                              "model": choose is not None})
        return out

    @app.get(P + "/{tid}/jobs/{jid}")
    def tenders_job(tid: str, jid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(T.job, engine, tenant, tid, jid)

    @app.patch(P + "/{tid}/items/{sira}")
    async def tenders_item_update(tid: str, sira: int, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)

        def enrich(codes: list[str]) -> dict[str, dict[str, Any]]:
            return enricher(catalog())(codes)

        out, diff = await run_in_threadpool(call, T.update_item, engine, tenant, user, tid, sira, body, enrich)
        if diff:
            audit(engine, user, "update", "tender_item", f"{tid}:{sira}", out["metin"][:120], diff)
        return out

    @app.get(P + "/{tid}/catalog-search")
    async def tenders_catalog_search(tid: str, request: Request, q: str = "") -> dict[str, Any]:
        """Kalemi elle eşleştirmek için katalog araması (ad, yazar, stok kodu ya da ISBN)."""
        await run_in_threadpool(ctx, request)
        cat = await run_in_threadpool(call, catalog)
        qs = q.strip()
        if len(qs) < 2:
            return {"items": []}
        isbn = T.norm_isbn(qs)
        if isbn and isbn in cat.by_isbn:
            ids = [(i, 1.0) for i in cat.by_isbn[isbn]]
        elif qs in cat.by_code:
            ids = [(cat.books.index(cat.by_code[qs]), 1.0)]
        else:
            ids = cat.candidates(qs, None, 30, 0.2)
        return {"items": [{"stokKodu": cat.books[i]["kod"], "ad": cat.books[i]["ad"], "yazar": cat.books[i]["yazar"],
                           "yayinevi": cat.books[i]["yayinevi"], "isbn": (cat.books[i].get("isbn") or [None])[0], "benzerlik": s}
                          for i, s in ids if cat.books[i].get("kod")]}

    @app.get(P + "/{tid}/pricing.xlsx")
    def tenders_pricing(tid: str, request: Request) -> Response:
        engine, tenant, user, _ = ctx(request)
        d = call(T.detail, engine, tenant, tid)
        data = T.pricing_xlsx(d)
        audit(engine, user, "run", "tender_export", tid, f"Teklif fiyat tablosu — {d['kurum']}",
              {"araToplam": d["toplamlar"]["araToplam"], "kalem": d["toplamlar"]["fiyatli"]})
        return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="teklif-tablosu-{tid[:8]}.xlsx"'})

    @app.get(P + "/{tid}/checklist")
    def tenders_checklist(tid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(T.checklist, engine, tenant, tid)

    @app.patch(P + "/{tid}/checklist")
    def tenders_checklist_update(tid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out, changes = call(T.update_checklist, engine, tenant, user, tid, body)
        audit(engine, user, "update", "tender", tid, "Belge kontrol listesi", changes)
        return out

    @app.post(P + "/{tid}/brief")
    async def tenders_brief(tid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        d = await run_in_threadpool(call, T.detail, engine, tenant, tid)
        out = await run_in_threadpool(T.brief_text, d["kararOzeti"], chatter(600, 0.2))
        await run_in_threadpool(call, T.set_brief, engine, tenant, user, tid, out["metin"])
        audit(engine, user, "run", "tender", tid, d["kurum"], {"is": "karar özeti", "kaynak": out["kaynak"]})
        return out

    # ------------------------------------------------------------------ karar ve sonuç

    @app.post(P + "/{tid}/decision/submit", status_code=201)
    def tenders_decision_submit(tid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(T.submit_decision, engine, tenant, user, tid, body)
        audit(engine, user, "create", "tender_decision", out["id"], out["kararAdi"],
              {"ihale": tid, "teklifToplami": out["teklifToplami"], "fiyatOrani": out["fiyatOrani"]})
        return out

    @app.post(P + "/{tid}/decision/withdraw")
    def tenders_decision_withdraw(tid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(T.withdraw_decision, engine, tenant, user, tid)
        audit(engine, user, "update", "tender_decision", out["id"], out["kararAdi"], {"ihale": tid, "durum": "geri çekildi"})
        return out

    @app.post(P + "/{tid}/decision/approve")
    def tenders_decision_approve(tid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, FEATURE_DECIDE, "İhale karar onayı")
        out = call(T.decide, engine, tenant, user, tid, True, body.get("note"))
        audit(engine, user, "approve", "tender_decision", out["id"], out["kararAdi"],
              {"ihale": tid, "teklifToplami": out["teklifToplami"], "not": body.get("note")})
        return out

    @app.post(P + "/{tid}/decision/reject")
    def tenders_decision_reject(tid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, FEATURE_DECIDE, "İhale karar onayı")
        out = call(T.decide, engine, tenant, user, tid, False, body.get("note"))
        audit(engine, user, "reject", "tender_decision", out["id"], out["kararAdi"], {"ihale": tid, "not": body.get("note")})
        return out

    @app.post(P + "/{tid}/result")
    def tenders_result(tid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(T.record_result, engine, tenant, user, tid, body)
        audit(engine, user, "update", "tender_result", tid, out["sonucAdi"],
              {"kazanan": out["kazanan"], "kazananFiyat": out["kazananFiyat"], "bizimFiyat": out["bizimFiyat"]})
        return out

    return cache
