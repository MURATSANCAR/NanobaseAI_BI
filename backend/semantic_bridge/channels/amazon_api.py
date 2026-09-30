"""M41 Amazon ve yurtdışı uçları: /api/v1/channels/amazon/* (M42 kanal paketinin altında; `channels.register` bağlar).

Sayfa kapısı `access.RULES`: konsinye `sayfa:amazon-konsinye`; yurtdışı, haklar, parametreler ve pazar kartları
`sayfa:amazon-yurtdisi`; taslaklar `sayfa:amazon-taslaklar`; açılış ve Amazon kitap listesi `sayfa:amazon`. İşlem
kapısı `FEATURE_RULES`: taslak ve pazar kartı açma `ozellik:amazon.taslak` (model harcar), cariyi eşleme listesine
ekleme `ozellik:kanal.eslesme`, Excel `ozellik:veri.disa-aktar`. Açıkça verilen, ucun içinde: `ozellik:amazon.parametre`
(finans parametreleri) ve `ozellik:amazon.pazar-karar` (kart kararı; hazırlayan karar veremez).

Hiçbir uç Amazon hesabına, CRM'e ya da Logo'ya yazmaz; Amazon API'sine istek gönderilmez (kullanıcı kararı 2026-09-28).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge.channels import amazon as A
from semantic_bridge import provenance as PV
from semantic_bridge import sorgu_yakala as Y
from semantic_bridge.channels import kaynak_pazaryeri as KP
from semantic_bridge.channels import mapping as M
from semantic_bridge.channels import platform_common as PC
from semantic_bridge.channels import report as RP
from semantic_bridge.channels import scorecard as SC
from semantic_bridge.channels import sources as src
from semantic_bridge.channels import store as S
from semantic_bridge.channels.amazon_client import AmazonClient

log = logging.getLogger("semantic.channels.amazon.api")

R = "/api/v1/channels/amazon"
PAGES = {"amazon": "sayfa:amazon", "konsinye": "sayfa:amazon-konsinye", "yurtdisi": "sayfa:amazon-yurtdisi",
         "taslaklar": "sayfa:amazon-taslaklar", "mutabakat": "sayfa:amazon-mutabakat"}
F_DRAFT = "ozellik:amazon.taslak"
F_PARAM = "ozellik:amazon.parametre"
F_DECIDE = "ozellik:amazon.pazar-karar"
F_MAP = "ozellik:kanal.eslesme"
F_EXPORT = "ozellik:veri.disa-aktar"
EXPORTS = {"konsinye": "konsinye", "yurtdisi": "yurtdisi", "yurtdisi-kitaplar": "yurtdisi", "haklar": "yurtdisi", "kitaplar": "amazon"}


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None], can: Callable[[str, str], bool]) -> dict[str, Any]:
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod

    job = PC.Job("amazon-refresh")

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
        A.ensure(r.store.engine)
        admin_mod.ensure(r.store.engine)
        return r.store.engine, r.settings.tenant_id, user, display

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except A.AmazonError as e:
            raise HTTPException(status_code=e.status, detail={"code": "AMAZON", "message": str(e)}) from e
        except SC.ChannelError as e:
            raise HTTPException(status_code=e.status, detail={"code": "AMAZON", "message": str(e)}) from e
        except (M.MappingError, ValueError) as e:
            raise HTTPException(status_code=400, detail={"code": "AMAZON", "message": str(e)}) from e
        except src.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "AMAZON_SOURCE", "message": str(e)}) from e

    def need(user: str, key: str, what: str) -> None:
        if not can(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def llm() -> Any:
        try:
            return rt().llm_for("amazon")
        except Exception:  # noqa: BLE001
            return None

    def schema() -> str:
        return conf("CRM_SCHEMA") or "Timas_MSCRM.dbo"

    def refresh_fn(engine, tenant) -> Callable[[Callable[[str], None]], Any]:
        return lambda step: A.refresh(engine, tenant, rt().settings.connection_file, crm_file(), schema(), conf, step)

    def wholesale(engine, tenant) -> dict[str, Any]:
        codes = PC.approved_codes(engine, tenant, A.PLATFORM)
        if not codes and not any(v == A.PLATFORM for v in M.kanal_map(engine, tenant).values()):
            return {"eslendi": False, "neden": "Logo'da Amazon'a bağlanmış cari yok (Cari eşleme). Amazon adlı cariler aşağıda."}
        try:
            d = SC.channel(engine, tenant, A.PLATFORM)
        except SC.ChannelError as e:
            return {"eslendi": True, "cariler": codes, "neden": str(e)}
        return {"eslendi": True, "cariler": codes, "period": d["period"], "donem": {k: d["donem"].get(k) for k in (
                    "netCiro", "netAdet", "satisCiro", "iadeCiro", "satisAdet", "iadeAdet", "iadeOrani", "iskontoOrani")},
                "degisim": d["degisim"], "cariSatirlari": [{"grup": c["grup"], "ad": c["ad"], "netCiro": c["donem"]["netCiro"],
                                                           "netAdet": c["donem"]["netAdet"], "crmSiparis": c["crmSiparis"]} for c in d["cariler"]],
                "crmSiparisGun": d["crmSiparisGun"]}

    # ------------------------------------------------------------------ genel

    @app.get(R + "/meta")
    def am_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        s = A.settings(conf)
        with Y.yakala(engine) as q:
            read = S.meta_get(engine, tenant, "amazon:read")
        out = {"draftTypes": A.DRAFT_TYPES, "decisions": A.DECISIONS, "api": AmazonClient(conf).status(), "job": job.status(),
                "read": read,
                "settings": {k: s[k] for k in ("yurtdisiKodlari", "yil", "konsinyeYil", "konsinyeTipi", "cariAdlari")},
                "modelReady": getattr(rt(), "llm", None) is not None,
                "me": {"username": user, "display": display, "canDraft": can(user, F_DRAFT), "canParam": can(user, F_PARAM),
                       "canDecide": can(user, F_DECIDE), "canMap": can(user, F_MAP), "canExport": can(user, F_EXPORT),
                       "canImport": can(user, "ozellik:kanal.yukle"), "pages": {k: can(user, v) for k, v in PAGES.items()}}}
        return PV.bagla(out, lambda: KP.am_list("okuma")(engine, tenant, out, q))

    @app.get(R + "/status")
    def am_status(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {"job": job.status(), "read": S.meta_get(engine, tenant, "amazon:read")}

    @app.post(R + "/refresh")
    def am_refresh(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        started = job.start(refresh_fn(engine, tenant))
        admin_mod.audit(engine, user, "run", "amazon_read", None, "Amazon ve yurtdışı verisi yenilendi", {"started": started})
        return {"started": started, "job": job.status()}

    @app.post(R + "/run-due")
    def am_run_due(request: Request) -> dict[str, Any]:
        """Zamanlayıcı (gece 04:30): konsinye, yurtdışı, döviz ve CRM hak/sipariş önbelleği. Ağa (Amazon'a) çıkmaz."""
        require_caller(request)
        r = rt()
        engine, tenant = r.store.engine, r.settings.tenant_id
        A.ensure(engine)
        admin_mod.ensure(engine)
        if job.running():
            return {"skipped": "başka bir okuma sürüyor"}
        return job.run(refresh_fn(engine, tenant))

    @app.get(R + "/overview")
    async def am_overview(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        with Y.yakala(engine) as q:
            out = await run_in_threadpool(lambda: call(A.overview, engine, tenant, wholesale(engine, tenant)))
        return PV.bagla(out, lambda: KP.am_overview(engine, tenant, out, q))

    @app.get(R + "/accounts")
    def am_accounts(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        with Y.yakala(engine) as q:
            m = S.meta_get(engine, tenant, "amazon:cariler")
            out = {"adayCariler": PC.candidates_view(engine, tenant, A.PLATFORM, m.get("items") or []), "desenler": m.get("desenler"),
                   "okundu": m.get("_at"), "onayli": PC.approved_codes(engine, tenant, A.PLATFORM), "toptan": wholesale(engine, tenant)}
        return PV.bagla(out, lambda: KP.am_list("cari")(engine, tenant, out, q))

    @app.post(R + "/cariler/ekle")
    def am_add_account(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        code = str(body.get("kod") or "").strip()
        card = next((c for c in (S.meta_get(engine, tenant, "amazon:cariler").get("items") or []) if c["cari_kodu"] == code), None)
        if card is None:
            raise HTTPException(status_code=404, detail={"code": "AMAZON", "message": "Cari, adla bulunan Amazon carileri arasında yok."})
        out = call(PC.add_to_mapping, engine, tenant, A.PLATFORM, card, "M41")
        admin_mod.audit(engine, user, "update", "channel_account", code, card.get("unvan") or code,
                        {"platform": A.PLATFORM, "durum": out.get("durum"), "modul": "M41"})
        return out

    @app.get(R + "/books")
    async def am_books(request: Request, yil: Optional[int] = None, ay: Optional[int] = None, q: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        with Y.yakala(engine) as yq:
            out = SC.redact(await run_in_threadpool(call, SC.books, engine, tenant, A.PLATFORM, yil, ay, q, "netCiro", page))
        return PV.bagla(out, lambda: KP.am_list("kitap")(engine, tenant, out, yq))

    # ------------------------------------------------------------------ konsinye ve yurtdışı

    def billed_this_year(engine, tenant) -> Optional[dict[str, float]]:
        """Aynı yıl Amazon'a faturalanan net adet (M42 kitap önbelleği); okunmadıysa None."""
        m = S.meta_get(engine, tenant, "amazon:read")
        end = m.get("veriSonu")
        if not end:
            return None
        try:
            return SC.sell_in_books(engine, tenant, A.PLATFORM, SC.months_between(f"{end[:4]}-01-01", end))
        except Exception:  # noqa: BLE001
            return None

    @app.get(R + "/consignment")
    async def am_consignment(request: Request, q: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        with Y.yakala(engine) as yq:
            billed = await run_in_threadpool(billed_this_year, engine, tenant)
            out = await run_in_threadpool(call, A.consignment, engine, tenant, q, page, billed)
        return PV.bagla(out, lambda: KP.am_list("konsinye")(engine, tenant, out, yq))

    @app.get(R + "/international")
    async def am_international(request: Request, yil: Optional[int] = None, ulke: str = "") -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        with Y.yakala(engine) as yq:
            out = await run_in_threadpool(call, A.international, engine, tenant, yil, ulke)
        return PV.bagla(out, lambda: KP.am_list("yurtdisi")(engine, tenant, out, yq))

    @app.get(R + "/international/books")
    async def am_intl_books(request: Request, yil: Optional[int] = None, ulke: str = "", q: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        with Y.yakala(engine) as yq:
            out = await run_in_threadpool(call, A.intl_books, engine, tenant, yil, ulke, q, page)
        return PV.bagla(out, lambda: KP.am_list("yurtdisiKitap")(engine, tenant, out, yq))

    @app.get(R + "/rights")
    async def am_rights(request: Request, q: str = "", ulke: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        with Y.yakala(engine) as yq:
            out = await run_in_threadpool(call, A.rights, engine, tenant, q, ulke, page)
        return PV.bagla(out, lambda: KP.am_list("hak")(engine, tenant, out, yq))

    # ------------------------------------------------------------------ parametreler

    @app.get(R + "/params")
    def am_params(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        with Y.yakala(engine) as q:
            out = {"items": A.params(engine, tenant)}
        return PV.bagla(out, lambda: KP.am_list("param")(engine, tenant, out, q))

    @app.put(R + "/params/{pazar}")
    def am_params_set(pazar: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_PARAM, "Uluslararası fiyat parametreleri")
        out, diff = call(A.set_params, engine, tenant, user, pazar, body)
        admin_mod.audit(engine, user, "update", "intl_params", out["pazar"], out["ad"], diff)
        return out

    @app.delete(R + "/params/{pazar}")
    def am_params_delete(pazar: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_PARAM, "Uluslararası fiyat parametreleri")
        A.delete_params(engine, tenant, pazar)
        admin_mod.audit(engine, user, "delete", "intl_params", pazar.upper(), pazar.upper(), None)
        return {"ok": True}

    # ------------------------------------------------------------------ taslaklar

    @app.get(R + "/drafts")
    def am_drafts(request: Request, stok: str = "", pazar: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        with Y.yakala(engine) as q:
            out = A.drafts(engine, tenant, stok, pazar, page)
        return PV.bagla(out, lambda: KP.am_list("taslak")(engine, tenant, out, q))

    @app.post(R + "/drafts", status_code=201)
    async def am_draft_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        code = PC.cell(body.get("stokKodu"), 60)
        if not code:
            raise HTTPException(status_code=400, detail={"code": "AMAZON", "message": "Stok kodu gerekli."})
        card = await run_in_threadpool(call, lambda: A.read_book_card(src.runner(crm_file()), schema(), code))
        out = await run_in_threadpool(call, A.create_draft, engine, tenant, user, llm(), card, body)
        admin_mod.audit(engine, user, "create", "intl_draft", out["id"], f"{out['kitap'] or code} · {out['pazar']} · {out['turAd']}",
                        {"dusen": len(out["dusen"])})
        return out

    @app.put(R + "/drafts/{did}")
    def am_draft_state(did: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(A.set_draft_state, engine, tenant, user, did, str(body.get("durum") or ""))
        admin_mod.audit(engine, user, "update", "intl_draft", did, out["kitap"] or out["stokKodu"], {"durum": out["durum"]})
        return out

    # ------------------------------------------------------------------ pazar kartları

    @app.get(R + "/market-cards")
    def am_cards(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        with Y.yakala(engine) as q:
            out = {"items": A.cards(engine, tenant), "decisions": A.DECISIONS}
        return PV.bagla(out, lambda: KP.am_list("kart")(engine, tenant, out, q))

    @app.post(R + "/market-cards", status_code=201)
    async def am_card_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        out = await run_in_threadpool(call, A.create_card, engine, tenant, user, llm(), body)
        admin_mod.audit(engine, user, "create", "intl_market_card", out["id"], f"Pazar değerlendirmesi {out['pazar']}", None)
        return out

    @app.post(R + "/market-cards/{cid}/decision")
    def am_card_decide(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_DECIDE, "Yeni pazar kararı")
        note = PC.cell(body.get("not"), 1000) or None
        out = call(A.decide_card, engine, tenant, user, cid, str(body.get("karar") or ""), note)
        admin_mod.audit(engine, user, "approve" if out["karar"] == "girilsin" else "reject", "intl_market_card", cid,
                        f"Pazar değerlendirmesi {out['pazar']}", {"karar": out["karar"], "not": note})
        return out

    # ------------------------------------------------------------------ dışa aktarım

    @app.get(R + "/export/{liste}.xlsx")
    async def am_export(liste: str, request: Request, yil: Optional[int] = None, ulke: str = "", q: str = "") -> Response:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        page = EXPORTS.get(liste)
        if not page:
            raise HTTPException(status_code=404, detail={"code": "AMAZON", "message": "Bilinmeyen liste."})
        need(user, PAGES[page], "Bu liste")

        def everything(fn, *a) -> list[dict[str, Any]]:
            first = call(fn, *a, 0)
            items = list(first["items"])
            for k in range(1, (first["total"] + first["pageSize"] - 1) // first["pageSize"]):
                items += call(fn, *a, k)["items"]
            return items

        if liste == "konsinye":
            billed = await run_in_threadpool(billed_this_year, engine, tenant)
            rows = await run_in_threadpool(everything, lambda e, t, qq, p: A.consignment(e, t, qq, p, billed), engine, tenant, q)
            for r in rows:
                r["cariler"] = ", ".join(r["cariler"])
            cols = [("stokKodu", "Stok kodu"), ("ad", "Kitap"), ("sevk", "Faturalanmamış sevk (adet)"), ("iade", "Faturalanmamış iade (adet)"),
                    ("kalan", "Konsinyede kalan"), ("faturalanan", "Bu yıl faturalanan net adet"), ("ilk", "İlk irsaliye"), ("son", "Son irsaliye"),
                    ("cariler", "Cariler")]
            note = "Amazon konsinye: faturalanmamış satış irsaliyesi − iade irsaliyesi (Logo)"
        elif liste == "yurtdisi":
            d = await run_in_threadpool(call, A.international, engine, tenant, yil, ulke)
            rows = d["items"]
            cols = [("cari", "Cari"), ("unvan", "Unvan"), ("ulke", "Ülke"), ("doviz", "Döviz"), ("netCiro", "Net ciro (TL)"),
                    ("dovizNet", "Net (döviz)"), ("netAdet", "Net adet"), ("fatura", "Fatura"),
                    ("gecenYilAyniDonem", "Geçen yıl aynı dönem net ciro (TL)"), ("gecenYil", "Geçen yıl tamamı net ciro (TL)")]
            note = f"Yurtdışı faturalı satış {d['yil']} · kanal kodları {', '.join(d['kodlar'] or [])}"
        elif liste == "yurtdisi-kitaplar":
            rows = await run_in_threadpool(everything, A.intl_books, engine, tenant, yil, ulke, q)
            for r in rows:
                r["ulkeler"] = ", ".join(f"{u['ulke']} {u['netAdet']:g}" for u in r["ulkeler"])
            cols = [("stokKodu", "Stok kodu"), ("ad", "Kitap"), ("netAdet", "Net adet"), ("netCiro", "Net ciro (TL)"), ("ulkeler", "Ülkeler")]
            note = "Yurtdışı kanal: kitap × ülke"
        elif liste == "haklar":
            rows = await run_in_threadpool(everything, A.rights, engine, tenant, q, ulke)
            for r in rows:
                r["ulkeler"] = ", ".join(r["ulkeler"])
                r["firmalar"] = ", ".join(r["firmalar"])
                r["sozlesmeNo"] = ", ".join(s["no"] or "" for s in r["sozlesmeler"])
            cols = [("stokKodu", "Stok kodu"), ("kitap", "Kitap"), ("ulkeler", "Hak satılan ülke"), ("firmalar", "Yayınevi / ajans"),
                    ("sozlesmeNo", "Sözleşme"), ("yurtdisiNetAdet", "Yurtdışı net adet")]
            note = "Satılmış yabancı haklar (CRM Telif Satış sözleşmeleri)"
        else:
            rows = await run_in_threadpool(everything, lambda e, t, qq, p: SC.books(e, t, A.PLATFORM, yil, None, qq, "netCiro", p), engine, tenant, q)
            rows = SC.redact(rows)
            cols = [("stokKodu", "Stok kodu"), ("ad", "Kitap"), ("satisAdet", "Kanala satış (adet)"), ("iadeAdet", "İade (adet)"),
                    ("netAdet", "Net adet"), ("netCiro", "Net ciro")]
            note = "Amazon carileri: kitap bazında faturalı satış ve iade (M42 karnesi)"
        data = RP.xlsx(liste, cols, rows, note)
        admin_mod.audit(engine, user, "run", "amazon_export", liste, f"Amazon listesi: {liste}", {"satir": len(rows)})
        return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="amazon-{liste}.xlsx"'})

    return {"job": job}
