"""M49 Veri yönetimi ve güvenlik uçları: /api/v1/data-security/*.

Sayfa kapısı `access.RULES` (`sayfa:veri-guvenligi`, açıkça verilen sayfa: «Herkes»in «bütün sayfalar»ı bu ekranı
açmaz). Uyarı kapatma `ozellik:guvenlik.uyari-kapat` (`FEATURE_RULES`); oturum kapatma `ozellik:guvenlik.oturum-kapat`
ve saklama politikası `ozellik:guvenlik.saklama` açıkça verilir ve burada denetlenir. `export-notice` her oturumlu
kişiye açıktır (kişi yalnız kendi istemci tarafı aktarımını bildirir). `run-due` yalnız zamanlayıcının
(`timas-security.timer`, 5 dk): giriş olaylarını çeker, kuralları koşar, uyarı e-postasını gönderir; günde bir kez
(`SECURITY_DAILY_AT`, 03:40) saklama işini ve günlük özeti çalıştırır.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool

from semantic_bridge import data_security as D

log = logging.getLogger("semantic.data_security.api")
P = "/api/v1/data-security"
FEATURE_CLOSE = "ozellik:guvenlik.uyari-kapat"
FEATURE_REVOKE = "ozellik:guvenlik.oturum-kapat"
FEATURE_RETENTION = "ozellik:guvenlik.saklama"


def _since(v: str) -> Optional[datetime]:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(v)
    except ValueError:
        raise HTTPException(400, detail={"code": "SECURITY", "message": "Tarih YYYY-AA-GG biçiminde olmalı."}) from None
    return d if d.tzinfo else d.replace(tzinfo=D._local_tz())


def _int(v: str) -> Optional[int]:
    try:
        return int(v) if v else None
    except ValueError:
        raise HTTPException(400, detail={"code": "SECURITY", "message": "Sayfa imleci geçersiz."}) from None


def register(app, rt: Callable[[], Any], require_caller: Callable[[Request], None], can: Callable[[str, str], bool],
             directory: Any, client: Optional[D.LoginClient] = None):
    from semantic_bridge import access as access_mod
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod

    login = client or D.LoginClient()

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        require_caller(request)
        try:
            user, _ = board_mod.session_of(request.headers.get("cookie", ""))
        except board_mod.NoUser:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Oturum gerekli."}) from None
        r = rt()
        D.ensure(r.store.engine)
        admin_mod.ensure(r.store.engine)
        return r.store.engine, r.settings.tenant_id, r.settings.datasource_id, user

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except D.SecurityError as e:
            raise HTTPException(status_code=e.status, detail={"code": "SECURITY", "message": str(e)}) from e
        except D.LoginServiceError as e:
            raise HTTPException(status_code=503, detail={"code": "LOGIN_SERVICE", "message": str(e)}) from e

    def need(user: str, key: str, what: str) -> None:
        if not can(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def people() -> tuple[dict[str, str], Optional[str]]:
        """Önizlemenin kişi evreni: AD'deki etkin kişiler; AD okunamazsa portal izi olan hesaplar (notla)."""
        try:
            return {p["subject"].lower(): p.get("label") or p["subject"] for p in directory.list_people()}, None
        except Exception as e:  # noqa: BLE001
            r = rt()
            names = {u: u for u in D.last_logins(r.store.engine)}
            for u in admin_mod.admins():
                names.setdefault(u, u)
            return names, f"Active Directory okunamadı ({type(e).__name__}); yalnız portala giriş kaydı olan hesaplar hesaplandı."

    def sessions_or_none() -> Optional[list[dict[str, Any]]]:
        if not login.configured:
            return None
        try:
            return login.sessions()
        except D.LoginServiceError as e:
            log.warning("güvenlik: oturum listesi okunamadı: %s", e)
            return None

    def link() -> str:
        base = (admin_mod.conf("ALERT_LINK") or "").split("/uyarilar")[0]
        return f"{base}/veri-guvenligi" if base else ""

    # ------------------------------------------------------------------ genel

    @app.get(P + "/meta")
    def ds_meta(request: Request) -> dict[str, Any]:
        _, _, _, user = ctx(request)
        cfg = D.settings()
        return {
            "me": {"username": user, "isAdmin": admin_mod.is_admin(user), "canClose": can(user, FEATURE_CLOSE),
                   "canRevoke": can(user, FEATURE_REVOKE), "canRetention": can(user, FEATURE_RETENTION)},
            "loginService": {"configured": login.configured},
            "rules": {"failThreshold": cfg["failThreshold"], "failWindowMin": cfg["failWindowMin"], "workHours": cfg["workHours"],
                      "workDays": sorted(cfg["workDays"]), "offhoursExportMin": cfg["offhoursExportMin"],
                      "idleDays": cfg["idleDays"], "recipients": len(cfg["recipients"]), "dailyAt": cfg["dailyAt"]},
            "kinds": D.KIND_LABEL, "reasons": D.REASON_LABEL, "ruleLabels": D.RULE_LABEL,
            "hygieneKinds": {k: {"label": v[0], "severity": v[1]} for k, v in D.HYGIENE_KIND.items()},
            "retention": [{k: o[k] for k in ("id", "label", "what", "default")} for o in D.RETENTION],
        }

    @app.get(P + "/summary")
    def ds_summary(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = D.summary(engine)
        access_mod.ensure(engine, tenant)
        st = access_mod._load(engine, tenant)
        herkes = st["roles"].get(access_mod._role_id(tenant, access_mod.EVERYONE_ID)) or {}
        pages = [p["key"] for p in access_mod.catalog()["pages"]]
        explicit = access_mod.explicit_keys()
        granted = [k for k in pages if k not in explicit] if herkes.get("all_perms") else [k for k in pages if k in herkes.get("perms", set())]
        out["everyone"] = {"all": bool(herkes.get("all_perms")), "pages": len(granted), "pagesTotal": len(pages)}
        try:
            profiles = rt().profiles
            emap = access_mod.entity_domains(engine, tenant, profiles)
            out["unassignedEntities"] = sum(1 for v in emap.values() if v == "atanmamis")
            out["sensitiveColumns"] = sum(1 for p in profiles for c in (p.columns or []) if getattr(c, "sensitive", False))
        except Exception as e:  # noqa: BLE001
            log.warning("güvenlik: özet katalog sayıları okunamadı: %s", e)
            out["unassignedEntities"] = out["sensitiveColumns"] = None
        out["loginService"] = {"configured": login.configured}
        return out

    # ------------------------------------------------------------------ uyarılar

    @app.get(P + "/alerts")
    def ds_alerts(request: Request, state: str = "open", before: str = "") -> dict[str, Any]:
        engine, _, _, _ = ctx(request)
        return D.list_alerts(engine, state=state, before=_int(before))

    @app.patch(P + "/alerts/{alert_id}")
    def ds_alert_close(alert_id: int, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, _, _, user = ctx(request)
        need(user, FEATURE_CLOSE, "Uyarı kapatma")
        out, diff = call(D.close_alert, engine, alert_id, user, body)
        admin_mod.audit(engine, user, "update", "security_alert", str(alert_id), out["ruleLabel"], diff)
        return out

    # ------------------------------------------------------------------ giriş ve oturumlar

    @app.get(P + "/logins")
    def ds_logins(request: Request, user: str = "", ok: str = "", since: str = "", before: str = "") -> dict[str, Any]:
        engine, _, _, _ = ctx(request)
        flag = True if ok == "1" else False if ok == "0" else None
        out = D.list_logins(engine, user=user, ok=flag, since=_since(since), before=_int(before))
        out["pull"] = D.state_get(engine, "login_pull")
        out["configured"] = login.configured
        return out

    @app.get(P + "/sessions")
    async def ds_sessions(request: Request) -> dict[str, Any]:
        await run_in_threadpool(ctx, request)
        if not login.configured:
            return {"configured": False, "items": []}
        items = await run_in_threadpool(call, login.sessions)
        ppl, note = await run_in_threadpool(people)
        for s in items:
            s["display"] = s.get("display") or ppl.get(str(s.get("username") or "").lower())
            s["adEnabled"] = None if note else str(s.get("username") or "").lower() in ppl
        return {"configured": True, "items": items, "note": note}

    @app.post(P + "/sessions/revoke")
    def ds_revoke(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, _, _, user = ctx(request)
        need(user, FEATURE_REVOKE, "Oturum kapatma")
        target = str(body.get("username") or "").strip().lower() or None
        session = str(body.get("session") or "").strip() or None
        if not target and not session:
            raise HTTPException(422, detail={"code": "SECURITY", "message": "Kişi ya da oturum seçilmedi."})
        out = call(login.revoke, username=target, session=session, actor=user)
        admin_mod.audit(engine, user, "delete", "session", target or session, "Oturum kapatıldı",
                        {"kisi": target, "oturum": session, "kapanan": out.get("revoked", 0)})
        return {"revoked": int(out.get("revoked") or 0)}

    # ------------------------------------------------------------------ erişim kaydı

    @app.get(P + "/access")
    def ds_access(request: Request, kind: str = "", user: str = "", since: str = "", before: str = "") -> dict[str, Any]:
        engine, tenant, ds, _ = ctx(request)
        if kind not in ("", "forbidden", "export", "not_permitted"):
            raise HTTPException(400, detail={"code": "SECURITY", "message": "Kayıt türü geçersiz."})
        if before:
            try:
                datetime.fromisoformat(before)
            except ValueError:
                raise HTTPException(400, detail={"code": "SECURITY", "message": "Sayfa imleci geçersiz."}) from None
        return D.list_access(engine, engine, tenant, ds, kind=kind, user=user, since=_since(since), before=before or None)

    @app.post(P + "/export-notice")
    def ds_export_notice(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, _, _, user = ctx(request)
        return call(D.export_notice, engine, user, body)

    # ------------------------------------------------------------------ hesap hijyeni, «Herkes» önizlemesi

    @app.get(P + "/hygiene")
    async def ds_hygiene(request: Request) -> dict[str, Any]:
        engine, tenant, ds, _ = await run_in_threadpool(ctx, request)
        sess = await run_in_threadpool(sessions_or_none)
        return await run_in_threadpool(D.hygiene, engine, tenant, ds, directory=directory, sessions=sess,
                                       is_admin=admin_mod.is_admin)

    @app.get(P + "/preview-everyone")
    async def ds_preview_everyone(request: Request, remove: str = "", perms: Optional[str] = None,
                                  all: bool = False) -> dict[str, Any]:  # noqa: A002 — sorgu adı
        engine, tenant, _, _ = await run_in_threadpool(ctx, request)
        ppl, note = await run_in_threadpool(people)
        out = await run_in_threadpool(
            call, D.preview_everyone, engine, tenant, people=ppl, is_admin=admin_mod.is_admin,
            perms=[p.strip() for p in perms.split(",")] if perms is not None else None,
            remove=[p.strip() for p in remove.split(",") if p.strip()], all_perms=all)
        out["note"] = note
        return out

    # ------------------------------------------------------------------ envanter ve saklama

    @app.get(P + "/inventory")
    async def ds_inventory(request: Request) -> dict[str, Any]:
        engine, _, _, _ = await run_in_threadpool(ctx, request)
        return await run_in_threadpool(D.inventory, engine, engine, rt().profiles)

    @app.get(P + "/retention")
    async def ds_retention(request: Request) -> dict[str, Any]:
        engine, tenant, ds, _ = await run_in_threadpool(ctx, request)
        objs = await run_in_threadpool(D.preview, engine, engine, tenant, ds)
        cfg = D.settings()
        return {"apply": cfg["apply"], "applyOn": D.state_get(engine, "retention_apply_on"),
                "lastOk": D._iso(D.last_retention_ok(engine)), "dailyAt": cfg["dailyAt"], "objects": objs}

    @app.post(P + "/retention/preview")
    async def ds_retention_preview(body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Kaydetmeden önce: verilen sürelerle kaç satır etkilenir (salt okuma)."""
        engine, tenant, ds, _ = await run_in_threadpool(ctx, request)
        days: dict[str, int] = {}
        for k, v in (body.get("days") or {}).items():
            try:
                days[str(k)] = max(0, int(v))
            except (TypeError, ValueError):
                raise HTTPException(422, detail={"code": "SECURITY", "message": "Gün sayısı tam sayı olmalı."}) from None
        return {"objects": await run_in_threadpool(D.preview, engine, engine, tenant, ds, None, days)}

    @app.put(P + "/retention")
    async def ds_retention_put(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, ds, user = await run_in_threadpool(ctx, request)
        need(user, FEATURE_RETENTION, "Saklama süresi politikası")
        days = None
        if isinstance(body.get("days"), dict):
            cur = D.settings()["days"]
            try:
                days = {o["id"]: max(0, int(body["days"].get(o["id"], cur[o["id"]]) or 0)) for o in D.RETENTION}
            except (TypeError, ValueError):
                raise HTTPException(422, detail={"code": "SECURITY", "message": "Gün sayısı tam sayı olmalı."}) from None
        prev = await run_in_threadpool(D.preview, engine, engine, tenant, ds, None, days)
        out = await run_in_threadpool(call, D.retention_update, engine, user, body, prev)
        return {**out, "objects": await run_in_threadpool(D.preview, engine, engine, tenant, ds), "apply": D.settings()["apply"]}

    @app.get(P + "/retention/runs")
    def ds_retention_runs(request: Request, before: str = "") -> dict[str, Any]:
        engine, _, _, _ = ctx(request)
        return D.list_runs(engine, before=_int(before))

    # ------------------------------------------------------------------ zamanlayıcı

    @app.post(P + "/run-due")
    def ds_run_due(request: Request, zorla: str = "") -> dict[str, Any]:
        """Zamanlayıcı (5 dk): giriş olayları, kurallar, uyarı e-postası; günde bir kez saklama ve günlük özet.
        `?zorla=gunluk` günlük kısmı hemen koşturur (ilk koşu elle yapılır)."""
        require_caller(request)
        from semantic_bridge.budget_api import _send_mail

        r = rt()
        engine, tenant, ds = r.store.engine, r.settings.tenant_id, r.settings.datasource_id
        D.ensure(engine)
        admin_mod.ensure(engine)
        access_mod.ensure(engine, tenant)
        now = D._now()
        cfg = D.settings()
        pull = D.pull_logins(engine, login)
        admin_set = set(admin_mod.admins()) | set(admin_mod.admin_group_members())
        access_mod.invalidate()
        st = access_mod._load(engine, tenant)
        herkes = st["roles"].get(access_mod._role_id(tenant, access_mod.EVERYONE_ID))
        everyone = {"all": bool(herkes["all_perms"]), "perms": sorted(herkes["perms"])} if herkes else None
        new = D.evaluate(engine, tenant, now, admin_set=admin_set, everyone=everyone,
                         retention_last_ok=D.last_retention_ok(engine), cfg=cfg)
        mail = "bos"
        if new:
            if cfg["recipients"]:
                mail = _send_mail(f"Portal güvenlik uyarısı: {len(new)} yeni", D.alert_text(new, link()), cfg["recipients"])
            else:
                mail = "alici_yok"
            D.mark_mailed(engine, [a["id"] for a in new], mail)
        out: dict[str, Any] = {"giris": pull, "yeniUyari": len(new), "eposta": mail, "gunluk": None}
        if zorla == "gunluk" or D.daily_due(engine, now, cfg):
            retention = D.run_retention(engine, engine, tenant, ds, now=now)
            digest = D.digest_text(engine, engine, tenant, ds, now)
            dmail = "bos"
            if digest:
                dmail = _send_mail("Portal güvenlik: günlük erişim özeti", digest, cfg["recipients"]) if cfg["recipients"] else "alici_yok"
            D.mark_daily(engine, now)
            out["gunluk"] = {"saklama": retention, "ozet": dmail}
        return out

    return {"client": login}

