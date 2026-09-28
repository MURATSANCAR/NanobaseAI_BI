"""M56 Performans yönetimi uçları: /api/v1/hr/performance/*.

Sayfa kapısı `access.RULES` (`sayfa:ik-performansim`, `sayfa:ik-ekibim`, `sayfa:ik-hedefler`, `sayfa:ik-degerlendirme`; hepsi
açıkça verilir). Kişi kapsamı (kendi kaydı, `manager_id` zinciri, İK/GM) ve işlem anahtarları (`ozellik:ik.*`) burada ve
`hr_performance`'ta denetlenir. `POST /reminders/run-due` yalnız zamanlayıcı (sistem jetonu).

Zeki AI: OKR taslağı (kişi adı gitmez), hizalama önerisi (kapalı seçim, olasılıkla), yorum yeniden yazımı (adlar ve iletişim
maskeli). Çağrılar `HrContext.llm` ile LLM kapısından; sıra kaydında yalnız etiket. Ekranda model adı yok.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import date
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import hr_core as H
from semantic_bridge import hr_engagement_text as T
from semantic_bridge import hr_performance as P
from semantic_bridge import hr_performance_sources as S
from semantic_bridge.hr_api import HrContext

log = logging.getLogger("semantic_bridge.hr.performance.api")
B = "/api/v1/hr/performance"


def register(app, hr: HrContext) -> None:
    ctx, need, call = hr.ctx, hr.need, hr.call
    P.register_hooks()

    def scoped(request: Request) -> tuple[Any, str, P.Scope]:
        engine, tenant, who = ctx(request)
        P.ensure(engine)
        return engine, tenant, P.Scope(engine, tenant, who)

    def model(label: str):
        m = hr.llm(label)
        if m is None:
            raise HTTPException(503, detail={"code": "HR_MODEL", "message": "Zeki AI bu kurulumda tanımlı değil."})
        return m

    def perf_settings() -> dict[str, Any]:
        return P.settings(hr.conf)

    def logo_run():
        return S.bsrc.runner(hr.rt().settings.connection_file, 300)

    def crm_run():
        import os

        return S.bsrc.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"), 300)

    # ------------------------------------------------------------------ genel

    @app.get(B + "/meta")
    def perf_meta(request: Request) -> dict[str, Any]:
        engine, tenant, sc = scoped(request)
        w = sc.who
        return {
            "levels": P.LEVELS, "goalStates": P.GOAL_STATES, "measureKinds": P.MEASURE_KINDS, "systemMeasures": P.SYSTEM_MEASURES,
            "formStates": P.FORM_STATES, "sectionKinds": P.SECTION_KINDS, "cycleStates": P.CYCLE_STATES,
            "reviewStates": P.REVIEW_STATES, "defaultOverall": P.DEFAULT_OVERALL, "settings": perf_settings(),
            "modelVar": hr.llm("durum") is not None,
            "units": [{"id": u.id, "name": u.name, "parentId": u.parent_id} for u in sorted(sc.units.values(), key=lambda x: x.name.casefold())],
            "me": {"username": w.user, "display": w.display, "employeeId": sc.me_id, "teamSize": len(sc.team),
                   "managedUnits": sorted(sc.managed_units()),
                   "can": {"goalWrite": w.can(P.F_GOAL_WRITE), "goalApprove": w.can(P.F_GOAL_APPROVE), "cycle": w.can(P.F_CYCLE),
                           "reviewWrite": w.can(P.F_REVIEW_WRITE), "reviewApprove": w.can(P.F_REVIEW_APPROVE),
                           "calibration": w.can(P.F_CALIBRATION), "workSummary": w.can(P.F_WORK), "export": w.can(P.F_EXPORT)}},
        }

    @app.get(B + "/me")
    def perf_me(request: Request) -> dict[str, Any]:
        engine, tenant, sc = scoped(request)
        return call(P.me_view, engine, tenant, sc)

    @app.get(B + "/team")
    def perf_team(request: Request, direct: bool = False) -> dict[str, Any]:
        engine, tenant, sc = scoped(request)
        if not sc.me_id:
            return {"me": None, "people": [], "gaps": P.hierarchy_gaps(sc) if sc.cycle_admin else None}
        return call(P.team_view, engine, tenant, sc, direct_only=direct)

    @app.get(B + "/team/{eid}")
    def perf_team_person(eid: str, request: Request) -> dict[str, Any]:
        """Ekibimdeki bir kişi: hedefleri, değerlendirmeleri ve iş kayıtları özetleri. Zincir dışı → 403 + erişim kaydı."""
        engine, tenant, sc = scoped(request)
        if not sc.sees_person(eid):
            raise HTTPException(403, detail={"code": "HR", "message": str(P.deny(engine, tenant, sc, eid, "ekip kişi kartı"))})
        e = sc.emp.get(eid)
        if e is None:
            raise HTTPException(404, detail={"code": "HR", "message": "Çalışan bulunamadı."})
        H.log_access(engine, tenant, sc.who.user, "calisan", eid, "goruntule", "performans kişi kartı")
        with engine.connect() as c:
            revs = c.execute(sa.select(P.REVIEWS, P.CYCLES.c.name).join(P.CYCLES, P.CYCLES.c.id == P.REVIEWS.c.cycle_id)
                             .where(P.REVIEWS.c.employee_id == eid).order_by(P.CYCLES.c.starts_on.desc())).all()
            works = c.execute(sa.select(P.WORK).where(P.WORK.c.employee_id == eid).order_by(P.WORK.c.generated_at.desc())).all()
        return {"employee": {"id": eid, "name": e.display_name, "title": e.title or "", "unitName": sc.unit_name(e.unit_id),
                             "managerName": sc.name(e.manager_id)},
                "goals": P.list_goals(engine, tenant, sc, owner=eid),
                "reviews": [{"id": r.id, "cycleName": r.name, "state": P.review_state(r), "stateLabel": P.REVIEW_STATES[P.review_state(r)],
                             "mine": r.manager_id == sc.me_id} for r in revs],
                "workSummaries": [P._work_out(w) for w in works] if sc.who.can(P.F_WORK) else None}

    # ------------------------------------------------------------------ hedefler

    @app.get(B + "/goals")
    def perf_goals(request: Request, period: str = "", year: str = "", owner: str = "", level: str = "") -> dict[str, Any]:
        engine, tenant, sc = scoped(request)
        if owner and not sc.sees_person(owner) and not sc.cycle_admin:
            raise HTTPException(403, detail={"code": "HR", "message": str(P.deny(engine, tenant, sc, owner, "hedef listesi"))})
        return {"items": call(P.list_goals, engine, tenant, sc, period=period, year=year, owner=owner, level=level)}

    @app.post(B + "/goals", status_code=201)
    def perf_goal_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, sc = scoped(request)
        out, diff = call(P.save_goal, engine, tenant, sc, body, system_measures_on=perf_settings()["logoSales"])
        hr.audit(engine, sc.who.user, "create", "hr_goal", out["id"], f"{out['levelLabel']} hedefi", diff)
        return out

    @app.get(B + "/goals/{gid}")
    def perf_goal(gid: str, request: Request) -> dict[str, Any]:
        engine, tenant, sc = scoped(request)
        return call(P.get_goal, engine, tenant, sc, gid)

    @app.patch(B + "/goals/{gid}")
    def perf_goal_update(gid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, sc = scoped(request)
        out, diff = call(P.save_goal, engine, tenant, sc, body, gid, system_measures_on=perf_settings()["logoSales"])
        if diff:
            hr.audit(engine, sc.who.user, "update", "hr_goal", gid, f"{out['levelLabel']} hedefi", diff)
        return out

    for action in ("submit", "withdraw", "approve", "reject", "close"):
        def make(act: str):
            def transition(gid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
                engine, tenant, sc = scoped(request)
                out = call(P.goal_transition, engine, tenant, sc, gid, act, str(body.get("note") or ""))
                hr.audit(engine, sc.who.user, "update", "hr_goal", gid, f"{out['levelLabel']} hedefi", {"islem": act, "durum": out["state"]})
                return out
            transition.__name__ = f"perf_goal_{act}"
            return transition
        app.post(B + "/goals/{gid}/" + action)(make(action))

    @app.post(B + "/goals/{gid}/checkins", status_code=201)
    def perf_checkin(gid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, sc = scoped(request)
        out = call(P.add_checkin, engine, tenant, sc, gid, body)
        hr.audit(engine, sc.who.user, "create", "hr_goal_checkin", gid, "Hedef check-in",
                 {"ilerleme": body.get("progressPct"), "deger": body.get("value")})
        return out

    @app.post(B + "/goals/{gid}/revisions", status_code=201)
    def perf_revision(gid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, sc = scoped(request)
        out = call(P.request_revision, engine, tenant, sc, gid, body)
        hr.audit(engine, sc.who.user, "create", "hr_goal_revision", gid, "Hedef revizyonu istendi",
                 {"alanlar": sorted((body.get("changes") or {}).keys())})
        return out

    @app.post(B + "/revisions/{rid}/decide")
    def perf_revision_decide(rid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, sc = scoped(request)
        out = call(P.decide_revision, engine, tenant, sc, rid, str(body.get("decision") or ""), str(body.get("note") or ""))
        hr.audit(engine, sc.who.user, "update", "hr_goal_revision", rid, "Hedef revizyonu kararı", {"karar": body.get("decision")})
        return out

    @app.get(B + "/goals/{gid}/progress")
    async def perf_goal_progress(gid: str, request: Request) -> dict[str, Any]:
        """Sistem ölçüsü: Logo'dan temsilcinin faturalı net satışı (rakam SQL'den). Beyan hedefte son check-in."""
        engine, tenant, sc = await run_in_threadpool(scoped, request)
        g = await run_in_threadpool(call, P.get_goal, engine, tenant, sc, gid)
        start, end = P.period_range(g["period"])
        if g["measureKind"] != "sistem":
            last = g["lastCheckin"]
            return {"kind": "beyan", "periodStart": start.isoformat(), "periodEnd": end.isoformat(), "target": g["targetValue"],
                    "value": last["value"] if last else None, "progressPct": last["progressPct"] if last else None}
        if not perf_settings()["logoSales"]:
            raise HTTPException(409, detail={"code": "HR", "message": "Sistem ölçüsü bu kurulumda kapalı."})
        res = await run_in_threadpool(call, lambda: S.salesman_net(logo_run(), g["measureRef"], start, end))
        tgt = g["targetValue"]
        return {"kind": "sistem", "measure": g["systemMeasure"], "code": g["measureRef"], "periodStart": start.isoformat(),
                "periodEnd": end.isoformat(), "target": tgt, **res,
                "progressPct": round(100 * res["value"] / tgt, 1) if tgt else None,
                "note": "Logo kopyası donmuşsa son fatura tarihi dönem sonundan önce kalır; oran o tarihe kadardır."}

    @app.get(B + "/logo-salesman-fill")
    async def perf_salesman_fill(request: Request, year: int = 0) -> dict[str, Any]:
        """Kabul 1 ölçümü: satış faturalarında temsilci alanı doluluğu (sistem ölçüsünü açma kararı için)."""
        engine, tenant, sc = await run_in_threadpool(scoped, request)
        need(sc.who, P.F_CYCLE, P.F_GOAL_APPROVE, what="Temsilci alanı ölçümü")
        return await run_in_threadpool(call, lambda: S.salesman_fill(logo_run(), year or date.today().year))

    @app.post(B + "/goals/draft")
    async def perf_goal_draft(body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Zeki AI OKR taslağı. Kaydetmez; kişi adı modele gitmez (üst hedef, birim, unvan)."""
        engine, tenant, sc = await run_in_threadpool(scoped, request)
        parent = None
        if body.get("parentGoalId"):
            parent = await run_in_threadpool(call, P.get_goal, engine, tenant, sc, str(body["parentGoalId"]))
        owner = sc.emp.get(str(body.get("ownerEmployeeId") or sc.me_id or ""))
        unit_name = sc.unit_name(body.get("unitId") or (owner.unit_id if owner else None)) or ""
        m = model("OKR taslağı")
        text = await run_in_threadpool(lambda: m.chat(P.okr_messages(parent, unit_name, (owner.title if owner else "") or "",
                                                                     str(body.get("hint") or "")), max_tokens=900, temperature=0.2))
        drafts = P.parse_drafts(text or "")
        if not drafts:
            raise HTTPException(502, detail={"code": "HR_MODEL", "message": "Zeki AI taslak yazamadı; yeniden deneyin."})
        hr.audit(engine, sc.who.user, "run", "hr_goal", body.get("parentGoalId") or "-", "Zeki AI hedef taslağı", {"taslak": len(drafts)})
        return {"items": drafts}

    @app.post(B + "/goals/{gid}/align-suggest")
    async def perf_align(gid: str, request: Request) -> dict[str, Any]:
        """Hizalama önerisi: kapalı seçim (aday üst hedeflerden biri) ve olasılığı. Bağlamayı kişi yapar."""
        engine, tenant, sc = await run_in_threadpool(scoped, request)
        g, cands = await run_in_threadpool(call, P.align_candidates, engine, tenant, sc, gid)
        if not cands:
            return {"candidates": [], "suggestion": None, "note": "Bu yıl için bağlanabilecek birim ya da şirket hedefi yok."}
        m = model("hedef hizalama")
        if not hasattr(m, "choose"):
            raise HTTPException(503, detail={"code": "HR_MODEL", "message": "Zeki AI seçim çağrısı bu kurulumda yok."})
        prompt, labels = P.align_prompt(g, cands)
        ch = await run_in_threadpool(m.choose, prompt, labels)
        pick = None
        if getattr(ch, "choice", None) in labels:
            i = labels.index(ch.choice)
            pick = {**cands[i], "probability": (ch.probs or {}).get(ch.choice) if ch.probs else None}
        return {"candidates": cands, "suggestion": pick}

    # ------------------------------------------------------------------ formlar ve dönemler

    @app.get(B + "/forms")
    def perf_forms(request: Request) -> dict[str, Any]:
        engine, tenant, sc = scoped(request)
        need(sc.who, P.F_CYCLE, what="Değerlendirme formları")
        return {"items": P.list_forms(engine, tenant), "starter": P.STARTER_FORM}

    @app.post(B + "/forms", status_code=201)
    def perf_form_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, sc = scoped(request)
        need(sc.who, P.F_CYCLE, what="Form düzenleme")
        out, diff = call(P.save_form, engine, tenant, sc.who.user, body)
        hr.audit(engine, sc.who.user, "create", "hr_review_form", out["id"], out["name"], diff)
        return out

    @app.patch(B + "/forms/{fid}")
    def perf_form_update(fid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, sc = scoped(request)
        need(sc.who, P.F_CYCLE, what="Form düzenleme")
        out, diff = call(P.save_form, engine, tenant, sc.who.user, body, fid)
        if diff:
            hr.audit(engine, sc.who.user, "update", "hr_review_form", fid, out["name"], diff)
        return out

    @app.get(B + "/cycles")
    def perf_cycles(request: Request) -> dict[str, Any]:
        engine, tenant, sc = scoped(request)
        return {"items": P.list_cycles(engine, tenant)}

    @app.post(B + "/cycles", status_code=201)
    def perf_cycle_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, sc = scoped(request)
        need(sc.who, P.F_CYCLE, what="Dönem yönetimi")
        out, diff = call(P.save_cycle, engine, tenant, sc.who.user, body)
        hr.audit(engine, sc.who.user, "create", "hr_review_cycle", out["id"], out["name"], diff)
        return out

    @app.patch(B + "/cycles/{cid}")
    def perf_cycle_update(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, sc = scoped(request)
        need(sc.who, P.F_CYCLE, what="Dönem yönetimi")
        out, diff = call(P.save_cycle, engine, tenant, sc.who.user, body, cid)
        if diff:
            hr.audit(engine, sc.who.user, "update", "hr_review_cycle", cid, out["name"], diff)
        return out

    for action in ("open", "calibrate", "reopen", "close"):
        def make_c(act: str):
            def cycle_action(cid: str, request: Request) -> dict[str, Any]:
                engine, tenant, sc = scoped(request)
                need(sc.who, P.F_CYCLE, what="Dönem yönetimi")
                out = call(P.cycle_transition, engine, tenant, sc, cid, act)
                hr.audit(engine, sc.who.user, "update", "hr_review_cycle", cid, out["name"],
                         {"islem": act, "durum": out["state"], "eklenen": out.get("added")})
                return out
            cycle_action.__name__ = f"perf_cycle_{act}"
            return cycle_action
        app.post(B + "/cycles/{cid}/" + action)(make_c(action))

    @app.post(B + "/cycles/{cid}/sync")
    def perf_cycle_sync(cid: str, request: Request) -> dict[str, Any]:
        engine, tenant, sc = scoped(request)
        need(sc.who, P.F_CYCLE, what="Dönem yönetimi")
        out = call(P.sync_participants, engine, tenant, sc, cid)
        hr.audit(engine, sc.who.user, "run", "hr_review_cycle", cid, "Katılımcılar eşitlendi", out)
        return out

    @app.get(B + "/cycles/{cid}/status")
    def perf_cycle_status(cid: str, request: Request) -> dict[str, Any]:
        """Tamamlanma panosu. Kişi listesi yalnız dönem yönetimi (İK) yetkisinde; diğerlerine yalnız sayılar."""
        engine, tenant, sc = scoped(request)
        out = call(P.cycle_status, engine, tenant, sc, cid)
        if not sc.cycle_admin and not sc.all:
            out["people"] = [p for p in out["people"] if p["employeeId"] in sc.team]
        return out

    @app.post(B + "/cycles/{cid}/remind")
    async def perf_cycle_remind(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        """İK'nın tek tıkla hatırlatması: formu eksik kişilere içeriksiz, yalnız bağlantılı e-posta (AD'deki iş adresine).
        Otomatik değildir; düğmeye İK basar. Adresi olmayan kişi sayılır, listesi ekranda İK'ya kalır."""
        from semantic_bridge import admin as admin_mod
        from semantic_bridge import people as people_mod
        from semantic_bridge.budget_api import _send_mail

        engine, tenant, sc = await run_in_threadpool(scoped, request)
        need(sc.who, P.F_CYCLE, what="Hatırlatma")
        which = str(body.get("which") or "self")
        st = await run_in_threadpool(call, P.cycle_status, engine, tenant, sc, cid)
        wanted = [p for p in st["people"] if (p["state"] == "oz_degerlendirme" if which == "self" else p["state"] in ("oz_degerlendirme", "yonetici"))]
        targets: list[tuple[str, str]] = []                   # (hesap, kime hatırlatılıyor)
        for p in wanted:
            if which == "self":
                targets.append((getattr(sc.emp.get(p["employeeId"]), "username", None) or "", "oz"))
            else:
                targets.append((getattr(sc.emp.get(p["managerId"] or ""), "username", None) or "", "yonetici"))
        accounts = sorted({t[0] for t in targets if t[0]})
        try:
            ad = await run_in_threadpool(people_mod.ad_people, {k: admin_mod.conf(k) for k in admin_mod.store_keys("ad")})
        except Exception as e:  # noqa: BLE001
            log.warning("hr: hatırlatma için AD okunamadı: %s", e)
            ad = None
        link = (hr.conf("ALERT_LINK") or "").split("/uyarilar")[0]
        subject = f"Değerlendirme dönemi: {st['cycle']['name']}"
        text = ("Portalda sizi bekleyen bir performans değerlendirmesi adımı var.\n\n"
                + (f"{link}/ik/{'performansim' if which == 'self' else 'ekibim'}\n" if link else "Portal → İnsan Kaynakları\n"))
        sent = no_mail = failed = 0
        for acc in accounts:
            addr = ((ad or {}).get(acc) or {}).get("email") if ad else None
            if not addr:
                no_mail += 1
                continue
            res = await run_in_threadpool(_send_mail, subject, text, [addr])
            sent += res == "sent"
            failed += res != "sent"
        no_mail += sum(1 for t in targets if not t[0])
        hr.audit(engine, sc.who.user, "run", "hr_review_cycle", cid, "Değerlendirme hatırlatması",
                 {"tur": which, "gonderilen": sent, "adressiz": no_mail, "hata": failed})
        return {"which": which, "people": len(wanted), "accounts": len(accounts), "sent": sent, "noMail": no_mail, "failed": failed,
                "adRead": ad is not None}

    @app.get(B + "/cycles/{cid}/calibration")
    def perf_calibration(cid: str, request: Request) -> dict[str, Any]:
        engine, tenant, sc = scoped(request)
        need(sc.who, P.F_CALIBRATION, what="Kalibrasyon görünümü")
        out = call(P.calibration, engine, tenant, sc, cid)
        H.log_access(engine, tenant, sc.who.user, "calisan", f"donem:{cid}"[:40], "goruntule", "kalibrasyon")
        return out

    @app.get(B + "/cycles/{cid}/export.csv")
    def perf_export(cid: str, request: Request) -> Response:
        engine, tenant, sc = scoped(request)
        need(sc.who, P.F_EXPORT, what="İK verisini dışa aktarma")
        need(sc.who, P.F_CYCLE, P.F_CALIBRATION, what="Dönem tablosu")
        rows = call(P.export_rows, engine, tenant, sc, cid)
        buf = io.StringIO()
        csv.writer(buf, delimiter=";").writerows(rows)
        H.log_access(engine, tenant, sc.who.user, "calisan", f"donem:{cid}"[:40], "disa_aktar", "değerlendirme dönemi tablosu")
        hr.audit(engine, sc.who.user, "run", "hr_review_cycle", cid, "Değerlendirme tablosu dışa aktarıldı", {"satir": len(rows) - 1})
        return Response(content=("﻿" + buf.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="degerlendirme-{cid[-8:]}.csv"', "Cache-Control": "private, no-store"})

    # ------------------------------------------------------------------ değerlendirmeler

    @app.get(B + "/reviews/{rid}")
    def perf_review(rid: str, request: Request) -> dict[str, Any]:
        engine, tenant, sc = scoped(request)
        return call(P.get_review, engine, tenant, sc, rid)

    @app.patch(B + "/reviews/{rid}")
    def perf_review_save(rid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, sc = scoped(request)
        return call(P.save_review, engine, tenant, sc, rid, body)

    @app.post(B + "/reviews/{rid}/submit-self")
    def perf_review_submit_self(rid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, sc = scoped(request)
        out = call(P.save_review, engine, tenant, sc, rid, {k: v for k, v in body.items() if k == "self"}, submit="self")
        hr.audit(engine, sc.who.user, "update", "hr_review", rid, "Öz değerlendirme teslim edildi")
        return out

    @app.post(B + "/reviews/{rid}/submit-manager")
    def perf_review_submit_manager(rid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, sc = scoped(request)
        out = call(P.save_review, engine, tenant, sc, rid, {k: v for k, v in body.items() if k == "manager"}, submit="manager")
        hr.audit(engine, sc.who.user, "update", "hr_review", rid, "Yönetici değerlendirmesi teslim edildi")
        return out

    for action in ("share", "comment", "approve", "reassign"):
        def make_r(act: str):
            def review_action(rid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
                engine, tenant, sc = scoped(request)
                out = call(P.review_action, engine, tenant, sc, rid, act, body)
                detail: dict[str, Any] = {"islem": act, "durum": out["state"]}
                if act == "comment":
                    detail["itiraz"] = out["objection"]
                hr.audit(engine, sc.who.user, "update", "hr_review", rid, "Değerlendirme", detail)
                return out
            review_action.__name__ = f"perf_review_{act}"
            return review_action
        app.post(B + "/reviews/{rid}/" + action)(make_r(action))

    @app.post(B + "/reviews/{rid}/rewrite")
    async def perf_review_rewrite(rid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Zeki AI yorumu yeniden yazar. Çalışan adı «[çalışan]», diğer adlar «[kişi]», iletişim ve özel nitelikli satırlar
        modele gitmeden maskelenir; dönen metinde «[çalışan]» yeniden adla doldurulur. Kaydetmez."""
        engine, tenant, sc = await run_in_threadpool(scoped, request)
        rv = await run_in_threadpool(call, P.get_review, engine, tenant, sc, rid, log_view=False)
        if not rv["can"]["rewrite"]:
            raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Yorumu yalnız değerlendiren yönetici yeniden yazdırır."})
        text = str(body.get("text") or "").strip()
        if not text:
            raise HTTPException(400, detail={"code": "HR", "message": "Yeniden yazılacak metin yok."})
        names = [e.display_name for e in sc.emp.values()]
        masked, counts = T.mask_text(text, names, keep=rv["employeeName"] or "", keep_as="[çalışan]")
        m = model("değerlendirme yorumu")
        out = (await run_in_threadpool(lambda: m.chat(T.rewrite_messages(masked), max_tokens=1500, temperature=0.2)) or "").strip()
        if not out:
            raise HTTPException(502, detail={"code": "HR_MODEL", "message": "Zeki AI metni yeniden yazamadı; yeniden deneyin."})
        first = (rv["employeeName"] or "").split(" ")[0]
        hr.audit(engine, sc.who.user, "run", "hr_review", rid, "Zeki AI yorum yeniden yazımı", {"maske": counts})
        return {"text": out.replace("[çalışan]", first or "[çalışan]"), "masked": counts}

    @app.post(B + "/reviews/{rid}/work-summary", status_code=201)
    async def perf_work_summary(rid: str, request: Request) -> dict[str, Any]:
        """İş kayıtları özeti (bilgi amaçlı): M2 görev sayıları + CRM sahiplik sayıları, dönem aralığında. Çalışan da görür."""
        engine, tenant, sc = await run_in_threadpool(scoped, request)
        rv = await run_in_threadpool(call, P.get_review, engine, tenant, sc, rid, log_view=False)
        if not rv["can"]["workSummary"]:
            raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "İş kayıtları özeti yalnız yöneticisi ve İK içindir."})
        e = sc.emp.get(rv["employeeId"])
        start, end = H.parse_date(rv["cycle"]["periodStart"], "Dönem"), H.parse_date(rv["cycle"]["periodEnd"], "Dönem")
        crm_id = (e.crm_systemuser_id if e else None) or None
        facts: dict[str, Any] = {"periodStart": start.isoformat(), "periodEnd": end.isoformat(),
                                 "editorial": await run_in_threadpool(S.editorial_facts, engine, tenant, crm_id, start, end)}
        if crm_id:
            try:
                from semantic_bridge import admin as admin_mod
                from semantic_bridge import hr_sources

                prefix = hr_sources.prefix(admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo")
                counts = await run_in_threadpool(lambda: S.crm_ownership(crm_run(), prefix, crm_id, start, end))
                facts["crm"] = {"available": True, **counts, "source": "new_projeBase/new_sozlesmeBase OwnerId"}
            except S.SourceError as ex:
                facts["crm"] = {"available": False, "reason": str(ex)}
        else:
            facts["crm"] = {"available": False, "reason": "Çalışanın CRM kullanıcısı bağlı değil."}
        out = await run_in_threadpool(P.save_work_summary, engine, tenant, sc.who.user, rv["employeeId"], rv["cycle"]["id"], start, end, facts)
        H.log_access(engine, tenant, sc.who.user, "calisan", rv["employeeId"], "goruntule", "iş kayıtları özeti")
        hr.audit(engine, sc.who.user, "create", "hr_work_summary", out["id"], "İş kayıtları özeti", {"calisan": rv["employeeId"]})
        return out

    # ------------------------------------------------------------------ zamanlayıcı

    @app.post(B + "/reminders/run-due")
    def perf_reminders(request: Request) -> dict[str, Any]:
        """Zamanlayıcı (her gün 08:30): açık dönemde son tarihe `HR_PERF_REMIND_DAYS` gün kala eksik sayılarını İK alıcılarına
        tek özet (kişi adı yok). Eşik ya da alıcı yoksa gönderim yok; dönem başına günde bir."""
        from semantic_bridge.budget_api import _send_mail

        hr.require_caller(request)
        engine, tenant = hr.system()
        P.ensure(engine)
        st, base = perf_settings(), hr.settings()
        items = P.due_reminders(engine, tenant, st["remindDays"])
        mail = "esik_yok" if not st["remindDays"] else "bos"
        if items:
            if base["alertRecipients"]:
                link = (hr.conf("ALERT_LINK") or "").split("/uyarilar")[0]
                mail = _send_mail(f"Değerlendirme dönemi: {len(items)} dönemde eksik var", P.reminder_text(items, f"{link}/ik/degerlendirme" if link else ""),
                                  base["alertRecipients"])
                if mail == "sent":
                    P.mark_reminded(engine, tenant, items)
            else:
                mail = "alici_yok"
        return {"remindDays": st["remindDays"], "cycles": len(items), "mail": mail, "recipients": len(base["alertRecipients"])}
