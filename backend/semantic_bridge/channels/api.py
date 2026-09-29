"""M42 kanal uçları: /api/v1/channels/* (M40/M41 kendi alt yollarını aynı öneke ekler: /channels/trendyol/*, /amazon/*).

Sayfa kapısı `access.RULES`: karne ve kanal detayı `sayfa:kanallar`, matris `sayfa:kanal-matris`, D2C `sayfa:kanal-d2c`,
eşleme `sayfa:kanal-eslesme`. İşlem kapısı `FEATURE_RULES`: eşleme yazma `ozellik:kanal.eslesme`, Excel yükleme
`ozellik:kanal.yukle`, öneri taslağı `ozellik:kanal.oneri-yaz`, dışa aktarma `ozellik:veri.disa-aktar`. Açıkça verilen
yetkiler ucun içinde: `ozellik:kanal.marj` (maliyet, brüt kâr, marj, simülasyon, ek kanal maliyeti — yoksa alanlar
cevaptan çıkarılır) ve `ozellik:kanal.oneri-karar` (öneri onayı/reddi; öneren onaylayamaz).

Hiçbir uç CRM'e, Logo'ya, T-soft'a ya da bir pazar yerine yazmaz. Zamanlayıcılar yalnız `POST run-due`'yu çağırır.
"""
from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import provenance as PV
from semantic_bridge import sorgu_yakala as Y
from semantic_bridge.channels import d2c as D
from semantic_bridge.channels import imports as I
from semantic_bridge.channels import kaynak as K
from semantic_bridge.channels import mapping as M
from semantic_bridge.channels import refresh as RF
from semantic_bridge.channels import report as RP
from semantic_bridge.channels import scorecard as SC
from semantic_bridge.channels import sources as src
from semantic_bridge.channels import store as S

log = logging.getLogger("semantic.channels.api")

R = "/api/v1/channels"
PAGES = {"kanallar": "sayfa:kanallar", "matris": "sayfa:kanal-matris", "d2c": "sayfa:kanal-d2c", "eslesme": "sayfa:kanal-eslesme"}
F_MARGIN = "ozellik:kanal.marj"
F_DECIDE = "ozellik:kanal.oneri-karar"
F_MAP = "ozellik:kanal.eslesme"
F_SUGGEST = "ozellik:kanal.oneri-yaz"
F_IMPORT = "ozellik:kanal.yukle"
F_EXPORT = "ozellik:veri.disa-aktar"
SUGGESTION_TYPES = {"iskonto": "İskonto önerisi", "stok-payi": "Stok payı önerisi", "d2c-set": "D2C'ye özel set",
                    "d2c-sadakat": "D2C sadakat önerisi"}


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None], can: Callable[[str, str], bool]):
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod
    from semantic_bridge.budget_api import _send_mail
    from semantic_layer.runtime.llm_queue import BATCH

    def conf(key: str) -> str:
        return admin_mod.conf(key) or ""

    crm_file = lambda: os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")  # noqa: E731
    refresher = RF.Refresher(lambda: rt().store.engine, lambda: rt().settings.tenant_id, lambda: rt().settings.connection_file,
                             crm_file, lambda: conf("CRM_SCHEMA") or "Timas_MSCRM.dbo", conf)

    def st() -> dict[str, Any]:
        return M.settings(conf)

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        require_caller(request)
        try:
            user, display = board_mod.session_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        r = rt()
        S.ensure(r.store.engine)
        admin_mod.ensure(r.store.engine)
        return r.store.engine, r.settings.tenant_id, user, display

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except SC.ChannelError as e:
            raise HTTPException(status_code=e.status, detail={"code": "CHANNELS", "message": str(e)}) from e
        except (M.MappingError, I.ImportError_) as e:
            raise HTTPException(status_code=400, detail={"code": "CHANNELS", "message": str(e)}) from e
        except src.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "CHANNELS_SOURCE", "message": str(e)}) from e

    def need(user: str, key: str, what: str) -> None:
        if not can(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def view(user: str, obj: Any) -> Any:
        return obj if can(user, F_MARGIN) else SC.redact(obj)

    def unit_costs() -> Optional[Callable[[list[str]], dict[str, dict[str, Any]]]]:
        # M9 birim maliyet sağlayıcısı (`pricing/cost_provider.py`, app.state.pricing_costs) kurulumda varsa kullanılır.
        prov = getattr(app.state, "pricing_costs", None)
        return prov.unit_costs if prov is not None and hasattr(prov, "unit_costs") else None

    def m46(engine, tenant) -> Callable[[int], dict[str, Any]]:
        from semantic_bridge import budget as B

        def read(year: int) -> dict[str, Any]:
            B.ensure(engine)
            return B.approved_targets(engine, tenant, year, with_actuals=False)
        return read

    def llm(batch: bool = False) -> Any:
        try:
            return rt().llm_for("kanal", BATCH if batch else None)
        except Exception:  # noqa: BLE001
            return None

    def start_if_scope_grew(engine, tenant) -> bool:
        years = RF.missing_scope(engine, tenant, st(), refresher.needed_years(engine, tenant))
        return refresher.start(years) if years else False

    # ------------------------------------------------------------------ genel

    @app.get(R + "/meta")
    def ch_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        s = st()
        with Y.yakala(engine) as q:
            out = meta_body(engine, tenant, user, display, s)
        return PV.bagla(out, lambda: K.for_meta(engine, tenant, out, q))

    def meta_body(engine, tenant: str, user: str, display: str, s: dict[str, Any]) -> dict[str, Any]:
        status = refresher.status()
        end = RF.data_end(engine, tenant)
        years = sorted(int(y) for y in status["years"])
        return {
            "platforms": [{"key": k, "label": v} for k, v in M.PLATFORMS.items()],
            "cardPlatforms": M.CARD_PLATFORMS, "d2c": M.D2C, "unmapped": M.UNMAPPED,
            "suggestionTypes": SUGGESTION_TYPES, "months": SC.AY, "years": years,
            "defaultYear": end.year if end else None, "data": status,
            "missingScope": RF.missing_scope(engine, tenant, s, years),
            "settings": {"specodes": s["specodes"], "returnThreshold": s["returnThreshold"], "discountRise": s["discountRise"],
                         "orderDays": s["orderDays"], "d2cMinAdet": s["d2cMinAdet"], "d2cIndex": s["d2cIndex"],
                         "recipients": len(s["recipients"])},
            "extraCosts": M.extra_costs(engine, tenant) if can(user, F_MARGIN) else {},
            "alerts": S.meta_get(engine, tenant, "alerts"),
            "crmOrders": {k: v for k, v in S.meta_get(engine, tenant, "crm_orders").items() if k in ("days", "byType", "_at")},
            "siteConnected": RF.h3_connected(engine),
            "modelReady": getattr(rt(), "llm", None) is not None,
            "me": {"username": user, "display": display, "canMargin": can(user, F_MARGIN), "canMap": can(user, F_MAP),
                   "canDecide": can(user, F_DECIDE), "canSuggest": can(user, F_SUGGEST), "canImport": can(user, F_IMPORT),
                   "canExport": can(user, F_EXPORT), "pages": {k: can(user, v) for k, v in PAGES.items()}},
        }

    @app.get(R + "/status")
    def ch_status(request: Request) -> dict[str, Any]:
        ctx(request)
        return refresher.status()

    @app.post(R + "/refresh")
    def ch_refresh(request: Request, yil: Optional[int] = None) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        years = refresher.needed_years(engine, tenant, [yil] if yil else [])
        started = refresher.start(years)
        admin_mod.audit(engine, user, "run", "channel_read", None, "Kanal verisi yenilendi", {"started": started, "years": years})
        return {"started": started, **refresher.status()}

    @app.post(R + "/run-due")
    def ch_run_due(request: Request, tur: str = "gece", zorla: bool = False) -> dict[str, Any]:
        """Zamanlayıcı. `?tur=gece`: bayat yılları okur, eşleme adaylarını üretir. `?tur=rapor`: pazartesi haftalık uyarı,
        ayın 2'si aylık karne (zorla=1 ikisini de şimdi yapar)."""
        require_caller(request)
        r = rt()
        engine, tenant = r.store.engine, r.settings.tenant_id
        S.ensure(engine)
        admin_mod.ensure(engine)
        s = st()
        out: dict[str, Any] = {"tur": tur}
        if tur != "rapor":
            years = refresher.due(engine, tenant)
            out["years"] = years
            out["read"] = {"skipped": "başka bir okuma sürüyor"} if refresher.running() else (refresher.run(years) if years else {"skipped": "taze"})
            out["mapping"] = M.propose(engine, tenant, llm(batch=True), s)
        else:
            today = date.today()
            try:
                if zorla or today.weekday() == 0:
                    out["weekly"] = RP.weekly(engine, tenant, s, _send_mail, today, force=zorla)
                if zorla or today.day == 2:
                    out["monthly"] = RP.monthly(engine, tenant, s, llm(batch=True), _send_mail, today, force=zorla)
            except SC.ChannelError as e:
                out["error"] = str(e)
        return out

    # ------------------------------------------------------------------ karne ve kanal

    @app.get(R + "/scorecard")
    async def ch_scorecard(request: Request, yil: Optional[int] = None, ay: Optional[int] = None) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        with Y.yakala(engine) as q:
            out = view(user, await run_in_threadpool(call, SC.scorecard, engine, tenant, yil, ay, dagitim=True))
        return PV.bagla(out, lambda: K.for_scorecard(engine, tenant, out, q))

    @app.get(R + "/channel/{platform}")
    async def ch_channel(platform: str, request: Request, yil: Optional[int] = None, ay: Optional[int] = None) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        uc = unit_costs() if can(user, F_MARGIN) else None
        with Y.yakala(engine) as q:
            out = await run_in_threadpool(call, SC.channel, engine, tenant, platform, yil, ay, uc)
            out["imports"] = I.list_imports(engine, tenant, platform)
        out["m9Bagli"] = uc is not None
        out = view(user, out)
        return PV.bagla(out, lambda: K.for_channel(engine, tenant, out, q))

    @app.get(R + "/channel/{platform}/books")
    async def ch_books(platform: str, request: Request, yil: Optional[int] = None, ay: Optional[int] = None, q: str = "",
                       sort: str = "netCiro", page: int = 0) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        if sort == "marj" and not can(user, F_MARGIN):
            sort = "netCiro"
        with Y.yakala(engine) as yq:
            out = view(user, await run_in_threadpool(call, SC.books, engine, tenant, platform, yil, ay, q, sort, page))
        return PV.bagla(out, lambda: K.for_books(engine, tenant, out, yq))

    @app.get(R + "/channel/{platform}/returns")
    async def ch_returns(platform: str, request: Request, yil: Optional[int] = None, ay: Optional[int] = None,
                         aylar: int = 3, page: int = 0) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        with Y.yakala(engine) as q:
            out = view(user, await run_in_threadpool(call, SC.returns, engine, tenant, platform, yil, ay, aylar, page))
        return PV.bagla(out, lambda: K.for_returns(engine, tenant, out, q))

    @app.get(R + "/matrix")
    async def ch_matrix(request: Request, yil: Optional[int] = None, ay: Optional[int] = None, q: str = "", page: int = 0,
                        sort: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        with Y.yakala(engine) as yq:
            out = await run_in_threadpool(call, SC.matrix, engine, tenant, yil, ay, q, page, sort)
        return PV.bagla(out, lambda: K.for_matrix(engine, tenant, out, yq))

    @app.get(R + "/targets")
    async def ch_targets(request: Request, yil: Optional[int] = None) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        with Y.yakala(engine) as q:
            out = view(user, await run_in_threadpool(call, SC.targets, engine, tenant, yil, m46(engine, tenant)))
        return PV.bagla(out, lambda: K.for_targets(engine, tenant, out, q))

    @app.post(R + "/simulate")
    async def ch_simulate(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        need(user, F_MARGIN, "Kanal marjı ve simülasyon")
        with Y.yakala(engine) as q:
            out = await run_in_threadpool(call, SC.simulate, engine, tenant, body)
        if body.get("yorum"):
            model = llm()
            out["yorum"] = await run_in_threadpool(_comment, model, out) if model is not None else None
        return PV.bagla(out, lambda: K.for_simulate(engine, tenant, out, q))

    @app.put(R + "/settings/ek-maliyet/{platform}")
    def ch_extra_cost(platform: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_MARGIN, "Kanal marjı")
        if platform not in M.CARD_PLATFORMS:
            raise HTTPException(status_code=404, detail={"code": "CHANNELS", "message": "Bilinmeyen platform."})
        v = body.get("oran")
        if v is not None:
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail={"code": "CHANNELS", "message": "Oran sayı olmalı."}) from None
            if not 0 <= v < 1:
                raise HTTPException(status_code=400, detail={"code": "CHANNELS", "message": "Oran 0 ile 1 arasında olmalı (ör. 0,12)."})
        S.setting_set(engine, tenant, f"ek-maliyet:{platform}", None if v is None else str(v), user)
        admin_mod.audit(engine, user, "update", "channel_setting", f"ek-maliyet:{platform}", M.PLATFORMS[platform], {"oran": v})
        return {"platform": platform, "oran": v}

    # ------------------------------------------------------------------ eşleme

    @app.get(R + "/accounts")
    def ch_accounts(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        with Y.yakala(engine) as q:
            items = S.accounts(engine, tenant)
            cards = S.meta_get(engine, tenant, "cards")
        counts: dict[str, int] = {}
        for a in items:
            counts[a["durum"]] = counts.get(a["durum"], 0) + 1
        out = {"items": items, "counts": counts, "cards": cards, "specodes": st()["specodes"]}
        return PV.bagla(out, lambda: K.for_accounts(engine, tenant, out, q))

    @app.get(R + "/accounts/kanal-kodlari")
    def ch_kanal_codes(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        with Y.yakala(engine) as q:
            kmap = M.kanal_map(engine, tenant)
            end = RF.data_end(engine, tenant)
            year = end.year if end else None
            rows = SC._months(engine, tenant, S.KANAL_MONTHS, [year]) if year else []
        tot: dict[str, float] = {}
        for r in rows:
            tot[r.kanal] = tot.get(r.kanal, 0.0) + float(r.satis_ciro or 0) - float(r.iade_ciro or 0)
        items = [{"kod": k, "netCiro": round(v, 2), "platform": kmap.get(k), "eticaret": k in st()["specodes"]}
                 for k, v in sorted(tot.items(), key=lambda kv: -kv[1])]
        for k, v in kmap.items():
            if k not in tot:
                items.append({"kod": k, "netCiro": 0.0, "platform": v, "eticaret": k in st()["specodes"]})
        out = {"yil": year, "items": items}
        return PV.bagla(out, lambda: K.for_kanal_codes(engine, tenant, out, q))

    @app.put(R + "/accounts/kanal-kodlari/{kod}")
    def ch_kanal_code_set(kod: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        call(M.set_kanal, engine, tenant, user, kod, body.get("platform") or None)
        admin_mod.audit(engine, user, "update", "channel_account", f"kanal:{kod}", f"Kanal kodu {kod}", {"platform": body.get("platform")})
        return {"kod": kod, "platform": body.get("platform") or None, "okumaBasladi": start_if_scope_grew(engine, tenant)}

    @app.get(R + "/accounts/bolgeler")
    def ch_regions(request: Request, yil: Optional[int] = None) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        import sqlalchemy as sa

        with Y.yakala(engine) as yq:
            rmap = M.region_map(engine, tenant)
            labels = S.meta_get(engine, tenant, "target_labels")
            with engine.connect() as c:
                rows = c.execute(sa.select(S.TARGETS).where(S.TARGETS.c.tenant_id == tenant)).all()
        out = []
        seen = set()
        for r in sorted(rows, key=lambda x: (-x.yil, -x.toplam)):
            if yil and r.yil != yil:
                continue
            if r.bolge in seen:
                continue
            seen.add(r.bolge)
            name = r.bolge_ad or (labels.get("regions") or {}).get(r.bolge) or r.bolge
            out.append({"kod": r.bolge, "ad": name, "yil": r.yil, "yillik": r.toplam, "satir": r.satir,
                        "aylikToplam": round(sum(float(x or 0) for x in S.jload(r.aylar_json, [])), 2),
                        "platform": rmap.get(r.bolge), "aday": M.region_candidate(name, st()["hints"])})
        for k, v in (labels.get("regions") or {}).items():
            if k not in seen:
                out.append({"kod": k, "ad": v, "yil": None, "yillik": 0.0, "platform": rmap.get(k), "aday": M.region_candidate(v, st()["hints"])})
        res = {"items": out, "crmError": (S.meta_get(engine, tenant, "crm") or {}).get("error")}
        return PV.bagla(res, lambda: K.for_regions(engine, tenant, res, yq))

    @app.put(R + "/accounts/bolgeler/{kod}")
    def ch_region_set(kod: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        call(M.set_region, engine, tenant, user, kod, body.get("platform") or None)
        admin_mod.audit(engine, user, "update", "channel_account", f"bolge:{kod}", f"Hedef bölgesi {kod}", {"platform": body.get("platform")})
        return {"kod": kod, "platform": body.get("platform") or None}

    @app.post(R + "/accounts/propose")
    async def ch_propose(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        only = [str(x) for x in (body.get("cariler") or []) if str(x).strip()] or None
        out = await run_in_threadpool(M.propose, engine, tenant, llm(), st(), budget_sec=int(body.get("sure") or 120),
                                      only=only, force=bool(only))
        admin_mod.audit(engine, user, "run", "channel_account", None, "Eşleme adayları", out)
        return out

    @app.put(R + "/accounts/{cari:path}")
    def ch_account_set(cari: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out, diff = call(M.decide, engine, tenant, user, cari, body)
        admin_mod.audit(engine, user, "approve" if out["durum"] == "onayli" else "update", "channel_account", cari,
                        out.get("unvan") or cari, diff)
        return {**out, "okumaBasladi": start_if_scope_grew(engine, tenant)}

    # ------------------------------------------------------------------ D2C

    @app.get(R + "/d2c")
    async def ch_d2c(request: Request, yil: Optional[int] = None, ay: Optional[int] = None) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        with Y.yakala(engine) as q:
            out = view(user, await run_in_threadpool(call, D.overview, engine, tenant, st(), yil, ay))
        return PV.bagla(out, lambda: K.for_d2c(engine, tenant, out, q))

    @app.post(R + "/d2c/suggest", status_code=201)
    async def ch_d2c_suggest(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        codes = [str(x) for x in (body.get("kitaplar") or []) if str(x).strip()]
        out = await run_in_threadpool(call, D.suggest_set, engine, tenant, user, st(), codes, llm(), body.get("yil"), body.get("ay"))
        admin_mod.audit(engine, user, "create", "channel_suggestion", out["id"], out["baslik"], {"tur": out["tur"]})
        return out

    # ------------------------------------------------------------------ öneriler

    @app.get(R + "/suggestions")
    def ch_suggestions(request: Request, platform: str = "", tur: str = "", durum: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        with Y.yakala(engine) as q:
            out = {"items": view(user, S.suggestions(engine, tenant, platform=platform, tur=tur, durum=durum)), "types": SUGGESTION_TYPES}
        return PV.bagla(out, lambda: K.for_suggestions(engine, tenant, out, q))

    @app.post(R + "/suggestions", status_code=201)
    async def ch_suggestion_add(body: dict[str, Any], request: Request) -> dict[str, Any]:
        """İskonto önerisi: simülasyon sunucuda yeniden hesaplanır, taslak olarak kaydedilir (hiçbir yere gönderilmez)."""
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        if str(body.get("tur") or "iskonto") != "iskonto":
            raise HTTPException(status_code=400, detail={"code": "CHANNELS", "message": "Bu uçtan yalnız iskonto önerisi açılır."})
        need(user, F_MARGIN, "Kanal marjı ve simülasyon")
        sim = await run_in_threadpool(call, SC.simulate, engine, tenant, body)
        note = str(body.get("not") or "").strip()[:1000] or None
        title = f"{sim['label']}: iskonto {sim['iskontoPuan']:+.1f} puan".replace(".", ",")
        out = S.suggestion_add(engine, tenant, user, sim["platform"], "iskonto", title, {"simulasyon": sim, "not": note},
                               str(body.get("yorum") or "").strip()[:2000] or None)
        admin_mod.audit(engine, user, "create", "channel_suggestion", out["id"], title, {"tur": "iskonto", "puan": sim["iskontoPuan"]})
        return out

    @app.post(R + "/suggestions/{sid}/decision")
    def ch_suggestion_decide(sid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_DECIDE, "Kanal önerisi kararı")
        cur = S.suggestion_get(engine, tenant, sid)
        if cur is None:
            raise HTTPException(status_code=404, detail={"code": "CHANNELS", "message": "Öneri bulunamadı."})
        karar = str(body.get("karar") or "")
        if karar not in ("onayli", "red"):
            raise HTTPException(status_code=400, detail={"code": "CHANNELS", "message": "Karar «onayli» ya da «red» olmalı."})
        if cur["durum"] != "taslak":
            raise HTTPException(status_code=409, detail={"code": "CHANNELS", "message": "Öneri zaten karara bağlandı."})
        if cur["olusturan"].lower() == user.lower():
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Öneriyi hazırlayan kişi onaylayamaz."})
        note = str(body.get("not") or "").strip()[:1000] or None
        if karar == "red" and not note:
            raise HTTPException(status_code=400, detail={"code": "CHANNELS", "message": "Ret gerekçesi yazılmalı."})
        S.suggestion_decide(engine, tenant, sid, user, karar, note)
        admin_mod.audit(engine, user, "approve" if karar == "onayli" else "reject", "channel_suggestion", sid, cur["baslik"], {"not": note})
        return view(user, S.suggestion_get(engine, tenant, sid))

    # ------------------------------------------------------------------ panel dosyası

    @app.get(R + "/imports")
    def ch_imports(request: Request, platform: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        with Y.yakala(engine) as q:
            out = {"items": I.list_imports(engine, tenant, platform)}
        return PV.bagla(out, lambda: K.for_imports(engine, tenant, out, q))

    @app.post(R + "/imports", status_code=201)
    async def ch_import(request: Request, platform: str = "", filename: str = "", donem_bas: str = "", donem_bit: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        if int(request.headers.get("content-length") or 0) > I.MAX_MB * 1024 * 1024:
            raise HTTPException(413, detail={"code": "CHANNELS", "message": f"Dosya {I.MAX_MB} MB sınırını aşıyor."})
        data = await request.body()
        out = await run_in_threadpool(call, I.store_import, engine, tenant, user, platform, filename, data, donem_bas, donem_bit)
        admin_mod.audit(engine, user, "upload", "channel_import", out["id"], out["dosya"] or "panel dosyası",
                        {"platform": platform, "satir": out["satir"], "eslesen": out["eslesen"],
                         "kisiselOlabilir": out["kolonlar"].get("kisiselOlabilir")})
        return out

    @app.get(R + "/imports/{iid}")
    async def ch_import_get(iid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        with Y.yakala(engine) as q:
            head = call(I.get, engine, tenant, iid)
            end = RF.data_end(engine, tenant)
            bas = head["donemBas"] or (f"{end.year}-01-01" if end else None)
            bit = head["donemBit"] or (end.isoformat() if end else None)
            months = SC.months_between(bas, bit) if bas and bit else []
            sell_in = await run_in_threadpool(SC.sell_in_books, engine, tenant, head["platform"], months) if months else {}
            out = await run_in_threadpool(call, I.sell_through, engine, tenant, iid, sell_in)
        out["kanalaSatisAylari"] = [f"{y}-{m:02d}" for y, m in months]
        return PV.bagla(out, lambda: K.for_import(engine, tenant, out, q))

    @app.delete(R + "/imports/{iid}")
    def ch_import_delete(iid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(I.delete, engine, tenant, iid)
        admin_mod.audit(engine, user, "delete", "channel_import", iid, out["dosya"] or "panel dosyası", {"satir": out["satir"]})
        return {"ok": True}

    # ------------------------------------------------------------------ dışa aktarım

    @app.get(R + "/export/{liste}.xlsx")
    async def ch_export(liste: str, request: Request, yil: Optional[int] = None, ay: Optional[int] = None, platform: str = "",
                        q: str = "", aylar: int = 3) -> Response:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        page = {"karne": "kanallar", "kitaplar": "kanallar", "iadeler": "kanallar", "matris": "matris", "eslesme": "eslesme"}.get(liste)
        if not page:
            raise HTTPException(status_code=404, detail={"code": "CHANNELS", "message": "Bilinmeyen liste."})
        need(user, PAGES[page], "Bu liste")
        margin = can(user, F_MARGIN)
        big = 10 ** 9
        if liste == "karne":
            d = await run_in_threadpool(call, SC.scorecard, engine, tenant, yil, ay)
            rows = [{"label": x["label"], **x["donem"], "degisim": x["degisim"], "paySirket": x["paySirket"]} for x in d["platforms"]]
            cols = [("label", "Platform"), ("netCiro", "Net ciro"), ("degisim", "Geçen yıla göre"), ("netAdet", "Net adet"),
                    ("iskontoOrani", "İskonto oranı"), ("iadeOrani", "İade oranı"), ("paySirket", "Şirket içindeki pay")]
            if margin:
                cols += [("brutKar", "Brüt kâr (maliyetli satırlar)"), ("marj", "Brüt marj"), ("iadeSonrasiMarj", "İade sonrası marj"),
                         ("maliyetsizSatir", "Maliyetsiz satır"), ("maliyetsizCiro", "Maliyetsiz ciro")]
            note = f"{d['period']['yil']} Ocak–{d['period']['ayAdi']} · kanala satış (sell-in) · Logo verisi {d['period']['veriSonu'] or '—'}"
        elif liste in ("kitaplar", "iadeler"):
            if liste == "kitaplar":
                d = await run_in_threadpool(call, SC.books, engine, tenant, platform, yil, ay, q, "netCiro", 0, big)
            else:
                d = await run_in_threadpool(call, SC.returns, engine, tenant, platform, yil, ay, aylar, 0, big)
            rows = d["items"]
            cols = [("stokKodu", "Stok kodu"), ("ad", "Kitap"), ("satisAdet", "Kanala satış (adet)"), ("iadeAdet", "İade (adet)"),
                    ("netAdet", "Net adet"), ("netCiro", "Net ciro"), ("iadeOrani", "İade oranı (adet)")]
            if margin:
                cols += [("brutKar", "Brüt kâr"), ("marj", "Brüt marj"), ("maliyetsizAdet", "Maliyetsiz adet")]
            note = f"{SC.platform_label(platform)} · {d['period']['yil']}"
        elif liste == "matris":
            d = await run_in_threadpool(call, SC.matrix, engine, tenant, yil, ay, q, 0, "", big)
            rows = [{"stokKodu": r["stokKodu"], "ad": r["ad"], "toplam": r["toplam"],
                     **{c["platform"]: (r["kanallar"].get(c["platform"]) or {}).get("net") for c in d["columns"]}} for r in d["items"]]
            cols = [("stokKodu", "Stok kodu"), ("ad", "Kitap"), ("toplam", "Toplam net adet")] + [(c["platform"], c["label"]) for c in d["columns"]]
            note = f"Kitap × kanal net adet (kanala satış − iade) · {d['period']['yil']} Ocak–{d['period']['ayAdi']}"
        else:
            rows = S.accounts(engine, tenant)
            for r in rows:
                r["platformAd"] = M.PLATFORMS.get(r["platform"] or "", "")
            cols = [("cariKodu", "Cari kodu"), ("unvan", "Logo unvanı"), ("kanal", "Kanal kodu"), ("crmAd", "CRM adı"),
                    ("platformAd", "Platform"), ("durum", "Durum"), ("yontem", "Yöntem"), ("olasilik", "Olasılık"),
                    ("onaylayan", "Onaylayan"), ("onayTarihi", "Onay tarihi")]
            note = "Cari ↔ platform eşlemesi (portal kaydı; CRM'e ve Logo'ya yazılmaz)"
        data = RP.xlsx(liste, cols, rows, note)
        admin_mod.audit(engine, user, "run", "channel_export", liste, f"Kanal listesi: {liste}", {"satir": len(rows)})
        return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="kanal-{liste}.xlsx"'})

    return {"refresher": refresher}


def _comment(model: Any, sim: dict[str, Any]) -> Optional[str]:
    """Simülasyonun 2–3 cümlelik yorumu; rakamlar hesaptan, modelin yazdığı rakamlı satır atılır."""
    import re

    prompt = ("Bir yayınevinin kanal iskontosu simülasyonunun sonucu aşağıda. Finans ekibi için 2–3 cümlelik yorum yaz: "
              "karar için neye bakmalı. Rakam, yüzde, tutar yazma; sonuç zaten tabloda.\n\n" + SC.facts_text(sim))
    try:
        text = (model.chat([{"role": "user", "content": prompt}], max_tokens=220, temperature=0.2) or "").strip()
    except Exception as e:  # noqa: BLE001
        log.warning("channels: simülasyon yorumu yazılamadı: %s", e)
        return None
    return re.sub(r"[^\n]*\d[^\n]*\n?", "", text).strip()[:1200] or None
