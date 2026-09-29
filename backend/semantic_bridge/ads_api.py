"""M21 Reklam uçları: /api/v1/ads/*.

Sayfa kapısı `access.RULES` (`sayfa:reklam`); içe aktarma, eşleme, kampanya bağı, bütçe planı, brief ve yenileme
`ozellik:reklam.duzenle` (`FEATURE_RULES`); rapor dışa aktarımı `ozellik:veri.disa-aktar`. Para kararı olan önerinin
(durdur, kaydır) onayı/reddi açıkça verilen `ozellik:reklam.onay` ile ucun içinde denetlenir; «uygulandı» işareti ve
uyarı türlerinin kapatılması düzenleme yetkisiyle.

Zamanlayıcı (`timas-ads.timer`, her gün 07:30) yalnız `POST /api/v1/ads/run-due`'yu çağırır: Logo önbelleğini tazeler
(e-ticaret cirosu, bağlı kitapların satışı ve stoğu), bağsız kampanyalara kitap önerir, öneri kurallarını koşar, yeni
önerileri e-postayla bildirir. Reklam platformlarına hiçbir şey gönderilmez.

app.py'de iki satır:
    from semantic_bridge import ads_api
    app.state.ads = ads_api.register(app, rt, _require_caller, _can)
"""
from __future__ import annotations

import base64
import binascii
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import ads as A
from semantic_bridge import hizli_kaynak as HK
from semantic_bridge import ads_kaynak as K
from semantic_bridge import pazarlama_kaynak as PK
from semantic_bridge import provenance as PV
from semantic_bridge import ads_export as X
from semantic_bridge import ads_sources as S
from semantic_layer.runtime.llm_queue import BATCH, NORMAL

log = logging.getLogger("semantic.ads.api")

R = "/api/v1/ads"
PAGE = "sayfa:reklam"
F_EDIT = "ozellik:reklam.duzenle"
F_APPROVE = "ozellik:reklam.onay"
F_EXPORT = "ozellik:veri.disa-aktar"
BOOK_SEARCH_SHOWN = 30

BRIEF_SYSTEM = (
    "Sen TİMAŞ Yayınları'nın dijital pazarlama ekibine reklam brief'i taslağı yazan Zeki AI'sın. Kurallar: Türkçe yaz. Yalnız "
    "sana verilen bilgileri kullan, kitap hakkında bilgi uydurma. Verilen olgu listesinde olmayan hiçbir sayı yazma (satış, "
    "takipçi, yüzde, bütçe, tarih dahil). Alıntıyı yalnız verilen metinlerde birebir geçen cümlelerden, « » içinde yaz. «En çok "
    "satan», «bir numara», «rekor», «eşsiz» gibi kanıtsız üstünlük iddiası ve kanıtlanamayan indirim iddiası yazma. Müşteri "
    "listesi (e-posta, telefon) yükleyerek benzer kitle kurmayı önerme. Hiçbir teknoloji, model ya da yazılım adı yazma.")
BRIEF_PROMPT = (
    "Bu kitap için reklam kampanyası brief'i taslağı yaz. Bölümler: 1) Hedef kitle (yaş aralığı, ilgi alanları, okuma "
    "alışkanlığı), 2) Ana mesaj ve konumlama, 3) Önerilen kanallar ve nedeni (arama reklamı, Meta, TikTok, pazaryeri), "
    "4) Üç reklam metni önerisi (başlık + kısa metin), 5) Görsel yön, 6) Kaçınılacaklar. Başlık ve açıklama cümlesi ekleme.")


def _b64(body: dict[str, Any], limit_mb: float) -> tuple[str, bytes]:
    name = str(body.get("dosyaAdi") or "").strip()[:300] or "dosya"
    raw = body.get("icerik")
    if not isinstance(raw, str) or not raw:
        raise A.AdsError("Dosya içeriği gelmedi.")
    if len(raw) * 3 / 4 > limit_mb * 1024 * 1024:
        raise A.AdsError(f"Dosya {limit_mb:g} MB'tan büyük (Yönetim → ayarlar: ADS_IMPORT_MAX_MB).", 413)
    try:
        return name, base64.b64decode(raw.split(",", 1)[-1] if raw.startswith("data:") else raw, validate=False)
    except (binascii.Error, ValueError):
        raise A.AdsError("Dosya içeriği okunamadı.") from None


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None], can: Callable[[str, str], bool]):
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod
    from semantic_bridge.budget_api import _send_mail
    from semantic_bridge.marketing import guard as G
    from semantic_bridge.marketing.sources import FIELD_LABELS as S_LABEL
    from semantic_bridge.marketing.sources import Crm as MktCrm
    from semantic_bridge.marketing.sources import SourceError as MktSourceError

    schema = lambda: admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo"  # noqa: E731
    crm_path = lambda: os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")  # noqa: E731
    crm = S.Crm(schema, S.crm_runner(crm_path))
    mkt = MktCrm(schema)
    logo = S.Logo(lambda: rt().settings.connection_file)
    pool = ThreadPoolExecutor(max_workers=max(1, int(os.environ.get("ADS_JOB_WORKERS", "2"))), thread_name_prefix="ads")
    state = {"stale": False}
    lock = threading.Lock()
    refresh_lock = threading.Lock()

    def st() -> dict[str, Any]:
        return A.settings(admin_mod.conf)

    def db() -> tuple[Any, str]:
        r = rt()
        A.ensure(r.store.engine)
        admin_mod.ensure(r.store.engine)
        with lock:
            if not state["stale"]:
                state["stale"] = True
                n = A.fail_stale_briefs(r.store.engine)
                if n:
                    log.info("ads: yarıda kalan %d brief kapatıldı", n)
        return r.store.engine, r.settings.tenant_id

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        require_caller(request)
        try:
            user, display = board_mod.session_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        engine, tenant = db()
        return engine, tenant, user, display

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except A.AdsError as e:
            raise HTTPException(status_code=e.status, detail={"code": "ADS", "message": str(e)}) from e
        except (S.SourceError, MktSourceError) as e:
            raise HTTPException(status_code=503, detail={"code": "ADS_SOURCE", "message": str(e)}) from e

    def need(user: str, key: str, what: str) -> None:
        if not can(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def audit(engine, user: str, action: str, kind: str, oid: Any, title: Any, detail: Any = None) -> None:
        admin_mod.audit(engine, user, action, kind, oid, title, detail)

    def link(path: str = "") -> str:
        base = (admin_mod.conf("ALERT_LINK") or "").split("/uyarilar")[0]
        return f"{base}/reklam{('/' + path) if path else ''}" if base else ""

    def period(frm: str, to: str) -> tuple[date, date]:
        t = call(A.day_of, to, "Bitiş") if to else A.today()
        f = call(A.day_of, frm, "Başlangıç") if frm else t - timedelta(days=29)
        if t < f:
            raise HTTPException(status_code=400, detail={"code": "ADS", "message": "Bitiş başlangıçtan önce olamaz."})
        return f, t

    def data_end(engine, tenant) -> Optional[date]:
        v = A.meta_get(engine, tenant, "logo").get("veriSonu")
        return date.fromisoformat(v) if v else None

    def isit() -> None:
        """Köprü açılışında CRM kitap listesi arkada okunur: reklam özetini ilk açan CRM'i beklemesin."""
        if HK.sqlite_mi(rt().store.engine):
            return
        crm.books(st()["offSaleStatus"])

    HK.acilista("reklam.kitaplar", isit)

    def crm_map(s: dict[str, Any], warnings: list[str]) -> dict[str, dict[str, Any]]:
        try:
            return {b["stokKodu"]: b for b in crm.books(s["offSaleStatus"])}
        except S.SourceError as e:
            warnings.append(f"CRM okunamadı; yayın durumu uyarısı gösterilmiyor ({e}).")
            return {}

    # ------------------------------------------------------------------ Logo önbelleği

    def refresh(engine, tenant: str, s: dict[str, Any], codes: Optional[list[str]] = None) -> dict[str, Any]:
        """E-ticaret günlük cirosu (pencere: veri sonundan `ADS_LOOKBACK_DAYS` geri, ilk reklam günü daha eskiyse ondan),
        bağlı kitapların günlük satışı, stok bakiyesi ve satış hızı. `codes` verilirse yalnız o kitaplar."""
        ran: list[dict[str, Any]] = []
        run, firms, end = logo.context(lambda r: PK.recording(r, "logo", ran))
        if not firms or end is None:
            raise S.SourceError("Logo'da satış dönemi ya da satış verisi yok.")
        frm = end - timedelta(days=s["lookbackDays"])
        first = A.first_ad_day(engine, tenant)
        if first and first < frm:
            frm = first
        out: dict[str, Any] = {"veriSonu": end.isoformat(), "pencere": {"bas": frm.isoformat(), "bit": end.isoformat()},
                               "kanallar": s["ecomChannels"]}
        if codes is None:
            rows = logo.ecom_daily(run, firms, frm, end, s["ecomChannels"])
            out["eticaretGun"] = A.write_ecom(engine, tenant, frm, end, rows)
        want = sorted(set(codes if codes is not None else A.linked_codes(engine, tenant)))
        if want:
            out["kitapSatir"] = A.write_book_sales(engine, tenant, frm, end, want,
                                                   logo.book_daily(run, firms, frm, end, want, s["ecomChannels"]))
            vel = A.velocity(engine, tenant, want, end, s["velocityDays"])
            stock = [{**r, "gunluk": vel.get(r["stok_kodu"], 0.0)} for r in logo.stock(run, firms, want)]
            out["stok"] = A.write_stock(engine, tenant, stock, end.isoformat(), None if codes is None else want)
        out["kitap"] = len(want)
        if codes is None:                                   # kısmi yenileme (tek kitap) genel önbellek kaydını değiştirmez
            A.meta_set(engine, tenant, "logo", {**out, "zaman": A.iso(A.now())})
            # Çalışan Logo sorgularının metni (sorgu bilgisi için; sonuç satırı yok). Kısmi yenileme eskileri korur.
            keep = [] if codes is None else [x for x in (A.meta_get(engine, tenant, K.LOGO_SQL_KEY).get("runs") or [])
                                             if not any(x.get("sql") == y["sql"] for y in ran)]
            A.meta_set(engine, tenant, K.LOGO_SQL_KEY, {"runs": keep + ran})
        return out

    def refresh_job(tenant: str, user: str, codes: Optional[list[str]] = None) -> None:
        engine = rt().store.engine
        if not refresh_lock.acquire(blocking=False):
            return
        try:
            A.meta_set(engine, tenant, "refresh", {"durum": "calisiyor", "kim": user, "basladi": A.iso(A.now())})
            out = refresh(engine, tenant, st(), codes)
            A.meta_set(engine, tenant, "refresh", {"durum": "bitti", "kim": user, "bitti": A.iso(A.now()), "sonuc": out})
        except Exception as e:  # noqa: BLE001 — iş hatası ekranda görünür
            log.warning("ads refresh failed: %s", e)
            A.meta_set(engine, tenant, "refresh", {"durum": "hata", "kim": user, "bitti": A.iso(A.now()), "hata": str(e)[:400]})
        finally:
            refresh_lock.release()

    # ------------------------------------------------------------------ eşleştirme

    def link_job(tenant: str, ids: Optional[list[str]], priority: int) -> dict[str, Any]:
        engine = rt().store.engine
        s = st()
        out = {"denenen": 0, "bagli": 0, "oneri": 0, "hata": None}
        try:
            books = crm.books(s["offSaleStatus"])
        except S.SourceError as e:
            out["hata"] = str(e)
            return out
        idx = A.book_index(books)
        llm = rt().llm_for("reklam", priority)
        for c in A.unlinked_campaigns(engine, tenant, ids):
            out["denenen"] += 1
            try:
                res = A.match_campaign(c, books, idx, llm, s)
            except Exception as e:  # noqa: BLE001 — model erişilemedi: kayıt yazılmaz, sonraki turda yeniden denenir
                log.warning("ads: kampanya eşleştirme modeli yanıt vermedi: %s", e)
                out["hata"] = "Zeki AI'a şu an ulaşılamıyor; bağsız kampanyalar sonraki turda yeniden denenecek."
                llm = None
                continue
            A.save_link_suggestion(engine, c["id"], res)
            if res.get("book"):
                out["bagli" if res.get("source") == "kod" else "oneri"] += 1
        return out

    def after_import(tenant: str, user: str) -> None:
        try:
            link_job(tenant, None, NORMAL)
            engine = rt().store.engine
            codes = A.linked_codes(engine, tenant)
            have = set(A.stock_of(engine, tenant))
            missing = [c for c in codes if c not in have]
            if missing and data_end(engine, tenant):
                refresh_job(tenant, user, missing)
            s = st()
            A.store_suggestions(engine, tenant, A.evaluate(engine, tenant, s, A.today(), crm_books=crm_map(s, [])), s)
        except Exception as e:  # noqa: BLE001
            log.warning("ads: yükleme sonrası iş bitmedi: %s", e)

    # ------------------------------------------------------------------ genel

    @app.get(R + "/meta")
    def ads_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        s = st()
        return {
            "platforms": A.PLATFORMS, "kinds": A.KINDS, "statuses": A.STATUSES, "linkStatuses": A.LINK_STATUSES,
            "linkSources": A.LINK_SOURCES, "fields": A.FIELDS, "required": list(A.REQUIRED), "briefStatuses": A.BRIEF_STATUSES,
            "approvalKinds": list(A.APPROVAL_KINDS),
            "settings": {"ecomChannels": s["ecomChannels"], "stockDays": s["stockDays"], "activeDays": s["activeDays"],
                         "noDataDays": s["noDataDays"], "perfWindowDays": s["perfWindowDays"],
                         "rules": {"stok": s["stockDays"] is not None, "satis-disi": bool(s["offSaleStatus"]), "veri-yok": True,
                                   "butce": True, "durdur": s["stopMinSpend"] is not None, "kaydir": s["shiftMinSpend"] is not None},
                         "m15Channels": s["m15Channels"], "maxUploadMb": s["maxUploadMb"]},
            "logo": A.meta_get(engine, tenant, "logo") or None, "refresh": A.meta_get(engine, tenant, "refresh") or None,
            "lastRun": A.meta_get(engine, tenant, "run-due") or None,
            "modelReady": getattr(rt(), "llm", None) is not None,
            "accounts": A.list_accounts(engine, tenant),
            "me": {"username": user, "display": display, "canEdit": can(user, F_EDIT), "canApprove": can(user, F_APPROVE),
                   "canExport": can(user, F_EXPORT)},
        }

    @app.get(R + "/overview")
    async def ads_overview(request: Request, frm: str = "", to: str = "", kanal: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        f, t = period(frm, to)
        if kanal and kanal not in A.PLATFORMS:
            raise HTTPException(status_code=400, detail={"code": "ADS", "message": "Kanal tanınmıyor."})
        s = st()
        warnings: list[str] = []
        books = await run_in_threadpool(crm_map, s, warnings)
        codes = [c["stokKodu"] for c in A.campaign_rows(engine, tenant) if c["stokKodu"] and c["bag"] == "onayli"]
        m15 = A.m15_by_book(engine, tenant, codes, set(s["m15Channels"].values()))
        out = await run_in_threadpool(call, A.overview, engine, tenant, f, t, kanal, data_end(engine, tenant), m15, books, s)
        out["oneriler"] = A.list_suggestions(engine, tenant, "acik")
        out["uyarilar"] = warnings
        if not A.meta_get(engine, tenant, "logo"):
            out["uyarilar"].append("Logo satış önbelleği henüz dolmadı: «Satış verisini yenile» ile ya da gece işiyle dolar.")
        de = data_end(engine, tenant)
        return PV.bagla(out, lambda: K.for_overview(engine, tenant, out, f, t, kanal, [b["stokKodu"] for b in out.get("kitaplar") or []],
                                                     de, PK.logo_db(rt), codes, set(s["m15Channels"].values())))

    @app.get(R + "/status")
    def ads_status(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = {"refresh": A.meta_get(engine, tenant, "refresh") or None, "logo": A.meta_get(engine, tenant, "logo") or None}
        return PV.bagla(out, lambda: K.for_status(engine, tenant, PK.logo_db(rt)))

    @app.post(R + "/refresh", status_code=202)
    def ads_refresh(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        if refresh_lock.locked():
            return {"basladi": False, "not": "Yenileme zaten sürüyor."}
        pool.submit(refresh_job, tenant, user, None)
        audit(engine, user, "run", "ads_refresh", None, "Reklam: satış verisi yenileme", None)
        return {"basladi": True}

    # ------------------------------------------------------------------ hesaplar ve içe aktarma

    @app.get(R + "/accounts")
    def ads_accounts(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return PV.bagla({"items": A.list_accounts(engine, tenant)}, lambda: K.for_accounts(engine, tenant))

    @app.post(R + "/accounts", status_code=201)
    def ads_account_new(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        acc = call(A.create_account, engine, tenant, user, body)
        audit(engine, user, "create", "ads_account", acc["id"], acc["ad"], {"platform": acc["platform"], "paraBirimi": acc["paraBirimi"]})
        return acc

    @app.patch(R + "/accounts/{account_id}")
    def ads_account_update(account_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        acc = call(A.update_account, engine, tenant, account_id, body)
        audit(engine, user, "update", "ads_account", acc["id"], acc["ad"], {k: body[k] for k in ("ad", "paraBirimi", "eslem") if k in body})
        return acc

    @app.post(R + "/imports/preview")
    async def ads_import_preview(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        s = st()
        name, data = call(_b64, body, s["maxUploadMb"])
        saved = None
        if body.get("hesapId"):
            saved = call(A.get_account, engine, tenant, str(body["hesapId"])).get("eslem")
        override = body.get("eslem") if isinstance(body.get("eslem"), dict) else None
        out = await run_in_threadpool(call, S.preview, name, data, saved, s["dayFirst"], override,
                                      int(body.get("baslikSatiri") or 0) or None)
        out["dosyaAdi"] = name
        out["zeki"] = {}
        if out["eksik"] and not override:
            llm = rt().llm_for("reklam", NORMAL)
            table = await run_in_threadpool(call, S.read_table, name, data)
            h = out["baslikSatiri"] - 1
            try:
                out["zeki"] = await run_in_threadpool(S.model_mapping, llm, out["kolonlar"], table[h + 1:h + 4], out["eksik"], s)
            except Exception as e:  # noqa: BLE001 — model yanıt vermezse eşleme elle yapılır
                log.warning("ads: kolon eşleme modeli yanıt vermedi: %s", e)
                out["zekiHata"] = "Zeki AI'a şu an ulaşılamıyor; eksik kolonları elle seçin."
            for f, v in out["zeki"].items():
                out["eslem"][f] = v["kolon"]
            out["eksik"] = [f for f in A.REQUIRED if f not in out["eslem"]]
            if not out["eksik"]:
                out["deneme"] = await run_in_threadpool(call, S.trial, table, h, out["eslem"], s["dayFirst"])
        return out

    @app.post(R + "/imports", status_code=201)
    async def ads_import(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        s = st()
        name, data = call(_b64, body, s["maxUploadMb"])
        acc = call(A.get_account, engine, tenant, str(body.get("hesapId") or ""))
        mapping = call(A.clean_mapping, body.get("eslem"))
        table = await run_in_threadpool(call, S.read_table, name, data)
        h = int(body.get("baslikSatiri") or 0) - 1
        if h < 0 or h >= len(table):
            h = S.find_header(table)
        res = await run_in_threadpool(call, S.apply_mapping, table, h, mapping, s["dayFirst"])
        if res["hataSayisi"]:
            raise HTTPException(status_code=400, detail={
                "code": "ADS_ROWS", "message": f"{res['hataSayisi']} satır okunamadı; dosya yüklenmedi. Toplamlar eksik kalmasın diye "
                                               "hatalı satır atlanmaz.", "hatalar": res["hatalar"], "hataSayisi": res["hataSayisi"]})
        warnings = []
        if res["ozetSatiri"]:
            warnings.append(f"{res['ozetSatiri']} özet/toplam satırı (kampanya adı boş ya da «Toplam») atlandı.")
        other = sorted({r["currency"] for r in res["rows"] if r["currency"] and r["currency"] != acc["paraBirimi"]})
        if other:
            warnings.append("Hesabın para biriminden farklı satırlar var: " + ", ".join(other) + " (TL toplamlarına katılmaz).")
        imp = await run_in_threadpool(call, A.commit_import, engine, tenant, user, acc, name, S.sha(data), res["rows"], mapping,
                                      warnings, res["okunan"])
        audit(engine, user, "upload", "ads_import", imp["id"], name, {"hesap": acc["ad"], "satir": imp["satir"], "kampanyaGun": imp["kampanyaGun"],
                                                                      "toplam": imp["paraBirimiToplam"], "bas": imp["bas"], "bit": imp["bit"]})
        pool.submit(after_import, tenant, user)
        return imp

    @app.get(R + "/imports")
    def ads_imports(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        items = A.list_imports(engine, tenant)
        return PV.bagla({"items": items, "total": len(items)}, lambda: K.for_imports(engine, tenant))

    @app.get(R + "/imports/{iid}")
    def ads_import_get(iid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return PV.bagla(call(A.import_row, engine, tenant, iid), lambda: K.for_import(engine, tenant, iid))

    @app.delete(R + "/imports/{iid}")
    def ads_import_delete(iid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(A.delete_import, engine, tenant, iid)
        audit(engine, user, "delete", "ads_import", out["id"], out["dosya"], {"silinenKampanyaGun": out["silinenKampanyaGun"]})
        return out

    # ------------------------------------------------------------------ kampanyalar ve kitap bağı

    @app.get(R + "/campaigns")
    def ads_campaigns(request: Request, frm: str = "", to: str = "", kanal: str = "", bag: str = "", q: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        f, t = period(frm, to)
        win: dict[str, list[Any]] = {}
        for r in A.daily_rows(engine, tenant, f, t, kanal):
            if (r.currency or A.MAIN_CURRENCY) == A.MAIN_CURRENCY:
                win.setdefault(r.campaign_id, []).append(r)
        items = []
        needle = A.fold(q)
        rows = A.campaign_rows(engine, tenant)
        for c in rows:
            if kanal and c["platform"] != kanal:
                continue
            if bag and c["bag"] != bag:
                continue
            if needle and needle not in A.fold(f"{c['ad']} {c.get('kitapAdi') or ''} {c.get('stokKodu') or ''}"):
                continue
            items.append({**c, **A.metrics(A._sum_rows(win.get(c["id"], [])))})
        items.sort(key=lambda x: (-(x["harcama"] or 0), x["ad"]))
        counts = {k: sum(1 for c in rows if c["bag"] == k) for k in A.LINK_STATUSES}
        return PV.bagla({"items": items, "total": len(items), "bagSayilari": counts, "donem": {"bas": f.isoformat(), "bit": t.isoformat()}},
                        lambda: K.for_campaigns(engine, tenant, f, t, kanal))

    @app.patch(R + "/campaigns/{cid}")
    def ads_campaign_update(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        s = st()

        def book_of(code: str) -> Optional[dict[str, Any]]:
            return next((b for b in crm.books(s["offSaleStatus"]) if b["stokKodu"] == code), None)

        before = call(A.get_campaign, engine, tenant, cid)
        out = call(A.set_link, engine, tenant, user, cid, body, book_of)
        audit(engine, user, "update", "ads_campaign", out["id"], out["ad"],
              {"once": {"stok": before["stokKodu"], "bag": before["bag"]}, "sonra": {"stok": out["stokKodu"], "bag": out["bag"]},
               **{k: body[k] for k in ("seri", "m15PlanId") if k in body}})
        if out["stokKodu"] and out["bag"] == "onayli" and out["stokKodu"] != before["stokKodu"] and data_end(engine, tenant):
            pool.submit(refresh_job, tenant, user, [out["stokKodu"]])
        return out

    @app.post(R + "/campaigns/{cid}/match")
    async def ads_campaign_match(cid: str, request: Request) -> dict[str, Any]:
        """Tek kampanya için Zeki AI eşleştirmesini yeniden koşar (elle ya da onaylı bağa dokunmaz)."""
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        cur = call(A.get_campaign, engine, tenant, cid)
        if cur["bag"] == "onayli":
            raise HTTPException(status_code=409, detail={"code": "ADS", "message": "Kampanya zaten bir kitaba bağlı; önce bağı kaldırın."})
        if cur["bag"] == "oneri":
            await run_in_threadpool(A.save_link_suggestion, engine, cid, {"book": None, "adaylar": []})
        res = await run_in_threadpool(link_job, tenant, [cid], NORMAL)
        out = call(A.get_campaign, engine, tenant, cid)
        audit(engine, user, "run", "ads_campaign", cid, cur["ad"], {"eslestirme": res, "sonuc": out["bag"]})
        return {**out, "is": res}

    @app.get(R + "/books")
    async def ads_books(request: Request, q: str = "") -> dict[str, Any]:
        """Kitap arama (elle bağ için): ad, stok kodu, barkod, yazar. En iyi eşleşen ilk 30 gösterilir, toplam sayı yazılır."""
        await run_in_threadpool(ctx, request)
        needle = A.fold(q)
        if len(needle) < 2:
            return {"items": [], "total": 0, "shown": 0}
        books = await run_in_threadpool(call, crm.books, st()["offSaleStatus"])
        hits = []
        for b in books:
            hay = A.fold(f"{b.get('ad') or ''} {b['stokKodu']} {b.get('ean') or ''} {b.get('yazar') or ''}")
            pos = hay.find(needle)
            if pos >= 0:
                hits.append((0 if b["stokKodu"].lower() == needle or (b.get("ean") or "") == needle else 1, pos, b.get("ad") or "", b))
        hits.sort(key=lambda x: (x[0], x[1], x[2]))
        return PV.bagla({"items": [h[3] for h in hits[:BOOK_SEARCH_SHOWN]], "total": len(hits), "shown": min(len(hits), BOOK_SEARCH_SHOWN)},
                        lambda: K.for_books(q))

    # ------------------------------------------------------------------ bütçe

    @app.get(R + "/budget")
    async def ads_budget(request: Request, year: int = 0) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        y = year or A.today().year
        s = st()
        warnings: list[str] = []
        crm_rows: list[dict[str, Any]] = []
        try:
            crm_rows = [r for r in await run_in_threadpool(crm.budget_records, date(y, 1, 1), date(y, 12, 31)) if r["reklam"]]
        except S.SourceError as e:
            warnings.append(f"CRM okunamadı; CRM pazarlama bütçesi sütunu boş ({e}).")
        out = await run_in_threadpool(A.budget, engine, tenant, y, s, crm_rows)
        out["uyarilar"] = warnings
        return PV.bagla(out, lambda: K.for_budget(engine, tenant, y, set(s["m15Channels"].values()), not warnings))

    @app.put(R + "/budget")
    def ads_budget_put(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        n = call(A.put_budget, engine, tenant, user, body.get("items"))
        audit(engine, user, "update", "ads_budget", None, "Reklam bütçe planı", {"satir": n, "items": body.get("items")})
        y = int(str((body.get("items") or [{}])[0].get("ay") or A.today().year)[:4])
        return {"degisen": n, **A.budget(engine, tenant, y, st(), None)}

    # ------------------------------------------------------------------ CRM kayıtları (okuma)

    @app.get(R + "/crm")
    async def ads_crm(request: Request, frm: str = "", to: str = "", yenile: bool = False) -> dict[str, Any]:
        await run_in_threadpool(ctx, request)
        f, t = period(frm, to)
        plans = await run_in_threadpool(call, crm.ad_plans, yenile)
        recs = await run_in_threadpool(call, crm.budget_records, f, t, yenile)
        overlapping = [p for p in plans if (p["bas"] or "9999") <= t.isoformat() and (p["bit"] or p["bas"] or "0000") >= f.isoformat()]
        out = {"donem": {"bas": f.isoformat(), "bit": t.isoformat(), "crmBas": S._utc(f), "crmBit": S._utc(t + timedelta(days=1))},
               "reklamPlanlari": {"toplam": len(plans), "donemde": overlapping, "onaysiz": sum(1 for p in plans if not p["onay"]),
                                  "hepsi": plans},
               "butceKayitlari": {"items": recs, "toplam": round(sum(r["tutar"] for r in recs), 2),
                                  "reklamToplam": round(sum(r["tutar"] for r in recs if r["reklam"]), 2)}}
        return PV.bagla(out, lambda: K.for_crm(f, t))

    # ------------------------------------------------------------------ öneriler

    @app.get(R + "/suggestions")
    def ads_suggestions(request: Request, durum: str = "acik") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        items = A.list_suggestions(engine, tenant, durum)
        return PV.bagla({"items": items, "total": len(items)}, lambda: K.for_suggestions(engine, tenant, durum))

    @app.post(R + "/suggestions/{sid}/decide")
    def ads_decide(sid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        karar = str(body.get("karar") or "")
        cur = call(A.get_suggestion, engine, tenant, sid)
        if cur["onayGerekir"] and karar in ("onayla", "reddet"):
            need(user, F_APPROVE, "Reklam önerisi onayı")
        else:
            need(user, F_EDIT, "Reklam düzenleme")
        out = call(A.decide, engine, tenant, user, sid, karar, body.get("not"))
        audit(engine, user, {"onayla": "approve", "reddet": "reject"}.get(karar, "update"), "ads_suggestion", out["id"], out["turAdi"],
              {"karar": karar, "not": body.get("not"), "kampanya": out.get("kampanya"), "veri": out.get("veri")})
        return out

    # ------------------------------------------------------------------ brief

    def brief_job(tenant: str, bid: str, stok: str, note: Optional[str]) -> None:
        engine = rt().store.engine
        try:
            book = mkt.book(stok)
            if not book:
                A.finish_brief(engine, bid, None, None, "CRM'de kitap kartı bulunamadı.")
                return
            llm = rt().llm_for("reklam", NORMAL)
            if llm is None:
                A.finish_brief(engine, bid, None, None, "Zeki AI modeli bu kurulumda bağlı değil; brief elle yazılabilir.")
                return
            s = st()
            facts: list[str] = []
            if book.get("fiyat"):
                facts.append(f"Liste fiyatı: {book['fiyat']:.2f} TL".replace(".", ","))
            if book.get("sayfa"):
                facts.append(f"Sayfa sayısı: {int(book['sayfa'])}")
            yas = [x for x in (book.get("yas") or []) if x not in (None, "")]
            if yas:
                facts.append("Hedef yaş: " + "–".join(str(x) for x in yas))
            end = data_end(engine, tenant)
            if end:
                sales = A.book_sales(engine, tenant, [stok], end - timedelta(days=364), end).get(stok)
                if sales:
                    facts.append(f"Son 12 ay e-ticaret net satış adedi: {sales['eticaretAdet']:.0f}")
                    facts.append(f"Son 12 ay bütün kanallar net satış adedi: {sales['toplamAdet']:.0f}")
            texts = [v for v in (book.get("metinler") or {}).values() if v]
            info = "\n".join(x for x in (
                f"Kitap: {book.get('ad')}", f"Yazar: {book.get('yazar') or '—'}", f"Yayınevi: {book.get('yayinevi') or '—'}",
                f"Kitaplık: {book.get('kitaplik') or '—'}", f"Hedef kitle (CRM): {book.get('hedefKitle') or '—'}",
                f"Türler: {book.get('turler') or '—'}") if x)
            src = "\n\n".join(f"{S_LABEL.get(k, k)}:\n{v[:3000]}" for k, v in (book.get("metinler") or {}).items() if v)
            prompt = (f"{BRIEF_PROMPT}\n\nİsteyenin notu: {note or '—'}\n\nOlgu listesi (yazabileceğin sayılar yalnız bunlar):\n"
                      + ("\n".join(facts) or "—") + f"\n\nKitap bilgisi:\n{info}\n\nCRM'deki metinler:\n{src[:12000] or '—'}")
            raw = str(llm.chat([{"role": "system", "content": BRIEF_SYSTEM}, {"role": "user", "content": prompt}], max_tokens=1800) or "").strip()
            res = G.check(raw, [*texts, info, note or ""], facts, s["claims"])
            if not res["metin"]:
                A.finish_brief(engine, bid, None, {"dusen": res["dusen"], "sayac": res["sayac"]}, "Denetimden geçen cümle kalmadı; yeniden isteyin ya da elle yazın.")
                return
            A.finish_brief(engine, bid, res["metin"], {"dusen": res["dusen"], "sayac": res["sayac"], "dusenSayisi": res["dusenSayisi"]})
        except Exception as e:  # noqa: BLE001
            log.warning("ads brief failed: %s", e)
            A.finish_brief(engine, bid, None, None, "Zeki AI'a ya da CRM'e şu an ulaşılamıyor; birazdan yeniden deneyin.")

    @app.get(R + "/briefs")
    def ads_briefs(request: Request, stok: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        items = A.list_briefs(engine, tenant, stok)
        return PV.bagla({"items": items, "total": len(items)}, lambda: K.for_briefs(engine, tenant, stok=stok))

    @app.post(R + "/briefs", status_code=201)
    async def ads_brief_new(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        stok = str(body.get("stokKodu") or "").strip()
        if not stok:
            raise HTTPException(status_code=400, detail={"code": "ADS", "message": "Kitap seçin."})
        books = await run_in_threadpool(call, crm.books, st()["offSaleStatus"])
        book = next((b for b in books if b["stokKodu"] == stok), None)
        if not book:
            raise HTTPException(status_code=404, detail={"code": "ADS", "message": "Bu stok kodunda CRM'de etkin kitap kartı yok."})
        b = call(A.create_brief, engine, tenant, user, book, body.get("not"))
        audit(engine, user, "create", "ads_brief", b["id"], b["kitapAdi"], {"stok": stok, "istek": b["istek"]})
        pool.submit(brief_job, tenant, b["id"], stok, b["istek"])
        return b

    @app.get(R + "/briefs/{bid}")
    def ads_brief_get(bid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return PV.bagla(call(A.get_brief, engine, tenant, bid), lambda: K.for_briefs(engine, tenant, bid=bid))

    @app.patch(R + "/briefs/{bid}")
    def ads_brief_update(bid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(A.update_brief, engine, tenant, user, bid, body)
        audit(engine, user, "approve" if body.get("onayla") else "update", "ads_brief", out["id"], out["kitapAdi"], {"durum": out["durum"]})
        return out

    @app.delete(R + "/briefs/{bid}")
    def ads_brief_delete(bid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(A.delete_brief, engine, tenant, bid)
        audit(engine, user, "delete", "ads_brief", out["id"], out["kitapAdi"], None)
        return {"ok": True}

    # ------------------------------------------------------------------ rapor

    def report_data(engine, tenant: str, f: date, t: date, kanal: str) -> tuple[dict[str, Any], list[dict[str, Any]], Optional[str]]:
        s = st()
        books = crm_map(s, [])
        codes = [c["stokKodu"] for c in A.campaign_rows(engine, tenant) if c["stokKodu"] and c["bag"] == "onayli"]
        ov = call(A.overview, engine, tenant, f, t, kanal, data_end(engine, tenant),
                  A.m15_by_book(engine, tenant, codes, set(s["m15Channels"].values())), books, s)
        comment = A.meta_get(engine, tenant, f"yorum:{f.isoformat()}:{t.isoformat()}:{kanal}").get("metin")
        return ov, A.list_suggestions(engine, tenant, ""), comment

    @app.get(R + "/report/export.pdf")
    async def ads_report_pdf(request: Request, frm: str = "", to: str = "", kanal: str = "") -> Response:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        f, t = period(frm, to)
        ov, sugg, comment = await run_in_threadpool(report_data, engine, tenant, f, t, kanal)
        body = await run_in_threadpool(call, X.report_pdf, ov, sugg, comment, user)
        audit(engine, user, "run", "ads_report", None, "Reklam raporu (PDF)", {"bas": f.isoformat(), "bit": t.isoformat(), "kanal": kanal or None})
        return Response(body, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="reklam-raporu-{f.isoformat()}-{t.isoformat()}.pdf"'})

    @app.get(R + "/report/export.xlsx")
    async def ads_report_xlsx(request: Request, frm: str = "", to: str = "", kanal: str = "") -> Response:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        f, t = period(frm, to)
        ov, sugg, comment = await run_in_threadpool(report_data, engine, tenant, f, t, kanal)
        body = await run_in_threadpool(X.report_xlsx, ov, sugg, comment)
        audit(engine, user, "run", "ads_report", None, "Reklam raporu (Excel)", {"bas": f.isoformat(), "bit": t.isoformat(), "kanal": kanal or None})
        return Response(body, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="reklam-raporu-{f.isoformat()}-{t.isoformat()}.xlsx"'})

    @app.post(R + "/report/summary")
    async def ads_report_summary(body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Zeki AI'ın beş cümlelik yorumu: hesaplanmış rakamları yorumlar, yeni rakam yazmaz (denetimden geçmeyen cümle düşer).
        Aynı dönem için saklanır; PDF raporuna girer."""
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        f, t = period(str(body.get("frm") or ""), str(body.get("to") or ""))
        kanal = str(body.get("kanal") or "")
        llm = rt().llm_for("reklam", NORMAL)
        if llm is None:
            raise HTTPException(status_code=503, detail={"code": "ADS", "message": "Zeki AI modeli bu kurulumda bağlı değil."})
        ov, _, _ = await run_in_threadpool(report_data, engine, tenant, f, t, kanal)
        g = ov["gosterge"]
        facts = [f"Toplam harcama: {X._money(g['harcama'])}", f"Tıklama: {X._num(g.get('tiklama'))}", f"TBM: {X._num(g.get('tbm'), 2)} TL",
                 f"Platform ROAS: {X._ratio(g.get('platformRoas'))}", f"E-ticaret net ciro: {X._money(g.get('eticaretCiro'))}",
                 f"Pazarlama verimi: {X._ratio(g.get('verim'))}", f"Kitaba bağsız harcama: {X._money(ov['bagsiz']['harcama'])}",
                 X.data_note(ov)]
        facts += [f"{c['kanalAdi']}: harcama {X._money(c['harcama'])}, platform ROAS {X._ratio(c.get('platformRoas'))}" for c in ov["kanallar"]]
        facts += [f"Kitap {k.get('ad') or k['stokKodu']}: harcama {X._money(k['harcama'])}, e-ticaret ciro "
                  f"{X._money((k.get('satis') or {}).get('eticaretCiro'))}, verim {X._ratio(k.get('verim'))}" for k in ov["kitaplar"][:15]]
        prompt = ("Aşağıdaki reklam raporu rakamları kodla hesaplandı. Pazarlama müdürüne beş cümlelik bir yorum yaz: ne iyi gitti, ne "
                  "kötü gitti, neye bakılmalı. Yeni sayı hesaplama ya da yazma; gerekirse listedeki sayıyı aynen kullan. Platform ROAS'ı "
                  "gerçek getiri diye sunma; satış verisinin tarihini belirt.\n\n" + "\n".join(facts))
        try:
            raw = await run_in_threadpool(lambda: str(llm.chat([{"role": "system", "content": BRIEF_SYSTEM},
                                                                {"role": "user", "content": prompt}], max_tokens=700) or "").strip())
        except Exception as e:  # noqa: BLE001
            log.warning("ads summary failed: %s", e)
            raise HTTPException(status_code=503, detail={"code": "ADS", "message": "Zeki AI'a şu an ulaşılamıyor."}) from None
        res = G.check(raw, [], facts, st()["claims"])
        A.meta_set(engine, tenant, f"yorum:{f.isoformat()}:{t.isoformat()}:{kanal}", {"metin": res["metin"] or None, "kim": user,
                                                                                     "dusen": res["dusenSayisi"]})
        audit(engine, user, "run", "ads_report", None, "Reklam raporu: Zeki AI yorumu", {"bas": f.isoformat(), "bit": t.isoformat(),
                                                                                         "dusen": res["dusenSayisi"]})
        return {"metin": res["metin"] or None, "dusenSayisi": res["dusenSayisi"], "dusen": res["dusen"]}

    # ------------------------------------------------------------------ zamanlayıcı

    @app.post(R + "/run-due")
    def ads_run_due(request: Request) -> dict[str, Any]:
        """Günlük: Logo önbelleği → bağsız kampanyalara kitap önerisi (toplu sıra) → öneri kuralları → yeni önerilerin
        e-postası. Bir adım düşerse diğerleri yine koşar; sonuç `run-due` meta kaydında ve Yönetim değişiklik kaydında."""
        require_caller(request)
        engine, tenant = db()
        s = st()
        ref = A.today()
        out: dict[str, Any] = {"tarih": ref.isoformat()}
        try:
            with refresh_lock:
                out["logo"] = refresh(engine, tenant, s)
        except Exception as e:  # noqa: BLE001
            out["logoHata"] = str(e)[:400]
        out["eslestirme"] = link_job(tenant, None, BATCH)
        warnings: list[str] = []
        books = crm_map(s, warnings)
        if warnings:
            out["crmHata"] = warnings[0]
        made = A.store_suggestions(engine, tenant, A.evaluate(engine, tenant, s, ref, crm_books=books), s)
        out["oneri"] = {"yeni": len(made["yeni"]), "kapanan": made["kapanan"]}
        fresh = [x for x in A.list_suggestions(engine, tenant, "yeni") if x["id"] in set(made["yeni"])]
        llm = rt().llm_for("reklam", BATCH)
        if llm is not None:
            for x in fresh:
                if x["tur"] not in A.APPROVAL_KINDS:
                    continue
                try:
                    facts = [x["gerekce"]]
                    raw = str(llm.chat([{"role": "system", "content": BRIEF_SYSTEM}, {"role": "user", "content":
                                        "Bu reklam önerisinin gerekçesini pazarlama müdürüne bir iki cümleyle açıkla. Yeni sayı yazma; "
                                        f"gerekirse aşağıdakini aynen kullan.\n\n{x['gerekce']}"}], max_tokens=200) or "").strip()
                    res = G.check(raw, [x["gerekce"]], facts, s["claims"])
                    A.set_model_note(engine, x["id"], res["metin"] or None)
                except Exception as e:  # noqa: BLE001 — gerekçe notu olmadan da öneri geçerli
                    log.warning("ads: öneri notu yazılamadı: %s", e)
                    break
        if fresh:
            text = "Yeni reklam önerileri ve uyarıları:\n\n" + "\n".join(f"- {x['turAdi']}: {x['gerekce']}" for x in fresh)
            text += "\n\nReklam platformlarında hiçbir değişiklik portaldan yapılmaz; öneriyi platformda uygulayıp portalda «uygulandı» işaretleyin."
            if link("oneriler"):
                text += f"\n\n{link()}"
            out["eposta"] = _send_mail(f"ZEKİ reklam: {len(fresh)} yeni öneri ({ref.strftime('%d.%m.%Y')})", text, s["recipients"]) \
                if s["recipients"] else "no_recipient"
        else:
            out["eposta"] = "yok"
        A.meta_set(engine, tenant, "run-due", out)
        admin_mod.audit(engine, "sistem", "run", "ads_run_due", None, "Reklam günlük işi", out)
        return out

    return {"crm": crm, "logo": logo, "mkt": mkt, "pool": pool, "refresh": refresh, "link_job": link_job}
