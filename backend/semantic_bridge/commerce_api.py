"""H3 E-ticaret müşteri yönetimi uçları: /api/v1/commerce/*.

Sayfa kapısı `access.RULES` (`sayfa:eticaret-musteri`, açıkça verilir). İşlem yetkileri (`FEATURE_RULES`): tetik yazma,
çalıştırma, önizleme ve kampanya açma `ozellik:eticaret.tetik`; eşikler ve T-soft okumasını yeniden başlatma
`ozellik:eticaret.ayar`; liste dosyası `ozellik:veri.disa-aktar`. Açıkça verilenler ucun içinde denetlenir: liste onayı
`ozellik:eticaret.liste-onay` (tetiği yazan ve listeyi çalıştıran onaylayamaz), dışa aktarım H2'nin
`ozellik:okur.liste-aktar`'ı, müşteri kartında kişisel veri H2'nin `ozellik:okur.kisisel-veri`'si. Her kişisel veri
görüntülemesi ve dışa aktarım `semantic_audit`'e yazılır.

Sözleşme ucu (M35, M42, M18): `GET /api/v1/commerce/segments/summary` — yalnız sayılar. M42 D2C sekmesi site özetini
`channels.d2c.register_site_provider(commerce.d2c_site)` ile alır.

Zamanlayıcı (`timas-commerce.timer`, 02:50 ve 07:20) yalnız `POST /api/v1/commerce/run-due`'yu çağırır: günde bir
T-soft okuması (pazar günleri tam tur), müşteri tablosu ve RFM, ürün görüntülenme farkı, kampanya sonuçları; 07:00'dan
sonra iç alıcılara sabah özeti (`COMMERCE_SUMMARY_RECIPIENTS`) ve okuma sorunu bildirimi (`COMMERCE_ADMIN_RECIPIENTS`).

Model çağrısı yalnız LLM kapısından: `rt.llm_for("commerce", NORMAL)` (`deps["llm"]`), kampanya sonucu yorumu. Modele
kişisel veri ve rakam gitmez. T-soft'a, CRM'e ve Logo'ya hiçbir şey yazılmaz; portal ileti göndermez.
"""
from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timezone
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import commerce as C
from semantic_bridge import commerce_kaynak as CK
from semantic_bridge import commerce_sources as src
from semantic_bridge import provenance as PV
from semantic_bridge import sorgu_yakala as Y
from semantic_bridge import readers as R
from semantic_bridge import readers_segments as seg
from semantic_bridge.hizli_bellek import Bellek

log = logging.getLogger("semantic.commerce.api")
P = "/api/v1/commerce"
F_TRIGGER = "ozellik:eticaret.tetik"
F_SETTINGS = "ozellik:eticaret.ayar"
F_APPROVE = "ozellik:eticaret.liste-onay"
F_LIST = "ozellik:okur.liste-aktar"
F_PERSONAL = "ozellik:okur.kisisel-veri"
F_EXPORT = "ozellik:veri.disa-aktar"
#: Tek tek T-soft'tan okunacak kişi bu sayıyı aşarsa üye listesi bir kez baştan sona okunur (istek sayısı düşsün).
BULK_MEMBER_READ = 50
#: Kitap adı haritaları (kitap dizini, sitedeki ürün adları) süreç belleğinde: bu kadar saniye taze, bayatsa hemen verilip
#: arkada yenilenir; bayat sınırını aşınca beklenir. Adlar gece eşitlemesiyle değişir.
NAMES_FRESH_SEC = 600
NAMES_STALE_SEC = 86400

_job: dict[str, Any] = {"running": False, "startedAt": None, "finishedAt": None, "error": None, "result": None, "full": False}
_job_lock = threading.Lock()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def register(app: Any, deps: dict[str, Any]) -> dict[str, Any]:
    """app.py'de bağlanır. `deps`: auth(request) → (engine, tenant, user, display) · require_caller(request) ·
    can(user, key) · audit(engine, user, action, kind, id, title, detail) · conf(key, default) · engine() · tenant() ·
    crm_file() · llm(priority) → LLM kapısı istemcisi ya da None · send_mail(subject, text, to) → durum."""
    auth, require_caller, can, audit, conf = (deps[k] for k in ("auth", "require_caller", "can", "audit", "conf"))

    C.FACTS.bind(deps["engine"], deps["tenant"])
    C.register_h2()
    try:
        from semantic_bridge.channels import d2c as d2c_mod

        d2c_mod.register_site_provider(C.d2c_site)
    except Exception as e:  # noqa: BLE001 — kanal modülü yoksa D2C bağlantısı kurulmaz, bu modül çalışır
        log.info("commerce: D2C bağlantısı kurulamadı: %s", e)

    def schema() -> str:
        return conf("CRM_SCHEMA", "Timas_MSCRM.dbo") or "Timas_MSCRM.dbo"

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        engine, tenant, user, display = auth(request)
        C.ensure(engine)
        return engine, tenant, user, display

    # Özetteki «en çok satanlar» adları: eskiden her istekte kitap dizininin tamamı ve (dizinde olmayan barkod varsa)
    # sitedeki bütün ürün kayıtları (JSON gövdesiyle) okunuyordu. Haritalar süreç belleğinde, kayıt başına ayrı.
    adlar = Bellek("commerce.kitap-adlari", taze=NAMES_FRESH_SEC, bayat=NAMES_STALE_SEC, en_cok=16)

    def names_for(engine: Any, tenant: str) -> C.NamesFn:
        def h1() -> dict[str, str]:
            return adlar.al((tenant, "dizin"), lambda: C.name_map_h1(engine, tenant))

        def site() -> dict[str, str]:
            return adlar.al((tenant, "site"), lambda: C.name_map_site(engine, tenant))
        return lambda barcodes: C.book_names(engine, tenant, barcodes, h1=h1, site=site)

    def warm_names(engine: Any, tenant: str) -> None:
        """Zamanlayıcı turunda (eşitlemeden sonra) adlar yeniden okunur; ekranı ilk açan beklemez. Hata turu durdurmaz."""
        try:
            adlar.al((tenant, "dizin"), lambda: C.name_map_h1(engine, tenant), zorla=True)
            adlar.al((tenant, "site"), lambda: C.name_map_site(engine, tenant), zorla=True)
        except Exception as e:  # noqa: BLE001
            log.info("commerce: kitap adları hazırlanamadı: %s", e)

    def st(engine: Any, tenant: str) -> dict[str, Any]:
        return C.settings(engine, tenant, conf)

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except C.CommerceError as e:
            raise HTTPException(status_code=e.status, detail={"code": "COMMERCE", "message": str(e)}) from e
        except R.ReadersError as e:
            raise HTTPException(status_code=e.status, detail={"code": "COMMERCE", "message": str(e)}) from e
        except src.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "COMMERCE_SOURCE", "message": str(e)}) from e

    def need(user: str, key: str, what: str) -> None:
        if not can(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def llm() -> Any:
        try:
            from semantic_layer.runtime.llm_queue import NORMAL
            return deps["llm"](NORMAL)
        except Exception:  # noqa: BLE001 — model tanımlı değil
            return None

    def crm_reader() -> Callable[[list[tuple[str, str]]], dict[tuple[str, str], dict[str, Any]]]:
        from semantic_bridge import readers_sources as rsrc

        return lambda keys: rsrc.read_personal(rsrc.runner(deps["crm_file"]()), schema(), keys)

    def site_reader() -> Callable[[list[Any]], dict[str, Optional[dict[str, Any]]]]:
        """Müşteri satırı → T-soft'taki güncel ad/e-posta/telefon/izin (yalnız o an; saklanmaz). Kimlik ve e-posta özeti
        tutmayan kayıt dönmez."""
        def read(rows: list[Any]) -> dict[str, Optional[dict[str, Any]]]:
            key = R.salt()
            f = src.fields(conf)
            client = src.tsoft()
            out: dict[str, Optional[dict[str, Any]]] = {}
            members = [r for r in rows if r.member_ref]
            bulk: dict[str, dict[str, Any]] = {}
            if len(members) > BULK_MEMBER_READ:
                path = conf("COMMERCE_TSOFT_MEMBER_PATH", "customer/get") or "customer/get"
                want = {r.member_ref for r in members}
                for page in src.pages(client, path, {}):
                    for row in page:
                        _, mid = src.pick(row, f["member_id"])
                        if str(mid or "").strip() in want:
                            bulk[str(mid).strip()] = row
            for r in rows:
                if r.member_ref and r.member_ref in bulk:
                    row = bulk[r.member_ref]
                    _, email = src.pick(row, f["email"])
                    if r.email_hash and R.email_key(email, key) != r.email_hash:
                        out[r.customer_key] = None
                        continue
                    _, phone = src.pick(row, f["phone"])
                    _, name = src.pick(row, f["name"])
                    out[r.customer_key] = {"ad": name, "eposta": R.norm_email(email), "cep": R.norm_phone(phone),
                                           "izin": {ch: src.truthy(src.pick(row, f[role])[1])
                                                    for ch, role in (("email", "consent_email"), ("sms", "consent_sms"))}}
                    continue
                out[r.customer_key] = src.read_person(client, conf, f, member_ref=None if len(members) > BULK_MEMBER_READ else r.member_ref,
                                                      order_no=r.last_order_no, expect_email_hash=r.email_hash, key=key)
            return out
        return read

    # ------------------------------------------------------------------ okuma turu

    def run_sync(engine: Any, tenant: str, full: bool) -> dict[str, Any]:
        try:
            res = C.sync(engine, tenant, src.tsoft(), conf, full=full)
        except Exception as e:  # noqa: BLE001 — hata tazelik kaydına düşer; ekran ve sabah özeti gösterir
            C.record_error(engine, tenant, str(e))
            raise
        if res.get("full"):
            C.meta_set(engine, tenant, "full", {"at": res["okAt"]})
        return res

    def start_refresh(engine: Any, tenant: str, full: bool) -> bool:
        with _job_lock:
            if _job["running"]:
                return False
            _job.update(running=True, startedAt=_iso_now(), finishedAt=None, error=None, result=None, full=full)

        def work() -> None:
            try:
                res = run_sync(engine, tenant, full)
                with _job_lock:
                    _job.update(result={k: res.get(k) for k in ("orders", "customers", "members", "moves", "seconds")})
            except Exception as e:  # noqa: BLE001
                log.warning("commerce: okuma turu düştü: %s", e)
                with _job_lock:
                    _job.update(error=str(e)[:400])
            finally:
                with _job_lock:
                    _job.update(running=False, finishedAt=_iso_now())

        threading.Thread(target=work, name="commerce-sync", daemon=True).start()
        return True

    # ------------------------------------------------------------------ genel

    @app.get(P + "/meta")
    def commerce_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        s = st(engine, tenant)
        rcfg = R.settings()
        with _job_lock:
            job = dict(_job)
        with Y.yakala(engine) as q:
            fresh = C.freshness(engine, tenant, s)
        out = {
            "me": {"username": user, "display": display, "canTrigger": can(user, F_TRIGGER), "canSettings": can(user, F_SETTINGS),
                   "canApprove": can(user, F_APPROVE), "canList": can(user, F_LIST) and can(user, F_EXPORT),
                   "canPersonal": can(user, F_PERSONAL)},
            "segments": C.SEGMENT_LABELS, "kinds": C.KINDS, "runStatuses": C.RUN_STATUS, "channels": R.CHANNEL_LABELS,
            "excludeLabels": seg.EXCLUDE_LABELS,
            "settings": {k: s[k] for k in C.SCREEN_DEFAULTS}, "settingLabels": C.SCREEN_LABELS,
            "exportEnabled": rcfg["exportEnabled"], "requireKvkk": rcfg["requireKvkk"], "okSources": rcfg["okSources"],
            "freshness": fresh, "job": job, "modelVar": llm() is not None,
            "tsoftConfigured": _tsoft_configured(),
        }
        return PV.bagla(out, lambda: CK.for_meta(engine, tenant, out, q))

    def _tsoft_configured() -> bool:
        try:
            return bool(src.tsoft().configured())
        except Exception:  # noqa: BLE001
            return False

    @app.get(P + "/overview")
    def commerce_overview(request: Request, period: str = "dun") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        s = st(engine, tenant)
        with Y.yakala(engine) as q:
            out = call(C.overview, engine, tenant, s, period, names=names_for(engine, tenant))
        return PV.bagla(out, lambda: CK.for_overview(engine, tenant, out, q))

    @app.get(P + "/status")
    def commerce_status(request: Request) -> dict[str, Any]:
        ctx(request)
        with _job_lock:
            return dict(_job)

    @app.post(P + "/refresh", status_code=202)
    def commerce_refresh(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        call(R.salt)
        full = bool((body or {}).get("full"))
        started = start_refresh(engine, tenant, full)
        if started:
            audit(engine, user, "run", "commerce_sync", tenant, "Site siparişleri yeniden okundu" + (" (tam tur)" if full else ""))
        with _job_lock:
            return {**_job, "started": started}

    @app.get(P + "/mine")
    def commerce_mine(request: Request) -> dict[str, Any]:
        """Kampüs zili: onayınızı bekleyen tetik listesi ve okuma sorunu (yalnız sayı)."""
        engine, tenant, user, _ = ctx(request)
        fr = C.freshness(engine, tenant, st(engine, tenant))
        return {"listsAwaiting": C.pending_runs(engine, tenant, user) if can(user, F_APPROVE) else 0,
                "sourceProblem": fr["error"] or ("Site siparişleri güncel değil." if fr["stale"] and fr["okAt"] else None)}

    # ------------------------------------------------------------------ müşteriler (RFM, liste, kart)

    @app.get(P + "/customers/rfm")
    def commerce_rfm(request: Request, days: int = 30) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        s = st(engine, tenant)
        with Y.yakala(engine) as q:
            out = call(C.rfm, engine, tenant, s, None, days)
        return PV.bagla(out, lambda: CK.for_rfm(engine, tenant, out, q))

    @app.get(P + "/customers/moves")
    def commerce_moves(request: Request, days: int = 30) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        with Y.yakala(engine) as q:
            out = C.moves(engine, tenant, days)
        return PV.bagla(out, lambda: CK.for_moves(engine, tenant, out, q))

    @app.get(P + "/customers")
    def commerce_customers(request: Request, segment: str = "", page: int = 0, sort: str = "son") -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        with Y.yakala(engine) as q:
            out = call(C.customers, engine, tenant, segment, page, 50, sort)
        return PV.bagla(out, lambda: CK.for_customers(engine, tenant, out, q))

    @app.get(P + "/customers/{key}")
    async def commerce_customer(key: str, request: Request, kisisel: bool = False) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        with Y.yakala(engine) as q:
            out = await run_in_threadpool(call, C.customer_card, engine, tenant, key)
        out = PV.bagla(out, lambda: CK.for_customer(engine, tenant, out, q))
        out["kisisel"] = None
        if kisisel:
            need(user, F_PERSONAL, "Kişisel veriyi görme yetkisi")
            row = await run_in_threadpool(call, C.customer_row, engine, tenant, key)
            live = await run_in_threadpool(call, site_reader(), [row])
            p = live.get(key)
            out["kisisel"] = {"ad": p.get("ad"), "eposta": p.get("eposta"), "cep": p.get("cep")} if p else {"bulunamadi": True}
            audit(engine, user, "view", "commerce_personal", C._mask(key), "Site müşterisinin kişisel verisi görüntülendi",
                  {"bulundu": bool(p)})
        return out

    # ------------------------------------------------------------------ ürün hunisi

    @app.get(P + "/products/funnel")
    def commerce_funnel(request: Request, days: int = 30, page: int = 0, zayif: bool = False) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        s = st(engine, tenant)
        with Y.yakala(engine) as q:
            out = call(C.funnel, engine, tenant, s, days, page, 100, zayif)
        return PV.bagla(out, lambda: CK.for_funnel(engine, tenant, out, q))

    # ------------------------------------------------------------------ tetikler

    @app.get(P + "/triggers/new-books")
    def commerce_new_books(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        s = st(engine, tenant)
        with Y.yakala(engine) as q:
            out = C.new_books(engine, tenant, s)
        return PV.bagla(out, lambda: CK.for_new_books(engine, tenant, out, q))

    @app.get(P + "/triggers")
    def commerce_triggers(request: Request, arsiv: bool = False) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        with Y.yakala(engine) as q:
            out = {"items": C.list_triggers(engine, tenant, arsiv)}
        return PV.bagla(out, lambda: CK.for_triggers(engine, tenant, out, q))

    @app.post(P + "/triggers", status_code=201)
    def commerce_trigger_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        t = call(C.create_trigger, engine, tenant, user, body or {}, st(engine, tenant))
        audit(engine, user, "create", "commerce_trigger", t["id"], t["name"], {"tur": t["kind"], "parametre": t["params"]})
        return t

    @app.patch(P + "/triggers/{tid}")
    def commerce_trigger_update(tid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        t, diff = call(C.update_trigger, engine, tenant, tid, user, body or {})
        if diff:
            audit(engine, user, "update", "commerce_trigger", tid, t["name"], diff)
        return t

    @app.post(P + "/triggers/{tid}/preview")
    async def commerce_trigger_preview(tid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        s = await run_in_threadpool(st, engine, tenant)
        with Y.yakala(engine) as q:
            out = await run_in_threadpool(call, C.preview, engine, tenant, tid, s)
        return PV.bagla(out, lambda: CK.for_run(engine, tenant, out, q))

    @app.post(P + "/triggers/{tid}/run", status_code=201)
    async def commerce_trigger_run(tid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        r = await run_in_threadpool(call, C.run_trigger, engine, tenant, tid, user, st(engine, tenant))
        audit(engine, user, "run", "commerce_run", r["id"], r["triggerName"],
              {k: r[k] for k in ("candidates", "reachable", "target", "control")})
        return r

    # ------------------------------------------------------------------ listeler (koşular)

    @app.get(P + "/runs")
    def commerce_runs(request: Request, durum: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        with Y.yakala(engine) as q:
            out = C.list_runs(engine, tenant, durum, page)
        return PV.bagla(out, lambda: CK.for_runs(engine, tenant, out, q))

    @app.get(P + "/runs/{rid}")
    def commerce_run(rid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        with Y.yakala(engine) as q:
            out = C._run_view(call(C.run_row, engine, tenant, rid))
        return PV.bagla(out, lambda: CK.for_run(engine, tenant, out, q))

    @app.post(P + "/runs/{rid}/approve")
    def commerce_run_approve(rid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_APPROVE, "Tetik listesi onayı")
        r = call(C.decide_run, engine, tenant, rid, user, True, (body or {}).get("note"))
        audit(engine, user, "approve", "commerce_run", rid, r["triggerName"], {"hedef": r["target"], "kontrol": r["control"]})
        return r

    @app.post(P + "/runs/{rid}/reject")
    def commerce_run_reject(rid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_APPROVE, "Tetik listesi onayı")
        r = call(C.decide_run, engine, tenant, rid, user, False, (body or {}).get("note"))
        audit(engine, user, "reject", "commerce_run", rid, r["triggerName"], {"not": r["decisionNote"]})
        return r

    @app.post(P + "/runs/{rid}/export")
    async def commerce_run_export(rid: str, body: dict[str, Any], request: Request) -> Response:
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        need(user, F_LIST, "Liste dışa aktarımı")
        s = st(engine, tenant)
        name, data, rec = await run_in_threadpool(call, C.export_run, engine, tenant, rid, user, (body or {}).get("purpose") or "",
                                                  crm_reader(), site_reader(), None, s["falseIsRet"])
        audit(engine, user, "export", "commerce_list", rid, f"E-ticaret tetik listesi dışa aktarıldı: {rec['count']} kişi",
              {"amac": (body or {}).get("purpose"), "disarida": rec["excluded"], "kayit": rec["id"]})
        return Response(content=data, media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store",
                                 "X-Readers-Count": str(rec["count"]), "X-Readers-Excluded": str(rec["excludedTotal"])})

    # ------------------------------------------------------------------ kampanyalar

    @app.get(P + "/campaigns")
    def commerce_campaigns(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        with Y.yakala(engine) as q:
            out = {"items": C.list_campaigns(engine, tenant)}
        return PV.bagla(out, lambda: CK.for_campaigns(engine, tenant, out, q))

    @app.post(P + "/campaigns", status_code=201)
    def commerce_campaign_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        cp = call(C.create_campaign, engine, tenant, user, body or {}, st(engine, tenant))
        audit(engine, user, "create", "commerce_campaign", cp["id"], cp["name"], {"liste": cp["runId"], "baslangic": cp["start"],
                                                                                   "bitis": cp["end"]})
        return cp

    @app.get(P + "/campaigns/{cid}")
    def commerce_campaign(cid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        s = st(engine, tenant)
        with Y.yakala(engine) as q:
            out = call(C.campaign, engine, tenant, cid, s)
        return PV.bagla(out, lambda: CK.for_campaign(engine, tenant, out, q))

    @app.post(P + "/campaigns/{cid}/comment")
    async def commerce_campaign_comment(cid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        return await run_in_threadpool(call, C.comment_campaign, engine, tenant, cid, llm(), st(engine, tenant))

    # ------------------------------------------------------------------ ayarlar

    @app.get(P + "/settings")
    def commerce_settings(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        s = st(engine, tenant)
        return {"values": {k: s[k] for k in C.SCREEN_DEFAULTS}, "labels": C.SCREEN_LABELS, "defaults": C.SCREEN_DEFAULTS,
                "limits": {k: list(v) for k, v in C._LIMITS.items()}}

    @app.put(P + "/settings")
    def commerce_settings_put(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        s, diff = call(C.update_settings, engine, tenant, user, body or {}, conf)
        if diff:
            audit(engine, user, "update", "commerce_settings", tenant, "E-ticaret müşteri eşikleri", diff)
        return {"values": {k: s[k] for k in C.SCREEN_DEFAULTS}}

    # ------------------------------------------------------------------ sözleşme

    @app.get(P + "/segments/summary")
    def commerce_segments_summary(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        with Y.yakala(engine) as q:
            out = C.segments_summary(engine, tenant)
        return PV.bagla(out, lambda: CK.for_segments_summary(engine, tenant, out, q))

    # ------------------------------------------------------------------ zamanlayıcı

    @app.post(P + "/run-due")
    async def commerce_run_due(request: Request, full: Optional[bool] = None, summary: Optional[bool] = None) -> dict[str, Any]:
        """Günde bir okuma (pazar tam tur), kampanya sonuçları, 07:00 sonrası sabah özeti. Tekrar çağrılırsa yapılmış işi
        yinelemez; `full`/`summary` ile elle zorlanır."""
        require_caller(request)
        engine, tenant = deps["engine"](), deps["tenant"]()
        C.ensure(engine)
        s = st(engine, tenant)
        if not s["enabled"]:
            return {"skipped": "COMMERCE_ENABLED kapalı"}
        d = C.due(engine, tenant)
        out: dict[str, Any] = {"due": d}
        if d["sync"] or full or d["full"]:
            try:
                res = await run_in_threadpool(run_sync, engine, tenant, bool(full) or d["full"])
                out["sync"] = {k: res.get(k) for k in ("orders", "customers", "members", "moves", "missing", "seconds", "full")}
            except Exception as e:  # noqa: BLE001
                out["syncError"] = str(e)[:400]
                if s["adminTo"]:
                    out["adminMail"] = deps["send_mail"]("E-ticaret müşteri: site siparişleri okunamadı",
                                                         f"T-soft okuması başarısız:\n{str(e)[:1000]}", s["adminTo"])
        out["results"] = await run_in_threadpool(C.refresh_results, engine, tenant, s)
        await run_in_threadpool(warm_names, engine, tenant)
        if (d["summary"] or summary) and C.has_data(engine, tenant):
            ov = await run_in_threadpool(lambda: C.overview(engine, tenant, s, "dun", names=names_for(engine, tenant)))
            if s["summaryTo"]:
                link = (conf("ALERT_LINK", "") or "").split("/uyarilar")[0]
                status = deps["send_mail"]("Site siparişleri — sabah özeti", C.summary_text(ov, C.pending_runs(engine, tenant), link),
                                           s["summaryTo"])
                out["summary"] = status
                if status == "sent":
                    C.meta_set(engine, tenant, "summarySent", date.today().isoformat())
            else:
                out["summary"] = "alici_yok"
        return out

    return {"facts": C.FACTS}
