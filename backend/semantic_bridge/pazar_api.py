"""M39 Pazar araştırması ve rekabet uçları: /api/v1/pazar/*.

Sayfa kapıları `access.RULES`: özet, iç göstergeler ve yönetim özeti `sayfa:pazar-arastirma`; rakip listesi, matris,
kategori eşlemesi, emsal ve izlenen rakipler `sayfa:pazar-rakipler`; sektör raporları ve rakamları
`sayfa:pazar-raporlar` (yüklenen dosya yalnız bu yetkiyle iner). İşlem yetkileri `FEATURE_RULES`: rapor yükleme ve
rakam çıkarımı `ozellik:pazar.rapor-yukle`, rakam kararı `ozellik:pazar.rakam-onay`, eşleme kararı / öneri / kaynak
yenileme `ozellik:pazar.kategori-esleme`, özet taslağı ve onaya gönderme `ozellik:pazar.ozet-yaz`, matris dışa
aktarımı `ozellik:veri.disa-aktar`. Özet onayı / geri gönderme açıkça verilen `ozellik:pazar.ozet-onay` ile burada
denetlenir (yazan ya da gönderen onaylayamaz).

Zamanlayıcı (`timas-pazar.timer`, pazartesi 05:30) yalnız `POST /api/v1/pazar/run-due`'yu çağırır: CRM rakip katalog ve
TİMAŞ kitapları, Logo iç göstergeleri, yeni ham kategoriler için eşleme önerisi (süre bütçesiyle; bitmeyen sonraki
tura kalır), tazelik uyarısı ve ayın ilk haftasında geçen ayın özet taslağı. Dış tarama yok.

Model çağrıları LLM kapısından: `rt.llm_for("pazar", …)` — eşleme önerisi, rapor çıkarımı ve özet düşük öncelikli
(`BATCH`), emsal sıralaması ekranda beklendiği için `NORMAL`. `LlmClient` doğrudan kurulmaz. CRM'e ve Logo'ya yazılmaz.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import pazar as P
from semantic_bridge import pazar_sources as src

log = logging.getLogger("semantic.pazar.api")
B = "/api/v1/pazar"
CRM_FILE_DEFAULT = "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"
F_UPLOAD = "ozellik:pazar.rapor-yukle"
F_FIGURE = "ozellik:pazar.rakam-onay"
F_MAP = "ozellik:pazar.kategori-esleme"
F_WRITE = "ozellik:pazar.ozet-yaz"
F_APPROVE = "ozellik:pazar.ozet-onay"
F_EXPORT = "ozellik:veri.disa-aktar"


class Job:
    """Arka plan işi: tek iş parçacığı, durum ekrana yoklanır."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.lock = threading.Lock()
        self.state: dict[str, Any] = {"running": False, "step": None, "startedAt": None, "finishedAt": None,
                                      "error": None, "result": None}
        self.thread: Optional[threading.Thread] = None

    def running(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def status(self) -> dict[str, Any]:
        return {**self.state, "running": self.running()}

    def start(self, work: Callable[[], Any]) -> bool:
        with self.lock:
            if self.running():
                return False

            def run() -> None:
                self.state.update({"startedAt": P.iso(P.now()), "finishedAt": None, "error": None, "result": None})
                try:
                    self.state["result"] = work()
                except Exception as e:  # noqa: BLE001
                    log.warning("pazar %s işi başarısız: %s", self.name, e)
                    self.state["error"] = str(e)[:400]
                finally:
                    self.state["finishedAt"] = P.iso(P.now())
                    self.state["step"] = None

            self.thread = threading.Thread(target=run, name=f"pazar-{self.name}", daemon=True)
            self.thread.start()
            return True


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None], can: Callable[[str, str], bool]):
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod

    sync_job, suggest_job = Job("kaynak"), Job("eslesme")
    extracting: dict[str, threading.Thread] = {}

    def crm_file() -> str:
        return os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", CRM_FILE_DEFAULT)

    def schema() -> str:
        return admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo"

    def llm(priority: Optional[int]):
        try:
            return rt().llm_for("pazar", priority)
        except Exception:  # noqa: BLE001 — model tanımlı değil
            return None

    def _prio(name: str) -> int:
        from semantic_layer.runtime import llm_queue

        return getattr(llm_queue, name)

    def chooser(background: bool) -> Optional[Callable[[str, list[str]], Any]]:
        m = llm(_prio("BATCH" if background else "NORMAL"))
        if m is None or not hasattr(m, "choose"):
            return None
        return lambda prompt, choices: m.choose(prompt, choices)

    def chatter(max_tokens: int) -> Optional[Callable[[list[dict[str, str]]], str]]:
        m = llm(_prio("BATCH"))
        if m is None:
            return None
        return lambda messages: m.chat(messages, max_tokens=max_tokens, temperature=0.0)

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        require_caller(request)
        try:
            user, display = board_mod.session_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        r = rt()
        P.ensure(r.store.engine)
        admin_mod.ensure(r.store.engine)
        return r.store.engine, r.settings.tenant_id, user, display

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except P.PazarError as e:
            raise HTTPException(status_code=e.status, detail={"code": "PAZAR", "message": str(e)}) from e
        except src.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "PAZAR_SOURCE", "message": str(e)}) from e

    def need(user: str, key: str, what: str) -> None:
        if not can(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def audit(engine, user, action, kind, oid, title, detail=None) -> None:
        admin_mod.audit(engine, user, action, kind, oid, title, detail)

    def mail(subject: str, text: str) -> str:
        to = P.settings()["recipients"]
        if not to:
            return "no_recipients"
        from semantic_bridge.budget_api import _send_mail

        link = (admin_mod.conf("ALERT_LINK") or "").rstrip("/")
        return _send_mail(subject, text + (f"\n\n{link}/pazar-arastirma" if link else ""), to)

    # ------------------------------------------------------------------ kaynak okuma

    def sync(engine, tenant: str, actor: str, job: Optional[Job] = None) -> dict[str, Any]:
        st = P.settings()
        step = (lambda t: job.state.__setitem__("step", t)) if job else (lambda t: None)
        crm = src.runner(crm_file())
        step("CRM rakip kitaplar okunuyor")
        comp = src.read_competitors(schema(), crm, st["blurbChars"])
        step("CRM TİMAŞ kitapları, emsal bağları ve kitaplıklar okunuyor")
        own = src.read_own_books(schema(), crm, st["blurbChars"])
        links = src.read_links(schema(), crm)
        kitaplik = src.read_kitaplik(schema(), crm)
        errors: dict[str, str] = {}
        own_sales = None
        step("Logo satışları okunuyor (iç göstergeler)")
        try:
            own_sales = src.read_own_sales(src.runner(rt().settings.connection_file), st["ownYears"])
        except Exception as e:  # noqa: BLE001 — Logo okunamazsa önceki iç göstergeler korunur, hata ekranda
            errors["logo"] = str(e)[:300]
            log.warning("pazar: Logo okunamadı: %s", e)
        step("Köprü tablolarına yazılıyor")
        return P.apply_snapshot(engine, tenant, competitors=comp, own_books=own, links=links, kitaplik=kitaplik,
                                own_sales=own_sales, actor=actor, errors=errors)

    def jobs() -> dict[str, Any]:
        return {"kaynak": sync_job.status(), "eslesme": suggest_job.status(),
                "cikarim": sorted(rid for rid, t in extracting.items() if t.is_alive())}

    # ------------------------------------------------------------------ genel

    @app.get(B + "/meta")
    def pazar_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        st = P.settings()
        snap = P.meta_get(engine, tenant, "snapshot", {}) or {}
        return {"me": {"username": user, "display": display, "canUpload": can(user, F_UPLOAD), "canFigure": can(user, F_FIGURE),
                       "canMap": can(user, F_MAP), "canWrite": can(user, F_WRITE), "canApprove": can(user, F_APPROVE),
                       "canExport": can(user, F_EXPORT)},
                "settings": {k: st[k] for k in ("staleDays", "newDays", "compPageTol", "compPriceTol", "compModel",
                                                "fileMaxMb", "twoEyes", "ownYears")},
                "categorySource": snap.get("categorySource"), "categoryNote": snap.get("categoryNote"),
                "olcu": P.OLCU, "mapStatus": P.MAP_STATUS, "figureStatus": P.FIGURE_STATUS, "briefStatus": P.BRIEF_STATUS,
                "reportStatus": P.REPORT_STATUS, "dimensions": P.DIMENSIONS, "similarity": P.SIMILARITY,
                "modelVar": llm(None) is not None, "jobs": jobs(), "sellIn": P.SELL_IN_NOTE}

    @app.get(B + "/overview")
    def pazar_overview(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {**P.overview(engine, tenant), "jobs": jobs()}

    @app.get(B + "/freshness")
    def pazar_freshness(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return P.freshness(engine, tenant)

    @app.get(B + "/status")
    def pazar_status(request: Request) -> dict[str, Any]:
        ctx(request)
        return jobs()

    @app.post(B + "/refresh")
    def pazar_refresh(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        started = sync_job.start(lambda: sync(engine, tenant, user, sync_job))
        audit(engine, user, "run", "pazar_sync", None, "Pazar kaynakları yenilendi", {"started": started})
        return {"started": started, **jobs()}

    @app.post(B + "/run-due")
    def pazar_run_due(request: Request, budget: int = 0, brief: bool = True) -> dict[str, Any]:
        """Zamanlayıcı: kaynakları oku, eşleme öner, tazelik uyarısı, ayın ilk haftasında geçen ayın özet taslağı."""
        require_caller(request)
        r = rt()
        engine, tenant = r.store.engine, r.settings.tenant_id
        P.ensure(engine)
        admin_mod.ensure(engine)
        out: dict[str, Any] = {}
        if sync_job.running():
            out["sync"] = {"skipped": "başka bir okuma sürüyor"}
        else:
            try:
                out["sync"] = sync(engine, tenant, "sistem")
            except Exception as e:  # noqa: BLE001
                out["sync"] = {"error": str(e)[:400]}
        try:
            sec = float(budget or P.settings()["batchSeconds"])
            out["suggest"] = P.suggest_mapping(engine, tenant, P.to_suggest(engine, tenant), chooser(True), "Zeki AI (zamanlayıcı)", sec)
        except P.PazarError as e:
            out["suggest"] = {"skipped": str(e)}
        fr = P.freshness(engine, tenant)
        if fr["stale"]:
            out["staleMail"] = mail("Rakip kitap verisi güncel değil",
                                    f"CRM'deki rakip kitap verisi {fr['ageDays']} gündür güncellenmedi (eşik {fr['staleDays']} gün). "
                                    f"Son kayıt: {fr['lastChange']}. Pazar ekranlarındaki rakip karşılaştırmaları bu tarihe göredir.")
        if brief:
            donem = P.due_brief_donem(engine, tenant)
            if donem:
                try:
                    b = P.draft_brief(engine, tenant, "Zeki AI (zamanlayıcı)", donem, chatter(3000))
                    audit(engine, "sistem", "create", "pazar_brief", b["id"], f"Pazar özeti taslağı {b['donemAd']}",
                          {"kaynak": len(b["kaynaklar"]), "reddedilen": len(b["reddedilen"])})
                    out["brief"] = {"id": b["id"], "donem": donem,
                                    "mail": mail(f"Pazar özeti taslağı hazır — {b['donemAd']}",
                                                 f"{b['donemAd']} pazar özeti taslağı yazıldı ({len(b['kaynaklar'])} kaynak). "
                                                 "Düzenleyip onaya gönderebilirsiniz.")}
                except P.PazarError as e:
                    out["brief"] = {"skipped": str(e), "donem": donem}
                except Exception as e:  # noqa: BLE001 — model kesintisi: sonraki tur yeniden dener
                    out["brief"] = {"error": f"Zeki AI cevap vermedi: {str(e)[:200]}", "donem": donem}
        P.meta_set(engine, tenant, "last_run", {"at": P.iso(P.now()), **{k: v for k, v in out.items() if k != "sync"},
                                                "syncError": (out.get("sync") or {}).get("error")})
        return out

    @app.get(B + "/categories")
    def pazar_categories(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        snap = P.meta_get(engine, tenant, "snapshot", {}) or {}
        return {"items": P.categories(engine, tenant).items(), "source": snap.get("categorySource"), "note": snap.get("categoryNote")}

    # ------------------------------------------------------------------ rakipler ve matris

    @app.get(B + "/publishers")
    def pazar_publishers(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {"items": P.publishers(engine, tenant)}

    @app.get(B + "/competitors")
    def pazar_competitors(request: Request, yayinevi: str = "", kategori: str = "", q: str = "", durum: str = "",
                          page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(P.competitors, engine, tenant, yayinevi=yayinevi, kategori=kategori, q=q, durum=durum, page=max(0, page))

    def _matrix(engine, tenant, kategori, oneri, sayfaMin, sayfaMax, yayinevi, izlenen):
        return call(P.matrix, engine, tenant, kategori=kategori, include_suggested=oneri, sayfa_min=sayfaMin or None,
                    sayfa_max=sayfaMax or None, yayinevi_q=yayinevi, watch_only=izlenen)

    @app.get(B + "/matrix")
    async def pazar_matrix(request: Request, kategori: str = "", oneri: bool = False, sayfaMin: int = 0, sayfaMax: int = 0,
                           yayinevi: str = "", izlenen: bool = False) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        return await run_in_threadpool(_matrix, engine, tenant, kategori, oneri, sayfaMin, sayfaMax, yayinevi, izlenen)

    @app.get(B + "/matrix/export.csv")
    def pazar_matrix_export(request: Request, kategori: str = "", oneri: bool = False, sayfaMin: int = 0, sayfaMax: int = 0,
                            yayinevi: str = "", izlenen: bool = False) -> Response:
        engine, tenant, user, _ = ctx(request)
        m = _matrix(engine, tenant, kategori, oneri, sayfaMin, sayfaMax, yayinevi, izlenen)
        audit(engine, user, "run", "pazar_export", kategori or None, "Rakip fiyat ve format matrisi (CSV)",
              {"satir": len(m["rows"]) + len(m["timas"]), "kategori": (m.get("kategori") or {}).get("yol")})
        return Response(P.matrix_csv(m), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="rakip-matrisi.csv"'})

    @app.get(B + "/own-market")
    def pazar_own_market(request: Request, boyut: str = "kategori", yil: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(P.own_market, engine, tenant, boyut, yil or None)

    @app.get(B + "/own-books")
    def pazar_own_books(request: Request, q: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        items = P.own_books(engine, tenant, q, 20)
        return {"items": items, "limit": 20, "note": "İlk 20 eşleşme; aramayı daraltın." if len(items) == 20 else None}

    # ------------------------------------------------------------------ kategori eşlemesi

    @app.get(B + "/category-map")
    def pazar_category_map(request: Request, durum: str = "", q: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {**P.category_map(engine, tenant, durum=durum, q=q, page=max(0, page)), "job": suggest_job.status()}

    @app.post(B + "/category-map/decision")
    def pazar_category_decision(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        items = body.get("items") or []
        if not isinstance(items, list) or not items:
            raise HTTPException(status_code=400, detail={"code": "PAZAR", "message": "Karar verilecek kategori seçilmedi."})
        out = call(P.decide_mapping, engine, tenant, user, items)
        audit(engine, user, "approve", "pazar_map", None, f"Rakip kategori eşlemesi ({len(out['decided'])})",
              {"kararlar": [[d["ham"], d["durum"], d["kategoriYol"]] for d in out["decided"]][:200],
               "toplam": len(out["decided"]), "hata": len(out["errors"])})
        return out

    @app.post(B + "/category-map/suggest")
    def pazar_category_suggest(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        hams = [str(x) for x in (body.get("hams") or []) if str(x).strip()] or None
        todo = P.to_suggest(engine, tenant, hams)
        if not todo:
            return {"started": False, "queued": 0, "job": suggest_job.status()}
        fn = chooser(True)
        started = suggest_job.start(lambda: P.suggest_mapping(engine, tenant, todo, fn, user, float(P.settings()["batchSeconds"])))
        audit(engine, user, "run", "pazar_map", None, "Rakip kategori eşleme önerisi", {"started": started, "kuyruk": len(todo)})
        return {"started": started, "queued": len(todo), "job": suggest_job.status()}

    # ------------------------------------------------------------------ emsal

    @app.post(B + "/comparables")
    async def pazar_comparables(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        from semantic_bridge import book_similarity as BS

        def neighbors(base_id: Optional[str], q: str, n: int) -> dict[str, Any]:
            """Kitap benzerliği dizini (ortak yapı taşı 5): TİMAŞ kitabından başlandıysa onun vektörü, yoksa konu cümlesi."""
            res = BS.similar_books(engine, tenant, kitap_id=base_id, n=n) if base_id else {"hazir": False}
            if not res.get("hazir") and q.strip():
                res = BS.similar_books(engine, tenant, metin=q, n=n)
            return res

        out = await run_in_threadpool(call, P.comparables, engine, tenant, body, chooser(False), neighbors)
        audit(engine, user, "run", "pazar_comparables", body.get("crmKitapId"), "Emsal arama",
              {"q": str(body.get("q") or "")[:120], "rakip": len(out["rakip"]), "timas": len(out["timas"]), **out["counts"]})
        return out

    # ------------------------------------------------------------------ izlenen rakipler

    @app.get(B + "/watchlist")
    def pazar_watchlist(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return P.watchlist(engine, tenant)

    @app.post(B + "/watchlist", status_code=201)
    def pazar_watch_add(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(P.add_watch, engine, tenant, user, body)
        audit(engine, user, "create", "pazar_watch", out["id"], out["yayinevi"], {"kategori": out["kategoriId"]})
        return out

    @app.delete(B + "/watchlist/{wid}")
    def pazar_watch_delete(wid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(P.delete_watch, engine, tenant, wid)
        audit(engine, user, "delete", "pazar_watch", wid, out["yayinevi"])
        return {"ok": True}

    # ------------------------------------------------------------------ sektör raporları

    def alive(rid: str) -> bool:
        t = extracting.get(rid)
        return bool(t and t.is_alive())

    def recover(engine, tenant: str, rep: dict[str, Any]) -> dict[str, Any]:
        """Köprü yeniden başladıysa yarım kalan çıkarımın durumu «yarım kaldı»ya çekilir (sessizce takılı kalmaz)."""
        if rep["durum"] == "cikariliyor" and not alive(rep["id"]):
            prog = {**(rep.get("ilerleme") or {}), "hata": "Çıkarım yarım kaldı (servis yeniden başladı); yeniden başlatın."}
            P.set_report_state(engine, tenant, rep["id"], "hata", prog)
            rep = {**rep, "durum": "hata", "durumAd": P.REPORT_STATUS["hata"], "ilerleme": prog}
        return rep

    @app.get(B + "/reports")
    def pazar_reports(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = P.list_reports(engine, tenant)
        out["items"] = [recover(engine, tenant, r) for r in out["items"]]
        return out

    @app.post(B + "/reports", status_code=201)
    async def pazar_report_add(request: Request, filename: str = "", kaynak: str = "", yil: str = "", baslik: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        max_mb = P.settings()["fileMaxMb"]
        if int(request.headers.get("content-length") or 0) > max_mb * 1024 * 1024:
            raise HTTPException(413, detail={"code": "PAZAR", "message": f"Dosya {max_mb} MB sınırını aşıyor."})
        data = await request.body()
        out = await run_in_threadpool(call, P.add_report, engine, tenant, user, filename, data,
                                      {"kaynak": kaynak, "yil": yil, "baslik": baslik}, src.pages_of)
        audit(engine, user, "upload", "pazar_report", out["id"], out["baslik"],
              {"kaynak": out["kaynak"], "yil": out["yil"], "bayt": out["boyut"], "sayfa": out["sayfaSayisi"]})
        return out

    @app.get(B + "/reports/{rid}")
    def pazar_report(rid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return recover(engine, tenant, call(P.get_report, engine, tenant, rid))

    @app.get(B + "/reports/{rid}/file")
    def pazar_report_file(rid: str, request: Request):
        engine, tenant, user, _ = ctx(request)
        path, name, mime = call(P.report_file, engine, tenant, rid)
        audit(engine, user, "run", "pazar_report", rid, name, {"islem": "indir"})
        return FileResponse(path, media_type=mime, filename=name, headers={"X-Content-Type-Options": "nosniff",
                                                                          "Cache-Control": "private, no-store"})

    @app.delete(B + "/reports/{rid}")
    def pazar_report_delete(rid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        if alive(rid):
            raise HTTPException(409, detail={"code": "PAZAR", "message": "Rakam çıkarımı sürüyor; bitince silin."})
        recover(engine, tenant, call(P.get_report, engine, tenant, rid))
        out = call(P.delete_report, engine, tenant, rid)
        audit(engine, user, "delete", "pazar_report", rid, out["baslik"], {"rakam": out["rakam"]})
        return {"ok": True}

    def run_extract(engine, tenant: str, rid: str) -> None:
        st = P.settings()
        prog: dict[str, Any] = {"sayfa": 0, "toplam": 0, "rakam": 0, "atilan": 0, "metinsiz": 0, "baslangic": P.iso(P.now())}
        try:
            path, name, _ = P.report_file(engine, tenant, rid)
            data = Path(path).read_bytes()
            pages = src.pages_of(name, data)
            prog["toplam"] = len(pages)
            if src.ext_of(name) == "pdf" and any(not (p["metin"] or "").strip() for p in pages):
                # Taranmış sayfalar ortak belge okuma hattından (OCR); rakamlar yine OCR metninde birebir aranır.
                P.set_report_state(engine, tenant, rid, "cikariliyor", {**prog, "adim": "Taranmış sayfalar okunuyor"})
                pages, ocr = src.read_scanned(name, data, pages)
                prog.update(ocr)
            chat = chatter(4000)
            if chat is None:
                raise P.PazarError("Zeki AI bu kurulumda tanımlı değil; rakamları elle girebilirsiniz.")
            prog["temizlenen"] = P.clear_pending(engine, tenant, rid)
            P.set_report_state(engine, tenant, rid, "cikariliyor", prog)
            for p in pages:
                res = P.extract_page(p, chat, st["extractChars"])
                prog["sayfa"] += 1
                if res["empty"]:
                    prog["metinsiz"] += 1
                else:
                    prog["rakam"] += P.store_figures(engine, tenant, rid, p["sayfa"], res["figures"])
                    prog["atilan"] += res["dropped"]
                P.set_report_state(engine, tenant, rid, "cikariliyor", prog)
            prog["bitis"] = P.iso(P.now())
            P.set_report_state(engine, tenant, rid, "cikarildi", prog)
        except Exception as e:  # noqa: BLE001 — model kesintisi ya da okunamayan dosya: yarım kalan durum kaydedilir
            log.warning("pazar raporu %s çıkarımı yarım kaldı: %s", rid, e)
            prog["hata"] = str(e)[:300]
            P.set_report_state(engine, tenant, rid, "hata", prog)

    @app.post(B + "/reports/{rid}/extract")
    def pazar_report_extract(rid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        rep = call(P.get_report, engine, tenant, rid)
        if alive(rid):
            raise HTTPException(409, detail={"code": "PAZAR", "message": "Bu raporun çıkarımı zaten sürüyor."})
        P.set_report_state(engine, tenant, rid, "cikariliyor", {"sayfa": 0, "toplam": rep.get("sayfaSayisi") or 0})
        t = threading.Thread(target=run_extract, args=(engine, tenant, rid), name=f"pazar-cikarim-{rid[:8]}", daemon=True)
        extracting[rid] = t
        t.start()
        audit(engine, user, "run", "pazar_report", rid, rep["baslik"], {"islem": "rakam çıkarımı", "sayfa": rep.get("sayfaSayisi")})
        return call(P.get_report, engine, tenant, rid)

    @app.get(B + "/reports/{rid}/figures")
    def pazar_report_figures(rid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = call(P.figures, engine, tenant, rid)
        out["report"] = recover(engine, tenant, {**out["report"]})
        return out

    @app.post(B + "/reports/{rid}/figures", status_code=201)
    def pazar_report_figure_add(rid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(P.add_figure, engine, tenant, user, rid, body)
        audit(engine, user, "create", "pazar_figure", out["id"], out["gosterge"],
              {"deger": out["deger"], "birim": out["birim"], "sayfa": out["sayfa"], "rapor": rid})
        return out

    @app.post(B + "/figures/{fid}/decision")
    def pazar_figure_decision(fid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(P.decide_figure, engine, tenant, user, fid, body)
        action = {"onaylandi": "approve", "duzeltildi": "approve", "reddedildi": "reject"}.get(out["durum"], "update")
        audit(engine, user, action, "pazar_figure", fid, out["gosterge"],
              {"durum": out["durum"], "deger": out["deger"], "oneri": out["degerOneri"], "sayfa": out["sayfa"]})
        return out

    # ------------------------------------------------------------------ yönetim özeti

    @app.get(B + "/briefs")
    def pazar_briefs(request: Request, durum: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return P.list_briefs(engine, tenant, durum)

    @app.get(B + "/briefs/approved")
    def pazar_brief_approved(request: Request) -> dict[str, Any]:
        """Sözleşme (DYK kurul paketi): son onaylı özet; yoksa `brief: null`."""
        engine, tenant, _, _ = ctx(request)
        return {"brief": P.approved_brief(engine, tenant)}

    @app.get(B + "/briefs/by-period/{donem}")
    def pazar_brief_by_period(donem: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {"brief": call(P.brief_by_donem, engine, tenant, donem), "donem": donem}

    @app.get(B + "/briefs/sources")
    def pazar_brief_sources(request: Request) -> dict[str, Any]:
        """Taslağa verilecek kaynakların önizlemesi (modelsiz)."""
        engine, tenant, _, _ = ctx(request)
        return P.brief_sources(engine, tenant)

    @app.get(B + "/briefs/{bid}")
    def pazar_brief(bid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(P.get_brief, engine, tenant, bid)

    @app.post(B + "/briefs/draft")
    async def pazar_brief_draft(request: Request, donem: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        try:
            out = await run_in_threadpool(call, P.draft_brief, engine, tenant, user, donem or None, chatter(3000))
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001 — model kesintisi
            log.warning("pazar özeti yazılamadı: %s", e)
            raise HTTPException(503, detail={"code": "PAZAR_MODEL", "message": "Zeki AI şu an cevap vermiyor; biraz sonra yeniden deneyin."}) from e
        audit(engine, user, "create", "pazar_brief", out["id"], f"Pazar özeti taslağı {out['donemAd']}",
              {"kaynak": len(out["kaynaklar"]), "reddedilen": len(out["reddedilen"]), "disarida": out["disarida"]})
        return out

    @app.patch(B + "/briefs/{bid}")
    def pazar_brief_update(bid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(P.update_brief, engine, tenant, user, bid, body.get("taslak"))
        audit(engine, user, "update", "pazar_brief", bid, f"Pazar özeti {out['donemAd']}", {"sorun": len(out["sorunlar"])})
        return out

    @app.post(B + "/briefs/{bid}/submit")
    def pazar_brief_submit(bid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(P.submit_brief, engine, tenant, user, bid)
        audit(engine, user, "update", "pazar_brief", bid, f"Pazar özeti {out['donemAd']}", {"durum": "onay_bekliyor"})
        mail(f"Pazar özeti onay bekliyor — {out['donemAd']}", f"{user} {out['donemAd']} pazar özetini onaya gönderdi.")
        return out

    @app.post(B + "/briefs/{bid}/approve")
    def pazar_brief_approve(bid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_APPROVE, "Pazar özeti onayı")
        out = call(P.decide_brief, engine, tenant, user, bid, True, body.get("not"))
        audit(engine, user, "approve", "pazar_brief", bid, f"Pazar özeti {out['donemAd']}", {"dyk": out["dykGonderildiAt"]})
        mail(f"Pazar özeti onaylandı — {out['donemAd']}",
             f"{out['donemAd']} pazar özeti {user} tarafından onaylandı ve kurul paketine (DYK) eklendi.\n\n{out['taslak']}")
        return out

    @app.post(B + "/briefs/{bid}/reject")
    def pazar_brief_reject(bid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_APPROVE, "Pazar özeti onayı")
        out = call(P.decide_brief, engine, tenant, user, bid, False, body.get("not"))
        audit(engine, user, "reject", "pazar_brief", bid, f"Pazar özeti {out['donemAd']}", {"not": out["kararNotu"]})
        return out

    return {"sync": sync_job, "suggest": suggest_job, "extracting": extracting}
