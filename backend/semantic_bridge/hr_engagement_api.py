"""M58 Çalışan deneyimi ve bağlılık uçları: /api/v1/hr/engagement/* ve oturumsuz anket formu /api/v1/hr/survey-public/*.

Sayfa kapısı `access.RULES` (`sayfa:ik-anketlerim`, `sayfa:ik-oneriler`, `sayfa:ik-baglilik`, `sayfa:ik-birimim`,
`sayfa:ik-anket-yonetimi`, `sayfa:ik-aksiyonlar`; hepsi açıkça verilir). Şirket geneli sonuç yalnız `sayfa:ik-baglilik`
ya da `ik.anket-yonet`; yorum metni yalnız `ik.anket-yorum` (duyarlı). `POST /run-due` yalnız zamanlayıcı.

Oturumsuz form (`/survey-public/{jeton}`) davet jetonu ya da basılı kodla çalışır; oturum çerezi aranmaz ve kişi hiçbir
yere yazılmaz. Nginx'te bu yol AD girişi (`auth_request`) dışında tutulur — kullanıcı onayıyla
(`deploy/nanobase-direct/add-hr-survey-public-route.py`). Onaylanana kadar form yalnız portal oturumuyla açılır.

Zeki AI: yorum teması ve öneri konusu (kapalı seçim, olasılıkla), tema özeti (alıntısız). Yalnız maskeli metin gider.
"""
from __future__ import annotations

import csv
import io
import logging
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import hr_core as H
from semantic_bridge import hr_engagement as E
from semantic_bridge import hr_kaynak as HK
from semantic_bridge import hr_engagement_text as T
from semantic_bridge.hr_api import HrContext

log = logging.getLogger("semantic_bridge.hr.engagement.api")
B = "/api/v1/hr/engagement"
PUB = "/api/v1/hr/survey-public"


# Sorgu bilgisi formülleri (hr_kaynak). Anket yanıtı sorgularında satır sayısı yazılmaz; eşik altı grup «gizli».
F_SORU = "Soru sayısı = anketin (ya da şablonun) madde listesindeki soru sayısı."
F_ANKET = ("Anket kaydı: gösterim eşiği (en az yanıt), soru sayısı, açılış/kapanış; sayılar portal kaydındandır. Kapanmış "
           "ankette davet ve yanıt sayıları kapanış anında dondurulur.")
F_ILERLEME = ("İlerleme: davet = gönderilen e-posta daveti, cevaplayan = yanıt veren davet; basılı kod = dağıtılan / kullanılan "
              "kod; yanıt oranı = (cevaplayan + kullanılan basılı kod) ÷ (davet + basılı kod). Yanıtlar kimliksiz saklanır.")
F_SONUC = ("Sonuç (anket kapanınca ve gösterim eşiği girilince): madde ortalaması = yanıtların 1–5 ortalaması, olumlu % = 4 ve 5 "
           "verenlerin payı, n = yanıt; eNPS = (9–10 verenler − 0–6 verenler) ÷ yanıt × 100; bağlılık endeksi = bağlılık "
           "maddelerinin olumlu payı. Birim, alt birimleriyle; yanıtı eşiğin altındaki ya da ayrı gösterilmesi başka birimi ele "
           "verecek birim üst birimle birleştirilir ve «gizli» kalır.")
F_TEMA = ("Tema: yorumların konusunu Zeki AI atar (kapalı küme); tema başına sayı = o temadaki yorum; eşik altı grupta tema "
          "gösterilmez. Yorum metinleri maskelenmiştir.")
F_EGILIM = ("Eğilim: her kapanmış anketin kapanışta saklanan şirket sonucu (yanıt oranı, eNPS, endeks); öneri sayacı = öneri "
            "kutusuna gelen, cevaplanan ve ortalama cevap süresi (gün).")
F_ONERI = "Öneri konusu: Zeki AI kapalı kümeden seçer; yüzde = modelin seçime verdiği olasılık. Öneri sahibi gösterilmez (anonim)."


def register(app, hr: HrContext) -> None:
    ctx, need, call = hr.ctx, hr.need, hr.call
    E.register_hooks()

    def ready(request: Request) -> tuple[Any, str, H.Who]:
        engine, tenant, who = ctx(request)
        E.ensure(engine)
        return engine, tenant, who

    def st() -> dict[str, Any]:
        return E.settings(hr.conf)

    def dashboard(who: H.Who) -> None:
        need(who, E.PAGE_DASHBOARD, E.F_SURVEY_ADMIN, what="Bağlılık panosu")

    def chooser():
        m = hr.llm("anket teması")
        return (lambda p, ch: m.choose(p, ch)) if m is not None and hasattr(m, "choose") else None

    def chatter():
        m = hr.llm("anket tema özeti")
        return (lambda msgs: m.chat(msgs, max_tokens=500, temperature=0.2)) if m is not None else None

    # ------------------------------------------------------------------ genel

    @app.get(B + "/meta")
    def eng_meta(request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        org = E.Org(engine, tenant)
        me = org.me(who.user)
        s = st()
        return {"kinds": E.KINDS, "qtypes": E.QTYPES, "templateStates": E.TEMPLATE_STATES, "surveyStates": E.SURVEY_STATES,
                "suggestionStates": E.SUGG_STATES, "actionStates": E.ACTION_STATES, "themes": s["themes"], "topics": s["topics"],
                "personalTopic": T.PERSONAL_TOPIC, "anonymity": E.ANONYMITY_TEXT, "modelVar": hr.llm("durum") is not None,
                "units": [{"id": u.id, "name": u.name, "parentId": u.parent_id} for u in sorted(org.units.values(), key=lambda x: x.name.casefold())],
                "me": {"username": who.user, "display": who.display, "employeeId": me.id if me else None,
                       "managedUnits": sorted(org.managed(who.user)),
                       "can": {"dashboard": who.can(E.PAGE_DASHBOARD, E.F_SURVEY_ADMIN), "surveys": who.can(E.F_SURVEY_ADMIN),
                               "unitResult": who.can(E.F_UNIT_RESULT), "comments": who.can(E.F_COMMENTS),
                               "suggestionAdmin": who.can(E.F_SUGG_ADMIN), "suggestionAnswer": who.can(E.F_SUGG_ANSWER),
                               "actions": who.can(E.F_ACTION), "export": who.can(E.F_EXPORT)}}}

    # ------------------------------------------------------------------ çalışan

    @app.get(B + "/me/surveys")
    def eng_my_surveys(request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        with HK.capture(engine) as got:
            out = {"items": E.my_surveys(engine, tenant, who.user)}
        return hr.kaynak(out, got, "anketim", {"items[]": ("soru", F_SORU)})

    @app.post(B + "/me/surveys/{sid}/link")
    def eng_my_link(sid: str, request: Request) -> dict[str, Any]:
        """Kişinin anket bağlantısı: jeton yenilenir, ham jeton bir kez döner (değişiklik kaydına yazılmaz: katılım izi olmasın)."""
        engine, tenant, who = ready(request)
        return {"token": call(E.issue_link, engine, tenant, who.user, sid)}

    # ------------------------------------------------------------------ oturumsuz form

    @app.get(PUB + "/{token}")
    def survey_public(token: str, request: Request) -> dict[str, Any]:
        hr.require_caller(request)
        engine, _ = hr.system()
        return call(E.public_form, engine, token)

    @app.post(PUB + "/{token}")
    def survey_public_submit(token: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Cevap. Kimlik, jeton ve saat cevaba yazılmaz; değişiklik kaydına da düşmez (kim cevapladı izi olmasın)."""
        hr.require_caller(request)
        engine, _ = hr.system()
        return call(E.submit_public, engine, token, body, delay_max=st()["shuffleMaxSec"])

    # ------------------------------------------------------------------ şablonlar

    @app.get(B + "/templates")
    def eng_templates(request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, E.F_SURVEY_ADMIN, what="Anket yönetimi")
        with HK.capture(engine) as got:
            out = {"items": E.list_templates(engine, tenant), "starters": T.STARTERS}
        return hr.kaynak(out, got, "sablon", {"items[]": ("soru", F_SORU)}, rest=("soru", F_SORU))

    @app.post(B + "/templates", status_code=201)
    def eng_template_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, E.F_SURVEY_ADMIN, what="Anket yönetimi")
        out, diff = call(E.save_template, engine, tenant, who.user, body)
        hr.audit(engine, who.user, "create", "hr_survey_template", out["id"], out["title"], diff)
        return out

    @app.patch(B + "/templates/{tid}")
    def eng_template_update(tid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, E.F_SURVEY_ADMIN, what="Anket yönetimi")
        out, diff = call(E.save_template, engine, tenant, who.user, body, tid)
        if diff:
            hr.audit(engine, who.user, "update", "hr_survey_template", tid, out["title"], diff)
        return out

    for action in ("submit", "approve", "reject", "archive"):
        def make_t(act: str):
            def tpl_action(tid: str, request: Request) -> dict[str, Any]:
                engine, tenant, who = ready(request)
                need(who, E.F_SURVEY_ADMIN, what="Anket yönetimi")
                out = call(E.template_transition, engine, tenant, who, tid, act)
                hr.audit(engine, who.user, "update", "hr_survey_template", tid, out["title"], {"islem": act, "durum": out["state"]})
                return out
            tpl_action.__name__ = f"eng_template_{act}"
            return tpl_action
        app.post(B + "/templates/{tid}/" + action)(make_t(action))

    # ------------------------------------------------------------------ anketler

    @app.get(B + "/surveys")
    def eng_surveys(request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        dashboard(who)
        with HK.capture(engine) as got:
            out = {"items": E.list_surveys(engine, tenant)}
        return hr.kaynak(out, got, "anketler", {"items[]": ("anket", F_ANKET)})

    @app.post(B + "/surveys", status_code=201)
    def eng_survey_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, E.F_SURVEY_ADMIN, what="Anket yönetimi")
        out, diff = call(E.save_survey, engine, tenant, who.user, body)
        hr.audit(engine, who.user, "create", "hr_survey", out["id"], out["title"], diff)
        return out

    @app.get(B + "/surveys/{sid}")
    def eng_survey(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        dashboard(who)
        with HK.capture(engine) as got:
            out = call(E.get_survey, engine, tenant, sid)
        return hr.kaynak(out, got, "anket", {}, rest=("anket", F_ANKET))

    @app.patch(B + "/surveys/{sid}")
    def eng_survey_update(sid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, E.F_SURVEY_ADMIN, what="Anket yönetimi")
        out, diff = call(E.save_survey, engine, tenant, who.user, body, sid)
        hr.audit(engine, who.user, "update", "hr_survey", sid, out["title"], diff)
        return out

    @app.post(B + "/surveys/{sid}/open")
    def eng_survey_open(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, E.F_SURVEY_ADMIN, what="Anket yönetimi")
        out = call(E.open_survey, engine, tenant, who.user, sid)
        hr.audit(engine, who.user, "update", "hr_survey", sid, out["title"], {"islem": "ac", "durum": out["state"], "davet": out["invited"]})
        return out

    @app.post(B + "/surveys/{sid}/close")
    def eng_survey_close(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, E.F_SURVEY_ADMIN, what="Anket yönetimi")
        out = call(E.close_survey, engine, tenant, who.user, sid)
        hr.audit(engine, who.user, "update", "hr_survey", sid, out["title"],
                 {"islem": "kapat", "davet": out["invited"], "cevap": out["responded"], "kagit": out["paperUsed"]})
        return out

    @app.post(B + "/surveys/{sid}/paper-codes")
    def eng_paper_codes(sid: str, request: Request, n: int = 0, unit: str = "") -> dict[str, Any]:
        """Bilgisayarsız çalışanlar için tek kullanımlık basılı kodlar. Kodlar yalnız bu cevapta; kişiye bağlanmaz."""
        engine, tenant, who = ready(request)
        need(who, E.F_SURVEY_ADMIN, what="Anket yönetimi")
        codes = call(E.paper_codes, engine, tenant, sid, n, unit or None)
        hr.audit(engine, who.user, "create", "hr_survey", sid, "Basılı anket kodları üretildi", {"adet": len(codes), "birim": unit or None})
        return {"codes": codes}

    @app.get(B + "/surveys/{sid}/progress")
    def eng_progress(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        dashboard(who)
        with HK.capture(engine) as got:
            out = call(E.progress, engine, tenant, sid)
        return hr.kaynak(out, got, "ilerleme", {}, rest=("ilerleme", F_ILERLEME))

    def sonuc(out: dict[str, Any], got: list) -> dict[str, Any]:
        """Anket sonucu: gösterilen rakamlar sonuç formülüne; eşik altı birim satırı «gizli»ye (sayı sızmaz)."""
        hidden = [f"units[]:{u['unitId']}" for u in (out.get("units") or []) if not u.get("shown")]
        return hr.kaynak(out, got, "sonuc", {"survey": ("anket", F_ANKET), "units": ("sonuc", F_SONUC)},
                         rest=("sonuc", F_SONUC), hidden=hidden)

    @app.get(B + "/surveys/{sid}/results")
    def eng_results(sid: str, request: Request, scope: str = "sirket") -> dict[str, Any]:
        engine, tenant, who = ready(request)
        if who.can(E.PAGE_DASHBOARD, E.F_SURVEY_ADMIN):
            with HK.capture(engine) as got:
                out = call(E.results, engine, tenant, sid, scope)
            return sonuc(out, got)
        # Birim yöneticisi: yalnız paylaşılmış ankette, yöneticisi olduğu birimler.
        need(who, E.F_UNIT_RESULT, what="Birim sonucu")
        s = call(E.get_survey, engine, tenant, sid)
        if not s["resultsSharedAt"]:
            raise HTTPException(403, detail={"code": "HR", "message": "Bu anketin birim sonuçları henüz paylaşılmadı."})
        managed = E.Org(engine, tenant).managed(who.user)
        if scope == "sirket" or scope not in managed:
            raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Yalnız yöneticisi olduğunuz birimin sonucunu görürsünüz."})
        with HK.capture(engine) as got:
            out = call(E.results, engine, tenant, sid, scope, allowed_units=managed)
        return sonuc(out, got)

    @app.get(B + "/surveys/{sid}/themes")
    def eng_themes(sid: str, request: Request, raw: int = 0) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        dashboard(who)
        if raw:
            need(who, E.F_COMMENTS, what="Yorum metinleri")
            H.log_access(engine, tenant, who.user, "anket", sid, "goruntule", "maskeli anket yorumları")
        with HK.capture(engine) as got:
            out = call(E.themes, engine, tenant, sid, raw=bool(raw))
        return hr.kaynak(out, got, "tema", {}, rest=("tema", F_TEMA))

    @app.post(B + "/surveys/{sid}/themes/refresh")
    async def eng_themes_refresh(sid: str, request: Request) -> dict[str, Any]:
        """Sınıflanmamış yorumları sınıflar ve tema özetlerini yeniden yazar (İK)."""
        engine, tenant, who = await run_in_threadpool(ready, request)
        need(who, E.F_SURVEY_ADMIN, what="Anket yönetimi")
        ch, chat = chooser(), chatter()
        if ch is None or chat is None:
            raise HTTPException(503, detail={"code": "HR_MODEL", "message": "Zeki AI bu kurulumda tanımlı değil."})
        n = await run_in_threadpool(E.classify_comments, engine, tenant, ch, st()["themes"])
        out = await run_in_threadpool(call, E.summarize_themes, engine, tenant, sid, chat)
        hr.audit(engine, who.user, "run", "hr_survey", sid, "Zeki AI tema özeti", {"siniflanan": n, "tema": len(out)})
        return {"classified": n, "themes": len(out)}

    @app.post(B + "/surveys/{sid}/share")
    def eng_share(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, E.F_SURVEY_ADMIN, what="Anket yönetimi")
        out = call(E.share_results, engine, tenant, who.user, sid)
        hr.audit(engine, who.user, "update", "hr_survey", sid, out["title"], {"islem": "birim sonuclari paylasildi"})
        return out

    @app.get(B + "/surveys/{sid}/export.csv")
    def eng_export(sid: str, request: Request) -> Response:
        engine, tenant, who = ready(request)
        dashboard(who)
        need(who, E.F_EXPORT, what="İK verisini dışa aktarma")
        rows = call(E.export_rows, engine, tenant, sid)
        buf = io.StringIO()
        csv.writer(buf, delimiter=";").writerows(rows)
        hr.audit(engine, who.user, "run", "hr_survey", sid, "Anket toplu sonucu dışa aktarıldı")
        return Response(content=("﻿" + buf.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="anket-{sid[-8:]}.csv"', "Cache-Control": "private, no-store"})

    @app.get(B + "/trend")
    def eng_trend(request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        dashboard(who)
        with HK.capture(engine) as got:
            out = {"items": E.trend(engine, tenant), "suggestions": E.suggestion_stats(engine, tenant)}
        return hr.kaynak(out, got, "egilim", {"items[]": ("egilim", F_EGILIM, ["semantic_hr_survey_results", "semantic_hr_surveys"]),
                                              "suggestions": ("oneriSay", F_EGILIM, ["semantic_hr_suggestions"])})

    @app.get(B + "/my-units")
    def eng_my_units(request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        need(who, E.F_UNIT_RESULT, what="Birim sonucu")
        with HK.capture(engine) as got:
            out = call(E.my_unit_results, engine, tenant, who.user)
        hidden = [f"results[]:{r['survey']['id']}:{r.get('scope')}" for r in out.get("results") or [] if r.get("suppressed")]
        return hr.kaynak(out, got, "birimim", {"results": ("sonuc", F_SONUC)}, hidden=hidden)

    # ------------------------------------------------------------------ öneriler

    @app.post(B + "/suggestions", status_code=201)
    def eng_suggestion_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Öneri. Adsızda yazar tutulmaz, değişiklik kaydında «anonim» görünür; takip kodu yalnız bu cevapta döner."""
        engine, tenant, who = ready(request)
        out = call(E.create_suggestion, engine, tenant, who.user, body)
        hr.audit(engine, "anonim" if out["anonymous"] else who.user, "create", "hr_suggestion", out["id"], "Çalışan önerisi")
        return out

    @app.get(B + "/suggestions")
    def eng_suggestions(request: Request, state: str = "") -> dict[str, Any]:
        engine, tenant, who = ready(request)
        with HK.capture(engine) as got:
            out = {"items": call(E.list_suggestions, engine, tenant, who, state=state), "topics": st()["topics"]}
        return hr.kaynak(out, got, "oneri", {"items[]": ("oneri", F_ONERI)})

    @app.get(B + "/suggestions/mine")
    def eng_suggestions_mine(request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        with HK.capture(engine) as got:
            out = {"items": E.my_suggestions(engine, tenant, who.user)}
        return hr.kaynak(out, got, "onerim", {"items[]": ("oneri", F_ONERI)})

    @app.get(B + "/suggestions/track/{code}")
    def eng_suggestion_track(code: str, request: Request) -> dict[str, Any]:
        engine, tenant, _ = ready(request)
        return call(E.track_suggestion, engine, tenant, code)

    for action in ("route", "topic", "answer", "close"):
        def make_s(act: str):
            def sugg_action(sgid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
                engine, tenant, who = ready(request)
                out = call(E.suggestion_action, engine, tenant, who, sgid, act, body, st()["topics"])
                hr.audit(engine, who.user, "update", "hr_suggestion", sgid, "Çalışan önerisi",
                         {"islem": act, "durum": out["state"], "birim": out["routedUnitId"]})
                return out
            sugg_action.__name__ = f"eng_suggestion_{act}"
            return sugg_action
        app.post(B + "/suggestions/{sgid}/" + action)(make_s(action))

    # ------------------------------------------------------------------ aksiyonlar

    @app.get(B + "/actions")
    def eng_actions(request: Request, survey: str = "") -> dict[str, Any]:
        engine, tenant, who = ready(request)
        return E.list_actions(engine, tenant, who, survey)

    @app.post(B + "/actions", status_code=201)
    def eng_action_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        out, diff = call(E.save_action, engine, tenant, who, body)
        hr.audit(engine, who.user, "create", "hr_action", out["id"], out["title"], diff)
        return out

    @app.patch(B + "/actions/{aid}")
    def eng_action_update(aid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, who = ready(request)
        out, diff = call(E.save_action, engine, tenant, who, body, aid)
        if diff:
            hr.audit(engine, who.user, "update", "hr_action", aid, out["title"], diff)
        return out

    # ------------------------------------------------------------------ zamanlayıcı

    @app.post(B + "/run-due")
    def eng_run_due(request: Request) -> dict[str, Any]:
        """Zamanlayıcı (15 dk): planlı anketi açar, tarihi geçeni kapatır, oryantasyon davetleri, tema/konu sınıflama,
        tema özeti. Kapanan anket için İK alıcılarına yalnız sayılar içeren tek e-posta."""
        from semantic_bridge.budget_api import _send_mail

        hr.require_caller(request)
        engine, tenant = hr.system()
        E.ensure(engine)
        out = E.run_due(engine, tenant, choose=chooser(), chat=chatter(), st=st())
        recipients = hr.settings()["alertRecipients"]
        if out["closed"] and recipients:
            lines = ["Kapanan anketler (yalnız toplamlar):", ""]
            for sid in out["closed"]:
                s = E.get_survey(engine, tenant, sid)
                reach = s["invited"] + s["paperIssued"]
                rate = f"%{round(100 * (s['responded'] + s['paperUsed']) / reach)}" if reach else "—"
                lines.append(f"- {s['title']}: davet {s['invited']}, basılı kod {s['paperIssued']}, yanıt oranı {rate}"
                             + ("" if s["minGroup"] else " — gösterim eşiği girilmedi, sonuç görünmüyor"))
            out["mail"] = _send_mail(f"Anket kapandı: {len(out['closed'])}", "\n".join(lines), recipients)
        return out

