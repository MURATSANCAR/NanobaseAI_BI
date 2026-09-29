"""M48 Sistem durumu uçları: /api/v1/it-ops/*.

Sayfa kapısı `access.RULES` (`sayfa:sistem-durumu`, açıkça verilir: «Herkes» rolüne ve «Bütün sayfalar»a girmez).
İşlem yetkileri de açıkça verilir ve burada denetlenir: «Şimdi dene» `ozellik:sistem.dene`, kök neden / değerlendirme
`ozellik:sistem.olay-kapat`, eşik ve alıcılar `ozellik:sistem.ayar`. Yönetici hepsini yapar.

Zamanlayıcı ve betik uçları (çerezsiz, `X-Semantic-Caller` jetonuyla): `run-due` (5 dk'lık tur), `watchdog` (köprü
bekçisi ve VM'deki iş kapsayıcısı iş sonucunu bildirir), `report-release` (kurulum betiği sürümü bildirir).
`banner` herkese açıktır ve yalnız kopuk halkanın adını söyler.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request

from semantic_bridge import ic_bildirim as IB
from semantic_bridge import it_ops as I
from semantic_bridge import it_ops_kaynak as IK
from semantic_bridge import provenance as P
from semantic_bridge import sorgu_izi as IZ
from semantic_bridge import it_ops_sources as S

log = logging.getLogger("semantic_bridge.it_ops.api")

SETTING_GROUP = "itops"


#: Bu köprü sürecinin açılış anı. Her turda `note_boot` ile kayda geçer; planlı yeniden başlatmanın çevresindeki
#: başarısız denemeler kopma sayılmaz (`it_ops.evaluate`).
BOOT_AT = datetime.now(timezone.utc)


def send_mail(notice: IB.Notice, to: list[str]) -> str:
    """İç bildirim şablonuyla (HTML + düz metin) gönderir."""
    return IB.send(notice, to)


def recipients(conf: Callable[[str, str], str], key: str = "ITOPS_RECIPIENTS") -> tuple[list[str], list[str]]:
    raw = conf(key, "") or ""
    if key != "ITOPS_RECIPIENTS" and not raw.strip():
        raw = conf("ITOPS_RECIPIENTS", "") or ""
    domains = conf("ITOPS_INTERNAL_DOMAINS", "") or conf("ALERT_RECIPIENT_DOMAINS", "") or ""
    return I.internal_recipients(raw, domains)


def run_tour(ctx: S.Ctx, datasource: str, *, source: str = "timer", rings: Optional[list[str]] = None,
             send: I.Sender = send_mail, collect: bool = True, digests: bool = True,
             now: Optional[datetime] = None, boot_at: Optional[datetime] = None) -> dict[str, Any]:
    """Bir denetim turu: açılış kaydı → halkalar → kayıt → olay aç/kapat → işler → bildirim → (zamanı geldiyse) özetler."""
    st = I.settings(ctx.conf)
    with I.run_lock:
        try:
            I.note_boot(ctx.engine, ctx.tenant, boot_at or BOOT_AT)
        except Exception as e:  # noqa: BLE001
            log.warning("itops: açılış kaydı yazılamadı: %s", e)
        results = S.run_rings(ctx, rings)
        for r in results:
            I.record_check(ctx.engine, ctx.tenant, r["ring"], r["ok"], latency_ms=r.get("latency_ms"),
                           data_end=r.get("data_end"), detail=r.get("detail") or "", source=source, at=now,
                           sql_text=r.get("sql"))
        changed = I.evaluate(ctx.engine, ctx.tenant, results, st, now=now)
        jobs = 0
        if collect:
            try:
                jobs += S.collect_timers(ctx)
            except Exception as e:  # noqa: BLE001
                log.warning("itops: zamanlayıcılar okunamadı: %s", e)
            jobs += S.collect_tables(ctx, datasource)
        to, rejected = recipients(ctx.conf)
        link = ctx.conf("ALERT_LINK", "") or ""
        sent = I.notify(ctx.engine, ctx.tenant, st, send, to, link=link, now=now)
        out: dict[str, Any] = {"checked": len(results), "ok": sum(1 for r in results if r["ok"]),
                               "failed": [r["ring"] for r in results if r["ok"] is False],
                               "opened": len(changed["opened"]), "closed": len(changed["closed"]), "jobs": jobs,
                               "notify": sent, "rejectedRecipients": rejected}
        if digests:
            n = now or I._now()
            due = I.due_digests(ctx.engine, ctx.tenant, st, n)
            if due["daily"]:
                failing = I.failing_jobs(ctx.engine, ctx.tenant, since=n - timedelta(hours=24))
                # Yalnız BT'nin yapabileceği (bağlantı/hesap/yetki) hata varken gider; uygulama hataları BT'ye iş değildir.
                failing = I.split_jobs(failing)[0] and failing
                res = (send(I.jobs_digest_notice(failing, n, link), to) if failing and to
                       else ("empty" if not failing else "no_recipient"))
                if res in ("sent", "empty"):
                    I.state_set(ctx.engine, ctx.tenant, "daily_sent", due["daily"])
                out["daily"] = res
            if due["weekly"]:
                wto, _ = recipients(ctx.conf, "ITOPS_WEEKLY_TO")
                notice = I.weekly_notice(ctx.engine, ctx.tenant, n, I.failing_jobs(ctx.engine, ctx.tenant), link)
                res = send(notice, wto) if wto else "no_recipient"
                if res == "sent":
                    I.state_set(ctx.engine, ctx.tenant, "weekly_sent", due["weekly"])
                out["weekly"] = res
    return out


def register(app, deps: dict[str, Any]):
    """deps: require_caller, can, audit, conf, engine(), tenant(), datasource(), logo_file(), crm_file(),
    llm(priority) → kapıdan geçen model ya da None, run_check(id)."""
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod
    from semantic_layer.runtime.llm_queue import BATCH

    require_caller: Callable[[Request], None] = deps["require_caller"]
    can: Callable[[str, str], bool] = deps["can"]
    audit = deps["audit"]
    conf = deps["conf"]

    def dbs() -> tuple[Optional[str], Optional[str]]:
        # Sorgu bilgisi: bağlantı dosyasından YALNIZ veritabanı adı (USE satırı için).
        return P.connection_database(deps["logo_file"]()), P.connection_database(deps["crm_file"]())

    def make_ctx() -> S.Ctx:
        engine = deps["engine"]()
        I.ensure(engine)
        admin_mod.ensure(engine)
        return S.Ctx(engine=engine, tenant=deps["tenant"](), conf=conf, logo_file=deps["logo_file"],
                     crm_file=deps["crm_file"], llm=lambda: deps["llm"](BATCH), run_check=deps.get("run_check"))

    def ctx(request: Request) -> tuple[Any, str, str]:
        require_caller(request)
        try:
            user, _display = board_mod.session_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        engine = deps["engine"]()
        I.ensure(engine)
        admin_mod.ensure(engine)
        return engine, deps["tenant"](), user

    def need(user: str, key: str, what: str) -> None:
        if not can(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except I.ItOpsError as e:
            raise HTTPException(status_code=e.status, detail={"code": "ITOPS", "message": str(e)}) from e

    def me(user: str) -> dict[str, Any]:
        return {"username": user, "canCheck": can(user, "ozellik:sistem.dene"),
                "canClose": can(user, "ozellik:sistem.olay-kapat"), "canSettings": can(user, "ozellik:sistem.ayar")}

    # ------------------------------------------------------------------ okuma

    @app.get("/api/v1/it-ops/status")
    def itops_status(request: Request) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        from semantic_bridge.alerts import email_status

        st = I.settings(conf)
        with IZ.izle(engine) as ran:
            out = I.status(engine, tenant, st)
            jobs = I.list_jobs(engine, tenant)
            rel = I.list_releases(engine, tenant, size=1)
        to, rejected = recipients(conf)
        res = {**out, "me": me(user), "email": {**email_status(), "recipients": to, "rejected": rejected},
               "env": "vm" if S.in_container(make_ctx()) else "test",
               "jobs": {"total": len(jobs), "failed": sum(1 for j in jobs if j["lastOk"] is False)},
               "releases": {"latest": rel["latest"], "parity": rel["parity"]}}
        return P.bagla(res, lambda: IK.for_status(engine, tenant, ran, res, *dbs()))

    @app.get("/api/v1/it-ops/checks")
    def itops_checks(request: Request, ring: Optional[str] = None, since: Optional[str] = None,
                     before: Optional[int] = None, size: int = 100) -> dict[str, Any]:
        engine, tenant, _ = ctx(request)
        s = I._aware(since) if since else None
        if since and s is None:
            raise HTTPException(status_code=422, detail={"code": "ITOPS", "message": "«since» ISO tarih olmalı."})
        return I.list_checks(engine, tenant, ring=ring or None, since=s, before=before, size=size)

    @app.get("/api/v1/it-ops/incidents")
    def itops_incidents(request: Request, state: str = "open", ring: Optional[str] = None,
                        before: Optional[str] = None, size: int = 50) -> dict[str, Any]:
        engine, tenant, _ = ctx(request)
        if state not in ("open", "closed", "all"):
            raise HTTPException(status_code=422, detail={"code": "ITOPS", "message": "state open, closed ya da all olmalı."})

        def read() -> dict[str, Any]:
            out = I.list_incidents(engine, tenant, state=state, ring=ring or None, before=before, size=size)
            if state != "open":
                since = I._now() - timedelta(days=30)
                out["downtime30"] = I.downtime(engine, tenant, since)
            return out
        return IZ.izli(engine, read, prefix="portal.itops.olaylar", title="Olaylar", text=IK.F_OLAY, skip=("size",))

    @app.get("/api/v1/it-ops/incidents/{iid}")
    def itops_incident(iid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _ = ctx(request)
        return IZ.izli(engine, lambda: call(I.get_incident, engine, tenant, iid), prefix="portal.itops.olay",
                       title="Olay", text=IK.F_OLAY)

    @app.patch("/api/v1/it-ops/incidents/{iid}")
    def itops_incident_update(iid: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        need(user, "ozellik:sistem.olay-kapat", "Olay değerlendirmesi")
        out, diff = call(I.update_incident, engine, tenant, iid, body or {}, user)
        audit(engine, user, "update", "itops_incident", iid, f"{out['ringLabel']} · {out['kindLabel']}", diff or None)
        return out

    @app.post("/api/v1/it-ops/incidents/{iid}/draft")
    def itops_incident_draft(iid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        need(user, "ozellik:sistem.olay-kapat", "Olay değerlendirmesi")
        inc = call(I.get_incident, engine, tenant, iid)
        llm = deps["llm"](BATCH)
        if llm is None:
            raise HTTPException(status_code=503, detail={"code": "NO_MODEL", "message": "Zeki AI modeli bu kurulumda tanımlı değil."})
        try:
            text = llm.chat(I.draft_prompt(inc), max_tokens=700)
        except Exception as e:  # noqa: BLE001
            log.warning("itops: taslak yazılamadı: %s", e)
            raise HTTPException(status_code=503, detail={"code": "MODEL", "message": "Zeki AI şu an taslak yazamadı; birazdan yeniden deneyin."}) from e
        # Rakamı model üretmez: taslaktaki her sayı olaya ait olgularda geçmeli; tutmayan taslak bütünüyle atılır,
        # yerine aynı olgulardan kalıp taslak konur (ekranda «kurala göre» işaretiyle).
        text, source, foreign = I.guard_draft(str(text or ""), inc)
        if foreign:
            log.info("itops: taslak olgu dışı sayı taşıdı (%s); kural taslağı kullanıldı", ", ".join(foreign))
        out = call(I.save_draft, engine, tenant, iid, text)
        title = "Zeki AI değerlendirme taslağı" if source == "zeki" else "kurala göre değerlendirme taslağı"
        audit(engine, user, "run", "itops_incident", iid, f"{out['ringLabel']} · {title}",
              {"kaynak": source, "olguDisiSayilar": foreign} if foreign or source != "zeki" else None)
        return dict(out, draftSource=source, draftForeignNumbers=foreign)

    @app.get("/api/v1/it-ops/jobs")
    def itops_jobs(request: Request) -> dict[str, Any]:
        engine, tenant, _ = ctx(request)
        with IZ.izle(engine) as ran:
            out = {"items": I.list_jobs(engine, tenant)}
        return P.bagla(out, lambda: IK.simple(engine, ran, out, prefix="portal.itops.isler", title="Zamanlanmış işler",
                                              text=IK.F_IS, dis=True))

    @app.get("/api/v1/it-ops/releases")
    def itops_releases(request: Request, before: Optional[int] = None, size: int = 50) -> dict[str, Any]:
        engine, tenant, _ = ctx(request)
        return IZ.izli(engine, lambda: I.list_releases(engine, tenant, before=before, size=size),
                       prefix="portal.itops.surumler", title="Kurulumlar", text=IK.F_SURUM, skip=("size",))

    @app.get("/api/v1/it-ops/capacity")
    def itops_capacity(request: Request, days: int = 7) -> dict[str, Any]:
        ctx(request)
        c = make_ctx()
        with IZ.izle(c.engine) as ran:
            out = S.capacity(c, max(1, min(int(days or 7), 366)))
        return P.bagla(out, lambda: IK.simple(c.engine, ran, out, prefix="portal.itops.kapasite", title="Kapasite",
                                              text=IK.F_KAPASITE, skip=("days",), dis=True))

    # ------------------------------------------------------------------ ayar (eşik ve alıcılar)

    def settings_items() -> list[dict[str, Any]]:
        v = admin_mod.settings_view()
        return [i for i in v["items"] if i["group"] == SETTING_GROUP]

    @app.get("/api/v1/it-ops/settings")
    def itops_settings(request: Request) -> dict[str, Any]:
        _, _, user = ctx(request)
        return {"items": settings_items(), "canEdit": can(user, "ozellik:sistem.ayar")}

    @app.put("/api/v1/it-ops/settings")
    def itops_settings_save(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, _, user = ctx(request)
        need(user, "ozellik:sistem.ayar", "Sistem durumu ayarı")
        values = dict((body or {}).get("values") or {})
        allowed = {i["key"] for i in settings_items()}
        extra = sorted(set(values) - allowed)
        if extra:
            raise HTTPException(status_code=422, detail={"code": "ITOPS", "message": "Bu ekrandan değiştirilemez: " + ", ".join(extra)})
        try:
            out = admin_mod.save_settings(engine, user, values)
        except admin_mod.AdminError as e:
            raise HTTPException(status_code=422, detail={"code": "ITOPS", "message": str(e)}) from e
        return {"items": settings_items(), "changed": out.get("changed", []), "canEdit": True}

    # ------------------------------------------------------------------ işlem

    @app.post("/api/v1/it-ops/check-now")
    def itops_check_now(request: Request, body: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        need(user, "ozellik:sistem.dene", "Bağlantıyı yeniden deneme")
        ring = str((body or {}).get("ring") or "").strip() or None
        if ring and ring not in I.RING_BY_ID:
            raise HTTPException(status_code=422, detail={"code": "ITOPS", "message": f"Bilinmeyen halka: {ring}"})
        out = run_tour(make_ctx(), deps["datasource"](), source="manual", rings=[ring] if ring else None,
                       collect=False, digests=False)
        audit(engine, user, "run", "itops_check", ring, "Sistem durumu: şimdi dene" + (f" ({I.RING_BY_ID[ring]['label']})" if ring else ""),
              {"failed": out["failed"], "opened": out["opened"], "closed": out["closed"]})
        return {**out, **I.status(engine, tenant, I.settings(conf))}

    # ------------------------------------------------------------------ zamanlayıcı ve betik (SYSTEM)

    @app.post("/api/v1/it-ops/run-due")
    def itops_run_due(request: Request) -> dict[str, Any]:
        require_caller(request)
        return run_tour(make_ctx(), deps["datasource"](), source="timer")

    @app.post("/api/v1/it-ops/watchdog")
    def itops_watchdog(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """Bekçi betiği ya da VM'deki iş kapsayıcısı bir işin sonucunu bildirir."""
        require_caller(request)
        engine = deps["engine"]()
        I.ensure(engine)
        job = str((body or {}).get("job") or "").strip()
        if not job:
            raise HTTPException(status_code=422, detail={"code": "ITOPS", "message": "«job» gerekli."})
        src = str(body.get("source") or "watchdog")
        src = src if src in ("watchdog", "jobs-container") else "watchdog"
        ok = body.get("ok")
        I.upsert_job(engine, deps["tenant"](), job, label=str(body.get("label") or job), source=src,
                     every=(str(body["every"]) if body.get("every") else None), last_at=I._now(),
                     last_ok=None if ok is None else bool(ok),
                     last_error=None if ok else str(body.get("detail") or body.get("error") or "başarısız"))
        return {"ok": True}

    @app.post("/api/v1/it-ops/report-release")
    def itops_report_release(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        require_caller(request)
        engine = deps["engine"]()
        I.ensure(engine)
        out = call(I.record_release, engine, deps["tenant"](), body or {})
        audit(engine, out["reportedBy"], "create", "itops_release", str(out["id"]),
              f"Sürüm: {out['env']} · {(out['codeSha'] or '?')[:12]}", {"image": out["image"], "appledouble": out["appledoubleCount"]})
        return out

    @app.get("/api/v1/it-ops/banner")
    def itops_banner(request: Request) -> dict[str, Any]:
        require_caller(request)
        engine = deps["engine"]()
        I.ensure(engine)
        return IZ.izli(engine, lambda: I.banner(engine, deps["tenant"]()), prefix="portal.itops.serit",
                       title="Kesinti şeridi", text=IK.F_BANNER)

    return {"run_tour": lambda **kw: run_tour(make_ctx(), deps["datasource"](), **kw)}
