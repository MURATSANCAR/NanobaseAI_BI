"""M34 E-ticaret ve platform yönetimi uçları: /api/v1/eticaret/*.

Sayfa kapısı `access.RULES` (`sayfa:eticaret`, `sayfa:eticaret-farklar`, `sayfa:eticaret-huni`,
`sayfa:eticaret-pazar-yerleri`). Fark işaretleme ve okumayı yenileme `ozellik:eticaret.fark-isaretle`, Zeki AI metin önerisi
`ozellik:eticaret.oneri-uret` (model harcar), fark listesi CSV'si ve içerik paketi `ozellik:veri.disa-aktar` (`FEATURE_RULES`).
Öneri onayı açıkça verilen `ozellik:eticaret.oneri-onay` ile burada denetlenir; öneriyi isteyen onaylayamaz (409).
Zamanlayıcı (`timas-eticaret.timer`, her gece 04:30) yalnız `POST /api/v1/eticaret/run-due`'yu çağırır.

**Dış gönderim yok.** T-soft'a, CRM'e, Logo'ya ve pazar yerlerine hiçbir şey yazılmaz. Onaylanan metin SEO öneri kaydında
durur (`semantic_seo_proposals`, kaynak «E-ticaret»); içerik paketi indirilir, platforma kişi yükler. E-posta yalnız iç
bildirimdir (`ECOM_ALERT_RECIPIENTS`, `ECOM_WEEKLY_TO`).

Model çağrıları LLM kapısından: `rt.llm_for("eticaret", …)` (`deps["llm"]`). `LlmClient` doğrudan kurulmaz.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, timedelta
from typing import Any, Callable, Optional

import sqlalchemy as sa
from fastapi import HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from semantic_bridge import eticaret as E
from semantic_bridge import eticaret_sources as src

log = logging.getLogger("semantic.eticaret.api")
P = "/api/v1/eticaret"
FEATURE_MARK = "ozellik:eticaret.fark-isaretle"
FEATURE_PROPOSE = "ozellik:eticaret.oneri-uret"
FEATURE_APPROVE = "ozellik:eticaret.oneri-onay"
FEATURE_EXPORT = "ozellik:veri.disa-aktar"
#: SEO öneri kaydında bu modülden gelen önerinin kaynağı (ekranda görünür; teknoloji adı yok).
PROPOSAL_SOURCE = "E-ticaret · Zeki AI"
MARKET_TTL = 30 * 60


# Gövde modelleri modül düzeyinde: `from __future__ import annotations` fonksiyon içindeki modeli sorgu parametresi sanar.
class Mark(BaseModel):
    durum: str = Field(pattern="^(acik|sonra|bilincli|duzeltildi)$")
    note: str = Field(default="", max_length=1000)
    sahip: Optional[str] = Field(default=None, max_length=120)


class BulkMark(BaseModel):
    ids: list[str] = Field(min_length=1)
    durum: str = Field(pattern="^(acik|sonra|bilincli|duzeltildi)$")
    note: str = Field(default="", max_length=1000)
    sahip: Optional[str] = Field(default=None, max_length=120)


class Decide(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")
    fields: dict[str, str] = Field(default_factory=dict)
    note: str = Field(default="", max_length=1000)


class _Cache:
    """Pazar yeri özetleri için süreli bellek (Logo okuması ağır; aynı yıl iki kez okunmaz)."""

    def __init__(self) -> None:
        self._data: dict[Any, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: Any, load: Callable[[], Any], fresh: bool = False) -> Any:
        with self._lock:
            hit = self._data.get(key)
            if hit and not fresh and time.monotonic() - hit[0] < MARKET_TTL:
                return hit[1]
        val = load()
        with self._lock:
            self._data[key] = (time.monotonic(), val)
        return val


def register(app: Any, deps: dict[str, Any]) -> E.Refresher:
    """app.py'de bağlanır. `deps`: auth(request) → (engine, tenant, user, display) · require_caller(request) · can(user, key) ·
    is_admin(user) · audit(engine, user, action, kind, id, title, detail) · conf(key, default) · engine() · tenant() ·
    logo_file() · crm_file() · llm(priority) → LLM kapısı istemcisi ya da None · seo → SEO & GEO nesnesi (öneri kaydı) ·
    send_mail(subject, text, to) → durum."""
    auth, require_caller, can, is_admin, audit, conf = (deps[k] for k in ("auth", "require_caller", "can", "is_admin", "audit", "conf"))
    settings = lambda: E.settings_from(conf)  # noqa: E731
    schema = lambda: conf("CRM_SCHEMA", "Timas_MSCRM.dbo") or "Timas_MSCRM.dbo"  # noqa: E731
    refresher = E.Refresher(deps["engine"], deps["tenant"], deps["logo_file"], deps["crm_file"], schema, settings)
    cache = _Cache()
    firms_cache: dict[str, Any] = {"at": 0.0, "firms": None, "cut": None}

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        engine, tenant, user, display = auth(request)
        E.ensure(engine)
        return engine, tenant, user, display

    def has(user: str, key: str) -> bool:
        return is_admin(user) or can(user, key)

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except E.EticaretError as e:
            raise HTTPException(status_code=e.status, detail={"code": "ETICARET", "message": str(e)}) from e
        except src.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "ETICARET_SOURCE", "retryable": True, "message": str(e)}) from e

    def logo():
        run = src.runner(deps["logo_file"]())
        if not firms_cache["firms"] or time.time() - firms_cache["at"] > 600:
            firms = src.firms_by_year(run)
            firms_cache.update(firms=firms, cut=src.read_data_end(run, firms), at=time.time())
        return run, firms_cache["firms"], firms_cache["cut"]

    def llm(priority_name: str) -> Any:
        from semantic_layer.runtime import llm_queue

        try:
            return deps["llm"](getattr(llm_queue, priority_name))
        except Exception as e:  # noqa: BLE001
            log.info("eticaret: model yok: %s", e)
            return None

    def link() -> str:
        return (conf("ALERT_LINK", "") or "").split("/uyarilar")[0]

    def markets(year: int, fresh: bool = False) -> dict[str, Any]:
        def load() -> dict[str, Any]:
            run, firms, cut = logo()
            this, prev = E.marketplace_windows(year, cut)
            rows = src.read_marketplaces(run, firms, settings()["channels"], *prev) + src.read_marketplaces(run, firms, settings()["channels"], *this)
            out = E.marketplace_summary(rows, year, cut)
            out["kanallar"] = settings()["channels"]
            out["yillar"] = sorted(firms)
            return out
        return call(cache.get, ("m", year, tuple(settings()["channels"])), load, fresh)

    def stock_risk(engine, tenant: str, year: int, fresh: bool = False) -> list[dict[str, Any]]:
        st = settings()

        def load() -> list[dict[str, Any]]:
            run, firms, cut = logo()
            this, _ = E.marketplace_windows(year, cut)
            return src.read_channel_books(run, firms, st["channels"], *this)
        rows = call(cache.get, ("r", year, tuple(st["channels"])), load, fresh)
        books = E.marketplace_books(rows, E.items_by_code(engine, tenant, [r["stok"] for r in rows]), st)
        return [b for b in books if b["tukenmeRiski"]]

    def this_year() -> int:
        cut = firms_cache.get("cut")
        return cut.year if cut else date.today().year

    # ------------------------------------------------------------------ genel

    @app.get(f"{P}/meta")
    def eticaret_meta(request: Request) -> dict[str, Any]:
        engine, _, user, display = ctx(request)
        st = settings()
        return {
            "turler": E.DIFF_KINDS, "durumlar": E.STATUSES, "isaretler": list(E.MARKS), "alanlar": E.FIELD_LABELS,
            "nedenler": E.REASONS, "gonderim": False,
            "ayarlar": {k: st[k] for k in ("channels", "priceRef", "priceTol", "stockMin", "required", "kinds", "alertKinds",
                                           "snoozeDays", "salesMonths", "funnelMinViews", "funnelLowRatio", "stockoutDays")}
                       | {"bildirim": bool(st["alertTo"]), "haftalik": bool(st["weeklyTo"])},
            "durum": refresher.status(),
            "me": {"username": user, "display": display, "admin": is_admin(user), "canMark": has(user, FEATURE_MARK),
                   "canPropose": has(user, FEATURE_PROPOSE), "canApprove": has(user, FEATURE_APPROVE),
                   "canExport": has(user, FEATURE_EXPORT)},
        }

    @app.get(f"{P}/overview")
    def eticaret_overview(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return E.overview(engine, tenant, refresher.status())

    @app.get(f"{P}/status")
    def eticaret_status(request: Request) -> dict[str, Any]:
        ctx(request)
        return refresher.status()

    @app.post(f"{P}/refresh")
    def eticaret_refresh(request: Request) -> dict[str, Any]:
        engine, _, user, _ = ctx(request)
        started = refresher.start(user)
        audit(engine, user, "run", "eticaret_refresh", None, "E-ticaret farkları yeniden okundu", {"started": started})
        return {"started": started, **refresher.status()}

    @app.post(f"{P}/run-due")
    async def eticaret_run_due(request: Request, weekly: Optional[bool] = None, model: bool = True) -> dict[str, Any]:
        """Zamanlayıcı: CRM + Logo okuması ve fark hesabı (site verisi SEO eşitlemesinden), Zeki AI neden önerisi (süre
        bütçeli), ilk kez görülen farkların tek özet e-postası, haftalık özet (ayardaki gün ya da `weekly=true`)."""
        require_caller(request)
        engine, tenant, st = deps["engine"](), deps["tenant"](), settings()
        E.ensure(engine)
        out: dict[str, Any] = {"read": await run_in_threadpool(refresher.run, "zamanlayıcı")}
        if model and st["llmBudgetSec"]:
            out["model"] = await run_in_threadpool(E.classify_reasons, engine, tenant, llm("BATCH"), st, st["llmBudgetSec"])
        pending = E.pending_alerts(engine, tenant, st)
        if pending and st["alertTo"]:
            status = deps["send_mail"](f"E-ticaret: {len(pending)} yeni fark", E.alert_text(pending, link()), st["alertTo"])
            if status == "sent":
                E.mark_alerted(engine, tenant, [p["id"] for p in pending])
            out["alert"] = {"status": status, "count": len(pending)}
        else:
            out["alert"] = {"status": "no_recipient" if pending else "nothing", "count": len(pending)}
        if weekly or (weekly is None and E.weekly_due(engine, tenant, st)):
            out["weekly"] = await run_in_threadpool(send_weekly, engine, tenant, st)
        return out

    def send_weekly(engine, tenant: str, st: dict[str, Any]) -> dict[str, Any]:
        started = E.now()
        ov = E.overview(engine, tenant, refresher.status())
        year = this_year()
        try:
            mk = markets(year, fresh=True)
            risky = stock_risk(engine, tenant, year, fresh=True)
        except HTTPException as e:
            mk, risky = None, []
            log.info("eticaret haftalık: pazar yeri okunamadı: %s", e.detail)
        if not st["weeklyTo"]:
            return {"status": "no_recipient"}
        status = deps["send_mail"]("E-ticaret haftalık özeti", E.weekly_text(ov, mk, risky, link()), st["weeklyTo"])
        E.record_run(engine, tenant, "haftalik", "zamanlayıcı", started, {"status": status}, None if status == "sent" else status)
        return {"status": status}

    # ------------------------------------------------------------------ farklar

    @app.get(f"{P}/diffs")
    def eticaret_diffs(request: Request, tur: str = "", durum: str = "", q: str = "", sahip: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(E.list_diffs, engine, tenant, tur=tur, durum=durum, q=q, sahip=sahip, page=page)

    @app.get(f"{P}/diffs/export.csv")
    def eticaret_diffs_csv(request: Request, tur: str = "", durum: str = "", q: str = "", sahip: str = "") -> Response:
        engine, tenant, user, _ = ctx(request)
        rows = call(E.all_diffs, engine, tenant, tur=tur, durum=durum, q=q, sahip=sahip)
        audit(engine, user, "run", "eticaret_export", None, "Fark listesi (CSV)", {"satir": len(rows), "tur": tur, "durum": durum})
        return Response(E.diffs_csv(rows), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="eticaret-farklar.csv"'})

    @app.post(f"{P}/diffs/mark-bulk")
    def eticaret_mark_bulk(body: BulkMark, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        st = settings()
        done, skipped = [], []
        for did in dict.fromkeys(body.ids):
            try:
                done.append(E.mark(engine, tenant, user, did, body.durum, body.note, body.sahip, st))
            except E.EticaretError as e:
                if e.status == 422:
                    raise HTTPException(status_code=422, detail={"code": "ETICARET", "message": str(e)}) from e
                skipped.append({"id": did, "neden": str(e)})
        audit(engine, user, "update", "eticaret_diff", None, f"{len(done)} fark işaretlendi",
              {"durum": body.durum, "not": body.note[:200], "atlanan": len(skipped)})
        return {"items": done, "atlanan": skipped}

    @app.get(f"{P}/diffs/{{did}}")
    def eticaret_diff(did: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(E.get_diff, engine, tenant, did)

    @app.post(f"{P}/diffs/{{did}}/mark")
    def eticaret_mark(did: str, body: Mark, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(E.mark, engine, tenant, user, did, body.durum, body.note, body.sahip, settings())
        audit(engine, user, "update", "eticaret_diff", did, (out.get("ad") or out["productKey"])[:300],
              {"tur": out["tur"], "durum": body.durum, "not": body.note[:200], "sahip": body.sahip})
        return out

    # ------------------------------------------------------------------ kitap

    @app.get(f"{P}/items/{{key}}")
    def eticaret_item(key: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(E.item_detail, engine, tenant, key)
        site = (conf("SEO_SITE_URL", "") or "").rstrip("/")
        url = out["kitap"].get("url")
        if url and not str(url).startswith("http"):
            out["kitap"]["url"] = f"{site}/{str(url).lstrip('/')}" if site else None
        out["oneriler"] = proposals_for(engine, tenant, out["kitap"].get("tsoftUrunId"))
        return out

    @app.post(f"{P}/items/{{key}}/propose")
    async def eticaret_propose(key: str, request: Request) -> dict[str, Any]:
        """Zeki AI ürün kartı metni (başlık, açıklama, anahtar kelime) → SEO öneri kaydına «E-ticaret» kaynağıyla düşer;
        onay bu modülde ya da SEO ekranında verilir. Hiçbir yere gönderilmez."""
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        return await run_in_threadpool(make_proposal, engine, tenant, user, key)

    def make_proposal(engine, tenant: str, user: str, key: str) -> dict[str, Any]:
        from semantic_bridge.seo_geo import propose as seo_propose
        from semantic_bridge.seo_geo import rules as seo_rules
        from semantic_bridge.seo_geo.store import loads

        seo = deps.get("seo")
        if seo is None:
            raise HTTPException(status_code=409, detail={"code": "ETICARET", "message": "SEO & GEO modülü bu kurulumda yok; öneri kaydı açılamaz."})
        item = call(E.item_detail, engine, tenant, key)["kitap"]
        pid = item.get("tsoftUrunId")
        if not pid:
            raise HTTPException(status_code=409, detail={"code": "ETICARET", "message": "Kitabın sitede ürünü yok; önce ürün açılmalı."})
        client = llm("NORMAL")
        if client is None:
            raise HTTPException(status_code=503, detail={"code": "ETICARET", "message": "Zeki AI bu kurulumda tanımlı değil."})
        p = dict(loads(seo.product_row(pid)["data_json"], {}))
        # Sitedeki açıklama boşsa kaynak metin CRM kartından gelir (arka kapak, spot); model yalnız bunlardan yazar.
        if key.isdigit():
            try:
                crm = src.read_crm_content(src.runner(deps["crm_file"]()), schema(), [key]).get(key) or {}
            except src.SourceError:
                crm = {}
            if len(seo_rules.text_of(p.get("Details") or "")) < 200 and crm.get("arka_kapak"):
                p["Details"] = crm["arka_kapak"]
            if not p.get("ShortDescription") and crm.get("spot"):
                p["ShortDescription"] = crm["spot"]
        try:
            fields = seo_propose.suggest(client, p, seo_rules.thresholds(conf))
        except ValueError as e:
            raise HTTPException(status_code=502, detail={"code": "ETICARET", "message": f"Öneri üretilemedi: {e}"}) from None
        prop = seo.external_proposal(pid, fields, user, PROPOSAL_SOURCE)
        audit(engine, user, "create", "eticaret_proposal", prop["id"], (item.get("ad") or key)[:300], {"urun": pid, "anahtar": key})
        return _proposal_view(prop)

    def proposals_for(engine, tenant: str, pid: Optional[str], status: str = "") -> list[dict[str, Any]]:
        from semantic_bridge.seo_geo.store import PROPOSALS, ensure as seo_ensure

        seo_ensure(engine)
        cond = [PROPOSALS.c.tenant_id == tenant, PROPOSALS.c.model == PROPOSAL_SOURCE]
        if pid is not None:
            cond.append(PROPOSALS.c.product_id == pid)
        if status:
            cond.append(PROPOSALS.c.status == status)
        with engine.connect() as c:
            rows = c.execute(sa.select(PROPOSALS).where(*cond).order_by(PROPOSALS.c.created_at.desc())).mappings().all()
        return [_proposal_view(dict(r)) for r in rows]

    @app.get(f"{P}/proposals")
    def eticaret_proposals(request: Request, durum: str = "hazir") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        if durum not in ("", "hazir", "onaylandi", "reddedildi"):
            raise HTTPException(status_code=422, detail={"code": "ETICARET", "message": "Bilinmeyen durum."})
        items = proposals_for(engine, tenant, None, durum)
        with engine.connect() as c:
            ids = [p["productId"] for p in items]
            by_pid = {}
            for i in range(0, len(ids), 500):
                for r in c.execute(sa.select(E.ITEMS.c.tsoft_product_id, E.ITEMS.c.product_key, E.ITEMS.c.ad).where(
                        E.ITEMS.c.tenant_id == tenant, E.ITEMS.c.tsoft_product_id.in_(ids[i:i + 500]))).all():
                    by_pid[r[0]] = {"productKey": r[1], "ad": r[2]}
        return {"items": [{**p, **by_pid.get(p["productId"], {})} for p in items], "canApprove": has(user, FEATURE_APPROVE)}

    @app.post(f"{P}/proposals/{{proposal_id}}/decide")
    def eticaret_decide(proposal_id: str, body: Decide, request: Request) -> dict[str, Any]:
        """Onay/ret: açıkça verilen `eticaret.oneri-onay`; öneriyi isteyen onaylayamaz. Onay yalnız kayıttır."""
        from semantic_bridge.seo_geo import propose as seo_propose
        from semantic_bridge.seo_geo.store import PROPOSALS, loads, now as seo_now

        engine, tenant, user, _ = ctx(request)
        if not has(user, FEATURE_APPROVE):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "E-ticaret önerisi onayı rolünüzde yok."})
        seo = deps.get("seo")
        if seo is None:
            raise HTTPException(status_code=409, detail={"code": "ETICARET", "message": "SEO & GEO modülü bu kurulumda yok."})
        prop = seo.proposal(proposal_id)
        if prop.get("model") != PROPOSAL_SOURCE:
            raise HTTPException(status_code=404, detail={"code": "ETICARET", "message": "Bu öneri e-ticaret önerisi değil."})
        if prop["status"] != "hazir":
            raise HTTPException(status_code=409, detail={"code": "ETICARET", "message": "Bu öneri için karar zaten verilmiş."})
        if (prop.get("created_by") or "").lower() == user.lower():
            raise HTTPException(status_code=409, detail={"code": "ETICARET", "message": "Öneriyi isteyen kişi onaylayamaz; başka bir onaycı karar vermeli."})
        if body.action == "reject":
            if not body.note.strip():
                raise HTTPException(status_code=422, detail={"code": "ETICARET", "message": "Ret için gerekçe yazılmalı."})
            with engine.begin() as c:
                c.execute(PROPOSALS.update().where(PROPOSALS.c.id == proposal_id).values(
                    status="reddedildi", decided_by=user, decided_at=seo_now(), note=body.note))
            audit(engine, user, "reject", "eticaret_proposal", proposal_id, prop["product_id"], {"not": body.note[:200]})
            return _proposal_view(seo.proposal(proposal_id))
        fields = {k: v for k, v in (body.fields or loads(prop["fields_json"], {})).items() if k in seo_propose.FIELDS}
        out = seo.approve(prop, fields, user, body.note)
        audit(engine, user, "approve", "eticaret_proposal", proposal_id, prop["product_id"], {"alanlar": sorted(fields)})
        return _proposal_view(out)

    # ------------------------------------------------------------------ huni

    @app.get(f"{P}/funnel")
    def eticaret_funnel(request: Request, dusuk: bool = False, q: str = "", sort: str = "goruntulenme", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return E.funnel(engine, tenant, settings(), dusuk=dusuk, q=q, sort=sort, page=page)

    # ------------------------------------------------------------------ pazar yerleri (Logo)

    @app.get(f"{P}/marketplaces")
    async def eticaret_marketplaces(request: Request, yil: Optional[int] = None, yenile: bool = False) -> dict[str, Any]:
        await run_in_threadpool(ctx, request)
        if yil is None:
            await run_in_threadpool(call, logo)
        year = yil or this_year()
        return await run_in_threadpool(markets, year, yenile)

    @app.get(f"{P}/marketplaces/stock-risk")
    async def eticaret_stock_risk(request: Request, yil: Optional[int] = None, yenile: bool = False) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        if yil is None:
            await run_in_threadpool(call, logo)
        year = yil or this_year()
        items = await run_in_threadpool(stock_risk, engine, tenant, year, yenile)
        return {"items": items, "yil": year, "kesim": firms_cache["cut"].isoformat() if firms_cache.get("cut") else None,
                "esikGun": settings()["stockoutDays"], "satisAyi": settings()["salesMonths"]}

    @app.get(f"{P}/marketplaces/{{code}}/books")
    async def eticaret_marketplace_books(code: str, request: Request, yil: Optional[int] = None) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        if not src.code_ok(code):
            raise HTTPException(status_code=400, detail={"code": "ETICARET", "message": "Cari kodu geçersiz."})

        def load() -> dict[str, Any]:
            run, firms, cut = logo()
            year = yil or (cut.year if cut else date.today().year)
            this, _ = E.marketplace_windows(year, cut)
            rows = src.read_marketplace_books(run, firms, code, *this)
            books = E.marketplace_books(rows, E.items_by_code(engine, tenant, [r["stok"] for r in rows]), settings())
            return {"kod": code, "yil": year, "donem": {"bas": this[0].isoformat(), "son": (this[1] - timedelta(days=1)).isoformat()},
                    "kesim": cut.isoformat() if cut else None,
                    "items": books, "total": len(books)}
        return await run_in_threadpool(call, load)

    # ------------------------------------------------------------------ içerik paketi

    @app.get(f"{P}/export/content-pack")
    def eticaret_content_pack(request: Request, keys: str = "", bicim: str = "xlsx") -> Response:
        engine, tenant, user, _ = ctx(request)
        wanted = [k for k in dict.fromkeys(src.ean_key(x) for x in keys.split(",")) if k]
        if not wanted:
            raise HTTPException(status_code=400, detail={"code": "ETICARET", "message": "En az bir kitap seçilmeli."})
        if bicim not in ("xlsx", "csv"):
            raise HTTPException(status_code=422, detail={"code": "ETICARET", "message": "Biçim xlsx ya da csv olmalı."})
        crm = call(src.read_crm_content, src.runner(deps["crm_file"]()), schema(), wanted)
        pack = E.content_pack_rows(wanted, crm, E.items_by_key(engine, tenant, wanted), conf("SEO_SITE_URL", "") or "")
        audit(engine, user, "run", "eticaret_export", None, "İçerik paketi", {"kitap": len(pack["rows"]), "eksik": len(pack["eksik"]), "bicim": bicim})
        stamp = date.today().isoformat()
        if bicim == "csv":
            return Response(E.content_pack_csv(pack), media_type="text/csv; charset=utf-8",
                            headers={"Content-Disposition": f'attachment; filename="icerik-paketi-{stamp}.csv"',
                                     "X-Eksik-Barkod": ",".join(pack["eksik"])[:2000]})
        return Response(E.content_pack_xlsx(pack), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="icerik-paketi-{stamp}.xlsx"'})

    return refresher


def _proposal_view(r: dict[str, Any]) -> dict[str, Any]:
    from semantic_bridge.seo_geo.store import iso, loads

    return {"id": r["id"], "productId": r["product_id"], "status": r["status"], "fields": loads(r["fields_json"], {}),
            "before": loads(r["before_json"], {}), "scoreBefore": r["score_before"], "scoreAfter": r["score_after"],
            "source": r["model"], "createdBy": r["created_by"], "createdAt": iso(r["created_at"]), "decidedBy": r["decided_by"],
            "decidedAt": iso(r["decided_at"]), "note": r["note"], "result": r["result"]}
