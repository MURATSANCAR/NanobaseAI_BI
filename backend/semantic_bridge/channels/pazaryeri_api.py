"""Aşama 0 (satış modeli tespiti) ve Aşama 1 (mutabakat + hakediş) uçları, iki platform için aynı sözleşme:
`/api/v1/channels/{trendyol|amazon}/model*` ve `/api/v1/channels/{trendyol|amazon}/mutabakat*`.

Sayfa kapısı (`access.RULES`): model uçları platformun özet sayfasında (`sayfa:trendyol`, `sayfa:amazon`); mutabakat ve
hakediş `sayfa:trendyol-mutabakat` / `sayfa:amazon-mutabakat`. İşlem kapısı (`FEATURE_RULES`): panel dosyası yükleme/silme
Trendyol'da `ozellik:trendyol.yukle`, Amazon'da `ozellik:amazon.yukle`; Excel `ozellik:veri.disa-aktar`.

Hiçbir uç pazar yerine, Logo'ya ya da CRM'e yazmaz; Logo/CRM yalnız SELECT ile okunur, platform API'sine istek gitmez.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import provenance as PV
from semantic_bridge import sorgu_yakala as Y
from semantic_bridge.channels import kaynak_mutabakat as KM
from semantic_bridge.channels import mutabakat as MU
from semantic_bridge.channels import pazaryeri_dosya as PD
from semantic_bridge.channels import pazaryeri_model as PM
from semantic_bridge.channels import platform_common as PC
from semantic_bridge.channels import report as RP
from semantic_bridge.channels import sources as src

log = logging.getLogger("semantic.channels.pazaryeri.api")

F_IMPORT = {"trendyol": "ozellik:trendyol.yukle", "amazon": "ozellik:amazon.yukle"}
F_EXPORT = "ozellik:veri.disa-aktar"
PAGE_RECON = {"trendyol": "sayfa:trendyol-mutabakat", "amazon": "sayfa:amazon-mutabakat"}


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None], can: Callable[[str, str], bool]) -> dict[str, Any]:
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod

    jobs = {(p, k): PC.Job(f"{p}-{k}") for p in PM.PLATFORMS for k in ("model", "mutabakat")}

    def conf(key: str) -> str:
        return admin_mod.conf(key) or ""

    crm_file = lambda: os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")  # noqa: E731

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        require_caller(request)
        try:
            user, display = board_mod.session_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        r = rt()
        MU.ensure(r.store.engine)
        admin_mod.ensure(r.store.engine)
        return r.store.engine, r.settings.tenant_id, user, display

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except MU.MutabakatError as e:
            raise HTTPException(status_code=e.status, detail={"code": "PAZARYERI", "message": str(e)}) from e
        except (PD.DosyaError, ValueError) as e:
            raise HTTPException(status_code=400, detail={"code": "PAZARYERI", "message": str(e)}) from e
        except src.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "PAZARYERI_SOURCE", "message": str(e)}) from e

    def model_fn(engine, tenant, platform):
        return lambda step: PM.refresh(engine, tenant, platform, rt().settings.connection_file, crm_file(),
                                       conf("CRM_SCHEMA") or "Timas_MSCRM.dbo", conf, step)

    def recon_fn(engine, tenant, platform):
        def go(step):
            try:
                return MU.refresh(engine, tenant, platform, rt().settings.connection_file, conf, step)
            except MU.MutabakatError as e:
                return {"ok": False, "error": str(e)}
        return go

    for platform in PM.PLATFORMS:
        _routes(app, platform, jobs, ctx, call, conf, can, admin_mod, model_fn, recon_fn)
    return {"jobs": jobs}


def _routes(app, platform: str, jobs, ctx, call, conf, can, admin_mod, model_fn, recon_fn) -> None:
    R = f"/api/v1/channels/{platform}"
    mjob, rjob = jobs[(platform, "model")], jobs[(platform, "mutabakat")]

    # ------------------------------------------------------------------ Aşama 0: satış modeli

    @app.get(R + "/model", name=f"{platform}_model")
    async def model_view(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)

        def build() -> dict[str, Any]:
            return PM.view(engine, tenant, platform, conf, MU.panel_evidence(engine, tenant, platform))

        with Y.yakala(engine) as q:
            out = await run_in_threadpool(call, build)
        out["job"] = mjob.status()
        return PV.bagla(out, lambda: KM.model(engine, tenant, platform, out, q))

    @app.post(R + "/model/refresh", name=f"{platform}_model_refresh")
    def model_refresh(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        started = mjob.start(model_fn(engine, tenant, platform))
        admin_mod.audit(engine, user, "run", "marketplace_model", platform, f"{platform}: satış modeli Logo'dan ölçüldü",
                        {"started": started})
        return {"started": started, "job": mjob.status()}

    @app.get(R + "/model/status", name=f"{platform}_model_status")
    def model_status(request: Request) -> dict[str, Any]:
        ctx(request)
        return {"job": mjob.status()}

    # ------------------------------------------------------------------ Aşama 1: mutabakat ve hakediş

    @app.get(R + "/mutabakat", name=f"{platform}_recon")
    async def recon_view(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = await run_in_threadpool(ctx, request)
        with Y.yakala(engine) as q:
            out = await run_in_threadpool(call, MU.overview, engine, tenant, platform, conf)
            out["dosyaTurleri"] = PD.TYPES[platform]
            out["dosyalar"] = await run_in_threadpool(PD.list_imports, engine, tenant, platform)
        out["job"] = rjob.status()
        out["me"] = {"username": user, "display": display, "canImport": can(user, F_IMPORT[platform]),
                     "canExport": can(user, F_EXPORT)}
        return PV.bagla(out, lambda: KM.mutabakat(engine, tenant, platform, out, q))

    @app.get(R + "/mutabakat/liste", name=f"{platform}_recon_items")
    async def recon_items(request: Request, tur: str = "", sinif: str = "", q: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        with Y.yakala(engine) as yq:
            out = await run_in_threadpool(call, MU.items, engine, tenant, platform, conf, tur, sinif, q, page)
        return PV.bagla(out, lambda: KM.mutabakat(engine, tenant, platform, out, yq))

    @app.get(R + "/mutabakat/hakedis", name=f"{platform}_recon_settlement")
    async def recon_settlement(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        with Y.yakala(engine) as q:
            out = await run_in_threadpool(call, MU.hakedis, engine, tenant, platform, conf)
        return PV.bagla(out, lambda: KM.hakedis(engine, tenant, platform, out, q))

    @app.post(R + "/mutabakat/refresh", name=f"{platform}_recon_refresh")
    def recon_refresh(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        started = rjob.start(recon_fn(engine, tenant, platform))
        admin_mod.audit(engine, user, "run", "marketplace_recon", platform, f"{platform}: mutabakat için Logo okundu",
                        {"started": started})
        return {"started": started, "job": rjob.status()}

    @app.get(R + "/mutabakat/status", name=f"{platform}_recon_status")
    def recon_status(request: Request) -> dict[str, Any]:
        ctx(request)
        return {"job": rjob.status()}

    @app.get(R + "/mutabakat/dosyalar", name=f"{platform}_recon_files")
    def recon_files(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        with Y.yakala(engine) as q:
            out = {"items": PD.list_imports(engine, tenant, platform), "types": PD.TYPES[platform]}
        return PV.bagla(out, lambda: KM.dosyalar(engine, tenant, platform, out, q))

    @app.post(R + "/mutabakat/dosyalar", status_code=201, name=f"{platform}_recon_upload")
    async def recon_upload(request: Request, tur: str = "", filename: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        if int(request.headers.get("content-length") or 0) > PD.MAX_MB * 1024 * 1024:
            raise HTTPException(413, detail={"code": "PAZARYERI", "message": f"Dosya {PD.MAX_MB} MB sınırını aşıyor."})
        data = await request.body()
        out = await run_in_threadpool(call, PD.store, engine, tenant, user, platform, tur, filename, data)
        admin_mod.audit(engine, user, "upload", "marketplace_file", out["id"], out["dosya"] or "panel dosyası",
                        {"platform": platform, "tur": tur, "satir": out["satir"],
                         "kisiselOlabilir": out["kolonlar"].get("kisiselOlabilir")})
        return out

    @app.delete(R + "/mutabakat/dosyalar/{iid}", name=f"{platform}_recon_delete")
    def recon_delete(iid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(PD.delete, engine, tenant, platform, iid)
        admin_mod.audit(engine, user, "delete", "marketplace_file", iid, out["dosya"] or "panel dosyası",
                        {"platform": platform, "tur": out["tur"], "satir": out["satir"]})
        return {"ok": True}

    @app.get(R + "/mutabakat/export/{liste}.xlsx", name=f"{platform}_recon_export")
    async def recon_export(liste: str, request: Request, tur: str = "", sinif: str = "", q: str = "") -> Response:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        if liste == "liste":
            r = await run_in_threadpool(call, MU.reconcile, engine, tenant, platform, conf)
            rows = []
            for x in r["items"]:
                if (tur and x["tur"] != tur) or (sinif and x["sinif"] != sinif):
                    continue
                inv = x["faturalar"]
                rows.append({**x, "turAd": MU.TURLER[x["tur"]], "sinifAd": MU.CLASSES[x["sinif"]],
                             "faturaTarihi": ", ".join(i["tarih"] or "" for i in inv), "faturaTuru": ", ".join(i["turAd"] for i in inv),
                             "cari": ", ".join(i["cari"] or "" for i in inv), "alan": ", ".join(i["alan"] or "" for i in inv)})
            cols = [("turAd", "Tür"), ("siparisNo", "Sipariş no"), ("tarih", "Panel tarihi"), ("durum", "Panel durumu"),
                    ("sinifAd", "Sonuç"), ("panelAdet", "Panel adet"), ("panelTutar", "Panel tutarı"), ("logoTutar", "Logo tutarı (KDV dahil)"),
                    ("fark", "Fark"), ("faturaTarihi", "Fatura tarihi"), ("faturaTuru", "Fatura türü"), ("cari", "Cari kodu"),
                    ("alan", "Eşleşen alan"), ("neden", "Not")]
            note = f"{platform}: panel ↔ Logo mutabakatı (yöntem: {r['yontem'] or '—'})"
        elif liste == "hakedis-faturasiz":
            h = await run_in_threadpool(call, MU.hakedis, engine, tenant, platform, conf)
            rows = h.get("logoFaturasiYok") or []
            cols = [("siparisNo", "Sipariş no"), ("satis", "Hakediş satış"), ("iade", "İade"), ("kesinti", "Kesinti"), ("net", "Net"),
                    ("mutabakat", "Mutabakat sonucu")]
            note = f"{platform}: hakedişte satışı olan, Logo faturası bulunmayan siparişler"
        else:
            raise HTTPException(status_code=404, detail={"code": "PAZARYERI", "message": "Bilinmeyen liste."})
        data = RP.xlsx(liste, cols, rows, note)
        admin_mod.audit(engine, user, "run", "marketplace_export", liste, f"{platform} mutabakat listesi: {liste}", {"satir": len(rows)})
        return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{platform}-{liste}.xlsx"'})
