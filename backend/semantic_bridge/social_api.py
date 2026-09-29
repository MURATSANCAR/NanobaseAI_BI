"""M22 Sosyal medya uçları: /api/v1/social/*.

Sayfa kapısı `access.RULES` (`sayfa:sosyal-medya`). Taslak, takvim, hesap, içe aktarma ve Zeki AI taslağı
`ozellik:sosyal.duzenle` (`FEATURE_RULES`); yayına hazır paket ve rapor PDF'i `ozellik:veri.disa-aktar`. Gönderi onayı
ve geri gönderme açıkça verilen `ozellik:sosyal.onay` ile ucun içinde denetlenir (gönderen onaylayamaz).
`ozellik:sosyal.topluluk` (yorum/mesaj ekranı) sonraki sürümde, resmî API bağlanınca kullanılır.

**Otomatik yayın yok:** bu modül hiçbir sosyal medya platformuna istek göndermez. Zamanlayıcı
(`timas-social.timer`, her gün 07:00) yalnız `POST /api/v1/social/run-due`'yu çağırır: yaklaşan özel gün, yarın
hazır olmayan gönderi, onay bekleyen özeti (iç e-posta) ve türü girilmemiş gönderilerin Zeki AI etiketi.

Model çağrıları LLM kapısından: `rt.llm_for("sosyal", NORMAL)` (taslak, rapor yorumu), `rt.llm_for("sosyal", BATCH)`
(gece tür etiketi, `choose`). `LlmClient` doğrudan kurulmaz; rakamı model üretmez (metin denetimi `marketing.guard`).
Sözleşme ucu (M18 aylık plan geri beslemesi okur): `GET /api/v1/social/contract/posts`.
"""
from __future__ import annotations

import logging
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import pazarlama_kaynak as PK
from semantic_bridge import provenance as PV
from semantic_bridge import social as S
from semantic_bridge import social_kaynak as K
from semantic_bridge import social_sources as src
from semantic_bridge.marketing import guard as G
from semantic_bridge.marketing.sources import Crm as MarketingCrm
from semantic_bridge.marketing.sources import SourceError
from semantic_layer.runtime.llm_queue import BATCH, NORMAL

log = logging.getLogger("semantic.social.api")

R = "/api/v1/social"
PAGE = "sayfa:sosyal-medya"
F_EDIT = "ozellik:sosyal.duzenle"
F_APPROVE = "ozellik:sosyal.onay"
F_COMMUNITY = "ozellik:sosyal.topluluk"
F_EXPORT = "ozellik:veri.disa-aktar"
IMPORT_MAX_MB = 25

SYSTEM = ("Sen TİMAŞ Yayınları'nın sosyal medya ekibine taslak yazan Zeki AI'sın. Kurallar: Türkçe yaz. Yalnız sana "
          "verilen bilgileri kullan, kitap ve yazar hakkında bilgi uydurma. Verilen olgu listesinde olmayan hiçbir sayı "
          "yazma (satış, takipçi, yüzde, sıra, tarih dahil). Kitaptan alıntıyı yalnız verilen metinlerde birebir geçen "
          "cümlelerden, en çok iki cümle ve « » içinde yaz; emin değilsen alıntı yapma. «En çok satan», «bir numara», "
          "«rekor», «eşsiz» gibi kanıtsız üstünlük iddiası yazma. Hiçbir teknoloji, model ya da yazılım adı yazma. Herkese "
          "aynı, yapay duran kalıp cümlelerden kaçın; hesabın diline uy.")
PLATFORM_HINT = {
    "instagram": "Instagram: görselle birlikte okunan, ilk satırı merak uyandıran, satır aralıklı kısa metin.",
    "facebook": "Facebook: biraz daha anlatıcı, paylaşmaya davet eden bir iki paragraf.",
    "x": "X: tek fikir, kısa ve net; etiketlerle birlikte 280 karakteri geçmesin.",
    "linkedin": "LinkedIn: kurumsal ve bilgilendirici ton; kitabın değerini ve okurunu anlatan kısa paragraf.",
    "tiktok": "TikTok: videoya eşlik eden çok kısa, samimi açıklama.",
    "youtube": "YouTube: video açıklaması; ilk iki satırda kitabın özü.",
}


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None], can: Callable[[str, str], bool]):
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod
    from semantic_bridge.budget_api import _send_mail

    def schema() -> str:
        return admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo"

    crm = src.Crm(schema)
    mail_crm = MarketingCrm(schema)
    pool = ThreadPoolExecutor(max_workers=max(1, int(os.environ.get("SOCIAL_JOB_WORKERS", "2"))), thread_name_prefix="social")
    started = {"stale": False}
    lock = threading.Lock()

    def st() -> dict[str, Any]:
        return S.settings(admin_mod.conf)

    def web_on() -> bool:
        return (admin_mod.conf("WEB_WATCH_ENABLED") or "0").strip().lower() in ("1", "true", "evet", "on")

    def db() -> tuple[Any, str]:
        r = rt()
        S.ensure(r.store.engine)
        admin_mod.ensure(r.store.engine)
        with lock:
            if not started["stale"]:
                started["stale"] = True
                n = S.fail_stale_jobs(r.store.engine)
                if n:
                    log.info("social: yarıda kalan %d iş kapatıldı", n)
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
        except S.SocialError as e:
            raise HTTPException(status_code=e.status, detail={"code": "SOCIAL", "message": str(e)}) from e
        except SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "SOCIAL_SOURCE", "message": str(e)}) from e

    def need(user: str, key: str, what: str) -> None:
        if not can(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def audit(engine, user: str, action: str, kind: str, oid: Any, title: Any, detail: Any = None) -> None:
        admin_mod.audit(engine, user, action, kind, oid, title, detail)

    # ------------------------------------------------------------------ saklanan CRM okumaları (hız, 2026-09-29)
    # Fırsatlar ve marka önerileri her açılışta CRM'e 1–3 sorgu atıyordu (her biri VPN üstünden yeni bağlantı; ekran
    # 4,8–6,8 sn). Özel günler, kitap bağları, marka kartları ve aralıktaki yeni kitaplar gün içinde nadiren değişir:
    # okuma portal tablosunda (semantic_social_meta, anahtar `crm.*`) saklanır, ekran oradan okur. Kayıt
    # `SOCIAL_CRM_FRESH_SEC` (varsayılan 1 saat) eskidiyse ya da «Verileri yenile» basıldıysa (1 dk'dan eskiyse) hemen
    # eldeki döner ve CRM arkada yeniden okunur; hiç kayıt yoksa (ilk kurulum, yeni tarih aralığı) CRM beklenir.
    # Sabah turu (run-due, 07:00) hepsini beklenerek yeniler. Sorgu bilgisi: saklanan kaydın okuması + onu dolduran CRM SQL'i.
    crm_busy: set[str] = set()

    def crm_fresh_sec() -> float:
        try:
            return max(0.0, float(os.environ.get("SOCIAL_CRM_FRESH_SEC", "3600")))
        except ValueError:
            return 3600.0

    def _age(at: Any) -> Optional[float]:
        try:
            dt = datetime.fromisoformat(str(at))
        except (TypeError, ValueError):
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (S.now() - dt).total_seconds()

    def crm_store(engine, tenant: str, key: str, data: Any) -> str:
        S.meta_set(engine, tenant, key, {"schema": schema(), "data": data})
        if key.startswith("crm.yeni."):
            S.meta_prune(engine, tenant, "crm.yeni.", key, S.now() - timedelta(days=2))
        return S.iso(S.now()) or ""

    def crm_later(engine, tenant: str, key: str, read: Callable[[], Any]) -> None:
        with lock:
            if key in crm_busy:
                return
            crm_busy.add(key)

        def run() -> None:
            try:
                crm_store(engine, tenant, key, read())
            except Exception as e:  # noqa: BLE001 — saklanan okuma gösterilmeye devam eder
                log.info("social: CRM okuması arkada yenilenemedi (%s): %s", key, e)
            finally:
                with lock:
                    crm_busy.discard(key)

        threading.Thread(target=run, name=f"social-crm:{key}", daemon=True).start()

    def crm_saved(engine, tenant: str, key: str, read: Callable[[], Any], *, force: bool = False,
                  nudge: bool = False) -> tuple[Any, Optional[str]]:
        """(veri, okuma anı). `force`: CRM beklenerek şimdi okunur. `nudge`: «Verileri yenile» — beklemeden arkada."""
        if not force:
            row = S.meta_get(engine, tenant, key)
            if "data" in row and row.get("schema") == schema():
                age = _age(row.get("_at"))
                if age is None or age > crm_fresh_sec() or (nudge and age > 60):
                    crm_later(engine, tenant, key, read)
                return row["data"], row.get("_at")
        data = read()
        return data, crm_store(engine, tenant, key, data)

    def saved_days(engine, tenant: str, *, force: bool = False, nudge: bool = False, seen: Optional[dict] = None):
        from semantic_bridge.seo_geo import seasons as SS

        def read() -> dict[str, Any]:
            days, books = crm.special_days_crm()
            return {"days": days, "books": books}

        data, at = crm_saved(engine, tenant, "crm.ozelgun", read, force=force, nudge=nudge)
        if seen is not None:
            seen["crm.ozelgun"] = at
        return SS.merge_builtin(list(data["days"])), dict(data["books"])

    def saved_new_books(engine, tenant: str, start: date, end: date, *, force: bool = False, nudge: bool = False,
                        seen: Optional[dict] = None) -> list[dict[str, Any]]:
        key = f"crm.yeni.{start.isoformat()}.{end.isoformat()}"
        data, at = crm_saved(engine, tenant, key, lambda: crm.new_books(start, end), force=force, nudge=nudge)
        if seen is not None:
            seen["crm.yeni"] = (key, at)
        return list(data)

    def saved_brands(engine, tenant: str, *, force: bool = False, nudge: bool = False,
                     seen: Optional[dict] = None) -> list[dict[str, Any]]:
        data, at = crm_saved(engine, tenant, "crm.marka", crm.brands, force=force, nudge=nudge)
        if seen is not None:
            seen["crm.marka"] = at
        return list(data)

    def refresh_asked(request: Request) -> bool:
        return request.headers.get("x-data-refresh") == "1"

    def link(path: str = "") -> str:
        base = (admin_mod.conf("ALERT_LINK") or "").split("/uyarilar")[0]
        return f"{base}/sosyal-medya{('/' + path) if path else ''}" if base else ""

    def notify(engine, post: dict[str, Any], subject: str, body: str, to_user: str | None) -> None:
        """İç e-posta arka planda; sonucu gönderi geçmişine yazılır. Kişinin CRM e-postası yoksa ayar listesine gider."""
        def run() -> None:
            try:
                to = list(st()["recipients"])
                if to_user:
                    mail = mail_crm.email_of(to_user)
                    to = [mail] if mail else to
                status = _send_mail(subject, body, to) if to else "no_recipient"
                with engine.begin() as c:
                    S.event(c, post["id"], "sistem", "bildirim", None, {"konu": subject, "alici": len(to), "sonuc": status})
            except Exception as e:  # noqa: BLE001
                log.warning("social: bildirim gönderilemedi: %s", e)
        pool.submit(run)

    def title_of(p: dict[str, Any]) -> str:
        return p.get("kitapAd") or p.get("occasionAd") or (p.get("text") or "")[:60] or p["id"]

    # ------------------------------------------------------------------ genel

    @app.get(R + "/meta")
    def social_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        s = st()
        return {
            "platforms": S.PLATFORMS, "statuses": S.STATUSES, "kinds": S.KINDS, "metrics": S.METRIC_LABELS,
            "settings": {"limits": s["limits"], "tagLimits": s["tagLimits"], "opportunityDays": s["opportunityDays"],
                         "leadDays": s["leadDays"], "backlistQuietDays": s["backlistQuietDays"],
                         "backlistMinAgeDays": s["backlistMinAgeDays"], "licensePending": s["licensePending"],
                         "defaultHour": s["defaultHour"], "recipientsSet": bool(s["recipients"])},
            "webWatch": web_on(), "creativeLinked": src.creative_provider(app.state) is not None,
            "lastRun": S.meta_get(engine, tenant, "run-due") or None,
            "modelReady": getattr(rt(), "llm", None) is not None,
            "me": {"username": user, "display": display, "canEdit": can(user, F_EDIT), "canApprove": can(user, F_APPROVE),
                   "canExport": can(user, F_EXPORT), "canCommunity": can(user, F_COMMUNITY)},
        }

    # ------------------------------------------------------------------ hesaplar

    @app.get(R + "/accounts")
    def social_accounts(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        items = S.list_accounts(engine, tenant)
        return PV.bagla({"items": items, "total": len(items)}, lambda: K.for_accounts(engine, tenant))

    @app.post(R + "/accounts", status_code=201)
    def social_account_new(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(S.create_account, engine, tenant, user, body)
        audit(engine, user, "create", "social_account", out["id"], out["ad"], {"platform": out["platform"], "handle": out["handle"]})
        return out

    @app.patch(R + "/accounts/{aid}")
    def social_account_update(aid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        old, out = call(S.update_account, engine, tenant, user, aid, body)
        audit(engine, user, "update", "social_account", out["id"], out["ad"],
              {k: {"eski": old.get(k), "yeni": out.get(k)} for k in out if old.get(k) != out.get(k) and k not in ("guncelleme", "guncelleyen")})
        return out

    @app.get(R + "/accounts/crm-suggestions")
    async def social_account_suggestions(request: Request) -> dict[str, Any]:
        """CRM marka kartlarındaki Instagram kullanıcı adları (hesap listesine öneri; eklenmişler işaretli)."""
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        seen: dict[str, Any] = {}
        brands = await run_in_threadpool(call, saved_brands, engine, tenant, nudge=refresh_asked(request), seen=seen)
        have = {(a["platform"], a["handle"].lstrip("@").lower()) for a in S.list_accounts(engine, tenant)}
        items = [{**b, "ekli": ("instagram", (b["instagram"] or "").lower()) in have} for b in brands]
        return PV.bagla({"items": items, "instagramDolu": sum(1 for b in brands if b["instagram"]), "marka": len(brands)},
                        lambda: K.for_brands(engine, tenant, saved=seen))

    # ------------------------------------------------------------------ kitap ve içerik havuzu

    @app.get(R + "/books")
    async def social_books(request: Request, q: str = "", page: int = 0) -> dict[str, Any]:
        await run_in_threadpool(ctx, request)
        out = await run_in_threadpool(call, crm.search, q, max(0, page))
        return PV.bagla(out, lambda: K.for_search(q, max(0, page)))

    @app.get(R + "/books/{stok}/content")
    async def social_book_content(stok: str, request: Request, platform: str = "") -> dict[str, Any]:
        """Kitaptan içerik: CRM metinleri, alıntılar (CRM + stüdyo), stüdyo sosyal görselleri, M19 onaylı varlıkları,
        telif hak açıklaması ve kitabın takvimdeki gönderileri."""
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        book = await run_in_threadpool(call, crm.book, stok)
        if not book:
            raise HTTPException(status_code=404, detail={"code": "SOCIAL", "message": "Kitap CRM'de bulunamadı."})
        studio = await run_in_threadpool(src.studio_assets, book.get("kitapId"), book.get("ad"))
        rights: list[dict[str, Any]] = []
        if book.get("kitapId"):
            try:
                rights = await run_in_threadpool(crm.rights, book["kitapId"])
            except SourceError as e:
                log.info("social: hak açıklaması okunamadı: %s", e)
        crm_quotes = []
        for m in book["metinler"]:
            if m["alan"] in ("new_kitabinenonemlicumlesi", "new_alintlar"):
                crm_quotes += [x.strip(" -•\t") for x in re.split(r"\n+", m["metin"]) if len(x.strip()) > 3]
        posts = S.list_posts(engine, tenant, st(), stok=stok)
        out = {"kitap": book, "alintilar": {"crm": crm_quotes, "studyo": studio["alintilar"]},
               "gorseller": {"studyo": studio["items"], "studyoHata": studio.get("hata"),
                             "arsiv": src.creative_assets(app.state, stok, platform)},
               "haklar": rights, "gonderiler": posts}
        return PV.bagla(out, lambda: K.for_content(engine, tenant, stok, book.get("kitapId")))

    @app.get(R + "/studio/{job}/{sid}")
    def social_studio_image(job: str, sid: str, request: Request, w: int = 320) -> Response:
        """Stüdyo sosyal görselinin önizlemesi (sosyal medya sayfası stüdyo sayfasına yetkisi olmayan kişiye de gösterir;
        yalnız okuma, stüdyo vekilinin aynısı)."""
        ctx(request)
        if not re.fullmatch(r"s_[0-9a-f]{8}", sid or "") or not re.fullmatch(r"[A-Za-z0-9_\-]{1,80}", job or ""):
            raise HTTPException(status_code=404, detail={"code": "SOCIAL", "message": "Görsel bulunamadı."})
        try:
            data, mime = src.studio_preview(job, sid, max(64, min(int(w), 1600)))
        except Exception as e:  # noqa: BLE001 — stüdyo kapalı ya da görsel silinmiş
            log.info("social: stüdyo görseli okunamadı: %s", e)
            raise HTTPException(status_code=404, detail={"code": "SOCIAL", "message": "Görsel şu an okunamıyor."}) from None
        return Response(content=data, media_type=mime, headers={"Cache-Control": "private, max-age=3600"})

    # ------------------------------------------------------------------ takvim ve fırsatlar

    @app.get(R + "/calendar")
    def social_calendar(request: Request, frm: str = "", to: str = "", account: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        t = S.today()
        start = S.day(frm, "Başlangıç") if frm else t - timedelta(days=t.weekday())
        end = S.day(to, "Bitiş") if to else start + timedelta(days=6)
        out = call(S.calendar, engine, tenant, st(), start, end, account)
        out["onayBekleyen"] = S.pending(engine, tenant, st())
        return PV.bagla(out, lambda: K.for_calendar(engine, tenant, start, end, account))

    def build_opportunities(engine, tenant: str, days: int, bpage: int, ref: date, *, force: bool = False,
                            nudge: bool = False, seen: Optional[dict] = None) -> dict[str, Any]:
        from semantic_bridge.seo_geo import seasons as SS

        s = st()
        posts = S.list_posts(engine, tenant, s, status="fikir,taslak,onayda,onayli,yayinlandi")
        window_books = {p["crmBookId"] for p in posts if p.get("crmBookId") and p.get("plannedAt")
                        and ref.isoformat() <= p["plannedAt"][:10] <= (ref + timedelta(days=days)).isoformat()}
        by_occ: dict[str, set[str]] = {}
        for p in posts:
            if p.get("occasionKey") and p.get("crmBookId"):
                by_occ.setdefault(p["occasionKey"], set()).add(p["crmBookId"])
        out: dict[str, Any] = {"tarih": ref.isoformat(), "gun": days, "hatalar": []}
        try:
            sdays, sbooks = saved_days(engine, tenant, force=force, nudge=nudge, seen=seen)
            planned = {d["key"]: by_occ.get(d["key"], set()) | window_books for d in sdays}
            out["ozelGunler"] = S.occasion_items(sdays, sbooks, ref, days, s["leadDays"], planned, SS.resolve, SS.next_occurrence)
        except SourceError as e:
            out["ozelGunler"], out["hatalar"] = [], out["hatalar"] + [f"Özel günler: {e}"]
        start = ref.replace(day=1)
        end = max(ref + timedelta(days=days), (start + timedelta(days=32)).replace(day=1) - timedelta(days=1))
        posted_stok = {p["stokKodu"] for p in posts if p.get("stokKodu")}
        try:
            nb = saved_new_books(engine, tenant, start, end, force=force, nudge=nudge, seen=seen)
            out["yeniKitaplar"] = {"baslangic": start.isoformat(), "bitis": end.isoformat(),
                                   "items": [{**b, "takvimde": b["stokKodu"] in posted_stok} for b in nb]}
        except SourceError as e:
            out["yeniKitaplar"] = {"baslangic": start.isoformat(), "bitis": end.isoformat(), "items": []}
            out["hatalar"].append(f"Yeni kitaplar: {e}")
        sales, info, data_end, (lo, hi) = src.backlist_sales(engine)
        last: dict[str, str] = {}
        for p in posts:
            if p.get("stokKodu") and p.get("plannedAt") and p["plannedAt"] > last.get(p["stokKodu"], ""):
                last[p["stokKodu"]] = p["plannedAt"]
        ranked = S.backlist_rank(sales, info, last, ref, s["backlistMinAgeDays"], s["backlistQuietDays"],
                                 [x for x in (admin_mod.conf("SOCIAL_BACKLIST_EXCLUDE_STATUS") or "").split(",") if x.strip()])
        size = 20
        out["backlist"] = {
            "veriSonu": data_end.isoformat() if data_end else None,
            "pencere": ({"bas": f"{lo // 12}-{lo % 12 + 1:02d}", "bit": f"{hi // 12}-{hi % 12 + 1:02d}"} if data_end else None),
            "items": ranked[bpage * size:(bpage + 1) * size], "total": len(ranked), "page": bpage, "pageSize": size,
            "not": None if data_end else "Satış verisi yok: bütçe modülünün Logo gerçekleşmesi bu kurulumda okunmamış.",
        }
        out["basin"] = {"acik": web_on(), "items": src.press_mentions(engine, tenant, ref - timedelta(days=days)) if web_on() else []}
        return out

    @app.get(R + "/opportunities")
    async def social_opportunities(request: Request, days: int = 0, bpage: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        d = min(days if days > 0 else st()["opportunityDays"], 366)
        ref = S.today()
        seen: dict[str, Any] = {}
        out = await run_in_threadpool(call, build_opportunities, engine, tenant, d, max(0, bpage), ref,
                                      nudge=refresh_asked(request), seen=seen)
        return PV.bagla(out, lambda: K.for_opportunities(engine, tenant, ref, d, PK.logo_db(rt), saved=seen))

    # ------------------------------------------------------------------ gönderiler

    @app.post(R + "/posts", status_code=201)
    def social_post_new(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(S.create_post, engine, tenant, user, body, st())
        audit(engine, user, "create", "social_post", out["id"], title_of(out),
              {"hesap": out.get("accountId"), "kitap": out.get("stokKodu"), "ozelGun": out.get("occasionKey"), "zaman": out.get("plannedAt")})
        return out

    @app.get(R + "/posts")
    def social_posts(request: Request, frm: str = "", to: str = "", account: str = "", status: str = "", stok: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        f, t = (S.day(frm, "Başlangıç") if frm else None), (S.day(to, "Bitiş") if to else None)
        items = call(S.list_posts, engine, tenant, st(), frm=f, to=t, account=account, status=status, stok=stok)
        return PV.bagla({"items": items, "total": len(items)},
                        lambda: K.for_posts(engine, tenant, frm=f, to=t, account=account, status=status, stok=stok))

    @app.get(R + "/posts/{pid}")
    def social_post(pid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = call(S.get_post, engine, tenant, pid, st())
        out["olcumler"] = S.post_metrics(engine, tenant, pid)
        return PV.bagla(out, lambda: K.for_post(engine, tenant, pid, out.get("accountId")))

    @app.patch(R + "/posts/{pid}")
    def social_post_update(pid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(S.update_post, engine, tenant, user, pid, body, st())
        audit(engine, user, "update", "social_post", pid, title_of(out),
              {k: body[k] for k in ("accountId", "plannedAt", "kind", "stokKodu", "occasionKey", "publishedUrl") if k in body}
              | ({"metin": True} if "text" in body else {}) | ({"gorsel": len(out["assets"])} if "assets" in body else {}))
        return out

    @app.delete(R + "/posts/{pid}")
    def social_post_delete(pid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(S.delete_post, engine, tenant, pid)
        audit(engine, user, "delete", "social_post", pid, out.get("kitapAd") or pid)
        return {"ok": True}

    def _act(pid: str, request: Request, action: str, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        if action in ("approve", "reject"):
            need(user, F_APPROVE, "Sosyal medya gönderisi onayı")
        out = call(S.transition, engine, tenant, user, pid, action, st(), body.get("note"), body.get("url"))
        audit(engine, user, {"approve": "approve", "reject": "reject", "cancel": "delete"}.get(action, "update"), "social_post",
              pid, title_of(out), {"islem": action, "durum": out["status"], "not": body.get("note"), "baglanti": body.get("url")})
        where = f"\n\nGönderi: {link('gonderi/' + pid)}" if link() else ""
        if action == "submit":
            notify(engine, out, f"Onay bekleyen sosyal medya gönderisi: {title_of(out)}",
                   f"{user} gönderiyi onaya gönderdi.\n{(out.get('account') or {}).get('ad') or ''} · {out.get('plannedAt') or ''}{where}", None)
        elif action in ("approve", "reject"):
            what = "onaylandı" if action == "approve" else "geri gönderildi"
            notify(engine, out, f"Sosyal medya gönderisi {what}: {title_of(out)}",
                   f"Gönderi {what} ({user}).\n" + (f"Not: {body.get('note')}\n" if body.get("note") else "") + where,
                   out.get("submittedBy"))
        return out

    for _name in ("submit", "withdraw", "approve", "reject", "published", "cancel", "reopen"):
        def _mk(action: str):
            def handler(pid: str, request: Request, body: dict[str, Any] | None = None) -> dict[str, Any]:
                return _act(pid, request, action, body or {})
            handler.__name__ = f"social_post_{action}"
            return handler
        app.post(R + "/posts/{pid}/" + _name, name=f"social_post_{_name}")(_mk(_name))

    @app.get(R + "/posts/{pid}/events")
    def social_post_events(pid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        call(S.get_post, engine, tenant, pid, st())
        return PV.bagla({"items": S.events(engine, pid)}, lambda: K.for_events(engine, pid))

    @app.post(R + "/posts/{pid}/metrics", status_code=201)
    def social_post_metric(pid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(S.add_manual_metric, engine, tenant, user, pid, body)
        audit(engine, user, "create", "social_metric", pid, "Elle içgörü", out)
        return out

    # ------------------------------------------------------------------ Zeki AI taslağı

    def facts_for(book: dict[str, Any] | None, post: dict[str, Any]) -> list[str]:
        f = []
        if book and book.get("ilkYayin"):
            f.append(f"İlk yayın tarihi: {book['ilkYayin']}")
        yas = [x for x in ((book or {}).get("yas") or []) if x]
        if len(yas) == 2:
            f.append(f"Hedef yaş: {yas[0]}–{yas[1]}")
        if post.get("occasionAd"):
            f.append(f"Özel gün: {post['occasionAd']}")
        return f

    def parse_options(raw: str) -> list[dict[str, str]]:
        return S.parse_options(raw)

    def run_draft(jid: str, tenant: str, user: str, pid: str) -> None:
        engine = rt().store.engine
        try:
            s = st()
            S.job_update(engine, jid, status="calisiyor", step="Kitap bilgisi okunuyor")
            post = S.get_post(engine, tenant, pid, s)
            acc = post.get("account") or {}
            book = crm.book(post["stokKodu"]) if post.get("stokKodu") else None
            studio = src.studio_assets(book.get("kitapId"), book.get("ad")) if book else {"alintilar": []}
            llm = rt().llm_for("sosyal", NORMAL)
            if llm is None:
                S.job_update(engine, jid, status="bitti", step=None,
                             result={"uyari": "Zeki AI bu kurulumda bağlı değil; taslak yazılamadı. Metni CRM'den alabilirsiniz."})
                return
            sources = [m["metin"] for m in (book or {}).get("metinler") or []] + list(studio.get("alintilar") or [])
            sources += [x for x in ((book or {}).get("ad"), (book or {}).get("yazar"), (book or {}).get("yayinevi"),
                                    acc.get("imprintAd"), post.get("occasionAd")) if x]
            facts = facts_for(book, post)
            plat = acc.get("platform") or "instagram"
            lim = s["limits"].get(plat)
            brief = [f"Platform: {S.PLATFORMS.get(plat, plat)}. {PLATFORM_HINT.get(plat, '')}",
                     f"Hesap: {acc.get('ad') or '—'}" + (f" (imprint: {acc['imprintAd']})" if acc.get("imprintAd") else ""),
                     f"Hesabın dili: {acc.get('ton') or 'yayınevinin olağan dili'}",
                     f"İçerik türü: {S.KINDS.get(post.get('kind') or '', 'serbest')}"]
            if post.get("occasionAd"):
                brief.append(f"Özel gün: {post['occasionAd']} (gönderi bu güne bağlanacak)")
            if book:
                brief.append(f"Kitap: {book.get('ad')} · yazar {book.get('yazar') or '—'} · {book.get('yayinevi') or '—'}")
                for m in book["metinler"]:
                    brief.append(f"\n[{m['ad']}]\n{m['metin'][:3000]}")
            if studio.get("alintilar"):
                brief.append("\n[Kitaptan alıntı adayları]\n" + "\n".join(studio["alintilar"][:20]))
            if post.get("text"):
                brief.append(f"\n[Uzmanın mevcut taslağı]\n{post['text'][:3000]}")
            prompt = ("Bu gönderi için üç farklı metin seçeneği yaz. Her seçeneği ayrı satırda «SEÇENEK 1», «SEÇENEK 2», "
                      "«SEÇENEK 3» başlığıyla başlat; metnin altına «ETİKETLER:» satırında konuya uygun beş etiket yaz "
                      "(etiketlerde sayı kullanma)." + (f" Metin ve etiketler birlikte {lim} karakteri geçmesin." if lim else "")
                      + "\n\nOlgu listesi (yazabileceğin sayılar yalnız bunlar):\n" + ("\n".join(facts) or "—") + "\n\n" + "\n".join(brief))
            S.job_update(engine, jid, step="Zeki AI taslağı yazıyor")
            raw = str(llm.chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}], max_tokens=1800) or "")
            opts, dropped = [], 0
            for o in parse_options(raw)[:3]:
                res = G.check(o["metin"], sources, facts, s["claims"])
                tags = []
                for t in (S.hashtags(o["etiketler"]) or "").split():
                    if not G.check(t, sources, facts, s["claims"])["dusenSayisi"]:
                        tags.append(t)
                    else:
                        dropped += 1
                dropped += res["dusenSayisi"]
                if not res["metin"]:
                    continue
                n = len(res["metin"]) + (len(" ".join(tags)) + 1 if tags else 0)
                opts.append({"metin": res["metin"], "etiketler": " ".join(tags), "dusen": res["dusen"],
                             "karakter": n, "uzun": bool(lim and n > lim)})
            draft = {"secenekler": opts, "dusen": dropped, "zaman": S.iso(S.now()), "kim": user, "platform": plat}
            S.set_draft(engine, pid, draft, user)
            S.job_update(engine, jid, status="bitti", step=None,
                         result={"secenek": len(opts), "dusen": dropped,
                                 **({"uyari": "Denetimden geçen seçenek kalmadı; metni elle yazın."} if not opts else {})})
            admin_mod.audit(engine, user, "run", "social_post", pid, "Zeki AI taslağı", {"secenek": len(opts), "dusen": dropped})
        except Exception as e:  # noqa: BLE001 — iş hatası ekranda görünür, köprüyü düşürmez
            log.exception("social draft job failed")
            S.job_update(engine, jid, status="hata", step=None, error=str(e)[:500] or e.__class__.__name__)

    @app.post(R + "/posts/{pid}/draft", status_code=202)
    def social_post_draft(pid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        post = call(S.get_post, engine, tenant, pid, st())
        if post["status"] not in S.OPEN:
            raise HTTPException(status_code=409, detail={"code": "SOCIAL", "message": "Zeki AI taslağı yalnız fikir ya da taslak gönderiye yazılır."})
        job = call(S.job_create, engine, tenant, user, "draft", pid)
        pool.submit(run_draft, job["id"], tenant, user, pid)
        return {"job": job}

    @app.get(R + "/posts/{pid}/jobs")
    def social_post_jobs(pid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        call(S.get_post, engine, tenant, pid, st())
        return PV.bagla({"items": S.jobs_of(engine, tenant, post_id=pid)}, lambda: K.for_jobs(engine, tenant, pid))

    # ------------------------------------------------------------------ yayına hazır paket

    @app.get(R + "/posts/{pid}/package.zip")
    def social_package(pid: str, request: Request) -> Response:
        engine, tenant, user, _ = ctx(request)
        post = call(S.get_post, engine, tenant, pid, st())
        if post["status"] not in ("onayli", "yayinlandi"):
            raise HTTPException(status_code=409, detail={"code": "SOCIAL", "message": "Paket yalnız onaylı gönderiden hazırlanır."})

        def fetch(a: dict[str, Any]) -> tuple[bytes, str] | None:
            if a["tip"] == "studio":
                return src.studio_file(a["job"], a["sid"])
            return src.creative_file(app.state, a["id"])

        body = S.package_zip(post, fetch, st())
        audit(engine, user, "run", "social_post", pid, title_of(post), {"disaAktar": "paket", "gorsel": len(post["assets"])})
        return Response(body, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="yayina-hazir-{pid}.zip"'})

    # ------------------------------------------------------------------ içe aktarma

    @app.post(R + "/imports", status_code=201)
    async def social_import(request: Request, account: str = "", filename: str = "", gun: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        if int(request.headers.get("content-length") or 0) > IMPORT_MAX_MB * 1024 * 1024:
            raise HTTPException(413, detail={"code": "SOCIAL", "message": f"Dosya {IMPORT_MAX_MB} MB sınırını aşıyor."})
        data = await request.body()
        out = await run_in_threadpool(call, S.import_metrics, engine, tenant, user, account, filename, data, gun or None)
        audit(engine, user, "upload", "social_import", out["id"], filename or "dosya",
              {"hesap": account, "satir": out["satir"], "eslesen": out["eslesen"], "toplam": out["toplam"]})
        return out

    @app.get(R + "/imports")
    def social_imports(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        items = S.list_imports(engine, tenant)
        return PV.bagla({"items": items, "total": len(items)}, lambda: K.for_imports(engine, tenant))

    @app.delete(R + "/imports/{iid}")
    def social_import_delete(iid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(S.delete_import, engine, tenant, iid)
        audit(engine, user, "delete", "social_import", iid, out["dosya"], {"satir": out["satir"]})
        return {"ok": True}

    # ------------------------------------------------------------------ rapor

    @app.get(R + "/report")
    def social_report(request: Request, month: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        m = month or S.today().strftime("%Y-%m")
        out = call(S.report, engine, tenant, m)
        jobs = S.jobs_of(engine, tenant, hedef=out["ay"])
        out["yorum"] = next((j for j in jobs if j["tur"] == "report"), None)
        return PV.bagla(out, lambda: K.for_report(engine, tenant, out["ay"]))

    @app.get(R + "/report/export.pdf")
    async def social_report_pdf(request: Request, month: str = "") -> Response:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        m = month or S.today().strftime("%Y-%m")
        rep = call(S.report, engine, tenant, m)
        jobs = S.jobs_of(engine, tenant, hedef=rep["ay"])
        yorum = next(((j.get("sonuc") or {}).get("metin") for j in jobs if j["tur"] == "report" and j["durum"] == "bitti"), None)
        body = await run_in_threadpool(call, S.report_pdf, rep, yorum, user)
        audit(engine, user, "run", "social_report", rep["ay"], f"Sosyal medya raporu {rep['ay']}", {"disaAktar": "pdf"})
        return Response(body, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="sosyal-medya-raporu-{rep["ay"]}.pdf"'})

    def run_comment(jid: str, tenant: str, user: str, month: str) -> None:
        engine = rt().store.engine
        try:
            S.job_update(engine, jid, status="calisiyor", step="Rapor okunuyor")
            rep = S.report(engine, tenant, month)
            llm = rt().llm_for("sosyal", NORMAL)
            if llm is None:
                S.job_update(engine, jid, status="bitti", step=None, result={"uyari": "Zeki AI bu kurulumda bağlı değil."})
                return
            facts = S.report_facts(rep)
            prompt = ("Aşağıdaki aylık sosyal medya rakamlarını pazarlama müdürüne beş cümleyle yorumla: hangi içerik türü "
                      "ve hesap iyi gitti, gelecek ayın planı için bir öneri. Rakamları yeniden hesaplama, yeni sayı yazma; "
                      "sayı gerekirse listedekini aynen kullan. Kişi adı yazma.\n\n" + "\n".join(facts))
            S.job_update(engine, jid, step="Zeki AI yorum yazıyor")
            raw = str(llm.chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}], max_tokens=700) or "")
            res = G.check(raw, facts, facts, st()["claims"])
            S.job_update(engine, jid, status="bitti", step=None, result={"metin": res["metin"] or None, "dusen": res["dusen"]})
        except Exception as e:  # noqa: BLE001
            log.exception("social report comment failed")
            S.job_update(engine, jid, status="hata", step=None, error=str(e)[:500] or e.__class__.__name__)

    @app.post(R + "/report/commentary", status_code=202)
    def social_report_comment(request: Request, body: dict[str, Any] | None = None) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        m = str((body or {}).get("month") or S.today().strftime("%Y-%m"))
        start, _ = call(S._month, m)
        month = start.strftime("%Y-%m")
        job = call(S.job_create, engine, tenant, user, "report", None, month)
        pool.submit(run_comment, job["id"], tenant, user, month)
        return {"job": job}

    # ------------------------------------------------------------------ sözleşme (M18 geri besleme)

    @app.get(R + "/contract/posts")
    def social_contract(request: Request, frm: str = "", to: str = "", stok: str = "") -> dict[str, Any]:
        """Onaylı ve yayınlanmış gönderiler, ölçü toplamlarıyla. M18 aylık plan kodlanınca bu uçla plan ↔ gönderi
        geri beslemesi kurulur (gönderideki `planRef` plan satırıdır)."""
        engine, tenant, _, _ = ctx(request)
        items = call(S.list_posts, engine, tenant, st(), frm=S.day(frm, "Başlangıç") if frm else None,
                     to=S.day(to, "Bitiş") if to else None, status="onayli,yayinlandi", stok=stok)
        for p in items:
            ms = S.post_metrics(engine, tenant, p["id"])
            p["olcu"] = {k: round(sum((m.get(k) or 0) for m in ms), 2) for k in S.METRIC_COLS if k != "followers"}
            p.pop("draft", None)
        return {"items": items, "total": len(items)}

    # ------------------------------------------------------------------ zamanlayıcı

    @app.post(R + "/run-due")
    def social_run_due(request: Request, force: bool = False) -> dict[str, Any]:
        """Günlük özet (yarın hazır olmayan gönderi, yaklaşan özel gün, onay bekleyen) tek iç e-posta; türü girilmemiş
        onaylı/yayınlanmış gönderilere Zeki AI tür etiketi. Hiçbir platforma paylaşım yapılmaz."""
        require_caller(request)
        engine, tenant = db()
        s = st()
        ref = S.today()
        out: dict[str, Any] = {"tarih": ref.isoformat()}
        try:
            # Sabah turu saklanan CRM okumalarını beklenerek yeniler (özel günler, kitap bağları, yeni kitaplar).
            opp = build_opportunities(engine, tenant, s["leadDays"], 0, ref, force=True)
            occ = [o for o in opp["ozelGunler"] if o["uyari"]]
            out["hatalar"] = opp["hatalar"]
        except Exception as e:  # noqa: BLE001
            occ, out["hatalar"] = [], [str(e)[:300]]
        out["crmOkuma"] = refresh_saved(engine, tenant, s, ref)
        dg = {"yarin": S.due_tomorrow(engine, tenant, s, ref), "ozelGun": occ, "onayda": len(S.pending(engine, tenant, s))}
        out["ozet"] = {"yarin": len(dg["yarin"]), "ozelGun": len(occ), "onayda": dg["onayda"]}
        body = S.digest_text(dg, link())
        last = S.meta_get(engine, tenant, "digest")
        if body is None:
            out["eposta"] = "yok"
        elif last.get("tarih") == ref.isoformat() and last.get("sonuc") == "sent" and not force:
            out["eposta"] = "bugün gönderildi"
        else:
            status = _send_mail(f"ZEKİ sosyal medya: günlük özet ({ref.strftime('%d.%m.%Y')})", body, s["recipients"]) \
                if s["recipients"] else "no_recipient"
            S.meta_set(engine, tenant, "digest", {"tarih": ref.isoformat(), "sonuc": status})
            out["eposta"] = status
        out["turEtiketi"] = label_kinds(engine, tenant)
        S.meta_set(engine, tenant, "run-due", out)
        return out

    def refresh_saved(engine, tenant: str, s: dict[str, Any], ref: date) -> dict[str, Any]:
        """Ekranın varsayılan fırsat penceresinin yeni kitapları ve marka kartları (özel günler yukarıda yenilendi)."""
        res: dict[str, Any] = {}
        start = ref.replace(day=1)
        end = max(ref + timedelta(days=s["opportunityDays"]), (start + timedelta(days=32)).replace(day=1) - timedelta(days=1))
        for name, fn in (("yeniKitaplar", lambda: saved_new_books(engine, tenant, start, end, force=True)),
                         ("markalar", lambda: saved_brands(engine, tenant, force=True))):
            try:
                res[name] = len(fn())
            except Exception as e:  # noqa: BLE001 — tur sürer; ekran saklanan okumayla çalışır
                res[name] = f"hata: {str(e)[:200]}"
        return res

    def label_kinds(engine, tenant: str) -> dict[str, Any]:
        """Türü boş, metni olan onaylı/yayınlanmış gönderiler: kapalı seçim (tek token + olasılık); eşiğin altı boş kalır."""
        llm = rt().llm_for("sosyal", BATCH)
        if llm is None or not hasattr(llm, "choose"):
            return {"atlandi": "Zeki AI kapalı seçim bu kurulumda yok."}
        s = st()
        names = list(S.KINDS.values())
        back = {v: k for k, v in S.KINDS.items()}
        done = low = 0
        for p in S.list_posts(engine, tenant, s, status="onayli,yayinlandi"):
            if p.get("kind") or not p.get("text"):
                continue
            q = (f"Sosyal medya gönderisi:\n{p['text'][:1500]}\n" + (f"Kitap: {p['kitapAd']}\n" if p.get("kitapAd") else "")
                 + (f"Özel gün: {p['occasionAd']}\n" if p.get("occasionAd") else "") + "\nBu gönderinin içerik türü hangisi?")
            try:
                ch = llm.choose(q, names)
            except Exception as e:  # noqa: BLE001
                log.info("social: tür etiketi alınamadı (%s): %s", p["id"], e)
                continue
            if ch.confident(s["minProb"], s["minMargin"]) and ch.choice in back:
                S.set_kind(engine, p["id"], back[ch.choice], ch.probability)
                done += 1
            else:
                low += 1
        return {"etiketlenen": done, "belirsiz": low}

    return {"crm": crm, "pool": pool}
